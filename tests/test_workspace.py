from concurrent.futures import ThreadPoolExecutor

from fastapi.testclient import TestClient
import pytest

from commerce_workbench.app import create_app
from commerce_workbench.database import Database, RevisionConflict


def test_workspace_update_survives_application_restart(settings):
    with TestClient(create_app(settings), base_url="http://localhost") as first:
        original = first.get("/api/workspace").json()
        response = first.put("/api/workspace", json={"name": "  新商品工作台  ", "revision": original["revision"]})
        assert response.status_code == 200
        saved = response.json()
        assert saved["name"] == "新商品工作台"
        assert saved["revision"] == original["revision"] + 1
    with TestClient(create_app(settings), base_url="http://localhost") as second:
        assert second.get("/api/workspace").json() == saved
    with Database(settings.database_path).connect() as connection:
        assert connection.execute("SELECT COUNT(*) FROM schema_migrations").fetchone()[0] == 5
        assert connection.execute("SELECT COUNT(*) FROM workspace").fetchone()[0] == 1


@pytest.mark.parametrize("name", ["", "   ", "长" * 81, "名称\n第二行", "名称\x00", 123, None])
def test_invalid_names_do_not_change_stored_data(client, name):
    before = client.get("/api/workspace").json()
    response = client.put("/api/workspace", json={"name": name, "revision": before["revision"]})
    assert response.status_code == 422
    assert client.get("/api/workspace").json() == before


def test_stale_update_does_not_overwrite_another_edit(client):
    first = client.get("/api/workspace").json()
    payload = {"name": "先保存的名称", "revision": first["revision"]}
    assert client.put("/api/workspace", json=payload).status_code == 200
    payload["name"] = "旧页面中的名称"
    assert client.put("/api/workspace", json=payload).status_code == 409
    assert client.get("/api/workspace").json()["name"] == "先保存的名称"


def test_concurrent_updates_accept_only_one_revision(settings):
    database = Database(settings.database_path)
    database.initialize()
    revision = database.workspace()["revision"]

    def update(name):
        try:
            database.update_workspace(name, revision)
            return "saved"
        except RevisionConflict:
            return "conflict"

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(update, ["名称一", "名称二"])) == ["conflict", "saved"]


def test_cross_site_and_non_json_changes_are_rejected(client):
    before = client.get("/api/workspace").json()
    payload = {"name": "变更", "revision": before["revision"]}
    assert client.put("/api/workspace", json=payload, headers={"Origin": "https://another.example"}).status_code == 403
    assert client.put("/api/workspace", content='{"name":"变更","revision":1}', headers={"Content-Type": "text/plain"}).status_code == 415
    assert client.get("/api/workspace").json() == before


def test_unrecognized_host_is_rejected(client):
    assert client.get("/api/workspace", headers={"Host": "another.example"}).status_code == 400


def test_newer_database_is_not_modified(settings):
    database = Database(settings.database_path)
    database.initialize()
    with database.connect() as connection:
        connection.execute("INSERT INTO schema_migrations VALUES (6, 'future')")
    before = database.workspace()
    with pytest.raises(RuntimeError, match="newer"):
        database.initialize()
    assert database.workspace() == before


def test_health_reports_unavailable_database(client, settings):
    with Database(settings.database_path).connect() as connection:
        connection.execute("DROP TABLE workspace")
    response = client.get("/api/health")
    assert response.status_code == 503
    assert response.json()["database"] == "unavailable"
    assert str(settings.data_dir) not in response.text
