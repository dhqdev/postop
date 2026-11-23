# syntax=docker/dockerfile:1.7
FROM denoland/deno:bin AS deno

FROM python:3.12-slim-bookworm

ARG APP_VERSION=dev
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    APP_VERSION=${APP_VERSION} \
    DATA_DIR=/data \
    HF_HOME=/data/models/hf \
    TZ=America/Sao_Paulo

RUN apt-get update \
 && apt-get install -y --no-install-recommends ffmpeg fonts-montserrat fonts-dejavu-core ca-certificates tzdata curl \
 && rm -rf /var/lib/apt/lists/*

# Deno: runtime JS que o yt-dlp usa para resolver o player do YouTube
COPY --from=deno /deno /usr/local/bin/deno

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY app ./app
COPY VERSION ./VERSION
COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh

RUN chmod +x /usr/local/bin/docker-entrypoint.sh \
 && useradd -u 1000 -m -s /bin/bash postop \
 && mkdir -p /data/media /data/work /data/models /data/uploads \
 && chown -R postop:postop /data /app

USER postop
VOLUME ["/data"]
EXPOSE 8000

# O worker desativa este healthcheck na stack (não tem servidor HTTP)
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
  CMD curl -fsS http://127.0.0.1:8000/api/health || exit 1

ENTRYPOINT ["docker-entrypoint.sh"]
CMD ["api"]
