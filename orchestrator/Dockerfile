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

# Préparer les répertoires runtime.
#   - /app/projects  : bind mount depuis ./projects/ côté hôte
#                      (sites générés, versionnés par Git)
#   - /app/memory    : SQLite (zflm.db), mémoire long terme
#   - /app/logs      : logs JSONL
# Tous ces chemins peuvent être bind-mountés en dev (machine hôte)
# OU montés comme volumes Docker nommés en production.
RUN mkdir -p /app/projects /app/memory /app/logs \
 && chown -R zflm:zflm /app

USER zflm

ENV PYTHONPATH=/app/src

# Healthcheck : le module src.main peut être importé et son
# entrypoint appelé en mode --show-recovery.
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -m src.main --show-recovery || exit 1

# Entrypoint par défaut (Phase 1). En Phase 2, on remplacera par un
# vrai service long-vivant (boucle d'expérience).
CMD ["python", "-m", "src.main"]