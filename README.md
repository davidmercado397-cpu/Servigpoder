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
2. Configurar las variables de `.env.example` (claves nuevas, `COOKIE_SECURE=true` si hay HTTPS).
3. Asignar el dominio al servicio **frontend** (puerto 3000). No exponer `backend` ni `db`.
4. El volumen `pgdata` guarda la base de datos; configurar respaldos en Coolify.

## Seguridad y permisos

Los **permisos** están definidos en `backend/app/core/permisos.py`. Los **roles** y los **usuarios** se
administran desde la aplicación (Administración → Roles y permisos / Usuarios). Roles base:
Administrador, Programador y Nómina.

## Fases

- [x] F0 Base: acceso, usuarios, roles dinámicos, Docker
- [ ] F1 Maestros, matriz comercial (con proyección mensual) y carga de programación SIESA
- [ ] F2 Motor de cobertura, tablero y vista de puesto
- [ ] F3 Cubrimientos, bandeja de nómina y bolsas
- [ ] F4 Histórico, comparación de cargas y alertas
