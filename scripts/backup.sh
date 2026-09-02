#!/usr/bin/env bash
# ============================================================
# ZFLM - Backup
# ============================================================
# Crée une archive tar.gz du contenu "versionnable" du projet :
#   - code source
#   - configs
#   - scripts
#   - documentation
#
# Le backup ne contient JAMAIS :
#   - .env / .env.*
#   - *.key / *.pem
#   - credentials / secrets
#   - clés SSH
#   - bases SQLite / JSON de mémoire runtime
#   - caches Python / Node
#   - logs bruts (volumineux, déjà rotés par l'orchestrateur)
#
# Usage :
#   bash scripts/backup.sh [destination]
#
#   destination = dossier où poser l'archive (par défaut ./backups)
#
# Le nom de l'archive est horodaté :
#   zflm-backup-YYYYMMDD-HHMMSS.tar.gz
# ============================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${SCRIPT_DIR}/.."

DEST="${1:-./backups}"
mkdir -p "${DEST}"

TS="$(date +%Y%m%d-%H%M%S)"
ARCHIVE="${DEST}/zflm-backup-${TS}.tar.gz"

echo "[backup] Création de l'archive : ${ARCHIVE}"

# Construire l'archive en excluant explicitement les chemins sensibles.
# On s'appuie sur --exclude pour chaque pattern, et --exclude-from pour
# relayer .gitignore (les patterns .gitignore s'appliquent alors comme
# des filtres).
tar \
  --create \
  --gzip \
  --file="${ARCHIVE}" \
  --exclude-from='.gitignore' \
  --exclude='./.git' \
  --exclude='./backups' \
  --exclude='./logs' \
  --exclude='./memory/*.db' \
  --exclude='./memory/*.json' \
  --exclude='./memory/*.jsonl' \
  --exclude='./projects/*/build' \
  --exclude='./projects/*/dist' \
  --exclude='./projects/*/node_modules' \
  --exclude='./projects/*/.cache' \
  --exclude='./*.tar.gz' \
  --transform "s,^,zflm-${TS}/," \
  .

echo "[backup] Archive créée : ${ARCHIVE}"
ls -lh "${ARCHIVE}"

echo "[backup] Vérification d'absence de secrets dans l'archive..."
if tar -tzf "${ARCHIVE}" | grep -E '(\.env|credentials|secrets|\.key$|\.pem$|id_rsa|authorized_keys)'; then
  echo "[backup][ERREUR] L'archive semble contenir des secrets potentiels !" >&2
  exit 1
fi

echo "[backup] OK"