"""Inventario FEFO, laboratorio, custodia autóloga e indicadores institucionales."""

from datetime import timedelta, date, datetime, time
from collections import Counter
from uuid import uuid4
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView
from .models import (
    UnidadSangreTotal,
    EjemplarBolsa,
    ParametroStockMinimo,
    UbicacionAlmacen,
    GrupoSanguineo,
    ReservaSangre,
    BajaInventario,
    ReposicionPendiente,
    SolicitudHospitalaria,
)
from apps.donantes.models import (
    Persona,
    PosibleDonador,
    Donante,
    Receptor,
    CitaDonacion,
    CitaLaboratorio,
    AnalisisInmunoSerologico,
    AnalisisInmunoHematologico,
    ExtraccionDonacion,
    TriajeClinico,
    IncentivoEntrega,
)
from apps.donantes.views import staff
from apps.donantes.services import block_if_ineligible
from apps.seguridad.models import Usuario, Rol, UsuarioRol
from apps.seguridad.permissions import ClinicalRole, IsAdminRole, IsHealthStaffRole
from apps.seguridad.views import audit
from .serializers import (
    ParametroStockMinimoSerializer,
    ParametroStockMinimoUpdateSerializer,
)

COMPONENTS = [
    "Concentrado de Globulos Rojos",
    "Plasma Fresco Congelado",
    "Concentrado Plaquetario",
]
AGES = ["Adulto", "Adolescente", "Pediátrico"]


def release_location(bag):
    if bag.idubicacion_id:
        location = UbicacionAlmacen.objects.select_for_update().get(
            pk=bag.idubicacion_id
        )
        location.capacidadocupada = max(0, location.capacidadocupada - 1)
        location.save(update_fields=["capacidadocupada"])


def retire(request, bag, reason):
    if bag.estadobolsak == "Baja":
        return
    bag.estadobolsak = "Baja"
    bag.save(update_fields=["estadobolsak"])
    release_location(bag)
    BajaInventario.objects.create(
        idunidadmadre=None,
        idejemplarbolsa=bag,
        idpersonalsalud=staff(request),
        motivobaja=reason,
    )
    audit(request, reason, "EjemplarBolsa", bag.pk)


def expire(request):
    with transaction.atomic():
        for bag in (
            EjemplarBolsa.objects.select_for_update()
            .filter(estadobolsak="Disponible", fechacaducidad__lt=timezone.localdate())
            .order_by("idejemplarbolsa")
        ):
            retire(request, bag, "Vencimiento de Caducidad")


class MonitorStockSemaforoView(APIView):
    permission_classes = [IsHealthStaffRole]

    def get(self, request):
        expire(request)
        today = timezone.localdate()
        age, component = (
            request.query_params.get("categoriaetaria"),
            request.query_params.get("componente"),
        )
        parameters = ParametroStockMinimo.objects.select_related("idgrupo")
        bags = EjemplarBolsa.objects.filter(
            estadobolsak="Disponible",
            esexclusivoautologo=False,
            fechacaducidad__gte=today,
        )
        if age and age != "Todos":
            parameters, bags = (
                parameters.filter(categoriaetaria=age),
                bags.filter(categoriaetaria=age),
            )
        if component:
            parameters, bags = (
                parameters.filter(tipocomponente=component),
                bags.filter(tipocomponente=component),
            )
        counts = Counter(
            (b["idgrupo"], b["tipocomponente"], b["categoriaetaria"])
            for b in bags.values("idgrupo", "tipocomponente", "categoriaetaria")
        )
        cards = []
        for p in parameters:
            available = counts[(p.idgrupo_id, p.tipocomponente, p.categoriaetaria)]
            cards.append(
                {
                    "idparametro": p.pk,
                    "idgrupo": p.idgrupo_id,
                    "grupo_sanguineo": str(p.idgrupo.tipificacion),
                    "tipocomponente": p.tipocomponente,
                    "categoriaetaria": p.categoriaetaria,
                    "stock_disponible": available,
                    "stock_minimo_seguridad": p.stockminimoseguridad,
                    "stock_critico_alerta": p.stockcriticoalerta,
                    "semaforo": "Rojo"
                    if available <= p.stockcriticoalerta
                    else (
                        "Amarillo" if available < p.stockminimoseguridad else "Verde"
                    ),
                }
            )
        fefo = [
            {
                "idejemplarbolsa": b.pk,
                "codigo": b.codigoejemplark,
                "componente": b.tipocomponente,
                "categoriaetaria": b.categoriaetaria,
                "grupo": b.idgrupo.tipificacion,
                "fechacaducidad": b.fechacaducidad,
                "dias_restantes": (b.fechacaducidad - today).days,
            }
            for b in bags.filter(fechacaducidad__lte=today + timedelta(days=7))
            .select_related("idgrupo")
            .order_by("fechacaducidad", "idejemplarbolsa")
        ]
        return Response(
            {
                "resumen_stock": cards,
                "tarjetas": cards,
                "cola_fefo": fefo,
                "cola_proximos_a_vencer": fefo,
            }
        )


class StockAlertasListView(MonitorStockSemaforoView):
    pass


class ParametroStockMinimoListView(APIView):
    permission_classes = [IsHealthStaffRole]

    def get(self, request):
        return Response(
            ParametroStockMinimoSerializer(
                ParametroStockMinimo.objects.select_related("idgrupo"), many=True
            ).data
        )

    @transaction.atomic
    def post(self, request):
        if not IsAdminRole().has_permission(request, self):
            from rest_framework.exceptions import PermissionDenied

            raise PermissionDenied()

        class Parameter(serializers.Serializer):
            idgrupo = serializers.PrimaryKeyRelatedField(
                queryset=GrupoSanguineo.objects.all()
            )
            tipocomponente = serializers.ChoiceField(choices=COMPONENTS)
            categoriaetaria = serializers.ChoiceField(choices=AGES)
            stockminimoseguridad = serializers.IntegerField(min_value=1)
            stockcriticoalerta = serializers.IntegerField(min_value=0)

        s = Parameter(data=request.data)
        s.is_valid(raise_exception=True)
        d = s.validated_data
        if d["stockcriticoalerta"] >= d["stockminimoseguridad"]:
            raise serializers.ValidationError(
                "El umbral crítico debe ser menor que el mínimo de seguridad."
            )
        # Bloquear el grupo serializa la creación del parámetro único sin cambiar el schema.
        GrupoSanguineo.objects.select_for_update().get(pk=d["idgrupo"].pk)
        if ParametroStockMinimo.objects.filter(
            idgrupo=d["idgrupo"],
            tipocomponente=d["tipocomponente"],
            categoriaetaria=d["categoriaetaria"],
        ).exists():
            raise serializers.ValidationError(
                "Ya existe un parámetro para ese grupo, componente y categoría."
            )
        p = ParametroStockMinimo.objects.create(**d)
        audit(request, "Parámetro de stock creado", "ParametroStockMinimo", p.pk)
        return Response(ParametroStockMinimoSerializer(p).data, status=201)


class ParametroStockMinimoUpdateView(APIView):
    permission_classes = [IsAdminRole]

    @transaction.atomic
    def put(self, request, pk):
        p = get_object_or_404(ParametroStockMinimo.objects.select_for_update(), pk=pk)
        s = ParametroStockMinimoUpdateSerializer(p, data=request.data, partial=True)
        s.is_valid(raise_exception=True)
        s.save()
        audit(request, "Umbrales de stock actualizados", "ParametroStockMinimo", p.pk)
        return Response(ParametroStockMinimoSerializer(p).data)

    patch = put


class FraccionarUnidadMadreView(APIView):
    permission_classes = [ClinicalRole]
    allowed_roles = ["ADMIN", "BIOQ_INTEGRAL"]

    @transaction.atomic
    def post(self, request, idunidadmadre):
        age = request.data.get("categoriaetaria")
        if age not in AGES:
            raise serializers.ValidationError("Selecciona la categoría etaria.")
        mother = get_object_or_404(
            UnidadSangreTotal.objects.select_for_update(), pk=idunidadmadre
        )
        if (
            mother.estadoliberacion == "Rechazada"
            or EjemplarBolsa.objects.filter(idunidadmadre=mother).exists()
        ):
            raise serializers.ValidationError(
                "La unidad está rechazada o ya fue fraccionada."
            )
        locations = request.data.get("ubicaciones", {})
        if not isinstance(locations, dict) or set(locations) != {"gr", "pl", "pq"}:
            raise serializers.ValidationError("Selecciona las ubicaciones gr, pl y pq.")
        try:
            ids = [int(locations[k]) for k in ("gr", "pl", "pq")]
        except (ValueError, TypeError):
            raise serializers.ValidationError("Ubicaciones inválidas.")
        rooms = {
            r.pk: r
            for r in UbicacionAlmacen.objects.select_for_update()
            .filter(pk__in=ids)
            .order_by("idubicacion")
        }
        if len(rooms) != len(set(ids)):
            raise serializers.ValidationError("Una ubicación seleccionada no existe.")
        quantities = Counter({})
        quantities.update(
            [ids[0]] * (3 if age == "Pediátrico" else 1) + [ids[1], ids[2]]
        )
        for room_id, amount in quantities.items():
            if (
                rooms[room_id].capacidadocupada + amount
                > rooms[room_id].capacidadmaxima
            ):
                raise serializers.ValidationError(
                    "Capacidad insuficiente en la ubicación seleccionada."
                )
        auto = Donante.objects.filter(
            pk=mother.idextraccion.idpersonadonante_id, tipodonante="Autologo"
        ).exists()
        state = (
            "Disponible"
            if mother.estadoliberacion == "Liberada Apta" and not auto
            else "En Cuarentena"
        )
        extracted = timezone.localtime(mother.idextraccion.fechahora).date()
        parts = (
            [(f"K1P{i}-GR", 75, 0, 35) for i in range(1, 4)]
            if age == "Pediátrico"
            else [("K1-GR", 250 if age == "Adulto" else 180, 0, 35)]
        )
        parts += [
            ("K2-PL", 100 if age == "Pediátrico" else 150, 1, 365),
            ("K3-PQ", 55 if age == "Adolescente" else 50, 2, 5),
        ]
        if (
            sum(volume for _, volume, _, _ in parts)
            > mother.idextraccion.volumenextraidoml
        ):
            raise serializers.ValidationError(
                "El volumen de los componentes excede la extracción registrada."
            )
        if any(
            extracted + timedelta(days=days) < timezone.localdate()
            for _, _, _, days in parts
        ):
            raise serializers.ValidationError(
                "La fecha de extracción supera la vigencia de los componentes."
            )
        codes = []
        for suffix, volume, index, days in parts:
            code = f"{mother.codigobolsamadre}-{suffix}"
            EjemplarBolsa.objects.create(
                idunidadmadre=mother,
                idgrupo=mother.idgrupo,
                idubicacion=rooms[ids[index]],
                codigoejemplark=code,
                tipocomponente=COMPONENTS[index],
                volumenml=volume,
                fechaextraccion=extracted,
                fechacaducidad=extracted + timedelta(days=days),
                estadobolsak=state,
                categoriaetaria=age,
                esexclusivoautologo=auto,
            )
            codes.append(code)
        for room_id, amount in quantities.items():
            room = rooms[room_id]
            room.capacidadocupada += amount
            room.save(update_fields=["capacidadocupada"])
        audit(request, f"Fraccionamiento {age}", "UnidadSangreTotal", mother.pk)
        return Response(
            {"ejemplares_generados": codes, "estado_asignado": state}, status=201
        )


class HematologiaView(APIView):
    permission_classes = [ClinicalRole]
    allowed_roles = ["ADMIN", "BIOQ_INTEGRAL"]

    @transaction.atomic
    def post(self, request):
        class Result(serializers.Serializer):
            idpersona = serializers.PrimaryKeyRelatedField(
                queryset=Persona.objects.all()
            )
            idunidadmadre = serializers.PrimaryKeyRelatedField(
                queryset=UnidadSangreTotal.objects.all(), required=False
            )
            grupoaboconfirmado = serializers.ChoiceField(choices=["A", "B", "AB", "O"])
            factorrhconfirmado = serializers.ChoiceField(
                choices=["Positivo", "Negativo"]
            )
            pruebacoombsdirecta = serializers.CharField(max_length=30)
            pruebacoombsindirecta = serializers.CharField(max_length=30)
            rastreoanticuerposirregulares = serializers.CharField(max_length=100)
            dictameninmunohematologico = serializers.ChoiceField(
                choices=["Apto", "No Apto"]
            )

        s = Result(data=request.data)
        s.is_valid(raise_exception=True)
        d = dict(s.validated_data)
        p = Persona.objects.select_for_update().get(pk=d.pop("idpersona").pk)
        mother = d.get("idunidadmadre")
        if mother and mother.idextraccion.idpersonadonante_id != p.pk:
            raise serializers.ValidationError("La unidad pertenece a otra persona.")
        possible, _ = PosibleDonador.objects.get_or_create(
            idpersona=p, defaults={"carnetprovisionalcodigo": f"HV-POST-{p.pk:08d}"}
        )
        a = AnalisisInmunoHematologico.objects.create(
            idposibledonador=possible,
            idpersonalsalud=staff(request),
            etapaanalisis="Post-Extraccion" if mother else "Pre-Extraccion",
            **d,
        )
        possible.tieneanalisis = True
        possible.estadoaptitud = (
            "Apto" if d["dictameninmunohematologico"] == "Apto" else "No Apto"
        )
        possible.save(update_fields=["tieneanalisis", "estadoaptitud"])
        audit(
            request,
            "Análisis inmunohematológico registrado",
            "AnalisisInmunoHematologico",
            a.pk,
        )
        return Response({"idanalisishematologico": a.pk}, status=201)


class SerologiaView(APIView):
    permission_classes = [ClinicalRole]
    allowed_roles = ["ADMIN", "BIOQ_INTEGRAL"]

    @transaction.atomic
    def post(self, request, pk):
        mother = get_object_or_404(UnidadSangreTotal.objects.select_for_update(), pk=pk)
        p = Persona.objects.select_for_update().get(
            pk=mother.idextraccion.idpersonadonante_id
        )
        fields = [
            "resultadovih",
            "resultadochagas",
            "resultadohepatitisb",
            "resultadohepatitisc",
            "resultadosifilis",
            "resultadohtlv",
        ]
        if AnalisisInmunoSerologico.objects.filter(idunidadmadre=mother).exists():
            raise serializers.ValidationError(
                "La unidad ya tiene un análisis registrado."
            )
        results = {f: request.data.get(f) for f in fields}
        if any(
            v not in ("No Reactivo", "Reactivo", "Indeterminado")
            for v in results.values()
        ):
            raise serializers.ValidationError(
                "Debes indicar los seis resultados serológicos."
            )
        approved = all(v == "No Reactivo" for v in results.values())
        a = AnalisisInmunoSerologico.objects.create(
            idunidadmadre=mother,
            idpersonalsalud=staff(request),
            codigoanalisis=f"SER-{uuid4().hex[:20]}",
            dictamenfinal="Apto" if approved else "No Apto",
            habilitaextraccion=approved,
            **results,
        )
        # El schema instala el trigger de ascenso. Las operaciones siguientes también sirven
        # en pruebas sin triggers y preservan las restricciones de exclusión de perfiles.
        possible, _ = PosibleDonador.objects.get_or_create(
            idpersona=p, defaults={"carnetprovisionalcodigo": f"HV-POST-{p.pk:08d}"}
        )
        possible.tieneanalisis, possible.estadoaptitud = (
            True,
            "Apto" if approved else "No Apto",
        )
        possible.save(update_fields=["tieneanalisis", "estadoaptitud"])
        mother.estadoliberacion = "Liberada Apta" if approved else "Rechazada"
        mother.save(update_fields=["estadoliberacion"])
        if approved:
            donor, _ = Donante.objects.get_or_create(
                idpersona=p, defaults={"carnetdigitalcodigo": f"HEMO-{p.pk:08d}"}
            )
            donor.fechaultimadonacion = timezone.localtime(
                mother.idextraccion.fechahora
            ).date()
            donor.save(update_fields=["fechaultimadonacion"])
            user = Usuario.objects.filter(idpersona=p).first()
            if user:
                UsuarioRol.objects.filter(
                    idusuario=user, idrol__codigorol="POSIBLE_DONADOR"
                ).delete()
                role = get_object_or_404(Rol, codigorol="DONANTE")
                UsuarioRol.objects.get_or_create(idusuario=user, idrol=role)
            if donor.tipodonante != "Autologo":
                EjemplarBolsa.objects.filter(
                    idunidadmadre=mother,
                    estadobolsak="En Cuarentena",
                    esexclusivoautologo=False,
                ).update(estadobolsak="Disponible")
        else:
            Donante.objects.filter(pk=p.pk).update(
                estadohabilitacion="Diferido Definitivo"
            )
            for b in (
                EjemplarBolsa.objects.select_for_update()
                .filter(idunidadmadre=mother)
                .order_by("idejemplarbolsa")
            ):
                retire(request, b, "Reactividad Serológica")
            ReservaSangre.objects.filter(
                idejemplarbolsa__idunidadmadre=mother, estadoreserva="Activa"
            ).update(estadoreserva="Cancelada")
        audit(
            request,
            f"Tamizaje serológico: {a.dictamenfinal}",
            "AnalisisInmunoSerologico",
            a.pk,
        )
        return Response(
            {"idanalisis": a.pk, "dictamenfinal": a.dictamenfinal}, status=201
        )


class AutologousSerializer(serializers.Serializer):
    idpersona = serializers.PrimaryKeyRelatedField(queryset=Persona.objects.all())
    idgrupo = serializers.PrimaryKeyRelatedField(queryset=GrupoSanguineo.objects.all())
    fechacirugia = serializers.DateField()
    fechahoracita = serializers.DateTimeField()

    def validate(self, d):
        days = (d["fechacirugia"] - d["fechahoracita"].date()).days
        if not 3 <= days <= 30 or d["fechahoracita"] <= timezone.now():
            raise serializers.ValidationError(
                "Programa una cita futura entre 3 y 30 días antes de la cirugía."
            )
        return d


class ProgramarDonacionAutologaView(APIView):
    permission_classes = [ClinicalRole]
    allowed_roles = ["ADMIN", "DOC_TRIAJE", "MED_SOLICITANTE"]

    @transaction.atomic
    def post(self, request):
        s = AutologousSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        d = s.validated_data
        p = Persona.objects.select_for_update().get(pk=d["idpersona"].pk)
        block_if_ineligible(p)
        if CitaDonacion.objects.filter(idpersona=p, estadocita="Programada").exists():
            raise serializers.ValidationError(
                "Ya existe una cita pendiente para el paciente."
            )
        donor, _ = Donante.objects.get_or_create(
            idpersona=p, defaults={"carnetdigitalcodigo": f"HEMO-AUTO-{p.pk}"}
        )
        donor.tipodonante = "Autologo"
        donor.save(update_fields=["tipodonante"])
        PosibleDonador.objects.get_or_create(
            idpersona=p, defaults={"carnetprovisionalcodigo": f"HV-POST-{p.pk:08d}"}
        )
        recipient, _ = Receptor.objects.get_or_create(
            idpersona=p,
            defaults={
                "codigohistorialclinico": f"HC-AUTO-{p.pk}",
                "gruposanguineoreceptor": d["idgrupo"].tipificacion,
                "idgrupo": d["idgrupo"],
            },
        )
        c = CitaDonacion.objects.create(
            idpersona=p, fechahoraprogramada=d["fechahoracita"], prefiltroaprobado=True
        )
        # CitaLaboratorio es la tabla existente que conserva la fecha quirúrgica.
        lab = CitaLaboratorio.objects.create(
            idreceptor=recipient,
            fechahoracita=d["fechahoracita"],
            fechacirugiaprogramada=d["fechacirugia"],
            tipoanalisisrequerido="Protocolo Autólogo",
        )
        audit(request, "Donación autóloga programada", "CitaLaboratorio", lab.pk)
        return Response(
            {
                "idcita": c.pk,
                "idcitalab": lab.pk,
                "carnet_autologo": donor.carnetdigitalcodigo,
            },
            status=201,
        )


class CustodiarFraccionamientoAutologoView(APIView):
    permission_classes = [ClinicalRole]
    allowed_roles = ["ADMIN", "BIOQ_INTEGRAL"]

    @transaction.atomic
    def post(self, request, idunidadmadre):
        mother = get_object_or_404(
            UnidadSangreTotal.objects.select_for_update(), pk=idunidadmadre
        )
        p = Persona.objects.select_for_update().get(
            pk=mother.idextraccion.idpersonadonante_id
        )
        get_object_or_404(Donante, pk=p.pk, tipodonante="Autologo")
        recipient = get_object_or_404(Receptor, pk=p.pk)
        lab = (
            CitaLaboratorio.objects.filter(
                idreceptor=recipient,
                tipoanalisisrequerido="Protocolo Autólogo",
                estadocita="Programada",
            )
            .order_by("-idcitalab")
            .first()
        )
        if not lab or lab.fechacirugiaprogramada < timezone.localdate():
            raise serializers.ValidationError(
                "No existe una cirugía programada vigente."
            )
        if mother.estadoliberacion != "Liberada Apta":
            raise serializers.ValidationError(
                "La serología debe liberar la unidad antes de la custodia."
            )
        bags = list(
            EjemplarBolsa.objects.select_for_update()
            .filter(idunidadmadre=mother)
            .order_by("idejemplarbolsa")
        )
        if not bags or any(
            b.estadobolsak not in ("En Cuarentena", "Reservada")
            or b.fechacaducidad < lab.fechacirugiaprogramada
            for b in bags
        ):
            raise serializers.ValidationError(
                "Se requieren bolsas válidas y vigentes hasta la cirugía."
            )
        for b in bags:
            b.esexclusivoautologo, b.estadobolsak = True, "Reservada"
            b.save(update_fields=["esexclusivoautologo", "estadobolsak"])
            ReservaSangre.objects.get_or_create(
                idejemplarbolsa=b,
                defaults={
                    "idreceptor": recipient,
                    "esautologa": True,
                    "fechavencimientoreserva": lab.fechacirugiaprogramada,
                    "estadoreserva": "Activa",
                    "motivoreserva": "Custodia autóloga exclusiva",
                },
            )
        audit(request, "Custodia autóloga exclusiva", "UnidadSangreTotal", mother.pk)
        return Response({"unidades_reservadas": [b.codigoejemplark for b in bags]})


class CancelarCirugiaAutologaView(APIView):
    permission_classes = [ClinicalRole]
    allowed_roles = ["ADMIN", "DOC_TRIAJE", "MED_SOLICITANTE"]

    @transaction.atomic
    def post(self, request, idpersona_paciente):
        p = get_object_or_404(
            Persona.objects.select_for_update(), pk=idpersona_paciente
        )
        get_object_or_404(Donante, pk=p.pk, tipodonante="Autologo")
        # Incluye unidades aún en cuarentena: una suspensión no puede liberarlas después.
        count = 0
        for b in (
            EjemplarBolsa.objects.select_for_update()
            .filter(
                idunidadmadre__idextraccion__idpersonadonante=p,
                esexclusivoautologo=True,
            )
            .exclude(estadobolsak__in=["Baja", "Despachada"])
            .order_by("idejemplarbolsa")
        ):
            retire(request, b, "Descarte Autólogo por Suspensión Quirúrgica")
            count += 1
        ReservaSangre.objects.filter(
            idreceptor_id=p.pk, esautologa=True, estadoreserva="Activa"
        ).update(estadoreserva="Cancelada")
        CitaLaboratorio.objects.filter(
            idreceptor_id=p.pk,
            tipoanalisisrequerido="Protocolo Autólogo",
            estadocita="Programada",
        ).update(estadocita="Cancelada")
        CitaDonacion.objects.filter(idpersona=p, estadocita="Programada").update(
            estadocita="Cancelada"
        )
        audit(request, "Suspensión quirúrgica definitiva", "Receptor", p.pk)
        return Response({"bolsas_descartadas": count})


class TableroControlKPIsView(APIView):
    permission_classes = [IsAdminRole]

    def get(self, request):
        today = timezone.localdate()
        period = request.query_params.get("periodo", "mensual")
        try:
            start = (
                date.fromisoformat(request.query_params["fecha_inicio"])
                if request.query_params.get("fecha_inicio")
                else today
                - timedelta(
                    days={"diario": 0, "mensual": 29, "semestral": 179}.get(period, 29)
                )
            )
            end = (
                date.fromisoformat(request.query_params["fecha_fin"])
                if request.query_params.get("fecha_fin")
                else today
            )
        except ValueError:
            raise serializers.ValidationError("Fechas inválidas. Usa AAAA-MM-DD.")
        if start > end:
            raise serializers.ValidationError(
                "La fecha inicial debe ser anterior a la final."
            )
        # El schema usa timestamp sin zona: comparar límites UTC evita que PostgreSQL
        # interprete incorrectamente una conversión de fecha por zona horaria.
        lower = timezone.make_aware(datetime.combine(start, time.min))
        upper = timezone.make_aware(datetime.combine(end + timedelta(days=1), time.min))
        dates = {"fechahoraprogramada__gte": lower, "fechahoraprogramada__lt": upper}
        appointments = CitaDonacion.objects.filter(**dates)
        serology = AnalisisInmunoSerologico.objects.filter(
            fechaanalisis__gte=lower, fechaanalisis__lt=upper
        )
        requests = SolicitudHospitalaria.objects.filter(
            fechahorarequerimiento__gte=lower, fechahorarequerimiento__lt=upper
        )
        extractions = ExtraccionDonacion.objects.filter(
            fechahora__gte=lower, fechahora__lt=upper
        )
        replacements = ReposicionPendiente.objects.filter(idsolicitud__in=requests)
        total, attended = (
            appointments.count(),
            appointments.filter(asistenciaconfirmada=True).count(),
        )
        tested, reactive = (
            serology.count(),
            serology.filter(dictamenfinal="No Apto").count(),
        )
        cases, settled = (
            replacements.count(),
            replacements.filter(estadoreposicion="Liquidada").count(),
        )
        active = bool(total or tested or requests.exists() or extractions.exists())
        ratio = lambda a, b: round(100 * a / b, 1) if b else 0.0
        rooms = list(UbicacionAlmacen.objects.all()) if active else []
        ranking = {}
        for r in requests.select_related("idinstitucion"):
            key = r.idinstitucion_id
            item = ranking.setdefault(
                key,
                {
                    "hospital": r.idinstitucion.nombreinstitucion,
                    "total_solicitudes": 0,
                    "bolsas_requeridas": 0,
                    "bolsas_entregadas": 0,
                },
            )
            item["total_solicitudes"] += 1
            item["bolsas_requeridas"] += r.cantidadbolsassolicitadas
            item["bolsas_entregadas"] += r.cantidadentregadareceptor
        return Response(
            {
                "fecha_inicio": start,
                "fecha_fin": end,
                "sin_actividad": not active,
                "kpis": {
                    "total_citas": total,
                    "citas_atendidas": attended,
                    "inasistencias": appointments.filter(
                        estadocita="Inasistencia"
                    ).count(),
                    "tasa_efectividad_citas": ratio(attended, total),
                    "total_serologias": tested,
                    "serologias_aptas": tested - reactive,
                    "serologias_reactivas": reactive,
                    "tasa_positividad_serologica": ratio(reactive, tested),
                    "total_reposiciones": cases,
                    "reposiciones_liquidadas": settled,
                    "reposiciones_pendientes_parciales": replacements.filter(
                        estadoreposicion__in=["Pendiente", "Parcial"]
                    ).count(),
                    "indice_reposicion_cumplida": ratio(settled, cases),
                    "ocupacion_camaras_porcentaje": ratio(
                        sum(c.capacidadocupada for c in rooms),
                        sum(c.capacidadmaxima for c in rooms),
                    ),
                    "total_extracciones": extractions.count(),
                },
                "camaras_detalle": [
                    {
                        "compartimento": c.identificadorcompartimento,
                        "equipo": c.tipoequipo,
                        "temperatura_c": c.temperaturaregistro,
                        "ocupadas": c.capacidadocupada,
                        "maxima": c.capacidadmaxima,
                        "porcentaje_uso": ratio(c.capacidadocupada, c.capacidadmaxima),
                    }
                    for c in rooms
                ],
                "ranking_hospitales": sorted(
                    ranking.values(), key=lambda r: r["bolsas_requeridas"], reverse=True
                ),
            }
        )


class CatalogosView(APIView):
    def get(self, request):
        return Response(
            {
                "grupos": list(GrupoSanguineo.objects.values()),
                "categorias": AGES,
                "componentes": COMPONENTS,
                "ubicaciones": list(UbicacionAlmacen.objects.values())
                if IsHealthStaffRole().has_permission(request, self)
                else [],
            }
        )


class OperacionesView(APIView):
    permission_classes = [IsHealthStaffRole]

    def get(self, request):
        extractions = list(
            ExtraccionDonacion.objects.select_related("idpersonadonante").order_by(
                "-fechahora"
            )[:200]
        )
        return Response(
            {
                "personas": list(
                    Persona.objects.values("idpersona", "ci", "nombres", "apellidos")[
                        :1000
                    ]
                ),
                "triajes": list(
                    TriajeClinico.objects.values(
                        "idtriaje", "idposibledonador", "resultadoaptitud", "fechahora"
                    )[:500]
                ),
                "extracciones": [
                    {
                        "idextraccion": e.pk,
                        "persona": e.idpersonadonante.nombreCompleto,
                        "codigoextraccion": e.codigoextraccion,
                        "refrigerioentregado": IncentivoEntrega.objects.filter(
                            idextraccion=e
                        ).exists(),
                    }
                    for e in extractions
                ],
                "unidades": list(
                    UnidadSangreTotal.objects.values(
                        "idunidadmadre",
                        "codigobolsamadre",
                        "estadoliberacion",
                        "idextraccion",
                        "idextraccion__idpersonadonante",
                    )[:500]
                ),
                "bolsas": list(
                    EjemplarBolsa.objects.values(
                        "idejemplarbolsa",
                        "codigoejemplark",
                        "tipocomponente",
                        "categoriaetaria",
                        "estadobolsak",
                        "fechacaducidad",
                        "esexclusivoautologo",
                    )[:1000]
                ),
                "autologas": list(
                    CitaLaboratorio.objects.filter(
                        tipoanalisisrequerido="Protocolo Autólogo"
                    ).values(
                        "idcitalab",
                        "idreceptor",
                        "fechacirugiaprogramada",
                        "estadocita",
                    )[:500]
                ),
            }
        )
