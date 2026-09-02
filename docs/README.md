# ZFLM — Documentation

Cette section regroupe la documentation du projet.

## Phase 0 — Bootstrap (terminée)

Cette phase ne contient **aucune logique métier**. Elle pose uniquement les fondations :

- arborescence propre ;
- configuration de base ;
- images sandbox reproductibles ;
- scripts d'infrastructure ;
- docker-compose séparant orchestrateur / FreeLLMAPI.

### Décisions prises en Phase 0

| Sujet | Décision | Raison |
|---|---|---|
| Runtime Python | 3.12 (dans Docker) | Compatibilité Pydantic v2 et stack minimale |
| Persistance | SQLite (volume Docker nommé) | Suffisant pour une expérience mono-VM |
| Projets générés | **Bind mount** `./projects` ↔ `/app/projects` | Versionnage Git direct des snapshots APPROVED et derniers états FAILED_AFTER_RETRIES |
| Sandboxes | Images Docker dédiées par niveau | Reproductibilité et isolation |
| FreeLLMAPI | Service tiers externe, NON versionné ici | Le code de FreeLLMAPI reste indépendant |
| OpenRouter | DEV uniquement (pour coder ZFLM) | L'expérience finale utilise FreeLLMAPI |
| Secrets | `.env` jamais versionné, `.env.example` fourni | Sécurité |

## Phase 1 — Coeur de l'orchestrateur (terminée)

Cette phase implémente le **moteur persistant** de l'orchestrateur, SANS
appel réseau réel. Toute la logique est testable avec des mocks.

### Composants livrés

- **SQLite** : base locale `memory/zflm.db`, schéma versionné
  (`orchestrator/src/memory/schema.sql`), wrapper
  `Database` (PRAGMA foreign_keys=ON, journal_mode=WAL, transactions explicites).
- **Modèle de données** : 11 entités (Project, Level, Task, Attempt,
  LLMCall, Review, Validation, Error, Memory, ProviderState, GitSnapshot)
  avec dataclasses DTOs et repository CRUD.
- **Machine à états** : 12 états, table de transitions stricte, persistance
  via `AttemptStateMachine`. Le cas `PAUSED_PROVIDER` mémorise
  `previous_state` pour reprise exacte.
- **Rôles LLM** : configuration YAML (`config/llm_roles.yaml`) avec
  generator / reviewer / validator. Modèles exacts **non choisis** en V1.
- **Abstraction LLM** : interface `LLMProvider`, DTOs (`GenerationResult`,
  `ReviewResult`, `ValidationResult`, `ProviderHealth`) et
  `MockLLMProvider` pour les tests.
- **Logging JSONL** : `JsonlLogger` écrit dans `logs/zflm.jsonl`.
- **Recovery** : `RecoverySnapshot` lit l'état courant depuis SQLite
  (projet actif → niveau → tâche → tentative → état).
- **Loop MOCK** : `MockCycle` exécute un cycle complet et respecte
  la limite de 3 tentatives par Task.
- **Entrypoint** : `python -m src.main` avec modes
  `--show-config`, `--show-recovery`, `--mock-cycle`.
- **Tests** : **75 tests pytest**, tous verts.

### Décisions techniques Phase 1

| Sujet | Décision |
|---|---|
| ORM | Aucun — `sqlite3` stdlib |
| Transitions | Table immuable `dict[AttemptState, frozenset[AttemptState]]` |
| `PAUSED_PROVIDER` | Sortie self-loop (`GENERATING -> GENERATING`) toujours autorisée |
| Statut Attempt | Champ séparé `status` (`active | done | failed`) en plus de `state` |
| Limite retries | Champ `attempt_number` 1..3 + compteur `count_for_task` |
| Sortie PAUSED_PROVIDER | Retour à `previous_state` par défaut, ou `target` explicite si valide |
| Modèles Qwen 2.5 / 3 | `family: qwen2.5` / `family: qwen3` dans YAML, `provider: null`, `model: null` |
| Tests | `tmp_path` par test, fixtures `db`, `repos`, `mock_provider`, `jsonl_logger`, `machine` |

## Phase 2+ — À valider ensemble

À venir (sans ordre figé) :

- Intégration FreeLLMAPI réelle (provider HTTP via httpx) ;
- Sandboxes Docker effectives (images `sandbox-images/*`) ;
- Boucle d'expérience (parcours des niveaux, génération autonome) ;
- Prompts définitifs Qwen 2.5 (reviewer) et Qwen 3 (validator) ;
- Snapshots Git réels (`orchestrator/src/git/`) ;
- Northflank deployment (après stabilisation) ;
- Mémoire long-terme exploitée ;
- Recovery robuste (auto-resume après crash) ;
- Dashboard minimal (optionnel).

## Architecture cible (rappel)

```
LLM générateur
  → génère / modifie un site
  → sandbox Docker
  → build / tests
  → Qwen 2.5 (reviewer)
  → Qwen 3 (validator)

  refus → Qwen 2.5 → instructions structurées → nouvelle tentative

  3 échecs → log + archive, puis on continue.
```

## Infrastructure cible

- VM Oracle Cloud Always Free — **Ubuntu ARM64**
- Docker + Compose + SQLite
- Sandboxes Docker éphémères
- Git pour versionner chaque projet généré

## Fichiers clés

| Fichier | Rôle |
|---|---|
| `README.md` | Vue d'ensemble |
| `config/levels.yaml` | Niveaux de difficulté |
| `config/llm_roles.yaml` | Configuration des rôles LLM (Phase 1) |
| `orchestrator/requirements.txt` | Dépendances Python V1 |
| `orchestrator/Dockerfile` | Image orchestrateur |
| `orchestrator/src/main.py` | Entrypoint (Phase 1) |
| `orchestrator/src/memory/schema.sql` | DDL SQLite (Phase 1) |
| `orchestrator/src/state_machine/` | Machine à états (Phase 1) |
| `orchestrator/src/recovery/` | Recovery depuis SQLite (Phase 1) |
| `orchestrator/src/llm/` | Interfaces LLM + Mock (Phase 1) |
| `sandbox-images/html-css/Dockerfile` | Sandbox HTML/CSS |
| `sandbox-images/js-frontend/Dockerfile` | Sandbox JS |
| `scripts/bootstrap_oracle.sh` | Préparation VM Oracle ARM64 |
| `scripts/health_check.sh` | Vérification système |
| `scripts/backup.sh` | Sauvegardes sans secrets |
| `docker-compose.yml` | Composition orchestrateur / FreeLLMAPI |
| `.env.example` | Modèle de variables d'environnement |
| `.gitignore` | Protection secrets et fichiers générés |