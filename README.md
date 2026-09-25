# Capacidad Operativa · Servigpoder

Control de la capacidad operativa de la programación de personal que se exporta de SIESA Cloud.
Compara lo **vendido** (matriz comercial) contra lo **programado** (Excel de SIESA) para detectar
huecos de cobertura, sobreprogramación, cubrimientos sin justificar y personal en bolsas.

## Stack

| Capa | Tecnología |
|---|---|
| Frontend | Next.js 15 (App Router, TypeScript, Tailwind) |
| Backend | Python 3.12 + FastAPI + SQLAlchemy 2 + Alembic |
| Análisis | Polars |
| Base de datos | PostgreSQL 16 |
| Despliegue | Docker Compose (Coolify) |

## Estructura

```
backend/    API FastAPI, modelos, migraciones (alembic/), pruebas (tests/)
frontend/   Aplicación Next.js (src/app)
docker-compose.yml
.env.example
```

El navegador solo habla con el frontend; Next.js reenvía `/api/*` al backend, por lo que la cookie
de sesión funciona sin configurar CORS. El backend no se publica hacia afuera.

## Ejecutar con Docker (igual que en producción)

```bash
cp .env.example .env      # y cambiar las claves
docker compose up -d --build
```

Abrir http://localhost:3000 e ingresar con `ADMIN_USERNAME` / `ADMIN_PASSWORD` del `.env`.
El administrador inicial solo se crea si la base de datos no tiene usuarios.

Al arrancar, el backend aplica las migraciones (`alembic upgrade head`) y sincroniza permisos y roles base.

## Desarrollo local

Backend (requiere PostgreSQL; se puede usar el de Docker exponiendo el puerto 5432):

```bash
cd backend
python -m venv .venv
.venv/Scripts/pip install -r requirements-dev.txt
.venv/Scripts/python -m pytest
.venv/Scripts/uvicorn app.main:app --reload
```

Frontend:

```bash
cd frontend
npm install
npm run dev
```

Documentación de la API: http://localhost:8000/api/docs

## Despliegue en Coolify

1. Nuevo recurso → **Docker Compose** → repositorio de GitHub, rama `main`.
2. Configurar las variables de `.env.example` (claves nuevas, `ENVIRONMENT=production`, `COOKIE_SECURE=true` con HTTPS).
3. Asignar el dominio al servicio **frontend** (puerto 3000). No exponer `backend` ni `db`.
4. El volumen `pgdata` guarda la base de datos; configurar respaldos en Coolify.

## Motor de cobertura (F2)

`backend/app/services/cobertura.py` cruza la matriz comercial del mes con la última carga de SIESA.
Cada puesto se evalúa en bloques de 30 minutos comparando personas vendidas contra personas
programadas trabajando: el faltante son **horas descubiertas** y el sobrante **horas en exceso**.
Los turnos que cruzan la medianoche se atribuyen al día en que empiezan. Las novedades (VAC, IEG,
IND, PSA…) no cuentan como cobertura. El **titular** de una persona es el puesto donde más turnos
tiene en el mes; los titulares de cada puesto se comparan con los hombres presupuestados.

El análisis se calcula al subir la programación (si existe la matriz del mes) o con "Recalcular",
y se marca como desactualizado si la matriz cambia o llega una carga más reciente.

## Formato de respuesta de la API

Todas las respuestas JSON usan el mismo sobre (`backend/app/core/respuestas.py`):

```json
{ "success": true,  "data": { },  "error": null,
  "meta": { "api_version": "v1", "request_id": "…", "timestamp": "…", "extra": { "total": 10 } } }

{ "success": false, "data": null,
  "error": { "code": "SIN_PERMISO", "message": "No tiene permiso…", "details": [] },
  "meta": { "api_version": "v1", "request_id": "…", "timestamp": "…" } }
```

`request_id` también viaja en la cabecera `X-Request-ID` y en los logs, para rastrear un error reportado.

## Base de datos y migraciones

El esquema se versiona con **Alembic** (`backend/alembic/versions`). Al arrancar, el contenedor ejecuta
`alembic upgrade head`. Para un cambio de modelo:

```bash
cd backend
.venv/Scripts/alembic revision --autogenerate -m "descripcion del cambio"
.venv/Scripts/alembic upgrade head
.venv/Scripts/alembic check   # confirma que modelos y migraciones coinciden
```

## Seguridad (OWASP)

| Riesgo OWASP Top 10 | Medida |
|---|---|
| A01 Control de acceso | Denegar por defecto; cada endpoint exige un permiso; roles dinámicos; sesiones revocadas al cambiar contraseña, roles o estado |
| A02 Fallas criptográficas | bcrypt (12 rondas); JWT HS256 con `SECRET_KEY` ≥ 32 caracteres obligatoria en producción; cookie `HttpOnly`, `SameSite=Strict`, `Secure` con HTTPS; HSTS |
| A03 Inyección | ORM con consultas parametrizadas; validación estricta de entradas con Pydantic; Excel procesado con `defusedxml` |
| A04 Diseño inseguro | Rate limit en endpoints críticos; bloqueo temporal por intentos fallidos; límites de tamaño |
| A05 Configuración | Cabeceras de seguridad (CSP, X-Frame-Options, nosniff, Referrer/Permissions-Policy); `/api/docs` deshabilitado en producción; errores sin trazas internas; `TrustedHost` |
| A07 Autenticación | Política de contraseñas (10+ caracteres, letras y números); mensaje genérico de login; tiempo constante exista o no el usuario |
| A08 Integridad | Validación de archivos subidos: extensión, firma ZIP, estructura de libro Excel y tamaño descomprimido |
| A09 Registro y monitoreo | Bitácora `auditoria` (login, cambios de usuarios, roles, matriz y cargas) con IP y `request_id`; log de acceso por petición |
| CSRF | Cabecera obligatoria `X-Requested-With` en peticiones que modifican datos + cookie `SameSite=Strict` |

**Middlewares** (`backend/app/core/middleware.py`): RequestId → SecurityHeaders → TrustedHost →
RateLimitGlobal → CsrfHeader → BodySizeLimit.

**Rate limit** (por IP): global 300/min; login 10/min y 50/hora; importaciones 10/min; escritura de
usuarios y roles 30/min; matriz 60/min; proyección 5/min. Bloqueo de un usuario tras 5 intentos
fallidos durante 15 minutos. El almacenamiento es en memoria (un contenedor); si se escala a varias
réplicas debe pasarse a Redis.

**IP del cliente**: el backend solo confía en `X-Forwarded-For` de proxies de la red interna
(`FORWARDED_ALLOW_IPS`), así un cliente no puede falsificar su IP.

## Permisos

Los **permisos** están definidos en `backend/app/core/permisos.py`. Los **roles** y los **usuarios** se
administran desde la aplicación (Administración → Roles y permisos / Usuarios). Roles base:
Administrador, Programador y Nómina.

## Fases

- [x] F0 Base: acceso, usuarios, roles dinámicos, Docker
- [x] F1 Maestros, matriz comercial (con proyección mensual) y carga de programación SIESA
- [x] F2 Motor de cobertura, tablero y vista de puesto
- [ ] F3 Cubrimientos, bandeja de nómina y bolsas
- [ ] F4 Histórico, comparación de cargas y alertas
