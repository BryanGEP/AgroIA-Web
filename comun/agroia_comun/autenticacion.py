"""Autenticación JWT (RS256) para los servicios Django.

Se implementa en la fase 4: valida la firma con la llave pública y lee `user_id`,
`rol` y `email_verificado` del token, sin consultar svc-usuarios. Se activa con la
variable AUTH_ACTIVA.
"""
