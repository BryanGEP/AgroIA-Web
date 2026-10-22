"""Autenticación JWT (RS256) para los servicios Django.

Cada servicio valida la firma del token con la llave pública, sin consultar
svc-usuarios, y lee `user_id`, `rol` y `email_verificado` de los claims.

Uso en config/settings.py (las funciones están en configuracion.py):

    validar_modo_auth(AUTH_ACTIVA, DEBUG)
    SIMPLE_JWT = configurar_jwt(leer_llave_publica(JWT_PUBLIC_KEY_PATH, AUTH_ACTIVA))
    REST_FRAMEWORK = {
        "DEFAULT_AUTHENTICATION_CLASSES": ["agroia_comun.autenticacion.AutenticacionJWT"],
        "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
        ...
    }

AUTH_ACTIVA (True por defecto) solo controla las revisiones de rol de permisos.py: un
token que llega siempre se valida, y los endpoints que necesitan saber quién es el
usuario responden 401 sin token aunque AUTH_ACTIVA sea False.
"""

from rest_framework_simplejwt.authentication import JWTStatelessUserAuthentication


class AutenticacionJWT(JWTStatelessUserAuthentication):
    """Valida firma, vencimiento, emisor y tipo de token, sin buscar al usuario en la base.

    `request.user` es un `TokenUser`: `request.user.id` y `request.user.token["rol"]`.
    Usa los helpers de permisos.py (`usuario_id`, `rol_de`) en lugar de leer el token a mano.
    """


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
                    "Token de acceso RS256 emitido por svc-usuarios. En desarrollo: "
                    "`python infra/emitir_token.py --usuario-id 10 --rol cliente`."
                ),
            }
