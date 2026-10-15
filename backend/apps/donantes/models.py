"""
Modelos ORM para la app Donantes de HemoVida.
Mapeo de tablas de PostgreSQL (Supabase):
- persona
- posibledonador
- donante
- receptor
- citadonacion
- diferimiento
- extracciondonacion
- analisisinmunoserologico
- compromisodonacion
"""
from django.db import models
from django.utils import timezone


import copy


ALIAS_FIELD_MAP = {
    'idanalisisserologico': 'idanalisis',
    'hepatitisbresultado': 'resultadohepatitisb',
    'hepatitiscresultado': 'resultadohepatitisc',
    'vihresultado': 'resultadovih',
    'chagasresultado': 'resultadochagas',
    'sifilisresultado': 'resultadosifilis',
    'htlvresultado': 'resultadohtlv',
}


def clean_lookup(model_or_key, key=None):
    if key is None:
        key = model_or_key
        curr_model = None
    else:
        curr_model = model_or_key

    parts = key.split('__')
    new_parts = []
    for part in parts:
        part_lower = part.lower()
        if curr_model is None:
            new_parts.append(part_lower)
            continue
        try:
            fields_by_lower = {f.name.lower(): f for f in curr_model._meta.get_fields()}
        except Exception:
            new_parts.append(part_lower)
            curr_model = None
            continue

        matched_field = None
        if part_lower in fields_by_lower:
            matched_field = fields_by_lower[part_lower]
        elif part_lower in ALIAS_FIELD_MAP and ALIAS_FIELD_MAP[part_lower] in fields_by_lower:
            matched_field = fields_by_lower[ALIAS_FIELD_MAP[part_lower]]
        elif f'id{part_lower}' in fields_by_lower:
            matched_field = fields_by_lower[f'id{part_lower}']
        elif part_lower.startswith('id') and part_lower[2:] in fields_by_lower:
            matched_field = fields_by_lower[part_lower[2:]]

        if matched_field:
            new_parts.append(matched_field.name)
            if hasattr(matched_field, 'related_model') and matched_field.related_model:
                curr_model = matched_field.related_model
            else:
                curr_model = None
        else:
            new_parts.append(part_lower)
            curr_model = None
    return '__'.join(new_parts)


def clean_q(model, q):
    from django.db.models import Q
    if not isinstance(q, Q):
        return q
    new_q = copy.copy(q)
    new_children = []
    for child in q.children:
        if isinstance(child, tuple) and len(child) == 2:
            k, v = child
            new_children.append((clean_lookup(model, k), v))
        elif isinstance(child, Q):
            new_children.append(clean_q(model, child))
        else:
            new_children.append(child)
    new_q.children = new_children
    return new_q


def clean_expr(model, expr):
    from django.db.models.expressions import F
    if isinstance(expr, str):
        return clean_lookup(model, expr)
    if isinstance(expr, F):
        return F(clean_lookup(model, expr.name))
    if hasattr(expr, 'get_source_expressions') and hasattr(expr, 'set_source_expressions'):
        sources = expr.get_source_expressions()
        if sources:
            new_sources = [clean_expr(model, s) for s in sources]
            new_expr = copy.copy(expr)
            new_expr.set_source_expressions(new_sources)
            return new_expr
    return expr


class FlexibleQuerySet(models.QuerySet):
    def select_related(self, *fields):
        if fields:
            fields = tuple(clean_lookup(self.model, f) for f in fields)
        return super().select_related(*fields)

    def order_by(self, *field_names):
        new_names = []
        for name in field_names:
            if not isinstance(name, str):
                new_names.append(name)
                continue
            prefix = '-' if name.startswith('-') else ('' if not name.startswith('+') else '+')
            clean_name = clean_lookup(self.model, name.lstrip('-+'))
            new_names.append(f"{prefix}{clean_name}")
        return super().order_by(*new_names)

    def aggregate(self, *args, **kwargs):
        new_args = tuple(clean_expr(self.model, a) for a in args)
        new_kwargs = {k: clean_expr(self.model, v) for k, v in kwargs.items()}
        return super().aggregate(*new_args, **new_kwargs)

    def annotate(self, *args, **kwargs):
        new_args = tuple(clean_expr(self.model, a) for a in args)
        new_kwargs = {k: clean_expr(self.model, v) for k, v in kwargs.items()}
        return super().annotate(*new_args, **new_kwargs)

    def values(self, *fields, **expressions):
        new_fields = tuple(clean_lookup(self.model, f) for f in fields)
        new_expressions = {k: clean_expr(self.model, v) for k, v in expressions.items()}
        return super().values(*new_fields, **new_expressions)

    def values_list(self, *fields, **kwargs):
        new_fields = tuple(clean_lookup(self.model, f) for f in fields)
        return super().values_list(*new_fields, **kwargs)

    def _filter_or_exclude(self, negate, args, kwargs):
        if args:
            args = tuple(clean_q(self.model, a) for a in args)
        if kwargs:
            kwargs = {clean_lookup(self.model, k): v for k, v in kwargs.items()}
        return super()._filter_or_exclude(negate, args, kwargs)


FlexibleManager = models.Manager.from_queryset(FlexibleQuerySet)


class Persona(models.Model):
    idpersona = models.AutoField(primary_key=True, db_column='idpersona')
    ci = models.CharField(max_length=20, unique=True, db_column='ci')
    nombres = models.CharField(max_length=80, db_column='nombres')
    apellidos = models.CharField(max_length=80, db_column='apellidos')
    sexo = models.CharField(
        max_length=1, 
        choices=[('M', 'Masculino'), ('F', 'Femenino'), ('O', 'Otro')],
        db_column='sexo'
    )
    fechanacimiento = models.DateField(db_column='fechanacimiento')
    direccion = models.CharField(max_length=150, null=True, blank=True, db_column='direccion')
    celular = models.CharField(max_length=20, null=True, blank=True, db_column='celular')
    ocupacion = models.CharField(max_length=80, null=True, blank=True, db_column='ocupacion')
    nacionalidad = models.CharField(max_length=50, default='Boliviana', db_column='nacionalidad')

    objects = FlexibleManager()

    class Meta:
        managed = False
        db_table = 'persona'
        verbose_name = 'Persona'
        verbose_name_plural = 'Personas'

    def __str__(self):
        return f"{self.nombres} {self.apellidos} (CI: {self.ci})"

    @property
    def idPersona(self):
        return self.idpersona

    @idPersona.setter
    def idPersona(self, val):
        self.idpersona = val

    @property
    def fechaNacimiento(self):
        return self.fechanacimiento

    @fechaNacimiento.setter
    def fechaNacimiento(self, val):
        self.fechanacimiento = val

    @property
    def nombreCompleto(self):
        return f"{self.nombres} {self.apellidos}"


class PosibleDonador(models.Model):
    idpersona = models.OneToOneField(
        Persona,
        primary_key=True,
        on_delete=models.CASCADE,
        db_column='idpersona',
        related_name='posible_donador'
    )
    estadoaptitud = models.CharField(
        max_length=30,
        default='No Apto',
        choices=[
            ('No Apto', 'No Apto'),
            ('En Evaluacion', 'En Evaluacion'),
            ('Apto', 'Apto')
        ],
        db_column='estadoaptitud'
    )
    tieneanalisis = models.BooleanField(default=False, db_column='tieneanalisis')
    fecharegistropostulante = models.DateField(auto_now_add=True, db_column='fecharegistropostulante')
    carnetprovisionalcodigo = models.CharField(
        max_length=40, 
        unique=True, 
        null=True, 
        blank=True, 
        db_column='carnetprovisionalcodigo'
    )

    objects = FlexibleManager()

    class Meta:
        managed = False
        db_table = 'posibledonador'
        verbose_name = 'Posible Donador'
        verbose_name_plural = 'Posibles Donadores'

    def __str__(self):
        return f"{self.idpersona.nombreCompleto} - {self.carnetprovisionalcodigo or 'Sin Código'} ({self.estadoaptitud})"

    @property
    def persona(self):
        return self.idpersona

    @persona.setter
    def persona(self, val):
        self.idpersona = val

    @property
    def estadoAptitud(self):
        return self.estadoaptitud

    @estadoAptitud.setter
    def estadoAptitud(self, val):
        self.estadoaptitud = val

    @property
    def tieneAnalisis(self):
        return self.tieneanalisis

    @tieneAnalisis.setter
    def tieneAnalisis(self, val):
        self.tieneanalisis = val

    @property
    def fechaRegistroPostulante(self):
        return self.fecharegistropostulante

    @property
    def carnetProvisionalCodigo(self):
        return self.carnetprovisionalcodigo

    @carnetProvisionalCodigo.setter
    def carnetProvisionalCodigo(self, val):
        self.carnetprovisionalcodigo = val


class Donante(models.Model):
    idpersona = models.OneToOneField(
        Persona, 
        primary_key=True, 
        on_delete=models.CASCADE, 
        db_column='idpersona',
        related_name='donante'
    )
    carnetdigitalcodigo = models.CharField(max_length=30, unique=True, db_column='carnetdigitalcodigo')
    tipodonante = models.CharField(
        max_length=30,
        default='Voluntario Altruista',
        choices=[
            ('Voluntario Altruista', 'Voluntario Altruista'),
            ('Reposicion Familiar', 'Reposicion Familiar'),
            ('Autologo', 'Autologo'),
        ],
        db_column='tipodonante'
    )
    estadohabilitacion = models.CharField(
        max_length=30,
        default='Apto',
        choices=[
            ('Apto', 'Apto'),
            ('Diferido Temporal', 'Diferido Temporal'),
            ('Diferido Definitivo', 'Diferido Definitivo'),
        ],
        db_column='estadohabilitacion'
    )
    fechaultimadonacion = models.DateField(null=True, blank=True, db_column='fechaultimadonacion')

    objects = FlexibleManager()

    class Meta:
        managed = False
        db_table = 'donante'
        verbose_name = 'Donante'
        verbose_name_plural = 'Donantes'

    def __str__(self):
        return f"{self.idpersona.nombreCompleto} - {self.carnetdigitalcodigo} ({self.estadohabilitacion})"

    @property
    def persona(self):
        return self.idpersona

    @persona.setter
    def persona(self, val):
        self.idpersona = val

    @property
    def carnetDigitalCodigo(self):
        return self.carnetdigitalcodigo

    @carnetDigitalCodigo.setter
    def carnetDigitalCodigo(self, val):
        self.carnetdigitalcodigo = val

    @property
    def tipoDonante(self):
        return self.tipodonante

    @tipoDonante.setter
    def tipoDonante(self, val):
        self.tipodonante = val

    @property
    def estadoHabilitacion(self):
        return self.estadohabilitacion

    @estadoHabilitacion.setter
    def estadoHabilitacion(self, val):
        self.estadohabilitacion = val

    @property
    def fechaUltimaDonacion(self):
        return self.fechaultimadonacion

    @fechaUltimaDonacion.setter
    def fechaUltimaDonacion(self, val):
        self.fechaultimadonacion = val


class Receptor(models.Model):
    idpersona = models.OneToOneField(
        Persona,
        primary_key=True,
        on_delete=models.CASCADE,
        db_column='idpersona',
        related_name='receptor'
    )
    codigohistorialclinico = models.CharField(max_length=40, unique=True, db_column='codigohistorialclinico')
    gruposanguineoreceptor = models.CharField(max_length=30, db_column='gruposanguineoreceptor')
    idgrupo = models.ForeignKey(
        'inventario.GrupoSanguineo',
        on_delete=models.RESTRICT,
        null=True,
        blank=True,
        db_column='idgrupo'
    )

    objects = FlexibleManager()

    class Meta:
        managed = False
        db_table = 'receptor'
        verbose_name = 'Receptor'
        verbose_name_plural = 'Receptores'

    def __str__(self):
        return f"{self.idpersona} - {self.codigohistorialclinico} ({self.gruposanguineoreceptor})"


class RequisitoDonacion(models.Model):
    idrequisito = models.AutoField(primary_key=True, db_column='idrequisito')
    nombrerequisito = models.CharField(max_length=120, db_column='nombrerequisito')
    tiporequisito = models.CharField(max_length=40, db_column='tiporequisito')
    esexcluyentedefinitivo = models.BooleanField(default=False, db_column='esexcluyentedefinitivo')

    objects = FlexibleManager()

    class Meta:
        managed = False
        db_table = 'requisitodonacion'
        verbose_name = 'Requisito de Donación'
        verbose_name_plural = 'Requisitos de Donación'

    def __str__(self):
        return f"{self.nombrerequisito} ({self.tiporequisito})"


class CitaDonacion(models.Model):
    idcita = models.AutoField(primary_key=True, db_column='idcita')
    idpersona = models.ForeignKey(
        Persona,
        on_delete=models.CASCADE,
        db_column='idpersona',
        related_name='citas_donacion'
    )
    fechahoraprogramada = models.DateTimeField(db_column='fechahoraprogramada')
    prefiltroaprobado = models.BooleanField(default=False, db_column='prefiltroaprobado')
    asistenciaconfirmada = models.BooleanField(default=False, db_column='asistenciaconfirmada')
    estadocita = models.CharField(
        max_length=25,
        default='Programada',
        choices=[
            ('Programada', 'Programada'),
            ('Atendida', 'Atendida'),
            ('Cancelada', 'Cancelada'),
            ('Inasistencia', 'Inasistencia')
        ],
        db_column='estadocita'
    )

    objects = FlexibleManager()

    class Meta:
        managed = False
        db_table = 'citadonacion'
        verbose_name = 'Cita de Donación'
        verbose_name_plural = 'Citas de Donación'
        ordering = ['-fechahoraprogramada']

    def __str__(self):
        return f"Cita #{self.idcita} ({self.estadocita}) - {self.fechahoraprogramada}"


class DetalleCitaRequisito(models.Model):
    iddetallecita = models.AutoField(primary_key=True, db_column='iddetallecita')
    idcita = models.ForeignKey(
        CitaDonacion,
        on_delete=models.CASCADE,
        db_column='idcita',
        related_name='requisitos_evaluados'
    )
    idrequisito = models.ForeignKey(
        RequisitoDonacion,
        on_delete=models.CASCADE,
        db_column='idrequisito'
    )
    cumplerequisito = models.BooleanField(db_column='cumplerequisito')
    observacionrespuesta = models.CharField(max_length=200, null=True, blank=True, db_column='observacionrespuesta')

    objects = FlexibleManager()

    class Meta:
        managed = False
        db_table = 'detallecitarequisito'
        verbose_name = 'Detalle Cita Requisito'
        verbose_name_plural = 'Detalles Citas Requisitos'


class TriajeClinico(models.Model):
    idtriaje = models.AutoField(primary_key=True, db_column='idtriaje')
    idposibledonador = models.ForeignKey(
        PosibleDonador,
        on_delete=models.CASCADE,
        db_column='idposibledonador',
        related_name='triajes'
    )
    idpersonalsalud = models.ForeignKey(
        'seguridad.PersonalSalud',
        on_delete=models.RESTRICT,
        db_column='idpersonalsalud',
        related_name='triajes_realizados'
    )
    fechahora = models.DateTimeField(default=timezone.now, db_column='fechahora')
    pesokg = models.DecimalField(max_digits=5, decimal_places=2, db_column='pesokg')
    presionsistolicammhg = models.IntegerField(db_column='presionsistolicammhg')
    presiondiastolicammhg = models.IntegerField(db_column='presiondiastolicammhg')
    nivelhemoglobina = models.DecimalField(max_digits=4, decimal_places=1, db_column='nivelhemoglobina')
    temperatura = models.DecimalField(max_digits=4, decimal_places=1, db_column='temperatura')
    resultadoaptitud = models.CharField(
        max_length=20,
        choices=[('Apto', 'Apto'), ('Rechazado', 'Rechazado')],
        db_column='resultadoaptitud'
    )

    objects = FlexibleManager()

    class Meta:
        managed = False
        db_table = 'triajeclinico'
        verbose_name = 'Triaje Clínico'
        verbose_name_plural = 'Triajes Clínicos'
        ordering = ['-fechahora']

    def __str__(self):
        return f"Triaje #{self.idtriaje} - {self.resultadoaptitud} ({self.fechahora})"


class Diferimiento(models.Model):
    iddiferimiento = models.AutoField(primary_key=True, db_column='iddiferimiento')
    idtriaje = models.OneToOneField(
        TriajeClinico,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        db_column='idtriaje',
        related_name='diferimiento'
    )
    idposibledonador = models.ForeignKey(
        PosibleDonador,
        on_delete=models.CASCADE,
        db_column='idposibledonador',
        related_name='diferimientos'
    )
    motivodetallado = models.CharField(max_length=255, db_column='motivodetallado')
    diasinhabilitacion = models.IntegerField(default=0, db_column='diasinhabilitacion')
    fechainiciodiferimiento = models.DateField(db_column='fechainiciodiferimiento')
    fechafindiferimiento = models.DateField(null=True, blank=True, db_column='fechafindiferimiento')

    objects = FlexibleManager()

    class Meta:
        managed = False
        db_table = 'diferimiento'
        verbose_name = 'Diferimiento'
        verbose_name_plural = 'Diferimientos'
        ordering = ['-fechafindiferimiento']

    def __str__(self):
        return f"Diferimiento #{self.iddiferimiento} hasta {self.fechafindiferimiento}: {self.motivodetallado}"


class ExtraccionDonacion(models.Model):
    idextraccion = models.AutoField(primary_key=True, db_column='idextraccion')
    idpersonadonante = models.ForeignKey(
        Persona, 
        on_delete=models.CASCADE, 
        db_column='idpersonadonante',
        related_name='extracciones'
    )
    idpersonalsalud = models.ForeignKey(
        'seguridad.PersonalSalud', 
        on_delete=models.RESTRICT, 
        db_column='idpersonalsalud',
        related_name='extracciones_realizadas',
        null=True,
        blank=True
    )
    codigoextraccion = models.CharField(max_length=30, unique=True, db_column='codigoextraccion')
    fechahora = models.DateTimeField(default=timezone.now, db_column='fechahora')
    volumenextraidoml = models.IntegerField(db_column='volumenextraidoml')
    brazoextraccion = models.CharField(
        max_length=15,
        choices=[('Izquierdo', 'Izquierdo'), ('Derecho', 'Derecho')],
        db_column='brazoextraccion'
    )
    idtriaje = models.ForeignKey(
        TriajeClinico,
        null=True,
        blank=True,
        on_delete=models.RESTRICT,
        db_column='idtriaje',
        related_name='extracciones'
    )

    objects = FlexibleManager()

    class Meta:
        managed = False
        db_table = 'extracciondonacion'
        verbose_name = 'Extracción de Donación'
        verbose_name_plural = 'Extracciones de Donaciones'
        ordering = ['-fechahora']

    def __str__(self):
        return f"{self.codigoextraccion} - {self.idpersonadonante.nombreCompleto} ({self.volumenextraidoml} ml)"

    @property
    def idExtraccion(self):
        return self.idextraccion

    @property
    def personaDonante(self):
        return self.idpersonadonante

    @personaDonante.setter
    def personaDonante(self, val):
        self.idpersonadonante = val

    @property
    def personalSalud(self):
        return self.idpersonalsalud

    @personalSalud.setter
    def personalSalud(self, val):
        self.idpersonalsalud = val

    @property
    def codigoExtraccion(self):
        return self.codigoextraccion

    @codigoExtraccion.setter
    def codigoExtraccion(self, val):
        self.codigoextraccion = val

    @property
    def fechaHora(self):
        return self.fechahora

    @fechaHora.setter
    def fechaHora(self, val):
        self.fechahora = val

    @property
    def volumenExtraidoMl(self):
        return self.volumenextraidoml

    @volumenExtraidoMl.setter
    def volumenExtraidoMl(self, val):
        self.volumenextraidoml = val

    @property
    def brazoExtraccion(self):
        return self.brazoextraccion

    @brazoExtraccion.setter
    def brazoExtraccion(self, val):
        self.brazoextraccion = val

    @property
    def idTriaje(self):
        return self.idtriaje

    @idTriaje.setter
    def idTriaje(self, val):
        self.idtriaje = val


class ConsentimientoInformado(models.Model):
    idconsentimiento = models.AutoField(primary_key=True, db_column='idconsentimiento')
    idextraccion = models.OneToOneField(
        ExtraccionDonacion,
        on_delete=models.CASCADE,
        db_column='idextraccion',
        related_name='consentimiento'
    )
    fechafirma = models.DateTimeField(default=timezone.now, db_column='fechafirma')
    declaracionjuradaaceptada = models.BooleanField(default=True, db_column='declaracionjuradaaceptada')
    firmadigital = models.TextField(db_column='firmadigital')

    objects = FlexibleManager()

    class Meta:
        managed = False
        db_table = 'consentimientoinformado'
        verbose_name = 'Consentimiento Informado'
        verbose_name_plural = 'Consentimientos Informados'


class IncentivoEntrega(models.Model):
    idincentivo = models.AutoField(primary_key=True, db_column='idincentivo')
    idextraccion = models.OneToOneField(
        ExtraccionDonacion,
        on_delete=models.CASCADE,
        db_column='idextraccion',
        related_name='incentivo'
    )
    tipoarticulo = models.CharField(max_length=80, db_column='tipoarticulo')
    refrigerioentregado = models.BooleanField(default=True, db_column='refrigerioentregado')
    fechahoraentrega = models.DateTimeField(default=timezone.now, db_column='fechahoraentrega')

    objects = FlexibleManager()

    class Meta:
        managed = False
        db_table = 'incentivoentrega'
        verbose_name = 'Incentivo de Entrega'
        verbose_name_plural = 'Incentivos de Entrega'


def generar_codigo_analisis():
    import uuid
    return f"SER-{uuid.uuid4().hex[:10].upper()}"


class AnalisisInmunoSerologico(models.Model):
    idanalisis = models.AutoField(primary_key=True, db_column='idanalisis')
    idunidadmadre = models.OneToOneField(
        'inventario.UnidadSangreTotal',
        on_delete=models.CASCADE,
        db_column='idunidadmadre',
        related_name='analisis_serologico'
    )
    idpersonalsalud = models.ForeignKey(
        'seguridad.PersonalSalud',
        on_delete=models.RESTRICT,
        db_column='idpersonalsalud',
        related_name='analisis_serologicos',
        null=True,
        blank=True
    )
    codigoanalisis = models.CharField(
        max_length=30, 
        unique=True, 
        default=generar_codigo_analisis, 
        db_column='codigoanalisis'
    )
    fechaanalisis = models.DateTimeField(default=timezone.now, db_column='fechaanalisis')
    resultadovih = models.CharField(max_length=20, default='No Reactivo', db_column='resultadovih')
    resultadochagas = models.CharField(max_length=20, default='No Reactivo', db_column='resultadochagas')
    resultadohepatitisb = models.CharField(max_length=20, default='No Reactivo', db_column='resultadohepatitisb')
    resultadohepatitisc = models.CharField(max_length=20, default='No Reactivo', db_column='resultadohepatitisc')
    resultadosifilis = models.CharField(max_length=20, default='No Reactivo', db_column='resultadosifilis')
    resultadohtlv = models.CharField(max_length=20, default='No Reactivo', db_column='resultadohtlv')
    dictamenfinal = models.CharField(
        max_length=20,
        default='Apto',
        choices=[('Apto', 'Apto'), ('No Apto', 'No Apto')],
        db_column='dictamenfinal'
    )
    habilitaextraccion = models.BooleanField(default=False, db_column='habilitaextraccion')

    objects = FlexibleManager()

    class Meta:
        managed = False
        db_table = 'analisisinmunoserologico'
        verbose_name = 'Análisis Inmuno-Serológico'
        verbose_name_plural = 'Análisis Inmuno-Serológicos'

    def __str__(self):
        return f"Análisis #{self.idanalisis} ({self.dictamenfinal})"

    @property
    def idAnalisis(self):
        return self.idanalisis

    @property
    def idAnalisisSerologico(self):
        return self.idanalisis

    @property
    def idanalisisserologico(self):
        return self.idanalisis

    @property
    def vihresultado(self):
        return self.resultadovih

    @vihresultado.setter
    def vihresultado(self, val):
        self.resultadovih = val

    @property
    def hepatitisbresultado(self):
        return self.resultadohepatitisb

    @hepatitisbresultado.setter
    def hepatitisbresultado(self, val):
        self.resultadohepatitisb = val

    @property
    def hepatitiscresultado(self):
        return self.resultadohepatitisc

    @hepatitiscresultado.setter
    def hepatitiscresultado(self, val):
        self.resultadohepatitisc = val

    @property
    def chagasresultado(self):
        return self.resultadochagas

    @chagasresultado.setter
    def chagasresultado(self, val):
        self.resultadochagas = val

    @property
    def sifilisresultado(self):
        return self.resultadosifilis

    @sifilisresultado.setter
    def sifilisresultado(self, val):
        self.resultadosifilis = val

    @property
    def htlvresultado(self):
        return self.resultadohtlv

    @htlvresultado.setter
    def htlvresultado(self, val):
        self.resultadohtlv = val


class AnalisisInmunoHematologico(models.Model):
    idanalisishematologico = models.AutoField(primary_key=True, db_column='idanalisishematologico')
    idpersonalsalud = models.ForeignKey(
        'seguridad.PersonalSalud',
        on_delete=models.RESTRICT,
        db_column='idpersonalsalud',
        related_name='analisis_hematologicos'
    )
    idposibledonador = models.ForeignKey(
        PosibleDonador,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        db_column='idposibledonador'
    )
    idreceptor = models.ForeignKey(
        Receptor,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        db_column='idreceptor'
    )
    idunidadmadre = models.ForeignKey(
        'inventario.UnidadSangreTotal',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        db_column='idunidadmadre'
    )
    idcitalab = models.ForeignKey(
        'CitaLaboratorio',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        db_column='idcitalab'
    )
    etapaanalisis = models.CharField(
        max_length=50,
        choices=[
            ('Pre-Extraccion', 'Pre-Extraccion'),
            ('Post-Extraccion', 'Post-Extraccion'),
            ('Pre-Transfusional', 'Pre-Transfusional')
        ],
        db_column='etapaanalisis'
    )
    fechaanalisis = models.DateTimeField(default=timezone.now, db_column='fechaanalisis')
    grupoaboconfirmado = models.CharField(
        max_length=5,
        choices=[('A', 'A'), ('B', 'B'), ('AB', 'AB'), ('O', 'O')],
        db_column='grupoaboconfirmado'
    )
    factorrhconfirmado = models.CharField(
        max_length=10,
        choices=[('Positivo', 'Positivo'), ('Negativo', 'Negativo')],
        db_column='factorrhconfirmado'
    )
    pruebacoombsdirecta = models.CharField(max_length=30, db_column='pruebacoombsdirecta')
    pruebacoombsindirecta = models.CharField(max_length=30, db_column='pruebacoombsindirecta')
    rastreoanticuerposirregulares = models.CharField(max_length=100, db_column='rastreoanticuerposirregulares')
    observaciones = models.TextField(null=True, blank=True, db_column='observaciones')
    fasesalina = models.CharField(max_length=30, null=True, blank=True, db_column='fasesalina')
    fasetermica = models.CharField(max_length=30, null=True, blank=True, db_column='fasetermica')
    dictameninmunohematologico = models.CharField(max_length=100, null=True, blank=True, db_column='dictameninmunohematologico')

    objects = FlexibleManager()

    class Meta:
        managed = False
        db_table = 'analisisinmunohematologico'
        verbose_name = 'Análisis Inmuno-Hematológico'
        verbose_name_plural = 'Análisis Inmuno-Hematológicos'


class CitaLaboratorio(models.Model):
    idcitalab = models.AutoField(primary_key=True, db_column='idcitalab')
    idreceptor = models.ForeignKey(
        Receptor,
        on_delete=models.CASCADE,
        db_column='idreceptor',
        related_name='citas_laboratorio'
    )
    idinstitucion = models.ForeignKey(
        'inventario.InstitucionSalud',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        db_column='idinstitucion'
    )
    fechahoracita = models.DateTimeField(db_column='fechahoracita')
    fechacirugiaprogramada = models.DateField(db_column='fechacirugiaprogramada')
    tipoanalisisrequerido = models.CharField(max_length=100, db_column='tipoanalisisrequerido')
    muestrarecolectada = models.BooleanField(default=False, db_column='muestrarecolectada')
    estadocita = models.CharField(
        max_length=25,
        default='Programada',
        choices=[
            ('Programada', 'Programada'),
            ('Completada', 'Completada'),
            ('Cancelada', 'Cancelada')
        ],
        db_column='estadocita'
    )

    objects = FlexibleManager()

    class Meta:
        managed = False
        db_table = 'citalaboratorio'
        verbose_name = 'Cita de Laboratorio'
        verbose_name_plural = 'Citas de Laboratorio'


class CompromisoDonacion(models.Model):
    idcompromiso = models.AutoField(primary_key=True, db_column='idcompromiso')
    idreposicion = models.ForeignKey(
        'inventario.ReposicionPendiente',
        on_delete=models.CASCADE,
        db_column='idreposicion',
        related_name='compromisos'
    )
    idpersonafirmante = models.ForeignKey(
        Persona,
        on_delete=models.CASCADE,
        db_column='idpersonafirmante',
        related_name='compromisos_firmados'
    )
    iddonante = models.ForeignKey(
        Donante,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        db_column='iddonante',
        related_name='compromisos_donante'
    )
    idextraccion = models.ForeignKey(
        ExtraccionDonacion,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        db_column='idextraccion',
        related_name='compromisos'
    )
    fechacompromiso = models.DateField(default=timezone.now, db_column='fechacompromiso')
    donacionconcretada = models.BooleanField(default=False, db_column='donacionconcretada')
    volumendonadoefectivoml = models.IntegerField(default=0, db_column='volumendonadoefectivoml')
    estadocompromiso = models.CharField(
        max_length=25,
        default='Vigente',
        choices=[('Vigente', 'Vigente'), ('Cumplido', 'Cumplido'), ('Anulado', 'Anulado')],
        db_column='estadocompromiso'
    )

    objects = FlexibleManager()

    class Meta:
        managed = False
        db_table = 'compromisodonacion'
        verbose_name = 'Compromiso de Donación'
        verbose_name_plural = 'Compromisos de Donación'

    def __str__(self):
        return f"Compromiso #{self.idcompromiso} ({self.estadocompromiso})"
