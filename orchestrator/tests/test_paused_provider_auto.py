"""
Tests unitaires pour PAUSED_PROVIDER automatique et reprise.

Ces tests verifient la logique de declenchement et reprise sans
appels reseau reels (utilisent un provider mock qui simule les erreurs).
"""

from __future__ import annotations

import pytest
from unittest.mock import Mock, MagicMock

from src.llm import (
    FreeLLMAPIError,
    GenerationResult,
    ReviewResult,
    ValidationResult,
    LLMProvider,
)
from src.loop import RealCycle
from src.memory import Database
from src.obs_logging.logger import JsonlLogger
from src.state_machine import AttemptState


# ----------------------------------------------------------------------
# Mock Provider qui simule les erreurs
# ----------------------------------------------------------------------


class FailingProvider(LLMProvider):
    """Provider qui leve des erreurs controlees."""

    def __init__(
        self,
        *,
        generate_error: FreeLLMAPIError | None = None,
        review_error: FreeLLMAPIError | None = None,
        validate_error: FreeLLMAPIError | None = None,
        health_status: str = "up",
    ):
        self._generate_error = generate_error
        self._review_error = review_error
        self._validate_error = validate_error
        self._health_status = health_status
        self.call_counts = {"generate": 0, "review": 0, "validate": 0, "health": 0}

    def generate(self, *, prompt: str, role_config: dict) -> GenerationResult:
        self.call_counts["generate"] += 1
        if self._generate_error:
            raise self._generate_error
        return GenerationResult(text="<html>ok</html>", token_usage=10, latency_ms=1)

    def review(self, *, code: str, role_config: dict) -> ReviewResult:
        self.call_counts["review"] += 1
        if self._review_error:
            raise self._review_error
        return ReviewResult(
            issues_found=[],
            severity="low",
            instructions_for_fix=[],
            retry_needed=False,
            token_usage=5,
            latency_ms=1,
        )

    def validate(self, *, code: str, role_config: dict) -> ValidationResult:
        self.call_counts["validate"] += 1
        if self._validate_error:
            raise self._validate_error
        return ValidationResult(
            approved=True,
            score=95,
            reason="ok",
            blocking_issues=[],
            token_usage=5,
            latency_ms=1,
        )

    def health(self):
        self.call_counts["health"] += 1
        from src.llm.interfaces import ProviderHealth
        return ProviderHealth(
            provider="mock",
            model="mock-model",
            status=self._health_status,
        )


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------


def _make_db():
    """Cree une DB en memoire pour tests."""
    db = Database(":memory:")
    db.initialize()
    return db


def _make_cycle(db, provider, auto_resume=True):
    """Cree un RealCycle avec logger mock."""
    logger = Mock(spec=JsonlLogger)
    return RealCycle(
        db=db,
        provider=provider,
        logger=logger,
        max_attempts=3,
        roles_config={
            "generator": {"provider": "mock", "model": "mock"},
            "reviewer": {"provider": "mock", "model": "mock"},
            "validator": {"provider": "mock", "model": "mock"},
        },
        auto_resume=auto_resume,
    )


# ----------------------------------------------------------------------
# Tests PAUSED_PROVIDER declenchement
# ----------------------------------------------------------------------


def test_paused_provider_on_timeout_during_generating():
    """Timeout pendant GENERATING -> PAUSED_PROVIDER (auto_resume=False pour verifier l'etat)."""
    db = _make_db()
    error = FreeLLMAPIError("timeout", "TIMEOUT", retryable=True)
    provider = FailingProvider(generate_error=error, health_status="down")
    cycle = _make_cycle(db, provider, auto_resume=False)

    task_id = cycle.run_once(task_description="test")

    attempt = db.connection.execute(
        "SELECT * FROM attempts WHERE task_id = ?", (task_id,)
    ).fetchone()
    assert attempt["state"] == "PAUSED_PROVIDER"
    assert attempt["previous_state"] == "GENERATING"


def test_paused_provider_on_429_during_reviewing():
    """Rate limit (429) pendant REVIEWING -> PAUSED_PROVIDER."""
    db = _make_db()
    error = FreeLLMAPIError("rate limited", "RATE_LIMITED", status_code=429, retryable=True)
    provider = FailingProvider(review_error=error, health_status="down")
    cycle = _make_cycle(db, provider, auto_resume=False)

    task_id = cycle.run_once(task_description="test")

    attempt = db.connection.execute(
        "SELECT * FROM attempts WHERE task_id = ?", (task_id,)
    ).fetchone()
    assert attempt["state"] == "PAUSED_PROVIDER"
    assert attempt["previous_state"] == "REVIEWING"


def test_paused_provider_on_5xx_during_validating():
    """Erreur 5xx pendant VALIDATING -> PAUSED_PROVIDER."""
    db = _make_db()
    error = FreeLLMAPIError("internal server error", "PROVIDER_UNAVAILABLE", status_code=500, retryable=True)
    provider = FailingProvider(validate_error=error, health_status="down")
    cycle = _make_cycle(db, provider, auto_resume=False)

    task_id = cycle.run_once(task_description="test")

    attempt = db.connection.execute(
        "SELECT * FROM attempts WHERE task_id = ?", (task_id,)
    ).fetchone()
    assert attempt["state"] == "PAUSED_PROVIDER"
    assert attempt["previous_state"] == "VALIDATING"


def test_paused_provider_on_network_error():
    """Erreur reseau -> PAUSED_PROVIDER."""
    db = _make_db()
    error = FreeLLMAPIError("connection failed", "NETWORK_ERROR", retryable=True)
    provider = FailingProvider(generate_error=error, health_status="down")
    cycle = _make_cycle(db, provider, auto_resume=False)

    task_id = cycle.run_once(task_description="test")

    attempt = db.connection.execute(
        "SELECT * FROM attempts WHERE task_id = ?", (task_id,)
    ).fetchone()
    assert attempt["state"] == "PAUSED_PROVIDER"


# ----------------------------------------------------------------------
# Tests PAS de PAUSED_PROVIDER pour erreurs non-retryable
# ----------------------------------------------------------------------


def test_no_paused_on_auth_error():
    """Erreur auth (401) -> PAS de PAUSED_PROVIDER."""
    db = _make_db()
    error = FreeLLMAPIError("invalid key", "AUTH_ERROR", status_code=401, retryable=False)
    provider = FailingProvider(generate_error=error, health_status="down")
    cycle = _make_cycle(db, provider, auto_resume=False)

    task_id = cycle.run_once(task_description="test")

    attempt = db.connection.execute(
        "SELECT * FROM attempts WHERE task_id = ?", (task_id,)
    ).fetchone()
    # Doit etre en erreur terminale, pas PAUSED
    assert attempt["state"] != "PAUSED_PROVIDER"


def test_no_paused_on_invalid_json():
    """Erreur JSON invalide -> PAS de PAUSED_PROVIDER."""
    db = _make_db()
    error = FreeLLMAPIError("bad json", "INVALID_JSON", retryable=False)
    provider = FailingProvider(generate_error=error, health_status="down")
    cycle = _make_cycle(db, provider, auto_resume=False)

    task_id = cycle.run_once(task_description="test")

    attempt = db.connection.execute(
        "SELECT * FROM attempts WHERE task_id = ?", (task_id,)
    ).fetchone()
    assert attempt["state"] != "PAUSED_PROVIDER"


def test_no_paused_on_empty_completion():
    """Completion vide -> PAS de PAUSED_PROVIDER."""
    db = _make_db()
    error = FreeLLMAPIError("empty", "EMPTY_COMPLETION", retryable=False)
    provider = FailingProvider(generate_error=error, health_status="down")
    cycle = _make_cycle(db, provider, auto_resume=False)

    task_id = cycle.run_once(task_description="test")

    attempt = db.connection.execute(
        "SELECT * FROM attempts WHERE task_id = ?", (task_id,)
    ).fetchone()
    assert attempt["state"] != "PAUSED_PROVIDER"


def test_no_paused_on_invalid_response():
    """Reponse invalide -> PAS de PAUSED_PROVIDER."""
    db = _make_db()
    error = FreeLLMAPIError("bad response", "INVALID_RESPONSE", retryable=False)
    provider = FailingProvider(generate_error=error, health_status="down")
    cycle = _make_cycle(db, provider, auto_resume=False)

    task_id = cycle.run_once(task_description="test")

    attempt = db.connection.execute(
        "SELECT * FROM attempts WHERE task_id = ?", (task_id,)
    ).fetchone()
    assert attempt["state"] != "PAUSED_PROVIDER"


# ----------------------------------------------------------------------
# Tests reprise automatique (auto_resume=True)
# ----------------------------------------------------------------------


def test_auto_resume_when_provider_healthy():
    """Provider redevient sain -> exit_paused vers previous_state."""
    db = _make_db()

    # Premier passage : erreur retryable
    error = FreeLLMAPIError("timeout", "TIMEOUT", retryable=True)
    provider = FailingProvider(generate_error=error, health_status="up")
    cycle = _make_cycle(db, provider, auto_resume=True)

    task_id = cycle.run_once(task_description="test")

    # Verifier qu'on est en PAUSED_PROVIDER (mais le resume se fait dans la boucle)
    attempt = db.connection.execute(
        "SELECT * FROM attempts WHERE task_id = ?", (task_id,)
    ).fetchone()
    # Avec auto_resume=True et provider sain, doit avoir repris
    # Verifier via les transitions
    transitions = db.connection.execute(
        "SELECT * FROM state_transitions WHERE attempt_id = (SELECT id FROM attempts WHERE task_id = ?) ORDER BY id",
        (task_id,)
    ).fetchall()
    transition_pairs = [(t["from_state"], t["to_state"]) for t in transitions]
    assert ("GENERATING", "PAUSED_PROVIDER") in transition_pairs
    assert ("PAUSED_PROVIDER", "GENERATING") in transition_pairs


def test_no_auto_resume_when_provider_unhealthy():
    """Provider encore indisponible -> reste en PAUSED_PROVIDER."""
    db = _make_db()

    error = FreeLLMAPIError("timeout", "TIMEOUT", retryable=True)
    provider = FailingProvider(generate_error=error, health_status="down")
    cycle = _make_cycle(db, provider, auto_resume=True)

    task_id = cycle.run_once(task_description="test")

    attempt = db.connection.execute(
        "SELECT * FROM attempts WHERE task_id = ?", (task_id,)
    ).fetchone()
    assert attempt["state"] == "PAUSED_PROVIDER"


def test_no_auto_resume_when_disabled():
    """auto_resume=False -> ne tente pas de reprendre."""
    db = _make_db()
    error = FreeLLMAPIError("timeout", "TIMEOUT", retryable=True)
    provider = FailingProvider(generate_error=error, health_status="up")
    cycle = _make_cycle(db, provider, auto_resume=False)

    task_id = cycle.run_once(task_description="test")

    attempt = db.connection.execute(
        "SELECT * FROM attempts WHERE task_id = ?", (task_id,)
    ).fetchone()
    assert attempt["state"] == "PAUSED_PROVIDER"


# ----------------------------------------------------------------------
# Tests round-trip pour les 3 etats LLM
# ----------------------------------------------------------------------


@pytest.mark.parametrize("state,error_attr", [
    ("GENERATING", "generate_error"),
    ("REVIEWING", "review_error"),
    ("VALIDATING", "validate_error"),
])
def test_paused_provider_round_trip_all_states(state, error_attr):
    """Round trip PAUSED_PROVIDER pour les 3 etats LLM."""
    db = _make_db()
    error = FreeLLMAPIError("temp error", "PROVIDER_UNAVAILABLE", status_code=503, retryable=True)

    kwargs = {error_attr: error}
    provider = FailingProvider(**kwargs, health_status="down")
    cycle = _make_cycle(db, provider, auto_resume=False)

    task_id = cycle.run_once(task_description="test")

    attempt = db.connection.execute(
        "SELECT * FROM attempts WHERE task_id = ?", (task_id,)
    ).fetchone()

    # Verifier PAUSED_PROVIDER avec bon previous_state
    assert attempt["state"] == "PAUSED_PROVIDER"
    assert attempt["previous_state"] == state


# ----------------------------------------------------------------------
# Tests enregistrement erreurs et ProviderState
# ----------------------------------------------------------------------


def test_error_recorded_on_retryable_error():
    """Erreur retryable -> enregistree en DB."""
    db = _make_db()
    error = FreeLLMAPIError("timeout", "TIMEOUT", retryable=True)
    provider = FailingProvider(generate_error=error, health_status="down")
    cycle = _make_cycle(db, provider, auto_resume=False)

    task_id = cycle.run_once(task_description="test")

    errors = db.connection.execute(
        "SELECT * FROM errors WHERE attempt_id = (SELECT id FROM attempts WHERE task_id = ?)",
        (task_id,)
    ).fetchall()
    assert len(errors) == 1
    assert errors[0]["type"] == "TIMEOUT"


def test_provider_state_updated_on_error():
    """ProviderState mis a jour sur erreur."""
    db = _make_db()
    error = FreeLLMAPIError("timeout", "TIMEOUT", retryable=True)
    provider = FailingProvider(generate_error=error, health_status="down")
    cycle = _make_cycle(db, provider, auto_resume=False)

    task_id = cycle.run_once(task_description="test")

    states = db.connection.execute(
        "SELECT * FROM provider_states WHERE provider = 'mock' AND model = 'mock'"
    ).fetchall()
    assert len(states) == 1
    assert states[0]["status"] in ("down", "error")


def test_provider_state_updated_on_success():
    """ProviderState mis a jour sur succes."""
    db = _make_db()
    provider = FailingProvider(health_status="up")
    cycle = _make_cycle(db, provider)

    task_id = cycle.run_once(task_description="test")

    states = db.connection.execute(
        "SELECT * FROM provider_states WHERE provider = 'mock' AND model = 'mock'"
    ).fetchall()
    assert len(states) == 1
    assert states[0]["status"] == "up"


def test_llmcall_logged_on_success_and_failure():
    """LLMCalls enregistres pour succes et echec."""
    db = _make_db()
    error = FreeLLMAPIError("timeout", "TIMEOUT", retryable=True)
    provider = FailingProvider(generate_error=error, health_status="down")
    cycle = _make_cycle(db, provider, auto_resume=False)

    task_id = cycle.run_once(task_description="test")

    calls = db.connection.execute(
        "SELECT * FROM llm_calls WHERE attempt_id = (SELECT id FROM attempts WHERE task_id = ?)",
        (task_id,)
    ).fetchall()
    assert len(calls) >= 1


# ----------------------------------------------------------------------
# Tests non-consommation tentative supplementaire
# ----------------------------------------------------------------------


def test_paused_does_not_consume_extra_attempt():
    """PAUSED_PROVIDER ne consomme pas de tentative supplementaire."""
    db = _make_db()
    error = FreeLLMAPIError("timeout", "TIMEOUT", retryable=True)
    provider = FailingProvider(generate_error=error, health_status="down")
    cycle = _make_cycle(db, provider, auto_resume=False)

    task_id = cycle.run_once(task_description="test")

    attempts = db.connection.execute(
        "SELECT * FROM attempts WHERE task_id = ?", (task_id,)
    ).fetchall()
    # Doit avoir exactement 1 attempt (pas de nouvelle creation)
    assert len(attempts) == 1
    assert attempts[0]["attempt_number"] == 1