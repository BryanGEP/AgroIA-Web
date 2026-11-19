"""Autenticación JWT (RS256) para los servicios Django.

Cada servicio valida la firma del token con la llave pública, sin consultar
svc-usuarios, y lee `user_id` (UUID en texto), `rol` y `email_verificado` de los claims.
El contrato completo está en docs/contrato-identidad.md.

Uso en config/settings.py (las funciones están en configuracion.py):

    validar_modo_auth(AUTH_ACTIVA, DEBUG)
    SIMPLE_JWT = configurar_jwt(
        leer_llave_publica(JWT_PUBLIC_KEY_PATH, AUTH_ACTIVA), issuer=JWT_ISSUER
    )
    REST_FRAMEWORK = {
        "DEFAULT_AUTHENTICATION_CLASSES": ["agroia_comun.autenticacion.AutenticacionJWT"],
        "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
        ...
    }

AUTH_ACTIVA (True por defecto) solo controla las revisiones de rol de permisos.py: un
token que llega siempre se valida, y los endpoints que necesitan saber quién es el
usuario responden 401 sin token aunque AUTH_ACTIVA sea False.
"""

import uuid

from rest_framework_simplejwt.authentication import JWTStatelessUserAuthentication
from rest_framework_simplejwt.exceptions import InvalidToken
from rest_framework_simplejwt.settings import api_settings


class AutenticacionJWT(JWTStatelessUserAuthentication):
    """Valida firma, vencimiento, emisor y tipo de token, sin buscar al usuario en la base.

    `request.user` es un `TokenUser`: `request.user.id` y `request.user.token["rol"]`.
    Usa los helpers de permisos.py (`usuario_id`, `rol_de`) en lugar de leer el token a mano.
    Un `user_id` que no sea UUID (por ejemplo, un token de antes de la Entrega 3) da 401.
    """

    def get_user(self, validated_token):
        usuario = super().get_user(validated_token)
        try:
            uuid.UUID(str(validated_token[api_settings.USER_ID_CLAIM]))
        except (KeyError, ValueError) as error:
            raise InvalidToken("El token no trae un user_id válido.") from error
        return usuario


try:
    from drf_spectacular.extensions import OpenApiAuthenticationExtension
except ImportError:  # el servicio no usa drf-spectacular
    pass
else:

    class EsquemaAutenticacionJWT(OpenApiAuthenticationExtension):
        """Esquema Bearer en Swagger (/api/docs/) para probar con un token."""

        target_class = "agroia_comun.autenticacion.AutenticacionJWT"
        name = "jwtAuth"

        def get_security_definition(self, auto_schema):
            return {
                "type": "http",
                "scheme": "bearer",
                "bearerFormat": "JWT",
                "description": (
                    "Token de acceso RS256: inicia sesión con POST /api/v1/auth/login/ "
                    "de svc-usuarios y pega aquí el `access`."
                ),
            }
