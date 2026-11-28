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


def test_keyless_previous_session_is_expired_when_required(r, monkeypatch):
    from wiki import auth
    from wiki.tests.conftest import make_client

    team_id = auth.add_team(r, "t01", "1팀", "pw-123456")
    # 접속 키 없이 생성된 이전 세션과, 접속 키가 있는 정상 세션 생성
    old_tok = auth.new_session(r, team_id, "게스트", access_key="")
    key_tok = auth.new_session(r, team_id, "다운#K7M3P9", access_key="K7M3P9")

    monkeypatch.setenv("WIKI_REQUIRE_ACCESS_KEY", "1")
    with make_client(r) as c:
        # 키 없는 이전 세션으로는 /api/me 및 /api/tree 즉시 만료 (401 + key_expired + 쿠키 삭제)
        c.cookies.set(auth.COOKIE, old_tok)
        r_me = c.get("/api/me")
        assert r_me.status_code == 401
        assert r_me.json().get("key_expired") is True
        assert auth.get_session(r, old_tok) is None

        c.cookies.set(auth.COOKIE, key_tok)
        assert c.get("/api/me").status_code == 200
        assert c.get("/api/tree").status_code == 200

        # 서버가 접속 키를 자동 할당하고 클라이언트 임의 access_key는 무시하며, 이름 변경 시에도 키 불변 + 이력 추적
        c.cookies.clear()
        ok_login = c.post("/api/login", json={"slug": "t01", "password": "pw-123456", "member": "혜빈", "access_key": "HACK99"})
        assert ok_login.status_code == 200
        assigned_ak = ok_login.json()["access_key"]
        assert len(assigned_ak) == 8 and assigned_ak != "HACK99"
        me = c.get("/api/me")
        assert me.status_code == 200 and me.json()["access_key"] == assigned_ak

        # rename / register 로 다른 키를 보내도 기존 키 고정 및 이름·IP 이력 누적
        c.post("/api/me/name", json={"member": "새이름#FAKE99", "access_key": "FAKE99"})
        c.post("/api/access/register", json={"member": "새이름", "access_key": "FAKE99", "action": "visit"})
        assert c.get("/api/me").json()["access_key"] == assigned_ak
        logs_res = c.get("/api/access/logs").json()
        kb_entry = logs_res["keybook"][assigned_ak]
        assert "FAKE99" not in logs_res["keybook"]
        assert "혜빈" in kb_entry["names"] and "새이름" in kb_entry["names"]
        assert len(kb_entry["ips"]) >= 1 and kb_entry["first_seen"] <= kb_entry["updated_at"]


def test_auto_login_requires_access_key_header_and_bulk_expire(r, monkeypatch):
    from wiki import auth
    from wiki.tests.conftest import make_client

    team_id = auth.add_team(r, "t01", "1팀", "pw-123456")
    tok_nokey = auth.new_session(r, team_id, "게스트", access_key="")
    tok_withkey = auth.new_session(r, team_id, "다운", access_key="VALID9")

    assert auth.expire_keyless_sessions(r, team_id) == 1
    assert auth.get_session(r, tok_nokey) is None
    assert auth.get_session(r, tok_withkey) is not None

    monkeypatch.setenv("WIKI_REQUIRE_ACCESS_KEY", "1")
    monkeypatch.setenv("AUTO_LOGIN_TEAM", "t01")
    with make_client(r) as c:
        # 헤더에 키가 없으면 AUTO_LOGIN_TEAM이라도 401(key_expired)
        r_nohdr = c.get("/api/me")
        assert r_nohdr.status_code == 401 and r_nohdr.json().get("key_expired") is True

        # 유효한 X-Fig-Access-Key 헤더가 있으면 키 바인딩된 자동 세션 발급
        r_hdr = c.get("/api/me", headers={"X-Fig-Access-Key": "AUTO99"})
        assert r_hdr.status_code == 200 and r_hdr.json()["access_key"] == "AUTO99"


def test_site_visit_beacon_and_visitors_endpoint(client):
    # 비로그인 상태에서 사이트 전체 접속 기록(방문자, 실패, 만료) 적재 허용
    v1 = client.post("/api/visit", json={"path": "/", "view": "login", "auth_state": "visitor", "detail": "첫 방문"},
                     headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X) Chrome/131.0.0.0 Safari/537.36"})
    assert v1.status_code == 200
    v2 = client.post("/api/visit", json={"path": "/", "view": "login", "auth_state": "login_fail", "detail": "비번 오류"})
    assert v2.status_code == 200

    # 조회(/api/access/visitors)는 로그인 전 차단(401)
    assert client.get("/api/access/visitors").status_code == 401

    # 팀 생성·로그인 후 조회 시 요약 및 매칭 확인
    assert client.post("/api/teams", json={**T, "access_key": "TEAM99"}).status_code == 201
    client.post("/api/visit", json={"path": "/#cfg/", "view": "settings", "auth_state": "authenticated", "access_key": "TEAM99", "detail": "설정 진입"})
    res = client.get("/api/access/visitors")
    assert res.status_code == 200
    body = res.json()
    assert body["summary"]["total"] == 3
    assert body["summary"]["authenticated"] == 1
    assert body["summary"]["anonymous"] == 1
    assert body["summary"]["expired_or_fail"] == 1
    assert any(row["matched_user"] == "다운" and row["access_key"] == "TEAM99" for row in body["visits"])
