"""
Rutas URL para la app Donantes.
"""
from django.urls import path
from .views import (
    DonanteCarnetDigitalView, CarnetDigitalQRView,
    AgendarCitaDonacionView, ProcesarTriajeClinicoView, RegistrarFlebotomiaFraccionamientoView
)

urlpatterns = [
    # Consultar Carnet Digital e Historial Biológico del Donante
    path('<str:ci>/carnet/', DonanteCarnetDigitalView.as_view(), name='donante_carnet_digital'),
    path('carnet-digital/<int:idpersona>/', CarnetDigitalQRView.as_view(), name='carnet_digital_qr'),
    path('<int:idpersona>/carnet-digital/', CarnetDigitalQRView.as_view(), name='carnet_digital_qr_alt'),

    # Orquestación Atómica DRF (sin procedimientos almacenados)
    path('citas/', AgendarCitaDonacionView.as_view(), name='agendar_cita_donacion'),
    path('triaje/', ProcesarTriajeClinicoView.as_view(), name='procesar_triaje_clinico'),
    path('flebotomia/', RegistrarFlebotomiaFraccionamientoView.as_view(), name='registrar_flebotomia_fraccionamiento'),
]


