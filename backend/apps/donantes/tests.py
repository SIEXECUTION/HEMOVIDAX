"""Regresiones del circuito real y protección de datos personales."""

from datetime import timedelta
from unittest.mock import patch
from django.utils import timezone
from apps.testing import WorkflowTestCase
from .models import (
    Donante,
    Diferimiento,
    CitaDonacion,
    DetalleCitaRequisito,
    ExtraccionDonacion,
    ConsentimientoInformado,
    IncentivoEntrega,
    AnalisisInmunoHematologico,
    TriajeClinico,
)


class DonationWorkflowTests(WorkflowTestCase):
    def booking(self, approved=True):
        return {
            "idpersona": self.person.pk,
            "fechahoraprogramada": (timezone.now() + timedelta(days=1)).isoformat(),
            "requisitos": [
                {"idrequisito": self.requirement.pk, "cumplerequisito": approved}
            ],
        }

    def test_booking_and_saved_answers(self):
        response = self.post("donantes/citas/", self.booking())
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["fase"], "Evaluación previa")
        self.assertTrue(DetalleCitaRequisito.objects.get().cumplerequisito)
        self.candidate.refresh_from_db()
        self.assertEqual(self.candidate.estadoaptitud, "En Evaluacion")

    def test_failed_prefilter_persists_cancelled_evaluation(self):
        r = self.post("donantes/citas/", self.booking(False))
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(CitaDonacion.objects.get().estadocita, "Cancelada")
        self.assertFalse(DetalleCitaRequisito.objects.get().cumplerequisito)
        self.assertEqual(len(r.data["motivos_exclusion"]), 1)

    def test_missing_or_duplicate_requirement_rejected_without_writes(self):
        for answers in ([], [self.booking()["requisitos"][0]] * 2):
            data = self.booking()
            data["requisitos"] = answers
            self.assertEqual(self.post("donantes/citas/", data).status_code, 400)
        self.assertFalse(CitaDonacion.objects.exists())

    def test_client_cannot_claim_prefilter_passed(self):
        data = self.booking(False)
        data["prefiltroaprobado"] = True
        self.assertFalse(self.post("donantes/citas/", data).data["prefiltroaprobado"])

    def test_second_booking_rejected(self):
        self.assertEqual(self.post("donantes/citas/", self.booking()).status_code, 201)
        self.assertEqual(self.post("donantes/citas/", self.booking()).status_code, 400)
        self.assertEqual(CitaDonacion.objects.count(), 1)

    def test_rest_interval_woman_and_man(self):
        donor = Donante.objects.create(
            idpersona=self.person,
            carnetdigitalcodigo="DON-1",
            fechaultimadonacion=self.today - timedelta(days=30),
        )
        for sex, remaining in [("F", 90), ("M", 60)]:
            self.person.sexo = sex
            self.person.save()
            r = self.client.get(f"/api/donantes/carnet-digital/{self.person.pk}/")
            self.assertEqual(r.data["elegibilidad"]["dias_restantes"], remaining)
            self.assertEqual(
                self.post("donantes/citas/", self.booking()).status_code, 400
            )

    def test_indefinite_deferral_blocks_booking_and_card_is_red(self):
        Diferimiento.objects.create(
            idposibledonador=self.candidate,
            fechainiciodiferimiento=self.today,
            motivodetallado="Indefinido",
            fechafindiferimiento=None,
        )
        self.assertEqual(self.post("donantes/citas/", self.booking()).status_code, 400)
        r = self.client.get(f"/api/donantes/carnet-digital/{self.person.pk}/")
        self.assertEqual(r.data["elegibilidad"]["semaforo"], "Rojo")

    def test_card_never_invents_blood_group(self):
        r = self.client.get(f"/api/donantes/{self.person.ci}/carnet/")
        self.assertEqual(r.data["grupo_sanguineo"], "Pendiente de tipificación")
        AnalisisInmunoHematologico.objects.create(
            idposibledonador=self.candidate,
            idpersonalsalud=self.staff,
            etapaanalisis="Pre-Extraccion",
            grupoaboconfirmado="AB",
            factorrhconfirmado="Negativo",
            pruebacoombsdirecta="Negativo",
            pruebacoombsindirecta="Negativo",
            rastreoanticuerposirregulares="Negativo",
        )
        self.assertEqual(
            self.client.get(f"/api/donantes/{self.person.ci}/carnet/").data[
                "grupo_sanguineo"
            ],
            "AB-",
        )

    def test_owner_access_and_other_person_denied(self):
        self.client.force_authenticate(self.donor_user)
        self.assertEqual(
            self.client.get(
                f"/api/donantes/carnet-digital/{self.person.pk}/"
            ).status_code,
            200,
        )
        self.assertEqual(
            self.client.get(
                f"/api/donantes/carnet-digital/{self.staff_person.pk}/"
            ).status_code,
            403,
        )
        self.client.force_authenticate(None)
        self.assertEqual(
            self.client.get(f"/api/donantes/{self.person.ci}/carnet/").status_code, 401
        )

    def test_admission_confirms_attendance_but_requires_triage(self):
        c = self.appointment()
        r = self.post(f"donantes/citas/{c.pk}/admision/", {})
        self.assertTrue(r.data["asistenciaconfirmada"])
        self.assertFalse(r.data["autoriza_flebotomia"])
        tr = self.triage()
        self.assertTrue(
            self.post(f"donantes/citas/{c.pk}/admision/", {}).data[
                "autoriza_flebotomia"
            ]
        )

    def triage_data(self, **extra):
        return dict(
            idpersona=self.person.pk,
            pesokg=65,
            temperatura=36.5,
            hemoglobina=14,
            presionsistolica=120,
            presiondiastolica=80,
            **extra,
        )

    def test_triage_requires_attendance(self):
        self.assertEqual(
            self.post("donantes/triaje/", self.triage_data()).status_code, 400
        )
        self.assertFalse(TriajeClinico.objects.exists())

    def test_triage_rejection_creates_deferral(self):
        self.appointment()
        data = self.triage_data()
        data["pesokg"] = 49
        data["diasinhabilitacion"] = 15
        r = self.post("donantes/triaje/", data)
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(r.data["resultadoaptitud"], "Rechazado")
        self.assertEqual(
            Diferimiento.objects.get().fechafindiferimiento,
            self.today + timedelta(days=15),
        )

    def extraction_data(self, tr):
        return dict(
            idpersonadonante=self.person.pk,
            idtriaje=tr.pk,
            idgrupo=self.group.pk,
            volumenml=450,
            brazo="Derecho",
            declaracionjuradaaceptada=True,
            firmadigital="Consentimiento de prueba",
        )

    def test_extraction_consent_quarantine_and_no_duplicate(self):
        self.appointment()
        tr = self.triage()
        r = self.post("donantes/flebotomia/", self.extraction_data(tr))
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(ConsentimientoInformado.objects.count(), 1)
        self.assertEqual(ExtraccionDonacion.objects.count(), 1)
        self.assertEqual(
            self.post("donantes/flebotomia/", self.extraction_data(tr)).status_code, 400
        )

    def test_missing_consent_writes_nothing(self):
        self.appointment()
        tr = self.triage()
        data = self.extraction_data(tr)
        data["declaracionjuradaaceptada"] = False
        self.assertEqual(self.post("donantes/flebotomia/", data).status_code, 400)
        self.assertFalse(ExtraccionDonacion.objects.exists())

    def test_failure_rolls_back_extraction_and_consent(self):
        self.appointment()
        tr = self.triage()
        with patch(
            "apps.donantes.views.UnidadSangreTotal.objects.create",
            side_effect=RuntimeError("test"),
        ):
            with self.assertRaises(RuntimeError):
                self.post("donantes/flebotomia/", self.extraction_data(tr))
        self.assertFalse(ExtraccionDonacion.objects.exists())
        self.assertFalse(ConsentimientoInformado.objects.exists())

    def test_refrigerio_requires_real_extraction_and_is_unique(self):
        self.assertEqual(
            self.post("donantes/extracciones/999/refrigerio/", {}).status_code, 404
        )
        self.appointment()
        tr = self.triage()
        ext = self.post("donantes/flebotomia/", self.extraction_data(tr)).data[
            "extraccion"
        ]["idextraccion"]
        self.assertEqual(
            self.post(f"donantes/extracciones/{ext}/refrigerio/", {}).status_code, 201
        )
        self.assertEqual(
            self.post(f"donantes/extracciones/{ext}/refrigerio/", {}).status_code, 400
        )
        self.assertTrue(IncentivoEntrega.objects.get().refrigerioentregado)

    def test_malformed_numeric_input_is_400(self):
        data = self.triage_data()
        data["pesokg"] = "invalid"
        self.assertEqual(self.post("donantes/triaje/", data).status_code, 400)

    def test_expired_temporary_deferral_allows_new_prefilter(self):
        Donante.objects.create(
            idpersona=self.person,
            carnetdigitalcodigo="DON-EXPIRED",
            estadohabilitacion="Diferido Temporal",
        )
        Diferimiento.objects.create(
            idposibledonador=self.candidate,
            fechainiciodiferimiento=self.today - timedelta(days=20),
            fechafindiferimiento=self.today - timedelta(days=1),
            motivodetallado="Temporal concluido",
        )
        r = self.post("donantes/citas/", self.booking())
        self.assertEqual(r.status_code, 201, r.data)

    def test_approved_analysis_selects_extraction_phase(self):
        AnalisisInmunoHematologico.objects.create(
            idposibledonador=self.candidate,
            idpersonalsalud=self.staff,
            etapaanalisis="Pre-Extraccion",
            grupoaboconfirmado="A",
            factorrhconfirmado="Positivo",
            pruebacoombsdirecta="Negativo",
            pruebacoombsindirecta="Negativo",
            rastreoanticuerposirregulares="Negativo",
            dictameninmunohematologico="Apto",
        )
        r = self.post("donantes/citas/", self.booking())
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(r.data["fase"], "Extracción")

    def test_foreign_patient_triage_cannot_authorize_extraction(self):
        from .models import PosibleDonador

        other = PosibleDonador.objects.create(
            idpersona=self.staff_person, carnetprovisionalcodigo="HV-OTHER"
        )
        tr = self.triage()
        tr.idposibledonador = other
        tr.save()
        self.appointment()
        self.assertEqual(
            self.post("donantes/flebotomia/", self.extraction_data(tr)).status_code, 400
        )
        self.assertFalse(ExtraccionDonacion.objects.exists())
