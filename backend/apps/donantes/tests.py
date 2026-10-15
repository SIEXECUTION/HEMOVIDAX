"""
Pruebas unitarias para la app Donantes y Carnet Digital de Donante.
"""
from django.test import TestCase
from rest_framework.test import APIClient
from rest_framework import status
from datetime import date, timedelta
from django.utils import timezone

from apps.seguridad.models import Persona, PersonalSalud
from apps.inventario.models import GrupoSanguineo, EjemplarBolsa, UnidadSangreTotal
from .models import (
    Donante, PosibleDonador, ExtraccionDonacion, Diferimiento,
    TriajeClinico, CitaDonacion, RequisitoDonacion
)

class DonanteCarnetDigitalTestCase(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.hoy = timezone.now().date()

        # Personal de salud para registrar extracciones
        self.persona_enfermero = Persona.objects.create(
            ci='ENF-1111',
            nombres='Silvia',
            apellidos='Guerrero',
            fechaNacimiento=date(1992, 1, 25),
            sexo='F'
        )
        self.enfermero = PersonalSalud.objects.create(
            persona=self.persona_enfermero,
            cargo='Bioquímica de Flebotomía',
            registroProfesional='FLE-2026-999'
        )

        # 1. Donante Varón (M) con donación hace 30 días (debe esperar 60 días más de los 90 reglamentarios)
        self.persona_varon = Persona.objects.create(
            ci='7894561-SC',
            nombres='Carlos Andrés',
            apellidos='Pimentel',
            fechaNacimiento=date(1995, 4, 18),
            sexo='M',
            celular='76044912'
        )
        self.donante_varon = Donante.objects.create(
            persona=self.persona_varon,
            tipoDonante='Voluntario Altruista',
            carnetDigitalCodigo='HV-DON-2024-0491',
            estadoHabilitacion='Apto',
            fechaUltimaDonacion=self.hoy - timedelta(days=30)
        )

        # Registrar 2 extracciones históricas (450ml + 450ml = 900ml)
        ExtraccionDonacion.objects.create(
            personaDonante=self.persona_varon,
            personalSalud=self.enfermero,
            codigoExtraccion='EXT-20260101-001',
            brazoExtraccion='Izquierdo',
            volumenExtraidoMl=450
        )
        ExtraccionDonacion.objects.create(
            personaDonante=self.persona_varon,
            personalSalud=self.enfermero,
            codigoExtraccion='EXT-20260201-002',
            brazoExtraccion='Derecho',
            volumenExtraidoMl=450
        )

        # 2. Donante Mujer (F) con donación hace 100 días (regla: 120 días, le faltan 20 días)
        self.persona_mujer = Persona.objects.create(
            ci='8934120-SC',
            nombres='Sofía Elena',
            apellidos='Mendoza',
            fechaNacimiento=date(1998, 9, 12),
            sexo='F',
            celular='78190234'
        )
        self.donante_mujer = Donante.objects.create(
            persona=self.persona_mujer,
            tipoDonante='Reposicion Familiar',
            carnetDigitalCodigo='HV-DON-2025-1102',
            estadoHabilitacion='Apto',
            fechaUltimaDonacion=self.hoy - timedelta(days=100)
        )

        # 3. Posible Donador (sin análisis)
        self.persona_posible = Persona.objects.create(
            ci='12345678',
            nombres='Mario',
            apellidos='Suarez',
            fechaNacimiento=date(2000, 5, 10),
            sexo='M',
            celular='70099887'
        )
        self.posible_donador = PosibleDonador.objects.create(
            persona=self.persona_posible,
            estadoAptitud='No Apto',
            tieneAnalisis=False
        )

    def test_carnet_digital_varon_regla_90_dias(self):
        response = self.client.get(f'/api/donantes/{self.persona_varon.ci}/carnet/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.data

        self.assertFalse(data['esPosibleDonador'])
        self.assertEqual(data['carnetDigitalCodigo'], 'HV-DON-2024-0491')
        self.assertEqual(data['ci'], '7894561-SC')
        self.assertEqual(data['sexo'], 'M')
        self.assertEqual(data['periodoEsperaDias'], 90)
        self.assertEqual(data['diasRestantesEspera'], 60)
        self.assertFalse(data['estaHabilitadoParaDonar'])
        self.assertEqual(data['totalDonacionesHistoricas'], 2)
        self.assertEqual(data['volumenHistoricoAportadoMl'], 900)
        self.assertEqual(len(data['extraccionesRecientes']), 2)

    def test_carnet_digital_mujer_regla_120_dias(self):
        response = self.client.get(f'/api/donantes/{self.persona_mujer.ci}/carnet/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.data

        self.assertFalse(data['esPosibleDonador'])
        self.assertEqual(data['sexo'], 'F')
        self.assertEqual(data['periodoEsperaDias'], 120)
        self.assertEqual(data['diasRestantesEspera'], 20)
        self.assertFalse(data['estaHabilitadoParaDonar'])

    def test_consulta_posible_donador(self):
        response = self.client.get(f'/api/donantes/{self.persona_posible.ci}/carnet/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.data

        self.assertTrue(data['esPosibleDonador'])
        self.assertEqual(data['ci'], '12345678')
        self.assertEqual(data['estadoAptitud'], 'No Apto')
        self.assertFalse(data['tieneAnalisis'])
        self.assertFalse(data['estaHabilitadoParaDonar'])

    def test_donante_no_encontrado(self):
        response = self.client.get('/api/donantes/9999999-INEXISTENTE/carnet/')
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    # -------------------------------------------------------------------------
    # CarnetDigitalQRView (/api/donantes/carnet-digital/<idpersona>/)
    # -------------------------------------------------------------------------
    def test_carnet_digital_qr_exitoso(self):
        response = self.client.get(f'/api/donantes/carnet-digital/{self.persona_varon.idpersona}/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.data

        self.assertEqual(data['carnet_codigo'], 'HV-DON-2024-0491')
        self.assertEqual(data['ci'], '7894561-SC')
        self.assertEqual(data['sexo'], 'M')
        self.assertEqual(data['intervalo_biologico_dias'], 90)
        self.assertEqual(data['dias_restantes_espera'], 60)
        self.assertEqual(data['semaforo_carnet'], 'Amarillo')
        self.assertFalse(data['apto_para_donar_hoy'])
        self.assertEqual(data['total_donaciones'], 2)
        self.assertEqual(data['volumen_total_aportado_ml'], 900)
        self.assertEqual(data['vidas_impactadas'], 6)
        self.assertIn('HEMOVIDA|CARNET:HV-DON-2024-0491', data['qr_validation_string'])
        self.assertEqual(len(data['historial_donaciones']), 2)

    def test_carnet_digital_qr_diferimiento_activo(self):
        # Crear diferimiento temporal activo de 15 días para la mujer
        posible_mujer, _ = PosibleDonador.objects.get_or_create(
            persona=self.persona_mujer,
            defaults={'estadoAptitud': 'Apto', 'tieneAnalisis': True}
        )
        Diferimiento.objects.create(
            idposibledonador=posible_mujer,
            motivodetallado='Tratamiento odontológico reciente',
            diasinhabilitacion=15,
            fechainiciodiferimiento=self.hoy,
            fechafindiferimiento=self.hoy + timedelta(days=15)
        )

        response = self.client.get(f'/api/donantes/carnet-digital/{self.persona_mujer.idpersona}/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.data

        self.assertEqual(data['semaforo_carnet'], 'Rojo')
        self.assertFalse(data['apto_para_donar_hoy'])
        self.assertIn('Tratamiento odontológico reciente', data['mensaje_estado'])

    def test_carnet_digital_qr_no_donante(self):
        response = self.client.get(f'/api/donantes/carnet-digital/{self.persona_posible.idpersona}/')
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


class OrquestacionOperacionesTestCase(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.hoy = timezone.now().date()

        self.medico_per = Persona.objects.create(
            ci='DOC-777', nombres='Valeria', apellidos='Guzman',
            fechaNacimiento=date(1985, 5, 20), sexo='F'
        )
        self.medico = PersonalSalud.objects.create(
            persona=self.medico_per, cargo='Médico Evaluador', registroProfesional='MED-777'
        )

        self.postulante_per = Persona.objects.create(
            ci='99887766', nombres='Jorge', apellidos='Torres',
            fechaNacimiento=date(1996, 7, 10), sexo='M'
        )
        self.posible_donador = PosibleDonador.objects.create(
            persona=self.postulante_per, estadoAptitud='No Apto', tieneAnalisis=False
        )

        self.grupo_o_pos = GrupoSanguineo.objects.create(
            idgrupo=1, grupoabo='O', factorrh='Positivo'
        )

    def test_agendar_cita_exitoso(self):
        req = RequisitoDonacion.objects.create(
            nombrerequisito='Mayor de 18 años',
            tiporequisito='Biometría Básica',
            esexcluyentedefinitivo=False
        )
        payload = {
            'idposibledonador': self.postulante_per.idpersona,
            'fechahoraprogramada': timezone.now().isoformat(),
            'tipocita': 'Voluntario Altruista',
            'requisitos': [
                {'idrequisito': req.idrequisito, 'cumplerequisito': True, 'observacion': 'Tiene 30 años'}
            ]
        }
        response = self.client.post('/api/donantes/citas/', payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIn('idcita', response.data)
        self.assertEqual(response.data['requisitos_evaluados'], 1)

    def test_agendar_cita_con_diferimiento_activo_falla(self):
        Diferimiento.objects.create(
            idposibledonador=self.posible_donador,
            motivodetallado='Tatuaje menor a 1 año',
            diasinhabilitacion=180,
            fechainiciodiferimiento=self.hoy,
            fechafindiferimiento=self.hoy + timedelta(days=180)
        )
        payload = {
            'idposibledonador': self.postulante_per.idpersona,
            'fechahoraprogramada': timezone.now().isoformat(),
            'tipocita': 'Voluntario Altruista'
        }
        response = self.client.post('/api/donantes/citas/', payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('diferimiento activo', response.data['detail'])

    def test_procesar_triaje_clinico_apto(self):
        payload = {
            'idposibledonador': self.postulante_per.idpersona,
            'idpersonalsalud': self.medico.persona.idpersona,
            'pesokg': 68.0,
            'presionsistolica': 120,
            'presiondiastolica': 80,
            'hemoglobina': 14.5,
            'temperatura': 36.5
        }
        response = self.client.post('/api/donantes/triaje/', payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['resultadoaptitud'], 'Apto')
        self.posible_donador.refresh_from_db()
        self.assertEqual(self.posible_donador.estadoaptitud, 'Apto')

    def test_procesar_triaje_clinico_rechazado_crea_diferimiento(self):
        payload = {
            'idposibledonador': self.postulante_per.idpersona,
            'idpersonalsalud': self.medico.persona.idpersona,
            'pesokg': 46.0,  # Bajo peso < 50kg
            'presionsistolica': 110,
            'presiondiastolica': 70,
            'hemoglobina': 11.0,  # Baja hemoglobina < 12.5
            'temperatura': 37.0,
            'diasinhabilitacion': 30
        }
        response = self.client.post('/api/donantes/triaje/', payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['resultadoaptitud'], 'Rechazado')
        self.assertIsNotNone(response.data['diferimiento'])
        self.posible_donador.refresh_from_db()
        self.assertEqual(self.posible_donador.estadoaptitud, 'No Apto')

    def test_registrar_flebotomia_y_fraccionamiento_atomic(self):
        # 1. Crear triaje Apto
        triaje = TriajeClinico.objects.create(
            idposibledonador=self.posible_donador,
            idpersonalsalud=self.medico,
            pesokg=70.0,
            presionsistolicammhg=120,
            presiondiastolicammhg=80,
            nivelhemoglobina=15.0,
            temperatura=36.6,
            resultadoaptitud='Apto'
        )

        payload = {
            'idpersonadonante': self.postulante_per.idpersona,
            'idpersonalsalud': self.medico.persona.idpersona,
            'idtriaje': triaje.idtriaje,
            'idgrupo': self.grupo_o_pos.idgrupo,
            'brazo': 'Izquierdo',
            'volumenml': 450,
            'categoriaetaria': 'Adulto'
        }
        response = self.client.post('/api/donantes/flebotomia/', payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['extraccion']['brazoextraccion'], 'Izquierdo')
        self.assertEqual(response.data['extraccion']['idtriaje'], triaje.idtriaje)

        # Verificar bolsas generadas: estrictamente 'Concentrado de Globulos Rojos' y 'Plasma Fresco Congelado'
        bolsas = response.data['bolsas']
        self.assertEqual(len(bolsas), 2)
        componentes = [b['tipocomponente'] for b in bolsas]
        self.assertIn('Concentrado de Globulos Rojos', componentes)
        self.assertIn('Plasma Fresco Congelado', componentes)
        for b in bolsas:
            self.assertEqual(b['categoriaetaria'], 'Adulto')


