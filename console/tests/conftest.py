import json
import pathlib
import sys

import pytest
from fastapi.testclient import TestClient

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
ORIGIN = "http://testserver"
PW = "console-pass-1"


@pytest.fixture
def targets(tmp_path):
    p = tmp_path / "targets.json"
    p.write_text(json.dumps([
        {"id": "echo", "area": "onprem", "name": "echo", "desc": "시험용 cat", "argv": ["cat"], "check": {"상태": "echo ok"}, "fix": {"재시작": "echo restart"}},
        {"id": "dead", "area": "aws", "name": "aws-ctl", "desc": "키 불일치", "argv": ["true"], "disabled": "키가 맞지 않아 연결 불가"},
    ]), encoding="utf-8")
    return p


@pytest.fixture
def app(targets, tmp_path, monkeypatch):
    from console.auth import hash_password
    h, salt = hash_password(PW)
    monkeypatch.setenv("CONSOLE_PASS_HASH", h)
    monkeypatch.setenv("CONSOLE_PASS_SALT", salt)
    monkeypatch.setenv("ALLOWED_ORIGIN", ORIGIN)
    monkeypatch.setenv("CONSOLE_LOG_DIR", str(tmp_path / "logs"))
    monkeypatch.setenv("CONSOLE_TARGETS", str(targets))
    monkeypatch.setenv("CONSOLE_STATUS_INTERVAL", "0")
    from console.app import create_app
    return create_app()


@pytest.fixture
def client(app):
    with TestClient(app, base_url="https://testserver") as c:
        c.headers.update({"Origin": ORIGIN})
        yield c


@pytest.fixture
def unlocked(client):
    assert client.post("/console/api/unlock", json={"password": PW}).status_code == 200
    return client
