"""Autenticación, cuentas institucionales y auditoría persistente."""

import math
from datetime import timedelta, date, datetime, time
from django.core import signing
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction, IntegrityError, connection
from django.db.models import Q, Func, Value, F, DateTimeField
from django.db.models.functions import ExtractHour
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.crypto import salted_hmac, constant_time_compare
from rest_framework import serializers
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from .models import Usuario, Rol, UsuarioRol, PersonalSalud, BitacoraAuditoria
from .permissions import IsAdminRole
from .serializers import (
    AutoRegistroPosibleDonadorSerializer,
    CrearPersonalSaludSerializer,
    PersonalSaludListSerializer,
    BitacoraAuditoriaSerializer,
)
from .utils import (
    generate_tokens_for_usuario,
    get_client_ip,
    registrar_auditoria,
    enviar_correo_institucional,
)
from .validators import validate_password_complexity


def audit(request, action, table, record, user=None):
    role = request.headers.get("X-Active-Role")
    if user is not None and role and not user.roles.filter(codigorol=role).exists():
        role = "Sistema"
    return registrar_auditoria(
        user or request.user, action, table, record, get_client_ip(request), role
    )


def account_data(user):
    p = user.idpersona
    roles = [
        {"id": r.idrol, "codigo": r.codigorol, "nombre": r.nombrerol}
        for r in user.roles.all()
    ]
    return {
        "idUsuario": user.idusuario,
        "username": user.username,
        "email": user.email,
        "estado": user.estado,
        "roles": roles,
        "persona": (
            {
                "idPersona": p.pk,
                "ci": p.ci,
                "nombres": p.nombres,
                "apellidos": p.apellidos,
                "nombreCompleto": p.nombreCompleto,
                "sexo": p.sexo,
                "fechaNacimiento": p.fechanacimiento,
            }
            if p
            else None
        ),
    }


class AutenticarUsuarioView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    @transaction.atomic
    def post(self, request):
        identifier = str(
            request.data.get("identificador") or request.data.get("username") or ""
        ).strip()
        password = request.data.get("password", "")
        user = (
            Usuario.objects.select_for_update()
            .filter(Q(username__iexact=identifier) | Q(email__iexact=identifier))
            .first()
        )
        if not user:
            return Response({"detail": "Credenciales inválidas."}, status=401)
        if user.estado in ("Bloqueado", "Inactivo"):
            return Response(
                {"detail": f"Cuenta {user.estado}. Contacte al Administrador."},
                status=403,
            )
        now = timezone.now()
        until = user.fechabloqueohasta
        if until and timezone.is_naive(until):
            until = timezone.make_aware(until)
        if until and until > now:
            return Response(
                {
                    "detail": f"Cuenta bloqueada por {math.ceil((until - now).total_seconds() / 60)} minuto(s).",
                    "bloqueado_hasta": until,
                },
                status=403,
            )
        if user.estado == "Bloqueado Temporal":
            user.estado, user.intentosfallidos, user.fechabloqueohasta = (
                "Activo",
                0,
                None,
            )
        if not user.check_password(password):
            user.intentosfallidos += 1
            if user.intentosfallidos >= 3:
                user.totalbloqueosrecibidos += 1
                minutes = (15, 30, 60)[min(user.totalbloqueosrecibidos - 1, 2)]
                user.estado = "Bloqueado Temporal"
                user.fechabloqueohasta = now + timedelta(minutes=minutes)
                user.save()
                audit(
                    request,
                    f"Bloqueo temporal progresivo ({minutes} min)",
                    "Usuario",
                    user.pk,
                    user,
                )
                return Response(
                    {"detail": f"Cuenta bloqueada por {minutes} minutos."}, status=403
                )
            user.save()
            audit(request, "Intento de acceso fallido", "Usuario", user.pk, user)
            return Response(
                {
                    "detail": f"Contraseña incorrecta. Intentos restantes: {3 - user.intentosfallidos}."
                },
                status=401,
            )
        user.estado, user.intentosfallidos, user.fechabloqueohasta = "Activo", 0, None
        user.save()
        data = account_data(user)
        tokens = generate_tokens_for_usuario(user)
        audit(request, "Inicio de Sesión Exitoso", "Usuario", user.pk, user)
        return Response(
            {
                "usuarioId": user.pk,
                "idusuario": user.pk,
                "idpersona": user.idpersona_id,
                "nombreCompleto": user.idpersona.nombreCompleto
                if user.idpersona
                else user.username,
                "rolesDisponibles": data["roles"],
                "roles": data["roles"],
                "requiere_selector_rol": len(data["roles"]) > 1,
                "usuario": data,
                "tokens": tokens,
                "token": tokens["access"],
            }
        )


LoginView = AutenticarUsuarioView


class MiCuentaView(APIView):
    def get(self, request):
        return Response(account_data(request.user))


class DesbloquearUsuarioAdminView(APIView):
    permission_classes = [IsAdminRole]

    @transaction.atomic
    def post(self, request, idusuario_objetivo):
        user = get_object_or_404(
            Usuario.objects.select_for_update(), pk=idusuario_objetivo
        )
        if user.estado in ("Bloqueado", "Inactivo"):
            return Response(
                {
                    "detail": "La suspensión administrativa requiere revisar el estado de la cuenta."
                },
                status=409,
            )
        user.estado, user.intentosfallidos, user.fechabloqueohasta = "Activo", 0, None
        user.save()
        audit(request, "Desbloqueo manual de cuenta", "Usuario", user.pk)
        return Response({"mensaje": "Cuenta rehabilitada."})


class AutoRegistroPosibleDonadorView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        s = AutoRegistroPosibleDonadorSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        try:
            with transaction.atomic():
                user = s.save()
                audit(request, "Auto-registro de postulante", "Usuario", user.pk, user)
        except IntegrityError:
            raise serializers.ValidationError(
                "La identidad, correo o usuario ya está registrado."
            )
        return Response(
            {
                "success": True,
                "message": "Registro completado. Ya puedes iniciar sesión.",
                "usuario": account_data(user),
            },
            status=201,
        )


class CrearPersonalSaludView(APIView):
    permission_classes = [IsAdminRole]

    def post(self, request):
        s = CrearPersonalSaludSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        try:
            with transaction.atomic():
                user = s.create_for_admin(request.user, s.validated_data)
                audit(request, "Alta de personal de salud", "Usuario", user.pk)
        except IntegrityError:
            raise serializers.ValidationError(
                "La persona, matrícula, correo o usuario ya está registrado."
            )
        return Response({"success": True, "usuario": account_data(user)}, status=201)


class PersonalSaludListView(APIView):
    permission_classes = [IsAdminRole]

    def get(self, request):
        qs = PersonalSalud.objects.select_related(
            "persona", "persona__usuario"
        ).prefetch_related("persona__usuario__roles")
        return Response(PersonalSaludListSerializer(qs, many=True).data)


class UsuarioEstadoUpdateView(APIView):
    permission_classes = [IsAdminRole]

    def get(self, request, pk=None):
        return Response(
            [
                account_data(u)
                for u in Usuario.objects.select_related("idpersona").prefetch_related(
                    "roles"
                )
            ]
        )

    @transaction.atomic
    def patch(self, request, pk):
        user = get_object_or_404(Usuario.objects.select_for_update(), pk=pk)
        state = request.data.get("estado")
        if state not in ("Activo", "Inactivo", "Bloqueado"):
            raise serializers.ValidationError("Estado inválido.")
        if user.pk == request.user.pk and state != "Activo":
            raise serializers.ValidationError("No puedes suspender tu propia cuenta.")
        user.estado = state
        if state == "Activo":
            user.intentosfallidos, user.fechabloqueohasta = 0, None
        user.save()
        audit(request, f"Estado de cuenta: {state}", "Usuario", user.pk)
        return Response(account_data(user))


class SolicitudCargoView(APIView):
    def get(self, request):
        qs = BitacoraAuditoria.objects.filter(
            tablaafectada="PersonalSalud",
            accionrealizada__startswith="Solicitud de cargo:",
        )
        if not IsAdminRole().has_permission(request, self):
            qs = qs.filter(idusuario=request.user)
        resolved = set(
            BitacoraAuditoria.objects.filter(
                tablaafectada="SolicitudCargo"
            ).values_list("idregistroafectado", flat=True)
        )
        result = []
        for event in qs.select_related("idusuario__idpersona"):
            p = PersonalSalud.objects.filter(pk=event.idregistroafectado).first()
            result.append(
                {
                    "id": event.pk,
                    "usuario": event.idusuario.username,
                    "cargo": p.cargo if p else "",
                    "registroprofesional": p.registroprofesional if p else "",
                    "codigo": event.accionrealizada.split(":", 1)[1],
                    "pendiente": event.pk not in resolved,
                }
            )
        return Response(result)

    @transaction.atomic
    def post(self, request):
        user = get_object_or_404(
            Usuario.objects.select_for_update(), pk=request.user.pk
        )
        if not user.idpersona_id:
            raise serializers.ValidationError(
                "La cuenta debe tener una persona asociada."
            )
        code = request.data.get("codigo", "")
        if code not in (
            "DOC_TRIAJE",
            "PERS_COLECTA",
            "BIOQ_INTEGRAL",
            "TEC_LOGISTICA",
            "MED_SOLICITANTE",
        ):
            raise serializers.ValidationError("Cargo no disponible para solicitud.")
        if user.roles.filter(codigorol=code).exists():
            raise serializers.ValidationError("Ya tienes asignado este perfil.")
        previous = BitacoraAuditoria.objects.filter(
            idusuario=user,
            tablaafectada="PersonalSalud",
            accionrealizada=f"Solicitud de cargo:{code}",
        )
        resolved = BitacoraAuditoria.objects.filter(
            tablaafectada="SolicitudCargo"
        ).values_list("idregistroafectado", flat=True)
        if previous.exclude(idauditoria__in=resolved).exists():
            raise serializers.ValidationError(
                "Ya hay una solicitud pendiente para este perfil."
            )
        s = type(
            "Cargo",
            (serializers.Serializer,),
            {
                "cargo": serializers.CharField(max_length=80),
                "registroprofesional": serializers.CharField(max_length=40),
            },
        )(data=request.data)
        s.is_valid(raise_exception=True)
        if PersonalSalud.objects.filter(pk=user.idpersona_id).exists():
            p = PersonalSalud.objects.get(pk=user.idpersona_id)
            if (p.cargo, p.registroprofesional) != (
                s.validated_data["cargo"],
                s.validated_data["registroprofesional"],
            ):
                raise serializers.ValidationError(
                    "Los datos deben coincidir con la acreditación profesional registrada."
                )
        else:
            if PersonalSalud.objects.filter(
                registroprofesional=s.validated_data["registroprofesional"]
            ).exists():
                raise serializers.ValidationError("Matrícula ya registrada.")
            PersonalSalud.objects.create(persona=user.idpersona, **s.validated_data)
        event = audit(
            request, f"Solicitud de cargo:{code}", "PersonalSalud", user.idpersona_id
        )
        return Response(
            {"id": event.pk, "mensaje": "Solicitud pendiente de revisión."}, status=201
        )


class ResolverCargoView(APIView):
    permission_classes = [IsAdminRole]

    @transaction.atomic
    def post(self, request, pk):
        event = get_object_or_404(
            BitacoraAuditoria.objects.select_for_update(),
            pk=pk,
            tablaafectada="PersonalSalud",
            accionrealizada__startswith="Solicitud de cargo:",
        )
        user = Usuario.objects.select_for_update().get(pk=event.idusuario_id)
        if BitacoraAuditoria.objects.filter(
            tablaafectada="SolicitudCargo", idregistroafectado=pk
        ).exists():
            return Response({"detail": "Solicitud ya resuelta."}, status=409)
        approve = request.data.get("aprobar")
        if not isinstance(approve, bool):
            raise serializers.ValidationError("Indica aprobar como booleano.")
        if approve:
            role = get_object_or_404(
                Rol, codigorol=event.accionrealizada.split(":", 1)[1]
            )
            UsuarioRol.objects.get_or_create(idusuario=user, idrol=role)
        audit(
            request,
            "Cargo aprobado" if approve else "Cargo rechazado",
            "SolicitudCargo",
            pk,
        )
        return Response({"mensaje": "Solicitud resuelta."})


class BitacoraAuditoriaListView(APIView):
    permission_classes = [IsAdminRole]

    def get(self, request):
        qs = BitacoraAuditoria.objects.select_related("idusuario__idpersona").all()
        night = request.query_params.get("fuera_turno") in ("true", "1")
        if night:
            timestamp = (
                Func(
                    Value("UTC"),
                    F("fechahora"),
                    function="timezone",
                    output_field=DateTimeField(),
                )
                if connection.vendor == "postgresql"
                else F("fechahora")
            )
            qs = qs.annotate(hora=ExtractHour(timestamp)).filter(
                Q(hora__gte=19) | Q(hora__lt=7)
            )
        for key, lookup in [
            ("fecha_inicio", "fechahora__gte"),
            ("fecha_fin", "fechahora__lt"),
            ("id_usuario", "idusuario_id"),
            ("tabla_afectada", "tablaafectada__iexact"),
        ]:
            value = request.query_params.get(key)
            if value and value != "all":
                try:
                    if key.startswith("fecha"):
                        day = date.fromisoformat(value)
                        if key == "fecha_fin":
                            day += timedelta(days=1)
                        value = timezone.make_aware(datetime.combine(day, time.min))
                    if key == "id_usuario":
                        value = int(value)
                except ValueError:
                    raise serializers.ValidationError(f"Filtro inválido: {key}.")
                qs = qs.filter(**{lookup: value})
        q = request.query_params.get("q", "").strip()
        if q:
            qs = qs.filter(
                Q(accionrealizada__icontains=q)
                | Q(tablaafectada__icontains=q)
                | Q(idusuario__username__icontains=q)
                | Q(idusuario__idpersona__ci__icontains=q)
            )
        return Response(
            {
                "totalRegistros": qs.count(),
                "esFiltroFueraTurno": night,
                "eventos": BitacoraAuditoriaSerializer(
                    qs.order_by("-fechahora")[:1000], many=True
                ).data,
            }
        )


def password_version(user):
    return salted_hmac("password-reset-version", user.passwordhash).hexdigest()


class PasswordResetRequestView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        identifier = str(request.data.get("email", "")).strip()
        user = Usuario.objects.filter(
            Q(email__iexact=identifier) | Q(username__iexact=identifier)
        ).first()
        if user:
            token = signing.dumps(
                {"uid": user.pk, "v": password_version(user)}, salt="hemovida-reset"
            )
            sent = enviar_correo_institucional(
                "HemoVida - Recuperación de contraseña",
                f"Código de recuperación (válido 15 minutos):\n{token}\nSi no lo solicitaste, ignora este correo.",
                "",
                user.email,
            )
            if not sent:
                return Response(
                    {
                        "detail": "No se pudo enviar el correo. Contacta al administrador."
                    },
                    status=503,
                )
            audit(
                request,
                "Solicitud de recuperación de contraseña",
                "Usuario",
                user.pk,
                user,
            )
        return Response(
            {
                "success": True,
                "message": "Si la cuenta existe, recibirás un código por correo.",
            }
        )


class PasswordResetConfirmView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    @transaction.atomic
    def post(self, request):
        try:
            payload = signing.loads(
                request.data.get("token", ""), salt="hemovida-reset", max_age=900
            )
            user = Usuario.objects.select_for_update().get(pk=payload["uid"])
            if not constant_time_compare(payload["v"], password_version(user)):
                raise signing.BadSignature()
        except (signing.BadSignature, Usuario.DoesNotExist, KeyError, TypeError):
            raise serializers.ValidationError("Código inválido, usado o vencido.")
        return update_password(request, user)


def update_password(request, user):
    password = request.data.get("new_password", "")
    try:
        validate_password_complexity(password)
    except DjangoValidationError as exc:
        raise serializers.ValidationError(exc.messages)
    user.set_password(password)
    user.save(update_fields=["passwordhash"])
    audit(request, "Contraseña actualizada", "Usuario", user.pk, user)
    return Response({"success": True, "message": "Contraseña actualizada."})


class PasswordChangeView(APIView):
    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def post(self, request):
        user = Usuario.objects.select_for_update().get(pk=request.user.pk)
        if not user.check_password(request.data.get("current_password", "")):
            raise serializers.ValidationError("La contraseña actual es incorrecta.")
        return update_password(request, user)
