# Plataforma Servigpoder · Desarrollos internos

Plataforma única para los desarrollos a la medida ("desarrollos Z") que complementan SIESA. Un solo
repositorio, un solo despliegue, un portal de inicio y un núcleo común de acceso, usuarios, roles y
auditoría. Cada usuario ve en el portal solo las apps para las que tiene permisos.

**Apps actuales**

| App | Ruta | Descripción |
|---|---|---|
| Capacidad Operativa | `/capacidad` | Compara lo **vendido** (matriz comercial) contra lo **programado** (Excel de SIESA): huecos de cobertura, sobreprogramación, cubrimientos, bolsas y alertas |

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
backend/
  app/core/            núcleo: configuración, seguridad, sesión, middlewares, auditoría, contrato App
  app/models/          modelos del núcleo (usuarios, roles, permisos, auditoría)
  app/api/routes/      rutas del núcleo: /api/auth, /api/usuarios, /api/roles, /api/plataforma
  app/apps/__init__.py registro de apps (APPS)
  app/apps/capacidad/  app Capacidad Operativa: manifest.py, models/, routes/, services/, schemas/
  alembic/versions/    migraciones (una sola historia para toda la plataforma)
  tests/
frontend/src/app/
  login/                     ingreso en dos pasos
  (plataforma)/page.tsx      portal de aplicaciones
  (plataforma)/admin/        usuarios, roles, auditoría
  (plataforma)/cuenta/       seguridad de mi cuenta
  (plataforma)/capacidad/    app Capacidad Operativa (menú lateral propio)
```

## Agregar un desarrollo nuevo

1. **Backend**: crear `backend/app/apps/<codigo>/` con `manifest.py`:
   `APP = App(codigo="<codigo>", nombre=..., descripcion=..., icono=..., color=..., permisos={"<codigo>.x.ver": (...)}, roles_base=..., router=..., seed=...)`.
   Los permisos **deben** empezar por `<codigo>.`; las rutas quedan bajo `/api/<codigo>`.
   Nombrar las tablas con el prefijo de la app para evitar choques.
2. Registrar la app en `backend/app/apps/__init__.py` (`APPS`) e importar sus modelos en `alembic/env.py`.
3. `alembic revision --autogenerate -m "<codigo>: tablas iniciales"` y revisar la migración.
4. **Frontend**: crear `frontend/src/app/(plataforma)/<codigo>/` con su `layout.tsx` y páginas; agregar su ícono
   en `ICONOS` del portal (`(plataforma)/page.tsx`).
5. Asignar sus permisos a roles desde Administración → Roles y permisos: la app aparece en el portal
   de quienes tengan al menos un permiso de ella.

El navegador solo habla con el frontend; Next.js reenvía `/api/*` al backend, por lo que la cookie
de sesión funciona sin configurar CORS. El backend no se publica hacia afuera.

## Ejecutar con Docker (igual que en producción)

```bash
cp .env.example .env      # y cambiar las claves
docker compose up -d --build
```

Abrir http://localhost:3000 e ingresar con `ADMIN_USERNAME` / `ADMIN_PASSWORD` del `.env`; en el primer
ingreso se configura la verificación en dos pasos con la app Authenticator.
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

## Cubrimientos y bolsas (F3)

`backend/app/services/cubrimientos.py`: un cubrimiento es un turno de una persona en un puesto donde
no es titular. Se justifica solo si un titular del puesto tiene una **novedad** que requiere
cubrimiento o está de **descanso** ese día, y el turno no se cruza con horas en exceso. Lo demás queda
**pendiente** para nómina. Las decisiones de nómina se guardan por (mes, cédula, puesto, día) y se
conservan al recalcular. El reporte de **personas en bolsa** lista quienes tienen turnos en 05/06 los
días en que no cubren ningún puesto.

## Histórico y alertas (F4)

Cada carga de SIESA queda guardada con su análisis. Se puede comparar una carga con la anterior del
mismo mes (turnos agregados, eliminados o cambiados y su impacto en la cobertura). Las alertas de
Inicio se evalúan con los umbrales de Administración → Parámetros de alertas.

## Asistente de IA (F6)

`backend/app/services/asistente.py`: agente con el Tool Runner del SDK de Anthropic. Claude recibe la
metodología en sus instrucciones y consulta los datos con **herramientas de solo lectura** (resumen de
cobertura, lista y detalle de puestos, cubrimientos, comparación de cargas, alertas, estado de datos)
que verifican los permisos del usuario que pregunta. Requiere `ANTHROPIC_API_KEY` (cuenta de API en
console.anthropic.com, facturación por uso). Controles: permiso `asistente.usar`, rate limit, tope diario
por usuario, auditoría de cada pregunta (pregunta recortada, herramientas y tokens) y conversación
guardada solo en la pestaña del navegador. `ASISTENTE_DATOS_PERSONALES=false` reemplaza nombres y
cédulas por seudónimos.

## Respaldos

La base vive en el volumen `pgdata`. En Coolify, programe una tarea (Scheduled Task) sobre el servicio
`db`, por ejemplo diaria:

```bash
pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc -f /var/lib/postgresql/data/respaldo_$(date +%F).dump
```

y copie los respaldos fuera del servidor. Restaurar:

```bash
docker compose exec -T db pg_restore -U capacidad -d capacidad --clean < respaldo.dump
```

## Validación QA

Lista completa de pruebas funcionales y de seguridad, con valores esperados: [`docs/QA.md`](docs/QA.md).

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

## Autenticación

Usuario y contraseña **más verificación en dos pasos obligatoria** (TOTP con Microsoft/Google Authenticator):

1. Usuario y contraseña → cookie temporal de pre-autenticación (5 min, solo para `/api/auth`). Nunca da acceso a la API.
2. Código de 6 dígitos de la app (o un **código de recuperación** de un solo uso) → sesión.
   En el primer ingreso el usuario escanea un QR y recibe 10 códigos de recuperación.
3. Si la contraseña la asignó un administrador (temporal), la sesión solo permite cambiarla.

Controles: bloqueo tras 5 contraseñas o códigos incorrectos (15 min), códigos TOTP no reutilizables,
secreto TOTP cifrado en la base (Fernet), códigos de recuperación guardados como hash, sesión que vence
tras **30 min de inactividad** y a las **12 h** en cualquier caso, cierre de las demás sesiones al cambiar
la contraseña, y auditoría de cada ingreso (con el método de MFA usado). Si alguien pierde el celular y
sus códigos, un administrador puede **restablecer su MFA** desde Administración → Usuarios.

## Permisos

Los permisos del núcleo están en `backend/app/core/permisos.py` y los de cada app en su `manifest.py`
(con prefijo, p. ej. `capacidad.analisis.ver`). Los **roles** y los **usuarios** se administran desde
Administración. Roles base: Administrador (todo), Programador y Nómina (Capacidad Operativa).

## Fases

- [x] F0 Base: acceso, usuarios, roles dinámicos, Docker
- [x] F1 Maestros, matriz comercial (con proyección mensual) y carga de programación SIESA
- [x] F2 Motor de cobertura, tablero y vista de puesto
- [x] F3 Cubrimientos, bandeja de nómina y bolsas
- [x] F4 Histórico, comparación de cargas, alertas y parámetros
- [ ] F5 Puesta en producción en Coolify (ver guía QA en `docs/QA.md`)
- [x] F6 Asistente de IA (Claude) que explica de dónde salen los datos
- [x] Plataforma multi-app (portal) y autenticación con MFA obligatoria
