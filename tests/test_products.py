from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
import sqlite3

import pytest

from commerce_workbench.database import Database, DuplicateModel
from commerce_workbench.schemas import ProductFields


def create(client, model="CUP-001", **values):
    response = client.post("/api/products", json={"name": "保温杯", "model": model, **values})
    assert response.status_code == 201
    return response.json()


def editable(product, **updates):
    fields = {key: product[key] for key in ("name", "model", "category", "description", "price_cents", "revision")}
    return {**fields, **updates}


def test_create_and_read_optional_fields_and_exact_price(client):
    product = create(client, "  ＣＵＰ-001  ", name="  保温杯  ", price_cents=1001, description="说明\r\n第二行")
    assert product["name"] == "保温杯"
    assert product["model"] == "CUP-001"
    assert product["price_cents"] == 1001
    assert product["description"] == "说明\n第二行"
    assert product["category"] == ""
    assert product["revision"] == 1
    assert client.get(f'/api/products/{product["id"]}').json() == product
    assert "model_key" not in product
    assert create(client, "CUP-002")["price_cents"] is None


@pytest.mark.parametrize("values", [
    {"name": " "}, {"name": "长" * 121}, {"name": 3}, {"model": ""},
    {"model": "M" * 65}, {"model": "A\u200b"}, {"category": "长" * 81},
    {"description": "长" * 4001}, {"description": "bad\x00value"},
    {"price_cents": -1}, {"price_cents": 1000000000}, {"price_cents": 1.5},
    {"price_cents": "123"}, {"price_cents": True}, {"unexpected": "field"},
])
def test_invalid_product_does_not_create_records(client, values):
    response = client.post("/api/products", json={"name": "商品", "model": "A-1", **values})
    assert response.status_code == 422
    assert client.get("/api/products").json()["total"] == 0


def test_required_fields_and_missing_products(client):
    assert client.post("/api/products", json={"name": "缺少型号"}).status_code == 422
    assert client.get("/api/products/12345").status_code == 404
    assert client.put("/api/products/12345", json={"name": "商品", "model": "A", "revision": 1}).status_code == 404
    assert client.get("/api/products/9223372036854775808").status_code == 422


def test_duplicate_model_is_normalized_and_does_not_overwrite(client):
    first = create(client, "Ab-1")
    for model in (" ab-1 ", "ＡＢ-1"):
        response = client.post("/api/products", json={"name": "另一件", "model": model})
        assert response.status_code == 409
        assert response.json()["detail"]["code"] == "duplicate_model"
    assert client.get(f'/api/products/{first["id"]}').json() == first
    assert client.get("/api/products").json()["total"] == 1


def test_empty_search_pagination_and_literal_query(client):
    assert client.get("/api/products").json() == {"items": [], "total": 0, "limit": 20, "offset": 0}
    first = create(client, "CUP-1", category="随行杯")
    second = create(client, "BAG-1", name="Travel Bag", category="出行")
    third = create(client, "PCT-1", name="100%_原色")
    result = client.get("/api/products", params={"limit": 2}).json()
    assert result["total"] == 3
    assert [row["id"] for row in result["items"]] == [third["id"], second["id"]]
    assert client.get("/api/products", params={"limit": 2, "offset": 2}).json()["items"] == [first]
    for query, expected in [("  ｃｕｐ-1  ", first), ("travel", second), ("出行", second), ("%_", third)]:
        response = client.get("/api/products", params={"q": query}).json()
        assert response["items"] == [expected]
    for query in ("不存在的商品", "' OR 1=1 --"):
        assert client.get("/api/products", params={"q": query}).json()["total"] == 0
    assert client.get("/api/products", params={"offset": 20}).json()["items"] == []


@pytest.mark.parametrize("params", [{"limit": 0}, {"limit": 101}, {"offset": -1}, {"offset": 1000001}, {"q": "字" * 121}])
def test_invalid_list_limits(client, params):
    assert client.get("/api/products", params=params).status_code == 422


def test_edit_isolated_from_other_products_and_stale_revisions(client):
    first = create(client, "A-1")
    other = create(client, "B-1")
    response = client.put(f'/api/products/{first["id"]}', json=editable(first, name="改过的商品", model="A-2", price_cents=0))
    assert response.status_code == 200
    updated = response.json()
    assert updated["revision"] == 2
    assert updated["created_at"] == first["created_at"]
    assert updated["price_cents"] == 0
    stale = client.put(f'/api/products/{first["id"]}', json=editable(first, name="旧页面内容"))
    assert stale.status_code == 409
    assert stale.json()["detail"]["code"] == "revision_conflict"
    assert client.get(f'/api/products/{first["id"]}').json() == updated
    assert client.get(f'/api/products/{other["id"]}').json() == other
    assert client.get("/api/products", params={"q": "A-1"}).json()["total"] == 0
    assert client.get("/api/products", params={"q": "A-2"}).json()["items"] == [updated]


def test_invalid_edit_and_duplicate_edit_are_atomic(client):
    first = create(client, "A-1")
    other = create(client, "B-1")
    path = f'/api/products/{first["id"]}'
    assert client.put(path, json=editable(first, name=" ")).status_code == 422
    duplicate = client.put(path, json=editable(first, model="b-1"))
    assert duplicate.status_code == 409
    assert duplicate.json()["detail"]["code"] == "duplicate_model"
    assert client.get(path).json() == first
    assert client.get(f'/api/products/{other["id"]}').json() == other
    assert client.put(path, json=editable(first, revision=True)).status_code == 422


def test_simultaneous_creation_accepts_one_model(settings):
    database = Database(settings.database_path)
    database.initialize()
    payload = ProductFields(name="商品", model="SAME").model_dump()
    def save(_):
        try:
            database.create_product(payload)
            return "saved"
        except DuplicateModel:
            return "duplicate"
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(save, range(2))) == ["duplicate", "saved"]
    assert database.products("", 20, 0)["total"] == 1


def test_version_one_migration_keeps_existing_workspace(settings):
    settings.database_path.parent.mkdir(parents=True)
    with closing(sqlite3.connect(settings.database_path)) as connection:
        connection.executescript("""
            CREATE TABLE schema_migrations (version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL);
            INSERT INTO schema_migrations VALUES (1, 'before');
            CREATE TABLE workspace (id INTEGER PRIMARY KEY, name TEXT NOT NULL,
                created_at TEXT NOT NULL, updated_at TEXT NOT NULL, revision INTEGER NOT NULL);
            INSERT INTO workspace VALUES (1, '已有工作台', 'before', 'after', 7);
        """)
    database = Database(settings.database_path)
    before = database.workspace()
    database.initialize()
    database.initialize()
    assert database.workspace() == before
    assert database.products("", 20, 0)["total"] == 0
    with database.connect() as connection:
        assert [row[0] for row in connection.execute("SELECT version FROM schema_migrations ORDER BY version")] == [1, 2]
