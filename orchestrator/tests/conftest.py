"""
Fixtures pytest partagees par tous les tests ZFLM.

Chaque test recoit une :class:`Database` isolee dans un fichier
temporaire via la fixture ``tmp_path``. Le DDL est execute a chaque
ouverture pour garantir un etat propre.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

# Permet d'importer src.* depuis n'importe quel repertoire.
_SRC_ROOT = Path(__file__).resolve().parents[1] / "src"
if str(_SRC_ROOT.parent) not in sys.path:
    sys.path.insert(0, str(_SRC_ROOT.parent))

# Verifie que les variables d'env ne pointent pas vers un fichier
# reel pendant les tests.
os.environ.setdefault("ZFLM_DB_PATH", "/tmp/zflm-test-ignored.db")
os.environ.setdefault("ZFLM_LOGS_DIR", "/tmp/zflm-test-ignored-logs")


@pytest.fixture
def tmp_db_path(tmp_path: Path) -> Path:
    """Fichier SQLite isole par test, supprime automatiquement."""
    return tmp_path / "zflm.db"


@pytest.fixture
def db(tmp_db_path: Path):
    """Database initialisee et fermee automatiquement a la fin du test."""
    from src.memory import Database
    database = Database(tmp_db_path)
    database.initialize()
    try:
        yield database
    finally:
        database.close()


@pytest.fixture
def repos(db):
    """Tous les repositories prets a l'emploi."""
    from src.memory import (
        AttemptRepository,
        ErrorRepository,
        GitSnapshotRepository,
        LevelRepository,
        LLMCallRepository,
        MemoryRepository,
        ProjectRepository,
        ProviderStateRepository,
        ReviewRepository,
        TaskRepository,
        ValidationRepository,
    )
    return {
        "projects": ProjectRepository(db),
        "levels": LevelRepository(db),
        "tasks": TaskRepository(db),
        "attempts": AttemptRepository(db),
        "llm_calls": LLMCallRepository(db),
        "reviews": ReviewRepository(db),
        "validations": ValidationRepository(db),
        "errors": ErrorRepository(db),
        "memories": MemoryRepository(db),
        "provider_states": ProviderStateRepository(db),
        "git_snapshots": GitSnapshotRepository(db),
    }


@pytest.fixture
def mock_provider():
    """Provider mock par defaut (validation=approved)."""
    from src.llm import MockLLMProvider
    return MockLLMProvider()


@pytest.fixture
def rejecting_provider():
    """Provider mock qui rejette la validation."""
    from src.llm import MockLLMProvider, ValidationResult
    p = MockLLMProvider()
    p.set_validation(ValidationResult(
        status="rejected",
        score=0.2,
        reason="Mock reject",
        blocking_issues=["mock-issue-1"],
    ))
    return p


@pytest.fixture
def jsonl_logger(tmp_path: Path):
    """Logger JSONL ecrivant dans un fichier temporaire."""
    from src.obs_logging.logger import JsonlLogger
    return JsonlLogger(tmp_path / "events.jsonl")


@pytest.fixture
def machine(db, jsonl_logger):
    """AttemptStateMachine prete a l'emploi."""
    from src.memory import AttemptRepository
    from src.state_machine import AttemptStateMachine
    return AttemptStateMachine(
        writer=AttemptRepository(db),
        logger=jsonl_logger,
    )
