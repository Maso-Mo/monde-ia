"""
Wrapper léger autour de sqlite3.

Responsabilités :
- ouvrir une connexion avec PRAGMA foreign_keys=ON ;
- exécuter le schéma (CREATE TABLE IF NOT EXISTS) à la demande ;
- exposer un context manager de transaction ;
- être réutilisable depuis plusieurs modules (repository).

On n'utilise PAS SQLAlchemy. SQLite est directement utilisé via
sqlite3 (stdlib). L'objectif est la lisibilité et la simplicité.
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

# Chemin absolu vers schema.sql, calculé à partir de ce module.
_SCHEMA_PATH = Path(__file__).resolve().parent / "schema.sql"


class Database:
    """Représente une connexion SQLite + état d'initialisation."""

    def __init__(self, path: Path | str):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn: sqlite3.Connection | None = None

    # ------------------------------------------------------------------
    # Cycle de vie
    # ------------------------------------------------------------------

    def connect(self) -> sqlite3.Connection:
        """Ouvre la connexion si nécessaire, applique les PRAGMA."""
        if self._conn is None:
            self._conn = sqlite3.connect(
                str(self.path),
                isolation_level=None,  # autocommit ; on gère via transactions explicites
                detect_types=sqlite3.PARSE_DECLTYPES,
            )
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA foreign_keys = ON")
            self._conn.execute("PRAGMA journal_mode = WAL")
        return self._conn

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def __enter__(self) -> "Database":
        self.connect()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    # ------------------------------------------------------------------
    # Initialisation
    # ------------------------------------------------------------------

    def initialize(self) -> None:
        """Exécute le DDL (idempotent). Crée les tables si absentes."""
        conn = self.connect()
        sql = _SCHEMA_PATH.read_text(encoding="utf-8")
        conn.executescript(sql)

    # ------------------------------------------------------------------
    # Transactions
    # ------------------------------------------------------------------

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        """Context manager de transaction explicite.

        Usage :

            with db.transaction() as conn:
                conn.execute(...)

        À la sortie sans exception : COMMIT. Avec exception : ROLLBACK.
        """
        conn = self.connect()
        conn.execute("BEGIN")
        try:
            yield conn
        except BaseException:
            conn.execute("ROLLBACK")
            raise
        else:
            conn.execute("COMMIT")

    # ------------------------------------------------------------------
    # Accès direct
    # ------------------------------------------------------------------

    @property
    def connection(self) -> sqlite3.Connection:
        return self.connect()


__all__ = ["Database"]