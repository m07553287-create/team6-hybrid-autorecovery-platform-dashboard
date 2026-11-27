T = {"slug": "t01", "name": "1팀", "password": "pw-123456", "member": "다운", "create_code": "test-code"}


def test_create_requires_code(client):
    r = client.post("/api/teams", json={**T, "create_code": "wrong"})
    assert r.status_code == 403


def test_create_then_me(client):
    assert client.post("/api/teams", json=T).status_code == 201
    me = client.get("/api/me").json()
    assert me == {"slug": "t01", "team_name": "1팀", "member": "다운"}


def test_duplicate_slug_409(client):
    client.post("/api/teams", json=T)
    assert client.post("/api/teams", json=T).status_code == 409


def test_bad_slug_422(client):
    assert client.post("/api/teams", json={**T, "slug": "A B"}).status_code == 422


def test_login_ok(client):
    client.post("/api/teams", json=T)
    client.post("/api/logout")
    r = client.post("/api/login", json={"slug": "t01", "password": "pw-123456", "member": "혜빈"})
    assert r.status_code == 200 and client.get("/api/me").json()["member"] == "혜빈"


def test_login_rate_limit(client):
    client.post("/api/teams", json=T)
    codes = [client.post("/api/login", json={"slug": "t01", "password": "nope", "member": "x"}).status_code
             for _ in range(11)]
    assert codes[:10] == [401] * 10 and codes[10] == 429


def test_password_hashed(client, r):
    client.post("/api/teams", json=T)
    h = r.hget("fw:team:t01", "pw_hash")
    assert h != T["password"] and len(h) == 64


def test_session_has_ttl(client, r):
    client.post("/api/teams", json=T)
    keys = r.keys("fw:sess:*")
    assert len(keys) == 1 and 0 < r.ttl(keys[0]) <= 7 * 24 * 3600


def test_logout(client):
    client.post("/api/teams", json=T)
    client.post("/api/logout")
    assert client.get("/api/me").status_code == 401


def test_change_password_expires_sessions(client):
    client.post("/api/teams", json=T)
    r = client.post("/api/team/password", json={"current": "pw-123456", "new": "pw-654321"})
    assert r.status_code == 200
    assert client.get("/api/me").status_code == 401
    assert client.post("/api/login", json={"slug": "t01", "password": "pw-654321", "member": "다운"}).status_code == 200


def test_post_without_origin_403(client):
    r = client.post("/api/teams", json=T, headers={"Origin": "https://evil.example"})
    assert r.status_code == 403


def test_cookie_flags(client):
    r = client.post("/api/teams", json=T)
    sc = r.headers["set-cookie"]
    assert "fw_s=" in sc and "HttpOnly" in sc and "Path=/api" in sc and "Secure" in sc and "SameSite=lax" in sc.replace("Lax", "lax")


def test_member_length_422(client):
    assert client.post("/api/teams", json={**T, "member": "가" * 21}).status_code == 422


def test_auto_login_me(r, monkeypatch):
    from wiki.auth import add_team
    from wiki.tests.conftest import make_client
    add_team(r, "t01", "1팀", "pw-123456")
    monkeypatch.setenv("AUTO_LOGIN_TEAM", "t01")
    with make_client(r) as c:
        resp = c.get("/api/me")
        assert resp.status_code == 200 and resp.json() == {"slug": "t01", "team_name": "1팀", "member": "게스트", "auto": True}
        assert "fw_s=" in resp.headers["set-cookie"]
        assert c.get("/api/tree").status_code == 200


def test_auto_login_off(client):
    assert client.get("/api/me").status_code == 401


def test_rename_member(client):
    client.post("/api/teams", json=T)
    assert client.post("/api/me/name", json={"member": "혜빈"}).status_code == 200
    assert client.get("/api/me").json()["member"] == "혜빈"
    assert client.post("/api/me/name", json={"member": "가" * 21}).status_code == 422
