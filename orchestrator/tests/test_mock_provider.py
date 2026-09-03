"""
Tests du MockLLMProvider.
"""

from __future__ import annotations

from src.llm import (
    GenerationResult,
    MockLLMProvider,
    ProviderHealth,
    ReviewResult,
    ValidationResult,
)


def test_generate_records_call():
    p = MockLLMProvider()
    res = p.generate(prompt="hi", role_config={})
    assert isinstance(res, GenerationResult)
    assert len(p.calls) == 1
    assert p.calls[0].role == "generator"


def test_review_records_call():
    p = MockLLMProvider()
    res = p.review(code="<html/>", role_config={})
    assert isinstance(res, ReviewResult)
    assert p.calls[0].role == "reviewer"


def test_validate_records_call():
    p = MockLLMProvider()
    res = p.validate(code="<html/>", role_config={})
    assert isinstance(res, ValidationResult)
    assert res.status == "approved"


def test_health_up_by_default():
    p = MockLLMProvider()
    h = p.health()
    assert isinstance(h, ProviderHealth)
    assert h.status == "up"


def test_health_can_be_set_down():
    p = MockLLMProvider(health_status="down")
    assert p.health().status == "down"


def test_validation_can_be_reprogrammed():
    p = MockLLMProvider()
    p.set_validation(ValidationResult(approved=False, reason="bad"))
    res = p.validate(code="x", role_config={})
    assert res.status == "rejected"


def test_call_history_order():
    p = MockLLMProvider()
    p.generate(prompt="1", role_config={})
    p.review(code="2", role_config={})
    p.validate(code="3", role_config={})
    assert [c.role for c in p.calls] == ["generator", "reviewer", "validator"]


def test_provider_satisfies_protocol():
    from src.llm.interfaces import LLMProvider
    p = MockLLMProvider()
    # isinstance avec Protocol fonctionne seulement avec @runtime_checkable
    assert isinstance(p, LLMProvider)
