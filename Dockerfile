# Dockerfile (web)
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential curl netcat-traditional \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Dependências primeiro (melhor cache)
COPY requirements.txt /app/requirements.txt
RUN pip install -r /app/requirements.txt

# Copia projeto (será sobrescrito pelo bind-mount em dev)
COPY . /app

# Garante diretório de uploads no novo path
RUN mkdir -p /app/files/molecules

# Entrypoint (migrações + runserver)
COPY entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

EXPOSE 8000
CMD ["bash", "/app/entrypoint.sh"]
