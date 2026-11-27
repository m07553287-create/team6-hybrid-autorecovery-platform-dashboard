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


# ---- 오픈스택 배치: 호스트(virsh) → VM 부모 자동 결정 ----
def test_build_script_vms():
    s = build_script([], None, vms=True)
    assert "virsh list --all --name" in s and "LANG=C" in s and "nova:name" in s
    assert "virsh" not in build_script([], None)


def test_parse_vm_lines():
    d = parse("vm k8s-cp1 running\nvm db-01 shutoff\nvm bad\n")
    assert d["vms"] == [{"name": "k8s-cp1", "state": "running"}, {"name": "db-01", "state": "shutoff"}]


def test_collector_places_vm_under_actual_host():
    from console.status import Collector
    targets = {
        "compute3": {"id": "compute3", "area": "openstack", "name": "compute3", "argv": ["true"], "vms": True},
        "compute4": {"id": "compute4", "area": "openstack", "name": "compute4", "argv": ["true"], "vms": True},
        "db-01": {"id": "db-01", "area": "openstack", "name": "db-01", "argv": ["true"], "parent": "compute4"},
        "k8s-cp1": {"id": "k8s-cp1", "area": "openstack", "name": "k8s-cp1", "argv": ["true"], "parent": "compute3"},
    }
    c = Collector(targets, list(targets), 0)
    items = [c._meta(targets[i]) for i in targets]
    items[0]["vms"] = [{"name": "db-01", "state": "running"}]   # db-01 이 compute3 으로 옮겨진 상황
    items[1]["vms"] = []
    Collector.place(items)
    by = {i["id"]: i for i in items}
    assert by["db-01"]["parent"] == "compute3" and by["db-01"]["vm_state"] == "running"
    assert by["k8s-cp1"]["parent"] == "compute3" and "vm_state" not in by["k8s-cp1"]   # 못 찾으면 정적 부모 유지


def test_s1_is_name_only():
    t = {x["id"]: x for x in json.load(open("console/targets.json", encoding="utf-8"))}
    assert t["s1"].get("disabled") and t["s1"]["argv"] == ["true"] and not t["s1"].get("check")
    assert all(t[h].get("parent") != "s1" for h in ("controller", "compute1", "compute3", "compute4"))
    assert t["k8s-cp1"]["role"] == "마스터" and t["k8s-w1"]["role"] == "워커" and t["db-01"]["role"] == "DB"
