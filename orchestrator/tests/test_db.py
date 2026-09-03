"""
Tests lies a la base SQLite : DDL idempotent, PRAGMA, transactions.
"""

from __future__ import annotations

import sqlite3

import pytest

from src.memory import Database


def test_initialize_is_idempotent(tmp_db_path):
    db = Database(tmp_db_path)
    db.initialize()
    db.initialize()  # doit passer sans erreur
    db.close()


def test_pragmas_applied(tmp_db_path):
    db = Database(tmp_db_path)
    db.initialize()
    cur = db.connection.execute("PRAGMA foreign_keys")
    assert cur.fetchone()[0] == 1
    cur = db.connection.execute("PRAGMA journal_mode")
    assert cur.fetchone()[0].lower() == "wal"
    db.close()


def test_all_expected_tables_exist(tmp_db_path):
    db = Database(tmp_db_path)
    db.initialize()
    expected = {
        "projects", "levels", "tasks", "attempts",
        "llm_calls", "reviews", "validations", "errors",
        "memories", "provider_states", "git_snapshots",
        "state_transitions",
    }
    rows = db.connection.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()
    names = {r["name"] for r in rows}
    assert expected.issubset(names), f"Missing tables: {expected - names}"
    db.close()


def test_transaction_commit(tmp_db_path):
    db = Database(tmp_db_path)
    db.initialize()
    with db.transaction() as conn:
        conn.execute(
            "INSERT INTO projects (name, status, created_at) VALUES (?, 'active', '2024-01-01T00:00:00')",
            ("tx-commit",),
        )
    row = db.connection.execute(
        "SELECT name FROM projects WHERE name = 'tx-commit'"
    ).fetchone()
    assert row is not None
    db.close()


def test_transaction_rollback(tmp_db_path):
    db = Database(tmp_db_path)
    db.initialize()
    with pytest.raises(RuntimeError):
        with db.transaction() as conn:
            conn.execute(
                "INSERT INTO projects (name, status, created_at) VALUES (?, 'active', '2024-01-01')",
                ("tx-rollback",),
            )
            raise RuntimeError("boom")
    row = db.connection.execute(
        "SELECT name FROM projects WHERE name = 'tx-rollback'"
    ).fetchone()
    assert row is None
    db.close()


def test_foreign_keys_enforced(tmp_db_path):
    db = Database(tmp_db_path)
    db.initialize()
    # Inserer un level qui reference un project_id inexistant doit echouer.
    with pytest.raises(sqlite3.IntegrityError):
        db.connection.execute(
            "INSERT INTO levels (project_id, level_number, spec, status, created_at) "
            "VALUES (?, ?, ?, 'pending', '2024-01-01')",
            (99999, 1, "spec"),
        )
    db.close()
