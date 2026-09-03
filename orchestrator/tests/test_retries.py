"""
Tests de la logique de retries (3 max par Task).

On simule le provider qui rejette, et on verifie qu'apres 3 tentatives
la Task atteint FAILED_AFTER_RETRIES -> COMPLETED.
"""

from __future__ import annotations

from src.llm import ValidationResult
from src.loop import MockCycle
from src.memory import (
    AttemptRepository,
    LevelRepository,
    ProjectRepository,
    TaskRepository,
)


def _count_attempts(repos, task_id):
    return repos["attempts"].count_for_task(task_id)


def _all_attempts(repos, task_id):
    return repos["attempts"].list_for_task(task_id)


def test_three_retries_lead_to_failed_after_retries(repos, rejecting_provider, jsonl_logger, tmp_db_path):
    # On utilise directement la MockCycle pour le scenario complet.
    from src.memory import Database
    db = Database(tmp_db_path.parent / (tmp_db_path.stem + "-retry") / "zflm.db")
    db.initialize()
    cycle = MockCycle(
        db=db,
        provider=rejecting_provider,
        logger=jsonl_logger,
        max_attempts=3,
    )
    task_id = cycle.run_once()
    db.close()

    # Reload et verifie l'etat final.
    db2 = Database(tmp_db_path.parent / (tmp_db_path.stem + "-retry") / "zflm.db")
    db2.connect()
    attempts_repo = AttemptRepository(db2)
    attempts = attempts_repo.list_for_task(task_id)
    db2.close()

    # Trois attempts ont ete crees.
    assert len(attempts) == 3
    # Chaque attempt a un numero distinct 1, 2, 3.
    assert [a.attempt_number for a in attempts] == [1, 2, 3]
    # Chaque attempt est arrivee jusqu'a COMPLETED.
    for a in attempts:
        assert a.state == "COMPLETED"
    # Le dernier est marque 'failed' (equivalent de FAILED_AFTER_RETRIES).
    last = attempts[-1]
    assert last.status == "failed"


def test_approved_provider_single_attempt(repos, mock_provider, jsonl_logger, tmp_db_path):
    from src.memory import Database
    db = Database(tmp_db_path.parent / (tmp_db_path.stem + "-retry") / "zflm.db")
    db.initialize()
    cycle = MockCycle(
        db=db,
        provider=mock_provider,
        logger=jsonl_logger,
        max_attempts=3,
    )
    task_id = cycle.run_once()
    db.close()

    db2 = Database(tmp_db_path.parent / (tmp_db_path.stem + "-retry") / "zflm.db")
    db2.connect()
    attempts = AttemptRepository(db2).list_for_task(task_id)
    db2.close()

    assert len(attempts) == 1
    assert attempts[0].state == "COMPLETED"


def test_two_retries_then_approval(repos, jsonl_logger, tmp_db_path):
    """Provider reject deux fois puis approve au troisieme coup."""
    from src.llm import MockLLMProvider, ValidationResult
    from src.memory import Database
    db = Database(tmp_db_path.parent / (tmp_db_path.stem + "-retry") / "zflm.db")
    db.initialize()

    provider = MockLLMProvider()
    # On va modifier le verdict entre les attempts via set_validation.
    # Mais MockCycle ne fournit pas de hook ; on triche en utilisant un
    # provider dynamique :
    state = {"n": 0}

    class DynamicProvider(MockLLMProvider):
        def validate(self, *, code, role_config):
            state["n"] += 1
            if state["n"] < 3:
                return ValidationResult(approved=False, reason="nope")
            return ValidationResult(approved=True, reason="finally")

    provider = DynamicProvider()

    cycle = MockCycle(
        db=db,
        provider=provider,
        logger=jsonl_logger,
        max_attempts=3,
    )
    task_id = cycle.run_once()
    db.close()

    db2 = Database(tmp_db_path.parent / (tmp_db_path.stem + "-retry") / "zflm.db")
    db2.connect()
    attempts = AttemptRepository(db2).list_for_task(task_id)
    db2.close()
    assert len(attempts) == 3
    assert all(a.state == "COMPLETED" for a in attempts)
    # Le provider a ete appele 3 fois en tout (3 attempts x 1 validate).
    assert state["n"] == 3


def test_max_attempts_respected(repos, rejecting_provider, jsonl_logger, tmp_db_path):
    """Au-dela de 3 tentatives, on n'en cree pas une 4e."""
    from src.memory import Database
    db = Database(tmp_db_path.parent / (tmp_db_path.stem + "-retry") / "zflm.db")
    db.initialize()
    cycle = MockCycle(
        db=db,
        provider=rejecting_provider,
        logger=jsonl_logger,
        max_attempts=3,
    )
    task_id = cycle.run_once()
    db.close()

    db2 = Database(tmp_db_path.parent / (tmp_db_path.stem + "-retry") / "zflm.db")
    db2.connect()
    attempts = AttemptRepository(db2).list_for_task(task_id)
    db2.close()
    assert len(attempts) == 3
