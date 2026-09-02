-- ============================================================
-- ZFLM - Schéma SQLite (Phase 1)
-- ============================================================
-- Toutes les colonnes utilisent snake_case.
-- Les timestamps sont en ISO 8601 UTC (TEXT).
-- Les enums sont TEXT avec CHECK constraints.
-- Les foreign keys sont activées via PRAGMA à la connexion.
--
-- Idempotent : peut être exécuté plusieurs fois sans casse (IF NOT EXISTS).
-- Pas de triggers en V1, pas de vues matérialisées, pas de FTS.

PRAGMA foreign_keys = ON;

-- ----------------------------------------------------------------------
-- Project
-- ----------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS projects (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  name            TEXT    NOT NULL,
  status          TEXT    NOT NULL DEFAULT 'active'
                          CHECK (status IN ('active', 'paused', 'archived')),
  created_at      TEXT    NOT NULL,
  current_level_id INTEGER NULL
);

CREATE INDEX IF NOT EXISTS idx_projects_status ON projects(status);

-- ----------------------------------------------------------------------
-- Level
-- ----------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS levels (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  project_id    INTEGER NOT NULL
                          REFERENCES projects(id) ON DELETE CASCADE,
  level_number  INTEGER NOT NULL
                          CHECK (level_number >= 1),
  spec          TEXT    NOT NULL,
  status        TEXT    NOT NULL DEFAULT 'pending'
                          CHECK (status IN ('pending', 'active', 'done', 'failed')),
  created_at    TEXT    NOT NULL,
  UNIQUE (project_id, level_number)
);

CREATE INDEX IF NOT EXISTS idx_levels_project ON levels(project_id);
CREATE INDEX IF NOT EXISTS idx_levels_status  ON levels(status);

-- ----------------------------------------------------------------------
-- Task
-- ----------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS tasks (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  level_id    INTEGER NOT NULL
                      REFERENCES levels(id) ON DELETE CASCADE,
  description TEXT    NOT NULL,
  status      TEXT    NOT NULL DEFAULT 'pending'
                      CHECK (status IN ('pending', 'active', 'done', 'failed')),
  created_at  TEXT    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_tasks_level  ON tasks(level_id);
CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);

-- ----------------------------------------------------------------------
-- Attempt
-- ----------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS attempts (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  task_id         INTEGER NOT NULL
                          REFERENCES tasks(id) ON DELETE CASCADE,
  attempt_number  INTEGER NOT NULL
                          CHECK (attempt_number BETWEEN 1 AND 3),
  state           TEXT    NOT NULL DEFAULT 'CREATED'
                          CHECK (state IN (
                              'CREATED',
                              'PREPARING',
                              'GENERATING',
                              'BUILDING',
                              'TESTING',
                              'REVIEWING',
                              'VALIDATING',
                              'APPROVED',
                              'RETRY_PENDING',
                              'FAILED_AFTER_RETRIES',
                              'PAUSED_PROVIDER',
                              'COMPLETED'
                          )),
  status          TEXT    NOT NULL DEFAULT 'active'
                          CHECK (status IN ('active', 'done', 'failed')),
  started_at      TEXT    NOT NULL,
  finished_at     TEXT    NULL,
  previous_state  TEXT    NULL,
  UNIQUE (task_id, attempt_number)
);

CREATE INDEX IF NOT EXISTS idx_attempts_task  ON attempts(task_id);
CREATE INDEX IF NOT EXISTS idx_attempts_state ON attempts(state);

-- ----------------------------------------------------------------------
-- LLMCall
-- ----------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS llm_calls (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  attempt_id    INTEGER NOT NULL
                          REFERENCES attempts(id) ON DELETE CASCADE,
  role          TEXT    NOT NULL
                          CHECK (role IN ('generator', 'reviewer', 'validator')),
  provider      TEXT    NULL,
  model         TEXT    NULL,
  latency_ms    INTEGER NULL
                          CHECK (latency_ms IS NULL OR latency_ms >= 0),
  token_usage   INTEGER NULL
                          CHECK (token_usage IS NULL OR token_usage >= 0),
  prompt_ref    TEXT    NULL,
  response_ref  TEXT    NULL,
  created_at    TEXT    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_llm_calls_attempt ON llm_calls(attempt_id);

-- ----------------------------------------------------------------------
-- Review
-- ----------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS reviews (
  id                  INTEGER PRIMARY KEY AUTOINCREMENT,
  attempt_id          INTEGER NOT NULL
                              REFERENCES attempts(id) ON DELETE CASCADE,
  issues_found        TEXT    NOT NULL,
  instructions_for_fix TEXT   NULL
);

CREATE INDEX IF NOT EXISTS idx_reviews_attempt ON reviews(attempt_id);

-- ----------------------------------------------------------------------
-- Validation
-- ----------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS validations (
  id               INTEGER PRIMARY KEY AUTOINCREMENT,
  attempt_id       INTEGER NOT NULL
                           REFERENCES attempts(id) ON DELETE CASCADE,
  status           TEXT    NOT NULL
                           CHECK (status IN ('approved', 'rejected')),
  score            REAL    NULL,
  reason           TEXT    NULL,
  blocking_issues  TEXT    NULL
);

CREATE INDEX IF NOT EXISTS idx_validations_attempt ON validations(attempt_id);

-- ----------------------------------------------------------------------
-- Error
-- ----------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS errors (
  id             INTEGER PRIMARY KEY AUTOINCREMENT,
  attempt_id     INTEGER NOT NULL
                         REFERENCES attempts(id) ON DELETE CASCADE,
  type           TEXT    NOT NULL,
  message        TEXT    NOT NULL,
  raw_output_ref TEXT    NULL,
  created_at     TEXT    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_errors_attempt ON errors(attempt_id);

-- ----------------------------------------------------------------------
-- Memory (memoire long-terme cle/valeur)
-- ----------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS memories (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  project_id INTEGER NULL
                     REFERENCES projects(id) ON DELETE CASCADE,
  scope      TEXT    NOT NULL,
  key        TEXT    NOT NULL,
  value      TEXT    NOT NULL,
  updated_at TEXT    NOT NULL,
  UNIQUE (scope, key)
);

CREATE INDEX IF NOT EXISTS idx_memories_project ON memories(project_id);

-- ----------------------------------------------------------------------
-- ProviderState
-- ----------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS provider_states (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  provider        TEXT    NOT NULL,
  model           TEXT    NOT NULL,
  status          TEXT    NOT NULL
                          CHECK (status IN ('up', 'down', 'unknown')),
  last_checked_at TEXT    NOT NULL,
  retry_after     TEXT    NULL,
  UNIQUE (provider, model)
);

-- ----------------------------------------------------------------------
-- GitSnapshot
-- ----------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS git_snapshots (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  attempt_id INTEGER NULL
                     REFERENCES attempts(id) ON DELETE SET NULL,
  level_id   INTEGER NULL
                     REFERENCES levels(id) ON DELETE SET NULL,
  commit_hash TEXT   NOT NULL,
  branch     TEXT    NOT NULL,
  created_at TEXT    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_git_snapshots_attempt ON git_snapshots(attempt_id);
CREATE INDEX IF NOT EXISTS idx_git_snapshots_level   ON git_snapshots(level_id);
