from pathlib import Path

import pytest

from commerce_workbench.config import Settings


def test_environment_config_can_select_data_directory(monkeypatch, tmp_path):
    monkeypatch.setenv("CW_DATA_DIR", str(tmp_path / "workspace"))
    monkeypatch.setenv("CW_PORT", "8899")
    monkeypatch.setenv("CW_HOST", "127.0.0.1")
    settings = Settings.from_environment()
    assert settings.port == 8899
    assert settings.database_path == tmp_path / "workspace" / "workbench.sqlite3"


@pytest.mark.parametrize("port", [0, -1, 65536])
def test_invalid_port_is_rejected(port):
    with pytest.raises(ValueError, match="Port"):
        Settings(data_dir=Path("data"), port=port)


def test_public_listener_is_not_enabled_without_authentication():
    with pytest.raises(ValueError, match="loopback"):
        Settings(data_dir=Path("data"), host="0.0.0.0")
