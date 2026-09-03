"""orchestrator.src.llm

Interfaces et providers LLM.

Voir :

- :mod:`.interfaces`         : GenerationResult, ReviewResult, ValidationResult, LLMProvider
- :mod:`.provider`           : MockLLMProvider (tests V1)
- :mod:`.freellmapi_provider`: FreeLLMAPIProvider (Phase 2, runtime)
- :mod:`.roles`              : chargement de config/llm_roles.yaml
"""

from .interfaces import (
    GenerationResult,
    ReviewResult,
    ValidationResult,
    ProviderHealth,
    LLMProvider,
)
from .provider import MockLLMProvider, MockCall
from .freellmapi_provider import FreeLLMAPIProvider, create_freellmapi_provider, FreeLLMAPIError, ERROR_CODES
from .roles import load_roles_config, get_role_config

__all__ = [
    "GenerationResult",
    "ReviewResult",
    "ValidationResult",
    "ProviderHealth",
    "LLMProvider",
    "MockLLMProvider",
    "MockCall",
    "FreeLLMAPIProvider",
    "create_freellmapi_provider",
    "FreeLLMAPIError",
    "ERROR_CODES",
    "load_roles_config",
    "get_role_config",
]
