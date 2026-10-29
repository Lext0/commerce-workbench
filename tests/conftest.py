import pytest
from fastapi.testclient import TestClient

from commerce_workbench.app import create_app
from commerce_workbench.config import Settings


@pytest.fixture
def settings(tmp_path):
    return Settings(data_dir=tmp_path / "data")


@pytest.fixture
def client(settings):
    with TestClient(create_app(settings), base_url="http://localhost") as client:
        yield client
