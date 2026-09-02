"""
MockLLMProvider : implementation de test pour V1.

Ce provider :
- ne fait AUCUN appel reseau ;
- repond de maniere deterministe selon le contenu du prompt ;
- permet de simuler succes / echec selon un scenario programmable ;
- enregistre chaque appel pour les assertions de test.

C'est le provider utilise par tous les tests Phase 1.
En Phase 2 il sera remplace (ou complete) par FreeLLMAPIProvider.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Optional

from .interfaces import (
    GenerationResult,
    ProviderHealth,
    ReviewResult,
    ValidationResult,
)


@dataclass
class MockCall:
    """Trace d'un appel mock pour assertions."""
    role: str
    prompt: str
    result: object
    latency_ms: int


class MockLLMProvider:
    """Provider de test, configurable par un scenario."""

    def __init__(
        self,
        *,
        generate_result: Optional[GenerationResult] = None,
        review_result: Optional[ReviewResult] = None,
        validation_result: Optional[ValidationResult] = None,
        health_status: str = "up",
        latency_ms: int = 1,
    ):
        self._generate_result = generate_result or GenerationResult(
            text="<html><!-- generated --></html>",
            token_usage=42,
            latency_ms=latency_ms,
        )
        self._review_result = review_result or ReviewResult(
            issues_found=[],
            instructions_for_fix=None,
            token_usage=12,
            latency_ms=latency_ms,
        )
        self._validation_result = validation_result or ValidationResult(
            status="approved",
            score=1.0,
            reason="Mock approve",
            blocking_issues=[],
            token_usage=10,
            latency_ms=latency_ms,
        )
        self._health_status = health_status
        self._latency = latency_ms
        self.calls: list[MockCall] = []

    # ------------------------------------------------------------------
    # API
    # ------------------------------------------------------------------

    def generate(self, *, prompt: str, role_config: dict) -> GenerationResult:
        result = self._generate_result
        self._record("generator", prompt, result)
        return result

    def review(self, *, code: str, role_config: dict) -> ReviewResult:
        result = self._review_result
        self._record("reviewer", code, result)
        return result

    def validate(self, *, code: str, role_config: dict) -> ValidationResult:
        result = self._validation_result
        self._record("validator", code, result)
        return result

    def health(self) -> ProviderHealth:
        return ProviderHealth(
            provider="mock",
            model="mock-model",
            status=self._health_status,
        )

    # ------------------------------------------------------------------
    # Outils
    # ------------------------------------------------------------------

    def _record(self, role: str, payload: str, result: object) -> None:
        self.calls.append(
            MockCall(
                role=role,
                prompt=payload,
                result=result,
                latency_ms=self._latency,
            )
        )

    def set_validation(self, result: ValidationResult) -> None:
        """Permet de changer le verdict de validation en cours de scenario."""
        self._validation_result = result

    def set_generate(self, result: GenerationResult) -> None:
        self._generate_result = result

    def set_review(self, result: ReviewResult) -> None:
        self._review_result = result

    def set_health(self, status: str) -> None:
        self._health_status = status


__all__ = ["MockLLMProvider", "MockCall"]
