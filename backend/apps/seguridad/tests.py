"""
Pruebas unitarias para Seguridad, Autenticación y Auditoría
con roles RBAC en UsuarioRol.
"""
from django.test import TestCase
from django.core.exceptions import ValidationError
from django.core.cache import cache
from rest_framework.test import APIClient
from rest_framework import status
from datetime import date, timedelta
from django.utils import timezone

from .models import Persona, Rol, PersonalSalud, Usuario, UsuarioRol, BitacoraAuditoria
from .validators import SecurePasswordValidator

class PasswordValidatorTestCase(TestCase):
    def setUp(self):
        self.validator = SecurePasswordValidator()

    def test_valid_passwords(self):
        valid_passwords = [
            'HemoVida#2026!',
            'Admin$99Abc',
            'Secure*Pass1',
            'B0l1v1a@2026#',
        ]
        for pwd in valid_passwords:
            try:
                self.validator.validate(pwd)
            except ValidationError:
                self.fail(f"La contraseña válida '{pwd}' falló la validación.")

    def test_invalid_passwords(self):
        invalid_cases = [
            'Sh1!a',  # 5 chars (< 8)
            'alllowercase123!',  # no uppercase
            'ALLUPPERCASE123!',  # no lowercase
            'NoDigitsHere!@#',  # no digit
            'NoSpecialChars123A',  # no special
        ]
        for pwd in invalid_cases:
            with self.assertRaises(ValidationError, msg=f"'{pwd}' debió ser rechazada."):
                self.validator.validate(pwd)


class SeguridadAPITestCase(TestCase):
    def setUp(self):
        self.client = APIClient()

        # Crear Roles
        self.rol_admin = Rol.objects.create(
            nombreRol='Administrador',
            codigoRol='ADMIN',
            descripcion='Administrador general'
        )
        self.rol_posible = Rol.objects.create(
            nombreRol='Posible Donador',
            codigoRol='POSIBLE_DONADOR',
            descripcion='Postulante'
        )
        self.rol_bioq = Rol.objects.create(
            nombreRol='Bioquímico(a) Integral',
            codigoRol='BIOQ_INTEGRAL',
            descripcion='Tamizaje de sangre'
        )

        # Crear Personas
        self.persona_admin = Persona.objects.create(
            ci='11223344',
            nombres='Ernesto',
            apellidos='Zabala',
            fechaNacimiento=date(1987, 4, 5),
            sexo='M',
            nacionalidad='Boliviana',
            celular='71655441'
        )

        self.persona_medico = Persona.objects.create(
            ci='55667788',
            nombres='Patricia',
            apellidos='Arteaga',
            fechaNacimiento=date(1988, 6, 12),
            sexo='F',
            nacionalidad='Boliviana',
            celular='76044912'
        )

        self.personal_medico = PersonalSalud.objects.create(
            persona=self.persona_medico,
            cargo='Lic. en Enfermería',
            registroProfesional='ENF-2026-001'
        )

        # Crear Usuario Admin Activo
        self.user_admin = Usuario.objects.create(
            persona=self.persona_admin,
            username='admin.test',
            email='admin.test@hemovida.org',
            passwordHash='HemoVida#2026!',
            estado='Activo'
        )
        UsuarioRol.objects.create(usuario=self.user_admin, rol=self.rol_admin)

        # Crear Usuario Inactivo
        self.user_inactivo = Usuario.objects.create(
            username='inactivo.test',
            email='inactivo@hemovida.org',
            passwordHash='Inactivo#2026!',
            estado='Inactivo'
        )
        UsuarioRol.objects.create(usuario=self.user_inactivo, rol=self.rol_bioq)

    # -------------------------------------------------------------------------
    # Autenticar Usuario e Iniciar Sesión (rolesDisponibles)
    # -------------------------------------------------------------------------
    def test_login_exitoso_y_auditoria(self):
        response = self.client.post('/api/auth/login/', {
            'username': 'admin.test',
            'password': 'HemoVida#2026!'
        })
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('token', response.data)
        self.assertIn('rolesDisponibles', response.data)
        self.assertEqual(len(response.data['rolesDisponibles']), 1)
        self.assertEqual(response.data['rolesDisponibles'][0]['codigo'], 'ADMIN')
        self.assertEqual(response.data['usuarioId'], self.user_admin.idUsuario)

        # Verificar que se registró la auditoría
        auditoria = BitacoraAuditoria.objects.filter(
            usuario=self.user_admin,
            accionRealizada='Inicio de Sesión Exitoso'
        ).first()
        self.assertIsNotNone(auditoria)
        self.assertEqual(auditoria.tablaAfectada, 'Usuario')

    def test_login_usuario_inactivo_rechazado(self):
        response = self.client.post('/api/auth/login/', {
            'username': 'inactivo.test',
            'password': 'Inactivo#2026!'
        })
        self.assertIn(response.status_code, [status.HTTP_400_BAD_REQUEST, status.HTTP_403_FORBIDDEN])
        self.assertIn('Inactivo', str(response.data))

    def test_login_password_incorrecto(self):
        response = self.client.post('/api/auth/login/', {
            'username': 'admin.test',
            'password': 'WrongPassword123!'
        })
        self.assertIn(response.status_code, [status.HTTP_400_BAD_REQUEST, status.HTTP_401_UNAUTHORIZED])

    # -------------------------------------------------------------------------
    # PROCEDIMIENTO 1: Auto-Registro Público de Posible Donador
    # -------------------------------------------------------------------------
    def test_autoregistro_posible_donador(self):
        response = self.client.post('/api/auth/autoregistro/', {
            'ci': '98765432',
            'nombres': 'Carlos',
            'apellidos': 'Vargas',
            'sexo': 'M',
            'fechaNacimiento': '1995-08-20',
            'direccion': 'Av. Las Américas 123',
            'celular': '70011223',
            'ocupacion': 'Ingeniero',
            'username': 'carlos.vargas',
            'email': 'carlos.vargas@email.com',
            'password': 'PasswordSeguro#2026'
        })
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(Usuario.objects.filter(username='carlos.vargas').exists())
        nuevo_user = Usuario.objects.get(username='carlos.vargas')
        self.assertTrue(nuevo_user.roles.filter(codigoRol='POSIBLE_DONADOR').exists())
        self.assertEqual(nuevo_user.persona.posible_donador.estadoAptitud, 'No Apto')
        self.assertFalse(nuevo_user.persona.posible_donador.tieneAnalisis)

    # -------------------------------------------------------------------------
    # PROCEDIMIENTO 2: Alta de Personal de Salud por Administrador
    # -------------------------------------------------------------------------
    def test_crear_personal_salud_por_admin(self):
        self.client.force_authenticate(user=self.user_admin)
        response = self.client.post('/api/personal/crear/', {
            'ci': '77889900',
            'nombres': 'Claudia',
            'apellidos': 'Morales',
            'sexo': 'F',
            'fechaNacimiento': '1985-03-15',
            'celular': '77788999',
            'cargo': 'Bioquímica Principal',
            'registroProfesional': 'BIOQ-2026-999',
            'username': 'claudia.morales',
            'email': 'claudia.morales@hemovida.org',
            'password': 'PasswordSeguro#2026',
            'codigoRolAsignar': 'BIOQ_INTEGRAL'
        })
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIn('email_enviado', response.data)
        self.assertTrue(Usuario.objects.filter(username='claudia.morales').exists())
        staff_user = Usuario.objects.get(username='claudia.morales')
        self.assertTrue(staff_user.roles.filter(codigoRol='BIOQ_INTEGRAL').exists())
        # Verificar que la contraseña esté hasheada (no en texto plano) y valide con check_password
        self.assertNotEqual(staff_user.passwordHash, 'PasswordSeguro#2026')
        self.assertTrue(staff_user.passwordHash.startswith(('pbkdf2_', 'argon2', 'bcrypt')))
        self.assertTrue(staff_user.check_password('PasswordSeguro#2026'))
        self.assertFalse(staff_user.check_password('PasswordIncorrecta#999'))

    def test_crear_personal_salud_denegado_sin_admin(self):
        self.client.force_authenticate(user=self.user_inactivo)
        response = self.client.post('/api/personal/crear/', {
            'ci': '33445566',
            'nombres': 'Intruso',
            'apellidos': 'Test',
            'sexo': 'M',
            'fechaNacimiento': '1990-01-01',
            'cargo': 'Médico',
            'registroProfesional': 'MED-000',
            'username': 'intruso',
            'email': 'intruso@test.com',
            'password': 'PasswordSeguro#2026',
            'codigoRolAsignar': 'DOC_TRIAJE'
        })
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    # -------------------------------------------------------------------------
    # Matriz de Personal de Salud
    # -------------------------------------------------------------------------
    def test_listado_personal(self):
        self.client.force_authenticate(user=self.user_admin)
        response = self.client.get('/api/personal/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsInstance(response.data, list)
        self.assertGreaterEqual(len(response.data), 1)
        item = response.data[0]
        self.assertIn('cargo', item)
        self.assertIn('registroProfesional', item)
        self.assertIn('ci', item)

    def test_modificar_estado_usuario(self):
        self.client.force_authenticate(user=self.user_admin)
        response = self.client.patch(f'/api/usuarios/{self.user_inactivo.idUsuario}/estado/', {
            'estado': 'Activo'
        })
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.user_inactivo.refresh_from_db()
        self.assertEqual(self.user_inactivo.estado, 'Activo')

    # -------------------------------------------------------------------------
    # Consultar y Auditar Bitácora de Eventos Forenses
    # -------------------------------------------------------------------------
    def test_listar_auditoria_con_filtros(self):
        self.client.force_authenticate(user=self.user_admin)
        BitacoraAuditoria.objects.create(
            usuario=self.user_admin,
            rolActivo='Administrador',
            accionRealizada='Edición de prueba',
            tablaAfectada='EjemplarBolsa',
            idRegistroAfectado=10,
            ipOrigen='192.168.1.50'
        )

        response = self.client.get('/api/auditoria/?tabla_afectada=EjemplarBolsa')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('eventos', response.data)
        self.assertGreaterEqual(len(response.data['eventos']), 1)
        self.assertEqual(response.data['eventos'][0]['tablaAfectada'], 'EjemplarBolsa')

    # -------------------------------------------------------------------------
    # Recuperación y Modificación de Contraseña
    # -------------------------------------------------------------------------
    def test_recuperar_password_solicitar_y_confirmar(self):
        res_req = self.client.post('/api/auth/recuperar-password/solicitar/', {
            'email': self.user_admin.email
        })
        self.assertEqual(res_req.status_code, status.HTTP_200_OK)
        self.assertTrue(res_req.data['success'])
        self.assertIn('code', res_req.data)
        cached = cache.get(f"pwd_reset_{self.user_admin.email.lower()}")
        self.assertIsNotNone(cached)
        token = cached['code']

        nueva_clave = 'HemoVida#Nueva2026'
        res_conf = self.client.post('/api/auth/recuperar-password/confirmar/', {
            'email': self.user_admin.email,
            'token': token,
            'new_password': nueva_clave
        })
        self.assertEqual(res_conf.status_code, status.HTTP_200_OK)
        self.assertTrue(res_conf.data['success'])

        self.user_admin.refresh_from_db()
        self.assertTrue(self.user_admin.check_password(nueva_clave))

    def test_recuperar_password_solicitar_con_username(self):
        res_req = self.client.post('/api/auth/recuperar-password/solicitar/', {
            'email': self.user_admin.username
        })
        self.assertEqual(res_req.status_code, status.HTTP_200_OK)
        self.assertTrue(res_req.data['success'])
        self.assertIn('code', res_req.data)
        cached = cache.get(f"pwd_reset_{self.user_admin.username.lower()}")
        self.assertIsNotNone(cached)

    def test_cambiar_password_con_clave_actual(self):
        res = self.client.post('/api/auth/cambiar-password/', {
            'email': self.user_admin.email,
            'current_password': 'HemoVida#2026!',
            'new_password': 'SuperClave#2026!'
        })
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.user_admin.refresh_from_db()
        self.assertTrue(self.user_admin.check_password('SuperClave#2026!'))

    # -------------------------------------------------------------------------
    # Bloqueo Progresivo y Desbloqueo por Administrador
    # -------------------------------------------------------------------------
    def test_bloqueo_progresivo_tres_niveles(self):
        user_test = Usuario.objects.create(
            username='bloqueo.test',
            email='bloqueo@test.com',
            passwordHash='ClaveValida#123',
            estado='Activo'
        )

        # 1er ciclo: 3 fallos -> 15 min
        for i in range(2):
            res = self.client.post('/api/auth/autenticar/', {
                'identificador': 'bloqueo.test',
                'password': 'WrongPassword!'
            })
            self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)
        
        # 3er intento fallido
        res3 = self.client.post('/api/auth/autenticar/', {
            'identificador': 'bloqueo.test',
            'password': 'WrongPassword!'
        })
        self.assertEqual(res3.status_code, status.HTTP_403_FORBIDDEN)
        user_test.refresh_from_db()
        self.assertEqual(user_test.estado, 'Bloqueado Temporal')
        self.assertEqual(user_test.totalbloqueosrecibidos, 1)
        self.assertEqual(user_test.intentosfallidos, 3)
        self.assertIsNotNone(user_test.fechabloqueohasta)

        # Intento mientras está en ventana de bloqueo
        res_bloqueado = self.client.post('/api/auth/autenticar/', {
            'identificador': 'bloqueo.test',
            'password': 'ClaveValida#123'
        })
        self.assertEqual(res_bloqueado.status_code, status.HTTP_403_FORBIDDEN)

        # 2do ciclo: Simular que expiró el tiempo y se desbloquea temporalmente
        user_test.estado = 'Activo'
        user_test.intentosfallidos = 0
        user_test.fechabloqueohasta = None
        user_test.save()

        for i in range(3):
            self.client.post('/api/auth/autenticar/', {
                'identificador': 'bloqueo.test',
                'password': 'WrongPassword!'
            })
        user_test.refresh_from_db()
        self.assertEqual(user_test.totalbloqueosrecibidos, 2)
        self.assertEqual(user_test.estado, 'Bloqueado Temporal')

        # 3er ciclo: 60 minutos
        user_test.estado = 'Activo'
        user_test.intentosfallidos = 0
        user_test.fechabloqueohasta = None
        user_test.save()

        for i in range(3):
            self.client.post('/api/auth/autenticar/', {
                'identificador': 'bloqueo.test',
                'password': 'WrongPassword!'
            })
        user_test.refresh_from_db()
        self.assertEqual(user_test.totalbloqueosrecibidos, 3)
        self.assertEqual(user_test.estado, 'Bloqueado Temporal')

    def test_desbloquear_usuario_admin(self):
        user_bloqueado = Usuario.objects.create(
            username='user.bloqueado',
            email='bloqueado@hemovida.org',
            passwordHash='Clave#123',
            estado='Bloqueado Temporal',
            intentosfallidos=3,
            fechabloqueohasta=timezone.now() + timedelta(minutes=30)
        )

        # Usuario no autenticado / no admin intenta desbloquear
        res_denegado = self.client.post(f'/api/usuarios/{user_bloqueado.idusuario}/desbloquear/')
        self.assertIn(res_denegado.status_code, [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN])

        # Admin autenticado desbloquea
        self.client.force_authenticate(user=self.user_admin)
        res_ok = self.client.post(f'/api/usuarios/{user_bloqueado.idusuario}/desbloquear/')
        self.assertEqual(res_ok.status_code, status.HTTP_200_OK)
        user_bloqueado.refresh_from_db()
        self.assertEqual(user_bloqueado.estado, 'Activo')
        self.assertEqual(user_bloqueado.intentosfallidos, 0)
        self.assertIsNone(user_bloqueado.fechabloqueohasta)

        # Verificar auditoría del desbloqueo
        auditoria = BitacoraAuditoria.objects.filter(
            accionrealizada__startswith='Desbloqueo manual de cuenta de usuario',
            idregistroafectado=user_bloqueado.idusuario
        ).first()
        self.assertIsNotNone(auditoria)

    def test_login_con_header_x_active_role(self):
        res = self.client.post(
            '/api/auth/autenticar/',
            {'identificador': 'admin.test', 'password': 'HemoVida#2026!'},
            HTTP_X_ACTIVE_ROLE='Rol Personalizado'
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        auditoria = BitacoraAuditoria.objects.filter(
            idusuario=self.user_admin,
            rolactivo='Rol Personalizado'
        ).first()
        self.assertIsNotNone(auditoria)

