# Dockerfile
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# deps do sistema (opcional; útil p/ compilação de libs no futuro)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential curl netcat-traditional \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Instala dependências primeiro (melhor cache)
COPY requirements.txt /app/requirements.txt
RUN pip install -r requirements.txt

# Copia o projeto
COPY . /app

# Garante diretório de uploads
RUN mkdir -p /app/molecules

# Entrypoint (migrações + runserver)
COPY entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

EXPOSE 8000
CMD ["/app/entrypoint.sh"]
