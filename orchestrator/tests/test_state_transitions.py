"""
Tests du journal append-only state_transitions.

Couvre :
- chaque transition cree une ligne ;
- ordre chronologique ;
- from_state / to_state corrects ;
- atomicite UPDATE attempts + INSERT state_transitions ;
- une transition invalide ne cree AUCUNE ligne ;
- le recovery fonctionne toujours avec l'historique present.
"""

from __future__ import annotations

import sqlite3

import pytest

from src.memory import (
    AttemptRepository,
    Database,
    LevelRepository,
    ProjectRepository,
    StateTransitionRepository,
    TaskRepository,
)
from src.recovery import find_active_state
from src.state_machine import (
    AttemptState,
    AttemptStateMachine,
    InvalidTransition,
)


def _new_attempt(repos):
    p = repos["projects"].create("p")
    lvl = repos["levels"].create(p.id, 1, "spec")
    t = repos["tasks"].create(lvl.id, "do")
    return repos["attempts"].create(t.id, 1)


# ----------------------------------------------------------------------
# Table de transitions
# ----------------------------------------------------------------------


def test_state_transitions_table_exists(tmp_db_path):
    db = Database(tmp_db_path)
    db.initialize()
    rows = db.connection.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()
    names = {r["name"] for r in rows}
    assert "state_transitions" in names
    db.close()


def test_each_transition_creates_one_row(machine, repos):
    """Chaine complete : chaque appel a transition() cree une ligne."""
    a = _new_attempt(repos)
    repo = StateTransitionRepository(repos["attempts"]._db)
    machine.transition(a, AttemptState.PREPARING)
    machine.transition(a, AttemptState.GENERATING)
    machine.transition(a, AttemptState.BUILDING)
    machine.transition(a, AttemptState.TESTING)
    machine.transition(a, AttemptState.REVIEWING)
    machine.transition(a, AttemptState.VALIDATING)
    machine.transition(a, AttemptState.APPROVED)
    machine.transition(a, AttemptState.COMPLETED)

    transitions = repo.list_for_attempt(a.id)
    assert len(transitions) == 8
    # La derniere ligne reflete l'etat final COMPLETED.
    assert transitions[-1].from_state == "APPROVED"
    assert transitions[-1].to_state == "COMPLETED"


def test_transitions_in_chronological_order(machine, repos):
    a = _new_attempt(repos)
    repo = StateTransitionRepository(repos["attempts"]._db)
    sequence = [
        AttemptState.PREPARING,
        AttemptState.GENERATING,
        AttemptState.BUILDING,
        AttemptState.TESTING,
        AttemptState.REVIEWING,
        AttemptState.VALIDATING,
        AttemptState.APPROVED,
        AttemptState.COMPLETED,
    ]
    for s in sequence:
        machine.transition(a, s)

    transitions = repo.list_for_attempt(a.id)
    # Les id sont croissants.
    ids = [t.id for t in transitions]
    assert ids == sorted(ids)
    # Les created_at aussi (ordre alphabetique ISO 8601).
    times = [t.created_at for t in transitions]
    assert times == sorted(times)


def test_from_state_and_to_state_correct(machine, repos):
    a = _new_attempt(repos)
    repo = StateTransitionRepository(repos["attempts"]._db)
    machine.transition(a, AttemptState.PREPARING)
    machine.transition(a, AttemptState.GENERATING)
    machine.transition(a, AttemptState.BUILDING)

    transitions = repo.list_for_attempt(a.id)
    assert len(transitions) == 3
    assert transitions[0].from_state == "CREATED"
    assert transitions[0].to_state == "PREPARING"
    assert transitions[1].from_state == "PREPARING"
    assert transitions[1].to_state == "GENERATING"
    assert transitions[2].from_state == "GENERATING"
    assert transitions[2].to_state == "BUILDING"


def test_reason_is_recorded(machine, repos):
    a = _new_attempt(repos)
    repo = StateTransitionRepository(repos["attempts"]._db)
    machine.transition(a, AttemptState.PREPARING, reason="kickoff")
    machine.transition(a, AttemptState.GENERATING, reason="start-gen")
    machine.enter_paused(a, reason="provider-429")

    transitions = repo.list_for_attempt(a.id)
    reasons = [t.reason for t in transitions]
    assert reasons == ["kickoff", "start-gen", "provider-429"]


# ----------------------------------------------------------------------
# Atomicite
# ----------------------------------------------------------------------


def test_atomic_update_attempt_and_insert_transition(machine, repos):
    """Apres chaque transition : attempts.state == state_transitions.last.to_state."""
    a = _new_attempt(repos)
    repo = StateTransitionRepository(repos["attempts"]._db)
    machine.transition(a, AttemptState.PREPARING)
    machine.transition(a, AttemptState.GENERATING)

    # Lecture directe depuis attempts.
    fresh = repos["attempts"].get(a.id)
    # Lecture de la derniere transition.
    last_transition = repo.last_for_attempt(a.id)

    assert fresh.state == last_transition.to_state
    assert fresh.state == "GENERATING"


def test_transition_failure_leaves_no_partial_state(machine, repos):
    """Une transition invalide ne doit rien modifier en DB."""
    a = _new_attempt(repos)
    repo = StateTransitionRepository(repos["attempts"]._db)

    # On fait un CREATED -> BUILDING directement : INTERDIT.
    with pytest.raises(InvalidTransition):
        machine.transition(a, AttemptState.BUILDING)

    # L'attempt n'a pas change.
    fresh = repos["attempts"].get(a.id)
    assert fresh.state == "CREATED"
    # Aucune transition n'a ete journalisee.
    assert repo.list_for_attempt(a.id) == []


def test_db_record_state_transition_uses_single_transaction(tmp_db_path):
    """Le contrat de :meth:`Database.record_state_transition` est de
    realiser UPDATE + INSERT dans la meme transaction. On verifie ici
    que les deux operations apparaissent en DB apres succes, et qu'on
    peut interroger chaque ligne separement (donc elles ont bien ete
    commitees ensemble)."""
    db = Database(tmp_db_path)
    db.initialize()
    projects = ProjectRepository(db)
    levels = LevelRepository(db)
    tasks = TaskRepository(db)
    attempts = AttemptRepository(db)
    p = projects.create("p")
    lvl = levels.create(p.id, 1, "spec")
    t = tasks.create(lvl.id, "do")
    a = attempts.create(t.id, 1)

    # Appel direct de la methode atomique.
    db.record_state_transition(
        attempt_id=a.id,
        from_state="CREATED",
        to_state="PREPARING",
        previous_state_field=None,
        finished_at=None,
        reason="atomic-test",
    )

    # L'attempt a bien change d'etat.
    fresh = attempts.get(a.id)
    assert fresh.state == "PREPARING"
    # ET une ligne a ete journalisee.
    trans = StateTransitionRepository(db).list_for_attempt(a.id)
    assert len(trans) == 1
    assert trans[0].from_state == "CREATED"
    assert trans[0].to_state == "PREPARING"
    assert trans[0].reason == "atomic-test"
    db.close()


def test_record_state_transition_failure_rolls_back(tmp_db_path):
    """Si l'INSERT dans state_transitions echoue apres l'UPDATE,
    le ROLLBACK doit laisser attempts dans son etat initial."""
    db = Database(tmp_db_path)
    db.initialize()
    projects = ProjectRepository(db)
    levels = LevelRepository(db)
    tasks = TaskRepository(db)
    attempts = AttemptRepository(db)
    p = projects.create("p")
    lvl = levels.create(p.id, 1, "spec")
    t = tasks.create(lvl.id, "do")
    a = attempts.create(t.id, 1)

    # On simule un echec : on renomme temporairement la table
    # state_transitions. L'INSERT echouera (no such table), le
    # ROLLBACK doit annuler l'UPDATE de attempts.
    db.connection.execute("ALTER TABLE state_transitions RENAME TO state_transitions_BAK")

    with pytest.raises(sqlite3.OperationalError):
        db.record_state_transition(
            attempt_id=a.id,
            from_state="CREATED",
            to_state="PREPARING",
            previous_state_field=None,
            finished_at=None,
            reason="x",
        )

    # Le ROLLBACK a annule l'UPDATE.
    fresh = attempts.get(a.id)
    assert fresh.state == "CREATED"

    # On restaure pour ne pas polluer la DB pour les tests suivants.
    db.connection.execute("ALTER TABLE state_transitions_BAK RENAME TO state_transitions")
    db.close()


def test_record_state_transition_is_append_only():
    """StateTransitionRepository ne doit jamais proposer d'update."""
    db = Database("/tmp/test_append_only.db")
    db.initialize()
    repo = StateTransitionRepository(db)
    # Pas de methode update/delete sur le repository.
    for forbidden in ("update", "delete", "modify"):
        assert not hasattr(repo, forbidden), (
            f"StateTransitionRepository ne doit pas exposer '{forbidden}'"
        )
    db.close()


# ----------------------------------------------------------------------
# Recovery avec historique
# ----------------------------------------------------------------------


def test_recovery_works_with_full_history(tmp_db_path):
    """Le scenario BUILDING -> restart -> BUILDING fonctionne avec historique."""
    db1 = Database(tmp_db_path)
    db1.initialize()
    projects = ProjectRepository(db1)
    levels = LevelRepository(db1)
    tasks = TaskRepository(db1)
    attempts = AttemptRepository(db1)
    trans = StateTransitionRepository(db1)

    p = projects.create("recover-hist")
    lvl = levels.create(p.id, 1, "spec")
    projects.set_current_level(p.id, lvl.id)
    t = tasks.create(lvl.id, "t")
    a = attempts.create(t.id, 1)

    machine = AttemptStateMachine(db=db1)
    machine.transition(a, AttemptState.PREPARING)
    machine.transition(a, AttemptState.GENERATING)
    machine.transition(a, AttemptState.BUILDING)
    db1.close()

    # Nouvelle instance.
    db2 = Database(tmp_db_path)
    db2.connect()
    snap = find_active_state(
        ProjectRepository(db2),
        LevelRepository(db2),
        TaskRepository(db2),
        AttemptRepository(db2),
    )
    assert snap.attempt_state == "BUILDING"

    # L'historique est aussi accessible.
    hist = StateTransitionRepository(db2).list_for_attempt(snap.attempt_id)
    assert [t.to_state for t in hist] == ["PREPARING", "GENERATING", "BUILDING"]
    db2.close()


# ----------------------------------------------------------------------
# PAUSED_PROVIDER : regles strictes
# ----------------------------------------------------------------------


PAUSED_ALLOWED_FROM = {
    AttemptState.GENERATING,
    AttemptState.REVIEWING,
    AttemptState.VALIDATING,
}

PAUSED_FORBIDDEN_FROM = {
    AttemptState.CREATED,
    AttemptState.PREPARING,
    AttemptState.BUILDING,
    AttemptState.TESTING,
    AttemptState.RETRY_PENDING,
    AttemptState.APPROVED,
    AttemptState.FAILED_AFTER_RETRIES,
    AttemptState.COMPLETED,
}


def _path_to(target, machine, repos, a):
    """Amene l'attempt jusqu'a l'etat ``target`` via le chemin normal."""
    path = [
        AttemptState.PREPARING,
        AttemptState.GENERATING,
        AttemptState.BUILDING,
        AttemptState.TESTING,
        AttemptState.REVIEWING,
        AttemptState.VALIDATING,
        AttemptState.APPROVED,
        AttemptState.COMPLETED,
    ]
    for s in path:
        machine.transition(a, s)
        if s == target:
            break


@pytest.mark.parametrize("src", sorted(PAUSED_ALLOWED_FROM, key=lambda x: x.value))
def test_paused_allowed_from_state(src, machine, repos):
    a = _new_attempt(repos)
    _path_to(src, machine, repos, a)
    machine.enter_paused(a, reason=f"from-{src.value}")
    assert a.state == "PAUSED_PROVIDER"
    assert a.previous_state == src.value
    # Reprise stricte vers previous_state.
    machine.exit_paused(a)
    assert a.state == src.value


@pytest.mark.parametrize("src", sorted(PAUSED_FORBIDDEN_FROM, key=lambda x: x.value))
def test_paused_forbidden_from_state(src, machine, repos):
    a = _new_attempt(repos)
    # Certains etats ne sont pas atteignables depuis CREATED ;
    # on les force en SQL directement pour le test.
    repos["attempts"].update_state(a.id, state=src.value)
    a = repos["attempts"].get(a.id)
    with pytest.raises(InvalidTransition):
        machine.enter_paused(a, reason="should-fail")


def test_paused_round_trip_three_states(machine, repos):
    """GENERATING -> PAUSED -> GENERATING,
       REVIEWING -> PAUSED -> REVIEWING,
       VALIDATING -> PAUSED -> VALIDATING."""
    for src in (AttemptState.GENERATING, AttemptState.REVIEWING, AttemptState.VALIDATING):
        a = _new_attempt(repos)
        _path_to(src, machine, repos, a)
        machine.enter_paused(a, reason="x")
        assert a.state == "PAUSED_PROVIDER"
        assert a.previous_state == src.value
        machine.exit_paused(a)
        assert a.state == src.value
        assert a.previous_state is None
