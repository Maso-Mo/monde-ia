"""
Tests de persistance : un cycle ecrit en DB survit a la fermeture
et a la reouverture d'une nouvelle instance de Database.
"""

from __future__ import annotations

import os

from src.memory import (
    Attempt,
    AttemptRepository,
    Database,
    LevelRepository,
    ProjectRepository,
    TaskRepository,
)
from src.state_machine import AttemptState, AttemptStateMachine


def test_db_file_persists_between_instances(tmp_db_path):
    """Cycle d'ecriture, fermeture, relecture : les donnees survivent."""
    db1 = Database(tmp_db_path)
    db1.initialize()

    p = ProjectRepository(db1).create("persist-1")
    lvl = LevelRepository(db1).create(p.id, 1, "spec")
    t = TaskRepository(db1).create(lvl.id, "task-a")
    a = AttemptRepository(db1).create(t.id, 1)

    machine = AttemptStateMachine(db=db1)
    machine.transition(a, AttemptState.PREPARING)
    machine.transition(a, AttemptState.GENERATING)
    machine.transition(a, AttemptState.BUILDING)

    db1.close()

    # Le fichier existe-t-il ?
    assert tmp_db_path.exists()
    assert tmp_db_path.stat().st_size > 0

    # Nouvelle instance : on doit retrouver l'etat.
    db2 = Database(tmp_db_path)
    # Pas d'initialize() ici : le schema existe deja.
    db2.connect()
    a2 = AttemptRepository(db2).get(a.id)
    assert a2 is not None
    assert a2.state == "BUILDING"
    assert a2.previous_state is None
    p2 = ProjectRepository(db2).get(p.id)
    assert p2.name == "persist-1"
    db2.close()


def test_state_survives_even_without_init(tmp_db_path):
    """Si on n'appelle pas initialize() sur un fichier deja cree, ca marche."""
    db1 = Database(tmp_db_path)
    db1.initialize()
    p = ProjectRepository(db1).create("z")
    db1.close()

    db2 = Database(tmp_db_path)
    db2.connect()
    p2 = ProjectRepository(db2).get(p.id)
    assert p2 is not None
    db2.close()
