"""
Rutas URL para la app Inventario.
"""
from django.urls import path
from .views import (
    CatalogosView, OperacionesView, HematologiaView, SerologiaView,
    ParametroStockMinimoListView,
    ParametroStockMinimoUpdateView,
    StockAlertasListView,
    FraccionarUnidadMadreView,
    MonitorStockSemaforoView,
    ProgramarDonacionAutologaView,
    CustodiarFraccionamientoAutologoView,
    CancelarCirugiaAutologaView,
    TableroControlKPIsView,
)

urlpatterns = [
    path('catalogos/', CatalogosView.as_view()),
    path('operaciones/', OperacionesView.as_view()),
    path('laboratorio/hematologia/', HematologiaView.as_view()),
    path('laboratorio/serologia/<int:pk>/', SerologiaView.as_view()),
    # Parametrizar Umbrales de Stock Mínimo y Alertas Críticas
    path('parametros/', ParametroStockMinimoListView.as_view(), name='stock_parametros_list'),
    path('parametros/<int:pk>/', ParametroStockMinimoUpdateView.as_view(), name='stock_parametros_update'),
    path('alertas/', StockAlertasListView.as_view(), name='stock_alertas_list'),

    # Semáforo de Stock de Hemocomponentes y Cola Prioritaria FEFO
    path('monitor-semaforo/', MonitorStockSemaforoView.as_view(), name='monitor_stock_semaforo'),
    path('monitor-stock-fefo/', MonitorStockSemaforoView.as_view(), name='monitor_stock_fefo'),
    path('semaforo/', MonitorStockSemaforoView.as_view(), name='stock_semaforo'),

    # Fraccionamiento de Bolsa Madre según Esquema Etario
    path('fraccionar/<int:idunidadmadre>/', FraccionarUnidadMadreView.as_view(), name='fraccionar_unidad_madre'),
    path('bolsas/fraccionar/<int:idunidadmadre>/', FraccionarUnidadMadreView.as_view(), name='fraccionar_bolsa'),

    # Gestión de Donación Autóloga Programada y Reserva Exclusiva
    path('autologa/programar/', ProgramarDonacionAutologaView.as_view(), name='programar_donacion_autologa'),
    path('autologa/custodiar/<int:idunidadmadre>/', CustodiarFraccionamientoAutologoView.as_view(), name='custodiar_fraccionamiento_autologo'),
    path('autologa/cancelar-cirugia/<int:idpersona_paciente>/', CancelarCirugiaAutologaView.as_view(), name='cancelar_cirugia_autologa'),

    # Generar Tableros de Control, KPIs e Informes de Gestión
    path('kpis-gerenciales/', TableroControlKPIsView.as_view(), name='tablero_kpis_gerenciales'),
]

