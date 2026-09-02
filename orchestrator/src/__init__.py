"""orchestrator.src

Package racine de l'orchestrateur ZFLM (Phase 1).

Sous-packages :

- :mod:`.state_machine` : machine a etats des Attempts
- :mod:`.memory`        : SQLite + repository
- :mod:`.llm`           : interfaces LLM + MockLLMProvider
- :mod:`.recovery`      : snapshot d'etat au demarrage
- :mod:`.obs_logging`   : logger JSONL
- :mod:`.config`        : configuration runtime
- :mod:`.levels`        : chargement des niveaux depuis config/levels.yaml
- :mod:`.loop`          : boucle d'execution (MockCycle)
- :mod:`.sandbox`       : pilote Docker sandbox (Phase 2+)
- :mod:`.git`           : gestion Git des projets (Phase 2+)
"""

__version__ = "0.2.0"
__phase__ = "1"
