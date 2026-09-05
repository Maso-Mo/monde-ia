"""
Tests pour FreeLLMAPIProvider (sans reseau).
"""

from __future__ import annotations

from unittest.mock import Mock, patch

import httpx
import pytest

from src.llm import (
    FreeLLMAPIProvider,
    create_freellmapi_provider,
    FreeLLMAPIError,
    _normalize_response_format,
)
from src.llm.interfaces import ProviderHealth


class TestFreeLLMAPIProvider:
    """Tests unitaires pour FreeLLMAPIProvider."""

    def test_repr_does_not_contain_api_key(self):
        """Le repr ne doit JAMAIS contenir la valeur de api_key."""
        provider = FreeLLMAPIProvider(
            base_url="http://localhost:3001",
            api_key="SECRET_API_KEY_12345",
            timeout_s=30.0,
        )
        repr_str = repr(provider)
        assert "SECRET_API_KEY_12345" not in repr_str, \
            f"api_key trouvée dans repr: {repr_str}"
        assert "api_key" not in repr_str.lower() or "SECRET" not in repr_str

    def test_repr_contains_base_url(self):
        """Le repr doit contenir base_url (non sensible)."""
        provider = FreeLLMAPIProvider(
            base_url="http://localhost:3001",
            api_key="secret",
            timeout_s=30.0,
        )
        repr_str = repr(provider)
        assert "http://localhost:3001" in repr_str

    def test_repr_does_not_contain_client(self):
        """Le repr ne doit pas contenir _client."""
        provider = FreeLLMAPIProvider(
            base_url="http://localhost:3001",
            api_key="secret",
            timeout_s=30.0,
        )
        repr_str = repr(provider)
        assert "_client" not in repr_str

    def test_create_freellmapi_provider_from_env(self, monkeypatch):
        """La factory lit les variables d'environnement."""
        monkeypatch.setenv("FREELLMAPI_BASE_URL", "http://test:3001")
        monkeypatch.setenv("FREELLMAPI_API_KEY", "env_key")

        provider = create_freellmapi_provider()
        assert provider.base_url == "http://test:3001"
        assert provider.api_key == "env_key"
        assert provider.timeout_s == 60.0

    def test_create_freellmapi_provider_explicit_args(self):
        """La factory accepte des arguments explicites."""
        provider = create_freellmapi_provider(
            base_url="http://explicit:3001",
            api_key="explicit_key",
            timeout_s=45.0,
        )
        assert provider.base_url == "http://explicit:3001"
        assert provider.api_key == "explicit_key"
        assert provider.timeout_s == 45.0

    def test_missing_base_url_raises(self):
        """base_url manquant leve une erreur."""
        with pytest.raises(ValueError, match="FREELLMAPI_BASE_URL is required"):
            FreeLLMAPIProvider(base_url="", api_key="key")

    def test_missing_api_key_raises(self):
        """api_key manquant leve une erreur."""
        with pytest.raises(ValueError, match="FREELLMAPI_API_KEY is required"):
            FreeLLMAPIProvider(base_url="http://test", api_key="")

    def test_health_check_calls_ping_endpoint(self):
        """health() appelle /api/ping et parse la reponse."""
        provider = FreeLLMAPIProvider(base_url="http://test", api_key="key")

        # Mock le client httpx
        mock_client = Mock()
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"version": "0.9.4"}
        mock_client.get.return_value = mock_response
        provider._client = mock_client

        health = provider.health()

        assert isinstance(health, ProviderHealth)
        assert health.provider == "freellmapi"
        assert health.status == "up"
        assert health.detail == "0.9.4"
        mock_client.get.assert_called_once_with("/api/ping", timeout=5.0)

    def test_health_check_handles_failure(self):
        """health() renvoie down si l'appel echoue."""
        provider = FreeLLMAPIProvider(base_url="http://test", api_key="key")

        mock_client = Mock()
        mock_client.get.side_effect = httpx.ConnectError("connection refused")
        provider._client = mock_client

        health = provider.health()
        assert health.status == "down"
        assert "Health check failed" in health.detail

    def test_close_closes_client(self):
        """close() ferme le client HTTP."""
        provider = FreeLLMAPIProvider(base_url="http://test", api_key="key")
        mock_client = Mock()
        provider._client = mock_client

        provider.close()
        mock_client.close.assert_called_once()
        assert provider._client is None


class TestFreeLLMAPIError:
    """Tests pour la classification d'erreurs."""

    def test_error_codes_defined(self):
        """Les codes d'erreur sont definis."""
        from src.llm.freellmapi_provider import ERROR_CODES
        expected = {
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
        assert ERROR_CODES == expected

    def test_error_attributes(self):
        """FreeLLMAPIError a les bons attributs."""
        err = FreeLLMAPIError(
            "test message",
            "TIMEOUT",
            status_code=408,
            retryable=True,
        )
        assert str(err) == "test message"
        assert err.code == "TIMEOUT"
        assert err.status_code == 408
        assert err.retryable is True


class TestNormalizeResponseFormat:
    """Tests pour la normalisation de response_format."""

    def test_none_returns_none(self):
        """None -> None (champ absent de la requete)."""
        assert _normalize_response_format(None) is None

    def test_string_json_object(self):
        """'json_object' -> {'type': 'json_object'}."""
        result = _normalize_response_format("json_object")
        assert result == {"type": "json_object"}

    def test_dict_json_object(self):
        """{'type': 'json_object'} -> inchangé."""
        input_value = {"type": "json_object"}
        result = _normalize_response_format(input_value)
        assert result == input_value
        # Pour un dict valide, on renvoie le meme objet (pas de copie)
        assert result is input_value

    def test_unknown_string_raises(self):
        """String inconnue -> erreur de configuration claire."""
        with pytest.raises(ValueError, match="response_format string inconnu"):
            _normalize_response_format("unknown_format")

    def test_invalid_dict_raises(self):
        """Objet invalide -> erreur de configuration claire."""
        with pytest.raises(ValueError, match="response_format objet invalide"):
            _normalize_response_format({"type": "invalid"})

    def test_invalid_type_raises(self):
        """Type non supporté -> erreur de configuration claire."""
        with pytest.raises(ValueError, match="response_format type non supporté"):
            _normalize_response_format(123)

    def test_empty_string_raises(self):
        """String vide -> erreur."""
        with pytest.raises(ValueError, match="response_format string inconnu"):
            _normalize_response_format("")


class TestValidateResponseFormatIntegration:
    """Tests d'integration pour validate avec response_format."""

    def test_validator_sends_correct_response_format(self):
        """Validator envoie le bon objet response_format."""
        provider = FreeLLMAPIProvider(base_url="http://test", api_key="key")

        mock_client = Mock()
        mock_response = Mock()
        mock_response.json.return_value = {
            "choices": [{
                "message": {
                    "content": '{"approved": true, "score": 100, "reason": "ok", "blocking_issues": []}'
                }
            }]
        }
        mock_response.raise_for_status = Mock()
        mock_client.post.return_value = mock_response
        provider._client = mock_client

        role_config = {
            "model": "qwen3.6-27b",
            "temperature": 0.2,
            "response_format": "json_object",
            "reasoning_effort": "none",
        }

        provider.validate(code="<html>test</html>", role_config=role_config)

        # Verifier l'appel au client
        call_args = mock_client.post.call_args
        payload = call_args[1]["json"]
        assert "response_format" in payload
        assert payload["response_format"] == {"type": "json_object"}
        assert payload["reasoning_effort"] == "none"
        assert payload["temperature"] == 0.2
        assert payload["model"] == "qwen3.6-27b"

    def test_reviewer_does_not_send_response_format(self):
        """Reviewer n'envoie pas response_format (null)."""
        provider = FreeLLMAPIProvider(base_url="http://test", api_key="key")

        mock_client = Mock()
        mock_response = Mock()
        mock_response.json.return_value = {
            "choices": [{
                "message": {
                    "content": '{"issues_found": [], "severity": "low", "instructions_for_fix": [], "retry_needed": false}'
                }
            }]
        }
        mock_response.raise_for_status = Mock()
        mock_client.post.return_value = mock_response
        provider._client = mock_client

        role_config = {
            "model": "@cf/qwen/qwen2.5-coder-32b-instruct",
            "temperature": 0.1,
            "response_format": None,
        }

        provider.review(code="const x = 1;", role_config=role_config)

        call_args = mock_client.post.call_args
        payload = call_args[1]["json"]
        assert "response_format" not in payload
        assert payload["temperature"] == 0.1
        assert "reasoning_effort" not in payload