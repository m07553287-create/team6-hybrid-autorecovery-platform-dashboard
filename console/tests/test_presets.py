import json

from console.tests.conftest import ORIGIN


def test_presets_require_login(client):
    assert client.get("/console/api/presets").status_code == 401


def test_presets_default_from_targets(unlocked):
    p = unlocked.get("/console/api/presets").json()
    items = p["echo"]["items"]
    assert p["echo"]["custom"] is False
    assert {"label": "상태", "cmd": "echo ok", "kind": "check"} in items
    assert {"label": "재시작", "cmd": "echo restart", "kind": "fix"} in items


def test_put_and_get(unlocked, tmp_path):
    items = [{"label": "디스크 사용량", "cmd": "df -h / && du -sh /var/log", "kind": "check"},
             {"label": "Restart nginx", "cmd": "sudo systemctl restart nginx", "kind": "fix"}]
    r = unlocked.put("/console/api/presets/echo", json={"items": items})
    assert r.status_code == 200
    p = unlocked.get("/console/api/presets").json()["echo"]
    assert p["custom"] is True and p["items"] == items
    saved = json.loads((tmp_path / "presets.json").read_text(encoding="utf-8"))
    assert saved["echo"] == items


def test_put_rejects_emoji(unlocked):
    r = unlocked.put("/console/api/presets/echo", json={"items": [{"label": "⏱ 상태", "cmd": "uptime", "kind": "check"}]})
    assert r.status_code == 422


def test_put_rejects_bad_items(unlocked):
    bad = [[{"label": "", "cmd": "uptime", "kind": "check"}],
           [{"label": "a", "cmd": "", "kind": "check"}],
           [{"label": "a", "cmd": "x" * 2001, "kind": "check"}],
           [{"label": "a", "cmd": "uptime", "kind": "other"}],
           [{"label": "a", "cmd": "uptime\nreboot", "kind": "check"}],
           [{"label": "a", "cmd": "uptime", "kind": "check"}] * 41]
    for items in bad:
        assert unlocked.put("/console/api/presets/echo", json={"items": items}).status_code == 422


def test_put_unknown_target_404(unlocked):
    assert unlocked.put("/console/api/presets/nope", json={"items": []}).status_code == 404


def test_put_origin_403(unlocked):
    r = unlocked.put("/console/api/presets/echo", json={"items": []}, headers={"Origin": "https://evil.example"})
    assert r.status_code == 403


def test_reset_restores_draft(unlocked):
    unlocked.put("/console/api/presets/echo", json={"items": [{"label": "x", "cmd": "uptime", "kind": "check"}]})
    assert unlocked.delete("/console/api/presets/echo").status_code == 200
    p = unlocked.get("/console/api/presets").json()["echo"]
    assert p["custom"] is False and p["items"][0]["label"] == "상태"
