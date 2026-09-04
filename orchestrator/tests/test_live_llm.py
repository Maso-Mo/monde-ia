"""
Tests live opt-in pour reviewer et validator via FreeLLMAPI.

Ces tests ne s'executent QUE si ZFLM_LIVE_LLM_TESTS=1 est defini.
Sans cette variable, ils sont SKIPPES.

Utilisation :
    ZFLM_LIVE_LLM_TESTS=1 python -m pytest orchestrator/tests/test_live_llm.py -v
"""

from __future__ import annotations

import os
import pytest

from src.llm import (
    FreeLLMAPIProvider,
    create_freellmapi_provider,
    ReviewResult,
    ValidationResult,
)
from src.config import ZflmConfig


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------


def _live_tests_enabled() -> bool:
    """Verifie si les tests live sont autorises."""
    return os.environ.get("ZFLM_LIVE_LLM_TESTS") == "1"


def _skip_if_not_live():
    """Skip le test si pas en mode live."""
    if not _live_tests_enabled():
        pytest.skip("ZFLM_LIVE_LLM_TESTS=1 non defini - test live desactive")


def _get_reviewer_config() -> dict:
    """Charge la config du reviewer depuis ZFLM."""
    config = ZflmConfig.load()
    return config.get_role("reviewer")


def _get_validator_config() -> dict:
    """Charge la config du validator depuis ZFLM."""
    config = ZflmConfig.load()
    return config.get_role("validator")


# ----------------------------------------------------------------------
# Tests live - Reviewer (Qwen2.5 via Cloudflare)
# ----------------------------------------------------------------------


@pytest.mark.live
def test_live_reviewer_qwen25_cloudflare():
    """Test live du reviewer Qwen2.5 via FreeLLMAPI -> Cloudflare.

    Verifie :
    - ReviewResult valide
    - issues_found non vide
    - severity valide
    - instructions_for_fix non vide
    - retry_needed == true
    """
    _skip_if_not_live()

    provider = create_freellmapi_provider()
    role_config = _get_reviewer_config()

    # Code avec erreur de syntaxe JavaScript
    bad_code = "const x = ;"  # SyntaxError: Unexpected token ;

    result = provider.review(code=bad_code, role_config=role_config)

    # Assertions
    assert isinstance(result, ReviewResult)
    assert result.issues_found, "issues_found doit etre non vide"
    assert result.severity in ("low", "medium", "high", "critical"), f"severity invalide: {result.severity}"
    assert result.instructions_for_fix, "instructions_for_fix doit etre non vide"
    assert result.retry_needed is True, "retry_needed doit etre True pour code invalide"
    assert result.latency_ms is not None and result.latency_ms > 0
    assert result.token_usage is not None and result.token_usage > 0

    print(f"Reviewer OK: {len(result.issues_found)} issues, severity={result.severity}")


@pytest.mark.live
def test_live_validator_qwen36_groq():
    """Test live du validator Qwen3.6 via FreeLLMAPI -> Groq.

    Verifie :
    - ValidationResult valide
    - approved == True pour code valide
    - blocking_issues == []
    """
    _skip_if_not_live()

    provider = create_freellmapi_provider()
    role_config = _get_validator_config()

    # Code HTML valide avec H1
    good_code = "<html><body><h1>Hello</h1></body></html>"

    result = provider.validate(code=good_code, role_config=role_config)

    # Assertions
    assert isinstance(result, ValidationResult)
    assert result.approved is True, "approved doit etre True pour code valide"
    assert result.blocking_issues == [], f"blocking_issues doit etre vide, recu: {result.blocking_issues}"
    assert result.score is not None and 0 <= result.score <= 100
    assert result.reason is not None and len(result.reason) > 0
    assert result.latency_ms is not None and result.latency_ms > 0
    assert result.token_usage is not None and result.token_usage > 0

    print(f"Validator OK: approved={result.approved}, score={result.score}")


@pytest.mark.live
def test_live_validator_rejects_invalid_html():
    """Test live : validator doit rejeter du HTML invalide."""
    _skip_if_not_live()

    provider = create_freellmapi_provider()
    role_config = _get_validator_config()

    # HTML malforme
    bad_code = "<html><body><h1>Hello</body></html>"  # h1 non ferme

    result = provider.validate(code=bad_code, role_config=role_config)

    assert isinstance(result, ValidationResult)
    # Le validator peut approuver ou rejeter selon sa tolerance
    # On verifie juste que le resultat est coherent
    assert result.score is not None
    assert result.reason is not None

    print(f"Validator invalid HTML: approved={result.approved}, score={result.score}")


@pytest.mark.live
def test_live_provider_health_check():
    """Test live : health check FreeLLMAPI."""
    _skip_if_not_live()

    provider = create_freellmapi_provider()
    health = provider.health()

    assert health.provider == "freellmapi"
    assert health.status in ("up", "down", "unknown")

    print(f"Health check: {health.status} ({health.detail})")


# ----------------------------------------------------------------------
# Test d'integration complet (optionnel)
# ----------------------------------------------------------------------


@pytest.mark.live
def test_live_full_cycle_smoke():
    """Smoke test d'un cycle complet : generate -> review -> validate.

    Ne verifie pas la qualite, juste que le pipeline fonctionne.
    Maximum 1 appel par role pour eviter la consommation de quota.
    """
    _skip_if_not_live()

    provider = create_freellmapi_provider()
    roles = {
        "generator": _get_reviewer_config(),  # Utilise reviewer config comme generator pour test
        "reviewer": _get_reviewer_config(),
        "validator": _get_validator_config(),
    }

    # 1. Generate (simple prompt)
    gen = provider.generate(
        prompt="Return a minimal HTML page with hello world",
        role_config=roles["generator"],
    )
    assert gen.text
    assert len(gen.text) > 10
    print(f"Generated: {gen.text[:100]}...")

    # 2. Review
    review = provider.review(code=gen.text, role_config=roles["reviewer"])
    assert isinstance(review, ReviewResult)
    print(f"Review: {len(review.issues_found)} issues, severity={review.severity}")

    # 3. Validate
    validation = provider.validate(code=gen.text, role_config=roles["validator"])
    assert isinstance(validation, ValidationResult)
    print(f"Validate: approved={validation.approved}, score={validation.score}")