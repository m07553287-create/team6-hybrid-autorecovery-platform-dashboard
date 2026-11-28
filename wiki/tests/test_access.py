T = {"slug": "t01", "name": "1팀", "password": "pw-123456", "member": "다운", "create_code": "test-code"}
CLOUD = {"name": "OpenStack", "provider": "openstack"}


def test_access_register_and_logs(client):
    assert client.post("/api/teams", json=T).status_code == 201
    reg = client.post("/api/access/register", json={"member": "다운", "access_key": "k7m3p9", "action": "visit"})
    assert reg.status_code == 200
    body = reg.json()
    assert body["access_key"] == "K7M3P9"
    assert body["member"] == "다운"
    assert body["keybook"]["K7M3P9"]["member"] == "다운"

    me = client.get("/api/me").json()
    assert me["access_key"] == "K7M3P9"
    assert me["member"] == "다운"

    logs = client.get("/api/access/logs").json()
    assert len(logs["logs"]) >= 1
    assert logs["logs"][0]["access_key"] == "K7M3P9"
    assert logs["logs"][0]["member"] == "다운"
    assert logs["keybook"]["K7M3P9"]["member"] == "다운"


def test_changes_and_revisions_include_access_key_and_matched_user(client):
    client.post("/api/teams", json=T)
    client.post("/api/access/register", json={"member": "다운", "access_key": "AB12CD"})

    cl = client.post("/api/docs", json={"kind": "cloud", "body": CLOUD, "message": "클라우드 추가"})
    assert cl.status_code == 201
    doc_id = cl.json()["id"]

    upd = client.put(f"/api/docs/{doc_id}", json={"base_rev": 1, "body": {**CLOUD, "desc": "수정됨"}, "message": "설명 추가"})
    assert upd.status_code == 200

    changes = client.get("/api/changes").json()
    assert changes[0]["access_key"] == "AB12CD"
    assert changes[0]["matched_user"] == "다운"

    revs = client.get(f"/api/docs/{doc_id}/revisions").json()
    assert revs[0]["access_key"] == "AB12CD"
    assert revs[0]["matched_user"] == "다운"

    logs = client.get("/api/access/logs").json()["logs"]
    actions = [x["action"] for x in logs]
    assert "edit" in actions and "create" in actions


def test_legacy_me_name_format_retroactively_matched_by_keybook(client):
    client.post("/api/teams", json=T)
    # 구버전 호환 포맷 (<이름>#<키값>) 으로만 세션 작성자 변경
    r = client.post("/api/me/name", json={"member": "게스트#R4X8N2"})
    assert r.status_code == 200

    cl = client.post("/api/docs", json={"kind": "cloud", "body": CLOUD, "message": "게스트 수정"}).json()
    ch1 = client.get("/api/changes").json()
    assert ch1[0]["access_key"] == "R4X8N2"
    assert ch1[0]["matched_user"] == "게스트"

    # 사후에 키북에서 R4X8N2 -> 혜빈 으로 매칭 등록
    kb = client.post("/api/access/keybook", json={"access_key": "r4x8n2", "member": "혜빈"})
    assert kb.status_code == 200
    assert kb.json()["keybook"]["R4X8N2"]["member"] == "혜빈"

    # 최근 변경자료 및 문서 기록 조회 시 즉시 소급 매칭되어 표시됨
    ch2 = client.get("/api/changes").json()
    assert ch2[0]["access_key"] == "R4X8N2"
    assert ch2[0]["matched_user"] == "혜빈"

    revs = client.get(f"/api/docs/{cl['id']}/revisions").json()
    assert revs[0]["matched_user"] == "혜빈"


def test_access_keybook_isolation_and_validation(client):
    client.post("/api/teams", json=T)
    bad = client.post("/api/access/register", json={"member": "다운", "access_key": "!"})
    assert bad.status_code == 422

    client.post("/api/access/keybook", json={"access_key": "TEAM1KEY", "member": "다운"})
    client.post("/api/logout")
    client.post("/api/teams", json={**T, "slug": "t02"})

    other_logs = client.get("/api/access/logs").json()
    assert "TEAM1KEY" not in other_logs["keybook"]
    assert other_logs["logs"] == []
