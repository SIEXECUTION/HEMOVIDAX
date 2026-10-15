"""
Vistas de API REST para la app Donantes
con soporte para Donante Calificado (con QR) y Posible Donador (sin análisis).
"""
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny
from django.db.models import Sum, Count, Q
from django.db import transaction
import random
from datetime import date, timedelta
from django.utils import timezone
from django.shortcuts import get_object_or_404

from .models import (
    Persona, PosibleDonador, Donante, ExtraccionDonacion,
    Diferimiento, CompromisoDonacion, CitaDonacion, DetalleCitaRequisito,
    TriajeClinico, RequisitoDonacion
)
from .serializers import CarnetDigitalResponseSerializer, PosibleDonadorResponseSerializer
from apps.inventario.models import UnidadSangreTotal, EjemplarBolsa, GrupoSanguineo, UbicacionAlmacen
from apps.seguridad.models import PersonalSalud, BitacoraAuditoria

class DonanteCarnetDigitalView(APIView):
    """
    Endpoint: GET /api/donantes/<ci>/carnet/
    Consultar Carnet Digital e Historial Biológico del Donante.
    Permite la búsqueda por C.I. o código de carnet (HEMO-YYYY-XXXX).
    Si el usuario aún es 'Posible Donador', devuelve su estado de aptitud y falta de análisis serológico.
    """
    permission_classes = [AllowAny]

    def get(self, request, ci):
        query = ci.strip()
        query_hyphen = query.replace(' ', '-').replace('_', '-')
        query_spaced = query.replace('-', ' ')
        query_digits = ''.join(c for c in query if c.isdigit())
        
        # 1. Búsqueda en Donante Calificado (superó Inmunoserología)
        donante_filter = (
            Q(persona__ci__iexact=query) |
            Q(persona__ci__iexact=query_hyphen) |
            Q(carnetDigitalCodigo__iexact=query) |
            Q(carnetDigitalCodigo__iexact=query_hyphen) |
            Q(carnetDigitalCodigo__iexact=query_spaced)
        )
        if len(query_digits) >= 4:
            donante_filter |= Q(persona__ci__icontains=query_digits) | Q(carnetDigitalCodigo__icontains=query_digits)

        donante = Donante.objects.select_related('persona').filter(donante_filter).first()

        if donante:
            persona = donante.persona
            sexo = (persona.sexo or 'M').upper()
            fecha_ultima = donante.fechaUltimaDonacion
            hoy = timezone.now().date()

            # REGLA BIOLÓGICA (CONSULTA C1):
            # Varones (M): 90 días de intervalo biológico entre donaciones.
            # Mujeres (F) y otros: 120 días de intervalo biológico de recuperación.
            periodo_espera_dias = 90 if sexo == 'M' else 120

            if fecha_ultima:
                fecha_habilitacion = fecha_ultima + timedelta(days=periodo_espera_dias)
                delta_dias = (fecha_habilitacion - hoy).days
                dias_restantes_espera = max(0, delta_dias)
            else:
                fecha_habilitacion = None
                dias_restantes_espera = 0

            # Regla de aptitud: Requiere estado 'Apto' y haber cumplido los días biológicos de reposo
            esta_habilitado = (donante.estadoHabilitacion == 'Apto') and (dias_restantes_espera == 0)

            # HISTORIAL ACUMULADO (CONSULTA C3):
            extracciones_qs = ExtraccionDonacion.objects.filter(
                personaDonante=persona
            ).select_related('personalSalud__persona').order_by('-fechaHora')

            agregados = extracciones_qs.aggregate(
                total_donaciones=Count('idextraccion'),
                volumen_total=Sum('volumenextraidoml')
            )
            total_donaciones = agregados['total_donaciones'] or 0
            volumen_total = agregados['volumen_total'] or 0

            payload = {
                'esPosibleDonador': False,
                'carnetDigitalCodigo': donante.carnetDigitalCodigo,
                'ci': persona.ci,
                'nombres': persona.nombres,
                'apellidos': persona.apellidos,
                'donante': persona.nombreCompleto,
                'sexo': persona.sexo,
                'celular': persona.celular,
                'direccion': persona.direccion,
                'ocupacion': persona.ocupacion,
                'tipoDonante': donante.tipoDonante,
                'estadoHabilitacion': donante.estadoHabilitacion,
                'fechaUltimaDonacion': fecha_ultima,
                'periodoEsperaDias': periodo_espera_dias,
                'fechaHabilitacionProxima': fecha_habilitacion,
                'diasRestantesEspera': dias_restantes_espera,
                'estaHabilitadoParaDonar': esta_habilitado,
                'totalDonacionesHistoricas': total_donaciones,
                'volumenHistoricoAportadoMl': volumen_total,
                'nacionalidad': getattr(persona, 'nacionalidad', 'Boliviana') or 'Boliviana',
                'grupoSanguineo': 'O',
                'factorRh': 'Positivo',
                'extraccionesRecientes': extracciones_qs[:10],
            }

            serializer = CarnetDigitalResponseSerializer(payload)
            return Response(serializer.data, status=status.HTTP_200_OK)

        # 2. Búsqueda en PosibleDonador (Postulante en fase inicial con código provisional o CI)
        posible_filter = (
            Q(persona__ci__iexact=query) |
            Q(persona__ci__iexact=query_hyphen) |
            Q(carnetProvisionalCodigo__iexact=query) |
            Q(carnetProvisionalCodigo__iexact=query_hyphen) |
            Q(persona__usuario__username__iexact=query) |
            Q(persona__usuario__username__iexact=query_hyphen)
        )
        if len(query_digits) >= 4:
            posible_filter |= (
                Q(persona__ci__icontains=query_digits) |
                Q(carnetProvisionalCodigo__icontains=query_digits) |
                Q(persona__usuario__username__icontains=query_digits)
            )

        posible = PosibleDonador.objects.select_related('persona').filter(posible_filter).first()

        if posible:
            persona = posible.persona
            codigo_provisional = posible.carnetProvisionalCodigo or f"HV-POST-{date.today().year}-{persona.idPersona}"
            payload_posible = {
                'esPosibleDonador': True,
                'carnetDigitalCodigo': codigo_provisional,
                'carnetProvisionalCodigo': codigo_provisional,
                'ci': persona.ci,
                'nombres': persona.nombres,
                'apellidos': persona.apellidos,
                'donante': persona.nombreCompleto,
                'sexo': persona.sexo,
                'celular': persona.celular,
                'direccion': persona.direccion,
                'ocupacion': persona.ocupacion,
                'nacionalidad': getattr(persona, 'nacionalidad', 'Boliviana') or 'Boliviana',
                'estadoAptitud': posible.estadoAptitud,
                'tieneAnalisis': posible.tieneAnalisis,
                'fechaRegistroPostulante': posible.fechaRegistroPostulante,
                'estaHabilitadoParaDonar': False,
                'mensaje': 'Postulante registrado en HemoVida. Habilitado para evaluación inicial y cuestionario de prefiltro.'
            }
            serializer = PosibleDonadorResponseSerializer(payload_posible)
            return Response(serializer.data, status=status.HTTP_200_OK)

        return Response({
            "detail": f"No se encontró ningún donante ni postulante registrado con C.I. o código '{ci}'."
        }, status=status.HTTP_404_NOT_FOUND)


class CarnetDigitalQRView(APIView):
    """
    Consultar Carnet Digital con QR e Historial Transaccional.
    Calcula descanso biológico (90d M / 120d F), verifica diferimientos vigentes
    y retorna el historial de donaciones y reposiciones.
    """
    permission_classes = [AllowAny]

    def get(self, request, idpersona):
        hoy = timezone.now().date()
        persona = Persona.objects.filter(idpersona=idpersona).first()
        donante = Donante.objects.filter(idpersona=idpersona).first()
        if not persona or not donante:
            return Response(
                {'error': 'La persona aún no cuenta con un Carnet Digital de Donante Calificado.'},
                status=status.HTTP_404_NOT_FOUND
            )

        # 1. Obtener grupo sanguíneo verificado desde su última bolsa madre o registro
        ultima_bolsa = UnidadSangreTotal.objects.filter(
            idextraccion__idpersonadonante=idpersona
        ).select_related('idgrupo').order_by('-idunidadmadre').first()
        if ultima_bolsa and ultima_bolsa.idgrupo:
            simbolo_rh = '+' if ultima_bolsa.idgrupo.factorrh == 'Positivo' else '-'
            grupo_sanguineo = f"{ultima_bolsa.idgrupo.grupoabo} Rh{simbolo_rh}"
        else:
            grupo_sanguineo = "Pendiente de Tipificación"

        # 2. Verificar Excepción E1: Diferimiento vigente
        diferimiento_activo = Diferimiento.objects.filter(
            idposibledonador=idpersona,
            fechafindiferimiento__gte=hoy
        ).order_by('-fechafindiferimiento').first()

        # 3. Calcular ventana de descanso celular (90 días varón / 120 días mujer)
        intervalo_dias = 90 if persona.sexo == 'M' else 120
        dias_restantes = 0
        proxima_fecha_habilitada = hoy
        porcentaje_recuperacion = 100

        if donante.fechaultimadonacion:
            proxima_fecha_habilitada = donante.fechaultimadonacion + timedelta(days=intervalo_dias)
            if proxima_fecha_habilitada > hoy:
                dias_restantes = (proxima_fecha_habilitada - hoy).days
                dias_transcurridos = (hoy - donante.fechaultimadonacion).days
                porcentaje_recuperacion = min(100, max(0, int((dias_transcurridos / intervalo_dias) * 100)))

        # Determinar semáforo del carnet
        if donante.estadohabilitacion == 'Diferido Definitivo':
            semaforo_carnet = 'Rojo'
            mensaje_estado = 'Suspensión Definitiva por Seguridad Transfusional'
            apto_para_donar_hoy = False
        elif diferimiento_activo:
            semaforo_carnet = 'Rojo'
            mensaje_estado = f"Diferido temporalmente hasta {diferimiento_activo.fechafindiferimiento} ({diferimiento_activo.motivodetallado})"
            proxima_fecha_habilitada = max(proxima_fecha_habilitada, diferimiento_activo.fechafindiferimiento)
            dias_restantes = (proxima_fecha_habilitada - hoy).days
            apto_para_donar_hoy = False
        elif dias_restantes > 0:
            semaforo_carnet = 'Amarillo'
            mensaje_estado = f'En recuperación celular ({dias_restantes} días restantes)'
            apto_para_donar_hoy = False
        else:
            semaforo_carnet = 'Verde'
            mensaje_estado = '¡Tu cuerpo está 100% listo para donar!'
            apto_para_donar_hoy = True

        # 4. Historial de extracciones y reposiciones
        extracciones = ExtraccionDonacion.objects.filter(
            idpersonadonante=idpersona
        ).order_by('-fechahora')
        historial_donaciones = [{
            'idextraccion': e.idextraccion,
            'codigo': e.codigoextraccion,
            'fecha': e.fechahora.strftime('%Y-%m-%d %H:%M') if e.fechahora else '',
            'volumen_ml': e.volumenextraidoml,
            'brazo': e.brazoextraccion
        } for e in extracciones]

        reposiciones = CompromisoDonacion.objects.filter(
            iddonante=idpersona,
            donacionconcretada=True
        ).select_related('idreposicion__idsolicitud').order_by('-fechacompromiso')
        historial_reposiciones = [{
            'idcompromiso': r.idcompromiso,
            'fecha': r.fechacompromiso,
            'solicitud_asociada': r.idreposicion.idsolicitud.numerosolicitud if r.idreposicion and r.idreposicion.idsolicitud else 'N/A',
            'volumen_donado_ml': r.volumendonadoefectivoml,
            'estado': r.estadocompromiso
        } for r in reposiciones]

        # Payload dinámico para el código QR de validación rápida
        qr_payload = (
            f"HEMOVIDA|CARNET:{donante.carnetdigitalcodigo}|CI:{persona.ci}|"
            f"GRUPO:{grupo_sanguineo}|ESTADO:{donante.estadohabilitacion}|"
            f"PROX_HAB:{proxima_fecha_habilitada}"
        )

        return Response({
            'carnet_codigo': donante.carnetdigitalcodigo,
            'nombre_completo': f"{persona.nombres} {persona.apellidos}",
            'ci': persona.ci,
            'sexo': persona.sexo,
            'intervalo_biologico_dias': intervalo_dias,
            'tipo_donante': donante.tipodonante,
            'grupo_sanguineo': grupo_sanguineo,
            'estado_habilitacion': donante.estadohabilitacion,
            'semaforo_carnet': semaforo_carnet,
            'mensaje_estado': mensaje_estado,
            'apto_para_donar_hoy': apto_para_donar_hoy,
            'fecha_ultima_donacion': donante.fechaultimadonacion,
            'proxima_fecha_habilitada': proxima_fecha_habilitada,
            'dias_restantes_espera': dias_restantes,
            'porcentaje_recuperacion': porcentaje_recuperacion,
            'total_donaciones': len(historial_donaciones),
            'volumen_total_aportado_ml': sum(e['volumen_ml'] for e in historial_donaciones),
            'vidas_impactadas': len(historial_donaciones) * 3,
            'qr_validation_string': qr_payload,
            'historial_donaciones': historial_donaciones,
            'historial_reposiciones': historial_reposiciones
        }, status=status.HTTP_200_OK)


# ============================================================================
# Orquestación Atómica de Citas de Donación (DRF @transaction.atomic)
# ============================================================================
class AgendarCitaDonacionView(APIView):
    """
    Orquestación atómica para agendar citas de donación.
    POST /api/donantes/citas/
    """
    permission_classes = [AllowAny]

    @transaction.atomic
    def post(self, request):
        id_postulante = request.data.get('idposibledonador') or request.data.get('idpersona')
        fecha_hora = request.data.get('fechahoraprogramada')
        tipo_cita = request.data.get('tipocita', 'Voluntario Altruista')
        requisitos = request.data.get('requisitos', [])

        if not id_postulante or not fecha_hora:
            return Response(
                {"detail": "Campos 'idposibledonador' (o 'idpersona') y 'fechahoraprogramada' son obligatorios."},
                status=status.HTTP_400_BAD_REQUEST
            )

        posible = PosibleDonador.objects.filter(idpersona=id_postulante).first()
        if not posible:
            persona = get_object_or_404(Persona, idpersona=id_postulante)
            posible = PosibleDonador.objects.create(
                persona=persona,
                estadoaptitud='No Apto',
                tieneanalisis=False
            )

        # Verificar si tiene diferimiento médico activo
        hoy = timezone.now().date()
        diferimiento = Diferimiento.objects.filter(
            idposibledonador=posible,
            fechafindiferimiento__gte=hoy
        ).first()
        if diferimiento:
            return Response(
                {
                    "detail": f"El postulante tiene un diferimiento activo hasta {diferimiento.fechafindiferimiento} por: {diferimiento.motivodetallado}."
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        prefiltro = bool(request.data.get('prefiltroaprobado', True))
        persona = posible.persona if hasattr(posible, 'persona') else posible
        cita = CitaDonacion.objects.create(
            idpersona=persona,
            fechahoraprogramada=fecha_hora,
            prefiltroaprobado=prefiltro,
            asistenciaconfirmada=False,
            estadocita='Programada'
        )

        detalles_creados = []
        for req in requisitos:
            id_req = req.get('idrequisito')
            cumple = req.get('cumplerequisito', True)
            obs = req.get('observacion', '')
            req_obj = RequisitoDonacion.objects.filter(idrequisito=id_req).first()
            if req_obj:
                det = DetalleCitaRequisito.objects.create(
                    idcita=cita,
                    idrequisito=req_obj,
                    cumplerequisito=cumple,
                    observacionrespuesta=obs
                )
                detalles_creados.append(det.iddetallecita)

        rol_activo = request.headers.get('X-Active-Role') or 'PERS_COLECTA'
        ip_origen = request.META.get('REMOTE_ADDR', '127.0.0.1')
        BitacoraAuditoria.objects.create(
            idusuario=getattr(request.user, 'idusuario', None) if request.user.is_authenticated else None,
            rolactivo=rol_activo,
            accionrealizada=f"Agendamiento de cita de donación #{cita.idcita}",
            tablaafectada='CitaDonacion',
            idregistroafectado=cita.idcita,
            iporigen=ip_origen
        )

        return Response({
            "mensaje": "Cita de donación agendada exitosamente.",
            "idcita": cita.idcita,
            "fechahoraprogramada": cita.fechahoraprogramada,
            "estadocita": cita.estadocita,
            "prefiltroaprobado": cita.prefiltroaprobado,
            "requisitos_evaluados": len(detalles_creados)
        }, status=status.HTTP_201_CREATED)


# ============================================================================
# Orquestación Atómica de Triaje Clínico (DRF @transaction.atomic)
# ============================================================================
class ProcesarTriajeClinicoView(APIView):
    """
    Orquestación atómica para procesamiento de triaje clínico (reemplazo SP sp_procesar_triaje_clinico).
    POST /api/donantes/triaje/
    """
    permission_classes = [AllowAny]

    @transaction.atomic
    def post(self, request):
        data = request.data
        id_postulante = data.get('idposibledonador') or data.get('idpersona')
        id_personal = data.get('idpersonalsalud')

        if not id_postulante or not id_personal:
            return Response(
                {"detail": "Campos 'idposibledonador' e 'idpersonalsalud' son obligatorios."},
                status=status.HTTP_400_BAD_REQUEST
            )

        posible = get_object_or_404(PosibleDonador, idpersona=id_postulante)
        personal = get_object_or_404(PersonalSalud, pk=id_personal)

        peso = float(data.get('pesokg', 0))
        temp = float(data.get('temperatura', 0))
        hb = float(data.get('hemoglobina', 0))
        p_sis = int(data.get('presionsistolica', 0))
        p_dia = int(data.get('presiondiastolica', 0))
        motivo_diferimiento = data.get('motivodiferimiento')
        dias_inhabilitacion = int(data.get('diasinhabilitacion', 0))

        # Regla clínica de biometría básica
        es_apto = (
            peso >= 50.0 and
            temp <= 37.5 and
            hb >= 12.5 and
            not motivo_diferimiento
        )
        resultado_aptitud = 'Apto' if es_apto else 'Rechazado'

        triaje = TriajeClinico.objects.create(
            idposibledonador=posible,
            idpersonalsalud=personal,
            fechahora=timezone.now(),
            pesokg=peso,
            presionsistolicammhg=p_sis,
            presiondiastolicammhg=p_dia,
            nivelhemoglobina=hb,
            temperatura=temp,
            resultadoaptitud=resultado_aptitud
        )

        diferimiento_obj = None
        hoy = timezone.now().date()
        if resultado_aptitud == 'Rechazado':
            motivo_final = motivo_diferimiento or 'No cumple parámetros de biometría en triaje (peso/hemoglobina/temperatura)'
            fin_dif = hoy + timedelta(days=dias_inhabilitacion) if dias_inhabilitacion > 0 else hoy + timedelta(days=30)
            diferimiento_obj = Diferimiento.objects.create(
                idtriaje=triaje,
                idposibledonador=posible,
                motivodetallado=motivo_final,
                diasinhabilitacion=dias_inhabilitacion or 30,
                fechainiciodiferimiento=hoy,
                fechafindiferimiento=fin_dif
            )
            Donante.objects.filter(idpersona=id_postulante).update(
                estadohabilitacion='Diferido Definitivo' if dias_inhabilitacion > 365 else 'Diferido Temporal'
            )
            PosibleDonador.objects.filter(idpersona=id_postulante).update(
                estadoaptitud='No Apto'
            )
        else:
            Donante.objects.filter(idpersona=id_postulante).update(
                estadohabilitacion='Apto'
            )
            PosibleDonador.objects.filter(idpersona=id_postulante).update(
                estadoaptitud='Apto'
            )

        rol_activo = request.headers.get('X-Active-Role') or 'DOC_TRIAJE'
        ip_origen = request.META.get('REMOTE_ADDR', '127.0.0.1')
        BitacoraAuditoria.objects.create(
            idusuario=getattr(request.user, 'idusuario', None) if request.user.is_authenticated else None,
            rolactivo=rol_activo,
            accionrealizada=f"Triaje clínico #{triaje.idtriaje}: Dictamen {resultado_aptitud}",
            tablaafectada='TriajeClinico',
            idregistroafectado=triaje.idtriaje,
            iporigen=ip_origen
        )

        return Response({
            "mensaje": f"Triaje clínico registrado con resultado '{resultado_aptitud}'.",
            "idtriaje": triaje.idtriaje,
            "resultadoaptitud": triaje.resultadoaptitud,
            "fechahora": triaje.fechahora,
            "diferimiento": {
                "iddiferimiento": diferimiento_obj.iddiferimiento,
                "motivo": diferimiento_obj.motivodetallado,
                "fechafindiferimiento": diferimiento_obj.fechafindiferimiento
            } if diferimiento_obj else None
        }, status=status.HTTP_201_CREATED)


# ============================================================================
# Orquestación Atómica de Flebotomía y Fraccionamiento (DRF @transaction.atomic)
# ============================================================================
class RegistrarFlebotomiaFraccionamientoView(APIView):
    """
    Orquestación atómica para registrar flebotomía y fraccionamiento mecánico inmediato
    (reemplazo del SP sp_registrar_flebotomia_y_fraccionar).
    POST /api/donantes/flebotomia/
    """
    permission_classes = [AllowAny]

    @transaction.atomic
    def post(self, request):
        data = request.data
        id_donante = data.get('idpersonadonante') or data.get('iddonante')
        id_personal = data.get('idpersonalsalud')
        id_triaje = data.get('idtriaje')
        id_grupo = data.get('idgrupo')
        id_camara = data.get('idubicacioncamara')
        brazo = data.get('brazo', 'Derecho')
        volumen_ml = int(data.get('volumenml', 450))
        categoria_etaria = data.get('categoriaetaria', 'Adulto')

        if not id_donante or not id_personal or not id_triaje or not id_grupo:
            return Response(
                {"detail": "Campos 'idpersonadonante', 'idpersonalsalud', 'idtriaje' e 'idgrupo' son obligatorios."},
                status=status.HTTP_400_BAD_REQUEST
            )

        persona = get_object_or_404(Persona, idpersona=id_donante)
        personal = get_object_or_404(PersonalSalud, pk=id_personal)
        triaje = get_object_or_404(TriajeClinico, idtriaje=id_triaje)
        grupo = get_object_or_404(GrupoSanguineo, idgrupo=id_grupo)
        camara = UbicacionAlmacen.objects.filter(idubicacion=id_camara).first() if id_camara else None

        if triaje.resultadoaptitud != 'Apto':
            return Response(
                {"detail": "No se puede realizar flebotomía: el triaje clínico asociado no resultó Apto."},
                status=status.HTTP_400_BAD_REQUEST
            )

        hoy = timezone.now().date()
        date_str = hoy.strftime('%Y%m%d')
        rnd_ext = random.randint(1000, 9999)
        rnd_mad = random.randint(1000, 9999)
        codigo_ext = f"EXT-{date_str}-{rnd_ext}"
        codigo_madre = f"MAD-{date_str}-{rnd_mad}"

        # 1. Registro de punción física (ExtraccionDonacion) con idpersonadonante e idtriaje vinculados obligatoriamente
        extraccion = ExtraccionDonacion.objects.create(
            idpersonadonante=persona,
            idpersonalsalud=personal,
            idtriaje=triaje,
            codigoextraccion=codigo_ext,
            volumenextraidoml=volumen_ml,
            brazoextraccion=brazo,
            fechahora=timezone.now()
        )

        # 2. Alta de bolsa madre en cuarentena (UnidadSangreTotal)
        madre = UnidadSangreTotal.objects.create(
            idextraccion=extraccion,
            idgrupo=grupo,
            codigobolsamadre=codigo_madre,
            tipobolsa='Bolsa Cuadruple CPD-SAGM',
            estadoliberacion='En Cuarentena'
        )

        # 3. Fraccionamiento mecánico inmediato (<6-8 horas)
        # Nombre oficial: 'Concentrado de Globulos Rojos' (estricto)
        bolsa_gr = EjemplarBolsa.objects.create(
            idunidadmadre=madre,
            idgrupo=grupo,
            idubicacion=camara,
            codigoejemplark=f"{codigo_madre}-K1-GR",
            tipocomponente='Concentrado de Globulos Rojos',
            volumenml=250,
            fechaextraccion=hoy,
            fechacaducidad=hoy + timedelta(days=35),
            estadobolsak='En Cuarentena',
            categoriaetaria=categoria_etaria
        )

        bolsa_pl = EjemplarBolsa.objects.create(
            idunidadmadre=madre,
            idgrupo=grupo,
            idubicacion=camara,
            codigoejemplark=f"{codigo_madre}-K2-PL",
            tipocomponente='Plasma Fresco Congelado',
            volumenml=150,
            fechaextraccion=hoy,
            fechacaducidad=hoy + timedelta(days=365),
            estadobolsak='En Cuarentena',
            categoriaetaria=categoria_etaria
        )

        # Actualizar fecha última donación en Donante (si existe)
        Donante.objects.filter(idpersona=id_donante).update(fechaultimadonacion=hoy)

        rol_activo = request.headers.get('X-Active-Role') or 'PERS_COLECTA'
        ip_origen = request.META.get('REMOTE_ADDR', '127.0.0.1')
        BitacoraAuditoria.objects.create(
            idusuario=getattr(request.user, 'idusuario', None) if request.user.is_authenticated else None,
            rolactivo=rol_activo,
            accionrealizada=f"Flebotomía #{extraccion.idextraccion} y fraccionamiento inmediato (CGR, PFC)",
            tablaafectada='ExtraccionDonacion',
            idregistroafectado=extraccion.idextraccion,
            iporigen=ip_origen
        )

        return Response({
            "mensaje": "Flebotomía y fraccionamiento procesados exitosamente en DRF con @transaction.atomic.",
            "extraccion": {
                "idextraccion": extraccion.idextraccion,
                "codigoextraccion": extraccion.codigoextraccion,
                "volumenextraidoml": extraccion.volumenextraidoml,
                "brazoextraccion": extraccion.brazoextraccion,
                "idtriaje": triaje.idtriaje
            },
            "unidadmadre": {
                "idunidadmadre": madre.idunidadmadre,
                "codigobolsamadre": madre.codigobolsamadre,
                "estadoliberacion": madre.estadoliberacion
            },
            "bolsas": [
                {
                    "idejemplarbolsa": bolsa_gr.idejemplarbolsa,
                    "codigoejemplark": bolsa_gr.codigoejemplark,
                    "tipocomponente": bolsa_gr.tipocomponente,
                    "volumenml": bolsa_gr.volumenml,
                    "fechacaducidad": bolsa_gr.fechacaducidad,
                    "categoriaetaria": bolsa_gr.categoriaetaria
                },
                {
                    "idejemplarbolsa": bolsa_pl.idejemplarbolsa,
                    "codigoejemplark": bolsa_pl.codigoejemplark,
                    "tipocomponente": bolsa_pl.tipocomponente,
                    "volumenml": bolsa_pl.volumenml,
                    "fechacaducidad": bolsa_pl.fechacaducidad,
                    "categoriaetaria": bolsa_pl.categoriaetaria
                }
            ]
        }, status=status.HTTP_201_CREATED)


