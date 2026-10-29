from contextlib import contextmanager
import json
import socket
import subprocess
import sys
import time
from urllib.request import Request, urlopen


@contextmanager
def running_server(data_dir):
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    process = subprocess.Popen(
        [sys.executable, "-m", "commerce_workbench", "--port", str(port), "--data-dir", str(data_dir)],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    base = f"http://127.0.0.1:{port}"
    try:
        deadline = time.monotonic() + 15
        while True:
            if process.poll() is not None:
                raise AssertionError("Application exited before becoming ready")
            try:
                with urlopen(base + "/api/health", timeout=1) as response:
                    assert response.status == 200
                break
            except OSError:
                if time.monotonic() > deadline:
                    raise AssertionError("Application did not start")
                time.sleep(0.1)
        yield base
    finally:
        process.terminate()
        process.wait(timeout=10)


def test_saved_workspace_survives_process_restart(tmp_path):
    with running_server(tmp_path / "data") as base:
        with urlopen(base + "/api/workspace", timeout=3) as response:
            workspace = json.load(response)
        request = Request(
            base + "/api/workspace",
            data=json.dumps({"name": "进程重启验证", "revision": workspace["revision"]}).encode(),
            method="PUT", headers={"Content-Type": "application/json"},
        )
        with urlopen(request, timeout=3) as response:
            saved = json.load(response)
    with running_server(tmp_path / "data") as base:
        with urlopen(base + "/api/workspace", timeout=3) as response:
            assert json.load(response) == saved
