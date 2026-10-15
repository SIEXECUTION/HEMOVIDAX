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
            "HemoVida#2026!",
            "Admin$99Abc",
            "Secure*Pass1",
            "B0l1v1a@2026#",
        ]
        for pwd in valid_passwords:
            try:
                self.validator.validate(pwd)
            except ValidationError:
                self.fail(f"La contraseña válida '{pwd}' falló la validación.")

    def test_invalid_passwords(self):
        invalid_cases = [
            "Sh1!a",  # 5 chars (< 8)
            "alllowercase123!",  # no uppercase
            "ALLUPPERCASE123!",  # no lowercase
            "NoDigitsHere!@#",  # no digit
            "NoSpecialChars123A",  # no special
        ]
        for pwd in invalid_cases:
            with self.assertRaises(
                ValidationError, msg=f"'{pwd}' debió ser rechazada."
            ):
                self.validator.validate(pwd)


from unittest.mock import patch
from apps.testing import WorkflowTestCase
from .models import UsuarioRol


class SecurityWorkflowTests(WorkflowTestCase):
    def login(self, password="Clave#Segura2026"):
        return self.post(
            "auth/login/", {"username": self.donor_user.username, "password": password}
        )

    def test_tokens_authenticate_real_user_and_return_person(self):
        self.client.force_authenticate(None)
        r = self.login()
        self.assertEqual(r.status_code, 200, r.data)
        self.assertTrue(r.data["tokens"]["access"])
        self.assertEqual(r.data["usuario"]["persona"]["idPersona"], self.person.pk)
        self.client.credentials(
            HTTP_AUTHORIZATION="Bearer " + r.data["tokens"]["access"],
            HTTP_X_ACTIVE_ROLE="POSIBLE_DONADOR",
        )
        r = self.client.get("/api/auth/me/")
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(r.data["username"], "ana")

    def test_composite_role_key_allows_multi_role_and_deletes_one(self):
        UsuarioRol.objects.create(
            idusuario=self.donor_user, idrol=self.roles["DOC_TRIAJE"]
        )
        self.assertEqual(self.donor_user.roles.count(), 2)
        self.assertTrue(self.login().data["requiere_selector_rol"])
        UsuarioRol.objects.get(
            idusuario=self.donor_user, idrol=self.roles["DOC_TRIAJE"]
        ).delete()
        self.assertEqual(self.donor_user.roles.count(), 1)

    def test_unassigned_role_header_is_denied(self):
        self.client.force_authenticate(None)
        token = self.login().data["tokens"]["access"]
        self.client.credentials(
            HTTP_AUTHORIZATION="Bearer " + token, HTTP_X_ACTIVE_ROLE="ADMIN"
        )
        self.assertEqual(self.client.get("/api/usuarios/").status_code, 401)

    def test_all_lockout_levels_and_expiration(self):
        for expected in (15, 30, 60):
            for i in range(3):
                self.assertEqual(
                    self.login("Incorrecta").status_code, 401 if i < 2 else 403
                )
            self.donor_user.refresh_from_db()
            self.assertAlmostEqual(
                (self.donor_user.fechabloqueohasta - timezone.now()).total_seconds()
                / 60,
                expected,
                delta=0.1,
            )
            self.assertEqual(self.login().status_code, 403)
            self.donor_user.fechabloqueohasta = timezone.now() - timedelta(seconds=1)
            self.donor_user.save()
            self.assertEqual(self.login().status_code, 200)
        self.donor_user.refresh_from_db()
        self.assertEqual(self.donor_user.totalbloqueosrecibidos, 3)
        self.assertEqual(self.donor_user.intentosfallidos, 0)

    def test_admin_unlock_preserves_disciplinary_block(self):
        self.donor_user.estado = "Bloqueado"
        self.donor_user.save()
        self.assertEqual(
            self.post(f"usuarios/{self.donor_user.pk}/desbloquear/", {}).status_code,
            409,
        )
        self.donor_user.estado = "Bloqueado Temporal"
        self.donor_user.save()
        self.assertEqual(
            self.post(f"usuarios/{self.donor_user.pk}/desbloquear/", {}).status_code,
            200,
        )

    def test_anonymous_cannot_impersonate_admin(self):
        self.client.force_authenticate(None)
        self.assertEqual(
            self.post(
                f"usuarios/{self.donor_user.pk}/desbloquear/",
                {"idusuario_admin": self.admin.pk},
            ).status_code,
            401,
        )

    def test_audit_admin_only_and_no_public_write(self):
        self.client.force_authenticate(self.donor_user)
        self.assertEqual(self.client.get("/api/auditoria/").status_code, 403)
        self.client.force_authenticate(self.admin)
        self.assertEqual(
            self.post(
                "auditoria/", {"idUsuario": self.donor_user.pk, "accion": "Falsa"}
            ).status_code,
            405,
        )

    def test_night_filter_includes_19_and_all_roles(self):
        from datetime import datetime

        for hour in (6, 7, 18, 19, 23):
            BitacoraAuditoria.objects.create(
                idusuario=self.admin,
                rolactivo="ADMIN",
                accionrealizada=str(hour),
                tablaafectada="Prueba",
                fechahora=timezone.make_aware(
                    datetime.combine(self.today, datetime.min.time()).replace(hour=hour)
                ),
            )
        r = self.client.get("/api/auditoria/?fuera_turno=true")
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(r.data["totalRegistros"], 3)

    def test_registration_creates_hashed_user_and_candidate(self):
        data = {
            "ci": "NEW-1",
            "nombres": "Nueva",
            "apellidos": "Persona",
            "sexo": "F",
            "fechaNacimiento": "2000-01-01",
            "username": "nueva",
            "email": "nueva@example.test",
            "password": "Segura#Nueva2026",
        }
        r = self.post("auth/autoregistro/", data)
        self.assertEqual(r.status_code, 201, r.data)
        user = Usuario.objects.get(username="nueva")
        self.assertNotEqual(user.passwordhash, data["password"])
        self.assertTrue(user.check_password(data["password"]))
        self.assertEqual(
            list(user.roles.values_list("codigorol", flat=True)), ["POSIBLE_DONADOR"]
        )
        self.assertEqual(self.post("auth/autoregistro/", data).status_code, 400)

    def test_request_and_approve_health_role(self):
        self.client.force_authenticate(self.donor_user)
        r = self.post(
            "personal/solicitudes/",
            {
                "cargo": "Medica",
                "registroprofesional": "TEST-2",
                "codigo": "DOC_TRIAJE",
            },
        )
        self.assertEqual(r.status_code, 201, r.data)
        self.assertFalse(self.donor_user.roles.filter(codigorol="DOC_TRIAJE").exists())
        self.client.force_authenticate(self.admin)
        url = f"personal/solicitudes/{r.data['id']}/resolver/"
        r = self.post(url, {"aprobar": True})
        self.assertEqual(r.status_code, 200, r.data)
        self.assertTrue(self.donor_user.roles.filter(codigorol="DOC_TRIAJE").exists())
        self.assertEqual(self.post(url, {"aprobar": True}).status_code, 409)

    def test_reset_delivered_only_by_email_and_single_use(self):
        self.client.force_authenticate(None)
        with patch(
            "apps.seguridad.views.enviar_correo_institucional", return_value=True
        ) as mail:
            r = self.post(
                "auth/recuperar-password/solicitar/", {"email": self.donor_user.email}
            )
        self.assertEqual(r.status_code, 200, r.data)
        self.assertNotIn("code", r.data)
        token = mail.call_args.args[1].splitlines()[1]
        d = {"token": token, "new_password": "Nueva#Segura2026"}
        self.assertEqual(
            self.post("auth/recuperar-password/confirmar/", d).status_code, 200
        )
        self.assertEqual(
            self.post("auth/recuperar-password/confirmar/", d).status_code, 400
        )

    def test_password_complexity_and_authenticated_change(self):
        self.client.force_authenticate(self.donor_user)
        d = {"current_password": "Clave#Segura2026", "new_password": "weak"}
        self.assertEqual(self.post("auth/cambiar-password/", d).status_code, 400)
        d["new_password"] = "Nueva#Segura2026"
        self.assertEqual(self.post("auth/cambiar-password/", d).status_code, 200)
        self.client.force_authenticate(None)
        self.assertEqual(self.post("auth/cambiar-password/", d).status_code, 401)

    def test_health_503_hides_database_credentials(self):
        with patch(
            "django.db.backends.utils.CursorWrapper.execute",
            side_effect=RuntimeError("private secret"),
        ):
            r = self.client.get("/api/health/")
        self.assertEqual(r.status_code, 503)
        self.assertNotIn("secret", r.content.decode())

    def test_pending_role_request_cannot_be_duplicated(self):
        self.client.force_authenticate(self.donor_user)
        data = {
            "cargo": "Medica",
            "registroprofesional": "TEST-2",
            "codigo": "DOC_TRIAJE",
        }
        self.assertEqual(self.post("personal/solicitudes/", data).status_code, 201)
        self.assertEqual(self.post("personal/solicitudes/", data).status_code, 400)

    def test_admin_can_create_health_staff(self):
        data = {
            "ci": "STAFF-NEW",
            "nombres": "Elena",
            "apellidos": "Nueva",
            "sexo": "F",
            "fechaNacimiento": "1990-01-01",
            "cargo": "Bioquimica",
            "registroProfesional": "NEW-REG",
            "username": "elena",
            "email": "elena@example.test",
            "password": "Segura#Nueva2026",
            "codigoRolAsignar": "BIOQ_INTEGRAL",
        }
        r = self.post("personal/crear/", data)
        self.assertEqual(r.status_code, 201, r.data)
        user = Usuario.objects.get(username="elena")
        self.assertTrue(user.roles.filter(codigorol="BIOQ_INTEGRAL").exists())
        self.assertTrue(user.check_password(data["password"]))
        r = self.client.get("/api/personal/")
        self.assertEqual(r.status_code, 200, r.data)

    def test_encoded_hash_cannot_be_used_as_password(self):
        self.assertTrue(self.donor_user.check_password('Clave#Segura2026'))
        self.assertFalse(self.donor_user.check_password(self.donor_user.passwordhash))

from django.test import SimpleTestCase


class CloudflareCorsTests(SimpleTestCase):
    origin = 'https://hemovidax.siexecution2026.workers.dev'

    def test_worker_origin_preflight_accepts_login_and_role_headers(self):
        r = self.client.options('/api/auth/login/', HTTP_ORIGIN=self.origin,
            HTTP_ACCESS_CONTROL_REQUEST_METHOD='POST',
            HTTP_ACCESS_CONTROL_REQUEST_HEADERS='content-type,authorization,x-active-role')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.headers.get('Access-Control-Allow-Origin'), self.origin)
        allowed = r.headers.get('Access-Control-Allow-Headers', '').lower()
        self.assertIn('authorization', allowed)
        self.assertIn('x-active-role', allowed)

    def test_other_workers_are_not_authorized(self):
        r = self.client.options('/api/auth/login/', HTTP_ORIGIN='https://other.example.workers.dev',
            HTTP_ACCESS_CONTROL_REQUEST_METHOD='POST')
        self.assertNotIn('Access-Control-Allow-Origin', r.headers)
