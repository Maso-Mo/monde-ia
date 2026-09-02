"""
Repository central pour toutes les entites ZFLM.

Toutes les operations passent par :class:`Database` ; aucune n'utilise
de SQL hors de ce module.

API par entite :

- ProjectRepository  : create, get, list, update_status, set_current_level
- LevelRepository    : create, get, list_for_project, update_status
- TaskRepository     : create, get, list_for_level, update_status, count_for_task
- AttemptRepository  : create, get, list_for_task, count_for_task,
                       update_state, count_per_task, latest_active,
                       latest_in_state
- LLMCallRepository  : create, list_for_attempt
- ReviewRepository   : create, list_for_attempt
- ValidationRepository : create, list_for_attempt
- ErrorRepository    : create, list_for_attempt
- MemoryRepository   : upsert, get, delete, list
- ProviderStateRepository : upsert, get, list
- GitSnapshotRepository : create, list_for_attempt
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Iterable, Optional

from .connection import Database
from .models import (
    Attempt,
    ErrorRecord,
    GitSnapshot,
    Level,
    LLMCall,
    MemoryEntry,
    Project,
    ProviderState,
    Review,
    Task,
    Validation,
    row_to_attempt,
    row_to_error,
    row_to_git_snapshot,
    row_to_level,
    row_to_llm_call,
    row_to_memory,
    row_to_project,
    row_to_provider_state,
    row_to_review,
    row_to_task,
    row_to_validation,
)


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ----------------------------------------------------------------------
# Projects
# ----------------------------------------------------------------------


class ProjectRepository:
    def __init__(self, db: Database):
        self._db = db

    def create(self, name: str, *, status: str = "active") -> Project:
        created_at = _utcnow_iso()
        with self._db.transaction() as conn:
            cur = conn.execute(
                "INSERT INTO projects (name, status, created_at) VALUES (?, ?, ?)",
                (name, status, created_at),
            )
            pid = cur.lastrowid
        return Project(id=pid, name=name, status=status, created_at=created_at)

    def get(self, project_id: int) -> Project | None:
        row = self._db.connection.execute(
            "SELECT * FROM projects WHERE id = ?", (project_id,)
        ).fetchone()
        return row_to_project(row) if row else None

    def list_all(self) -> list[Project]:
        rows = self._db.connection.execute(
            "SELECT * FROM projects ORDER BY id"
        ).fetchall()
        return [row_to_project(r) for r in rows]

    def update_status(self, project_id: int, status: str) -> None:
        self._db.connection.execute(
            "UPDATE projects SET status = ? WHERE id = ?",
            (status, project_id),
        )

    def set_current_level(self, project_id: int, level_id: int | None) -> None:
        self._db.connection.execute(
            "UPDATE projects SET current_level_id = ? WHERE id = ?",
            (level_id, project_id),
        )


# ----------------------------------------------------------------------
# Levels
# ----------------------------------------------------------------------


class LevelRepository:
    def __init__(self, db: Database):
        self._db = db

    def create(
        self,
        project_id: int,
        level_number: int,
        spec: str,
        *,
        status: str = "pending",
    ) -> Level:
        created_at = _utcnow_iso()
        with self._db.transaction() as conn:
            cur = conn.execute(
                "INSERT INTO levels (project_id, level_number, spec, status, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (project_id, level_number, spec, status, created_at),
            )
            lid = cur.lastrowid
        return Level(
            id=lid,
            project_id=project_id,
            level_number=level_number,
            spec=spec,
            status=status,
            created_at=created_at,
        )

    def get(self, level_id: int) -> Level | None:
        row = self._db.connection.execute(
            "SELECT * FROM levels WHERE id = ?", (level_id,)
        ).fetchone()
        return row_to_level(row) if row else None

    def list_for_project(self, project_id: int) -> list[Level]:
        rows = self._db.connection.execute(
            "SELECT * FROM levels WHERE project_id = ? ORDER BY level_number",
            (project_id,),
        ).fetchall()
        return [row_to_level(r) for r in rows]

    def update_status(self, level_id: int, status: str) -> None:
        self._db.connection.execute(
            "UPDATE levels SET status = ? WHERE id = ?", (status, level_id)
        )


# ----------------------------------------------------------------------
# Tasks
# ----------------------------------------------------------------------


class TaskRepository:
    def __init__(self, db: Database):
        self._db = db

    def create(
        self,
        level_id: int,
        description: str,
        *,
        status: str = "pending",
    ) -> Task:
        created_at = _utcnow_iso()
        with self._db.transaction() as conn:
            cur = conn.execute(
                "INSERT INTO tasks (level_id, description, status, created_at) "
                "VALUES (?, ?, ?, ?)",
                (level_id, description, status, created_at),
            )
            tid = cur.lastrowid
        return Task(
            id=tid, level_id=level_id, description=description,
            status=status, created_at=created_at,
        )

    def get(self, task_id: int) -> Task | None:
        row = self._db.connection.execute(
            "SELECT * FROM tasks WHERE id = ?", (task_id,)
        ).fetchone()
        return row_to_task(row) if row else None

    def list_for_level(self, level_id: int) -> list[Task]:
        rows = self._db.connection.execute(
            "SELECT * FROM tasks WHERE level_id = ? ORDER BY id", (level_id,)
        ).fetchall()
        return [row_to_task(r) for r in rows]

    def update_status(self, task_id: int, status: str) -> None:
        self._db.connection.execute(
            "UPDATE tasks SET status = ? WHERE id = ?", (status, task_id)
        )

    def count_for_level(self, level_id: int) -> int:
        row = self._db.connection.execute(
            "SELECT COUNT(*) AS c FROM tasks WHERE level_id = ?", (level_id,)
        ).fetchone()
        return row["c"]


# ----------------------------------------------------------------------
# Attempts
# ----------------------------------------------------------------------


class AttemptRepository:
    def __init__(self, db: Database):
        self._db = db

    def create(
        self,
        task_id: int,
        attempt_number: int,
        *,
        state: str = "CREATED",
    ) -> Attempt:
        started_at = _utcnow_iso()
        with self._db.transaction() as conn:
            cur = conn.execute(
                "INSERT INTO attempts (task_id, attempt_number, state, status, started_at) "
                "VALUES (?, ?, ?, 'active', ?)",
                (task_id, attempt_number, state, started_at),
            )
            aid = cur.lastrowid
        return Attempt(
            id=aid,
            task_id=task_id,
            attempt_number=attempt_number,
            state=state,
            status="active",
            started_at=started_at,
        )

    def get(self, attempt_id: int) -> Attempt | None:
        row = self._db.connection.execute(
            "SELECT * FROM attempts WHERE id = ?", (attempt_id,)
        ).fetchone()
        return row_to_attempt(row) if row else None

    def list_for_task(self, task_id: int) -> list[Attempt]:
        rows = self._db.connection.execute(
            "SELECT * FROM attempts WHERE task_id = ? ORDER BY attempt_number",
            (task_id,),
        ).fetchall()
        return [row_to_attempt(r) for r in rows]

    def count_for_task(self, task_id: int) -> int:
        row = self._db.connection.execute(
            "SELECT COUNT(*) AS c FROM attempts WHERE task_id = ?", (task_id,)
        ).fetchone()
        return row["c"]

    def update_state(
        self,
        attempt_id: int,
        *,
        state: str,
        previous_state: str | None = None,
        finished_at: str | None = None,
    ) -> None:
        """Met a jour state / previous_state / finished_at d'un Attempt.

        Utilise par :class:`AttemptStateMachine`.
        """
        self._db.connection.execute(
            "UPDATE attempts SET state = ?, previous_state = ?, finished_at = ? "
            "WHERE id = ?",
            (state, previous_state, finished_at, attempt_id),
        )

    def update_status(self, attempt_id: int, status: str) -> None:
        """Met a jour status (active | done | failed)."""
        self._db.connection.execute(
            "UPDATE attempts SET status = ? WHERE id = ?", (status, attempt_id)
        )

    def latest_active(self) -> Attempt | None:
        """Renvoie l'Attempt actif le plus recent (non COMPLETED)."""
        row = self._db.connection.execute(
            "SELECT * FROM attempts WHERE state != 'COMPLETED' "
            "ORDER BY id DESC LIMIT 1"
        ).fetchone()
        return row_to_attempt(row) if row else None

    def latest_in_state(self, state: str) -> Attempt | None:
        row = self._db.connection.execute(
            "SELECT * FROM attempts WHERE state = ? ORDER BY id DESC LIMIT 1",
            (state,),
        ).fetchone()
        return row_to_attempt(row) if row else None


# ----------------------------------------------------------------------
# LLMCalls
# ----------------------------------------------------------------------


class LLMCallRepository:
    def __init__(self, db: Database):
        self._db = db

    def create(
        self,
        attempt_id: int,
        role: str,
        *,
        provider: str | None = None,
        model: str | None = None,
        latency_ms: int | None = None,
        token_usage: int | None = None,
        prompt_ref: str | None = None,
        response_ref: str | None = None,
    ) -> LLMCall:
        created_at = _utcnow_iso()
        with self._db.transaction() as conn:
            cur = conn.execute(
                "INSERT INTO llm_calls (attempt_id, role, provider, model, "
                "latency_ms, token_usage, prompt_ref, response_ref, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (attempt_id, role, provider, model, latency_ms, token_usage,
                 prompt_ref, response_ref, created_at),
            )
            cid = cur.lastrowid
        return LLMCall(
            id=cid, attempt_id=attempt_id, role=role,
            provider=provider, model=model,
            latency_ms=latency_ms, token_usage=token_usage,
            prompt_ref=prompt_ref, response_ref=response_ref,
            created_at=created_at,
        )

    def list_for_attempt(self, attempt_id: int) -> list[LLMCall]:
        rows = self._db.connection.execute(
            "SELECT * FROM llm_calls WHERE attempt_id = ? ORDER BY id",
            (attempt_id,),
        ).fetchall()
        return [row_to_llm_call(r) for r in rows]


# ----------------------------------------------------------------------
# Reviews
# ----------------------------------------------------------------------


class ReviewRepository:
    def __init__(self, db: Database):
        self._db = db

    def create(
        self,
        attempt_id: int,
        issues_found: list[str] | str,
        instructions_for_fix: str | None = None,
    ) -> Review:
        if isinstance(issues_found, list):
            issues_found = json.dumps(issues_found, ensure_ascii=False)
        with self._db.transaction() as conn:
            cur = conn.execute(
                "INSERT INTO reviews (attempt_id, issues_found, instructions_for_fix) "
                "VALUES (?, ?, ?)",
                (attempt_id, issues_found, instructions_for_fix),
            )
            rid = cur.lastrowid
        return Review(
            id=rid, attempt_id=attempt_id,
            issues_found=issues_found,
            instructions_for_fix=instructions_for_fix,
        )

    def list_for_attempt(self, attempt_id: int) -> list[Review]:
        rows = self._db.connection.execute(
            "SELECT * FROM reviews WHERE attempt_id = ? ORDER BY id",
            (attempt_id,),
        ).fetchall()
        return [row_to_review(r) for r in rows]


# ----------------------------------------------------------------------
# Validations
# ----------------------------------------------------------------------


class ValidationRepository:
    def __init__(self, db: Database):
        self._db = db

    def create(
        self,
        attempt_id: int,
        status: str,
        *,
        score: float | None = None,
        reason: str | None = None,
        blocking_issues: list[str] | str | None = None,
    ) -> Validation:
        if isinstance(blocking_issues, list):
            blocking_issues = json.dumps(blocking_issues, ensure_ascii=False)
        with self._db.transaction() as conn:
            cur = conn.execute(
                "INSERT INTO validations (attempt_id, status, score, reason, blocking_issues) "
                "VALUES (?, ?, ?, ?, ?)",
                (attempt_id, status, score, reason, blocking_issues),
            )
            vid = cur.lastrowid
        return Validation(
            id=vid, attempt_id=attempt_id, status=status,
            score=score, reason=reason, blocking_issues=blocking_issues,
        )

    def list_for_attempt(self, attempt_id: int) -> list[Validation]:
        rows = self._db.connection.execute(
            "SELECT * FROM validations WHERE attempt_id = ? ORDER BY id",
            (attempt_id,),
        ).fetchall()
        return [row_to_validation(r) for r in rows]


# ----------------------------------------------------------------------
# Errors
# ----------------------------------------------------------------------


class ErrorRepository:
    def __init__(self, db: Database):
        self._db = db

    def create(
        self,
        attempt_id: int,
        type: str,
        message: str,
        raw_output_ref: str | None = None,
    ) -> ErrorRecord:
        created_at = _utcnow_iso()
        with self._db.transaction() as conn:
            cur = conn.execute(
                "INSERT INTO errors (attempt_id, type, message, raw_output_ref, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (attempt_id, type, message, raw_output_ref, created_at),
            )
            eid = cur.lastrowid
        return ErrorRecord(
            id=eid, attempt_id=attempt_id, type=type,
            message=message, raw_output_ref=raw_output_ref,
            created_at=created_at,
        )

    def list_for_attempt(self, attempt_id: int) -> list[ErrorRecord]:
        rows = self._db.connection.execute(
            "SELECT * FROM errors WHERE attempt_id = ? ORDER BY id",
            (attempt_id,),
        ).fetchall()
        return [row_to_error(r) for r in rows]


# ----------------------------------------------------------------------
# Memories
# ----------------------------------------------------------------------


class MemoryRepository:
    def __init__(self, db: Database):
        self._db = db

    def upsert(
        self,
        scope: str,
        key: str,
        value: str,
        *,
        project_id: int | None = None,
    ) -> MemoryEntry:
        updated_at = _utcnow_iso()
        with self._db.transaction() as conn:
            conn.execute(
                "INSERT INTO memories (project_id, scope, key, value, updated_at) "
                "VALUES (?, ?, ?, ?, ?) "
                "ON CONFLICT(scope, key) DO UPDATE SET "
                "  project_id = excluded.project_id, "
                "  value      = excluded.value, "
                "  updated_at = excluded.updated_at",
                (project_id, scope, key, value, updated_at),
            )
            row = conn.execute(
                "SELECT * FROM memories WHERE scope = ? AND key = ?",
                (scope, key),
            ).fetchone()
        return row_to_memory(row)

    def get(self, scope: str, key: str) -> MemoryEntry | None:
        row = self._db.connection.execute(
            "SELECT * FROM memories WHERE scope = ? AND key = ?",
            (scope, key),
        ).fetchone()
        return row_to_memory(row) if row else None

    def list_for_project(self, project_id: int) -> list[MemoryEntry]:
        rows = self._db.connection.execute(
            "SELECT * FROM memories WHERE project_id = ? ORDER BY id",
            (project_id,),
        ).fetchall()
        return [row_to_memory(r) for r in rows]

    def list_all(self) -> list[MemoryEntry]:
        rows = self._db.connection.execute(
            "SELECT * FROM memories ORDER BY id"
        ).fetchall()
        return [row_to_memory(r) for r in rows]

    def delete(self, scope: str, key: str) -> None:
        self._db.connection.execute(
            "DELETE FROM memories WHERE scope = ? AND key = ?", (scope, key)
        )


# ----------------------------------------------------------------------
# ProviderStates
# ----------------------------------------------------------------------


class ProviderStateRepository:
    def __init__(self, db: Database):
        self._db = db

    def upsert(
        self,
        provider: str,
        model: str,
        status: str,
        retry_after: str | None = None,
    ) -> ProviderState:
        last_checked_at = _utcnow_iso()
        with self._db.transaction() as conn:
            conn.execute(
                "INSERT INTO provider_states (provider, model, status, last_checked_at, retry_after) "
                "VALUES (?, ?, ?, ?, ?) "
                "ON CONFLICT(provider, model) DO UPDATE SET "
                "  status          = excluded.status, "
                "  last_checked_at = excluded.last_checked_at, "
                "  retry_after     = excluded.retry_after",
                (provider, model, status, last_checked_at, retry_after),
            )
            row = conn.execute(
                "SELECT * FROM provider_states WHERE provider = ? AND model = ?",
                (provider, model),
            ).fetchone()
        return row_to_provider_state(row)

    def get(self, provider: str, model: str) -> ProviderState | None:
        row = self._db.connection.execute(
            "SELECT * FROM provider_states WHERE provider = ? AND model = ?",
            (provider, model),
        ).fetchone()
        return row_to_provider_state(row) if row else None

    def list_all(self) -> list[ProviderState]:
        rows = self._db.connection.execute(
            "SELECT * FROM provider_states ORDER BY id"
        ).fetchall()
        return [row_to_provider_state(r) for r in rows]


# ----------------------------------------------------------------------
# GitSnapshots
# ----------------------------------------------------------------------


class GitSnapshotRepository:
    def __init__(self, db: Database):
        self._db = db

    def create(
        self,
        commit_hash: str,
        branch: str,
        *,
        attempt_id: int | None = None,
        level_id: int | None = None,
    ) -> GitSnapshot:
        created_at = _utcnow_iso()
        with self._db.transaction() as conn:
            cur = conn.execute(
                "INSERT INTO git_snapshots (attempt_id, level_id, commit_hash, branch, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (attempt_id, level_id, commit_hash, branch, created_at),
            )
            gid = cur.lastrowid
        return GitSnapshot(
            id=gid, attempt_id=attempt_id, level_id=level_id,
            commit_hash=commit_hash, branch=branch, created_at=created_at,
        )

    def list_for_attempt(self, attempt_id: int) -> list[GitSnapshot]:
        rows = self._db.connection.execute(
            "SELECT * FROM git_snapshots WHERE attempt_id = ? ORDER BY id",
            (attempt_id,),
        ).fetchall()
        return [row_to_git_snapshot(r) for r in rows]


__all__ = [
    "ProjectRepository",
    "LevelRepository",
    "TaskRepository",
    "AttemptRepository",
    "LLMCallRepository",
    "ReviewRepository",
    "ValidationRepository",
    "ErrorRepository",
    "MemoryRepository",
    "ProviderStateRepository",
    "GitSnapshotRepository",
]
