"""Reglas compartidas de elegibilidad y trazabilidad de donantes."""

from datetime import timedelta
from django.db.models import Q
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError
from .models import (
    Donante,
    PosibleDonador,
    Diferimiento,
    ExtraccionDonacion,
    AnalisisInmunoHematologico,
    AnalisisInmunoSerologico,
    CompromisoDonacion,
)


def eligible(person):
    today = timezone.localdate()
    donor = Donante.objects.filter(pk=person.pk).first()
    deferred = (
        Diferimiento.objects.filter(idposibledonador_id=person.pk)
        .filter(
            Q(fechafindiferimiento__gte=today) | Q(fechafindiferimiento__isnull=True)
        )
        .first()
    )
    interval = 90 if person.sexo == "M" else 120
    # La extracción es la fuente efectiva aun si el trigger de ascenso acaba de ejecutarse.
    last = (
        ExtraccionDonacion.objects.filter(idpersonadonante=person)
        .order_by("-fechahora")
        .first()
    )
    last_date = timezone.localtime(last.fechahora).date() if last else None
    if donor and donor.fechaultimadonacion:
        last_date = (
            max(last_date, donor.fechaultimadonacion)
            if last_date
            else donor.fechaultimadonacion
        )
    next_date = last_date + timedelta(days=interval) if last_date else today
    remaining = max(0, (next_date - today).days)
    recovery = max(0, min(100, round(100 * (interval - remaining) / interval)))
    reason = ""
    if donor and donor.estadohabilitacion == "Diferido Definitivo":
        reason = "Diferimiento definitivo."
    elif deferred:
        reason = f"{deferred.motivodetallado}. Hasta: {deferred.fechafindiferimiento or 'indefinido'}."
    elif remaining:
        reason = f"Descanso biológico pendiente: {remaining} días."
    return {
        "apto": not reason,
        "motivo": reason,
        "dias_restantes": remaining,
        "intervalo_dias": interval,
        "porcentaje_recuperacion": recovery,
        "proxima_fecha": next_date,
        "suspendido_hasta": deferred.fechafindiferimiento if deferred else None,
        "semaforo": "Rojo"
        if deferred or (donor and donor.estadohabilitacion == "Diferido Definitivo")
        else ("Amarillo" if remaining else "Verde"),
    }


def access_person(request, person):
    from apps.seguridad.permissions import IsHealthStaffRole

    if (
        request.user.idpersona_id != person.pk
        and not IsHealthStaffRole().has_permission(request, None)
    ):
        raise PermissionDenied("Solo puedes consultar tus propios datos.")


def card(person):
    donor = Donante.objects.filter(pk=person.pk).first()
    candidate = PosibleDonador.objects.filter(pk=person.pk).first()
    lab = (
        AnalisisInmunoHematologico.objects.filter(
            Q(idposibledonador_id=person.pk)
            | Q(idunidadmadre__idextraccion__idpersonadonante_id=person.pk)
        )
        .order_by("-fechaanalisis")
        .first()
    )
    state = eligible(person)
    extractions = list(
        ExtraccionDonacion.objects.filter(idpersonadonante=person).values(
            "idextraccion",
            "codigoextraccion",
            "fechahora",
            "volumenextraidoml",
            "brazoextraccion",
        )
    )
    commitments = list(
        CompromisoDonacion.objects.filter(iddonante_id=person.pk).values(
            "idcompromiso",
            "fechacompromiso",
            "estadocompromiso",
            "donacionconcretada",
            "volumendonadoefectivoml",
        )
    )
    code = (
        donor.carnetdigitalcodigo
        if donor
        else (candidate.carnetprovisionalcodigo if candidate else "")
    )
    group = (
        f"{lab.grupoaboconfirmado}{'+' if lab.factorrhconfirmado == 'Positivo' else '-'}"
        if lab
        else "Pendiente de tipificación"
    )
    return {
        "idpersona": person.pk,
        "ci": person.ci,
        "nombres": person.nombres,
        "apellidos": person.apellidos,
        "nombre_completo": person.nombreCompleto,
        "carnet_codigo": code,
        "grupo_sanguineo": group,
        "esPosibleDonador": not bool(donor),
        "tieneanalisis": candidate.tieneanalisis if candidate else False,
        "estado_habilitacion": (
            "Diferido Definitivo"
            if donor.estadohabilitacion == "Diferido Definitivo"
            else ("Diferido Temporal" if state["semaforo"] == "Rojo" else "Apto")
        )
        if donor
        else (candidate.estadoaptitud if candidate else "Sin evaluación"),
        "elegibilidad": state,
        "historial_donaciones": extractions,
        "historial_reposiciones": commitments,
        "total_donaciones": len(extractions),
        "volumen_total_aportado_ml": sum(e["volumenextraidoml"] for e in extractions),
        "qr_validation_string": code,
    }


def block_if_ineligible(person):
    state = eligible(person)
    if not state["apto"]:
        raise ValidationError(state["motivo"])


def has_reactive(person):
    return AnalisisInmunoSerologico.objects.filter(
        idunidadmadre__idextraccion__idpersonadonante=person, dictamenfinal="No Apto"
    ).exists()


def appointment_phase(person):
    lab = (
        AnalisisInmunoHematologico.objects.filter(idposibledonador_id=person.pk)
        .order_by("-fechaanalisis")
        .first()
    )
    serology = (
        AnalisisInmunoSerologico.objects.filter(
            idunidadmadre__idextraccion__idpersonadonante=person
        )
        .order_by("-fechaanalisis")
        .first()
    )
    approved = (
        lab and (lab.dictameninmunohematologico or "").strip().lower() == "apto"
    ) or (serology and serology.dictamenfinal == "Apto")
    return (
        "Extracción" if approved and not has_reactive(person) else "Evaluación previa"
    )
