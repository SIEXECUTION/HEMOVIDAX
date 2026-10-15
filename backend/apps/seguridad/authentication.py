"""
Autenticación JWT personalizada para el modelo Usuario de HemoVida.
"""
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import InvalidToken, AuthenticationFailed
from .models import Usuario

class CustomJWTAuthentication(JWTAuthentication):
    """
    Autenticador JWT que recupera la entidad Usuario de HemoVida
    a partir del claim 'user_id' contenido en el token de acceso.
    """
    def get_user(self, validated_token):
        user_id = validated_token.get('user_id')
        if not user_id:
            raise InvalidToken('El token JWT no contiene un identificador de usuario válido.')
        
        try:
            usuario = Usuario.objects.select_related('idpersona').prefetch_related('roles').get(idusuario=user_id)
        except Usuario.DoesNotExist:
            raise AuthenticationFailed('El usuario referenciado en el token no existe.')

        if usuario.estado != 'Activo':
            raise AuthenticationFailed('La cuenta del usuario se encuentra inactiva o bloqueada.')

        return usuario

    def authenticate(self, request):
        result = super().authenticate(request)
        if result:
            usuario, _ = result
            role = request.headers.get('X-Active-Role')
            if role and not usuario.roles.filter(codigorol=role).exists():
                raise AuthenticationFailed('El perfil seleccionado no está asignado a esta cuenta.')
        return result
