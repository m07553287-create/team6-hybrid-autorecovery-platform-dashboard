import json
import sqlite3
import sys

import pytest
from fastapi.testclient import TestClient

from wiki.tests.conftest import ROOT, ORIGIN

sys.path.insert(0, str(ROOT / "tools"))
from seed_wiki import seed  # noqa: E402

PW = "pw-123456"


def test_seed_counts(tmp_path):
    c = seed(str(tmp_path / "w.db"), "figteam", "figteam (team6)", PW)
    assert c == {"cloud": 4, "instance": 9, "area": 29, "steps": 1, "page": 3, "scripts": 18}


def test_seed_login_tree(tmp_path, monkeypatch):
    p = tmp_path / "w.db"
    seed(str(p), "figteam", "figteam (team6)", PW)
    monkeypatch.setenv("WIKI_DB", str(p))
    monkeypatch.setenv("ALLOWED_ORIGIN", ORIGIN)
    from wiki.app import create_app
    with TestClient(create_app(), base_url="https://testserver") as c:
        c.headers.update({"Origin": ORIGIN})
        assert c.post("/api/login", json={"slug": "figteam", "password": PW, "member": "seed-test"}).status_code == 200
        docs = c.get("/api/tree").json()["docs"]
        assert len(docs) == 46
        inst = [d for d in docs if d["kind"] == "instance"]
        assert {d["body"]["short"] for d in inst} >= {"s1", "db-01", "kt-w1", "aws-ctl"}
        revs = c.get(f"/api/docs/{inst[0]['id']}/revisions").json()
        assert revs[0]["author"] == "seed" and revs[0]["message"] == "2026-11-26 실측 가이드에서 가져옴"


def test_seed_steps_refs(tmp_path):
    p = tmp_path / "w.db"
    seed(str(p), "figteam", "figteam (team6)", PW)
    conn = sqlite3.connect(p)
    ids = {r[0]: r[1] for r in conn.execute("select id, kind from docs")}
    body = json.loads(conn.execute("select current_body from docs where kind='steps'").fetchone()[0])
    assert len(body["items"]) == 13
    for it in body["items"]:
        assert ids[it["instance_id"]] == "instance" and ids[it["area_id"]] == "area"


def test_seed_scripts_no_bucket(tmp_path):
    p = tmp_path / "w.db"
    seed(str(p), "figteam", "figteam (team6)", PW)
    texts = [r[0] for r in sqlite3.connect(p).execute("select text from scripts")]
    assert all("fig-minwon-db-backup" not in t for t in texts)


def test_seed_twice_fails(tmp_path):
    p = str(tmp_path / "w.db")
    seed(p, "figteam", "figteam (team6)", PW)
    with pytest.raises(SystemExit):
        seed(p, "figteam", "figteam (team6)", PW)
