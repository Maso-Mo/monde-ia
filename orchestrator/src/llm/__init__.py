"""orchestrator.src.llm

Interfaces et provider mock pour les appels LLM.

Voir :

- :mod:`.interfaces` : GenerationResult, ReviewResult, ValidationResult, LLMProvider
- :mod:`.provider`   : MockLLMProvider (utilise par les tests V1)
- :mod:`.roles`      : chargement de config/llm_roles.yaml
"""

from .interfaces import (
    GenerationResult,
    ReviewResult,
    ValidationResult,
    ProviderHealth,
    LLMProvider,
)
from .provider import MockLLMProvider, MockCall
from .roles import load_roles_config, get_role_config

__all__ = [
    "GenerationResult",
    "ReviewResult",
    "ValidationResult",
    "ProviderHealth",
    "LLMProvider",
    "MockLLMProvider",
    "MockCall",
    "load_roles_config",
    "get_role_config",
]
