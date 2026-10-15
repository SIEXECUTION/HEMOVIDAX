"""
Vistas de API REST para la app Inventario y Fraccionamiento de Hemocomponentes.
"""
from datetime import timedelta
from django.db import transaction
from django.db.models import Count, Sum, F
from django.utils import timezone
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated

from .models import (
    UnidadSangreTotal, EjemplarBolsa, ParametroStockMinimo,
    UbicacionAlmacen, GrupoSanguineo, ReservaSangre, BajaInventario,
    ReposicionPendiente, SolicitudHospitalaria, ComprobantePago
)
from apps.donantes.models import Donante, Receptor, CitaDonacion, AnalisisInmunoSerologico, ExtraccionDonacion
from .serializers import (
    ParametroStockMinimoSerializer,
    ParametroStockMinimoUpdateSerializer,
    StockAlertaSerializer,
)
from apps.seguridad.models import BitacoraAuditoria
from apps.seguridad.permissions import IsAdminRole, IsHealthStaffRole
from apps.seguridad.utils import get_client_ip, registrar_auditoria

# Nombres oficiales exigidos por normativa y cruce estricto de base de datos
NOMBRE_OFICIAL_GR = 'Concentrado de Globulos Rojos'
NOMBRE_OFICIAL_PL = 'Plasma Fresco Congelado'
NOMBRE_OFICIAL_PQ = 'Concentrado Plaquetario'


# ============================================================================
# Fraccionamiento de Bolsa Madre según Esquema Etario
# ============================================================================
class FraccionarUnidadMadreView(APIView):
    """
    Fraccionamiento de Bolsa Madre según esquema etario:
    - 'Adulto': 1 GR (280ml), 1 PL (220ml), 1 PQ (60ml)
    - 'Adolescente': 1 GR (180ml), 1 PL (150ml), 1 PQ (55ml)
    - 'Pediátrico': 3 alícuotas satélites GR (-K1P1, -K1P2, -K1P3 de 75ml c/u), 1 PL (100ml), 1 PQ (50ml)
    """
    permission_classes = [AllowAny]

    @transaction.atomic
    def post(self, request, idunidadmadre):
        esquema = request.data.get('categoriaetaria', 'Adulto') # 'Adulto', 'Adolescente', 'Pediátrico'
        idusuario = request.data.get('idusuario')
        rol_activo = request.headers.get('X-Active-Role', 'Bioquímico(a) Integral')

        if esquema not in ['Adulto', 'Adolescente', 'Pediátrico']:
            return Response({'error': 'Categoría etaria inválida.'},
                            status=status.HTTP_400_BAD_REQUEST)

        madre = UnidadSangreTotal.objects.filter(idunidadmadre=idunidadmadre).first()
        if not madre:
            return Response({'error': 'Bolsa madre no existe.'},
                            status=status.HTTP_404_NOT_FOUND)

        if EjemplarBolsa.objects.filter(idunidadmadre=madre).exists():
            return Response({'error': 'Esta unidad madre ya fue fraccionada previamente.'},
                            status=status.HTTP_400_BAD_REQUEST)

        hoy = timezone.now().date()
        estado_inicial = 'Disponible' if madre.estadoliberacion == 'Liberada Apta' else 'En Cuarentena'

        # Ubicaciones por defecto según esquema de cámaras frías
        cam_gr = UbicacionAlmacen.objects.filter(identificadorcompartimento='CAM-01-A').first()
        cam_pl = UbicacionAlmacen.objects.filter(identificadorcompartimento='FREEZER-01').first()
        cam_pq = UbicacionAlmacen.objects.filter(identificadorcompartimento='AGITADOR-01').first()

        bolsas_creadas = []

        # 1. Crear Concentrado de Globulos Rojos (Caducidad: 35 días)
        if esquema == 'Pediátrico':
            # 3 Bolsas Satélites Pediátricas (50-100 ml)
            for i in range(1, 4):
                codigo_k = f"{madre.codigobolsamadre}-K1P{i}-GR"
                b = EjemplarBolsa.objects.create(
                    idunidadmadre=madre,
                    idgrupo=madre.idgrupo,
                    idubicacion=cam_gr,
                    codigoejemplark=codigo_k,
                    tipocomponente=NOMBRE_OFICIAL_GR,
                    volumenml=75,
                    fechaextraccion=hoy,
                    fechacaducidad=hoy + timedelta(days=35),
                    estadobolsak=estado_inicial,
                    categoriaetaria='Pediátrico'
                )
                bolsas_creadas.append(b.codigoejemplark)
            vol_pl, vol_pq = 100, 50
        else:
            vol_gr = 280 if esquema == 'Adulto' else 180
            vol_pl = 220 if esquema == 'Adulto' else 150
            vol_pq = 60 if esquema == 'Adulto' else 55
            codigo_k1 = f"{madre.codigobolsamadre}-K1-GR"
            b1 = EjemplarBolsa.objects.create(
                idunidadmadre=madre,
                idgrupo=madre.idgrupo,
                idubicacion=cam_gr,
                codigoejemplark=codigo_k1,
                tipocomponente=NOMBRE_OFICIAL_GR,
                volumenml=vol_gr,
                fechaextraccion=hoy,
                fechacaducidad=hoy + timedelta(days=35),
                estadobolsak=estado_inicial,
                categoriaetaria=esquema
            )
            bolsas_creadas.append(b1.codigoejemplark)

        # 2. Crear Plasma Fresco Congelado (Caducidad: 365 días)
        b_pl = EjemplarBolsa.objects.create(
            idunidadmadre=madre,
            idgrupo=madre.idgrupo,
            idubicacion=cam_pl,
            codigoejemplark=f"{madre.codigobolsamadre}-K2-PL",
            tipocomponente=NOMBRE_OFICIAL_PL,
            volumenml=vol_pl,
            fechaextraccion=hoy,
            fechacaducidad=hoy + timedelta(days=365),
            estadobolsak=estado_inicial,
            categoriaetaria=esquema
        )
        bolsas_creadas.append(b_pl.codigoejemplark)

        # 3. Crear Concentrado Plaquetario (Caducidad: 5 días)
        b_pq = EjemplarBolsa.objects.create(
            idunidadmadre=madre,
            idgrupo=madre.idgrupo,
            idubicacion=cam_pq,
            codigoejemplark=f"{madre.codigobolsamadre}-K3-PQ",
            tipocomponente=NOMBRE_OFICIAL_PQ,
            volumenml=vol_pq,
            fechaextraccion=hoy,
            fechacaducidad=hoy + timedelta(days=5),
            estadobolsak=estado_inicial,
            categoriaetaria=esquema
        )
        bolsas_creadas.append(b_pq.codigoejemplark)

        ip_origen = get_client_ip(request) if hasattr(request, 'META') else '127.0.0.1'
        BitacoraAuditoria.objects.create(
            idusuario_id=idusuario,
            rolactivo=rol_activo,
            accionrealizada=f"Fraccionamiento {esquema} de bolsa {madre.codigobolsamadre}: {', '.join(bolsas_creadas)}",
            tablaafectada='EjemplarBolsa',
            idregistroafectado=madre.idunidadmadre,
            iporigen=ip_origen
        )

        return Response({
            'mensaje': f'Fraccionamiento ({esquema}) registrado exitosamente.',
            'estado_asignado': estado_inicial,
            'ejemplares_generados': bolsas_creadas
        }, status=status.HTTP_201_CREATED)


# ============================================================================
# Semáforo de Stock y Cola Prioritaria FEFO
# ============================================================================
class MonitorStockSemaforoView(APIView):
    """
    Cruza los registros de ParametroStockMinimo contra EjemplarBolsa
    usando (idgrupo, tipocomponente, categoriaetaria) y calcula la alerta FEFO <= 7 días.
    """
    permission_classes = [AllowAny]

    def get(self, request):
        hoy = timezone.now().date()
        ventana_fefo = hoy + timedelta(days=7)
        filtro_componente = request.query_params.get('componente')
        filtro_edad = request.query_params.get('categoriaetaria')

        parametros = ParametroStockMinimo.objects.select_related('idgrupo').all()
        if filtro_componente:
            parametros = parametros.filter(tipocomponente=filtro_componente)
        if filtro_edad and filtro_edad != 'Todos':
            parametros = parametros.filter(categoriaetaria=filtro_edad)

        tarjetas = []
        for param in parametros:
            # Equivalencia estricta con 'Concentrado de Globulos Rojos'
            stock_actual = EjemplarBolsa.objects.filter(
                idgrupo=param.idgrupo,
                tipocomponente=param.tipocomponente,
                categoriaetaria=param.categoriaetaria,
                estadobolsak='Disponible',
                esexclusivoautologo=False,
                fechacaducidad__gte=hoy
            ).count()

            if stock_actual <= param.stockcriticoalerta:
                nivel = 'Rojo'
            elif stock_actual <= param.stockminimoseguridad:
                nivel = 'Amarillo'
            else:
                nivel = 'Verde'

            simbolo_rh = '+' if param.idgrupo.factorrh == 'Positivo' else '-'
            tarjetas.append({
                'idparametro': param.idparametro,
                'idgrupo': param.idgrupo.idgrupo,
                'grupo_sanguineo': f"{param.idgrupo.grupoabo}{simbolo_rh}",
                'tipocomponente': param.tipocomponente,
                'categoriaetaria': param.categoriaetaria,
                'stock_disponible': stock_actual,
                'stock_minimo_seguridad': param.stockminimoseguridad,
                'stock_critico_alerta': param.stockcriticoalerta,
                'semaforo': nivel
            })

        # Cola prioritaria FEFO (<= 7 días para caducar)
        cola_fefo = EjemplarBolsa.objects.filter(
            estadobolsak='Disponible',
            fechacaducidad__gte=hoy,
            fechacaducidad__lte=ventana_fefo
        ).select_related('idgrupo', 'idubicacion').order_by('fechacaducidad')

        alertas_fefo = [{
            'idejemplarbolsa': b.idejemplarbolsa,
            'codigo': b.codigoejemplark,
            'codigoejemplark': b.codigoejemplark,
            'componente': b.tipocomponente,
            'tipocomponente': b.tipocomponente,
            'categoriaetaria': b.categoriaetaria,
            'grupo': f"{b.idgrupo.grupoabo}{'+' if b.idgrupo.factorrh == 'Positivo' else '-'}",
            'fechacaducidad': b.fechacaducidad,
            'dias_restantes': (b.fechacaducidad - hoy).days,
            'ubicacion': b.idubicacion.identificadorcompartimento if b.idubicacion else 'Sin Asignar'
        } for b in cola_fefo]

        return Response({
            'resumen_stock': tarjetas,
            'tarjetas': tarjetas,
            'cola_fefo': alertas_fefo,
            'cola_proximos_a_vencer': alertas_fefo
        }, status=status.HTTP_200_OK)


# ============================================================================
# Endpoints de Consulta de Parámetros de Stock
# ============================================================================
class ParametroStockMinimoListView(APIView):
    """
    Endpoint: GET /api/stock/parametros/
    Devuelve la lista de umbrales configurados para cada hemocomponente y grupo sanguíneo ABO/Rh.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        queryset = ParametroStockMinimo.objects.select_related('idgrupo').all()

        id_grupo = request.query_params.get('id_grupo')
        if id_grupo:
            queryset = queryset.filter(idgrupo__idgrupo=id_grupo)

        tipo_componente = request.query_params.get('tipo_componente')
        if tipo_componente:
            queryset = queryset.filter(tipocomponente__icontains=tipo_componente)

        serializer = ParametroStockMinimoSerializer(queryset, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


class ParametroStockMinimoUpdateView(APIView):
    """
    Endpoint: PUT /api/stock/parametros/<id>/
    Permite al Administrador actualizar los valores de stock mínimo de seguridad y alerta crítica.
    Audita la modificación en BitacoraAuditoria.
    """
    permission_classes = [IsAdminRole]

    @transaction.atomic
    def put(self, request, pk):
        parametro = get_object_or_404(ParametroStockMinimo.objects.select_related('idgrupo'), idparametro=pk)
        
        serializer = ParametroStockMinimoUpdateSerializer(parametro, data=request.data, partial=True)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        min_anterior = parametro.stockminimoseguridad
        critico_anterior = parametro.stockcriticoalerta

        parametro = serializer.save()

        # Registro en Bitácora de Auditoría
        ip_origen = get_client_ip(request)
        registrar_auditoria(
            usuario=request.user,
            accion=(
                f"Modificación de parámetro de stock para '{parametro.tipocomponente}' ({parametro.idgrupo.tipificacion}): "
                f"Mínimo ({min_anterior} -> {parametro.stockminimoseguridad}), "
                f"Crítico ({critico_anterior} -> {parametro.stockcriticoalerta})"
            ),
            tabla='ParametroStockMinimo',
            idRegistroAfectado=parametro.idparametro,
            ip_origen=ip_origen
        )

        return Response({
            "message": "Parámetro de stock actualizado correctamente.",
            "parametro": ParametroStockMinimoSerializer(parametro).data
        }, status=status.HTTP_200_OK)


class StockAlertasListView(APIView):
    """
    Endpoint: GET /api/stock/alertas/
    Replicación estricta de la Subconsulta B4 / Consulta 20:
    Compara las bolsas en estado 'Disponible' en EjemplarBolsa contra ParametroStockMinimo
    y devuelve los grupos en déficit o alerta crítica.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        mostrar_todos = request.query_params.get('todos', '').lower() in ('true', '1')

        # Recuperar todos los parámetros con sus grupos
        parametros = ParametroStockMinimo.objects.select_related('idgrupo').all()
        
        alertas = []
        for p in parametros:
            # Conteo de bolsas disponibles en inventario físico real
            disponibles = EjemplarBolsa.objects.filter(
                idgrupo=p.idgrupo,
                tipocomponente=p.tipocomponente,
                estadobolsak='Disponible'
            ).count()

            esta_en_deficit = disponibles < p.stockminimoseguridad

            # Si mostrar_todos es False, filtramos únicamente los que están en déficit (Subconsulta B4)
            if not mostrar_todos and not esta_en_deficit:
                continue

            deficit = max(0, p.stockminimoseguridad - disponibles)
            if disponibles <= p.stockcriticoalerta:
                nivel_alerta = 'DEFICIT CRITICO'
                requiere_campana = True
            elif esta_en_deficit:
                nivel_alerta = 'DEFICIT SEGURIDAD'
                requiere_campana = False
            else:
                nivel_alerta = 'STOCK OPTIMO / NORMAL'
                requiere_campana = False

            alertas.append({
                'idParametro': p.idparametro,
                'idGrupo': p.idgrupo.idgrupo,
                'tipificacion': p.idgrupo.tipificacion,
                'tipoComponente': p.tipocomponente,
                'stockMinimoSeguridad': p.stockminimoseguridad,
                'stockCriticoAlerta': p.stockcriticoalerta,
                'stockDisponibleActual': disponibles,
                'deficitUnidades': deficit,
                'nivelAlerta': nivel_alerta,
                'requiereCampanaDonacion': requiere_campana,
            })

        # Ordenar: primero los de déficit crítico, luego déficit seguridad
        prioridad_map = {'DEFICIT CRITICO': 1, 'DEFICIT SEGURIDAD': 2, 'STOCK OPTIMO / NORMAL': 3}
        alertas.sort(key=lambda x: (prioridad_map.get(x['nivelAlerta'], 4), -x['deficitUnidades']))

        serializer = StockAlertaSerializer(alertas, many=True)
        return Response({
            "totalAlertas": len([a for a in alertas if a['nivelAlerta'] != 'STOCK OPTIMO / NORMAL']),
            "alertas": serializer.data
        }, status=status.HTTP_200_OK)


# ============================================================================
# Gestión de Donación Autóloga Programada y Reserva Exclusiva
# ============================================================================
class ProgramarDonacionAutologaView(APIView):
    """
    Registra al paciente como Donante Autólogo y Receptor,
    y agenda su cita de extracción preoperatoria.
    """
    permission_classes = [AllowAny]

    @transaction.atomic
    def post(self, request):
        idpersona = request.data.get('idpersona')
        idgrupo = request.data.get('idgrupo')
        grupo_texto = request.data.get('grupo_texto', 'O Positivo')
        fecha_cirugia = request.data.get('fechacirugia')
        fecha_cita = request.data.get('fechahoracita')
        idusuario = request.data.get('idusuario')

        if not fecha_cirugia or not fecha_cita:
            return Response({'error': 'fechacirugia y fechahoracita son requeridos.'},
                            status=status.HTTP_400_BAD_REQUEST)

        try:
            from datetime import datetime
            if isinstance(fecha_cirugia, str):
                f_cirugia = datetime.fromisoformat(fecha_cirugia.replace('Z', '')).date() if 'T' in fecha_cirugia else datetime.strptime(fecha_cirugia[:10], '%Y-%m-%d').date()
            else:
                f_cirugia = fecha_cirugia

            if isinstance(fecha_cita, str):
                f_cita = datetime.fromisoformat(fecha_cita.replace('Z', '')).date() if 'T' in fecha_cita else datetime.strptime(fecha_cita[:10], '%Y-%m-%d').date()
            else:
                f_cita = fecha_cita

            dias_antelacion = (f_cirugia - f_cita).days
            if dias_antelacion < 3:
                return Response({
                    'error': f'Antelación insuficiente ({dias_antelacion} días). La donación autóloga debe programarse con al menos 72 horas (3 días) de antelación respecto a la cirugía.'
                }, status=status.HTTP_400_BAD_REQUEST)
            if dias_antelacion > 30:
                return Response({
                    'error': f'Antelación excesiva ({dias_antelacion} días). La donación autóloga debe programarse como máximo 30 días antes de la intervención quirúrgica.'
                }, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({'error': f'Error en formato de fechas: {str(e)}'},
                            status=status.HTTP_400_BAD_REQUEST)

        # 1. Asegurar registro en Donante con categoría 'Autologo'
        carnet_auto = f"HEMO-AUTO-{idpersona}"
        donante, created = Donante.objects.get_or_create(
            idpersona_id=idpersona,
            defaults={
                'carnetdigitalcodigo': carnet_auto,
                'tipodonante': 'Autologo',
                'estadohabilitacion': 'Apto'
            }
        )
        if not created and donante.tipodonante != 'Autologo':
            donante.tipodonante = 'Autologo'
            donante.save()

        # 2. Asegurar registro simultáneo en Receptor para vincular ReservaSangre
        Receptor.objects.get_or_create(
            idpersona_id=idpersona,
            defaults={
                'codigohistorialclinico': f"HC-AUTO-{idpersona}",
                'gruposanguineoreceptor': grupo_texto,
                'idgrupo_id': idgrupo
            }
        )

        # 3. Agendar Cita de Extracción Autóloga
        cita = CitaDonacion.objects.create(
            idpersona_id=idpersona,
            fechahoraprogramada=fecha_cita,
            prefiltroaprobado=True,
            estadocita='Programada'
        )

        BitacoraAuditoria.objects.create(
            idusuario_id=idusuario,
            rolactivo=request.headers.get('X-Active-Role', 'Médico Solicitante'),
            accionrealizada=f'Programación de protocolo de Donación Autóloga para cirugía {fecha_cirugia}',
            tablaafectada='Donante',
            idregistroafectado=idpersona,
            iporigen=get_client_ip(request) if hasattr(request, 'META') else '127.0.0.1'
        )

        return Response({
            'mensaje': 'Protocolo de Donación Autóloga programado exitosamente.',
            'carnet_autologo': donante.carnetdigitalcodigo,
            'idcita': cita.idcita
        }, status=status.HTTP_201_CREATED)


class CustodiarFraccionamientoAutologoView(APIView):
    """
    Etiqueta las unidades fraccionadas como exclusivas del paciente
    (esexclusivoautologo = True, estadobolsak = 'Reservada') y crea los registros en ReservaSangre.
    """
    permission_classes = [AllowAny]

    @transaction.atomic
    def post(self, request, idunidadmadre):
        fecha_cirugia = request.data.get('fechacirugia')
        idusuario = request.data.get('idusuario')
        madre = UnidadSangreTotal.objects.select_related('idextraccion').filter(
            idunidadmadre=idunidadmadre
        ).first()
        if not madre:
            return Response({'error': 'Unidad madre no encontrada.'},
                            status=status.HTTP_404_NOT_FOUND)

        id_paciente = madre.idextraccion.idpersonadonante_id
        # Asegurar que el paciente figure en Receptor para la llave foránea de ReservaSangre
        receptor, _ = Receptor.objects.get_or_create(
            idpersona_id=id_paciente,
            defaults={
                'codigohistorialclinico': f"HC-AUTO-{id_paciente}",
                'gruposanguineoreceptor': 'Autólogo Confirmado',
                'idgrupo': madre.idgrupo
            }
        )

        ejemplares = EjemplarBolsa.objects.filter(idunidadmadre=madre)
        bolsas_reservadas = []
        for bolsa in ejemplares:
            bolsa.esexclusivoautologo = True
            bolsa.estadobolsak = 'Reservada'
            bolsa.save()

            ReservaSangre.objects.update_or_create(
                idejemplarbolsa=bolsa,
                defaults={
                    'idreceptor': receptor,
                    'esautologa': True,
                    'motivoreserva': 'Custodia exclusiva por Donación Autóloga Programada',
                    'fechavencimientoreserva': fecha_cirugia or bolsa.fechacaducidad,
                    'estadoreserva': 'Activa'
                }
            )
            bolsas_reservadas.append(bolsa.codigoejemplark)

        BitacoraAuditoria.objects.create(
            idusuario_id=idusuario,
            rolactivo=request.headers.get('X-Active-Role', 'Bioquímico(a) Integral'),
            accionrealizada=f"Reserva exclusiva autóloga de unidades: {', '.join(bolsas_reservadas)}",
            tablaafectada='ReservaSangre',
            idregistroafectado=idunidadmadre,
            iporigen=get_client_ip(request) if hasattr(request, 'META') else '127.0.0.1'
        )

        return Response({
            'mensaje': 'Unidades etiquetadas y bloqueadas exclusivamente para el paciente autólogo.',
            'unidades_reservadas': bolsas_reservadas
        }, status=status.HTTP_200_OK)


class CancelarCirugiaAutologaView(APIView):
    """
    Cancelación quirúrgica definitiva:
    Las bolsas autólogas NO pasan al stock general de terceros; se anula la reserva
    y se derivan a incineración en BajaInventario.
    """
    permission_classes = [AllowAny]

    @transaction.atomic
    def post(self, request, idpersona_paciente):
        idpersonalsalud = request.data.get('idpersonalsalud')
        motivo_cancelacion = request.data.get('motivo', 'Cancelación quirúrgica definitiva notificada por cirugía')

        reservas_activas = ReservaSangre.objects.filter(
            idreceptor_id=idpersona_paciente,
            esautologa=True,
            estadoreserva='Activa'
        ).select_related('idejemplarbolsa')

        if not reservas_activas.exists():
            return Response({'error': 'No existen reservas autólogas activas para este paciente.'},
                            status=status.HTTP_404_NOT_FOUND)

        bolsas_dadas_de_baja = []
        for res in reservas_activas:
            bolsa = res.idejemplarbolsa
            bolsa.estadobolsak = 'Baja'
            bolsa.save()

            res.estadoreserva = 'Cancelada'
            res.save()

            # Registro en BajaInventario respetando chk_baja_origen_xor (idunidadmadre NULL, idejemplarbolsa NOT NULL)
            BajaInventario.objects.create(
                idunidadmadre=None,
                idejemplarbolsa=bolsa,
                idpersonalsalud_id=idpersonalsalud,
                motivobaja='Cancelación Quirúrgica Autóloga',
                observaciones=f"Prohibido traspaso a stock de terceros. Orden de incineración. Detalle: {motivo_cancelacion}"
            )
            bolsas_dadas_de_baja.append(bolsa.codigoejemplark)

        return Response({
            'mensaje': 'Cirugía cancelada. Unidades autólogas enviadas a BajaInventario (incineración) sin pasar a stock de terceros.',
            'unidades_incineradas': bolsas_dadas_de_baja
        }, status=status.HTTP_200_OK)


# ============================================================================
# Generar Tableros de Control, KPIs e Informes de Gestión
# ============================================================================
class TableroControlKPIsView(APIView):
    """
    Generar Tableros de Control, KPIs e Informes de Gestión.
    Calcula:
    1. Tasa de efectividad de citas
    2. Tasa de positividad serológica
    3. Rotación y ocupación de cámaras frías
    4. Índice de reposición biológica cumplida
    5. Ranking de demanda intrahospitalaria y recaudación
    """
    permission_classes = [AllowAny]

    def get(self, request):
        periodo = request.query_params.get('periodo', 'mensual') # 'diario', 'mensual', 'semestral', 'historico', 'personalizado'
        ahora = timezone.now()

        fecha_inicio_param = request.query_params.get('fecha_inicio')
        if fecha_inicio_param:
            try:
                from datetime import datetime
                dt = datetime.strptime(fecha_inicio_param, '%Y-%m-%d')
                fecha_inicio = timezone.make_aware(dt) if timezone.is_naive(dt) else dt
                periodo = 'personalizado'
            except Exception:
                fecha_inicio = ahora - timedelta(days=30)
        elif periodo == 'diario':
            fecha_inicio = ahora - timedelta(days=1)
        elif periodo == 'mensual':
            fecha_inicio = ahora - timedelta(days=30)
        elif periodo == 'semestral':
            fecha_inicio = ahora - timedelta(days=180)
        else:
            fecha_inicio = ahora - timedelta(days=3650)

        # Consultas filtradas por período
        citas_qs = CitaDonacion.objects.filter(fechahoraprogramada__gte=fecha_inicio)
        serologia_qs = AnalisisInmunoSerologico.objects.filter(fechaanalisis__gte=fecha_inicio)
        solicitudes_qs = SolicitudHospitalaria.objects.filter(fechahorarequerimiento__gte=fecha_inicio)
        extracciones_qs = ExtraccionDonacion.objects.filter(fechahora__gte=fecha_inicio)

        total_movimientos = (
            citas_qs.count() + serologia_qs.count() +
            solicitudes_qs.count() + extracciones_qs.count()
        )

        # Excepción E1: Período sin movimientos
        if total_movimientos == 0:
            return Response({
                'periodo_seleccionado': periodo,
                'sin_actividad': True,
                'mensaje': 'No se registraron movimientos operativos en el período seleccionado.',
                'kpis': {
                    'tasa_efectividad_citas': 0.0,
                    'tasa_positividad_serologica': 0.0,
                    'ocupacion_camaras_porcentaje': 0.0,
                    'indice_reposicion_cumplida': 0.0,
                    'total_extracciones': 0,
                    'recaudacion_bs': 0.0
                },
                'camaras_detalle': [],
                'ranking_hospitales': []
            }, status=status.HTTP_200_OK)

        # KPI 1: Tasa de efectividad de citas (%)
        total_citas = citas_qs.count()
        citas_atendidas = citas_qs.filter(asistenciaconfirmada=True).count()
        tasa_efectividad_citas = round((citas_atendidas / total_citas) * 100, 1) if total_citas > 0 else 0.0

        # KPI 2: Tasa de positividad serológica (%)
        total_serologias = serologia_qs.count()
        serologias_reactivas = serologia_qs.filter(dictamenfinal='No Apto').count()
        tasa_positividad = round((serologias_reactivas / total_serologias) * 100, 1) if total_serologias > 0 else 0.0

        # KPI 3: Ocupación y rotación de cámaras frías
        camaras = UbicacionAlmacen.objects.all()
        cap_max_total = sum(c.capacidadmaxima for c in camaras) or 1
        cap_ocup_total = sum(c.capacidadocupada for c in camaras)
        ocupacion_global = round((cap_ocup_total / cap_max_total) * 100, 1)
        camaras_detalle = [{
            'compartimento': c.identificadorcompartimento,
            'equipo': c.tipoequipo,
            'temperatura_c': float(c.temperaturaregistro),
            'ocupadas': c.capacidadocupada,
            'maxima': c.capacidadmaxima,
            'porcentaje_uso': round((c.capacidadocupada / c.capacidadmaxima) * 100, 1) if c.capacidadmaxima > 0 else 0.0
        } for c in camaras]

        # KPI 4: Índice de cumplimiento de reposición biológica
        reposiciones = ReposicionPendiente.objects.all()
        bolsas_a_reponer = sum(r.cantidadbolsasareponer for r in reposiciones)
        bolsas_recuperadas = sum(r.cantidadrecuperada for r in reposiciones)
        indice_reposicion = round((bolsas_recuperadas / bolsas_a_reponer) * 100, 1) if bolsas_a_reponer > 0 else 100.0

        # KPI 5: Ranking de demanda por institución hospitalaria
        ranking_qs = (
            solicitudes_qs
            .values(hospital=F('idinstitucion__nombreinstitucion'))
            .annotate(
                total_solicitudes=Count('idsolicitud'),
                bolsas_requeridas=Sum('cantidadbolsassolicitadas')
            )
            .order_by('-bolsas_requeridas')
        )

        # Balance financiero (ComprobantePago)
        recaudacion = ComprobantePago.objects.filter(
            estadopago='Pagado'
        ).aggregate(total=Sum('montototal'))['total'] or 0.0

        return Response({
            'periodo_seleccionado': periodo,
            'sin_actividad': False,
            'kpis': {
                'tasa_efectividad_citas': tasa_efectividad_citas,
                'citas_atendidas': citas_atendidas,
                'total_citas': total_citas,
                'tasa_positividad_serologica': tasa_positividad,
                'serologias_reactivas': serologias_reactivas,
                'total_serologias': total_serologias,
                'ocupacion_camaras_porcentaje': ocupacion_global,
                'indice_reposicion_cumplida': indice_reposicion,
                'bolsas_recuperadas': bolsas_recuperadas,
                'bolsas_a_reponer': bolsas_a_reponer,
                'total_extracciones': extracciones_qs.count(),
                'recaudacion_bs': float(recaudacion)
            },
            'camaras_detalle': camaras_detalle,
            'ranking_hospitales': list(ranking_qs)
        }, status=status.HTTP_200_OK)

