# ============================================================
# ZFLM - Orchestrator image
# ============================================================
# Runtime : Python 3.12 (officiel pour cet orchestrateur).
# On utilise python:3.12-slim déjà préchargé localement.

FROM python:3.12-slim

# Empêcher Python d'écrire des .pyc et de bufferiser stdout/stderr
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Dépendances système minimales (curl pour healthchecks,
# git pour la gestion des projets versionnés).
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
        curl \
        git \
        ca-certificates \
 && rm -rf /var/lib/apt/lists/*

# Créer un utilisateur non-root (bonne pratique Docker)
RUN groupadd -r zflm && useradd -r -g zflm -d /app -s /usr/sbin/nologin zflm

WORKDIR /app

# Copier requirements en premier pour profiter du cache Docker
COPY requirements.txt /app/requirements.txt
RUN pip install -r /app/requirements.txt

# Copier le code source
COPY src/ /app/src/

# Préparer les répertoires runtime (seront montés en volumes
# via docker-compose, mais on les crée pour le mode standalone)
RUN mkdir -p /data /projects /memory /logs \
 && chown -R zflm:zflm /app /data /projects /memory /logs

USER zflm

ENV PYTHONPATH=/app/src

# Healthcheck simple : python peut-il s'importer ?
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import sys; sys.exit(0)" || exit 1

# Commande par défaut (sera remplacée en Phase 1)
# En Phase 0, on vérifie simplement que les imports fonctionnent.
CMD ["python", "-c", "import pydantic, httpx, docker, yaml, dotenv, pytest; print('ZFLM orchestrator runtime OK')"]