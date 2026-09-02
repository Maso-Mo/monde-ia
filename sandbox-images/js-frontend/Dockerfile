# ============================================================
# ZFLM - Sandbox JavaScript / Frontend
# ============================================================
# Image basée sur node:20-slim (déjà préchargée localement).
# Sert à valider syntaxe JS et structure frontend légère.
#
# Validation effectuée (V1) :
#   - node --check sur chaque .js
#   - présence d'au moins un addEventListener (pour les
#     niveaux JS basique/interactions)
#
# Pas de bundler, pas de framework lourd : le sandbox reste
# minimal pour ne pas fausser l'évaluation des LLM.

FROM node:20-slim

ENV NPM_CONFIG_LOGLEVEL=warn \
    NODE_ENV=production

# Outils système utiles
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
        git \
        ca-certificates \
        curl \
 && rm -rf /var/lib/apt/lists/*

# Linters/légers utiles :
#   - htmlhint : validation HTML rapide (déjà écrit en JS)
# Ces outils sont installés globalement dans le sandbox.
RUN npm install -g --no-audit --no-fund htmlhint

RUN mkdir -p /work /out
WORKDIR /work

# Healthcheck : node + htmlhint répondent ?
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD node --version && which htmlhint || exit 1

CMD ["node", "-e", "console.log('ZFLM sandbox js-frontend ready')"]