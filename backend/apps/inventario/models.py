"""
Modelos ORM para la app Inventario de HemoVida.
Mapeo de tablas de PostgreSQL (Supabase):
- gruposanguineo
- ubicacionalmacen
- parametrostockminimo
- unidadsangretotal
- ejemplarbolsa
- solicitudhospitalaria
- detallesolicitud
"""
from django.db import models
from django.utils import timezone


import copy


ALIAS_MAP = {
    'grupo': 'idgrupo',
    'ubicacion': 'idubicacion',
    'unidadmadre': 'idunidadmadre',
    'solicitud': 'idsolicitud',
    'detalle': 'iddetalle',
    'receptor': 'idreceptor',
    'institucion': 'idinstitucion',
    'despacho': 'iddespacho',
    'ejemplar': 'idejemplarbolsa',
    'personalsalud': 'idpersonalsalud',
}


def clean_lookup(key):
    parts = key.split('__')
    clean_parts = []
    for p in parts:
        p_lower = p.lower()
        if p_lower in ALIAS_MAP:
            clean_parts.append(ALIAS_MAP[p_lower])
        else:
            clean_parts.append(p_lower)
    return '__'.join(clean_parts)


def clean_q(q):
    from django.db.models import Q
    if not isinstance(q, Q):
        return q
    new_q = copy.copy(q)
    new_children = []
    for child in q.children:
        if isinstance(child, tuple) and len(child) == 2:
            k, v = child
            new_children.append((clean_lookup(k), v))
        elif isinstance(child, Q):
            new_children.append(clean_q(child))
        else:
            new_children.append(child)
    new_q.children = new_children
    return new_q


def clean_expr(expr):
    from django.db.models.expressions import F
    if isinstance(expr, str):
        return clean_lookup(expr)
    if isinstance(expr, F):
        return F(clean_lookup(expr.name))
    if hasattr(expr, 'get_source_expressions') and hasattr(expr, 'set_source_expressions'):
        sources = expr.get_source_expressions()
        if sources:
            new_sources = [clean_expr(s) for s in sources]
            new_expr = copy.copy(expr)
            new_expr.set_source_expressions(new_sources)
            return new_expr
    return expr


class FlexibleQuerySet(models.QuerySet):
    def select_related(self, *fields):
        if fields:
            fields = tuple(clean_lookup(f) for f in fields)
        return super().select_related(*fields)

    def order_by(self, *field_names):
        new_names = []
        for name in field_names:
            if not isinstance(name, str):
                new_names.append(name)
                continue
            prefix = '-' if name.startswith('-') else ('' if not name.startswith('+') else '+')
            clean_name = clean_lookup(name.lstrip('-+'))
            new_names.append(f"{prefix}{clean_name}")
        return super().order_by(*new_names)

    def aggregate(self, *args, **kwargs):
        new_args = tuple(clean_expr(a) for a in args)
        new_kwargs = {k: clean_expr(v) for k, v in kwargs.items()}
        return super().aggregate(*new_args, **new_kwargs)

    def annotate(self, *args, **kwargs):
        new_args = tuple(clean_expr(a) for a in args)
        new_kwargs = {k: clean_expr(v) for k, v in kwargs.items()}
        return super().annotate(*new_args, **new_kwargs)

    def values(self, *fields, **expressions):
        new_fields = tuple(clean_lookup(f) for f in fields)
        new_expressions = {k: clean_expr(v) for k, v in expressions.items()}
        return super().values(*new_fields, **new_expressions)

    def values_list(self, *fields, **kwargs):
        new_fields = tuple(clean_lookup(f) for f in fields)
        return super().values_list(*new_fields, **kwargs)

    def _filter_or_exclude(self, negate, args, kwargs):
        if args:
            args = tuple(clean_q(a) for a in args)
        if kwargs:
            kwargs = {clean_lookup(k): v for k, v in kwargs.items()}
        return super()._filter_or_exclude(negate, args, kwargs)


FlexibleManager = models.Manager.from_queryset(FlexibleQuerySet)


class GrupoSanguineo(models.Model):
    idgrupo = models.AutoField(primary_key=True, db_column='idgrupo')
    grupoabo = models.CharField(max_length=5, db_column='grupoabo')
    factorrh = models.CharField(max_length=10, db_column='factorrh')

    objects = FlexibleManager()

    class Meta:
        db_table = 'gruposanguineo'
        managed = False
        verbose_name = 'Grupo Sanguíneo'
        verbose_name_plural = 'Grupos Sanguíneos'

    def __str__(self):
        return f"{self.grupoabo} {self.factorrh}"

    @property
    def idGrupo(self):
        return self.idgrupo

    @idGrupo.setter
    def idGrupo(self, val):
        self.idgrupo = val

    @property
    def grupoABO(self):
        return self.grupoabo

    @grupoABO.setter
    def grupoABO(self, val):
        self.grupoabo = val

    @property
    def factorRh(self):
        return self.factorrh

    @factorRh.setter
    def factorRh(self, val):
        self.factorrh = val

    @property
    def tipificacion(self):
        return f"{self.grupoabo} {self.factorrh}"


class UbicacionAlmacen(models.Model):
    idubicacion = models.AutoField(primary_key=True, db_column='idubicacion')
    identificadorcompartimento = models.CharField(
        max_length=30, 
        unique=True,
        db_column='identificadorcompartimento'
    )
    tipoequipo = models.CharField(max_length=80, db_column='tipoequipo')
    temperaturaregistro = models.DecimalField(
        max_digits=4, 
        decimal_places=1,
        db_column='temperaturaregistro'
    )
    capacidadmaxima = models.IntegerField(db_column='capacidadmaxima')
    capacidadocupada = models.IntegerField(default=0, db_column='capacidadocupada')

    objects = FlexibleManager()

    class Meta:
        db_table = 'ubicacionalmacen'
        managed = False
        verbose_name = 'Ubicación de Almacén'
        verbose_name_plural = 'Ubicaciones de Almacén'

    def __str__(self):
        return f"{self.identificadorcompartimento} ({self.tipoequipo})"


class ParametroStockMinimo(models.Model):
    COMPONENTES_CHOICES = [
        ('Concentrado de Globulos Rojos', 'Concentrado de Globulos Rojos'),
        ('Plasma Fresco Congelado', 'Plasma Fresco Congelado'),
        ('Concentrado Plaquetario', 'Concentrado Plaquetario'),
        ('Crioprecipitado', 'Crioprecipitado'),
        ('Sangre Total', 'Sangre Total'),
    ]

    idparametro = models.AutoField(primary_key=True, db_column='idparametro')
    idgrupo = models.ForeignKey(
        GrupoSanguineo, 
        on_delete=models.CASCADE,
        db_column='idgrupo',
        related_name='parametros_stock'
    )
    tipocomponente = models.CharField(max_length=50, db_column='tipocomponente')
    stockminimoseguridad = models.IntegerField(db_column='stockminimoseguridad')
    stockcriticoalerta = models.IntegerField(db_column='stockcriticoalerta')
    categoriaetaria = models.CharField(
        max_length=20, 
        default='Adulto',
        db_column='categoriaetaria'
    )

    objects = FlexibleManager()

    class Meta:
        db_table = 'parametrostockminimo'
        managed = False
        unique_together = (('idgrupo', 'tipocomponente', 'categoriaetaria'),)
        verbose_name = 'Parámetro de Stock Mínimo'
        verbose_name_plural = 'Parámetros de Stock Mínimo'
        ordering = ['idgrupo__idgrupo', 'tipocomponente', 'categoriaetaria']

    def __str__(self):
        return f"{self.idgrupo} - {self.tipocomponente} [{self.categoriaetaria}] (Mín: {self.stockminimoseguridad}, Crítico: {self.stockcriticoalerta})"

    @property
    def idParametro(self):
        return self.idparametro

    @idParametro.setter
    def idParametro(self, val):
        self.idparametro = val

    @property
    def grupo(self):
        return self.idgrupo

    @grupo.setter
    def grupo(self, val):
        self.idgrupo = val

    @property
    def tipoComponente(self):
        return self.tipocomponente

    @tipoComponente.setter
    def tipoComponente(self, val):
        self.tipocomponente = val

    @property
    def stockMinimoSeguridad(self):
        return self.stockminimoseguridad

    @stockMinimoSeguridad.setter
    def stockMinimoSeguridad(self, val):
        self.stockminimoseguridad = val

    @property
    def stockCriticoAlerta(self):
        return self.stockcriticoalerta

    @stockCriticoAlerta.setter
    def stockCriticoAlerta(self, val):
        self.stockcriticoalerta = val

    @property
    def categoriaEtaria(self):
        return self.categoriaetaria

    @categoriaEtaria.setter
    def categoriaEtaria(self, val):
        self.categoriaetaria = val


class UnidadSangreTotal(models.Model):
    idunidadmadre = models.AutoField(primary_key=True, db_column='idunidadmadre')
    idextraccion = models.OneToOneField(
        'donantes.ExtraccionDonacion',
        on_delete=models.CASCADE, 
        db_column='idextraccion',
        null=True,
        blank=True
    )
    idgrupo = models.ForeignKey(
        GrupoSanguineo, 
        on_delete=models.RESTRICT,
        db_column='idgrupo'
    )
    codigobolsamadre = models.CharField(
        max_length=40, 
        unique=True,
        db_column='codigobolsamadre'
    )
    tipobolsa = models.CharField(max_length=40, db_column='tipobolsa')
    estadoliberacion = models.CharField(
        max_length=30, 
        default='En Cuarentena',
        db_column='estadoliberacion'
    )

    objects = FlexibleManager()

    class Meta:
        db_table = 'unidadsangretotal'
        managed = False
        verbose_name = 'Unidad Sangre Total'
        verbose_name_plural = 'Unidades Sangre Total'

    def __str__(self):
        return f"{self.codigobolsamadre} ({self.estadoliberacion})"


class EjemplarBolsa(models.Model):
    idejemplarbolsa = models.AutoField(primary_key=True, db_column='idejemplarbolsa')
    idunidadmadre = models.ForeignKey(
        UnidadSangreTotal, 
        on_delete=models.SET_NULL,
        null=True, 
        blank=True, 
        db_column='idunidadmadre'
    )
    idgrupo = models.ForeignKey(
        GrupoSanguineo, 
        on_delete=models.RESTRICT,
        db_column='idgrupo',
        related_name='bolsas'
    )
    idubicacion = models.ForeignKey(
        UbicacionAlmacen, 
        on_delete=models.SET_NULL,
        null=True, 
        blank=True, 
        db_column='idubicacion'
    )
    codigoejemplark = models.CharField(
        max_length=40, 
        unique=True,
        db_column='codigoejemplark'
    )
    tipocomponente = models.CharField(max_length=50, db_column='tipocomponente')
    volumenml = models.IntegerField(db_column='volumenml')
    fechaextraccion = models.DateField(db_column='fechaextraccion')
    fechacaducidad = models.DateField(db_column='fechacaducidad')
    estadobolsak = models.CharField(
        max_length=25, 
        default='En Cuarentena',
        db_column='estadobolsak'
    )
    esexclusivoautologo = models.BooleanField(
        default=False, 
        db_column='esexclusivoautologo'
    )
    categoriaetaria = models.CharField(
        max_length=20, 
        default='Adulto',
        db_column='categoriaetaria'
    )

    objects = FlexibleManager()

    class Meta:
        db_table = 'ejemplarbolsa'
        managed = False
        verbose_name = 'Ejemplar de Bolsa (K)'
        verbose_name_plural = 'Ejemplares de Bolsas (K)'
        ordering = ['fechacaducidad']

    def __str__(self):
        return f"{self.codigoejemplark} ({self.tipocomponente} [{self.categoriaetaria}]) [{self.estadobolsak}]"

    @property
    def idEjemplarBolsa(self):
        return self.idejemplarbolsa

    @idEjemplarBolsa.setter
    def idEjemplarBolsa(self, val):
        self.idejemplarbolsa = val

    @property
    def idUnidadMadre(self):
        return self.idunidadmadre

    @idUnidadMadre.setter
    def idUnidadMadre(self, val):
        if isinstance(val, int):
            self.idunidadmadre_id = val
        else:
            self.idunidadmadre = val

    @property
    def grupo(self):
        return self.idgrupo

    @grupo.setter
    def grupo(self, val):
        self.idgrupo = val

    @property
    def idUbicacion(self):
        return self.idubicacion

    @idUbicacion.setter
    def idUbicacion(self, val):
        if isinstance(val, int):
            self.idubicacion_id = val
        else:
            self.idubicacion = val

    @property
    def codigoEjemplarK(self):
        return self.codigoejemplark

    @codigoEjemplarK.setter
    def codigoEjemplarK(self, val):
        self.codigoejemplark = val

    @property
    def tipoComponente(self):
        return self.tipocomponente

    @tipoComponente.setter
    def tipoComponente(self, val):
        self.tipocomponente = val

    @property
    def volumenMl(self):
        return self.volumenml

    @volumenMl.setter
    def volumenMl(self, val):
        self.volumenml = val

    @property
    def fechaExtraccion(self):
        return self.fechaextraccion

    @fechaExtraccion.setter
    def fechaExtraccion(self, val):
        self.fechaextraccion = val

    @property
    def fechaCaducidad(self):
        return self.fechacaducidad

    @fechaCaducidad.setter
    def fechaCaducidad(self, val):
        self.fechacaducidad = val

    @property
    def estadoBolsaK(self):
        return self.estadobolsak

    @estadoBolsaK.setter
    def estadoBolsaK(self, val):
        self.estadobolsak = val

    @property
    def esExclusivoAutologo(self):
        return self.esexclusivoautologo

    @esExclusivoAutologo.setter
    def esExclusivoAutologo(self, val):
        self.esexclusivoautologo = val

    @property
    def categoriaEtaria(self):
        return self.categoriaetaria

    @categoriaEtaria.setter
    def categoriaEtaria(self, val):
        self.categoriaetaria = val


class InstitucionSalud(models.Model):
    idinstitucion = models.AutoField(primary_key=True, db_column='idinstitucion')
    nombreinstitucion = models.CharField(max_length=100, unique=True, db_column='nombreinstitucion')
    tipoinstitucion = models.CharField(max_length=50, db_column='tipoinstitucion')
    direccion = models.CharField(max_length=150, null=True, blank=True, db_column='direccion')
    telefonocontacto = models.CharField(max_length=25, null=True, blank=True, db_column='telefonocontacto')

    objects = FlexibleManager()

    class Meta:
        db_table = 'institucionsalud'
        managed = False
        verbose_name = 'Institución de Salud'
        verbose_name_plural = 'Instituciones de Salud'

    def __str__(self):
        return f"{self.nombreinstitucion} ({self.tipoinstitucion})"


class SolicitudHospitalaria(models.Model):
    idsolicitud = models.AutoField(primary_key=True, db_column='idsolicitud')
    idinstitucion = models.ForeignKey(
        InstitucionSalud,
        on_delete=models.RESTRICT,
        null=True,
        blank=True,
        db_column='idinstitucion',
        related_name='solicitudes'
    )
    idreceptor = models.ForeignKey(
        'donantes.Receptor',
        on_delete=models.RESTRICT,
        null=True,
        blank=True,
        db_column='idreceptor',
        related_name='solicitudes'
    )
    numerosolicitud = models.CharField(max_length=35, unique=True, db_column='numerosolicitud')
    fechahorarequerimiento = models.DateTimeField(default=timezone.now, db_column='fechahorarequerimiento')
    prioridadsolicitud = models.CharField(max_length=25, default='Programada', db_column='prioridadsolicitud')
    motivotransfusion = models.CharField(max_length=150, null=True, blank=True, db_column='motivotransfusion')
    velocidadgoteo = models.CharField(max_length=50, null=True, blank=True, db_column='velocidadgoteo')
    horariorequerido = models.CharField(max_length=50, null=True, blank=True, db_column='horariorequerido')
    cantidadbolsassolicitadas = models.IntegerField(default=1, db_column='cantidadbolsassolicitadas')
    cantidadentregadareceptor = models.IntegerField(default=0, db_column='cantidadentregadareceptor')
    cantidadretiradastock = models.IntegerField(default=0, db_column='cantidadretiradastock')
    estadosolicitud = models.CharField(max_length=25, default='Registrada', db_column='estadosolicitud')

    objects = FlexibleManager()

    class Meta:
        db_table = 'solicitudhospitalaria'
        managed = False
        verbose_name = 'Solicitud Hospitalaria'
        verbose_name_plural = 'Solicitudes Hospitalarias'

    def __str__(self):
        return f"{self.numerosolicitud} ({self.estadosolicitud})"


class DetalleSolicitud(models.Model):
    iddetalle = models.AutoField(primary_key=True, db_column='iddetalle')
    idsolicitud = models.ForeignKey(
        SolicitudHospitalaria, 
        on_delete=models.CASCADE,
        db_column='idsolicitud'
    )
    idgrupo = models.ForeignKey(
        GrupoSanguineo, 
        on_delete=models.RESTRICT,
        db_column='idgrupo'
    )
    tipocomponenterequerido = models.CharField(
        max_length=50,
        db_column='tipocomponenterequerido'
    )
    cantidadsolicitada = models.IntegerField(db_column='cantidadsolicitada')
    cantidadasignada = models.IntegerField(default=0, db_column='cantidadasignada')
    categoriaetaria = models.CharField(
        max_length=20, 
        default='Adulto',
        db_column='categoriaetaria'
    )

    objects = FlexibleManager()

    class Meta:
        db_table = 'detallesolicitud'
        managed = False
        verbose_name = 'Detalle de Solicitud'
        verbose_name_plural = 'Detalles de Solicitudes'

    def __str__(self):
        return f"Detalle #{self.iddetalle} de Solicitud #{self.idsolicitud_id}"


class ReservaSangre(models.Model):
    idreserva = models.AutoField(primary_key=True, db_column='idreserva')
    idreceptor = models.ForeignKey(
        'donantes.Receptor',
        on_delete=models.CASCADE,
        db_column='idreceptor',
        related_name='reservas'
    )
    idejemplarbolsa = models.OneToOneField(
        EjemplarBolsa,
        on_delete=models.CASCADE,
        db_column='idejemplarbolsa',
        related_name='reserva'
    )
    iddetallesolicitud = models.ForeignKey(
        DetalleSolicitud,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_column='iddetallesolicitud'
    )
    fechareserva = models.DateTimeField(default=timezone.now, db_column='fechareserva')
    esautologa = models.BooleanField(default=False, db_column='esautologa')
    motivoreserva = models.CharField(max_length=100, null=True, blank=True, db_column='motivoreserva')
    fechavencimientoreserva = models.DateField(db_column='fechavencimientoreserva')
    estadoreserva = models.CharField(max_length=30, default='Activa', db_column='estadoreserva')

    objects = FlexibleManager()

    class Meta:
        db_table = 'reservasangre'
        managed = False
        verbose_name = 'Reserva de Sangre'
        verbose_name_plural = 'Reservas de Sangre'

    def __str__(self):
        return f"Reserva #{self.idreserva} - {self.idejemplarbolsa} ({self.estadoreserva})"


class BajaInventario(models.Model):
    idbaja = models.AutoField(primary_key=True, db_column='idbaja')
    idunidadmadre = models.ForeignKey(
        UnidadSangreTotal,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_column='idunidadmadre'
    )
    idejemplarbolsa = models.ForeignKey(
        EjemplarBolsa,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_column='idejemplarbolsa'
    )
    idpersonalsalud = models.ForeignKey(
        'seguridad.PersonalSalud',
        on_delete=models.RESTRICT,
        null=True,
        blank=True,
        db_column='idpersonalsalud'
    )
    fechahorabaja = models.DateTimeField(default=timezone.now, db_column='fechahorabaja')
    motivobaja = models.CharField(max_length=100, db_column='motivobaja')
    observaciones = models.TextField(null=True, blank=True, db_column='observaciones')

    objects = FlexibleManager()

    class Meta:
        db_table = 'bajainventario'
        managed = False
        verbose_name = 'Baja de Inventario'
        verbose_name_plural = 'Bajas de Inventario'

    def __str__(self):
        return f"Baja #{self.idbaja} - {self.motivobaja}"


class ReposicionPendiente(models.Model):
    idreposicion = models.AutoField(primary_key=True, db_column='idreposicion')
    idsolicitud = models.OneToOneField(
        SolicitudHospitalaria,
        on_delete=models.CASCADE,
        db_column='idsolicitud',
        related_name='reposicion_pendiente'
    )
    cantidadbolsasareponer = models.IntegerField(db_column='cantidadbolsasareponer')
    cantidadrecuperada = models.IntegerField(default=0, db_column='cantidadrecuperada')
    fechalimitereposicion = models.DateField(db_column='fechalimitereposicion')
    estadoreposicion = models.CharField(max_length=25, default='Pendiente', db_column='estadoreposicion')

    objects = FlexibleManager()

    class Meta:
        db_table = 'reposicionpendiente'
        managed = False
        verbose_name = 'Reposición Pendiente'
        verbose_name_plural = 'Reposiciones Pendientes'

    def __str__(self):
        return f"Reposición #{self.idreposicion} ({self.estadoreposicion})"


class ComprobantePago(models.Model):
    idcomprobante = models.AutoField(primary_key=True, db_column='idcomprobante')
    idsolicitud = models.OneToOneField(
        SolicitudHospitalaria,
        on_delete=models.CASCADE,
        db_column='idsolicitud',
        related_name='comprobante_pago'
    )
    numerorecibofactura = models.CharField(max_length=35, unique=True, db_column='numerorecibofactura')
    conceptoservicio = models.CharField(max_length=150, db_column='conceptoservicio')
    montototal = models.DecimalField(max_digits=10, decimal_places=2, db_column='montototal')
    estadopago = models.CharField(max_length=30, db_column='estadopago')
    metodopago = models.CharField(max_length=50, db_column='metodopago')
    fechahorapago = models.DateTimeField(null=True, blank=True, db_column='fechahorapago')

    objects = FlexibleManager()

    class Meta:
        db_table = 'comprobantepago'
        managed = False
        verbose_name = 'Comprobante de Pago'
        verbose_name_plural = 'Comprobantes de Pago'

    def __str__(self):
        return f"Recibo #{self.numerorecibofactura} - {self.montototal} Bs ({self.estadopago})"


class PruebaCompatibilidad(models.Model):
    RESULTADO_CHOICES = [
        ('Compatible', 'Compatible'),
        ('Incompatible', 'Incompatible'),
        ('Dudoso', 'Dudoso'),
    ]

    idpruebacompatibilidad = models.AutoField(primary_key=True, db_column='idpruebacompatibilidad')
    idsolicitud = models.ForeignKey(
        SolicitudHospitalaria,
        on_delete=models.RESTRICT,
        db_column='idsolicitud',
        related_name='pruebas_compatibilidad'
    )
    idejemplarbolsa = models.ForeignKey(
        EjemplarBolsa,
        on_delete=models.RESTRICT,
        db_column='idejemplarbolsa',
        related_name='pruebas_compatibilidad'
    )
    idpersonalsalud = models.ForeignKey(
        'seguridad.PersonalSalud',
        on_delete=models.RESTRICT,
        db_column='idpersonalsalud',
        related_name='pruebas_compatibilidad'
    )
    fechahoraprueba = models.DateTimeField(default=timezone.now, db_column='fechahoraprueba')
    resultadocompatibilidad = models.CharField(max_length=25, db_column='resultadocompatibilidad')
    faseantiglobulina = models.CharField(max_length=50, null=True, blank=True, db_column='faseantiglobulina')
    reaccionobservada = models.CharField(max_length=150, null=True, blank=True, db_column='reaccionobservada')
    aprobadoparadespacho = models.BooleanField(default=False, db_column='aprobadoparadespacho')

    objects = FlexibleManager()

    class Meta:
        db_table = 'pruebacompatibilidad'
        managed = False
        verbose_name = 'Prueba de Compatibilidad'
        verbose_name_plural = 'Pruebas de Compatibilidad'

    def __str__(self):
        return f"Prueba #{self.idpruebacompatibilidad} - Solicitud #{self.idsolicitud_id} ({self.resultadocompatibilidad})"

    @property
    def idPruebaCompatibilidad(self):
        return self.idpruebacompatibilidad

    @idPruebaCompatibilidad.setter
    def idPruebaCompatibilidad(self, val):
        self.idpruebacompatibilidad = val

    @property
    def idSolicitud(self):
        return self.idsolicitud

    @idSolicitud.setter
    def idSolicitud(self, val):
        if isinstance(val, int):
            self.idsolicitud_id = val
        else:
            self.idsolicitud = val

    @property
    def idEjemplarBolsa(self):
        return self.idejemplarbolsa

    @idEjemplarBolsa.setter
    def idEjemplarBolsa(self, val):
        if isinstance(val, int):
            self.idejemplarbolsa_id = val
        else:
            self.idejemplarbolsa = val

    @property
    def idPersonalSalud(self):
        return self.idpersonalsalud

    @idPersonalSalud.setter
    def idPersonalSalud(self, val):
        if isinstance(val, int):
            self.idpersonalsalud_id = val
        else:
            self.idpersonalsalud = val

    @property
    def fechaHoraPrueba(self):
        return self.fechahoraprueba

    @fechaHoraPrueba.setter
    def fechaHoraPrueba(self, val):
        self.fechahoraprueba = val

    @property
    def resultadoCompatibilidad(self):
        return self.resultadocompatibilidad

    @resultadoCompatibilidad.setter
    def resultadoCompatibilidad(self, val):
        self.resultadocompatibilidad = val

    @property
    def faseAntiglobulina(self):
        return self.faseantiglobulina

    @faseAntiglobulina.setter
    def faseAntiglobulina(self, val):
        self.faseantiglobulina = val

    @property
    def reaccionObservada(self):
        return self.reaccionobservada

    @reaccionObservada.setter
    def reaccionObservada(self, val):
        self.reaccionobservada = val

    @property
    def aprobadoParaDespacho(self):
        return self.aprobadoparadespacho

    @aprobadoParaDespacho.setter
    def aprobadoParaDespacho(self, val):
        self.aprobadoparadespacho = val


class ComprobanteDespacho(models.Model):
    ESTADO_ENTREGA_CHOICES = [
        ('En Transito', 'En Transito'),
        ('En Transito Urgente', 'En Transito Urgente'),
        ('Entregado en Destino', 'Entregado en Destino'),
    ]

    iddespacho = models.AutoField(primary_key=True, db_column='iddespacho')
    idsolicitud = models.ForeignKey(
        SolicitudHospitalaria,
        on_delete=models.RESTRICT,
        db_column='idsolicitud',
        related_name='despachos'
    )
    codigoguiadespacho = models.CharField(max_length=35, unique=True, db_column='codigoguiadespacho')
    fechahorasalida = models.DateTimeField(default=timezone.now, db_column='fechahorasalida')
    receptorentrega = models.CharField(max_length=100, db_column='receptorentrega')
    temperaturadespacho = models.DecimalField(max_digits=4, decimal_places=1, db_column='temperaturadespacho')
    estadoentrega = models.CharField(
        max_length=30,
        default='En Transito',
        db_column='estadoentrega'
    )

    objects = FlexibleManager()

    class Meta:
        db_table = 'comprobantedespacho'
        managed = False
        verbose_name = 'Comprobante de Despacho'
        verbose_name_plural = 'Comprobantes de Despacho'

    def __str__(self):
        return f"Guía {self.codigoguiadespacho} - Solicitud #{self.idsolicitud_id} ({self.estadoentrega})"

    @property
    def idDespacho(self):
        return self.iddespacho

    @idDespacho.setter
    def idDespacho(self, val):
        self.iddespacho = val

    @property
    def idSolicitud(self):
        return self.idsolicitud

    @idSolicitud.setter
    def idSolicitud(self, val):
        if isinstance(val, int):
            self.idsolicitud_id = val
        else:
            self.idsolicitud = val

    @property
    def codigoGuiaDespacho(self):
        return self.codigoguiadespacho

    @codigoGuiaDespacho.setter
    def codigoGuiaDespacho(self, val):
        self.codigoguiadespacho = val

    @property
    def fechaHoraSalida(self):
        return self.fechahorasalida

    @fechaHoraSalida.setter
    def fechaHoraSalida(self, val):
        self.fechahorasalida = val

    @property
    def receptorEntrega(self):
        return self.receptorentrega

    @receptorEntrega.setter
    def receptorEntrega(self, val):
        self.receptorentrega = val

    @property
    def temperaturaDespacho(self):
        return self.temperaturadespacho

    @temperaturaDespacho.setter
    def temperaturaDespacho(self, val):
        self.temperaturadespacho = val

    @property
    def estadoEntrega(self):
        return self.estadoentrega

    @estadoEntrega.setter
    def estadoEntrega(self, val):
        self.estadoentrega = val


class DetalleDespacho(models.Model):
    iddetalledespacho = models.AutoField(primary_key=True, db_column='iddetalledespacho')
    iddespacho = models.ForeignKey(
        ComprobanteDespacho,
        on_delete=models.CASCADE,
        db_column='iddespacho',
        related_name='detalles'
    )
    idejemplarbolsa = models.OneToOneField(
        EjemplarBolsa,
        on_delete=models.RESTRICT,
        db_column='idejemplarbolsa',
        related_name='detalle_despacho'
    )

    objects = FlexibleManager()

    class Meta:
        db_table = 'detalledespacho'
        managed = False
        verbose_name = 'Detalle de Despacho'
        verbose_name_plural = 'Detalles de Despacho'

    def __str__(self):
        return f"Detalle #{self.iddetalledespacho} - Despacho #{self.iddespacho_id} - Bolsa #{self.idejemplarbolsa_id}"

    @property
    def idDetalleDespacho(self):
        return self.iddetalledespacho

    @idDetalleDespacho.setter
    def idDetalleDespacho(self, val):
        self.iddetalledespacho = val

    @property
    def idDespacho(self):
        return self.iddespacho

    @idDespacho.setter
    def idDespacho(self, val):
        if isinstance(val, int):
            self.iddespacho_id = val
        else:
            self.iddespacho = val

    @property
    def idEjemplarBolsa(self):
        return self.idejemplarbolsa

    @idEjemplarBolsa.setter
    def idEjemplarBolsa(self, val):
        if isinstance(val, int):
            self.idejemplarbolsa_id = val
        else:
            self.idejemplarbolsa = val

