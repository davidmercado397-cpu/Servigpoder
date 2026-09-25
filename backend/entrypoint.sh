#!/bin/sh
set -e
alembic upgrade head
python -m app.seed
# Solo se confía en X-Forwarded-For cuando viene de proxies de la red interna (Traefik de
# Coolify y el frontend Next.js). Se toma la IP más a la derecha que no sea de un proxy
# confiable, así un cliente no puede falsificar su IP para evadir el rate limit.
exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers \
  --forwarded-allow-ips="${FORWARDED_ALLOW_IPS:-127.0.0.1,10.0.0.0/8,172.16.0.0/12,192.168.0.0/16}"
