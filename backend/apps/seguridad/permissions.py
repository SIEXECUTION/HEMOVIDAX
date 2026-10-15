"""
Permisos RBAC para el sistema HemoVida basados en UsuarioRol.
"""
from rest_framework import permissions

class IsAdminRole(permissions.BasePermission):
    """
    Permite el acceso exclusivamente a usuarios con rol de Administrador (ADMIN).
    """
    message = "Se requieren privilegios de Administrador del Sistema para realizar esta acción."

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        
        # Comprobar estado activo
        if getattr(request.user, 'estado', None) != 'Activo':
            return False

        # Comprobar rol ADMIN en la tabla UsuarioRol
        if hasattr(request.user, 'roles'):
            role = request.headers.get('X-Active-Role')
            return (not role or role == 'ADMIN') and request.user.roles.filter(codigorol='ADMIN').exists()
        return False


class IsHealthStaffRole(permissions.BasePermission):
    """
    Permite el acceso a personal de salud autorizado y administradores.
    """
    message = "Se requiere pertenecer al personal asistencial o administrativo autorizado."

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False

        if getattr(request.user, 'estado', None) != 'Activo':
            return False

        roles_salud = [
            'ADMIN',
            'DOC_TRIAJE',
            'PERS_COLECTA',
            'BIOQ_INTEGRAL',
            'TEC_LOGISTICA',
            'MED_SOLICITANTE'
        ]
        if hasattr(request.user, 'roles'):
            role = request.headers.get('X-Active-Role')
            return request.user.roles.filter(codigorol__in=[role] if role else roles_salud).exists() and (not role or role in roles_salud)
        return False


class ClinicalRole(IsHealthStaffRole):
    def has_permission(self, request, view):
        if not super().has_permission(request, view):
            return False
        roles = getattr(view, 'allowed_roles', ['ADMIN'])
        selected = request.headers.get('X-Active-Role')
        return request.user.roles.filter(codigorol__in=[selected] if selected else roles).exists() and (not selected or selected in roles)
