from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
import sqlite3
from typing import Iterator


class RevisionConflict(Exception):
    """The workspace was changed after it was loaded."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


class Database:
    def __init__(self, path: Path):
        self.path = path

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, timeout=5)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as connection:
            connection.execute("PRAGMA journal_mode = WAL")
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                "CREATE TABLE IF NOT EXISTS schema_migrations "
                "(version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)"
            )
            version = connection.execute(
                "SELECT COALESCE(MAX(version), 0) FROM schema_migrations"
            ).fetchone()[0]
            if version > 1:
                raise RuntimeError("Database version is newer than this application")
            if version == 0:
                connection.execute(
                    "CREATE TABLE workspace ("
                    "id INTEGER PRIMARY KEY CHECK (id = 1), "
                    "name TEXT NOT NULL CHECK (length(trim(name)) BETWEEN 1 AND 80), "
                    "created_at TEXT NOT NULL, updated_at TEXT NOT NULL, "
                    "revision INTEGER NOT NULL CHECK (revision >= 1))"
                )
                now = utc_now()
                connection.execute(
                    "INSERT INTO workspace VALUES (1, ?, ?, ?, 1)",
                    ("我的商品工作台", now, now),
                )
                connection.execute(
                    "INSERT INTO schema_migrations VALUES (1, ?)", (now,)
                )

    def workspace(self) -> dict:
        with self.connect() as connection:
            row = connection.execute("SELECT * FROM workspace WHERE id = 1").fetchone()
            if row is None:
                raise sqlite3.DatabaseError("Workspace is missing")
            return dict(row)

    def update_workspace(self, name: str, revision: int) -> dict:
        with self.connect() as connection:
            result = connection.execute(
                "UPDATE workspace SET name = ?, updated_at = ?, revision = revision + 1 "
                "WHERE id = 1 AND revision = ?",
                (name, utc_now(), revision),
            )
            if result.rowcount != 1:
                raise RevisionConflict()
            return dict(connection.execute("SELECT * FROM workspace WHERE id = 1").fetchone())
