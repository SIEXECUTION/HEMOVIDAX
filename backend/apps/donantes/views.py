"""API del circuito de donación, desde el prefiltro hasta el refrigerio."""

from uuid import uuid4
from datetime import timedelta
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView
from .models import (
    Persona,
    PosibleDonador,
    CitaDonacion,
    RequisitoDonacion,
    DetalleCitaRequisito,
    TriajeClinico,
    Diferimiento,
    Donante,
    ExtraccionDonacion,
    ConsentimientoInformado,
    IncentivoEntrega,
)
from .services import (
    card,
    access_person,
    block_if_ineligible,
    has_reactive,
    appointment_phase,
)
from apps.inventario.models import GrupoSanguineo, UnidadSangreTotal
from apps.seguridad.models import PersonalSalud
from apps.seguridad.permissions import ClinicalRole, IsHealthStaffRole
from apps.seguridad.views import audit


class DonanteCarnetDigitalView(APIView):
    def get(self, request, ci):
        p = Persona.objects.filter(
            Q(ci__iexact=ci)
            | Q(donante__carnetdigitalcodigo__iexact=ci)
            | Q(posible_donador__carnetprovisionalcodigo__iexact=ci)
        ).first()
        if not p:
            return Response({"detail": "No se encontró la persona."}, status=404)
        access_person(request, p)
        return Response(card(p))


class CarnetDigitalQRView(APIView):
    def get(self, request, idpersona):
        p = get_object_or_404(Persona, pk=idpersona)
        access_person(request, p)
        return Response(card(p))


class RequisitosView(APIView):
    def get(self, request):
        return Response(
            list(
                RequisitoDonacion.objects.values(
                    "idrequisito",
                    "nombrerequisito",
                    "tiporequisito",
                    "esexcluyentedefinitivo",
                )
            )
        )


class AnswerSerializer(serializers.Serializer):
    idrequisito = serializers.PrimaryKeyRelatedField(
        queryset=RequisitoDonacion.objects.all()
    )
    cumplerequisito = serializers.BooleanField()
    observacion = serializers.CharField(
        max_length=200, required=False, allow_blank=True
    )


class AppointmentSerializer(serializers.Serializer):
    idpersona = serializers.PrimaryKeyRelatedField(queryset=Persona.objects.all())
    fechahoraprogramada = serializers.DateTimeField()
    requisitos = AnswerSerializer(many=True)

    def validate_fechahoraprogramada(self, value):
        if value <= timezone.now():
            raise serializers.ValidationError("Selecciona una fecha futura.")
        return value


def appointment_data(c):
    return {
        "idcita": c.pk,
        "idpersona": c.idpersona_id,
        "persona": c.idpersona.nombreCompleto,
        "ci": c.idpersona.ci,
        "fechahoraprogramada": c.fechahoraprogramada,
        "prefiltroaprobado": c.prefiltroaprobado,
        "asistenciaconfirmada": c.asistenciaconfirmada,
        "estadocita": c.estadocita,
        "fase": appointment_phase(c.idpersona),
    }


class AgendarCitaDonacionView(APIView):
    def get(self, request):
        qs = CitaDonacion.objects.select_related("idpersona").all()
        if not IsHealthStaffRole().has_permission(request, self):
            qs = qs.filter(idpersona_id=request.user.idpersona_id)
        return Response([appointment_data(c) for c in qs[:500]])

    @transaction.atomic
    def post(self, request):
        data = dict(request.data)
        data["idpersona"] = data.get("idpersona") or data.get("idposibledonador")
        s = AppointmentSerializer(data=data)
        s.is_valid(raise_exception=True)
        d = s.validated_data
        p = Persona.objects.select_for_update().get(pk=d["idpersona"].pk)
        access_person(request, p)
        block_if_ineligible(p)
        if has_reactive(p):
            raise serializers.ValidationError(
                "Antecedente serológico no apto. Requiere evaluación médica."
            )
        expected = set(RequisitoDonacion.objects.values_list("idrequisito", flat=True))
        answers = d["requisitos"]
        ids = [a["idrequisito"].pk for a in answers]
        if not expected or set(ids) != expected or len(ids) != len(expected):
            raise serializers.ValidationError(
                "Debes responder una vez cada requisito del catálogo vigente."
            )
        if CitaDonacion.objects.filter(idpersona=p, estadocita="Programada").exists():
            raise serializers.ValidationError(
                "Ya existe una cita programada. Cancélala antes de agendar otra."
            )
        possible, _ = PosibleDonador.objects.get_or_create(
            idpersona=p, defaults={"carnetprovisionalcodigo": f"HV-POST-{p.pk:08d}"}
        )
        failed = [a["idrequisito"] for a in answers if not a["cumplerequisito"]]
        approved = not failed
        possible.estadoaptitud = "En Evaluacion" if approved else "No Apto"
        possible.save(update_fields=["estadoaptitud"])
        c = CitaDonacion.objects.create(
            idpersona=p,
            fechahoraprogramada=d["fechahoraprogramada"],
            prefiltroaprobado=approved,
            estadocita="Programada" if approved else "Cancelada",
        )
        DetalleCitaRequisito.objects.bulk_create(
            [
                DetalleCitaRequisito(
                    idcita=c,
                    idrequisito=a["idrequisito"],
                    cumplerequisito=a["cumplerequisito"],
                    observacionrespuesta=a.get("observacion", ""),
                )
                for a in answers
            ]
        )
        audit(
            request,
            "Prefiltro aprobado y cita agendada" if approved else "Prefiltro rechazado",
            "CitaDonacion",
            c.pk,
        )
        result = appointment_data(c)
        result["motivos_exclusion"] = [
            {"motivo": r.nombrerequisito, "definitivo": r.esexcluyentedefinitivo}
            for r in failed
        ]
        return Response(result, status=201)


class CancelarCitaView(APIView):
    @transaction.atomic
    def post(self, request, pk):
        c = get_object_or_404(CitaDonacion.objects.select_for_update(), pk=pk)
        access_person(request, c.idpersona)
        if c.estadocita != "Programada" or c.asistenciaconfirmada:
            raise serializers.ValidationError(
                "Esta cita ya no se puede cancelar desde el portal."
            )
        c.estadocita = "Cancelada"
        c.save(update_fields=["estadocita"])
        audit(request, "Cita cancelada", "CitaDonacion", c.pk)
        return Response(appointment_data(c))


class AdmisionView(APIView):
    permission_classes = [ClinicalRole]
    allowed_roles = ["ADMIN", "PERS_COLECTA"]

    @transaction.atomic
    def post(self, request, pk):
        c = get_object_or_404(
            CitaDonacion.objects.select_for_update(), pk=pk, estadocita="Programada"
        )
        p = Persona.objects.select_for_update().get(pk=c.idpersona_id)
        block_if_ineligible(p)
        if not c.prefiltroaprobado:
            raise serializers.ValidationError("Debe aprobar el prefiltro.")
        c.asistenciaconfirmada = True
        c.save(update_fields=["asistenciaconfirmada"])
        tr = (
            TriajeClinico.objects.filter(idposibledonador_id=p.pk)
            .order_by("-fechahora")
            .first()
        )
        authorized = bool(
            tr
            and tr.resultadoaptitud == "Apto"
            and timezone.localtime(tr.fechahora).date() == timezone.localdate()
            and not has_reactive(p)
        )
        audit(
            request,
            "Asistencia confirmada; "
            + ("pase a extracción" if authorized else "derivación al área médica"),
            "CitaDonacion",
            c.pk,
        )
        return Response(
            {
                "asistenciaconfirmada": True,
                "autoriza_flebotomia": authorized,
                "idtriaje": tr.pk if authorized else None,
                "mensaje": "Pase autorizado."
                if authorized
                else "Debe pasar al área médica para evaluación.",
            }
        )


class TriageSerializer(serializers.Serializer):
    idpersona = serializers.PrimaryKeyRelatedField(queryset=Persona.objects.all())
    pesokg = serializers.DecimalField(max_digits=5, decimal_places=2, min_value=1)
    temperatura = serializers.DecimalField(
        max_digits=4, decimal_places=1, min_value=30, max_value=45
    )
    hemoglobina = serializers.DecimalField(max_digits=4, decimal_places=1, min_value=1)
    presionsistolica = serializers.IntegerField(min_value=1, max_value=300)
    presiondiastolica = serializers.IntegerField(min_value=1, max_value=200)
    motivodiferimiento = serializers.CharField(
        max_length=255, required=False, allow_blank=True
    )
    diasinhabilitacion = serializers.IntegerField(
        min_value=1, max_value=36500, default=30
    )
    definitivo = serializers.BooleanField(default=False)


def staff(request):
    return get_object_or_404(PersonalSalud, pk=request.user.idpersona_id)


class ProcesarTriajeClinicoView(APIView):
    permission_classes = [ClinicalRole]
    allowed_roles = ["ADMIN", "DOC_TRIAJE"]

    @transaction.atomic
    def post(self, request):
        data = dict(request.data)
        data["idpersona"] = data.get("idpersona") or data.get("idposibledonador")
        s = TriageSerializer(data=data)
        s.is_valid(raise_exception=True)
        d = s.validated_data
        p = Persona.objects.select_for_update().get(pk=d["idpersona"].pk)
        c = CitaDonacion.objects.filter(
            idpersona=p, estadocita="Programada", asistenciaconfirmada=True
        ).first()
        if not c:
            raise serializers.ValidationError(
                "Debe confirmar la asistencia a una cita antes del triaje."
            )
        possible, _ = PosibleDonador.objects.get_or_create(
            idpersona=p, defaults={"carnetprovisionalcodigo": f"HV-POST-{p.pk:08d}"}
        )
        approved = (
            d["pesokg"] >= 50
            and d["temperatura"] <= 37.5
            and d["hemoglobina"] >= 12.5
            and not d.get("motivodiferimiento")
            and not d["definitivo"]
        )
        # El dictamen médico se complementa con las restricciones persistentes.
        if approved:
            block_if_ineligible(p)
            if has_reactive(p):
                raise serializers.ValidationError(
                    "Existe serología no apta; no se puede autorizar extracción."
                )
        tr = TriajeClinico.objects.create(
            idposibledonador=possible,
            idpersonalsalud=staff(request),
            pesokg=d["pesokg"],
            temperatura=d["temperatura"],
            nivelhemoglobina=d["hemoglobina"],
            presionsistolicammhg=d["presionsistolica"],
            presiondiastolicammhg=d["presiondiastolica"],
            resultadoaptitud="Apto" if approved else "Rechazado",
        )
        if not approved:
            today = timezone.localdate()
            Diferimiento.objects.create(
                idtriaje=tr,
                idposibledonador=possible,
                motivodetallado=d.get("motivodiferimiento")
                or "No cumple parámetros del triaje",
                diasinhabilitacion=d["diasinhabilitacion"],
                fechainiciodiferimiento=today,
                fechafindiferimiento=None
                if d["definitivo"]
                else today + timedelta(days=d["diasinhabilitacion"]),
            )
            Donante.objects.filter(pk=p.pk).update(
                estadohabilitacion="Diferido Definitivo"
                if d["definitivo"]
                else "Diferido Temporal"
            )
        possible.estadoaptitud = "Apto" if approved else "No Apto"
        possible.save(update_fields=["estadoaptitud"])
        audit(
            request, f"Triaje registrado: {tr.resultadoaptitud}", "TriajeClinico", tr.pk
        )
        return Response(
            {"idtriaje": tr.pk, "resultadoaptitud": tr.resultadoaptitud}, status=201
        )


class ExtractionSerializer(serializers.Serializer):
    idpersonadonante = serializers.PrimaryKeyRelatedField(
        queryset=Persona.objects.all()
    )
    idtriaje = serializers.PrimaryKeyRelatedField(queryset=TriajeClinico.objects.all())
    idgrupo = serializers.PrimaryKeyRelatedField(queryset=GrupoSanguineo.objects.all())
    volumenml = serializers.IntegerField(min_value=1, max_value=1000)
    brazo = serializers.ChoiceField(choices=["Izquierdo", "Derecho"])
    declaracionjuradaaceptada = serializers.BooleanField()
    firmadigital = serializers.CharField(max_length=20000)


class RegistrarFlebotomiaFraccionamientoView(APIView):
    permission_classes = [ClinicalRole]
    allowed_roles = ["ADMIN", "PERS_COLECTA"]

    @transaction.atomic
    def post(self, request):
        s = ExtractionSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        d = s.validated_data
        p = Persona.objects.select_for_update().get(pk=d["idpersonadonante"].pk)
        tr = TriajeClinico.objects.select_for_update().get(pk=d["idtriaje"].pk)
        block_if_ineligible(p)
        if (
            tr.idposibledonador_id != p.pk
            or tr.resultadoaptitud != "Apto"
            or timezone.localtime(tr.fechahora).date() != timezone.localdate()
        ):
            raise serializers.ValidationError(
                "Se requiere triaje aprobado de esta persona en la fecha actual."
            )
        latest = (
            TriajeClinico.objects.filter(idposibledonador_id=p.pk)
            .order_by("-fechahora", "-idtriaje")
            .first()
        )
        if latest.pk != tr.pk or has_reactive(p):
            raise serializers.ValidationError(
                "Debe utilizar el último triaje vigente y no tener serología no apta."
            )
        if ExtraccionDonacion.objects.filter(idtriaje=tr).exists():
            raise serializers.ValidationError(
                "Este triaje ya tiene una extracción registrada."
            )
        c = CitaDonacion.objects.filter(
            idpersona=p, estadocita="Programada", asistenciaconfirmada=True
        ).first()
        if not c or not d["declaracionjuradaaceptada"]:
            raise serializers.ValidationError(
                "Se requiere asistencia confirmada y consentimiento aceptado."
            )
        ext = ExtraccionDonacion.objects.create(
            idpersonadonante=p,
            idpersonalsalud=staff(request),
            idtriaje=tr,
            codigoextraccion=f"EXT-{uuid4().hex[:20]}",
            volumenextraidoml=d["volumenml"],
            brazoextraccion=d["brazo"],
        )
        ConsentimientoInformado.objects.create(
            idextraccion=ext,
            declaracionjuradaaceptada=True,
            firmadigital=d["firmadigital"],
        )
        mother = UnidadSangreTotal.objects.create(
            idextraccion=ext,
            idgrupo=d["idgrupo"],
            codigobolsamadre=f"MAD-{uuid4().hex[:20]}",
            tipobolsa="Bolsa Cuadruple CPD-SAGM",
            estadoliberacion="En Cuarentena",
        )
        Donante.objects.filter(pk=p.pk).update(fechaultimadonacion=timezone.localdate())
        c.estadocita = "Atendida"
        c.save(update_fields=["estadocita"])
        audit(
            request,
            "Extracción y consentimiento registrados; bolsa madre en cuarentena",
            "ExtraccionDonacion",
            ext.pk,
        )
        return Response(
            {
                "extraccion": {
                    "idextraccion": ext.pk,
                    "codigoextraccion": ext.codigoextraccion,
                },
                "unidadmadre": {
                    "idunidadmadre": mother.pk,
                    "codigobolsamadre": mother.codigobolsamadre,
                },
                "bolsas": [],
            },
            status=201,
        )


class RefrigerioView(APIView):
    permission_classes = [ClinicalRole]
    allowed_roles = ["ADMIN", "PERS_COLECTA"]

    @transaction.atomic
    def post(self, request, pk):
        ext = get_object_or_404(ExtraccionDonacion.objects.select_for_update(), pk=pk)
        if (
            ext.volumenextraidoml <= 0
            or not ConsentimientoInformado.objects.filter(idextraccion=ext).exists()
        ):
            raise serializers.ValidationError(
                "No existe extracción efectiva con consentimiento."
            )
        if IncentivoEntrega.objects.filter(idextraccion=ext).exists():
            raise serializers.ValidationError("El refrigerio ya está registrado.")
        article = request.data.get("tipoarticulo", "Refrigerio nutricional")
        if not isinstance(article, str) or not article.strip() or len(article) > 80:
            raise serializers.ValidationError(
                "Indica el artículo entregado (máximo 80 caracteres)."
            )
        item = IncentivoEntrega.objects.create(
            idextraccion=ext, tipoarticulo=article, refrigerioentregado=True
        )
        audit(request, "Refrigerio entregado", "IncentivoEntrega", item.pk)
        return Response(
            {"idincentivo": item.pk, "refrigerioentregado": True}, status=201
        )
