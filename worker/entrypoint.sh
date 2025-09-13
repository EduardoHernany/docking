#!/usr/bin/env bash
set -e

echo "[worker] iniciando..."

# opcional: aguardar volume / checar GPU
if command -v nvidia-smi >/dev/null 2>&1; then
  echo "[worker] GPUs disponíveis:"
  nvidia-smi || true
else
  echo "[worker] nvidia-smi não encontrado (verifique NVIDIA Container Toolkit no host)."
fi

# garante diretório do volume
mkdir -p /app/files/molecules
ls -la /app/files/molecules || true

# aqui você pode iniciar seu orquestrador, fila, etc.
python /app/main.py
