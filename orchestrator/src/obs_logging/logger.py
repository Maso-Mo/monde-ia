"""
Logger JSONL minimal pour ZFLM.

Chaque événement est une ligne JSON unique (JSON Lines) écrite dans
un fichier. Le logger capture les informations clés d'orchestration :

- timestamp
- project_id, level_id, task_id, attempt_id
- state
- event
- details (dict libre)

Ce module n'utilise PAS le module ``logging`` de la stdlib (sinon il
serait écrasé par un sous-package local nommé ``obs_logging``).

API :

- ``JsonlLogger(path)`` : instance liée à un fichier
- ``JsonlLogger.event(state=, event=, project_id=, ..., details=)``
- ``get_logger(name)`` : singleton pour le module principal
- ``configure_from_config(config)`` : initialise depuis ZflmConfig
"""

from __future__ import annotations

import json
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _utc_now_iso() -> str:
    """Timestamp UTC ISO 8601 avec microsecondes."""
    return datetime.now(timezone.utc).isoformat()


class JsonlLogger:
    """Logger JSONL thread-safe (un verrou par instance)."""

    def __init__(self, path: Path | str, *, also_stdout: bool = False):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._also_stdout = also_stdout
        # Crée le fichier s'il n'existe pas déjà (mais n'écrit rien).
        self.path.touch(exist_ok=True)

    # ------------------------------------------------------------------
    # API publique
    # ------------------------------------------------------------------

    def event(
        self,
        *,
        event: str,
        state: str | None = None,
        project_id: int | None = None,
        level_id: int | None = None,
        task_id: int | None = None,
        attempt_id: int | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        """Émet un événement structuré."""
        payload: dict[str, Any] = {
            "timestamp": _utc_now_iso(),
            "event": event,
        }
        if state is not None:
            payload["state"] = state
        if project_id is not None:
            payload["project_id"] = project_id
        if level_id is not None:
            payload["level_id"] = level_id
        if task_id is not None:
            payload["task_id"] = task_id
        if attempt_id is not None:
            payload["attempt_id"] = attempt_id
        if details:
            payload["details"] = details

        line = json.dumps(payload, ensure_ascii=False, sort_keys=False)

        with self._lock:
            with self.path.open("a", encoding="utf-8") as fh:
                fh.write(line + "\n")

        if self._also_stdout:
            print(line, file=sys.stdout)

    # Convenience helpers ------------------------------------------------

    def info(self, event: str, **kwargs: Any) -> None:
        self.event(event=event, **kwargs)

    def warn(self, event: str, **kwargs: Any) -> None:
        self.event(event=f"warn:{event}", **kwargs)

    def error(self, event: str, **kwargs: Any) -> None:
        self.event(event=f"error:{event}", **kwargs)


# ----------------------------------------------------------------------
# Singleton minimal
# ----------------------------------------------------------------------

_default_logger: JsonlLogger | None = None


def get_logger(name: str = "zflm") -> JsonlLogger:
    """Renvoie un logger par défaut (stdout only). À configurer via
    :func:`configure_from_config` pour écrire dans un fichier."""
    global _default_logger
    if _default_logger is None:
        _default_logger = JsonlLogger(
            path=Path(f"/tmp/{name}.jsonl"),
            also_stdout=True,
        )
    return _default_logger


def configure_from_config(config, *, name: str = "zflm") -> JsonlLogger:
    """Configure le singleton depuis une :class:`ZflmConfig`."""
    global _default_logger
    log_file = config.logs_dir / f"{name}.jsonl"
    _default_logger = JsonlLogger(
        path=log_file,
        also_stdout=(config.log_level.upper() == "DEBUG"),
    )
    return _default_logger


__all__ = ["JsonlLogger", "get_logger", "configure_from_config"]