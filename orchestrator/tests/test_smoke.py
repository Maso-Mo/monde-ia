# ============================================================
# ZFLM - Smoke tests (Phase 0)
# ============================================================
# Vérifie que la structure du package est importable et
# que les dépendances critiques sont installées.
# Pas encore de logique métier : on valide juste le squelette.

import importlib
import sys


def test_python_version_is_supported():
    """Python 3.10+ requis (les modèles Pydantic v2 le supportent)."""
    assert sys.version_info >= (3, 10), (
        f"Python {sys.version_info.major}.{sys.version_info.minor} "
        f"trop ancien. Requis : >= 3.10."
    )


def test_pydantic_v2_available():
    import pydantic
    assert pydantic.VERSION.startswith("2."), (
        f"Pydantic v2 requis, trouvé {pydantic.VERSION}"
    )


def test_httpx_available():
    import httpx
    assert hasattr(httpx, "Client")


def test_yaml_available():
    import yaml
    assert hasattr(yaml, "safe_load")


def test_docker_sdk_available():
    import docker
    assert hasattr(docker, "from_env")


def test_dotenv_available():
    import dotenv
    assert hasattr(dotenv, "load_dotenv")


def test_subpackages_importable():
    """
    Les sous-packages du src/ doivent être importables (même vides).
    Cela garantit que la structure est correcte pour la Phase 1.
    """
    expected = [
        "state_machine",
        "loop",
        "llm",
        "levels",
        "sandbox",
        "memory",
        "obs_logging",
        "git",
        "recovery",
        "config",
    ]
    for name in expected:
        # Import relatif au package src/ ; PYTHONPATH=/app/src en Docker
        try:
            importlib.import_module(name)
        except ImportError as e:
            # Tolérance : les sous-packages peuvent ne pas encore
            # exposer quoi que ce soit d'utile. On vérifie juste
            # qu'ils sont dans sys.modules après un import forcé
            # du package parent si nécessaire.
            # Ici on se contente de signaler le cas.
            raise AssertionError(
                f"Sous-package '{name}' non importable : {e}"
            )


def test_levels_yaml_parses():
    """
    Le fichier config/levels.yaml doit être un YAML valide.
    On le charge depuis le répertoire racine du projet
    (relatif à la racine, pas au test).
    """
    import yaml
    from pathlib import Path

    repo_root = Path(__file__).resolve().parents[2]
    levels_file = repo_root / "config" / "levels.yaml"

    assert levels_file.exists(), f"levels.yaml introuvable : {levels_file}"

    data = yaml.safe_load(levels_file.read_text(encoding="utf-8"))
    assert "levels" in data and isinstance(data["levels"], list)
    assert len(data["levels"]) > 0, "Aucun niveau défini dans levels.yaml"

    for level in data["levels"]:
        assert "id" in level, f"Niveau sans id : {level}"
        assert "description" in level, f"Niveau sans description : {level}"
        assert "sandbox" in level, f"Niveau sans sandbox : {level}"