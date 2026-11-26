import os
import sqlite3
import sys
import pathlib

import pytest
from fastapi.testclient import TestClient

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

ORIGIN = "http://testserver"


@pytest.fixture
def db_path(tmp_path, monkeypatch):
    p = tmp_path / "wiki.db"
    monkeypatch.setenv("WIKI_DB", str(p))
    monkeypatch.setenv("TEAM_CREATE_CODE", "test-code")
    monkeypatch.setenv("ALLOWED_ORIGIN", ORIGIN)
    return p


@pytest.fixture
def client(db_path):
    from wiki.app import create_app
    with TestClient(create_app(), base_url="https://testserver") as c:
        c.headers.update({"Origin": ORIGIN})
        yield c


@pytest.fixture
def conn(db_path, client):
    c = sqlite3.connect(db_path)
    yield c
    c.close()
