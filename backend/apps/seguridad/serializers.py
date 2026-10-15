"""
Serializadores para Seguridad, Autenticación y Auditoría
adaptados al modelo relacional con RBAC múltiple (UsuarioRol).
"""

from rest_framework import serializers
from django.db import transaction
from .models import Usuario, Rol, UsuarioRol, Persona, PersonalSalud, BitacoraAuditoria
from .validators import validate_password_complexity
from apps.donantes.models import PosibleDonador


class AutoRegistroPosibleDonadorSerializer(serializers.Serializer):
    """
    Serializador para Procedimiento 1: Auto-Registro Público de Posible Donador (Sin Admin).
    Ejecuta sp_autoregistro_posible_donador o lógica equivalente.
    """

    ci = serializers.CharField(max_length=20, required=True)
    nombres = serializers.CharField(max_length=80, required=True)
    apellidos = serializers.CharField(max_length=80, required=True)
    sexo = serializers.ChoiceField(choices=["M", "F", "O"], required=True)
    fechaNacimiento = serializers.DateField(required=True)
    direccion = serializers.CharField(
        max_length=150, required=False, allow_blank=True, default=""
    )
    celular = serializers.CharField(
        max_length=20, required=False, allow_blank=True, default=""
    )
    ocupacion = serializers.CharField(
        max_length=80, required=False, allow_blank=True, default=""
    )
    username = serializers.CharField(max_length=50, required=True)
    email = serializers.EmailField(max_length=100, required=True)
    password = serializers.CharField(write_only=True, required=True)

    def validate_password(self, value):
        validate_password_complexity(value)
        return value

    def validate_ci(self, value):
        if Persona.objects.filter(ci__iexact=value).exists():
            raise serializers.ValidationError(
                "Ya existe una persona registrada con esta cédula de identidad."
            )
        return value

    def validate_username(self, value):
        if Usuario.objects.filter(username__iexact=value).exists():
            raise serializers.ValidationError(
                "El nombre de usuario ya se encuentra en uso."
            )
        return value

    def validate_email(self, value):
        if Usuario.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError(
                "El correo electrónico ya se encuentra registrado."
            )
        return value

    @transaction.atomic
    def create(self, validated_data):
        data = dict(validated_data)
        password = data.pop("password")
        username, email = data.pop("username"), data.pop("email").lower()
        data["fechanacimiento"] = data.pop("fechaNacimiento")
        persona = Persona.objects.create(**data)
        usuario = Usuario(
            idpersona=persona, username=username, email=email, estado="Activo"
        )
        usuario.set_password(password)
        usuario.save()
        PosibleDonador.objects.create(
            idpersona=persona,
            carnetprovisionalcodigo=f"HV-POST-{persona.pk:08d}",
            estadoaptitud="No Apto",
        )
        rol = Rol.objects.get(codigorol="POSIBLE_DONADOR")
        UsuarioRol.objects.create(idusuario=usuario, idrol=rol)
        return usuario


class CrearPersonalSaludSerializer(serializers.Serializer):
    """
    Serializador para Procedimiento 2: Alta de Personal de Salud (Solo Ejecutable por Administrador).
    Ejecuta sp_crear_usuario_personal_salud o lógica equivalente.
    """

    ci = serializers.CharField(max_length=20, required=True)
    nombres = serializers.CharField(max_length=80, required=True)
    apellidos = serializers.CharField(max_length=80, required=True)
    sexo = serializers.ChoiceField(choices=["M", "F", "O"], required=True)
    fechaNacimiento = serializers.DateField(required=True)
    celular = serializers.CharField(
        max_length=20, required=False, allow_blank=True, default=""
    )
    cargo = serializers.CharField(max_length=80, required=True)
    registroProfesional = serializers.CharField(max_length=40, required=True)
    username = serializers.CharField(max_length=50, required=True)
    email = serializers.EmailField(max_length=100, required=True)
    password = serializers.CharField(write_only=True, required=True)
    codigoRolAsignar = serializers.CharField(max_length=30, required=True)

    def validate_password(self, value):
        validate_password_complexity(value)
        return value

    def validate_codigoRolAsignar(self, value):
        val_upper = value.strip().upper()
        if val_upper in ("POSIBLE_DONADOR", "DONANTE"):
            raise serializers.ValidationError(
                "No se puede asignar un rol de postulante o donante como personal operativo."
            )
        if not Rol.objects.filter(codigoRol=val_upper).exists():
            raise serializers.ValidationError(
                f"El rol con código '{value}' no existe en el catálogo oficial."
            )
        return val_upper

    def validate_registroProfesional(self, value):
        if PersonalSalud.objects.filter(registroProfesional__iexact=value).exists():
            raise serializers.ValidationError(
                "El registro profesional / matrícula ya está asignado."
            )
        return value

    def validate_ci(self, value):
        if Persona.objects.filter(ci__iexact=value).exists():
            raise serializers.ValidationError(
                "Ya existe una persona registrada con este documento de identidad."
            )
        return value

    def validate_username(self, value):
        if Usuario.objects.filter(username__iexact=value).exists():
            raise serializers.ValidationError(
                "El nombre de usuario institucional ya está en uso."
            )
        return value

    def validate_email(self, value):
        if Usuario.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError(
                "El correo electrónico institucional ya se encuentra registrado."
            )
        return value

    @transaction.atomic
    def create_for_admin(self, admin_user, validated_data):
        d = validated_data
        persona = Persona.objects.create(
            ci=d["ci"],
            nombres=d["nombres"],
            apellidos=d["apellidos"],
            sexo=d["sexo"],
            fechanacimiento=d["fechaNacimiento"],
            celular=d.get("celular", ""),
        )
        PersonalSalud.objects.create(
            persona=persona,
            cargo=d["cargo"],
            registroprofesional=d["registroProfesional"],
        )
        usuario = Usuario(
            idpersona=persona,
            username=d["username"],
            email=d["email"].lower(),
            estado="Activo",
        )
        usuario.set_password(d["password"])
        usuario.save()
        UsuarioRol.objects.create(
            idusuario=usuario, idrol=Rol.objects.get(codigorol=d["codigoRolAsignar"])
        )
        return usuario


class PersonalSaludListSerializer(serializers.ModelSerializer):
    """
    Serializador para la Matriz de personal de salud clasificados por rol institucional.
    """

    idUsuario = serializers.SerializerMethodField()
    username = serializers.SerializerMethodField()
    email = serializers.SerializerMethodField()
    rolesDisponibles = serializers.SerializerMethodField()
    nombreRol = serializers.SerializerMethodField()
    estadoUsuario = serializers.SerializerMethodField()
    ci = serializers.CharField(source="persona.ci")
    nombreCompleto = serializers.CharField(source="persona.nombreCompleto")

    class Meta:
        model = PersonalSalud
        fields = [
            "idUsuario",
            "username",
            "email",
            "nombreRol",
            "rolesDisponibles",
            "cargo",
            "registroProfesional",
            "estadoUsuario",
            "ci",
            "nombreCompleto",
        ]

    def get_idUsuario(self, obj):
        usuario = getattr(obj.persona, "usuario", None)
        return usuario.idUsuario if usuario else None

    def get_username(self, obj):
        usuario = getattr(obj.persona, "usuario", None)
        return usuario.username if usuario else None

    def get_email(self, obj):
        usuario = getattr(obj.persona, "usuario", None)
        return usuario.email if usuario else None

    def get_estadoUsuario(self, obj):
        usuario = getattr(obj.persona, "usuario", None)
        return usuario.estado if usuario else "Inactivo"

    def get_rolesDisponibles(self, obj):
        usuario = getattr(obj.persona, "usuario", None)
        if usuario:
            return [
                {"id": r.idRol, "codigo": r.codigoRol, "nombre": r.nombreRol}
                for r in usuario.roles.all()
            ]
        return []

    def get_nombreRol(self, obj):
        roles = self.get_rolesDisponibles(obj)
        if roles:
            return ", ".join([r["nombre"] for r in roles])
        return "Sin Rol Asignado"


class UsuarioEstadoUpdateSerializer(serializers.Serializer):
    """
    Serializador para cambiar el estado de un usuario (Activo / Inactivo / Bloqueado).
    """

    estado = serializers.ChoiceField(
        choices=[
            ("Activo", "Activo"),
            ("Inactivo", "Inactivo"),
            ("Bloqueado", "Bloqueado"),
        ],
        required=True,
    )


class BitacoraAuditoriaSerializer(serializers.ModelSerializer):
    """
    Serializador para Consulta y Auditoría Forense.
    Incluye rolActivo y datos extendidos de Usuario y Persona.
    """

    idAuditoria = serializers.IntegerField(source="idauditoria", read_only=True)
    idUsuario = serializers.IntegerField(
        source="idusuario.idusuario", default=None, allow_null=True
    )
    username = serializers.CharField(
        source="idusuario.username", default="Sistema / Anónimo"
    )
    nombreRol = serializers.CharField(source="rolactivo", default="N/A")
    rolActivo = serializers.CharField(source="rolactivo", default="N/A")
    accionRealizada = serializers.CharField(source="accionrealizada", read_only=True)
    tablaAfectada = serializers.CharField(source="tablaafectada", read_only=True)
    idRegistroAfectado = serializers.IntegerField(
        source="idregistroafectado", read_only=True, allow_null=True
    )
    fechaHora = serializers.DateTimeField(source="fechahora", read_only=True)
    ipOrigen = serializers.CharField(source="iporigen", read_only=True, allow_null=True)
    funcionario = serializers.SerializerMethodField()
    ci = serializers.SerializerMethodField()
    nacionalidad = serializers.SerializerMethodField()

    class Meta:
        model = BitacoraAuditoria
        fields = [
            "idAuditoria",
            "idUsuario",
            "fechaHora",
            "username",
            "funcionario",
            "ci",
            "nacionalidad",
            "rolActivo",
            "nombreRol",
            "accionRealizada",
            "tablaAfectada",
            "idRegistroAfectado",
            "ipOrigen",
        ]

    def get_funcionario(self, obj):
        if obj.usuario and obj.usuario.persona:
            return obj.usuario.persona.nombreCompleto
        return "N/A"

    def get_ci(self, obj):
        if obj.usuario and obj.usuario.persona:
            return obj.usuario.persona.ci
        return "N/A"

    def get_nacionalidad(self, obj):
        if obj.usuario and obj.usuario.persona:
            return (
                getattr(obj.usuario.persona, "nacionalidad", "Boliviana") or "Boliviana"
            )
        return "Boliviana"
