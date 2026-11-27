import json
import time

import pytest
from starlette.websockets import WebSocketDisconnect

from console.tests.conftest import PW, ORIGIN


def H(client, origin=ORIGIN):
    """TestClient 의 WebSocket 은 쿠키 저장소를 쓰지 않아 쿠키를 직접 싣는다."""
    tok = next((c.value for c in client.cookies.jar if c.name == "fc_s"), "")
    return {"Origin": origin, "cookie": f"fc_s={tok}"}


def test_unlock_wrong_then_rate_limit(client):
    codes = [client.post("/console/api/unlock", json={"password": "nope"}).status_code for _ in range(6)]
    assert codes[:5] == [401] * 5 and codes[5] == 429


def test_unlock_cookie_flags(client):
    r = client.post("/console/api/unlock", json={"password": PW})
    sc = r.headers["set-cookie"]
    assert r.status_code == 200 and "fc_s=" in sc and "HttpOnly" in sc and "Path=/console" in sc and "strict" in sc.lower()


def test_targets_requires_unlock(client):
    assert client.get("/console/api/targets").status_code == 401


def test_targets_list(unlocked):
    t = unlocked.get("/console/api/targets").json()
    assert [x["id"] for x in t] == ["echo", "dead"]
    assert "argv" not in t[0] and t[1]["disabled"]


def test_unlock_bad_origin_403(client):
    r = client.post("/console/api/unlock", json={"password": PW}, headers={"Origin": "https://evil.example"})
    assert r.status_code == 403


def test_ws_requires_unlock(client):
    with client.websocket_connect("/console/ws/echo", headers={"Origin": ORIGIN}) as ws:
        with pytest.raises(WebSocketDisconnect) as e:
            ws.receive_text()
    assert e.value.code == 4401


def test_ws_bad_origin(unlocked):
    with unlocked.websocket_connect("/console/ws/echo", headers=H(unlocked, "https://evil.example")) as ws:
        with pytest.raises(WebSocketDisconnect) as e:
            ws.receive_text()
    assert e.value.code == 4403


def test_ws_unknown_target(unlocked):
    with unlocked.websocket_connect("/console/ws/nope", headers=H(unlocked)) as ws:
        with pytest.raises(WebSocketDisconnect) as e:
            ws.receive_text()
    assert e.value.code == 4404


def test_ws_disabled_target(unlocked):
    with unlocked.websocket_connect("/console/ws/dead", headers=H(unlocked)) as ws:
        with pytest.raises(WebSocketDisconnect) as e:
            ws.receive_text()
    assert e.value.code == 4409


def read_until(ws, needle, limit=50):
    buf = ""
    for _ in range(limit):
        buf += ws.receive_text()
        if needle in buf:
            return buf
    raise AssertionError(buf)


def test_ws_roundtrip_and_audit(unlocked, tmp_path):
    with unlocked.websocket_connect("/console/ws/echo?cols=100&rows=30", headers=H(unlocked)) as ws:
        ws.send_text(json.dumps({"t": "r", "c": 120, "r": 40}))
        ws.send_text(json.dumps({"t": "i", "d": "hello-console\n"}))
        assert "hello-console" in read_until(ws, "hello-console")
    time.sleep(0.2)
    logs = list((tmp_path / "logs").rglob("*.log"))
    assert len(logs) == 1 and "echo" in logs[0].name
    assert "hello-console" in logs[0].read_text(errors="replace")


def test_ws_max_sessions(unlocked, monkeypatch):
    import console.app as ca
    monkeypatch.setattr(ca, "MAX_SESSIONS", 1)
    with unlocked.websocket_connect("/console/ws/echo", headers=H(unlocked)) as ws1:
        ws1.send_text(json.dumps({"t": "i", "d": "x\n"}))
        read_until(ws1, "x")
        with unlocked.websocket_connect("/console/ws/echo", headers=H(unlocked)) as ws2:
            with pytest.raises(WebSocketDisconnect) as e:
                ws2.receive_text()
        assert e.value.code == 4429


def test_lock(unlocked):
    assert unlocked.post("/console/api/lock").status_code == 200
    assert unlocked.get("/console/api/targets").status_code == 401
