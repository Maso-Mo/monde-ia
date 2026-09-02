"""
Chargement de la configuration ZFLM.

Ce module lit :

- les variables d'environnement (via python-dotenv),
- les fichiers YAML statiques (config/levels.yaml, config/llm_roles.yaml).

Il NE fait AUCUN appel réseau et n'instancie AUCUN client.
C'est une simple couche de lecture.

L'environnement de configuration est immutable : ``load_config()`` renvoie
un ``ZflmConfig`` qui peut être passé explicitement aux autres composants.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv


# ----------------------------------------------------------------------
# Valeurs par défaut
# ----------------------------------------------------------------------

# Chemin par défaut du dossier de configuration (relatif à la racine du repo).
# On accepte d'être appelé depuis /app (Docker) ou depuis la racine du repo
# en développement.
_DEFAULT_CONFIG_PATHS = (
    Path("/app/config"),
    Path(__file__).resolve().parents[3] / "config",
    Path.cwd() / "config",
)


def _find_config_file(filename: str) -> Path:
    """Recherche un fichier de config dans les emplacements connus."""
    for base in _DEFAULT_CONFIG_PATHS:
        candidate = base / filename
        if candidate.is_file():
            return candidate
    raise FileNotFoundError(
        f"Impossible de trouver {filename} dans : "
        + ", ".join(str(p) for p in _DEFAULT_CONFIG_PATHS)
    )


# ----------------------------------------------------------------------
# Structures de configuration
# ----------------------------------------------------------------------


@dataclass(frozen=True)
class LLMRoleConfig:
    """Configuration d'un rôle logique (generator / reviewer / validator)."""

    name: str
    provider: str | None = None
    model: str | None = None
    family: str | None = None  # ex. "qwen2.5", "qwen3" — indicatif

    @classmethod
    def from_yaml(cls, name: str, data: dict[str, Any]) -> "LLMRoleConfig":
        return cls(
            name=name,
            provider=data.get("provider"),
            model=data.get("model"),
            family=data.get("family"),
        )


@dataclass(frozen=True)
class ZflmConfig:
    """Configuration globale ZFLM."""

    db_path: Path
    projects_dir: Path
    memory_dir: Path
    logs_dir: Path
    log_level: str = "INFO"
    max_attempts_per_task: int = 3
    llm_roles: dict[str, LLMRoleConfig] = field(default_factory=dict)

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    @classmethod
    def load(
        cls,
        env_file: Path | str | None = None,
        config_dir: Path | str | None = None,
    ) -> "ZflmConfig":
        """
        Charge la configuration depuis l'environnement + YAML.

        ``env_file`` : chemin vers un fichier .env (None = recherche auto).
        ``config_dir`` : dossier contenant levels.yaml / llm_roles.yaml
                        (None = recherche auto).
        """
        # Charge .env si présent
        if env_file is not None:
            load_dotenv(env_file)
        else:
            # Charge .env à la racine du repo si présent
            for base in _DEFAULT_CONFIG_PATHS:
                env_path = base.parent / ".env"
                if env_path.is_file():
                    load_dotenv(env_path)
                    break

        # Chemins runtime
        db_path = Path(os.environ.get("ZFLM_DB_PATH", "/app/memory/zflm.db"))
        projects_dir = Path(os.environ.get("ZFLM_PROJECTS_DIR", "/app/projects"))
        memory_dir = Path(os.environ.get("ZFLM_MEMORY_DIR", "/app/memory"))
        logs_dir = Path(os.environ.get("ZFLM_LOGS_DIR", "/app/logs"))
        log_level = os.environ.get("ZFLM_LOG_LEVEL", "INFO")
        max_attempts = int(os.environ.get("ZFLM_MAX_ATTEMPTS_PER_TASK", "3"))

        # Rôles LLM
        if config_dir is not None:
            llm_roles_path = Path(config_dir) / "llm_roles.yaml"
        else:
            llm_roles_path = _find_config_file("llm_roles.yaml")

        with llm_roles_path.open("r", encoding="utf-8") as fh:
            llm_roles_raw = yaml.safe_load(fh) or {}

        roles_data = llm_roles_raw.get("roles", {}) or {}
        llm_roles = {
            name: LLMRoleConfig.from_yaml(name, data or {})
            for name, data in roles_data.items()
        }

        return cls(
            db_path=db_path,
            projects_dir=projects_dir,
            memory_dir=memory_dir,
            logs_dir=logs_dir,
            log_level=log_level,
            max_attempts_per_task=max_attempts,
            llm_roles=llm_roles,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def get_role(self, name: str) -> LLMRoleConfig:
        """Renvoie la config d'un rôle ou lève une erreur explicite."""
        if name not in self.llm_roles:
            raise KeyError(
                f"Rôle LLM '{name}' non défini dans llm_roles.yaml. "
                f"Rôles disponibles : {sorted(self.llm_roles.keys())}"
            )
        return self.llm_roles[name]


__all__ = ["ZflmConfig", "LLMRoleConfig"]