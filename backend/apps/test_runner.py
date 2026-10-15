"""
Custom Test Runner que habilita managed=True temporalmente durante las pruebas
para que Django cree las tablas en la base de datos de pruebas en memoria.
"""
from django.test.runner import DiscoverRunner

class UnmanagedModelTestRunner(DiscoverRunner):
    def setup_databases(self, **kwargs):
        from apps.seguridad.models import (
            Rol, Usuario, UsuarioRol, PersonalSalud, BitacoraAuditoria
        )
        from apps.donantes.models import (
            Persona, PosibleDonador, Donante, Receptor, RequisitoDonacion,
            CitaDonacion, DetalleCitaRequisito, TriajeClinico, Diferimiento,
            ExtraccionDonacion, ConsentimientoInformado, IncentivoEntrega,
            AnalisisInmunoSerologico, AnalisisInmunoHematologico,
            CitaLaboratorio, CompromisoDonacion
        )
        from apps.inventario.models import (
            GrupoSanguineo, UbicacionAlmacen, ParametroStockMinimo,
            UnidadSangreTotal, EjemplarBolsa, InstitucionSalud,
            SolicitudHospitalaria, DetalleSolicitud, PruebaCompatibilidad,
            ReservaSangre, BajaInventario, ComprobanteDespacho,
            DetalleDespacho, ReposicionPendiente, ComprobantePago
        )

        unmanaged_models = [
            Rol, Usuario, UsuarioRol, PersonalSalud, BitacoraAuditoria,
            Persona, PosibleDonador, Donante, Receptor, RequisitoDonacion,
            CitaDonacion, DetalleCitaRequisito, TriajeClinico, Diferimiento,
            ExtraccionDonacion, ConsentimientoInformado, IncentivoEntrega,
            AnalisisInmunoSerologico, AnalisisInmunoHematologico,
            CitaLaboratorio, CompromisoDonacion,
            GrupoSanguineo, UbicacionAlmacen, ParametroStockMinimo,
            UnidadSangreTotal, EjemplarBolsa, InstitucionSalud,
            SolicitudHospitalaria, DetalleSolicitud, PruebaCompatibilidad,
            ReservaSangre, BajaInventario, ComprobanteDespacho,
            DetalleDespacho, ReposicionPendiente, ComprobantePago
        ]

        for model in unmanaged_models:
            model._meta.managed = True

        return super().setup_databases(**kwargs)

