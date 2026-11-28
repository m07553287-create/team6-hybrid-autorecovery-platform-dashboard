import json
import urllib.parse

from fastapi.testclient import TestClient

from wiki.app import create_app

TEAM = {
    "slug": "figteam",
    "name": "figteam",
    "password": "pw-figteam-1234",
    "member": "홍길동",
    "access_key": "DEV01",
    "create_code": "test-code",
}
CB_URI = "https://chatgpt.com/aip/g-test/oauth/callback"
MOCK_WEBHOOK = "https://discord.com/api/webhooks/100000000000000000/mock-token"


class _FakeResp:
    def __init__(self, status=204, body=b""):
        self.status = status
        self._body = body

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def test_openapi_spec(client):
    res = client.get("/api/ai/openapi.json")
    assert res.status_code == 200
    spec = res.json()
    assert "figteamOAuth" in spec["components"]["securitySchemes"]
    assert spec["paths"]["/api/ai/feed"]["get"]["operationId"] == "getTeamFeed"
    assert spec["paths"]["/api/ai/share"]["post"]["operationId"] == "shareTeamUpdate"


def test_oauth_rejects_bad_redirect(client):
    res = client.get(
        "/api/ai/oauth/authorize",
        params={"client_id": "figteam-ai-connector", "redirect_uri": "https://evil.example.com/cb"},
    )
    assert res.status_code == 400


def test_oauth_full_flow_and_bearer_api(client, r, monkeypatch):
    assert client.post("/api/teams", json=TEAM).status_code == 201
    client.post("/api/logout")

    # 1. Authorize page
    auth_page = client.get(
        "/api/ai/oauth/authorize",
        params={"client_id": "figteam-ai-connector", "redirect_uri": CB_URI, "state": "st-xyz"},
    )
    assert auth_page.status_code == 200
    assert "AI 커넥터 로그인 승인" in auth_page.text

    # 2. Approve with login credentials -> 302 callback with code
    approve = client.post(
        "/api/ai/oauth/approve",
        data={
            "client_id": "figteam-ai-connector",
            "redirect_uri": CB_URI,
            "state": "st-xyz",
            "scope": "read write",
            "slug": "figteam",
            "member": "홍길동",
            "access_key": "DEV01",
            "password": TEAM["password"],
        },
        follow_redirects=False,
    )
    assert approve.status_code == 302
    loc = approve.headers["location"]
    assert loc.startswith(CB_URI)
    qs = urllib.parse.parse_qs(urllib.parse.urlparse(loc).query)
    assert qs["state"] == ["st-xyz"]
    code = qs["code"][0]

    # 3. Token exchange from external AI client (no Origin header)
    ext_client = TestClient(create_app(redis_client=r), base_url="https://testserver")
    tok_res = ext_client.post(
        "/api/ai/oauth/token",
        data={
            "grant_type": "authorization_code",
            "code": code,
            "client_id": "figteam-ai-connector",
            "redirect_uri": CB_URI,
        },
    )
    assert tok_res.status_code == 200
    tok_json = tok_res.json()
    assert tok_json["token_type"] == "Bearer"
    access_token = tok_json["access_token"]
    assert access_token.startswith("ft_")

    # Code cannot be reused
    reuse = ext_client.post(
        "/api/ai/oauth/token",
        data={
            "grant_type": "authorization_code",
            "code": code,
            "client_id": "figteam-ai-connector",
            "redirect_uri": CB_URI,
        },
    )
    assert reuse.status_code == 400
    assert reuse.json()["error"] == "invalid_grant"

    # 4. Share via Bearer token + mocked Discord Webhook
    captured = []

    def fake_urlopen(req, timeout=5):
        captured.append(
            {
                "url": req.full_url,
                "ua": req.get_header("User-agent"),
                "body": json.loads(req.data.decode("utf-8")),
            }
        )
        return _FakeResp(204)

    monkeypatch.setenv("FIGTEAM_DISCORD_WEBHOOK_URL", MOCK_WEBHOOK)
    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    share_res = ext_client.post(
        "/api/ai/share",
        headers={"Authorization": f"Bearer {access_token}"},
        json={
            "area": "inst-db01/mysql",
            "status": "done",
            "title": "MySQL GTID 상태 확인",
            "summary": "db-01 MySQL binlog 및 GTID 복제 지연 0초 확인 완료",
            "check_request": "AWS DR 담당자 ch_dr 확인 부탁드립니다",
            "cfg_url": "https://figteam.ktci5.kr/#cfg/inst/inst-db01/mysql",
        },
    )
    assert share_res.status_code == 200
    body = share_res.json()
    assert body["ok"] is True
    assert body["discord"]["sent"] is True
    assert any("GTID" in h for h in body["crosscheck_hints"])
    assert len(captured) == 1
    assert captured[0]["url"] == MOCK_WEBHOOK
    assert captured[0]["ua"] == "figteam-collab/1.0"
    assert "[완료] MySQL GTID 상태 확인" in captured[0]["body"]["embeds"][0]["title"]

    # 5. Feed read via Bearer token
    feed_res = ext_client.get(
        "/api/ai/feed",
        headers={"Authorization": f"Bearer {access_token}"},
        params={"area": "db01"},
    )
    assert feed_res.status_code == 200
    feed = feed_res.json()
    assert len(feed["shares"]) == 1
    assert "MySQL GTID 상태 확인" in feed["markdown_brief"]

    # 6. Invalid Bearer rejected, and non-Bearer external Origin POST rejected (403)
    bad_tok = ext_client.get("/api/ai/feed", headers={"Authorization": "Bearer ft_invalid"})
    assert bad_tok.status_code == 401
    no_origin_post = ext_client.post("/api/ai/share", json={"summary": "blocked"})
    assert no_origin_post.status_code == 403


def test_share_blocks_secrets(client, monkeypatch):
    monkeypatch.setenv("FIGTEAM_DISCORD_WEBHOOK_URL", "")
    assert client.post("/api/teams", json=TEAM).status_code == 201

    r1 = client.post("/api/ai/share", json={"summary": f"hook={MOCK_WEBHOOK}"})
    assert r1.status_code == 422

    r2 = client.post("/api/ai/share", json={"summary": "-----BEGIN OPENSSH PRIVATE KEY-----"})
    assert r2.status_code == 422


def test_share_ui_get_and_post(client, monkeypatch):
    monkeypatch.setenv("FIGTEAM_DISCORD_WEBHOOK_URL", "")
    assert client.post("/api/teams", json=TEAM).status_code == 201

    page = client.get(
        "/api/ai/share-ui",
        params={"area": "ktedge/nginx", "status": "check_needed", "summary": "<script>alert(1)</script>"},
    )
    assert page.status_code == 200
    assert "<script>alert(1)</script>" not in page.text
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in page.text

    posted = client.post(
        "/api/ai/share-ui",
        data={
            "area": "ktedge/nginx",
            "status": "in_progress",
            "title": "WAF 캐시 TTL 조정",
            "summary": "10초 마이크로캐시 유지 및 upstream 점검중",
            "check_request": "k3s NodePort 30080 응답 확인 필요",
            "cfg_url": "https://figteam.ktci5.kr/#cfg/inst/inst-ktedge/nginx",
        },
    )
    assert posted.status_code == 200
    assert "WAF 캐시 TTL 조정" in posted.text
    assert "등록됨" in posted.text


def test_internal_feed_auth_and_markdown(client, monkeypatch):
    monkeypatch.setenv("FIGTEAM_INTERNAL_KEY", "internal-test-key")
    monkeypatch.setenv("FIGTEAM_DISCORD_WEBHOOK_URL", "")
    assert client.post("/api/teams", json=TEAM).status_code == 201
    assert client.post(
        "/api/ai/share",
        json={"area": "cp1/k8s", "status": "done", "title": "k3s 노드 정상", "summary": "cp1/w1 Ready"},
    ).status_code == 200

    assert client.get("/api/ai/feed/internal").status_code == 401
    assert client.get("/api/ai/feed/internal", headers={"X-Internal-Key": "wrong"}).status_code == 401

    ok = client.get("/api/ai/feed/internal", headers={"X-Internal-Key": "internal-test-key"})
    assert ok.status_code == 200
    data = ok.json()
    assert len(data["shares"]) == 1
    assert "## 5. 최신 팀 진행상황 및 설정 공유" in data["markdown_section"]
    assert "k3s 노드 정상" in data["markdown_section"]
