import json
import time

import pytest

T = {"slug": "t01", "name": "1팀", "password": "pw-123456", "member": "다운", "create_code": "test-code"}
AREA = {"name": "WireGuard", "status": "live", "domains": ["network"], "design": ["a"], "config": [],
        "commands": [], "verify": [], "trouble": []}


@pytest.fixture
def team(client):
    assert client.post("/api/teams", json=T).status_code == 201
    return client


def mk(c, kind, body, parent=None):
    r = c.post("/api/docs", json={"kind": kind, "parent_id": parent, "sort": 0, "body": body, "message": "new"})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def chain(c):
    cl = mk(c, "cloud", {"name": "OpenStack", "provider": "openstack"})
    inst = mk(c, "instance", {"title": "k8s-cp1"}, cl)
    area = mk(c, "area", AREA, inst)
    return cl, inst, area


def test_create_tree(team):
    cl, inst, area = chain(team)
    tree = team.get("/api/tree").json()
    assert tree["team"] == {"slug": "t01", "name": "1팀"}
    docs = {d["id"]: d for d in tree["docs"]}
    assert len(docs) == 3 and docs[area]["parent_id"] == inst and docs[area]["rev"] == 1
    assert docs[area]["body"]["name"] == "WireGuard"


def test_parent_kind_enforced(team):
    cl = mk(team, "cloud", {"name": "A", "provider": "aws"})
    r = team.post("/api/docs", json={"kind": "area", "parent_id": cl, "body": AREA})
    assert r.status_code == 422


def test_update_rev2(team):
    _, _, area = chain(team)
    r = team.put(f"/api/docs/{area}", json={"base_rev": 1, "body": {**AREA, "name": "WG"}, "message": "rename"})
    assert r.json() == {"rev": 2}


def test_update_conflict_409(team):
    _, _, area = chain(team)
    team.put(f"/api/docs/{area}", json={"base_rev": 1, "body": {**AREA, "name": "A"}})
    r = team.put(f"/api/docs/{area}", json={"base_rev": 1, "body": {**AREA, "name": "B"}})
    assert r.status_code == 409
    cur = r.json()["current"]
    assert cur["rev"] == 2 and cur["body"]["name"] == "A" and cur["author"] == "다운"


def test_secret_422_field(team):
    _, inst, _ = chain(team)
    body = {**AREA, "config": [{"label": "wg", "code": "PrivateKey = " + "B" * 43 + "="}]}
    r = team.post("/api/docs", json={"kind": "area", "parent_id": inst, "body": body})
    assert r.status_code == 422 and r.json()["field"] == "body.config[0].code"


def test_body_too_large_413(team):
    _, inst, _ = chain(team)
    body = {**AREA, "design": ["x" * 70000]}
    r = team.post("/api/docs", json={"kind": "area", "parent_id": inst, "body": body})
    assert r.status_code == 413


def test_delete_with_children_422(team):
    cl, _, _ = chain(team)
    r = team.request("DELETE", f"/api/docs/{cl}", json={"base_rev": 1})
    assert r.status_code == 422


def test_restore_deleted(team):
    _, _, area = chain(team)
    assert team.request("DELETE", f"/api/docs/{area}", json={"base_rev": 1}).json() == {"rev": 2}
    assert area not in [d["id"] for d in team.get("/api/tree").json()["docs"]]
    r = team.post(f"/api/docs/{area}/restore", json={"rev": 1, "base_rev": 2})
    assert r.json() == {"rev": 3}
    assert area in [d["id"] for d in team.get("/api/tree").json()["docs"]]


def test_revisions_newest_first(team):
    _, _, area = chain(team)
    team.put(f"/api/docs/{area}", json={"base_rev": 1, "body": AREA, "message": "m2"})
    revs = team.get(f"/api/docs/{area}/revisions").json()
    assert [r["rev"] for r in revs] == [2, 1] and revs[0]["message"] == "m2"
    one = team.get(f"/api/docs/{area}/revisions/1").json()
    assert one["rev"] == 1 and one["body"]["name"] == "WireGuard"


def test_other_team_404(team, client):
    _, _, area = chain(team)
    client.post("/api/logout")
    client.post("/api/teams", json={**T, "slug": "t02"})
    assert client.get(f"/api/docs/{area}/revisions").status_code == 404
    assert client.put(f"/api/docs/{area}", json={"base_rev": 1, "body": AREA}).status_code == 404
    assert client.get("/api/tree").json()["docs"] == []


def test_changes_title_author(team):
    _, _, area = chain(team)
    ch = team.get("/api/changes?limit=10").json()
    assert ch[0]["title"] == "WireGuard" and ch[0]["author"] == "다운" and len(ch) == 3


def test_doc_limit_2000(team, conn):
    tid, = conn.execute("select id from teams").fetchone()
    now = int(time.time())
    conn.executemany("insert into docs(team_id,kind,parent_id,sort,current_rev,current_body,created_at,updated_at) "
                     "values(?,?,?,?,?,?,?,?)", [(tid, "page", None, 0, 1, '{"title":"x"}', now, now)] * 2000)
    conn.commit()
    r = team.post("/api/docs", json={"kind": "page", "body": {"title": "y"}})
    assert r.status_code == 422


def test_requires_login(client):
    assert client.get("/api/tree").status_code == 401


def test_scripts(team, conn):
    tid, = conn.execute("select id from teams").fetchone()
    conn.execute("insert into scripts(team_id,path,host,status,keys,text) values(?,?,?,?,?,?)",
                 (tid, "/opt/a.sh", "db-01", "live", json.dumps(["a.sh"]), "echo hi"))
    conn.commit()
    lst = team.get("/api/scripts").json()
    assert lst[0]["keys"] == ["a.sh"] and "text" not in lst[0]
    assert team.get(f"/api/scripts/{lst[0]['id']}").json()["text"] == "echo hi"
