import sys
import pathlib

import fakeredis
import pytest
from fastapi.testclient import TestClient

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

ORIGIN = "http://testserver"


@pytest.fixture
def r(monkeypatch):
    monkeypatch.setenv("TEAM_CREATE_CODE", "test-code")
    monkeypatch.setenv("ALLOWED_ORIGIN", ORIGIN)
    monkeypatch.setenv("WIKI_REQUIRE_ACCESS_KEY", "0")
    return fakeredis.FakeRedis(decode_responses=True)


def make_client(r):
    from wiki.app import create_app
    c = TestClient(create_app(redis_client=r), base_url="https://testserver")
    c.headers.update({"Origin": ORIGIN})
    return c


@pytest.fixture
def client(r):
    with make_client(r) as c:
        yield c
