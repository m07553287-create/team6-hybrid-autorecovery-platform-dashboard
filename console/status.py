"""읽기 전용 상태 수집: 각 대상에서 고정 스크립트로 CPU·메모리·디스크·가동 시간·유닛·파드를 모은다.

사용자 입력은 받지 않는다. 유닛 이름은 허용 문자만, 파드 명령은 targets.json 에서만 온다.
"""
import asyncio
import re
import time
import urllib.request

UNIT_RE = re.compile(r"^[A-Za-z0-9@._-]+$")
TIMEOUT = 15

_BASE = r"""
echo "nproc $(nproc 2>/dev/null)"
echo "load $(cut -d' ' -f1 /proc/loadavg 2>/dev/null)"
awk '/^MemTotal/{t=$2}/^MemAvailable/{a=$2}END{if(t)printf "mem %d %d\n",t*1024,a*1024}' /proc/meminfo 2>/dev/null
df -P -B1 / 2>/dev/null | awk 'NR==2{print "disk",$2,$3}'
echo "uptime $(cut -d. -f1 /proc/uptime 2>/dev/null)"
if [ -r /proc/stat ]; then
  set -- $(head -1 /proc/stat); shift; t1=0; for v in "$@"; do t1=$((t1+v)); done; i1=$(($4+${5:-0}))
  sleep 0.5
  set -- $(head -1 /proc/stat); shift; t2=0; for v in "$@"; do t2=$((t2+v)); done; i2=$(($4+${5:-0}))
  dt=$((t2-t1)); [ "$dt" -gt 0 ] || dt=1; echo "cpu $(( 100*(dt-(i2-i1))/dt ))"
fi
"""


def build_script(units, pods_cmd):
    for u in units:
        if not UNIT_RE.match(u):
            raise ValueError("허용되지 않은 유닛 이름: " + u)
    s = _BASE
    if units:
        s += ("for u in " + " ".join(units) + "; do "
              'echo "unit $u $(systemctl is-active $u 2>/dev/null | head -1) '
              '$(systemctl show -p ActiveEnterTimestampMonotonic --value $u 2>/dev/null)"; done\n')
    if pods_cmd:
        s += "(" + pods_cmd + ") 2>/dev/null | awk '{print \"pod\",$1,$2,$3,$4}'\n"
    return s


def _num(v, cast=int):
    try:
        return cast(v)
    except (TypeError, ValueError):
        return None


def parse(text):
    d = {"nproc": None, "load1": None, "cpu_pct": None, "mem_total": None, "mem_used": None,
         "disk_total": None, "disk_used": None, "uptime_s": None, "units": [], "pods": []}
    for line in text.splitlines():
        f = line.split()
        if not f:
            continue
        k = f[0]
        if k == "nproc" and len(f) > 1:
            d["nproc"] = _num(f[1])
        elif k == "load" and len(f) > 1:
            d["load1"] = _num(f[1], float)
        elif k == "cpu" and len(f) > 1:
            d["cpu_pct"] = _num(f[1])
        elif k == "mem" and len(f) > 2:
            t, a = _num(f[1]), _num(f[2])
            if t is not None and a is not None:
                d["mem_total"], d["mem_used"] = t, t - a
        elif k == "disk" and len(f) > 2:
            d["disk_total"], d["disk_used"] = _num(f[1]), _num(f[2])
        elif k == "uptime" and len(f) > 1:
            d["uptime_s"] = _num(f[1])
        elif k == "unit" and len(f) > 2:
            mono = _num(f[3]) if len(f) > 3 else None
            d["units"].append({"unit": f[1], "state": f[2], "mono_us": mono})
        elif k == "pod" and len(f) > 3:
            d["pods"].append({"ns": f[1], "name": f[2], "phase": f[3], "start": f[4] if len(f) > 4 else None})
    up = d["uptime_s"]
    for u in d["units"]:
        mono = u.pop("mono_us")
        u["since_s"] = (up - mono // 1_000_000) if (u["state"] == "active" and up and mono) else None
    return d


def probe_argv(argv):
    if argv and argv[0] == "ssh":
        return ["-T" if a == "-tt" else a for a in argv] + ["bash -s"]
    return ["bash", "-s"]


async def probe(target, raw=False):
    """대상 하나를 조사한다. raw=True 면 argv 를 그대로 실행(시험용)."""
    units = [u[0] for u in target.get("units", [])]
    script = build_script(units, target.get("pods"))
    argv = target["argv"] if raw else probe_argv(target["argv"])
    t0 = time.time()
    try:
        p = await asyncio.create_subprocess_exec(*argv, stdin=asyncio.subprocess.PIPE,
                                                 stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        out, err = await asyncio.wait_for(p.communicate(script.encode()), TIMEOUT)
        rc = p.returncode
    except (asyncio.TimeoutError, OSError) as e:
        try:
            p.kill()
        except Exception:
            pass
        return {"alive": False, "error": f"응답 없음 ({type(e).__name__})", "latency_ms": None}
    ms = int((time.time() - t0) * 1000)
    if rc == 255 or (rc != 0 and not out.strip()):
        return {"alive": False, "error": (err.decode(errors="replace").strip()[-200:] or f"종료 코드 {rc}"), "latency_ms": ms}
    d = parse(out.decode(errors="replace"))
    d.update(alive=True, error=None, latency_ms=ms)
    return d


async def probe_http(url):
    t0 = time.time()
    def get():
        with urllib.request.urlopen(url, timeout=6) as r:
            return r.status
    try:
        code = await asyncio.get_running_loop().run_in_executor(None, get)
        return {"alive": 200 <= code < 500, "error": None, "latency_ms": int((time.time() - t0) * 1000), "http_status": code}
    except Exception as e:
        return {"alive": False, "error": f"API 응답 없음 ({type(e).__name__})", "latency_ms": None}


class Collector:
    def __init__(self, targets, order, interval):
        self.targets, self.order, self.interval = targets, order, interval
        self.snapshot = {"collected_at": None, "instances": []}

    def _meta(self, t):
        return {k: t[k] for k in ("id", "area", "name", "desc", "host", "disabled", "parent") if k in t} | {
            "unit_meta": {u[0]: {"type": u[1], "desc": u[2]} for u in t.get("units", [])}}

    async def run_once(self):
        async def one(tid):
            t = self.targets[tid]
            if t.get("http"):
                r = await probe_http(t["http"])
            elif t.get("disabled"):
                r = {"alive": None, "error": t["disabled"]}
            else:
                r = await probe(t)
            return self._meta(t) | r
        items = await asyncio.gather(*(one(i) for i in self.order))
        self.snapshot = {"collected_at": int(time.time()), "instances": list(items)}
        return self.snapshot

    async def loop(self):
        while True:
            try:
                await self.run_once()
            except Exception:
                pass
            await asyncio.sleep(self.interval)
