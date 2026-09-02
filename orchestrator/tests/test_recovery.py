"""
Tests du scenario demande :

1. une tentative arrive a BUILDING
2. le programme est arrete (on ferme la DB)
3. une nouvelle instance lit la DB
4. elle retrouve BUILDING comme etat a reprendre
"""

from __future__ import annotations

from src.memory import (
    AttemptRepository,
    Database,
    LevelRepository,
    ProjectRepository,
    TaskRepository,
)
from src.recovery import find_active_state
from src.state_machine import AttemptState, AttemptStateMachine


def test_recovery_after_restart_at_building(tmp_db_path):
    # --- Phase 1 : on cree un cycle et on l'amene a BUILDING. ---
    db1 = Database(tmp_db_path)
    db1.initialize()
    projects = ProjectRepository(db1)
    levels = LevelRepository(db1)
    tasks = TaskRepository(db1)
    attempts = AttemptRepository(db1)

    p = projects.create("recovery-project")
    projects.set_current_level(p.id, None)
    lvl = levels.create(p.id, 1, "spec")
    projects.set_current_level(p.id, lvl.id)
    t = tasks.create(lvl.id, "task-1")
    a = attempts.create(t.id, 1)

    machine = AttemptStateMachine(writer=attempts)
    machine.transition(a, AttemptState.PREPARING)
    machine.transition(a, AttemptState.GENERATING)
    machine.transition(a, AttemptState.BUILDING)

    snap1 = find_active_state(projects, levels, tasks, attempts)
    assert snap1.attempt_state == "BUILDING"
    db1.close()  # <-- simulation d'un crash / arret

    # --- Phase 2 : nouvelle instance, on retrouve BUILDING. ---
    db2 = Database(tmp_db_path)
    db2.connect()
    snap2 = find_active_state(
        ProjectRepository(db2),
        LevelRepository(db2),
        TaskRepository(db2),
        AttemptRepository(db2),
    )
    assert snap2.is_recoverable
    assert snap2.attempt_state == "BUILDING"
    assert snap2.attempt_id == a.id
    assert snap2.task_id == t.id
    assert snap2.level_id == lvl.id
    assert snap2.project_id == p.id
    assert snap2.previous_state is None
    db2.close()


def test_recovery_no_active_state(tmp_db_path):
    db = Database(tmp_db_path)
    db.initialize()
    snap = find_active_state(
        ProjectRepository(db),
        LevelRepository(db),
        TaskRepository(db),
        AttemptRepository(db),
    )
    assert not snap.is_recoverable
    assert snap.project_id is None
    db.close()


def test_recovery_after_completion(tmp_db_path):
    """Un projet COMPLETED ne doit pas apparaitre comme 'a reprendre'."""
    db = Database(tmp_db_path)
    db.initialize()
    projects = ProjectRepository(db)
    levels = LevelRepository(db)
    tasks = TaskRepository(db)
    attempts = AttemptRepository(db)

    p = projects.create("done-project")
    lvl = levels.create(p.id, 1, "spec")
    projects.set_current_level(p.id, lvl.id)
    t = tasks.create(lvl.id, "done task")
    a = attempts.create(t.id, 1)

    machine = AttemptStateMachine(writer=attempts)
    machine.transition(a, AttemptState.PREPARING)
    machine.transition(a, AttemptState.GENERATING)
    machine.transition(a, AttemptState.BUILDING)
    machine.transition(a, AttemptState.TESTING)
    machine.transition(a, AttemptState.REVIEWING)
    machine.transition(a, AttemptState.VALIDATING)
    machine.transition(a, AttemptState.APPROVED)
    machine.transition(a, AttemptState.COMPLETED)
    db.close()

    # Au redemarrage : on ne doit pas voir cet Attempt comme actif.
    db2 = Database(tmp_db_path)
    db2.connect()
    snap = find_active_state(
        ProjectRepository(db2),
        LevelRepository(db2),
        TaskRepository(db2),
        AttemptRepository(db2),
    )
    # Aucun attempt actif : on retombe sur le projet mais sans recovery.
    assert snap.attempt_id is None or snap.attempt_state == "COMPLETED"
    db2.close()
