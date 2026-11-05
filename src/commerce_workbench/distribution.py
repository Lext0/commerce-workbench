"""Local product preparation for distribution."""
import csv
import io
import sqlite3
import json
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

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
            with database.connect() as conn:
                now = utc_now()
                try:
                    cur = conn.execute('INSERT INTO products (name,model,model_key,category,description,price_cents,search_text,created_at,updated_at,revision) VALUES (?,?,?,?,?,?,?,?,?,1)', (*product_values(payload.model_dump()), now, now))
                except sqlite3.IntegrityError as exc:
                    if exc.sqlite_errorname == 'SQLITE_CONSTRAINT_UNIQUE':
                        raise DuplicateModel() from exc
                    raise
                product_id = cur.lastrowid
                conn.execute('INSERT INTO distribution_queue VALUES (?,1,?)', (product_id, now))
            results.append({'line': line, 'status': 'imported', 'product_id': product_id})
        except (ValueError, ValidationError, DuplicateModel, InvalidOperation) as exc:
            results.append({'line': line, 'status': 'error', 'message': '型号重复' if isinstance(exc, DuplicateModel) else '资料或售价无效'})
    return results


def create_batch(database, request_id):
    with database.connect() as conn:
        conn.execute('BEGIN IMMEDIATE')
        existing = conn.execute('SELECT id FROM distribution_batches WHERE request_id=?', (request_id,)).fetchone()
        if existing:
            return existing[0]
        products = conn.execute('SELECT product_id FROM distribution_queue WHERE selected=1 ORDER BY product_id').fetchall()
        if not products:
            raise ValueError('请先选择待铺货商品')
        now = utc_now()
        batch_id = conn.execute('INSERT INTO distribution_batches(request_id,created_at) VALUES (?,?)', (request_id, now)).lastrowid
        conn.executemany("INSERT INTO distribution_items VALUES (?,?,'pending','',?)", [(batch_id, row[0], now) for row in products])
        return batch_id


def batch(database, batch_id):
    with database.connect() as conn:
        header = conn.execute('SELECT id, created_at FROM distribution_batches WHERE id=?', (batch_id,)).fetchone()
        if not header:
            raise ProductNotFound()
        items = [dict(row) for row in conn.execute('SELECT i.product_id,p.name,p.model,i.status,i.message,i.updated_at FROM distribution_items i JOIN products p ON p.id=i.product_id WHERE i.batch_id=? ORDER BY i.product_id', (batch_id,))]
        return {**dict(header), 'items': items}


def batches(database):
    with database.connect() as conn:
        return [dict(row) for row in conn.execute('SELECT id,created_at FROM distribution_batches ORDER BY id DESC LIMIT 100')]


def process_batch(database, batch_id, product_id=None):
    current = batch(database, batch_id)
    if product_id is not None and not any(item['product_id'] == product_id for item in current['items']):
        raise ProductNotFound()
    for item in current['items']:
        if product_id is not None and item['product_id'] != product_id:
            continue
        if item['status'] not in ('pending', 'failed'):
            continue
        with database.connect() as conn:
            conn.execute('BEGIN IMMEDIATE')
            row = conn.execute('SELECT status FROM distribution_items WHERE batch_id=? AND product_id=?', (batch_id, item['product_id'])).fetchone()
            if row['status'] not in ('pending', 'failed'):
                continue
            pid = item['product_id']
            product = dict(conn.execute(f'SELECT {PRODUCT_COLUMNS} FROM products WHERE id=?', (pid,)).fetchone())
            listing = conn.execute("SELECT 1 FROM listings WHERE product_id=? AND status='published'", (pid,)).fetchone()
            image = conn.execute('SELECT content_type,content FROM product_images WHERE product_id=?', (pid,)).fetchone()
            if listing:
                status, message = 'skipped', '模拟店铺已有该型号'
            elif product['price_cents'] is None or product['price_cents'] <= 0:
                status, message = 'failed', '请填写大于零的售价'
            elif image is None:
                status, message = 'failed', '请上传商品图片'
            else:
                status, message = 'success', '发布成功'
                conn.execute("INSERT INTO listings VALUES (?, 'published', ?, ?, ?, ?) ON CONFLICT(product_id) DO UPDATE SET status='published', snapshot=excluded.snapshot, updated_at=excluded.updated_at, image_type=excluded.image_type, image=excluded.image", (pid, json.dumps(product, ensure_ascii=False), utc_now(), image[0], image[1]))
            conn.execute('UPDATE distribution_items SET status=?,message=?,updated_at=? WHERE batch_id=? AND product_id=?', (status, message, utc_now(), batch_id, pid))
    return batch(database, batch_id)


def quote(cost, shipping, exchange, fee, profit):
    try:
        cost, shipping, exchange, fee, profit = [Decimal(x) for x in (cost, shipping, exchange, fee, profit)]
        if not all(x.is_finite() for x in (cost, shipping, exchange, fee, profit)):
            raise ValueError()
        if not (Decimal('0') <= cost <= 100000000 and 0 <= shipping <= 100000000 and Decimal('0.0001') <= exchange <= 1000000 and 0 <= fee < 100 and 0 <= profit < 100 and fee + profit < 100):
            raise ValueError()
        value = ((cost + shipping) / exchange / (1 - (fee + profit) / 100)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        return {'usd': format(value, '.2f')}
    except (InvalidOperation, ValueError, OverflowError):
        raise ValueError('请输入有效的成本、汇率和比例，费用与利润比例之和须小于 100%')
