# ============================================================
# ZFLM - Sandbox HTML / CSS
# ============================================================
# Image minimale pour exécuter et valider des projets HTML/CSS.
# Pas de serveur web : les validations sont statiques (parsing).
#
# Validation effectuée :
#   - HTML bien formé (via python html.parser + html5lib léger)
#   - Présentence du doctype
#   - Présentence de <html>
#   - CSS parsable (via tinycss2)
#
# Pour les niveaux avancés, un serveur HTTP pourrait être ajouté
# (nginx statique) mais ce n'est pas requis en V1.

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Paquets utiles : curl pour healthcheck, git pour récupérer
# les sources, et les libs Python de validation.
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
        curl \
        git \
        ca-certificates \
 && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir \
        html5lib \
        tinycss2

# Crée un point d'entrée neutre. En V1 ce conteneur sert
# surtout à fournir un environnement reproductible pour les
# validations. Un script de validation dédié sera ajouté en
# Phase 1.
RUN mkdir -p /work /out
WORKDIR /work

# Healthcheck : Python peut-il s'importer ?
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
  CMD python -c "import html5lib, tinycss2; print('OK')" || exit 1

CMD ["python", "-c", "print('ZFLM sandbox html-css ready')"]