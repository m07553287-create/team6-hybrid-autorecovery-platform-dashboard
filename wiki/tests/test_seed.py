import json
import sys

import pytest

from wiki.tests.conftest import ROOT, make_client

sys.path.insert(0, str(ROOT / "tools"))
from seed_wiki import seed  # noqa: E402

PW = "pw-123456"


def test_seed_counts(r):
    c = seed(r, "figteam", "figteam (team6)", PW)
    assert c == {"cloud": 4, "instance": 9, "area": 29, "steps": 1, "page": 3, "scripts": 18}


def test_seed_login_tree(r):
    seed(r, "figteam", "figteam (team6)", PW)
    with make_client(r) as c:
        assert c.post("/api/login", json={"slug": "figteam", "password": PW, "member": "seed-test"}).status_code == 200
        docs = c.get("/api/tree").json()["docs"]
        assert len(docs) == 46
        inst = [d for d in docs if d["kind"] == "instance"]
        assert {d["body"]["short"] for d in inst} >= {"s1", "db-01", "kt-w1", "aws-ctl"}
        assert {d["body"]["slug"] for d in inst} >= {"inst-s1", "inst-awsdr"}
        assert "mysql" in {d["body"].get("slug") for d in docs if d["kind"] == "area"}
        revs = c.get(f"/api/docs/{inst[0]['id']}/revisions").json()
        assert revs[0]["author"] == "seed" and revs[0]["message"] == "2026-11-26 실측 가이드에서 가져옴"
        assert len(c.get("/api/scripts").json()) == 18


def test_seed_steps_refs(r):
    seed(r, "figteam", "figteam (team6)", PW)
    tid = r.hget("fw:team:figteam", "id")
    kinds = {int(i): r.hget(f"fw:doc:{i}", "kind") for i in r.smembers(f"fw:docs:{tid}")}
    steps_id = next(i for i, k in kinds.items() if k == "steps")
    body = json.loads(r.hget(f"fw:doc:{steps_id}", "body"))
    assert len(body["items"]) == 13
    for it in body["items"]:
        assert kinds[it["instance_id"]] == "instance" and kinds[it["area_id"]] == "area"


def test_seed_scripts_no_bucket(r):
    seed(r, "figteam", "figteam (team6)", PW)
    texts = [r.hget(k, "text") for k in r.keys("fw:script:*")]
    assert texts and all("fig-minwon-db-backup" not in t for t in texts)


def test_seed_twice_fails(r):
    seed(r, "figteam", "figteam (team6)", PW)
    with pytest.raises(SystemExit):
        seed(r, "figteam", "figteam (team6)", PW)
