# worker/Dockerfile
FROM nvidia/cuda:12.2.0-devel-ubuntu22.04 as base

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    GPU_INCLUDE_PATH=/usr/local/cuda/include \
    GPU_LIBRARY_PATH=/usr/local/cuda/lib64

# Dependências de sistema
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 python3-pip python3-venv \
    build-essential \
    netcat-openbsd \
    git wget curl \
    openbabel \
    zip unzip \
    nano tree \
 && rm -rf /var/lib/apt/lists/*

# Alias
RUN ln -sf /usr/bin/python3 /usr/bin/python && ln -sf /usr/bin/pip3 /usr/bin/pip

# -------- AutoDock-GPU --------
WORKDIR /home/autodockgpu
RUN wget -q https://github.com/ccsb-scripps/AutoDock-GPU/archive/refs/heads/develop.zip \
 && unzip -q develop.zip \
 && mv AutoDock-GPU-develop AutoDock-GPU \
 && cd AutoDock-GPU && make DEVICE=CUDA NUMWI=128 \
 && rm -f /home/autodockgpu/develop.zip
ENV PATH="/home/autodockgpu/AutoDock-GPU/bin:${PATH}"

# -------- MGLTools --------
RUN wget -q https://ccsb.scripps.edu/mgltools/download/491/ -O mgltools_x86_64Linux2_1.5.7.tar.gz \
 && tar -xzf mgltools_x86_64Linux2_1.5.7.tar.gz \
 && cd mgltools_x86_64Linux2_1.5.7 && ./install.sh \
 && rm -f /home/autodockgpu/mgltools_x86_64Linux2_1.5.7.tar.gz
ENV PATH="/home/autodockgpu/mgltools_x86_64Linux2_1.5.7/bin:${PATH}"
ENV LD_LIBRARY_PATH="/home/autodockgpu/mgltools_x86_64Linux2_1.5.7/lib:${LD_LIBRARY_PATH}"

# -------- AutoDock Suite --------
RUN wget -q https://autodock.scripps.edu/wp-content/uploads/sites/56/2021/10/autodocksuite-4.2.6-x86_64Linux2.tar \
 && tar -xf autodocksuite-4.2.6-x86_64Linux2.tar \
 && rm -f /home/autodockgpu/autodocksuite-4.2.6-x86_64Linux2.tar
ENV PATH="/home/autodockgpu/autodocksuite-4.2.6:${PATH}"

# -------- App Python (worker) --------
WORKDIR /app

# 1) libs do projeto Django (web)
COPY worker/AD4_parameters.dat /home/autodockgpu/x86_64Linux2/AD4_parameters.dat
COPY requirements.txt /app/web-requirements.txt
RUN pip install --no-cache-dir -r /app/web-requirements.txt

# 2) libs do worker (Celery, etc.)
COPY worker/requirements.txt /app/worker-requirements.txt
RUN pip install --no-cache-dir -r /app/worker-requirements.txt

# 3) (opcional) fallback do entrypoint do worker
COPY worker/entrypoint.sh /app/worker-entrypoint.sh
RUN chmod +x /app/worker-entrypoint.sh

# Garante diretório (será montado por volume)
RUN mkdir -p /app/files/molecules

# Não definimos CMD aqui; o compose chamará "bash worker/entrypoint.sh"
