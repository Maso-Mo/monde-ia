"""
Tests de la machine a etats : transitions valides / interdites.
"""

from __future__ import annotations

import pytest

from src.state_machine import (
    AttemptState,
    AttemptStateMachine,
    InvalidTransition,
    StateMachineError,
    allowed_targets,
    is_allowed,
)
from src.memory import Attempt


def _new_attempt(repos, number=1, state="CREATED"):
    p = repos["projects"].create("p")
    lvl = repos["levels"].create(p.id, 1, "spec")
    t = repos["tasks"].create(lvl.id, "do")
    a = repos["attempts"].create(t.id, number)
    if state != "CREATED":
        repos["attempts"].update_state(a.id, state=state)
        a = repos["attempts"].get(a.id)
    return a


# ----------------------------------------------------------------------
# Table de transitions
# ----------------------------------------------------------------------


def test_is_allowed_true_cases():
    assert is_allowed(AttemptState.CREATED, AttemptState.PREPARING)
    assert is_allowed(AttemptState.PREPARING, AttemptState.GENERATING)
    assert is_allowed(AttemptState.GENERATING, AttemptState.BUILDING)
    assert is_allowed(AttemptState.BUILDING, AttemptState.TESTING)
    assert is_allowed(AttemptState.TESTING, AttemptState.REVIEWING)
    assert is_allowed(AttemptState.REVIEWING, AttemptState.VALIDATING)
    assert is_allowed(AttemptState.VALIDATING, AttemptState.APPROVED)
    assert is_allowed(AttemptState.APPROVED, AttemptState.COMPLETED)
    assert is_allowed(AttemptState.VALIDATING, AttemptState.RETRY_PENDING)
    assert is_allowed(AttemptState.RETRY_PENDING, AttemptState.COMPLETED)
    assert is_allowed(AttemptState.RETRY_PENDING, AttemptState.FAILED_AFTER_RETRIES)
    assert is_allowed(AttemptState.FAILED_AFTER_RETRIES, AttemptState.COMPLETED)


def test_is_allowed_false_cases():
    # Sauts illegaux
    assert not is_allowed(AttemptState.CREATED, AttemptState.BUILDING)
    assert not is_allowed(AttemptState.BUILDING, AttemptState.APPROVED)
    assert not is_allowed(AttemptState.REVIEWING, AttemptState.COMPLETED)
    # COMPLETED est terminal
    assert not is_allowed(AttemptState.COMPLETED, AttemptState.GENERATING)
    assert not is_allowed(AttemptState.COMPLETED, AttemptState.PREPARING)
    # Pas de transition inverse sauf PAUSED_PROVIDER gere separement
    assert not is_allowed(AttemptState.GENERATING, AttemptState.PREPARING)


def test_allowed_targets_is_immutable():
    s = allowed_targets(AttemptState.BUILDING)
    assert AttemptState.TESTING in s
    # frozenset n'est pas mutable
    with pytest.raises(AttributeError):
        s.add(AttemptState.CREATED)  # type: ignore[attr-defined]


# ----------------------------------------------------------------------
# Transitions reelles
# ----------------------------------------------------------------------


def test_full_happy_path(machine, repos):
    a = _new_attempt(repos)
    machine.transition(a, AttemptState.PREPARING)
    machine.transition(a, AttemptState.GENERATING)
    machine.transition(a, AttemptState.BUILDING)
    machine.transition(a, AttemptState.TESTING)
    machine.transition(a, AttemptState.REVIEWING)
    machine.transition(a, AttemptState.VALIDATING)
    machine.transition(a, AttemptState.APPROVED)
    result = machine.transition(a, AttemptState.COMPLETED)
    assert result.finished is True
    assert result.from_state == "APPROVED"
    assert result.to_state == "COMPLETED"


def test_retry_pending_path(machine, repos):
    a = _new_attempt(repos)
    machine.transition(a, AttemptState.PREPARING)
    machine.transition(a, AttemptState.GENERATING)
    # Build KO -> RETRY_PENDING
    machine.transition(a, AttemptState.RETRY_PENDING)
    machine.transition(a, AttemptState.COMPLETED)
    assert a.state == "COMPLETED"


def test_invalid_transition_raises(machine, repos):
    a = _new_attempt(repos)
    # CREATED -> BUILDING directement n'est pas autorise
    with pytest.raises(InvalidTransition):
        machine.transition(a, AttemptState.BUILDING)


def test_completed_is_terminal(machine, repos):
    a = _new_attempt(repos)
    machine.transition(a, AttemptState.PREPARING)
    machine.transition(a, AttemptState.GENERATING)
    machine.transition(a, AttemptState.BUILDING)
    machine.transition(a, AttemptState.TESTING)
    machine.transition(a, AttemptState.REVIEWING)
    machine.transition(a, AttemptState.VALIDATING)
    machine.transition(a, AttemptState.APPROVED)
    machine.transition(a, AttemptState.COMPLETED)
    with pytest.raises(InvalidTransition):
        machine.transition(a, AttemptState.GENERATING)


def test_transition_without_persisted_id(machine):
    a = Attempt(id=None, task_id=1, attempt_number=1)
    with pytest.raises(StateMachineError):
        machine.transition(a, AttemptState.PREPARING)


def test_failed_after_retries(machine, repos):
    a = _new_attempt(repos, number=3)
    machine.transition(a, AttemptState.PREPARING)
    machine.transition(a, AttemptState.GENERATING)
    machine.transition(a, AttemptState.RETRY_PENDING)
    machine.transition(a, AttemptState.FAILED_AFTER_RETRIES)
    result = machine.transition(a, AttemptState.COMPLETED)
    assert result.finished is True
    assert a.state == "COMPLETED"


# ----------------------------------------------------------------------
# PAUSED_PROVIDER
# ----------------------------------------------------------------------


def test_paused_provider_preserves_previous_state(machine, repos):
    a = _new_attempt(repos)
    machine.transition(a, AttemptState.PREPARING)
    machine.transition(a, AttemptState.GENERATING)
    machine.enter_paused(a, reason="provider down")
    assert a.state == "PAUSED_PROVIDER"
    assert a.previous_state == "GENERATING"
    # L'etat est bien persiste en DB
    refreshed = repos["attempts"].get(a.id)
    assert refreshed.state == "PAUSED_PROVIDER"
    assert refreshed.previous_state == "GENERATING"


def test_paused_provider_return_to_previous_state(machine, repos):
    a = _new_attempt(repos)
    machine.transition(a, AttemptState.PREPARING)
    machine.transition(a, AttemptState.GENERATING)
    machine.enter_paused(a, reason="rate limit")
    # Reprise -> retour a GENERATING
    machine.exit_paused(a)
    assert a.state == "GENERATING"
    assert a.previous_state is None
    refreshed = repos["attempts"].get(a.id)
    assert refreshed.state == "GENERATING"
    assert refreshed.previous_state is None


def test_exit_paused_strictly_returns_to_previous_state(machine, repos):
    """Phase 1.1 : exit_paused retourne strictement vers previous_state.

    Aucune cible arbitraire n'est acceptee. La machine reprend
    exactement la ou elle s'etait arretee.
    """
    a = _new_attempt(repos)
    machine.transition(a, AttemptState.PREPARING)
    machine.transition(a, AttemptState.GENERATING)
    machine.enter_paused(a, reason="x")
    machine.exit_paused(a)
    # previous_state etait GENERATING ; on y revient forcement.
    assert a.state == "GENERATING"
    assert a.previous_state is None


def test_exit_paused_without_previous_state_raises(machine, repos):
    a = _new_attempt(repos)
    # Forcer l'etat PAUSED_PROVIDER avec previous_state=None
    repos["attempts"].update_state(a.id, state="PAUSED_PROVIDER", previous_state=None)
    a = repos["attempts"].get(a.id)
    with pytest.raises(StateMachineError):
        machine.exit_paused(a)


def test_exit_paused_when_not_paused_raises(machine, repos):
    a = _new_attempt(repos)
    machine.transition(a, AttemptState.PREPARING)
    with pytest.raises(StateMachineError):
        machine.exit_paused(a)


def test_enter_paused_from_completed_raises(machine, repos):
    a = _new_attempt(repos)
    machine.transition(a, AttemptState.PREPARING)
    machine.transition(a, AttemptState.GENERATING)
    machine.transition(a, AttemptState.BUILDING)
    machine.transition(a, AttemptState.TESTING)
    machine.transition(a, AttemptState.REVIEWING)
    machine.transition(a, AttemptState.VALIDATING)
    machine.transition(a, AttemptState.APPROVED)
    machine.transition(a, AttemptState.COMPLETED)
    with pytest.raises(InvalidTransition):
        machine.enter_paused(a)


# ----------------------------------------------------------------------
# Persistance
# ----------------------------------------------------------------------


def test_transitions_are_persisted(machine, repos):
    a = _new_attempt(repos)
    machine.transition(a, AttemptState.PREPARING)
    machine.transition(a, AttemptState.GENERATING)
    machine.transition(a, AttemptState.BUILDING)
    # Lecture directe en DB : on doit voir BUILDING, previous_state=NULL
    row = repos["attempts"].get(a.id)
    assert row.state == "BUILDING"
    assert row.previous_state is None
