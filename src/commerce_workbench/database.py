from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
import sqlite3
import json
from typing import Iterator
import unicodedata


class RevisionConflict(Exception):
    """The record was changed after it was loaded."""


class ProductNotFound(Exception):
    pass


class DuplicateModel(Exception):
    pass


PRODUCT_COLUMNS = "id, name, model, category, description, price_cents, created_at, updated_at, revision"


def search_key(value: str) -> str:
    return unicodedata.normalize("NFKC", value).casefold()


def product_values(payload: dict) -> tuple:
    return (
        payload["name"], payload["model"], search_key(payload["model"]),
        payload["category"], payload["description"], payload["price_cents"],
        search_key("\n".join(payload[key] for key in ("name", "model", "category"))),
    )


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
            if version > 5:
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
            if version < 2:
                connection.execute(
                    "CREATE TABLE products ("
                    "id INTEGER PRIMARY KEY AUTOINCREMENT, "
                    "name TEXT NOT NULL CHECK (length(trim(name)) BETWEEN 1 AND 120), "
                    "model TEXT NOT NULL CHECK (length(trim(model)) BETWEEN 1 AND 64), "
                    "model_key TEXT NOT NULL UNIQUE, "
                    "category TEXT NOT NULL DEFAULT '' CHECK (length(category) <= 80), "
                    "description TEXT NOT NULL DEFAULT '' CHECK (length(description) <= 4000), "
                    "price_cents INTEGER CHECK (price_cents BETWEEN 0 AND 999999999), "
                    "search_text TEXT NOT NULL, "
                    "created_at TEXT NOT NULL, updated_at TEXT NOT NULL, "
                    "revision INTEGER NOT NULL CHECK (revision >= 1))"
                )
                connection.execute("CREATE INDEX products_updated ON products(updated_at DESC, id DESC)")
                connection.execute("INSERT INTO schema_migrations VALUES (2, ?)", (utc_now(),))
            if version < 3:
                connection.execute("CREATE TABLE product_images (product_id INTEGER PRIMARY KEY REFERENCES products(id) ON DELETE CASCADE, content_type TEXT NOT NULL, content BLOB NOT NULL)")
                connection.execute("INSERT INTO schema_migrations VALUES (3, ?)", (utc_now(),))
            if version < 4:
                connection.execute("CREATE TABLE listings (product_id INTEGER PRIMARY KEY REFERENCES products(id) ON DELETE CASCADE, status TEXT NOT NULL CHECK(status IN ('published','withdrawn')), snapshot TEXT NOT NULL, updated_at TEXT NOT NULL, image_type TEXT NOT NULL, image BLOB NOT NULL)")
                connection.execute("INSERT INTO schema_migrations VALUES (4, ?)", (utc_now(),))
            if version < 5:
                connection.execute("CREATE TABLE distribution_queue (product_id INTEGER PRIMARY KEY REFERENCES products(id) ON DELETE CASCADE, selected INTEGER NOT NULL DEFAULT 1 CHECK(selected IN (0,1)), added_at TEXT NOT NULL)")
                connection.execute("INSERT INTO schema_migrations VALUES (5, ?)", (utc_now(),))

    def listing(self, product_id: int):
        self.product(product_id)
        with self.connect() as connection:
            row = connection.execute("SELECT status, snapshot, updated_at FROM listings WHERE product_id=?", (product_id,)).fetchone()
            if row is None:
                return {"status": "unpublished"}
            result = dict(row)
            result["snapshot"] = json.loads(result["snapshot"])
            return result

    def publish(self, product_id: int):
        with self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(f"SELECT {PRODUCT_COLUMNS} FROM products WHERE id=?", (product_id,)).fetchone()
            if row is None:
                raise ProductNotFound()
            product = dict(row)
            if product["price_cents"] is None or product["price_cents"] <= 0:
                raise ValueError("发布前请填写大于零的售价")
            image = connection.execute("SELECT content_type, content FROM product_images WHERE product_id=?", (product_id,)).fetchone()
            if not image:
                raise ValueError("发布前请上传商品图片")
            timestamp = utc_now()
            connection.execute("INSERT INTO listings VALUES (?, 'published', ?, ?, ?, ?) ON CONFLICT(product_id) DO UPDATE SET status='published', snapshot=excluded.snapshot, updated_at=excluded.updated_at, image_type=excluded.image_type, image=excluded.image", (product_id, json.dumps(product, ensure_ascii=False), timestamp, image[0], image[1]))
        return self.listing(product_id)

    def withdraw(self, product_id: int):
        self.product(product_id)
        with self.connect() as connection:
            connection.execute("UPDATE listings SET status='withdrawn', updated_at=? WHERE product_id=? AND status='published'", (utc_now(), product_id))
        return self.listing(product_id)

    def image(self, product_id: int):
        self.product(product_id)
        with self.connect() as connection:
            return connection.execute("SELECT content_type, content FROM product_images WHERE product_id = ?", (product_id,)).fetchone()

    def put_image(self, product_id: int, content_type: str, content: bytes):
        with self.connect() as connection:
            if not connection.execute("SELECT 1 FROM products WHERE id = ?", (product_id,)).fetchone():
                raise ProductNotFound()
            connection.execute("INSERT INTO product_images VALUES (?, ?, ?) ON CONFLICT(product_id) DO UPDATE SET content_type=excluded.content_type, content=excluded.content", (product_id, content_type, content))

    def delete_image(self, product_id: int):
        self.product(product_id)
        with self.connect() as connection:
            connection.execute("DELETE FROM product_images WHERE product_id = ?", (product_id,))

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

    def product(self, product_id: int) -> dict:
        with self.connect() as connection:
            row = connection.execute(
                f"SELECT {PRODUCT_COLUMNS} FROM products WHERE id = ?", (product_id,),
            ).fetchone()
            if row is None:
                raise ProductNotFound()
            return dict(row)

    def products(self, query: str, limit: int, offset: int) -> dict:
        with self.connect() as connection:
            # Count and rows belong to the same SQLite snapshot.
            connection.execute("BEGIN")
            parameters = (search_key(query.strip()),)
            where = "WHERE instr(search_text, ?) > 0"
            total = connection.execute(f"SELECT COUNT(*) FROM products {where}", parameters).fetchone()[0]
            rows = connection.execute(
                f"SELECT {PRODUCT_COLUMNS} FROM products {where} "
                "ORDER BY updated_at DESC, id DESC LIMIT ? OFFSET ?",
                (*parameters, limit, offset),
            ).fetchall()
            return {"items": [dict(row) for row in rows], "total": total, "limit": limit, "offset": offset}

    def create_product(self, payload: dict) -> dict:
        with self.connect() as connection:
            timestamp = utc_now()
            try:
                result = connection.execute(
                    "INSERT INTO products (name, model, model_key, category, description, price_cents, "
                    "search_text, created_at, updated_at, revision) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1)",
                    (*product_values(payload), timestamp, timestamp),
                )
            except sqlite3.IntegrityError as exc:
                if exc.sqlite_errorname == "SQLITE_CONSTRAINT_UNIQUE":
                    raise DuplicateModel() from exc
                raise
            return dict(connection.execute(
                f"SELECT {PRODUCT_COLUMNS} FROM products WHERE id = ?", (result.lastrowid,),
            ).fetchone())

    def update_product(self, product_id: int, payload: dict, revision: int) -> dict:
        with self.connect() as connection:
            try:
                result = connection.execute(
                    "UPDATE products SET name = ?, model = ?, model_key = ?, category = ?, "
                    "description = ?, price_cents = ?, search_text = ?, updated_at = ?, revision = revision + 1 "
                    "WHERE id = ? AND revision = ?",
                    (*product_values(payload), utc_now(), product_id, revision),
                )
            except sqlite3.IntegrityError as exc:
                if exc.sqlite_errorname == "SQLITE_CONSTRAINT_UNIQUE":
                    raise DuplicateModel() from exc
                raise
            if result.rowcount != 1:
                if connection.execute("SELECT id FROM products WHERE id = ?", (product_id,)).fetchone() is None:
                    raise ProductNotFound()
                raise RevisionConflict()
            return dict(connection.execute(
                f"SELECT {PRODUCT_COLUMNS} FROM products WHERE id = ?", (product_id,),
            ).fetchone())
