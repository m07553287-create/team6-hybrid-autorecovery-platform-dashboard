import asyncio
import json

from console.status import build_script, parse, probe, probe_argv

SAMPLE = """nproc 2
load 0.42
mem 4000000000 1000000000
disk 40000000000 10000000000
uptime 86400
cpu 37
unit k3s active 3600000000
unit nope inactive 0
pod kube-system coredns-abc Running 2026-11-19T02:02:13Z
pod minwon-sample minwon-app-1 Pending <none>
"""


def test_build_script_has_units_and_pods():
    s = build_script(["k3s", "mysql"], "kubectl get pods")
    assert "for u in k3s mysql" in s and "kubectl get pods" in s and "/proc/stat" in s


def test_build_script_rejects_bad_unit():
    import pytest
    with pytest.raises(ValueError):
        build_script(["k3s; rm -rf /"], None)


def test_parse_sample():
    d = parse(SAMPLE)
    assert d["nproc"] == 2 and d["cpu_pct"] == 37 and d["load1"] == 0.42
    assert d["mem_total"] == 4000000000 and d["mem_used"] == 3000000000
    assert d["disk_total"] == 40000000000 and d["disk_used"] == 10000000000
    assert d["uptime_s"] == 86400
    u = {x["unit"]: x for x in d["units"]}
    assert u["k3s"]["state"] == "active" and u["k3s"]["since_s"] == 86400 - 3600
    assert u["nope"]["state"] == "inactive" and u["nope"]["since_s"] is None
    assert d["pods"][0] == {"ns": "kube-system", "name": "coredns-abc", "phase": "Running", "start": "2026-11-19T02:02:13Z"}


def test_parse_garbage_safe():
    d = parse("nproc x\nload \nunit\n")
    assert d["nproc"] is None and d["units"] == []


def test_probe_argv():
    assert probe_argv(["ssh", "-tt", "-o", "X=1", "u@h"]) == ["ssh", "-T", "-o", "X=1", "u@h", "bash -s"]
    assert probe_argv(["bash", "-l"]) == ["bash", "-s"]


def test_probe_alive_and_dead():
    ok = {"id": "a", "argv": ["sh", "-c", "cat >/dev/null; printf 'nproc 4\\ncpu 10\\n'"], "units": [["x", "daemon", "d"]]}
    dead = {"id": "b", "argv": ["sh", "-c", "cat >/dev/null; exit 255"]}
    r1, r2 = asyncio.run(probe(ok, raw=True)), asyncio.run(probe(dead, raw=True))
    assert r1["alive"] is True and r1["nproc"] == 4 and r1["latency_ms"] >= 0
    assert r2["alive"] is False and r2["error"]


def test_status_api_no_lock(client, app):
    app.state.collector.snapshot = {"collected_at": 1, "instances": [{"id": "echo", "alive": True}]}
    r = client.get("/console/api/status")
    assert r.status_code == 200 and r.json()["instances"][0]["id"] == "echo"
    assert "argv" not in json.dumps(r.json())


def test_targets_include_presets(unlocked):
    t = unlocked.get("/console/api/targets").json()
    assert "check" in t[0] and "argv" not in t[0]
