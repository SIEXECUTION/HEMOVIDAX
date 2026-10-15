"""
Pruebas unitarias para la app Inventario, Stock y Trazabilidad.
"""
from django.test import TestCase
from rest_framework.test import APIClient
from rest_framework import status
from datetime import date, timedelta
from django.utils import timezone

from apps.seguridad.models import Rol, Usuario, UsuarioRol, PersonalSalud
from apps.donantes.models import (
    Persona, Receptor, CitaDonacion, ExtraccionDonacion,
    AnalisisInmunoSerologico, CompromisoDonacion
)
from .models import (
    GrupoSanguineo, ParametroStockMinimo, EjemplarBolsa, UnidadSangreTotal, UbicacionAlmacen,
    InstitucionSalud, ReservaSangre, BajaInventario, ReposicionPendiente, ComprobantePago, SolicitudHospitalaria
)

class StockAlertasTestCase(TestCase):
    def setUp(self):
        self.client = APIClient()

        # Usuario Administrador autenticado con rol ADMIN
        self.rol_admin = Rol.objects.create(nombreRol='Administrador', codigoRol='ADMIN')
        self.user_admin = Usuario.objects.create(
            username='admin.stock',
            email='admin.stock@hemovida.org',
            passwordHash='HemoVida#2026!',
            estado='Activo'
        )
        UsuarioRol.objects.create(usuario=self.user_admin, rol=self.rol_admin)
        self.client.force_authenticate(user=self.user_admin)

        # Grupos Sanguíneos
        self.grupo_o_neg = GrupoSanguineo.objects.create(idGrupo=2, grupoABO='O', factorRh='Negativo')
        self.grupo_o_pos = GrupoSanguineo.objects.create(idGrupo=1, grupoABO='O', factorRh='Positivo')

        # Parámetro 1: O- Glóbulos Rojos (Mínimo: 10, Crítico: 3)
        self.param_o_neg = ParametroStockMinimo.objects.create(
            grupo=self.grupo_o_neg,
            tipoComponente='Concentrado de Globulos Rojos',
            stockMinimoSeguridad=10,
            stockCriticoAlerta=3
        )

        # Parámetro 2: O+ Glóbulos Rojos (Mínimo: 15, Crítico: 5)
        self.param_o_pos = ParametroStockMinimo.objects.create(
            grupo=self.grupo_o_pos,
            tipoComponente='Concentrado de Globulos Rojos',
            stockMinimoSeguridad=15,
            stockCriticoAlerta=5
        )

        # Crear 1 bolsa disponible para O- (1 <= 3 -> DEFICIT CRITICO)
        EjemplarBolsa.objects.create(
            idUnidadMadre=None,
            grupo=self.grupo_o_neg,
            codigoEjemplarK='BOLSA-O-NEG-01',
            tipoComponente='Concentrado de Globulos Rojos',
            volumenMl=250,
            fechaExtraccion=date.today(),
            fechaCaducidad=date.today() + timedelta(days=30),
            estadoBolsaK='Disponible'
        )

        # Crear 8 bolsas disponibles para O+ (8 < 15 pero 8 > 5 -> DEFICIT SEGURIDAD)
        for i in range(8):
            EjemplarBolsa.objects.create(
                idUnidadMadre=None,
                grupo=self.grupo_o_pos,
                codigoEjemplarK=f'BOLSA-O-POS-{i}',
                tipoComponente='Concentrado de Globulos Rojos',
                volumenMl=250,
                fechaExtraccion=date.today(),
                fechaCaducidad=date.today() + timedelta(days=30),
                estadoBolsaK='Disponible'
            )

    def test_listar_parametros_stock(self):
        response = self.client.get('/api/stock/parametros/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 2)

    def test_actualizar_parametro_stock_valido(self):
        response = self.client.put(f'/api/stock/parametros/{self.param_o_neg.idParametro}/', {
            'stockMinimoSeguridad': 12,
            'stockCriticoAlerta': 4
        })
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.param_o_neg.refresh_from_db()
        self.assertEqual(self.param_o_neg.stockMinimoSeguridad, 12)
        self.assertEqual(self.param_o_neg.stockCriticoAlerta, 4)

    def test_actualizar_parametro_invalido_critico_mayor_a_minimo(self):
        response = self.client.put(f'/api/stock/parametros/{self.param_o_neg.idParametro}/', {
            'stockMinimoSeguridad': 5,
            'stockCriticoAlerta': 10  # Inválido: Crítico mayor a Mínimo
        })
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('stockCriticoAlerta', response.data)

    def test_reporte_alertas_subconsulta_b4(self):
        response = self.client.get('/api/stock/alertas/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('alertas', response.data)
        self.assertGreaterEqual(len(response.data['alertas']), 1)

    # -------------------------------------------------------------------------
    # Fraccionamiento de Bolsa Madre
    # -------------------------------------------------------------------------
    def test_fraccionamiento_adulto(self):
        madre = UnidadSangreTotal.objects.create(
            idgrupo=self.grupo_o_pos,
            codigobolsamadre='MADRE-ADULTO-001',
            tipobolsa='Triple',
            estadoliberacion='Liberada Apta'
        )

        res = self.client.post(f'/api/fraccionar/{madre.idunidadmadre}/', {
            'categoriaetaria': 'Adulto'
        })
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertIn('ejemplares_generados', res.data)
        self.assertEqual(len(res.data['ejemplares_generados']), 3)

        # Verificar ejemplares creados
        bolsas = EjemplarBolsa.objects.filter(idunidadmadre=madre)
        self.assertEqual(bolsas.count(), 3)
        gr = bolsas.get(tipocomponente='Concentrado de Globulos Rojos')
        pl = bolsas.get(tipocomponente='Plasma Fresco Congelado')
        pq = bolsas.get(tipocomponente='Concentrado Plaquetario')

        self.assertEqual(gr.volumenml, 280)
        self.assertEqual(gr.categoriaetaria, 'Adulto')
        self.assertEqual(gr.estadobolsak, 'Disponible')
        self.assertEqual(pl.volumenml, 220)
        self.assertEqual(pq.volumenml, 60)

        # Intento de re-fraccionar debe ser rechazado
        res_dup = self.client.post(f'/api/fraccionar/{madre.idunidadmadre}/', {
            'categoriaetaria': 'Adulto'
        })
        self.assertEqual(res_dup.status_code, status.HTTP_400_BAD_REQUEST)

    def test_fraccionamiento_pediatrico_alicuotas(self):
        madre_ped = UnidadSangreTotal.objects.create(
            idgrupo=self.grupo_o_neg,
            codigobolsamadre='MADRE-PED-001',
            tipobolsa='Cuádruple',
            estadoliberacion='En Cuarentena'
        )

        res = self.client.post(f'/api/fraccionar/{madre_ped.idunidadmadre}/', {
            'categoriaetaria': 'Pediátrico'
        })
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertEqual(len(res.data['ejemplares_generados']), 5)

        bolsas = EjemplarBolsa.objects.filter(idunidadmadre=madre_ped)
        self.assertEqual(bolsas.count(), 5)

        # 3 alícuotas de GR
        alicuotas = bolsas.filter(tipocomponente='Concentrado de Globulos Rojos')
        self.assertEqual(alicuotas.count(), 3)
        for b in alicuotas:
            self.assertEqual(b.volumenml, 75)
            self.assertEqual(b.categoriaetaria, 'Pediátrico')
            self.assertEqual(b.estadobolsak, 'En Cuarentena')
            self.assertIn('-K1P', b.codigoejemplark)

        pl = bolsas.get(tipocomponente='Plasma Fresco Congelado')
        pq = bolsas.get(tipocomponente='Concentrado Plaquetario')
        self.assertEqual(pl.volumenml, 100)
        self.assertEqual(pq.volumenml, 50)

    # -------------------------------------------------------------------------
    # Monitor de Semáforo de Stock y FEFO
    # -------------------------------------------------------------------------
    def test_monitor_stock_semaforo_y_fefo(self):
        # Crear una bolsa próxima a vencer (a 3 días, dentro de FEFO <= 7 días)
        bolsa_fefo = EjemplarBolsa.objects.create(
            idgrupo=self.grupo_o_neg,
            codigoejemplark='BOLSA-FEFO-01',
            tipocomponente='Concentrado de Globulos Rojos',
            volumenml=250,
            fechaextraccion=date.today() - timedelta(days=32),
            fechacaducidad=date.today() + timedelta(days=3),
            estadobolsak='Disponible'
        )

        res = self.client.get('/api/monitor-semaforo/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertIn('tarjetas', res.data)
        self.assertIn('cola_proximos_a_vencer', res.data)

        # Verificar que la bolsa próxima a vencer aparece en la cola FEFO
        codigos_fefo = [b['codigoejemplark'] for b in res.data['cola_proximos_a_vencer']]
        self.assertIn('BOLSA-FEFO-01', codigos_fefo)


# =============================================================================
# Pruebas del Protocolo de Donación Autóloga
# =============================================================================
class ProtocoloAutologoTestCase(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.rol_med = Rol.objects.create(nombreRol='Médico Transfusional', codigoRol='MED_TRANS')
        self.user_med = Usuario.objects.create(
            username='dr.transfusion',
            email='dr.transfusion@hemovida.org',
            passwordHash='HemoVida#2026!',
            estado='Activo'
        )
        UsuarioRol.objects.create(usuario=self.user_med, rol=self.rol_med)
        self.client.force_authenticate(user=self.user_med)

        self.grupo_o_pos = GrupoSanguineo.objects.create(idGrupo=1, grupoABO='O', factorRh='Positivo')

        self.paciente = Persona.objects.create(
            ci='4455667',
            nombres='Roberto',
            apellidos='Gómez',
            fechanacimiento=date(1980, 5, 20),
            sexo='M',
            celular='77123456'
        )
        self.medico_persona = Persona.objects.create(
            ci='9988771',
            nombres='Doctora Elena',
            apellidos='Vásquez',
            fechanacimiento=date(1975, 3, 15),
            sexo='F'
        )
        self.personal_medico = PersonalSalud.objects.create(
            persona=self.medico_persona,
            cargo='Médico Hemoterapeuta',
            registroprofesional='MED-7788'
        )
        self.receptor = Receptor.objects.create(
            idpersona=self.paciente,
            idgrupo=self.grupo_o_pos,
            codigohistorialclinico='HC-1234',
            gruposanguineoreceptor='O+'
        )

    def test_programar_donacion_autologa_exito(self):
        fecha_cirugia = timezone.now().date() + timedelta(days=15)
        fecha_cita = timezone.now().date() + timedelta(days=5)

        response = self.client.post('/api/autologa/programar/', {
            'idpersona': self.paciente.idpersona,
            'idgrupo': self.grupo_o_pos.idgrupo,
            'gruposanguineo': 'O+',
            'fechacirugia': fecha_cirugia.isoformat(),
            'fechahoracita': fecha_cita.isoformat(),
            'idusuario': self.user_med.idusuario
        })
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIn('idcita', response.data)
        self.assertIn('carnet_autologo', response.data)
        self.assertTrue(response.data['carnet_autologo'].startswith('HEMO-AUTO-'))

    def test_programar_donacion_autologa_rechazo_tiempo_invalido(self):
        # Menos de 72 horas (2 días de antelación)
        fecha_cirugia = timezone.now().date() + timedelta(days=2)
        fecha_cita = timezone.now().date() + timedelta(days=1)

        response = self.client.post('/api/autologa/programar/', {
            'idpersona': self.paciente.idpersona,
            'idgrupo': self.grupo_o_pos.idgrupo,
            'fechacirugia': fecha_cirugia.isoformat(),
            'fechahoracita': fecha_cita.isoformat()
        })
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('error', response.data)

    def test_custodia_fraccionamiento_y_cancelacion(self):
        extraccion = ExtraccionDonacion.objects.create(
            idpersonadonante=self.paciente,
            idpersonalsalud=self.personal_medico,
            codigoextraccion='EXT-AUT-001',
            fechahora=timezone.now(),
            volumenextraidoml=450,
            brazoextraccion='Izquierdo'
        )
        madre = UnidadSangreTotal.objects.create(
            idextraccion=extraccion,
            idgrupo=self.grupo_o_pos,
            codigobolsamadre='AUT-MADRE-999',
            tipobolsa='Doble',
            estadoliberacion='Liberada Apta'
        )
        EjemplarBolsa.objects.create(
            idunidadmadre=madre,
            idgrupo=self.grupo_o_pos,
            codigoejemplark='AUT-BOLSA-01',
            tipocomponente='Concentrado de Globulos Rojos',
            volumenml=250,
            fechaextraccion=timezone.now().date(),
            fechacaducidad=timezone.now().date() + timedelta(days=35),
            estadobolsak='Disponible'
        )
        EjemplarBolsa.objects.create(
            idunidadmadre=madre,
            idgrupo=self.grupo_o_pos,
            codigoejemplark='AUT-BOLSA-02',
            tipocomponente='Plasma Fresco Congelado',
            volumenml=200,
            fechaextraccion=timezone.now().date(),
            fechacaducidad=timezone.now().date() + timedelta(days=365),
            estadobolsak='Disponible'
        )

        res_custodia = self.client.post(f'/api/autologa/custodiar/{madre.idunidadmadre}/', {
            'fechacirugia': (timezone.now().date() + timedelta(days=15)).isoformat(),
            'idusuario': self.user_med.idusuario
        })
        self.assertEqual(res_custodia.status_code, status.HTTP_200_OK)
        self.assertEqual(len(res_custodia.data['unidades_reservadas']), 2)

        # Verificar que las bolsas tienen esexclusivoautologo=True y estadobolsak='Reservada'
        bolsas = EjemplarBolsa.objects.filter(idunidadmadre=madre)
        self.assertEqual(bolsas.count(), 2)
        for b in bolsas:
            self.assertTrue(b.esexclusivoautologo)
            self.assertEqual(b.estadobolsak, 'Reservada')

        # Cancelación Quirúrgica Definitiva
        res_cancel = self.client.post(f'/api/autologa/cancelar-cirugia/{self.paciente.idpersona}/', {
            'idpersonalsalud': self.personal_medico.persona_id,
            'motivo': 'Suspensión definitiva por complicaciones cardiovasculares'
        })
        self.assertEqual(res_cancel.status_code, status.HTTP_200_OK)
        self.assertEqual(len(res_cancel.data['unidades_incineradas']), 2)

        # Verificar que las bolsas pasaron a 'Baja'
        for b in EjemplarBolsa.objects.filter(idunidadmadre=madre):
            self.assertEqual(b.estadobolsak, 'Baja')

        # Verificar que se crearon los registros de BajaInventario para incineración
        bajas = BajaInventario.objects.filter(idejemplarbolsa__idunidadmadre=madre)
        self.assertEqual(bajas.count(), 2)
        for baja in bajas:
            self.assertEqual(baja.motivobaja, 'Cancelación Quirúrgica Autóloga')
            self.assertIn('Prohibido traspaso a stock de terceros', baja.observaciones)


# =============================================================================
# Pruebas del Tablero de Control Gerencial y KPIs
# =============================================================================
class TableroControlKPIsTestCase(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.rol_dir = Rol.objects.create(nombreRol='Director Ejecutivo', codigoRol='DIRECTOR')
        self.user_dir = Usuario.objects.create(
            username='director.kpis',
            email='director@hemovida.org',
            passwordHash='HemoVida#2026!',
            estado='Activo'
        )
        UsuarioRol.objects.create(usuario=self.user_dir, rol=self.rol_dir)
        self.client.force_authenticate(user=self.user_dir)

    def test_kpis_sin_actividad(self):
        # Período futuro sin actividad
        response = self.client.get('/api/kpis-gerenciales/?fecha_inicio=2040-01-01')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data['sin_actividad'])
        self.assertEqual(response.data['kpis']['tasa_efectividad_citas'], 0.0)
        self.assertEqual(response.data['kpis']['tasa_positividad_serologica'], 0.0)
        self.assertEqual(response.data['kpis']['recaudacion_bs'], 0.0)

    def test_kpis_con_actividad_y_filtros(self):
        hoy = timezone.now().date()
        p1 = Persona.objects.create(ci='9001', nombres='Test1', apellidos='Donante', fechanacimiento=date(1990, 1, 1), sexo='M')
        p2 = Persona.objects.create(ci='9002', nombres='Test2', apellidos='Donante', fechanacimiento=date(1992, 1, 1), sexo='F')
        
        # Cita efectiva y ausente
        CitaDonacion.objects.create(idpersona=p1, fechahoraprogramada=timezone.now(), asistenciaconfirmada=True)
        CitaDonacion.objects.create(idpersona=p2, fechahoraprogramada=timezone.now(), asistenciaconfirmada=False)

        grupo = GrupoSanguineo.objects.create(idGrupo=3, grupoABO='A', factorRh='Positivo')
        madre1 = UnidadSangreTotal.objects.create(
            idgrupo=grupo, codigobolsamadre='MADRE-TEST-01', tipobolsa='Simple', estadoliberacion='Liberada Apta'
        )
        madre2 = UnidadSangreTotal.objects.create(
            idgrupo=grupo, codigobolsamadre='MADRE-TEST-02', tipobolsa='Simple', estadoliberacion='En Cuarentena'
        )

        # Análisis Apto y No Apto (reactivo)
        AnalisisInmunoSerologico.objects.create(
            idunidadmadre=madre1,
            vihresultado='No Reactivo', hepatitisbresultado='No Reactivo',
            hepatitiscresultado='No Reactivo', sifilisresultado='No Reactivo', chagasresultado='No Reactivo',
            dictamenfinal='Apto', fechaanalisis=timezone.now()
        )
        AnalisisInmunoSerologico.objects.create(
            idunidadmadre=madre2,
            vihresultado='Reactivo', hepatitisbresultado='No Reactivo',
            hepatitiscresultado='No Reactivo', sifilisresultado='No Reactivo', chagasresultado='No Reactivo',
            dictamenfinal='No Apto', fechaanalisis=timezone.now()
        )

        # Cámara de almacenamiento
        cam = UbicacionAlmacen.objects.create(
            identificadorcompartimento='CAM-01',
            tipoequipo='Cámara Fría',
            temperaturaregistro=4.0,
            capacidadmaxima=100,
            capacidadocupada=25
        )
        EjemplarBolsa.objects.create(
            idgrupo=grupo, codigoejemplark='BOLSA-KPI-1',
            tipocomponente='Concentrado de Globulos Rojos', volumenml=250,
            fechaextraccion=hoy, fechacaducidad=hoy + timedelta(days=30),
            estadobolsak='Disponible', idubicacion=cam
        )

        # Hospital, Solicitud y Comprobante
        hosp = InstitucionSalud.objects.create(nombreinstitucion='Hospital Japonés', tipoinstitucion='Hospital Público', direccion='Santa Cruz')
        receptor = Receptor.objects.create(idpersona=p1, idgrupo=grupo, codigohistorialclinico='HC-999', gruposanguineoreceptor='A+')
        sol = SolicitudHospitalaria.objects.create(
            idinstitucion=hosp, idreceptor=receptor,
            numerosolicitud='SOL-2026-001',
            fechahorarequerimiento=timezone.now(),
            prioridadsolicitud='Media',
            cantidadbolsassolicitadas=2,
            estadosolicitud='Entregada'
        )
        ComprobantePago.objects.create(
            idsolicitud=sol,
            numerorecibofactura='FAC-001',
            conceptoservicio='Pruebas de compatibilidad',
            montototal=350.00,
            metodopago='Efectivo',
            estadopago='Pagado',
            fechahorapago=timezone.now()
        )

        response = self.client.get('/api/kpis-gerenciales/?periodo=mensual')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(response.data['sin_actividad'])
        self.assertEqual(response.data['kpis']['total_citas'], 2)
        self.assertEqual(response.data['kpis']['citas_atendidas'], 1)
        self.assertEqual(response.data['kpis']['tasa_efectividad_citas'], 50.0)
        self.assertEqual(response.data['kpis']['total_serologias'], 2)
        self.assertEqual(response.data['kpis']['serologias_reactivas'], 1)
        self.assertEqual(response.data['kpis']['tasa_positividad_serologica'], 50.0)
        self.assertEqual(response.data['kpis']['recaudacion_bs'], 350.0)
        self.assertGreaterEqual(len(response.data['ranking_hospitales']), 1)
        self.assertEqual(response.data['ranking_hospitales'][0]['hospital'], 'Hospital Japonés')


