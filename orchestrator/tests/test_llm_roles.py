"""
Tests de chargement de llm_roles.yaml.
"""

from __future__ import annotations

from src.llm import get_role_config, load_roles_config


def test_load_default_roles_file():
    roles = load_roles_config()
    assert set(roles.keys()) >= {"generator", "reviewer", "validator"}
    # Les modeles sont a null tant qu'on n'a pas choisi.
    for name in ("generator", "reviewer", "validator"):
        cfg = get_role_config(roles, name)
        assert cfg is not None
        # provider / model peuvent etre None ou None
        assert "provider" in cfg or "model" in cfg or cfg == {}


def test_get_role_config_unknown_role_returns_empty():
    roles = load_roles_config()
    assert get_role_config(roles, "nope") == {}


def test_roles_have_expected_family_hint():
    roles = load_roles_config()
    # reviewer = qwen2.5, validator = qwen3 (en V1, indicatif uniquement)
    reviewer = get_role_config(roles, "reviewer")
    validator = get_role_config(roles, "validator")
    assert reviewer.get("family") == "qwen2.5"
    assert validator.get("family") == "qwen3"
