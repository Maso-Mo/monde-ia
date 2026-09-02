# Monde des ZFLM — Monde des LLM

> Une expérience autonome : des LLM créent successivement des sites web de difficulté croissante, pendant un mois ou plus, en s'auto-corrigeant via une boucle de revue/validation.

---

## ⚠️ Phase 0 — Bootstrap architecturel uniquement

Ce dépôt contient pour l'instant **uniquement l'ossature** (arborescence, configuration, images sandbox, scripts d'infrastructure). **Aucune logique métier n'est encore implémentée.**

Nous validerons ensemble la Phase 0 avant d'entamer la Phase 1.

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
├── projects/                 # Sorties générées par les LLM
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