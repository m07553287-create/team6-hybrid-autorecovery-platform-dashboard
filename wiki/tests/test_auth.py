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


def test_password_hashed(client, conn):
    client.post("/api/teams", json=T)
    h, = conn.execute("select pw_hash from teams").fetchone()
    assert h != T["password"] and len(h) == 64


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
