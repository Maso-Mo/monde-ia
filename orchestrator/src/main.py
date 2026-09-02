"""
Entrypoint ZFLM (Phase 1).

Modes supportes :

- (defaut)            : initialise la DB, affiche l'etat recupere, sort.
- --mock-cycle        : execute un MockCycle (mode developpement).
- --show-config       : affiche la configuration chargee, sort.
- --show-recovery     : affiche le RecoverySnapshot, sort.

Aucun appel reseau reel n'est effectue.

Usage :

    python -m src.main
    python -m src.main --mock-cycle
    python -m src.main --show-config
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .config import ZflmConfig
from .llm import MockLLMProvider, load_roles_config
from .loop import MockCycle
from .memory import (
    AttemptRepository,
    Database,
    LevelRepository,
    ProjectRepository,
    TaskRepository,
)
from .obs_logging.logger import configure_from_config, get_logger
from .recovery import find_active_state


def _parse_args(argv):
    p = argparse.ArgumentParser(prog="zflm", description="Orchestrateur ZFLM (Phase 1)")
    p.add_argument("--mock-cycle", action="store_true",
                   help="Execute un cycle MOCK et sort.")
    p.add_argument("--show-config", action="store_true",
                   help="Affiche la configuration et sort.")
    p.add_argument("--show-recovery", action="store_true",
                   help="Affiche le RecoverySnapshot et sort.")
    p.add_argument("--no-color", action="store_true",
                   help="Pas de couleur dans la sortie.")
    return p.parse_args(argv)


def _print(msg: str, color: bool = True) -> None:
    if color:
        print(msg)
    else:
        print(msg)


def cmd_show_config(config: ZflmConfig) -> int:
    _print("=== ZFLM Configuration ===")
    _print(f"db_path            : {config.db_path}")
    _print(f"projects_dir       : {config.projects_dir}")
    _print(f"memory_dir         : {config.memory_dir}")
    _print(f"logs_dir           : {config.logs_dir}")
    _print(f"log_level          : {config.log_level}")
    _print(f"max_attempts       : {config.max_attempts_per_task}")
    _print("LLM roles :")
    for name, role in sorted(config.llm_roles.items()):
        _print(f"  - {name:10s} provider={role.provider} model={role.model} family={role.family}")
    return 0


def cmd_show_recovery(db: Database) -> int:
    projects = ProjectRepository(db)
    levels = LevelRepository(db)
    tasks = TaskRepository(db)
    attempts = AttemptRepository(db)
    snap = find_active_state(projects, levels, tasks, attempts)
    print("=== ZFLM Recovery Snapshot ===")
    print(snap.summary())
    print(f"recoverable        : {snap.is_recoverable}")
    return 0


def cmd_mock_cycle(config: ZflmConfig, logger) -> int:
    db = Database(config.db_path)
    db.initialize()
    try:
        provider = MockLLMProvider()
        roles = load_roles_config()
        cycle = MockCycle(
            db=db,
            provider=provider,
            logger=logger,
            max_attempts=config.max_attempts_per_task,
            roles_config=roles,
        )
        task_id = cycle.run_once()
        print(f"[mock-cycle] termine, task_id={task_id}")
    finally:
        db.close()
    return 0


def main(argv=None) -> int:
    args = _parse_args(argv or sys.argv[1:])

    config = ZflmConfig.load()
    logger = configure_from_config(config)

    # Initialise la DB dans tous les cas (idempotent).
    db = Database(config.db_path)
    db.initialize()

    if args.show_config:
        rc = cmd_show_config(config)
        db.close()
        return rc

    if args.show_recovery:
        rc = cmd_show_recovery(db)
        db.close()
        return rc

    if args.mock_cycle:
        db.close()
        return cmd_mock_cycle(config, logger)

    # Mode par defaut : juste afficher l'etat recupere.
    snap = find_active_state(
        ProjectRepository(db),
        LevelRepository(db),
        TaskRepository(db),
        AttemptRepository(db),
    )
    print("=== ZFLM orchestrator (Phase 1) ===")
    print(f"DB                 : {config.db_path}")
    print(f"recovery.is_recoverable: {snap.is_recoverable}")
    print(snap.summary())
    db.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
