"""
Tests CRUD pour Project, Level, Task, Attempt.
"""

from __future__ import annotations


def test_create_project(repos):
    p = repos["projects"].create("hello")
    assert p.id is not None
    assert p.name == "hello"
    assert p.status == "active"
    assert p.created_at  # ISO timestamp non vide


def test_get_project(repos):
    p1 = repos["projects"].create("alpha")
    p2 = repos["projects"].get(p1.id)
    assert p2 is not None
    assert p2.name == "alpha"
    assert repos["projects"].get(99999) is None


def test_list_projects(repos):
    repos["projects"].create("a")
    repos["projects"].create("b")
    projects = repos["projects"].list_all()
    assert len(projects) == 2
    assert {p.name for p in projects} == {"a", "b"}


def test_update_project_status(repos):
    p = repos["projects"].create("x")
    repos["projects"].update_status(p.id, "paused")
    assert repos["projects"].get(p.id).status == "paused"


def test_set_current_level(repos):
    p = repos["projects"].create("p")
    lvl = repos["levels"].create(p.id, 1, "spec")
    repos["projects"].set_current_level(p.id, lvl.id)
    assert repos["projects"].get(p.id).current_level_id == lvl.id


def test_create_level(repos):
    p = repos["projects"].create("p")
    lvl = repos["levels"].create(p.id, 1, "spec-1")
    assert lvl.id is not None
    assert lvl.project_id == p.id
    assert lvl.level_number == 1
    assert lvl.status == "pending"


def test_unique_project_level_number(repos):
    import sqlite3
    p = repos["projects"].create("p")
    repos["levels"].create(p.id, 1, "spec")
    with __import__("pytest").raises(sqlite3.IntegrityError):
        repos["levels"].create(p.id, 1, "spec-dup")


def test_create_task(repos):
    p = repos["projects"].create("p")
    lvl = repos["levels"].create(p.id, 1, "spec")
    t = repos["tasks"].create(lvl.id, "do something")
    assert t.id is not None
    assert t.level_id == lvl.id
    assert t.status == "pending"


def test_create_attempt(repos):
    p = repos["projects"].create("p")
    lvl = repos["levels"].create(p.id, 1, "spec")
    t = repos["tasks"].create(lvl.id, "do")
    a = repos["attempts"].create(t.id, 1)
    assert a.id is not None
    assert a.task_id == t.id
    assert a.attempt_number == 1
    assert a.state == "CREATED"
    assert a.status == "active"
    assert a.finished_at is None


def test_attempt_count_for_task(repos):
    p = repos["projects"].create("p")
    lvl = repos["levels"].create(p.id, 1, "spec")
    t = repos["tasks"].create(lvl.id, "do")
    assert repos["attempts"].count_for_task(t.id) == 0
    repos["attempts"].create(t.id, 1)
    repos["attempts"].create(t.id, 2)
    assert repos["attempts"].count_for_task(t.id) == 2


def test_attempt_update_state(repos):
    p = repos["projects"].create("p")
    lvl = repos["levels"].create(p.id, 1, "spec")
    t = repos["tasks"].create(lvl.id, "do")
    a = repos["attempts"].create(t.id, 1)
    repos["attempts"].update_state(
        a.id, state="BUILDING", previous_state="GENERATING"
    )
    refreshed = repos["attempts"].get(a.id)
    assert refreshed.state == "BUILDING"
    assert refreshed.previous_state == "GENERATING"


def test_invalid_state_rejected_by_schema(repos):
    import sqlite3
    p = repos["projects"].create("p")
    lvl = repos["levels"].create(p.id, 1, "spec")
    t = repos["tasks"].create(lvl.id, "do")
    repos["attempts"].create(t.id, 1)
    a = repos["attempts"].list_for_task(t.id)[0]
    with __import__("pytest").raises(sqlite3.IntegrityError):
        repos["attempts"].update_state(a.id, state="NOT_A_REAL_STATE")


def test_invalid_attempt_number_rejected(repos):
    import sqlite3
    import pytest
    p = repos["projects"].create("p")
    lvl = repos["levels"].create(p.id, 1, "spec")
    t = repos["tasks"].create(lvl.id, "do")
    with pytest.raises(sqlite3.IntegrityError):
        repos["attempts"].create(t.id, 99)


def test_llm_call_creation(repos):
    p = repos["projects"].create("p")
    lvl = repos["levels"].create(p.id, 1, "spec")
    t = repos["tasks"].create(lvl.id, "do")
    a = repos["attempts"].create(t.id, 1)
    call = repos["llm_calls"].create(
        a.id, "generator", provider="mock", model="m", latency_ms=10, token_usage=42
    )
    assert call.id is not None
    assert call.role == "generator"
    listed = repos["llm_calls"].list_for_attempt(a.id)
    assert len(listed) == 1


def test_review_creation(repos):
    p = repos["projects"].create("p")
    lvl = repos["levels"].create(p.id, 1, "spec")
    t = repos["tasks"].create(lvl.id, "do")
    a = repos["attempts"].create(t.id, 1)
    r = repos["reviews"].create(a.id, ["issue-a", "issue-b"], "fix things")
    assert r.id is not None
    assert "issue-a" in r.issues_found


def test_validation_creation(repos):
    p = repos["projects"].create("p")
    lvl = repos["levels"].create(p.id, 1, "spec")
    t = repos["tasks"].create(lvl.id, "do")
    a = repos["attempts"].create(t.id, 1)
    v = repos["validations"].create(a.id, "approved", score=0.9, reason="ok")
    assert v.status == "approved"


def test_error_creation(repos):
    p = repos["projects"].create("p")
    lvl = repos["levels"].create(p.id, 1, "spec")
    t = repos["tasks"].create(lvl.id, "do")
    a = repos["attempts"].create(t.id, 1)
    e = repos["errors"].create(a.id, "BuildError", "missing file")
    assert e.id is not None
    assert e.type == "BuildError"


def test_memory_upsert_and_get(repos):
    m1 = repos["memories"].upsert("global", "last_success", "html-basic")
    assert m1.id is not None
    again = repos["memories"].upsert("global", "last_success", "css-basic")
    assert again.id == m1.id
    assert again.value == "css-basic"
    assert repos["memories"].get("global", "last_success").value == "css-basic"


def test_provider_state_upsert(repos):
    s1 = repos["provider_states"].upsert("mock", "m", "up")
    s2 = repos["provider_states"].upsert("mock", "m", "down", retry_after="2024-01-01T00:00:00")
    assert s1.id == s2.id
    assert s2.status == "down"
    assert s2.retry_after == "2024-01-01T00:00:00"


def test_git_snapshot(repos):
    p = repos["projects"].create("p")
    lvl = repos["levels"].create(p.id, 1, "spec")
    t = repos["tasks"].create(lvl.id, "do")
    a = repos["attempts"].create(t.id, 1)
    snap = repos["git_snapshots"].create("abc123", "main", attempt_id=a.id, level_id=lvl.id)
    listed = repos["git_snapshots"].list_for_attempt(a.id)
    assert len(listed) == 1
    assert listed[0].commit_hash == "abc123"
