#!/usr/bin/env bash
set -euo pipefail

echo "[web] starting..."
umask 0002

APP_UID="${APP_UID:-1000}"
APP_GID="${APP_GID:-1000}"
MOLECULES_DIR="${MOLECULES_DIR:-/app/files/molecules}"

# corrige proprietário e permissões do volume (idempotente)
mkdir -p "$MOLECULES_DIR"
chown -R "${APP_UID}:${APP_GID}" "$MOLECULES_DIR" || true
chmod -R ug+rwX "$MOLECULES_DIR" || true
# herança de grupo nas pastas
find "$MOLECULES_DIR" -type d -exec chmod 2775 {} + || true

# Espera Postgres se variáveis foram definidas
if [ -n "${POSTGRES_HOST:-}" ]; then
  echo "[web] waiting postgres at ${POSTGRES_HOST}:${POSTGRES_PORT:-5432}..."
  until nc -z "${POSTGRES_HOST}" "${POSTGRES_PORT:-5432}"; do sleep 1; done
fi

echo "[web] migrate"
python manage.py migrate --noinput

# opcional: coletar estáticos
# python manage.py collectstatic --noinput

echo "[web] runserver"
exec python manage.py runserver 0.0.0.0:8000
