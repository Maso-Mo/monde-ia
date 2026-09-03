"""
Tests specifiques a PAUSED_PROVIDER : entree, sortie, idempotence,
combinaison avec une reprise d'orchestration reelle.
"""

from __future__ import annotations

import pytest

from src.state_machine import (
    AttemptState,
    AttemptStateMachine,
    InvalidTransition,
    StateMachineError,
)


def _new_attempt(repos):
    p = repos["projects"].create("p")
    lvl = repos["levels"].create(p.id, 1, "spec")
    t = repos["tasks"].create(lvl.id, "do")
    return repos["attempts"].create(t.id, 1)


def test_pause_at_each_llm_state(machine, repos):
    """Le provider peut declencher une pause aux etats LLM (Phase 1.1).

    Seuls GENERATING, REVIEWING et VALIDATING peuvent entrer en
    PAUSED_PROVIDER (cf. table de transitions stricte).
    """
    llm_states = [
        AttemptState.GENERATING,
        AttemptState.REVIEWING,
        AttemptState.VALIDATING,
    ]
    for target in llm_states:
        a = _new_attempt(repos)
        # Amene l'attempt jusqu'a target.
        path = [
            AttemptState.PREPARING,
            AttemptState.GENERATING,
            AttemptState.BUILDING,
            AttemptState.TESTING,
            AttemptState.REVIEWING,
            AttemptState.VALIDATING,
        ]
        for s in path:
            machine.transition(a, s)
            if s == target:
                break
        # Pause
        machine.enter_paused(a, reason=f"paused at {target.value}")
        assert a.state == "PAUSED_PROVIDER"
        assert a.previous_state == target.value
        # Reprise (vers previous_state uniquement)
        machine.exit_paused(a)
        assert a.state == target.value
        assert a.previous_state is None


def test_pause_then_resume_then_complete(machine, repos):
    a = _new_attempt(repos)
    machine.transition(a, AttemptState.PREPARING)
    machine.transition(a, AttemptState.GENERATING)
    machine.enter_paused(a, reason="net blip")
    machine.exit_paused(a)
    # On peut continuer normalement
    machine.transition(a, AttemptState.BUILDING)
    machine.transition(a, AttemptState.TESTING)
    machine.transition(a, AttemptState.REVIEWING)
    machine.transition(a, AttemptState.VALIDATING)
    machine.transition(a, AttemptState.APPROVED)
    result = machine.transition(a, AttemptState.COMPLETED)
    assert result.finished


def test_multiple_consecutive_pauses(machine, repos):
    """On peut pauser / reprendre plusieurs fois dans une meme Attempt."""
    a = _new_attempt(repos)
    machine.transition(a, AttemptState.PREPARING)
    machine.transition(a, AttemptState.GENERATING)
    machine.enter_paused(a, reason="1st")
    machine.exit_paused(a)
    machine.enter_paused(a, reason="2nd")
    machine.exit_paused(a)
    machine.enter_paused(a, reason="3rd")
    machine.exit_paused(a)
    assert a.state == "GENERATING"


def test_cannot_pause_after_completed(machine, repos):
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


def test_exit_paused_signature_rejects_arbitrary_target(machine, repos):
    """Phase 1.1 : exit_paused ne prend plus de target arbitraire.

    La sortie est strictement vers previous_state. On verifie ici
    que la signature n'accepte qu'un seul argument (l'attempt).
    """
    a = _new_attempt(repos)
    machine.transition(a, AttemptState.PREPARING)
    machine.transition(a, AttemptState.GENERATING)
    machine.enter_paused(a)
    # La signature ne doit pas accepter de second argument.
    with pytest.raises(TypeError):
        machine.exit_paused(a, AttemptState.REVIEWING)  # type: ignore[misc]
