"""
URL configuration for hemovida_project.
Rutas centrales de la API REST de HemoVida.
"""
from django.contrib import admin
from django.urls import path, include
from django.http import JsonResponse
from django.utils import timezone

def health_check(request):
    return JsonResponse({
        "status": "ok",
        "service": "HemoVida API Backend",
        "timestamp": timezone.now().isoformat()
    })

urlpatterns = [
    # Health Check raíz para Render (evita 404 en HEAD /)
    path('', health_check, name='root_health_check'),
    
    # Health Check para Render Keep-Alive / Uptime Monitors
    path('health/', health_check, name='health_check'),
    path('api/health/', health_check, name='api_health_check'),

    path('admin/', admin.site.urls),
    
    # Seguridad, Autenticación, Usuarios, Personal y Auditoría
    path('api/', include('apps.seguridad.urls')),
    
    # Parámetros de Stock, Semáforo FEFO y Fraccionamiento
    path('api/stock/', include('apps.inventario.urls')),
    path('api/inventario/', include('apps.inventario.urls')),
    path('api/', include('apps.inventario.urls')),
    
    # Carnet Digital y Donantes
    path('api/donantes/', include('apps.donantes.urls')),
]

