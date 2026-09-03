"""
FreeLLMAPIProvider : implementation concrète appelant FreeLLMAPI via HTTP.

Ce provider :
- ne connait que FREELLMAPI_BASE_URL et FREELLMAPI_API_KEY ;
- n'utilise AUCUN SDK Groq / Cloudflare / OpenRouter ;
- transmet role_config tel quel a FreeLLMAPI (temperature, response_format, etc.) ;
- normalise les reponses (string JSON ou dict deja decode) ;
- classifie correctement les erreurs.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from typing import Any, Optional

import httpx

from .interfaces import (
    GenerationResult,
    ProviderHealth,
    ReviewResult,
    ValidationResult,
    LLMProvider,
    SEVERITY_VALUES,
)


# ---------------------------------------------------------------------------
# Erreurs classify
# ---------------------------------------------------------------------------

class FreeLLMAPIError(Exception):
    """Erreur de base FreeLLMAPI avec code d'erreur."""
    def __init__(
        self,
        message: str,
        code: str,
        *,
        status_code: Optional[int] = None,
        retryable: bool = False,
    ):
        super().__init__(message)
        self.code = code
        self.status_code = status_code
        self.retryable = retryable


ERROR_CODES = {
    "AUTH_ERROR",
    "RATE_LIMITED",
    "PROVIDER_UNAVAILABLE",
    "NETWORK_ERROR",
    "TIMEOUT",
    "INVALID_RESPONSE",
    "INVALID_JSON",
    "EMPTY_COMPLETION",
    "UNKNOWN_PROVIDER_ERROR",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _classify_httpx_error(exc: httpx.HTTPError) -> FreeLLMAPIError:
    """Classifie une exception httpx en erreur FreeLLMAPI."""
    if isinstance(exc, httpx.TimeoutException):
        return FreeLLMAPIError(
            f"Request timeout: {exc}",
            "TIMEOUT",
            retryable=True,
        )
    if isinstance(exc, httpx.ConnectError):
        return FreeLLMAPIError(
            f"Connection failed: {exc}",
            "NETWORK_ERROR",
            retryable=True,
        )
    if isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code
        if status == 401 or status == 403:
            return FreeLLMAPIError(
                f"Authentication failed: {exc}",
                "AUTH_ERROR",
                status_code=status,
            )
        if status == 429:
            return FreeLLMAPIError(
                f"Rate limited: {exc}",
                "RATE_LIMITED",
                status_code=status,
                retryable=True,
            )
        if 500 <= status < 600:
            return FreeLLMAPIError(
                f"Provider unavailable ({status}): {exc}",
                "PROVIDER_UNAVAILABLE",
                status_code=status,
                retryable=True,
            )
        return FreeLLMAPIError(
            f"HTTP error {status}: {exc}",
            "UNKNOWN_PROVIDER_ERROR",
            status_code=status,
        )
    return FreeLLMAPIError(
        f"Network error: {exc}",
        "NETWORK_ERROR",
        retryable=True,
    )


def _normalize_content(content: Any) -> dict[str, Any]:
    """Normalise le contenu de reponse en dict.

    Accepte :
    - dict deja decode
    - string JSON
    - None / "" -> {}
    """
    if content is None:
        return {}
    if isinstance(content, dict):
        return content
    if isinstance(content, str):
        stripped = content.strip()
        if not stripped:
            return {}
        try:
            parsed = json.loads(stripped)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass
    return {}


def _extract_json_from_text(text: str) -> Optional[dict[str, Any]]:
    """Extrait un objet JSON depuis un texte (peut contenir du markdown)."""
    text = text.strip()
    # Essayer parsing direct
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass
    # Essayer extraction de bloc markdown ```json ... ```
    import re
    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass
    return None


def _make_generation_result(
    text: str,
    *,
    token_usage: Optional[int] = None,
    latency_ms: Optional[int] = None,
) -> GenerationResult:
    return GenerationResult(
        text=text,
        token_usage=token_usage,
        latency_ms=latency_ms,
    )


def _make_review_result(
    data: dict[str, Any],
    *,
    raw_output_ref: Optional[str] = None,
    token_usage: Optional[int] = None,
    latency_ms: Optional[int] = None,
) -> ReviewResult:
    severity = data.get("severity", "low")
    if severity not in SEVERITY_VALUES:
        severity = "low"
    return ReviewResult(
        issues_found=data.get("issues_found", []) or [],
        severity=severity,
        instructions_for_fix=data.get("instructions_for_fix", []) or [],
        retry_needed=bool(data.get("retry_needed", False)),
        raw_output_ref=raw_output_ref,
        token_usage=token_usage,
        latency_ms=latency_ms,
    )


def _make_validation_result(
    data: dict[str, Any],
    *,
    raw_output_ref: Optional[str] = None,
    token_usage: Optional[int] = None,
    latency_ms: Optional[int] = None,
) -> ValidationResult:
    return ValidationResult(
        approved=bool(data.get("approved", False)),
        score=data.get("score"),
        reason=data.get("reason"),
        blocking_issues=data.get("blocking_issues", []) or [],
        raw_output_ref=raw_output_ref,
        token_usage=token_usage,
        latency_ms=latency_ms,
    )


# ---------------------------------------------------------------------------
# FreeLLMAPIProvider
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class FreeLLMAPIProvider(LLMProvider):
    """Provider FreeLLMAPI utilisant httpx."""

    base_url: str
    api_key: str
    timeout_s: float = 60.0

    # Internal client (lazy init)
    _client: Optional[httpx.Client] = None

    def __post_init__(self) -> None:
        if not self.base_url:
            raise ValueError("FREELLMAPI_BASE_URL is required")
        if not self.api_key:
            raise ValueError("FREELLMAPI_API_KEY is required")
        # Normalize base_url (remove trailing slash)
        self.base_url = self.base_url.rstrip("/")

    def _get_client(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(
                base_url=self.base_url,
                timeout=self.timeout_s,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
            )
        return self._client

    def close(self) -> None:
        if self._client is not None:
            self._client.close()
            self._client = None

    def __enter__(self) -> FreeLLMAPIProvider:
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()

    # -----------------------------------------------------------------------
    # Helpers internes
    # -----------------------------------------------------------------------

    def _post_chat(
        self,
        *,
        model: str,
        messages: list[dict[str, Any]],
        temperature: Optional[float] = None,
        response_format: Optional[dict[str, Any]] = None,
        reasoning_effort: Optional[str] = None,
    ) -> dict[str, Any]:
        """Effectue l'appel POST /chat/completions vers FreeLLMAPI."""
        client = self._get_client()
        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
        }
        if temperature is not None:
            payload["temperature"] = temperature
        if response_format is not None:
            payload["response_format"] = response_format
        if reasoning_effort is not None:
            payload["reasoning_effort"] = reasoning_effort

        start = time.perf_counter()
        try:
            response = client.post("/v1/chat/completions", json=payload)
            latency_ms = int((time.perf_counter() - start) * 1000)
            response.raise_for_status()
            return response.json(), latency_ms
        except httpx.HTTPError as exc:
            raise _classify_httpx_error(exc)

    def _parse_completion(
        self,
        response: dict[str, Any],
        *,
        expected_type: str,  # "generate" | "review" | "validate"
    ) -> tuple[dict[str, Any], Optional[int]]:
        """Extrait et valide le contenu de la completion."""
        choices = response.get("choices")
        if not choices or not isinstance(choices, list) or len(choices) == 0:
            raise FreeLLMAPIError(
                "No choices in response",
                "INVALID_RESPONSE",
            )

        choice = choices[0]
        message = choice.get("message")
        if not message or not isinstance(message, dict):
            raise FreeLLMAPIError(
                "Invalid message in choice",
                "INVALID_RESPONSE",
            )

        content = message.get("content")
        if content is None:
            raise FreeLLMAPIError(
                "Empty completion (content is null)",
                "EMPTY_COMPLETION",
            )

        # Normalize content
        normalized = _normalize_content(content)
        if not normalized:
            # Try to extract JSON from text if content was a string
            if isinstance(content, str):
                extracted = _extract_json_from_text(content)
                if extracted:
                    normalized = extracted
                else:
                    raise FreeLLMAPIError(
                        f"Could not parse JSON from completion: {content[:200]}",
                        "INVALID_JSON",
                    )
            else:
                raise FreeLLMAPIError(
                    "Empty completion after normalization",
                    "EMPTY_COMPLETION",
                )

        usage = response.get("usage")
        token_usage = None
        if usage and isinstance(usage, dict):
            token_usage = usage.get("total_tokens")

        return normalized, token_usage

    # -----------------------------------------------------------------------
    # LLMProvider interface
    # -----------------------------------------------------------------------

    def generate(
        self,
        *,
        prompt: str,
        role_config: dict,
    ) -> GenerationResult:
        model = role_config.get("model")
        if not model:
            raise FreeLLMAPIError(
                "generator role requires a model in role_config",
                "INVALID_RESPONSE",
            )

        temperature = role_config.get("temperature")

        messages = [
            {"role": "user", "content": prompt},
        ]

        response, latency_ms = self._post_chat(
            model=model,
            messages=messages,
            temperature=temperature,
        )

        normalized, token_usage = self._parse_completion(
            response,
            expected_type="generate",
        )

        # For generator, we expect plain text/code, not JSON
        text = normalized.get("text") or normalized.get("content") or ""
        if not text and isinstance(normalized, dict):
            # Fallback: maybe the whole response IS the text
            text = str(normalized)

        return _make_generation_result(
            text=text,
            token_usage=token_usage,
            latency_ms=latency_ms,
        )

    def review(
        self,
        *,
        code: str,
        role_config: dict,
    ) -> ReviewResult:
        model = role_config.get("model")
        if not model:
            raise FreeLLMAPIError(
                "reviewer role requires a model in role_config",
                "INVALID_RESPONSE",
            )

        temperature = role_config.get("temperature")

        # Build prompt for reviewer
        prompt = (
            "Review the following code and return a JSON object with:\n"
            "- issues_found: array of strings\n"
            "- severity: 'low' | 'medium' | 'high' | 'critical'\n"
            "- instructions_for_fix: array of strings\n"
            "- retry_needed: boolean\n\n"
            f"Code:\n```\n{code}\n```"
        )

        messages = [
            {"role": "system", "content": "You are a code reviewer. Output ONLY valid JSON."},
            {"role": "user", "content": prompt},
        ]

        response, latency_ms = self._post_chat(
            model=model,
            messages=messages,
            temperature=temperature,
        )

        normalized, token_usage = self._parse_completion(
            response,
            expected_type="review",
        )

        # Store raw output for debugging
        raw_output = json.dumps(normalized, ensure_ascii=False)

        return _make_review_result(
            normalized,
            raw_output_ref=raw_output,
            token_usage=token_usage,
            latency_ms=latency_ms,
        )

    def validate(
        self,
        *,
        code: str,
        role_config: dict,
    ) -> ValidationResult:
        model = role_config.get("model")
        if not model:
            raise FreeLLMAPIError(
                "validator role requires a model in role_config",
                "INVALID_RESPONSE",
            )

        temperature = role_config.get("temperature")
        response_format = role_config.get("response_format")
        reasoning_effort = role_config.get("reasoning_effort")

        # Build prompt for validator
        prompt = (
            "Validate the following code and return a JSON object with:\n"
            "- approved: boolean\n"
            "- score: integer 0-100\n"
            "- reason: string\n"
            "- blocking_issues: array of strings\n\n"
            f"Code:\n```\n{code}\n```"
        )

        messages = [
            {"role": "system", "content": "You are a code validator. Output ONLY valid JSON."},
            {"role": "user", "content": prompt},
        ]

        response, latency_ms = self._post_chat(
            model=model,
            messages=messages,
            temperature=temperature,
            response_format=response_format,
            reasoning_effort=reasoning_effort,
        )

        normalized, token_usage = self._parse_completion(
            response,
            expected_type="validate",
        )

        raw_output = json.dumps(normalized, ensure_ascii=False)

        return _make_validation_result(
            normalized,
            raw_output_ref=raw_output,
            token_usage=token_usage,
            latency_ms=latency_ms,
        )

    def health(self) -> ProviderHealth:
        """Verifie la sante de FreeLLMAPI via /api/ping."""
        client = self._get_client()
        try:
            response = client.get("/api/ping", timeout=5.0)
            if response.status_code == 200:
                data = response.json()
                return ProviderHealth(
                    provider="freellmapi",
                    model="unknown",
                    status="up",
                    detail=data.get("version"),
                )
        except httpx.HTTPError:
            pass
        return ProviderHealth(
            provider="freellmapi",
            model="unknown",
            status="down",
            detail="Health check failed",
        )


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def create_freellmapi_provider(
    base_url: Optional[str] = None,
    api_key: Optional[str] = None,
    timeout_s: float = 60.0,
) -> FreeLLMAPIProvider:
    """Cree un FreeLLMAPIProvider depuis l'environnement ou parametres explicites.

    Priorite :
    1. Parametres explicites
    2. Variables d'environnement FREELLMAPI_BASE_URL / FREELLMAPI_API_KEY
    """
    base_url = base_url or os.environ.get("FREELLMAPI_BASE_URL")
    api_key = api_key or os.environ.get("FREELLMAPI_API_KEY")
    return FreeLLMAPIProvider(
        base_url=base_url or "",
        api_key=api_key or "",
        timeout_s=timeout_s,
    )


__all__ = [
    "FreeLLMAPIProvider",
    "FreeLLMAPIError",
    "create_freellmapi_provider",
    "ERROR_CODES",
]