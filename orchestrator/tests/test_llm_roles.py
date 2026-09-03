"""
Tests de chargement de llm_roles.yaml.

Phase 1.1 : les modeles sont maintenant specifies.
"""

from __future__ import annotations

from src.llm import get_role_config, load_roles_config


def test_load_default_roles_file():
    roles = load_roles_config()
    assert set(roles.keys()) >= {"generator", "reviewer", "validator"}
    for name in ("generator", "reviewer", "validator"):
        cfg = get_role_config(roles, name)
        assert cfg is not None


def test_get_role_config_unknown_role_returns_empty():
    roles = load_roles_config()
    assert get_role_config(roles, "nope") == {}


def test_reviewer_qwen2_5_coder():
    """reviewer: cloudflare / @cf/qwen/qwen2.5-coder-32b-instruct.

    Configuration verifiee runtime reellement.
    PAS de json_object : le JSON est impose par le prompt systeme.
    """
    roles = load_roles_config()
    reviewer = get_role_config(roles, "reviewer")
    assert reviewer.get("family") == "qwen2.5"
    assert reviewer.get("provider") == "cloudflare"
    assert reviewer.get("model") == "@cf/qwen/qwen2.5-coder-32b-instruct"
    assert reviewer.get("temperature") == 0.1
    # response_format: null -> pas de json_object force, le prompt
    # impose la structure.
    assert reviewer.get("response_format") is None
    assert reviewer.get("context_window") == 32768


def test_validator_qwen3_groq():
    """validator: groq / qwen3.6-27b / reasoning_effort none."""
    roles = load_roles_config()
    validator = get_role_config(roles, "validator")
    assert validator.get("family") == "qwen3"
    assert validator.get("provider") == "groq"
    assert validator.get("model") == "qwen3.6-27b"
    assert validator.get("temperature") == 0.2
    assert validator.get("response_format") == "json_object"
    assert validator.get("reasoning_effort") == "none"
    assert validator.get("context_window") == 131072


def test_generator_unchanged():
    """generator reste configure minimalement (provider: null, model: null)."""
    roles = load_roles_config()
    gen = get_role_config(roles, "generator")
    # provider et model peuvent etre null ou absents.
    assert gen.get("provider") in (None, "")
    assert gen.get("model") in (None, "")


def test_roles_have_no_secret():
    """Aucun role ne doit contenir de cle API ou token."""
    roles = load_roles_config()
    forbidden_keys = {"api_key", "secret", "token", "password"}
    for name, cfg in roles.items():
        for k in cfg.keys():
            assert k.lower() not in forbidden_keys, (
                f"Rôle '{name}' contient la clé suspecte '{k}'"
            )
