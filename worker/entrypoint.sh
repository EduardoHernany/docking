#!/usr/bin/env bash
set -euo pipefail

echo "[worker] starting..."
umask 0002

APP_UID="${APP_UID:-1000}"
APP_GID="${APP_GID:-1000}"
MOLECULES_DIR="${MOLECULES_DIR:-/app/files/molecules}"

# corrige proprietário e permissões do volume (idempotente)
mkdir -p "$MOLECULES_DIR"
chown -R "${APP_UID}:${APP_GID}" "$MOLECULES_DIR" || true
chmod -R ug+rwX "$MOLECULES_DIR" || true
find "$MOLECULES_DIR" -type d -exec chmod 2775 {} + || true
ls -la "$MOLECULES_DIR" || true

# GPU (opcional)
if command -v nvidia-smi >/dev/null 2>&1; then
  echo "[worker] GPUs:"
  nvidia-smi || true
fi

# Espera RabbitMQ
RABBITMQ_HOST="${RABBITMQ_HOST:-rabbitmq}"
RABBITMQ_PORT="${RABBITMQ_PORT:-5672}"
echo "[worker] waiting rabbitmq at ${RABBITMQ_HOST}:${RABBITMQ_PORT}..."
until nc -z "$RABBITMQ_HOST" "$RABBITMQ_PORT"; do sleep 1; done

# Parâmetros Celery
CELERY_APP="${CELERY_APP:-djangoAPI}"
CELERY_QUEUE="${CELERY_QUEUE:-default}"
CELERY_CONCURRENCY="${CELERY_CONCURRENCY:-1}"
CELERY_LOGLEVEL="${CELERY_LOGLEVEL:-info}"

echo "[worker] starting celery worker"
exec celery -A "${CELERY_APP}" worker \
  -l "${CELERY_LOGLEVEL}" \
  -Q "${CELERY_QUEUE}" \
  -n "worker@%h" \
  --concurrency="${CELERY_CONCURRENCY}"
