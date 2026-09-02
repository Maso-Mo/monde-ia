# ZFLM — Documentation

Cette section regroupe la documentation du projet.

## Phase 0 — Bootstrap (en cours)

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

## Phase 1+ — À valider ensemble

La phase 1 ne sera démarrée **qu'après validation explicite** de la phase 0.

À venir :

- machine à états des tâches ;
- boucle d'expérience avec tentatives (max 3) ;
- abstraction LLM (interface unique vers FreeLLMAPI / OpenRouter) ;
- intégration des niveaux définis dans `config/levels.yaml` ;
- Qwen 2.5 (reviewer) + Qwen 3 (validator) via API ;
- mémoire persistante ;
- reprise après crash.

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
| `orchestrator/requirements.txt` | Dépendances Python V1 |
| `orchestrator/Dockerfile` | Image orchestrateur |
| `sandbox-images/html-css/Dockerfile` | Sandbox HTML/CSS |
| `sandbox-images/js-frontend/Dockerfile` | Sandbox JS |
| `scripts/bootstrap_oracle.sh` | Préparation VM Oracle ARM64 |
| `scripts/health_check.sh` | Vérification système |
| `scripts/backup.sh` | Sauvegardes sans secrets |
| `docker-compose.yml` | Composition orchestrateur / FreeLLMAPI |
| `.env.example` | Modèle de variables d'environnement |
| `.gitignore` | Protection secrets et fichiers générés |