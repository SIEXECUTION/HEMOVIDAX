"""Fixtures aisladas para probar los flujos sin tocar Supabase."""

from datetime import date, timedelta
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient
from apps.seguridad.models import Usuario, Rol, UsuarioRol, PersonalSalud
from apps.donantes.models import (
    Persona,
    PosibleDonador,
    CitaDonacion,
    TriajeClinico,
    ExtraccionDonacion,
    RequisitoDonacion,
)
from apps.inventario.models import (
    GrupoSanguineo,
    UbicacionAlmacen,
    UnidadSangreTotal,
    EjemplarBolsa,
)


class WorkflowTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.today = timezone.localdate()
        cls.person = Persona.objects.create(
            ci="12345",
            nombres="Ana",
            apellidos="Prueba",
            sexo="F",
            fechanacimiento=date(1995, 1, 1),
        )
        cls.candidate = PosibleDonador.objects.create(
            idpersona=cls.person, carnetprovisionalcodigo="HV-POST-1"
        )
        cls.donor_user = Usuario.objects.create(
            idpersona=cls.person,
            username="ana",
            email="ana@example.test",
            estado="Activo",
        )
        cls.donor_user.set_password("Clave#Segura2026")
        cls.donor_user.save()
        cls.staff_person = Persona.objects.create(
            ci="67890",
            nombres="Luis",
            apellidos="Personal",
            sexo="M",
            fechanacimiento=date(1985, 1, 1),
        )
        cls.staff = PersonalSalud.objects.create(
            persona=cls.staff_person, cargo="Medico", registroprofesional="TEST-1"
        )
        cls.admin = Usuario.objects.create(
            idpersona=cls.staff_person,
            username="admin",
            email="admin@example.test",
            estado="Activo",
        )
        cls.admin.set_password("Clave#Segura2026")
        cls.admin.save()
        cls.roles = {}
        for code in [
            "ADMIN",
            "DOC_TRIAJE",
            "PERS_COLECTA",
            "BIOQ_INTEGRAL",
            "TEC_LOGISTICA",
            "MED_SOLICITANTE",
            "POSIBLE_DONADOR",
            "DONANTE",
        ]:
            cls.roles[code] = Rol.objects.create(codigorol=code, nombrerol=code)
        UsuarioRol.objects.create(idusuario=cls.admin, idrol=cls.roles["ADMIN"])
        UsuarioRol.objects.create(
            idusuario=cls.donor_user, idrol=cls.roles["POSIBLE_DONADOR"]
        )
        cls.group = GrupoSanguineo.objects.create(grupoabo="O", factorrh="Positivo")
        cls.room = UbicacionAlmacen.objects.create(
            identificadorcompartimento="TEST-ROOM",
            tipoequipo="Camara",
            temperaturaregistro=4,
            capacidadmaxima=100,
            capacidadocupada=0,
        )
        cls.requirement = RequisitoDonacion.objects.create(
            nombrerequisito="Requisito de prueba", tiporequisito="Temporal"
        )

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(self.admin)

    def post(self, url, data):
        return self.client.post("/api/" + url, data, format="json")

    def appointment(self):
        return CitaDonacion.objects.create(
            idpersona=self.person,
            fechahoraprogramada=timezone.now() + timedelta(days=1),
            prefiltroaprobado=True,
            asistenciaconfirmada=True,
        )

    def triage(self, **kwargs):
        return TriajeClinico.objects.create(
            idposibledonador=self.candidate,
            idpersonalsalud=self.staff,
            pesokg=65,
            presionsistolicammhg=120,
            presiondiastolicammhg=80,
            nivelhemoglobina=14,
            temperatura=36.5,
            resultadoaptitud=kwargs.pop("resultadoaptitud", "Apto"),
            **kwargs,
        )

    def mother(self):
        ext = ExtraccionDonacion.objects.create(
            idpersonadonante=self.person,
            idpersonalsalud=self.staff,
            codigoextraccion="EXT-TEST",
            volumenextraidoml=450,
            brazoextraccion="Derecho",
        )
        return UnidadSangreTotal.objects.create(
            idextraccion=ext,
            idgrupo=self.group,
            codigobolsamadre="MAD-TEST",
            tipobolsa="Cuadruple",
            estadoliberacion="En Cuarentena",
        )

    def bag(self, mother, **kwargs):
        defaults = dict(
            idunidadmadre=mother,
            idgrupo=self.group,
            idubicacion=self.room,
            codigoejemplark="BAG-TEST",
            tipocomponente="Concentrado de Globulos Rojos",
            volumenml=250,
            fechaextraccion=self.today,
            fechacaducidad=self.today + timedelta(days=5),
            estadobolsak="Disponible",
        )
        defaults.update(kwargs)
        return EjemplarBolsa.objects.create(**defaults)
