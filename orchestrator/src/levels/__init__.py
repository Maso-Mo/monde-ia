"""
Chargement de la definition des niveaux (config/levels.yaml).

API :

- :func:`load_levels` : renvoie la liste brute des niveaux ;
- :func:`find_level_by_id` : retrouve un niveau par son id logique.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

import yaml


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
    raise FileNotFoundError(filename)


def load_levels(path: Path | str | None = None) -> dict[str, Any]:
    """Charge levels.yaml et renvoie le dict brut."""
    if path is None:
        path = _find_config_file("levels.yaml")
    else:
        path = Path(path)
    with path.open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def list_levels(path: Path | str | None = None) -> list[dict[str, Any]]:
    """Renvoie la liste des niveaux (vide si aucun)."""
    data = load_levels(path)
    return data.get("levels", []) or []


def find_level_by_id(
    level_id: str,
    path: Path | str | None = None,
) -> Optional[dict[str, Any]]:
    """Cherche un niveau par son id logique (champ ``id``)."""
    for lvl in list_levels(path):
        if lvl.get("id") == level_id:
            return lvl
    return None


__all__ = ["load_levels", "list_levels", "find_level_by_id"]
