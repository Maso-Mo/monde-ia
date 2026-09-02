#!/usr/bin/env bash
# ============================================================
# ZFLM - Health check
# ============================================================
# Vérifie rapidement :
#   - statut Git du dépôt
#   - Docker daemon joignable
#   - images Docker critiques présentes
#   - absence de secrets suivis
#   - fichiers de configuration clés présents
#
# Sortie : code 0 si tout va bien, != 0 sinon.
# Utilisable depuis cron, systemd, ou en manuel.
# ============================================================

set -euo pipefail

# Toujours se placer à la racine du projet
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${SCRIPT_DIR}/.."

# Couleurs
if [[ -t 1 ]]; then
  C_OK=$'\033[1;32m'
  C_ERR=$'\033[1;31m'
  C_INFO=$'\033[1;34m'
  C_RESET=$'\033[0m'
else
  C_OK=""; C_ERR=""; C_INFO=""; C_RESET=""
fi

pass=0
fail=0

check() {
  local name="$1"
  shift
  if "$@" >/dev/null 2>&1; then
    printf "%s[ OK ]%s  %s\n" "$C_OK"   "$C_RESET" "$name"
    pass=$((pass + 1))
  else
    printf "%s[FAIL]%s  %s\n" "$C_ERR"  "$C_RESET" "$name"
    fail=$((fail + 1))
  fi
}

# 1. Git : on est bien dans un dépôt
check "Dépôt Git (.git présent)"          test -d .git
check "Branche = main"                    bash -c 'git branch --show-current | grep -qx main'
check "Remote origin = Maso-Mo/monde-ia"  bash -c 'git remote get-url origin | grep -qx git@github.com:Maso-Mo/monde-ia.git'

# 2. Working tree propre (autorise fichiers non suivis)
check "Working tree propre (hors untracked)" \
  bash -c 'git diff --quiet && git diff --cached --quiet'

# 3. Aucun secret suivi par Git
check ".env absent du suivi Git"          bash -c '! git ls-files | grep -qx .env'
check "Pas de .key ou .pem suivi"         bash -c '! git ls-files | grep -Eq "\.(key|pem)$"'

# 4. Fichiers clés présents
check "config/levels.yaml présent"        test -f config/levels.yaml
check "docker-compose.yml présent"        test -f docker-compose.yml
check "orchestrator/Dockerfile présent"   test -f orchestrator/Dockerfile
check "scripts/bootstrap_oracle.sh présent"  test -f scripts/bootstrap_oracle.sh

# 5. Docker
check "Docker CLI présent"                command -v docker
check "Docker daemon joignable"           docker info
check "Image python:3.12-slim présente"   bash -c 'docker images --format "{{.Repository}}:{{.Tag}}" | grep -qx python:3.12-slim'
check "Image node:20-slim présente"       bash -c 'docker images --format "{{.Repository}}:{{.Tag}}" | grep -qx node:20-slim'

# 6. Python (orchestrateur runtime)
check "python3 (>= 3.10)"                bash -c 'python3 -c "import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)"'

printf "\n%s[RESULT]%s %d OK, %d FAIL\n" "$C_INFO" "$C_RESET" "$pass" "$fail"

if (( fail > 0 )); then
  exit 1
fi