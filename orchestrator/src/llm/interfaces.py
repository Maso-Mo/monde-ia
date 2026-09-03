"""
Interfaces / DTOs pour les providers LLM.

Ces structures sont les contrats que tout LLMProvider doit respecter.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Protocol, runtime_checkable


@dataclass(slots=True)
class GenerationResult:
    """Resultat d'un appel ``generator``."""
    text: str
    raw_output_ref: Optional[str] = None
    token_usage: Optional[int] = None
    latency_ms: Optional[int] = None


# Severites possibles pour ReviewResult.severity.
SEVERITY_VALUES: tuple[str, ...] = ("low", "medium", "high", "critical")


@dataclass(slots=True)
class ReviewResult:
    """Resultat d'un appel ``reviewer`` (Qwen 2.5 Coder via FreeLLMAPI).

    Schema JSON attendu (Phase 1.1) :

        {
          "issues_found": ["..."],
          "severity": "low|medium|high|critical",
          "instructions_for_fix": ["..."],
          "retry_needed": true
        }
    """
    issues_found: list[str] = field(default_factory=list)
    severity: str = "low"
    instructions_for_fix: list[str] = field(default_factory=list)
    retry_needed: bool = False
    raw_output_ref: Optional[str] = None
    token_usage: Optional[int] = None
    latency_ms: Optional[int] = None


@dataclass(slots=True)
class ValidationResult:
    """Resultat d'un appel ``validator`` (Qwen 3.6 via FreeLLMAPI).

    Schema JSON attendu (Phase 1.1) :

        {
          "approved": true,
          "score": 0-100,
          "reason": "...",
          "blocking_issues": ["..."]
        }
    """
    approved: bool = False
    score: Optional[int] = None  # 0..100
    reason: Optional[str] = None
    blocking_issues: list[str] = field(default_factory=list)
    raw_output_ref: Optional[str] = None
    token_usage: Optional[int] = None
    latency_ms: Optional[int] = None

    @property
    def status(self) -> str:
        """Compat : renvoie 'approved' ou 'rejected' pour les anciens
        consommateurs (MockCycle, ValidationRepository)."""
        return "approved" if self.approved else "rejected"


@dataclass(slots=True)
class ProviderHealth:
    """Sante d'un provider/model."""
    provider: str
    model: str
    status: str  # up | down | unknown
    detail: Optional[str] = None


@runtime_checkable
class LLMProvider(Protocol):
    """Contrat minimal d'un provider LLM.

    Un provider concret (MockLLMProvider en V1, FreeLLMAPI en V2)
    doit implementer ces trois methodes.
    """

    def generate(
        self,
        *,
        prompt: str,
        role_config: dict,
    ) -> GenerationResult: ...

    def review(
        self,
        *,
        code: str,
        role_config: dict,
    ) -> ReviewResult: ...

    def validate(
        self,
        *,
        code: str,
        role_config: dict,
    ) -> ValidationResult: ...

    def health(self) -> ProviderHealth: ...


__all__ = [
    "GenerationResult",
    "ReviewResult",
    "ValidationResult",
    "ProviderHealth",
    "LLMProvider",
    "SEVERITY_VALUES",
]
