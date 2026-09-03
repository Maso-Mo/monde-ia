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
  generator / reviewer / validator.
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
- **Tests** : **101 tests pytest** (75 Phase 1 + 26 Phase 1.1), tous verts.

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

## Phase 1.1 — Corrections de conformité (terminée)

Phase 1.1 a apporté :

- Une **table `state_transitions`** append-only qui journalise chaque
  transition d'état d'un Attempt. Chaque transition est persistée
  **atomiquement** avec `attempts.state` via
  `Database.record_state_transition` (UPDATE + INSERT dans la même
  transaction SQLite).
- Une **table de transitions** restreinte :
  `PAUSED_PROVIDER` n'est accessible que depuis `GENERATING`,
  `REVIEWING` et `VALIDATING`. La sortie de `PAUSED_PROVIDER`
  est strictement vers `previous_state` (pas de cible arbitraire).
- Les **modèles réels** configurés dans `config/llm_roles.yaml`
  (reviewer Qwen 2.5 Coder via Cloudflare, validator Qwen 3.6 via Groq).

### Routage runtime final

```
LLM provider (reviewer) :
  ZFLM
    → FreeLLMAPI
    → Cloudflare
    → @cf/qwen/qwen2.5-coder-32b-instruct

LLM provider (validator) :
  ZFLM
    → FreeLLMAPI
    → Groq
    → qwen/qwen3.6-27b
```

ZFLM ne contacte **jamais** Cloudflare ou Groq directement. Le champ
`provider` dans `llm_roles.yaml` est informatif (logging/diagnostic).
Le runtime parle uniquement à FreeLLMAPI.

### Incompatibilité connue : Cloudflare / Qwen 2.5 / FreeLLMAPI (Phase 2)

Le reviewer Qwen 2.5-Coder-32B-Instruct, testé runtime réel via
Cloudflare Workers AI, renvoie `choices[0].message.content`
**directement comme un objet JSON** (et non comme une string JSON) :

```json
"message": {
  "role": "assistant",
  "content": {
    "issues_found": [...],
    "severity": "critical",
    "instructions_for_fix": [...],
    "retry_needed": true
  }
}
```

Le provider Cloudflare actuellement utilisé par FreeLLMAPI interprète
ce contenu-objet comme un `empty_completion`. **Le modèle, le prompt
et Cloudflare ne sont pas en panne** ; c'est un écart de normalisation
entre la forme de réponse Cloudflare et le traitement actuel de
FreeLLMAPI.

**Correctif prévu Phase 2** (à appliquer dans FreeLLMAPI, PAS dans ZFLM) :

- Si `choices[0].message.content` est un objet JSON non-null,
  normaliser via `JSON.stringify(content)` avant le traitement standard,
  pour produire une réponse OpenAI-compatible consommable par ZFLM.
- Correctif limité au provider Cloudflare **OU** limité au cas
  `message.content` non-string-non-null. Pas de transformation naïve
  sur tous les providers (sinon Groq casse).
- Tests de régression Phase 2 prévus :
  1. content string classique ;
  2. content objet Cloudflare ;
  3. content null ;
  4. réponse vide réelle ;
  5. provider non-Cloudflare ;
  6. Qwen 2.5 reviewer ;
  7. Qwen 3 validator via Groq.

**Décision Phase 2** : nous utiliserons une version **contrôlée et
pinnée** de FreeLLMAPI. La version ne devra pas évoluer
automatiquement pendant l'expérience d'un mois.

Note sécurité : aucun token, Account ID ou clé API n'apparaît dans
ce document ni dans le repo.

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