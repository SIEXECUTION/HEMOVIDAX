"""Pruebas de FEFO, fraccionamiento, laboratorio y autodonación."""

from datetime import timedelta
from django.utils import timezone
from apps.testing import WorkflowTestCase
from apps.donantes.models import (
    Donante,
    Receptor,
    CitaLaboratorio,
    CitaDonacion,
    AnalisisInmunoSerologico,
)
from apps.seguridad.models import UsuarioRol
from .models import (
    EjemplarBolsa,
    ParametroStockMinimo,
    BajaInventario,
    ReservaSangre,
    SolicitudHospitalaria,
    InstitucionSalud,
)


class InventoryWorkflowTests(WorkflowTestCase):
    def split(self, mother, age="Adulto"):
        return self.post(
            f"stock/fraccionar/{mother.pk}/",
            {
                "categoriaetaria": age,
                "ubicaciones": {k: self.room.pk for k in ("gr", "pl", "pq")},
            },
        )

    def test_adult_and_adolescent_fractionation(self):
        mother = self.mother()
        r = self.split(mother)
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(EjemplarBolsa.objects.count(), 3)
        self.assertTrue(
            all(b.estadobolsak == "En Cuarentena" for b in EjemplarBolsa.objects.all())
        )
        self.assertEqual(self.split(mother).status_code, 400)
        self.room.refresh_from_db()
        self.assertEqual(self.room.capacidadocupada, 3)

    def test_pediatric_has_three_75ml_aliquots(self):
        r = self.split(self.mother(), "Pediátrico")
        self.assertEqual(r.status_code, 201, r.data)
        gr = EjemplarBolsa.objects.filter(
            tipocomponente="Concentrado de Globulos Rojos"
        )
        self.assertEqual(gr.count(), 3)
        self.assertTrue(
            all(b.volumenml == 75 and b.categoriaetaria == "Pediátrico" for b in gr)
        )
        self.assertTrue(
            all(
                f"-K1P{i}-GR" in r.data["ejemplares_generados"][i - 1]
                for i in range(1, 4)
            )
        )
        self.assertEqual(EjemplarBolsa.objects.count(), 5)

    def test_capacity_rejects_entire_split(self):
        self.room.capacidadmaxima = 2
        self.room.save()
        self.assertEqual(self.split(self.mother()).status_code, 400)
        self.assertFalse(EjemplarBolsa.objects.exists())
        self.room.refresh_from_db()
        self.assertEqual(self.room.capacidadocupada, 0)

    def test_invalid_category_is_rejected(self):
        self.assertEqual(self.split(self.mother(), "Otro").status_code, 400)

    def test_expiration_is_idempotent_and_records_xor(self):
        b = self.bag(self.mother(), fechacaducidad=self.today - timedelta(days=1))
        self.room.capacidadocupada = 1
        self.room.save()
        for _ in range(2):
            r = self.client.get("/api/stock/monitor-semaforo/")
            self.assertEqual(r.status_code, 200, r.data)
        b.refresh_from_db()
        self.assertEqual(b.estadobolsak, "Baja")
        disposal = BajaInventario.objects.get()
        self.assertIsNone(disposal.idunidadmadre_id)
        self.assertEqual(disposal.idejemplarbolsa_id, b.pk)
        self.room.refresh_from_db()
        self.assertEqual(self.room.capacidadocupada, 0)

    def test_fefo_excludes_autologous_and_applies_filters(self):
        mother = self.mother()
        self.bag(mother, esexclusivoautologo=True)
        valid = self.bag(mother, codigoejemplark="VALID", categoriaetaria="Pediátrico")
        self.bag(
            mother,
            codigoejemplark="ADULT",
            fechacaducidad=self.today + timedelta(days=2),
        )
        r = self.client.get("/api/stock/monitor-semaforo/?categoriaetaria=Pediátrico")
        self.assertEqual([b["codigo"] for b in r.data["cola_fefo"]], ["VALID"])
        r = self.client.get("/api/stock/monitor-semaforo/")
        self.assertEqual([b["codigo"] for b in r.data["cola_fefo"]], ["ADULT", "VALID"])

    def test_minimum_boundary_is_green(self):
        self.bag(self.mother())
        ParametroStockMinimo.objects.create(
            idgrupo=self.group,
            tipocomponente="Concentrado de Globulos Rojos",
            stockminimoseguridad=1,
            stockcriticoalerta=0,
        )
        r = self.client.get("/api/stock/monitor-semaforo/")
        self.assertEqual(r.data["tarjetas"][0]["semaforo"], "Verde")

    def test_threshold_equal_negative_and_duplicates_rejected(self):
        data = {
            "idgrupo": self.group.pk,
            "tipocomponente": "Concentrado de Globulos Rojos",
            "categoriaetaria": "Adulto",
            "stockminimoseguridad": 5,
            "stockcriticoalerta": 5,
        }
        self.assertEqual(self.post("stock/parametros/", data).status_code, 400)
        data["stockcriticoalerta"] = -1
        self.assertEqual(self.post("stock/parametros/", data).status_code, 400)
        data["stockcriticoalerta"] = 1
        self.assertEqual(self.post("stock/parametros/", data).status_code, 201)
        self.assertEqual(self.post("stock/parametros/", data).status_code, 400)

    def serology(self, mother, reactive=False):
        values = {
            f: "No Reactivo"
            for f in [
                "resultadovih",
                "resultadochagas",
                "resultadohepatitisb",
                "resultadohepatitisc",
                "resultadosifilis",
                "resultadohtlv",
            ]
        }
        if reactive:
            values["resultadovih"] = "Reactivo"
        return self.post(f"inventario/laboratorio/serologia/{mother.pk}/", values)

    def test_serology_releases_and_promotes_exclusive_role(self):
        mother = self.mother()
        self.split(mother)
        r = self.serology(mother)
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(
            EjemplarBolsa.objects.filter(estadobolsak="Disponible").count(), 3
        )
        self.assertTrue(Donante.objects.filter(pk=self.person.pk).exists())
        self.assertEqual(
            list(self.donor_user.roles.values_list("codigorol", flat=True)), ["DONANTE"]
        )
        self.assertEqual(self.serology(mother).status_code, 400)

    def test_reactive_serology_retires_all_and_never_releases(self):
        mother = self.mother()
        self.split(mother)
        r = self.serology(mother, True)
        self.assertEqual(r.status_code, 201, r.data)
        mother.refresh_from_db()
        self.assertEqual(mother.estadoliberacion, "Rechazada")
        self.assertEqual(EjemplarBolsa.objects.filter(estadobolsak="Baja").count(), 3)
        self.assertEqual(BajaInventario.objects.count(), 3)

    def test_anonymous_and_donor_cannot_operate_laboratory(self):
        self.client.force_authenticate(self.donor_user)
        self.assertEqual(self.split(self.mother()).status_code, 403)
        self.client.force_authenticate(None)
        self.assertEqual(
            self.client.get("/api/inventario/operaciones/").status_code, 401
        )

    def test_kpi_date_end_excludes_future_activity(self):
        self.appointment()
        r = self.client.get(
            f"/api/stock/kpis-gerenciales/?fecha_inicio={self.today}&fecha_fin={self.today}"
        )
        self.assertEqual(r.status_code, 200, r.data)
        self.assertTrue(r.data["sin_actividad"])
        self.assertTrue(all(v == 0 for v in r.data["kpis"].values()))
        r = self.client.get("/api/stock/kpis-gerenciales/?fecha_inicio=bad")
        self.assertEqual(r.status_code, 400)

    def test_kpi_activity_zero_denominators_and_demand(self):
        hospital = InstitucionSalud.objects.create(
            nombreinstitucion="TEST",
            tipoinstitucion="Hospital",
            direccion="TEST",
            telefonocontacto="123",
        )
        recipient = Receptor.objects.create(
            idpersona=self.person,
            codigohistorialclinico="HC-1",
            gruposanguineoreceptor="O+",
        )
        SolicitudHospitalaria.objects.create(
            idinstitucion=hospital,
            idreceptor=recipient,
            numerosolicitud="SOL-1",
            cantidadbolsassolicitadas=3,
            fechahorarequerimiento=timezone.now(),
            prioridadsolicitud="Programada",
        )
        r = self.client.get("/api/stock/kpis-gerenciales/")
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(r.data["ranking_hospitales"][0]["bolsas_requeridas"], 3)
        self.assertEqual(r.data["kpis"]["indice_reposicion_cumplida"], 0)

    def autologous(self):
        data = {
            "idpersona": self.person.pk,
            "idgrupo": self.group.pk,
            "fechahoracita": (timezone.now() + timedelta(days=1)).isoformat(),
            "fechacirugia": (self.today + timedelta(days=5)).isoformat(),
        }
        return self.post("stock/autologa/programar/", data)

    def test_autologous_program_persists_surgery(self):
        r = self.autologous()
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(Donante.objects.get(pk=self.person.pk).tipodonante, "Autologo")
        self.assertEqual(
            CitaLaboratorio.objects.get().fechacirugiaprogramada,
            self.today + timedelta(days=5),
        )

    def test_autologous_never_available_even_after_serology(self):
        self.autologous()
        mother = self.mother()
        self.split(mother)
        self.assertEqual(self.serology(mother).status_code, 201)
        self.assertFalse(
            EjemplarBolsa.objects.filter(estadobolsak="Disponible").exists()
        )
        self.assertTrue(all(b.esexclusivoautologo for b in EjemplarBolsa.objects.all()))

    def test_autologous_custody_and_final_cancellation_xor(self):
        self.autologous()
        mother = self.mother()
        self.split(mother)
        self.serology(mother)
        r = self.post(f"stock/autologa/custodiar/{mother.pk}/", {})
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(
            ReservaSangre.objects.filter(
                esautologa=True, estadoreserva="Activa"
            ).count(),
            3,
        )
        self.assertEqual(
            self.post(
                f"stock/autologa/cancelar-cirugia/{self.person.pk}/", {}
            ).status_code,
            200,
        )
        self.assertEqual(EjemplarBolsa.objects.filter(estadobolsak="Baja").count(), 3)
        self.assertEqual(
            ReservaSangre.objects.filter(estadoreserva="Cancelada").count(), 3
        )
        self.assertTrue(
            all(
                b.idunidadmadre_id is None and b.idejemplarbolsa_id
                for b in BajaInventario.objects.all()
            )
        )
        self.assertEqual(
            self.post(
                f"stock/autologa/cancelar-cirugia/{self.person.pk}/", {}
            ).status_code,
            200,
        )
        self.assertEqual(BajaInventario.objects.count(), 3)

    def test_cancellation_before_custody_also_retires_quarantine(self):
        self.autologous()
        mother = self.mother()
        self.split(mother)
        self.post(f"stock/autologa/cancelar-cirugia/{self.person.pk}/", {})
        self.assertEqual(EjemplarBolsa.objects.filter(estadobolsak="Baja").count(), 3)
        self.assertEqual(self.serology(mother).status_code, 201)
        self.assertFalse(EjemplarBolsa.objects.exclude(estadobolsak="Baja").exists())

    def test_custody_requires_released_unit_and_actual_surgery(self):
        self.autologous()
        mother = self.mother()
        self.split(mother)
        self.assertEqual(
            self.post(f"stock/autologa/custodiar/{mother.pk}/", {}).status_code, 400
        )

    def test_components_cannot_exceed_extracted_volume(self):
        mother = self.mother()
        mother.idextraccion.volumenextraidoml = 100
        mother.idextraccion.save()
        self.assertEqual(self.split(mother).status_code, 400)
        self.assertFalse(EjemplarBolsa.objects.exists())
