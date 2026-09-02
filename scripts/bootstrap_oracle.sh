#!/usr/bin/env bash
# ============================================================
# ZFLM - Bootstrap VM Oracle Cloud Always Free (Ubuntu ARM64)
# ============================================================
# Ce script prépare une VM Ubuntu ARM64 vierge (Oracle Cloud)
# pour y faire tourner l'orchestrateur ZFLM + FreeLLMAPI.
#
# IMPORTANT :
#   - NE PAS exécuter ce script sur Arch Linux (machine dev).
#   - À exécuter uniquement sur la VM Oracle cible.
#   - Idempotent : peut être ré-exécuté sans casse.
#   - Ne touche à aucun secret. Aucun credential n'est écrit
#     dans le dépôt.
#
# Usage (sur la VM Oracle) :
#   curl -sSL https://raw.githubusercontent.com/Maso-Mo/monde-ia/main/scripts/bootstrap_oracle.sh | bash
#   # ou, en local après clonage du repo :
#   bash scripts/bootstrap_oracle.sh
#
# Prérequis :
#   - Ubuntu 22.04 LTS (ou 24.04) ARM64
#   - Accès sudo (le script utilise sudo pour apt)
#   - Connectivité Internet
# ============================================================

set -euo pipefail

# Couleurs pour logs (désactivables)
if [[ -t 1 ]]; then
  C_RESET=$'\033[0m'
  C_INFO=$'\033[1;34m'
  C_OK=$'\033[1;32m'
  C_WARN=$'\033[1;33m'
  C_ERR=$'\033[1;31m'
else
  C_RESET=""; C_INFO=""; C_OK=""; C_WARN=""; C_ERR=""
fi

log()  { printf "%s[INFO]%s %s\n"  "$C_INFO"  "$C_RESET" "$*"; }
ok()   { printf "%s[ OK ]%s %s\n"  "$C_OK"   "$C_RESET" "$*"; }
warn() { printf "%s[WARN]%s %s\n"  "$C_WARN" "$C_RESET" "$*"; }
err()  { printf "%s[ERR ]%s %s\n"  "$C_ERR"  "$C_RESET" "$*" >&2; }

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || {
    err "Commande requise manquante : $1"
    return 1
  }
}

# Garde-fou : refuser de tourner si on n'est pas sur Ubuntu
if [[ ! -f /etc/os-release ]]; then
  err "/etc/os-release introuvable. Ce script cible Ubuntu."
  exit 1
fi
. /etc/os-release
if [[ "${ID:-}" != "ubuntu" ]]; then
  err "OS détecté : ${ID:-inconnu}. Ce script cible Ubuntu (ARM64)."
  err "NE PAS l'exécuter sur Arch Linux ou autre."
  exit 1
fi

log "Cible : ${PRETTY_NAME} (${VERSION:-?})"

# Paquets de base
log "Installation des paquets système..."
export DEBIAN_FRONTEND=noninteractive
sudo apt-get update -y
sudo apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    wget \
    git \
    jq \
    rsync \
    openssh-client \
    unzip \
    tar \
    build-essential \
    python3 \
    python3-venv \
    python3-pip \
    iptables \
    gnupg

ok "Paquets système installés"

# Docker (officiel, ARM64)
if ! command -v docker >/dev/null 2>&1; then
  log "Installation de Docker (officiel, multi-arch)..."
  sudo install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
    | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
  sudo chmod a+r /etc/apt/keyrings/docker.gpg

  ARCH="$(dpkg --print-architecture)"
  # Sur Ubuntu, ARCH est déjà 'arm64' ou 'amd64'.
  echo "deb [arch=${ARCH} signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
    $(. /etc/os-release && echo "${VERSION_CODENAME}") stable" \
    | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

  sudo apt-get update -y
  sudo apt-get install -y --no-install-recommends \
      docker-ce \
      docker-ce-cli \
      containerd.io \
      docker-buildx-plugin \
      docker-compose-plugin
  ok "Docker installé"
else
  ok "Docker déjà présent : $(docker --version)"
fi

# Activer Docker au boot
sudo systemctl enable --now docker || warn "systemctl non disponible (pas grave en conteneur/VM éphémère)"

# Vérifier que l'utilisateur courant peut utiliser docker sans sudo
if ! docker ps >/dev/null 2>&1; then
  warn "L'utilisateur courant n'a pas accès au daemon Docker."
  warn "Si besoin : sudo usermod -aG docker \$USER  puis  newgrp docker"
fi

# Compose (vérif)
if docker compose version >/dev/null 2>&1; then
  ok "Docker Compose : $(docker compose version)"
else
  warn "Docker Compose non détecté (devrait être inclus via le plugin)."
fi

# Précharger les images Docker de base pour économiser la bande passante
# plus tard (sera fait de toute façon par docker-compose, mais utile si
# la VM a une connexion limitée).
log "Préchargement des images de base (peut prendre quelques minutes)..."
sudo docker pull python:3.12-slim || warn "Échec pull python:3.12-slim"
sudo docker pull node:20-slim     || warn "Échec pull node:20-slim"
ok "Images de base prêtes"

# Dossier de travail
WORKDIR="${HOME}/zflm"
mkdir -p "${WORKDIR}"
ok "Dossier de travail : ${WORKDIR}"

log "Bootstrap Oracle terminé."
log "Prochaines étapes :"
log "  1. Cloner le repo :  git clone git@github.com:Maso-Mo/monde-ia.git ${WORKDIR}"
log "  2. Copier .env.example vers .env et remplir"
log "  3. Lancer :          cd ${WORKDIR} && docker compose pull && docker compose up -d"