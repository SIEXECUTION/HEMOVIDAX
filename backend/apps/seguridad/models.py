"""
Modelos ORM para la app de Seguridad y Auditoría de HemoVida.
Mapeo de tablas de PostgreSQL (Supabase):
- persona
- rol
- usuariorol
- usuario
- personalsalud
- bitacoraauditoria
"""
from django.db import models
from django.utils import timezone
from django.contrib.auth.hashers import check_password, make_password
from apps.donantes.models import Persona


class FlexibleQuerySet(models.QuerySet):
    def _filter_or_exclude(self, negate, args, kwargs):
        if kwargs:
            field_names = {f.name.lower(): f.name for f in self.model._meta.get_fields() if hasattr(f, 'name')}
            alias_map = {
                'usuario': 'idusuario',
                'rol': 'idrol',
                'persona': 'idpersona',
                'codigorol': 'codigorol',
                'nombrerol': 'nombrerol',
                'idrol': 'idrol',
                'idusuario': 'idusuario',
                'idpersona': 'idpersona',
            }
            new_kwargs = {}
            for k, v in kwargs.items():
                parts = k.split('__')
                clean_parts = []
                for p in parts:
                    p_lower = p.lower()
                    if p_lower in alias_map:
                        clean_parts.append(alias_map[p_lower])
                    elif p_lower in field_names:
                        clean_parts.append(field_names[p_lower])
                    else:
                        clean_parts.append(p)
                new_kwargs['__'.join(clean_parts)] = v
            kwargs = new_kwargs
        return super()._filter_or_exclude(negate, args, kwargs)

FlexibleManager = models.Manager.from_queryset(FlexibleQuerySet)


class Rol(models.Model):
    idrol = models.AutoField(primary_key=True, db_column='idrol')
    nombrerol = models.CharField(max_length=60, unique=True, db_column='nombrerol')
    codigorol = models.CharField(max_length=30, unique=True, db_column='codigorol')
    descripcion = models.TextField(null=True, blank=True, db_column='descripcion')

    objects = FlexibleManager()

    class Meta:
        db_table = 'rol'
        managed = False
        verbose_name = 'Rol'
        verbose_name_plural = 'Roles'

    def __str__(self):
        return f"{self.nombrerol} ({self.codigorol})"

    @property
    def idRol(self):
        return self.idrol

    @idRol.setter
    def idRol(self, val):
        self.idrol = val

    @property
    def nombreRol(self):
        return self.nombrerol

    @nombreRol.setter
    def nombreRol(self, val):
        self.nombrerol = val

    @property
    def codigoRol(self):
        return self.codigorol

    @codigoRol.setter
    def codigoRol(self, val):
        self.codigorol = val


class Usuario(models.Model):
    idusuario = models.AutoField(primary_key=True, db_column='idusuario')
    idpersona = models.OneToOneField(
        'donantes.Persona', 
        on_delete=models.CASCADE,
        db_column='idpersona',
        null=True,
        blank=True
    )
    username = models.CharField(max_length=50, unique=True, db_column='username')
    email = models.CharField(max_length=100, unique=True, db_column='email')
    passwordhash = models.CharField(max_length=255, db_column='passwordhash')
    estado = models.CharField(max_length=20, default='Activo', db_column='estado')
    fechacreacion = models.DateTimeField(default=timezone.now, db_column='fechacreacion')

    # Bloqueo progresivo y auditoría de accesos fallidos
    intentosfallidos = models.IntegerField(default=0, db_column='intentosfallidos')
    fechabloqueohasta = models.DateTimeField(null=True, blank=True, db_column='fechabloqueohasta')
    totalbloqueosrecibidos = models.IntegerField(default=0, db_column='totalbloqueosrecibidos')

    roles = models.ManyToManyField(
        Rol,
        through='UsuarioRol',
        related_name='usuarios'
    )

    objects = FlexibleManager()

    class Meta:
        db_table = 'usuario'
        managed = False
        verbose_name = 'Usuario'
        verbose_name_plural = 'Usuarios'

    def __str__(self):
        return f"{self.username} - {self.estado}"

    @property
    def idUsuario(self):
        return self.idusuario

    @property
    def persona(self):
        return self.idpersona

    @persona.setter
    def persona(self, val):
        self.idpersona = val

    @property
    def passwordHash(self):
        return self.passwordhash

    @passwordHash.setter
    def passwordHash(self, val):
        self.passwordhash = val

    @property
    def intentosFallidos(self):
        return self.intentosfallidos

    @intentosFallidos.setter
    def intentosFallidos(self, val):
        self.intentosfallidos = val

    @property
    def fechaBloqueoHasta(self):
        return self.fechabloqueohasta

    @fechaBloqueoHasta.setter
    def fechaBloqueoHasta(self, val):
        self.fechabloqueohasta = val

    @property
    def totalBloqueosRecibidos(self):
        return self.totalbloqueosrecibidos

    @totalBloqueosRecibidos.setter
    def totalBloqueosRecibidos(self, val):
        self.totalbloqueosrecibidos = val

    @property
    def fechaCreacion(self):
        return self.fechacreacion

    def check_password(self, raw_password: str) -> bool:
        """
        Valida la contraseña permitiendo hashes argon2id, pbkdf2 y texto plano.
        """
        if not self.passwordhash or not raw_password:
            return False
        # 1. Comprobación directa (texto plano precargado o de procedimiento)
        if self.passwordhash == raw_password:
            return True
        # 2. Comprobación nativa con argon2id si el hash inicia con $argon2
        if self.passwordhash.startswith('$argon2'):
            try:
                from argon2 import PasswordHasher
                ph = PasswordHasher()
                ph.verify(self.passwordhash, raw_password)
                return True
            except Exception:
                return False
        # 3. Comprobación con hasher de Django
        try:
            return check_password(raw_password, self.passwordhash)
        except Exception:
            return False

    def set_password(self, raw_password: str):
        if raw_password:
            self.passwordhash = make_password(raw_password)
        else:
            self.passwordhash = ''

    def save(self, *args, **kwargs):
        if 'update_fields' in kwargs and kwargs['update_fields'] is not None:
            field_map = {
                'passwordHash': 'passwordhash',
                'intentosFallidos': 'intentosfallidos',
                'fechaBloqueoHasta': 'fechabloqueohasta',
                'totalBloqueosRecibidos': 'totalbloqueosrecibidos',
                'fechaCreacion': 'fechacreacion',
                'idPersona': 'idpersona',
                'persona': 'idpersona',
            }
            kwargs['update_fields'] = [field_map.get(f, f.lower()) for f in kwargs['update_fields']]
        super().save(*args, **kwargs)

    @property
    def is_authenticated(self):
        return True

    @property
    def is_anonymous(self):
        return False

    @property
    def is_active(self):
        return self.estado == 'Activo'

    @property
    def is_staff(self):
        return self.roles.filter(codigorol='ADMIN').exists()


class UsuarioRol(models.Model):
    idusuario = models.ForeignKey(
        Usuario, 
        on_delete=models.CASCADE, 
        db_column='idusuario', 
        primary_key=True
    )
    idrol = models.ForeignKey(
        Rol, 
        on_delete=models.CASCADE, 
        db_column='idrol'
    )
    fechaasignacion = models.DateTimeField(
        default=timezone.now, 
        db_column='fechaasignacion'
    )

    objects = FlexibleManager()

    class Meta:
        db_table = 'usuariorol'
        managed = False
        unique_together = (('idusuario', 'idrol'),)
        verbose_name = 'Usuario Rol'
        verbose_name_plural = 'Usuarios Roles'

    def __str__(self):
        return f"{self.idusuario.username} -> {self.idrol.codigorol}"

    @property
    def usuario(self):
        return self.idusuario

    @usuario.setter
    def usuario(self, val):
        self.idusuario = val

    @property
    def rol(self):
        return self.idrol

    @rol.setter
    def rol(self, val):
        self.idrol = val

    @property
    def fechaAsignacion(self):
        return self.fechaasignacion

    @fechaAsignacion.setter
    def fechaAsignacion(self, val):
        self.fechaasignacion = val


class PersonalSalud(models.Model):
    persona = models.OneToOneField(
        'donantes.Persona', 
        primary_key=True, 
        on_delete=models.CASCADE, 
        db_column='idpersona',
        related_name='personal_salud'
    )
    cargo = models.CharField(max_length=80, db_column='cargo')
    registroprofesional = models.CharField(max_length=40, unique=True, db_column='registroprofesional')

    objects = FlexibleManager()

    class Meta:
        managed = False
        db_table = 'personalsalud'
        verbose_name = 'Personal de Salud'
        verbose_name_plural = 'Personal de Salud'

    def __str__(self):
        return f"{self.persona.nombreCompleto} - {self.cargo} ({self.registroprofesional})"

    @property
    def registroProfesional(self):
        return self.registroprofesional

    @registroProfesional.setter
    def registroProfesional(self, val):
        self.registroprofesional = val


class BitacoraAuditoria(models.Model):
    idauditoria = models.AutoField(primary_key=True, db_column='idauditoria')
    idusuario = models.ForeignKey(
        Usuario, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        db_column='idusuario'
    )
    rolactivo = models.CharField(max_length=60, null=True, blank=True, db_column='rolactivo')
    accionrealizada = models.CharField(max_length=255, db_column='accionrealizada')
    tablaafectada = models.CharField(max_length=60, db_column='tablaafectada')
    idregistroafectado = models.IntegerField(null=True, blank=True, db_column='idregistroafectado')
    fechahora = models.DateTimeField(default=timezone.now, db_column='fechahora')
    iporigen = models.CharField(max_length=45, null=True, blank=True, db_column='iporigen')

    objects = FlexibleManager()

    class Meta:
        db_table = 'bitacoraauditoria'
        managed = False
        verbose_name = 'Bitácora de Auditoría'
        verbose_name_plural = 'Bitácoras de Auditoría'
        ordering = ['-fechahora']

    def __str__(self):
        return f"[{self.fechahora}] [{self.rolactivo or 'N/A'}] {self.accionrealizada} en {self.tablaafectada} (#{self.idregistroafectado})"

    @property
    def idAuditoria(self):
        return self.idauditoria

    @idAuditoria.setter
    def idAuditoria(self, val):
        self.idauditoria = val

    @property
    def usuario(self):
        return self.idusuario

    @usuario.setter
    def usuario(self, val):
        self.idusuario = val

    @property
    def rolActivo(self):
        return self.rolactivo

    @rolActivo.setter
    def rolActivo(self, val):
        self.rolactivo = val

    @property
    def accionRealizada(self):
        return self.accionrealizada

    @accionRealizada.setter
    def accionRealizada(self, val):
        self.accionrealizada = val

    @property
    def tablaAfectada(self):
        return self.tablaafectada

    @tablaAfectada.setter
    def tablaAfectada(self, val):
        self.tablaafectada = val

    @property
    def idRegistroAfectado(self):
        return self.idregistroafectado

    @idRegistroAfectado.setter
    def idRegistroAfectado(self, val):
        self.idregistroafectado = val

    @property
    def fechaHora(self):
        return self.fechahora

    @fechaHora.setter
    def fechaHora(self, val):
        self.fechahora = val

    @property
    def ipOrigen(self):
        return self.iporigen

    @ipOrigen.setter
    def ipOrigen(self, val):
        self.iporigen = val
