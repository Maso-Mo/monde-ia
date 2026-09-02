"""
Chargement de la configuration des roles LLM.

Cette couche est distincte de :class:`ZflmConfig` pour deux raisons :

1. :class:`ZflmConfig` est charge depuis ``ZFLM_*`` env / .env ;
2. Les roles dependent d'un fichier YAML specifique (llm_roles.yaml).

L'API principale est :func:`load_roles_config` qui lit le YAML et
renvoie un mapping ``dict[str, LLMRoleConfig]``.

On n'importe PAS :class:`ZflmConfig` ici pour eviter les cycles.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


# Liste des emplacements ou chercher llm_roles.yaml.
_DEFAULT_PATHS = (
    Path("/app/config"),
    Path(__file__).resolve().parents[3] / "config",
    Path.cwd() / "config",
)


def _find_config_file(filename: str) -> Path:
    for base in _DEFAULT_PATHS:
        candidate = base / filename
        if candidate.is_file():
            return candidate
    raise FileNotFoundError(
        f"Impossible de trouver {filename} dans : "
        + ", ".join(str(p) for p in _DEFAULT_PATHS)
    )


def load_roles_config(
    path: Path | str | None = None,
) -> dict[str, dict[str, Any]]:
    """Lit llm_roles.yaml et renvoie un dict brut role -> config.

    On renvoie le dict brut (pas des LLMRoleConfig) pour eviter une
    dependance directe vers :mod:`config.loader`. Le contenu est
    directement utilisable par les providers via le champ
    ``role_config``.
    """
    if path is None:
        path = _find_config_file("llm_roles.yaml")
    else:
        path = Path(path)

    with path.open("r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh) or {}

    roles = raw.get("roles", {}) or {}
    # Garantir que toutes les cles standard existent (meme a null).
    normalized: dict[str, dict[str, Any]] = {}
    for name in ("generator", "reviewer", "validator"):
        normalized[name] = roles.get(name) or {}
    # Ajouter les roles supplementaires non standard.
    for name, data in roles.items():
        if name not in normalized:
            normalized[name] = data or {}
    return normalized


def get_role_config(
    roles: dict[str, dict[str, Any]],
    role_name: str,
) -> dict[str, Any]:
    """Renvoie la config d'un role ou un dict vide par defaut."""
    return roles.get(role_name) or {}


__all__ = ["load_roles_config", "get_role_config"]
