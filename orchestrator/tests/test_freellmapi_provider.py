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