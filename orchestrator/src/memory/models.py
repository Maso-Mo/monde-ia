"""
Dataclasses representant les entites ZFLM (DTOs legers).

Pas de methodes de persistance, pas de validation Pydantic en V1.
Le mapping ligne <-> dataclass est centralise dans ``row_to_xxx``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any


def _row_get(row, key, default=None):
    try:
        return row[key]
    except (IndexError, KeyError):
        return default


def _isoformat(dt):
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()


@dataclass(slots=True)
class Project:
    id: int | None
    name: str
    status: str = "active"
    created_at: str = ""
    current_level_id: int | None = None


@dataclass(slots=True)
class Level:
    id: int | None
    project_id: int
    level_number: int
    spec: str
    status: str = "pending"
    created_at: str = ""


@dataclass(slots=True)
class Task:
    id: int | None
    level_id: int
    description: str
    status: str = "pending"
    created_at: str = ""


@dataclass(slots=True)
class Attempt:
    id: int | None
    task_id: int
    attempt_number: int
    state: str = "CREATED"
    status: str = "active"
    started_at: str = ""
    finished_at: str | None = None
    previous_state: str | None = None


@dataclass(slots=True)
class LLMCall:
    id: int | None
    attempt_id: int
    role: str
    provider: str | None = None
    model: str | None = None
    latency_ms: int | None = None
    token_usage: int | None = None
    prompt_ref: str | None = None
    response_ref: str | None = None
    created_at: str = ""


@dataclass(slots=True)
class Review:
    id: int | None
    attempt_id: int
    issues_found: str
    instructions_for_fix: str | None = None


@dataclass(slots=True)
class Validation:
    id: int | None
    attempt_id: int
    status: str
    score: float | None = None
    reason: str | None = None
    blocking_issues: str | None = None


@dataclass(slots=True)
class ErrorRecord:
    id: int | None
    attempt_id: int
    type: str
    message: str
    raw_output_ref: str | None = None
    created_at: str = ""


@dataclass(slots=True)
class MemoryEntry:
    id: int | None
    project_id: int | None
    scope: str
    key: str
    value: str
    updated_at: str = ""


@dataclass(slots=True)
class ProviderState:
    id: int | None
    provider: str
    model: str
    status: str
    last_checked_at: str
    retry_after: str | None = None


@dataclass(slots=True)
class GitSnapshot:
    id: int | None
    attempt_id: int | None
    level_id: int | None
    commit_hash: str
    branch: str
    created_at: str = ""


def row_to_project(row):
    return Project(
        id=row["id"],
        name=row["name"],
        status=row["status"],
        created_at=row["created_at"],
        current_level_id=_row_get(row, "current_level_id"),
    )


def row_to_level(row):
    return Level(
        id=row["id"],
        project_id=row["project_id"],
        level_number=row["level_number"],
        spec=row["spec"],
        status=row["status"],
        created_at=row["created_at"],
    )


def row_to_task(row):
    return Task(
        id=row["id"],
        level_id=row["level_id"],
        description=row["description"],
        status=row["status"],
        created_at=row["created_at"],
    )


def row_to_attempt(row):
    return Attempt(
        id=row["id"],
        task_id=row["task_id"],
        attempt_number=row["attempt_number"],
        state=row["state"],
        status=row["status"],
        started_at=row["started_at"],
        finished_at=_row_get(row, "finished_at"),
        previous_state=_row_get(row, "previous_state"),
    )


def row_to_llm_call(row):
    return LLMCall(
        id=row["id"],
        attempt_id=row["attempt_id"],
        role=row["role"],
        provider=_row_get(row, "provider"),
        model=_row_get(row, "model"),
        latency_ms=_row_get(row, "latency_ms"),
        token_usage=_row_get(row, "token_usage"),
        prompt_ref=_row_get(row, "prompt_ref"),
        response_ref=_row_get(row, "response_ref"),
        created_at=row["created_at"],
    )


def row_to_review(row):
    return Review(
        id=row["id"],
        attempt_id=row["attempt_id"],
        issues_found=row["issues_found"],
        instructions_for_fix=_row_get(row, "instructions_for_fix"),
    )


def row_to_validation(row):
    return Validation(
        id=row["id"],
        attempt_id=row["attempt_id"],
        status=row["status"],
        score=_row_get(row, "score"),
        reason=_row_get(row, "reason"),
        blocking_issues=_row_get(row, "blocking_issues"),
    )


def row_to_error(row):
    return ErrorRecord(
        id=row["id"],
        attempt_id=row["attempt_id"],
        type=row["type"],
        message=row["message"],
        raw_output_ref=_row_get(row, "raw_output_ref"),
        created_at=row["created_at"],
    )


def row_to_memory(row):
    return MemoryEntry(
        id=row["id"],
        project_id=_row_get(row, "project_id"),
        scope=row["scope"],
        key=row["key"],
        value=row["value"],
        updated_at=row["updated_at"],
    )


def row_to_provider_state(row):
    return ProviderState(
        id=row["id"],
        provider=row["provider"],
        model=row["model"],
        status=row["status"],
        last_checked_at=row["last_checked_at"],
        retry_after=_row_get(row, "retry_after"),
    )


def row_to_git_snapshot(row):
    return GitSnapshot(
        id=row["id"],
        attempt_id=_row_get(row, "attempt_id"),
        level_id=_row_get(row, "level_id"),
        commit_hash=row["commit_hash"],
        branch=row["branch"],
        created_at=row["created_at"],
    )


__all__ = [
    "Project",
    "Level",
    "Task",
    "Attempt",
    "LLMCall",
    "Review",
    "Validation",
    "ErrorRecord",
    "MemoryEntry",
    "ProviderState",
    "GitSnapshot",
    "row_to_project",
    "row_to_level",
    "row_to_task",
    "row_to_attempt",
    "row_to_llm_call",
    "row_to_review",
    "row_to_validation",
    "row_to_error",
    "row_to_memory",
    "row_to_provider_state",
    "row_to_git_snapshot",
]
