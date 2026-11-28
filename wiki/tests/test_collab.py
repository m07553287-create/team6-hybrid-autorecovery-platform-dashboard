import json
import pathlib
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
ROOT = pathlib.Path(__file__).resolve().parents[2]


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
    assert spec["paths"]["/api/ai/goals"]["post"]["operationId"] == "upsertTeamGoal"


def test_oauth_rejects_bad_redirect(client):
    res = client.get(
        "/api/ai/oauth/authorize",
        params={"client_id": "figteam-ai-connector", "redirect_uri": "https://evil.example.com/cb"},
    )
    assert res.status_code == 400


def test_oauth_full_flow_goals_and_bearer_api(client, r, monkeypatch):
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

    # 4. Create goal & share via Bearer token + mocked Discord Webhook
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

    goal_res = ext_client.post(
        "/api/ai/goals",
        headers={"Authorization": f"Bearer {access_token}"},
        json={
            "title": "k3s flannel 10.42.0.0/16 및 DB GTID 검증",
            "area": "inst-cp1/k8s",
            "status": "in_progress",
            "note": "cp1/w1 Ready 및 ch_dr 지연 0초 목표",
        },
    )
    assert goal_res.status_code == 200
    goal_data = goal_res.json()
    gid = goal_data["goal"]["id"]
    assert goal_data["summary"]["in_progress"] == 1
    assert len(captured) == 1
    assert "목표 진행중" in captured[0]["body"]["embeds"][0]["title"]

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
            "goal_id": gid,
            "goal_status": "done",
        },
    )
    assert share_res.status_code == 200
    body = share_res.json()
    assert body["ok"] is True
    assert body["discord"]["sent"] is True
    assert body["goal"]["status"] == "done"
    assert any("GTID" in h for h in body["crosscheck_hints"])
    assert len(captured) == 2
    assert captured[1]["url"] == MOCK_WEBHOOK
    assert captured[1]["ua"] == "figteam-collab/1.0"
    assert "[완료] MySQL GTID 상태 확인" in captured[1]["body"]["embeds"][0]["title"]

    # 5. Feed read via Bearer token
    feed_res = ext_client.get(
        "/api/ai/feed",
        headers={"Authorization": f"Bearer {access_token}"},
        params={"area": "db01"},
    )
    assert feed_res.status_code == 200
    feed = feed_res.json()
    assert len(feed["shares"]) == 1
    assert feed["goal_summary"]["percent"] == 100
    assert "10.42.0.0/16" in feed["ai_launch_prompt"]
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


def test_hub_launchers_goals_and_xss(client, monkeypatch):
    monkeypatch.setenv("FIGTEAM_DISCORD_WEBHOOK_URL", "")
    assert client.post("/api/teams", json=TEAM).status_code == 201

    # Add goal via hub form
    g_post = client.post(
        "/api/ai/hub/goal",
        data={"title": "3사 DR 리허설", "area": "inst-awsdr/mysql", "owner": "홍길동", "note": "ch_dr 확인"},
    )
    assert g_post.status_code == 200
    assert "3사 DR 리허설" in g_post.text

    # Change goal status via 1-click button endpoint
    st_post = client.post("/api/ai/hub/goal-status", data={"goal_id": "1", "status": "done"})
    assert st_post.status_code == 200
    assert "달성 1/1 · 100%" in st_post.text

    # Hub GET with XSS prefill + check GPT/Claude/Gemini launchers
    page = client.get(
        "/api/ai/hub",
        params={"area": "ktedge/nginx", "status": "check_needed", "summary": "<script>alert(1)</script>"},
    )
    assert page.status_code == 200
    assert "<script>alert(1)</script>" not in page.text
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in page.text
    assert "ChatGPT로 열기" in page.text
    assert "Claude로 열기" in page.text
    assert "Gemini로 열기" in page.text

    # Prompt API
    p_res = client.get("/api/ai/prompt", params={"goal_id": 1})
    assert p_res.status_code == 200
    p_data = p_res.json()
    assert "3사 DR 리허설" in p_data["prompt"]
    assert "https://figteam.ktci5.kr/api/ai/hub" in p_data["prompt"]

    # Share via /api/ai/share-ui backward compatibility
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
        "/api/ai/goals",
        json={"title": "flannel CIDR 통일", "area": "cp1/k8s", "status": "done"},
    ).status_code == 200
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
    assert len(data["goals"]) == 1
    assert "## 5. 최신 팀 공동 목표 · 진행상황 및 설정 공유" in data["markdown_section"]
    assert "flannel CIDR 통일" in data["markdown_section"]
    assert "k3s 노드 정상" in data["markdown_section"]


def test_mcp_server_uses_flannel_1042():
    src = (ROOT / "mcp_server.py").read_text(encoding="utf-8")
    assert "Calico" not in src
    assert "10.244." not in src
    assert "10.42.0.0/16" in src
    assert "flannel VXLAN" in src


def test_discord_message_classification_task_vs_share():
    from wiki.collab import classify_discord_message, has_figteam_trigger

    assert has_figteam_trigger("#figteaminfra db-01 확인해주세요") is True
    assert has_figteam_trigger("일반 잡담입니다 점심 뭐먹지") is False

    t1 = classify_discord_message("#figteaminfra KT Edge 502 에러 간헐 발생 확인해주세요")
    assert t1["category"] == "task"
    assert t1["area"] == "inst-ktedge/nginx"

    t2 = classify_discord_message("#figteaminfra #과제 AWS DR GTID 지연 점검")
    assert t2["category"] == "task"
    assert t2["area"] == "inst-awsdr/dr"

    s1 = classify_discord_message("#figteaminfra #공유 k3s flannel 10.42.0.0/16 점검 완료했습니다")
    assert s1["category"] == "share"
    assert s1["area"] == "inst-cp1/k8s"


def test_discord_inbound_inbox_state_and_doc_delete_webhook(client, monkeypatch):
    monkeypatch.setenv("FIGTEAM_INTERNAL_KEY", "internal-test-key")
    monkeypatch.setenv("FIGTEAM_DISCORD_WEBHOOK_URL", MOCK_WEBHOOK)
    monkeypatch.setenv("FIGTEAM_DISCORD_NOTIFY_WIKI", "1")
    sent_payloads = []

    def fake_urlopen(req, timeout=5):
        sent_payloads.append(json.loads(req.data.decode("utf-8")))
        return _FakeResp(204)

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    assert client.post("/api/teams", json=TEAM).status_code == 201

    # 1. 트리거 없는 일반 메시지 무시, 트리거 있는 과제/공유 적재 + 중복 방지 + 비밀값 차단
    ig = client.post(
        "/api/discord/inbound",
        headers={"X-Internal-Key": "internal-test-key"},
        json={"content": "트리거 없는 잡담", "discord_message_id": "m1"},
    )
    assert ig.status_code == 200 and ig.json().get("ignored") is True

    sec = client.post(
        "/api/discord/inbound",
        headers={"X-Internal-Key": "internal-test-key"},
        json={"content": f"#figteaminfra {MOCK_WEBHOOK}", "discord_message_id": "m2"},
    )
    assert sec.status_code == 422

    r_task = client.post(
        "/api/discord/inbound",
        headers={"X-Internal-Key": "internal-test-key"},
        json={
            "content": "#figteaminfra db-01 MySQL 3306 연결 지연 확인 부탁드립니다",
            "discord_message_id": "m3",
            "author": "현진",
            "notify_discord": True,
        },
    )
    assert r_task.status_code == 200
    task_id = r_task.json()["item"]["id"]
    assert r_task.json()["item"]["category"] == "task"

    # 중복 discord_message_id 차단
    dup = client.post(
        "/api/discord/inbound",
        headers={"X-Internal-Key": "internal-test-key"},
        json={"content": "#figteaminfra duplicate", "discord_message_id": "m3"},
    )
    assert dup.status_code == 200 and dup.json().get("duplicate") is True

    r_share = client.post(
        "/api/discord/inbound",
        headers={"X-Internal-Key": "internal-test-key"},
        json={
            "content": "#figteaminfra #공유 k3s w1 노드 패치 완료했습니다",
            "discord_message_id": "m4",
            "author": "민수",
        },
    )
    assert r_share.status_code == 200 and r_share.json()["item"]["category"] == "share"

    # 2. 수신함 조회 및 처리 (처리완료 + 공동목표 승격)
    inbox = client.get("/api/discord/inbox").json()
    assert inbox["summary"]["total"] == 2
    assert inbox["summary"]["tasks_open"] == 1
    assert inbox["summary"]["shares"] == 1

    upd = client.post(
        f"/api/discord/inbox/{task_id}/state",
        json={"task_status": "done", "promote_goal": True},
    )
    assert upd.status_code == 200 and upd.json()["item"]["task_status"] == "done" and upd.json()["goal"]["id"] >= 1

    # 3. /api/ai/hub HTML 에 수신함/발신함 분리 메뉴바 및 탭 패널 확인
    hub = client.get("/api/ai/hub")
    assert hub.status_code == 200
    assert "Discord 멘션 수신함" in hub.text
    assert "처리할 과제" in hub.text and "공유" in hub.text
    assert "hub-nav" in hub.text and "pane-inbox" in hub.text and "pane-dispatch" in hub.text
    assert "수신함 (디코 ➔ 웹)" in hub.text and "발신함 (웹 ➔ 디코)" in hub.text

    hub_dispatch = client.get("/api/ai/hub?tab=dispatch")
    assert hub_dispatch.status_code == 200
    assert 'default_tab = "dispatch"' in hub_dispatch.text or 'switchHubTab(\'dispatch\')' in hub_dispatch.text or 'data-pane="dispatch"' in hub_dispatch.text

    # 4. 문서 생성·수정·삭제·복원 모두 Discord Webhook 알림 전송 확인
    sent_payloads.clear()
    created = client.post("/api/docs", json={"kind": "page", "body": {"title": "노트", "blocks": []}, "message": "생성"}).json()
    assert client.put(f"/api/docs/{created['id']}", json={"base_rev": 1, "body": {"title": "노트2", "blocks": []}, "message": "수정"}).status_code == 200
    assert client.request("DELETE", f"/api/docs/{created['id']}", json={"base_rev": 2, "message": "삭제"}).status_code == 200
    assert client.post(f"/api/docs/{created['id']}/restore", json={"base_rev": 3, "rev": 1, "message": "복원"}).status_code == 200
    titles = [p["embeds"][0]["title"] for p in sent_payloads]
    assert any("신규 생성" in t for t in titles)
    assert any("수정" in t for t in titles)
    assert any("삭제" in t for t in titles)
    assert any("되돌리기" in t for t in titles)
