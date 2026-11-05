"""Local product preparation for distribution."""
import csv
import io
import sqlite3
from decimal import Decimal, InvalidOperation

from pydantic import ValidationError

from .database import DuplicateModel, ProductNotFound, PRODUCT_COLUMNS, product_values, utc_now
from .schemas import ProductFields


def queue(database):
    with database.connect() as conn:
        return [dict(row) for row in conn.execute(
            f"SELECT p.{PRODUCT_COLUMNS.replace(', ', ', p.')}, q.selected, q.added_at "
            "FROM distribution_queue q JOIN products p ON p.id=q.product_id ORDER BY q.added_at, p.id")]


def add(database, product_id):
    with database.connect() as conn:
        if not conn.execute('SELECT 1 FROM products WHERE id=?', (product_id,)).fetchone():
            raise ProductNotFound()
        conn.execute('INSERT OR IGNORE INTO distribution_queue VALUES (?, 1, ?)', (product_id, utc_now()))


def select(database, product_id, selected):
    with database.connect() as conn:
        if not conn.execute('UPDATE distribution_queue SET selected=? WHERE product_id=?', (int(selected), product_id)).rowcount:
            raise ProductNotFound()


def remove(database, product_id):
    with database.connect() as conn:
        if not conn.execute('DELETE FROM distribution_queue WHERE product_id=?', (product_id,)).rowcount:
            raise ProductNotFound()


def copy_product(database, product_id, new_model):
    with database.connect() as conn:
        conn.execute('BEGIN IMMEDIATE')
        row = conn.execute(f'SELECT {PRODUCT_COLUMNS} FROM products WHERE id=?', (product_id,)).fetchone()
        if row is None:
            raise ProductNotFound()
        original = dict(row)
        payload = ProductFields(name=original['name'], model=new_model, category=original['category'],
                                description=original['description'], price_cents=original['price_cents']).model_dump()
        now = utc_now()
        try:
            cur = conn.execute('INSERT INTO products (name,model,model_key,category,description,price_cents,search_text,created_at,updated_at,revision) VALUES (?,?,?,?,?,?,?,?,?,1)', (*product_values(payload), now, now))
        except sqlite3.IntegrityError as exc:
            if exc.sqlite_errorname == 'SQLITE_CONSTRAINT_UNIQUE':
                raise DuplicateModel() from exc
            raise
        new_id = cur.lastrowid
        conn.execute('INSERT INTO product_images SELECT ?, content_type, content FROM product_images WHERE product_id=?', (new_id, product_id))
        conn.execute('INSERT INTO distribution_queue VALUES (?,1,?)', (new_id, now))
        return new_id


def import_csv(database, text):
    reader = csv.DictReader(io.StringIO(text.lstrip('\ufeff'), newline=''), strict=True)
    if reader.fieldnames != ['商品名称', '型号', '分类', '售价', '商品说明']:
        raise ValueError('表头应为：商品名称,型号,分类,售价,商品说明')
    parsed = []
    for row in reader:
        parsed.append((reader.line_num, row))
        if len(parsed) > 500:
            raise ValueError('每次最多导入 500 行')
    results = []
    for line, row in parsed:
        if not any((value or '').strip() for value in row.values() if isinstance(value, str)) and None not in row:
            continue
        try:
            if None in row or any(value is None for value in row.values()):
                raise ValueError('列数不正确')
            price = row['售价'].strip()
            amount = Decimal(price) if price else None
            if amount is not None and (not amount.is_finite() or amount < 0 or amount > Decimal('9999999.99') or amount.as_tuple().exponent < -2):
                raise ValueError('售价无效，最多保留两位小数')
            payload = ProductFields(name=row['商品名称'], model=row['型号'], category=row['分类'],
                                    description=row['商品说明'], price_cents=int(amount * 100) if amount is not None else None)
            product = database.create_product(payload.model_dump())
            add(database, product['id'])
            results.append({'line': line, 'status': 'imported', 'product_id': product['id']})
        except (ValueError, ValidationError, DuplicateModel, InvalidOperation) as exc:
            results.append({'line': line, 'status': 'error', 'message': '型号重复' if isinstance(exc, DuplicateModel) else '资料或售价无效'})
    return results
