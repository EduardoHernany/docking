#!/usr/bin/env bash
set -e

# Espera o Postgres (depende do healthcheck, mas extra aqui é ok)
if [ -n "${POSTGRES_HOST}" ]; then
  echo "Aguardando Postgres em ${POSTGRES_HOST}:${POSTGRES_PORT:-5432}..."
  while ! nc -z ${POSTGRES_HOST} ${POSTGRES_PORT:-5432}; do
    sleep 1
  done
fi

echo "Aplicando migrations..."
python manage.py migrate --noinput

# opcional: coletar estáticos (se usar)
# python manage.py collectstatic --noinput

echo "Iniciando Django (runserver)..."
python manage.py runserver 0.0.0.0:8000
