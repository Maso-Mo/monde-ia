# Monde des ZFLM — Monde des LLM

> Une expérience autonome : des LLM créent successivement des sites web de difficulté croissante, pendant un mois ou plus, en s'auto-corrigeant via une boucle de revue/validation.

---

## ⚠️ Phase 1 — Coeur de l'orchestrateur (en cours)

Le squelette de la Phase 0 est en place, et le **moteur persistant** de l'orchestrateur est implémenté :

- SQLite + modèle de données complet (11 entités) ;
- machine à états persistante (12 états) ;
- configuration des rôles LLM (Qwen 2.5 / Qwen 3 — modèles exacts à choisir) ;
- abstraction LLM avec `MockLLMProvider` ;
- recovery depuis SQLite ;
- logging JSONL ;
- 75 tests pytest, tous verts.

**Aucun appel réseau réel** n'est encore effectué. L'intégration FreeLLMAPI viendra en Phase 2.

Voir `docs/README.md` pour le détail des décisions techniques Phase 1.

---

## 🏗️ Architecture cible

```
LLM générateur
  → génère / modifie un site
  → sandbox Docker
  → build / tests
  → Qwen 2.5 (reviewer) analyse le code et les problèmes
  → Qwen 3 (validator) accepte ou refuse

  en cas de refus :
    Qwen 3 → Qwen 2.5 → instructions structurées
    → LLM générateur → nouvelle tentative

  Maximum 3 tentatives par tâche.
  Au-delà : on enregistre l'échec, on conserve le code + logs + reviews,
  et on continue sans bloquer.
```

Progression des niveaux :

`HTML` → `HTML structuré` → `CSS` → `responsive` → `JavaScript` → `interactions` → `frontend complexe` → `projets ambitieux`

---

## 📂 Structure du dépôt

```
entreprise-ia-maso-dev-youtube/
├── orchestrator/             # Orchestrateur Python 3.12 (Pydantic v2)
│   ├── src/
│   │   ├── state_machine/    # Machine à états des tâches
│   │   ├── loop/             # Boucle principale d'expérience
│   │   ├── llm/              # Abstraction LLM
│   │   ├── levels/           # Définition des niveaux
│   │   ├── sandbox/          # Pilotage Docker sandbox
│   │   ├── memory/           # Mémoire persistante SQLite
│   │   ├── obs_logging/      # Logs JSON structurés (renommé pour éviter le conflit avec le module stdlib `logging`)
│   │   ├── git/              # Gestion Git par projet
│   │   ├── recovery/         # Reprise après crash
│   │   └── config/           # Chargement config
│   ├── tests/                # Tests pytest
│   ├── requirements.txt
│   └── Dockerfile
├── sandbox-images/
│   ├── html-css/             # Sandbox pour projets HTML/CSS
│   ├── js-frontend/          # Sandbox pour projets JS
│   └── advanced/             # Sandbox projets ambitieux (à venir)
├── projects/                 # Sites générés (bind mount Docker, versionnés par Git)
├── memory/archives/          # Mémoire long terme
├── logs/                     # Logs runtime
├── scripts/
│   ├── bootstrap_oracle.sh   # Préparation VM Oracle ARM64
│   ├── health_check.sh       # Vérification système
│   └── backup.sh             # Sauvegardes (sans secrets)
├── docs/                     # Documentation
├── config/levels.yaml        # Définition des niveaux
├── docker-compose.yml        # Séparation orchestrator / freellmapi
├── .env.example              # Modèle de variables d'env
└── README.md
```

---

## 🔌 Fournisseurs LLM

| Phase | Fournisseur |
|---|---|
| **Développement actuel** | OpenRouter (uniquement pour coder ZFLM) |
| **Expérience finale** | **FreeLLMAPI** (passerelle vers modèles gratuits), appelé en HTTP par l'orchestrateur |

**FreeLLMAPI** est un [projet tiers](https://github.com/tashfeenahmed/freellmapi) — il **n'est pas copié dans ce dépôt**. Il tourne séparément et est référencé comme service externe dans `docker-compose.yml`.

Les gros modèles (Qwen 2.5, Qwen 3) ne sont **pas téléchargés localement** : ils sont appelés par API.

---

## 🚀 Infrastructure de déploiement

Cible : **VM Oracle Cloud Always Free — ARM64**.

La VM hébergera :

- L'orchestrateur ZFLM (conteneur Docker)
- FreeLLMAPI (conteneur Docker tiers)
- SQLite (dans le conteneur orchestrateur)
- Sandboxes Docker éphémères
- Git / logs / workspaces / sauvegardes

Le script `scripts/bootstrap_oracle.sh` prépare une VM Ubuntu ARM64 vierge avec toutes les dépendances système (Git, Docker, Compose, jq, rsync, etc.).

### Persistance des projets

Le dossier `./projects/` est exposé à l'orchestrateur via un **bind mount** (`./projects:/app/projects`) et non via un volume Docker nommé. Cela permet de versionner directement dans Git :

- un **snapshot** du site lorsqu'une tâche passe en `APPROVED` ;
- le **dernier état** du site lorsqu'une tâche atteint `FAILED_AFTER_RETRIES`.

Les artefacts éphémères (`build/`, `dist/`, `node_modules/`, `.cache/`) restent ignorés par Git (cf. `.gitignore`). Les données runtime opaques (SQLite, mémoire, logs) restent dans des volumes Docker nommés.

---

## 🧪 Stack V1

| Couche | Choix |
|---|---|
| Langage orchestrateur | Python 3.12 (dans Docker) |
| Validation | Pydantic v2 |
| Persistance | SQLite |
| HTTP | httpx |
| Config | PyYAML + python-dotenv |
| Sandbox | Docker SDK for Python |
| Tests | pytest |
| Logs | JSON structuré |

**Pas de** Kubernetes, Kafka, Redis, Celery, LangChain, vector DB, microservices inutiles, dashboard complexe.

---

## 📜 Licence & origine

Dépôt officiel : `git@github.com:Maso-Mo/monde-ia.git`