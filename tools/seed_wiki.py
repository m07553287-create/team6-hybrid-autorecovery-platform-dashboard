"""figteam 실측 가이드(content/settings_guide.py) → 위키 DB 시드.

사용: REDIS_PASSWORD=… python3 tools/seed_wiki.py --slug figteam --name "figteam (team6)"
비밀번호는 실행할 때 입력받고, 해시만 DB 에 들어간다.
"""
import argparse
import getpass
import json
import pathlib
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "content"))

import settings_guide as g  # noqa: E402
from wiki import store  # noqa: E402
from wiki.auth import add_team  # noqa: E402
from wiki.docs import add_script, insert_doc  # noqa: E402
from wiki.errors import ApiError  # noqa: E402

AUTHOR = "seed"
MESSAGE = "2026-11-26 실측 가이드에서 가져옴"
CLOUDS = [("onprem", "온프렘 호스트", "GPU 노트북 s1 — VMware 위에 OpenStack 노드, WireGuard·Cloudflare 터널"),
          ("openstack", "OpenStack", "Packstack/RDO, OVN — controller + compute1·3·4"),
          ("kt", "KT Cloud", "공개 진입점(Edge·WAF)과 WireGuard 허브"),
          ("aws", "AWS", "Pilot-Light DR(aws-dr)과 Recovery Orchestrator(aws-ctl)")]
AREA_FIELDS = ["name", "status", "domains", "design", "config", "commands", "verify", "trouble"]
INST_FIELDS = ["title", "short", "tag", "status", "desc", "steps", "specs"]


def _ins(r, team_id, kind, parent, sort, body, now):
    return insert_doc(r, team_id, kind, parent, sort, body, AUTHOR, MESSAGE, now)


def _script_text(sc):
    if "generate" in sc:
        pid, aid, idx = sc["generate"]
        area = next(a for a in g.PAGES[pid]["areas"] if a["id"] == aid)
        lines = area["config"][idx]["code"].split("\n")
        lines.insert(1, "# 원본: 이 가이드의 설계안 (" + sc["path"] + " 로 저장해 실행) · 아직 적용 전")
        return "\n".join(lines) + "\n"
    return (ROOT / "content" / "scripts" / sc["file"]).read_text(encoding="utf-8")


def _page_blocks(page):
    out = []
    for b in page["blocks"]:
        if b["type"] == "vars":
            out.append({"type": "table", "head": ["변수", "값 (실측)", "사용처", "바뀌면 확인"], "rows": g.VARIABLES})
        elif b["type"] == "legend":
            out.append({"type": "p", "text": "실측: 현재 구성을 직접 조회한 값 / 설계·미적용: 적용 전 설계안 / "
                                             "미실측: 접속 불가로 외부 응답·문서만 확인"})
        else:
            out.append(b)
    return out


def seed(r, slug, name, password):
    data = g.data()
    if r.exists(f"fw:team:{slug}"):
        raise SystemExit(f"이미 '{slug}' 팀이 있습니다. 시드를 중단합니다.")
    try:
        team_id = add_team(r, slug, name, password)
    except ApiError as e:
        raise SystemExit(e.message)
    now = int(time.time())
    counts = {"cloud": 0, "instance": 0, "area": 0, "steps": 0, "page": 0, "scripts": 0}
    cloud_id = {}
    for i, (prov, cname, cdesc) in enumerate(CLOUDS):
        cloud_id[prov] = _ins(r, team_id, "cloud", None, i, {"name": cname, "provider": prov, "desc": cdesc}, now)
        counts["cloud"] += 1
    inst_id, area_id = {}, {}
    for i, pid in enumerate(data["instances"]):
        p = g.PAGES[pid]
        body = {k: p.get(k) for k in INST_FIELDS}
        body["short"] = g.INSTANCE_SHORT[pid]
        body["slug"] = pid  # 예전 공개 링크(#cfg/inst/inst-s1/…) 연결용
        inst_id[pid] = _ins(r, team_id, "instance", cloud_id[p["cloud"]], i, body, now)
        counts["instance"] += 1
        for j, a in enumerate(p["areas"]):
            abody = {k: a.get(k) for k in AREA_FIELDS}
            abody["domains"] = g.AREA_DOMAINS[pid + "." + a["id"]]
            abody["slug"] = a["id"]
            area_id[(pid, a["id"])] = _ins(r, team_id, "area", inst_id[pid], j, abody, now)
            counts["area"] += 1
    items = [{"no": s["no"], "title": s["title"], "where": s["where"], "why": s["why"], "gate": s["gate"],
              "instance_id": inst_id[s["page"]], "area_id": area_id[(s["page"], s["area"])]} for s in g.STEPS]
    _ins(r, team_id, "steps", None, 0, {"items": items}, now)
    counts["steps"] += 1
    for i, (pid, _title) in enumerate(g.REFERENCE):
        p = g.PAGES[pid]
        _ins(r, team_id, "page", None, i, {"title": p["title"], "tag": p.get("tag", ""), "desc": p["desc"],
                                            "blocks": _page_blocks(p)}, now)
        counts["page"] += 1
    for sc in g.SCRIPTS:
        if "url" in sc:
            continue  # 외부 링크는 화면 정적 설정에 둔다
        add_script(r, team_id, sc["path"], sc["host"], sc["status"], sc["keys"], _script_text(sc))
        counts["scripts"] += 1
    return counts


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--slug", default="figteam")
    ap.add_argument("--name", default="figteam (team6)")
    a = ap.parse_args()
    pw = getpass.getpass(f"'{a.slug}' 팀 비밀번호: ")
    if pw != getpass.getpass("한 번 더: "):
        sys.exit("두 입력이 다릅니다")
    if len(pw) < 6:
        sys.exit("비밀번호는 6자 이상이어야 합니다")
    print(seed(store.connect(), a.slug, a.name, pw))


if __name__ == "__main__":
    main()
