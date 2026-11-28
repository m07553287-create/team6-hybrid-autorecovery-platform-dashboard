"""로컬 캡처 서버 + Chrome Headless CDP로 figteam #cfg 실화면 6종 및 요소 좌표(coords.json) 캡처."""
import asyncio
import base64
import json
import os
import pathlib
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request

import fakeredis
import uvicorn
import websockets

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "content"))

from tools import seed_wiki  # noqa: E402
from wiki.app import create_app  # noqa: E402

CHROME_BIN = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
OUT_DIR = ROOT / "public" / "manual" / "screens"
VW, VH = 1440, 900


def free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def start_server(port):
    r = fakeredis.FakeRedis(decode_responses=True)
    seed_wiki.seed(r, "figteam", "figteam (team6)", "demo1234")
    os.environ["AUTO_LOGIN_TEAM"] = "figteam"
    os.environ["SERVE_STATIC"] = str(ROOT / "public")
    os.environ["ALLOWED_ORIGIN"] = f"http://127.0.0.1:{port}"
    app = create_app(redis_client=r)

    @app.get("/console/api/me")
    def _console_me():
        return {"unlocked": True}

    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)
    t = threading.Thread(target=server.run, daemon=True)
    t.start()
    for _ in range(50):
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/health", timeout=0.5) as resp:
                if resp.status == 200:
                    return server
        except Exception:
            time.sleep(0.1)
    raise RuntimeError("Capture server did not start")


class CDP:
    def __init__(self, ws):
        self.ws = ws
        self.seq = 0

    async def call(self, method, params=None):
        self.seq += 1
        cid = self.seq
        await self.ws.send(json.dumps({"id": cid, "method": method, "params": params or {}}))
        while True:
            raw = await self.ws.recv()
            msg = json.loads(raw)
            if msg.get("id") == cid:
                if "error" in msg:
                    raise RuntimeError(f"CDP {method} error: {msg['error']}")
                return msg.get("result", {})

    async def eval(self, expr):
        res = await self.call("Runtime.evaluate", {
            "expression": expr,
            "awaitPromise": True,
            "returnByValue": True,
        })
        if "exceptionDetails" in res:
            raise RuntimeError(f"JS error: {res['exceptionDetails']}")
        return res.get("result", {}).get("value")

    async def shot(self, filename):
        res = await self.call("Page.captureScreenshot", {"format": "png", "fromSurface": True})
        data = base64.b64decode(res["data"])
        (OUT_DIR / filename).write_bytes(data)
        print(f"saved {filename} ({len(data)} bytes)")


async def measure(cdp, specs):
    expr = f"""(() => {{
      const vw = {VW}, vh = {VH};
      const specs = {json.dumps(specs, ensure_ascii=False)};
      return specs.map(s => {{
        const el = document.querySelector(s.selector);
        if (!el) return {{ id: s.id, selector: s.selector, found: false }};
        const r = el.getBoundingClientRect();
        const x = Math.max(0, r.left), y = Math.max(0, r.top);
        const right = Math.min(vw, r.right), bottom = Math.min(vh, r.bottom);
        const w = Math.max(0, right - x), h = Math.max(0, bottom - y);
        const px = Math.min(97.5, Math.max(2.5, ((x + w / 2) / vw) * 100));
        const py = Math.min(97.5, Math.max(2.5, ((y + h / 2) / vh) * 100));
        return {{
          id: s.id,
          selector: s.selector,
          found: w > 0 && h > 0,
          box: {{
            left: Number(((x / vw) * 100).toFixed(2)),
            top: Number(((y / vh) * 100).toFixed(2)),
            width: Number(((w / vw) * 100).toFixed(2)),
            height: Number(((h / vh) * 100).toFixed(2)),
          }},
          pin: {{
            x: s.pinX !== undefined ? s.pinX : Number(px.toFixed(2)),
            y: s.pinY !== undefined ? s.pinY : Number(py.toFixed(2)),
          }}
        }};
      }});
    }})()"""
    items = await cdp.eval(expr)
    for it in items:
        if not it.get("found"):
            raise RuntimeError(f"Element not visible/found: {it['selector']}")
    return items


async def wait_ready(cdp, expr_cond, timeout=8.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if await cdp.eval(expr_cond):
            await asyncio.sleep(0.35)
            return
        await asyncio.sleep(0.15)
    raise RuntimeError(f"Condition timeout: {expr_cond}")


async def run_capture(base_url, cdp_port):
    ws_url = None
    for _ in range(40):
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{cdp_port}/json/list", timeout=1.0) as resp:
                pages = json.loads(resp.read().decode())
                pg = next((p for p in pages if p.get("type") == "page"), None)
                if pg and pg.get("webSocketDebuggerUrl"):
                    ws_url = pg["webSocketDebuggerUrl"]
                    break
        except Exception:
            await asyncio.sleep(0.15)
    if not ws_url:
        raise RuntimeError("Could not connect to Chrome DevTools")

    coords = {}
    async with websockets.connect(ws_url, max_size=50 * 1024 * 1024) as ws:
        cdp = CDP(ws)
        await cdp.call("Page.enable")
        await cdp.call("Runtime.enable")
        await cdp.call("Emulation.setDeviceMetricsOverride", {
            "width": VW, "height": VH, "deviceScaleFactor": 2, "mobile": False
        })

        # Seed session storage & navigate to #cfg/inst
        await cdp.call("Page.navigate", {"url": f"{base_url}/#cfg/inst"})
        await wait_ready(cdp, "document.readyState === 'complete'")
        await cdp.eval("""(async () => {
          sessionStorage.setItem('figteam_auth_token', 'valid');
          localStorage.setItem('fig.view', 'settings');
          if (typeof checkAuth === 'function') checkAuth();
          if (typeof switchView === 'function') switchView('settings');
          if (document.fonts && document.fonts.ready) await document.fonts.ready;
        })()""")
        await wait_ready(cdp, "Boolean(typeof WIKI !== 'undefined' && WIKI.ready && document.querySelector('.cfg-tree-nav .cfg-tree-major'))")

        # 1. 01-overview-nav.png
        coords["01-overview-nav.png"] = await measure(cdp, [
            {"id": 1, "selector": "#btn-tab-settings"},
            {"id": 2, "selector": ".cfg-lens"},
            {"id": 3, "selector": ".cfg-tree-nav"},
            {"id": 4, "selector": ".cfg-crumb"},
        ])
        await cdp.shot("01-overview-nav.png")

        # 2. 02-area-builder.png — navigate to controller 'net' or 'svc' area (commands rich) and scroll to commands section
        await cdp.eval("""(() => {
          const inst = (CFG.data.instances || []).find(pid => cfgPage(pid).short === 'controller') || CFG.data.instances[0];
          const p = cfgPage(inst);
          const area = p.areas.find(a => (a.commands || []).length >= 2) || p.areas[0];
          cfgSelect('inst', inst, area.id);
          const body = document.getElementById('manual-body-content');
          const sec2 = document.getElementById('cfg-sec-2');
          if (body && sec2) body.scrollTop = Math.max(0, sec2.offsetTop - 90);
        })()""")
        await wait_ready(cdp, "Boolean(document.querySelector('#cfg-sec-2 .cfg-card-bar') && document.querySelector('#cfg-sec-2 .cfg-code-actions'))")
        coords["02-area-builder.png"] = await measure(cdp, [
            {"id": 1, "selector": "#cfg-sec-2 .cfg-btn-add"},
            {"id": 2, "selector": "#cfg-sec-2 .cfg-card-bar"},
            {"id": 3, "selector": "#cfg-sec-2 .cfg-code-actions"},
            {"id": 4, "selector": ".cfg-crumb"},
        ])
        await cdp.shot("02-area-builder.png")

        # 3. 03-terminal-safety.png — click danger button on config or command to show red warning modal
        await cdp.eval("""(() => {
          const body = document.getElementById('manual-body-content');
          if (body) body.scrollTop = 0;
          const cfgSec = document.querySelector('#cfg-sec-1 .cfg-run-danger') || document.querySelector('.cfg-run-danger');
          if (cfgSec) cfgSec.click();
        })()""")
        await wait_ready(cdp, "Boolean(document.querySelector('#cfg-edit-modal .cfg-modal-card, #cfg-confirm-modal .cfg-modal-card'))")
        modal_sel = "#cfg-edit-modal" if await cdp.eval("Boolean(document.querySelector('#cfg-edit-modal'))") else "#cfg-confirm-modal"
        coords["03-terminal-safety.png"] = await measure(cdp, [
            {"id": 1, "selector": f"{modal_sel} .cfg-modal-head"},
            {"id": 2, "selector": f"{modal_sel} .cfg-modal-alert"},
            {"id": 3, "selector": f"{modal_sel} .cfg-modal-code"},
            {"id": 4, "selector": f"{modal_sel} .cfg-btn-confirm"},
        ])
        await cdp.shot("03-terminal-safety.png")
        await cdp.eval("document.querySelector('#cfg-edit-modal, #cfg-confirm-modal')?.remove()")

        # 4. 04-guide-studio.png — open guide studio and load example into preview
        await cdp.eval("""(() => {
          cfgGuideOpen({ action: 'patch', kind: 'area' });
          cfgGuideUseExampleObj(null);
        })()""")
        await wait_ready(cdp, "Boolean(document.querySelector('#cfg-guide-modal .cfg-guide-op-card.ok'))")
        coords["04-guide-studio.png"] = await measure(cdp, [
            {"id": 1, "selector": "#cfg-guide-modal .cfg-guide-toolbar"},
            {"id": 2, "selector": "#cfg-guide-modal .cfg-guide-left-acts"},
            {"id": 3, "selector": "#cfg-guide-input"},
            {"id": 4, "selector": "#cfg-guide-apply"},
        ])
        await cdp.shot("04-guide-studio.png")
        await cdp.eval("document.querySelector('#cfg-guide-modal')?.remove()")

        # 5. 05-wiki-editor.png — open wiki editor on current area and expand inline guide helper
        await cdp.eval("""(() => {
          const cur = cfgCurrentArea();
          const docId = cur && cur.area ? cur.area.docId : null;
          if (docId) wikiEdit(docId);
          const det = document.getElementById('cfg-guide-inline');
          if (det) det.open = true;
          const body = document.getElementById('manual-body-content');
          if (body) body.scrollTop = 0;
        })()""")
        await wait_ready(cdp, "Boolean(document.querySelector('#cfg-guide-inline[open] .cfg-guide-inline-foot'))")
        coords["05-wiki-editor.png"] = await measure(cdp, [
            {"id": 1, "selector": "#cfg-guide-inline > summary"},
            {"id": 2, "selector": ".cfg-guide-inline-acts"},
            {"id": 3, "selector": "#cfg-guide-inline-input"},
            {"id": 4, "selector": ".cfg-guide-inline-foot"},
        ])
        await cdp.shot("05-wiki-editor.png")

        # 6. 06-steps-and-zoom.png — step view S0
        await cdp.eval("cfgSelect('step', 'all', 'S0')")
        await wait_ready(cdp, "Boolean(CFG.lens === 'step' && document.querySelector('.cfg-tree-minor.active') && document.querySelector('.wk-acts'))")
        coords["06-steps-and-zoom.png"] = await measure(cdp, [
            {"id": 1, "selector": ".cfg-lens-btn.active"},
            {"id": 2, "selector": ".cfg-tree-minor.active"},
            {"id": 3, "selector": ".wk-acts"},
            {"id": 4, "selector": ".cfg-code"},
        ])
        await cdp.shot("06-steps-and-zoom.png")

    (OUT_DIR / "coords.json").write_text(json.dumps(coords, indent=2, ensure_ascii=False), encoding="utf-8")
    print("wrote", OUT_DIR / "coords.json")


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    port = free_port()
    cdp_port = free_port()
    server = start_server(port)
    tmp_profile = tempfile.mkdtemp(prefix="fig-chrome-")
    proc = subprocess.Popen(
        [
            CHROME_BIN,
            "--headless=new",
            "--disable-gpu",
            "--no-first-run",
            "--no-default-browser-check",
            "--hide-scrollbars",
            f"--remote-debugging-port={cdp_port}",
            f"--user-data-dir={tmp_profile}",
            f"--window-size={VW},{VH}",
            "about:blank",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        asyncio.run(run_capture(f"http://127.0.0.1:{port}", cdp_port))
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            proc.kill()
        shutil.rmtree(tmp_profile, ignore_errors=True)
        server.should_exit = True


if __name__ == "__main__":
    main()
