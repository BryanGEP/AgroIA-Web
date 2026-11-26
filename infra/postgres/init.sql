-- Crea una base y un usuario por servicio: cada servicio solo puede entrar a la suya.
--
-- Solo corre la PRIMERA vez que se crea el volumen de PostgreSQL. Para volver a
-- ejecutarlo hay que borrar el volumen con `docker compose down -v` (borra los datos).
--
-- Las contraseñas no están en este archivo: psql las lee del entorno del contenedor
-- con \getenv (docker-compose.yml se las pasa desde el .env).
-- CREATEDB permite que pytest-django cree la base temporal de pruebas (test_<base>).

\set ON_ERROR_STOP on

\getenv usuarios_password USUARIOS_DB_PASSWORD
\getenv tienda_password TIENDA_DB_PASSWORD
\getenv web_password WEB_DB_PASSWORD

-- svc-usuarios
CREATE ROLE usuarios LOGIN CREATEDB PASSWORD :'usuarios_password';
CREATE DATABASE usuarios_db OWNER usuarios;
REVOKE ALL ON DATABASE usuarios_db FROM PUBLIC;

-- svc-tienda
CREATE ROLE tienda LOGIN CREATEDB PASSWORD :'tienda_password';
CREATE DATABASE tienda_db OWNER tienda;
REVOKE ALL ON DATABASE tienda_db FROM PUBLIC;

-- web (sesiones del gateway)
CREATE ROLE web LOGIN CREATEDB PASSWORD :'web_password';
CREATE DATABASE web_db OWNER web;
REVOKE ALL ON DATABASE web_db FROM PUBLIC;
