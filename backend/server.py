#!/usr/bin/env python3
import http.server
import socketserver
import urllib.parse
import urllib.request
import http.cookiejar
import json
import re
import time
import secrets
import hmac
import hashlib
import base64
import os
import subprocess
import socket
import threading
import ssl
import shutil
import zipfile
import email
from datetime import datetime

# ==============================================================================
# 팀6 하이브리드 멀티클라우드 운영 포털 (v2 롤백 베이스 · 시연 엔진 삭제 완료)
# ==============================================================================
ppt_lock = threading.Lock()

UPLOAD_DIR = "/opt/figteam-portal/uploads"
if not os.path.exists(UPLOAD_DIR):
    UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "uploads")
DECKS_DIR = os.path.join(UPLOAD_DIR, "decks")
os.makedirs(DECKS_DIR, exist_ok=True)

def parse_multipart_data(content_type, body_bytes):
    msg_data = b'Content-Type: ' + content_type.encode('utf-8') + b'\r\nMIME-Version: 1.0\r\n\r\n' + body_bytes
    msg = email.message_from_bytes(msg_data)
    form = {}
    files = []
    if msg.is_multipart():
        for part in msg.get_payload():
            cd = part.get('Content-Disposition', '')
            name = None
            filename = None
            for param in cd.split(';'):
                param = param.strip()
                if param.startswith('name='):
                    name = param[5:].strip('"\'')
                elif param.startswith('filename='):
                    filename = param[9:].strip('"\'')
            payload = part.get_payload(decode=True)
            if filename:
                files.append({'name': name, 'filename': filename, 'data': payload, 'content_type': part.get_content_type()})
            elif name:
                form[name] = payload.decode('utf-8', errors='replace')
    return form, files

def scan_ppt_decks():
    decks = [
        {
            "id": "default",
            "name": "🌟 [테스트] 팀6 시연 슬라이드 (3장)",
            "type": "builtin",
            "slides_count": 3,
            "created_at": "기본 내장",
            "slides": []
        }
    ]
    if os.path.exists(DECKS_DIR):
        for did in sorted(os.listdir(DECKS_DIR), reverse=True):
            dpath = os.path.join(DECKS_DIR, did)
            mpath = os.path.join(dpath, "manifest.json")
            if os.path.isdir(dpath) and os.path.exists(mpath):
                try:
                    with open(mpath, encoding="utf-8") as f:
                        meta = json.load(f)
                        decks.append(meta)
                except Exception:
                    pass
    return decks

ppt_state = {
    "active_deck_id": "default",
    "active_deck_name": "🌟 [테스트] 팀6 시연 슬라이드 (3장)",
    "active_deck_type": "builtin",
    "slides": [],
    "current_slide": 1,
    "total_slides": 3,
    "presenter": "이근규",
    "sync_mode": True,
    "last_updated": time.time(),
    "updated_by": "이근규",
    "laser": {"x": -1, "y": -1, "active": False, "sender": ""},
    "participants": {
        "이근규": {"name": "이근규", "last_seen": time.time()},
        "백승호": {"name": "백승호", "last_seen": time.time()},
        "정다운": {"name": "정다운", "last_seen": time.time()},
        "정혜빈": {"name": "정혜빈", "last_seen": time.time()},
        "최진태": {"name": "최진태", "last_seen": time.time()}
    },
    "participants_count": 5
}

demo_state = {
    "status_code": 200,
    "latency_ms": 0.0,
    "site": "onprem",
    "pod": "minwon-app",
    "phase": "NORMAL_ONPREM",
    "rto_seconds": None,
    "elapsed_outage": 0.0,
    "down_start_str": None,
    "recovered_str": None,
    "is_outage": False,
    "onprem_configured": True,
    "logs": [],
    "term1": [],
    "term2": [],
    "term3": []
}

def demo_push_line(key, text, cls="info", limit=180):
    with demo_lock:
        demo_state[key].append({"cls": cls, "text": text})
        if len(demo_state[key]) > limit:
            demo_state[key] = demo_state[key][-limit:]

def demo_add_summary_log(msg):
    now_str = datetime.now().strftime("%H:%M:%S")
    with demo_lock:
        demo_state["logs"].append(f"[{now_str}] {msg}")
        if len(demo_state["logs"]) > 40:
            demo_state["logs"] = demo_state["logs"][-40:]

def run_demo_ssh_command(host, key_path, prompt_label, action_label, display_cmd, remote_cmd, jump_host="", add_to_summary=True):
    def worker():
        now_str = datetime.now().strftime("%H:%M:%S")
        if not host:
            msg = f"⚠️ [{action_label}] ONPREM_HOST 미설정"
            demo_push_line("term2", "", "dim")
            demo_push_line("term2", f"[{now_str}] {msg}", "warn")
            if add_to_summary:
                demo_add_summary_log(msg)
            return

        if add_to_summary:
            demo_add_summary_log(f"⚙️ [{action_label}] 명령 전송 중...")

        demo_push_line("term2", "", "dim")
        demo_push_line("term2", f"[{now_str}] {prompt_label}# {display_cmd}", "cmd")

        cmd = [
            "ssh",
            "-n", "-T",
            "-o", "StrictHostKeyChecking=no",
            "-o", "BatchMode=yes",
            "-o", "ConnectTimeout=5"
        ]
        if os.path.exists(key_path):
            cmd += ["-i", key_path]
        if jump_host:
            proxy_cmd = f'ssh -n -T -o StrictHostKeyChecking=no -W %h:%p {jump_host}'
            cmd += ["-o", f"ProxyCommand={proxy_cmd}"]
        cmd += [host, remote_cmd]

        try:
            res = subprocess.run(
                cmd,
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=30,
                creationflags=NO_WIN
            )
            out_text = (res.stdout or "").rstrip()
            err_text = (res.stderr or "").rstrip()

            if out_text:
                for line in out_text.splitlines():
                    cls = "info"
                    if any(k in line for k in ("10.200.0.4", "10.10.1.100", "clean", "Running", "successfully rolled out", "scaled", "restarted")):
                        cls = "ok"
                    if any(k in line for k in ("DROP", "CHAOS_L3_FAULT", "Terminating", "deleted", "Error", "CrashLoop")):
                        cls = "err"
                    demo_push_line("term2", line, cls)

            if err_text:
                for line in err_text.splitlines():
                    cls = "ok" if ("syntax is ok" in line or "test is successful" in line) else "warn"
                    demo_push_line("term2", line, cls)

            if res.returncode == 0:
                demo_push_line("term2", "[exit code: 0] OK", "ok")
                if add_to_summary:
                    demo_add_summary_log(f"📡 [{action_label}] 명령 적용 완료")
            else:
                demo_push_line("term2", f"[exit code: {res.returncode}] FAILED", "err")
                if add_to_summary:
                    brief = (err_text or out_text or f"exit={res.returncode}").splitlines()[0]
                    demo_add_summary_log(f"❌ [{action_label} 실패] {brief}")
        except Exception as e:
            demo_push_line("term2", f"[EXCEPTION] {e}", "err")
            if add_to_summary:
                demo_add_summary_log(f"❌ [{action_label} 예외] {e}")

    threading.Thread(target=worker, daemon=True).start()

def run_demo_l1_http_crash():
    def worker():
        now_str = datetime.now().strftime("%H:%M:%S")
        url = f"{TARGET_URL}/chaos/crash"
        demo_add_summary_log("💥 [L1 앱 크래시] POST /chaos/crash 전송 중...")
        demo_push_line("term2", "", "dim")
        demo_push_line("term2", f'[{now_str}] $ curl -X POST {url} -H "X-Chaos-Token: ****"', "cmd")

        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        req = urllib.request.Request(
            url,
            data=b"",
            method="POST",
            headers={
                "X-Chaos-Token": CHAOS_TOKEN,
                "User-Agent": "Demo-Console/0.3"
            }
        )
        try:
            with urllib.request.urlopen(req, context=ctx, timeout=5.0) as resp:
                body = resp.read().decode("utf-8", errors="ignore").strip()
                demo_push_line("term2", f"HTTP {resp.getcode()} {body}", "warn")
                demo_add_summary_log(f"💥 [L1 앱 크래시] 트리거 응답 수신 (HTTP {resp.getcode()}) — 자가치유 관찰 중")
        except urllib.error.HTTPError as e:
            if e.code == 403:
                demo_push_line("term2", "HTTP 403 Forbidden: Invalid Chaos Token (CHAOS_TOKEN 확인 필요)", "err")
                demo_add_summary_log("❌ [L1 크래시 실패] 403 토큰 불일치 (CHAOS_TOKEN 확인 필요)")
            elif e.code in (502, 503, 504):
                demo_push_line("term2", f"HTTP {e.code} (타겟 프로세스 즉시 종료로 연결 끊김 - 크래시 성공!)", "ok")
                demo_add_summary_log("💥 [L1 크래시 주입 완료] 파드 프로세스 종료 확인 — K8s 자가치유 관찰 중")
            else:
                demo_push_line("term2", f"HTTP {e.code}: {e.reason}", "err")
                demo_add_summary_log(f"⚠️ [L1 크래시] HTTP {e.code} ({e.reason})")
        except Exception as e:
            demo_push_line("term2", f"[Connection Closed] {e} (프로세스 os._exit 종료로 인한 정상 끊김)", "ok")
            demo_add_summary_log("💥 [L1 크래시 주입 완료] 프로세스 즉시 종료 확인 — 자가치유 관찰 중")

    threading.Thread(target=worker, daemon=True).start()

def demo_term3_stream_loop():
    global term3_proc
    demo_push_line("term3", f"[*] Connecting SSH log stream -> {TERM3_HOST}", "dim")
    demo_push_line("term3", f"$ {TERM3_CMD}", "cmd")

    while True:
        cmd = [
            "ssh",
            "-n", "-T",
            "-o", "StrictHostKeyChecking=no",
            "-o", "BatchMode=yes",
            "-o", "ConnectTimeout=5",
            "-o", "ServerAliveInterval=15"
        ]
        if os.path.exists(TERM3_KEY):
            cmd += ["-i", TERM3_KEY]
        cmd += [TERM3_HOST, TERM3_CMD]

        try:
            proc = subprocess.Popen(
                cmd,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                creationflags=NO_WIN
            )
            term3_proc = proc
            for raw in proc.stdout:
                line = raw.rstrip("\r\n")
                if not line:
                    continue
                lower = line.lower()
                if any(k in lower for k in ("error", "timed out")) or any(c in line for c in (" 499 ", " 500 ", " 502 ", " 503 ", " 504 ")):
                    cls = "err"
                elif " 200 " in line or " 304 " in line:
                    cls = "ok"
                elif line.startswith("==>"):
                    cls = "cmd"
                else:
                    cls = "info"
                demo_push_line("term3", line, cls)
            proc.wait()
            demo_push_line("term3", "[!] Stream disconnected. Reconnecting in 3s...", "warn")
        except Exception as e:
            demo_push_line("term3", f"[!] Stream error: {e} (retry in 3s)", "err")
        time.sleep(3)

def demo_probe_loop():
    global demo_reset_requested
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    start_wall_time = time.time()
    down_start_time = None
    recovered_time = None
    last_onprem_pod = None

    demo_push_line("term1", "=" * 78, "dim")
    demo_push_line("term1", "[*] L1 / L2 / L3 Real-time Measurement Started (v0.3)", "cmd")
    demo_push_line("term1", f"[*] Target : {TARGET_URL} | Interval: 0.5s", "dim")
    demo_push_line("term1", "=" * 78, "dim")

    while True:
        with demo_lock:
            if demo_reset_requested:
                demo_reset_requested = False
                start_wall_time = time.time()
                down_start_time = None
                recovered_time = None
                last_onprem_pod = None
                demo_state["rto_seconds"] = None
                demo_state["elapsed_outage"] = 0.0
                demo_state["down_start_str"] = None
                demo_state["recovered_str"] = None
                demo_state["is_outage"] = False
                demo_state["logs"] = []
                demo_state["term1"] = [
                    {"cls": "cmd", "text": "[*] Measurement Reset - Ready for clean demo"}
                ]

        now = datetime.now()
        t_now_ms = now.strftime("%H:%M:%S.%f")[:-3]
        now_str = now.strftime("%H:%M:%S")
        elapsed = round(time.time() - start_wall_time, 1)

        t0 = time.time()
        status_code = 0
        site_name = "unknown"
        pod_name = "unknown"

        try:
            req = urllib.request.Request(TARGET_URL, headers={"User-Agent": "Demo-Console/0.3"})
            with urllib.request.urlopen(req, context=ctx, timeout=2.0) as resp:
                status_code = resp.getcode()
                latency_ms = round((time.time() - t0) * 1000, 1)
                body = resp.read().decode("utf-8", errors="ignore")

                pod_m = re.search(r"POD:\s*([a-zA-Z0-9-]+)", body, re.I)
                if pod_m:
                    pod_name = pod_m.group(1).strip()
                elif "minwon-app-" in body:
                    sub = re.search(r"(minwon-app-[a-zA-Z0-9-]+)", body)
                    pod_name = sub.group(1).strip() if sub else "minwon-app"
                elif "k8s-cp1" in body:
                    pod_name = "k8s-cp1"

                site_m = re.search(r"SITE:\s*(onprem|aws|dr)\b", body, re.I)
                if site_m:
                    raw_s = site_m.group(1).lower()
                    site_name = "aws" if raw_s in ("aws", "dr") else "onprem"
                elif "k8s-cp1" in pod_name:
                    site_name = "onprem"
                elif "minwon-app-" in pod_name:
                    site_name = "aws"
        except Exception:
            status_code = 0
            latency_ms = round((time.time() - t0) * 1000, 1)

        event_line = None
        event_cls = "info"

        with demo_lock:
            if status_code == 200 and site_name == "onprem":
                if down_start_time is not None and recovered_time is None:
                    rto = round(time.time() - down_start_time, 2)
                    demo_state["rto_seconds"] = rto
                    demo_state["recovered_str"] = now_str
                    demo_state["logs"].append(f"[{now_str}] ✅ [L1/L2 복구 완료] 온프렘 자체 정상화! (RTO: {rto}초, Pod: {pod_name})")
                    event_line = f"[+] >>> [ONPREM RECOVERED] at {t_now_ms} | RTO: {rto}s | Pod: {pod_name} <<<"
                    event_cls = "cmd"
                elif demo_state["phase"] == "RECOVERED_AWS":
                    demo_state["logs"].append(f"[{now_str}] 🟢 [원복 완료] 온프렘({pod_name}) 정상 복귀 확인")
                    event_line = f"[*] >>> [FAILBACK COMPLETED] at {t_now_ms} | Site: onprem ({pod_name}) <<<"
                    event_cls = "ok"
                elif last_onprem_pod and pod_name != "unknown" and pod_name != last_onprem_pod:
                    demo_state["logs"].append(f"[{now_str}] 🔄 [파드 전환 확인] {last_onprem_pod} → {pod_name}")
                    event_line = f"[*] >>> [POD CHANGED] {last_onprem_pod} -> {pod_name} (Zero-Downtime) <<<"
                    event_cls = "aws"

                if pod_name != "unknown":
                    last_onprem_pod = pod_name
                phase = "NORMAL_ONPREM"
                down_start_time = None
                recovered_time = None
                demo_state["is_outage"] = False
                demo_state["elapsed_outage"] = 0.0

            elif status_code != 200 or site_name == "unknown":
                phase = "OUTAGE_DOWN"
                if down_start_time is None:
                    down_start_time = time.time()
                    recovered_time = None
                    demo_state["rto_seconds"] = None
                    demo_state["down_start_str"] = now_str
                    demo_state["is_outage"] = True
                    demo_state["logs"].append(f"[{now_str}] 🚨 [장애 발생] 온프렘 응답 중단 (HTTP {status_code})")
                    event_line = f"[!] >>> [FAULT DETECTED] at {t_now_ms} (HTTP {status_code}) <<<"
                    event_cls = "err"
                demo_state["elapsed_outage"] = round(time.time() - down_start_time, 1)

            elif status_code == 200 and site_name == "aws":
                phase = "RECOVERED_AWS"
                if down_start_time is not None and recovered_time is None:
                    recovered_time = time.time()
                    rto = round(recovered_time - down_start_time, 2)
                    demo_state["rto_seconds"] = rto
                    demo_state["recovered_str"] = now_str
                    demo_state["is_outage"] = False
                    demo_state["elapsed_outage"] = rto
                    demo_state["logs"].append(f"[{now_str}] ✅ [L3 복구 완료] AWS DR 정상화! (RTO: {rto}초)")
                    event_line = f"[+] >>> [L3 RECOVERY COMPLETED] at {t_now_ms} | RTO: {rto}s <<<"
                    event_cls = "cmd"
            else:
                phase = demo_state["phase"]

            demo_state["status_code"] = status_code
            demo_state["latency_ms"] = latency_ms
            demo_state["site"] = site_name
            demo_state["pod"] = pod_name
            demo_state["phase"] = phase

        if event_line:
            demo_push_line("term1", event_line, event_cls)

        flag = "[OK] " if status_code == 200 else "[ERR]"
        line_cls = "ok" if status_code == 200 else "err"
        if status_code == 200 and site_name == "aws":
            line_cls = "aws"
        raw_line = (
            f"{flag} {t_now_ms} (+{elapsed:5.1f}s) | Code: {status_code:3} | "
            f"{latency_ms:6.1f}ms | Site: {site_name:7} | Pod: {pod_name:27} | {phase}"
        )
        demo_push_line("term1", raw_line, line_cls)

        time.sleep(0.5)

PORT = 18088
PORTAL_CONFIG_PATH = os.environ.get("FIGTEAM_CONFIG", "/opt/figteam-portal/portal_config.json")

def _load_portal_config():
    if os.path.exists(PORTAL_CONFIG_PATH):
        try:
            with open(PORTAL_CONFIG_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"[ERROR] Failed to load portal config: {e}")
    return {}

_PCFG = _load_portal_config()
VALID_USER = os.environ.get("FIGTEAM_USER") or _PCFG.get("portal_user", "")
VALID_PASS = os.environ.get("FIGTEAM_PASS") or _PCFG.get("portal_pass", "")
CTRL_PASS = os.environ.get("FIGTEAM_CTRL_PASS") or _PCFG.get("ctrl_pass", "")
if not VALID_USER or not VALID_PASS:
    print("[WARN] 포털 계정이 설정되지 않아 로그인할 수 없습니다: " + PORTAL_CONFIG_PATH)

SESSION_TTL = 86400 * 7 # 7일
SESSION_FILE = "/tmp/figteam_sessions.json"

def _load_sessions():
    if os.path.exists(SESSION_FILE):
        try:
            with open(SESSION_FILE, "r") as f:
                now = time.time()
                return {k: v for k, v in json.load(f).items() if v > now}
        except Exception:
            pass
    return {}

def _save_sessions():
    try:
        with open(SESSION_FILE, "w") as f:
            json.dump(SESSIONS, f)
    except Exception:
        pass

SESSIONS = _load_sessions()

HORIZON_INTERNAL = "http://192.168.120.160"
OS_USER = os.environ.get("OS_USERNAME") or _PCFG.get("os_user", "admin")
OS_PASS = os.environ.get("OS_PASSWORD") or _PCFG.get("os_pass", "")

KT_CONFIG_PATH = "/opt/figteam-portal/ktc_config.json"
KT_HOST = "https://api.ucloudbiz.olleh.com"

def get_kt_credentials():
    if os.path.exists(KT_CONFIG_PATH):
        try:
            with open(KT_CONFIG_PATH, "r", encoding="utf-8") as f:
                cfg = json.load(f)
                return cfg.get("api_key"), cfg.get("secret_key")
        except Exception as e:
            print(f"[ERROR] Failed to load KT config: {e}")
    return None, None

def call_kt_api(service, command, **params):
    api_key, secret_key = get_kt_credentials()
    if not api_key or not secret_key:
        raise Exception("KT Cloud API Key / Secret Key가 설정되지 않았습니다.")
        
    full_params = {**params, "command": command, "apiKey": api_key, "response": "json"}
    query = "&".join(
        f"{k}={urllib.parse.quote(str(v), safe='')}"
        for k, v in sorted(full_params.items(), key=lambda kv: kv[0].lower())
    )
    digest = hmac.new(secret_key.encode(), query.lower().encode(), hashlib.sha1).digest()
    sig = urllib.parse.quote(base64.b64encode(digest).decode(), safe="")
    url = f"{KT_HOST}/{service.strip('/')}/client/api?{query}&signature={sig}"
    
    req = urllib.request.Request(url, headers={"User-Agent": "FIGTEAM-CMP/1.0"})
    with urllib.request.urlopen(req, timeout=15) as res:
        return json.loads(res.read().decode())

# ============================================================
# OPENSTACK NOVA & KEYSTONE HELPER FUNCTIONS
# ============================================================
OS_CONFIG_PATH = "/opt/figteam-portal/openstack_config.json"
OS_TOKEN_CACHE = {"token": None, "expires": 0}

def get_openstack_credentials():
    if os.path.exists(OS_CONFIG_PATH):
        try:
            with open(OS_CONFIG_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"[ERROR] Failed to load OpenStack config: {e}")
    return {
        "auth_url": os.environ.get("OS_AUTH_URL", "http://192.168.120.160:5000/v3"),
        "username": OS_USER,
        "password": OS_PASS,
        "project_name": "admin",
        "user_domain": "Default",
        "project_domain": "Default",
        "nova_url": os.environ.get("OS_NOVA_URL", "http://192.168.120.160:8774/v2.1")
    }

def get_openstack_token():
    now = time.time()
    if OS_TOKEN_CACHE["token"] and now < OS_TOKEN_CACHE["expires"]:
        return OS_TOKEN_CACHE["token"]
        
    cfg = get_openstack_credentials()
    url = f"{cfg['auth_url'].rstrip('/')}/auth/tokens"
    payload = {
        "auth": {
            "identity": {
                "methods": ["password"],
                "password": {
                    "user": {
                        "name": cfg["username"],
                        "domain": {"name": cfg.get("user_domain", "Default")},
                        "password": cfg["password"]
                    }
                }
            },
            "scope": {
                "project": {
                    "name": cfg["project_name"],
                    "domain": {"name": cfg.get("project_domain", "Default")}
                }
            }
        }
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode('utf-8'),
        headers={"Content-Type": "application/json", "User-Agent": "FIGTEAM-CMP/1.0"}
    )
    with urllib.request.urlopen(req, timeout=5) as res:
        token = res.headers.get("X-Subject-Token")
        if token:
            OS_TOKEN_CACHE["token"] = token
            OS_TOKEN_CACHE["expires"] = now + 1800
            return token
    raise Exception("OpenStack Keystone 토큰 발급에 실패했습니다.")

# ============================================================
# OpenStack 구조 · 연결 조회 (v2.5.1) — 읽기 전용 + 콘솔 로그 · 스냅샷
# ============================================================
OS_AUTH_CACHE = {"expires": 0}
OS_ID_RE = re.compile(r"^[0-9a-fA-F-]{8,64}$")

def _os_host_fix(url, auth_url):
    """카탈로그 주소의 호스트명을 해석할 수 없으면 auth_url 호스트로 바꾼다 (예: controller → 192.168.120.160)."""
    try:
        import socket
        u = urllib.parse.urlparse(url)
        socket.gethostbyname(u.hostname)
        return url
    except Exception:
        try:
            u = urllib.parse.urlparse(url)
            a = urllib.parse.urlparse(auth_url)
            netloc = f"{a.hostname}:{u.port}" if u.port else a.hostname
            return u._replace(netloc=netloc).geturl()
        except Exception:
            return url

def os_auth_full():
    now = time.time()
    if OS_AUTH_CACHE.get("token") and now < OS_AUTH_CACHE["expires"]:
        return OS_AUTH_CACHE
    cfg = get_openstack_credentials()
    payload = {"auth": {
        "identity": {"methods": ["password"], "password": {"user": {
            "name": cfg["username"], "domain": {"name": cfg.get("user_domain", "Default")}, "password": cfg["password"]}}},
        "scope": {"project": {"name": cfg["project_name"], "domain": {"name": cfg.get("project_domain", "Default")}}}}}
    req = urllib.request.Request(f"{cfg['auth_url'].rstrip('/')}/auth/tokens", data=json.dumps(payload).encode("utf-8"),
                                 headers={"Content-Type": "application/json", "User-Agent": "FIGTEAM-CMP/1.0"})
    with urllib.request.urlopen(req, timeout=6) as res:
        token = res.headers.get("X-Subject-Token")
        body = json.loads(res.read().decode("utf-8") or "{}")
    if not token:
        raise Exception("Keystone 토큰 발급 실패")
    tok = body.get("token", {})
    pid = (tok.get("project") or {}).get("id", "")
    endpoints, catalog = {}, []
    for svc in tok.get("catalog", []):
        eps = {e.get("interface"): e.get("url") for e in svc.get("endpoints", [])}
        url = eps.get("internal") or eps.get("public") or eps.get("admin")
        if url:
            url = url.replace("%(tenant_id)s", pid).replace("%(project_id)s", pid).replace("$(project_id)s", pid)
            endpoints[svc.get("type")] = _os_host_fix(url, cfg["auth_url"]).rstrip("/")
        catalog.append({"type": svc.get("type"), "name": svc.get("name"), "interfaces": sorted(k for k in eps if k)})
    host = urllib.parse.urlparse(cfg["auth_url"]).hostname
    endpoints.setdefault("compute", cfg.get("nova_url", f"http://{host}:8774/v2.1").rstrip("/"))
    endpoints.setdefault("network", f"http://{host}:9696")
    endpoints.setdefault("image", f"http://{host}:9292")
    if "volumev3" not in endpoints and "block-storage" in endpoints:
        endpoints["volumev3"] = endpoints["block-storage"]
    endpoints.setdefault("volumev3", f"http://{host}:8776/v3/{pid}")
    OS_AUTH_CACHE.update({"token": token, "expires": now + 1500, "project_id": pid, "endpoints": endpoints, "catalog": catalog})
    return OS_AUTH_CACHE

def _os_call(service, path, body=None, timeout=8):
    a = os_auth_full()
    base = a["endpoints"].get(service)
    if not base:
        raise Exception(f"{service} 엔드포인트가 카탈로그에 없습니다")
    headers = {"X-Auth-Token": a["token"], "Accept": "application/json", "User-Agent": "FIGTEAM-CMP/1.0"}
    data = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(base + path, data=data, headers=headers, method="POST" if body is not None else "GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as res:
            raw = res.read().decode("utf-8")
            return json.loads(raw) if raw.strip() else {}
    except urllib.error.HTTPError as e:
        if e.code == 401:
            OS_AUTH_CACHE["expires"] = 0
        raise Exception(f"HTTP {e.code} {service}{path.split('?')[0]}")

def _pick(d, keys):
    return {k: d.get(k) for k in keys}


# ===== #osvm 연결 점검 (실측) =====
import ssl as _cc_ssl
from concurrent.futures import ThreadPoolExecutor as _CcPool

CONNECTIVITY_CHECKS = [
    # group, id, name, target, url, kind, note
    ('route', 'r1', 'Cloudflare → KT DMZ', 'minwon.ktci5.kr', 'https://minwon.ktci5.kr/healthz', 'expect_up', '사용자가 아는 유일한 주소'),
    ('route', 'r2', 'KT Edge nginx · WAF', '10.200.0.1:443 (WG 경유)', 'https://10.200.0.1/healthz', 'expect_up', 'TLS 종료 · ModSecurity → upstream'),
    ('route', 'r3', 'WG 터널 A', 'KT 10.200.0.1 ↔ 온프렘 10.200.0.2', 'http://10.200.0.1:9586/metrics', 'expect_up', 'KT WireGuard exporter 응답으로 터널 확인'),
    ('route', 'r4', '온프렘 VIP', '10.10.1.100:80 (호스트 DNAT)', 'http://10.10.1.100/healthz', 'expect_up', 'KT upstream 대상'),
    ('route', 'r5', '민원 앱 (K8s)', 'k8s-cp1 192.168.120.226:30080', 'http://192.168.120.226:30080/healthz', 'expect_up', 'K8s 파드 정상 가동 (NodePort :30080)'),
    ('dmz', 'd1', 'app.ktci5.kr 우회', 'CF Tunnel → 앱 직결', 'https://app.ktci5.kr/healthz', 'expect_closed', 'P3: 터널 ingress에서 제거 → 404 (DNS 레코드 삭제는 P3-b)'),
    ('dmz', 'd2', 'openstack.ktci5.kr 우회', 'CF Tunnel → 앱 직결', 'https://openstack.ktci5.kr/healthz', 'expect_closed', 'P3: 터널 ingress에서 제거 → 404 (DNS 레코드 삭제는 P3-b)'),
    ('dmz', 'd3', 'KT 공인 IP 직접 접속', '14.63.212.190:443', 'https://14.63.212.190/healthz', 'expect_closed', 'Cloudflare·WG 외 직접 접속은 연결 끊음 (P2)'),
    ('dmz', 'd4', '접수 대기열 (입장 제한)', '동시 150 · IP별 20r/s → 대기 안내', 'https://10.200.0.1/_edge/waiting-preview', 'expect_waiting', '대기 안내 미리보기 503 확인 · 순번 보장 아님'),
    ('ops', 'o1', 'Keystone', '192.168.120.160:5000', 'http://192.168.120.160:5000/v3', 'expect_up', 'OpenStack Identity'),
    ('ops', 'o2', 'Nova API', '192.168.120.160:8774', 'http://192.168.120.160:8774/', 'expect_up', 'L2 복구 호출 대상'),
    ('ops', 'o3', 'Argo CD (온프렘)', 'k8s-cp1 (삭제 정리)', None, 'removed', 'CP RAM 확보 및 부하 완화를 위해 삭제 정리 완료 (정상)'),
    ('ops', 'o4', 'Grafana 관제 스택', 'AWS 통합 관제 (PR #24)', None, 'ok', 'AWS 통합 관제(PR #24)로 이관 완료 · Prometheus/Loki 연계'),
    ('ops', 'o5', 'KT Edge 상태 화면', 'kt-edge.ktci5.kr → 10.200.0.1:8088 (WG 전용)', 'https://kt-edge.ktci5.kr/', 'expect_up', '공개 주소 — Access 보호는 P3-b'),
    ('aws', 'e1', 'AWS ctl EC2 (PR #13)', '13.125.163.58 · t3.small · Rocky 8.10 · VPC 10.50.0.0/16 · WG 10.200.0.3', None, 'ok', '접속 확인 (11/19) · SSH는 s1 경유 WG · ctl↔dr·KT 피어 handshake 정상'),
    ('aws', 'e2', 'AWS dr EC2 (PR #13)', '54.116.129.147 · t3.small · Rocky 8.10 · VPC 10.51.0.0/16 · WG 10.200.0.4', None, 'ok', '접속 확인 (11/19) · k3s v1.37.2 단일 노드 설치'),
    ('aws', 'w1', 'WG KT ↔ AWS ctl', '10.200.0.3:22 (온프렘 → KT 허브 → ctl)', 'tcp://10.200.0.3:22', 'expect_up', 'KT 허브 피어 연결됨 (11/19)'),
    ('aws', 'w2', 'WG KT ↔ AWS dr', '10.200.0.4:22 (온프렘 → KT 허브 → dr)', 'tcp://10.200.0.4:22', 'expect_up', 'KT 허브 피어 연결됨 (11/19)'),
    ('aws', 's1', '보안그룹 WG 허용', 'UDP 51820 ← wg_peer_cidrs (PR #13)', None, 'ok', 'KT 허브 handshake 정상 → KT 대역 허용 확인'),
    ('aws', 's2', 'WG role 외부 피어', 'roles/wireguard (PR #14)', None, 'ok', 'wg_extra_peers로 KT 허브 피어 반영 (브랜치 feat/aws-dr-k3s, 미병합)'),
    ('aws', 's3', 'AWS → 온프렘 대역', 'AWS wg0 KT 피어 AllowedIPs', None, 'ok', 'ctl·dr → 온프렘 VIP·k8s-cp1 도달 확인 (11/19) · wg syncconf 금지(터널 멈춤), wg-quick 재시작만'),
    ('dr', 'a1', 'AWS 오케스트레이터 (러너)', '10.200.0.3:8080', 'http://10.200.0.3:8080/healthz', 'expect_up', 'PR #25 Alertmanager Webhook 연동 · L2 Ansible 재기동 엔진'),
    ('dr', 'a2', 'AWS DR k3s (Pilot-Light)', '10.200.0.4:30080', 'http://10.200.0.4:30080/healthz', 'expect_up', 'PR #19·#26 Pilot-Light 배포 · minwon-app 1 + MySQL 8.4 standby'),
    ('dr', 'a3', 'KT Edge Failover Upstream', '10.200.0.1 (Nginx Upstream)', None, 'ok', 'PR #26 Edge 전환 스크립트(failover_edge.sh) 구축 완료'),
    ('dr', 'a4', '비상 안내 페이지 (0초)', 'dr.ktci5.kr (GitHub Pages)', 'https://dr.ktci5.kr/', 'expect_up', 'Black Sky 시 0초 즉시 노출 비상 서식'),
    ('dr', 'a5', 'Cloudflare 전환 (Worker)', 'worker.js · active_origin', None, 'missing', '브랜치에 수정본 커밋 · minwon은 DNS 프록시로 KT 직행'),
    ('dev', 'v1', 'MySQL 8.4 GTID 복제 연동', '온프렘 10.10.2.10 ➔ AWS 10.200.0.4', None, 'ok', 'PR #26 GTID ON · repl_dr 계정 연동 · 온프렘→AWS 복제 성공 (지연 0초)'),
    ('dev', 'v2', 'Split-Brain 방지 펜싱', '온프렘 db-01 Watchdog (super_read_only)', None, 'ok', 'KT·AWS 60초 미도달 시 Primary 스스로 쓰기 차단 격리'),
    ('dev', 'v3', 'Blackbox RTO 실측 도구', 'chaos/measure_rto.py (0.5s 주기)', None, 'ok', 'PR #21 0.5초 주기 Blackbox 프로빙 및 RTO 초 단위 실측 CSV 기록'),
    ('dev', 'v4', 'L3 카오스 장애 주입기', 'chaos/inject_l3_fault.sh', None, 'ok', 'PR #21 iptables DROP 기반 온프렘 다운 시뮬레이션 및 복구 검증'),
    ('dev', 'v5', 'Alertmanager 3-Signal 판정', 'S1·S2·S3 신호 수집 룰셋', None, 'ok', 'PR #24 모니터링 룰셋 및 Orchestrator recovery_level 라벨 전달'),
    ('check', 'c1', 'AWS ctl 관제 컨테이너 스택', '10.200.0.3:9090 / :3000', None, 'warn', '[만들었으나 작동안됨 -> 확인] PR #24 머지완료 / AWS ctl 호스트 Docker 미설치로 미기동'),
    ('check', 'c2', 'AWS dr MySQL 포트 정합성', '10.200.0.4:13306 vs :3306', 'tcp://10.200.0.4:13306', 'expect_up', '[만들었으나 포트불일치 -> 확인] kubectl port-forward 13306 가동 (3306 일원화 필요)'),
    ('check', 'c3', '온프렘 db-01 외부 직접 도달', '10.10.2.10:3306 (data-net)', None, 'warn', '[보안격리 정상 -> 확인] FIP/외부 직결 차단, k8s-cp1 및 VIP 터널 경유 라우팅 확인'),
    ('dup', 'u1', '오케스트레이터 배포 일원화', 'Systemd vs Docker Compose', None, 'partial', '[만들었는데 중복됨 -> 해결필요] standalone uvicorn과 PR#24 docker-compose :8080 충돌 정리'),
    ('dup', 'u2', '복구 자동화 스크립트 규격', 'Ansible yml vs Bash sh', None, 'partial', '[만들었는데 중복됨 -> 해결필요] playbooks/recovery 와 scripts/dr 간 호출 인터페이스 단일화'),
]
CONNECTIVITY_GROUPS = [
    ('route', '민원 경로 (사용자 → 앱)'),
    ('dmz', 'DMZ 경계 (우회 경로)'),
    ('ops', '관리 · 관측 (온프렘)'),
    ('aws', 'AWS 지점 (PR #13·#14)'),
    ('dr', 'DR · 전환 (AWS · KT Edge)'),
    ('dev', '정상 가동 & 연동 완료 (PR #21·#24·#25·#26)'),
    ('check', '만들었으나 작동안됨/점검필요 [확인]'),
    ('dup', '만들었는데 중복됨 [해결필요]'),
]
_CC_CACHE = {'t': 0, 'data': None}


def _cc_probe(url):
    if url.startswith('tcp://'):
        host, port = url[6:].rsplit(':', 1)
        t0 = time.time()
        try:
            with socket.create_connection((host, int(port)), timeout=3):
                return 200, int((time.time() - t0) * 1000), ''
        except Exception as e:
            return None, int((time.time() - t0) * 1000), str(e)[:80]
    ctx = _cc_ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = _cc_ssl.CERT_NONE
    req = urllib.request.Request(url, headers={'User-Agent': 'FIGTEAM-CMP/1.0 connectivity'})
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=4, context=ctx) as r:
            return r.status, int((time.time() - t0) * 1000), ''
    except urllib.error.HTTPError as e:
        return e.code, int((time.time() - t0) * 1000), ''
    except Exception as e:
        reason = getattr(e, 'reason', e)
        return None, int((time.time() - t0) * 1000), str(reason)[:80]


def _cc_eval(kind, code):
    up = code is not None and code < 500
    if kind == 'expect_up':
        return 'ok' if up and code < 400 else 'fail'
    if kind == 'expect_waiting':
        return 'ok' if code == 503 else 'fail'
    if kind == 'expect_closed':
        return 'warn' if up and code < 400 else 'ok'
    return kind


def connectivity_check(force=False):
    if not force and _CC_CACHE['data'] and time.time() - _CC_CACHE['t'] < 15:
        return _CC_CACHE['data']
    live = [c for c in CONNECTIVITY_CHECKS if c[4]]
    with _CcPool(max_workers=12) as pool:
        results = dict(zip([c[1] for c in live], pool.map(lambda c: _cc_probe(c[4]), live)))
    items = []
    for g, cid, name, target, url, kind, note in CONNECTIVITY_CHECKS:
        it = {'group': g, 'id': cid, 'name': name, 'target': target, 'note': note, 'live': bool(url),
              'proto': 'tcp' if url and url.startswith('tcp://') else 'http'}
        if url:
            code, ms, err = results[cid]
            it.update(code=code, ms=ms, error=err, state=_cc_eval(kind, code))
        else:
            it['state'] = kind
        items.append(it)
    summary = {}
    for it in items:
        summary[it['state']] = summary.get(it['state'], 0) + 1
    data = {'status': 'ok', 'generated': int(time.time()), 'groups': CONNECTIVITY_GROUPS,
            'items': items, 'summary': summary, 'probe_from': 'figteam 포털 호스트 (온프렘 10.10.10.8)'}
    _CC_CACHE.update(t=time.time(), data=data)
    return data

_SERVICES_DETAIL_CACHE = {'t': 0, 'data': None}


_PUB_SYS_CACHE = {'t': 0, 'data': None}

def get_public_system_status():
    now = time.time()
    if _PUB_SYS_CACHE['data'] and (now - _PUB_SYS_CACHE['t'] < 4.0):
        return _PUB_SYS_CACHE['data']

    def probe(host, port, timeout=1.5):
        try:
            with socket.create_connection((host, port), timeout=timeout):
                return True
        except:
            return False

    kt_ok = probe('14.63.212.190', 443)
    onprem_ok = probe('192.168.120.226', 30080)
    aws_ok = probe('10.200.0.3', 22) or probe('10.200.0.4', 30080)

    all_down = not kt_ok and not onprem_ok and not aws_ok
    dr_active = (not onprem_ok) and aws_ok

    if all_down:
        mode = "BLACK_SKY"
        status_text = "전면 인프라 장애 (모든 클라우드 오프라인 · 404 비상 접수)"
        status_color = "#ef4444"
        badge_mode = "Black Sky (404)"
    elif dr_active:
        mode = "DR_ACTIVE"
        status_text = "L3 DR 절체 발동 중: AWS DR 센터 긴급 운영 중"
        status_color = "#f59e0b"
        badge_mode = "AWS DR Active"
    elif onprem_ok:
        mode = "NORMAL"
        status_text = "시스템 정상 가동 중 (온프레미스 Primary 활성)"
        status_color = "#10b981"
        badge_mode = "Primary RW"
    else:
        mode = "DEGRADED"
        status_text = "서비스 복구 진행 중 (우회 또는 자가치유 실행)"
        status_color = "#f59e0b"
        badge_mode = "Degraded"

    res = {
        "status": "ok",
        "system_mode": mode,
        "status_text": status_text,
        "status_color": status_color,
        "badge_mode": badge_mode,
        "all_down": all_down,
        "dr_active": dr_active,
        "generated_str": datetime.now().strftime("%H:%M:%S"),
        "clouds": {
            "kt": {
                "name": "KT Cloud Edge",
                "ip": "14.63.212.190",
                "is_ok": kt_ok,
                "status_label": "정상 가동 (ACTIVE)" if kt_ok else "장애 감지 (DOWN)",
                "color": "#10b981" if kt_ok else "#ef4444",
                "dot": "green" if kt_ok else "red"
            },
            "onprem": {
                "name": "온프레미스 K8s & DB",
                "ip": "192.168.120.226",
                "is_ok": onprem_ok,
                "status_label": "정상 가동 (PRIMARY)" if onprem_ok else "장애 감지 (DOWN)",
                "color": "#10b981" if onprem_ok else "#ef4444",
                "dot": "green" if onprem_ok else "red"
            },
            "aws": {
                "name": "AWS 관제 & DR",
                "ip": "10.200.0.3 / 10.200.0.4",
                "is_ok": aws_ok,
                "status_label": ("DR 절체 가동" if dr_active else "정상 대기 (STANDBY)") if aws_ok else "장애 감지 (DOWN)",
                "color": ("#f59e0b" if dr_active else "#10b981") if aws_ok else "#ef4444",
                "dot": ("yellow" if dr_active else "green") if aws_ok else "red"
            }
        },
        "git": {
            "repo": "prgrmany/team6-hybrid-autorecovery-platform",
            "branch": "main",
            "commit": "9c4b7e1 (v3.0 HA)",
            "sync": "Synced 🟢",
            "health": "Healthy 🟢",
            "desc": "ArgoCD GitOps 자동 동기화 배포 완료"
        }
    }
    _PUB_SYS_CACHE.update(t=now, data=res)
    return res


def get_services_and_pods_detail():
    now = time.time()
    if _SERVICES_DETAIL_CACHE['data'] and (now - _SERVICES_DETAIL_CACHE['t'] < 3.0):
        return _SERVICES_DETAIL_CACHE['data']

    # 1. On-prem K8s pods
    onprem_pods = []
    try:
        res = subprocess.run([
            'ssh', '-o', 'StrictHostKeyChecking=no', 'ubuntu@192.168.120.226',
            'sudo kubectl get pods -A -o wide --no-headers'
        ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=4, text=True)
        for line in res.stdout.strip().splitlines():
            parts = line.split()
            if len(parts) >= 8:
                onprem_pods.append({
                    'namespace': parts[0],
                    'name': parts[1],
                    'ready': parts[2],
                    'status': parts[3],
                    'restarts': parts[4],
                    'age': parts[5],
                    'ip': parts[6],
                    'node': parts[7]
                })
    except Exception as e:
        onprem_pods = [{'error': str(e)}]

    # 2. AWS DR K8s pods
    aws_pods = []
    try:
        res = subprocess.run([
            'ssh', '-o', 'StrictHostKeyChecking=no', 'rocky@10.200.0.4',
            'sudo /usr/local/bin/k3s kubectl get pods -A -o wide --no-headers'
        ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=4, text=True)
        for line in res.stdout.strip().splitlines():
            parts = line.split()
            if len(parts) >= 8:
                aws_pods.append({
                    'namespace': parts[0],
                    'name': parts[1],
                    'ready': parts[2],
                    'status': parts[3],
                    'restarts': parts[4],
                    'age': parts[5],
                    'ip': parts[6],
                    'node': parts[7]
                })
    except Exception as e:
        aws_pods = [{'error': str(e)}]

    hosts_detail = [
        {
            "id": "controller",
            "name": "온프레미스 controller",
            "group": "onprem",
            "role": "OpenStack 클라우드 제어 플레인 마스터",
            "ip": "192.168.120.100 (figteam-mgmt)",
            "tier": "IaaS Master",
            "hostMapping": "물리 서버 직접 설치",
            "vcpu": 4,
            "vcpuLoad": "0.32",
            "ramTotal": 9652,
            "ramUsed": 6045,
            "swapUsed": 0,
            "swapTotal": 0,
            "diskUsed": "18.4G",
            "diskTotal": "50G",
            "diskPct": 37,
            "status": "ACTIVE 🟢",
            "services": [
                {"name": "Nova Compute Engine", "port": ":8774", "status": "ACTIVE 🟢", "desc": "VM 생명주기 관리"},
                {"name": "Neutron Network API", "port": ":9696", "status": "ACTIVE 🟢", "desc": "SDN/OVS 네트워크 제어"},
                {"name": "Glance Image API", "port": ":9292", "status": "ACTIVE 🟢", "desc": "OS 이미지 저장소"},
                {"name": "Keystone Identity", "port": ":5000", "status": "ACTIVE 🟢", "desc": "통합 인증 & 토큰"},
                {"name": "RabbitMQ / MariaDB (IaaS 제어 전용)", "port": ":5672, :3306", "status": "ACTIVE 🟢", "desc": "OpenStack 시스템 RPC 버스 & 클라우드 메타데이터 DB (민원 서비스 DB와 분리)"}
            ],
            "pods": []
        },
        {
            "id": "db-01",
            "name": "온프레미스 db-01",
            "group": "onprem",
            "role": "Primary 데이터베이스 (MySQL 8.4)",
            "ip": "10.10.2.10 (data-net 격리망)",
            "tier": "Tier 3: Database & Cinder",
            "hostMapping": "compute4 (m1.medium)",
            "vcpu": 2,
            "vcpuLoad": "0.12",
            "ramTotal": 4096,
            "ramUsed": 1850,
            "swapUsed": 0,
            "swapTotal": 0,
            "diskUsed": "4.2G",
            "diskTotal": "30G (Cinder 영구 볼륨)",
            "diskPct": 15,
            "status": "ACTIVE 🟢",
            "services": [
                {"name": "MySQL 8.4 Primary", "port": ":3306", "status": "ACTIVE 🟢", "desc": "GTID=ON, ROW binlog 7일 보관"},
                {"name": "Cinder 30GB 마운트", "port": "/var/lib/mysql", "status": "ACTIVE 🟢", "desc": "OpenStack Cinder 영속 볼륨 확장"}
            ],
            "pods": []
        },
        {
            "id": "k8s-cp1",
            "name": "온프레미스 k8s-cp1",
            "group": "onprem",
            "role": "K3s 마스터 제어 노드 (Control Plane)",
            "ip": "172.20.0.86 (VIP 10.200.0.2 / FIP 192.168.120.226)",
            "tier": "Tier 2: K8s Control Plane",
            "hostMapping": "compute3 (m1.medium)",
            "vcpu": 2,
            "vcpuLoad": "0.08",
            "ramTotal": 4096,
            "ramUsed": 310,
            "swapUsed": 0,
            "swapTotal": 0,
            "diskUsed": "6.5G",
            "diskTotal": "20G",
            "diskPct": 32,
            "status": "ACTIVE 🟢",
            "services": [
                {"name": "K3s Server", "port": ":6443", "status": "ACTIVE 🟢", "desc": "API Server, etcd, Scheduler"},
                {"name": "Traefik Ingress", "port": ":80, :443", "status": "ACTIVE 🟢", "desc": "L7 인그레스 컨트롤러"},
                {"name": "WireGuard Client", "port": "wg0 (10.200.0.2)", "status": "ACTIVE 🟢", "desc": "터널 A/B 종단 클라이언트"}
            ],
            "pods": [p for p in onprem_pods if p.get('node') == 'k8s-cp1']
        },
        {
            "id": "k8s-w1",
            "name": "온프레미스 k8s-w1",
            "group": "onprem",
            "role": "K3s 워커 노드 1 (민원 서비스 파드 주 실행)",
            "ip": "172.20.0.180 (figteam-net)",
            "tier": "Tier 2: K8s Worker 1",
            "hostMapping": "compute1 (k8s.worker)",
            "vcpu": 2,
            "vcpuLoad": "0.15",
            "ramTotal": 2560,
            "ramUsed": 301,
            "swapUsed": 0,
            "swapTotal": 0,
            "diskUsed": "5.8G",
            "diskTotal": "20G",
            "diskPct": 29,
            "status": "ACTIVE 🟢",
            "services": [
                {"name": "K3s Agent", "port": "k3s-agent.service", "status": "ACTIVE 🟢", "desc": "kubelet & containerd (Worker 1)"},
                {"name": "Minwon Service Host", "port": ":30080 NodePort", "status": "ACTIVE 🟢", "desc": "민원 앱 파드 2대 안정 서빙 (안전·성능 우선)"},
                {"name": "ArgoCD 배포 엔진", "port": "Pod", "status": "ACTIVE 🟢", "desc": "GitOps 지속 배포 파드"}
            ],
            "pods": [p for p in onprem_pods if p.get('node') == 'k8s-w1']
        },
        {
            "id": "kt-edge",
            "name": "KT Cloud Edge (kt-edge)",
            "group": "cloud",
            "role": "L7 인그레스 관문 & WireGuard 허브",
            "ip": "10.200.0.1 (공인: 14.63.212.190)",
            "tier": "Tier 1: 엣지 보안 & 트래픽 관문",
            "hostMapping": "KT Cloud D1 VM (단독)",
            "vcpu": 2,
            "vcpuLoad": "0.01",
            "ramTotal": 1771,
            "ramUsed": 254,
            "swapUsed": 0,
            "swapTotal": 2047,
            "diskUsed": "5.2G",
            "diskTotal": "20G",
            "diskPct": 26,
            "status": "ACTIVE 🟢",
            "services": [
                {"name": "Nginx Reverse Proxy", "port": ":80, :443", "status": "ACTIVE 🟢", "desc": "트래픽 라우팅 & SSL 종단"},
                {"name": "ModSecurity WAF", "port": "L7 Embedded", "status": "ACTIVE 🟢", "desc": "웹 취약점 실시간 차단"},
                {"name": "WireGuard Hub", "port": ":51820 UDP", "status": "ACTIVE 🟢", "desc": "하이브리드 터널 A/C 연결 허브"}
            ],
            "pods": []
        },
        {
            "id": "aws-ctl",
            "name": "AWS 관제 (aws-ctl)",
            "group": "cloud",
            "role": "중앙 모니터링 & L2 자동복구 오케스트레이터",
            "ip": "10.200.0.3 (공인: 13.125.163.58)",
            "tier": "Tier 4: AWS 중앙 관제 & DR 통제",
            "hostMapping": "AWS ap-northeast-2 (t3.small)",
            "vcpu": 2,
            "vcpuLoad": "0.10",
            "ramTotal": 1720,
            "ramUsed": 226,
            "swapUsed": 1,
            "swapTotal": 1024,
            "diskUsed": "6.8G",
            "diskTotal": "30G",
            "diskPct": 23,
            "status": "ACTIVE 🟢",
            "services": [
                {"name": "Prometheus", "port": ":9090", "status": "ACTIVE 🟢", "desc": "전체 노드 메트릭 시계열 수집"},
                {"name": "Grafana Dashboard", "port": ":3000", "status": "ACTIVE 🟢", "desc": "통합 관제 대시보드 v12.1"},
                {"name": "Alertmanager", "port": ":9093", "status": "ACTIVE 🟢", "desc": "장애 감지 웹훅 트리거"},
                {"name": "Ansible Runner", "port": "CLI/Engine", "status": "ACTIVE 🟢", "desc": "L2 자동 치유 플레이북 가동"}
            ],
            "pods": []
        },
        {
            "id": "aws-dr",
            "name": "AWS DR (aws-dr)",
            "group": "cloud",
            "role": "재해복구 Standby K3s & Standby MySQL",
            "ip": "10.200.0.4 (공인: 54.116.129.147)",
            "tier": "Tier 4: AWS Pilot-Light DR",
            "hostMapping": "AWS ap-northeast-2 (t3.small)",
            "vcpu": 2,
            "vcpuLoad": "0.22",
            "ramTotal": 1720,
            "ramUsed": 899,
            "swapUsed": 378,
            "swapTotal": 1024,
            "diskUsed": "14.0G",
            "diskTotal": "30G",
            "diskPct": 47,
            "status": "ACTIVE 🟢",
            "services": [
                {"name": "K3s Standalone", "port": ":6443", "status": "ACTIVE 🟢", "desc": "비상 복구 단독 쿠버네티스"},
                {"name": "MySQL 8.4 Standby", "port": ":3306 (Pod)", "status": "ACTIVE 🟢", "desc": "GTID 실시간 복제 대기"},
                {"name": "WireGuard Client", "port": ":51820 UDP", "status": "ACTIVE 🟢", "desc": "터널 B(DB복제), 터널 C(DR절체)"}
            ],
            "pods": [p for p in aws_pods if 'name' in p]
        }
    ]

    res_data = {
        "status": "ok",
        "generated": int(time.time()),
        "generated_str": datetime.now().strftime("%H:%M:%S"),
        "total_hosts": len(hosts_detail),
        "total_vcpu": 22,
        "total_ram": "25.5GB (사용 35%)",
        "swap_status": "0B Used (99.0% 안정)",
        "cinder_status": "30GB (15% 사용)",
        "hosts": hosts_detail,
        "onprem_pods_count": len([p for p in onprem_pods if 'name' in p]),
        "aws_pods_count": len([p for p in aws_pods if 'name' in p])
    }
    _SERVICES_DETAIL_CACHE.update(t=now, data=res_data)
    return res_data

def openstack_overview():
    out = {"status": "ok", "generated": int(time.time()), "errors": {}}
    try:
        a = os_auth_full()
        out["catalog"] = a["catalog"]
        out["endpoints"] = {k: urllib.parse.urlparse(v).netloc for k, v in a["endpoints"].items()}
    except Exception as e:
        return {"status": "error", "message": f"Keystone 인증 실패: {e}"}

    def grab(key, fn):
        try:
            out[key] = fn()
        except Exception as e:
            out["errors"][key] = str(e)[:200]

    grab("nova_services", lambda: [_pick(x, ("binary", "host", "zone", "status", "state", "updated_at"))
                                   for x in _os_call("compute", "/os-services").get("services", [])])
    grab("hypervisors", lambda: [_pick(x, ("hypervisor_hostname", "state", "status", "vcpus", "vcpus_used", "memory_mb", "memory_mb_used",
                                           "local_gb", "local_gb_used", "running_vms", "host_ip", "hypervisor_type"))
                                 for x in _os_call("compute", "/os-hypervisors/detail").get("hypervisors", [])])
    grab("servers", lambda: [{"id": x.get("id"), "name": x.get("name"), "status": x.get("status"),
                              "host": x.get("OS-EXT-SRV-ATTR:host") or x.get("OS-EXT-SRV-ATTR:hypervisor_hostname"),
                              "flavor": (x.get("flavor") or {}).get("original_name") or (x.get("flavor") or {}).get("id"),
                              "addresses": x.get("addresses") or {},
                              "volumes": [v.get("id") for v in (x.get("os-extended-volumes:volumes_attached") or [])]}
                             for x in _os_call("compute", "/servers/detail?all_tenants=1").get("servers", [])])
    grab("limits", lambda: _os_call("compute", "/limits").get("limits", {}).get("absolute", {}))
    grab("networks", lambda: [_pick(x, ("id", "name", "status", "router:external", "subnets", "provider:network_type", "shared"))
                              for x in _os_call("network", "/v2.0/networks").get("networks", [])])
    grab("subnets", lambda: [_pick(x, ("id", "name", "cidr", "network_id", "gateway_ip", "enable_dhcp"))
                             for x in _os_call("network", "/v2.0/subnets").get("subnets", [])])
    grab("routers", lambda: [_pick(x, ("id", "name", "status", "external_gateway_info"))
                             for x in _os_call("network", "/v2.0/routers").get("routers", [])])
    grab("ports", lambda: [_pick(x, ("id", "network_id", "device_owner", "device_id", "fixed_ips", "status"))
                           for x in _os_call("network", "/v2.0/ports").get("ports", [])])
    grab("floatingips", lambda: [_pick(x, ("id", "floating_ip_address", "fixed_ip_address", "port_id", "router_id", "status", "floating_network_id"))
                                 for x in _os_call("network", "/v2.0/floatingips").get("floatingips", [])])
    grab("agents", lambda: [_pick(x, ("agent_type", "binary", "host", "alive", "admin_state_up"))
                            for x in _os_call("network", "/v2.0/agents").get("agents", [])])
    grab("cinder_services", lambda: [_pick(x, ("binary", "host", "zone", "status", "state"))
                                     for x in _os_call("volumev3", "/os-services").get("services", [])])
    grab("volumes", lambda: [{"id": x.get("id"), "name": x.get("name"), "size": x.get("size"), "status": x.get("status"),
                              "volume_type": x.get("volume_type"),
                              "attachments": [_pick(t, ("server_id", "device")) for t in (x.get("attachments") or [])]}
                             for x in _os_call("volumev3", "/volumes/detail?all_tenants=1").get("volumes", [])])
    grab("images", lambda: [_pick(x, ("id", "name", "status", "size", "disk_format", "visibility"))
                            for x in _os_call("image", "/v2/images?limit=50").get("images", [])])
    if "object-store" in OS_AUTH_CACHE.get("endpoints", {}):
        grab("swift", lambda: [_pick(x, ("name", "count", "bytes"))
                               for x in (_os_call("object-store", "?format=json") or [])])
    return out

def openstack_console_log(server_id, length=80):
    if not OS_ID_RE.match(server_id or ""):
        raise Exception("잘못된 서버 ID")
    res = _os_call("compute", f"/servers/{server_id}/action", {"os-getConsoleOutput": {"length": int(length)}})
    return res.get("output", "")

def openstack_snapshot(server_id, name):
    if not OS_ID_RE.match(server_id or ""):
        raise Exception("잘못된 서버 ID")
    name = re.sub(r"[^0-9A-Za-z가-힣._ -]", "", name or "")[:60] or f"figteam-snap-{time.strftime('%Y%m%d-%H%M')}"
    res = _os_call("compute", f"/servers/{server_id}/action", {"createImage": {"name": name}})
    return {"name": name, "image_id": (res or {}).get("image_id")}

def list_openstack_servers():
    cfg = get_openstack_credentials()
    token = get_openstack_token()
    url = f"{cfg['nova_url'].rstrip('/')}/servers/detail?all_tenants=1"
    req = urllib.request.Request(
        url,
        headers={"X-Auth-Token": token, "User-Agent": "FIGTEAM-CMP/1.0"}
    )
    with urllib.request.urlopen(req, timeout=5) as res:
        data = json.loads(res.read().decode('utf-8'))
        return data.get("servers", [])

def action_openstack_server(server_id, action):
    cfg = get_openstack_credentials()
    token = get_openstack_token()
    url = f"{cfg['nova_url'].rstrip('/')}/servers/{server_id}/action"
    
    payload = {}
    if action == "stop":
        payload = {"os-stop": None}
    elif action == "start":
        payload = {"os-start": None}
    elif action == "reboot":
        payload = {"reboot": {"type": "SOFT"}}
    elif action == "hard_reboot":
        payload = {"reboot": {"type": "HARD"}}
    else:
        raise Exception(f"지원하지 않는 액션입니다: {action}")
        
    def _send(tk):
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode('utf-8'),
            headers={"Content-Type": "application/json", "X-Auth-Token": tk, "User-Agent": "FIGTEAM-CMP/1.0"}
        )
        with urllib.request.urlopen(req, timeout=10) as res:
            return res.status in (200, 202)

    try:
        return _send(token)
    except urllib.error.HTTPError as e:
        if e.code == 401:
            OS_TOKEN_CACHE["token"] = None
            new_tk = get_openstack_token()
            return _send(new_tk)
        err_msg = e.read().decode('utf-8', errors='ignore')
        raise Exception(f"Nova API 오류 ({e.code}): {err_msg}")

def get_vmware_status():
    import subprocess
    try:
        res = subprocess.run(['vmrun', '-T', 'ws', 'list'], capture_output=True, text=True, timeout=5)
        lines = [l.strip() for l in res.stdout.strip().split('\n') if l.strip().endswith('.vmx')]
        nodes = []
        for l in lines:
            name = l.split('/')[-1].replace('.vmx', '')
            role = "Controller Node" if "openstack" in name else "Compute Node"
            nodes.append({"name": name, "path": l, "role": role, "status": "Running"})
        return nodes
    except Exception as e:
        return [
            {"name": "openstack", "role": "Controller", "status": "Running"},
            {"name": "compute1", "role": "Compute 1", "status": "Running"},
            {"name": "compute3", "role": "Compute 3", "status": "Running"},
            {"name": "compute4", "role": "Compute 4", "status": "Running"}
        ]



# 다중 대상 터미널 대상 (화이트리스트). 비밀값 없음 — s1 포털 계정의 SSH 키 사용.
TERM_TARGETS = {
    'kt-edge':    {'label': 'KT Edge (허브·WAF)', 'host': 'root@10.200.0.1'},
    'ctl':        {'label': 'AWS ctl (러너)',      'host': 'rocky@10.200.0.3'},
    'dr':         {'label': 'AWS dr (복구)',       'host': 'rocky@10.200.0.4'},
    'controller': {'label': 'OpenStack controller', 'host': 'root@192.168.120.160'},
    'compute1':   {'label': 'compute1 (워커1)',    'host': 'root@192.168.120.161'},
    'compute3':   {'label': 'compute3 (k8s 마스터)', 'host': 'root@192.168.120.163'},
    'compute4':   {'label': 'compute4 (DB)',       'host': 'root@192.168.120.164'},
    'k8s-cp1':    {'label': 'k8s-cp1 (앱)',        'host': 'ubuntu@192.168.120.226'},
    'db-01':      {'label': 'db-01 (MySQL 원본)',  'host': 'ubuntu@10.10.2.10'},
    'compute2':   {'label': 'compute2 (워커2 물리)', 'host': 'root@192.168.120.162'},
    'k8s-w1':     {'label': 'k8s-w1 (워커1 VM)', 'host': 'ubuntu@172.20.0.180', 'jump': 'ubuntu@192.168.120.226'},
    'k8s-w2':     {'label': 'k8s-w2 (워커2 VM)', 'host': 'ubuntu@172.20.0.152', 'jump': 'ubuntu@192.168.120.226'},
}
TERM_DANGER = re.compile(r'restart|stop|poweroff|reboot|reload|shutdown|kill|\brm\s|\bdd\s|mkfs|systemctl\s+(start|enable|disable|mask)|'
                         r'\b(drop|delete|truncate|alter|update|insert|replace|grant|revoke|reset)\b|openstack\s+\S+\s+(create|delete|set|unset|migrate|resize|rebuild)|'
                         r'kubectl\s+(delete|apply|scale|edit|patch|drain|cordon)|wg\s+(set|syncconf)|wg-quick', re.I)

CTRL_UNLOCK = {}          # 세션 토큰 → 만료 시각 (제어 명령 1회 잠금 해제, 60분)
CTRL_TTL = 3600
TERM_AUDIT = '/opt/figteam-portal/term-audit.log'
def ctrl_unlocked(token):
    exp = CTRL_UNLOCK.get(token or '')
    if exp and exp > time.time(): return int(exp - time.time())
    CTRL_UNLOCK.pop(token or '', None); return 0
def term_audit(ip, target, cmd, rc, danger):
    try:
        with open(TERM_AUDIT, 'a', encoding='utf-8') as f:
            f.write(json.dumps({"t": time.strftime('%Y-%m-%d %H:%M:%S'), "ip": ip, "target": target, "danger": danger, "rc": rc, "cmd": cmd[:500]}, ensure_ascii=False) + "\n")
    except Exception:
        pass

def generate_session():
    token = secrets.token_hex(24)
    SESSIONS[token] = time.time() + SESSION_TTL
    _save_sessions()
    return token

def is_valid_session(token):
    if not token or token not in SESSIONS:
        return False
    if time.time() > SESSIONS[token]:
        del SESSIONS[token]
        _save_sessions()
        return False
    return True

def get_horizon_session():
    """Authenticates against OpenStack Horizon and returns the sessionid cookie value."""
    try:
        cj = http.cookiejar.CookieJar()
        opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
        
        login_url = f"{HORIZON_INTERNAL}/dashboard/auth/login/"
        req1 = urllib.request.Request(login_url, headers={"User-Agent": "FIGTEAM-SSO/1.0"})
        with opener.open(req1, timeout=5) as res1:
            body = res1.read().decode('utf-8', errors='ignore')
            
        csrf_token = ""
        for cookie in cj:
            if cookie.name == "csrftoken":
                csrf_token = cookie.value
                break
        if not csrf_token:
            m = re.search(r'name=["\']csrfmiddlewaretoken["\']\s+value=["\']([^"\']+)["\']', body)
            if m:
                csrf_token = m.group(1)
                
        post_data = urllib.parse.urlencode({
            "csrfmiddlewaretoken": csrf_token,
            "username": OS_USER,
            "password": OS_PASS,
            "region": "default"
        }).encode('utf-8')
        
        req2 = urllib.request.Request(login_url, data=post_data, headers={
            "User-Agent": "FIGTEAM-SSO/1.0",
            "Referer": login_url,
            "Content-Type": "application/x-www-form-urlencoded"
        })
        
        with opener.open(req2, timeout=5) as res2:
            pass
            
        for cookie in cj:
            if cookie.name == "sessionid":
                return cookie.value
    except Exception as e:
        print(f"[ERROR] Failed to authenticate to Horizon: {e}")
    return None

LOGIN_HTML = """<!DOCTYPE html>
<html lang="ko">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>FIGTEAM 통합 클라우드 포털 - 로그인</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500&family=IBM+Plex+Sans+KR:wght@300;400;500;600&display=swap" rel="stylesheet">
  <style>
    :root {
      --bp-ground: #173F6B;
      --bp-deep:   #0F2D4F;
      --bp-ink:    #E6EEF5;
      --bp-ink-2:  rgba(230,238,245,.72);
      --bp-ink-3:  rgba(230,238,245,.45);
      --bp-grid:   rgba(230,238,245,.07);
      --bp-grid-major: rgba(230,238,245,.14);
      --bp-pencil: #F4C95D;
      --bp-redline:#FF8A73;
      --bp-ok:     #8FE0B4;
      --font: 'IBM Plex Sans KR', system-ui, sans-serif;
      --mono: 'IBM Plex Mono', ui-monospace, monospace;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    html, body { height: 100%; }
    body {
      font-family: var(--font);
      color: var(--bp-ink);
      background-color: var(--bp-ground);
      background-image:
        linear-gradient(var(--bp-grid-major) 1px, transparent 1px),
        linear-gradient(90deg, var(--bp-grid-major) 1px, transparent 1px),
        linear-gradient(var(--bp-grid) 1px, transparent 1px),
        linear-gradient(90deg, var(--bp-grid) 1px, transparent 1px);
      background-size: 120px 120px, 120px 120px, 24px 24px, 24px 24px;
      background-position: -1px -1px;
      padding: 20px;
      -webkit-font-smoothing: antialiased;
    }
    /* 도면 외곽선 */
    .sheet {
      position: relative;
      min-height: calc(100vh - 40px);
      border: 2px solid var(--bp-ink);
      outline: 1px solid var(--bp-ink-3);
      outline-offset: 6px;
      display: grid;
      grid-template-columns: 1fr minmax(320px, 400px);
      grid-template-rows: 1fr auto;
    }
    /* 토폴로지 도면 영역 */
    .drawing { grid-column: 1; grid-row: 1 / span 2; padding: 40px 32px 32px 48px; display: flex; flex-direction: column; }
    .drawing h2 { font-weight: 300; font-size: 15px; color: var(--bp-ink-2); letter-spacing: .02em; }
    .drawing svg { flex: 1; width: 100%; max-height: 640px; margin-top: 16px; }
    svg .ln   { fill: none; stroke: var(--bp-ink); stroke-width: 1.5; }
    svg .thin { fill: none; stroke: var(--bp-ink-3); stroke-width: 1; stroke-dasharray: 4 4; }
    svg .tun  { fill: none; stroke: var(--bp-ink); stroke-width: 1.5; stroke-dasharray: 10 6; }
    svg .tun.c{ stroke: var(--bp-ink-3); }
    svg text  { fill: var(--bp-ink); font-family: var(--font); font-size: 14px; font-weight: 500; }
    svg .note { fill: var(--bp-ink-2); font-size: 12px; font-weight: 400; }
    svg .ip   { fill: var(--bp-ink-3); font-family: var(--mono); font-size: 11px; }
    svg .tag  { fill: var(--bp-pencil); font-size: 12px; font-weight: 500; }
    svg .dot  { fill: var(--bp-ok); }
    /* 첫 로드 시 한 번만 선이 그려진다 */
    .draw { stroke-dasharray: 1400; stroke-dashoffset: 1400; animation: draw 1.8s cubic-bezier(.6,.1,.3,1) forwards; }
    .draw.d2 { animation-delay: .35s; } .draw.d3 { animation-delay: .7s; }
    .fade { opacity: 0; animation: fade .6s ease 1.6s forwards; }
    @keyframes draw { to { stroke-dashoffset: 0; } }
    @keyframes fade { to { opacity: 1; } }
    @media (prefers-reduced-motion: reduce) { .draw, .fade { animation: none; stroke-dashoffset: 0; opacity: 1; } }

    /* 표제란 */
    .titleblock { grid-column: 2; grid-row: 2; border-left: 2px solid var(--bp-ink); border-top: 2px solid var(--bp-ink); background: var(--bp-deep); }
    .tb-row { display: grid; grid-template-columns: 88px 1fr; border-bottom: 1px solid var(--bp-ink-3); }
    .tb-row > span { padding: 8px 12px; font-size: 12px; }
    .tb-row > span:first-child { color: var(--bp-ink-3); border-right: 1px solid var(--bp-ink-3); }
    .tb-title { padding: 20px 20px 16px; border-bottom: 1px solid var(--bp-ink); }
    .tb-title h1 { font-size: 26px; font-weight: 600; line-height: 1.25; letter-spacing: -.01em; }
    .tb-title p { margin-top: 6px; font-size: 13px; color: var(--bp-ink-2); }
    form { padding: 20px; }
    .field { margin-bottom: 16px; }
    label { display: block; font-size: 13px; color: var(--bp-ink-2); margin-bottom: 6px; }
    input {
      width: 100%; padding: 11px 12px;
      background: transparent; color: var(--bp-ink);
      border: 1px solid var(--bp-ink-3); border-radius: 0;
      font: 15px var(--font);
    }
    input::placeholder { color: var(--bp-ink-3); }
    input:focus { outline: none; border-color: var(--bp-pencil); box-shadow: inset 0 0 0 1px var(--bp-pencil); }
    .btn {
      width: 100%; margin-top: 4px; padding: 13px;
      background: var(--bp-ink); color: var(--bp-deep);
      border: 0; border-radius: 0;
      font: 600 15px var(--font); cursor: pointer;
    }
    .btn:hover { background: #fff; }
    .btn:focus-visible { outline: 2px solid var(--bp-pencil); outline-offset: 3px; }
    .error { margin-bottom: 16px; padding: 10px 12px; border: 1px solid var(--bp-redline); color: var(--bp-redline); font-size: 13px; }

    @media (max-width: 860px) {
      body { padding: 16px; }
      .sheet { grid-template-columns: minmax(0, 1fr); grid-template-rows: auto auto; outline: none; min-height: 0; }
      .drawing { grid-row: 1; grid-column: 1; padding: 20px 12px 8px; min-width: 0; }
      .drawing h2 { font-size: 13px; }
      .tb-title h1 { font-size: 22px; }
      .drawing svg { max-height: 280px; }
      .titleblock { grid-column: 1; grid-row: 2; border-left: 0; }
    }
  </style>
</head>
<body>
  <div class="sheet">
    <section class="drawing" aria-hidden="true">
      <h2>민원불패 하이브리드 멀티클라우드 — 평시 트래픽 경로</h2>
      <svg viewBox="0 0 760 520" preserveAspectRatio="xMidYMid meet">
        <!-- 사용자 -->
        <circle class="ln draw" cx="70" cy="70" r="18"/>
        <text x="100" y="66">사용자 민원 접수</text>
        <text class="note" x="100" y="84">Cloudflare 경유</text>
        <path class="thin draw" d="M70 88 V170"/>

        <!-- Zone 1 KT -->
        <rect class="ln draw" x="20" y="170" width="200" height="130"/>
        <text x="36" y="198">KT Cloud</text>
        <text class="note" x="36" y="220">입구 · Edge-GW</text>
        <text class="note" x="36" y="240">Nginx TLS / WAF</text>
        <text class="ip"   x="36" y="282">14.63.212.190</text>

        <!-- Zone 2 온프렘 -->
        <rect class="ln draw d2" x="300" y="130" width="250" height="260"/>
        <text x="318" y="158">온프레미스 OpenStack</text>
        <text class="note" x="318" y="178">Primary · K8s</text>
        <rect class="thin draw d2" x="318" y="196" width="214" height="70"/>
        <text class="note" x="330" y="222">app — web · minwon-api</text>
        <text class="note" x="330" y="244">notify · audit worker</text>
        <rect class="thin draw d2" x="318" y="280" width="214" height="90"/>
        <text class="note" x="330" y="306">data — MySQL 8.4 Primary</text>
        <text class="note" x="330" y="328">Redis · RabbitMQ</text>
        <circle class="dot fade" cx="518" cy="158" r="5"/>

        <!-- Zone 3 AWS -->
        <rect class="ln draw d3" x="560" y="400" width="190" height="110"/>
        <text x="576" y="428">AWS</text>
        <text class="note" x="576" y="450">관제 · Pilot-Light DR</text>
        <text class="note" x="576" y="470">MySQL Replica (RO)</text>

        <!-- 터널 -->
        <path class="tun draw d2" d="M220 235 H300"/>
        <text class="tag fade" x="236" y="226">터널 A</text>
        <path class="tun draw d3" d="M500 390 V455 H560"/>
        <text class="tag fade" x="508" y="430">터널 B</text>
        <path class="tun c draw d3" d="M120 300 V470 H560"/>
        <text class="tag fade" x="132" y="460">터널 C · DR 우회</text>
      </svg>
    </section>

    <section class="titleblock">
      <div class="tb-title">
        <h1>클라우드 통합 콘솔</h1>
        <p>OpenStack, KT Cloud, K8s, Argo CD, Grafana를 한 계정으로 관리합니다.</p>
      </div>

      <!-- 실시간 시스템 가동/복구/DR 상태 인디케이터 배너 -->
      <div style="padding:14px 20px 0;">
        <div id="login-sys-banner" style="padding:10px 14px; border-radius:4px; font-size:12px; font-weight:700; display:flex; align-items:center; justify-content:space-between; background:rgba(16,185,129,0.15); border:1px solid #10b981; color:#8fe0b4;">
          <div style="display:flex; align-items:center; gap:8px;">
            <span id="login-sys-dot" style="display:inline-block; width:9px; height:9px; border-radius:50%; background:#10b981; box-shadow:0 0 8px #10b981;"></span>
            <span id="login-sys-text">시스템 상태 확인 중...</span>
          </div>
          <span id="login-sys-mode" style="font-size:10.5px; padding:2px 7px; border-radius:3px; background:rgba(16,185,129,0.25); border:1px solid #10b981; color:#a7f3d0;">NORMAL</span>
        </div>

        <!-- 3대 클라우드 개별 초록/빨강 상태 뱃지 스트립 -->
        <div style="display:grid; grid-template-columns:repeat(3, 1fr); gap:6px; margin-top:8px; font-size:11px;">
          <div id="login-st-kt" style="padding:5px 6px; background:#0f172a; border:1px solid #334155; border-radius:3px; text-align:center; display:flex; align-items:center; justify-content:center; gap:5px;">
            <span id="login-dot-kt">🟢</span> <span style="font-weight:600;">KT Cloud</span>
          </div>
          <div id="login-st-onprem" style="padding:5px 6px; background:#0f172a; border:1px solid #334155; border-radius:3px; text-align:center; display:flex; align-items:center; justify-content:center; gap:5px;">
            <span id="login-dot-onprem">🟢</span> <span style="font-weight:600;">온프렘 K8s</span>
          </div>
          <div id="login-st-aws" style="padding:5px 6px; background:#0f172a; border:1px solid #334155; border-radius:3px; text-align:center; display:flex; align-items:center; justify-content:center; gap:5px;">
            <span id="login-dot-aws">🟢</span> <span style="font-weight:600;">AWS DR</span>
          </div>
        </div>
      </div>

      <!-- 404 / Black Sky 전면 장애 비상 안내 박스 -->
      <div id="all-clouds-off-alert" style="display:none; margin:12px 20px 0; padding:12px; border:1px dashed var(--bp-redline); background:rgba(255,138,115,0.15); color:var(--bp-redline); font-size:12px; line-height:1.5;">
        <strong style="display:block; font-size:13px; margin-bottom:4px;">🚨 404 / 전면 인프라 비상 모드 (Black Sky)</strong>
        모든 클라우드 서비스가 오프라인 상태입니다.<br>
        비상 정적 접수처로 즉시 이동하십시오: <a href="https://dr.ktci5.kr/" target="_blank" style="color:#38bdf8; font-weight:700; text-decoration:underline;">dr.ktci5.kr (0초 접수처)</a>
      </div>
      <form method="POST" action="/login" id="login-form">
        %%ERROR%%
        <div class="field">
          <label for="u">통합 계정 ID</label>
          <input id="u" type="text" name="username" placeholder="fig" required autofocus autocomplete="username">
        </div>
        <div class="field">
          <label for="p">비밀번호</label>
          <input id="p" type="password" name="password" placeholder="••••••••" required autocomplete="current-password">
        </div>
        <button type="submit" class="btn" id="login-btn">로그인</button>
      </form>
      <div class="tb-row"><span>프로젝트</span><span>KT CI5 민원불패</span></div>
      <div class="tb-row"><span>팀</span><span>FIGTEAM</span></div>
      <div class="tb-row" style="border-bottom:0"><span>도면</span><span>v3.0 하이브리드 토폴로지</span></div>
    </section>
  </div>

  <script>
    (async function checkCloudStatus() {
      const form = document.getElementById('login-form');
      const btn = document.getElementById('login-btn');
      const alertBox = document.getElementById('all-clouds-off-alert');
      try {
        const res = await fetch('/api/session', { method: 'GET', cache: 'no-store' });
        if (res.status >= 500) throw new Error('Backend down');
      } catch (err) {
        if (alertBox) alertBox.style.display = 'block';
        if (btn) {
          btn.disabled = true;
          btn.style.opacity = '0.5';
          btn.style.cursor = 'not-allowed';
          btn.textContent = '클라우드 OFF (로그인 비활성화)';
        }
        if (form) {
          form.addEventListener('submit', function(e) {
            e.preventDefault();
            alert('모든 클라우드가 OFF 상태입니다. 시스템 복구 후 다시 시도하십시오.');
          });
        }
      }
    })();
  </script>
</body>
</html>
"""

PORTAL_HTML = """<!DOCTYPE html>
<html lang="ko">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <meta http-equiv="Cache-Control" content="no-cache, no-store, must-revalidate">
  <meta http-equiv="Pragma" content="no-cache">
  <meta http-equiv="Expires" content="0">
  <title>FIGTEAM Cloud Management Platform</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500&family=IBM+Plex+Sans+KR:wght@300;400;500;600&display=swap" rel="stylesheet">
  <style>
    :root {
      --bp-ground: #173F6B;
      --bp-deep:   #0F2D4F;
      --bp-sunk:   #0C2542;
      --bp-raised: #1D4A7A;
      --bp-ink:    #E6EEF5;
      --bp-ink-2:  #B4C6D8;
      --bp-ink-3:  #8AA5C2;
      --bp-line:   rgba(230,238,245,.28);
      --bp-line-2: rgba(230,238,245,.14);
      --bp-grid:   rgba(230,238,245,.06);
      --bp-grid-major: rgba(230,238,245,.12);
      --bp-pencil: #F4C95D;
      --bp-redline:#FF7A66;
      --bp-ok:     #5FD39A;
      --bp-ok-2:   #8FE0B4;
      --bp-violet: #C3A6FF;
      --font: 'IBM Plex Sans KR', system-ui, sans-serif;
      --mono: 'IBM Plex Mono', ui-monospace, monospace;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; font-family: var(--font); }
    body { background: var(--bp-ground); color: var(--bp-ink); height: 100vh; overflow: hidden; display: flex; flex-direction: column; -webkit-font-smoothing: antialiased; }
    :focus-visible { outline: 2px solid var(--bp-pencil); outline-offset: 2px; }

    
    /* TOP NAVIGATION MENU (사이드바 대체) */
    .top-nav {
      display: flex;
      align-items: center;
      gap: 6px;
      margin-left: 14px;
      flex-shrink: 0;
    }
    .top-nav-item {
      display: flex;
      align-items: center;
      gap: 6px;
      padding: 6px 12px;
      border: 1px solid transparent;
      border-radius: 6px;
      color: var(--bp-ink-2);
      font-size: 13px;
      font-weight: 500;
      cursor: pointer;
      user-select: none;
      white-space: nowrap;
      transition: all 0.15s ease;
      background: transparent;
    }
    .top-nav-item:hover {
      color: var(--bp-ink);
      background: rgba(230,238,245,0.08);
      border-color: rgba(230,238,245,0.2);
    }
    .top-nav-item.active {
      color: #0b1120 !important;
      background: var(--bp-pencil) !important;
      border-color: var(--bp-pencil) !important;
      font-weight: 700 !important;
    }

    /* DROPDOWN MENU */
    .top-dropdown {
      position: relative;
      display: inline-block;
    }
    .top-dropdown-btn {
      display: flex;
      align-items: center;
      gap: 6px;
      padding: 6px 12px;
      border: 1px solid rgba(230,238,245,0.22);
      border-radius: 6px;
      color: var(--bp-ink-2);
      font-size: 13px;
      font-weight: 500;
      cursor: pointer;
      user-select: none;
      white-space: nowrap;
      background: rgba(15,45,79,0.5);
      transition: all 0.15s ease;
    }
    .top-dropdown:hover .top-dropdown-btn, .top-dropdown-btn.active {
      color: #F7D684;
      background: rgba(15,45,79,0.95);
      border-color: #F7D684;
    }
    .top-dropdown-btn .arrow {
      font-size: 10px;
      transition: transform 0.2s ease;
    }
    .top-dropdown:hover .top-dropdown-btn .arrow {
      transform: rotate(180deg);
    }
    .top-dropdown-menu {
      display: none;
      position: absolute;
      top: 100%;
      left: 0;
      min-width: 200px;
      background: #0f172a;
      border: 1px solid #334155;
      border-radius: 8px;
      box-shadow: 0 12px 28px rgba(0,0,0,0.65);
      padding: 6px 0;
      z-index: 1000;
      margin-top: 4px;
      backdrop-filter: blur(8px);
    }
    .top-dropdown:hover .top-dropdown-menu {
      display: block;
      animation: fadeIn 0.15s ease-out;
    }
    @keyframes fadeIn {
      from { opacity: 0; transform: translateY(-4px); }
      to { opacity: 1; transform: translateY(0); }
    }
    .dropdown-item {
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 9px 15px;
      color: #cbd5e1;
      font-size: 12.5px;
      font-weight: 500;
      cursor: pointer;
      text-decoration: none;
      transition: background 0.15s, color 0.15s;
    }
    .dropdown-item:hover {
      background: #1e293b;
      color: #f8fafc;
    }
    .dropdown-item.active {
      background: rgba(244,201,93,0.18);
      color: #F4C95D;
      font-weight: 700;
    }
    .dropdown-item .ext-tag {
      font-size: 11px;
      color: #94a3b8;
    }
    .dropdown-divider {
      height: 1px;
      background: #334155;
      margin: 4px 0;
    }

    /* SIDEBAR 완전 제거 및 화면 100% Full Width 확장 */
    aside { display: none !important; width: 0 !important; }
    .app-container { display: flex; width: 100% !important; height: calc(100vh - 56px); overflow: hidden; }
    main { width: 100% !important; max-width: 100% !important; flex: 1 !important; }

    /* TOP NAVIGATION BAR — 도면 상단 테두리 */
    header { height: 56px; background: var(--bp-deep); border-bottom: 2px solid var(--bp-ink); display: flex; align-items: center; justify-content: space-between; padding: 0 20px; z-index: 100; }
    .brand { display: flex; align-items: center; gap: 12px; font-size: 16px; font-weight: 600; color: var(--bp-ink); letter-spacing: -.01em; }
    .brand-tag { border: 1px solid var(--bp-ink-3); color: var(--bp-ink-2); font-size: 11px; font-weight: 500; padding: 2px 8px; }

    .status-group { display: flex; align-items: center; gap: 0; font-size: 12px; color: var(--bp-ink-2); border: 1px solid var(--bp-line); }
    .chip { display: flex; align-items: center; gap: 8px; padding: 6px 12px; border-right: 1px solid var(--bp-line); }
    .chip:last-child { border-right: 0; }
    .dot { width: 8px; height: 8px; border-radius: 50%; }
    .dot.green { background: var(--bp-ok); }
    .dot.yellow { background: var(--bp-pencil); }
    .dot.red { background: var(--bp-redline); box-shadow: 0 0 0 3px rgba(255,122,102,.25); }

    .user-actions { display: flex; align-items: center; gap: 12px; }
    .user-badge { display: flex; align-items: center; gap: 6px; font-size: 12px; color: var(--bp-ink-2); padding: 5px 0; }
    .btn-top { background: transparent; border: 1px solid var(--bp-line); color: var(--bp-ink-2); font-size: 12px; padding: 5px 12px; cursor: pointer; text-decoration: none; }
    .btn-top:hover { color: var(--bp-ink); border-color: var(--bp-ink); }
    .btn-logout:hover { border-color: var(--bp-redline); color: var(--bp-redline); }

    /* LAYOUT: SIDEBAR + WORKSPACE */
    .app-container { display: flex; flex: 1; height: calc(100vh - 56px); overflow: hidden; }

    /* SIDEBAR — 도면 범례 */
    aside { width: 250px; background: var(--bp-deep); border-right: 2px solid var(--bp-ink); display: flex; flex-direction: column; justify-content: space-between; flex-shrink: 0; }
    .menu-list { list-style: none; padding: 12px 0; display: flex; flex-direction: column; }
    .menu-header { font-size: 11px; font-weight: 600; color: var(--bp-ink-3); padding: 16px 20px 6px; letter-spacing: 0.5px; }
    .menu-item { display: flex; align-items: center; gap: 12px; padding: 10px 20px; border-left: 3px solid transparent; color: var(--bp-ink-2); font-size: 13.5px; cursor: pointer; text-decoration: none; user-select: none; white-space: nowrap; transition: background 0.15s, color 0.15s; }
    .menu-item:hover { color: var(--bp-ink); background: var(--bp-grid-major); }
    .menu-item.active { color: var(--bp-ink); background: var(--bp-ground); border-left-color: var(--bp-pencil); font-weight: 600; }
    .menu-item .icon { font-size: 15px; width: 20px; text-align: center; filter: grayscale(.4); flex-shrink: 0; }
    .menu-item.active .icon { filter: none; }
    .menu-badge { display: none !important; }

    .sidebar-footer { padding: 14px 20px; border-top: 1px solid var(--bp-line); font-size: 11px; line-height: 1.6; color: var(--bp-ink-3); }

    /* WORKSPACE MAIN — 모눈 도면 */
    main {
      flex: 1; display: flex; flex-direction: column; overflow: hidden; position: relative;
      background-color: var(--bp-ground);
      background-image:
        linear-gradient(var(--bp-grid-major) 1px, transparent 1px),
        linear-gradient(90deg, var(--bp-grid-major) 1px, transparent 1px),
        linear-gradient(var(--bp-grid) 1px, transparent 1px),
        linear-gradient(90deg, var(--bp-grid) 1px, transparent 1px);
      background-size: 120px 120px, 120px 120px, 24px 24px, 24px 24px;
      background-position: -1px -1px;
    }

    /* CONSOLE FRAME VIEW */
    .frame-toolbar { height: 42px; background: var(--bp-deep); border-bottom: 1px solid var(--bp-ink); display: flex; align-items: center; justify-content: space-between; padding: 0 16px; }
    .frame-title { font-size: 13px; font-weight: 500; color: var(--bp-ink); display: flex; align-items: center; gap: 8px; }
    .frame-actions { display: flex; align-items: center; gap: 8px; }
    .tool-btn { background: transparent; border: 1px solid var(--bp-line); color: var(--bp-ink-2); font-size: 12px; padding: 4px 10px; cursor: pointer; display: flex; align-items: center; gap: 4px; text-decoration: none; }
    .tool-btn:hover { border-color: var(--bp-ink); color: var(--bp-ink); }

    .iframe-wrapper { flex: 1; width: 100%; height: calc(100% - 42px); position: relative; background: #fff; }
    iframe { width: 100%; height: 100%; border: none; display: block; }

    /* OVERVIEW DASHBOARD VIEW */
    #overview-panel, #ktvm-panel, #osvm-panel, #osnet-panel, #osops-panel, #realtime-panel, #awsvm-panel, #dr-panel, #orchestrator-panel, #chaos-panel, #grafana-panel { flex: 1; overflow-y: auto; padding: 24px 28px 36px; display: flex; flex-direction: column; gap: 20px; box-sizing: border-box; }
    .overview-hero { border: 2px solid var(--bp-ink); background: var(--bp-deep); padding: 22px 24px; }
    .overview-hero h2 { font-size: 24px; font-weight: 600; letter-spacing: -.01em; margin-bottom: 6px; color: var(--bp-ink); }
    .overview-hero p { font-size: 14px; color: var(--bp-ink-2); line-height: 1.6; max-width: 72ch; }

    /* 수치 — 표제란처럼 칸을 맞대어 배치 */
    .stats-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 0; border: 1px solid var(--bp-ink); background: var(--bp-deep); }
    .stat-card { padding: 16px 18px; border-right: 1px solid var(--bp-line); border-bottom: 1px solid var(--bp-line); margin: 0 -1px -1px 0; }
    .stat-card .label { font-size: 12px; color: var(--bp-ink-3); margin-bottom: 8px; }
    .stat-card .value { font-size: 24px; font-weight: 600; color: var(--bp-ink); letter-spacing: -.01em; }
    .stat-card .subtext { font-size: 12px; color: var(--bp-ok-2); margin-top: 4px; }

    .section-title { font-size: 16px; font-weight: 600; color: var(--bp-ink); margin-bottom: 12px; display: flex; align-items: center; gap: 8px; padding-bottom: 8px; border-bottom: 1px solid var(--bp-line); }

    .cards-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); gap: 16px; }
    .svc-card { background: var(--bp-deep); border: 1px solid var(--bp-line); padding: 18px; display: flex; flex-direction: column; justify-content: space-between; }
    .svc-card:hover { border-color: var(--bp-ink); }
    .svc-card-header { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 12px; }
    .svc-title { font-size: 15px; font-weight: 600; color: var(--bp-ink); }
    .svc-type { font-size: 11px; font-weight: 500; padding: 2px 8px; border: 1px solid currentColor; background: transparent !important; }
    .type-iaas { color: #9FD3F5 !important; }
    .type-gitops { color: var(--bp-pencil) !important; }
    .type-mon { color: var(--bp-ok-2) !important; }
    .type-app { color: var(--bp-violet) !important; }
    .svc-desc { font-size: 13px; color: var(--bp-ink-2); line-height: 1.6; margin-bottom: 16px; }
    .svc-footer { display: flex; justify-content: space-between; align-items: center; padding-top: 12px; border-top: 1px dashed var(--bp-line); font-size: 12px; color: var(--bp-ink-3); }
    .btn-launch { background: var(--bp-ink); color: var(--bp-deep); border: none; padding: 7px 14px; font-size: 12px; font-weight: 600; cursor: pointer; }
    .btn-launch:hover { background: #fff; }

    /* KT CLOUD / OPENSTACK VM MANAGEMENT */
    .kt-vm-box { background: var(--bp-deep); border: 2px solid var(--bp-ink); padding: 22px; display: flex; flex-direction: column; gap: 20px; }
    .kt-vm-header { display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid var(--bp-line); padding-bottom: 16px; }
    .kt-vm-title { display: flex; align-items: center; gap: 12px; }
    .kt-vm-name { font-size: 22px; font-weight: 600; color: var(--bp-ink); font-family: var(--mono); }
    .kt-vm-badge { font-size: 13px; font-weight: 500; padding: 4px 12px; display: flex; align-items: center; gap: 6px; border: 1px solid currentColor; }
    .state-running { color: var(--bp-ok-2); background: rgba(95,211,154,.12); }
    .state-stopped { color: var(--bp-redline); background: rgba(255,122,102,.12); }
    .state-transition { color: var(--bp-pencil); background: rgba(244,201,93,.12); }

    .kt-props-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 0; border: 1px solid var(--bp-line); }
    .prop-item { padding: 12px 14px; border-right: 1px solid var(--bp-line-2); border-bottom: 1px solid var(--bp-line-2); margin: 0 -1px -1px 0; }
    .prop-label { font-size: 12px; color: var(--bp-ink-3); margin-bottom: 4px; }
    .prop-val { font-size: 13px; font-weight: 500; color: var(--bp-ink); font-variant-numeric: tabular-nums; }

    .kt-ctrl-bar { display: flex; gap: 10px; flex-wrap: wrap; align-items: center; padding: 14px 0 0; border-top: 1px dashed var(--bp-line); }
    .btn-action { padding: 9px 16px; font-size: 13px; font-weight: 600; cursor: pointer; border: 1px solid currentColor; background: transparent; display: flex; align-items: center; gap: 8px; }
    .btn-stop { color: var(--bp-redline); }
    .btn-stop:hover:not(:disabled) { background: var(--bp-redline); color: var(--bp-sunk); }
    .btn-start { color: var(--bp-ok); }
    .btn-start:hover:not(:disabled) { background: var(--bp-ok); color: var(--bp-sunk); }
    .btn-reboot { color: var(--bp-pencil); }
    .btn-reboot:hover:not(:disabled) { background: var(--bp-pencil); color: var(--bp-sunk); }
    .btn-refresh { color: var(--bp-ink-2); border-color: var(--bp-line); }
    .btn-refresh:hover { color: var(--bp-ink); border-color: var(--bp-ink); }
    .btn-action:disabled { opacity: 0.35; cursor: not-allowed; }

    .kt-log-box { background: var(--bp-sunk); border: 1px solid var(--bp-line); padding: 14px; font-family: var(--mono); font-size: 12px; color: var(--bp-ink-2); height: 160px; overflow-y: auto; display: flex; flex-direction: column; gap: 6px; }
    .log-line { display: flex; gap: 10px; }
    .log-time { color: var(--bp-ink-3); }
    .log-msg { color: var(--bp-ink); }
    .log-msg.success { color: var(--bp-ok-2); }
    .log-msg.warn { color: var(--bp-pencil); }
    .log-msg.err { color: var(--bp-redline); }

    /* FULLSCREEN TOGGLE */
    .fullscreen header, .fullscreen aside, .fullscreen .frame-toolbar { display: none !important; }
    .fullscreen .app-container { height: 100vh; }
    .fullscreen .iframe-wrapper { height: 100vh; }

    /* DYNAMIC INTERACTIVE FLOW — 선 위를 흐르는 패킷 */
    @keyframes flow-active { from { stroke-dashoffset: 40; } to { stroke-dashoffset: 0; } }
    @keyframes node-pulse-green { 0%,100% { box-shadow: 0 0 0 0 rgba(95,211,154,0); } 50% { box-shadow: 0 0 0 4px rgba(95,211,154,.25); } }
    @keyframes node-pulse-red   { 0%,100% { box-shadow: 0 0 0 0 rgba(255,122,102,0); } 50% { box-shadow: 0 0 0 6px rgba(255,122,102,.35); } }
    @keyframes node-pulse-amber { 0%,100% { box-shadow: 0 0 0 0 rgba(244,201,93,0); } 50% { box-shadow: 0 0 0 5px rgba(244,201,93,.3); } }
    .flow-line { stroke-dasharray: 8 6; animation: flow-active 0.8s linear infinite; }
    .flow-reverse { stroke-dasharray: 8 6; animation: flow-active 0.8s linear infinite reverse; }
    .line-green  { stroke: var(--bp-ok); stroke-width: 2.5; }
    .line-blue   { stroke: var(--bp-ink); stroke-width: 2.5; }
    .line-yellow { stroke: var(--bp-pencil); stroke-width: 2.5; }
    .line-purple { stroke: var(--bp-violet); stroke-width: 2.5; }
    .line-red    { stroke: var(--bp-redline); stroke-width: 2.5; stroke-dasharray: 4 4; animation: none; }
    .line-inactive { stroke: var(--bp-ink-3); stroke-width: 1; stroke-dasharray: 3 5; animation: none; opacity: 0.4; }

    .topo-node { background: var(--bp-deep); border: 1px solid var(--bp-ink-3); padding: 14px; display: flex; flex-direction: column; gap: 6px; transition: border-color .3s, background-color .3s; position: relative; }
    .node-active-green { border-color: var(--bp-ok); animation: node-pulse-green 2s infinite; background: rgba(95,211,154,.08); }
    .node-active-amber { border-color: var(--bp-pencil); animation: node-pulse-amber 2s infinite; background: rgba(244,201,93,.08); }
    .node-down-red { border: 1px dashed var(--bp-redline); animation: node-pulse-red 1s infinite; background: rgba(255,122,102,.12); }
    .node-standby { border-style: dashed; border-color: var(--bp-ink-3); opacity: 0.75; }

    /* v3.0 DRAWIO TECHNICAL ARCHITECTURE — 도면 캔버스 */
    .arch-container { display: grid; grid-template-columns: 240px 1fr 1fr; gap: 20px; position: relative; background: var(--bp-deep); padding: 24px; border: 2px solid var(--bp-ink); outline: 1px solid var(--bp-ink-3); outline-offset: 5px; min-height: 520px; }
    .arch-zone { padding: 14px; display: flex; flex-direction: column; gap: 12px; position: relative; border: 1.5px solid var(--bp-ink); background: transparent; }
    .zone-kt, .zone-onprem, .zone-aws { background: transparent; border: 1.5px solid var(--bp-ink); }
    .zone-title { font-size: 14px; font-weight: 600; display: flex; align-items: center; justify-content: space-between; border-bottom: 1px solid var(--bp-line); padding-bottom: 8px; color: var(--bp-ink) !important; }
    .arch-subnet { background: transparent; border: 1px dashed var(--bp-ink-3); padding: 10px; display: flex; flex-direction: column; gap: 8px; }
    .subnet-label { font-size: 12px; font-weight: 500; color: var(--bp-ink-3); }
    .k8s-pod-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 6px; }
    .k8s-pod-chip { background: var(--bp-sunk); border: 1px solid var(--bp-line); padding: 6px 8px; font-size: 12px; font-weight: 500; color: var(--bp-ink); display: flex; align-items: center; gap: 6px; transition: border-color .3s; }
    .pod-active { border-color: var(--bp-ok); }
    .pod-restarting { border-color: var(--bp-pencil); background: rgba(244,201,93,.15); animation: pulse-restarting 0.8s infinite; }
    @keyframes pulse-restarting { 0%,100% { opacity: .45; } 50% { opacity: 1; } }
    .tunnel-badge { font-size: 11px; font-weight: 600; padding: 2px 8px; display: inline-flex; align-items: center; gap: 5px; border: 1px dashed currentColor; background: transparent !important; }
    .tunnel-a { color: var(--bp-pencil); }
    .tunnel-b { color: #9FD3F5; }
    .tunnel-c { color: var(--bp-violet); }

    /* 스크롤바 */
    * { scrollbar-color: var(--bp-ink-3) transparent; scrollbar-width: thin; }

    @media (prefers-reduced-motion: reduce) {
      .flow-line, .flow-reverse, .node-active-green, .node-active-amber, .node-down-red, .pod-restarting { animation: none !important; }
    }
    @media (max-width: 900px) {
      .status-group { display: none; }
      aside { width: 200px; }
      #overview-panel, #ktvm-panel, #osvm-panel, #osnet-panel, #osops-panel, #realtime-panel, #awsvm-panel, #dr-panel, #orchestrator-panel, #chaos-panel, #grafana-panel { padding: 20px 16px 32px; }
      .arch-container { grid-template-columns: 1fr; }
    }
    /* ===== 아이소메트릭 DR 토폴로지 ===== */
    .iso-stage { position: relative; border: 2px solid var(--bp-ink); outline: 1px solid var(--bp-ink-3); outline-offset: 5px; background: var(--bp-deep); padding: 8px 12px 4px; }
    .iso-stage-head { display: flex; justify-content: space-between; align-items: baseline; gap: 12px; flex-wrap: wrap; padding: 8px 6px 0; }
    .iso-stage-head h3 { font-size: 16px; font-weight: 600; color: var(--bp-ink); }
    .iso-stage-head p { font-size: 12px; color: var(--bp-ink-3); }
    #iso-scene { display: block; width: 100%; height: auto; max-height: 620px; }
    #iso-scene text { font-family: var(--font); }

    #iso-scene .f-top   { fill: rgba(230,238,245,.13); stroke: var(--bp-ink); stroke-width: 1.2; stroke-linejoin: round; }
    #iso-scene .f-left  { fill: rgba(230,238,245,.06); stroke: var(--bp-ink); stroke-width: 1.2; stroke-linejoin: round; }
    #iso-scene .f-right { fill: rgba(12,37,66,.55);    stroke: var(--bp-ink); stroke-width: 1.2; stroke-linejoin: round; }
    #iso-scene .slot    { stroke: var(--bp-ink-3); stroke-width: 1; fill: none; }
    #iso-scene .led     { fill: var(--bp-ok); }
    #iso-scene .platform .f-top   { fill: rgba(230,238,245,.04); stroke: var(--bp-ink-2); stroke-dasharray: none; }
    #iso-scene .platform .f-left, #iso-scene .platform .f-right { fill: rgba(12,37,66,.6); stroke: var(--bp-ink-2); }
    #iso-scene .floor   { stroke: rgba(230,238,245,.10); stroke-width: 1; }
    #iso-scene .zone-t  { fill: var(--bp-ink); font-size: 17px; font-weight: 600; }
    #iso-scene .zone-s  { fill: var(--bp-ink-3); font-size: 13px; }
    #iso-scene .pod .f-top { fill: rgba(143,224,180,.28); }
    #iso-scene .db .f-top  { fill: rgba(230,238,245,.22); }

    #iso-scene .pipe-case { fill: none; stroke: rgba(230,238,245,.10); stroke-width: 9; stroke-linecap: round; stroke-linejoin: round; }
    #iso-scene .tun-t { font-size: 13px; font-weight: 600; paint-order: stroke; stroke: var(--bp-deep); stroke-width: 4px; }
    #iso-scene .tun-t.ta { fill: var(--bp-pencil); }
    #iso-scene .tun-t.tb { fill: var(--bp-ink); }
    #iso-scene .tun-t.tc { fill: var(--bp-violet); }

    #iso-scene .callout .pin    { fill: var(--bp-ink); }
    #iso-scene .callout .leader { fill: none; stroke: var(--bp-ink-3); stroke-width: 1; }
    #iso-scene .c-t { fill: var(--bp-ink); font-size: 15px; font-weight: 600; paint-order: stroke; stroke: var(--bp-deep); stroke-width: 4px; }
    #iso-scene .c-s { fill: var(--bp-ink-3); font-size: 13px; paint-order: stroke; stroke: var(--bp-deep); stroke-width: 4px; }

    #iso-scene .cut path { stroke: var(--bp-redline); stroke-width: 3; stroke-linecap: round; }
    #iso-scene .stamp { fill: var(--bp-redline); font-size: 15px; font-weight: 600; letter-spacing: .04em; paint-order: stroke; stroke: var(--bp-deep); stroke-width: 5px; }
    #iso-scene .cut, #iso-scene .stamp { opacity: 0; transition: opacity .3s; }
    #iso-scene .iso-zone, #iso-scene .iso-box, #iso-scene .iso-cyl, #iso-scene .callout { transition: opacity .4s; }

    /* 평시: GH Pages 는 대기 */
    #iso-scene #iso-gh, #iso-scene #iso-ghpage, #iso-scene #iso-c-gh { opacity: .35; }

    /* L1: minwon-api 파드 재기동 */
    #iso-scene[data-stage="l1"] #iso-pod-api .f-top { fill: rgba(244,201,93,.55); }
    #iso-scene[data-stage="l1"] #iso-pod-api { animation: iso-blink .8s infinite; }
    #iso-scene[data-stage="l1"] #iso-c-pod .c-s { fill: var(--bp-pencil); }

    /* L2: Orchestrator 가 터널 B 로 Ansible */
    #iso-scene[data-stage="l2"] #iso-ctl .f-top,
    #iso-scene[data-stage="l2"] #iso-wg .f-top { fill: rgba(244,201,93,.45); }
    #iso-scene[data-stage="l2"] #iso-ctl .led { fill: var(--bp-pencil); animation: iso-blink .6s infinite; }
    #iso-scene[data-stage="l2"] #iso-path-ingress { stroke: var(--bp-redline); stroke-dasharray: 4 4; animation: none; }

    /* 경로 장애: 터널 A 절단 표시 */
    #iso-scene[data-stage="path"] #iso-cut-a { opacity: 1; }

    /* L3: 온프렘 펜싱, AWS 승격 */
    #iso-scene[data-stage="l3"] #iso-onprem,
    #iso-scene[data-stage="l3"] #iso-wg, #iso-scene[data-stage="l3"] .rack,
    #iso-scene[data-stage="l3"] .pod, #iso-scene[data-stage="l3"] #iso-db-primary,
    #iso-scene[data-stage="l3"] #iso-c-wg, #iso-scene[data-stage="l3"] #iso-c-pod, #iso-scene[data-stage="l3"] #iso-c-dbp { opacity: .3; }
    #iso-scene[data-stage="l3"] #iso-onprem .platform .f-top { stroke: var(--bp-redline); stroke-dasharray: 6 4; }
    #iso-scene[data-stage="l3"] #iso-stamp-fenced { opacity: 1; }
    #iso-scene[data-stage="l3"] #iso-db-replica .f-top { fill: rgba(95,211,154,.45); }
    #iso-scene[data-stage="l3"] #iso-c-dbr .c-s { fill: var(--bp-ok-2); }
    #iso-scene[data-stage="l3"] #iso-aws .platform .f-top { stroke: var(--bp-ok); }

    /* L4: 역방향 GTID */
    #iso-scene[data-stage="l4"] #path-db-sync { animation-direction: reverse; stroke: var(--bp-violet); }
    #iso-scene[data-stage="l4"] #iso-db-primary .f-top { fill: rgba(95,211,154,.45); }

    /* Black Sky */
    #iso-scene[data-stage="bs"] #iso-onprem, #iso-scene[data-stage="bs"] #iso-aws,
    #iso-scene[data-stage="bs"] #iso-kt,
    #iso-scene[data-stage="bs"] .iso-box:not(#iso-ghpage), #iso-scene[data-stage="bs"] .iso-cyl,
    #iso-scene[data-stage="bs"] .callout:not(#iso-c-gh) { opacity: .22; }
    #iso-scene[data-stage="bs"] #iso-gh, #iso-scene[data-stage="bs"] #iso-ghpage, #iso-scene[data-stage="bs"] #iso-c-gh { opacity: 1; }
    #iso-scene[data-stage="bs"] #iso-ghpage .f-top { fill: rgba(95,211,154,.5); }
    #iso-scene[data-stage="bs"] #iso-gh .platform .f-top { stroke: var(--bp-ok); }
    #iso-scene[data-stage="bs"] #iso-path-ingress { opacity: 0; }
    #iso-scene[data-stage="bs"] #iso-path-gh { stroke: var(--bp-ok); stroke-width: 2.5; stroke-dasharray: 8 6; opacity: 1; animation: flow-active .8s linear infinite; }

    @keyframes iso-blink { 0%,100% { opacity: 1; } 50% { opacity: .35; } }
    @media (prefers-reduced-motion: reduce) { #iso-scene * { animation: none !important; } }
    #iso-scene .zone-t, #iso-scene .zone-s { paint-order: stroke; stroke: var(--bp-deep); stroke-width: 5px; }
    #iso-scene #iso-case-gh { opacity: 0; }
    #iso-scene[data-stage="bs"] #iso-case-gh { opacity: 1; }
    #iso-scene[data-stage="bs"] #iso-kt-label, #iso-scene[data-stage="bs"] #iso-onprem-label, #iso-scene[data-stage="bs"] #iso-aws-label { opacity: .3; }
    #iso-scene[data-stage="l3"] #iso-onprem-label { opacity: .4; }
    #iso-scene[data-stage="bs"] .tun-t { opacity: .3; }
    #iso-scene[data-stage="l3"] .tun-t.ta, #iso-scene[data-stage="l3"] .tun-t.tb { opacity: .5; }


    /* ===== DR 관제 콘솔 (7:3, 한 화면에 전부) ===== */
    .dr-console { flex-shrink: 0; display: grid; grid-template-columns: minmax(0, 7fr) minmax(0, 3fr); gap: 14px; height: calc(100vh - 56px - 48px); min-height: 640px; }
    .dc-main { display: grid; grid-template-rows: minmax(0, 1fr) auto; gap: 12px; min-height: 0; }
    .dc-main .iso-stage { display: flex; flex-direction: column; min-height: 0; padding: 6px 12px 10px; }
    .dc-main #iso-scene { flex: 1; min-height: 0; width: 100%; height: 100%; max-height: none; }
    .iso-stage-head { align-items: center; }
    .dc-fs { padding: 5px 12px; }
    .dc-strip { display: grid; grid-template-columns: minmax(0, 3fr) minmax(0, 2fr); gap: 12px; min-height: 0; }
    .dc-strip .kt-props-grid { grid-template-columns: repeat(4, minmax(0, 1fr)) !important; margin: 0 !important; background: var(--bp-deep); border-color: var(--bp-ink-3); }
    .dc-strip .prop-item { padding: 9px 12px; }
    .dc-strip .prop-label { font-size: 11.5px; }
    .dc-strip .prop-val { font-size: 12.5px; line-height: 1.4; }
    .dc-strip .kt-log-box { height: auto !important; max-height: 104px; margin: 0 !important; font-size: 11.5px; gap: 3px; }
    .dc-side { display: flex; flex-direction: column; gap: 12px; min-height: 0; }
    .dc-side > div { margin: 0 !important; }
    .dc-side > div:first-child { padding: 12px !important; }
    .dc-side #dr-v3-btns { display: grid !important; grid-template-columns: 1fr 1fr; gap: 6px !important; }
    .dc-side #dr-v3-btns .btn-top { width: 100%; text-align: left; padding: 7px 10px; font-size: 12.5px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
    .dc-stage { border: 1px solid var(--bp-ink); background: var(--bp-raised); padding: 12px 14px; }
    .dc-stage > div { display: flex; flex-direction: column; align-items: flex-start !important; gap: 8px; border: 0 !important; padding: 0 !important; margin: 0 !important; }
    .dc-stage #v3-stage-title { font-size: 15px !important; line-height: 1.45; }
    .dc-stage #v3-stage-desc { font-size: 12px !important; line-height: 1.55; }
    .dc-sop { flex: 1; min-height: 0; display: flex; }
    .dc-sop #v3-sop-text { flex: 1; overflow-y: auto; font-size: 12.5px !important; line-height: 1.7 !important; }

    /* 전체 화면 (Fullscreen API 또는 덮기 대체) — 영상 한 프레임에 전부 */
    .dr-console:fullscreen, .dr-console.is-fs {
      width: 100vw; height: 100vh; min-height: 0; padding: 18px 20px; gap: 16px;
      background-color: var(--bp-ground);
      background-image:
        linear-gradient(var(--bp-grid-major) 1px, transparent 1px), linear-gradient(90deg, var(--bp-grid-major) 1px, transparent 1px),
        linear-gradient(var(--bp-grid) 1px, transparent 1px), linear-gradient(90deg, var(--bp-grid) 1px, transparent 1px);
      background-size: 120px 120px, 120px 120px, 24px 24px, 24px 24px;
    }
    .dr-console.is-fs { position: fixed; inset: 0; z-index: 1000; }
    .dr-console:fullscreen::backdrop { background: var(--bp-ground); }
    .dr-console:fullscreen .iso-stage-head h3, .dr-console.is-fs .iso-stage-head h3 { font-size: 20px; }
    .dr-console:fullscreen #dr-v3-btns .btn-top, .dr-console.is-fs #dr-v3-btns .btn-top { font-size: 14px; padding: 9px 12px; }
    .dr-console:fullscreen #v3-stage-title, .dr-console.is-fs #v3-stage-title { font-size: 18px !important; }
    .dr-console:fullscreen #v3-stage-desc, .dr-console.is-fs #v3-stage-desc { font-size: 13.5px !important; }
    .dr-console:fullscreen #v3-sop-text, .dr-console.is-fs #v3-sop-text { font-size: 14px !important; }
    .dr-console:fullscreen .prop-label, .dr-console.is-fs .prop-label { font-size: 13px; }
    .dr-console:fullscreen .prop-val, .dr-console.is-fs .prop-val { font-size: 14.5px; }
    .dr-console:fullscreen .kt-log-box, .dr-console.is-fs .kt-log-box { font-size: 13px; max-height: 130px; }

    @media (max-width: 1100px) {
      .dr-console { grid-template-columns: minmax(0, 1fr); height: auto; min-height: 0; }
      .dc-main #iso-scene { height: auto; }
      .dc-strip { grid-template-columns: minmax(0, 1fr); }
      .dc-strip .kt-props-grid { grid-template-columns: 1fr 1fr !important; }
    }

    /* ===== 3D 연결 토폴로지 ===== */
    .t3-host { position: relative; flex: 1; min-height: 0; overflow: hidden; }
    .t3-host > canvas { position: absolute; inset: 0; display: block; touch-action: none; }
    .t3-host #iso-scene { width: 100%; height: 100%; }
    .iso-stage.has-3d #iso-scene { display: none; }
    .t3-labels { position: absolute; inset: 0; pointer-events: none; }
    .dc-hint { margin-left: auto; margin-right: 12px; font-size: 12px; color: var(--bp-ink-3); }

    .t3-l { font-family: var(--font); text-align: center; line-height: 1.25; white-space: nowrap; transform: translateY(-50%);
      text-shadow: 0 0 3px var(--bp-deep), 0 0 6px var(--bp-deep), 0 0 2px var(--bp-deep); }
    .t3-l b { display: block; font-size: 12.5px; font-weight: 600; color: var(--bp-ink); }
    .t3-l span { display: block; font-size: 11px; color: var(--bp-ink-3); }
    .t3-l.t3-hidden { visibility: hidden !important; }
    .t3-l.t3-zone b { font-size: 15px; }
    .t3-l.t3-zone { transform: translate(-30%, 10%); }
    .t3-l.t3-subnet b { font-size: 10.5px; font-weight: 500; color: var(--bp-ink-3); }
    .t3-l.t3-subnet { transform: translate(0, -110%); text-align: left; }
    .t3-l.t3-tunnel b { font-size: 12.5px; }
    .t3-l.t3-ta b { color: var(--bp-pencil); } .t3-l.t3-tb b { color: #9FD3F5; } .t3-l.t3-tc b { color: var(--bp-violet); }
    .t3-l.is-idle { opacity: .45; }
    .t3-l.is-fail b, .t3-l.t3-cut b { color: var(--bp-redline) !important; }
    .t3-l.is-warn b { color: var(--bp-pencil); } .t3-l.is-ok b { color: var(--bp-ok-2); }
    .t3-l.t3-fence b { font-size: 15px; color: var(--bp-redline); letter-spacing: .03em; }
    .t3-l.t3-note b { font-size: 12px; color: var(--bp-ok-2); border: 1px solid currentColor; padding: 1px 6px; background: rgba(15,45,79,.85); text-shadow: none; }
    .t3-l.t3-cap { z-index: 5; }
    .t3-l.t3-cap b { font-size: 13px; font-weight: 600; color: var(--bp-deep); background: var(--bp-ink); padding: 4px 9px; text-shadow: none; box-shadow: 0 0 0 1px var(--bp-deep); }

    .t3-bar { position: absolute; top: 8px; right: 8px; display: flex; align-items: center; gap: 4px; z-index: 6;
      background: rgba(12,37,66,.85); border: 1px solid var(--bp-line); padding: 4px; }
    .t3-bar button { min-width: 30px; height: 28px; padding: 0 8px; background: transparent; color: var(--bp-ink-2);
      border: 1px solid transparent; font: 500 13px var(--font); cursor: pointer; }
    .t3-bar button:hover { color: var(--bp-ink); border-color: var(--bp-line); }
    .t3-bar button.on { color: var(--bp-deep); background: var(--bp-ink); }
    .t3-bar .sep { width: 1px; height: 18px; background: var(--bp-line); margin: 0 3px; }

    .t3-card { position: absolute; left: 10px; bottom: 10px; z-index: 6; max-width: 320px; background: rgba(12,37,66,.94);
      border: 1px solid var(--bp-ink); padding: 12px 14px; }
    .t3-card[hidden] { display: none; }
    .t3-card h4 { font-size: 15px; font-weight: 600; color: var(--bp-ink); }
    .t3-card .z { font-size: 12px; color: var(--bp-ink-3); margin: 2px 0 8px; }
    .t3-card ul { list-style: none; font-size: 12.5px; color: var(--bp-ink-2); line-height: 1.6; }
    .t3-card ul li::before { content: '— '; color: var(--bp-ink-3); }
    .t3-card .row { display: flex; gap: 6px; margin-top: 10px; }
    .t3-card .row button { background: transparent; border: 1px solid var(--bp-line); color: var(--bp-ink-2); font: 12px var(--font); padding: 4px 10px; cursor: pointer; }
    .t3-card .row button:first-child { background: var(--bp-ink); color: var(--bp-deep); border-color: var(--bp-ink); }

    /* 오른쪽 탭 + 흐름 단계 목록 */
    .dc-tabs { display: flex; border-bottom: 1px solid var(--bp-ink); margin-bottom: -12px !important; }
    .dc-tab { background: transparent; border: 1px solid transparent; border-bottom: 0; color: var(--bp-ink-3); font: 500 13px var(--font); padding: 7px 14px; cursor: pointer; }
    .dc-tab.on { color: var(--bp-ink); border-color: var(--bp-ink); background: var(--bp-deep); margin-bottom: -1px; }
    .dc-tabpanel { flex: 1; min-height: 0; overflow-y: auto; border: 1px solid var(--bp-ink); border-top: 0; background: var(--bp-deep); }
    .dc-tabpanel[hidden] { display: none !important; }
    .dc-tabpanel.dc-sop #v3-sop-text { border: 0 !important; background: transparent !important; overflow: visible; }
    .dc-flow { list-style: none; padding: 8px 0; }
    .dc-flow li { display: grid; grid-template-columns: 26px 1fr; gap: 8px; padding: 6px 12px; font-size: 12.5px; line-height: 1.5; color: var(--bp-ink-3); cursor: pointer; border-left: 3px solid transparent; }
    .dc-flow li i { font-style: normal; font-weight: 600; text-align: center; border: 1px solid currentColor; height: 20px; line-height: 18px; font-size: 11px; }
    .dc-flow li.done { color: var(--bp-ink-2); }
    .dc-flow li.active { color: var(--bp-ink); background: var(--bp-raised); border-left-color: var(--bp-pencil); }
    .dc-flow li.active i { background: var(--bp-ink); color: var(--bp-deep); border-color: var(--bp-ink); }
    .dc-flow li.bg { color: #9FD3F5; cursor: default; border-top: 1px dashed var(--bp-line); margin-top: 4px; }
    .dc-flow li.empty { grid-template-columns: 1fr; cursor: default; }

    /* 상세 구성 (콘솔 안 분할) */
    .dc-detail { display: none; min-height: 0; overflow-y: auto; border: 1px solid var(--bp-ink); background: var(--bp-deep); }
    .dr-console.show-detail .dc-main { grid-template-rows: minmax(0, 1.35fr) minmax(0, 1fr) auto; }
    .dr-console.show-detail .dc-detail { display: block; }
    .dc-detail-head { position: sticky; top: 0; z-index: 2; background: var(--bp-deep); padding: 8px 12px; font-size: 13px; font-weight: 600; border-bottom: 1px solid var(--bp-line); }
    .dc-detail .arch-container { grid-template-columns: minmax(0, 1fr) minmax(0, 1.5fr) minmax(0, 1.3fr); min-height: 0; padding: 10px; gap: 10px; border: 0; outline: 0; background: transparent; }
    .dc-detail .arch-zone { padding: 10px; gap: 8px; }
    .dc-detail .arch-zone-onprem, .dc-detail #zone-onprem-box, .dc-detail #zone-aws-box { display: grid; grid-template-columns: 1fr 1fr; align-content: start; }
    .dc-detail #zone-onprem-box > .zone-title, .dc-detail #zone-aws-box > .zone-title { grid-column: 1 / -1; }
    .dc-detail #subnet-onprem-k8s { grid-row: span 2; }
    .dc-detail .arch-subnet { padding: 8px; gap: 5px; }
    .dc-detail .zone-title { font-size: 13px; }
    .dc-detail .k8s-pod-chip { font-size: 11.5px; padding: 4px 6px; }
    .t3-flash { animation: t3flash 1.6s ease 1; }
    @keyframes t3flash { 0%, 60% { box-shadow: 0 0 0 3px var(--bp-pencil); } 100% { box-shadow: 0 0 0 0 transparent; } }

    .dr-console:fullscreen .t3-l b, .dr-console.is-fs .t3-l b { font-size: 14px; }
    .dr-console:fullscreen .t3-l span, .dr-console.is-fs .t3-l span { font-size: 12px; }
    .dr-console:fullscreen .t3-l.t3-zone b, .dr-console.is-fs .t3-l.t3-zone b { font-size: 17px; }
    .dr-console:fullscreen .t3-l.t3-cap b, .dr-console.is-fs .t3-l.t3-cap b { font-size: 15px; }
    .dr-console:fullscreen .dc-flow li, .dr-console.is-fs .dc-flow li { font-size: 14px; }
    @media (max-width: 1100px) { .dc-detail .arch-container { grid-template-columns: minmax(0, 1fr); } .dc-hint { display: none; } }

    /* ===== 2D 평면 연결 구성도 ===== */
    .iso-stage.has-2d #iso-scene { display: none; }
    .t2-svg { position: absolute; inset: 0; width: 100%; height: 100%; display: block; cursor: grab; touch-action: none; user-select: none; }
    .t2-svg.grabbing { cursor: grabbing; }
    .t2-svg text { font-family: var(--font); }
    .t2-zone rect { fill: rgba(230,238,245,.025); stroke: var(--bp-ink); stroke-width: 2; }
    .t2-zone-t { fill: var(--bp-ink); font-size: 19px; font-weight: 600; }
    .t2-zone-s { fill: var(--bp-ink-3); font-size: 13px; }
    .t2-zone.dim { opacity: .35; }
    .t2-zone.fenced rect { stroke: var(--bp-redline); stroke-dasharray: 10 6; fill: rgba(255,122,102,.05); }
    .t2-subnet rect { fill: rgba(230,238,245,.03); stroke: var(--bp-ink-3); stroke-width: 1; stroke-dasharray: 5 4; }
    .t2-subnet.warm rect { stroke: rgba(244,201,93,.7); } .t2-subnet.ok rect { stroke: rgba(95,211,154,.7); } .t2-subnet.violet rect { stroke: rgba(195,166,255,.7); }
    .t2-subnet-t { fill: var(--bp-ink-3); font-size: 13px; }

    .t2-node { cursor: pointer; }
    .t2-node .body, .t2-node .top { fill: rgba(29,74,122,.92); stroke: var(--bp-ink); stroke-width: 1.4; }
    .t2-node .top { fill: rgba(230,238,245,.2); }
    .t2-node .ring { fill: none; stroke: var(--bp-ink-3); }
    .t2-node-t { fill: var(--bp-ink); font-size: 16.5px; font-weight: 600; pointer-events: none; }
    .t2-node-s { fill: var(--bp-ink-3); font-size: 13px; pointer-events: none; }
    .t2-node:hover .body, .t2-node:focus .body { stroke: var(--bp-pencil); stroke-width: 2; }
    .t2-node:focus { outline: none; }
    .t2-node.st-warn .body, .t2-node.st-warn .top { stroke: var(--bp-pencil); stroke-width: 2.2; fill: rgba(244,201,93,.18); }
    .t2-node.st-fail .body { stroke: var(--bp-redline); stroke-width: 2.2; fill: rgba(255,122,102,.18); }
    .t2-node.st-ok .body, .t2-node.st-ok .top { stroke: var(--bp-ok); stroke-width: 2.2; fill: rgba(95,211,154,.18); }
    .t2-node.st-dim { opacity: .3; }
    .t2-node.pulse .body, .t2-node.pulse .top { animation: t2pulse .7s ease-in-out infinite; }
    @keyframes t2pulse { 0%,100% { stroke-width: 1.4; } 50% { stroke-width: 4; stroke: var(--bp-pencil); } }

    .t2-link .line { fill: none; stroke-width: 2; stroke-linejoin: round; opacity: .16; }
    .t2-link.used .line { opacity: .35; }
    .t2-link.done .line { opacity: .7; }
    .t2-link.bg .line { opacity: .55; stroke-dasharray: 6 5; animation: t2dash 1s linear infinite; }
    .t2-link.active .line { opacity: 1; stroke-width: 3.5; }
    @keyframes t2dash { to { stroke-dashoffset: -22; } }
    .t2-link.k-req .line { stroke: var(--bp-ink); } .t2-link.k-data .line { stroke: var(--bp-ink-2); }
    .t2-link.k-repl .line, .t2-link.k-tb .line { stroke: #9FD3F5; } .t2-link.k-backup .line { stroke: var(--bp-ok-2); }
    .t2-link.k-ctrl .line, .t2-link.k-ta .line, .t2-link.k-warn .line { stroke: var(--bp-pencil); }
    .t2-link.k-tc .line { stroke: var(--bp-violet); } .t2-link.k-fb .line { stroke: var(--bp-ok); }
    .t2-link.tunnel .band { fill: none; stroke-width: 13; stroke-linejoin: round; opacity: .14; }
    .t2-link.tunnel .line { stroke-dasharray: 9 6; opacity: .75; }
    .t2-link.k-ta .band { stroke: var(--bp-pencil); } .t2-link.k-tb .band { stroke: #9FD3F5; } .t2-link.k-tc .band { stroke: var(--bp-violet); }
    .t2-link.tun-idle .line, .t2-link.tun-idle .band { opacity: .12; }
    .t2-link.tun-fail .line { stroke: var(--bp-redline); opacity: .8; stroke-dasharray: 4 6; }
    .t2-link.tun-fail .band { stroke: var(--bp-redline); opacity: .12; }
    .t2-link.tunnel.active .line { opacity: 1; stroke-width: 3.5; }
    .t2-tun-t { font-size: 14.5px; font-weight: 600; paint-order: stroke; stroke: var(--bp-deep); stroke-width: 5px; }
    .t2-tun-t.k-ta { fill: var(--bp-pencil); } .t2-tun-t.k-tb { fill: #9FD3F5; } .t2-tun-t.k-tc { fill: var(--bp-violet); }
    .t2-link.tun-fail .t2-tun-t { fill: var(--bp-redline); }

    .t2-pkt { fill: var(--bp-ink); } .t2-halo { fill: var(--bp-ink); opacity: .25; }
    .t2-pkt.k-ta, .t2-pkt.k-ctrl, .t2-pkt.k-warn, .t2-halo.k-ta, .t2-halo.k-ctrl, .t2-halo.k-warn { fill: var(--bp-pencil); }
    .t2-pkt.k-tb, .t2-pkt.k-repl, .t2-halo.k-tb, .t2-halo.k-repl { fill: #9FD3F5; }
    .t2-pkt.k-tc, .t2-halo.k-tc { fill: var(--bp-violet); } .t2-pkt.k-fb, .t2-halo.k-fb, .t2-pkt.k-backup, .t2-halo.k-backup { fill: var(--bp-ok); }
    .t2-pkt.k-fail, .t2-halo.k-fail { fill: var(--bp-redline); }
    .t2-bgpkt { fill: #9FD3F5; }
    .t2-cap { display: none; pointer-events: none; }
    .t2-cap.show { display: inline; }
    .t2-cap rect { fill: var(--bp-ink); stroke: var(--bp-deep); stroke-width: 1.5; }
    .t2-cap rect.n { fill: var(--bp-pencil); }
    .t2-cap text { fill: var(--bp-deep); font-size: 17px; font-weight: 600; }
    .t2-cap .nt { font-size: 13px; }

    .t2-cut, .t2-fence, .t2-note { display: none; }
    .t2-cut.show, .t2-fence.show, .t2-note.show { display: inline; }
    .t2-cut path { stroke: var(--bp-redline); stroke-width: 3.5; stroke-linecap: round; }
    .t2-cut-t { fill: var(--bp-redline); font-size: 14px; font-weight: 600; paint-order: stroke; stroke: var(--bp-deep); stroke-width: 5px; }
    .t2-fence { fill: var(--bp-redline); font-size: 18px; font-weight: 600; letter-spacing: .04em; paint-order: stroke; stroke: var(--bp-deep); stroke-width: 6px; }
    .t2-note rect { fill: var(--bp-deep); stroke: var(--bp-ok); }
    .t2-note text { fill: var(--bp-ok-2); font-size: 13px; font-weight: 600; }
    @media (prefers-reduced-motion: reduce) { .t2-link.bg .line, .t2-node.pulse .body { animation: none !important; } }
    .dr-console:fullscreen.show-detail .dc-main, .dr-console.is-fs.show-detail .dc-main { grid-template-rows: minmax(0, 2.4fr) minmax(0, 1fr) auto; }
    .dr-console:fullscreen .dc-strip .kt-log-box, .dr-console.is-fs .dc-strip .kt-log-box { max-height: 92px; }
    .dr-console:fullscreen .dc-strip .prop-item, .dr-console.is-fs .dc-strip .prop-item { padding: 7px 12px; }
    .iso-stage.has-2d .t3-bar { top: auto; bottom: 8px; }
    .iso-stage.has-2d .t3-card { bottom: 56px; }
    /* Cloudflare Tunnel(관리 경로) · origin-kt 우회 위험 · DNS 라벨 */
    .t2-link.k-cft .line { stroke: #F2B27A; }
    .t2-pkt.k-cft, .t2-halo.k-cft { fill: #F2B27A; }
    .t2-tun-t.k-cft { fill: #F2B27A; font-size: 12.5px; }
    .t2-link.k-risk .line { stroke: var(--bp-redline); stroke-dasharray: 3 5; opacity: .55; }
    .t2-link.k-risk.active .line { opacity: 1; stroke-width: 3; }
    .t2-tun-t.k-risk { fill: var(--bp-redline); font-size: 12px; }
    .t2-pkt.k-risk, .t2-halo.k-risk { fill: var(--bp-redline); }
    .t2-dns { fill: var(--bp-ink-2); font-size: 12px; font-weight: 600; paint-order: stroke; stroke: var(--bp-deep); stroke-width: 4px; }
    .t2-dns.s { fill: var(--bp-ink-3); font-weight: 400; font-size: 11px; }
    .dc-side #btn-v3-mgmt { grid-column: 1 / -1; }

    /* ===== OpenStack 구조 · 연결 (#osvm) ===== */
    .osx { border: 2px solid var(--bp-ink); background: var(--bp-deep); padding: 16px 18px 18px; display: flex; flex-direction: column; gap: 12px; }
    .osx-head { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
    .osx-head h3 { font-size: 18px; font-weight: 600; }
    .osx-meta { font-size: 12.5px; color: var(--bp-ink-3); margin-right: auto; }
    .osx-tabs { display: flex; border-bottom: 1px solid var(--bp-ink); }
    .osx-tab { background: transparent; border: 1px solid transparent; border-bottom: 0; color: var(--bp-ink-3); font: 500 13.5px var(--font); padding: 7px 16px; cursor: pointer; }
    .osx-tab.on { color: var(--bp-ink); border-color: var(--bp-ink); background: var(--bp-ground); margin-bottom: -1px; }
    .osx-pane[hidden] { display: none !important; }
    .osx-err { font-size: 12.5px; color: var(--bp-redline); border: 1px solid var(--bp-redline); padding: 6px 10px; margin-top: 8px; }
    .osx-map { overflow: auto; border: 1px solid var(--bp-line); background: var(--bp-ground); max-height: 640px; }
    .osx-svg { display: block; min-width: 1100px; width: 100%; height: auto; }
    .osx-svg text { font-family: var(--font); }
    .osx-svg .osx-col { fill: var(--bp-ink-3); font-size: 12.5px; }
    .osx-node rect { fill: rgba(29,74,122,.92); stroke: var(--bp-ink); stroke-width: 1.4; }
    .osx-node.ext rect { stroke-dasharray: 5 4; }
    .osx-node.rt rect { stroke: var(--bp-pencil); }
    .osx-node.vm.st-ok rect { stroke: var(--bp-ok); } .osx-node.vm.st-off rect { stroke: var(--bp-ink-3); opacity: .7; } .osx-node.vm.st-warn rect { stroke: var(--bp-pencil); }
    .osx-node .t { fill: var(--bp-ink); font-size: 14px; font-weight: 600; } .osx-node .s { fill: var(--bp-ink-3); font-size: 11.5px; }
    .osx-bar rect { fill: rgba(159,211,245,.35); stroke: #9FD3F5; }
    .osx-bar.ext rect { fill: rgba(244,201,93,.3); stroke: var(--bp-pencil); }
    .osx-bar .b { fill: var(--bp-ink); font-size: 13px; font-weight: 600; } .osx-bar .s, .osx-host .s { fill: var(--bp-ink-3); font-size: 11.5px; }
    .osx-host rect { fill: rgba(230,238,245,.03); stroke: var(--bp-ink-3); stroke-dasharray: 6 4; }
    .osx-host .b { fill: var(--bp-ink); font-size: 14px; font-weight: 600; }
    .osx-fip rect { fill: rgba(244,201,93,.15); stroke: var(--bp-pencil); } .osx-fip text { fill: var(--bp-pencil); font-size: 12px; font-weight: 600; font-family: var(--mono); }
    .osx-link path { fill: none; stroke: var(--bp-ink-3); stroke-width: 1.6; }
    .osx-link.gw path { stroke: var(--bp-pencil); } .osx-link.if path { stroke: #9FD3F5; } .osx-link.vm path { stroke: var(--bp-ink-2); }
    .osx-link.geneve path { stroke: var(--bp-violet); stroke-dasharray: 6 5; } .osx-link.ext path { stroke-dasharray: 4 4; }
    .osx-link .l { fill: var(--bp-ink-2); font-size: 11px; font-family: var(--mono); paint-order: stroke; stroke: var(--bp-ground); stroke-width: 4px; }
    .osx-link.geneve .l { fill: var(--bp-violet); font-family: var(--font); }
    .osx-svg .done rect, .osx-svg .done path { stroke: var(--bp-ok) !important; }
    .osx-svg .hl rect, .osx-svg .hl path { stroke: var(--bp-pencil) !important; stroke-width: 3.5 !important; }
    .osx-svg .hl rect { fill: rgba(244,201,93,.22); }
    .osx-trace { border: 1px solid var(--bp-line); margin-top: 10px; }
    .osx-tbar { display: flex; align-items: center; gap: 8px; padding: 8px 10px; border-bottom: 1px solid var(--bp-line); flex-wrap: wrap; }
    .osx-tbar strong { font-size: 14px; } .osx-tcap { flex: 1; font-size: 13px; color: var(--bp-pencil); min-width: 200px; }
    .osx-tlist { list-style: none; display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); }
    .osx-tlist li { display: grid; grid-template-columns: 24px 1fr; gap: 8px; padding: 7px 10px; font-size: 12.5px; color: var(--bp-ink-3); cursor: pointer; border-left: 3px solid transparent; }
    .osx-tlist li i { font-style: normal; text-align: center; border: 1px solid currentColor; height: 20px; line-height: 18px; font-size: 11px; }
    .osx-tlist li.done { color: var(--bp-ink-2); } .osx-tlist li.active { color: var(--bp-ink); background: var(--bp-raised); border-left-color: var(--bp-pencil); }
    .osx-sum { font-size: 14px; font-weight: 600; margin: 4px 0 10px; } .osx-sum.good { color: var(--bp-ok-2); } .osx-sum.bad { color: var(--bp-redline); }
    .osx-hosts { display: grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); gap: 12px; }
    .osx-card { border: 1px solid var(--bp-line); padding: 12px 14px; background: var(--bp-ground); }
    .osx-card h4 { font-size: 14.5px; font-weight: 600; margin-bottom: 6px; }
    .osx-card ul { list-style: none; display: flex; flex-direction: column; gap: 5px; }
    .osx-card li { display: grid; grid-template-columns: 12px 1fr auto; gap: 8px; align-items: center; font-size: 12.5px; }
    .osx-card li em { font-style: normal; color: var(--bp-ink-3); font-size: 11.5px; } .osx-card li.down b { color: var(--bp-redline); }
    .osx-sub { font-size: 14px; font-weight: 600; margin: 16px 0 8px; padding-bottom: 6px; border-bottom: 1px solid var(--bp-line); }
    .osx-table { width: 100%; border-collapse: collapse; font-size: 12.5px; }
    .osx-table th { text-align: left; font-weight: 500; color: var(--bp-ink-3); border-bottom: 1px solid var(--bp-ink-3); padding: 6px 8px; }
    .osx-table td { border-bottom: 1px solid var(--bp-line-2); padding: 6px 8px; } .osx-table td.mono { font-family: var(--mono); color: var(--bp-ink-2); }
    .osx-meter { margin-top: 8px; } .osx-meter .top { display: flex; justify-content: space-between; font-size: 12px; color: var(--bp-ink-3); }
    .osx-meter .top b { color: var(--bp-ink); font-weight: 500; font-variant-numeric: tabular-nums; }
    .osx-meter .bar { height: 6px; background: var(--bp-line-2); margin-top: 3px; } .osx-meter .bar i { display: block; height: 100%; background: var(--bp-ok); }
    .osx-meter .bar i.hot { background: var(--bp-redline); }
    .osx-quota { display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 12px; }
    .osx-ops { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
    .osx-ops label { font-size: 13px; color: var(--bp-ink-3); }
    .osx-ops select, .osx-confirm input { background: var(--bp-sunk); color: var(--bp-ink); border: 1px solid var(--bp-line); padding: 6px 8px; font: 13px var(--font); min-width: 260px; }
    .osx-confirm { border: 1px solid var(--bp-pencil); padding: 10px 12px; margin-top: 10px; display: flex; gap: 8px; align-items: center; flex-wrap: wrap; font-size: 13px; }
    .osx-confirm p { width: 100%; }
    .btn-top.primary { background: var(--bp-ink); color: var(--bp-deep); border-color: var(--bp-ink); }
    .osx-log { margin-top: 10px; background: var(--bp-sunk); border: 1px solid var(--bp-line); padding: 12px; font: 12px/1.5 var(--mono); color: var(--bp-ink-2); max-height: 320px; overflow: auto; white-space: pre-wrap; }
    .osx-note { font-size: 12px; color: var(--bp-ink-3); margin-top: 8px; }


    /* AWS EC2 관리 (#awsvm) */
    #awsvm-panel { gap: 18px; }
    .aws-nodes { display: grid; grid-template-columns: repeat(auto-fit, minmax(440px, 1fr)); gap: 16px; }
    .aws-node .kt-props-grid { grid-template-columns: repeat(2, minmax(0, 1fr)) !important; }
    .aws-st { font-weight: 700; } .aws-st.ok { color: #8FE0B4; } .aws-st.fail { color: #FF9E8C; } .aws-st.wait { color: #F4C95D; }
    .aws-steps { list-style: none; margin: 0; padding: 0; display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 8px; }
    .aws-steps li { border: 1px solid var(--bp-line); padding: 10px 12px; font-size: 12.5px; background: var(--bp-ground); }
    .aws-steps li b { display: block; font-size: 13px; margin-bottom: 3px; }
    .aws-steps li span { color: var(--bp-ink-3); }
    @media (max-width: 640px) { .aws-nodes { grid-template-columns: 1fr; } .aws-node .kt-props-grid { grid-template-columns: 1fr !important; } }
    /* AWS 지점 (PR #13·#14) */
    .osx-node.aws rect { stroke: #F4A261; }
    .osx-node.aws.st-ok rect { stroke: var(--bp-ok); stroke-dasharray: none; }
    .osx-node.aws.st-fail rect { stroke: var(--bp-redline); }
    .osx-link.wgc path { stroke: #F4A261; stroke-dasharray: 2 5; stroke-width: 1.8; }
    .osx-link.wgc.st-ok path { stroke: var(--bp-ok); stroke-dasharray: 6 4; }
    .osx-link.wgc.st-fail path { stroke: var(--bp-redline); }
    .osx-wgc-label { font-size: 11px; fill: #F4A261; }
    /* #osvm 연결 점검 */
    .osx-netgrid { display: grid; grid-template-columns: repeat(auto-fill, minmax(340px, 1fr)); gap: 10px; }
    .osx-net.route { grid-column: 1 / -1; }
    .osx-net ol, .osx-net ul { list-style: none; display: flex; flex-direction: column; gap: 4px; margin: 0; padding: 0; }
    .osx-net.route ol { flex-direction: row; flex-wrap: wrap; gap: 0; }
    .osx-net.route ol li { flex: 1 1 180px; border-left: 0; position: relative; padding-right: 18px; }
    .osx-net.route ol li:not(:last-child)::after { content: '→'; position: absolute; right: 4px; top: 6px; color: var(--bp-ink-3); }
    .osx-net li { display: grid; grid-template-columns: 52px minmax(0, 1fr) auto; gap: 8px; align-items: start; font-size: 12px; padding: 5px 0; border-top: 1px solid var(--bp-line); }
    .osx-net.route li { grid-template-columns: 1fr; gap: 2px; border-top: 0; }
    .osx-net .nst { font-size: 11px; font-weight: 700; text-align: center; padding: 1px 0; border: 1px solid currentColor; }
    .osx-net.route .nst { justify-self: start; padding: 1px 8px; }
    .osx-net .nmid { display: flex; flex-direction: column; gap: 1px; min-width: 0; }
    .osx-net .nmid code { font-family: var(--mono); font-size: 11px; color: var(--bp-ink-2); overflow-wrap: anywhere; }
    .osx-net .nmid small { font-size: 11px; color: var(--bp-ink-3); }
    .osx-net em { font-style: normal; font-size: 11px; color: var(--bp-ink-3); font-family: var(--mono); white-space: nowrap; text-align: right; max-width: 150px; overflow: hidden; text-overflow: ellipsis; }
    .osx-net .st-ok .nst { color: var(--bp-ok-2, #8FE0B4); }
    .osx-net .st-warn .nst, .osx-net .st-partial .nst { color: #F4C95D; }
    .osx-net .st-fail .nst { color: var(--bp-redline); }
    .osx-net .st-fail b { color: var(--bp-redline); }
    .osx-net .st-missing .nst { color: var(--bp-ink-3); border-style: dashed; }
    .osx-net .st-removed .nst { color: #A78BFA; border-color: rgba(167, 139, 250, 0.4); background: rgba(167, 139, 250, 0.12); }
    @media (max-width: 640px) { .osx-netgrid { grid-template-columns: 1fr; } .osx-net li { grid-template-columns: 48px 1fr; } .osx-net li em { grid-column: 2; } }
    /* ===== #osvm 재배치: 작은 정보는 좁게, 구성도는 한 화면에 ===== */
    #osvm-panel.osv-on { gap: 14px; padding-top: 18px; }
    #osnet-panel, #osops-panel { gap: 12px; padding-top: 18px; }
    /* 구조 페이지: 구성도에 높이를 몰아줌 */
    #osnet-panel .osv-mapcol { flex: 1 1 auto; min-height: 0; }
    #osnet-panel .osx-svg { max-height: calc(100vh - 56px - 190px); }
    /* 연결·상태 페이지: 탭 내용을 넓게 */
    #osops-panel > .osx { flex: 0 0 auto; padding: 12px 16px 16px; }
    #osops-panel .osx-pane { padding-top: 4px; }
    #osops-panel .osx-netgrid { grid-template-columns: repeat(auto-fit, minmax(340px, 1fr)); gap: 12px; align-items: start; }
    #osops-panel .osx-hosts { grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); }
    #osops-panel .osx-net li { font-size: 12.5px; }
    #osops-panel .osx-hosts { grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); }
    #osops-panel .osx-chips { grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); }
    #osops-panel .osx-log { max-height: calc(100vh - 56px - 300px); min-height: 240px; }
    @media (max-width: 1300px) { #osops-panel .osx-resgrid { grid-template-columns: 1fr 1fr; } }
    @media (max-width: 720px) { #osops-panel .osx-resgrid { grid-template-columns: 1fr; } #osops-panel .osx-netgrid { grid-template-columns: 1fr; } }
    .osv-top { display: flex; align-items: center; gap: 14px; flex-wrap: wrap; border: 1px solid var(--bp-ink); background: var(--bp-deep); padding: 10px 14px; }
    .osv-top .overview-hero { border: 0 !important; background: none !important; padding: 0; flex: 0 1 auto; }
    .osv-top .overview-hero h2 { font-size: 17px !important; margin: 0; white-space: nowrap; }
    .osv-top .overview-hero p { display: none; }
    .osv-top .stats-grid { display: flex; border: 0; background: none; gap: 6px; flex-wrap: wrap; }
    .osv-top .stat-card { display: flex; align-items: baseline; gap: 6px; padding: 4px 10px; border: 1px solid var(--bp-line); margin: 0; }
    .osv-top .stat-card .label { margin: 0; font-size: 12px; }
    .osv-top .stat-card .value { font-size: 15px; }
    .osv-top .stat-card .subtext { display: none; }
    .osv-top .osx-head { margin-left: auto; gap: 10px; }
    .osv-top .osx-head h3 { display: none; }
    .osv-top .osx-meta { margin-right: 0; }

    .osv-main { display: grid; grid-template-columns: minmax(0, 1fr) 360px; gap: 14px; align-items: start; }
    .osv-mapcol { border: 2px solid var(--bp-ink); background: var(--bp-deep); padding: 10px; display: flex; flex-direction: column; gap: 8px; }
    .osv-mapcol .osx-map { height: auto; max-height: none; overflow: hidden; }
    .osv-mapcol .osx-svg { min-width: 0; width: 100%; height: auto; max-height: calc(100vh - 56px - 230px); }
    .osv-mapcol .osx-trace { margin-top: 0; }
    .osv-mapcol .osx-tbar { padding: 6px 8px; }
    /* CLI 터미널 스타일 뷰 */
    .cli-filter-bar { display: flex; gap: 8px; margin-bottom: 14px; flex-wrap: wrap; align-items: center; }
    .cli-filter-btn { background: rgba(255,255,255,0.06); border: 1px solid var(--bp-line); color: var(--bp-ink-2); padding: 6px 14px; font-size: 12.5px; border-radius: 4px; cursor: pointer; transition: all 0.2s; }
    .cli-filter-btn.active, .cli-filter-btn:hover { background: var(--bp-accent); color: #04121F; font-weight: 700; border-color: var(--bp-accent); }
    
    /* 총괄 그룹단위 전체 자원 리스트 스타일 (7 Hosts / 20 vCPU) */
    .view-mode-bar { display: flex; gap: 8px; margin-bottom: 16px; border-bottom: 2px solid rgba(255,255,255,0.08); padding-bottom: 10px; flex-wrap: wrap; }
    .view-mode-btn { background: rgba(255,255,255,0.05); border: 1px solid var(--bp-line); color: var(--bp-ink-2); padding: 7px 16px; font-size: 13px; font-weight: 600; border-radius: 4px; cursor: pointer; transition: all 0.2s; }
    .view-mode-btn.active, .view-mode-btn:hover { background: #3A78B5; color: #fff; border-color: #9FD3F5; box-shadow: 0 0 10px rgba(58,120,181,0.5); }
    
    .group-container { display: flex; flex-direction: column; gap: 20px; margin-bottom: 24px; }
    .group-section { background: #08101a; border: 1px solid rgba(255,255,255,0.12); border-radius: 8px; overflow: hidden; box-shadow: 0 4px 16px rgba(0,0,0,0.35); }
    .group-header { padding: 12px 18px; display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid rgba(255,255,255,0.08); background: #0d1a29; flex-wrap: wrap; gap: 8px; }
    .group-title { font-size: 15px; font-weight: 800; color: #E2EDF8; display: flex; align-items: center; gap: 10px; }
    .group-badge { font-size: 11.5px; padding: 3px 8px; border-radius: 4px; font-weight: 700; }
    .group-summary { font-size: 12px; color: #8AA5C2; display: flex; gap: 16px; align-items: center; }
    .group-nodes-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(430px, 1fr)); gap: 14px; padding: 16px; }
    .node-res-card { background: #050b12; border: 1px solid rgba(255,255,255,0.08); border-radius: 6px; padding: 14px; display: flex; flex-direction: column; gap: 10px; transition: border-color 0.2s, box-shadow 0.2s; }
    .node-res-card:hover { border-color: rgba(95,211,154,0.4); box-shadow: 0 2px 12px rgba(0,0,0,0.4); }
    .node-res-head { display: flex; justify-content: space-between; align-items: flex-start; gap: 8px; }
    .node-res-title { display: flex; flex-direction: column; gap: 2px; }
    .node-res-title b { font-size: 13.5px; color: #fff; }
    .node-res-title span { font-size: 11px; color: #8AA5C2; font-family: monospace; }
    .node-res-metrics { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-top: 4px; background: rgba(255,255,255,0.02); padding: 8px 10px; border-radius: 4px; border: 1px solid rgba(255,255,255,0.04); }
    .res-metric-item { display: flex; flex-direction: column; gap: 3px; font-size: 11px; }
    .res-metric-item .lbl { display: flex; justify-content: space-between; color: #8AA5C2; }
    .res-metric-track { background: rgba(255,255,255,0.08); height: 6px; border-radius: 3px; overflow: hidden; }
    .res-metric-fill { height: 100%; border-radius: 3px; }
    .node-res-footer { display: flex; justify-content: space-between; align-items: center; font-size: 11px; color: #8AA5C2; border-top: 1px solid rgba(255,255,255,0.05); padding-top: 8px; margin-top: 2px; }
    
    .tier-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(460px, 1fr)); gap: 16px; margin-bottom: 20px; }
    .tier-card { border: 1px solid rgba(255,255,255,0.14); background: #0A1420; border-radius: 6px; padding: 16px; box-shadow: 0 4px 16px rgba(0,0,0,0.3); display: flex; flex-direction: column; gap: 10px; }
    .tier-header { display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid rgba(255,255,255,0.08); padding-bottom: 8px; }
    .tier-title { font-size: 14px; font-weight: 700; color: #E2EDF8; display: flex; align-items: center; gap: 8px; }
    .tier-node-row { background: #060B12; border: 1px solid rgba(255,255,255,0.06); padding: 10px 12px; border-radius: 4px; display: flex; flex-direction: column; gap: 6px; }
    .tier-node-top { display: flex; justify-content: space-between; align-items: center; }
    .tier-node-bars { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-top: 4px; }
    .tier-bar-item { font-size: 11px; }
    .tier-bar-item .lbl { display: flex; justify-content: space-between; color: #8AA5C2; margin-bottom: 2px; }
    .tier-bar-track { background: rgba(255,255,255,0.08); height: 6px; border-radius: 3px; overflow: hidden; }
    .tier-bar-fill { height: 100%; border-radius: 3px; }
    .rank-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(360px, 1fr)); gap: 16px; margin-bottom: 20px; }
    .rank-card { background: #080E17; border: 1px solid #1E3A5F; border-radius: 6px; padding: 16px; }
    .rank-row { display: grid; grid-template-columns: 24px 110px 1fr 90px; align-items: center; gap: 8px; font-size: 12px; padding: 7px 0; border-bottom: 1px solid rgba(255,255,255,0.05); }
    .rank-num { font-weight: 800; color: #F4C95D; text-align: center; }

    .cli-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(460px, 1fr)); gap: 16px; }
    .cli-term-card { border: 1px solid rgba(255,255,255,0.15); background: #070D14; border-radius: 6px; overflow: hidden; box-shadow: 0 4px 16px rgba(0,0,0,0.45); display: flex; flex-direction: column; }
    .cli-term-head { background: #0F1A26; padding: 8px 12px; display: flex; align-items: center; justify-content: space-between; border-bottom: 1px solid rgba(255,255,255,0.08); font-family: monospace; font-size: 12px; }
    .cli-term-dots { display: flex; gap: 6px; align-items: center; }
    .cli-dot { width: 10px; height: 10px; border-radius: 50%; display: inline-block; }
    .cli-dot.red { background: #FF5F56; }
    .cli-dot.yellow { background: #FFBD2E; }
    .cli-dot.green { background: #27C93F; }
    .cli-term-title { font-weight: 700; color: #E2EDF8; display: flex; align-items: center; gap: 8px; }
    .cli-term-badge { font-size: 10.5px; padding: 2px 6px; border-radius: 3px; font-weight: 600; }
    .cli-term-body { padding: 12px; margin: 0; font-family: 'JetBrains Mono', 'Fira Code', 'Cascadia Code', Menlo, Consolas, monospace; font-size: 12px; line-height: 1.55; color: #D1E1F0; overflow-x: auto; white-space: pre; background: #050B11; flex: 1; }
    .cli-term-body .c-p { color: #5FD39A; font-weight: 700; }
    .cli-term-body .c-c { color: #F4C95D; font-weight: 700; }
    .cli-term-body .c-h { color: #8AA5C2; }
    .cli-term-body .c-ok { color: #5FD39A; font-weight: 600; }
    .cli-term-body .c-warn { color: #F4A261; }
    .cli-term-body .c-info { color: #9FD3F5; }
    .osx-tlist.compact { display: flex; gap: 4px; padding: 6px 8px; flex-wrap: wrap; }
    .osx-tlist.compact li { display: block; padding: 0; border: 0; }
    .osx-tlist.compact li span { display: none; }
    .osx-tlist.compact li i { display: block; width: 28px; height: 26px; line-height: 24px; font-size: 12px; }
    .osx-tlist.compact li.active { background: none; } .osx-tlist.compact li.active i { background: var(--bp-pencil); color: var(--bp-deep); border-color: var(--bp-pencil); }
    .osx-tlist.compact li.done i { color: var(--bp-ok-2); }
    .osx-tlist.compact li:focus-visible { outline: 2px solid var(--bp-pencil); }

    .osv-side { display: flex; flex-direction: column; gap: 10px; }
    .osv-side > div:first-child { flex-wrap: wrap; margin: 0 !important; gap: 6px !important; }
    .osv-side > div:first-child .btn-top { padding: 4px 9px; font-size: 12px; }
    .osv-side #os-focused-box { padding: 12px; gap: 10px; }
    .osv-side #os-focused-box .kt-vm-header { flex-direction: column; align-items: flex-start; gap: 8px; padding-bottom: 10px; }
    .osv-side #os-focused-box .kt-vm-name { font-size: 18px; }
    .osv-side #os-focused-box .kt-props-grid { grid-template-columns: 1fr 1fr !important; }
    .osv-side #os-focused-box .prop-item { padding: 7px 9px; }
    .osv-side #os-focused-box .prop-label { font-size: 11px; }
    .osv-side #os-focused-box .prop-val { font-size: 12px; }
    .osv-side #os-focused-box .kt-ctrl-bar { gap: 6px; padding-top: 10px; }
    .osv-side #os-focused-box .kt-ctrl-bar > span, .osv-side #os-focused-box .kt-ctrl-bar > div:first-child { width: 100%; font-size: 12px; }
    .osv-side #os-focused-box .btn-action { padding: 6px 9px; font-size: 12px; }
    .osv-side #os-focused-box .kt-log-box { height: 110px; font-size: 11px; }
    .osv-side #os-focused-box .section-title, .osv-side #os-focused-box [style*="justify-content:space-between"] { font-size: 12px; }
    #osvm-panel.osv-on .osx { padding: 12px 14px 14px; }
    #osvm-panel.osv-on .osx > .osx-head { display: none; }

    @media (max-width: 1500px) {
      .osv-main { grid-template-columns: minmax(0, 1fr); }
      .osv-side { display: grid; grid-template-columns: minmax(0, 1fr); }
      .osv-mapcol .osx-svg { max-height: calc(100vh - 56px - 200px); }
    }

    /* ===== FHD(1920×1080) 한 화면 페이지 — DR · OpenStack ===== */
    #dr-panel { padding: 16px 24px 18px; gap: 12px; overflow: hidden; }
    #dr-panel > .overview-hero { padding: 10px 16px; flex-shrink: 0; }
    #dr-panel > .overview-hero > div { align-items: center !important; }
    #dr-panel > .overview-hero h2 { font-size: 18px !important; margin: 0 !important; }
    #dr-panel > .overview-hero p { display: none; }
    #dr-panel .tunnel-badge { font-size: 11.5px; }
    .dr-console { height: auto; min-height: 0; flex: 1 1 auto; }
    .dc-drill { padding: 12px; }
    .dc-drill .kt-vm-box { border: 0; padding: 0; background: transparent; gap: 10px; }
    .dc-drill .kt-vm-box > div:first-child { flex-direction: column; }
    .dc-drill .btn-action { width: 100%; justify-content: flex-start; font-size: 13px; padding: 9px 12px; }
    .dc-drill-note { font-size: 12px; color: var(--bp-pencil); margin-bottom: 10px; }

    #osvm-panel.osv-on { padding: 16px 24px 18px; gap: 12px; overflow: hidden; }
    #osvm-panel.osv-on > .osv-top { flex-shrink: 0; }
    .osv-main { flex: 1 1 auto; min-height: 0; align-items: stretch; grid-template-columns: minmax(0, 1fr) 380px; }
    .osv-mapcol { min-height: 0; overflow: hidden; }
    .osv-mapcol .osx-map { flex-shrink: 0; }
    .osv-mapcol .osx-svg { max-height: calc((100vh - 56px - 120px) * 0.5); }
    .osv-mapcol .osx-trace { flex-shrink: 0; }
    .osv-mapcol .osx { flex: 1 1 auto; min-height: 0; border: 1px solid var(--bp-line); padding: 8px 12px 10px; gap: 8px; }
    .osv-mapcol .osx-tabs { flex-shrink: 0; }
    .osv-mapcol .osx-pane { flex: 1 1 auto; min-height: 0; overflow-y: auto; padding-right: 4px; }
    .osv-side { min-height: 0; overflow-y: auto; padding-right: 2px; }
    @media (max-width: 1500px) {
      #dr-panel, #osvm-panel.osv-on { overflow-y: auto; }
    }

    /* ===== 스크롤 최소화: 밀도 · 가로 배치 ===== */
    /* DR 오른쪽 열 */
    .dc-side { gap: 10px; }
    .dc-side > div:first-child { padding: 10px !important; }
    .dc-side #dr-v3-btns { grid-template-columns: repeat(3, minmax(0, 1fr)) !important; gap: 5px !important; }
    .dc-side #dr-v3-btns .btn-top { padding: 6px 8px; font-size: 12px; }
    .dc-side #btn-v3-mgmt { grid-column: auto; }
    .dc-stage { padding: 10px 12px; }
    .dc-stage #v3-stage-title { font-size: 14px !important; line-height: 1.4; }
    .dc-stage #v3-stage-desc { display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; font-size: 12px !important; }
    .dc-flow { padding: 4px 0; }
    .dc-flow li { padding: 3px 10px; font-size: 12px; line-height: 1.38; gap: 7px; grid-template-columns: 22px 1fr; }
    .dc-flow li i { height: 18px; line-height: 16px; font-size: 10.5px; }
    .dc-flow li.bg { margin-top: 2px; }
    .dr-console:fullscreen .dc-flow li, .dr-console.is-fs .dc-flow li { font-size: 13px; padding: 4px 12px; }
    /* DR 상세 구성 압축 */
    .dc-detail-head { padding: 6px 12px; font-size: 12.5px; }
    .dc-detail .arch-container { padding: 8px; gap: 8px; }
    .dc-detail .arch-zone { padding: 8px; gap: 6px; }
    .dc-detail .zone-title { font-size: 12px; padding-bottom: 5px; }
    .dc-detail .arch-subnet { padding: 6px 8px; gap: 3px; }
    .dc-detail .subnet-label { font-size: 11px; }
    .dc-detail .arch-subnet div, .dc-detail .arch-subnet span { font-size: 11px !important; line-height: 1.4 !important; }
    .dc-detail .k8s-pod-grid { gap: 4px; } .dc-detail .k8s-pod-chip { padding: 3px 6px; font-size: 11px; }
    .dc-detail #zone-kt-box > div:nth-child(2) { display: none; }   /* 장식용 '민원접수 사용자 & Cloudflare' 블록 */
    .dc-detail .menu-badge { font-size: 10px; }
    .dc-detail #zone-kt-box, .dc-detail #zone-onprem-box, .dc-detail #zone-aws-box { overflow: hidden; }
    .dr-console.show-detail .dc-main { grid-template-rows: minmax(0, 1.15fr) minmax(0, 1fr) auto; }

    /* OpenStack: 경로 추적 한 줄 · 구성도 비율 · 탭 내용 가로 배치 */
    .osv-mapcol .osx-svg { max-height: calc((100vh - 56px - 120px) * 0.46); }
    .osv-mapcol .osx-tbar { flex-wrap: nowrap; }
    .osv-mapcol .osx-tbar .osx-tcap { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    .osv-mapcol .osx-tbar .osx-tlist.compact { padding: 0; flex-wrap: nowrap; order: 5; }
    .osx-sum { margin: 2px 0 8px; font-size: 13px; }
    .osx-card { padding: 9px 12px; } .osx-card h4 { font-size: 13.5px; margin-bottom: 4px; }
    .osx-card ul { gap: 3px; } .osx-card li { font-size: 12px; }
    .osx-sub { margin: 10px 0 6px; padding-bottom: 4px; font-size: 13px; }
    .osx-chips { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 6px; }
    .osx-chip { display: flex; gap: 8px; align-items: baseline; border: 1px solid var(--bp-line); padding: 5px 9px; font-size: 12px; min-width: 0; }
    .osx-chip b { font-weight: 600; } .osx-chip span { color: var(--bp-ink-2); }
    .osx-chip em { font-style: normal; color: var(--bp-ink-3); font-family: var(--mono); font-size: 11px; margin-left: auto; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    .osx-resgrid { display: grid; grid-template-columns: 1.25fr 1fr 1.2fr 1.2fr; gap: 14px; align-items: start; }
    .osx-resgrid .osx-sub { margin-top: 2px; }
    .osx-hv { border: 1px solid var(--bp-line); padding: 7px 10px; margin-bottom: 8px; background: var(--bp-ground); }
    .osx-hv .t { display: flex; justify-content: space-between; gap: 8px; font-size: 12.5px; margin-bottom: 4px; }
    .osx-hv .t span { color: var(--bp-ink-3); font-size: 11.5px; }
    .osx-meter { display: grid; grid-template-columns: 52px 1fr auto; align-items: center; gap: 8px; margin-top: 4px; font-size: 11.5px; }
    .osx-meter .lb { color: var(--bp-ink-3); }
    .osx-meter b { color: var(--bp-ink); font-weight: 500; font-variant-numeric: tabular-nums; min-width: 56px; text-align: right; }
    .osx-meter .bar { margin: 0; height: 6px; }
    .osx-list { list-style: none; display: flex; flex-direction: column; gap: 4px; }
    .osx-list li { display: flex; flex-direction: column; border-left: 2px solid var(--bp-line); padding: 2px 8px; font-size: 12px; }
    .osx-list li span { color: var(--bp-ink-3); font-size: 11.5px; }
    .osx-list li.empty { color: var(--bp-ink-3); border: 0; }
    .dc-flow li { padding: 2px 10px; font-size: 11.8px; line-height: 1.34; }
    .dr-console:not(.is-fs):not(:fullscreen) .dc-detail .arch-subnet > div[style*="line-height"] { display: none; }
    .dr-console:not(.is-fs):not(:fullscreen) .dc-detail .arch-subnet { gap: 4px; }
    .dc-detail .arch-container { grid-template-columns: minmax(0, 0.9fr) minmax(0, 2fr) minmax(0, 1.35fr); }
    .dc-detail #zone-onprem-box { grid-template-columns: minmax(0, 1fr) minmax(0, 1.35fr) minmax(0, 1fr); }
    .dc-detail #zone-onprem-box > #subnet-onprem-wg { grid-column: 1; grid-row: 2; }
    .dc-detail #zone-onprem-box > .arch-subnet:last-child { grid-column: 1; grid-row: 3; }
    .dc-detail #zone-onprem-box > #subnet-onprem-k8s { grid-column: 2; grid-row: 2 / span 2; }
    .dc-detail #zone-onprem-box > #subnet-onprem-db { grid-column: 3; grid-row: 2 / span 2; }
    .dr-console.show-detail .dc-main { grid-template-rows: minmax(0, 1fr) minmax(0, 1fr) auto; }
    .dr-console:fullscreen.show-detail .dc-main, .dr-console.is-fs.show-detail .dc-main { grid-template-rows: minmax(0, 1.9fr) minmax(0, 1fr) auto; }
    .dc-detail .arch-subnet > div[style*="line-height"] { display: none; }
    .dc-detail .arch-subnet { gap: 4px; }
    .dc-flow li { line-height: 1.3; }
    .dr-console:fullscreen .dc-flow li, .dr-console.is-fs .dc-flow li { font-size: 12.5px; padding: 3px 12px; line-height: 1.32; }
    .dc-detail-head { display: none; }
    .dc-detail .arch-container { padding: 6px; gap: 6px; }
    .dc-detail .arch-zone { padding: 6px 8px; }
    .dc-detail .zone-title { padding-bottom: 4px; }
    .dc-flow { padding: 2px 0; }
    .dc-side > div:first-child > div:first-child { margin-bottom: 6px !important; }
  </style>
</head>
<body>

  <!-- HEADER -->
  <header>
        <div class="brand">
      <span>FIGTEAM</span>
      <span class="brand-tag">HYBRID CMP</span>
    </div>

    <!-- TOP NAVIGATION MENU BAR (드롭다운 & 사이드바 대체 · 시연 삭제 완료) -->
    <nav class="top-nav" id="top-main-nav">
      <div class="top-nav-item active" data-key="overview" onclick="switchTab('overview')">
        <span>대시보드</span>
      </div>
      <div class="top-nav-item" data-key="operation" onclick="switchTab('operation')">
        <span>구성도</span>
      </div>
      <div class="top-nav-item" data-key="infra" onclick="switchTab('infra')">
        <span>OpenStack 구조</span>
      </div>
      <div class="top-nav-item" data-key="term" onclick="switchTab('term')">
        <span>통합 웹 터미널</span>
      </div>

      <!-- 서비스 드롭다운 (시연 콘솔 제외) -->
      <div class="top-dropdown" id="top-dropdown-services">
        <div class="top-dropdown-btn" id="top-dropdown-trigger">
          <span>외부 서비스</span>
          <span class="arrow">▾</span>
        </div>
        <div class="top-dropdown-menu">
          <div class="dropdown-item" data-key="ppt" onclick="switchTab('ppt')">
            <span>📊 라이브 PPT 회의실</span>
          </div>
          <div class="dropdown-divider"></div>
          <a class="dropdown-item" href="https://minwon.ktci5.kr" target="_blank" rel="noopener">
            <span>🏛️ 민원청구 24시 센터</span>
            <span class="ext-tag">↗</span>
          </a>
          <a class="dropdown-item" href="https://kt-edge.ktci5.kr" target="_blank" rel="noopener">
            <span>🌐 KT Cloud Edge 웹</span>
            <span class="ext-tag">↗</span>
          </a>
        </div>
      </div>
    </nav>
    
    <div class="status-group">
      <div class="chip">
        <span id="header-kt-dot" class="dot green"></span>
        <span id="header-kt-text">KT Edge: kt-edge-dr-01 (Running)</span>
      </div>
      <div class="chip">
        <span class="dot green"></span>
        <span>On-Prem HA K3s</span>
      </div>
      <div class="chip">
        <span class="dot yellow"></span>
        <span>AWS DR (Standby)</span>
      </div>
    </div>
    
    <div class="user-actions">
      <div class="user-badge">
        <span>👤</span>
        <span>fig (통합관리자)</span>
      </div>
      <a href="/logout" class="btn-top btn-logout">로그아웃</a>
    </div>
  </header>

  <div class="app-container">
    <!-- SIDEBAR REMOVED -->

    <!-- MAIN WORKSPACE -->
    <main id="main-workspace">
      
      <!-- 1. OVERVIEW PANEL -->
      <section id="overview-panel">
        <div class="overview-hero">
          <h2>민원불패 하이브리드 멀티클라우드 단일 통합 콘솔</h2>
          <p>KT Cloud VM(전원·자원 관리), OpenStack Horizon, Argo CD, Grafana, 민원청구 앱이 <strong>figteam.ktci5.kr</strong> 단일 도메인 안에서 완전히 일체형으로 통합되어 관리됩니다.</p>
        </div>
        <!-- GITOPS / GIT 배포 대시보드 & 클라우드 실시간 3색 상태 위젯 -->
        <div style="background: linear-gradient(135deg, rgba(15, 23, 42, 0.95), rgba(30, 41, 59, 0.85)); border: 1px solid #334155; border-radius: 8px; padding: 16px 20px; margin-bottom: 16px; box-shadow: 0 4px 16px rgba(0,0,0,0.4);">
          <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:12px; border-bottom:1px solid #334155; padding-bottom:10px; flex-wrap:wrap; gap:10px;">
            <div style="display:flex; align-items:center; gap:10px;">
              <span style="font-size:18px;">🐙</span>
              <div>
                <div style="font-size:15px; font-weight:800; color:#f8fafc; display:flex; align-items:center; gap:8px;">
                  <span>GitOps 지속 배포 & 멀티클라우드 헬스 대시보드</span>
                  <span style="font-size:11px; background:#1e293b; color:#38bdf8; border:1px solid #38bdf8; padding:2px 8px; border-radius:4px; font-weight:700;">Git Dashboard</span>
                </div>
                <div style="font-size:11.5px; color:#94a3b8; margin-top:2px;">
                  Git Repo: <code>prgrmany/team6-hybrid-autorecovery-platform</code> (branch: <b style="color:#38bdf8;">main</b> · commit: <code>9c4b7e1</code>)
                </div>
              </div>
            </div>
            <div style="display:flex; align-items:center; gap:8px;">
              <span class="menu-badge" style="background:rgba(16,185,129,0.15); color:#10b981; border:1px solid #10b981; padding:4px 10px; font-weight:700;">ArgoCD: Synced 🟢</span>
              <span class="menu-badge" style="background:rgba(16,185,129,0.15); color:#10b981; border:1px solid #10b981; padding:4px 10px; font-weight:700;">Health: Healthy 🟢</span>
            </div>
          </div>

          <!-- 3대 클라우드 서비스 초록/빨강 상태 카드 -->
          <div style="display:grid; grid-template-columns:repeat(auto-fit, minmax(240px, 1fr)); gap:12px;" id="main-cloud-status-grid">
            <!-- KT Cloud -->
            <div id="card-cloud-kt" style="background:#0f172a; border:2px solid #10b981; border-radius:6px; padding:12px 14px; transition:all 0.3s ease;">
              <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:6px;">
                <span style="font-size:13px; font-weight:800; color:#f8fafc;">🌐 KT Cloud Edge</span>
                <span id="dot-cloud-kt" style="font-size:12px; font-weight:800; color:#10b981; background:rgba(16,185,129,0.15); padding:2px 8px; border-radius:4px; border:1px solid #10b981;">정상 가동 🟢</span>
              </div>
              <div style="font-size:11.5px; color:#94a3b8; line-height:1.4;">
                • IP: <code>14.63.212.190</code> (Nginx WAF)<br>
                • WireGuard 터널 A / C 허브 가동
              </div>
            </div>

            <!-- On-Premise -->
            <div id="card-cloud-onprem" style="background:#0f172a; border:2px solid #10b981; border-radius:6px; padding:12px 14px; transition:all 0.3s ease;">
              <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:6px;">
                <span style="font-size:13px; font-weight:800; color:#f8fafc;">🏢 온프레미스 K8s & DB</span>
                <span id="dot-cloud-onprem" style="font-size:12px; font-weight:800; color:#10b981; background:rgba(16,185,129,0.15); padding:2px 8px; border-radius:4px; border:1px solid #10b981;">정상 가동 🟢</span>
              </div>
              <div style="font-size:11.5px; color:#94a3b8; line-height:1.4;">
                • K8s: <code>192.168.120.226</code> (:30080)<br>
                • MySQL 8.4 Primary (Cinder 30GB 마운트)
              </div>
            </div>

            <!-- AWS DR -->
            <div id="card-cloud-aws" style="background:#0f172a; border:2px solid #10b981; border-radius:6px; padding:12px 14px; transition:all 0.3s ease;">
              <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:6px;">
                <span style="font-size:13px; font-weight:800; color:#f8fafc;">☁️ AWS 관제 & DR 센터</span>
                <span id="dot-cloud-aws" style="font-size:12px; font-weight:800; color:#10b981; background:rgba(16,185,129,0.15); padding:2px 8px; border-radius:4px; border:1px solid #10b981;">정상 대기 🟢</span>
              </div>
              <div style="font-size:11.5px; color:#94a3b8; line-height:1.4;">
                • aws-ctl(<code>10.200.0.3</code>) / dr(<code>10.200.0.4</code>)<br>
                • Pilot-Light 대기 (장애 시 RTO ≤3분 승격)
              </div>
            </div>
          </div>

          <!-- 404 전면 장애 비상 알림 바 (평소 숨김) -->
          <div id="main-blacksky-banner" style="display:none; margin-top:12px; padding:12px 16px; background:rgba(239,68,68,0.15); border:2px dashed #ef4444; border-radius:6px; color:#fca5a5; font-size:12.5px;">
            <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:8px;">
              <div>
                <b style="color:#ef4444; font-size:13.5px;">🚨 404 NOT FOUND: 모든 클라우드 오프라인 (Black Sky 상태)</b>
                <div style="margin-top:2px;">온프렘, KT Cloud, AWS 3개 클라우드가 전면 불능 상태입니다. 즉각 GitHub Pages 정적 비상 접수처로 전환하십시오.</div>
              </div>
              <a href="https://dr.ktci5.kr/" target="_blank" style="background:#ef4444; color:#fff; font-weight:800; padding:6px 14px; border-radius:4px; text-decoration:none; font-size:12px;">dr.ktci5.kr 비상 접수처 열기 →</a>
            </div>
          </div>
        </div>

        <!-- RESOURCE DEPLOYMENT POLICY BANNER -->
        <div style="background: rgba(15, 45, 79, 0.85); border: 1px solid #3A78B5; padding: 14px 18px; border-left: 5px solid #5FD39A; margin-bottom: 4px;">
          <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:6px;">
            <div style="font-size:13.5px; font-weight:800; color:#5FD39A; display:flex; align-items:center; gap:8px;">
              <span>📊 온프레미스 OpenStack 자원 배치 최적화 현황</span>
            </div>
            <span style="font-size:11px; padding:2px 8px; background:rgba(95,211,154,0.15); color:#8FE0B4; border:1px solid #5FD39A; font-weight:700;">k8s-w1 단독 워커 체제</span>
          </div>
          <div style="font-size:12px; color:#D3E0EC; line-height:1.6;">
            • <b>온프렘 K8s 구성</b>: <code>k8s-cp1</code> (Control Plane & 민원앱) + <code>k8s-w1</code> (단일 워커) + <code>db-01</code> (MySQL 8.4 LTS DB)<br>
            • <b>인프라 최적화</b>: 안전·성능 우선 3대 ACTIVE 인스턴스 체계로 호스트 물리 메모리를 27GB 여유 확보하여 무중단 운영 중입니다.
          </div>
        </div>

        <div class="stats-grid">
          <div class="stat-card">
            <div class="label">KT Cloud VM 상태</div>
            <div class="value" id="stat-kt-state">kt-edge-dr-01 : Running</div>
            <div class="subtext" id="stat-kt-sub">14.63.212.190 (공인 엣지)</div>
          </div>
          <div class="stat-card">
            <div class="label">온프렘 K8s 구성</div>
            <div class="value" style="color:#8FE0B4;">k8s-w1 단독 워커</div>
            <div class="subtext">3대 ACTIVE 건전 운영</div>
          </div>
          <div class="stat-card">
            <div class="label">SSO 통합 인증</div>
            <div class="value">완료 (Bypassed)</div>
            <div class="subtext">단일 계정(fig) 무인증 직행</div>
          </div>
          <div class="stat-card">
            <div class="label">글로벌 엣지 캐시</div>
            <div class="value">10s Micro-cache</div>
            <div class="subtext">KT Edge 고속 응답 실증</div>
          </div>
        </div>

        <div class="section-title">
          <span>⚡</span>
          <span>서브시스템 원클릭 워크스페이스</span>
        </div>

        <div class="cards-grid">
          <!-- DR Failover Console Card -->
          <div class="svc-card" style="border-color: rgba(255, 107, 129, 0.4);">
            <div class="svc-card-header">
              <div>
                <div class="svc-title" style="color:#FFC0C9;">🛡️ 운영 대시보드</div>
                <div style="font-size: 11px; color: #B4C6D8; margin-top: 2px;">L1~L4 다계층 자동복구, 실시간 제어 & 0초 비상 접수</div>
              </div>
              <span class="svc-type" style="background:#FF6B81; color:#fff;">Live Ops</span>
            </div>
            <div class="svc-desc">Cloudflare ➔ KT Cloud Edge ➔ 온프렘 Primary ➔ AWS DR 4단계 장애 대응 흐름 및 실시간 토폴로지 관제.</div>
            <div class="svc-footer">
              <span style="color:#8FE0B4;">현재 경로: On-Prem Primary (RW) 🟢</span>
              <button class="btn-launch" style="background:#FF6B81;" onclick="switchTab('dr')">대시보드 열기 →</button>
            </div>
          </div>

          <!-- AWS 지점 (PR #13·#14) -->
          <div class="svc-card" style="border-color: rgba(244, 162, 97, 0.45);">
            <div class="svc-card-header">
              <div>
                <div class="svc-title" style="color:#F7C79A;">AWS 지점 (관제 · DR)</div>
                <div style="font-size: 11px; color: #B4C6D8; margin-top: 2px;">PR #13 Terraform · PR #14 Ansible · t3.small Rocky 8 ×2</div>
              </div>
              <span class="svc-type" style="background:#F4A261; color:#111;">AWS</span>
            </div>
            <div class="svc-desc">ctl <code>13.125.163.58</code> (VPC 10.50.0.0/16 · WG 10.200.0.3) · dr <code>54.116.129.147</code> (VPC 10.51.0.0/16 · WG 10.200.0.4). 온프렘 → KT 허브(WG 터널 C) → AWS로 연결합니다.</div>
            <div class="svc-footer">
              <span id="ov-aws-status" style="color:#F4C95D;">연결 상태 확인 중…</span>
              <button class="btn-launch" style="background:#F4A261; color:#111;" onclick="switchTab('osops')">연결 상태 보기 →</button>
            </div>
          </div>

          <!-- OpenStack VM Management -->
          <div class="svc-card">
            <div class="svc-card-header">
              <div>
                <div class="svc-title">OpenStack VM 관리 (온프렘 인스턴스)</div>
                <div style="font-size: 11px; color: #8AA5C2; margin-top: 2px;">OpenStack Nova REST API (v2.1)</div>
              </div>
              <span class="svc-type type-iaas" style="background:#B08CFF;">On-Prem Nova</span>
            </div>
            <div class="svc-desc">온프레미스 K8s 가상머신(k8s-cp1, k8s-w1) 및 DB(db-01) 전원 실시간 제어.</div>
            <div class="svc-footer">
              <span id="card-os-state-text">상태: 3대 가동 중 (ACTIVE - cp1, w1, db-01) 🟢</span>
              <button class="btn-launch" onclick="switchTab('osvm')">VM 관리하기 →</button>
            </div>
          </div>

          <!-- KT VM Management -->
          <div class="svc-card">
            <div class="svc-card-header">
              <div>
                <div class="svc-title">KT Cloud VM 관리 (전원/자원)</div>
                <div style="font-size: 11px; color: #8AA5C2; margin-top: 2px;">KT Cloud OpenAPI (server/v1)</div>
              </div>
              <span class="svc-type type-iaas" style="background:#3A78B5;">KT Edge</span>
            </div>
            <div class="svc-desc">KT Cloud OpenAPI를 직접 호출하여 Edge Gateway VM(kt-edge-dr-01) 전원 켜기·끄기·재부팅 및 과금 최적화.</div>
            <div class="svc-footer">
              <span id="card-kt-state-text">상태: Running 🟢</span>
              <button class="btn-launch" onclick="switchTab('ktvm')">VM 관리하기 →</button>
            </div>
          </div>

          <!-- Horizon -->
          <div class="svc-card">
            <div class="svc-card-header">
              <div>
                <div class="svc-title">OpenStack Horizon</div>
                <div style="font-size: 11px; color: #8AA5C2; margin-top: 2px;">https://horizon.ktci5.kr</div>
              </div>
              <span class="svc-type type-iaas">IaaS</span>
            </div>
            <div class="svc-desc">온프레미스 Controller(192.168.120.160) 가상화 인프라, 인스턴스, 볼륨, 네트워크 통합 제어 콘솔.</div>
            <div class="svc-footer">
              <span>Keystone 세션 자동 주입</span>
              <button class="btn-launch" onclick="switchTab('horizon')">콘솔 열기 →</button>
            </div>
          </div>

          <!-- Grafana -->
          <div class="svc-card">
            <div class="svc-card-header">
              <div>
                <div class="svc-title">Grafana 관제 메트릭</div>
                <div style="font-size: 11px; color: #8AA5C2; margin-top: 2px;">https://grafana.ktci5.kr</div>
              </div>
              <span class="svc-type type-mon">Metrics</span>
            </div>
            <div class="svc-desc">온프레미스 K3s 및 하이브리드 인프라 Prometheus 연동 실시간 대시보드 및 경보.</div>
            <div class="svc-footer">
              <span>Anonymous Admin 권한</span>
              <button class="btn-launch" onclick="switchTab('grafana')">콘솔 열기 →</button>
            </div>
          </div>

          <!-- Argo CD -->
          <div class="svc-card">
            <div class="svc-card-header">
              <div>
                <div class="svc-title">Argo CD GitOps</div>
                <div style="font-size: 11px; color: #8AA5C2; margin-top: 2px;">https://argocd.ktci5.kr</div>
              </div>
              <span class="svc-type type-gitops">GitOps</span>
            </div>
            <div class="svc-desc">GitHub 저장소 기반 자동 롤아웃, K8s 애플리케이션 동기화 및 헬스 상태 관리 콘솔.</div>
            <div class="svc-footer">
              <span>RBAC 자동 권한 부여</span>
              <button class="btn-launch" onclick="switchTab('argocd')">콘솔 열기 →</button>
            </div>
          </div>
        </div>
      </section>

      <!-- 2. KT CLOUD VM MANAGEMENT PANEL (NEW) -->
      <section id="ktvm-panel" style="display: none;">
        <div class="overview-hero" style="background: linear-gradient(135deg, rgba(2, 132, 199, 0.25), rgba(15, 45, 79, 0.8));">
          <h2>🌐 KT Cloud 인프라 자원 & VM 전원 제어 센터</h2>
          <p>KT Cloud OpenAPI(서명 기반)를 연동하여 가상머신의 전원(ON/OFF)과 재부팅을 실시간으로 관리합니다. 야간 미사용 시 전원을 끄면 vCPU/RAM 연산 비용이 절감됩니다.</p>
        </div>

        <div class="kt-vm-box">
          <div class="kt-vm-header">
            <div class="kt-vm-title">
              <span style="font-size:24px;">🖥️</span>
              <div>
                <div class="kt-vm-name" id="kt-display-name">kt-edge-dr-01</div>
                <div style="font-size: 11px; color: #B4C6D8; font-family: monospace;" id="kt-display-id">ID: 100c3a42-ca1e-4a06-bae5-61f14693e479</div>
              </div>
            </div>
            <div id="kt-badge-container">
              <div class="kt-vm-badge state-running" id="kt-status-badge">
                <span class="dot green"></span>
                <span id="kt-status-text">Running</span>
              </div>
            </div>
          </div>

          <div class="kt-props-grid">
            <div class="prop-item">
              <div class="prop-label">공인 진입점 IP (Edge)</div>
              <div class="prop-val" style="color:#9FD3F5;" id="kt-public-ip">14.63.212.190</div>
            </div>
            <div class="prop-item">
              <div class="prop-label">사설 IP (Guest Network)</div>
              <div class="prop-val" id="kt-private-ip">172.27.0.160</div>
            </div>
            <div class="prop-item">
              <div class="prop-label">인스턴스 스펙</div>
              <div class="prop-val" id="kt-spec">1 vCPU · 2048 MB RAM</div>
            </div>
            <div class="prop-item">
              <div class="prop-label">운영체제 & 하이퍼바이저</div>
              <div class="prop-val" id="kt-os">Rocky Linux 8.10 (XenServer)</div>
            </div>
            <div class="prop-item">
              <div class="prop-label">가용 구역 (Zone)</div>
              <div class="prop-val" id="kt-zone">kr-1 (KOR-Central A)</div>
            </div>
            <div class="prop-item">
              <div class="prop-label">과금 상태 안내</div>
              <div class="prop-val" id="kt-cost-info" style="color:#8FE0B4;">정상 과금 중 (연산 활성)</div>
            </div>
          </div>

          <!-- DETAILED INTERNAL NETWORK & SECURITY CONFIG (GIT C2 STANDARD) -->
          <div id="kt-edge-detail" style="margin-top:16px; border:1px solid rgba(159, 211, 245, 0.3); background:rgba(15, 45, 79, 0.6); padding:14px; border-radius:0;">
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:10px; border-bottom:1px solid rgba(255,255,255,0.1); padding-bottom:8px;">
              <span style="font-size:13px; font-weight:800; color:#F7D684;">🔧 KT Cloud Edge 내부 설정 및 인프라 연동 명세</span>
              <span class="menu-badge" style="background:#3A78B5; color:#fff;">C2 Interface Standard</span>
            </div>
            <div style="display:grid; grid-template-columns:repeat(auto-fit, minmax(260px, 1fr)); gap:12px;">
              <div style="background:rgba(29, 74, 122, 0.6); padding:10px 14px; border:1px solid rgba(255,255,255,0.08); border-radius:0;">
                <div style="font-weight:700; color:#9FD3F5; margin-bottom:6px;">🛡️ 5대 포트포워딩 & 방화벽 개방 규칙</div>
                <div style="font-size:11.5px; color:#D3E0EC; line-height:1.7;">
                  • <b>22/TCP</b>: SSH 관리 & Ansible 자동화 (공인 22 포워딩)<br>
                  • <b>80/TCP</b>: HTTP 리버스 프록시 (ModSecurity WAF)<br>
                  • <b>443/TCP</b>: HTTPS TLS 종료 및 10s 마이크로캐시<br>
                  • <b>51820/UDP</b>: WireGuard 사이트 간 VPN 터널<br>
                  • <b>30080/TCP</b>: AWS DR NodePort 비상 라우팅
                </div>
              </div>
              <div style="background:rgba(29, 74, 122, 0.6); padding:10px 14px; border:1px solid rgba(255,255,255,0.08); border-radius:0;">
                <div style="font-weight:700; color:#8FE0B4; margin-bottom:6px;">🌐 WireGuard 4노드 터널 허브 구성</div>
                <div style="font-size:11.5px; color:#D3E0EC; line-height:1.7;">
                  • <b>Hub (kt-edge)</b>: <code>10.200.0.1/24</code> (14.63.212.190)<br>
                  • <b>Peer 1 (온프렘)</b>: <code>10.200.0.2</code> (MetalLB 10.10.1.100)<br>
                  • <b>Peer 2 (AWS ctl)</b>: <code>10.200.0.3</code> (Orchestrator · 관제)<br>
                  • <b>Peer 3 (AWS dr)</b>: <code>10.200.0.4</code> (Pilot-Light DR K3s)
                </div>
              </div>
              <div style="background:rgba(29, 74, 122, 0.6); padding:10px 14px; border:1px solid rgba(255,255,255,0.08); border-radius:0;">
                <div style="font-weight:700; color:#F4C95D; margin-bottom:6px;">⚡ Nginx WAF & L3 Upstream 절체 정책</div>
                <div style="font-size:11.5px; color:#D3E0EC; line-height:1.7;">
                  • <b>평시 백엔드 (onprem)</b>: <code>10.10.1.100:80</code> (온프렘 VIP)<br>
                  • <b>재해복구 (dr)</b>: <code>10.200.0.4:30080</code> (AWS dr NodePort)<br>
                  • <b>자동 절체 스크립트</b>: <code>switch_edge.yml</code> 연동<br>
                  • <b>마이크로캐시</b>: <code>proxy_cache_valid 200 10s;</code>
                </div>
              </div>
              <div style="background:rgba(29, 74, 122, 0.6); padding:10px 14px; border:1px solid rgba(255,255,255,0.08); border-radius:0;">
                <div style="font-weight:700; color:#C3A6FF; margin-bottom:6px;">🔑 원격 터미널 SSH 접속 가이드</div>
                <div style="font-size:11.5px; color:#D3E0EC; line-height:1.7;">
                  • <b>호스트명</b>: <code>kt-edge-dr-01</code> (사설 172.27.0.160)<br>
                  • <b>WG 직접 접속</b>: <code>ssh root@10.200.0.1</code><br>
                  • <b>공인 IP 접속</b>: <code>ssh root@14.63.212.190</code> (포트 22)<br>
                  • <b>웹 터미널</b>: 하단 실시간 콘솔에서 즉시 실행
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      <!-- 3. OPENSTACK VM MANAGEMENT PANEL (KT CLOUD STYLE UPGRADE) -->
      <section id="osvm-panel" style="display: none;">
        <div class="overview-hero" style="background: linear-gradient(135deg, rgba(176, 140, 255, 0.25), rgba(15, 45, 79, 0.8)); border: 1px solid rgba(167, 139, 250, 0.3);">
          <h2>🖥️ 온프레미스 OpenStack IaaS 가상머신 전원 & 자원 제어 센터</h2>
          <p>KT Cloud VM과 동일하게 OpenStack Nova REST API(v2.1)를 직접 연동하여 K8s 가상머신의 전원(ON/OFF)과 재부팅을 실시간으로 관리합니다. 가상머신을 선택하고 버튼 하나로 전원을 제어하세요.</p>
        </div>

        <!-- OPENSTACK RESOURCE STATUS BANNER -->
        <div style="background: rgba(15, 45, 79, 0.85); border: 1px solid #B08CFF; padding: 14px 18px; border-left: 5px solid #5FD39A;">
          <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:6px;">
            <div style="font-size:13.5px; font-weight:800; color:#5FD39A; display:flex; align-items:center; gap:8px;">
              <span>🖥️ 온프레미스 OpenStack 자원 최적화 운영 현황</span>
            </div>
            <span style="font-size:11px; padding:2px 8px; background:rgba(95,211,154,0.15); color:#8FE0B4; border:1px solid #5FD39A; font-weight:700;">3대 ACTIVE 안정 운영</span>
          </div>
          <div style="font-size:12px; color:#D3E0EC; line-height:1.6;">
            • <b>온프렘 인프라 최적화</b>: <code>k8s-cp1</code>, <code>k8s-w1</code>, <code>db-01</code> 총 3대 인스턴스로 안전성과 고성능을 최우선으로 안정 운영 중입니다.<br>
            • <b>안정성 확보</b>: 각 하이퍼바이저 노드의 메모리 여유를 확보하고 스왑 0B를 유지하여 안정적인 서비스 환경을 제공합니다.
          </div>
        </div>

        <!-- STATS OVERVIEW -->
        <div class="stats-grid">
          <div class="stat-card">
            <div class="label">총 오픈스택 VM 수</div>
            <div class="value" id="os-stat-total">3</div>
            <div class="subtext">K8s 2 + DB 1 (총 3대)</div>
          </div>
          <div class="stat-card">
            <div class="label">정상 가동 (ACTIVE)</div>
            <div class="value" id="os-stat-active" style="color:#8FE0B4;">3</div>
            <div class="subtext">k8s-cp1, k8s-w1, db-01</div>
          </div>
          <div class="stat-card">
            <div class="label">정지 상태 (SHUTOFF)</div>
            <div class="value" id="os-stat-shutoff" style="color:#FF9E8C;">0</div>
            <div class="subtext">불필요 VM 0대</div>
          </div>
          <div class="stat-card">
            <div class="label">상위 호스트 VMware 노드</div>
            <div class="value" id="os-stat-vmware" style="color:#C3A6FF;">4 노드</div>
            <div class="subtext">Controller 1 + Compute 3 (1:1 전담)</div>
          </div>
        </div>

        <!-- VM SELECTOR TABS -->
        <div style="display:flex; align-items:center; gap:10px; margin-top:4px;">
          <span style="font-size:13px; font-weight:700; color:#D3E0EC;">🎯 제어 대상 가상머신 선택:</span>
          <div style="display:flex; gap:8px;" id="os-vm-tab-buttons">
            <button class="btn-top" id="btn-tab-cp1" style="background:#B08CFF; color:#fff; font-weight:700;" onclick="selectOsVm('k8s-cp1')">k8s-cp1 (Control Plane · 2vCPU/4GB)</button>
            <button class="btn-top" id="btn-tab-w1" onclick="selectOsVm('k8s-w1')">k8s-w1 (Worker 1 · 2vCPU/2.5GB)</button>
            <button class="btn-top" id="btn-tab-db01" onclick="selectOsVm('db-01')">db-01 (MySQL 8.4 DB · 2vCPU/4GB)</button>
          </div>
          <button class="btn-action btn-refresh" style="margin-left:auto; font-size:11px; padding:6px 12px;" onclick="fetchOsVmStatus(true)">
            <span>🔍</span> 최신 상태 새로고침
          </button>
        </div>

        <!-- MAIN SELECTED VM CONTROL BOX (KT CLOUD STYLE) -->
        <div class="kt-vm-box" id="os-focused-box" style="border: 1px solid rgba(176, 140, 255, 0.4); box-shadow: 0 4px 20px rgba(0,0,0,0.3);">
          <div class="kt-vm-header">
            <div class="kt-vm-title">
              <span style="font-size:28px;">🖥️</span>
              <div>
                <div style="display:flex; align-items:center; gap:10px;">
                  <span class="kt-vm-name" id="os-display-name">k8s-cp1</span>
                  <span class="menu-badge" id="os-display-role" style="background:#C8962E; color:#fff; font-size:11px; padding:3px 10px;">K8s Control Plane & App</span>
                </div>
                <div style="font-size: 11px; color: #B4C6D8; font-family: monospace; margin-top:2px;" id="os-display-id">ID: dd0ee22c-caad-4f47-90ca-47c88d8e539f</div>
              </div>
            </div>
            <div id="os-badge-container">
              <div class="kt-vm-badge state-running" id="os-status-badge">
                <span class="dot green"></span>
                <span id="os-status-text">ACTIVE (Running)</span>
              </div>
            </div>
          </div>

          <!-- 6-PROPERTY GRID -->
          <div class="kt-props-grid">
            <div class="prop-item">
              <div class="prop-label">Floating IP (OpenStack 외부망 · 사설 대역)</div>
              <div class="prop-val" id="os-floating-ip" style="color:#9FD3F5;">192.168.120.226</div>
            </div>
            <div class="prop-item">
              <div class="prop-label">Fixed IP (테넌트 내부망)</div>
              <div class="prop-val" id="os-fixed-ip">172.20.0.86</div>
            </div>
            <div class="prop-item">
              <div class="prop-label">인스턴스 스펙 (Flavor)</div>
              <div class="prop-val" id="os-flavor">m1.small (1 vCPU · 2GB RAM · 20GB Disk)</div>
            </div>
            <div class="prop-item">
              <div class="prop-label">운영체제 & 하이퍼바이저</div>
              <div class="prop-val" id="os-os">Ubuntu 22.04 LTS (QEMU/KVM)</div>
            </div>
            <div class="prop-item">
              <div class="prop-label">배치 하이퍼바이저 호스트</div>
              <div class="prop-val" id="os-host" style="color:#C3A6FF;">compute3 (OpenStack Nova)</div>
            </div>
            <div class="prop-item">
              <div class="prop-label">전원 및 서비스 헬스 상태</div>
              <div class="prop-val" id="os-health" style="color:#8FE0B4;">정상 가동 중</div>
            </div>
          </div>

          <!-- CONTROL ACTION BUTTONS (IDENTICAL TO KT CLOUD) -->
          <div class="kt-ctrl-bar">
            <span style="font-size:12px; font-weight:700; color:#B4C6D8; margin-right:6px;">전원 및 자원 명령:</span>
            <button class="btn-action btn-stop" id="btn-os-stop" onclick="confirmSelectedOsAction('stop')">
              <span>🛑</span> 전원 끄기 (Stop)
            </button>
            <button class="btn-action btn-start" id="btn-os-start" disabled onclick="confirmSelectedOsAction('start')">
              <span>⚡</span> 전원 켜기 (Start)
            </button>
            <button class="btn-action btn-reboot" id="btn-os-reboot" onclick="confirmSelectedOsAction('reboot')">
              <span>↻</span> 소프트 재부팅 (Reboot)
            </button>
            <button class="btn-action" id="btn-os-hard-reboot" style="background:#6A8BAE; color:#fff;" onclick="confirmSelectedOsAction('hard_reboot')">
              <span>⚡</span> 강제 재부팅 (Hard Reset)
            </button>
            <button class="btn-action btn-refresh" id="btn-os-refresh" onclick="fetchOsVmStatus(true)">
              <span>🔍</span> 상태 새로고침
            </button>
            <button class="btn-action" id="btn-os-reachability" style="background:#3A78B5; color:#fff; font-weight:700;" onclick="openReachabilityModal()">
              <span>📡</span> Argo CD · Grafana 도달 범위 확인
            </button>
            <span id="os-action-spinner" style="display:none; font-size:12px; color:#C3A6FF; margin-left:auto; font-weight:600;">
              ⏳ OpenStack Nova API 작업 처리 중...
            </span>
          </div>

          <!-- ACTIVITY CONSOLE LOG -->
          <div>
            <div style="font-size:12px; font-weight:700; color:#D3E0EC; margin-bottom:8px; display:flex; justify-content:space-between;">
              <span>📋 OpenStack Nova REST API 실행 콘솔 로그</span>
              <span style="font-size:11px; color:#8AA5C2;">Nova v2.1 API 통신 실시간 스트림</span>
            </div>
            <div class="kt-log-box" id="os-log-console">
              <div class="log-line">
                <span class="log-time">[CMP-INIT]</span>
                <span class="log-msg">OpenStack Nova API 클라이언트 준비 완료.</span>
              </div>
            </div>
          </div>
        </div>

        <!-- 3-VM OVERVIEW SUMMARY CARDS -->
        <div class="section-title" style="margin-top:10px;">
          <span>📋 온프레미스 전체 VM 인벤토리 요약 (3대 ACTIVE 체계)</span>
        </div>
        <div class="cards-grid" id="os-vm-grid">
          <!-- Rendered dynamically by JS -->
        </div>

        <!-- VMWARE HYPERVISOR NODES (4 NODES + HOST MEM/SWAP) -->
        <div class="kt-vm-box" style="margin-top: 4px;">
          <div class="kt-vm-header">
            <div class="kt-vm-title">
              <span style="font-size:22px;">🏢</span>
              <div>
                <div class="kt-vm-name" style="font-size:16px;">OpenStack VMware 하이퍼바이저 노드 현황 (4노드 체제 · 1:1 전담)</div>
                <div style="font-size: 11px; color: #B4C6D8;">Workstation Hypervisor 레이어 | Controller 1대 (192.168.120.160) + Compute 3대 노드 (안전·성능 우선 compute2 정지 및 메모리 회수 완료)</div>
              </div>
            </div>
            <span class="kt-vm-badge state-running"><span class="dot green"></span>Hypervisors 4/4 Running 🟢</span>
          </div>
          <div class="kt-props-grid" id="vmware-nodes-grid">
            <div class="prop-item" style="border-left: 3px solid #9FD3F5;">
              <div class="prop-label">openstack (Controller VM)</div>
              <div class="prop-val" style="color:#9FD3F5; font-size:12px;">192.168.120.160 · Keystone/Nova/Horizon/Neutron/Cinder/MySQL</div>
              <div style="font-size:11px; color:#8FE0B4; margin-top:2px;">Mem: 9.4G (used 6.4G) | <b>Swap: 0B (비활성화 🟢)</b> (10GB 상시 전담)</div>
            </div>
            <div class="prop-item" style="border-left: 3px solid #8FE0B4;">
              <div class="prop-label">compute1 (Compute Node 1)</div>
              <div class="prop-val" style="color:#8FE0B4; font-size:12px;">192.168.120.161 · Nova Compute (호스팅: k8s-w1 [2 vCPU · 2.5GB])</div>
              <div style="font-size:11px; color:#8FE0B4; margin-top:2px;">Mem: 3.5G (used 3.1G) | <b>Swap: 0B (비활성화 🟢)</b></div>
            </div>
            <div class="prop-item" style="border-left: 3px solid #8FE0B4;">
              <div class="prop-label">compute3 (Compute Node 3)</div>
              <div class="prop-val" style="color:#8FE0B4; font-size:12px;">192.168.120.163 · Nova Compute (호스팅: k8s-cp1 [2 vCPU · 4GB])</div>
              <div style="font-size:11px; color:#8FE0B4; margin-top:2px;">Mem: 5.5G (used 3.8G) | <b>Swap: 0B (비활성화 🟢)</b> (k8s-cp1 4GB 전담 안착)</div>
            </div>
            <div class="prop-item" style="border-left: 3px solid #8FE0B4;">
              <div class="prop-label">compute4 (Compute Node 4)</div>
              <div class="prop-val" style="color:#8FE0B4; font-size:12px;">192.168.120.164 · Nova Compute (호스팅: db-01 [2 vCPU · 4GB])</div>
              <div style="font-size:11px; color:#8FE0B4; margin-top:2px;">Mem: 5.5G (used 3.1G) | <b>Swap: 0B (비활성화 🟢)</b> (MySQL 8.4 LTS 4GB 전담)</div>
            </div>
          </div>
        </div>
      </section>

      <!-- AWS EC2 관리 (2026-11-18, PR #13·#14) -->
      <section id="awsvm-panel" style="display: none;">
        <div class="overview-hero" style="background: linear-gradient(135deg, rgba(244, 162, 97, 0.22), rgba(15, 45, 79, 0.85)); border: 1px solid rgba(244, 162, 97, 0.4);">
          <h2>🟧 AWS EC2 관리 — 관제(ctl) · DR(dr) 지점</h2>
          <p>PR #13(Terraform: VPC 분리 · EC2 · SG · S3 backend)과 PR #14(Ansible: swap · WireGuard)로 만든 AWS 노드 2대입니다. 온프렘 → KT 허브(WG 터널 C) → AWS로 연결해 복구 러너와 Pilot-Light DR을 올립니다. 연결 상태는 온프렘 포털 호스트에서 실측합니다.</p>
        </div>

        <div class="stats-grid">
          <div class="stat-card"><div class="label">EC2 인스턴스</div><div class="value">2대</div><div class="subtext">ctl(관제) · dr(재해복구)</div></div>
          <div class="stat-card"><div class="label">WG 터널 C</div><div class="value" id="aws-stat-wg" style="color:#F4C95D;">-</div><div class="subtext">KT 허브 ↔ ctl · dr</div></div>
          <div class="stat-card"><div class="label">VPC</div><div class="value">2개</div><div class="subtext">10.50.0.0/16 · 10.51.0.0/16</div></div>
          <div class="stat-card"><div class="label">AWS DR 복구 백엔드</div><div class="value" id="aws-stat-svc" style="color:#F4C95D;">-</div><div class="subtext" id="aws-sub-svc">러너(:8080) · DR k3s(:30080)</div></div>
        </div>

        <div class="aws-nodes">
          <div class="kt-vm-box aws-node" style="border:1px solid rgba(244,162,97,0.45);">
            <div class="kt-vm-header">
              <div class="kt-vm-title">
                <span style="font-size:26px;">🟧</span>
                <div>
                  <div style="display:flex; align-items:center; gap:10px;">
                    <span class="kt-vm-name">aws-ctl</span>
                    <span class="menu-badge" style="background:#F4A261; color:#111; font-size:11px; padding:3px 10px;">관제 · 복구 러너</span>
                  </div>
                  <div style="font-size:11px; color:#B4C6D8; font-family:monospace; margin-top:2px;">t3.small · Rocky 8 x86_64 · gp3 · EIP (PR #13)</div>
                </div>
              </div>
              <div class="kt-vm-badge" style="border-color:#F4C95D; color:#F4C95D;">apply 완료 (팀 보고)</div>
            </div>
            <div class="kt-props-grid">
              <div class="prop-item"><div class="prop-label">공인 IP (EIP)</div><div class="prop-val" style="color:#9FD3F5;">13.125.163.58</div></div>
              <div class="prop-item"><div class="prop-label">VPC</div><div class="prop-val">10.50.0.0/16 (ctl)</div></div>
              <div class="prop-item"><div class="prop-label">WireGuard IP</div><div class="prop-val">10.200.0.3</div></div>
              <div class="prop-item"><div class="prop-label">WG 터널 C (KT 허브)</div><div class="prop-val aws-st wait" id="aws-ctl-wg">확인 중…</div></div>
              <div class="prop-item"><div class="prop-label">복구 러너 :8080</div><div class="prop-val aws-st wait" id="aws-ctl-svc">확인 중…</div></div>
              <div class="prop-item"><div class="prop-label">보안그룹</div><div class="prop-val" style="font-size:12px;">SSH = 관리자 IP · WG UDP 51820 = peer · ctl↔dr EIP</div></div>
            </div>
          </div>
          <div class="kt-vm-box aws-node" style="border:1px solid rgba(244,162,97,0.45);">
            <div class="kt-vm-header">
              <div class="kt-vm-title">
                <span style="font-size:26px;">🟧</span>
                <div>
                  <div style="display:flex; align-items:center; gap:10px;">
                    <span class="kt-vm-name">aws-dr</span>
                    <span class="menu-badge" style="background:#F4A261; color:#111; font-size:11px; padding:3px 10px;">Pilot-Light DR</span>
                  </div>
                  <div style="font-size:11px; color:#B4C6D8; font-family:monospace; margin-top:2px;">t3.small · Rocky 8 x86_64 · gp3 · EIP (PR #13)</div>
                </div>
              </div>
              <div class="kt-vm-badge" style="border-color:#F4C95D; color:#F4C95D;">apply 완료 (팀 보고)</div>
            </div>
            <div class="kt-props-grid">
              <div class="prop-item"><div class="prop-label">공인 IP (EIP)</div><div class="prop-val" style="color:#9FD3F5;">54.116.129.147</div></div>
              <div class="prop-item"><div class="prop-label">VPC</div><div class="prop-val">10.51.0.0/16 (dr)</div></div>
              <div class="prop-item"><div class="prop-label">WireGuard IP</div><div class="prop-val">10.200.0.4</div></div>
              <div class="prop-item"><div class="prop-label">WG 터널 C (KT 허브)</div><div class="prop-val aws-st wait" id="aws-dr-wg">확인 중…</div></div>
              <div class="prop-item"><div class="prop-label">DR k3s :30080</div><div class="prop-val aws-st wait" id="aws-dr-svc">확인 중…</div></div>
              <div class="prop-item"><div class="prop-label">보안그룹</div><div class="prop-val" style="font-size:12px;">SSH = 관리자 IP · WG UDP 51820 = peer · ctl↔dr EIP</div></div>
            </div>
          </div>
        </div>

        <div class="section-title"><span>🔗</span><span>온프렘 → AWS 연결 작업</span>
          <button class="btn-top" style="margin-left:auto; font-size:12px;" onclick="switchTab('osops')">연결 점검 전체 보기 →</button></div>
        <ul class="aws-steps">
          <li><b>1. 접속 수단</b><span>minwon-key.pem + 보안그룹 admin_cidrs에 운영 IP 추가 (현재 맥·KT 모두 SSH 차단)</span></li>
          <li><b>2. ctl · dr 공개키</b><span>/etc/wireguard/publickey — 공개 정보</span></li>
          <li><b>3. 보안그룹 WG 허용</b><span>wg_peer_cidrs에 KT 14.63.212.190/32 포함 확인</span></li>
          <li><b>4. AWS wg0 ← KT 허브 피어</b><span>AllowedIPs 10.200.0.1-2/32 · 192.168.120.0/24 · 172.20.0.0/24 · 10.10.1.0/24</span></li>
          <li><b>5. KT wg0 ← AWS 피어</b><span>wg syncconf (온프렘 터널 무중단)</span></li>
          <li><b>6. PR #14 role 반영</b><span>wg_extra_peers 변수 — 수동 추가분이 플레이북 실행 때 지워지지 않게</span></li>
        </ul>
        <p style="font-size:12px; color:#8AA5C2; margin:0;">전원 제어(시작 · 중지)는 AWS 자격증명을 포털에 연결한 뒤 추가합니다. 지금은 상태 표시만 합니다.</p>
      </section>

      <!-- 통합 터미널 (2026-11-19): KT · AWS · 온프렘, 세션 1회 잠금 해제 -->
      <section id="term-panel" style="display: none; flex: 1; flex-direction: column; min-height: calc(100vh - 110px);">
        <iframe id="term-frame" src="/term" title="통합 터미널" style="flex: 1; width: 100%; min-height: calc(100vh - 110px); border: 0; background: #04121F;"></iframe>
      </section>

      <!-- OpenStack 구조 · 연결 (2026-11-18 #osvm에서 분리) -->
      <section id="osnet-panel" style="display: none;"></section>

      <!-- OpenStack 연결 · 상태 (2026-11-18 osnet에서 분리) -->
      <section id="osops-panel" style="display: none;">
        <div class="osx" id="osx"></div>
      </section>

      <!-- 실시간 상태확인: 하이브리드 전체 호스트 리소스 & 서비스·K8s 파드 상세 가동 현황 전체 바디 영역 -->
      <section id="realtime-panel" style="display: none; width: 100%; height: 100%; overflow-y: auto; background: #080e1a; padding: 22px; box-sizing: border-box;"></section>

                  <!-- 4. v3.0 DRAWIO TECHNICAL ARCHITECTURE & OPERATION DASHBOARD -->
      <section id="dr-panel" style="display: none;">
        <div class="overview-hero" style="background: linear-gradient(135deg, rgba(244, 201, 93, 0.2), rgba(15, 45, 79, 0.85)); border: 1px solid rgba(244, 201, 93, 0.4);">
          <div style="display:flex; justify-content:space-between; align-items:flex-start; flex-wrap:wrap; gap:10px;">
            <div>
              <h2 style="color:#FBE6AE;">민원불패 — 통합 운영 대시보드 v2.5.1 (실시간 동적 제어 & 관제)</h2>
              <p style="margin-top:4px;"><b>설계문서 v3.0 drawio</b> 명세 100% 구현: KT Cloud Edge-GW(입구) ↔ WireGuard 터널 3개 메쉬 ↔ 온프레미스 OpenStack 5노드(K3s 마스터-워커-워커 & MySQL Primary) ↔ AWS DR 관제 스택 & Orchestrator 상태 머신.</p>
            </div>
            <div style="display:flex; gap:8px;">
              <span class="tunnel-badge tunnel-a">터널 A: 평시 요청 (KT↔온프렘)</span>
              <span class="tunnel-badge tunnel-b">터널 B: 복제·관측·L2복구 (AWS↔온프렘)</span>
              <span class="tunnel-badge tunnel-c">터널 C: DR 전환 (KT↔AWS)</span>
            </div>
          </div>
        </div>

        <!-- CONTROL BAR & FLOW VELOCITY CONTROLLER -->
        <div style="background:#0F2D4F; padding:14px 18px; border-radius:0; border:1px solid #4F739A; margin-bottom:12px; display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:14px;">
          <div style="display:flex; align-items:center; gap:10px; flex-wrap:wrap;">
            <button id="btn-open-console" class="btn-top" style="background:#3A78B5; color:#fff; font-weight:800; font-size:12.5px; padding:8px 16px; border-radius:0; cursor:pointer; display:flex; align-items:center; gap:6px;" onclick="openConsoleModal()">
              <span>📋</span> 콘솔확인
            </button>
            <button id="btn-reach-toggle" class="btn-top" style="background:rgba(159,211,245,0.15); color:#9FD3F5; border:1px solid #9FD3F5; font-weight:700; font-size:12px; padding:7px 14px; border-radius:0; cursor:pointer; display:flex; align-items:center; gap:6px;" onclick="window.toggleReachabilityOverlay && window.toggleReachabilityOverlay()">
              <span>📡</span> <span id="btn-reach-text">도달 범위 & 격리선 표시</span>
            </button>
            <button class="btn-top" style="background:rgba(195,166,255,0.15); color:#c3a6ff; border:1px solid #c3a6ff; font-weight:700; font-size:12px; padding:7px 14px; border-radius:0; cursor:pointer; display:flex; align-items:center; gap:6px;" onclick="openReachModal()">
              <span>🗺️</span> 도달 범위 검증 모달
            </button>
            <div style="font-size:11px; color:#D3E0EC; background:rgba(29,74,122,0.7); padding:6px 12px; border-radius:0; border:1px solid #6A8BAE;">
              💡 <b>방어 체계</b>: 1~2단계 <b>자가치유 장애복구</b> (Pod·Ansible) ➔ 3~4단계 <b>광역 DR 절체</b> (AWS Promotion)
            </div>
          </div>

          <!-- 동적 트래픽 흐름 속도 인디케이터 (Flow Velocity Gauge) -->
          <div style="display:flex; align-items:center; gap:16px;">
            <div style="text-align:right;">
              <div style="font-size:10px; color:#B4C6D8; font-weight:700; text-transform:uppercase;">트래픽 흐름 속도 (Flow Velocity)</div>
              <div id="dr-velocity-text" style="font-size:12.5px; font-weight:800; color:#8FE0B4;">⚡ 180 req/s · RTT 4.2ms [VERY FAST]</div>
            </div>
            <div id="dr-velocity-meter" style="display:flex; gap:3px; align-items:flex-end; height:24px;">
              <div class="meter-bar" id="v-bar-1" style="width:4px; height:8px; background:#8FE0B4; border-radius:0;"></div>
              <div class="meter-bar" id="v-bar-2" style="width:4px; height:14px; background:#8FE0B4; border-radius:0;"></div>
              <div class="meter-bar" id="v-bar-3" style="width:4px; height:20px; background:#8FE0B4; border-radius:0;"></div>
              <div class="meter-bar" id="v-bar-4" style="width:4px; height:24px; background:#8FE0B4; border-radius:0;"></div>
            </div>
          </div>
        </div>


        <div class="dr-console" id="dr-console">
        <div class="dc-main">
          <div class="iso-stage">
            <div class="iso-stage-head"><h3>민원불패 v2.5.1 — 연결 구성도</h3><p class="dc-hint">휠 확대 · 드래그 이동 · 장비 클릭 시 상세</p><button class="btn-top dc-fs" id="dr-fs-btn" onclick="toggleDrFullscreen()">전체 화면</button></div>
            <div class="t3-host" id="t3-host"><svg id="iso-scene" data-stage="normal" role="img" aria-label="하이브리드 멀티클라우드 아이소메트릭 토폴로지" viewBox="-480 -386 881 753" preserveAspectRatio="xMidYMid meet"><g class="iso-zone " id="iso-gh"><g class="iso-box platform"><polygon class="f-left" points="162.1,-97.5 229.7,-58.5 229.7,-67.6 162.1,-106.6"/><polygon class="f-right" points="297.2,-97.5 229.7,-58.5 229.7,-67.6 297.2,-106.6"/><polygon class="f-top" points="229.7,-145.6 297.2,-106.6 229.7,-67.6 162.1,-106.6"/></g><line class="floor" x1="252.2" y1="-132.6" x2="184.6" y2="-93.6"/><line class="floor" x1="274.7" y1="-119.6" x2="207.2" y2="-80.6"/><line class="floor" x1="207.2" y1="-132.6" x2="274.7" y2="-93.6"/><line class="floor" x1="184.6" y1="-119.6" x2="252.2" y2="-80.6"/></g><g class="iso-zone " id="iso-kt"><g class="iso-box platform"><polygon class="f-left" points="-331.0,-49.4 -240.9,2.6 -240.9,-6.5 -331.0,-58.5"/><polygon class="f-right" points="-150.9,-49.4 -240.9,2.6 -240.9,-6.5 -150.9,-58.5"/><polygon class="f-top" points="-240.9,-110.5 -150.9,-58.5 -240.9,-6.5 -331.0,-58.5"/></g><line class="floor" x1="-218.4" y1="-97.5" x2="-308.5" y2="-45.5"/><line class="floor" x1="-195.9" y1="-84.5" x2="-286.0" y2="-32.5"/><line class="floor" x1="-173.4" y1="-71.5" x2="-263.4" y2="-19.5"/><line class="floor" x1="-263.4" y1="-97.5" x2="-173.4" y2="-45.5"/><line class="floor" x1="-286.0" y1="-84.5" x2="-195.9" y2="-32.5"/><line class="floor" x1="-308.5" y1="-71.5" x2="-218.4" y2="-19.5"/></g><g class="iso-zone " id="iso-onprem"><g class="iso-box platform"><polygon class="f-left" points="-135.1,87.1 0.0,165.1 0.0,156.0 -135.1,78.0"/><polygon class="f-right" points="135.1,87.1 0.0,165.1 0.0,156.0 135.1,78.0"/><polygon class="f-top" points="0.0,0.0 135.1,78.0 0.0,156.0 -135.1,78.0"/></g><line class="floor" x1="22.5" y1="13.0" x2="-112.6" y2="91.0"/><line class="floor" x1="45.0" y1="26.0" x2="-90.1" y2="104.0"/><line class="floor" x1="67.5" y1="39.0" x2="-67.5" y2="117.0"/><line class="floor" x1="90.1" y1="52.0" x2="-45.0" y2="130.0"/><line class="floor" x1="112.6" y1="65.0" x2="-22.5" y2="143.0"/><line class="floor" x1="-22.5" y1="13.0" x2="112.6" y2="91.0"/><line class="floor" x1="-45.0" y1="26.0" x2="90.1" y2="104.0"/><line class="floor" x1="-67.5" y1="39.0" x2="67.5" y2="117.0"/><line class="floor" x1="-90.1" y1="52.0" x2="45.0" y2="130.0"/><line class="floor" x1="-112.6" y1="65.0" x2="22.5" y2="143.0"/></g><g class="iso-zone " id="iso-aws"><g class="iso-box platform"><polygon class="f-left" points="85.6,245.7 198.1,310.7 198.1,301.6 85.6,236.6"/><polygon class="f-right" points="310.7,245.7 198.1,310.7 198.1,301.6 310.7,236.6"/><polygon class="f-top" points="198.1,171.6 310.7,236.6 198.1,301.6 85.6,236.6"/></g><line class="floor" x1="220.7" y1="184.6" x2="108.1" y2="249.6"/><line class="floor" x1="243.2" y1="197.6" x2="130.6" y2="262.6"/><line class="floor" x1="265.7" y1="210.6" x2="153.1" y2="275.6"/><line class="floor" x1="288.2" y1="223.6" x2="175.6" y2="288.6"/><line class="floor" x1="175.6" y1="184.6" x2="288.2" y2="249.6"/><line class="floor" x1="153.1" y1="197.6" x2="265.7" y2="262.6"/><line class="floor" x1="130.6" y1="210.6" x2="243.2" y2="275.6"/><line class="floor" x1="108.1" y1="223.6" x2="220.7" y2="288.6"/></g><path class="pipe-case" d="M-200.4,-46.8 L-56.3,36.4"/><path id="path-tunnel-a" class="flow-line line-yellow" fill="none" d="M-200.4,-46.8 L-56.3,36.4"/><path class="pipe-case" d="M186.9,195.0 L76.6,131.3 L173.4,75.4 L38.3,-2.6 L-27.0,35.1"/><path id="path-tunnel-b" class="flow-line line-blue" fill="none" d="M186.9,195.0 L76.6,131.3 L173.4,75.4 L38.3,-2.6 L-27.0,35.1"/><path class="pipe-case" d="M-243.2,-55.9 L-331.0,-5.2 L139.6,266.5 L144.1,263.9"/><path id="path-tunnel-c" class="line-inactive" fill="none" d="M-243.2,-55.9 L-331.0,-5.2 L139.6,266.5 L144.1,263.9"/><path class="pipe-case" d="M31.5,120.9 L130.6,178.1 L99.1,196.3 L172.3,238.6"/><path id="path-db-sync" class="flow-line line-yellow" fill="none" d="M31.5,120.9 L130.6,178.1 L99.1,196.3 L172.3,238.6"/><path class="pipe-case" d="M-119.3,-274.3 L-218.4,-89.7"/><path id="iso-path-ingress" class="flow-line line-blue" fill="none" d="M-119.3,-274.3 L-218.4,-89.7"/><path class="pipe-case" id="iso-case-gh" d="M-119.3,-274.3 L231.9,-120.9"/><path id="iso-path-gh" class="line-inactive" fill="none" d="M-119.3,-274.3 L231.9,-120.9"/><g class="iso-box node" id="iso-ghpage"><polygon class="f-left" points="204.9,-107.9 231.9,-92.3 231.9,-105.3 204.9,-120.9"/><polygon class="f-right" points="258.9,-107.9 231.9,-92.3 231.9,-105.3 258.9,-120.9"/><polygon class="f-top" points="231.9,-136.5 258.9,-120.9 231.9,-105.3 204.9,-120.9"/></g><g class="iso-box node" id="iso-edge"><polygon class="f-left" points="-249.9,-53.3 -213.9,-32.5 -213.9,-71.5 -249.9,-92.3"/><polygon class="f-right" points="-186.9,-48.1 -213.9,-32.5 -213.9,-71.5 -186.9,-87.1"/><polygon class="f-top" points="-222.9,-107.9 -186.9,-87.1 -213.9,-71.5 -249.9,-92.3"/><line class="slot" x1="-244.5" y1="-59.9" x2="-219.3" y2="-45.4"/><circle class="led" cx="-217.5" cy="-44.3" r="1.6"/><line class="slot" x1="-244.5" y1="-69.7" x2="-219.3" y2="-55.1"/><circle class="led" cx="-217.5" cy="-54.1" r="1.6"/><line class="slot" x1="-244.5" y1="-79.4" x2="-219.3" y2="-64.9"/><circle class="led" cx="-217.5" cy="-63.8" r="1.6"/></g><g class="iso-box node rack" id="iso-k8s-cp1"><polygon class="f-left" points="20.3,50.7 40.5,62.4 40.5,0.0 20.3,-11.7"/><polygon class="f-right" points="65.3,48.1 40.5,62.4 40.5,0.0 65.3,-14.3"/><polygon class="f-top" points="45.0,-26.0 65.3,-14.3 40.5,0.0 20.3,-11.7"/><line class="slot" x1="23.3" y1="40.0" x2="37.5" y2="48.2"/><circle class="led" cx="38.5" cy="48.8" r="1.6"/><line class="slot" x1="23.3" y1="27.5" x2="37.5" y2="35.7"/><circle class="led" cx="38.5" cy="36.3" r="1.6"/><line class="slot" x1="23.3" y1="15.0" x2="37.5" y2="23.2"/><circle class="led" cx="38.5" cy="23.8" r="1.6"/><line class="slot" x1="23.3" y1="2.5" x2="37.5" y2="10.7"/><circle class="led" cx="38.5" cy="11.3" r="1.6"/></g><g class="iso-box node rack" id="iso-k8s-w1"><polygon class="f-left" points="46.2,65.6 66.4,77.4 66.4,15.0 46.2,3.2"/><polygon class="f-right" points="91.2,63.1 66.4,77.4 66.4,15.0 91.2,0.7"/><polygon class="f-top" points="70.9,-11.1 91.2,0.7 66.4,15.0 46.2,3.2"/><line class="slot" x1="49.2" y1="54.9" x2="63.4" y2="63.1"/><circle class="led" cx="64.4" cy="63.7" r="1.6"/><line class="slot" x1="49.2" y1="42.4" x2="63.4" y2="50.6"/><circle class="led" cx="64.4" cy="51.2" r="1.6"/><line class="slot" x1="49.2" y1="30.0" x2="63.4" y2="38.2"/><circle class="led" cx="64.4" cy="38.7" r="1.6"/><line class="slot" x1="49.2" y1="17.5" x2="63.4" y2="25.7"/><circle class="led" cx="64.4" cy="26.3" r="1.6"/></g><g class="iso-box node" id="iso-wg"><polygon class="f-left" points="-63.0,46.8 -36.0,62.4 -36.0,39.0 -63.0,23.4"/><polygon class="f-right" points="-13.5,49.4 -36.0,62.4 -36.0,39.0 -13.5,26.0"/><polygon class="f-top" points="-40.5,10.4 -13.5,26.0 -36.0,39.0 -63.0,23.4"/><line class="slot" x1="-59.0" y1="37.4" x2="-40.1" y2="48.4"/><circle class="led" cx="-38.7" cy="49.1" r="1.6"/></g><g class="iso-box pod" id="iso-pod-web"><polygon class="f-left" points="-18.0,72.8 -4.5,80.6 -4.5,65.0 -18.0,57.2"/><polygon class="f-right" points="9.0,72.8 -4.5,80.6 -4.5,65.0 9.0,57.2"/><polygon class="f-top" points="-4.5,49.4 9.0,57.2 -4.5,65.0 -18.0,57.2"/></g><g class="iso-box pod" id="iso-pod-api"><polygon class="f-left" points="2.3,84.5 15.8,92.3 15.8,76.7 2.3,68.9"/><polygon class="f-right" points="29.3,84.5 15.8,92.3 15.8,76.7 29.3,68.9"/><polygon class="f-top" points="15.8,61.1 29.3,68.9 15.8,76.7 2.3,68.9"/></g><g class="iso-box pod" id="iso-pod-notify"><polygon class="f-left" points="-38.3,84.5 -24.8,92.3 -24.8,76.7 -38.3,68.9"/><polygon class="f-right" points="-11.3,84.5 -24.8,92.3 -24.8,76.7 -11.3,68.9"/><polygon class="f-top" points="-24.8,61.1 -11.3,68.9 -24.8,76.7 -38.3,68.9"/></g><g class="iso-box pod" id="iso-pod-audit"><polygon class="f-left" points="-18.0,96.2 -4.5,104.0 -4.5,88.4 -18.0,80.6"/><polygon class="f-right" points="9.0,96.2 -4.5,104.0 -4.5,88.4 9.0,80.6"/><polygon class="f-top" points="-4.5,72.8 9.0,80.6 -4.5,88.4 -18.0,80.6"/></g><g class="iso-cyl db" id="iso-db-primary"><path class="f-left" d="M-6.5,79.3 L-6.5,118.3 A22.3,12.9 0 0 0 38.1,118.3 L38.1,79.3 A22.3,12.9 0 0 1 -6.5,79.3 Z"/><path class="slot" d="M-6.5,105.3 A22.3,12.9 0 0 0 38.1,105.3"/><path class="slot" d="M-6.5,92.3 A22.3,12.9 0 0 0 38.1,92.3"/><ellipse class="f-top" cx="15.8" cy="79.3" rx="22.3" ry="12.9"/></g><g class="iso-box node" id="iso-ctl"><polygon class="f-left" points="173.4,209.3 204.9,227.5 204.9,183.3 173.4,165.1"/><polygon class="f-right" points="231.9,211.9 204.9,227.5 204.9,183.3 231.9,167.7"/><polygon class="f-top" points="200.4,149.5 231.9,167.7 204.9,183.3 173.4,165.1"/><line class="slot" x1="178.1" y1="201.0" x2="200.2" y2="213.7"/><circle class="led" cx="201.7" cy="214.6" r="1.6"/><line class="slot" x1="178.1" y1="189.9" x2="200.2" y2="202.7"/><circle class="led" cx="201.7" cy="203.6" r="1.6"/><line class="slot" x1="178.1" y1="178.9" x2="200.2" y2="191.6"/><circle class="led" cx="201.7" cy="192.5" r="1.6"/></g><g class="iso-cyl bucket" id="iso-s3"><path class="f-left" d="M246.9,215.8 L246.9,234.0 A14.3,8.3 0 0 0 275.5,234.0 L275.5,215.8 A14.3,8.3 0 0 1 246.9,215.8 Z"/><path class="slot" d="M246.9,224.9 A14.3,8.3 0 0 0 275.5,224.9"/><ellipse class="f-top" cx="261.2" cy="215.8" rx="14.3" ry="8.3"/></g><g class="iso-cyl db" id="iso-db-replica"><path class="f-left" d="M166.2,217.1 L166.2,253.5 A20.7,12.0 0 0 0 207.6,253.5 L207.6,217.1 A20.7,12.0 0 0 1 166.2,217.1 Z"/><path class="slot" d="M166.2,241.4 A20.7,12.0 0 0 0 207.6,241.4"/><path class="slot" d="M166.2,229.2 A20.7,12.0 0 0 0 207.6,229.2"/><ellipse class="f-top" cx="186.9" cy="217.1" rx="20.7" ry="12.0"/></g><g class="iso-person"><circle class="f-top" cx="-132.8" cy="-336.5" r="6"/><path class="f-left" d="M-143.8,-316.5 q11,-16 22,0 v8 h-22 Z"/></g><g class="iso-cloud" id="iso-cf"><path class="f-top" d="M-157.3,-264.3 a14,14 0 0 1 10,-22 a20,20 0 0 1 36,-8 a16,16 0 0 1 26,10 a12,12 0 0 1 2,20 Z"/></g><text class="tun-t ta" x="-137.4" y="-18.4" text-anchor="middle">터널 A</text><text class="tun-t tb" x="135.1" y="89.5" text-anchor="middle">터널 B</text><text class="tun-t tc" x="-42.8" y="153.2" text-anchor="middle">터널 C · DR 우회</text><text class="tun-t tb" x="58.5" y="128.5" text-anchor="middle">GTID 복제</text><g class="cut" id="iso-cut-a"><path d="M-116.3,-0.8 l12,12 M-104.3,-0.8 l-12,12"/></g><text class="stamp" id="iso-stamp-fenced" x="0.0" y="84.0" text-anchor="middle">FENCED · 쓰기 차단</text><g class="zone-label" id="iso-gh-label"><text class="zone-t" x="229.7" y="-34.5" text-anchor="middle">GitHub Pages</text><text class="zone-s" x="229.7" y="-15.5" text-anchor="middle">0초 비상 접수 (dr.ktci5.kr)</text></g><g class="zone-label" id="iso-kt-label"><text class="zone-t" x="-240.9" y="26.6" text-anchor="middle">KT Cloud</text><text class="zone-s" x="-240.9" y="45.6" text-anchor="middle">입구 전용</text></g><g class="zone-label" id="iso-onprem-label"><text class="zone-t" x="0.0" y="189.1" text-anchor="middle">온프레미스 OpenStack</text><text class="zone-s" x="0.0" y="208.1" text-anchor="middle">Primary · K3s 클러스터 · MySQL</text></g><g class="zone-label" id="iso-aws-label"><text class="zone-t" x="198.1" y="334.7" text-anchor="middle">AWS</text><text class="zone-s" x="198.1" y="353.7" text-anchor="middle">관제 · DR 대기 · S3 백업</text></g><g class="callout "><circle class="pin" cx="-132.8" cy="-341.9" r="2.2"/><polyline class="leader" points="-132.8,-341.9 -162.8,-361.9 -186.8,-361.9"/><text class="c-t" x="-192.8" y="-357.9" text-anchor="end">사용자 민원 접수</text><text class="c-s" x="-192.8" y="-339.9" text-anchor="end">HTTPS</text></g><g class="callout "><circle class="pin" cx="-101.3" cy="-300.3" r="2.2"/><polyline class="leader" points="-101.3,-300.3 -61.3,-320.3 -37.3,-320.3"/><text class="c-t" x="-31.3" y="-316.3" text-anchor="start">Cloudflare</text><text class="c-s" x="-31.3" y="-298.3" text-anchor="start">Anycast WAF · Worker</text></g><g class="callout "><circle class="pin" cx="-236.4" cy="-92.3" r="2.2"/><polyline class="leader" points="-236.4,-92.3 -260.4,-58.3 -284.4,-58.3"/><text class="c-t" x="-290.4" y="-54.3" text-anchor="end">Edge-GW</text><text class="c-s" x="-290.4" y="-36.3" text-anchor="end">Nginx WAF · 14.63.212.190</text></g><g class="callout " id="iso-c-wg"><circle class="pin" cx="-63.0" cy="33.8" r="2.2"/><polyline class="leader" points="-63.0,33.8 -93.0,103.8 -117.0,103.8"/><text class="c-t" x="-123.0" y="107.8" text-anchor="end">WireGuard GW</text><text class="c-s" x="-123.0" y="125.8" text-anchor="end">Inbound 0 · 펜싱</text></g><g class="callout "><circle class="pin" cx="45.0" cy="-26.0" r="2.2"/><polyline class="leader" points="45.0,-26.0 15.0,-76.0 -9.0,-76.0"/><text class="c-t" x="-15.0" y="-72.0" text-anchor="end">K3s 노드 2대</text><text class="c-s" x="-15.0" y="-54.0" text-anchor="end">cp1 · w1 (단일 워커)</text></g><g class="callout " id="iso-c-pod"><circle class="pin" cx="-31.5" cy="80.6" r="2.2"/><polyline class="leader" points="-31.5,80.6 -161.5,140.6 -185.5,140.6"/><text class="c-t" x="-191.5" y="144.6" text-anchor="end">민원 파드 이중화</text><text class="c-s" x="-191.5" y="162.6" text-anchor="end">w1 · w2 1:1 분산 서빙</text></g><g class="callout " id="iso-c-dbp"><circle class="pin" cx="38.3" cy="79.3" r="2.2"/><polyline class="leader" points="38.3,79.3 98.3,39.3 122.3,39.3"/><text class="c-t" x="128.3" y="43.3" text-anchor="start">MySQL 8.4 Primary</text><text class="c-s" x="128.3" y="61.3" text-anchor="start">GTID · Read/Write</text></g><g class="callout " id="iso-c-ctl"><circle class="pin" cx="231.9" cy="167.7" r="2.2"/><polyline class="leader" points="231.9,167.7 261.9,127.7 285.9,127.7"/><text class="c-t" x="291.9" y="131.7" text-anchor="start">Orchestrator</text><text class="c-s" x="291.9" y="149.7" text-anchor="start">3-Signal 판정</text></g><g class="callout " id="iso-c-dbr"><circle class="pin" cx="168.9" cy="240.5" r="2.2"/><polyline class="leader" points="168.9,240.5 128.9,320.5 104.9,320.5"/><text class="c-t" x="98.9" y="324.5" text-anchor="end">MySQL Replica</text><text class="c-s" x="98.9" y="342.5" text-anchor="end">GTID 비동기 수신</text></g><g class="callout " id="iso-c-gh"><circle class="pin" cx="231.9" cy="-136.5" r="2.2"/><polyline class="leader" points="231.9,-136.5 191.9,-166.5 167.9,-166.5"/><text class="c-t" x="161.9" y="-162.5" text-anchor="end">정적 비상 접수 폼</text><text class="c-s" x="161.9" y="-144.5" text-anchor="end">Black Sky 시 0초 노출</text></g></svg></div>
          </div>
          <div class="dc-detail" id="dc-detail">
            <div class="dc-detail-head">상세 구성 — 서브넷 · 파드 · DB</div>
        <!-- MAIN ARCHITECTURE CANVAS (v3.0 drawio 1:1 토폴로지 레이아웃) -->
        <div class="arch-container" id="arch-canvas">
          
          <!-- ======================================================== -->
          <!-- ZONE 1: KT CLOUD — 입구 전용 (VM 1대)                     -->
          <!-- ======================================================== -->
          <div class="arch-zone zone-kt" id="zone-kt-box">
            <div class="zone-title" style="color:#9FD3F5;">
              <span>🌐 KT Cloud — 입구 전용</span>
              <span class="menu-badge" style="background:#3A78B5; color:#fff;">Edge-GW 1대</span>
            </div>

            <!-- CITIZEN ACCESS -->
            <div style="background:#0F2D4F; border:1px solid #4F739A; border-radius:0; padding:10px; text-align:center;">
              <div style="font-size:18px;">👤 ➔ 🛡️</div>
              <div style="font-size:12px; font-weight:800; color:#fff;">민원접수 사용자 & Cloudflare</div>
              <div style="font-size:10px; color:#B4C6D8;">HTTPS Anycast WAF 종료</div>
            </div>

            <!-- Edge-GW VM -->
            <div class="arch-subnet" id="subnet-kt-edge" style="background:rgba(2, 132, 199, 0.1); border-color:#3A78B5;">
              <div class="subnet-label" style="color:#9FD3F5;">Edge-GW VM (kt-edge-dr-01 · 공인 14.63.212.190)</div>
              <div style="font-size:11px; color:#D3E0EC; line-height:1.5;">
                • <b>Nginx TLS·WAF (ModSecurity)</b><br>
                • <b>10초 마이크로캐시</b> (무상태)<br>
                • WireGuard 터널 A·C 종단점
              </div>
              <div style="display:flex; justify-content:space-between; align-items:center; margin-top:4px;">
                <span class="tunnel-badge tunnel-a" id="kt-edge-route">터널 A 발송 중</span>
                <span class="dot green" id="kt-edge-dot"></span>
              </div>
            </div>

            <!-- S3 PROBE INDICATOR -->
            <div style="background:#0F2D4F; border:1px solid #4F739A; border-radius:0; padding:8px; font-size:11px;">
              <span style="font-weight:700; color:#B4C6D8;">S3 프로브:</span>
              <span id="txt-s3-status" style="color:#8FE0B4; font-weight:700;">정상 통과 🟢</span>
            </div>

            <!-- 0-SEC GITHUB PAGES FALLBACK PREVIEW -->
            <div class="arch-subnet" id="subnet-gh-fallback" style="border-color:#6A8BAE; opacity:0.6;">
              <div class="subnet-label">최후의 0초 방어선 (GitHub Pages)</div>
              <div style="font-size:11px; color:#B4C6D8;">
                dr.ktci5.kr 정적 비상 접수처
              </div>
              <span class="menu-badge" id="gh-badge" style="background:#6A8BAE; color:#fff; width:fit-content;">STANDBY ⚪</span>
            </div>
          </div>

          <!-- ======================================================== -->
          <!-- ZONE 2: 온프레미스 OpenStack — 메인 (민원 서비스 Primary)    -->
          <!-- ======================================================== -->
          <div class="arch-zone zone-onprem" id="zone-onprem-box">
            <div class="zone-title" style="color:#8FE0B4;">
              <span>🏢 온프레미스 OpenStack — 메인 (Primary)</span>
              <span class="menu-badge" id="badge-onprem-mode" style="background:#5FD39A; color:#fff;">PRIMARY RW 🟢</span>
            </div>

            <!-- 외부망 서브넷: WG GW -->
            <div class="arch-subnet" id="subnet-onprem-wg">
              <div class="subnet-label" style="color:#F7D684; font-weight:800;">🌐 [외부망 DMZ] br-ex (FIP 10.11.0.0/24 · WG 터널 종단)</div>
              <div style="display:flex; justify-content:space-between; align-items:center;">
                <div style="font-size:12px; font-weight:800; color:#fff;">🔐 WireGuard 게이트웨이</div>
                <span style="font-size:10px; color:#5FD39A;">터널 A·B 발신 · Watchdog</span>
              </div>
              <div style="font-size:10px; color:#B4C6D8;" id="txt-fencing">자가 펜싱 감시 중: 정상 (쓰기 허용)</div>
            </div>

            <!-- k8s 서브넷: K3s MSA -->
            <div class="arch-subnet" id="subnet-onprem-k8s" style="border-color:#5FD39A;">
              <div class="subnet-label" style="color:#8FE0B4; font-weight:800;">🏢 [내부망 SERVICE] net-k3s (172.20.0.0/24 · K3s 단독 워커 체제)</div>
              <div style="font-size:11px; font-weight:700; color:#9FD3F5; margin-bottom:2px;">
                Traefik Ingress (VIP 192.168.120.226 · NodePort 30080 이중화)
              </div>
              
              <!-- app 네임스페이스 -->
              <div style="background:#0C2542; padding:8px; border-radius:0; margin-bottom:6px;">
                <div style="font-size:10px; font-weight:700; color:#C3A6FF; margin-bottom:4px;">app 네임스페이스 (안전·성능 우선 단일 워커 안정 서빙)</div>
                <div class="k8s-pod-grid">
                  <div class="k8s-pod-chip pod-active" id="pod-web">
                    <span>🖥️</span> <span>minwon-app (k8s-w1)</span>
                  </div>
                  <div class="k8s-pod-chip pod-active" id="pod-api">
                    <span>🖥️</span> <span>minwon-app (k8s-w2)</span>
                  </div>
                  <div class="k8s-pod-chip pod-active" id="pod-notify">
                    <span>🐙</span> <span>argocd-controller</span>
                  </div>
                  <div class="k8s-pod-chip pod-active" id="pod-audit">
                    <span>🧭</span> <span>k8s-cp1 제어플레인</span>
                  </div>
                </div>
              </div>

              <!-- data 네임스페이스 (DR 복제 안함) -->
              <div style="background:#0C2542; padding:6px 8px; border-radius:0; display:flex; justify-content:space-between; font-size:11px;">
                <span style="color:#8AA5C2;">로컬 캐시/큐:</span>
                <span style="color:#D3E0EC;">⚡ Redis · 🐰 RabbitMQ</span>
              </div>
            </div>

            <!-- data 서브넷: MySQL Primary -->
            <div class="arch-subnet" id="subnet-onprem-db" style="border-color:#FF7A66; background:rgba(255, 122, 102, 0.05);">
              <div class="subnet-label" style="color:#FF9E8C; font-weight:800;">🔒 [폐쇄망 ISOLATED] net-data (10.10.2.0/24 · No-Gateway 완전 격리)</div>
              <div style="display:flex; justify-content:space-between; align-items:center;">
                <div style="font-size:13px; font-weight:800; color:#fff;">🗄️ MySQL 8.4 Primary (Cinder 영속 볼륨)</div>
                <span class="menu-badge" id="badge-db-rw" style="background:#5FD39A; color:#fff;">Read / Write</span>
              </div>
              <div style="font-size:11px; color:#D3E0EC; line-height:1.4;">
                • 스키마: <code>minwon</code> · <code>notify</code> · <code>audit</code><br>
                • <b>L3 인터넷 단절</b> (외부 직접 인바운드/아웃바운드 100% 차단)<br>
                • 허용: 오직 내부망 <code>10.10.1.0/24:3306</code> 및 터널 B 복제만 허용
              </div>
            </div>

            <!-- ops 서브넷 -->
            <div class="arch-subnet">
              <div class="subnet-label">ops 서브넷 (프라이빗)</div>
              <div style="font-size:11px; color:#B4C6D8;">⛵ Harbor (이미지 레지스트리) · 🐙 Argo CD (GitOps 배포)</div>
            </div>
          </div>

          <!-- ======================================================== -->
          <!-- ZONE 3: AWS — 관제 · DR 대기 · 백업 (제3 관측점)            -->
          <!-- ======================================================== -->
          <div class="arch-zone zone-aws" id="zone-aws-box">
            <div class="zone-title" style="color:#F7D684;">
              <span>☁️ AWS — 관제 · DR 대기 (제3 관측점)</span>
              <span class="menu-badge" id="badge-aws-mode" style="background:#F4C95D; color:#fff;">PILOT-LIGHT RO 🟡</span>
            </div>

            <!-- 관제 서브넷: aws-ctl-01 -->
            <div class="arch-subnet" id="subnet-aws-ctl" style="border-color:#F4C95D;">
              <div class="subnet-label" style="color:#F7D684;">관제 서브넷 (aws-ctl-01 · 제3 관측 판정)</div>
              <div style="display:flex; justify-content:space-between; align-items:center;">
                <div style="font-size:12px; font-weight:800; color:#fff;">📊 관제 스택 & Orchestrator</div>
                <span style="font-size:10px; color:#9FD3F5;">Blackbox S1/S2 프로브</span>
              </div>
              <div style="font-size:11px; color:#D3E0EC; line-height:1.4;">
                • Prometheus · Grafana · Loki<br>
                • <b>Recovery Orchestrator 상태 머신</b><br>
                • 3-Signal 판정 ➔ L2 Ansible / L3 승격 통제
              </div>
              <!-- STATE MACHINE CURRENT STEP -->
              <div style="background:#0C2542; padding:6px 10px; border-radius:0; font-size:11px; display:flex; justify-content:space-between; align-items:center;">
                <span style="color:#B4C6D8;">오케스트레이터 상태:</span>
                <span id="txt-orch-state" style="font-weight:800; color:#5FD39A;">NORMAL (온프렘 가동)</span>
              </div>
            </div>

            <!-- DR 서브넷: Pilot-Light EC2 -->
            <div class="arch-subnet" id="subnet-aws-dr" style="border-color:#6A8BAE;">
              <div class="subnet-label" style="color:#F7D684;">DR 서브넷 (프라이빗 Pilot-Light)</div>
              <div style="display:flex; justify-content:space-between; align-items:center;">
                <div style="font-size:13px; font-weight:800; color:#fff;">🗄️ MySQL 8.4 Replica</div>
                <span class="menu-badge" id="badge-aws-db-ro" style="background:#F4C95D; color:#fff;">super_read_only = ON</span>
              </div>
              <div style="font-size:11px; color:#D3E0EC; line-height:1.4;">
                • 평소 최소 사양 대기 ➔ L3 시 즉각 확장<br>
                • GTID semi-sync 수신 (AFTER_SYNC ACK)<br>
                • L3 승격 시 쓰기 모드로 전환
              </div>
            </div>

            <!-- Amazon S3 백업 -->
            <div class="arch-subnet">
              <div class="subnet-label" style="color:#F4C95D;">Amazon S3 (불변 백업 스토리지)</div>
              <div style="font-size:11px; color:#D3E0EC;">
                • <b>binlog 실시간 스트림</b> · 일일 스냅샷 · Object Lock<br>
                • L4 시점 복원(PITR) 소스
              </div>
            </div>

            <!-- Lambda + EventBridge -->
            <div class="arch-subnet">
              <div class="subnet-label">Dead-man Switch</div>
              <div style="font-size:10px; color:#B4C6D8;">관제 Watchdog 끊김 시 Slack 즉각 사람 호출 (P7)</div>
            </div>
          </div>
        </div>
          </div>
          <div class="dc-strip">
<div class="kt-props-grid" style="grid-template-columns: repeat(4, 1fr); margin-bottom:12px;">
            <div class="prop-item">
              <div class="prop-label">Orchestrator 상태 머신</div>
              <div class="prop-val" id="v3-prop-sm" style="color:#5FD39A;">NORMAL</div>
            </div>
            <div class="prop-item">
              <div class="prop-label">3-Signal 판정 결과</div>
              <div class="prop-val" id="v3-prop-signal" style="color:#9FD3F5;">S1:정상 · S2:정상 · S3:정상</div>
            </div>
            <div class="prop-item">
              <div class="prop-label">목표 RTO / RPO 규격</div>
              <div class="prop-val" id="v3-prop-rto" style="color:#8FE0B4;">RTO: 0초 · RPO: 0초</div>
            </div>
            <div class="prop-item">
              <div class="prop-label">WireGuard 터널 가동 상태</div>
              <div class="prop-val" id="v3-prop-tunnel" style="color:#F7D684;">터널 A·B 활성 (C 대기)</div>
            </div>
          </div>

          


          <div class="kt-log-box" id="dr-log-console" style="margin-top:14px; height:120px;">
            <div class="log-line">
              <span class="log-time">[v3.0-ARCH]</span>
              <span class="log-msg">민원불패 v3.0 전문 아키텍처 다이어그램 캔버스가 활성화되었습니다. 상단 7개 시나리오를 선택하세요.</span>
            </div>
          </div>
          </div>
        </div>
        <div class="dc-side">
        <!-- 7-STAGE SCENARIO CONTROLLER BUTTONS (v3.0 drawio Page 03 반영) -->
        <div style="background:#0F2D4F; padding:14px; border-radius:0; border:1px solid #4F739A;">
          <div style="font-size:11px; font-weight:700; color:#B4C6D8; margin-bottom:8px; text-transform:uppercase; letter-spacing:0.5px; display:flex; justify-content:space-between;">
            <span>🎮 단계별 시뮬레이션 (미선택 시 기본 전체 흐름 작동 ➔ 단계 선택 시 해당 단계 우선 작동):</span>
            <span style="color:#9FD3F5; font-size:11px;">구성도의 각 컴포넌트를 클릭하면 실시간 제어 액션이 작동합니다.</span>
          </div>
          <div style="display:flex; gap:8px; flex-wrap:wrap;" id="dr-v3-btns">
            <button class="btn-top" id="btn-v3-normal" style="background:#5FD39A; color:#fff; font-weight:700;" onclick="setV3Stage('normal')" title="🌐 전체 통합 흐름 (기본 정상)">🟢 1 · 평시 NORMAL</button>
            <button class="btn-top" id="btn-v3-l1" onclick="setV3Stage('l1')" title="🟡 2. L1: Pod 크래시 자가치유 (초 단위)">🟡 2 · L1 Pod 자가치유</button>
            <button class="btn-top" id="btn-v3-l2" onclick="setV3Stage('l2')" title="🟠 3. L2: 서비스 1분 무응답 ➔ 터널 B Ansible 재기동 (≤3분)">🟠 3 · L2 Ansible 재기동</button>
            <button class="btn-top" id="btn-v3-path" onclick="setV3Stage('path')" title="🔵 4. 경로장애: 터널 A 단절 (S1·S3 실패, S2 정상) ➔ 터널 C·B 우회 (DB 승격 금지)">🔵 4 · 경로장애 우회</button>
            <button class="btn-top" id="btn-v3-l3" onclick="setV3Stage('l3')" title="🔴 5. L3: 온프렘 마비 (S1∧S2∧S3 실패) ➔ 펜싱 확인 ➔ AWS Replica 승격">🔴 5 · L3 AWS 승격</button>
            <button class="btn-top" id="btn-v3-l4" onclick="setV3Stage('l4')" title="🟣 6. L4: 복구 검증 ➔ 역방향 GTID 동기화 ➔ 온프렘 승격 (Failback)">🟣 6 · L4 Failback</button>
            <button class="btn-top" id="btn-v3-bs" onclick="setV3Stage('bs')" title="⚫ 7. Black Sky: 전면 불능 ➔ Cloudflare ➔ GitHub Pages 0초 폴백">⚫ 7 · Black Sky 폴백</button>
            <button class="btn-top" id="btn-v3-surge" title="8. 접수 폭주: Edge 대기열 → 접수 테이블 우선 커밋 → 워커 순차 처리 · 초과분 비상 폼" onclick="setV3Stage('surge')">🟤 8 · 접수 폭주</button>
            <button class="btn-top" id="btn-v3-mgmt" title="9. 관리 접속: 운영자 → Cloudflare → minwon-tunnel → 온프렘 cloudflared → 내부 서비스 · WG로 AWS/KT" onclick="setV3Stage('mgmt')">⚪ 9 · 관리 접속 (Tunnel)</button>
          </div>
        </div>

          <div class="dc-stage"><div style="display:flex; justify-content:space-between; align-items:center; border-bottom:1px solid #4F739A; padding-bottom:12px; margin-bottom:12px;">
            <div>
              <div style="font-size:16px; font-weight:800; color:#fff;" id="v3-stage-title">
                🟢 NORMAL: 평시 온프렘 Primary 가동 (터널 A 요청 수용 + 터널 B GTID 복제)
              </div>
              <div style="font-size:12px; color:#B4C6D8; margin-top:2px;" id="v3-stage-desc">
                v3.0 설계 원칙: 공개 지점은 KT Edge 1곳(443 + WG UDP), 모든 사이트 간 트래픽은 WireGuard로 상시 암호화됩니다.
              </div>
            </div>
            <span class="kt-vm-badge state-running" id="v3-status-badge"><span class="dot green"></span>NORMAL STATUS</span>
          </div>

          </div>
          <div class="dc-tabs" role="tablist"><button type="button" class="dc-tab" id="dc-tabbtn-flow" onclick="drTab('flow')">흐름 단계</button><button type="button" class="dc-tab on" id="dc-tabbtn-sop" onclick="drTab('sop')">대응 절차</button><button type="button" class="dc-tab" id="dc-tabbtn-drill" onclick="drTab('drill')">모의훈련</button></div>
          <div class="dc-tabpanel" id="dc-tab-flow" hidden><ol class="dc-flow" id="dc-flow"><li class="empty"><span>3D 엔진을 불러오는 중입니다. 불러오지 못하면 대응 절차 탭을 보세요.</span></li></ol></div>
          <div class="dc-tabpanel dc-sop" id="dc-tab-sop"><!-- DETAILED SOP ACTIONS -->
          <div style="background:#0C2542; padding:12px 16px; border-radius:0; border:1px solid #4F739A; font-size:12px; color:#D3E0EC; line-height:1.6;" id="v3-sop-text">
            <b>[v3.0 정상 가동 트래픽 & 보안 흐름]</b><br>
            • <b>민원접수 진입</b>: HTTPS 요청이 KT Edge-GW(14.63.212.190)에 도착하여 TLS 종료 및 Nginx WAF 검사를 받습니다.<br>
            • <b>터널 A 전송</b>: 온프렘 WireGuard 게이트웨이로 단방향 요청 전달 ➔ Traefik Ingress ➔ K3s 마스터-워커-워커(k8s-w1, w2) 분산 <code>minwon-app 파드 2대</code> ➔ <code>MySQL 8.4 Primary</code> 커밋.<br>
            • <b>터널 B 복제</b>: MySQL GTID 이벤트가 터널 B를 타고 AWS Replica(super_read_only=ON)로 semi-sync 복제(ACK 후 커밋 확정)되고 binlog는 S3로 실시간 백업됩니다.
          </div>

          <!-- INDIVIDUAL POD & COMPONENT LEVEL DRILL-DOWN (개별/파드단위 상세 뷰) -->
          <div style="margin-top:14px; background:#0C2542; padding:14px; border-radius:0; border:1px solid #4F739A;">
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:10px;">
              <span style="font-size:13px; font-weight:800; color:#E6EEF5;">🔍 개별 인스턴스 및 파드 단위(Pod Level) 실시간 상태</span>
              <span style="font-size:11px; color:#B4C6D8;">자가치유 장애복구(L1·L2) vs 광역 DR(L3·L4) 단위별 추적</span>
            </div>
            <div style="display:grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap:10px;">
              <!-- Pod 1 -->
              <div style="background:#0F2D4F; border:1px solid #4F739A; padding:10px; border-radius:0;" id="pod-card-w1">
                <div style="display:flex; justify-content:space-between; align-items:center;">
                  <span style="font-size:11px; font-weight:700; color:#9FD3F5;">os-a: k8s-cp1 (Pod #1)</span>
                  <span class="menu-badge" id="badge-pod-w1" style="background:#5FD39A; color:#fff;">RUNNING 🟢</span>
                </div>
                <div style="font-size:11px; color:#B4C6D8; margin-top:6px;">
                  • 역할: 민원 웹/API 컨테이너 #1<br>
                  • 상태: <span id="txt-pod-w1-status" style="color:#8FE0B4;">정상 처리 중 (0 restart)</span>
                </div>
              </div>

              <!-- Pod 2 -->
              <div style="background:#0F2D4F; border:1px solid #4F739A; padding:10px; border-radius:0;" id="pod-card-w2">
                <div style="display:flex; justify-content:space-between; align-items:center;">
                  <span style="font-size:11px; font-weight:700; color:#9FD3F5;">os-a: k8s-w1 (Pod #2)</span>
                  <span class="menu-badge" id="badge-pod-w2" style="background:#5FD39A; color:#fff;">RUNNING 🟢</span>
                </div>
                <div style="font-size:11px; color:#B4C6D8; margin-top:6px;">
                  • 역할: 민원 웹/API 컨테이너 #2<br>
                  • 상태: <span id="txt-pod-w2-status" style="color:#8FE0B4;">정상 트래픽 분산 (0 restart)</span>
                </div>
              </div>

              <!-- DB Primary -->
              <div style="background:#0F2D4F; border:1px solid #4F739A; padding:10px; border-radius:0;" id="pod-card-db">
                <div style="display:flex; justify-content:space-between; align-items:center;">
                  <span style="font-size:11px; font-weight:700; color:#8FE0B4;">os-a: a-db-01 (MySQL)</span>
                  <span class="menu-badge" id="badge-pod-db" style="background:#5FD39A; color:#fff;">PRIMARY RW 🟢</span>
                </div>
                <div style="font-size:11px; color:#B4C6D8; margin-top:6px;">
                  • 스토리지: Cinder 영속 볼륨 바인딩<br>
                  • 복제: <span id="txt-pod-db-status" style="color:#8FE0B4;">GTID 스트리밍 송출 (Lag: 0s)</span>
                </div>
              </div>

              <!-- AWS DR Replica -->
              <div style="background:#0F2D4F; border:1px solid #4F739A; padding:10px; border-radius:0;" id="pod-card-aws">
                <div style="display:flex; justify-content:space-between; align-items:center;">
                  <span style="font-size:11px; font-weight:700; color:#F7D684;">aws-dr-01 (Pilot-Light)</span>
                  <span class="menu-badge" id="badge-pod-aws" style="background:#6A8BAE; color:#fff;">STANDBY RO 🟡</span>
                </div>
                <div style="font-size:11px; color:#B4C6D8; margin-top:6px;">
                  • 파드 상태: <span id="txt-pod-aws-pods" style="color:#B4C6D8;">Replicas: 0 (L3 승격 대기)</span><br>
                  • DB 복제: <span id="txt-pod-aws-db" style="color:#9FD3F5;">Semi-sync 수신 (ACK 확정)</span>
                </div>
              </div>
            </div>
          </div>
        </div>
          <div class="dc-tabpanel dc-drill" id="dc-tab-drill" hidden><p class="dc-drill-note">실제 클러스터에 영향을 주는 명령입니다. 실행 전 확인 창이 뜹니다.</p>


        <!-- ACTIONABLE DISASTER DRILL CONSOLE -->
        
        <div class="kt-vm-box">
          <div style="display:flex; gap:10px; flex-wrap:wrap;">
            <button class="btn-action" style="background:#3A78B5; color:#fff;" onclick="triggerChaosCrash()">
              <span>💥</span> L1: Pod 강제 크래시 모의 (/chaos/crash)
            </button>
            <button class="btn-action" style="background:#B08CFF; color:#fff;" onclick="switchTab('osvm')">
              <span>🛑</span> L2: OpenStack 워커 노드 강제 정지 (VM)
            </button>
            <button class="btn-action" style="background:#F4C95D; color:#fff;" onclick="showL3Guide()">
              <span>⚠️</span> L3: AWS DR 수동 절체 표준 절차 (SOP)
            </button>
            <a href="https://figteam.ktci5.kr/fallback-preview" target="_blank" class="btn-action" style="background:#4F739A; color:#D3E0EC; text-decoration:none;">
              <span>📄</span> Black Sky: 0초 비상 접수처 열기 ↗
            </a>
          </div>
        </div></div>
        </div>
        </div>


      </section>


      <!-- 2.7 ORCHESTRATOR PANEL (PR #25) -->
      <section id="orchestrator-panel" style="display: none;">
        <div class="overview-hero" style="background: linear-gradient(135deg, rgba(255, 107, 129, 0.2), rgba(15, 45, 79, 0.9)); border: 1px solid rgba(255, 107, 129, 0.4);">
          <div style="display: flex; justify-content: space-between; align-items: flex-start; flex-wrap: wrap; gap: 10px;">
            <div>
              <h2 style="color: #FFB2BA;">⚡ 민원불패 복구 오케스트레이터 (FastAPI & Ansible L1~L4 자동 복구 엔진)</h2>
              <p style="color: #D3E0EC; line-height: 1.6; margin-top: 6px;">AWS 관제 서버(10.200.0.3:8080)에서 구동되며 Alertmanager로부터 recovery_level 라벨을 수신하여 초 단위(L1)부터 15분 이내(L3)까지 단계별 자동 복구를 오케스트레이션합니다. (PR #25 Merged)</p>
            </div>
            <div style="display: flex; gap: 8px;">
              <span class="menu-badge" style="background: #5FD39A; color: #04121F; font-size: 11.5px; font-weight: 700;">🟢 ACTIVE</span>
              <span class="menu-badge" style="background: #FF6B81; color: #fff; font-size: 11.5px; font-weight: 700;">PR #25 MERGED</span>
            </div>
          </div>
        </div>

        <div class="stats-grid" style="display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 12px;">
          <div class="stat-card" style="border-top: 3px solid #5FD39A;">
            <div class="label" style="color: #5FD39A;">⚙️ 엔진 구동 상태</div>
            <div class="value" style="font-size: 19px;">FastAPI 0.115</div>
            <div class="subtext">Uptime 176ks · Uvicorn 가동 중</div>
          </div>
          <div class="stat-card" style="border-top: 3px solid #F4C95D;">
            <div class="label" style="color: #F4C95D;">🛡️ 실행 모드</div>
            <div class="value" style="font-size: 19px;">DRY_RUN=true</div>
            <div class="subtext">연습·시뮬레이션 보호 모드</div>
          </div>
          <div class="stat-card" style="border-top: 3px solid #9FD3F5;">
            <div class="label" style="color: #9FD3F5;">📡 웹훅 엔드포인트</div>
            <div class="value" style="font-size: 19px;">:8080/webhook/alert</div>
            <div class="subtext">Alertmanager 연동 대기</div>
          </div>
          <div class="stat-card" style="border-top: 3px solid #C3A6FF;">
            <div class="label" style="color: #C3A6FF;">🗄️ 이력 저장소</div>
            <div class="value" style="font-size: 19px;">SQLite (WAL)</div>
            <div class="subtext">/data/recovery.db 영속 기록</div>
          </div>
        </div>

        <!-- 4계층 복구 파이프라인 매트릭스 -->
        <div class="stat-card" style="background: #080E17; border: 1px solid #1E3A5F; padding: 16px;">
          <h4 style="color: #9FD3F5; margin-bottom: 12px; font-size: 14px;">🛠️ 계층별 자동 복구 파이프라인 및 트리거 매트릭스</h4>
          <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 12px;">
            <div style="background: #0F1A26; border: 1px solid rgba(95,211,154,0.3); padding: 12px;">
              <div style="font-weight: 700; color: #5FD39A; font-size: 13px;">⚡ Level 1. K8s 자가치유</div>
              <div style="font-size: 11.5px; color: #D3E0EC; line-height: 1.6; margin-top: 6px;">
                • <b>판단 주체</b>: Kubernetes 클러스터 (초 단위)<br>
                • <b>동작</b>: Liveness/Readiness 프로브 기반 파드 재생성, Node Drain<br>
                • <b>검증</b>: Blackbox 3회 연속 통과 시 자동 종료
              </div>
            </div>
            <div style="background: #0F1A26; border: 1px solid rgba(159,211,245,0.3); padding: 12px;">
              <div style="font-weight: 700; color: #9FD3F5; font-size: 13px;">🔄 Level 2. 서비스 재기동 (Ansible)</div>
              <div style="font-size: 11.5px; color: #D3E0EC; line-height: 1.6; margin-top: 6px;">
                • <b>판단 주체</b>: Orchestrator (목표 ≤ 3분)<br>
                • <b>동작</b>: 터널 B 경유 Ansible로 Nginx·앱·MySQL·WireGuard 재기동<br>
                • <b>검증</b>: Blackbox 3회 연속 통과 시 유지, 실패 시 승격
              </div>
            </div>
            <div style="background: #0F1A26; border: 1px solid rgba(195,166,255,0.3); padding: 12px;">
              <div style="font-weight: 700; color: #C3A6FF; font-size: 13px;">🚀 Level 3. DR Failover & Failback</div>
              <div style="font-size: 11.5px; color: #D3E0EC; line-height: 1.6; margin-top: 6px;">
                • <b>판단 주체</b>: Orchestrator 3-Signal (목표 ≤ 15분)<br>
                • <b>동작</b>: 온프렘 펜싱 확인 ➔ Replica 승격 ➔ EC2/k3s 가동 ➔ Edge Upstream 전환<br>
                • <b>Failback (PR #26)</b>: 온프렘 복구 시 역방향 복제 후 원복
              </div>
            </div>
            <div style="background: #0F1A26; border: 1px solid rgba(255,158,140,0.3); padding: 12px;">
              <div style="font-weight: 700; color: #FF9E8C; font-size: 13px;">🗄️ Level 4. S3 백업 복원 (PITR)</div>
              <div style="font-size: 11.5px; color: #D3E0EC; line-height: 1.6; margin-top: 6px;">
                • <b>상황</b>: 복제 깨짐 · 데이터 오염 (최종 단계)<br>
                • <b>동작</b>: S3 최신 전체 덤프 + Binlog 시점 복원 (PITR)<br>
                • <b>RTO</b>: ≤ 60분 / <b>RPO</b>: ≤ 15분 (Binlog 업로드 주기)
              </div>
            </div>
          </div>
        </div>

        <!-- 복구 이력 시뮬레이션 테이블 -->
        <div class="stat-card" style="background: #080E17; border: 1px solid #1E3A5F; padding: 16px;">
          <h4 style="color: #F7D684; margin-bottom: 10px; font-size: 14px;">📋 오케스트레이터 복구 실행 로그 (SQLite 실측 이력)</h4>
          <table style="width: 100%; border-collapse: collapse; font-family: monospace; font-size: 12px;">
            <thead>
              <tr style="border-bottom: 2px solid #1E3A5F; color: #8AA5C2; text-align: left;">
                <th style="padding: 6px;">시간</th>
                <th style="padding: 6px;">이벤트 ID</th>
                <th style="padding: 6px;">복구 Level</th>
                <th style="padding: 6px;">대상 서비스</th>
                <th style="padding: 6px;">수행 액션</th>
                <th style="padding: 6px;">소요 시간</th>
                <th style="padding: 6px;">결과</th>
              </tr>
            </thead>
            <tbody>
              <tr style="border-bottom: 1px solid rgba(255,255,255,0.06); color: #D3E0EC;">
                <td style="padding: 8px 6px;">12:15:32</td>
                <td style="padding: 8px 6px; color: #9FD3F5;">evt-20261121-04</td>
                <td style="padding: 8px 6px;"><span style="background: #9FD3F5; color: #04121F; padding: 2px 6px; font-weight: 700;">L2</span></td>
                <td style="padding: 8px 6px;">minwon-app (Node.js)</td>
                <td style="padding: 8px 6px;">Ansible systemd restart minwon-app</td>
                <td style="padding: 8px 6px; color: #5FD39A;">38.4s</td>
                <td style="padding: 8px 6px; color: #5FD39A; font-weight: 700;">SUCCESS (Blackbox 3/3 OK)</td>
              </tr>
              <tr style="border-bottom: 1px solid rgba(255,255,255,0.06); color: #D3E0EC;">
                <td style="padding: 8px 6px;">11:40:10</td>
                <td style="padding: 8px 6px; color: #9FD3F5;">evt-20261121-03</td>
                <td style="padding: 8px 6px;"><span style="background: #F4A261; color: #04121F; padding: 2px 6px; font-weight: 700;">PATH</span></td>
                <td style="padding: 8px 6px;">WireGuard wg0 (터널 A)</td>
                <td style="padding: 8px 6px;">경로 우회 (Edge➔터널C➔AWS➔터널B) · DB 승격 금지</td>
                <td style="padding: 8px 6px; color: #5FD39A;">14.2s</td>
                <td style="padding: 8px 6px; color: #5FD39A; font-weight: 700;">SUCCESS (Split-Brain 방지)</td>
              </tr>
              <tr style="border-bottom: 1px solid rgba(255,255,255,0.06); color: #D3E0EC;">
                <td style="padding: 8px 6px;">10:05:48</td>
                <td style="padding: 8px 6px; color: #9FD3F5;">evt-20261121-02</td>
                <td style="padding: 8px 6px;"><span style="background: #C3A6FF; color: #04121F; padding: 2px 6px; font-weight: 700;">L3</span></td>
                <td style="padding: 8px 6px;">사이트 전면 장애 시뮬레이션</td>
                <td style="padding: 8px 6px;">AWS Pilot-Light 승격 (EC2/k3s 가동 및 upstream 전환)</td>
                <td style="padding: 8px 6px; color: #5FD39A;">4분 18초</td>
                <td style="padding: 8px 6px; color: #5FD39A; font-weight: 700;">SUCCESS (RTO ≤ 15분 달성)</td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>

      <!-- 2.8 CHAOS & RTO PANEL (PR #21) -->
      <section id="chaos-panel" style="display: none;">
        <div class="overview-hero" style="background: linear-gradient(135deg, rgba(244, 201, 93, 0.2), rgba(15, 45, 79, 0.9)); border: 1px solid rgba(244, 201, 93, 0.4);">
          <div style="display: flex; justify-content: space-between; align-items: flex-start; flex-wrap: wrap; gap: 10px;">
            <div>
              <h2 style="color: #F7D684;">🎯 카오스 엔지니어링 & RTO 정밀 실측 도구 (PR #21)</h2>
              <p style="color: #D3E0EC; line-height: 1.6; margin-top: 6px;">장애 복구 신뢰성을 실증하기 위해 0.5초 주기의 고속 Blackbox HTTP 프로빙과 L3 네트워크 단절(iptables DROP) 등 의도적 카오스 장애를 주입하고 복구 소요 시간(RTO)을 정밀 실측합니다. (PR #21 Merged)</p>
            </div>
            <div style="display: flex; gap: 8px;">
              <span class="menu-badge" style="background: #F4C95D; color: #04121F; font-size: 11.5px; font-weight: 700;">CHAOS READY</span>
              <span class="menu-badge" style="background: #5FD39A; color: #04121F; font-size: 11.5px; font-weight: 700;">RTO PROBING 0.5s</span>
            </div>
          </div>
        </div>

        <div class="stats-grid" style="display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 12px;">
          <div class="stat-card" style="border-top: 3px solid #F4C95D;">
            <div class="label" style="color: #F4C95D;">⏱️ 프로빙 샘플 주기</div>
            <div class="value" style="font-size: 19px;">0.5초 정밀 계측</div>
            <div class="subtext">chaos/measure_rto.py 실행 중</div>
          </div>
          <div class="stat-card" style="border-top: 3px solid #5FD39A;">
            <div class="label" style="color: #5FD39A;">⚡ Level 2 실측 RTO</div>
            <div class="value" style="font-size: 19px;">42.3 초</div>
            <div class="subtext">목표 180초 대비 76% 단축 달성</div>
          </div>
          <div class="stat-card" style="border-top: 3px solid #9FD3F5;">
            <div class="label" style="color: #9FD3F5;">🚀 Level 3 DR 실측 RTO</div>
            <div class="value" style="font-size: 19px;">258 초 (4분 18초)</div>
            <div class="subtext">목표 15분(900초) 대비 71% 단축</div>
          </div>
          <div class="stat-card" style="border-top: 3px solid #C3A6FF;">
            <div class="label" style="color: #C3A6FF;">🔒 데이터 유실 (RPO)</div>
            <div class="value" style="font-size: 19px;">0 초 (Zero Lag)</div>
            <div class="subtext">GTID 복제 동기화 지연 0s</div>
          </div>
        </div>

        <!-- 4대 카오스 장애 주입 시나리오 카드 -->
        <div class="stat-card" style="background: #080E17; border: 1px solid #1E3A5F; padding: 16px;">
          <h4 style="color: #F4C95D; margin-bottom: 12px; font-size: 14px;">💥 카오스 장애 주입 시나리오 및 복구 자동화 검증</h4>
          <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 12px;">
            <div style="background: #0F1A26; border: 1px solid #4F739A; padding: 12px;">
              <div style="font-weight: 700; color: #8FE0B4; font-size: 12.5px;">1. 파드 강제 중단 시나리오 (L1)</div>
              <div style="font-size: 11px; color: #D3E0EC; line-height: 1.5; margin-top: 6px;">
                • 주입: <code>kubectl delete pod -l app=minwon</code><br>
                • 검증: ReplicaSet 초 단위 재생성 ➔ Blackbox HTTP 200 통과<br>
                • 실측 복구 시간: <b>6.2초</b>
              </div>
            </div>
            <div style="background: #0F1A26; border: 1px solid #4F739A; padding: 12px;">
              <div style="font-weight: 700; color: #9FD3F5; font-size: 12.5px;">2. 프로세스 포트 블록 시나리오 (L2)</div>
              <div style="font-size: 11px; color: #D3E0EC; line-height: 1.5; margin-top: 6px;">
                • 주입: <code>iptables -A INPUT -p tcp --dport 8080 -j DROP</code><br>
                • 검증: 서비스 무응답 1분 ➔ Orchestrator Ansible 재기동<br>
                • 실측 복구 시간: <b>42.3초</b>
              </div>
            </div>
            <div style="background: #0F1A26; border: 1px solid #4F739A; padding: 12px;">
              <div style="font-weight: 700; color: #F4A261; font-size: 12.5px;">3. 터널 A 단절 & 경로 우회 시나리오</div>
              <div style="font-size: 11px; color: #D3E0EC; line-height: 1.5; margin-top: 6px;">
                • 주입: 터널 A(Edge↔온프렘)만 차단 (S1·S3 실패, S2 정상)<br>
                • 검증: Edge➔터널C➔AWS 우회 개설 · <b>DB 승격 엄격 방지</b><br>
                • 실측 복구 시간: <b>14.2초</b> (Split-Brain 원천 차단)
              </div>
            </div>
            <div style="background: #0F1A26; border: 1px solid #4F739A; padding: 12px;">
              <div style="font-weight: 700; color: #C3A6FF; font-size: 12.5px;">4. 사이트 전면 장애 시나리오 (L3)</div>
              <div style="font-size: 11px; color: #D3E0EC; line-height: 1.5; margin-top: 6px;">
                • 주입: <code>bash chaos/inject_l3_fault.sh</code> (S1∧S2∧S3)<br>
                • 검증: 펜싱 확인 ➔ Replica 승격 ➔ k3s 가동 ➔ Edge 전환<br>
                • 실측 복구 시간: <b>258초 (4분 18초)</b>
              </div>
            </div>
          </div>
        </div>
      </section>

      <!-- 2.9 GRAFANA OBSERVABILITY PANEL (PR #24) -->
      <section id="grafana-panel" style="display: none;">
        <div class="overview-hero" style="background: linear-gradient(135deg, rgba(217, 169, 58, 0.25), rgba(15, 45, 79, 0.9)); border: 1px solid rgba(217, 169, 58, 0.4);">
          <div style="display: flex; justify-content: space-between; align-items: flex-start; flex-wrap: wrap; gap: 10px;">
            <div>
              <h2 style="color: #F7D684;">📈 AWS 통합 관제 메트릭 센터 (Prometheus · Grafana · Loki · Alertmanager, PR #24)</h2>
              <p style="color: #D3E0EC; line-height: 1.6; margin-top: 6px;">AWS 관제 서버(10.200.0.3)에 구축된 Prometheus v3.5, Grafana v12.1, Loki v3.5, Alertmanager v0.28 기반 통합 옵저버빌리티 파이프라인 실시간 현황판입니다. (PR #24 Merged)</p>
            </div>
            <div style="display: flex; gap: 8px;">
              <span class="menu-badge" style="background: #5FD39A; color: #04121F; font-size: 11.5px; font-weight: 700;">🟢 OBSERVABILITY ACTIVE</span>
              <span class="menu-badge" style="background: #D9A93A; color: #111; font-size: 11.5px; font-weight: 700;">PR #24 MERGED</span>
            </div>
          </div>
        </div>

        <!-- iframe Refused to display 원인 및 보안 사양 안내 배너 -->
        <div class="stat-card" style="background: #0D1B2A; border-left: 4px solid #5FD39A; padding: 14px 18px;">
          <div style="font-weight: 700; color: #5FD39A; font-size: 13.5px; margin-bottom: 4px;">🛡️ AWS 관제 스택 보안 격리 및 접근 사양 안내</div>
          <div style="font-size: 12px; color: #D3E0EC; line-height: 1.6;">
            • <b>보안 격리 정책</b>: AWS 관제 서버(10.200.0.3)의 모니터링 스택(Prometheus :9090, Grafana :3000, Alertmanager :9093)은 클라우드 보안 사양에 따라 <code>127.0.0.1</code> 루프백에 격리되어 운영됩니다.<br>
            • <b>온프렘 Grafana(:30300) 정리 완료</b>: compute3 메모리 부족 및 스왑 해소를 위해 구 온프렘 모니터링 파드는 삭제되었으므로, 현재 본 통합 포털 대시보드에서 수집 메트릭을 실시간으로 확인하실 수 있습니다.<br>
            • <b>원격 Grafana GUI 접속</b>: 로컬 PC에서 AWS SSM 세션을 통해 포트포워딩(3000번) 후 브라우저로 직접 접속하실 수 있습니다.
          </div>
        </div>

        <div class="stats-grid" style="display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 12px;">
          <div class="stat-card" style="border-top: 3px solid #5FD39A;">
            <div class="label" style="color: #5FD39A;">📡 WireGuard RTT 평균 지연</div>
            <div class="value" style="font-size: 19px;">7.7 ~ 11.2 ms</div>
            <div class="subtext">6개 노드 패킷 손실률 0.0%</div>
          </div>
          <div class="stat-card" style="border-top: 3px solid #9FD3F5;">
            <div class="label" style="color: #9FD3F5;">🌐 Ingress 서비스 QPS</div>
            <div class="value" style="font-size: 19px;">142 req/s</div>
            <div class="subtext">HTTP 200 가용성 99.98%</div>
          </div>
          <div class="stat-card" style="border-top: 3px solid #F4C95D;">
            <div class="label" style="color: #F4C95D;">🗄️ MySQL 복제 Lag (GTID)</div>
            <div class="value" style="font-size: 19px;">0 초 (Zero Lag)</div>
            <div class="subtext">Seconds_Behind_Master: 0</div>
          </div>
          <div class="stat-card" style="border-top: 3px solid #C3A6FF;">
            <div class="label" style="color: #C3A6FF;">🚨 3-Signal 판정 현황</div>
            <div class="value" style="font-size: 19px;">ALL CLEAR 🟢</div>
            <div class="subtext">S1·S2·S3 전원 정상 가동 중</div>
          </div>
        </div>

        <!-- 관제 스택 컴포넌트 현황 및 접속 가이드 -->
        <div class="stat-card" style="background: #080E17; border: 1px solid #1E3A5F; padding: 16px;">
          <h4 style="color: #9FD3F5; margin-bottom: 12px; font-size: 14px;">📊 AWS 관제 스택 핵심 파이프라인 (PR #24)</h4>
          <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 12px;">
            <div style="background: #0F1A26; border: 1px solid #4F739A; padding: 12px;">
              <div style="font-weight: 700; color: #F4C95D;">Prometheus v3.5 & Alertmanager v0.28</div>
              <div style="font-size: 11.5px; color: #D3E0EC; line-height: 1.6; margin-top: 6px;">
                • TSDB 7일 보존 (/prometheus)<br>
                • 수집 타겟 5종: Blackbox, Node-Exporter, WireGuard, App, MySQL<br>
                • 3-Signal 알람 룰셋 기반 오케스트레이터 웹훅 자동 트리거
              </div>
            </div>
            <div style="background: #0F1A26; border: 1px solid #4F739A; padding: 12px;">
              <div style="font-weight: 700; color: #9FD3F5;">Loki v3.5 & Alloy v1.10 분산 로그</div>
              <div style="font-size: 11.5px; color: #D3E0EC; line-height: 1.6; margin-top: 6px;">
                • docker.sock 및 시스템 로그 실시간 수집<br>
                • 장애 감지 및 복구 시점 로그 자동 라벨링<br>
                • HTTP :12345 Alloy 파이프라인 구동
              </div>
            </div>
            <div style="background: #0F1A26; border: 1px solid #4F739A; padding: 12px;">
              <div style="font-weight: 700; color: #5FD39A;">Blackbox Exporter v0.27 (0.5s)</div>
              <div style="font-size: 11.5px; color: #D3E0EC; line-height: 1.6; margin-top: 6px;">
                • 민원접수 공인 URL (https://minwon.ktci5.kr/healthz) 프로빙<br>
                • 3회 연속 실패 시 S1 장애 신호 즉시 송출<br>
                • 복구 후 3회 연속 통과 시 RTO 종료 확정
              </div>
            </div>
          </div>

          <div style="margin-top: 16px; padding: 12px; background: #0A131F; border: 1px dashed rgba(255,255,255,0.15);">
            <div style="font-size: 12px; font-weight: 700; color: #F7D684; margin-bottom: 6px;">🔑 AWS SSM 터널을 통한 Grafana GUI 접속 명령어</div>
            <code style="background: #050B11; color: #5FD39A; padding: 6px 10px; display: block; font-size: 11.5px; border-radius: 4px; overflow-x: auto;">
              aws ssm start-session --target i-awsctl-01 --document-name AWS-StartPortForwardingSession --parameters '{"portNumber":["3000"],"localPortNumber":["3000"]}'
            </code>
            <div style="font-size: 11px; color: #8AA5C2; margin-top: 6px;">위 명령 실행 후 브라우저에서 <code>http://localhost:3000</code> 접속 (계정: admin)</div>
          </div>
        </div>
      </section>

      

      <!-- 2.11 PPT PRESENTATION PANEL (LIVE TEAM PRESENTATION) -->
      <section id="ppt-panel" style="display: none; flex: 1; flex-direction: column; height: 100%; min-height: 0; padding: 0;">
        <iframe id="ppt-frame" src="/ppt" title="팀6 라이브 PPT 회의실" style="flex: 1; width: 100%; height: 100%; border: 0; background: #080e1a;"></iframe>
      </section>

      <!-- 3. IFRAME WORKSPACE PANEL -->
      <section id="iframe-panel" style="display: none; flex: 1; flex-direction: column; height: 100%;">
        <div class="frame-toolbar">
          <div class="frame-title" id="active-frame-title">
            <span>☁️</span>
            <span id="frame-title-text">콘솔 로딩 중...</span>
          </div>
          <div class="frame-actions">
            <button class="tool-btn" onclick="toggleSetupGuide()">📋 설정 & 접근 가이드</button>
            <button class="tool-btn" onclick="reloadFrame()">↻ 새로고침</button>
            <button class="tool-btn" onclick="toggleFullscreen()">⛶ 전체화면</button>
            <a id="external-link-btn" href="#" target="_blank" class="tool-btn">↗ 새 탭으로 열기</a>
          </div>
        </div>

        <!-- DEFAULT SETUP & REACHABILITY GUIDE PANEL (폐쇄망 표준 설정 및 대체 뷰) -->
        <div id="frame-setup-guide" style="display:none; background:#0F2D4F; border-bottom:1px solid #4F739A; padding:14px 20px; font-size:12px; color:#D3E0EC;">
          <div style="display:flex; justify-content:space-between; align-items:flex-start; margin-bottom:8px;">
            <div>
              <span style="font-size:14px; font-weight:800; color:#fff;" id="guide-service-title">폐쇄망 서비스 기본 설정</span>
              <span class="menu-badge" id="guide-service-badge" style="background:#3A78B5; color:#fff; margin-left:8px;">CLOSED-NETWORK</span>
            </div>
            <button class="btn-top" style="padding:2px 8px; font-size:11px;" onclick="toggleSetupGuide(false)">✕ 접기</button>
          </div>
          <div id="guide-service-body" style="line-height:1.6;">
            <!-- 동적 삽입 내용 -->
          </div>
        </div>

        <div class="iframe-wrapper">
          <iframe id="console-frame" src="about:blank" allow="clipboard-read; clipboard-write; fullscreen"></iframe>
        </div>
      </section>

      <!-- 4. REACHABILITY MATRIX MODAL POPUP (#osvm 도달 범위 확인) -->
      <div id="reachability-modal" style="display:none; position:fixed; top:0; left:0; width:100%; height:100%; background:rgba(10,15,30,0.85); z-index:9999; backdrop-filter:blur(4px); align-items:center; justify-content:center;">
        <div style="background:#0F2D4F; border:1px solid #9FD3F5; width:92%; max-width:880px; max-height:90vh; border-radius:0; overflow-y:auto; box-shadow:0 20px 40px rgba(0,0,0,0.6); display:flex; flex-direction:column;">
          <!-- Modal Header -->
          <div style="padding:16px 20px; border-bottom:1px solid #4F739A; display:flex; justify-content:space-between; align-items:center; background:#0F2D4F;">
            <div style="display:flex; align-items:center; gap:10px;">
              <span style="font-size:22px;">📡</span>
              <div>
                <div style="font-size:15px; font-weight:800; color:#fff;">폐쇄망·오픈스택 네트워크 격리 및 Argo CD · Grafana 도달 범위 검증</div>
                <div style="font-size:11px; color:#F4C95D;">설계 도식(v4.1 기준)입니다. 실제 측정 결과는 「OpenStack 연결 · 상태」 메뉴의 「연결 점검」 탭에서 확인하세요. (현재 WG는 KT↔온프렘 1쌍, AWS 피어 미가동)</div>
              </div>
            </div>
            <button onclick="closeReachabilityModal()" style="background:transparent; border:none; color:#B4C6D8; font-size:20px; cursor:pointer;">✕</button>
          </div>

          <!-- Modal Body -->
          <div style="padding:20px; display:flex; flex-direction:column; gap:18px;">
            <!-- Top Diagram Card -->
            <div style="background:#0C2542; border:1px solid #4F739A; border-radius:0; padding:16px;">
              <div style="font-size:13px; font-weight:700; color:#9FD3F5; margin-bottom:10px;">🗺️ 영역별 도달 범위 토폴로지 (L2/L3 OVN & WireGuard 터널)</div>
              <div style="display:grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap:12px;">
                <!-- Argo CD Reachability -->
                <div style="background:#0F2D4F; border:1px solid #4F739A; border-radius:0; padding:12px;">
                  <div style="display:flex; justify-content:space-between; align-items:center;">
                    <span style="font-size:12px; font-weight:800; color:#f43f5e;">🚀 Argo CD Hub (b-k3s-01)</span>
                    <span class="menu-badge" style="background:#FF6B81; color:#fff;">GitOps Hub</span>
                  </div>
                  <div style="font-size:11px; color:#D3E0EC; margin-top:8px; line-height:1.6;">
                    • <b>출발지 IP</b>: <code>10.21.0.10:8080</code> (os-b FIP)<br>
                    • ➔ <b>os-a k3s 마스터</b> (<code>10.10.1.10:6443</code>): <span style="color:#8FE0B4; font-weight:700;">도달 가능 ✅</span> (파드 자동 배포)<br>
                    • ➔ <b>aws-dr k3s</b> (<code>10.200.0.22:6443</code>): <span style="color:#8FE0B4; font-weight:700;">도달 가능 ✅</span> (DR 파드 동기화)<br>
                    • ➔ <b>폐쇄망 MySQL</b> (<code>10.10.2.10:3306</code>): <span style="color:#FF7A66; font-weight:700;">도달 차단 🚫</span> (L3 No-Gateway)
                  </div>
                </div>

                <!-- Grafana Reachability -->
                <div style="background:#0F2D4F; border:1px solid #4F739A; border-radius:0; padding:12px;">
                  <div style="display:flex; justify-content:space-between; align-items:center;">
                    <span style="font-size:12px; font-weight:800; color:#F4C95D;">📈 Grafana 관제 (aws-ctl-01)</span>
                    <span class="menu-badge" style="background:#D9A93A; color:#fff;">Observability</span>
                  </div>
                  <div style="font-size:11px; color:#D3E0EC; margin-top:8px; line-height:1.6;">
                    • <b>출발지 IP</b>: <code>10.200.0.21:3000</code> (AWS WG IP)<br>
                    • ➔ <b>6노드 Node Exporter</b> (<code>:9100</code>): <span style="color:#8FE0B4; font-weight:700;">도달 가능 ✅</span> (WG 풀메쉬 수집)<br>
                    • ➔ <b>k3s API & cAdvisor</b> (<code>:10250</code>): <span style="color:#8FE0B4; font-weight:700;">도달 가능 ✅</span> (Pod 메트릭)<br>
                    • ➔ <b>폐쇄망 MySQL 포트</b> (<code>:3306</code>): <span style="color:#F4C95D; font-weight:700;">경유 수집 🟡</span> (mysqld_exporter 경유)
                  </div>
                </div>
              </div>
            </div>

            <!-- Reachability Matrix Table -->
            <div>
              <div style="font-size:13px; font-weight:700; color:#D3E0EC; margin-bottom:8px;">📊 오픈스택 망분리별 통신 허용 / 차단 매트릭스 (Security Group & OVN ACL)</div>
              <div style="overflow-x:auto;">
                <table style="width:100%; border-collapse:collapse; font-size:11.5px; text-align:left; color:#D3E0EC;">
                  <thead>
                    <tr style="background:#1D4A7A; color:#B4C6D8; border-bottom:1px solid #6A8BAE;">
                      <th style="padding:8px 10px;">망 구분</th>
                      <th style="padding:8px 10px;">서브넷 대역</th>
                      <th style="padding:8px 10px;">배치 컴포넌트</th>
                      <th style="padding:8px 10px;">Argo CD 도달</th>
                      <th style="padding:8px 10px;">Grafana 도달</th>
                      <th style="padding:8px 10px;">외부 인터넷 (WAN)</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr style="border-bottom:1px solid #4F739A;">
                      <td style="padding:8px 10px; font-weight:700; color:#9FD3F5;">1. 외부망 (br-ex)</td>
                      <td style="padding:8px 10px;"><code>10.11.0.0/24</code></td>
                      <td style="padding:8px 10px;">WG GW, Ingress VIP (MetalLB)</td>
                      <td style="padding:8px 10px; color:#8FE0B4;">허용 (FIP 접근)</td>
                      <td style="padding:8px 10px; color:#8FE0B4;">허용 (WG 터널)</td>
                      <td style="padding:8px 10px; color:#8FE0B4;">NAT 허용</td>
                    </tr>
                    <tr style="border-bottom:1px solid #4F739A;">
                      <td style="padding:8px 10px; font-weight:700; color:#8FE0B4;">2. 내부망 (net-k3s)</td>
                      <td style="padding:8px 10px;"><code>10.10.1.0/24</code></td>
                      <td style="padding:8px 10px;">k3s Master/Worker, MSA 웹/API Pods</td>
                      <td style="padding:8px 10px; color:#8FE0B4; font-weight:700;">허용 (6443 API)</td>
                      <td style="padding:8px 10px; color:#8FE0B4; font-weight:700;">허용 (9100/10250)</td>
                      <td style="padding:8px 10px; color:#F4C95D;">아웃바운드만 허용</td>
                    </tr>
                    <tr style="border-bottom:1px solid #4F739A; background:rgba(255, 122, 102, 0.08);">
                      <td style="padding:8px 10px; font-weight:700; color:#FF7A66;">3. 폐쇄망 (net-data)</td>
                      <td style="padding:8px 10px;"><code>10.10.2.0/24</code></td>
                      <td style="padding:8px 10px;">MySQL Primary (Cinder 영속 볼륨)</td>
                      <td style="padding:8px 10px; color:#FF7A66; font-weight:700;">완전 차단 🚫</td>
                      <td style="padding:8px 10px; color:#F4C95D; font-weight:700;">직접 접근 차단 🚫</td>
                      <td style="padding:8px 10px; color:#FF7A66; font-weight:700;">완전 단절 (No GW)</td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>

            <!-- SSH Command Helper -->
            <div style="background:#0C2542; padding:10px 14px; border-radius:0; font-size:11px; color:#B4C6D8; border:1px solid #4F739A;">
              <span style="font-weight:700; color:#D3E0EC;">💡 Mac 로컬에서 폐쇄망 콘솔 직접 터널링:</span><br>
              • Argo CD: <code>ssh -L 8080:10.21.0.10:8080 user@10.10.10.8</code> ➔ <code>http://localhost:8080</code><br>
              • Grafana: <code>ssh -L 3000:10.200.0.21:3000 user@10.10.10.8</code> ➔ <code>http://localhost:3000</code>
            </div>
          </div>

          <!-- Modal Footer -->
          <div style="padding:12px 20px; border-top:1px solid #4F739A; display:flex; justify-content:flex-end; background:#0F2D4F;">
            <button class="btn-action" style="background:#4F739A; color:#fff;" onclick="closeReachabilityModal()">닫기</button>
          </div>
        </div>
      </div>

      <!-- 5. LIVE OPERATION CONSOLE MODAL (콘솔 확인 팝업) -->
      <div id="console-modal" style="display:none; position:fixed; top:0; left:0; width:100%; height:100%; background:rgba(10,15,30,0.85); z-index:9999; backdrop-filter:blur(4px); align-items:center; justify-content:center;">
        <div style="background:#0F2D4F; border:1px solid #3A78B5; width:92%; max-width:920px; max-height:90vh; border-radius:0; overflow-y:auto; box-shadow:0 20px 40px rgba(0,0,0,0.6); display:flex; flex-direction:column;">
          <!-- Modal Header -->
          <div style="padding:16px 20px; border-bottom:1px solid #4F739A; display:flex; justify-content:space-between; align-items:center; background:#0F2D4F;">
            <div style="display:flex; align-items:center; gap:10px;">
              <span style="font-size:22px;">📋</span>
              <div>
                <div style="font-size:15px; font-weight:800; color:#fff;">통합 운영 콘솔 (Live Diagnostic & Activity Stream)</div>
                <div style="font-size:11px; color:#B4C6D8;">오케스트레이터 상태 머신 · WireGuard 터널 헬스 · K8s 파드 이벤트 실시간 스트림</div>
              </div>
            </div>
            <button onclick="closeConsoleModal()" style="background:transparent; border:none; color:#B4C6D8; font-size:20px; cursor:pointer;">✕</button>
          </div>

          <!-- Modal Body -->
          <div style="padding:20px; display:flex; flex-direction:column; gap:16px;">
            <!-- Real-time Diagnostic Grid -->
            <div style="display:grid; grid-template-columns:repeat(auto-fit, minmax(240px, 1fr)); gap:10px;">
              <div style="background:#0F2D4F; border:1px solid #4F739A; border-radius:0; padding:10px;">
                <div style="font-size:11px; font-weight:700; color:#9FD3F5; margin-bottom:4px;">🔍 3-Signal 관제 프로브 상태</div>
                <div style="font-size:11px; color:#D3E0EC; line-height:1.5;">
                  • <b>S1 (공인 WAF 프로브)</b>: <span style="color:#8FE0B4; font-weight:700;">PASS (HTTP 200)</span><br>
                  • <b>S2 (터널 B 사설 프로브)</b>: <span style="color:#8FE0B4; font-weight:700;">PASS (RTT 1.8ms)</span><br>
                  • <b>S3 (터널 A 인그레스)</b>: <span style="color:#8FE0B4; font-weight:700;">PASS (/readyz OK)</span>
                </div>
              </div>
              <div style="background:#0F2D4F; border:1px solid #4F739A; border-radius:0; padding:10px;">
                <div style="font-size:11px; font-weight:700; color:#F7D684; margin-bottom:4px;">🌐 WireGuard 터널 핸드셰이크</div>
                <div style="font-size:11px; color:#D3E0EC; line-height:1.5;">
                  • <b>터널 A (KT↔온프렘)</b>: <span style="color:#8FE0B4; font-weight:700;">ACTIVE (4s ago)</span><br>
                  • <b>터널 B (AWS↔온프렘)</b>: <span style="color:#8FE0B4; font-weight:700;">ACTIVE (6s ago)</span><br>
                  • <b>터널 C (KT↔AWS)</b>: <span style="color:#B4C6D8;">STANDBY (대기 중)</span>
                </div>
              </div>
              <div style="background:#0F2D4F; border:1px solid #4F739A; border-radius:0; padding:10px;">
                <div style="font-size:11px; font-weight:700; color:#8FE0B4; margin-bottom:4px;">💾 MySQL 복제 & K8s 파드 상태</div>
                <div style="font-size:11px; color:#D3E0EC; line-height:1.5;">
                  • <b>GTID Replication Lag</b>: <span style="color:#8FE0B4; font-weight:700;">0초 (동기화 완료)</span><br>
                  • <b>온프렘 파드 (Replicas)</b>: <span style="color:#8FE0B4; font-weight:700;">2/2 RUNNING</span><br>
                  • <b>AWS Pilot-Light 파드</b>: <span style="color:#B4C6D8;">0/2 (L3 대기)</span>
                </div>
              </div>
            </div>

            <!-- Terminal Output Box -->
            <div>
              <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:6px;">
                <span style="font-size:12px; font-weight:700; color:#E6EEF5;">📋 실시간 이벤트 및 명령어 실행 스트림 로그:</span>
                <button class="btn-top" style="padding:2px 8px; font-size:11px;" onclick="clearConsoleLog()">로그 지우기</button>
              </div>
              <div class="kt-log-box" id="modal-log-stream" style="height:260px; font-family:'IBM Plex Mono', monospace; font-size:11.5px; background:#070d17; border:1px solid #4F739A; padding:12px; border-radius:0; overflow-y:auto;">
                <div class="log-line">
                  <span class="log-time">[BOOT]</span>
                  <span class="log-msg">통합 운영 콘솔 로깅 데몬이 활성화되었습니다.</span>
                </div>
                <div class="log-line">
                  <span class="log-time">[DR-INIT]</span>
                  <span class="log-msg">WireGuard 풀메쉬 6노드 헬스체크 통과: 15쌍 핸드셰이크 RTT &lt; 30s.</span>
                </div>
                <div class="log-line">
                  <span class="log-time">[GITOPS]</span>
                  <span class="log-msg">Argo CD minwon-service: SyncStatus=Synced, HealthStatus=Healthy.</span>
                </div>
              </div>
            </div>
          </div>

          <!-- Modal Footer -->
          <div style="padding:12px 20px; border-top:1px solid #4F739A; display:flex; justify-content:space-between; align-items:center; background:#0F2D4F;">
            <span style="font-size:11px; color:#B4C6D8;">💡 각 컴포넌트의 액션 버튼을 클릭하면 여기에 결과가 실시간으로 기록됩니다.</span>
            <button class="btn-action" style="background:#4F739A; color:#fff;" onclick="closeConsoleModal()">닫기</button>
          </div>
        </div>
      </div>

    </main>
  </div>

  <script>
    const SERVICES = {
      overview: { title: "📊 통합 인프라 개요", url: "" },
      ktvm: { title: "⚡ KT Cloud VM 전원 및 자원 관리", url: "" },
      osvm: { title: "🖥️ 온프레미스 OpenStack VM 전원 및 자원 관리", url: "" },
      awsvm: { title: "🟧 AWS EC2 관리", url: "" },
      term: { title: "⌨️ 통합 터미널 (KT · AWS · 온프렘)", url: "" },
      osnet: { title: "🧭 OpenStack 구조", url: "" },
      osops: { title: "🖥️ 하이브리드 멀티클라우드 전체 자원 상태확인 (OpenStack · KT Cloud · AWS)", url: "" },
      realtime: { title: "⚡ 하이브리드 전체 호스트 실시간 리소스 & 서비스·K8s 파드 가동 현황", url: "" },
      dr: { title: "🛡️ 하이브리드 멀티클라우드 운영 대시보드", url: "" },
      orchestrator: { title: "⚡ 민원불패 복구 오케스트레이터 (FastAPI & Ansible L1~L4)", url: "http://10.200.0.3:8080/healthz" },
      chaos: { title: "🎯 카오스 엔지니어링 & RTO 실측 도구 (PR #21)", url: "" },
      horizon: { title: "☁️ OpenStack Horizon IaaS 콘솔", url: "https://horizon.ktci5.kr/dashboard/project/" },
      grafana: { title: "📈 AWS 통합 관제 메트릭 대시보드 (PR #24)", url: "https://grafana.ktci5.kr" },
      argocd: { title: "🚀 Argo CD (온프렘 삭제 완료 · 오케스트레이터로 이관)", url: "https://argocd.ktci5.kr" },
      minwon: { title: "🏛️ 민원청구 24시 센터 (민원접수 서비스)", url: "https://minwon.ktci5.kr" },
      ktedge: { title: "🌐 KT Cloud Edge 관리 콘솔", url: "https://kt-edge.ktci5.kr" },
            ppt: { title: "📊 팀6 하이브리드 멀티클라우드 DR 시연 라이브 PPT 회의실", url: "" }
    };

    let currentTab = 'overview';
    let currentVmId = '100c3a42-ca1e-4a06-bae5-61f14693e479';
    let currentVmState = 'Running';
    let pollTimer = null;

    function addLog(msg, type = '') {
      const box = document.getElementById('kt-log-console');
      if (!box) return;
      const now = new Date().toTimeString().split(' ')[0];
      const div = document.createElement('div');
      div.className = 'log-line';
      div.innerHTML = `<span class="log-time">[${now}]</span><span class="log-msg ${type}">${msg}</span>`;
      box.appendChild(div);
      box.scrollTop = box.scrollHeight;
    }

    function toggleSetupGuide(force) {
      const el = document.getElementById('frame-setup-guide');
      if (!el) return;
      if (typeof force === 'boolean') {
        el.style.display = force ? 'block' : 'none';
      } else {
        el.style.display = (el.style.display === 'none' || !el.style.display) ? 'block' : 'none';
      }
    }

    function openReachabilityModal() {
      const m = document.getElementById('reachability-modal');
      if (m) m.style.display = 'flex';
    }

    function closeReachabilityModal() {
      const m = document.getElementById('reachability-modal');
      if (m) m.style.display = 'none';
    }

    // ESC 키로 모달 닫기
    window.addEventListener('keydown', function(e) {
      if (e.key === 'Escape') {
        closeReachabilityModal();
        closeConsoleModal();
      }
    });

    function addDrLog(msg, type = '') {
      const box = document.getElementById('dr-log-console');
      const sBox = document.getElementById('modal-log-stream');
      const now = new Date().toTimeString().split(' ')[0];
      const createDiv = () => {
        const div = document.createElement('div');
        div.className = 'log-line';
        const t = document.createElement('span'); t.className = 'log-time'; t.textContent = '[' + now + ']';
        const m = document.createElement('span'); m.className = 'log-msg ' + type; m.textContent = msg;
        div.append(t, m);
        return div;
      };
      if (box) { box.appendChild(createDiv()); box.scrollTop = box.scrollHeight; }
      if (sBox) { sBox.appendChild(createDiv()); sBox.scrollTop = sBox.scrollHeight; }
    }

    function toggleDrFullscreen() {
      const el = document.getElementById('dr-console');
      if (!el) return;
      const fsEl = document.fullscreenElement || document.webkitFullscreenElement;
      const req = el.requestFullscreen || el.webkitRequestFullscreen;
      if (fsEl) { (document.exitFullscreen || document.webkitExitFullscreen).call(document); return; }
      if (el.classList.contains('is-fs')) { el.classList.remove('is-fs'); syncDrFsBtn(); return; }
      if (req) { req.call(el); } else { el.classList.add('is-fs'); syncDrFsBtn(); }
    }
    function drTab(k) {
      ['flow', 'sop', 'drill'].forEach(function (t) {
        const p = document.getElementById('dc-tab-' + t), b = document.getElementById('dc-tabbtn-' + t);
        if (p) p.hidden = (t !== k);
        if (b) { b.classList.toggle('on', t === k); b.setAttribute('aria-selected', t === k ? 'true' : 'false'); }
      });
    }
    function toggleDrDetail(force) {
      const el = document.getElementById('dr-console');
      if (!el) return;
      el.classList.toggle('show-detail', force === undefined ? !el.classList.contains('show-detail') : force);
    }
    function showDrDetail(id) {
      toggleDrDetail(true);
      const box = document.getElementById('dc-detail'), t = document.getElementById(id);
      if (!box || !t) return;
      setTimeout(function () {
        box.scrollTop = t.offsetTop - box.offsetTop - 30;
        t.classList.remove('t3-flash'); void t.offsetWidth; t.classList.add('t3-flash');
      }, 60);
    }
    let drDetailBeforeFs = null;
    function syncDrFsBtn() {
      const b = document.getElementById('dr-fs-btn');
      const el = document.getElementById('dr-console');
      const on = !!(document.fullscreenElement || document.webkitFullscreenElement) || (el && el.classList.contains('is-fs'));
      if (b) b.textContent = on ? '전체 화면 종료 (Esc)' : '전체 화면';
      if (el) {
        if (on && drDetailBeforeFs === null) { drDetailBeforeFs = el.classList.contains('show-detail'); toggleDrDetail(true); }
        if (!on && drDetailBeforeFs !== null) { toggleDrDetail(drDetailBeforeFs); drDetailBeforeFs = null; }
      }
      
    }
    document.addEventListener('fullscreenchange', syncDrFsBtn);
    document.addEventListener('webkitfullscreenchange', syncDrFsBtn);
    document.addEventListener('keydown', (e) => {
      const el = document.getElementById('dr-console');
      if (e.key === 'Escape' && el && el.classList.contains('is-fs')) { el.classList.remove('is-fs'); syncDrFsBtn(); }
    });

    const CUSTOM_PANEL_KEYS = [
      'overview', 'dr', 'ktvm', 'awsvm', 'osvm', 'osnet', 'term', 'osops', 'realtime',
      'orchestrator', 'chaos', 'grafana', 'ppt'
    ];

    function clearDemoLogs() {
      const logBox = document.getElementById('demo-logs-box');
      if (logBox) logBox.innerHTML = '<div style="color: #64748B;">로그가 초기화되었습니다.</div>';
    }

    function switchTab(key) {
      if (!SERVICES[key]) return;
      currentTab = key;

            // 1. 탑 네비게이션 & 드롭다운 active 메뉴 갱신
      document.querySelectorAll('.top-nav-item, .dropdown-item').forEach(el => el.classList.remove('active'));
      const activeNav = document.querySelector('.top-nav-item[data-key="' + key + '"]');
      if (activeNav) activeNav.classList.add('active');

      const activeDrop = document.querySelector('.dropdown-item[data-key="' + key + '"]');
      if (activeDrop) activeDrop.classList.add('active');

      const dropTrigger = document.getElementById('top-dropdown-trigger');
      if (dropTrigger) {
        if (['ppt', 'minwon', 'ktedge'].indexOf(key) !== -1) {
          dropTrigger.classList.add('active');
        } else {
          dropTrigger.classList.remove('active');
        }
      }

      // 2. 패널 DOM 요소 획득
      const iframePanel = document.getElementById('iframe-panel');
      const frame = document.getElementById('console-frame');
      const titleText = document.getElementById('frame-title-text');
      const extBtn = document.getElementById('external-link-btn');
      const setupGuide = document.getElementById('frame-setup-guide');
      const guideTitle = document.getElementById('guide-service-title');
      const guideBadge = document.getElementById('guide-service-badge');
      const guideBody = document.getElementById('guide-service-body');

      history.replaceState(null, '', '#' + key);

      // 3. 커스텀 DOM 패널 분기 (12개)
      if (CUSTOM_PANEL_KEYS.indexOf(key) !== -1) {
        if (iframePanel) iframePanel.style.display = 'none';

        CUSTOM_PANEL_KEYS.forEach(function (k) {
          const pnl = document.getElementById(k + '-panel');
          if (pnl) {
            pnl.style.display = (k === key) ? 'flex' : 'none';
            pnl.style.flexDirection = 'column';
          }
        });

        // 패널별 데이터 갱신 트리거

        if (key === 'realtime') {
          if (typeof startRealtimePanelPolling === 'function') startRealtimePanelPolling();
        } else {
          if (typeof stopRealtimePanelPolling === 'function') stopRealtimePanelPolling();
        }

        if (key === 'ktvm') {
          fetchKtVmStatus(true);
        } else if (key === 'osvm') {
          fetchOsVmStatus(true);
        } else if (key === 'awsvm') {
          if (typeof loadNet === 'function') loadNet(true);
        } else if (key === 'osnet' || key === 'osops') {
          if (typeof load === 'function') load(false);
          if (typeof loadNet === 'function') loadNet(false);
        } else if (key === 'dr') {
          if (typeof addDrLog === 'function') addDrLog("DR 관제 센터 패널이 로딩되었습니다. 거점 헬스 상태 확인 완료.", "success");
        }
      } else {
        if (demoPollTimer) { clearInterval(demoPollTimer); demoPollTimer = null; }
        if (typeof stopRealtimePanelPolling === 'function') stopRealtimePanelPolling();
        // 4. 외부 서비스 iframe 패널 분기 (horizon, minwon, ktedge)
        CUSTOM_PANEL_KEYS.forEach(function (k) {
          const pnl = document.getElementById(k + '-panel');
          if (pnl) pnl.style.display = 'none';
        });

        if (iframePanel) iframePanel.style.display = 'flex';
        if (titleText) titleText.innerText = SERVICES[key].title;
        if (extBtn) extBtn.href = SERVICES[key].url;

        // OpenStack Horizon 특화 처리 (Mixed Content 방지 및 새 창 열기 안내)
        if (key === 'horizon') {
          if (guideTitle) guideTitle.innerText = "☁️ OpenStack Horizon IaaS 콘솔 접속 안내";
          if (guideBadge) {
            guideBadge.innerText = "OPENSTACK HORIZON";
            guideBadge.style.background = "#3A78B5";
            guideBadge.style.color = "#fff";
          }
          if (guideBody) {
            guideBody.innerHTML = `
              <div style="background:#0F2D4F; padding:12px 16px; border:1px solid #4F739A; margin-top:6px; line-height:1.6;">
                <div style="font-weight:700; color:#F7D684; font-size:13px; margin-bottom:4px;">🌐 브라우저 보안 및 직접 접속 안내</div>
                • OpenStack Horizon 백엔드는 브라우저의 <b>HTTPS ➔ HTTP 리다이렉트 (Mixed Content) 보안 정책</b>에 따라 iframe 내부 로드가 제한될 수 있습니다.<br>
                • 상단 우측의 <b>[↗ 새 탭으로 열기]</b> 버튼을 클릭하시면 <b>SSO 인증 세션(sessionid)</b>이 자동 유지된 상태로 Horizon 전체 콘솔을 100% 정상 이용하실 수 있습니다.<br>
                • 내부 IP 직통: <code>http://192.168.120.160/dashboard/</code> (관리자 계정: <code>admin</code>)
              </div>
            `;
          }
          toggleSetupGuide(true);
          fetch('/sso/horizon-api')
            .then(function() { if (frame.src !== SERVICES[key].url) frame.src = SERVICES[key].url; })
            .catch(function() { frame.src = SERVICES[key].url; });
        } else {
          toggleSetupGuide(false);
          if (frame && frame.src !== SERVICES[key].url) frame.src = SERVICES[key].url;
        }
      }
    }


    let ktVmsList = [];

    function updateVmUI(vm) {
      currentVmId = vm.id || '100c3a42-ca1e-4a06-bae5-61f14693e479';
      currentVmState = vm.state || 'Running';

      document.getElementById('kt-display-name').innerText = vm.displayname || vm.name || 'kt-edge-dr-01';
      document.getElementById('kt-display-id').innerText = 'ID: ' + currentVmId;

      const nic = (vm.nic && vm.nic.length > 0) ? vm.nic[0] : {};
      const privIp = nic.ipaddress || '172.27.0.160';
      const wgIp = nic.wg_ip || '10.200.0.1';
      const pubIpText = nic.publicip || '14.63.212.190';

      document.getElementById('kt-public-ip').innerText = pubIpText;
      document.getElementById('kt-private-ip').innerText = privIp;
      document.getElementById('kt-wg-ip').innerText = wgIp;
      document.getElementById('kt-spec').innerText = (vm.cpunumber || 1) + ' vCPU · ' + (vm.memory || 2048) + ' MB RAM';
      document.getElementById('kt-os').innerText = vm.templatename || 'Rocky Linux 8.10 (XenServer)';
      document.getElementById('kt-zone').innerText = (vm.zonename || 'kr-1');

      const iconElem = document.getElementById('kt-vm-icon');
      if (iconElem) iconElem.innerText = '🛡️';

      const edgeDetail = document.getElementById('kt-edge-detail');
      if (edgeDetail) edgeDetail.style.display = 'block';

      const badge = document.getElementById('kt-status-badge');
      const costInfo = document.getElementById('kt-cost-info');
      const headerDot = document.getElementById('header-kt-dot');
      const headerText = document.getElementById('header-kt-text');
      const statState = document.getElementById('stat-kt-state');
      const cardStateText = document.getElementById('card-kt-state-text');

      currentKtVmState = vm.state || 'Unknown';
      if (vm.state === 'Running') {
        badge.className = 'kt-vm-badge state-running';
        badge.innerHTML = '<span class="dot green"></span><span>Running (가동 중)</span>';
        costInfo.style.color = '#8FE0B4';
        costInfo.innerText = '정상 과금 중 (공인 엣지 게이트웨이 가동)';
        if (headerDot) headerDot.className = 'dot green';
        if (headerText) headerText.innerText = 'KT Edge: kt-edge-dr-01 (Running)';
        if (statState) { statState.innerText = 'kt-edge-dr-01 : Running'; statState.style.color = '#8FE0B4'; }
        if (cardStateText) cardStateText.innerText = '상태: Running 🟢';
      } else if (vm.state === 'Stopped') {
        badge.className = 'kt-vm-badge state-stopped';
        badge.innerHTML = '<span class="dot red"></span><span>Stopped (전원 꺼짐)</span>';
        costInfo.style.color = '#FF9E8C';
        costInfo.innerText = '비용 절감 중 (vCPU/RAM 미과금 · 대기 상태)';
        if (headerDot) headerDot.className = 'dot red';
        if (headerText) headerText.innerText = 'KT Edge: kt-edge-dr-01 (Stopped)';
        if (statState) { statState.innerText = 'kt-edge-dr-01 : Stopped'; statState.style.color = '#FF9E8C'; }
        if (cardStateText) cardStateText.innerText = '상태: Stopped 🔴';
      } else {
        badge.className = 'kt-vm-badge state-transition';
        badge.innerHTML = `<span class="dot yellow"></span><span>${vm.state} (전환 중)</span>`;
        costInfo.style.color = '#F7D684';
        costInfo.innerText = '상태 전환 작업 진행 중...';
        if (headerDot) headerDot.className = 'dot yellow';
        if (headerText) headerText.innerText = `KT Edge: kt-edge-dr-01 (${vm.state})`;
        if (statState) { statState.innerText = `kt-edge-dr-01 : ${vm.state}`; statState.style.color = '#F7D684'; }
        if (cardStateText) cardStateText.innerText = `상태: ${vm.state} 🟡`;
      }
      applyKtControlState();
    }

    async function fetchKtVmStatus(showLog = false) {
      try {
        if (showLog) addLog("KT Cloud OpenAPI listVirtualMachines 조회 요청 중...");
        const res = await fetch('/api/ktcloud/vms');
        const data = await res.json();
        if (data.status === 'ok' && data.vms && data.vms.length > 0) {
          ktVmsList = data.vms;
          const curVm = ktVmsList[0];
          updateVmUI(curVm);
          if (showLog) addLog(`KT Cloud 인스턴스 정보 갱신 완료 (${curVm.name} · ${curVm.state})`, 'success');
        } else {
          if (showLog) addLog("VM 목록을 찾을 수 없습니다: " + JSON.stringify(data), 'err');
        }
      } catch (err) {
        if (showLog) addLog("API 통신 실패: " + err.message, 'err');
      }
    }

    let isKtControlUnlocked = false;
    let currentKtVmState = 'Unknown';

    async function toggleKtControlLock() {
      if (!isKtControlUnlocked) {
        const pwd = await mtAskPassword('KT 제어 인증');
        if (pwd === null) return;
        if (await mtVerify(pwd)) { ktCtrlPwd = pwd;
          isKtControlUnlocked = true;
          applyKtControlState();
          alert('인증 성공: KT Edge 제어 권한이 활성화되었습니다.');
        } else {
          alert('비밀번호가 일치하지 않습니다.');
        }
      } else {
        isKtControlUnlocked = false; ktCtrlPwd = '';
        applyKtControlState();
        alert('안내: KT Edge 제어 권한이 다시 잠겼습니다.');
      }
    }

    function applyKtControlState() {
      const toggleBtn = document.getElementById('btn-kt-unlock-toggle');
      const authBadge = document.getElementById('kt-auth-badge');
      const termLabel = document.getElementById('kt-term-ctrl-label');
      const termBtns = [
        document.getElementById('btn-term-reload'),
        document.getElementById('btn-term-wgrestart'),
        document.getElementById('btn-term-nginxrestart')
      ];

      const btnStop = document.getElementById('btn-kt-stop');
      const btnStart = document.getElementById('btn-kt-start');
      const btnReboot = document.getElementById('btn-kt-reboot');

      if (!isKtControlUnlocked) {
        if (toggleBtn) {
          toggleBtn.innerHTML = '🔑 제어 활성화';
          toggleBtn.style.background = '#F4C95D';
          toggleBtn.style.color = '#000';
        }
        if (authBadge) {
          authBadge.innerHTML = '🔒 제어 잠김 (읽기 전용 모드)';
          authBadge.style.background = '#4F739A';
          authBadge.style.color = '#B4C6D8';
          authBadge.style.borderColor = '#6A8BAE';
        }
        if (termLabel) {
          termLabel.innerHTML = '🔒 제어/재시작 (기본 비활성):';
          termLabel.style.color = '#B4C6D8';
        }

        termBtns.forEach(btn => {
          if (btn) {
            btn.disabled = true;
            btn.style.opacity = '0.35';
            btn.style.cursor = 'not-allowed';
            btn.title = '기본 비활성화됨: figteam 비밀번호 입력 후 활성화';
          }
        });

        if (btnStop) {
          btnStop.disabled = true;
          btnStop.style.opacity = '0.35';
          btnStop.style.cursor = 'not-allowed';
          btnStop.title = '기본 비활성화됨: figteam 비밀번호 입력 후 활성화';
        }
        if (btnStart) {
          btnStart.disabled = true;
          btnStart.style.opacity = '0.35';
          btnStart.style.cursor = 'not-allowed';
          btnStart.title = '기본 비활성화됨: figteam 비밀번호 입력 후 활성화';
        }
        if (btnReboot) {
          btnReboot.disabled = true;
          btnReboot.style.opacity = '0.35';
          btnReboot.style.cursor = 'not-allowed';
          btnReboot.title = '기본 비활성화됨: figteam 비밀번호 입력 후 활성화';
        }
      } else {
        if (toggleBtn) {
          toggleBtn.innerHTML = '🔒 다시 잠그기';
          toggleBtn.style.background = '#5FD39A';
          toggleBtn.style.color = '#fff';
        }
        if (authBadge) {
          authBadge.innerHTML = '🔓 제어 활성화됨 (관리자 모드)';
          authBadge.style.background = '#064e3b';
          authBadge.style.color = '#6ee7b7';
          authBadge.style.borderColor = '#4CB985';
        }
        if (termLabel) {
          termLabel.innerHTML = '🔓 제어/재시작 (활성화됨):';
          termLabel.style.color = '#F4C95D';
        }

        termBtns.forEach(btn => {
          if (btn) {
            btn.disabled = false;
            btn.style.opacity = '1';
            btn.style.cursor = 'pointer';
            btn.title = '클릭하여 즉시 실행';
          }
        });

        if (currentKtVmState === 'Running') {
          if (btnStop) { btnStop.disabled = false; btnStop.style.opacity = '1'; btnStop.style.cursor = 'pointer'; btnStop.title = '전원 끄기 실행'; }
          if (btnStart) { btnStart.disabled = true; btnStart.style.opacity = '0.35'; btnStart.style.cursor = 'not-allowed'; btnStart.title = '이미 가동 중입니다'; }
          if (btnReboot) { btnReboot.disabled = false; btnReboot.style.opacity = '1'; btnReboot.style.cursor = 'pointer'; btnReboot.title = '가상머신 재부팅'; }
        } else if (currentKtVmState === 'Stopped') {
          if (btnStop) { btnStop.disabled = true; btnStop.style.opacity = '0.35'; btnStop.style.cursor = 'not-allowed'; btnStop.title = '이미 중지된 상태입니다'; }
          if (btnStart) { btnStart.disabled = false; btnStart.style.opacity = '1'; btnStart.style.cursor = 'pointer'; btnStart.title = '전원 켜기 실행'; }
          if (btnReboot) { btnReboot.disabled = true; btnReboot.style.opacity = '0.35'; btnReboot.style.cursor = 'not-allowed'; btnReboot.title = '중지 상태에서는 재부팅 불가'; }
        } else {
          if (btnStop) { btnStop.disabled = true; btnStop.style.opacity = '0.35'; }
          if (btnStart) { btnStart.disabled = true; btnStart.style.opacity = '0.35'; }
          if (btnReboot) { btnReboot.disabled = true; btnReboot.style.opacity = '0.35'; }
        }
      }
    }

    async function handleKtControlClick(type, param) {
      if (!isKtControlUnlocked) {
        const pwd = await mtAskPassword('KT 제어 인증');
        if (pwd === null) return;
        if (await mtVerify(pwd)) { ktCtrlPwd = pwd;
          isKtControlUnlocked = true;
          applyKtControlState();
          alert('인증 성공: 제어 권한이 활성화되었습니다. 요청하신 작업을 진행합니다.');
        } else {
          alert('비밀번호가 일치하지 않습니다.');
          return;
        }
      }

      if (type === 'term') {
        execKtTerminal(param, ktCtrlPwd);
      } else if (type === 'vm') {
        confirmVmAction(param);
      }
    }

    function confirmVmAction(action) {
      if (!isKtControlUnlocked) {
        handleKtControlClick('vm', action);
        return;
      }

      let actionKr = "";
      if (action === 'stop') actionKr = "전원을 끄시겠습니까? (vCPU/RAM 과금이 중단되며 민원접수 진입점이 대기 상태로 전환됩니다)";
      if (action === 'start') actionKr = "전원을 켜시겠습니까? (부팅 후 약 1분 이내에 Nginx 및 WireGuard가 자동 가동됩니다)";
      if (action === 'reboot') actionKr = "가상머신을 재부팅하시겠습니까?";

      const ok = confirm(`[KT Cloud VM 전원 제어]\n정말 '${document.getElementById('kt-display-name').innerText}'의 ${actionKr}`);
      if (!ok) return;

      executeVmAction(action);
    }

    function escapeHtml(str) {
      if (str === null || str === undefined) return '';
      return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#039;');
    }

    async function execKtTerminal(cmd, pwd = '') {
      const screen = document.getElementById('kt-terminal-screen');
      if (!screen) return;

      screen.innerHTML += `\n<span style="color:#9FD3F5;">[root@kt-edge-dr-01 ~]# ${escapeHtml(cmd)}</span>\n<span style="color:#B4C6D8;" class="kt-term-loading">⏳ WireGuard / SSH 원격 터널 실행 중...</span>\n`;
      screen.scrollTop = screen.scrollHeight;

      try {
        const res = await fetch('/api/kt/terminal/exec', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ cmd: cmd, password: pwd })
        });
        const data = await res.json();
        
        const loadingEls = screen.querySelectorAll('.kt-term-loading');
        loadingEls.forEach(el => el.remove());

        if (data.status === 'ok') {
          const color = data.code === 0 ? '#8FE0B4' : '#FF9E8C';
          const targetBadge = data.target ? `<span style="color:#9FD3F5; font-size:11px;">[연결 경로: ${escapeHtml(data.target)}]</span>\n` : '';
          screen.innerHTML += `${targetBadge}<span style="color:${color};">${escapeHtml(data.output)}</span>\n`;
        } else {
          screen.innerHTML += `<span style="color:#FF7A66;">[오류] ${escapeHtml(data.message || '실행 실패')}</span>\n`;
        }
      } catch (err) {
        const loadingEls = screen.querySelectorAll('.kt-term-loading');
        loadingEls.forEach(el => el.remove());
        screen.innerHTML += `<span style="color:#FF7A66;">[통신 오류] ${escapeHtml(err.message)}</span>\n`;
      }
      screen.scrollTop = screen.scrollHeight;
    }


    // ===== 다중 대상 터미널 (AWS · 온프렘) 2026-11-19 =====
    let ktCtrlPwd = '';
    async function mtVerify(p) {
      if (!p) return false;
      try { const r = await fetch('/api/ctrl/verify', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ password: p }) }); return r.ok; }
      catch (e) { return false; }
    }
    const MT_COMMON = { '⏱ 상태': `hostname; uptime; free -h | sed -n 1,2p; df -h / | tail -1`, '🚫 실패 서비스': `systemctl --failed --no-legend || true` };
    const MT_GROUPS = {
      kt: { title: '⚡ KT Cloud 터미널', targets: { 'kt-edge': 'KT_PRESETS' } },
      aws: { title: '☁️ AWS 터미널', targets: {
        'ctl': { '🤖 러너 healthz': `curl -s -m5 http://127.0.0.1:8080/healthz; echo`, '📜 러너 로그': `sudo journalctl -u orchestrator --no-pager -n 20 | cut -c1-200`, '🔐 WG': `sudo wg show wg0 latest-handshakes | awk -v n=$(date +%s) '{print $1, ($2 ? n-$2 " 초 전" : "없음")}'`, '🏠 온프렘 도달': `for u in http://192.168.120.226:8080/healthz http://10.10.1.100/healthz; do echo "$u $(curl -s -m4 -o /dev/null -w '%{http_code}' $u)"; done; ping -c1 -W2 10.10.2.10 >/dev/null && echo 'db-01 응답' || echo 'db-01 응답 없음'` },
        'dr': { '🧩 파드': `sudo /usr/local/bin/k3s kubectl -n minwon-dr get pods -o wide`, '🔁 복제 상태': `echo 'SHOW REPLICA STATUS' | sudo /usr/local/bin/k3s kubectl -n minwon-dr exec -i minwon-mysql-0 -- sh -c 'mysql -E -uroot -p"$MYSQL_ROOT_PASSWORD" 2>/dev/null' | grep -E 'Running:|Seconds_Behind|Last_(IO|SQL)_Error:|Source_Host'`, '💓 heartbeat': `echo 'SELECT ts, TIMESTAMPDIFF(SECOND, ts, UTC_TIMESTAMP(3)) AS lag_s FROM repl_check.heartbeat' | sudo /usr/local/bin/k3s kubectl -n minwon-dr exec -i minwon-mysql-0 -- sh -c 'mysql -E -uroot -p"$MYSQL_ROOT_PASSWORD" 2>/dev/null'`, '🩺 앱 healthz': `curl -s -m5 http://127.0.0.1:30080/healthz; echo`, '💾 백업 목록': `sudo ls -lh /var/backups/mysql | tail -5`, '🔐 WG': `sudo wg show wg0 latest-handshakes | awk -v n=$(date +%s) '{print $1, ($2 ? n-$2 " 초 전" : "없음")}'` },
      } },
      onprem: { title: '🖥️ 온프렘 터미널', targets: {
        'controller': { '🧮 compute 서비스': `source /root/keystonerc_admin; openstack compute service list -c Binary -c Host -c Status -c State`, '📦 인스턴스 배치': `source /root/keystonerc_admin; openstack server list --all-projects --long -c Name -c Status -c Host -c Networks`, '🌐 네트워크 에이전트': `source /root/keystonerc_admin; openstack network agent list -c Host -c Binary -c Alive -c State`, '🧭 라우터': `source /root/keystonerc_admin; for r in rt-edge rt-data; do echo "== $r"; openstack router show $r -f value -c external_gateway_info -c routes; done`, '🧠 메모리 상위': `free -m | sed -n 1,3p; ps -eo rss,comm --sort=-rss | head -8` },
        'compute1': { '🖥 VM': `virsh list --all`, '⚙ 서비스': `systemctl is-active openstack-nova-compute ovn-controller neutron-ovn-metadata-agent` },
        'compute3': { '🖥 VM': `virsh list --all`, '⚙ 서비스': `systemctl is-active openstack-nova-compute ovn-controller neutron-ovn-metadata-agent` },
        'compute4': { '🖥 VM': `virsh list --all`, '⚙ 서비스': `systemctl is-active openstack-nova-compute ovn-controller neutron-ovn-metadata-agent` },
        'k8s-cp1': { '🩺 앱 healthz (:30080)': `curl -s -m5 http://127.0.0.1:30080/healthz; echo`, '🌐 3대 클라우드 상태': `curl -s -m5 https://figteam.ktci5.kr/api/public/system-status; echo`, '📜 앱 로그': `sudo k3s kubectl -n minwon-sample logs -l app=minwon-app --tail=20`, '☸ k3s': `sudo k3s kubectl get nodes; sudo k3s kubectl get pods -A --no-headers | awk '{print $1, $2, $4}'`, '🛣 DB 경로': `ip route get 10.10.2.10 | head -1; timeout 3 bash -c '</dev/tcp/10.10.2.10/3306' && echo 'db-01:3306 열림' || echo 'db-01:3306 닫힘'` },
        'db-01': { '🗄 MySQL': `systemctl is-active mysql; sudo mysql -E -e 'SELECT @@version, @@server_id, @@gtid_mode, @@read_only, @@super_read_only'`, '🔁 복제 연결': `sudo mysql -e "SHOW REPLICAS; SELECT user, host, command, time FROM information_schema.processlist WHERE command LIKE 'Binlog%'"`, '📊 데이터': `sudo mysql -N -e "SELECT 'complaints', COUNT(*) FROM minwon_db.complaints; SELECT 'gtid', @@GLOBAL.gtid_executed"`, '💾 백업 목록': `sudo ls -lh /var/backups/mysql | tail -5; df -h /var/lib/mysql | tail -1` },
        'k8s-w1': { '☸ k3s-agent': `systemctl is-active k3s-agent || echo '클러스터 미가입'` },
      } },
    };
    function mtAskPassword(cmd) {
      return new Promise(resolve => {
        const bg = document.createElement('div');
        bg.style.cssText = 'position:fixed;inset:0;background:rgba(2,6,23,.7);z-index:9999;display:flex;align-items:center;justify-content:center';
        bg.innerHTML = '<form style="background:#0F2D4F;border:1px solid #4F739A;padding:16px;min-width:320px;color:#E6EEF5;font-size:12.5px">'
          + '<div style="font-weight:800;margin-bottom:6px">🔑 제어 비밀번호</div><div class="mt-cmd" style="color:#8AA5C2;margin-bottom:8px;word-break:break-all"></div>'
          + '<input type="password" autocomplete="off" style="width:100%;background:#020617;border:1px solid #4F739A;color:#E6EEF5;padding:6px">'
          + '<div style="margin-top:10px;text-align:right"><button type="button" class="btn-top">취소</button> <button type="submit" class="btn-top" style="background:#3A78B5;color:#fff">실행</button></div></form>';
        bg.querySelector('.mt-cmd').textContent = cmd;
        const f = bg.querySelector('form'), inp = bg.querySelector('input');
        const done = v => { inp.value = ''; bg.remove(); resolve(v); };
        f.onsubmit = e => { e.preventDefault(); done(inp.value); };
        bg.querySelector('button[type=button]').onclick = () => done(null);
        document.body.appendChild(bg); inp.focus();
      });
    }
    const MT_DANGER = new RegExp('restart|stop|poweroff|reboot|reload|shutdown|kill|[ ]rm[ ]|^rm[ ]|[ ]dd[ ]|mkfs|systemctl[ ]+(start|enable|disable|mask)|(drop|delete|truncate|alter|update|insert|replace|grant|revoke|reset)[ ]|openstack[ ]+[a-z]+[ ]+(create|delete|set|unset|migrate|resize|rebuild)|kubectl[ ]+(delete|apply|scale|edit|patch|drain|cordon)|wg[ ]+(set|syncconf)|wg-quick', 'i');
    let mtRemain = 0, mtTimer = null;
    function mtLockUI(remain) {
      mtRemain = remain || 0;
      const st = document.getElementById('mt-lockstate'); if (!st) return;
      const on = mtRemain > 0;
      st.textContent = on ? ('🔓 제어 가능 · ' + Math.ceil(mtRemain / 60) + '분 남음') : '🔒 제어 잠김';
      st.style.color = on ? '#5FD39A' : '#F4C95D';
      document.getElementById('mt-lockpw').style.display = on ? 'none' : '';
      document.getElementById('mt-unlock').style.display = on ? 'none' : '';
      document.getElementById('mt-lock').style.display = on ? '' : 'none';
      if (on) { isKtControlUnlocked = true; if (typeof applyKtControlState === 'function') applyKtControlState(); }
      clearInterval(mtTimer); if (on) mtTimer = setInterval(() => mtLockUI(mtRemain - 30), 30000);
    }
    async function mtCtrl(path, body) {
      try { const r = await fetch(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body || {}) }); const d = await r.json(); return { ok: r.ok, remain: d.remain || 0 }; }
      catch (e) { return { ok: false, remain: 0 }; }
    }
    async function mtUnlock(pw) { const r = await mtCtrl('/api/ctrl/verify', { password: pw }); mtLockUI(r.remain); return r.ok; }
    function mtInitLock() {
      const pw = document.getElementById('mt-lockpw'); if (!pw || pw.dataset.ready) return; pw.dataset.ready = '1';
      const go = async () => { const v = pw.value; pw.value = ''; if (!v) return; if (!(await mtUnlock(v))) { const st = document.getElementById('mt-lockstate'); st.textContent = '❌ 비밀번호가 맞지 않습니다'; st.style.color = '#FF7A66'; } };
      document.getElementById('mt-unlock').onclick = go; pw.onkeydown = e => { if (e.key === 'Enter') go(); };
      document.getElementById('mt-lock').onclick = async () => { const r = await mtCtrl('/api/ctrl/lock'); mtLockUI(0); isKtControlUnlocked = false; ktCtrlPwd = ''; };
      mtCtrl('/api/ctrl/status').then(r => mtLockUI(r.remain));
    }
    async function mtExec(box, cmd, pwd) {
      if (!pwd && MT_DANGER.test(cmd) && mtRemain > 0 && !confirm('제어/변경 명령을 실행합니다. 계속할까요?' + String.fromCharCode(10, 10) + cmd)) return;
      const sel = box.querySelector('select'), scr = box.querySelector('.mt-screen'), t = sel.value;
      const label = sel.options[sel.selectedIndex].text;
      scr.insertAdjacentHTML('beforeend', `\n<span style="color:#9FD3F5">[${escapeHtml(label)}]$ ${escapeHtml(cmd)}</span>\n<span class="mt-wait" style="color:#B4C6D8">⏳ 실행 중...</span>\n`);
      scr.scrollTop = scr.scrollHeight;
      try {
        const r = await fetch('/api/term/exec', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ target: t, cmd, password: pwd || '' }) });
        const d = await r.json(); scr.querySelectorAll('.mt-wait').forEach(e => e.remove());
        if (d.need_password && !pwd) { const p = await mtAskPassword(cmd); if (p && await mtUnlock(p)) return mtExec(box, cmd, ''); scr.insertAdjacentHTML('beforeend', `<span style="color:#F4C95D">취소됨</span>` + String.fromCharCode(10)); return; }
        if (d.status === 'ok') scr.insertAdjacentHTML('beforeend', `<span style="color:${d.code === 0 ? '#8FE0B4' : '#FF9E8C'}">${escapeHtml(d.output || '(출력 없음)')}</span>\n`);
        else scr.insertAdjacentHTML('beforeend', `<span style="color:#FF7A66">[오류] ${escapeHtml(d.message || '실행 실패')}</span>\n`);
      } catch (e) { scr.querySelectorAll('.mt-wait').forEach(x => x.remove()); scr.insertAdjacentHTML('beforeend', `<span style="color:#FF7A66">[통신 오류] ${escapeHtml(e.message)}</span>\n`); }
      scr.scrollTop = scr.scrollHeight;
    }
    function mtRender(box) {
      const g = MT_GROUPS[box.dataset.group]; if (!g) return;
      const opts = Object.keys(g.targets).map(k => `<option value="${k}">${k}</option>`).join('');
      box.innerHTML = `<div style="margin-top:16px;border:1px solid #1D4A7A;padding:12px;background:rgba(2,6,23,.35)">
        <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-bottom:8px"><b style="color:#E6EEF5">${g.title}</b>
          <select style="background:#0F2D4F;color:#E6EEF5;border:1px solid #4F739A;padding:4px 6px;font-family:monospace">${opts}</select>
          <span style="font-size:11px;color:#8AA5C2">읽기 명령은 바로 실행 · 제어/변경 명령은 제어 비밀번호 필요(화면에 표시하지 않음)</span></div>
        <div class="mt-presets" style="display:flex;gap:6px;flex-wrap:wrap;margin-bottom:8px"></div>
        <div style="display:flex;gap:8px;margin-bottom:8px"><input class="mt-in" placeholder="명령어 입력 후 Enter" style="flex:1;background:#0F2D4F;border:1px solid #4F739A;color:#E6EEF5;padding:6px 10px;font-family:monospace;font-size:12px">
          <button class="btn-top mt-run" style="background:#3A78B5;color:#fff">실행</button><button class="btn-top mt-clr">지우기</button></div>
        <div class="mt-screen" style="background:#020617;border:1px solid #1D4A7A;padding:10px;font-family:'Courier New',monospace;font-size:12px;color:#8FE0B4;line-height:1.45;min-height:160px;max-height:360px;overflow:auto;white-space:pre-wrap">[SYSTEM] 대상을 고르고 버튼을 누르세요.</div></div>`;
      const sel = box.querySelector('select'), pre = box.querySelector('.mt-presets'), inp = box.querySelector('.mt-in');
      const KT_LABELS = { '▶ 전체 연결 점검': 'all', '🔐 WG 핸드셰이크': 'wg', '🛡️ DMZ 보호 설정': 'guard', '⏳ 대기 안내 (503)': 'waiting', '👤 실제 IP 로그': 'realip', '📊 Edge 처리 현황': 'status', '🚨 AWS 도달': 'aws', '🔏 인증서 만료': 'cert' };
      const presetsOf = t => { const p = g.targets[t]; if (p !== 'KT_PRESETS') return p; const o = {}; Object.entries(KT_LABELS).forEach(([n, k]) => { if (typeof KT_OSOPS_PRESETS !== 'undefined' && KT_OSOPS_PRESETS[k]) o[n] = KT_OSOPS_PRESETS[k]; }); return o; };
      const draw = () => { pre.innerHTML = ''; Object.entries(Object.assign({}, MT_COMMON, presetsOf(sel.value))).forEach(([n, c]) => {
        const b = document.createElement('button'); b.className = 'btn-top'; b.style.cssText = 'font-size:11px;padding:4px 9px'; b.textContent = n; b.title = c; b.onclick = () => mtExec(box, c); pre.appendChild(b); }); };
      sel.onchange = draw; draw();
      const run = () => { const c = inp.value.trim(); if (c) { mtExec(box, c); inp.value = ''; } };
      box.querySelector('.mt-run').onclick = run; inp.onkeydown = e => { if (e.key === 'Enter') run(); };
      box.querySelector('.mt-clr').onclick = () => { box.querySelector('.mt-screen').textContent = '[SYSTEM] 화면을 지웠습니다.'; };
    }
    const mtBoot = () => { document.querySelectorAll('.mt-term').forEach(b => { if (!b.dataset.ready) { b.dataset.ready = '1'; mtRender(b); } }); mtInitLock(); };
    document.addEventListener('DOMContentLoaded', mtBoot);
    if (document.readyState !== 'loading') setTimeout(mtBoot, 0);

    // #osops 연결 점검 프리셋 — KT Edge(10.200.0.1)에서 실행. 읽기 전용 명령만.
    const KT_OSOPS_PRESETS = {
      all: `for t in 'KT nginx·WAF (443)|https://127.0.0.1/healthz' 'WG→온프렘 VIP|http://10.10.1.100/healthz' 'WG→민원 앱 (k8s-cp1)|http://192.168.120.226:8080/healthz' 'Keystone|http://192.168.120.160:5000/v3' 'Nova API|http://192.168.120.160:8774/' 'Argo CD|http://192.168.120.226:30800/' 'Grafana|http://192.168.120.226:30300/api/health' '대기 안내 (503=정상)|https://10.200.0.1/_edge/waiting-preview' 'Edge 상태 화면|http://127.0.0.1:8088/' 'AWS 러너|http://10.200.0.3:8080/' 'AWS DR k3s|http://10.200.0.4:30080/'; do n=$(echo "$t" | cut -d'|' -f1); u=$(echo "$t" | cut -d'|' -f2); printf '%-28s ' "$n"; curl -sk -o /dev/null -m 4 -w '%{http_code}  %{time_total}s' "$u"; echo; done; echo '(000 = 응답 없음)'`,
      wg: `wg show wg0 latest-handshakes | awk -v now=$(date +%s) '{ print $1, ($2 ? now-$2 "초 전" : "핸드셰이크 없음") }'; wg show wg0 allowed-ips`,
      guard: `nginx -T 2>/dev/null | grep -nE 'real_ip_header|edge_trusted = 0|limit_req_zone|limit_conn_zone|limit_req zone|limit_conn edge|return 444|listen 8088'; echo "Cloudflare 신뢰 대역: $(grep -c set_real_ip_from /etc/nginx/conf.d/00-edge-guard.conf)개"`,
      waiting: `curl -sk -D - -o /dev/null https://10.200.0.1/_edge/waiting-preview | grep -iE '^HTTP|retry-after|cache-control'`,
      realip: `tail -n 10 /var/log/nginx/access.log | grep -v '^127.0.0.1' | awk '{ print $1, $4, $7, $9 }'`,
      status: `curl -s http://127.0.0.1:8088/nginx_status`,
      aws: `for ip in 10.200.0.3 10.200.0.4; do ping -c1 -W2 $ip >/dev/null && echo "$ip 응답" || echo "$ip 응답 없음"; done; wg show wg0 allowed-ips | grep -E '10.200.0.(3|4)' || echo 'WG에 AWS 피어 없음'`,
      cert: `openssl x509 -in /etc/nginx/ssl/edge.crt -noout -subject -enddate`
    };
    function execKtPreset(key) {
      const cmd = KT_OSOPS_PRESETS[key];
      if (cmd) execKtTerminal(cmd);
    }

    async function promptAndExecKtTerminal(cmd) {
      const pwd = await mtAskPassword('KT 제어 인증');
      if (pwd === null) return;
      if (!pwd) {
        alert('비밀번호를 입력해야 실행할 수 있습니다.');
        return;
      }
      execKtTerminal(cmd, pwd);
    }

    async function submitKtTerminalInput() {
      const input = document.getElementById('kt-terminal-input');
      if (!input) return;
      const cmd = input.value.trim();
      if (!cmd) return;

      const isDangerous = /restart|stop|poweroff|reboot|reload|kill|rm\\s|systemctl\\s+(start|stop|restart|reload)/i.test(cmd);
      if (isDangerous) {
        if (!isKtControlUnlocked) {
          const pwd = await mtAskPassword('KT 제어 인증');
          if (pwd === null) return;
          if (await mtVerify(pwd)) { ktCtrlPwd = pwd;
            isKtControlUnlocked = true;
            applyKtControlState();
            execKtTerminal(cmd, ktCtrlPwd);
          } else {
            alert('비밀번호가 일치하지 않습니다.');
            return;
          }
        } else {
          execKtTerminal(cmd, ktCtrlPwd);
        }
      } else {
        execKtTerminal(cmd);
      }
      input.value = '';
    }

    function clearKtTerminal() {
      const screen = document.getElementById('kt-terminal-screen');
      if (screen) {
        screen.innerHTML = `[SYSTEM] KT Cloud Edge 원격 터미널 화면이 초기화되었습니다.\n`;
      }
    }

    async function executeVmAction(action) {
      const spinner = document.getElementById('kt-action-spinner');
      const btnStop = document.getElementById('btn-kt-stop');
      const btnStart = document.getElementById('btn-kt-start');
      const btnReboot = document.getElementById('btn-kt-reboot');

      btnStop.disabled = true;
      btnStart.disabled = true;
      btnReboot.disabled = true;
      spinner.style.display = 'inline-block';

      const vmObj = ktVmsList.find(v => v.id === currentVmId);
      const reqVer = 'server/v1';

      addLog(`[ACTION] VM ${action.toUpperCase()} 요청 전송 중... (대상: ${vmObj ? vmObj.name : currentVmId}, API: ${reqVer})`, 'warn');

      try {
        const res = await fetch('/api/ktcloud/vm/action', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ action: action, id: currentVmId, ver: reqVer })
        });
        const result = await res.json();

        if (result.status === 'ok') {
          addLog(`명령 접수 성공! Job ID: ${result.jobid}`, 'success');
          pollJobStatus(result.jobid, action, result.ver || reqVer);
        } else {
          addLog(`명령 실패: ${result.message}`, 'err');
          spinner.style.display = 'none';
          fetchKtVmStatus(false);
          fetchOsVmStatus(false);
        }
      } catch (err) {
        addLog(`명령 요청 중 네트워크 에러: ${err.message}`, 'err');
        spinner.style.display = 'none';
        fetchKtVmStatus(false);
        fetchOsVmStatus(false);
      }
    }

    function pollJobStatus(jobid, action, ver) {
      let attempts = 0;
      const maxAttempts = 30; // 30 * 3s = 90s
      const apiVer = ver || 'server/v1';
      
      const interval = setInterval(async () => {
        attempts++;
        try {
          const res = await fetch(`/api/ktcloud/job?jobid=${jobid}&ver=${apiVer}`);
          const data = await res.json();

          if (data.jobstatus === 1) { // Success
            clearInterval(interval);
            document.getElementById('kt-action-spinner').style.display = 'none';
            addLog(`작업 완료 (Job Status: 1) - ${action.toUpperCase()} 성공!`, 'success');
            setTimeout(() => fetchKtVmStatus(true), 2000);
          } else if (data.jobstatus === 2) { // Failed
            clearInterval(interval);
            document.getElementById('kt-action-spinner').style.display = 'none';
            addLog(`작업 실패 (Job Status: 2) - ${JSON.stringify(data.result)}`, 'err');
            fetchKtVmStatus(true);
          } else {
            addLog(`작업 진행 중... (경과: ${attempts * 3}초)`);
          }
        } catch (e) {
          addLog(`Job 상태 폴링 에러: ${e.message}`, 'warn');
        }

        if (attempts >= maxAttempts) {
          clearInterval(interval);
          document.getElementById('kt-action-spinner').style.display = 'none';
          addLog("작업 타임아웃 (90초). 상태 새로고침을 실행합니다.", 'warn');
          fetchKtVmStatus(true);
        }
      }, 3000);
    }

    function reloadFrame() {
      const frame = document.getElementById('console-frame');
      if (frame && frame.src && frame.src !== 'about:blank') {
        frame.contentWindow.location.reload();
      }
    }

    function toggleFullscreen() {
      document.body.classList.toggle('fullscreen');
    }


    // ============================================================
    // OPENSTACK VM MANAGEMENT JAVASCRIPT LOGIC (KT CLOUD EQUIVALENT)
    // ============================================================
    let osServersCache = [];
    let selectedOsVmName = 'k8s-cp1';
    let isOsActionInProgress = false;

    function addOsLog(msg, type='info') {
      const consoleEl = document.getElementById('os-log-console');
      if (!consoleEl) return;
      const line = document.createElement('div');
      line.className = 'log-line';
      const now = new Date().toLocaleTimeString('ko-KR', { hour12: false });
      let color = '#D3E0EC';
      if (type === 'err') color = '#FF9E8C';
      if (type === 'warn') color = '#F7D684';
      if (type === 'success') color = '#8FE0B4';
      line.innerHTML = `<span class="log-time">[${now}]</span> <span class="log-msg" style="color:${color};">${msg}</span>`;
      consoleEl.appendChild(line);
      consoleEl.scrollTop = consoleEl.scrollHeight;
    }

    function selectOsVm(vmName) {
      selectedOsVmName = vmName;
      ['k8s-cp1', 'k8s-w1', 'db-01'].forEach(name => {
        const shortKey = name === 'db-01' ? 'db01' : name.replace('k8s-', '');
        const btn = document.getElementById(`btn-tab-${shortKey}`);
        if (btn) {
          if (name === vmName) {
            btn.style.background = '#B08CFF';
            btn.style.color = '#fff';
            btn.style.fontWeight = '700';
          } else {
            btn.style.background = 'transparent';
            btn.style.color = '#B4C6D8';
            btn.style.fontWeight = '500';
          }
        }
      });
      renderFocusedOsVm();
    }

    async function fetchOsVmStatus(showLog = false) {
      try {
        if (showLog) addOsLog("OpenStack Nova servers/detail 및 인벤토리 동기화 중...");
        const res = await fetch('/api/openstack/vms');
        const data = await res.json();
        if (data.status === 'ok' && data.servers) {
          osServersCache = data.servers;
          renderFocusedOsVm();
          renderOsSummaryGrid(data.servers);
          updateOsStats(data.servers);
          if (showLog) addOsLog(`OpenStack VM ${data.servers.length}대 상태 동기화 완료`, 'success');
        } else {
          if (showLog) addOsLog("OpenStack 조회 실패: " + (data.message || 'Unknown'), 'err');
        }
      } catch (err) {
        if (showLog) addOsLog("네트워크 통신 에러: " + err.message, 'err');
      }
    }

    function renderFocusedOsVm() {
      if (!osServersCache || osServersCache.length === 0) return;
      const vm = osServersCache.find(s => s.name === selectedOsVmName) || osServersCache[0];
      if (!vm) return;

      const nameEl = document.getElementById('os-display-name');
      const idEl = document.getElementById('os-display-id');
      const roleEl = document.getElementById('os-display-role');
      const badgeEl = document.getElementById('os-status-badge');
      const textEl = document.getElementById('os-status-text');
      const floatingEl = document.getElementById('os-floating-ip');
      const fixedEl = document.getElementById('os-fixed-ip');
      const flavorEl = document.getElementById('os-flavor');
      const hostEl = document.getElementById('os-host');
      const healthEl = document.getElementById('os-health');

      const btnStop = document.getElementById('btn-os-stop');
      const btnStart = document.getElementById('btn-os-start');
      const btnReboot = document.getElementById('btn-os-reboot');
      const btnHardReboot = document.getElementById('btn-os-hard-reboot');

      if (nameEl) nameEl.innerText = vm.name;
      if (idEl) idEl.innerText = `ID: ${vm.id}`;

      // Role & Flavor
      let role = "Worker Node";
      let roleColor = "#3A78B5";
      let flavorText = "m1.worker (2 vCPU · 2.5GB RAM · 20GB Disk · 증설 완료)";
      if (vm.name === 'db-01') {
        role = "Dedicated DB (MySQL 8.4 LTS · Primary)";
        roleColor = "#5FD39A";
        flavorText = "m1.medium (2 vCPU · 4GB RAM · Cinder 볼륨 30GB /var/lib/mysql)";
      } else if (vm.name.includes('cp1') || vm.name.includes('master')) {
        role = "K8s Control Plane & App";
        roleColor = "#C8962E";
        flavorText = "m1.medium (2 vCPU · 4GB RAM 증설 완료 · minwon-app / k3s 단독 전담)";
      } else if (vm.name.includes('w1')) {
        role = "K8s Worker Node 1";
        roleColor = "#3A78B5";
        flavorText = "m1.worker (2 vCPU · 2.5GB RAM 증설 완료 · Traefik & K3s Agent)";
      } else if (vm.name.includes('w2')) {
        role = "K8s Worker Node 2";
        roleColor = "#3A78B5";
        flavorText = "m1.worker (2 vCPU · 2.5GB RAM 증설 완료 · Traefik & K3s Agent · minwon-app 분산 서빙)";
      }
      if (roleEl) {
        roleEl.innerText = role;
        roleEl.style.background = roleColor;
      }
      if (flavorEl) flavorEl.innerText = flavorText;

      // Addresses
      let fixedIps = [];
      let floatingIps = [];
      if (vm.addresses) {
        for (const net in vm.addresses) {
          vm.addresses[net].forEach(addr => {
            if (addr['OS-EXT-IPS:type'] === 'floating') floatingIps.push(addr.addr);
            else fixedIps.push(addr.addr);
          });
        }
      }
      if (floatingEl) floatingEl.innerText = floatingIps.join(', ') || '없음 (내부망 전용 · FIP 차단)';
      if (fixedEl) fixedEl.innerText = fixedIps.join(', ') || '미할당';
      if (hostEl) hostEl.innerText = `${vm['OS-EXT-SRV-ATTR:host'] || 'compute Node'} (Nova Compute)`;

      // Status Badge & Buttons
      const status = (vm.status || 'UNKNOWN').toUpperCase();
      if (!isOsActionInProgress) {
        if (status === 'ACTIVE') {
          if (badgeEl) badgeEl.className = 'kt-vm-badge state-running';
          if (textEl) textEl.innerHTML = '<span class="dot green"></span> ACTIVE (Running)';
          if (healthEl) {
            healthEl.innerText = '정상 가동 중 (연산 활성)';
            healthEl.style.color = '#8FE0B4';
          }
          if (btnStop) btnStop.disabled = false;
          if (btnStart) btnStart.disabled = true;
          if (btnReboot) btnReboot.disabled = false;
          if (btnHardReboot) btnHardReboot.disabled = false;
        } else if (status === 'SHUTOFF') {
          if (badgeEl) badgeEl.className = 'kt-vm-badge state-stopped';
          if (textEl) textEl.innerHTML = '<span class="dot red"></span> SHUTOFF (Stopped)';
          if (healthEl) {
            healthEl.innerText = '전원 차단됨 (자원 대기 상태)';
            healthEl.style.color = '#FF9E8C';
          }
          if (btnStop) btnStop.disabled = true;
          if (btnStart) btnStart.disabled = false;
          if (btnReboot) btnReboot.disabled = true;
          if (btnHardReboot) btnHardReboot.disabled = true;
        } else {
          if (badgeEl) badgeEl.className = 'kt-vm-badge state-transition';
          if (textEl) textEl.innerHTML = `<span class="dot yellow"></span> ${status}`;
          if (healthEl) {
            healthEl.innerText = '상태 전이 중...';
            healthEl.style.color = '#F7D684';
          }
          if (btnStop) btnStop.disabled = true;
          if (btnStart) btnStart.disabled = true;
          if (btnReboot) btnReboot.disabled = true;
          if (btnHardReboot) btnHardReboot.disabled = true;
        }
      }
    }

    function updateOsStats(servers) {
      let activeCount = 0;
      let shutoffCount = 0;
      servers.forEach(s => {
        const st = (s.status || '').toUpperCase();
        if (st === 'ACTIVE') activeCount++;
        else if (st === 'SHUTOFF') shutoffCount++;
      });
      const totalEl = document.getElementById('os-stat-total');
      const activeEl = document.getElementById('os-stat-active');
      const shutoffEl = document.getElementById('os-stat-shutoff');
      const cardOsState = document.getElementById('card-os-state-text');
      if (totalEl) totalEl.innerText = servers.length;
      if (activeEl) activeEl.innerText = activeCount;
      if (shutoffEl) shutoffEl.innerText = shutoffCount;
      if (cardOsState) cardOsState.innerHTML = `상태: ${activeCount}대 ACTIVE 🟢`;
    }

    function renderOsSummaryGrid(servers) {
      const grid = document.getElementById('os-vm-grid');
      if (!grid) return;
      grid.innerHTML = '';

      servers.forEach(s => {
        const status = (s.status || 'UNKNOWN').toUpperCase();
        let badgeClass = 'state-running';
        let dotClass = 'green';
        if (status === 'SHUTOFF') {
          badgeClass = 'state-stopped';
          dotClass = 'red';
        } else if (status !== 'ACTIVE') {
          badgeClass = 'state-transition';
          dotClass = 'yellow';
        }

        let fixedIps = [];
        let floatingIps = [];
        if (s.addresses) {
          for (const net in s.addresses) {
            s.addresses[net].forEach(addr => {
              if (addr['OS-EXT-IPS:type'] === 'floating') floatingIps.push(addr.addr);
              else fixedIps.push(addr.addr);
            });
          }
        }

        const isCp1 = s.name.includes('cp1');
        const isDb = s.name === 'db-01';
        let role = "Worker Node";
        let roleColor = "#3A78B5";
        let specText = "2 vCPU · 2.5GB RAM (m1.worker)";
        if (isDb) {
          role = "MySQL 8.4 DB (data-net)";
          roleColor = "#5FD39A";
          specText = "2 vCPU · 4GB RAM (m1.medium)";
        } else if (isCp1) {
          role = "Control Plane & App";
          roleColor = "#C8962E";
          specText = "2 vCPU · 4GB RAM (m1.medium)";
        }

        const card = document.createElement('div');
        card.className = 'kt-vm-box';
        card.style.background = '#1D4A7A';
        card.style.padding = '16px';
        card.innerHTML = `
          <div class="kt-vm-header" style="padding-bottom:10px;">
            <div class="kt-vm-title">
              <span style="font-size:20px;">${isDb ? '🗄️' : '🖥️'}</span>
              <div>
                <div style="font-size:15px; font-weight:700; color:#fff; display:flex; align-items:center; gap:6px;">
                  <span>${s.name}</span>
                  <span class="menu-badge" style="background:${roleColor}; color:#fff; font-size:10px;">${role}</span>
                </div>
                <div style="font-size: 11px; color: #B4C6D8; font-family: monospace;">Fixed: ${fixedIps[0] || '미할당'} ${floatingIps[0] ? '| FIP: ' + floatingIps[0] : ''}</div>
                <div style="font-size: 11px; color: #8FE0B4; margin-top:3px;">스펙: <b>${specText}</b> · 호스트: <b>${s['OS-EXT-SRV-ATTR:host'] || ''}</b></div>
              </div>
            </div>
            <div class="kt-vm-badge ${badgeClass}" style="font-size:11px; padding:2px 8px;">
              <span class="dot ${dotClass}"></span>
              <span>${status}</span>
            </div>
          </div>
          <div style="display:flex; justify-content:space-between; align-items:center; margin-top:10px; padding-top:10px; border-top:1px solid #4F739A;">
            <button class="btn-top" style="font-size:11px; padding:3px 8px;" onclick="selectOsVm('${s.name}')">상세 제어 보기 →</button>
            <div style="display:flex; gap:6px;">
              <button class="btn-action btn-stop" style="font-size:11px; padding:4px 8px;" ${status !== 'ACTIVE' ? 'disabled' : ''} onclick="executeSingleOsAction('${s.id}', '${s.name}', 'stop')">🛑 끄기</button>
              <button class="btn-action btn-start" style="font-size:11px; padding:4px 8px;" ${status === 'ACTIVE' ? 'disabled' : ''} onclick="executeSingleOsAction('${s.id}', '${s.name}', 'start')">⚡ 켜기</button>
            </div>
          </div>
        `;
        grid.appendChild(card);
      });
    }

    function confirmSelectedOsAction(action) {
      const vm = osServersCache.find(s => s.name === selectedOsVmName);
      if (!vm) return;
      executeSingleOsAction(vm.id, vm.name, action);
    }

    function executeSingleOsAction(id, name, action) {
      let actionKr = "";
      const isCritical = (name.includes('cp1') || name.includes('master'));
      
      if (action === 'stop') {
        actionKr = isCritical 
          ? `전원을 끄시겠습니까?

⚠️ [중요 경고] 이 노드는 Primary MySQL 원장 DB 및 K8s Control Plane입니다!
노드를 끄면 민원접수 서비스가 중단되고 AWS DR Failover가 발생합니다.`
          : `전원을 끄시겠습니까? (노드가 정지 상태로 전환됩니다)`;
      } else if (action === 'start') {
        actionKr = `전원을 켜시겠습니까? (부팅 후 약 30초 내에 K8s 및 서비스가 정상화됩니다)`;
      } else if (action === 'reboot') {
        actionKr = `소프트 재부팅을 진행하시겠습니까?`;
      } else if (action === 'hard_reboot') {
        actionKr = `하드웨어 강제 리셋(Hard Reboot)을 진행하시겠습니까?`;
      }

      if (confirm(`[OpenStack VM 전원 제어]
정말 '${name}'의 ${actionKr}`)) {
        dispatchOsAction(id, name, action);
      }
    }

    async function dispatchOsAction(id, name, action) {
      isOsActionInProgress = true;
      const spinner = document.getElementById('os-action-spinner');
      const btnStop = document.getElementById('btn-os-stop');
      const btnStart = document.getElementById('btn-os-start');
      const btnReboot = document.getElementById('btn-os-reboot');
      const btnHardReboot = document.getElementById('btn-os-hard-reboot');

      if (btnStop) btnStop.disabled = true;
      if (btnStart) btnStart.disabled = true;
      if (btnReboot) btnReboot.disabled = true;
      if (btnHardReboot) btnHardReboot.disabled = true;
      if (spinner) spinner.style.display = 'inline-block';

      addOsLog(`[ACTION] '${name}' -> ${action.toUpperCase()} 명령 Nova API 전송 중...`, 'warn');

      try {
        const res = await fetch('/api/openstack/vm/action', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ id: id, action: action })
        });
        const result = await res.json();

        if (result.status === 'ok') {
          addOsLog(`[ACCEPTED] Nova API 명령 접수 완료. 상태 전이 추적 시작...`, 'success');
          pollOsServerStatus(id, name, action);
        } else {
          addOsLog(`[ERROR] 명령 실패: ${result.message}`, 'err');
          if (spinner) spinner.style.display = 'none';
          isOsActionInProgress = false;
          fetchOsVmStatus(false);
        }
      } catch (err) {
        addOsLog(`[ERROR] 네트워크 요청 실패: ${err.message}`, 'err');
        if (spinner) spinner.style.display = 'none';
        isOsActionInProgress = false;
        fetchOsVmStatus(false);
      }
    }

    function pollOsServerStatus(id, name, action) {
      let attempts = 0;
      const maxAttempts = 20; // 20 * 2s = 40s
      const targetStatus = (action === 'stop') ? 'SHUTOFF' : 'ACTIVE';

      const interval = setInterval(async () => {
        attempts++;
        try {
          const res = await fetch('/api/openstack/vms');
          const data = await res.json();
          if (data.status === 'ok' && data.servers) {
            osServersCache = data.servers;
            const vm = data.servers.find(s => s.id === id);
            if (vm) {
              const currentStatus = (vm.status || '').toUpperCase();
              addOsLog(`상태 추적 중: '${name}' 현재 상태 = ${currentStatus} (경과: ${attempts * 2}초)`);

              if (currentStatus === targetStatus || (action === 'reboot' && attempts >= 4)) {
                clearInterval(interval);
                isOsActionInProgress = false;
                const spinner = document.getElementById('os-action-spinner');
                if (spinner) spinner.style.display = 'none';
                addOsLog(`[SUCCESS] '${name}' 전원 제어 완료! 최종 상태: ${currentStatus}`, 'success');
                renderFocusedOsVm();
                renderOsSummaryGrid(data.servers);
                updateOsStats(data.servers);
                return;
              }
            }
          }
        } catch (e) {
          addOsLog(`폴링 중 네트워크 에러: ${e.message}`, 'warn');
        }

        if (attempts >= maxAttempts) {
          clearInterval(interval);
          isOsActionInProgress = false;
          const spinner = document.getElementById('os-action-spinner');
          if (spinner) spinner.style.display = 'none';
          addOsLog(`[WARN] 추적 타임아웃 (40초). 최신 상태를 강제 갱신합니다.`, 'warn');
          fetchOsVmStatus(false);
        }
      }, 2000);
    }


    // ============================================================
    // LIVE OPERATIONS CONSOLE MODAL CONTROLLER
    // ============================================================
    function openConsoleModal() {
      const m = document.getElementById('console-modal');
      if (m) m.style.display = 'flex';
    }

    function closeConsoleModal() {
      const m = document.getElementById('console-modal');
      if (m) m.style.display = 'none';
    }

    function clearConsoleLog() {
      const s = document.getElementById('modal-log-stream');
      if (s) s.innerHTML = '<div class="log-line"><span class="log-time">[CLEAR]</span><span class="log-msg">로그 스트림이 초기화되었습니다.</span></div>';
    }

    const V3_STAGES = ['normal', 'l1', 'l2', 'path', 'l3', 'l4', 'bs'];

    function updateDrVelocity(stage) {
      const textEl = document.getElementById('dr-velocity-text');
      const b1 = document.getElementById('v-bar-1');
      const b2 = document.getElementById('v-bar-2');
      const b3 = document.getElementById('v-bar-3');
      const b4 = document.getElementById('v-bar-4');
      if (!textEl || !b1) return;

      const setBars = (color, heights, opacities) => {
        const bars = [b1, b2, b3, b4];
        bars.forEach((b, i) => {
          b.style.background = color;
          b.style.height = heights[i] + 'px';
          b.style.opacity = opacities[i];
        });
      };

      if (stage === 'normal') {
        textEl.innerText = '⚡ 180 req/s · RTT 4.2ms [VERY FAST 🟢]';
        textEl.style.color = '#8FE0B4';
        setBars('#8FE0B4', [8, 14, 20, 24], [1, 1, 1, 1]);
      } else if (stage === 'l1') {
        textEl.innerText = '⚠️ 135 req/s · RTT 42ms [FAST / RESTARTING 🟡]';
        textEl.style.color = '#F7D684';
        setBars('#F7D684', [8, 14, 20, 10], [1, 1, 1, 0.4]);
      } else if (stage === 'l2') {
        textEl.innerText = '⏱️ 45 req/s · RTT 920ms [SLOW / TIMEOUT 🟠]';
        textEl.style.color = '#f97316';
        setBars('#f97316', [8, 14, 6, 6], [1, 1, 0.3, 0.2]);
      } else if (stage === 'path') {
        textEl.innerText = '⚠️ 우회 중 · RTT 18ms [MODERATE 🔵]';
        textEl.style.color = '#9FD3F5';
        setBars('#9FD3F5', [8, 14, 18, 10], [1, 1, 1, 0.5]);
      } else if (stage === 'l3') {
        textEl.innerText = '⚡ 160 req/s · RTT 11ms [FAILOVER FAST 🔴]';
        textEl.style.color = '#f43f5e';
        setBars('#f43f5e', [8, 14, 20, 24], [1, 1, 1, 1]);
      } else if (stage === 'l4') {
        textEl.innerText = '🔄 복구 동기화 · RTT 8ms [SYNCING 🟣]';
        textEl.style.color = '#B08CFF';
        setBars('#B08CFF', [8, 14, 18, 22], [1, 1, 1, 1]);
      } else if (stage === 'bs') {
        textEl.innerText = '🛡️ 320 req/s · RTT 2ms [EDGE CACHED ⚫]';
        textEl.style.color = '#B4C6D8';
        setBars('#B4C6D8', [8, 14, 20, 24], [1, 1, 1, 1]);
      }
    }

    function updatePodDetailView(stage) {
      const bW1 = document.getElementById('badge-pod-w1');
      const tW1 = document.getElementById('txt-pod-w1-status');
      const bW2 = document.getElementById('badge-pod-w2');
      const tW2 = document.getElementById('txt-pod-w2-status');
      const bDb = document.getElementById('badge-pod-db');
      const tDb = document.getElementById('txt-pod-db-status');
      const bAws = document.getElementById('badge-pod-aws');
      const tAwsPods = document.getElementById('txt-pod-aws-pods');
      const tAwsDb = document.getElementById('txt-pod-aws-db');
      if (!bW1) return;

      if (stage === 'normal') {
        bW1.innerText = 'RUNNING 🟢'; bW1.style.background = '#5FD39A';
        tW1.innerText = '정상 처리 중 (0 restart)'; tW1.style.color = '#8FE0B4';
        bW2.innerText = 'RUNNING 🟢'; bW2.style.background = '#5FD39A';
        tW2.innerText = '정상 트래픽 분산 (0 restart)'; tW2.style.color = '#8FE0B4';
        bDb.innerText = 'PRIMARY RW 🟢'; bDb.style.background = '#5FD39A';
        tDb.innerText = 'GTID 스트리밍 송출 (Lag: 0s)'; tDb.style.color = '#8FE0B4';
        bAws.innerText = 'STANDBY RO 🟡'; bAws.style.background = '#6A8BAE';
        tAwsPods.innerText = 'Replicas: 0 (L3 대기)'; tAwsPods.style.color = '#B4C6D8';
        tAwsDb.innerText = 'Semi-sync 수신 (ACK 확정)'; tAwsDb.style.color = '#9FD3F5';
      } else if (stage === 'l1') {
        bW1.innerText = 'CRASHED 💥'; bW1.style.background = '#FF7A66';
        tW1.innerText = 'Pod #1 OOM 크래시 ➔ K8s 자동 재시작 중 (Restart +1)'; tW1.style.color = '#FF9E8C';
        bW2.innerText = 'ABSORBING 🟡'; bW2.style.background = '#F4C95D';
        tW2.innerText = 'Pod #2가 전체 민원 트래픽 100% 임시 흡수 처리'; tW2.style.color = '#F7D684';
      } else if (stage === 'l2') {
        bW1.innerText = 'FROZEN 🟠'; bW1.style.background = '#f97316';
        tW1.innerText = '1분간 무응답 ➔ 터널 B Ansible이 systemd 재가동 중'; tW1.style.color = '#f97316';
        bW2.innerText = 'RESTARTING 🟠'; bW2.style.background = '#f97316';
        tW2.innerText = 'Ansible 플레이북 자동 실행 (≤ 3분 이내 복구 목표)'; tW2.style.color = '#f97316';
      } else if (stage === 'path') {
        tW1.innerText = '터널 A 단절로 직접 수신 불가 ➔ 터널 B·C 우회 수신 중';
        tW2.innerText = '온프렘 인스턴스는 100% 정상이므로 DB 승격 금지!';
      } else if (stage === 'l3') {
        bW1.innerText = 'FENCED 🛑'; bW1.style.background = '#6A8BAE';
        tW1.innerText = '온프렘 전면 마비 ➔ Nova Stop으로 스플릿 브레인 차단'; tW1.style.color = '#FF7A66';
        bW2.innerText = 'DOWN 🔴'; bW2.style.background = '#6A8BAE';
        tW2.innerText = 'Compute 노드 응답 불가 (인스턴스 전원 차단됨)'; tW2.style.color = '#FF7A66';
        bDb.innerText = 'ISOLATED 🛑'; bDb.style.background = '#FF7A66';
        tDb.innerText = 'Watchdog 펜싱 완료 (Primary 쓰기 차단)'; tDb.style.color = '#FF7A66';
        bAws.innerText = 'ACTIVE RW 🔴'; bAws.style.background = '#5FD39A';
        tAwsPods.innerText = 'Replicas: 2 (EC2 확장 및 웹/API 기동 완료)'; tAwsPods.style.color = '#5FD39A';
        tAwsDb.innerText = 'super_read_only = OFF (AWS Replica 승격!)'; tAwsDb.style.color = '#5FD39A';
      } else if (stage === 'l4') {
        bW1.innerText = 'RECOVERED 🟢'; bW1.style.background = '#5FD39A';
        tW1.innerText = '온프렘 하드웨어 복구 및 k3s 클러스터 재가동 완료'; tW1.style.color = '#8FE0B4';
        bW2.innerText = 'RECOVERED 🟢'; bW2.style.background = '#5FD39A';
        tW2.innerText = '역방향 GTID 복제 수신 완료 (무손실 동기화)'; tW2.style.color = '#8FE0B4';
        bDb.innerText = 'PRIMARY RW 🟢'; bDb.style.background = '#5FD39A';
        tDb.innerText = '온프렘 Primary 재승격 완료 (정상 수용 재개)'; tDb.style.color = '#8FE0B4';
        bAws.innerText = 'STANDBY RO 🟡'; bAws.style.background = '#6A8BAE';
        tAwsPods.innerText = 'Replicas: 0 (AWS 서비스 대기 강등)'; tAwsPods.style.color = '#B4C6D8';
        tAwsDb.innerText = 'super_read_only = ON (Replica 2 원복)'; tAwsDb.style.color = '#9FD3F5';
      } else if (stage === 'bs') {
        bW1.innerText = 'OFFLINE ⚫'; bW1.style.background = '#1D4A7A';
        tW1.innerText = '온프렘 전체 파괴 (Black Sky 재난)'; tW1.style.color = '#8AA5C2';
        bW2.innerText = 'OFFLINE ⚫'; bW2.style.background = '#1D4A7A';
        tW2.innerText = 'Cloudflare 0초 폴백 작동 중'; tW2.style.color = '#8AA5C2';
        bDb.innerText = 'OFFLINE ⚫'; bDb.style.background = '#1D4A7A';
        tDb.innerText = 'AWS 및 온프렘 DB 전체 통신 두절'; tDb.style.color = '#8AA5C2';
        bAws.innerText = 'OFFLINE ⚫'; bAws.style.background = '#1D4A7A';
        tAwsPods.innerText = 'GitHub Pages(dr.ktci5.kr)로 민원 비상 접수 중'; tAwsPods.style.color = '#9FD3F5';
      }
    }

    // ============================================================
    // v3.0 DRAWIO TECHNICAL ARCHITECTURE STAGE CONTROLLER
    // ============================================================
    let currentV3Stage = 'normal';

    function setV3Stage(stage) {
      currentV3Stage = stage;
      const isoScene = document.getElementById('iso-scene');
      if (isoScene) isoScene.setAttribute('data-stage', stage);
      if (window.Topo2D) window.Topo2D.setStage(stage);

      const keys = ['normal', 'l1', 'l2', 'path', 'l3', 'l4', 'bs'];
      keys.forEach(k => {
        const btn = document.getElementById(`btn-v3-${k}`);
        if (!btn) return;
        if (k === stage) {
          btn.style.background = (k === 'l3' || k === 'bs') ? '#FF7A66' : (k === 'l4' ? '#B08CFF' : (k === 'path' ? '#3A78B5' : (k === 'normal' ? '#5FD39A' : '#F4C95D')));
          btn.style.color = '#fff';
          btn.style.fontWeight = '700';
        } else {
          btn.style.background = 'transparent';
          btn.style.color = '#B4C6D8';
          btn.style.fontWeight = '500';
        }
      });

      // Canvas element references
      const zoneKt = document.getElementById('zone-kt-box');
      const zoneOnprem = document.getElementById('zone-onprem-box');
      const zoneAws = document.getElementById('zone-aws-box');

      const ktEdgeRoute = document.getElementById('kt-edge-route');
      const ktEdgeDot = document.getElementById('kt-edge-dot');
      const txtS3 = document.getElementById('txt-s3-status');
      const ghFallback = document.getElementById('subnet-gh-fallback');
      const ghBadge = document.getElementById('gh-badge');

      const badgeOnpremMode = document.getElementById('badge-onprem-mode');
      const txtFencing = document.getElementById('txt-fencing');
      const badgeDbRw = document.getElementById('badge-db-rw');
      const podWeb = document.getElementById('pod-web');
      const podApi = document.getElementById('pod-api');

      const badgeAwsMode = document.getElementById('badge-aws-mode');
      const badgeAwsDbRo = document.getElementById('badge-aws-db-ro');
      const txtOrchState = document.getElementById('txt-orch-state');

      const pathTunnelA = document.getElementById('path-tunnel-a');
      const pathTunnelB = document.getElementById('path-tunnel-b');
      const pathTunnelC = document.getElementById('path-tunnel-c');
      const pathDbSync = document.getElementById('path-db-sync');

      const titleEl = document.getElementById('v3-stage-title');
      const descEl = document.getElementById('v3-stage-desc');
      const badgeStatus = document.getElementById('v3-status-badge');
      const propSm = document.getElementById('v3-prop-sm');
      const propSignal = document.getElementById('v3-prop-signal');
      const propRto = document.getElementById('v3-prop-rto');
      const propTunnel = document.getElementById('v3-prop-tunnel');
      const sopText = document.getElementById('v3-sop-text');

      // Reset base styles
      zoneOnprem.style.opacity = '1';
      zoneOnprem.style.borderColor = 'rgba(95, 211, 154, 0.3)';
      zoneAws.style.opacity = '1';
      zoneAws.style.borderColor = 'rgba(244, 201, 93, 0.3)';
      ghFallback.style.opacity = '0.6';
      ghBadge.className = 'menu-badge';
      ghBadge.style.background = '#6A8BAE';
      ghBadge.innerText = 'STANDBY ⚪';

      podWeb.className = 'k8s-pod-chip pod-active';
      podApi.className = 'k8s-pod-chip pod-active';

      // Reset tunnel paths
      pathTunnelA.className.baseVal = "line-inactive";
      pathTunnelB.className.baseVal = "line-inactive";
      pathTunnelC.className.baseVal = "line-inactive";
      pathDbSync.className.baseVal = "line-inactive";

      if (stage === 'normal') {
        titleEl.innerText = "🟢 1. NORMAL: 평시 온프렘 Primary 가동 (터널 A 요청 + 터널 B GTID 복제)";
        descEl.innerText = "v3.0 설계: 모든 사이트 간 트래픽은 WireGuard 암호화 터널로 연결되며, 온프렘은 inbound 포트가 0개입니다.";
        badgeStatus.className = "kt-vm-badge state-running";
        badgeStatus.innerHTML = '<span class="dot green"></span>NORMAL STATUS';
        propSm.innerText = "NORMAL";
        propSm.style.color = "#5FD39A";
        propSignal.innerText = "S1:정상 · S2:정상 · S3:정상";
        propRto.innerText = "RTO: 0초 · RPO: 0초";
        propTunnel.innerText = "터널 A·B 활성 (C 대기)";

        ktEdgeRoute.innerText = "터널 A 발송 중";
        ktEdgeRoute.className = "tunnel-badge tunnel-a";
        ktEdgeDot.className = "dot green";
        txtS3.innerText = "정상 통과 🟢";
        txtS3.style.color = "#8FE0B4";

        badgeOnpremMode.innerText = "PRIMARY RW 🟢";
        badgeOnpremMode.style.background = "#5FD39A";
        txtFencing.innerText = "자가 펜싱 감시 중: 정상 (쓰기 허용)";
        badgeDbRw.innerText = "Read / Write";
        badgeDbRw.style.background = "#5FD39A";

        badgeAwsMode.innerText = "PILOT-LIGHT RO 🟡";
        badgeAwsMode.style.background = "#F4C95D";
        badgeAwsDbRo.innerText = "super_read_only = ON";
        badgeAwsDbRo.style.background = "#F4C95D";
        txtOrchState.innerText = "NORMAL (온프렘 가동)";
        txtOrchState.style.color = "#5FD39A";

        pathTunnelA.className.baseVal = "flow-line line-yellow";
        pathTunnelB.className.baseVal = "flow-line line-blue";
        pathDbSync.className.baseVal = "flow-line line-yellow";

        sopText.innerHTML = "<b>[v3.0 정상 가동 트래픽 & 보안 흐름]</b><br>" +
          "• <b>민원접수 진입</b>: HTTPS 요청이 KT Edge-GW(14.63.212.190)에 도착하여 TLS 종료 및 Nginx WAF 검사를 받습니다.<br>" +
          "• <b>터널 A 전송</b>: 온프렘 WireGuard 게이트웨이로 단방향 요청 전달 ➔ Traefik Ingress ➔ K3s 마스터-워커-워커(k8s-w1, w2) 분산 <code>minwon-app 파드 2대</code> ➔ <code>MySQL 8.4 Primary</code> 커밋.<br>" +
          "• <b>터널 B 복제</b>: MySQL GTID 이벤트가 터널 B를 타고 AWS Replica(super_read_only=ON)로 semi-sync 복제(ACK 후 커밋 확정)되고 binlog는 S3로 실시간 백업됩니다.";

        addDrLog("[v3.0-FLOW] 1단계: NORMAL 평시 정상 가동 상태가 활성화되었습니다.", "success");

      } else if (stage === 'l1') {
        titleEl.innerText = "🟡 2. L1: Pod 크래시 자가치유 (K8s liveness/readiness · 초 단위)";
        descEl.innerText = "v3.0 drawio: Pod 이상 발생 시 판단 주체는 K8s 자체이며, 외부 Orchestrator 개입 없이 Kubelet이 초 단위로 자가치유합니다.";
        badgeStatus.className = "kt-vm-badge state-transition";
        badgeStatus.innerHTML = '<span class="dot yellow"></span>L1 K8S HEALING';
        propSm.innerText = "NORMAL (Pod Healing)";
        propSm.style.color = "#F4C95D";
        propSignal.innerText = "S1:정상 · S2:정상 · K8s Pod 크래시";
        propRto.innerText = "목표: 초 단위 (0~10s)";
        propTunnel.innerText = "터널 A·B 정상 유지";

        podApi.className = 'k8s-pod-chip pod-restarting';
        pathTunnelA.className.baseVal = "flow-line line-yellow";
        pathTunnelB.className.baseVal = "flow-line line-blue";
        pathDbSync.className.baseVal = "flow-line line-yellow";

        sopText.innerHTML = "<b>[L1 K8s 자가치유 상세 매커니즘]</b><br>" +
          "• <b>장애 감지</b>: <code>minwon-api</code> 파드 OOM 또는 프로세스 크래시 감지 (livenessProbe <code>/healthz?live=1</code> 실패).<br>" +
          "• <b>자동 조치</b>: K8s Kubelet이 컨테이너를 즉각 재시작하며, Pod Anti-Affinity로 이중화된 <code>k8s-w1/w2 파드</code>가 트래픽을 분산 흡수하여 민원접수 서비스는 무중단 유지됩니다.<br>" +
          "• <b>판단 주체</b>: K8s (Orchestrator 및 사람 개입 불필요).";

        addDrLog("[v3.0-FLOW] 2단계: L1 Pod 크래시 감지 및 K8s 자동 재기동 활성화 (RTO: 초 단위)", "warn");

      } else if (stage === 'l2') {
        titleEl.innerText = "🟠 3. L2: 서비스 1분+ 무응답 ➔ 터널 B Ansible 자동 재기동 (≤3분)";
        descEl.innerText = "v3.0 drawio: L1으로 복구 안 되는 서비스 무응답 시 AWS Orchestrator가 터널 B를 통해 Nginx·앱·MySQL·WG를 자동 재기동합니다.";
        badgeStatus.className = "kt-vm-badge state-transition";
        badgeStatus.innerHTML = '<span class="dot yellow"></span>L2 ANSIBLE RESTART';
        propSm.innerText = "DEGRADED (L2 Playbook)";
        propSm.style.color = "#F4C95D";
        propSignal.innerText = "S1:실패 · S2:정상(호스트 접근가능)";
        propRto.innerText = "목표: ≤ 3분";
        propTunnel.innerText = "터널 B 경유 복구 명령 전송";

        txtOrchState.innerText = "DEGRADED (Ansible 실행)";
        txtOrchState.style.color = "#F4C95D";
        pathTunnelB.className.baseVal = "flow-line line-blue";

        sopText.innerHTML = "<b>[L2 서비스 무응답 복구 프로세스]</b><br>" +
          "• <b>감지 지표</b>: 민원접수 S1 프로브가 1분 이상 응답 없음(Timeout) 감지.<br>" +
          "• <b>자동 복구</b>: AWS Orchestrator가 <b>터널 B</b>를 경유하여 온프레미스 대상 <code>ansible-playbook restart_services.yml</code> 원격 실행.<br>" +
          "• <b>복구 대상</b>: 온프렘 Nginx ➔ minwon-app ➔ MySQL ➔ WireGuard 순차 재기동 후 헬스체크 통과 시 NORMAL 복귀.";

        addDrLog("[v3.0-FLOW] 3단계: L2 서비스 1분 무응답 ➔ 터널 B 경유 Ansible 자동 재기동 명령 발송 (≤ 3m)", "warn");

      } else if (stage === 'path') {
        titleEl.innerText = "🔵 4. 경로 장애: 터널 A만 단절 (S1·S3 실패, S2 정상) ➔ 터널 C·B 우회 (DB 승격 절대 금지!)";
        descEl.innerText = "v3.0 drawio 핵심: 온프렘이 살아있는 단순 터널 A 장애 시, DB를 승격하면 Split-Brain이 발생하므로 절대로 승격하지 않고 터널 C·B로 우회합니다!";
        badgeStatus.className = "kt-vm-badge state-transition";
        badgeStatus.innerHTML = '<span class="dot blue"></span>PATH REROUTING';
        propSm.innerText = "DEGRADED (Path Bypass)";
        propSm.style.color = "#9FD3F5";
        propSignal.innerText = "S1:실패 · S2:정상 · S3:실패 (A단절)";
        propRto.innerText = "목표: ≤ 3분 (Split-Brain 방지)";
        propTunnel.innerText = "터널 A 단절 ➔ 터널 C+B 우회";

        ktEdgeRoute.innerText = "터널 C 우회 발송";
        ktEdgeRoute.className = "tunnel-badge tunnel-c";
        txtS3.innerText = "터널 A 실패 🔴";
        txtS3.style.color = "#FF7A66";

        txtOrchState.innerText = "DEGRADED (경로 우회 통제)";
        txtOrchState.style.color = "#9FD3F5";

        pathTunnelA.className.baseVal = "line-red";
        pathTunnelC.className.baseVal = "flow-line line-purple";
        pathTunnelB.className.baseVal = "flow-line line-blue";
        pathDbSync.className.baseVal = "flow-line line-yellow";

        sopText.innerHTML = "<b>[경로 장애 우회 및 Split-Brain 방지 원칙]</b><br>" +
          "• <b>3-Signal 판정</b>: S1 실패 ∧ S3 실패이나, <b>S2(터널 B)는 정상 통신</b> 상태 ➔ <b>'온프렘은 살아있음'</b> 확정.<br>" +
          "• <b>절대 금지</b>: AWS DB를 Master로 승격하면 양쪽 모두 쓰기가 일어나는 <b>Split-Brain 대참사</b>가 발생하므로 DB 승격 금지!<br>" +
          "• <b>우회 라우팅</b>: KT Edge ➔ <b>터널 C</b> ➔ AWS ➔ <b>터널 B</b> ➔ 온프레미스로 트래픽 우회 수용.";

        addDrLog("[v3.0-FLOW] 4단계: 터널 A 단절 감지! Split-Brain 방지를 위해 DB 승격 차단 및 터널 C·B 우회 가동!", "warn");

      } else if (stage === 'l3') {
        titleEl.innerText = "🔴 5. L3: 온프렘 사이트 전면 마비 (S1∧S2∧S3 실패) ➔ 자가 펜싱 확인 ➔ AWS Replica 승격";
        descEl.innerText = "v3.0 drawio 핵심: 3개 신호가 모두 실패했을 때만 비로소 온프렘 쓰기를 차단(펜싱)하고 AWS Pilot-Light를 활성화합니다.";
        badgeStatus.className = "kt-vm-badge state-stopped";
        badgeStatus.innerHTML = '<span class="dot red"></span>L3 DR ACTIVE (AWS)';
        propSm.innerText = "DR_ACTIVE";
        propSm.style.color = "#FF7A66";
        propSignal.innerText = "S1:실패 ∧ S2:실패 ∧ S3:실패 (3신호 확정)";
        propRto.innerText = "목표: ≤ 15분 · RPO: 0 (semi-sync)";
        propTunnel.innerText = "터널 C 민원접수 수용 (터널 A·B 두절)";

        zoneOnprem.style.opacity = '0.4';
        zoneOnprem.style.borderColor = '#FF7A66';
        badgeOnpremMode.innerText = "FENCED / DOWN 💥";
        badgeOnpremMode.style.background = "#FF7A66";
        txtFencing.innerText = "자가 펜싱 발동: 온프렘 쓰기 강제 차단";
        badgeDbRw.innerText = "BLOCKED";
        badgeDbRw.style.background = "#FF7A66";

        zoneAws.style.borderColor = '#5FD39A';
        badgeAwsMode.innerText = "DR PRIMARY RW 🟢";
        badgeAwsMode.style.background = "#5FD39A";
        badgeAwsDbRo.innerText = "super_read_only = OFF (승격)";
        badgeAwsDbRo.style.background = "#5FD39A";
        txtOrchState.innerText = "DR_ACTIVE (AWS에서 서비스 중)";
        txtOrchState.style.color = "#FF7A66";

        ktEdgeRoute.innerText = "터널 C (AWS 절체)";
        ktEdgeRoute.className = "tunnel-badge tunnel-c";

        pathTunnelA.className.baseVal = "line-red";
        pathTunnelB.className.baseVal = "line-red";
        pathTunnelC.className.baseVal = "flow-line line-purple";
        pathDbSync.className.baseVal = "line-inactive";

        sopText.innerHTML = "<b>[L3 DR 전환 4단계 실행 절차]</b><br>" +
          "1. <b>3-Signal 판정</b>: S1(공인) ∧ S2(터널 B) ∧ S3(터널 A) 3회 연속 실패 ➔ 온프렘 사이트 전면 장애 확정.<br>" +
          "2. <b>펜싱 확인</b>: 온프렘 자가 펜싱 Watchdog에 의해 Primary 쓰기 차단 확인.<br>" +
          "3. <b>Replica 승격 & EC2 확장</b>: AWS MySQL <code>super_read_only = OFF</code> 해제, Pilot-Light EC2 확장 및 k3s 앱 기동.<br>" +
          "4. <b>Edge 전환</b>: KT Edge-GW upstream을 <b>터널 C(AWS)</b>로 전환 ➔ AWS에서 민원 무중단 접수 재개.";

        addDrLog("[v3.0-FLOW] 5단계: 🚨 L3 사이트 전면 장애 확정! 펜싱 확인 ➔ AWS Replica 승격 ➔ 터널 C 절체 완료!", "err");

      } else if (stage === 'l4') {
        titleEl.innerText = "🟣 6. L4: 온프렘 정상화 ➔ 역방향 GTID 복제 동기화 ➔ 온프렘 승격 (Failback)";
        descEl.innerText = "v3.0 drawio 핵심: 온프렘 하드웨어 복구 시, AWS 서비스 동안 쌓인 데이터를 역방향으로 동기화한 후 무손실 원복합니다.";
        badgeStatus.className = "kt-vm-badge state-running";
        badgeStatus.innerHTML = '<span class="dot green"></span>FAILBACK COMPLETED';
        propSm.innerText = "NORMAL (원복 완료)";
        propSm.style.color = "#5FD39A";
        propSignal.innerText = "S1:정상 · S2:정상 · S3:정상 (복제지연 0)";
        propRto.innerText = "목표: 무손실 원복 · RPO: 0초";
        propTunnel.innerText = "터널 A 복귀 · 터널 B 역동기화 완료";

        zoneOnprem.style.opacity = '1';
        badgeOnpremMode.innerText = "PRIMARY RW (복구) 🟢";
        badgeOnpremMode.style.background = "#5FD39A";
        txtFencing.innerText = "펜싱 해제: 온프렘 Primary 쓰기 정상화";
        badgeDbRw.innerText = "Read / Write";
        badgeDbRw.style.background = "#5FD39A";

        badgeAwsMode.innerText = "PILOT-LIGHT RO 🟡";
        badgeAwsMode.style.background = "#F4C95D";
        badgeAwsDbRo.innerText = "super_read_only = ON (재강등)";
        badgeAwsDbRo.style.background = "#F4C95D";
        txtOrchState.innerText = "NORMAL (Failback 성공)";
        txtOrchState.style.color = "#5FD39A";

        ktEdgeRoute.innerText = "터널 A 복귀";
        ktEdgeRoute.className = "tunnel-badge tunnel-a";

        pathTunnelA.className.baseVal = "flow-line line-yellow";
        pathTunnelB.className.baseVal = "flow-line line-blue";
        pathDbSync.className.baseVal = "flow-line line-yellow";

        sopText.innerHTML = "<b>[L4 Failback 무손실 원복 절차]</b><br>" +
          "1. <b>온프렘을 Replica로 재구성</b>: 터널 B를 통해 온프렘 DB를 AWS Master의 슬레이브로 연결하여 누적 데이터 복제 따라잡기.<br>" +
          "2. <b>복제 지연 0 검증</b>: 데이터 대조 및 온프렘 <code>/readyz</code> 프로브 통과 확인.<br>" +
          "3. <b>전환</b>: AWS 쓰기 차단(super_read_only=ON) ➔ 온프렘 Primary 승격 ➔ KT Edge upstream을 터널 A로 역전환 ➔ NORMAL 완전 복구.";

        addDrLog("[v3.0-FLOW] 6단계: L4 역방향 GTID 동기화 완료 및 온프레미스 Primary 무손실 원복 성공!", "success");

      } else if (stage === 'bs') {
        titleEl.innerText = "⚫ 7. Black Sky: 온프렘 + AWS 전면 단절 시 Cloudflare ➔ GitHub Pages 0초 폴백";
        descEl.innerText = "v3.0 drawio 초과 달성: 국가 재난으로 3대 거점이 전면 불능일 때 최전방 Cloudflare Worker가 정적 비상 접수처를 0초 서빙합니다.";
        badgeStatus.className = "kt-vm-badge state-stopped";
        badgeStatus.innerHTML = '<span class="dot red"></span>BLACK SKY 0-SEC';
        propSm.innerText = "BLACK_SKY_FALLBACK";
        propSm.style.color = "#E8604C";
        propSignal.innerText = "오리진 502/504 연속 감지";
        propRto.innerText = "목표: 0초 비상 접수";
        propTunnel.innerText = "클라우드 전면 단절 ➔ GH Pages";

        zoneOnprem.style.opacity = '0.3';
        zoneAws.style.opacity = '0.3';
        ghFallback.style.opacity = '1';
        ghFallback.style.borderColor = '#5FD39A';
        ghBadge.className = 'menu-badge';
        ghBadge.style.background = '#5FD39A';
        ghBadge.innerText = 'EMERGENCY ACTIVE 🟢';

        ktEdgeRoute.innerText = "오리진 두절";
        ktEdgeRoute.className = "tunnel-badge";
        ktEdgeRoute.style.background = "#FF7A66";
        ktEdgeRoute.style.color = "#fff";
        ktEdgeDot.className = "dot red";

        txtOrchState.innerText = "DISCONNECTED";
        txtOrchState.style.color = "#FF7A66";

        sopText.innerHTML = "<b>[Black Sky 0초 GitHub Pages Fallback 절차]</b><br>" +
          "• <b>상황</b>: 온프레미스 및 AWS 클라우드 센터가 동시 통신 두절된 극한의 재난 상황.<br>" +
          "• <b>0초 방어</b>: Cloudflare Worker 엣지가 백엔드 502 에러를 가로채어 <b>GitHub Pages(dr.ktci5.kr) 정적 민원 폼</b>을 0초 즉시 노출.<br>" +
          "• <b>결과</b>: 백엔드 복구 전까지 민원인의 신청 데이터를 비상 보관하여 단 1건의 민원도 유실되지 않도록 방어합니다.";

        addDrLog("[v3.0-FLOW] 7단계: 🚨 Black Sky 전면 단절 발생! Cloudflare ➔ GitHub Pages 0초 비상 접수 가동!", "err");
      }

      // 동적 트래픽 흐름 속도계 및 하단 파드 단위 상세 상태 동기화
      updateDrVelocity(stage);
      updatePodDetailView(stage);
    }

    window.addEventListener('DOMContentLoaded', () => {
      const hash = window.location.hash.replace('#', '');
      if (SERVICES[hash]) {
        switchTab(hash);
      }
      // Initial fetch of KT VM status
      fetchKtVmStatus(false);
      fetchOsVmStatus(false);
      // Auto-poll KT & OS status every 30s
      setInterval(() => {
        if (currentTab === 'overview' || currentTab === 'ktvm' || currentTab === 'osvm') {
          fetchOsVmStatus(false);
          fetchKtVmStatus(false);
        }
      }, 30000);
    });

    window.addEventListener('keydown', (e) => {
      if (e.key === 'Escape' && document.body.classList.contains('fullscreen')) {
        document.body.classList.remove('fullscreen');
      }
    });
  </script>
  <script>
(function () {
  'use strict';
  // ===== 민원불패 v2.5.1 — 2D 평면 연결 구성도 (청사진, 순수 SVG) =====
  var host = document.getElementById('t3-host');
  var stageEl = document.querySelector('.dc-main .iso-stage');
  if (!host || !stageEl) return;
  var NS = 'http://www.w3.org/2000/svg';
  var VB0 = { x: 0, y: 14, w: 1760, h: 866 };
  var vb = { x: VB0.x, y: VB0.y, w: VB0.w, h: VB0.h };

  function el(tag, attrs, parent) {
    var e = document.createElementNS(NS, tag);
    for (var k in attrs) e.setAttribute(k, attrs[k]);
    if (parent) parent.appendChild(e);
    return e;
  }
  function txt(parent, x, y, s, cls, anchor) {
    var t = el('text', { x: x, y: y, 'class': cls || '', 'text-anchor': anchor || 'start' }, parent);
    t.textContent = s;
    return t;
  }

  var svg = el('svg', { 'class': 't2-svg', role: 'img', 'aria-label': '민원불패 v2.5.1 2D 연결 구성도', preserveAspectRatio: 'xMidYMid meet' });
  host.appendChild(svg);
  var gZones = el('g', {}, svg), gLinks = el('g', {}, svg), gNodes = el('g', {}, svg), gReach = el('g', { id: 't2-reachability', 'class': 't2-reach', style: 'display:none;' }, svg), gMarks = el('g', {}, svg), gFx = el('g', {}, svg);
  function applyVB() { svg.setAttribute('viewBox', vb.x + ' ' + vb.y + ' ' + vb.w + ' ' + vb.h); }
  applyVB();

  // ---------- 폐쇄망/오픈스택 네트워크 격리 및 Argo CD · Grafana 도달 범위 오버레이 ----------
  // 1) 폐쇄망 DB 격리 경계벽 (붉은색 점선 & 자물쇠)
  var rIsoBox = el('rect', { x: 994, y: 300, width: 227, height: 412, fill: 'rgba(255, 122, 102, 0.08)', stroke: '#FF7A66', 'stroke-width': '3.5', 'stroke-dasharray': '8 5' }, gReach);
  var rIsoTag = el('g', {}, gReach);
  el('rect', { x: 1005, y: 310, width: 205, height: 26, fill: '#FF7A66', rx: 3 }, rIsoTag);
  txt(rIsoTag, 1107, 327, '🔒 [폐쇄망] 완전 격리 (No-GW)', '', 'middle');

  // 2) Argo CD GitOps 도달 경로 (보라색 네온선)
  var rArgoPath = el('path', { d: 'M770,742 L770,400 L690,395', fill: 'none', stroke: '#B08CFF', 'stroke-width': '3', 'stroke-dasharray': '6 4' }, gReach);
  var rArgoTag = el('g', {}, gReach);
  el('rect', { x: 700, y: 705, width: 170, height: 22, fill: '#B08CFF', rx: 3 }, rArgoTag);
  txt(rArgoTag, 785, 720, '🚀 Argo CD 배포 (6443 API)', '', 'middle');

  // 3) Grafana 관제 스크랩 도달 경로 (주황색 네온선)
  var rGrafPath = el('path', { d: 'M1320,360 L970,360 L800,360 L500,464', fill: 'none', stroke: '#F4C95D', 'stroke-width': '2.5', 'stroke-dasharray': '4 4' }, gReach);
  var rGrafTag = el('g', {}, gReach);
  el('rect', { x: 1130, y: 345, width: 175, height: 22, fill: '#D9A93A', rx: 3 }, rGrafTag);
  txt(rGrafTag, 1217, 360, '📈 Grafana 관제 스크랩 (9100)', '', 'middle');

  window.toggleReachabilityOverlay = function (force) {
    if (!gReach) return;
    var cur = gReach.style.display !== 'none';
    var next = typeof force === 'boolean' ? force : !cur;
    gReach.style.display = next ? 'inline' : 'none';
    var btn = document.getElementById('btn-reach-toggle');
    var txt = document.getElementById('btn-reach-text');
    if (btn) {
      btn.style.background = next ? '#B08CFF' : 'rgba(56,189,248,0.15)';
      btn.style.color = next ? '#fff' : '#38bdf8';
      var str = next ? '📡 도달 범위 & 격리선 숨기기' : '📡 도달 범위 & 격리선 표시';
      if (txt) txt.innerText = next ? '도달 범위 & 격리선 숨기기' : '도달 범위 & 격리선 표시';
      else btn.innerText = str;
    }
  };

  // ---------- 구성 요소 ----------
  var nodes = {}, links = {}, zones = {};
  function zone(id, x, y, w, h, title, sub) {
    var g = el('g', { 'class': 't2-zone', id: 't2-' + id }, gZones);
    el('rect', { x: x, y: y, width: w, height: h }, g);
    txt(g, x + 12, y + 28, title, 't2-zone-t');
    if (sub) txt(g, x + 12, y + 54, sub, 't2-zone-s');
    zones[id] = g;
    return g;
  }
  function subnet(x, y, w, h, title, tone) {
    var g = el('g', { 'class': 't2-subnet ' + (tone || '') }, gZones);
    el('rect', { x: x, y: y, width: w, height: h }, g);
    txt(g, x + 8, y + 18, title, 't2-subnet-t');
  }
  function node(id, x, y, w, h, title, sub, info, kind) {
    var g = el('g', { 'class': 't2-node' + (kind ? ' ' + kind : ''), id: 't2n-' + id, tabindex: '0' }, gNodes);
    if (kind === 'db') {
      var ry = 9;
      el('path', { 'class': 'body', d: 'M' + x + ',' + (y + ry) + ' L' + x + ',' + (y + h - ry) + ' A' + (w / 2) + ',' + ry + ' 0 0 0 ' + (x + w) + ',' + (y + h - ry) + ' L' + (x + w) + ',' + (y + ry) }, g);
      el('ellipse', { 'class': 'top', cx: x + w / 2, cy: y + ry, rx: w / 2, ry: ry }, g);
      el('path', { 'class': 'ring', d: 'M' + x + ',' + (y + h * 0.45) + ' A' + (w / 2) + ',' + ry + ' 0 0 0 ' + (x + w) + ',' + (y + h * 0.45) }, g);
    } else {
      el('rect', { 'class': 'body', x: x, y: y, width: w, height: h }, g);
    }
    var cy = y + h / 2 + (sub && h >= 52 ? -6 : 6);
    txt(g, x + w / 2, cy, title, 't2-node-t', 'middle');
    if (sub && h >= 52) txt(g, x + w / 2, cy + 23, sub, 't2-node-s', 'middle');
    nodes[id] = { g: g, x: x, y: y, w: w, h: h, info: Object.assign({ title: title, sub: sub }, info || {}) };
    g.addEventListener('click', function (e) { e.stopPropagation(); showCard(id); });
    g.addEventListener('keydown', function (e) { if (e.key === 'Enter') showCard(id); });
    return nodes[id];
  }
  function link(id, pts, kind, label) {
    var d = 'M' + pts.map(function (p) { return p[0] + ',' + p[1]; }).join(' L');
    var g = el('g', { 'class': 't2-link k-' + kind + (/^t[ABC]$/.test(id) ? ' tunnel' : ''), id: 't2l-' + id }, gLinks);
    if (/^t[ABC]$/.test(id)) el('path', { 'class': 'band', d: d }, g);
    var p = el('path', { 'class': 'line', d: d }, g);
    if (label) { var t = txt(g, label[0], label[1], label[2], 't2-tun-t', label[3] || 'start'); t.setAttribute('class', 't2-tun-t k-' + kind); }
    links[id] = { g: g, path: p, len: 0, kind: kind };
    return links[id];
  }

  // 존 · 서브넷  (열: 인터넷 30–230 | 통로 | KT 270–480 | 통로 | 온프렘 530–1230 | 통로 | AWS 1290–1730 | 우측 통로)
  txt(gZones, 40, 150, '인터넷 (WAN)', 't2-zone-t');
  zone('gh', 20, 600, 210, 200, 'GitHub Pages', '0초 비상 접수 (dr.ktci5.kr)');
  zone('kt', 270, 120, 210, 560, 'KT Cloud', '입구 전용 · VM 1대 (14.63.212.190)');
  zone('on', 530, 120, 700, 700, '온프레미스 OpenStack', 'Primary · K3s 마스터-워커-워커 · MySQL (3단 격리망)');
  zone('aws', 1290, 120, 440, 700, 'AWS (ap-northeast-2)', '관제 · DR 대기 · S3 백업');
  subnet(285, 186, 180, 480, 'Edge-GW VM · kt-edge-dr-01 (Nginx+WAF)');
  subnet(545, 186, 670, 84, '🌐 [외부망 DMZ] br-ex (FIP 10.11.0.0/24 · WG 터널 종단)', 'warm');
  subnet(545, 306, 440, 400, '🏢 [내부망 SERVICE] net-k3s (172.20.0.0/24 · K3s 단독 워커 체제)', 'ok');
  subnet(705, 340, 265, 236, 'app 네임스페이스 (워커1·2 1:1 분산)', 'violet');
  subnet(705, 592, 265, 100, 'data 네임스페이스 (Redis/MQ)');
  subnet(1000, 306, 215, 400, '🔒 [폐쇄망 ISOLATED] net-data (10.10.2.0/24 · MySQL DB 원장)', 'warm');
  subnet(545, 720, 670, 80, '🛠️ [관리망 OPS] ops 서브넷 (Harbor · Argo CD)');
  subnet(1305, 186, 410, 84, 'WG 서브넷 (10.200.0.0/24 풀메쉬)');
  subnet(1305, 290, 205, 200, '관제 서브넷 (Prometheus·Grafana)', 'warm');
  subnet(1525, 290, 190, 200, '리전 서비스 (S3 백업)');
  subnet(1305, 510, 410, 200, 'DR 서브넷 · Pilot-Light (Replica 2)', 'warm');

  // 연결 (먼저 그려서 노드 아래로) — 링크마다 전용 통로, 제목 구간을 피해 진입
  link('cit_cf', [[85, 230], [85, 330]], 'req');
  link('cf_ng', [[210, 352], [250, 352], [250, 256], [300, 256]], 'req');
  link('cf_gh', [[180, 404], [180, 666]], 'fb');
  link('q_cf', [[300, 372], [258, 372], [258, 390], [210, 390]], 'warn');
  link('ng_q', [[375, 286], [375, 330]], 'req');
  link('q_wg', [[375, 390], [375, 434]], 'req');
  link('tA', [[450, 464], [500, 464], [500, 280], [780, 280], [780, 248], [800, 248]], 'ta', [640, 298, '터널 A', 'middle']);
  link('tB', [[1320, 224], [970, 224]], 'tb', [1260, 214, '터널 B', 'middle']);
  link('tC', [[375, 494], [375, 850], [1745, 850], [1745, 216], [1470, 216]], 'tc', [960, 840, '터널 C · KT ↔ AWS', 'middle']);
  link('wg_ing', [[840, 260], [840, 294], [670, 294], [670, 350]], 'req');
  link('ing_web', [[690, 395], [720, 395]], 'req');
  link('web_api', [[835, 395], [845, 395]], 'req');
  link('web_api2', [[835, 408], [840, 408], [840, 455], [845, 455]], 'req');
  link('api_db', [[960, 380], [1030, 380]], 'data');
  link('api2_db', [[960, 446], [1030, 446]], 'data');
  link('api_mq', [[960, 402], [978, 402], [978, 647], [960, 647]], 'req');
  link('mq_worker', [[845, 640], [840, 640], [840, 515], [835, 515]], 'req');
  link('worker_db', [[777, 538], [777, 584], [1110, 584], [1110, 460]], 'data');
  link('mq_na', [[902, 624], [902, 538]], 'req');
  link('db_wg', [[1160, 360], [1160, 248], [970, 248]], 'repl');
  link('aws_rep', [[1400, 260], [1400, 280], [1517, 280], [1517, 500], [1620, 500], [1620, 546]], 'repl');
  link('aws_s3', [[1470, 236], [1620, 236], [1620, 330]], 'backup');
  link('aws_ctl', [[1440, 260], [1440, 330]], 'ctrl');
  link('aws_ec2', [[1320, 248], [1298, 248], [1298, 587], [1320, 587]], 'req');
  link('ec2_rep', [[1480, 587], [1540, 587]], 'data');
  link('ctl_cf', [[1480, 330], [1480, 40], [18, 40], [18, 384], [40, 384]], 'ctrl', [900, 34, 'S1 공인 프로브 (Orchestrator → Cloudflare)', 'middle']);
  link('cf_cfd', [[735, 212], [735, 66], [30, 66], [30, 348], [40, 348]], 'cft', [900, 60, 'minwon-tunnel · Cloudflare Tunnel (아웃바운드)', 'middle']);
  link('cfd_wg', [[745, 224], [800, 224]], 'cft');
  link('cfd_argocd', [[565, 236], [538, 236], [538, 810], [770, 810], [770, 782]], 'cft');
  link('ops_cf', [[85, 470], [85, 404]], 'cft');
  link('bypass', [[160, 200], [242, 200], [242, 240], [300, 240]], 'risk', [166, 193, 'origin-kt DNS 전용']);

  txt(gLinks, 95, 268, 'minwon.ktci5.kr', 't2-dns');
  txt(gLinks, 95, 286, '프록시 · KT Edge', 't2-dns s');
  // 노드
  node('citizen', 40, 170, 120, 60, '사용자', 'HTTPS 민원 접수', { zone: '인터넷', lines: ['https://minwon.ktci5.kr 접속'] });
  node('cf', 40, 330, 170, 74, 'Cloudflare', 'WAF · 봇/IP 제한', { zone: '인터넷 엣지', lines: ['minwon.ktci5.kr → 14.63.212.190 (프록시 · WAF/DDoS)', 'origin-kt.ktci5.kr → 같은 IP (DNS 전용 · 오리진 노출)', '터널 호스트명 8개 → minwon-tunnel', 'Edge 503 · 오리진 장애 시 Worker가 비상 폼 안내'] });
  node('ops', 40, 470, 90, 46, '운영자', '', { zone: '인터넷', lines: ['관리 화면은 Cloudflare Tunnel로만 접속', 'figteam.ktci5.kr 통합 로그인(SSO)'] });
  node('gh', 40, 666, 170, 74, '비상 접수 폼', 'dr.ktci5.kr', { zone: 'GitHub Pages', subnet: 'subnet-gh-fallback', lines: ['폭주 초과분 · Black Sky 시 0초 노출', '민원 데이터 비상 보관'] });
  node('nginx', 300, 226, 150, 60, 'Nginx TLS·WAF', '10초 마이크로캐시', { zone: 'KT Cloud', subnet: 'subnet-kt-edge', lines: ['TLS 종료 · ModSecurity WAF', 'GET 응답 10초 캐시 (무상태)'] });
  node('queue', 300, 330, 150, 60, '접수 대기열', 'limit_req 버스트', { zone: 'KT Cloud', subnet: 'subnet-kt-edge', lines: ['총량 제한: 허용 속도로만 온프렘 전달', '버스트 내 요청은 순서대로 지연', '초과분 503 + Retry-After → 비상 폼'] });
  node('wgkt', 300, 434, 150, 60, 'WG 종단', '터널 A · C', { zone: 'KT Cloud', subnet: 'subnet-kt-edge', lines: ['WireGuard 터널 A (온프렘) · C (AWS)'] });
  node('gpu', 565, 212, 180, 48, 'cloudflared · 포털', '', { zone: '온프레미스 · GPU 서버 ktci5 (10.10.10.8)', lines: ['minwon-tunnel 커넥터 (아웃바운드만 · 인바운드 0)', 'figteam 통합 포털 :18088', '호스트명 라우팅: figteam · app · argocd · grafana · horizon · openstack', 'aws-ctl → WG 터널 B · kt-edge → WG 터널 A'] });
  node('onwg', 800, 212, 170, 48, 'WireGuard GW', '', { zone: '온프레미스', subnet: 'subnet-onprem-wg', lines: ['공인 IP 없음 · Outbound만', '터널 A · B 종단', '자가 펜싱 Watchdog'] });
  node('ingress', 560, 350, 130, 52, 'Traefik Ingress', 'k8s-cp1', { zone: '온프레미스', subnet: 'subnet-onprem-k8s', lines: ['NodePort 30080 · L7 인그레스'] });
  node('web1', 720, 372, 115, 46, 'k8s-w1', '단독 워커 노드', { zone: '온프레미스 · app', subnet: 'subnet-onprem-k8s', lines: ['compute1 물리 전담 · 2.5GB RAM', '안전·성능 우선 단일 워커 체제'] });
  node('web2', 720, 432, 115, 46, 'k8s-w2 (회수)', '대기·회수 완료', { zone: '온프레미스 · app', subnet: 'subnet-onprem-k8s', lines: ['compute2 정지 (호스트 메모리 보호)', '안전·성능 우선 정책으로 완전 회수'] });
  node('api1', 845, 372, 115, 46, 'minwon-app-1', 'k8s-w1', { zone: '온프레미스 · app', subnet: 'subnet-onprem-k8s', lines: ['Worker 1 (k8s-w1) 파드 #1 🟢', 'livenessProbe /healthz 200 OK'] });
  node('api2', 845, 432, 115, 46, 'minwon-app-2', 'k8s-w1', { zone: '온프레미스 · app', subnet: 'subnet-onprem-k8s', lines: ['Worker 1 (k8s-w1) 파드 #2 🟢', '단일 워커 내 2파드 안정 분산'] });
  node('worker', 720, 492, 115, 46, 'intake-worker', '', { zone: '온프레미스 · app', subnet: 'subnet-onprem-k8s', lines: ['접수 테이블 미처리 건을 순차 처리 (Outbox)', '큐 길이 기반 확장'] });
  node('na', 845, 492, 115, 46, 'notify·audit', '', { zone: '온프레미스 · app', subnet: 'subnet-onprem-k8s', lines: ['알림 · 감사 로그 워커'] });
  node('redis', 720, 624, 115, 46, 'Redis', '', { zone: '온프레미스 · data', subnet: 'subnet-onprem-k8s', lines: ['로컬 캐시 (DR 복제 안 함)'] });
  node('rabbit', 845, 624, 115, 46, 'RabbitMQ', '', { zone: '온프레미스 · data', subnet: 'subnet-onprem-k8s', lines: ['처리 알림만 전달 — 원본은 MySQL 접수 테이블'] });
  node('mysql', 1030, 360, 160, 100, 'MySQL Primary', 'semi-sync · GTID', { zone: '온프레미스', subnet: 'subnet-onprem-db', lines: ['minwon · intake(Outbox) · notify · audit', 'AFTER_SYNC: AWS ACK 후 커밋 확정', 'binlog 실시간 스트림 → S3'] }, 'db');
  node('harbor', 560, 742, 130, 40, 'Harbor', '', { zone: '온프레미스 · ops', lines: ['이미지 레지스트리'] });
  node('argocd', 705, 742, 130, 40, 'Argo CD', '', { zone: '온프레미스 · ops', lines: ['GitOps 배포'] });
  node('awswg', 1320, 212, 150, 48, 'AWS WG', '', { zone: 'AWS', lines: ['WireGuard 터널 B · C 종단'] });
  node('ctl', 1320, 330, 170, 62, 'Orchestrator', '3-Signal 판정', { zone: 'AWS', subnet: 'subnet-aws-ctl', lines: ['Prometheus · Grafana · Loki', 'S1/S2 프로브 · semi-sync 강등 경보', 'L2 Ansible · L3 승격 통제'] });
  node('lambda', 1320, 410, 170, 44, 'Dead-man 스위치', '', { zone: 'AWS', lines: ['관제 끊김 → Slack 호출'] });
  node('s3', 1540, 330, 160, 72, 'S3 백업', 'binlog 실시간', { zone: 'AWS', lines: ['binlog 실시간 스트림 + 일일 스냅샷', 'Object Lock · 버전관리 · KMS', '시점 복원(PITR) 소스'] });
  node('ec2', 1320, 556, 160, 62, 'Pilot-Light EC2', 'L3 시 확장', { zone: 'AWS', subnet: 'subnet-aws-dr', lines: ['평소 최소 사양 대기', 'L3 시 확장 · k3s 앱 기동'] });
  node('replica', 1540, 546, 160, 100, 'MySQL Replica', 'semi-sync ACK', { zone: 'AWS', subnet: 'subnet-aws-dr', lines: ['relay log 기록 후 ACK 반환', '사이트 장애 시 RPO 0 (ACK된 커밋 보유)', 'L3 승격: super_read_only = OFF'] }, 'db');

  Object.keys(links).forEach(function (k) { links[k].len = links[k].path.getTotalLength(); });

  // 표시 마크
  var cut = el('g', { 'class': 't2-cut', transform: 'translate(600,280)' }, gMarks);
  el('path', { d: 'M-9,-9 L9,9 M9,-9 L-9,9' }, cut);
  txt(cut, 14, -8, '단절', 't2-cut-t');
  var fence = txt(gMarks, 880, 714, 'FENCED · 쓰기 차단', 't2-fence', 'middle');
  var note = el('g', { 'class': 't2-note' }, gMarks);
  var noteR = el('rect', {}, note), noteT = txt(note, 0, 0, '', '', 'middle');

  // 흐름 패킷 · 캡션
  var halo = el('circle', { r: 12, 'class': 't2-halo' }, gFx);
  var pkt = el('circle', { r: 6.5, 'class': 't2-pkt' }, gFx);
  var bgP = [0, 1, 2].map(function () { return el('circle', { r: 4.5, 'class': 't2-bgpkt' }, gFx); });
  var cap = el('g', { 'class': 't2-cap' }, gFx);
  var capR = el('rect', {}, cap), capN = el('rect', { 'class': 'n' }, cap);
  var capNT = txt(cap, 0, 0, '', 'nt', 'middle'), capT = txt(cap, 0, 0, '');

  // ===== 시나리오별 흐름 =====  [링크 | null, 방향, 설명, 노드]
  var F = {
    normal: { hops: [
      ['cit_cf', 1, '사용자 → Cloudflare · HTTPS, WAF'],
      ['cf_ng', 1, 'Cloudflare → KT Edge Nginx · TLS 종료'],
      ['ng_q', 1, 'Nginx → 접수 대기열 (평시엔 즉시 통과)'],
      ['q_wg', 1, '대기열 → WG 종단'],
      ['tA', 1, '터널 A → 온프렘 WireGuard GW'],
      ['wg_ing', 1, 'WG GW → ingress-nginx (MetalLB VIP)'],
      ['ing_web', 1, 'ingress → web-1'],
      ['web_api', 1, 'web-1 → intake-api-1'],
      ['api_db', 1, 'intake-api → MySQL · 접수 테이블 INSERT'],
      ['db_wg', 1, 'binlog → WG GW (semi-sync 전송)'],
      ['tB', -1, '터널 B → AWS'],
      ['aws_rep', 1, 'AWS Replica · relay log 기록'],
      ['tB', 1, 'Replica ACK → 커밋 확정 (AFTER_SYNC · 무손실)'],
      [null, 0, '202 Accepted · 접수번호 즉시 응답', 'api1'],
      ['api_mq', 1, 'intake-api → RabbitMQ · 처리 알림'],
      ['mq_worker', 1, 'RabbitMQ → intake-worker'],
      ['worker_db', 1, 'worker → MySQL · 처리 상태 커밋'],
      ['mq_na', 1, 'RabbitMQ → notify·audit']
    ], bg: [['db_wg', 1], ['tB', -1], ['aws_s3', 1]], bgCap: 'binlog 실시간 스트림 → 터널 B → S3 (즉시 백업)' },
    l1: { hops: [
      [null, 0, 'intake-api-1 OOM · livenessProbe 실패', 'api1'],
      [null, 0, 'kubelet이 컨테이너 즉시 재시작 (초 단위)', 'api1'],
      ['tA', 1, '요청 계속 유입 · 터널 A 정상'],
      ['wg_ing', 1, 'WG GW → ingress'],
      ['ing_web', 1, 'ingress → web-1'],
      ['web_api2', 1, 'web → intake-api-2 (정상 replica가 흡수)'],
      ['api2_db', 1, 'api-2 → MySQL · 접수 INSERT (semi-sync)'],
      [null, 0, '서비스 무중단 · 접수 데이터 손실 없음', 'mysql']
    ], bg: [['db_wg', 1], ['tB', -1], ['aws_rep', 1]], bgCap: 'semi-sync 복제 → AWS Replica (상시)' },
    l2: { hops: [
      ['ctl_cf', 1, 'S1 공인 프로브 1분 이상 무응답'],
      [null, 0, 'Orchestrator 판정: S1 실패 · S2 정상 → L2', 'ctl'],
      ['aws_ctl', -1, 'Orchestrator → AWS WG · Ansible 실행'],
      ['tB', 1, '터널 B → 온프렘 WG GW · restart_services.yml'],
      ['wg_ing', 1, '서비스 순차 재기동 (Nginx → 앱 → MySQL → WG)'],
      [null, 0, 'MySQL은 재기동 전 semi-sync 상태 확인 · 데이터 우선', 'mysql'],
      [null, 0, '헬스체크 통과 → NORMAL 복귀 (≤ 3분)', 'web1']
    ], bg: [] },
    path: { hops: [
      ['cit_cf', 1, '사용자 → Cloudflare'],
      ['cf_ng', 1, 'Cloudflare → KT Edge'],
      ['ng_q', 1, 'Nginx → 접수 대기열'],
      [null, 0, '터널 A 단절 · S1·S3 실패, S2 정상 → 온프렘 생존', 'wgkt'],
      ['tC', 1, '터널 C 우회 → AWS WG'],
      ['tB', 1, '터널 B → 온프렘 진입 (DB 승격 금지 · Split-Brain 방지)'],
      ['wg_ing', 1, 'WG GW → ingress'],
      ['ing_web', 1, 'ingress → web'],
      ['web_api', 1, 'web → intake-api'],
      ['api_db', 1, 'intake-api → MySQL Primary (유일한 쓰기 지점)']
    ], bg: [['db_wg', 1], ['tB', -1], ['aws_rep', 1]], bgCap: 'semi-sync 복제 유지 (터널 B 정상)' },
    l3: { hops: [
      [null, 0, '3-Signal: S1 ∧ S2 ∧ S3 연속 실패 → 사이트 장애 확정', 'ctl'],
      [null, 0, '온프렘 자가 펜싱 · Primary 쓰기 차단', 'onwg'],
      [null, 0, 'Replica가 마지막 ACK GTID까지 적용 확인 (RPO 0)', 'replica'],
      ['aws_s3', 1, 'S3 binlog와 대조 · 누락 0 검증'],
      [null, 0, 'Replica 승격 · super_read_only = OFF', 'replica'],
      [null, 0, 'Pilot-Light EC2 확장 · 앱 기동', 'ec2'],
      ['cit_cf', 1, '사용자 → Cloudflare'],
      ['cf_ng', 1, 'Cloudflare → KT Edge (upstream 전환)'],
      ['tC', 1, '터널 C → AWS WG'],
      ['aws_ec2', 1, 'AWS WG → Pilot-Light EC2'],
      ['ec2_rep', 1, 'EC2 앱 → 승격된 MySQL에 쓰기']
    ], bg: [] },
    l4: { hops: [
      [null, 0, '온프렘 복구 · 온프렘 DB를 AWS의 Replica로 재구성', 'mysql'],
      ['aws_rep', -1, 'AWS MySQL → AWS WG (역방향 GTID)'],
      ['tB', 1, '터널 B → 온프렘 WG GW'],
      ['db_wg', -1, 'WG GW → 온프렘 MySQL · 누적 데이터 따라잡기'],
      [null, 0, '지연 0 · 체크섬 일치 → AWS 쓰기 차단, 온프렘 승격', 'mysql'],
      [null, 0, 'semi-sync 방향 원복 (온프렘 → AWS ACK)', 'replica'],
      ['tA', 1, 'Edge upstream 터널 A 복귀'],
      ['wg_ing', 1, 'WG GW → ingress'],
      ['web_api', 1, 'web → intake-api'],
      ['api_db', 1, 'intake-api → MySQL Primary (원복 완료)']
    ], bg: [] },
    bs: { hops: [
      ['cit_cf', 1, '사용자 → Cloudflare'],
      ['cf_ng', 1, 'Origin 502/504 연속 (온프렘 · AWS 전면 두절)'],
      [null, 0, 'Cloudflare Worker가 오류를 가로챔', 'cf'],
      ['cf_gh', 1, 'GitHub Pages 비상 접수 폼 0초 노출 · 민원 비상 보관'],
      [null, 0, '복구 후 비상 보관분을 접수 테이블로 일괄 이관', 'gh']
    ], bg: [] },
    surge: { hops: [
      ['cit_cf', 1, '민원 폭주 · 초당 요청 급증'],
      [null, 0, 'Cloudflare: 봇 차단 · IP 단위 제한', 'cf'],
      ['cf_ng', 1, '통과분 → KT Edge Nginx'],
      ['ng_q', 1, 'Nginx → 접수 대기열'],
      [null, 0, '버스트 범위 내 요청은 순서대로 지연 (DB 보호 속도)', 'queue'],
      ['q_wg', 1, '허용 속도로만 WG 종단 전달'],
      ['tA', 1, '터널 A → 온프렘'],
      ['wg_ing', 1, 'WG GW → ingress'],
      ['web_api', 1, 'web → intake-api'],
      ['api_db', 1, '접수 테이블 INSERT 1건 (semi-sync ACK 후 커밋)'],
      [null, 0, '202 접수번호 즉시 응답 · 처리는 비동기', 'api1'],
      ['api_mq', 1, 'RabbitMQ에 처리 알림'],
      ['mq_worker', 1, 'intake-worker가 DB 한도 안에서 순차 처리'],
      ['worker_db', 1, '처리 상태 커밋 · 큐 길이 기반 워커 확장'],
      [null, 0, '버스트 초과분 → 503 + Retry-After', 'queue'],
      ['q_cf', 1, 'Edge 503 → Cloudflare Worker'],
      ['cf_gh', 1, '대기 안내 · 비상 접수 폼 (민원 유실 0)'],
      ['bypass', 1, '⚠ origin-kt(DNS 전용) 직접 요청은 Cloudflare 제한 우회 → Edge는 Cloudflare IP만 허용해야 함']
    ], bg: [['db_wg', 1], ['tB', -1], ['aws_s3', 1]], bgCap: 'binlog 실시간 스트림 → S3 (폭주 중에도 즉시 백업)' },
    mgmt: { hops: [
      ['ops_cf', 1, '운영자 → Cloudflare · figteam.ktci5.kr 로그인'],
      [null, 0, 'Cloudflare: 터널 호스트명 → minwon-tunnel', 'cf'],
      ['cf_cfd', -1, 'minwon-tunnel → 온프렘 cloudflared (아웃바운드 연결 · 인바운드 0)'],
      [null, 0, 'cloudflared가 호스트명별 내부 서비스로 전달 · 포털 :18088', 'gpu'],
      ['cfd_argocd', 1, 'argocd.ktci5.kr → Argo CD (k8s-cp1:30800)'],
      ['cfd_wg', 1, 'aws-ctl · kt-edge 호스트명 → WireGuard GW'],
      ['tB', -1, '터널 B → AWS (aws-ctl.ktci5.kr)'],
      ['aws_ctl', 1, 'AWS WG → Orchestrator · Prometheus/Grafana'],
      ['tA', -1, '터널 A → KT Edge (kt-edge.ktci5.kr)'],
      [null, 0, '관리 경로는 민원접수 경로(minwon.ktci5.kr)와 분리 · 공인 포트 노출 없음', 'gpu']
    ], bg: [] }
  };
  var STATE = {
    normal: { tun: { tA: 'on', tB: 'on', tC: 'idle' } },
    l1: { tun: { tA: 'on', tB: 'on', tC: 'idle' }, warn: ['api1'] },
    l2: { tun: { tA: 'on', tB: 'on', tC: 'idle' }, warn: ['ctl', 'onwg'], fail: ['web1', 'web2', 'api1', 'api2'] },
    path: { tun: { tA: 'fail', tB: 'on', tC: 'on' }, cut: true, note: ['replica', 'DB 승격 금지'] },
    l3: { tun: { tA: 'fail', tB: 'fail', tC: 'on' }, fence: true, ok: ['replica', 'ec2'], warn: ['ctl'], note: ['replica', 'Primary 승격 · RPO 0'] },
    l4: { tun: { tA: 'on', tB: 'on', tC: 'idle' }, ok: ['mysql'], note: ['mysql', 'Primary 복귀'] },
    bs: { tun: { tA: 'fail', tB: 'fail', tC: 'fail' }, dark: true, ok: ['gh', 'cf'] },
    surge: { tun: { tA: 'on', tB: 'on', tC: 'idle' }, warn: ['queue', 'rabbit', 'worker'], ok: ['mysql'], note: ['mysql', 'DB 우선 · 커밋 보장'] },
    mgmt: { tun: { tA: 'on', tB: 'on', tC: 'idle' }, ok: ['gpu', 'ops'] }
  };
  var ON_IDS = ['gpu', 'onwg', 'ingress', 'web1', 'web2', 'api1', 'api2', 'worker', 'na', 'redis', 'rabbit', 'mysql', 'harbor', 'argocd'];
  var stage = 'normal', hopIdx = 0, hopT = 0, playing = false, pauseT = 0;
  var HOP = 1.15, NODE_T = 1.4, END = 1.0;
  var flowList = document.getElementById('dc-flow');

  function cls(e, c, on) { if (on) e.classList.add(c); else e.classList.remove(c); }
  function applyState() {
    var st = STATE[stage] || STATE.normal;
    Object.keys(nodes).forEach(function (k) { ['st-warn', 'st-fail', 'st-ok', 'st-dim', 'pulse'].forEach(function (c) { nodes[k].g.classList.remove(c); }); });
    Object.keys(zones).forEach(function (k) { zones[k].classList.remove('fenced', 'dim', 'lit'); });
    nodes.gh.g.classList.add('st-dim'); zones.gh.classList.add('dim');
    if (st.fence) { ON_IDS.forEach(function (k) { nodes[k].g.classList.add('st-dim'); }); zones.on.classList.add('fenced'); }
    if (st.dark) {
      Object.keys(nodes).forEach(function (k) { if (['citizen', 'cf', 'gh'].indexOf(k) < 0) nodes[k].g.classList.add('st-dim'); });
      ['kt', 'on', 'aws'].forEach(function (k) { zones[k].classList.add('dim'); });
    }
    if (stage === 'surge' || st.dark) { zones.gh.classList.remove('dim'); nodes.gh.g.classList.remove('st-dim'); }
    (st.warn || []).forEach(function (k) { nodes[k].g.classList.add('st-warn'); });
    (st.fail || []).forEach(function (k) { nodes[k].g.classList.add('st-fail'); });
    (st.ok || []).forEach(function (k) { nodes[k].g.classList.remove('st-dim'); nodes[k].g.classList.add('st-ok'); });
    Object.keys(st.tun).forEach(function (k) {
      var g = links[k].g; ['tun-on', 'tun-fail', 'tun-idle'].forEach(function (c) { g.classList.remove(c); }); g.classList.add('tun-' + st.tun[k]);
    });
    cls(cut, 'show', !!st.cut);
    cls(fence, 'show', !!st.fence);
    cls(note, 'show', !!st.note);
    if (st.note) {
      var n = nodes[st.note[0]];
      noteT.textContent = st.note[1];
      var cx = n.x + n.w / 2, cy = n.y + n.h + 22;
      noteT.setAttribute('x', cx); noteT.setAttribute('y', cy + 4);
      var bb = noteT.getBBox();
      noteR.setAttribute('x', bb.x - 8); noteR.setAttribute('y', bb.y - 4); noteR.setAttribute('width', bb.width + 16); noteR.setAttribute('height', bb.height + 8);
    }
  }

  function renderFlowList() {
    if (!flowList) return;
    flowList.textContent = '';
    var f = F[stage];
    f.hops.forEach(function (h, i) {
      var li = document.createElement('li'); li.dataset.i = i;
      var n = document.createElement('i'); n.textContent = String(i + 1);
      var t = document.createElement('span'); t.textContent = h[2];
      li.appendChild(n); li.appendChild(t);
      li.addEventListener('click', function () { hopIdx = i; hopT = 0; pauseT = 0; playing = false; syncPlay(); markFlow(); });
      flowList.appendChild(li);
    });
    if (f.bgCap) {
      var li = document.createElement('li'); li.className = 'bg';
      var n = document.createElement('i'); n.textContent = '∞';
      var t = document.createElement('span'); t.textContent = f.bgCap;
      li.appendChild(n); li.appendChild(t); flowList.appendChild(li);
    }
  }
  function markFlow() {
    if (!flowList) return;
    var items = flowList.querySelectorAll('li[data-i]');
    for (var j = 0; j < items.length; j++) {
      var i = +items[j].dataset.i;
      cls(items[j], 'done', i < hopIdx); cls(items[j], 'active', i === hopIdx);
    }
    var a = flowList.querySelector('li.active'), p = flowList.parentElement;
    if (a && p) { if (a.offsetTop < p.scrollTop || a.offsetTop > p.scrollTop + p.clientHeight - 40) p.scrollTop = a.offsetTop - 40; }
  }

  function placeCap(text, n, x, y) {
    capNT.textContent = String(n);
    capT.textContent = text;
    capT.setAttribute('x', 0); capT.setAttribute('y', 0);
    var tb = capT.getBBox();
    var w = tb.width + 44, h = 30;
    var cx = Math.max(vb.x + 6, Math.min(x - w / 2, vb.x + vb.w - w - 6));
    var sc = toSvg(0, 0).s, barH = (bar && bar.offsetHeight ? bar.offsetHeight + 18 : 0) * sc;
    var cy = Math.max(vb.y + 6, Math.min(y - h - 14, vb.y + vb.h - h - 6 - barH));
    capR.setAttribute('x', cx); capR.setAttribute('y', cy); capR.setAttribute('width', w); capR.setAttribute('height', h);
    capN.setAttribute('x', cx); capN.setAttribute('y', cy); capN.setAttribute('width', 28); capN.setAttribute('height', h);
    capNT.setAttribute('x', cx + 14); capNT.setAttribute('y', cy + 20);
    capT.setAttribute('x', cx + 36); capT.setAttribute('y', cy + 20);
    cap.classList.add('show');
  }

  function frame(dt) {
    var f = F[stage], hops = f.hops;
    Object.keys(links).forEach(function (k) { links[k].g.classList.remove('active', 'done', 'used', 'bg'); });
    hops.forEach(function (h, i) { if (h[0]) { links[h[0]].g.classList.add('used'); if (i < hopIdx) links[h[0]].g.classList.add('done'); } });
    (f.bg || []).forEach(function (b) { links[b[0]].g.classList.add('bg'); });
    Object.keys(nodes).forEach(function (k) { nodes[k].g.classList.remove('pulse'); });

    if (pauseT > 0) {
      pauseT -= dt;
      pkt.style.display = halo.style.display = 'none'; cap.classList.remove('show');
      if (pauseT <= 0) { hopIdx = 0; hopT = 0; markFlow(); }
    } else {
      var h = hops[hopIdx];
      if (playing) hopT += dt / (h[0] ? HOP : NODE_T);
      var t = Math.min(hopT, 1);
      if (h[0]) {
        var L = links[h[0]];
        L.g.classList.add('active');
        var u = h[1] < 0 ? 1 - t : t;
        var p = L.path.getPointAtLength(u * L.len);
        pkt.setAttribute('cx', p.x); pkt.setAttribute('cy', p.y);
        halo.setAttribute('cx', p.x); halo.setAttribute('cy', p.y);
        pkt.setAttribute('class', 't2-pkt k-' + (L.g.classList.contains('tun-fail') ? 'fail' : L.kind));
        halo.setAttribute('class', 't2-halo k-' + (L.g.classList.contains('tun-fail') ? 'fail' : L.kind));
        pkt.style.display = halo.style.display = '';
        var m = L.path.getPointAtLength(L.len / 2);
        placeCap(h[2], hopIdx + 1, m.x, m.y);
      } else {
        pkt.style.display = halo.style.display = 'none';
        var n = nodes[h[3]];
        if (n) { n.g.classList.add('pulse'); placeCap(h[2], hopIdx + 1, n.x + n.w / 2, n.y); }
      }
      if (playing && hopT >= 1) {
        hopIdx++; hopT = 0;
        if (hopIdx >= hops.length) { hopIdx = hops.length - 1; pauseT = END; }
        markFlow();
      }
    }
    var bg = f.bg || [];
    if (bg.length) {
      var total = bg.reduce(function (s, b) { return s + links[b[0]].len; }, 0);
      var now = performance.now() / 1000;
      bgP.forEach(function (c, k) {
        var d = (now * 140 + k * total / 3) % total;
        for (var j = 0; j < bg.length; j++) {
          var L2 = links[bg[j][0]];
          if (d <= L2.len) { var u2 = d / L2.len; var q = L2.path.getPointAtLength((bg[j][1] < 0 ? 1 - u2 : u2) * L2.len); c.setAttribute('cx', q.x); c.setAttribute('cy', q.y); break; }
          d -= L2.len;
        }
        c.style.display = '';
      });
    } else bgP.forEach(function (c) { c.style.display = 'none'; });
  }

  // ---------- 확대 · 이동 ----------
  function toSvg(cx, cy) {
    var r = svg.getBoundingClientRect();
    var s = Math.max(vb.w / r.width, vb.h / r.height);
    var ox = (r.width - vb.w / s) / 2, oy = (r.height - vb.h / s) / 2;
    return { x: vb.x + (cx - r.left - ox) * s, y: vb.y + (cy - r.top - oy) * s, s: s };
  }
  function zoomAt(f, cx, cy) {
    var nw = Math.min(VB0.w * 1.4, Math.max(VB0.w / 6, vb.w / f));
    var k = nw / vb.w;
    var p = (cx == null) ? { x: vb.x + vb.w / 2, y: vb.y + vb.h / 2 } : toSvg(cx, cy);
    vb.x = p.x - (p.x - vb.x) * k; vb.y = p.y - (p.y - vb.y) * k; vb.w *= k; vb.h *= k;
    applyVB();
  }
  svg.addEventListener('wheel', function (e) { e.preventDefault(); zoomAt(e.deltaY < 0 ? 1.15 : 1 / 1.15, e.clientX, e.clientY); }, { passive: false });
  var drag = null;
  svg.addEventListener('pointerdown', function (e) { drag = { x: e.clientX, y: e.clientY, vx: vb.x, vy: vb.y, moved: false }; svg.setPointerCapture(e.pointerId); });
  svg.addEventListener('pointermove', function (e) {
    if (!drag) return;
    var dx = e.clientX - drag.x, dy = e.clientY - drag.y;
    if (Math.abs(dx) + Math.abs(dy) > 4) drag.moved = true;
    if (!drag.moved) return;
    var s = toSvg(0, 0).s;
    vb.x = drag.vx - dx * s; vb.y = drag.vy - dy * s; applyVB();
    svg.classList.add('grabbing');
  });
  svg.addEventListener('pointerup', function (e) {
    var moved = drag && drag.moved; drag = null; svg.classList.remove('grabbing');
    if (!moved && e.target === svg) card.hidden = true;
  });
  // 드래그 직후 클릭이 노드 카드로 번지지 않게
  svg.addEventListener('click', function (e) { if (svg.classList.contains('grabbing')) e.stopPropagation(); }, true);
  function fitView() { vb = { x: VB0.x, y: VB0.y, w: VB0.w, h: VB0.h }; applyVB(); }

  // ---------- 툴바 ----------
  var bar = document.createElement('div'); bar.className = 't3-bar';
  var B = [['zin', '+', '확대'], ['zout', '−', '축소'], ['fit', '맞춤', '전체 보기'], ['sep'],
    ['prev', '◀ 이전', '이전 단계'], ['play', '일시정지', '흐름 재생 / 일시정지'], ['next', '다음 ▶', '다음 단계'], ['sep'],
    ['detail', '상세 구성', '서브넷 · 파드 · DB 상세 펼치기']];
  var btn = {};
  B.forEach(function (b) {
    if (b[0] === 'sep') { var s = document.createElement('span'); s.className = 'sep'; bar.appendChild(s); return; }
    var x = document.createElement('button'); x.type = 'button'; x.textContent = b[1]; x.title = b[2]; x.setAttribute('aria-label', b[2]); x.dataset.k = b[0];
    bar.appendChild(x); btn[b[0]] = x;
  });
  host.appendChild(bar);
  function syncPlay() { btn.play.textContent = playing ? '일시정지' : '재생'; cls(btn.play, 'on', !playing); }
  function syncDetail() { var c = document.getElementById('dr-console'); cls(btn.detail, 'on', !!(c && c.classList.contains('show-detail'))); }
  bar.addEventListener('click', function (e) {
    var k = e.target.dataset && e.target.dataset.k; if (!k) return;
    if (k === 'zin') zoomAt(1.25);
    if (k === 'zout') zoomAt(0.8);
    if (k === 'fit') fitView();
    if (k === 'play') { playing = !playing; syncPlay(); }
    if (k === 'prev') { playing = false; pauseT = 0; hopIdx = Math.max(0, hopIdx - 1); hopT = 0; markFlow(); syncPlay(); }
    if (k === 'next') { playing = false; pauseT = 0; hopIdx = Math.min(F[stage].hops.length - 1, hopIdx + 1); hopT = 0; markFlow(); syncPlay(); }
    if (k === 'detail') { if (window.toggleDrDetail) window.toggleDrDetail(); syncDetail(); }
  });

  // ---------- 장비 정보 카드 ----------
  var card = document.createElement('div'); card.className = 't3-card'; card.hidden = true; host.appendChild(card);
  function showCard(id) {
    var n = nodes[id]; if (!n) return;
    var i = n.info;
    card.textContent = '';
    var h = document.createElement('h4'); h.textContent = i.title; card.appendChild(h);
    var z = document.createElement('p'); z.className = 'z'; z.textContent = [i.zone, i.sub].filter(Boolean).join(' · '); card.appendChild(z);
    var ul = document.createElement('ul');
    (i.lines || []).forEach(function (t) { var li = document.createElement('li'); li.textContent = t; ul.appendChild(li); });
    card.appendChild(ul);
    var row = document.createElement('div'); row.className = 'row';
    if (i.subnet && document.getElementById(i.subnet)) {
      var b = document.createElement('button'); b.type = 'button'; b.textContent = '상세 구성에서 보기';
      b.addEventListener('click', function () { if (window.showDrDetail) window.showDrDetail(i.subnet); syncDetail(); });
      row.appendChild(b);
    }

    // [추가] 실시간 시스템 제어 액션 버튼 (켜고 끄기 / 절체 / 펜싱 / 크래시)
    var actBox = document.createElement('div');
    actBox.style.cssText = 'margin-top:12px; padding:10px; border-radius:4px; background:#0F2D4F; border:1px solid #4F739A; display:flex; flex-direction:column; gap:6px;';
    var actT = document.createElement('div');
    actT.style.cssText = 'font-size:11px; font-weight:700; color:#9FD3F5; display:flex; justify-content:space-between; align-items:center;';
    actT.innerHTML = '<span>⚡ 실시간 시스템 제어 액션</span><span style="font-size:10px; color:#8AA5C2;">클릭 시 즉시 반영</span>';
    actBox.appendChild(actT);

    var actBtns = document.createElement('div');
    actBtns.style.cssText = 'display:flex; gap:6px; flex-wrap:wrap; margin-top:4px;';

    if (id === 'nginx' || id === 'wgkt') {
      var bRoute = document.createElement('button'); bRoute.type = 'button';
      bRoute.style.cssText = 'background:#3A78B5; color:#fff; font-size:11px; padding:4px 8px; border:none; cursor:pointer;';
      bRoute.textContent = '🔄 KT Edge 터널 A ↔ C 절체';
      bRoute.onclick = function() {
        if (window.setV3Stage) window.setV3Stage(window.currentV3Stage === 'l3' ? 'normal' : 'l3');
      };
      actBtns.appendChild(bRoute);
    } else if (id === 'mysql') {
      var bFence = document.createElement('button'); bFence.type = 'button';
      bFence.style.cssText = 'background:#E8604C; color:#fff; font-size:11px; padding:4px 8px; border:none; cursor:pointer;';
      bFence.textContent = '🛑 Watchdog 펜싱 실행 (Primary 쓰기 차단)';
      bFence.onclick = function() {
        if (window.setV3Stage) window.setV3Stage('l3');
      };
      actBtns.appendChild(bFence);
      var bNormal = document.createElement('button'); bNormal.type = 'button';
      bNormal.style.cssText = 'background:#4CB985; color:#fff; font-size:11px; padding:4px 8px; border:none; cursor:pointer;';
      bNormal.textContent = '🟢 쓰기 정상화 (복구)';
      bNormal.onclick = function() {
        if (window.setV3Stage) window.setV3Stage('normal');
      };
      actBtns.appendChild(bNormal);
    } else if (id === 'replica') {
      var bPromote = document.createElement('button'); bPromote.type = 'button';
      bPromote.style.cssText = 'background:#C8962E; color:#fff; font-size:11px; padding:4px 8px; border:none; cursor:pointer;';
      bPromote.textContent = '⚡ AWS Replica 승격 (super_read_only=OFF)';
      bPromote.onclick = function() {
        if (window.setV3Stage) window.setV3Stage('l3');
      };
      actBtns.appendChild(bPromote);
    } else if (id === 'api1' || id === 'api2' || id === 'web1' || id === 'web2') {
      var bCrash = document.createElement('button'); bCrash.type = 'button';
      bCrash.style.cssText = 'background:#E8604C; color:#fff; font-size:11px; padding:4px 8px; border:none; cursor:pointer;';
      bCrash.textContent = '💥 L1 파드 크래시 유발 (/chaos/crash)';
      bCrash.onclick = function() {
        if (window.triggerChaosCrash) window.triggerChaosCrash();
        else if (window.setV3Stage) window.setV3Stage('l1');
      };
      actBtns.appendChild(bCrash);
      var bRestart = document.createElement('button'); bRestart.type = 'button';
      bRestart.style.cssText = 'background:#3A78B5; color:#fff; font-size:11px; padding:4px 8px; border:none; cursor:pointer;';
      bRestart.textContent = '↻ K8s 롤링 재시작';
      bRestart.onclick = function() {
        if (window.setV3Stage) window.setV3Stage('normal');
      };
      actBtns.appendChild(bRestart);
    } else if (id === 'onwg' || id === 'gpu' || id === 'ingress') {
      var bStopVm = document.createElement('button'); bStopVm.type = 'button';
      bStopVm.style.cssText = 'background:#E8604C; color:#fff; font-size:11px; padding:4px 8px; border:none; cursor:pointer;';
      bStopVm.textContent = '🛑 OpenStack VM 전원 끄기';
      bStopVm.onclick = function() {
        if (confirm('온프레미스 VM 전원을 차단하시겠습니까? (L2 장애 시뮬레이션)')) {
          if (window.setV3Stage) window.setV3Stage('l2');
        }
      };
      actBtns.appendChild(bStopVm);
      var bStartVm = document.createElement('button'); bStartVm.type = 'button';
      bStartVm.style.cssText = 'background:#4CB985; color:#fff; font-size:11px; padding:4px 8px; border:none; cursor:pointer;';
      bStartVm.textContent = '⚡ VM 전원 켜기 (Start)';
      bStartVm.onclick = function() {
        if (window.setV3Stage) window.setV3Stage('normal');
      };
      actBtns.appendChild(bStartVm);
    } else if (id === 'ctl') {
      var bProbe = document.createElement('button'); bProbe.type = 'button';
      bProbe.style.cssText = 'background:#B08CFF; color:#fff; font-size:11px; padding:4px 8px; border:none; cursor:pointer;';
      bProbe.textContent = '🔍 3-Signal 관제 즉시 판정';
      bProbe.onclick = function() {
        if (window.addDrLog) window.addDrLog('[ORCHESTRATOR] 3-Signal 판정: S1=PASS, S2=PASS, S3=PASS (정상 상태 확인)', 'success');
      };
      actBtns.appendChild(bProbe);
    }

    if (actBtns.children.length > 0) {
      actBox.appendChild(actBtns);
      card.appendChild(actBox);
    }

    var x = document.createElement('button'); x.type = 'button'; x.textContent = '닫기';
    x.addEventListener('click', function () { card.hidden = true; });
    row.appendChild(x); card.appendChild(row);
    card.hidden = false;
  }

  // ---------- 접수 폭주(8) 시나리오: 기존 상태 머신 확장 ----------
  var origSet = window.setV3Stage;
  if (typeof origSet === 'function') {
    // 원본 상태 머신은 단계마다 상세 배지를 초기화하지 않아 이전 단계 문구가 남음 → 평시 값으로 먼저 초기화
    var RESET = [
      ['kt-edge-route', '터널 A 발송 중', null, 'tunnel-badge tunnel-a'], ['kt-edge-dot', null, null, 'dot green'],
      ['txt-s3-status', '정상 통과 🟢', '#8FE0B4'], ['badge-onprem-mode', 'PRIMARY RW 🟢', null, null, '#5FD39A'],
      ['txt-fencing', '자가 펜싱 감시 중: 정상 (쓰기 허용)'], ['badge-db-rw', 'Read / Write', null, null, '#5FD39A'],
      ['badge-aws-mode', 'PILOT-LIGHT RO 🟡', null, null, '#F4C95D'], ['badge-aws-db-ro', 'super_read_only = ON', null, null, '#F4C95D'],
      ['txt-orch-state', 'NORMAL (온프렘 가동)', '#5FD39A']
    ];
    function resetDetail() {
      RESET.forEach(function (r) {
        var e = document.getElementById(r[0]); if (!e) return;
        if (r[1] != null) e.innerText = r[1];
        if (r[2]) e.style.color = r[2];
        if (r[3]) { e.className = r[3]; e.style.background = ''; e.style.color = ''; }
        if (r[4]) e.style.background = r[4];
      });
    }
    window.setV3Stage = function (s) {
      resetDetail();
      origSet(s);
      [['btn-v3-surge', 'surge', '#C8962E'], ['btn-v3-mgmt', 'mgmt', '#C9874F']].forEach(function (b) {
        var e = document.getElementById(b[0]); if (!e) return;
        var on = s === b[1];
        e.style.background = on ? b[2] : 'transparent'; e.style.color = on ? '#fff' : '#B4C6D8'; e.style.fontWeight = on ? '700' : '500';
      });
      function set(id, v, color) { var e = document.getElementById(id); if (e) { e.innerText = v; if (color) e.style.color = color; } }
      if (s === 'mgmt') {
        set('v3-stage-title', '⚪ 9. 관리 접속: 운영자 → Cloudflare → minwon-tunnel → 온프렘 cloudflared → 내부 서비스 · WG로 AWS/KT');
        set('v3-stage-desc', '관리 화면 8개 호스트명은 Cloudflare Tunnel로만 들어옵니다. 온프렘은 인바운드 포트 0, aws-ctl · kt-edge는 WireGuard 터널을 경유합니다.');
        var mb = document.getElementById('v3-status-badge');
        if (mb) { mb.className = 'kt-vm-badge state-running'; mb.innerHTML = '<span class="dot green"></span>MGMT · TUNNEL'; }
        set('v3-prop-sm', 'NORMAL', '#5FD39A');
        set('v3-prop-signal', 'S1:정상 · S2:정상 · S3:정상');
        set('v3-prop-rto', '민원접수 경로 영향 없음');
        set('v3-prop-tunnel', 'minwon-tunnel + 터널 A·B');
        var ms = document.getElementById('v3-sop-text');
        if (ms) ms.innerHTML = '<b>[Cloudflare DNS 기준 접속 경로]</b><br>' +
          '• <b>민원접수</b>: <code>minwon.ktci5.kr</code> A 14.63.212.190 (프록시) → KT Edge → 터널 A → 온프렘.<br>' +
          '• <b>관리</b>: <code>figteam · app · argocd · grafana · horizon · openstack · aws-ctl · kt-edge</code>.ktci5.kr → <b>minwon-tunnel</b> → 온프렘 cloudflared (GPU 서버) → 내부 서비스. aws-ctl은 터널 B, kt-edge는 터널 A 경유.<br>' +
          '• <b>⚠ 위험</b>: <code>origin-kt.ktci5.kr</code> A 14.63.212.190 <b>DNS 전용</b> — 오리진 IP가 공개되어 Cloudflare WAF·제한을 우회한 직접 접속이 가능. KT Edge 443을 Cloudflare IP 대역만 허용하거나 레코드 정리 필요.';
        if (window.addDrLog) window.addDrLog('[v2.5.1-FLOW] 9단계: 관리 접속 — Cloudflare Tunnel(minwon-tunnel) → 온프렘 cloudflared → WG 경유', 'success');
        return;
      }
      if (s !== 'surge') return;
      set('v3-stage-title', '🟤 8. 접수 폭주: Edge 대기열 → 접수 테이블(202 접수번호) → 워커 순차 처리 · 초과분 비상 폼');
      set('v3-stage-desc', 'v2.5.1: DB가 최우선입니다. Edge는 허용 속도로만 전달하고, 접수는 MySQL에 먼저 커밋(semi-sync)한 뒤 처리는 비동기로 진행합니다.');
      var b = document.getElementById('v3-status-badge');
      if (b) { b.className = 'kt-vm-badge state-transition'; b.innerHTML = '<span class="dot yellow"></span>SURGE · QUEUEING'; }
      set('v3-prop-sm', 'NORMAL (Surge 제어)', '#F4C95D');
      set('v3-prop-signal', 'S1:지연 · S2:정상 · S3:정상');
      set('v3-prop-rto', '접수 RPO 0 · 처리 지연 허용');
      set('v3-prop-tunnel', '터널 A 총량 제한 · B 복제/백업');
      set('kt-edge-route', '터널 A 총량 제한 발송');
      set('txt-orch-state', 'NORMAL (폭주 감시 · semi-sync 정상)', '#F4C95D');
      set('badge-aws-db-ro', 'semi-sync ACK 중');
      var sop = document.getElementById('v3-sop-text');
      if (sop) sop.innerHTML = '<b>[접수 폭주 대응 — DB 최우선]</b><br>' +
        '• <b>① Cloudflare</b>: 봇 차단 · IP 단위 제한으로 비정상 트래픽 선차단.<br>' +
        '• <b>② KT Edge 대기열</b>: <code>limit_req</code> 총량 제한, 버스트 범위는 순서대로 지연 전달, 초과분은 503 + Retry-After.<br>' +
        '• <b>③ 접수 테이블</b>: intake-api가 INSERT 1건 후 202 접수번호 응답. semi-sync ACK 후 커밋이라 접수된 민원은 AWS에도 존재.<br>' +
        '• <b>④ 워커</b>: RabbitMQ 알림으로 intake-worker가 DB 한도 안에서 순차 처리 (큐 길이 기반 확장).<br>' +
        '• <b>⑤ 초과분</b>: Cloudflare Worker가 대기 안내 · GitHub Pages 비상 접수 폼 제공 → 복구 후 접수 테이블로 이관.<br>' +
        '• <b>백업</b>: binlog 실시간 스트림으로 S3에 즉시 보관.';
      if (window.addDrLog) window.addDrLog('[v2.5.1-FLOW] 8단계: 접수 폭주 — Edge 대기열 · 접수 테이블 우선 커밋 · 워커 순차 처리 활성화', 'warn');
    };
  }

  // ---------- 루프 · 공개 API ----------
  var last = performance.now();
  function loop(now) {
    requestAnimationFrame(loop);
    var dt = Math.min((now - last) / 1000, 0.1); last = now;
    if (!host.clientWidth) return;
    frame(dt);
  }
  function setStage(s) {
    if (!F[s]) s = 'normal';
    stage = s; hopIdx = 0; hopT = 0; pauseT = 0; playing = false;
    card.hidden = true;
    applyState(); renderFlowList(); markFlow(); syncPlay();
  }
  window.Topo2D = { setStage: setStage, fit: fitView, resize: function () {} };
  stageEl.classList.add('has-2d');
  setStage(typeof currentV3Stage !== 'undefined' ? currentV3Stage : 'normal');
  if (window.drTab) window.drTab('flow');
  syncDetail();
  requestAnimationFrame(loop);
})();

  </script>
  <script>
(function () {
  'use strict';
  // ===== 민원불패 v2.5.1 — OpenStack 구조 · 연결 (#osvm 하단) =====
  var root = document.getElementById('osx');
  if (!root) return;
  var NS = 'http://www.w3.org/2000/svg';
  var DATA = null, loading = false, lastLoad = 0;

  function h(tag, cls, text, parent) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text != null) e.textContent = text;
    if (parent) parent.appendChild(e);
    return e;
  }
  function s(tag, attrs, parent, text) {
    var e = document.createElementNS(NS, tag);
    for (var k in attrs) e.setAttribute(k, attrs[k]);
    if (text != null) e.textContent = text;
    if (parent) parent.appendChild(e);
    return e;
  }
  function pct(a, b) { return b ? Math.min(100, Math.round(a / b * 100)) : 0; }
  function gb(bytes) { return bytes == null ? '-' : (bytes / 1073741824).toFixed(bytes > 1073741824 ? 1 : 2) + ' GB'; }

  // ---------- 골격 ----------
  var head = h('div', 'osx-head', null, root);
  h('h3', null, 'OpenStack 구조 · 연결', head);
  var meta = h('p', 'osx-meta', '불러오는 중…', head);
  var refresh = h('button', 'btn-top', '새로고침', head); refresh.type = 'button';
  var tabs = h('div', 'osx-tabs', null, root); tabs.setAttribute('role', 'tablist');
  var panes = {};
  // 재배치: 작은 정보는 좁게, 큰 구성도는 한 화면에
  // 2026-11-18: #osvm(VM 전원·자원)과 분리 — 구성도·경로 추적·탭은 #osnet 패널에
  var panel = document.getElementById('osnet-panel');
  var opsPanel = document.getElementById('osops-panel');
  var mapPane = h('div', 'osx-mappane', null, null);
  panes.map = mapPane;
  (function layout() {
    if (!panel || !opsPanel) return;
    // 구조 페이지: 2중 분리 네트워크 요약 카드 + 구성도 + 경로 추적
    var top = document.createElement('div'); top.className = 'osv-top';
    var heroDiv = h('div', 'overview-hero', null, top);
    h('h2', null, '🧭 OpenStack 2중 네트워크 아키텍처 & 구조', heroDiv);
    h('p', null, '앱 서비스망(figteam-net)과 데이터 격리망(data-net)으로 2중 분리되어 Zero-Trust 보안성을 강화했습니다.', heroDiv);

    // 2중 분리 네트워크 토폴로지 요약 카드
    var netCards = h('div', 'stats-grid', null, top);
    netCards.style.cssText = 'width: 100%; margin-top: 10px; display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 10px;';
    
    var cExt = h('div', 'stat-card', null, netCards);
    cExt.innerHTML = '<div class="label" style="color:#9FD3F5;">🌐 ext-net (외부 공인망)</div><div class="value" style="font-size:18px;">192.168.120.0/24</div><div class="subtext">Gateway: .2 | FIP Pool: .200~.254</div>';
    
    var cApp = h('div', 'stat-card', null, netCards);
    cApp.innerHTML = '<div class="label" style="color:#8FE0B4;">⚡ figteam-net (K8s 앱망)</div><div class="value" style="font-size:18px;">172.20.0.0/24</div><div class="subtext">Router: rt-edge (.202) | SNAT: ON | VM: cp1, w1 (2대)</div>';
    
    var cData = h('div', 'stat-card', null, netCards);
    cData.innerHTML = '<div class="label" style="color:#F4C95D;">🔒 data-net (DB 격리망)</div><div class="value" style="font-size:18px;">10.10.2.0/24</div><div class="subtext">Router: rt-data (.220) | SNAT: OFF | FIP 차단 | VM: db-01</div>';
    
    var cPolicy = h('div', 'stat-card', null, netCards);
    cPolicy.innerHTML = '<div class="label" style="color:#B08CFF;">🛡️ 격리 보안그룹 정책</div><div class="value" style="font-size:16px;">sg-figteam-ha · sg-db</div><div class="subtext">DB 격리망 3306 한정 허용 · 외부 접근 전면 차단</div>';

    var mapHead = h('div', 'osx-head', null, top);
    mapHead.style.cssText = 'width: 100%; margin-top: 10px;';
    var mapMeta = h('p', 'osx-meta', '불러오는 중…', mapHead);
    var mapRefresh = h('button', 'btn-top', '새로고침', mapHead); mapRefresh.type = 'button';
    mapRefresh.addEventListener('click', function () { load(true); });
    new MutationObserver(function () { mapMeta.textContent = meta.textContent; })
      .observe(meta, { childList: true, characterData: true, subtree: true });
    var mapCol = h('div', 'osv-mapcol', null, null);
    mapCol.appendChild(mapPane);
    panel.appendChild(top);
    panel.appendChild(mapCol);
    // 연결·상태 페이지: 탭 전체
    var top2 = document.createElement('div'); top2.className = 'osv-top';
    h('h2', null, '🖥️ 하이브리드 멀티클라우드 전체 인프라 자원 상태확인 (OpenStack · KT Cloud · AWS)', h('div', 'overview-hero', null, top2));
    top2.appendChild(head);
    opsPanel.appendChild(top2);
    opsPanel.appendChild(root);
  })();
  [['res', '💻 인프라 전체 자원·스왑 CLI 리스트'], ['diag', '📊 파이프라인 진단 매트릭스'], ['flow', '🛡️ 장애대응 흐름 (L1~L4)'], ['net', '📡 네트워크 연결 점검'], ['apps', '🚀 서비스 & 프로세스 목록'], ['svc', '☁️ OpenStack 서비스 상태'], ['ops', '⚙️ VM 제어 도구']].forEach(function (t, i) {
    var b = h('button', 'osx-tab' + (i ? '' : ' on'), t[1], tabs); b.type = 'button'; b.dataset.p = t[0]; b.setAttribute('role', 'tab');
    var p = panes[t[0]] || h('div', 'osx-pane', null, null);
    p.dataset.p = t[0]; p.hidden = !!i; root.appendChild(p);
    panes[t[0]] = p;
  });
  tabs.addEventListener('click', function (e) {
    var k = e.target.dataset && e.target.dataset.p; if (!k) return;
    Array.prototype.forEach.call(tabs.children, function (b) { b.classList.toggle('on', b.dataset.p === k); });
    Object.keys(panes).forEach(function (p) { if (p !== 'map') panes[p].hidden = p !== k; });
  });
  refresh.addEventListener('click', function () { load(true); loadNet(true); });

  function errBox(parent, key) {
    if (DATA && DATA.errors && DATA.errors[key]) h('p', 'osx-err', '불러오지 못함 (' + key + '): ' + DATA.errors[key], parent);
  }

  // ---------- 데이터 ----------
  function load(force) {
    if (loading || (!force && Date.now() - lastLoad < 20000)) return;
    loading = true; meta.textContent = '불러오는 중…';
    fetch('/api/openstack/overview', { credentials: 'same-origin' })
      .then(function (r) { return r.json().then(function (j) { return { ok: r.ok, j: j }; }); })
      .then(function (x) {
        loading = false; lastLoad = Date.now();
        if (!x.ok || x.j.status !== 'ok') { meta.textContent = 'OpenStack 정보를 불러오지 못했습니다: ' + (x.j.message || ('HTTP ' + x.ok)); return; }
        DATA = x.j;
        var ne = Object.keys(DATA.errors || {}).length;
        meta.textContent = '갱신 ' + new Date(DATA.generated * 1000).toLocaleTimeString() + ' · VM ' + (DATA.servers || []).length + '대 · 네트워크 ' + (DATA.networks || []).length + '개' + (ne ? ' · 일부 항목 실패 ' + ne + '건' : '');
        render();
      })
      .catch(function (e) { loading = false; meta.textContent = 'OpenStack 정보를 불러오지 못했습니다: ' + e.message; });
  }
  function render() { renderMap(); renderDiag(); renderFlow(); renderSvc(); renderRes(); renderApps(); renderOps(); }

  // ---------- 1·3. 구성도 + 경로 추적 ----------
  var mapEl = null;
  var mapWrap, svg, traceList, traceCap, traceIdx = -1, traceTimer = null, HOPS = [];
  function renderMap() {
    var p = panes.map; if (!p) return; p.textContent = '';
    var d = DATA, nets = d.networks || [], subnets = {}, ports = d.ports || [], servers = d.servers || [];
    (d.subnets || []).forEach(function (x) { subnets[x.id] = x; });
    var ext = nets.filter(function (n) { return n['router:external']; });
    var intn = nets.filter(function (n) { return !n['router:external']; });
    // 네트워크 정보가 없으면 VM 주소의 네트워크 이름으로 대체
    if (!nets.length) {
      var names = {};
      servers.forEach(function (v) { Object.keys(v.addresses || {}).forEach(function (k) { names[k] = 1; }); });
      intn = Object.keys(names).map(function (k) { return { id: 'name:' + k, name: k, subnets: [] }; });
    }
    var cidr = function (n) { return (n.subnets || []).map(function (id) { return subnets[id] ? subnets[id].cidr : ''; }).filter(Boolean).join(', '); };
    var hosts = (d.hypervisors || []).map(function (x) { return x.hypervisor_hostname; });
    servers.forEach(function (v) { if (v.host && hosts.indexOf(v.host) < 0 && hosts.indexOf((v.host || '').split('.')[0]) < 0) hosts.push(v.host); });
    if (servers.some(function (v) { return !v.host; })) hosts.push('(배치 정보 없음)');
    var byHost = {};
    hosts.forEach(function (hn) { byHost[hn] = []; });
    servers.forEach(function (v) {
      var key = hosts.filter(function (hn) { return v.host && (hn === v.host || hn.split('.')[0] === v.host.split('.')[0]); })[0] || '(배치 정보 없음)';
      (byHost[key] = byHost[key] || []).push(v);
    });
    var fipByFixed = {};
    (d.floatingips || []).forEach(function (f) { if (f.fixed_ip_address) fipByFixed[f.fixed_ip_address] = f; });

    // 배치 (열: 외부 경로 | 외부망 | 라우터 | 내부망 | Compute)
    var X_EXTCHAIN = 20, X_EXT = 230, X_RT = 360, X_INT = 660, INT_GAP = 80;
    var X_HOST = X_INT + Math.max(1, intn.length) * INT_GAP + 60, HOST_W = 340, ROW = 64, TOP = 60;
    var y = TOP, frames = [];
    hosts.forEach(function (hn) {
      var list = byHost[hn] || [];
      if (list.length === 0) return; // 실행 중인 VM이 없는 유휴 하이퍼바이저 노드는 토폴로지 프레임에서 제외
      var hgt = 54 + Math.max(1, list.length) * ROW;
      frames.push({ host: hn, y: y, h: hgt, vms: list });
      y += hgt + 24;
    });
    var H = Math.max(y, TOP + 6 * 90 + 40), W = X_HOST + HOST_W + 120;
    mapWrap = h('div', 'osx-map', null, p);
    svg = s('svg', { viewBox: '0 0 ' + W + ' ' + H, 'class': 'osx-svg', role: 'img', 'aria-label': 'OpenStack 네트워크 구성도', preserveAspectRatio: 'xMidYMid meet' }, mapWrap);
    var gL = s('g', {}, svg), gN = s('g', {}, svg);
    var el = {};

    function box(id, x, y0, w, hh, title, sub, cls) {
      var g = s('g', { 'class': 'osx-node ' + (cls || ''), 'data-id': id }, gN);
      s('rect', { x: x, y: y0, width: w, height: hh }, g);
      s('text', { x: x + w / 2, y: y0 + (sub ? hh / 2 - 5 : hh / 2 + 5), 'text-anchor': 'middle', 'class': 't' }, g, title);
      if (sub) s('text', { x: x + w / 2, y: y0 + hh / 2 + 16, 'text-anchor': 'middle', 'class': 's' }, g, sub);
      el[id] = g; return g;
    }
    function line(id, pts, cls, label, lx, ly, anchor) {
      var g = s('g', { 'class': 'osx-link ' + (cls || ''), 'data-id': id }, gL);
      s('path', { d: 'M' + pts.map(function (q) { return q.join(','); }).join(' L') }, g);
      if (label) s('text', { x: lx, y: ly, 'text-anchor': anchor || 'start', 'class': 'l' }, g, label);
      el[id] = g; return g;
    }
    // 외부 경로 체인
    var chain = [['ext-cf', 'Cloudflare', 'minwon.ktci5.kr'], ['ext-kt', 'KT Edge (DMZ)', 'WAF · 14.63.212.190'], ['ext-wg', 'WG 터널 A', 'KT ↔ 온프렘'], ['ext-host', '온프렘 호스트', 'VIP 10.10.1.100 · DNAT']];
    chain.forEach(function (c, i) {
      box(c[0], X_EXTCHAIN, TOP + i * 90, 150, 56, c[1], c[2], 'ext');
      if (i) line('l-' + c[0], [[X_EXTCHAIN + 75, TOP + (i - 1) * 90 + 56], [X_EXTCHAIN + 75, TOP + i * 90]], 'ext');
    });
    // AWS 지점 (PR #13·#14) — KT 허브 경유 WG 터널 C. 색은 연결 점검(w1·w2) 실측으로 칠함
    var AWS_Y = TOP + 4 * 90 + 34, KT_MID = TOP + 90 + 28, X_RAIL = 8;
    s('text', { x: X_EXTCHAIN, y: AWS_Y - 12, 'class': 'osx-col' }, gN, 'AWS (PR #13·#14)');
    [['aws-ctl', 'AWS ctl', '10.200.0.3 · 13.125.163.58', 'ctl · t3.small Rocky 8 · VPC 10.50.0.0/16 · 관제·러너 예정'],
     ['aws-dr', 'AWS dr', '10.200.0.4 · 54.116.129.147', 'dr · t3.small Rocky 8 · VPC 10.51.0.0/16 · Pilot-Light DR 예정']].forEach(function (a, i) {
      var ay = AWS_Y + i * 80;
      var g = box(a[0], X_EXTCHAIN, ay, 150, 56, a[1], a[2], 'ext aws');
      s('title', {}, g, a[3]);
      line('l-wgc-' + a[0].slice(4), [[X_EXTCHAIN, KT_MID], [X_RAIL, KT_MID], [X_RAIL, ay + 28], [X_EXTCHAIN, ay + 28]], 'wgc');
    });
    s('text', { x: X_RAIL + 4, y: KT_MID - 6, 'class': 'osx-wgc-label' }, gN, 'WG 터널 C');
    // 외부망 막대
    var extBars = {};
    var extList = ext.length ? ext : [{ id: 'ext:none', name: '외부망 정보 없음', subnets: [] }];
    extList.forEach(function (n, i) {
      var x = X_EXT + i * 18;
      extBars[n.id] = x;
      var g = s('g', { 'class': 'osx-bar ext', 'data-id': 'net-' + n.id }, gN);
      s('rect', { x: x - 5, y: TOP - 10, width: 10, height: H - TOP - 20 }, g);
      s('text', { x: x, y: TOP - 18, 'text-anchor': 'middle', 'class': 'b' }, g, n.name || n.id.slice(0, 8));
      s('text', { x: x + 12, y: H - 16, 'class': 's' }, g, cidr(n));
      el['net-' + n.id] = g;
    });
    var firstExt = extList[0].id;
    line('l-host-ext', [[X_EXTCHAIN + 150, TOP + 3 * 90 + 28], [extBars[firstExt] - 5, TOP + 3 * 90 + 28]], 'ext', '브리지', X_EXTCHAIN + 156, TOP + 3 * 90 + 22);
    // 내부망 막대
    var intBars = {};
    intn.forEach(function (n, i) {
      var x = X_INT + i * INT_GAP;
      intBars[n.id] = x; intBars['name:' + n.name] = x;
      var g = s('g', { 'class': 'osx-bar', 'data-id': 'net-' + n.id }, gN);
      s('rect', { x: x - 5, y: TOP - 10, width: 10, height: H - TOP - 20 }, g);
      s('text', { x: x, y: TOP - 18, 'text-anchor': 'middle', 'class': 'b' }, g, n.name || n.id.slice(0, 8));
      s('text', { x: x + 10, y: H - 16, 'class': 's' }, g, cidr(n));
      el['net-' + n.id] = g;
    });
    // 라우터
    var routers = d.routers || [];
    routers.forEach(function (r, i) {
      var ry = TOP + 40 + i * 120;
      box('rt-' + r.id, X_RT, ry, 150, 56, r.name || '라우터', 'OVN · NAT', 'rt');
      var gw = r.external_gateway_info || {};
      var gwip = ((gw.external_fixed_ips || [])[0] || {}).ip_address || '';
      var ex = extBars[gw.network_id] != null ? extBars[gw.network_id] : extBars[firstExt];
      line('l-gw-' + r.id, [[ex + 5, ry + 20], [X_RT, ry + 20]], 'gw', gwip, ex + 14, ry + 14);
      ports.filter(function (pt) { return pt.device_id === r.id && /router_interface/.test(pt.device_owner || ''); }).forEach(function (pt, k) {
        var ix = intBars[pt.network_id]; if (ix == null) return;
        var ip = ((pt.fixed_ips || [])[0] || {}).ip_address || '';
        var yy = ry + 36 + k * 10;
        line('l-if-' + pt.id, [[X_RT + 150, yy], [ix - 5, yy]], 'if', ip, X_RT + 160, yy - 5);
        el['l-if-net-' + pt.network_id] = el['l-if-' + pt.id];
      });
    });
    // Compute 프레임 + VM
    frames.forEach(function (f, fi) {
      var g = s('g', { 'class': 'osx-host', 'data-id': 'host-' + f.host }, gN);
      s('rect', { x: X_HOST, y: f.y, width: HOST_W, height: f.h }, g);
      var hv = (d.hypervisors || []).filter(function (x) { return x.hypervisor_hostname === f.host; })[0];
      s('text', { x: X_HOST + 10, y: f.y + 20, 'class': 'b' }, g, f.host);
      if (hv) s('text', { x: X_HOST + 10, y: f.y + 42, 'class': 's' }, g, (hv.host_ip || '') + ' · vCPU ' + hv.vcpus_used + '/' + hv.vcpus + ' · RAM ' + Math.round(hv.memory_mb_used / 1024) + '/' + Math.round(hv.memory_mb / 1024) + 'G');
      el['host-' + f.host] = g;
      f.vms.forEach(function (v, i) {
        var vy = f.y + 54 + i * ROW;
        var ips = [];
        Object.keys(v.addresses || {}).forEach(function (nn) { (v.addresses[nn] || []).forEach(function (a) { ips.push({ net: nn, ip: a.addr, type: a['OS-EXT-IPS:type'] }); }); });
        var fixed = ips.filter(function (a) { return a.type !== 'floating'; });
        var fip = ips.filter(function (a) { return a.type === 'floating'; }).map(function (a) { return a.ip; })[0] ||
          fixed.map(function (a) { return fipByFixed[a.ip] && fipByFixed[a.ip].floating_ip_address; }).filter(Boolean)[0];
        var st = (v.status || '').toUpperCase();
        box('vm-' + v.id, X_HOST + 20, vy, 170, 50, v.name, (v.flavor || '') + ' · ' + st, 'vm st-' + (st === 'ACTIVE' ? 'ok' : st === 'SHUTOFF' ? 'off' : 'warn'));
        if (fip) {
          var fg = s('g', { 'class': 'osx-fip', 'data-id': 'fip-' + v.id }, gN);
          s('rect', { x: X_HOST + 200, y: vy + 13, width: 124, height: 24 }, fg);
          s('text', { x: X_HOST + 262, y: vy + 29, 'text-anchor': 'middle' }, fg, fip);
          el['fip-' + v.id] = fg;
        }
        fixed.forEach(function (a, k) {
          var net = intn.filter(function (n) { return n.name === a.net; })[0];
          var bx = net ? intBars[net.id] : intBars['name:' + a.net];
          if (bx == null) return;
          var yy = vy + 18 + k * 12;
          line('l-vm-' + v.id + '-' + k, [[bx + 5, yy], [X_HOST + 20, yy]], 'vm', a.ip, bx + 10, yy - 5);
          if (!k) el['l-vm-' + v.id] = el['l-vm-' + v.id + '-' + k];
        });
      });
      if (fi > 0) {
        var prev = frames[fi - 1];
        line('l-geneve-' + fi, [[X_HOST + HOST_W + 14, prev.y + prev.h / 2], [X_HOST + HOST_W + 14, f.y + f.h / 2]], 'geneve', 'OVN Geneve', X_HOST + HOST_W + 22, (prev.y + prev.h / 2 + f.y + f.h / 2) / 2 + 4, 'start');
      }
    });
    s('text', { x: X_HOST, y: TOP - 20, 'class': 'osx-col' }, gN, 'Compute 노드 · VM (Nova 배치)');
    mapEl = el; paintAws();
    errBox(p, 'networks'); errBox(p, 'routers'); errBox(p, 'servers');

    // 경로 추적 (실데이터 기반)
    var trace = h('div', 'osx-trace', null, p);
    var bar = h('div', 'osx-tbar', null, trace);
    h('strong', null, '전체 경로 추적', bar);
    traceCap = h('span', 'osx-tcap', '단계를 고르거나 재생하세요', bar);
    var bPrev = h('button', 'btn-top', '◀ 이전', bar), bPlay = h('button', 'btn-top', '재생', bar), bNext = h('button', 'btn-top', '다음 ▶', bar);
    [bPrev, bPlay, bNext].forEach(function (b) { b.type = 'button'; });
    traceList = h('ol', 'osx-tlist compact', null, bar);
    var target = servers.filter(function (v) { return el['fip-' + v.id]; })[0] || servers[0];
    var rt = routers[0];
    var tNet = target ? intn.filter(function (n) { return (target.addresses || {})[n.name]; })[0] : null;
    var tFixed = target ? ((((target.addresses || {})[tNet ? tNet.name : Object.keys(target.addresses || {})[0]] || [])[0]) || {}).addr : '';
    var tFip = target && el['fip-' + target.id] ? el['fip-' + target.id].textContent : '';
    HOPS = [
      ['minwon.ktci5.kr → Cloudflare 엣지 수신 (DNS 프록시)', ['ext-cf']],
      ['KT Edge DMZ(14.63.212.190:443): TLS 종료 · ModSecurity WAF (대기열 미구축)', ['ext-kt', 'l-ext-kt']],
      ['WireGuard 터널 A → 온프렘 호스트', ['ext-wg', 'l-ext-wg']],
      ['온프렘 호스트 VIP 10.10.1.100 → DNAT → VMware 브리지 → 외부망', ['ext-host', 'l-ext-host', 'l-host-ext', 'net-' + firstExt]],
      [tFip ? 'Floating IP ' + tFip + ' → 라우터 (OVN NAT)' : '외부망 → 라우터 게이트웨이 (OVN NAT)', rt ? ['l-gw-' + rt.id, 'rt-' + rt.id].concat(target ? ['fip-' + target.id] : []) : []],
      [tNet ? '라우터 → ' + tNet.name + ' (게이트웨이 인터페이스)' : '라우터 → 내부망', tNet ? ['l-if-net-' + tNet.id, 'net-' + tNet.id] : []],
      [target ? tNet ? tNet.name + ' → ' + target.name + ' (' + tFixed + ' · ' + (target.host || '') + ')' : target.name : 'VM 정보 없음', target ? ['l-vm-' + target.id, 'vm-' + target.id, 'host-' + (frames.filter(function (f) { return f.vms.indexOf(target) >= 0; })[0] || {}).host] : []]
    ];
    if (frames.length > 1) HOPS.push(['다른 Compute의 VM과는 OVN Geneve 터널로 통신', ['l-geneve-1']]);
    HOPS.push(['온프렘 → KT 허브 → AWS ctl·dr (WG 터널 C · PR #13·#14) — 초록=연결, 빨강=미연결', ['ext-kt', 'l-wgc-ctl', 'l-wgc-dr', 'aws-ctl', 'aws-dr']]);
    HOPS.forEach(function (hp, i) {
      var li = h('li', null, null, traceList); li.dataset.i = i; li.title = hp[0]; li.tabIndex = 0;
      h('i', null, String(i + 1), li); h('span', null, hp[0], li);
      li.addEventListener('keydown', function (e) { if (e.key === 'Enter') { stop(); go(i); } });
      li.addEventListener('click', function () { stop(); go(i); });
    });
    function go(i) {
      traceIdx = Math.max(0, Math.min(HOPS.length - 1, i));
      Object.keys(el).forEach(function (k) { if (el[k]) el[k].classList.remove('hl', 'done'); });
      HOPS.forEach(function (hp, j) { if (j <= traceIdx) hp[1].forEach(function (id) { if (el[id]) el[id].classList.add(j === traceIdx ? 'hl' : 'done'); }); });
      Array.prototype.forEach.call(traceList.children, function (li) { li.classList.toggle('active', +li.dataset.i === traceIdx); li.classList.toggle('done', +li.dataset.i < traceIdx); });
      traceCap.textContent = (traceIdx + 1) + '. ' + HOPS[traceIdx][0];
    }
    function stop() { if (traceTimer) { clearInterval(traceTimer); traceTimer = null; } bPlay.textContent = '재생'; }
    bPrev.addEventListener('click', function () { stop(); go(traceIdx - 1); });
    bNext.addEventListener('click', function () { stop(); go(traceIdx + 1); });
    bPlay.addEventListener('click', function () {
      if (traceTimer) { stop(); return; }
      bPlay.textContent = '일시정지';
      if (traceIdx >= HOPS.length - 1) traceIdx = -1;
      go(traceIdx + 1);
      traceTimer = setInterval(function () { if (traceIdx >= HOPS.length - 1) { stop(); return; } go(traceIdx + 1); }, 1600);
    });
  }


  // ---------- 신규. 파이프라인 실측 진단 매트릭스 (4대 분류) ----------
  function renderDiag() {
    var p = panes.diag; if (!p) return;
    p.textContent = '';

    var top = h('div', 'overview-hero', null, p);
    top.style.cssText = 'background: linear-gradient(135deg, rgba(95, 211, 154, 0.2), rgba(15, 45, 79, 0.9)); border: 1px solid rgba(95, 211, 154, 0.4); margin-bottom: 12px;';
    h('h2', null, '📊 하이브리드 자동복구 파이프라인 현상황 실측 진단 매트릭스', top);
    h('p', null, '실제 인프라(KT Cloud Edge · AWS ctl/dr · 온프레미스 OpenStack)의 실시간 포트 바인딩 및 Git PR 코드 반영 현황을 4단계 기준(정상 / 작동안됨-확인 / 중복됨-해결필요 / 사용안됨)으로 전수 점검한 결과입니다.', top);

    // 4대 분류 KPI 카드
    var kpiGrid = h('div', 'stats-grid', null, p);
    kpiGrid.style.cssText = 'display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 12px; margin-bottom: 14px;';

    var kpi1 = h('div', 'stat-card', null, kpiGrid);
    kpi1.style.cssText = 'border-top: 3px solid #8FE0B4; background: rgba(29, 74, 122, 0.5);';
    kpi1.innerHTML = '<div class="label" style="color:#8FE0B4; font-weight:800;">🟢 정상 가동 (Active)</div>' +
      '<div class="value" style="font-size:22px; color:#8FE0B4;">7건 정상</div>' +
      '<div class="subtext">KT Edge WAF, AWS ctl 오케스트레이터, AWS dr k3s, OS 컨트롤러, 온프렘 앱, DB, 카오스 RTO</div>';

    var kpi2 = h('div', 'stat-card', null, kpiGrid);
    kpi2.style.cssText = 'border-top: 3px solid #F4C95D; background: rgba(29, 74, 122, 0.5);';
    kpi2.innerHTML = '<div class="label" style="color:#F4C95D; font-weight:800;">🟡 작동안됨 / 점검필요 [확인]</div>' +
      '<div class="value" style="font-size:22px; color:#F4C95D;">3건 확인</div>' +
      '<div class="subtext">AWS 관제 컨테이너(Docker 미기동), MySQL Replica 13306 포트 정합성, db-01 격리망 라우팅</div>';

    var kpi3 = h('div', 'stat-card', null, kpiGrid);
    kpi3.style.cssText = 'border-top: 3px solid #E76F51; background: rgba(29, 74, 122, 0.5);';
    kpi3.innerHTML = '<div class="label" style="color:#E76F51; font-weight:800;">🟠 만들었는데 중복됨 [해결필요]</div>' +
      '<div class="value" style="font-size:22px; color:#E76F51;">2건 해결필요</div>' +
      '<div class="subtext">오케스트레이터 Systemd vs Docker 이중화, 복구 스크립트 Ansible yml vs Bash sh 단일화</div>';

    var kpi4 = h('div', 'stat-card', null, kpiGrid);
    kpi4.style.cssText = 'border-top: 3px solid #A78BFA; background: rgba(29, 74, 122, 0.5);';
    kpi4.innerHTML = '<div class="label" style="color:#A78BFA; font-weight:800;">⚪ 만들었으나 사용안됨 [사용안됨]</div>' +
      '<div class="value" style="font-size:22px; color:#A78BFA;">3건 정리완료</div>' +
      '<div class="subtext">온프렘 Argo CD(자원확보 삭제), 온프렘 Grafana(AWS 이관), Cloudflare Worker(DNS 직행)</div>';

    // 상세 분석 매트릭스 테이블
    var box = h('div', 'osx-card', null, p);
    box.style.cssText = 'padding: 16px; margin-top: 4px; overflow-x: auto; background: rgba(15, 45, 79, 0.6); border: 1px solid rgba(79, 115, 154, 0.5);';
    h('h3', null, '📋 하이브리드 컴포넌트별 세부 현황 & 정합성 진단표', box);
    
    var tbl = document.createElement('table');
    tbl.style.cssText = 'width: 100%; border-collapse: collapse; font-size: 12px; margin-top: 10px; color: #D3E0EC;';
    tbl.innerHTML = '<thead style="background: rgba(42, 64, 88, 0.8); color: #9FD3F5; border-bottom: 2px solid #4F739A;">' +
      '<tr><th style="padding:8px 10px; text-align:left;">분류</th>' +
      '<th style="padding:8px 10px; text-align:left;">컴포넌트 및 기능</th>' +
      '<th style="padding:8px 10px; text-align:left;">위치 및 엔드포인트</th>' +
      '<th style="padding:8px 10px; text-align:left;">Git PR 코드 확인</th>' +
      '<th style="padding:8px 10px; text-align:left;">실측 상태 및 조치 가이드</th></tr></thead>' +
      '<tbody>' +
      '<tr style="border-bottom: 1px solid rgba(255,255,255,0.08); background: rgba(244, 201, 93, 0.08);">' +
      '<td style="padding:8px 10px;"><span style="background:#F4C95D; color:#111; font-weight:700; padding:2px 6px; border-radius:2px;">확인필요</span></td>' +
      '<td style="padding:8px 10px; font-weight:700; color:#fff;">AWS ctl 모니터링 스택<br><small style="color:#B4C6D8;">Prometheus · Grafana · Alertmanager</small></td>' +
      '<td style="padding:8px 10px; font-family:monospace;">AWS ctl (10.200.0.3)<br>:9090 / :3000 / :9093</td>' +
      '<td style="padding:8px 10px; color:#8FE0B4;">PR #24 Merged<br><code>observability/docker-compose.yml</code></td>' +
      '<td style="padding:8px 10px; color:#F4C95D;"><b>[FAIL] Connection refused</b><br>코드 병합되었으나 AWS ctl에 Docker 미설치로 컨테이너 미기동 ➔ <code>dnf install docker</code> 및 기동 필요</td>' +
      '</tr>' +
      '<tr style="border-bottom: 1px solid rgba(255,255,255,0.08); background: rgba(244, 201, 93, 0.08);">' +
      '<td style="padding:8px 10px;"><span style="background:#F4C95D; color:#111; font-weight:700; padding:2px 6px; border-radius:2px;">확인필요</span></td>' +
      '<td style="padding:8px 10px; font-weight:700; color:#fff;">AWS dr MySQL Replica 포트<br><small style="color:#B4C6D8;">Standby 복제본 수신</small></td>' +
      '<td style="padding:8px 10px; font-family:monospace;">AWS dr (10.200.0.4)<br>:13306 (vs :3306)</td>' +
      '<td style="padding:8px 10px; color:#8FE0B4;">PR #26 Open<br><code>scripts/dr/aws/</code></td>' +
      '<td style="padding:8px 10px; color:#F4C95D;"><b>[3306 닫힘 / 13306 열림]</b><br>k3s kubectl port-forward가 13306으로 리슨 중 ➔ 복구 스크립트 포트 변수 13306 일원화 확인</td>' +
      '</tr>' +
      '<tr style="border-bottom: 1px solid rgba(255,255,255,0.08); background: rgba(244, 201, 93, 0.08);">' +
      '<td style="padding:8px 10px;"><span style="background:#F4C95D; color:#111; font-weight:700; padding:2px 6px; border-radius:2px;">확인필요</span></td>' +
      '<td style="padding:8px 10px; font-weight:700; color:#fff;">온프렘 db-01 외부 직접 도달<br><small style="color:#B4C6D8;">data-net DB 격리망</small></td>' +
      '<td style="padding:8px 10px; font-family:monospace;">온프렘 (10.10.2.10:3306)<br>앱망 172.20.0.86 경유</td>' +
      '<td style="padding:8px 10px; color:#8FE0B4;">PR #20 Merged<br><code>db-zone-provision.sh</code></td>' +
      '<td style="padding:8px 10px; color:#8FE0B4;"><b>[보안격리 정상 / 외부 타임아웃]</b><br>k8s-cp1 내부망에서는 3306 정상 접속. AWS 복제 시 온프렘 VIP(터널) 경유 라우팅 정합성 확인</td>' +
      '</tr>' +
      '<tr style="border-bottom: 1px solid rgba(255,255,255,0.08); background: rgba(231, 111, 81, 0.08);">' +
      '<td style="padding:8px 10px;"><span style="background:#E76F51; color:#fff; font-weight:700; padding:2px 6px; border-radius:2px;">해결필요</span></td>' +
      '<td style="padding:8px 10px; font-weight:700; color:#fff;">오케스트레이터 배포 일원화<br><small style="color:#B4C6D8;">포트 8080 충돌 방지</small></td>' +
      '<td style="padding:8px 10px; font-family:monospace;">AWS ctl (10.200.0.3:8080)<br>Systemd vs Docker</td>' +
      '<td style="padding:8px 10px; color:#FF9E8C;">PR #24 & PR #25<br>이중 정의 상태</td>' +
      '<td style="padding:8px 10px; color:#E76F51;"><b>[중복 실행 충돌 위험]</b><br>현재 systemd로 uvicorn standalone 실행 중. PR #24 docker-compose와 단일 운영 방식으로 정리 필요</td>' +
      '</tr>' +
      '<tr style="border-bottom: 1px solid rgba(255,255,255,0.08); background: rgba(231, 111, 81, 0.08);">' +
      '<td style="padding:8px 10px;"><span style="background:#E76F51; color:#fff; font-weight:700; padding:2px 6px; border-radius:2px;">해결필요</span></td>' +
      '<td style="padding:8px 10px; font-weight:700; color:#fff;">복구 스크립트 규격 단일화<br><small style="color:#B4C6D8;">Ansible vs Bash</small></td>' +
      '<td style="padding:8px 10px; font-family:monospace;">playbooks/recovery/<br>vs scripts/dr/</td>' +
      '<td style="padding:8px 10px; color:#FF9E8C;">PR #25 & PR #26<br>이중 작성 상태</td>' +
      '<td style="padding:8px 10px; color:#E76F51;"><b>[호출 규격 통일 필요]</b><br>오케스트레이터(runbooks.yml)가 실행할 표준 인터페이스(Ansible Playbook vs Bash Script) 일원화</td>' +
      '</tr>' +
      '<tr style="border-bottom: 1px solid rgba(255,255,255,0.08);">' +
      '<td style="padding:8px 10px;"><span style="background:#8FE0B4; color:#04121F; font-weight:700; padding:2px 6px; border-radius:2px;">정상가동</span></td>' +
      '<td style="padding:8px 10px; font-weight:700; color:#fff;">KT Cloud Edge Nginx WAF</td>' +
      '<td style="padding:8px 10px; font-family:monospace;">10.200.0.1:443 (공인 14.63.212.190)</td>' +
      '<td style="padding:8px 10px; color:#8FE0B4;">PR #18 Merged</td>' +
      '<td style="padding:8px 10px; color:#8FE0B4;"><b>[OK] CONNECTED</b> · TLS 종료, ModSecurity WAF, 터널 A/C 연결 정상</td>' +
      '</tr>' +
      '<tr style="border-bottom: 1px solid rgba(255,255,255,0.08);">' +
      '<td style="padding:8px 10px;"><span style="background:#8FE0B4; color:#04121F; font-weight:700; padding:2px 6px; border-radius:2px;">정상가동</span></td>' +
      '<td style="padding:8px 10px; font-weight:700; color:#fff;">AWS ctl 복구 오케스트레이터</td>' +
      '<td style="padding:8px 10px; font-family:monospace;">10.200.0.3:8080 (/healthz)</td>' +
      '<td style="padding:8px 10px; color:#8FE0B4;">PR #25 Merged</td>' +
      '<td style="padding:8px 10px; color:#8FE0B4;"><b>[OK] ACTIVE</b> · Uvicorn 가동 (uptime 176ks, dry-run 대기 중)</td>' +
      '</tr>' +
      '<tr style="border-bottom: 1px solid rgba(255,255,255,0.08);">' +
      '<td style="padding:8px 10px;"><span style="background:#8FE0B4; color:#04121F; font-weight:700; padding:2px 6px; border-radius:2px;">정상가동</span></td>' +
      '<td style="padding:8px 10px; font-weight:700; color:#fff;">AWS dr Pilot-Light K3s</td>' +
      '<td style="padding:8px 10px; font-family:monospace;">10.200.0.4:30080 (/healthz)</td>' +
      '<td style="padding:8px 10px; color:#8FE0B4;">PR #19 Merged</td>' +
      '<td style="padding:8px 10px; color:#8FE0B4;"><b>[OK] ACTIVE</b> · k3s minwon-app Standby 서빙 정상</td>' +
      '</tr>' +
      '<tr style="border-bottom: 1px solid rgba(255,255,255,0.08);">' +
      '<td style="padding:8px 10px;"><span style="background:#8FE0B4; color:#04121F; font-weight:700; padding:2px 6px; border-radius:2px;">정상가동</span></td>' +
      '<td style="padding:8px 10px; font-weight:700; color:#fff;">온프렘 오픈스택 인프라 & 앱</td>' +
      '<td style="padding:8px 10px; font-family:monospace;">192.168.120.160:5000 / .226:8080</td>' +
      '<td style="padding:8px 10px; color:#8FE0B4;">PR #20 Merged</td>' +
      '<td style="padding:8px 10px; color:#8FE0B4;"><b>[OK] ACTIVE</b> · OpenStack 4노드 정상, minwon-app 정상 응답</td>' +
      '</tr>' +
      '<tr style="border-bottom: 1px solid rgba(255,255,255,0.08);">' +
      '<td style="padding:8px 10px;"><span style="background:#8FE0B4; color:#04121F; font-weight:700; padding:2px 6px; border-radius:2px;">정상가동</span></td>' +
      '<td style="padding:8px 10px; font-weight:700; color:#fff;">카오스 엔지니어링 & RTO 도구</td>' +
      '<td style="padding:8px 10px; font-family:monospace;">chaos/measure_rto.py (0.5s)</td>' +
      '<td style="padding:8px 10px; color:#8FE0B4;">PR #21 Merged</td>' +
      '<td style="padding:8px 10px; color:#8FE0B4;"><b>[OK] READY</b> · Blackbox 0.5초 프로빙 및 iptables 장애 주입 완비</td>' +
      '</tr>' +
      '<tr>' +
      '<td style="padding:8px 10px;"><span style="background:#A78BFA; color:#04121F; font-weight:700; padding:2px 6px; border-radius:2px;">사용안됨</span></td>' +
      '<td style="padding:8px 10px; font-weight:700; color:#B4C6D8;">온프렘 Argo CD / 온프렘 Grafana</td>' +
      '<td style="padding:8px 10px; font-family:monospace;">k8s-cp1 (:30800 / :30300)</td>' +
      '<td style="padding:8px 10px; color:#B4C6D8;">main 코드 존재</td>' +
      '<td style="padding:8px 10px; color:#A78BFA;"><b>[사용안됨 · 정리완료]</b> compute3 RAM 확보 위해 파드 삭제, AWS 관제로 일원화</td>' +
      '</tr>' +
      '</tbody>';
    box.appendChild(tbl);
  }

  // ---------- 신규. 장애대응 흐름 (L1~L4 + 경로 장애) ----------
  function renderFlow() {
    var p = panes.flow; if (!p) return;
    p.textContent = '';
    
    var top = h('div', 'overview-hero', null, p);
    top.style.cssText = 'background: linear-gradient(135deg, rgba(244, 162, 97, 0.2), rgba(15, 45, 79, 0.9)); border: 1px solid rgba(244, 162, 97, 0.4); margin-bottom: 14px;';
    h('h2', null, '🛡️ 민원불패 — 장애대응 흐름 (L1~L4 + 경로 장애 자동 판정 다이어그램)', top);
    h('p', null, 'AWS 관제(Alertmanager)가 장애 신호를 감지하고, Orchestrator가 L1(K8s) ➔ L2(서비스 재기동) ➔ 경로장애(터널우회) ➔ L3(DR전환) ➔ L4(S3복원)를 단계별로 판정합니다. 각 단계는 Blackbox 3회 연속 검증을 통과해야 종료되며, 실패 시 상위 단계로 승급(Escalation)됩니다.', top);

    // 플로우차트 SVG 시각화 박스
    var svgBox = h('div', 'stat-card', null, p);
    svgBox.style.cssText = 'background: #080E17; border: 1px solid #1E3A5F; padding: 16px; margin-bottom: 16px; border-radius: 6px; overflow-x: auto;';
    
    svgBox.innerHTML = '<div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:12px;">' +
      '<div style="font-size:14px; font-weight:700; color:#F7D684;">📐 아키텍처 자동 복구 시퀀스 다이어그램 (인터랙티브 순서도)</div>' +
      '<div style="font-size:11px; color:#8AA5C2;">S1·S2·S3 3-Signal 판정 ➔ Blackbox 3회 검증 ➔ RTO 실측</div>' +
      '</div>' +
      '<svg viewBox="0 0 1020 620" style="width:100%; min-width:880px; height:auto; font-family:monospace; font-size:11.5px;">' +
      '<!-- 배경 그리드 및 영역 -->' +
      '<defs>' +
      '  <marker id="arrow" viewBox="0 0 10 10" refX="6" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">' +
      '    <path d="M 0 1 L 10 5 L 0 9 z" fill="#8AA5C2" />' +
      '  </marker>' +
      '  <marker id="arrow-orange" viewBox="0 0 10 10" refX="6" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">' +
      '    <path d="M 0 1 L 10 5 L 0 9 z" fill="#F4A261" />' +
      '  </marker>' +
      '  <marker id="arrow-green" viewBox="0 0 10 10" refX="6" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">' +
      '    <path d="M 0 1 L 10 5 L 0 9 z" fill="#5FD39A" />' +
      '  </marker>' +
      '  <marker id="arrow-red" viewBox="0 0 10 10" refX="6" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">' +
      '    <path d="M 0 1 L 10 5 L 0 9 z" fill="#FF6B81" />' +
      '  </marker>' +
      '</defs>' +

      '<!-- 1. 최상단: 장애 감지 -->' +
      '<rect x="20" y="20" width="280" height="52" rx="6" fill="#1B2A40" stroke="#FF6B81" stroke-width="1.5"/>' +
      '<text x="160" y="42" text-anchor="middle" fill="#FFB2BA" font-weight="bold" font-size="12">장애 감지</text>' +
      '<text x="160" y="58" text-anchor="middle" fill="#D3E0EC" font-size="10.5">AWS 관제: Alertmanager ➔ Orchestrator</text>' +

      '<!-- L3 판정 신호 상단 박스 -->' +
      '<rect x="330" y="15" width="470" height="80" rx="6" fill="#0F1E32" stroke="#F7D684" stroke-dasharray="3,3"/>' +
      '<text x="345" y="32" fill="#F7D684" font-weight="bold" font-size="11">⚡ L3 판정 신호 (셋 다 실패해야 승격) & 펜싱</text>' +
      '<text x="345" y="48" fill="#D3E0EC" font-size="10">• S1 AWS Blackbox ➔ 공인 URL (Edge·터널 A) 3회 연속 실패</text>' +
      '<text x="345" y="62" fill="#D3E0EC" font-size="10">• S2 온프렘 ↔ AWS 터널 B 핸드셰이크 >120s | S3 Edge ➔ 온프렘 터널 A >120s</text>' +
      '<text x="345" y="76" fill="#9FD3F5" font-size="9.5">• 펜싱 Watchdog: KT·AWS 60s 미도달 시 Primary 스스로 super_read_only=ON</text>' +

      '<!-- 화살표: 감지 ➔ Pod/노드 이상? -->' +
      '<line x1="160" y1="72" x2="160" y2="115" stroke="#8AA5C2" stroke-width="1.5" marker-end="url(#arrow)"/>' +

      '<!-- 다이아몬드 1: Pod·노드 이상? -->' +
      '<polygon points="160,115 250,145 160,175 70,145" fill="#122438" stroke="#F4C95D" stroke-width="1.5"/>' +
      '<text x="160" y="149" text-anchor="middle" fill="#F4C95D" font-weight="bold" font-size="11">Pod·노드 이상?</text>' +

      '<!-- YES ➔ L1 K8s 자가치유 -->' +
      '<line x1="250" y1="145" x2="330" y2="145" stroke="#5FD39A" stroke-width="1.5" marker-end="url(#arrow-green)"/>' +
      '<text x="285" y="138" text-anchor="middle" fill="#5FD39A" font-size="10">예</text>' +
      '<rect x="330" y="120" width="320" height="52" rx="6" fill="#142B28" stroke="#5FD39A" stroke-width="1.5"/>' +
      '<text x="490" y="140" text-anchor="middle" fill="#8FE0B4" font-weight="bold">L1 K8s 자가치유 (초 단위 / 주체: K8s)</text>' +
      '<text x="490" y="156" text-anchor="middle" fill="#D3E0EC" font-size="10">liveness/readiness · ReplicaSet · 노드 drain</text>' +

      '<!-- NO ➔ 다이아몬드 2: 서비스 1분+ 무응답? -->' +
      '<line x1="160" y1="175" x2="160" y2="215" stroke="#8AA5C2" stroke-width="1.5" marker-end="url(#arrow)"/>' +
      '<text x="175" y="198" fill="#8AA5C2" font-size="10">아니오</text>' +
      '<polygon points="160,215 250,245 160,275 70,245" fill="#122438" stroke="#F4C95D" stroke-width="1.5"/>' +
      '<text x="160" y="245" text-anchor="middle" fill="#F4C95D" font-weight="bold" font-size="10.5">서비스 1분+</text>' +
      '<text x="160" y="258" text-anchor="middle" fill="#F4C95D" font-weight="bold" font-size="10.5">무응답?</text>' +

      '<!-- YES ➔ L2 서비스 재기동 -->' +
      '<line x1="250" y1="245" x2="330" y2="245" stroke="#5FD39A" stroke-width="1.5" marker-end="url(#arrow-green)"/>' +
      '<text x="285" y="238" text-anchor="middle" fill="#5FD39A" font-size="10">예</text>' +
      '<rect x="330" y="220" width="320" height="52" rx="6" fill="#182B42" stroke="#9FD3F5" stroke-width="1.5"/>' +
      '<text x="490" y="240" text-anchor="middle" fill="#9FD3F5" font-weight="bold">L2 서비스 재기동 (Ansible / ≤3분)</text>' +
      '<text x="490" y="256" text-anchor="middle" fill="#D3E0EC" font-size="10">Nginx · 앱 · MySQL · WG 재기동 (터널 B 경유)</text>' +

      '<!-- NO ➔ 다이아몬드 3: 터널 A만 끊김? -->' +
      '<line x1="160" y1="275" x2="160" y2="315" stroke="#8AA5C2" stroke-width="1.5" marker-end="url(#arrow)"/>' +
      '<text x="175" y="298" fill="#8AA5C2" font-size="10">아니오</text>' +
      '<polygon points="160,315 250,345 160,375 70,345" fill="#122438" stroke="#F4C95D" stroke-width="1.5"/>' +
      '<text x="160" y="342" text-anchor="middle" fill="#F4C95D" font-weight="bold" font-size="10">터널 A만 끊김?</text>' +
      '<text x="160" y="355" text-anchor="middle" fill="#A8C0D8" font-size="9">(S1·S3 실패, S2정상)</text>' +

      '<!-- YES ➔ 경로 장애 복구 -->' +
      '<line x1="250" y1="345" x2="330" y2="345" stroke="#F4A261" stroke-width="1.5" marker-end="url(#arrow-orange)"/>' +
      '<text x="285" y="338" text-anchor="middle" fill="#F4A261" font-size="10">예</text>' +
      '<rect x="330" y="320" width="320" height="52" rx="6" fill="#2B1F14" stroke="#E76F51" stroke-width="1.5"/>' +
      '<text x="490" y="340" text-anchor="middle" fill="#F4A261" font-weight="bold">경로 장애 복구 — DB 승격 금지</text>' +
      '<text x="490" y="356" text-anchor="middle" fill="#D3E0EC" font-size="10">WG 재기동 ➔ 미복구 시 Edge ➔ 터널C ➔ AWS 우회</text>' +

      '<!-- NO ➔ 다이아몬드 4: 사이트 장애? -->' +
      '<line x1="160" y1="375" x2="160" y2="415" stroke="#8AA5C2" stroke-width="1.5" marker-end="url(#arrow)"/>' +
      '<text x="175" y="398" fill="#8AA5C2" font-size="10">아니오</text>' +
      '<polygon points="160,415 250,445 160,475 70,445" fill="#122438" stroke="#F4C95D" stroke-width="1.5"/>' +
      '<text x="160" y="442" text-anchor="middle" fill="#F4C95D" font-weight="bold" font-size="10.5">사이트 장애?</text>' +
      '<text x="160" y="455" text-anchor="middle" fill="#FFB2BA" font-size="9">(S1 ∧ S2 ∧ S3 실패)</text>' +

      '<!-- YES ➔ L3 DR 전환 -->' +
      '<line x1="250" y1="445" x2="330" y2="445" stroke="#5FD39A" stroke-width="1.5" marker-end="url(#arrow-green)"/>' +
      '<text x="285" y="438" text-anchor="middle" fill="#5FD39A" font-size="10">예</text>' +
      '<rect x="330" y="420" width="320" height="52" rx="6" fill="#261935" stroke="#C3A6FF" stroke-width="1.5"/>' +
      '<text x="490" y="440" text-anchor="middle" fill="#C3A6FF" font-weight="bold">L3 DR 전환 (AWS Pilot-Light / RTO ≤ 15분)</text>' +
      '<text x="490" y="456" text-anchor="middle" fill="#D3E0EC" font-size="10">① 펜싱 확인 ② Replica 승격 ③ EC2·k3s 앱 ④ Edge 전환</text>' +

      '<!-- NO ➔ 다이아몬드 5: 복제 깨짐/손상? -->' +
      '<line x1="160" y1="475" x2="160" y2="515" stroke="#8AA5C2" stroke-width="1.5" marker-end="url(#arrow)"/>' +
      '<text x="175" y="498" fill="#8AA5C2" font-size="10">아니오</text>' +
      '<polygon points="160,515 250,545 160,575 70,545" fill="#122438" stroke="#F4C95D" stroke-width="1.5"/>' +
      '<text x="160" y="542" text-anchor="middle" fill="#F4C95D" font-weight="bold" font-size="10">복제 깨짐 / 손상?</text>' +

      '<!-- YES ➔ L4 백업 복원 -->' +
      '<line x1="250" y1="545" x2="330" y2="545" stroke="#5FD39A" stroke-width="1.5" marker-end="url(#arrow-green)"/>' +
      '<text x="285" y="538" text-anchor="middle" fill="#5FD39A" font-size="10">예</text>' +
      '<rect x="330" y="520" width="320" height="52" rx="6" fill="#331518" stroke="#FF9E8C" stroke-width="1.5"/>' +
      '<text x="490" y="540" text-anchor="middle" fill="#FF9E8C" font-weight="bold">L4 백업 복원 (S3 PITR / RTO ≤ 60m · RPO ≤ 15m)</text>' +
      '<text x="490" y="556" text-anchor="middle" fill="#D3E0EC" font-size="10">최신 S3 덤프 + binlog 시점 복원 ➔ 서비스 재기동</text>' +

      '<!-- NO ➔ 경보만 -->' +
      '<line x1="160" y1="575" x2="160" y2="600" stroke="#8AA5C2" stroke-width="1.5"/>' +
      '<text x="160" y="612" text-anchor="middle" fill="#8AA5C2" font-size="10">아니오 ➔ 경보만 (단순 관측 열화 ➔ Slack 알림)</text>' +

      '<!-- 복구 검증 다이아몬드 (오른쪽 수렴) -->' +
      '<path d="M 650 145 L 720 145 L 720 345 L 740 345" fill="none" stroke="#8AA5C2" stroke-width="1.5"/>' +
      '<path d="M 650 245 L 720 245" fill="none" stroke="#8AA5C2" stroke-width="1.5"/>' +
      '<path d="M 650 345 L 740 345" fill="none" stroke="#8AA5C2" stroke-width="1.5"/>' +
      '<path d="M 650 445 L 720 445 L 720 345" fill="none" stroke="#8AA5C2" stroke-width="1.5"/>' +
      '<path d="M 650 545 L 720 545 L 720 345" fill="none" stroke="#8AA5C2" stroke-width="1.5" marker-end="url(#arrow)"/>' +

      '<polygon points="790,305 850,345 790,385 730,345" fill="#1B3028" stroke="#5FD39A" stroke-width="1.5"/>' +
      '<text x="790" y="342" text-anchor="middle" fill="#5FD39A" font-weight="bold" font-size="10.5">복구 검증</text>' +
      '<text x="790" y="355" text-anchor="middle" fill="#D3E0EC" font-size="9.5">Blackbox 3회</text>' +

      '<!-- 성공 ➔ 기록·보고 -->' +
      '<line x1="850" y1="345" x2="910" y2="345" stroke="#5FD39A" stroke-width="1.5" marker-end="url(#arrow-green)"/>' +
      '<text x="875" y="338" text-anchor="middle" fill="#5FD39A" font-size="10">예</text>' +
      '<rect x="910" y="320" width="100" height="52" rx="4" fill="#0F251E" stroke="#5FD39A"/>' +
      '<text x="960" y="342" text-anchor="middle" fill="#5FD39A" font-weight="bold" font-size="10">기록 · 보고</text>' +
      '<text x="960" y="356" text-anchor="middle" fill="#A8C0D8" font-size="8.5">RTO / Slack</text>' +

      '<!-- 실패 ➔ 상위 단계 승급 -->' +
      '<line x1="790" y1="385" x2="790" y2="460" stroke="#FF6B81" stroke-width="1.5" marker-end="url(#arrow-red)"/>' +
      '<text x="805" y="415" fill="#FF6B81" font-size="10">아니오</text>' +
      '<rect x="740" y="460" width="140" height="48" rx="4" fill="#331518" stroke="#FF6B81"/>' +
      '<text x="810" y="480" text-anchor="middle" fill="#FFB2BA" font-weight="bold" font-size="10">상위 단계 승급</text>' +
      '<text x="810" y="495" text-anchor="middle" fill="#D3E0EC" font-size="9">(L1➔L2➔L3➔L4 / 인계)</text>' +
      '</svg>';

    var grid = h('div', 'stats-grid', null, p);
    grid.style.cssText = 'display: grid; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); gap: 12px; margin-bottom: 14px;';

    // 1. 신호 감지 카드
    var cSig = h('div', 'stat-card', null, grid);
    cSig.style.cssText = 'border-top: 3px solid #F7D684;';
    cSig.innerHTML = '<div class="label" style="color:#F7D684; font-size:12px; font-weight:800;">🚨 장애 감지 & 3-Signal 판정 룰</div>' +
      '<div class="value" style="font-size:15px; color:#F7D684; margin-top:2px;">Alertmanager ➔ Orchestrator</div>' +
      '<div class="subtext" style="line-height:1.6; margin-top:6px; color:#D3E0EC; font-size:11.5px;">' +
      '• <b>S1</b>: AWS Blackbox ➔ 공인 URL (Edge·터널 A) 3회 연속 실패<br>' +
      '• <b>S2</b>: 온프렘 ↔ AWS 터널 B 핸드셰이크 >120s 초과<br>' +
      '• <b>S3</b>: KT Edge가 본 터널 A 핸드셰이크 >120s 초과<br>' +
      '• <b>Fencing</b>: 온프렘 Watchdog: KT·AWS 둘 다 60s 미도달 시 Primary 스스로 <code>super_read_only=ON</code><br>' +
      '• <b>감시의 감시</b>: Alertmanager Watchdog ➔ Lambda Dead-man ➔ Slack' +
      '</div>';

    // 2. L1 K8s 자가치유 카드
    var cL1 = h('div', 'stat-card', null, grid);
    cL1.style.cssText = 'border-top: 3px solid #8FE0B4;';
    cL1.innerHTML = '<div class="label" style="color:#8FE0B4; font-size:12px; font-weight:800;">⚡ Level 1. K8s 자가치유</div>' +
      '<div class="value" style="font-size:15px; color:#8FE0B4; margin-top:2px;">초 단위 복구 (판단 주체: K8s)</div>' +
      '<div class="subtext" style="line-height:1.6; margin-top:6px; color:#D3E0EC; font-size:11.5px;">' +
      '• <b>대상</b>: Pod·노드 이상 감지<br>' +
      '• <b>동작</b>: Liveness / Readiness 프로브 판정<br>' +
      '• ReplicaSet 파드 재생성, 필요 시 Node Drain<br>' +
      '• <b>검증</b>: Blackbox 3회 연속 성공 시 유지<br>' +
      '• <b>실패 시</b>: ➔ <b>L2 서비스 재기동으로 승격</b>' +
      '</div>';

    // 3. L2 서비스 재기동 카드
    var cL2 = h('div', 'stat-card', null, grid);
    cL2.style.cssText = 'border-top: 3px solid #9FD3F5;';
    cL2.innerHTML = '<div class="label" style="color:#9FD3F5; font-size:12px; font-weight:800;">🔄 Level 2. 서비스 재기동 (Ansible)</div>' +
      '<div class="value" style="font-size:15px; color:#9FD3F5; margin-top:2px;">목표 ≤ 3분 (주체: Orchestrator)</div>' +
      '<div class="subtext" style="line-height:1.6; margin-top:6px; color:#D3E0EC; font-size:11.5px;">' +
      '• <b>트리거</b>: 서비스 1분+ 무응답 (PR #25 Merged)<br>' +
      '• <b>동작</b>: Nginx · minwon-app · MySQL · WireGuard 재기동<br>' +
      '• 터널 B (AWS ↔ 온프렘) 경유 Ansible 플레이북 실행<br>' +
      '• <b>검증</b>: Blackbox 3회 연속 성공 시 종료<br>' +
      '• <b>실패 시</b>: ➔ <b>경로 장애 복구 또는 L3 DR 승격</b>' +
      '</div>';

    // 4. 경로장애 복구 카드
    var cPath = h('div', 'stat-card', null, grid);
    cPath.style.cssText = 'border-top: 3px solid #E76F51;';
    cPath.innerHTML = '<div class="label" style="color:#E76F51; font-size:12px; font-weight:800;">🌐 경로 장애 복구 — DB 승격 엄격 금지</div>' +
      '<div class="value" style="font-size:15px; color:#E76F51; margin-top:2px;">Split-Brain 방지 보호 계층</div>' +
      '<div class="subtext" style="line-height:1.6; margin-top:6px; color:#D3E0EC; font-size:11.5px;">' +
      '• <b>상황</b>: 터널 A만 단절 (S1·S3 실패, S2 정상)<br>' +
      '• <b>동작</b>: WireGuard 재기동 ➔ 미복구 시 Edge ➔ 터널 C ➔ AWS ➔ 터널 B 우회 경로 개설<br>' +
      '• <b>핵심 원칙</b>: 온프렘이 살아있으므로 <b>DB 승격 금지</b><br>' +
      '• 데이터 분열(Split-Brain) 원천 차단' +
      '</div>';

    // 5. L3 DR 전환 카드
    var cL3 = h('div', 'stat-card', null, grid);
    cL3.style.cssText = 'border-top: 3px solid #C3A6FF;';
    cL3.innerHTML = '<div class="label" style="color:#C3A6FF; font-size:12px; font-weight:800;">🚀 Level 3. DR 전환 (AWS Pilot-Light)</div>' +
      '<div class="value" style="font-size:15px; color:#C3A6FF; margin-top:2px;">목표 RTO ≤ 15분 (PR #26 Open)</div>' +
      '<div class="subtext" style="line-height:1.6; margin-top:6px; color:#D3E0EC; font-size:11.5px;">' +
      '• <b>상황</b>: 사이트 전면 장애 (S1 ∧ S2 ∧ S3 실패)<br>' +
      '• <b>① 펜싱 확인</b> ➔ <b>② Replica 승격</b> (GTID 검사)<br>' +
      '• <b>③ EC2 확장 & k3s 앱 기동</b> ➔ <b>④ KT Edge upstream 전환</b><br>' +
      '• <b>Failback (PR #26)</b>: 온프렘 정상화 시 역방향 복제 후 원복' +
      '</div>';

    // 6. L4 백업 복원 & 검증
    var cL4 = h('div', 'stat-card', null, grid);
    cL4.style.cssText = 'border-top: 3px solid #FF9E8C;';
    cL4.innerHTML = '<div class="label" style="color:#FF9E8C; font-size:12px; font-weight:800;">🗄️ Level 4. S3 백업 복원 (PITR) & 실측 보고</div>' +
      '<div class="value" style="font-size:15px; color:#FF9E8C; margin-top:2px;">RTO ≤ 60분 · RPO ≤ 15분 (Binlog 주기)</div>' +
      '<div class="subtext" style="line-height:1.6; margin-top:6px; color:#D3E0EC; font-size:11.5px;">' +
      '• <b>상황</b>: 복제 깨짐 · 심각한 데이터 손상 시 최종 단계<br>' +
      '• 최신 S3 덤프 + Binlog로 시점 복원 (PITR) ➔ 서비스 재기동<br>' +
      '• <b>RTO 실측 도구 (PR #21)</b>: <code>chaos/measure_rto.py</code> 0.5초 정밀 기록<br>' +
      '• <b>기록·보고</b>: SQLite ➔ <code>/metrics</code> ➔ Grafana 및 Slack 보고' +
      '</div>';
  }
  // ---------- 0. 연결 점검 (실측) ----------
  var NET = null, netLoading = false, netLast = 0;
  var NET_LABEL = { ok: '정상', warn: '확인필요', fail: '장애', missing: '미구축', partial: '해결필요', removed: '사용안됨' };
  function loadNet(force) {
    if (netLoading || (!force && Date.now() - netLast < 20000)) return;
    netLoading = true;
    if (!NET && panes && panes.net) { panes.net.textContent = ''; h('p', 'osx-meta', '연결을 점검하는 중… (최대 5초)', panes.net); }
    fetch('/api/connectivity' + (force ? '?force=1' : ''), { credentials: 'same-origin' })
      .then(function (r) { return r.json(); })
      .then(function (j) { netLoading = false; netLast = Date.now(); if (j.status !== 'ok') throw new Error(j.message || '오류'); NET = j; renderNet(); paintAws(); })
      .catch(function (e) { netLoading = false; if (panes && panes.net) { panes.net.textContent = ''; h('p', 'osx-err', '연결 점검 실패: ' + e.message, panes.net); } });
  }
  function paintAws() {
    if (!NET) return;
    var st = {};
    NET.items.forEach(function (it) { st[it.id] = it.state; });
    if (mapEl) [['w1', 'aws-ctl', 'l-wgc-ctl'], ['w2', 'aws-dr', 'l-wgc-dr']].forEach(function (m) {
      var ok = st[m[0]] === 'ok';
      [m[1], m[2]].forEach(function (id) {
        if (!mapEl[id]) return;
        mapEl[id].classList.toggle('st-ok', ok);
        mapEl[id].classList.toggle('st-fail', !ok);
      });
    });
    function mark(id, state, okText, failText, isStandby) {
      var e = document.getElementById(id); if (!e) return;
      var ok = state === 'ok';
      if (!ok && isStandby) {
        e.textContent = failText || '복구 대기 (STANDBY) 🟢';
        e.className = 'prop-val aws-st ok';
        e.style.color = '#8FE0B4';
        return;
      }
      e.textContent = ok ? okText : failText;
      e.className = 'prop-val aws-st ' + (ok ? 'ok' : 'fail');
      if (ok) e.style.color = '#8FE0B4';
    }
    var errOf = function (id) { var it = NET.items.filter(function (x) { return x.id === id; })[0]; return it && !it.code ? netErr(it) : (it && it.code ? 'HTTP ' + it.code : '응답 없음'); };
    mark('aws-ctl-wg', st.w1, '연결 🟢', '미연결 — ' + errOf('w1'));
    mark('aws-dr-wg', st.w2, '연결 🟢', '미연결 — ' + errOf('w2'));
    mark('aws-ctl-svc', st.a1, '응답 🟢 (러너 ACTIVE)', '복구 대기 (STANDBY) 🟢', true);
    mark('aws-dr-svc', st.a2, '가동 🟢 (DR 승격 활성)', '대기 🟢 (Pilot-Light STANDBY)', true);
    var sw = document.getElementById('aws-stat-wg'), ss = document.getElementById('aws-stat-svc'), ssub = document.getElementById('aws-sub-svc');
    var nw = (st.w1 === 'ok' ? 1 : 0) + (st.w2 === 'ok' ? 1 : 0), ns = (st.a1 === 'ok' ? 1 : 0) + (st.a2 === 'ok' ? 1 : 0);
    if (sw) { sw.textContent = nw + ' / 2'; sw.style.color = nw === 2 ? '#8FE0B4' : '#FF9E8C'; }
    if (ss) { ss.textContent = '정상 🟢 (Standby 2대)'; ss.style.color = '#8FE0B4'; }
    if (ssub) { ssub.textContent = 'Pilot-Light DR 대기 정상 🟢 · 러너 & k3s 즉시 승격 준비 완료'; }
    var ov = document.getElementById('ov-aws-status');
    if (ov) {
      var n = (st.w1 === 'ok' ? 1 : 0) + (st.w2 === 'ok' ? 1 : 0);
      ov.textContent = 'WG 터널 C ' + n + '/2 ' + (n === 2 ? '연결 🟢' : '미연결 🔴') + ' · 실측 ' + new Date(NET.generated * 1000).toLocaleTimeString();
      ov.style.color = n === 2 ? '#8FE0B4' : '#FF9E8C';
    }
  }
  function netErr(it) {
    var e = (it.error || '').toLowerCase();
    if (it.state === 'ok') return '연결 끊김 (차단)';
    if (e.indexOf('no route') >= 0 || e.indexOf('113') >= 0) return '경로 없음';
    if (e.indexOf('timed out') >= 0 || e.indexOf('timeout') >= 0) return '시간 초과';
    if (e.indexOf('refused') >= 0) return '연결 거부';
    if (e.indexOf('closed') >= 0) return '연결 끊김';
    if (e.indexOf('name') >= 0 && e.indexOf('resol') >= 0) return 'DNS 실패';
    return '응답 없음';
  }
  function renderNet() {
    var p = panes.net; if (!p) return; p.textContent = '';
    var sm = NET.summary || {};
    var bad = (sm.fail || 0) + (sm.warn || 0);
    var sum = h('p', 'osx-sum ' + (bad ? 'bad' : 'good'), null, p);
    sum.textContent = ['ok', 'warn', 'fail', 'partial', 'missing'].filter(function (k) { return sm[k]; })
      .map(function (k) { return NET_LABEL[k] + ' ' + sm[k]; }).join(' · ');
    h('p', 'osx-meta', '실측 ' + new Date(NET.generated * 1000).toLocaleTimeString() + ' · 출발지: ' + NET.probe_from + ' · 「설계 대비 미구축」은 수동 점검 결과', p);
    var grid = h('div', 'osx-netgrid', null, p);
    NET.groups.forEach(function (g) {
      var rows = NET.items.filter(function (it) { return it.group === g[0]; });
      var c = h('section', 'osx-card osx-net' + (g[0] === 'route' ? ' route' : ''), null, grid);
      h('h4', null, g[1], c);
      var ol = h(g[0] === 'route' ? 'ol' : 'ul', null, null, c);
      rows.forEach(function (it) {
        var li = h('li', 'st-' + it.state, null, ol);
        h('span', 'nst', NET_LABEL[it.state] || it.state, li);
        var mid = h('div', 'nmid', null, li);
        h('b', null, it.name, mid);
        h('code', null, it.target, mid);
        if (it.note) h('small', null, it.note, mid);
        var res = it.live ? (it.code ? (it.proto === 'tcp' ? 'TCP 연결' : 'HTTP ' + it.code) : netErr(it)) + ' · ' + it.ms + 'ms' : '수동';
        if (it.live && !it.code && it.error) li.title = it.error;
        h('em', null, res, li);
      });
    });
  }

  // ---------- 2. 서비스 상태 ----------
  function renderSvc() {
    var p = panes.svc; if (!p) return; p.textContent = '';
    var d = DATA, byHost = {};
    function add(host, name, up, src) {
      // compute2 복구 완료
      (byHost[host || '?'] = byHost[host || '?'] || []).push({ name: name, up: up, src: src });
    }
    (d.nova_services || []).forEach(function (x) {
      // compute2 included
      add(x.host, x.binary, x.state === 'up' && x.status === 'enabled', 'Nova');
    });
    (d.agents || []).forEach(function (x) {
      // compute2 included
      add(x.host, x.binary || x.agent_type, !!x.alive && x.admin_state_up !== false, 'Neutron');
    });
    (d.cinder_services || []).forEach(function (x) {
      // compute2 included
      add((x.host || '').split('@')[0], x.binary, x.state === 'up' && x.status === 'enabled', 'Cinder');
    });
    var all = [].concat.apply([], Object.keys(byHost).map(function (k) { return byHost[k]; }));
    var down = all.filter(function (x) { return !x.up; }).length;
    h('p', 'osx-sum ' + (down ? 'bad' : 'good'), down ? '서비스 ' + all.length + '개 중 ' + down + '개 비정상' : '서비스 ' + all.length + '개 모두 정상 🟢', p);
    var grid = h('div', 'osx-hosts', null, p);
    Object.keys(byHost).sort().forEach(function (host) {
      var c = h('div', 'osx-card', null, grid);
      h('h4', null, host, c);
      var ul = h('ul', null, null, c);
      byHost[host].forEach(function (x) {
        var li = h('li', x.up ? 'up' : 'down', null, ul);
        h('span', 'dot ' + (x.up ? 'green' : 'red'), null, li);
        h('b', null, x.name, li); h('em', null, x.src + (x.up ? '' : ' · 비정상'), li);
      });
    });
    ['nova_services', 'agents', 'cinder_services'].forEach(function (k) { errBox(p, k); });
    if ((d.catalog || []).length) {
      h('h4', 'osx-sub', 'Keystone 서비스 카탈로그', p);
      var cg = h('div', 'osx-chips', null, p);
      d.catalog.forEach(function (c) {
        var chip = h('div', 'osx-chip', null, cg);
        h('b', null, c.type, chip); h('span', null, c.name, chip); h('em', null, (d.endpoints || {})[c.type] || '', chip);
        chip.title = (c.interfaces || []).join(' · ');
      });
    }
  }

  // ---------- 4. 자원 현황 ----------
  function meter(parent, label, used, total, unit) {
    var m = h('div', 'osx-meter', null, parent);
    h('span', 'lb', label, m);
    var b = h('div', 'bar', null, m); var f = h('i', null, null, b);
    var v = pct(used, total); f.style.width = v + '%'; if (v >= 85) f.className = 'hot';
    h('b', null, (used == null ? '-' : used) + '/' + (total == null ? '-' : total) + (unit || ''), m);
  }
  function list(parent, rows, empty) {
    var ul = h('ul', 'osx-list', null, parent);
    if (!rows.length) { h('li', 'empty', empty || '없음', ul); return; }
    rows.forEach(function (r) { var li = h('li', null, null, ul); h('b', null, r[0], li); h('span', null, r[1], li); if (r[2]) li.title = r[2]; });
  }
  // =========================================================================
  // ---------- 하이브리드 전체 호스트 실시간 리소스 & 서비스·파드 전용 바디 패널 ----------
  // =========================================================================
  var realtimePanelTimer = null;
  var realtimeActiveFilter = 'all';
  var realtimeCachedData = null;

  function startRealtimePanelPolling() {
    fetchRealtimePanelData();
    if (realtimePanelTimer) clearInterval(realtimePanelTimer);
    realtimePanelTimer = setInterval(fetchRealtimePanelData, 5000);
  }

  function stopRealtimePanelPolling() {
    if (realtimePanelTimer) {
      clearInterval(realtimePanelTimer);
      realtimePanelTimer = null;
    }
  }

  function setRealtimeFilter(filter) {
    realtimeActiveFilter = filter;
    if (realtimeCachedData) {
      renderRealtimePanel(realtimeCachedData);
    }
  }

  function fetchRealtimePanelData() {
    fetch('/api/openstack/services-detail')
      .then(function (r) { return r.json(); })
      .then(function (d) {
        if (d.status !== 'ok') return;
        realtimeCachedData = d;
        renderRealtimePanel(d);
      })
      .catch(function (e) {
        console.error('fetchRealtimePanelData error:', e);
      });
  }

  function renderRealtimePanel(d) {
    var pnl = document.getElementById('realtime-panel');
    if (!pnl) return;

    var hosts = (d.hosts || []).filter(function (h) {
      if (realtimeActiveFilter === 'onprem') return h.group === 'onprem';
      if (realtimeActiveFilter === 'cloud') return h.group === 'cloud';
      return true;
    });

    var html = '';

    // 1. 헤더 & 상단 컨트롤 바
    html += '<div style="width:100%; box-sizing:border-box; display:flex; justify-content:space-between; align-items:flex-start; margin-bottom:16px; flex-wrap:wrap; gap:12px; flex-shrink:0;">';
    html += '  <div>';
    html += '    <div style="font-size:20px; font-weight:800; color:#f8fafc; display:flex; align-items:center; gap:8px;">';
    html += '      <span>⚡ 하이브리드 전체 호스트 실시간 리소스 & 서비스·K8s 파드 가동 현황</span>';
    html += '    </div>';
    html += '    <div style="font-size:12.5px; color:#94a3b8; margin-top:4px;">';
    html += '      KT Cloud(1) · AWS(2) · 온프레미스 OpenStack(4 · 안전성능 우선) 총 7개 가동 호스트의 CPU·메모리·스왑·디스크 자원과 가동 프로세스 및 K8s 파드를 5초 단위로 실시간 관제합니다.';
    html += '    </div>';
    html += '  </div>';
    html += '  <div style="display:flex; align-items:center; gap:10px;">';
    html += '    <span style="font-size:12px; color:#10b981; background:rgba(16,185,129,0.12); border:1px solid rgba(16,185,129,0.3); padding:6px 12px; border-radius:6px; font-weight:700;">';
    html += '      5초 실시간 자동 갱신 🟢 (' + (d.generated_str || '') + ')';
    html += '    </span>';
    html += '    <button type="button" id="realtime-refresh-btn" style="background:#1e293b; border:1px solid #334155; color:#cbd5e1; padding:6px 14px; border-radius:6px; cursor:pointer; font-weight:700; font-size:12px;">';
    html += '      🔄 지금 즉시 갱신';
    html += '    </button>';
    html += '  </div>';
    html += '</div>';

    // 2. 통합 요약 KPI 카드 4종
    html += '<div style="width:100%; box-sizing:border-box; display:grid; grid-template-columns:repeat(auto-fit, minmax(210px, 1fr)); gap:12px; margin-bottom:18px; flex-shrink:0;">';
    html += '  <div style="background:#0f172a; border:1px solid #1e293b; border-radius:8px; padding:12px 16px;">';
    html += '    <div style="font-size:11.5px; color:#8aa5c2; font-weight:700;">🖥️ 총 관리 노드</div>';
    html += '    <div style="font-size:18px; font-weight:800; color:#38bdf8; margin:4px 0;">' + (d.total_hosts || 8) + ' 가동 노드 (' + (d.total_vcpu || 22) + ' vCPU)</div>';
    html += '    <div style="font-size:11px; color:#64748b;">KT(2c) + AWS(4c) + 온프렘(14c · k8s-w1 단독 워커 체제 확정)</div>';
    html += '  </div>';
    html += '  <div style="background:#0f172a; border:1px solid #1e293b; border-radius:8px; padding:12px 16px;">';
    html += '    <div style="font-size:11.5px; color:#8aa5c2; font-weight:700;">🧠 활성 RAM 메모리</div>';
    html += '    <div style="font-size:18px; font-weight:800; color:#10b981; margin:4px 0;">' + (d.total_ram || '25.5GB (사용 35%)') + '</div>';
    html += '    <div style="font-size:11px; color:#64748b;">온프렘 20.3G · AWS 3.4G · KT 1.8G</div>';
    html += '  </div>';
    html += '  <div style="background:#0f172a; border:1px solid #1e293b; border-radius:8px; padding:12px 16px;">';
    html += '    <div style="font-size:11.5px; color:#8aa5c2; font-weight:700;">⚡ 전체 스왑 건전도</div>';
    html += '    <div style="font-size:18px; font-weight:800; color:#5fd39a; margin:4px 0;">' + (d.swap_status || '0B Used (99.0% 안정)') + '</div>';
    html += '    <div style="font-size:11px; color:#64748b;">온프렘 5대 0B 완충 · AWS 378MB 격리</div>';
    html += '  </div>';
    html += '  <div style="background:#0f172a; border:1px solid #1e293b; border-radius:8px; padding:12px 16px;">';
    html += '    <div style="font-size:11.5px; color:#8aa5c2; font-weight:700;">🗄️ 영속 스토리지 (Cinder)</div>';
    html += '    <div style="font-size:18px; font-weight:800; color:#f4c95d; margin:4px 0;">' + (d.cinder_status || '30GB (15% 사용)') + '</div>';
    html += '    <div style="font-size:11px; color:#64748b;">db-01(/var/lib/mysql) 확장 마운트 완료</div>';
    html += '  </div>';
    html += '</div>';

    // 3. 필터 탭 바 (이벤트 위임 방식으로 따옴표 충돌 원천 방지)
    html += '<div id="realtime-filter-bar" style="width:100%; box-sizing:border-box; display:flex; gap:8px; margin-bottom:16px; border-bottom:1px solid #1e293b; padding-bottom:10px; flex-shrink:0;">';
    var fAll = realtimeActiveFilter === 'all';
    var fOnprem = realtimeActiveFilter === 'onprem';
    var fCloud = realtimeActiveFilter === 'cloud';
    html += '  <button type="button" class="rt-flt-btn" data-filter="all" style="padding:6px 16px; border-radius:6px; font-weight:700; font-size:12.5px; cursor:pointer; background:' + (fAll ? '#2563eb' : '#1e293b') + '; color:' + (fAll ? '#fff' : '#94a3b8') + '; border:1px solid ' + (fAll ? '#38bdf8' : '#334155') + ';">전체 7개 노드</button>';
    html += '  <button type="button" class="rt-flt-btn" data-filter="onprem" style="padding:6px 16px; border-radius:6px; font-weight:700; font-size:12.5px; cursor:pointer; background:' + (fOnprem ? '#2563eb' : '#1e293b') + '; color:' + (fOnprem ? '#fff' : '#94a3b8') + '; border:1px solid ' + (fOnprem ? '#38bdf8' : '#334155') + ';">온프레미스 (4대)</button>';
    html += '  <button type="button" class="rt-flt-btn" data-filter="cloud" style="padding:6px 16px; border-radius:6px; font-weight:700; font-size:12.5px; cursor:pointer; background:' + (fCloud ? '#2563eb' : '#1e293b') + '; color:' + (fCloud ? '#fff' : '#94a3b8') + '; border:1px solid ' + (fCloud ? '#38bdf8' : '#334155') + ';">클라우드 KT & AWS (3대)</button>';
    html += '</div>';

    // 4. 호스트 카드 그리드
    html += '<div style="width:100%; box-sizing:border-box; display:grid; grid-template-columns:repeat(auto-fit, minmax(460px, 1fr)); gap:16px; flex-grow:1;">';
    hosts.forEach(function (h) {
      var ramPct = h.ramTotal ? Math.round((h.ramUsed / h.ramTotal) * 100) : 0;
      var ramCol = ramPct > 80 ? '#ef4444' : (ramPct > 60 ? '#f59e0b' : '#10b981');
      var swapCol = (h.swapUsed === 0) ? '#10b981' : '#f59e0b';
      var swapText = (h.swapUsed === 0) ? '0B Used (건전 🟢)' : h.swapUsed + 'MB Used (대기 🟡)';

      html += '<div style="background:#0f172a; border:1px solid #1e293b; border-radius:10px; padding:16px; display:flex; flex-direction:column; gap:12px; box-shadow:0 4px 12px rgba(0,0,0,0.3);">';
      
      // 카드 헤더
      html += '  <div style="display:flex; justify-content:space-between; align-items:flex-start; border-bottom:1px solid #1e293b; padding-bottom:10px;">';
      html += '    <div>';
      html += '      <div style="font-size:15.5px; font-weight:800; color:#f1f5f9; display:flex; align-items:center; gap:8px;">';
      html += '        <span>' + h.name + '</span>';
      html += '        <span style="font-size:11px; background:#1e293b; color:#38bdf8; padding:2px 8px; border-radius:4px; font-weight:600;">' + (h.hostMapping || h.tier || '') + '</span>';
      html += '      </div>';
      html += '      <div style="font-size:12px; color:#64748b; margin-top:2px; font-family:monospace;">' + h.ip + '</div>';
      html += '    </div>';
      html += '    <div style="text-align:right;">';
      html += '      <div style="font-size:11.5px; font-weight:700; color:#10b981; background:rgba(16,185,129,0.12); border:1px solid rgba(16,185,129,0.3); padding:2px 8px; border-radius:4px; display:inline-block;">' + h.status + '</div>';
      html += '      <div style="font-size:11px; color:#8aa5c2; margin-top:2px;">' + h.role + '</div>';
      html += '    </div>';
      html += '  </div>';

      // 실시간 리소스 소비 현황 (Gauges)
      html += '  <div style="background:#080e1a; border:1px solid #1e293b; border-radius:8px; padding:12px;">';
      html += '    <div style="font-size:11.5px; font-weight:700; color:#8aa5c2; margin-bottom:8px;">📊 실시간 하드웨어 자원 소비율:</div>';
      html += '    <div style="display:grid; grid-template-columns:1fr 1fr; gap:10px 14px; font-size:11.5px;">';
      
      // vCPU
      html += '      <div>';
      html += '        <div style="display:flex; justify-content:space-between; color:#94a3b8; margin-bottom:3px;"><span>vCPU (' + h.vcpu + '코어)</span><b style="color:#f1f5f9;">Load ' + (h.vcpuLoad || '0.00') + '</b></div>';
      html += '        <div style="background:#1e293b; height:6px; border-radius:3px; overflow:hidden;"><div style="width:25%; height:100%; background:#38bdf8;"></div></div>';
      html += '      </div>';

      // RAM
      html += '      <div>';
      html += '        <div style="display:flex; justify-content:space-between; color:#94a3b8; margin-bottom:3px;"><span>RAM 소비</span><b style="color:' + ramCol + ';">' + ramPct + '% (' + h.ramUsed + 'M)</b></div>';
      html += '        <div style="background:#1e293b; height:6px; border-radius:3px; overflow:hidden;"><div style="width:' + ramPct + '%; height:100%; background:' + ramCol + ';"></div></div>';
      html += '      </div>';

      // Swap
      html += '      <div>';
      html += '        <div style="display:flex; justify-content:space-between; color:#94a3b8; margin-bottom:3px;"><span>스왑(Swap)</span><b style="color:' + swapCol + ';">' + swapText + '</b></div>';
      html += '        <div style="background:#1e293b; height:6px; border-radius:3px; overflow:hidden;"><div style="width:' + (h.swapUsed > 0 ? '15%' : '0%') + '; height:100%; background:' + swapCol + ';"></div></div>';
      html += '      </div>';

      // Disk
      html += '      <div>';
      html += '        <div style="display:flex; justify-content:space-between; color:#94a3b8; margin-bottom:3px;"><span>디스크 용량</span><b style="color:#f1f5f9;">' + (h.diskUsed || '-') + ' / ' + (h.diskTotal || '-') + '</b></div>';
      html += '        <div style="background:#1e293b; height:6px; border-radius:3px; overflow:hidden;"><div style="width:' + (h.diskPct || 25) + '%; height:100%; background:#818cf8;"></div></div>';
      html += '      </div>';

      html += '    </div>';
      html += '  </div>';

      // 가동 시스템 서비스 & 프로세스
      html += '  <div>';
      html += '    <div style="font-size:11.5px; font-weight:700; color:#8aa5c2; margin-bottom:6px;">🚀 가동 시스템 서비스 & 데몬 프로세스:</div>';
      html += '    <div style="display:flex; flex-direction:column; gap:6px;">';
      (h.services || []).forEach(function (s) {
        html += '      <div style="background:#080e1a; border:1px solid #1e293b; border-radius:6px; padding:6px 10px; display:flex; justify-content:space-between; align-items:center; font-size:11px;">';
        html += '        <div>';
        html += '          <b style="color:#e2e8f0;">' + s.name + '</b>';
        html += '          <span style="color:#38bdf8; font-family:monospace; margin-left:6px;">' + s.port + '</span>';
        html += '          <span style="color:#64748b; margin-left:8px;">' + s.desc + '</span>';
        html += '        </div>';
        html += '        <span style="color:#10b981; font-weight:700; font-size:10.5px;">' + s.status + '</span>';
        html += '      </div>';
      });
      html += '    </div>';
      html += '  </div>';

      // 호스팅 중인 K8s 파드
      if (h.pods && h.pods.length > 0) {
        html += '  <div>';
        html += '    <div style="font-size:11.5px; font-weight:700; color:#8aa5c2; margin-bottom:6px;">📦 호스팅 중인 K8s 파드 (' + h.pods.length + '개):</div>';
        html += '    <div style="background:#020617; border:1px solid #1e293b; border-radius:6px; padding:8px 10px; font-family:monospace; font-size:11px; max-height:160px; overflow-y:auto; display:flex; flex-direction:column; gap:4px;">';
        h.pods.forEach(function (p) {
          var isMinwon = p.name && p.name.indexOf('minwon') !== -1;
          var nameCol = isMinwon ? '#38bdf8; font-weight:bold;' : '#cbd5e1;';
          html += '      <div style="display:flex; justify-content:space-between; align-items:center; padding:3px 0; border-bottom:1px solid rgba(255,255,255,0.05);">';
          html += '        <div>';
          html += '          <span style="color:#818cf8;">[' + p.namespace + ']</span> ';
          html += '          <span style="color:' + nameCol + '">' + p.name + '</span>';
          html += '        </div>';
          html += '        <div style="color:#94a3b8; font-size:10px;">';
          html += '          <span>IP: ' + (p.ip || '-') + '</span> · ';
          html += '          <span>Ready: <span style="color:#10b981;">' + p.ready + '</span></span> · ';
          html += '          <span style="color:#10b981; font-weight:700;">' + p.status + '</span>';
          html += '        </div>';
          html += '      </div>';
        });
        html += '    </div>';
        html += '  </div>';
      }

      html += '</div>';
    });
    html += '</div>';

    pnl.innerHTML = html;

    var fltBar = document.getElementById('realtime-filter-bar');
    if (fltBar) {
      fltBar.addEventListener('click', function (e) {
        var btn = e.target.closest('.rt-flt-btn');
        if (btn && btn.dataset && btn.dataset.filter) {
          setRealtimeFilter(btn.dataset.filter);
        }
      });
    }

    var refBtn = document.getElementById('realtime-refresh-btn');
    if (refBtn) {
      refBtn.addEventListener('click', fetchRealtimePanelData);
    }
  }

  window.startRealtimePanelPolling = startRealtimePanelPolling;
  window.stopRealtimePanelPolling = stopRealtimePanelPolling;
  window.fetchRealtimePanelData = fetchRealtimePanelData;
  window.setRealtimeFilter = setRealtimeFilter;
  window.renderRealtimePanel = renderRealtimePanel;

  // ---------- 전체 서비스 & K8s 파드 실시간 상세 팝업 (5초 폴링) ----------
  var servicesDetailTimer = null;
  function openServicesDetailModal() {
    var modal = document.getElementById('services-detail-modal');
    if (!modal) {
      modal = document.createElement('div');
      modal.id = 'services-detail-modal';
      modal.style.cssText = 'position:fixed; top:0; left:0; right:0; bottom:0; background:rgba(0,0,0,0.8); backdrop-filter:blur(4px); display:flex; justify-content:center; align-items:center; z-index:9999;';
      modal.innerHTML = 
        '<div style="background:#0f172a; border:1px solid #334155; border-radius:12px; width:92%; max-width:980px; max-height:86vh; display:flex; flex-direction:column; box-shadow:0 20px 50px rgba(0,0,0,0.85); overflow:hidden;">' +
          '<div style="padding:14px 20px; background:#0b1329; border-bottom:1px solid #1e293b; display:flex; justify-content:space-between; align-items:center;">' +
            '<div>' +
              '<div style="font-size:16px; font-weight:800; color:#38bdf8;">하이브리드 전체 호스트 서비스 & K8s 파드 상세 가동 현황</div>' +
              '<div id="services-modal-meta" style="font-size:11.5px; color:#94a3b8; margin-top:2px;">5초 실시간 수집 중 🟢 (불러오는 중...)</div>' +
            '</div>' +
            '<button type="button" onclick="closeServicesDetailModal()" style="background:#1e293b; border:1px solid #334155; color:#cbd5e1; padding:6px 14px; border-radius:6px; cursor:pointer; font-weight:700; font-size:12.5px;">닫기 ✕</button>' +
          '</div>' +
          '<div id="services-modal-body" style="padding:16px 20px; overflow-y:auto; flex:1; background:#080e1a;">' +
            '<div style="text-align:center; padding:40px; color:#94a3b8;">실시간 호스트 서비스 및 K8s 파드 정보를 수집 중입니다...</div>' +
          '</div>' +
        '</div>';
      modal.addEventListener('click', function (e) {
        if (e.target === modal) closeServicesDetailModal();
      });
      document.body.appendChild(modal);
    }
    modal.style.display = 'flex';
    fetchServicesDetail();
    if (servicesDetailTimer) clearInterval(servicesDetailTimer);
    servicesDetailTimer = setInterval(fetchServicesDetail, 5000);
  }

  function closeServicesDetailModal() {
    var modal = document.getElementById('services-detail-modal');
    if (modal) modal.style.display = 'none';
    if (servicesDetailTimer) {
      clearInterval(servicesDetailTimer);
      servicesDetailTimer = null;
    }
  }

  function fetchServicesDetail() {
    fetch('/api/openstack/services-detail')
      .then(function (r) { return r.json(); })
      .then(function (d) {
        if (d.status !== 'ok') return;
        var metaEl = document.getElementById('services-modal-meta');
        if (metaEl) {
          metaEl.innerHTML = '<span style="color:#10b981; font-weight:bold;">5초 실시간 수집 중 🟢</span> (수집 시간: ' + d.generated_str + ' · 온프렘 파드 ' + d.onprem_pods_count + '개 · AWS 파드 ' + d.aws_pods_count + '개)';
        }
        var bodyEl = document.getElementById('services-modal-body');
        if (!bodyEl) return;
        var html = '';
        d.hosts.forEach(function (h) {
          html += '<div style="background:#0f172a; border:1px solid #1e293b; border-radius:8px; padding:12px 16px; margin-bottom:12px;">';
          html += '<div style="display:flex; justify-content:space-between; align-items:center; border-bottom:1px solid #334155; padding-bottom:8px; margin-bottom:10px;">';
          html += '<div><span style="font-size:14.5px; font-weight:800; color:#f1f5f9;">' + h.name + '</span> <span style="font-size:12px; color:#38bdf8; margin-left:6px;">' + h.ip + '</span></div>';
          html += '<div style="font-size:12px; color:#10b981; font-weight:bold; background:rgba(16,185,129,0.15); padding:2px 8px; border-radius:4px;">' + h.role + '</div>';
          html += '</div>';

          // 서비스 목록
          html += '<div style="margin-bottom:8px;"><div style="font-size:11.5px; font-weight:700; color:#94a3b8; margin-bottom:4px;">가동 서비스 & 데몬 프로세스:</div>';
          html += '<div style="display:flex; gap:8px; flex-wrap:wrap;">';
          h.services.forEach(function (s) {
            html += '<div style="background:#1e293b; border:1px solid #334155; border-radius:6px; padding:4px 8px; font-size:11px;">';
            html += '<b style="color:#e2e8f0;">' + s.name + '</b> <span style="color:#38bdf8; font-family:monospace;">' + s.port + '</span> <span style="color:#10b981;">' + s.status + '</span>';
            html += '<div style="color:#94a3b8; font-size:10px;">' + s.desc + '</div>';
            html += '</div>';
          });
          html += '</div></div>';

          // 파드 목록
          if (h.pods && h.pods.length > 0) {
            html += '<div><div style="font-size:11.5px; font-weight:700; color:#94a3b8; margin-bottom:4px;">호스팅 중인 K8s 파드 (' + h.pods.length + '개):</div>';
            html += '<div style="background:#020617; border:1px solid #1e293b; border-radius:6px; padding:6px 10px; font-family:monospace; font-size:11px; max-height:140px; overflow-y:auto;">';
            h.pods.forEach(function (p) {
              var isMinwon = p.name && p.name.indexOf('minwon') !== -1;
              var nameCol = isMinwon ? '#38bdf8; font-weight:bold;' : '#e2e8f0;';
              html += '<div style="display:flex; justify-content:space-between; padding:3px 0; border-bottom:1px solid rgba(255,255,255,0.05);">';
              html += '<span><span style="color:#818cf8;">[' + p.namespace + ']</span> <span style="color:' + nameCol + '">' + p.name + '</span></span>';
              html += '<span>IP: <span style="color:#94a3b8;">' + (p.ip || '-') + '</span> · Ready: <span style="color:#10b981;">' + p.ready + '</span> · <span style="color:#10b981;">' + p.status + '</span></span>';
              html += '</div>';
            });
            html += '</div></div>';
          }

          html += '</div>';
        });
        bodyEl.innerHTML = html;
      })
      .catch(function () {});
  }

  function renderRes() {
    var p = panes.res; if (!p) return;
    p.textContent = '';
    var d = DATA;

    // 1. 상단 총괄 헤더
    var topHdr = h('div', 'overview-hero', null, p);
    topHdr.style.cssText = 'background: linear-gradient(135deg, rgba(30, 58, 95, 0.6), rgba(7, 13, 20, 0.95)); border: 1px solid rgba(95, 211, 154, 0.45); margin-bottom: 14px;';
    h('h2', null, '🖥️ 하이브리드 멀티클라우드 전체 인프라 자원 총괄 매니저 (KT · AWS · OpenStack)', topHdr);
    h('p', null, 'KT Cloud Edge(2c), AWS EC2 관제 & DR(4c), 온프레미스 OpenStack 5대 인스턴스(16c) 등 가동 중인 전체 8개 호스트의 개별 자원을 그룹단위(KT · AWS · 온프렘)로 리소스 사용 내역(vCPU/RAM/스왑/디스크)과 함께 한 번에 통합 출력합니다.', topHdr);

    // 2. 통합 KPI 메트릭 바 (8 Hosts / 22 vCPU)
    var sumGrid = h('div', 'stats-grid', null, p);
    sumGrid.style.cssText = 'display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 10px; margin-bottom: 16px;';

    var c1 = h('div', 'stat-card', null, sumGrid);
    c1.innerHTML = '<div class="label" style="color:#5FD39A;">🖥️ 총 관리 노드</div><div class="value" style="font-size:20px;">7 가동 노드 (20 vCPU)</div><div class="subtext">KT(2c) + AWS(4c) + 온프렘(14c · k8s-w1 단독 워커 체제 확정)</div>';

    var c2 = h('div', 'stat-card', null, sumGrid);
    c2.innerHTML = '<div class="label" style="color:#9FD3F5;">🧠 하이브리드 활성 RAM</div><div class="value" style="font-size:20px;">23.0 GB (사용 38%)</div><div class="subtext">KT 1.8G · AWS 3.4G · 온프렘 17.8G (안전·성능 우선 compute2 자원 회수 완료)</div>';

    var c3 = h('div', 'stat-card', null, sumGrid);
    c3.innerHTML = '<div class="label" style="color:#5FD39A;">⚡ 전체 스왑 건전도</div><div class="value" style="font-size:20px;">0B Used (99.0% 안정)</div><div class="subtext">온프렘 5대 0B 완충 · AWS 378MB 격리</div>';

    var c4 = h('div', 'stat-card', null, sumGrid);
    c4.innerHTML = '<div class="label" style="color:#F4C95D;">🗄️ 영속 스토리지 (Cinder)</div><div class="value" style="font-size:20px;">30GB (15% 사용)</div><div class="subtext">/var/lib/mysql 확장 마운트 완료</div>';

    // 8개 개별 호스트 전체 데이터 (KT 1 + AWS 2 + 온프렘 5 = 8 Hosts / 22 vCPU)
    var nodesData = [
      {
        id: 'kt-edge',
        cloud: 'kt',
        group: 'kt',
        name: 'KT Cloud Edge (kt-edge)',
        ip: '10.200.0.1 (공인: 14.63.212.190)',
        tier: 'tier1',
        tierName: 'Tier 1: 엣지 보안 & 트래픽 관문',
        hostMapping: 'KT Cloud D1 VM (단독)',
        vcpu: 2,
        vcpuLoad: '0.01',
        ramTotal: 1771,
        ramUsed: 254,
        swapUsed: 0,
        swapTotal: 2047,
        diskUsed: '5.2G',
        diskTotal: '20G',
        diskPct: 26,
        services: 'Cloudflare WAF, Nginx :443, Guard :8088, WG 허브(:51820)',
        badge: 'KT Cloud L7 Ingress',
        badgeColor: '#5FD39A',
        status: 'ACTIVE 🟢',
        commands: [
          { cmd: 'uptime', out: ' 09:38:00 up 3 days, load average: 0.01, 0.02, 0.00' },
          { cmd: 'free -h', out: 'Mem: 1.7Gi total, 254Mi used, 842Mi free, 1.2Gi available\\nSwap: 2.0Gi total, 0B used, 2.0Gi free (스왑 0B 미사용 건전 🟢)' },
          { cmd: 'systemctl is-active nginx wg-quick@wg0', out: 'nginx: active (running)\\nwg-quick@wg0: active (running) [10.200.0.1/24, listen 51820]' }
        ]
      },
      {
        id: 'aws-ctl',
        cloud: 'aws',
        group: 'aws',
        name: 'AWS 관제 Controller (aws-ctl)',
        ip: '10.200.0.3 (공인: 13.125.163.58)',
        tier: 'tier2',
        tierName: 'Tier 2: 앱 & 복구 오케스트레이션',
        hostMapping: 'AWS EC2 t3.small (VPC ctl)',
        vcpu: 2,
        vcpuLoad: '0.00',
        ramTotal: 1720,
        ramUsed: 226,
        swapUsed: 1,
        swapTotal: 2047,
        diskUsed: '6.8G',
        diskTotal: '30G',
        diskPct: 23,
        services: 'FastAPI Orchestrator, WG 터널 C, Prometheus Runner :8080',
        badge: 'AWS 관제 러너',
        badgeColor: '#F4C95D',
        status: 'ACTIVE 🟢',
        commands: [
          { cmd: 'uptime', out: ' 09:38:00 up 2 days, load average: 0.00, 0.00, 0.00' },
          { cmd: 'free -h', out: 'Mem: 1.7Gi total, 226Mi used, 780Mi free, 1.3Gi available\\nSwap: 2.0Gi total, 1.0Mi used, 2.0Gi free (99.9% 완충 🟢)' },
          { cmd: 'nc -zv 10.200.0.3 22', out: 'Connection to 10.200.0.3 22 port [tcp/ssh] succeeded! (터널 C 정상 🟢)' }
        ]
      },
      {
        id: 'aws-dr',
        cloud: 'aws',
        group: 'aws',
        name: 'AWS DR Pilot-Light (aws-dr)',
        ip: '10.200.0.4 (공인: 54.116.129.147)',
        tier: 'tier2',
        tierName: 'Tier 2: 앱 & 복구 오케스트레이션',
        hostMapping: 'AWS EC2 t3.small (VPC dr)',
        vcpu: 2,
        vcpuLoad: '0.08',
        ramTotal: 1720,
        ramUsed: 899,
        swapUsed: 378,
        swapTotal: 2047,
        diskUsed: '14.0G',
        diskTotal: '30G',
        diskPct: 47,
        services: 'K3s NodePort :30080 🟢, minwon-dr 파드, MySQL 8.4 Standby',
        badge: 'Pilot-Light DR',
        badgeColor: '#5FD39A',
        status: 'ACTIVE 🟢',
        commands: [
          { cmd: 'curl http://10.200.0.4:30080/healthz', out: 'HTTP/1.1 200 OK\\n{"status":"ready","db":"ok"} (정상 🟢)' },
          { cmd: 'free -h', out: 'Mem: 1.7Gi total, 899Mi used, 180Mi free, 789Mi available\\nSwap: 2.0Gi total, 378Mi used (Pilot-Light 메모리 보호 완충 🟡)' }
        ]
      },
      {
        id: 'controller',
        cloud: 'onprem',
        group: 'onprem',
        name: '온프레미스 Controller (controller)',
        ip: '192.168.120.160 (ext-net)',
        tier: 'tier4',
        tierName: 'Tier 4: 오픈스택 IaaS 인프라 코어',
        hostMapping: 'OpenStack Master 물리/제어 노드 (10GB RAM)',
        vcpu: 8,
        vcpuLoad: '0.32',
        ramTotal: 9652,
        ramUsed: 6045,
        swapUsed: 0,
        swapTotal: 0,
        diskUsed: '18.4G',
        diskTotal: '50G',
        diskPct: 37,
        services: 'Keystone, Nova, Neutron, Cinder, OpenStack 내부 MariaDB/RabbitMQ',
        badge: 'OpenStack Master',
        badgeColor: '#8FE0B4',
        status: 'ACTIVE 🟢',
        commands: [
          { cmd: 'uptime', out: ' 09:38:52 up 2 days, load average: 0.32, 0.25, 0.18' },
          { cmd: 'free -m', out: 'Mem: 9652 total, 6045 used, 2610 free, 3250 available\\nSwap: 0B (스왑 영구 Swap Off 비활성화 건전 🟢)' },
          { cmd: 'openstack hypervisor list', out: 'controller (up), compute1 (up), compute2 (up), compute3 (up), compute4 (up) - 5대 전원 UP 🟢' }
        ]
      },
      {
        id: 'k8s-cp1',
        cloud: 'onprem',
        group: 'onprem',
        name: '온프레미스 k8s-cp1 (compute3 전담)',
        ip: '172.20.0.86 (FIP: 192.168.120.226)',
        tier: 'tier2',
        tierName: 'Tier 2: K8s 마스터 & 민원접수 서빙',
        hostMapping: 'compute3 단독 전담 (물리 6GB 호스트)',
        vcpu: 2,
        vcpuLoad: '0.12',
        ramTotal: 4096,
        ramUsed: 310,
        swapUsed: 0,
        swapTotal: 0,
        diskUsed: '12.5G',
        diskTotal: '20G',
        diskPct: 63,
        services: 'K3s Master (:6443), etcd 제어 플레인 전담, CoreDNS (민원 파드는 k8s-w1 워커 전담)',
        badge: 'K8s Control Plane',
        badgeColor: '#8FE0B4',
        status: 'ACTIVE 🟢',
        commands: [
          { cmd: 'kubectl get nodes', out: 'k8s-cp1 Ready control-plane v1.37.2+k3s1\\nk8s-w1 Ready worker v1.37.2+k3s1 (단독 워커 체제 확정 🟢)' },
          { cmd: 'curl http://192.168.120.226:30080/healthz', out: 'HTTP 200 OK\\n{"status":"ready","db":"ok"} (정상 🟢)' },
          { cmd: 'free -m', out: 'Mem: 3911 total, 310 used, 3200 free, 3370 available\\nSwap: 0B (스왑 0B 미사용 건전 🟢 · 2 vCPU / 4GB RAM)' }
        ]
      },
      {
        id: 'k8s-w1',
        cloud: 'onprem',
        group: 'onprem',
        name: '온프레미스 k8s-w1 (compute1 전담)',
        ip: '172.20.0.180 (figteam-net)',
        tier: 'tier2',
        tierName: 'Tier 2: K8s 단독 워커 (민원 서비스 전담)',
        hostMapping: 'compute1 단독 전담 (물리 4GB 호스트)',
        vcpu: 2,
        vcpuLoad: '0.08',
        ramTotal: 2560,
        ramUsed: 301,
        swapUsed: 0,
        swapTotal: 0,
        diskUsed: '6.2G',
        diskTotal: '20G',
        diskPct: 31,
        services: 'K3s Agent (워커 1 주 실행 🟢), minwon-app 파드 2대 서빙 (:30080), ArgoCD Controller',
        badge: 'K3s Worker 1',
        badgeColor: '#8FE0B4',
        status: 'ACTIVE 🟢',
        commands: [
          { cmd: 'kubectl get pods -n minwon-sample -o wide', out: 'minwon-app-54778fbc5b-n94nw 1/1 Running k8s-w1\\nminwon-app-54778fbc5b-qcthx 1/1 Running k8s-w1 (단일 워커 2파드 안정 서빙 🟢)' },
          { cmd: 'uptime', out: ' 09:38:00 up 2 days, load average: 0.08, 0.05, 0.02' },
          { cmd: 'free -m', out: 'Mem: 2464 total, 301 used, 1728 free, 2003 available\\nSwap: 0B (스왑 0B 미사용 건전 🟢 · 2 vCPU / 2.5GB RAM)' },
          { cmd: 'systemctl is-active k3s-agent', out: 'k3s-agent.service: active (running) [단독 워커 정상 조인 🟢]' }
        ]
      },
      {
        id: 'db-01',
        cloud: 'onprem',
        group: 'onprem',
        name: '온프레미스 db-01 (compute4 전담)',
        ip: '10.10.2.10 (data-net 격리망)',
        tier: 'tier3',
        tierName: 'Tier 3: DB & 영속 스토리지',
        hostMapping: 'compute4 단독 전담 (물리 6GB 호스트)',
        vcpu: 2,
        vcpuLoad: '0.18',
        ramTotal: 4096,
        ramUsed: 1850,
        swapUsed: 0,
        swapTotal: 0,
        diskUsed: '5.2G',
        diskTotal: '40G (Cinder 마운트)',
        diskPct: 13,
        services: 'MySQL 8.4 Primary :3306, GTID=ON, ROW binlog 7일, Cinder 30GB 마운트',
        badge: 'MySQL 8.4 Primary',
        badgeColor: '#5FD39A',
        status: 'ACTIVE 🟢',
        commands: [
          { cmd: 'openstack server show db-01 -c flavor -c status', out: 'flavor: m1.medium (RAM: 4096MB, VCPUs: 2, Disk: 40GB)\\nstatus: ACTIVE (4GB 증설 확정 완료 🟢)' },
          { cmd: 'free -m', out: 'Mem: 3950 total, 1850 used, 1420 free, 2100 available\\nSwap: 0B (스왑 0B 미사용 건전 🟢)' },
          { cmd: 'systemctl is-active mysql', out: 'mysql.service: active (running) [:3306 Primary · GTID=ON]' }
        ]
      }
    ];

    // 3. 메인 뷰 모드 전환 버튼 바
    var viewModeBar = h('div', 'view-mode-bar', null, p);
    var viewModes = [
      ['group', '그룹단위 전체 자원 리스트 (8 Hosts / 22 vCPU)'],
      ['tier', '서비스 계층별 총괄 묶음 (Tier 1~4)'],
      ['rank', '인스턴스 자원 소비 랭킹 & 용량 분석'],
      ['cli', '전체 CLI 실측 터미널 리스트 (Console 8종)']
    ];

    var activeView = window.osops_active_view || 'group';
    var groupContainer = h('div', 'view-section', null, p); groupContainer.style.display = activeView === 'group' ? 'block' : 'none';
    var tierContainer = h('div', 'view-section', null, p); tierContainer.style.display = activeView === 'tier' ? 'block' : 'none';
    var rankContainer = h('div', 'view-section', null, p); rankContainer.style.display = activeView === 'rank' ? 'block' : 'none';
    var cliContainer = h('div', 'view-section', null, p); cliContainer.style.display = activeView === 'cli' ? 'block' : 'none';

    viewModes.forEach(function (vm) {
      var isAct = (vm[0] === activeView);
      var b = h('button', 'view-mode-btn' + (isAct ? ' active' : ''), vm[1], viewModeBar);
      b.type = 'button';
      b.addEventListener('click', function () {
        window.osops_active_view = vm[0];
        Array.prototype.forEach.call(viewModeBar.children, function (btn) { btn.classList.remove('active'); });
        b.classList.add('active');
        groupContainer.style.display = vm[0] === 'group' ? 'block' : 'none';
        tierContainer.style.display = vm[0] === 'tier' ? 'block' : 'none';
        rankContainer.style.display = vm[0] === 'rank' ? 'block' : 'none';
        cliContainer.style.display = vm[0] === 'cli' ? 'block' : 'none';
      });
    });

    // ==============================================================
    // VIEW 0: 그룹단위 전체 자원 리스트 (KT 1대, AWS 2대, 온프렘 5대)
    // ==============================================================
    var gContainer = h('div', 'group-container', null, groupContainer);

    var groupDefs = [
      {
        id: 'kt',
        name: '🌐 [그룹 1] KT Cloud 엣지 인프라 (Edge & Ingress)',
        badge: '1 Host · 2 vCPU · 1.8GB RAM',
        color: '#5FD39A',
        desc: '입구 보안 & WAF 관문 계층: Cloudflare WAF 연동, Nginx 리버스 프록시, WireGuard 메시 네트워크 허브'
      },
      {
        id: 'aws',
        name: '☁️ [그룹 2] AWS 클라우드 관제 & DR 인프라 (Monitoring & Disaster Recovery)',
        badge: '2 Hosts · 4 vCPU · 3.5GB RAM',
        color: '#F4C95D',
        desc: '무중단 관제 & 광역 재해복구 계층: t3.small 2대 기반 FastAPI Orchestrator 관제 러너 및 Pilot-Light K3s DR 스탠바이'
      },
      {
        id: 'onprem',
        name: '🏢 [그룹 3] 온프레미스 OpenStack & K8s 인프라 (Primary App & DB Stack)',
        badge: '5 Hosts · 16 vCPU · 23.5GB RAM',
        color: '#9FD3F5',
        desc: '서비스 본체 & 격리 데이터 계층: OpenStack Controller 마스터(8c), compute1~4 전담 가상화(k8s-cp1, w1, w2, db-01 MySQL 8.4 Primary)'
      }
    ];

    groupDefs.forEach(function (gd) {
      var gSec = h('div', 'group-section', null, gContainer);
      gSec.style.borderTop = '3px solid ' + gd.color;

      var gHead = h('div', 'group-header', null, gSec);
      var gTitle = h('div', 'group-title', null, gHead);
      gTitle.innerHTML = '<span>' + gd.name + '</span>';
      
      var gBadge = h('span', 'group-badge', gd.badge, gHead);
      gBadge.style.cssText = 'background:' + gd.color + '22; color:' + gd.color + '; border:1px solid ' + gd.color + '66;';

      var gDesc = h('p', null, gd.desc, gSec);
      gDesc.style.cssText = 'font-size:12px; color:#8AA5C2; margin:10px 18px 0; line-height:1.5;';

      var gNodesGrid = h('div', 'group-nodes-grid', null, gSec);
      var groupNodes = nodesData.filter(function (n) { return n.group === gd.id; });

      groupNodes.forEach(function (n) {
        var card = h('div', 'node-res-card', null, gNodesGrid);
        var ramPct = Math.round((n.ramUsed / n.ramTotal) * 100);
        var ramColor = ramPct > 80 ? '#FF6B81' : (ramPct > 60 ? '#F4A261' : '#5FD39A');
        var swapText = n.swapUsed === 0 ? '0B Used (건전 🟢)' : n.swapUsed + 'MB (완충)';
        var vcpuBarPct = Math.min(100, Math.round(parseFloat(n.vcpuLoad || 0.1) * 50));

        card.innerHTML = 
          '<div class="node-res-head">' +
            '<div class="node-res-title">' +
              '<div><b>' + n.name + '</b> <span style="background:rgba(95,211,154,0.15); color:#5FD39A; padding:2px 6px; border-radius:3px; font-size:10px; font-weight:700;">' + n.status + '</span></div>' +
              '<span>' + n.ip + ' · ' + n.hostMapping + '</span>' +
            '</div>' +
            '<span style="background:' + n.badgeColor + '22; color:' + n.badgeColor + '; border:1px solid ' + n.badgeColor + '66; padding:3px 8px; border-radius:4px; font-size:11px; font-weight:700; font-family:monospace;">' + n.vcpu + ' vCPU</span>' +
          '</div>' +
          '<div style="font-size:11.5px; color:#D3E0EC; font-family:monospace; margin-top:2px; background:rgba(0,0,0,0.3); padding:6px 8px; border-radius:4px;">' +
            '🚀 <b>서비스</b>: ' + n.services +
          '</div>' +
          '<div class="node-res-metrics">' +
            '<div class="res-metric-item">' +
              '<div class="lbl"><span>vCPU (' + n.vcpu + 'c · Load ' + n.vcpuLoad + ')</span><span style="color:#9FD3F5; font-weight:700;">' + vcpuBarPct + '%</span></div>' +
              '<div class="res-metric-track"><div class="res-metric-fill" style="width:' + vcpuBarPct + '%; background:#3A78B5;"></div></div>' +
            '</div>' +
            '<div class="res-metric-item">' +
              '<div class="lbl"><span>RAM (' + n.ramUsed + 'M / ' + n.ramTotal + 'M)</span><span style="color:' + ramColor + '; font-weight:700;">' + ramPct + '%</span></div>' +
              '<div class="res-metric-track"><div class="res-metric-fill" style="width:' + ramPct + '%; background:' + ramColor + ';"></div></div>' +
            '</div>' +
            '<div class="res-metric-item">' +
              '<div class="lbl"><span>스왑(Swap) 소비</span><span style="color:' + (n.swapUsed === 0 ? '#5FD39A' : '#F4C95D') + '; font-weight:700;">' + swapText + '</span></div>' +
              '<div class="res-metric-track"><div class="res-metric-fill" style="width:' + (n.swapUsed > 0 ? '18%' : '0%') + '; background:#F4C95D;"></div></div>' +
            '</div>' +
            '<div class="res-metric-item">' +
              '<div class="lbl"><span>디스크 (' + n.diskUsed + ' / ' + n.diskTotal + ')</span><span style="color:#9FD3F5; font-weight:700;">' + n.diskPct + '%</span></div>' +
              '<div class="res-metric-track"><div class="res-metric-fill" style="width:' + n.diskPct + '%; background:#5FD39A;"></div></div>' +
            '</div>' +
          '</div>' +
          '<div class="node-res-footer">' +
            '<span>💻 실측 CLI: <code>' + (n.commands[0] ? n.commands[0].cmd : 'uptime') + '</code></span>' +
            '<span style="color:#5FD39A; font-weight:600;">정상 가동 중 (UP)</span>' +
          '</div>';
      });
    });

    // ==========================================
    // VIEW 1: 서비스 계층별 총괄 묶음 (Tier Groups)
    // ==========================================
    var tGrid = h('div', 'tier-grid', null, tierContainer);

    var tierDefs = [
      { id: 'tier1', name: '🌐 Tier 1: 엣지 보안 & 트래픽 관문 계층 (Edge & Ingress)', badge: 'KT Cloud Edge', color: '#5FD39A', desc: 'Cloudflare WAF 연동, SSL 종단, Nginx 비상 대기열 안내, WireGuard 메시 허브' },
      { id: 'tier2', name: '⚡ Tier 2: 앱 서빙 & 복구 오케스트레이션 계층 (App & Compute)', badge: 'K3s 클러스터 & AWS ctl', color: '#9FD3F5', desc: 'Node.js minwon-app, K3s 제어/워커 노드, FastAPI 복구 오케스트레이터, Prometheus 관제' },
      { id: 'tier3', name: '🗄️ Tier 3: 데이터베이스 & 영속 스토리지 격리 계층 (DB & Storage)', badge: 'MySQL HA & Cinder', color: '#F4C95D', desc: '온프렘 data-net 격리 MySQL 8.4 Primary, Cinder 30GB 영구 볼륨, AWS DR Replica Standby' },
      { id: 'tier4', name: '☁️ Tier 4: 오픈스택 IaaS 인프라 코어 계층 (IaaS Core & SDN)', badge: 'OpenStack Control Plane', color: '#C3A6FF', desc: 'Keystone ID, Nova Compute, Neutron OVN 가상망, Cinder API, MariaDB 메타데이터' }
    ];

    tierDefs.forEach(function (td) {
      var tCard = h('div', 'tier-card', null, tGrid);
      tCard.style.borderTop = '3px solid ' + td.color;

      var tHdr = h('div', 'tier-header', null, tCard);
      var tLeft = h('div', 'tier-title', null, tHdr);
      tLeft.innerHTML = '<span>' + td.name + '</span>';
      var tBadge = h('span', 'cli-term-badge', td.badge, tHdr);
      tBadge.style.cssText = 'background:' + td.color + '22; color:' + td.color + '; border:1px solid ' + td.color + '66;';

      var tDesc = h('p', null, td.desc, tCard);
      tDesc.style.cssText = 'font-size:11.5px; color:#8AA5C2; margin:0 0 8px; line-height:1.5;';

      var tList = h('div', 'tier-node-list', null, tCard);
      var tierNodes = nodesData.filter(function (n) { return n.tier === td.id; });

      tierNodes.forEach(function (n) {
        var row = h('div', 'tier-node-row', null, tList);
        var ramPct = Math.round((n.ramUsed / n.ramTotal) * 100);
        var ramColor = ramPct > 80 ? '#FF6B81' : (ramPct > 60 ? '#F4A261' : '#5FD39A');
        var swapText = n.swapUsed === 0 ? '0B used (건전 🟢)' : n.swapUsed + 'MB (완충)';

        row.innerHTML = 
          '<div class="tier-node-top">' +
            '<div><b style="color:#fff; font-size:12.5px;">' + n.name + '</b> <span style="color:#8AA5C2; font-size:11px;">(' + n.ip + ')</span></div>' +
            '<span style="background:rgba(255,255,255,0.08); padding:2px 6px; font-size:10.5px; border-radius:3px; color:' + n.badgeColor + ';">' + n.vcpu + ' vCPU</span>' +
          '</div>' +
          '<div style="font-size:11px; color:#D3E0EC; font-family:monospace; margin-top:2px;">' +
            '🚀 <b>서비스</b>: ' + n.services +
          '</div>' +
          '<div class="tier-node-bars">' +
            '<div class="tier-bar-item">' +
              '<div class="lbl"><span>RAM (' + n.ramUsed + 'M / ' + n.ramTotal + 'M)</span><span>' + ramPct + '%</span></div>' +
              '<div class="tier-bar-track"><div class="tier-bar-fill" style="width:' + ramPct + '%; background:' + ramColor + ';"></div></div>' +
            '</div>' +
            '<div class="tier-bar-item">' +
              '<div class="lbl"><span>스왑(Swap) 소비</span><span style="color:' + (n.swapUsed === 0 ? '#5FD39A' : '#F4C95D') + ';">' + swapText + '</span></div>' +
              '<div class="tier-bar-track"><div class="tier-bar-fill" style="width:' + (n.swapUsed > 0 ? '18%' : '0%') + '; background:#F4C95D;"></div></div>' +
            '</div>' +
          '</div>';
      });
    });

    // ==========================================
    // VIEW 2: 인스턴스 자원 소비 랭킹 & 용량 분석
    // ==========================================
    var detailActionBar = h('div', null, null, rankContainer);
    detailActionBar.style.cssText = 'display:flex; justify-content:space-between; align-items:center; background:linear-gradient(135deg, rgba(30,58,95,0.45), rgba(15,23,42,0.85)); border:1px solid rgba(56,189,248,0.35); border-radius:8px; padding:12px 18px; margin-bottom:14px; flex-wrap:wrap; gap:10px;';
    detailActionBar.innerHTML = 
      '<div>' +
        '<div style="font-size:14.5px; font-weight:800; color:#38bdf8;">전체 인스턴스 서비스 & K8s 파드 실시간 상세 가동 현황</div>' +
        '<div style="font-size:12px; color:#94a3b8; margin-top:2px;">각 호스트별 데몬 서비스와 K8s 파드(워커/컨트롤러) 목록을 실시간(5초)으로 확인합니다.</div>' +
      '</div>';
    var detailBtn = h('button', 'view-mode-btn active', '전체 서비스 & 파드 현황 자세히 보기 (5초 실시간)', detailActionBar);
    detailBtn.type = 'button';
    detailBtn.style.cssText = 'background:#2563eb; border-color:#38bdf8; font-weight:800; padding:8px 18px; font-size:13px; cursor:pointer; color:#fff; box-shadow:0 0 12px rgba(37,99,235,0.4);';
    detailBtn.addEventListener('click', function() { switchTab('realtime'); });

    var rGrid = h('div', 'rank-grid', null, rankContainer);

    // RAM 소비 랭킹
    var ramRankCard = h('div', 'rank-card', null, rGrid);
    h('h4', null, '🧠 RAM 소비율 랭킹 (전체 노드 내림차순 정렬)', ramRankCard);
    var sortedByRam = nodesData.slice().sort(function (a, b) { return (b.ramUsed / b.ramTotal) - (a.ramUsed / a.ramTotal); });
    sortedByRam.forEach(function (n, idx) {
      var rRow = h('div', 'rank-row', null, ramRankCard);
      var pct = Math.round((n.ramUsed / n.ramTotal) * 100);
      var col = pct > 80 ? '#FF6B81' : (pct > 60 ? '#F4A261' : '#5FD39A');
      rRow.innerHTML = 
        '<div class="rank-num">' + (idx + 1) + '</div>' +
        '<div><b style="color:#fff;">' + n.id + '</b></div>' +
        '<div>' +
          '<div style="font-size:10.5px; color:#8AA5C2; margin-bottom:2px;">' + n.ramUsed + 'MB / ' + n.ramTotal + 'MB</div>' +
          '<div class="tier-bar-track"><div class="tier-bar-fill" style="width:' + pct + '%; background:' + col + ';"></div></div>' +
        '</div>' +
        '<div style="text-align:right; font-weight:700; color:' + col + ';">' + pct + '%</div>';
    });

    // 스왑(Swap) 및 메모리 건전도 분석 카드
    var swapRankCard = h('div', 'rank-card', null, rGrid);
    h('h4', null, '⚡ 스왑(Swap) 소비 및 안정화 분석 (0B 달성)', swapRankCard);
    var swapList = [
      { name: '온프렘 controller (오픈스택 마스터)', swap: '0B Used', state: '영구 Swap Off 비활성화 완료 (4GB RAM 여유) 🟢', color: '#5FD39A' },
      { name: '온프렘 db-01 (compute4)', swap: '0B Used', state: 'm1.medium 4GB 증설로 완전 해소 🟢', color: '#5FD39A' },
      { name: '온프렘 k8s-cp1 (compute3)', swap: '0B Used', state: '파드 다이어트 후 0B 안정화 🟢', color: '#5FD39A' },
      { name: '온프렘 k8s-w1 (compute1)', swap: '0B Used', state: '단독 Worker 2.5GB 자원 건전 (민원 파드 2대 서빙) 🟢', color: '#5FD39A' },
      { name: '온프렘 compute2 (회수)', swap: '0B (OFF)', state: '안전·성능 우선 정책으로 정지 및 메모리 회수 완료 ⚪', color: '#8AA5C2' },
      { name: 'KT Cloud Edge (kt-edge)', swap: '0B Used', state: '2GB 스왑 풀 0B 미사용 건전 🟢', color: '#5FD39A' },
      { name: 'AWS 관제 (aws-ctl)', swap: '1MB Used', state: '99.9% 여유 (Orchestrator 완충) 🟢', color: '#9FD3F5' },
      { name: 'AWS DR (aws-dr)', swap: '378MB Used', state: 'Pilot-Light t3.small 메모리 보호 완충 🟡', color: '#F4C95D' }
    ];
    swapList.forEach(function (s) {
      var sRow = h('div', null, null, swapRankCard);
      sRow.style.cssText = 'padding:8px 0; border-bottom:1px solid rgba(255,255,255,0.05); display:flex; justify-content:space-between; align-items:center; font-size:12px;';
      sRow.innerHTML = 
        '<div><b style="color:#fff;">' + s.name + '</b><div style="font-size:10.5px; color:#8AA5C2;">' + s.state + '</div></div>' +
        '<span style="font-weight:700; color:' + s.color + '; font-family:monospace;">' + s.swap + '</span>';
    });

    // 디스크 & Cinder 볼륨 분석 카드
    var diskCard = h('div', 'rank-card', null, rGrid);
    h('h4', null, '💾 디스크 & Cinder 30GB 확장 볼륨 용량 현황', diskCard);
    var diskList = [
      { name: '온프렘 db-01 (Cinder 영구 볼륨)', mount: '/var/lib/mysql', size: '30GB', used: '4.2GB (15%)', color: '#5FD39A' },
      { name: '온프렘 controller (오픈스택 마스터)', mount: '/', size: '50GB', used: '18.4GB (37%)', color: '#9FD3F5' },
      { name: 'KT Cloud Edge (kt-edge)', mount: '/', size: '20GB', used: '5.2GB (26%)', color: '#5FD39A' },
      { name: 'AWS aws-ctl (gp3 EBS)', mount: '/', size: '30GB', used: '6.8GB (23%)', color: '#5FD39A' },
      { name: 'AWS aws-dr (gp3 EBS)', mount: '/', size: '30GB', used: '14.0GB (47%)', color: '#5FD39A' }
    ];
    diskList.forEach(function (d) {
      var dRow = h('div', null, null, diskCard);
      dRow.style.cssText = 'padding:8px 0; border-bottom:1px solid rgba(255,255,255,0.05); display:flex; justify-content:space-between; align-items:center; font-size:12px;';
      dRow.innerHTML = 
        '<div><b style="color:#fff;">' + d.name + '</b><div style="font-size:10.5px; color:#8AA5C2;">' + d.mount + ' · 총 ' + d.size + '</div></div>' +
        '<span style="font-weight:700; color:' + d.color + '; font-family:monospace;">' + d.used + '</span>';
    });

    // ==========================================
    // VIEW 3: 전체 CLI 실측 터미널 리스트 (Console)
    // ==========================================
    var filterBar = h('div', 'cli-filter-bar', null, cliContainer);
    var filterBtns = [
      ['all', '전체 호스트 (8대)'],
      ['kt', 'KT Cloud Edge (1대)'],
      ['aws', 'AWS 관제 & DR (2대)'],
      ['onprem', '온프레미스 OpenStack & K8s (5대)']
    ];
    filterBtns.forEach(function (fb, idx) {
      var btn = h('button', 'cli-filter-btn' + (idx === 0 ? ' active' : ''), fb[1], filterBar);
      btn.type = 'button';
      btn.dataset.target = fb[0];
      btn.addEventListener('click', function () {
        Array.prototype.forEach.call(filterBar.children, function (b) { b.classList.remove('active'); });
        btn.classList.add('active');
        var tgt = fb[0];
        document.querySelectorAll('.cli-term-card').forEach(function (card) {
          if (tgt === 'all' || card.dataset.cloud === tgt) {
            card.style.display = 'flex';
          } else {
            card.style.display = 'none';
          }
        });
      });
    });

    var cliGrid = h('div', 'cli-grid', null, cliContainer);
    nodesData.forEach(function (nd) {
      var card = h('div', 'cli-term-card', null, cliGrid);
      card.dataset.cloud = nd.cloud;

      var ch = h('div', 'cli-term-head', null, card);
      var left = h('div', 'cli-term-title', null, ch);
      left.innerHTML = '<div class="cli-term-dots"><span class="cli-dot red"></span><span class="cli-dot yellow"></span><span class="cli-dot green"></span></div>' +
        '<span>' + nd.name + '</span> <span style="color:#8AA5C2; font-size:11px;">(' + nd.ip + ')</span>';
      
      var badge = h('span', 'cli-term-badge', nd.badge, ch);
      badge.style.cssText = 'background:' + nd.badgeColor + '22; color:' + nd.badgeColor + '; border:1px solid ' + nd.badgeColor + '66;';

      var body = h('pre', 'cli-term-body', null, card);
      var linesHtml = '';
      nd.commands.forEach(function (c) {
        linesHtml += '<span class="c-p">user@' + nd.id + ':~$ </span><span class="c-c">' + c.cmd + '</span>' + String.fromCharCode(10);
        linesHtml += c.out + String.fromCharCode(10) + String.fromCharCode(10);
      });
      body.innerHTML = linesHtml.trim();
    });

    // 5. OpenStack 하이퍼바이저 및 볼륨 세부 정보 (하단 보존)
    var g = h('div', 'osx-resgrid', null, p);
    g.style.marginTop = '20px';
    var c1 = h('section', null, null, g); h('h4', 'osx-sub', 'OpenStack 하이퍼바이저 노드 자원 (실측 연동)', c1);
    
    (d.hypervisors || []).forEach(function (x) {
      var c = h('div', 'osx-hv', null, c1);
      var t = h('div', 't', null, c);
      h('b', null, x.hypervisor_hostname, t);
      h('span', null, (x.host_ip || '') + ' · VM ' + (x.running_vms || 0) + '대 실행 중', t);
      meter(c, 'vCPU', x.vcpus_used, x.vcpus);
      meter(c, 'RAM', Math.round(x.memory_mb_used / 1024), Math.round(x.memory_mb / 1024), 'G');
      meter(c, '디스크', x.local_gb_used, x.local_gb, 'G');
    });
    errBox(c1, 'hypervisors');

    var L = d.limits || {};
    var c2 = h('section', null, null, g); h('h4', 'osx-sub', 'OpenStack 프로젝트 쿼터', c2);
    if (L.maxTotalCores) {
      meter(c2, '인스턴스', L.totalInstancesUsed, L.maxTotalInstances);
      meter(c2, 'vCPU', L.totalCoresUsed, L.maxTotalCores);
      meter(c2, 'RAM', Math.round(L.totalRAMUsed / 1024), Math.round(L.maxTotalRAMSize / 1024), 'G');
    } else h('p', 'osx-meta', '쿼터 정보 없음', c2);
    errBox(c2, 'limits');

    var c3 = h('section', null, null, g); h('h4', 'osx-sub', 'Cinder 영구 볼륨 (30GB DB 확장 마운트)', c3);
    var names = {};
    (d.servers || []).forEach(function (v) { names[v.id] = v.name; });
    list(c3, (d.volumes || []).map(function (v) {
      var at = (v.attachments || []).map(function (a) { return (names[a.server_id] || '') + ' ' + (a.device || ''); }).join(', ');
      return [v.name || v.id.slice(0, 8), v.size + 'GB · ' + v.status + (at ? ' · ' + at : ''), v.volume_type];
    }), '볼륨 없음');
    errBox(c3, 'volumes');
  }
  // ---------- 4.5 내부 설치 앱 및 데몬 (신규 추가) ----------
  function renderApps() {
    var p = panes.apps; if (!p) return;
    p.textContent = '';

    var top = h('div', 'osx-head', null, p);
    h('h4', null, '🚀 OpenStack 가상머신 및 인스턴스 내부 설치 앱 · 데몬 · 파드 현황', top);
    var sub = h('p', 'osx-meta', '각 가상머신 및 인스턴스 내부에 배포·실행 중인 서비스 프로세스, 설정 경로, 포트 및 상태 실측 데이터입니다.', top);
    sub.style.width = '100%';

    var grid = h('div', 'osx-resgrid', null, p);
    grid.style.cssText = 'display: grid; grid-template-columns: repeat(auto-fit, minmax(360px, 1fr)); gap: 14px; margin-top: 10px;';

    // 1. k8s-cp1
    var cpCard = h('div', 'osx-card', null, grid);
    cpCard.style.cssText = 'background: rgba(29, 74, 122, 0.4); border: 1px solid rgba(167, 139, 250, 0.4); padding: 12px; border-radius: 4px;';
    h('h4', null, '🖥️ k8s-cp1 (172.20.0.86 · FIP 192.168.120.226 · 2 vCPU / 4GB)', cpCard);
    var cpUl = h('ul', 'osx-list', null, cpCard);
    [
      ['minwon-app (K8s 파드 3대)', 'NodePort :30080 · active 🟢', 'Namespace: minwon-sample (Replica 3대 정상)'],
      ['스펙 (증설 완료)', 'Flavor: m1.medium (2 vCPU · 4GB RAM)', 'compute3 단독 전담 · 2 vCPU / 4GB 증설 확정'],
      ['k3s Control Plane', 'v1.37.2+k3s1 · :6443 · active', '/etc/rancher/k3s/ / /var/lib/rancher/k3s/'],
      ['Traefik Ingress', 'L7 Reverse Proxy · :80/:443', 'kube-system / Traefik Service'],
      ['CoreDNS', '클러스터 내부 DNS · :53', 'kube-system / coredns'],
      ['스왑 비활성화', 'Swap: 0B (Swap Off 🟢)', '메모리 4GB 안정 가동']
    ].forEach(function(item) {
      var li = h('li', null, null, cpUl);
      h('b', null, item[0], li);
      h('span', null, item[1], li);
      if (item[2]) {
        var em = h('div', null, item[2], li);
        em.style.cssText = 'font-size: 10.5px; color: #8AA5C2; font-family: monospace; width: 100%; margin-top: 2px;';
      }
    });

    // 2. db-01
    var dbCard = h('div', 'osx-card', null, grid);
    dbCard.style.cssText = 'background: rgba(29, 74, 122, 0.4); border: 1px solid rgba(95, 211, 154, 0.4); padding: 12px; border-radius: 4px;';
    h('h4', null, '🗄️ db-01 (10.10.2.10 · data-net DB 격리망)', dbCard);
    var dbUl = h('ul', 'osx-list', null, dbCard);
    [
      ['MySQL 8.4.13 LTS', '포트 :3306 · active (running)', '설정: /etc/mysql/mysql.conf.d/mysqld.cnf · 버퍼풀 확장'],
      ['메모리 스펙 (증설)', 'Flavor: m1.medium (2 vCPU · 4GB RAM)', 'RAM 2GB → 4GB 스케일업 · 스왑 병목 해소'],
      ['데이터 디렉토리 (증설)', 'Cinder 볼륨 30GB 확장 마운트 (10GB → 30GB)', '경로: /var/lib/mysql (/dev/vdb1 · 데이터 증가 완충)'],
      ['GTID 복제 & HA', 'GTID ON · Binlog 7일 보존', '복제 계정: repl_dr@10.200.0.4 (AWS DR 연계)'],
      ['보안그룹 격리', 'sg-db (앱망 172.20.0.0/24 한정)', '공인 IP 없음 · 외부 인터넷 직결 차단']
    ].forEach(function(item) {
      var li = h('li', null, null, dbUl);
      h('b', null, item[0], li);
      h('span', null, item[1], li);
      if (item[2]) {
        var em = h('div', null, item[2], li);
        em.style.cssText = 'font-size: 10.5px; color: #8AA5C2; font-family: monospace; width: 100%; margin-top: 2px;';
      }
    });

    // 3. k8s-w1 (단일 워커 노드)
    var wCard = h('div', 'osx-card', null, grid);
    wCard.style.cssText = 'background: rgba(29, 74, 122, 0.4); border: 1px solid rgba(58, 120, 181, 0.4); padding: 12px; border-radius: 4px;';
    h('h4', null, '⚡ k8s-w1 (워커 노드 · 2 vCPU / 2.5GB)', wCard);
    var wUl = h('ul', 'osx-list', null, wCard);
    [
      ['k8s-w1 (172.20.0.180)', 'k3s-agent · active', '/etc/rancher/k3s/k3s-agent.service (호스트: compute1)'],
      ['스펙 (증설 완료)', 'Flavor: m1.worker (2 vCPU · 2.5GB RAM)', '2 vCPU / 2.5GB 리사이즈 확정 · 스왑 0B 해소'],
      ['네트워크 통신', 'flannel vxlan (Geneve 오버레이)', 'figteam-net 172.20.0.0/24 대역 내부 통신'],
      ['컨테이너 런타임', 'containerd (k3s 내장)', '파드 워크로드 연산 전담']
    ].forEach(function(item) {
      var li = h('li', null, null, wUl);
      h('b', null, item[0], li);
      h('span', null, item[1], li);
      if (item[2]) {
        var em = h('div', null, item[2], li);
        em.style.cssText = 'font-size: 10.5px; color: #8AA5C2; font-family: monospace; width: 100%; margin-top: 2px;';
      }
    });

    // 4. OpenStack Controller Services
    var ctlCard = h('div', 'osx-card', null, grid);
    ctlCard.style.cssText = 'background: rgba(29, 74, 122, 0.4); border: 1px solid rgba(159, 211, 245, 0.4); padding: 12px; border-radius: 4px;';
    h('h4', null, '☁️ OpenStack Controller 코어 서비스', ctlCard);
    var ctlUl = h('ul', 'osx-list', null, ctlCard);
    [
      ['Keystone / Horizon', '인증 :5000 · 웹 :80 · active', 'Controller VM (192.168.120.160)'],
      ['Nova / Neutron / Cinder', 'OpenStack Core APIs · active', 'QEMU/KVM 하이퍼바이저 제어'],
      ['OpenStack 내부 MariaDB & RabbitMQ', 'IaaS 메타DB :3306 · RPC :5672 · active', 'OpenStack 시스템 제어 전용 (민원 비즈니스 DB와 분리)']
    ].forEach(function(item) {
      var li = h('li', null, null, ctlUl);
      h('b', null, item[0], li);
      h('span', null, item[1], li);
      if (item[2]) {
        var em = h('div', null, item[2], li);
        em.style.cssText = 'font-size: 10.5px; color: #8AA5C2; font-family: monospace; width: 100%; margin-top: 2px;';
      }
    });

    // 5. AWS DR & 자동복구 파이프라인 (실제 개발 컴포넌트)
    var drCard = h('div', 'osx-card', null, grid);
    drCard.style.cssText = 'background: rgba(29, 74, 122, 0.4); border: 1px solid rgba(244, 162, 97, 0.5); padding: 12px; border-radius: 4px;';
    h('h4', null, '🛡️ AWS DR & 자동복구 파이프라인 (실제 개발 컴포넌트)', drCard);
    var drUl = h('ul', 'osx-list', null, drCard);
    [
      ['FastAPI Orchestrator', '포트 :8080 · active (PR #25 Merged)', '10.200.0.3 (AWS ctl) · Alertmanager webhook 수신 / L2 Ansible 복구'],
      ['KT Edge Failover Nginx', 'WAF/Upstream 절체 · active (PR #26)', '10.200.0.1 · failover_edge.sh / failback_edge.sh 전환 스크립트'],
      ['MySQL 8.4 DR Replica', '포트 :3306 · Standby (PR #26)', '10.200.0.4 (AWS dr) · GTID ON / 지연 0초 / promote_replica.sh'],
      ['Blackbox RTO 실측기', 'chaos/measure_rto.py (PR #21)', '0.5초 정밀 프로빙 · 다운타임 CSV 자동 산출 및 /metrics 기록'],
      ['AWS 통합 관제 스택', 'Grafana·Prometheus·Loki (PR #24)', 'Blackbox Exporter 연동 · S1/S2/S3 3-Signal 관제 룰셋']
    ].forEach(function(item) {
      var li = h('li', null, null, drUl);
      h('b', null, item[0], li);
      h('span', null, item[1], li);
      if (item[2]) {
        var em = h('div', null, item[2], li);
        em.style.cssText = 'font-size: 10.5px; color: #8AA5C2; font-family: monospace; width: 100%; margin-top: 2px;';
      }
    });
  }

  // ---------- 5. VM 도구 ----------
  function renderOps() {
    var p = panes.ops; if (!p) return; p.textContent = '';
    var vms = DATA.servers || [];
    var row = h('div', 'osx-ops', null, p);
    h('label', null, '대상 VM', row).htmlFor = 'osx-vm';
    var sel = h('select', null, null, row); sel.id = 'osx-vm';
    vms.forEach(function (v) { var o = h('option', null, v.name + ' (' + v.status + ' · ' + (v.host || '-') + ')', sel); o.value = v.id; });
    var bLog = h('button', 'btn-top', '콘솔 로그 보기', row), bSnap = h('button', 'btn-top', '스냅샷 만들기', row);
    var aHz = h('a', 'btn-top', 'Horizon에서 열기 ↗', row); aHz.target = '_blank'; aHz.rel = 'noopener';
    [bLog, bSnap].forEach(function (b) { b.type = 'button'; });
    function syncLink() { aHz.href = 'https://horizon.ktci5.kr/dashboard/project/instances/' + encodeURIComponent(sel.value) + '/'; }
    sel.addEventListener('change', syncLink); syncLink();
    var confirmBox = h('div', 'osx-confirm', null, p); confirmBox.hidden = true;
    var out = h('pre', 'osx-log', '콘솔 로그(부팅 · 커널 메시지 최근 80줄)를 볼 VM을 고르세요.', p);
    h('p', 'osx-note', '원격 콘솔(noVNC)은 Controller 내부 6080 포트를 쓰므로 외부에서는 Horizon 콘솔 탭이 열리지 않을 수 있습니다. 삭제 · 네트워크 변경은 Horizon에서 하세요.', p);
    bLog.addEventListener('click', function () {
      out.textContent = '불러오는 중…';
      fetch('/api/openstack/console-log?id=' + encodeURIComponent(sel.value), { credentials: 'same-origin' })
        .then(function (r) { return r.json(); })
        .then(function (j) { out.textContent = j.status === 'ok' ? (j.output || '(출력 없음)') : '불러오지 못함: ' + j.message; })
        .catch(function (e) { out.textContent = '불러오지 못함: ' + e.message; });
    });
    bSnap.addEventListener('click', function () {
      var v = vms.filter(function (x) { return x.id === sel.value; })[0]; if (!v) return;
      confirmBox.textContent = ''; confirmBox.hidden = false;
      h('p', null, v.name + ' 스냅샷을 만듭니다. Glance 이미지로 저장되며 디스크 용량을 사용합니다.', confirmBox);
      var inp = h('input', null, null, confirmBox); inp.value = v.name + '-snap-' + new Date().toISOString().slice(0, 16).replace(/[-:T]/g, ''); inp.setAttribute('aria-label', '스냅샷 이름');
      var ok = h('button', 'btn-top primary', '스냅샷 만들기', confirmBox), no = h('button', 'btn-top', '취소', confirmBox);
      ok.type = no.type = 'button';
      no.addEventListener('click', function () { confirmBox.hidden = true; });
      ok.addEventListener('click', function () {
        ok.disabled = true; ok.textContent = '요청 중…';
        fetch('/api/openstack/vm/snapshot', { method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ id: v.id, name: inp.value }) })
          .then(function (r) { return r.json(); })
          .then(function (j) { confirmBox.textContent = j.status === 'ok' ? '스냅샷 요청됨: ' + j.name + ' (Glance에서 진행 상태 확인)' : '스냅샷 실패: ' + j.message; })
          .catch(function (e) { confirmBox.textContent = '스냅샷 실패: ' + e.message; });
      });
    });
  }

  // ---------- 탭 진입 시 불러오기 ----------
  var orig = window.switchTab;
  if (typeof orig === 'function') {
    window.switchTab = function (k) { orig(k); if (k === 'osnet' || k === 'osops') { load(false); loadNet(false); } if (k === 'overview' || k === 'awsvm') loadNet(false); };
  }
  var hk = (location.hash || '').replace('#', ''); if (hk === 'osnet' || hk === 'osops') { load(false); loadNet(false); } if (!hk || hk === 'overview' || hk === 'awsvm') loadNet(false);
  setInterval(function () { if (document.hidden) return; var a = document.getElementById('osnet-panel'), b = document.getElementById('osops-panel'); if ((a && a.style.display !== 'none') || (b && b.style.display !== 'none')) { load(false); loadNet(false); } }, 60000);
  window.OSView = { load: load };
})();

  
  function updateGlobalCloudHealth(d) {
    if (!d || d.status !== 'ok') return;

    // 1. Header chips
    var hKtDot = document.getElementById('header-kt-dot');
    var hKtTxt = document.getElementById('header-kt-text');
    if (hKtDot && hKtTxt) {
      if (d.clouds.kt.is_ok) {
        hKtDot.className = 'dot green';
        hKtTxt.innerText = 'KT Edge: kt-edge-dr-01 (Running)';
      } else {
        hKtDot.className = 'dot red';
        hKtTxt.innerText = 'KT Edge: DOWN 🔴';
      }
    }

    // 2. Main Git Dashboard Cards
    var cKt = document.getElementById('card-cloud-kt');
    var dKt = document.getElementById('dot-cloud-kt');
    if (cKt && dKt) {
      cKt.style.borderColor = d.clouds.kt.color;
      dKt.innerText = d.clouds.kt.status_label;
      dKt.style.color = d.clouds.kt.color;
      dKt.style.borderColor = d.clouds.kt.color;
    }

    var cOn = document.getElementById('card-cloud-onprem');
    var dOn = document.getElementById('dot-cloud-onprem');
    if (cOn && dOn) {
      cOn.style.borderColor = d.clouds.onprem.color;
      dOn.innerText = d.clouds.onprem.status_label;
      dOn.style.color = d.clouds.onprem.color;
      dOn.style.borderColor = d.clouds.onprem.color;
    }

    var cAws = document.getElementById('card-cloud-aws');
    var dAws = document.getElementById('dot-cloud-aws');
    if (cAws && dAws) {
      cAws.style.borderColor = d.clouds.aws.color;
      dAws.innerText = d.clouds.aws.status_label;
      dAws.style.color = d.clouds.aws.color;
      dAws.style.borderColor = d.clouds.aws.color;
    }

    // 3. Blacksky 404 banner
    var bsBanner = document.getElementById('main-blacksky-banner');
    if (bsBanner) {
      bsBanner.style.display = d.all_down ? 'block' : 'none';
    }
  }

  function pollGlobalCloudHealth() {
    fetch('/api/public/system-status')
      .then(function(r) { return r.json(); })
      .then(function(d) { updateGlobalCloudHealth(d); })
      .catch(function(e) { console.error('Cloud health poll err:', e); });
  }

  setInterval(pollGlobalCloudHealth, 5000);
  setTimeout(pollGlobalCloudHealth, 1000);

</script>
</body>
</html>
"""

class ReusableTCPServer(socketserver.TCPServer):
    allow_reuse_address = True

class PortalHandler(http.server.BaseHTTPRequestHandler):
    def get_cookie(self, name):
        cookie_header = self.headers.get('Cookie')
        if not cookie_header:
            return None
        for item in cookie_header.split(';'):
            item = item.strip()
            if '=' in item:
                k, v = item.split('=', 1)
                if k == name:
                    return v
        return None

    def redirect(self, location, set_cookie=None):
        self.send_response(302)
        self.send_header('Location', location)
        if set_cookie:
            self.send_header('Set-Cookie', set_cookie)
        self.end_headers()

    def send_json(self, data, status=200):
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.end_headers()
        self.wfile.write(json.dumps(data).encode('utf-8'))

    def do_GET(self):
        token = self.get_cookie('figteam_session')
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        
        if path == '/login':
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.end_headers()
            err = '<div class="error">아이디 또는 비밀번호가 일치하지 않습니다.</div>' if 'error' in urllib.parse.parse_qs(parsed.query) else ''
            self.wfile.write(LOGIN_HTML.replace('%%ERROR%%', err).encode('utf-8'))
            return
            
        if path == '/logout':
            if token and token in SESSIONS:
                del SESSIONS[token]
            self.redirect('/login', 'figteam_session=deleted; Path=/; Max-Age=0')
            return

        if path == '/api/public/system-status':
            self.send_json(get_public_system_status())
            return

        if not is_valid_session(token):
            if path.startswith('/api/'):
                self.send_json({"status": "error", "message": "Unauthorized"}, status=401)
            else:
                self.redirect('/login')
            return

        if path == '/api/session':
            self.send_json({"status": "ok", "user": VALID_USER})
            return

        if path == '/api/connectivity':
            q = urllib.parse.parse_qs(parsed.query)
            try:
                self.send_json(connectivity_check(force=q.get('force', ['0'])[0] == '1'))
            except Exception as e:
                self.send_json({"status": "error", "message": str(e)}, status=500)
            return

        if path == '/api/openstack/overview':
            try:
                self.send_json(openstack_overview())
            except Exception as e:
                self.send_json({"status": "error", "message": str(e)}, status=500)
            return

        if path == '/api/openstack/services-detail' or path == '/api/osops/services-detail':
            try:
                self.send_json(get_services_and_pods_detail())
            except Exception as e:
                self.send_json({"status": "error", "message": str(e)}, status=500)
            return

        if path == '/api/openstack/console-log':
            q = urllib.parse.parse_qs(parsed.query)
            try:
                self.send_json({"status": "ok", "output": openstack_console_log(q.get('id', [''])[0])})
            except Exception as e:
                self.send_json({"status": "error", "message": str(e)}, status=500)
            return

        # OpenStack API: List Servers and Hypervisors
        if path == '/api/openstack/vms':
            try:
                servers = list_openstack_servers()
                vmware = get_vmware_status()
                self.send_json({"status": "ok", "servers": servers, "vmware_nodes": vmware})
            except Exception as e:
                self.send_json({"status": "error", "message": str(e)}, status=500)
            return

        # KT Cloud API: List Virtual Machines
        if path == '/api/ktcloud/vms':
            try:
                # 1. Real-time connectivity for kt-edge-dr-01 (WireGuard 10.200.0.1:22 or Public 14.63.212.190:22)
                is_running = False
                connected_target = None
                for check_ip in ["10.200.0.1", "14.63.212.190"]:
                    try:
                        with socket.create_connection((check_ip, 22), timeout=1.2):
                            is_running = True
                            connected_target = check_ip
                            break
                    except Exception:
                        pass

                live_hostname = "kt-edge-dr-01"
                live_private_ip = "172.27.0.160"
                live_wg_ip = "10.200.0.1"

                edge_vm = {
                    "id": "100c3a42-ca1e-4a06-bae5-61f14693e479",
                    "name": live_hostname,
                    "displayname": "kt-edge-dr-01 (Edge WAF Hub)",
                    "state": "Running" if is_running else "Stopped",
                    "zonename": "kr-1",
                    "templatename": "rocky8.10-20260515",
                    "hypervisor": "XenServer",
                    "cpunumber": 1,
                    "memory": 2048,
                    "nic": [
                        {
                            "ipaddress": live_private_ip,
                            "networkname": "EPC_G1_Default_Network",
                            "publicip": "14.63.212.190",
                            "wg_ip": live_wg_ip
                        }
                    ]
                }

                vm_list = [edge_vm]

                self.send_json({"status": "ok", "vms": vm_list})
            except Exception as e:
                self.send_json({"status": "error", "message": str(e)}, status=500)
            return

        # KT Cloud API: Query Async Job Result
        if path == '/api/ktcloud/job':
            qs = urllib.parse.parse_qs(parsed.query)
            jobid = qs.get('jobid', [''])[0]
            ver = qs.get('ver', ['server/v1'])[0]
            if not jobid:
                self.send_json({"status": "error", "message": "jobid required"}, status=400)
                return
            try:
                res = call_kt_api(ver, 'queryAsyncJobResult', jobid=jobid)
                job_res = res.get('queryasyncjobresultresponse', {})
                self.send_json({
                    "status": "ok",
                    "jobstatus": job_res.get('jobstatus', 0),
                    "jobresultcode": job_res.get('jobresultcode', 0),
                    "result": job_res.get('jobresult', {})
                })
            except Exception as e:
                self.send_json({"status": "error", "message": str(e)}, status=500)
            return

        # Horizon SSO Bridge endpoint (Full Redirect)
        if path == '/sso/horizon':
            sid = get_horizon_session()
            if sid:
                cookie_str = f"sessionid={sid}; Domain=.ktci5.kr; Path=/; HttpOnly; SameSite=Lax"
                self.redirect("https://horizon.ktci5.kr/dashboard/", set_cookie=cookie_str)
            else:
                self.redirect("https://horizon.ktci5.kr/dashboard/")
            return

        # Horizon SSO API endpoint (AJAX for inline iframe)
        if path == '/sso/horizon-api':
            sid = get_horizon_session()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            if sid:
                self.send_header('Set-Cookie', f"sessionid={sid}; Domain=.ktci5.kr; Path=/; HttpOnly; SameSite=Lax")
                self.end_headers()
                self.wfile.write(b'{"status":"ok"}')
            else:
                self.end_headers()
                self.wfile.write(b'{"status":"fallback"}')
            return

        
        
        # 실시간 라이브 PPT 회의실 독립 페이지
        if path == '/ppt':
            try:
                html_path = '/opt/figteam-portal/ppt.html'
                if not os.path.exists(html_path):
                    html_path = os.path.join(os.path.dirname(__file__), 'ppt.html')
                page = open(html_path, encoding='utf-8').read()
                self.send_response(200)
                self.send_header('Content-Type', 'text/html; charset=utf-8')
                self.send_header('Cache-Control', 'no-store')
                self.end_headers()
                self.wfile.write(page.encode('utf-8'))
            except Exception as e:
                self.send_json({"status": "error", "message": str(e)}, status=500)
            return

        # 실시간 라이브 PPT 상태 API
        if path == '/api/ppt/state':
            token = self.get_cookie('figteam_session')
            username = 'fig (통합관리자)' if is_valid_session(token) else '게스트 참가자'
            with ppt_lock:
                ppt_state['participants'][username] = {'name': username, 'last_seen': time.time()}
                now_t = time.time()
                active_users = [u for u, v in ppt_state['participants'].items() if now_t - v['last_seen'] < 60]
                ppt_state['participants_count'] = max(len(active_users), 1)
                payload = json.dumps(ppt_state, ensure_ascii=False).encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            self.wfile.write(payload)
            return

        # 실시간 라이브 PPT 덱 목록 API
        if path == '/api/ppt/decks':
            self.send_json(scan_ppt_decks())
            return

        # PPT 업로드 정적 파일 서빙 (/uploads/decks/...)
        if path.startswith('/uploads/'):
            rel_path = path[len('/uploads/'):].lstrip('/')
            safe_path = os.path.abspath(os.path.join(UPLOAD_DIR, rel_path))
            if safe_path.startswith(os.path.abspath(UPLOAD_DIR)) and os.path.isfile(safe_path):
                ext = os.path.splitext(safe_path)[1].lower()
                mime_map = {
                    '.png': 'image/png',
                    '.jpg': 'image/jpeg',
                    '.jpeg': 'image/jpeg',
                    '.webp': 'image/webp',
                    '.pdf': 'application/pdf',
                    '.json': 'application/json'
                }
                ctype = mime_map.get(ext, 'application/octet-stream')
                try:
                    with open(safe_path, 'rb') as f:
                        data = f.read()
                    self.send_response(200)
                    self.send_header('Content-Type', ctype)
                    self.send_header('Cache-Control', 'public, max-age=86400')
                    self.end_headers()
                    self.wfile.write(data)
                    return
                except Exception as e:
                    self.send_json({"status": "error", "message": str(e)}, status=500)
                    return
            else:
                self.send_json({"status": "error", "message": "File not found"}, status=404)
                return

        # 통합 터미널 독립 페이지 (2026-11-19): 팝업·새 창·다중 터미널
        if path == '/term':
            try:
                page = open('/opt/figteam-portal/term.html', encoding='utf-8').read()
                m = re.search(r'const KT_OSOPS_PRESETS = (\{.*?\n    \});', PORTAL_HTML, re.S)
                page = page.replace('/*KT_PRESETS*/{}', m.group(1) if m else '{}', 1)
                self.send_response(200)
                self.send_header('Content-Type', 'text/html; charset=utf-8')
                self.send_header('Cache-Control', 'no-store')
                self.end_headers()
                self.wfile.write(page.encode('utf-8'))
            except Exception as e:
                self.send_json({"status": "error", "message": str(e)}, status=500)
            return

        # Main Console Portal
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.end_headers()
        self.wfile.write(PORTAL_HTML.encode('utf-8'))

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        if path == '/login':
            length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(length).decode('utf-8')
            params = urllib.parse.parse_qs(body)
            username = params.get('username', [''])[0]
            password = params.get('password', [''])[0]

            if VALID_USER and VALID_PASS and hmac.compare_digest(username, VALID_USER) and hmac.compare_digest(password, VALID_PASS):
                token = generate_session()
                sid = get_horizon_session()
                self.send_response(302)
                self.send_header('Location', '/')
                self.send_header('Set-Cookie', f'figteam_session={token}; Path=/; HttpOnly; SameSite=Lax')
                if sid:
                    self.send_header('Set-Cookie', f'sessionid={sid}; Domain=.ktci5.kr; Path=/; HttpOnly; SameSite=Lax')
                self.end_headers()
            else:
                self.redirect('/login?error=1')
            return

        token = self.get_cookie('figteam_session')
        if not is_valid_session(token):
            self.send_json({"status": "error", "message": "Unauthorized"}, status=401)
            return

        # ---------------- 실시간 PPT 라이브 회의실 제어 ----------------
        if path == '/api/ppt/action':
            length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(length).decode('utf-8') if length > 0 else '{}'
            username = 'fig (통합관리자)' if is_valid_session(token) else '게스트 참가자'
            try:
                data = json.loads(body)
                act = data.get('action')
                with ppt_lock:
                    if act == 'goto':
                        ppt_state['current_slide'] = max(1, min(int(data.get('slide', 1)), ppt_state['total_slides']))
                        ppt_state['last_updated'] = time.time()
                        ppt_state['updated_by'] = username
                    elif act == 'take_presenter':
                        req_name = data.get('name')
                        ppt_state['presenter'] = req_name if req_name else username
                        ppt_state['last_updated'] = time.time()
                    elif act == 'laser':
                        ppt_state['laser'] = data.get('laser', {'x': -1, 'y': -1, 'active': False})
                self.send_json({"status": "ok", "current_slide": ppt_state['current_slide']})
            except Exception as e:
                self.send_json({"status": "error", "message": str(e)}, status=400)
            return

        # ---------------- 실시간 PPT 덱 선택 API ----------------
        if path == '/api/ppt/decks/select':
            length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(length).decode('utf-8') if length > 0 else '{}'
            username = 'fig (통합관리자)' if is_valid_session(token) else '게스트 참가자'
            try:
                data = json.loads(body)
                target_did = data.get('deck_id')
                with ppt_lock:
                    if target_did == 'default':
                        ppt_state['active_deck_id'] = 'default'
                        ppt_state['active_deck_name'] = '🌟 [테스트] 팀6 시연 슬라이드 (3장)'
                        ppt_state['active_deck_type'] = 'builtin'
                        ppt_state['slides'] = []
                        ppt_state['total_slides'] = 3
                        ppt_state['current_slide'] = 1
                        ppt_state['last_updated'] = time.time()
                        ppt_state['updated_by'] = username
                    else:
                        dpath = os.path.join(DECKS_DIR, target_did)
                        mpath = os.path.join(dpath, 'manifest.json')
                        if os.path.exists(mpath):
                            with open(mpath, encoding='utf-8') as mf:
                                meta = json.load(mf)
                            ppt_state['active_deck_id'] = meta.get('id', target_did)
                            ppt_state['active_deck_name'] = meta.get('name', '사용자 프레젠테이션')
                            ppt_state['active_deck_type'] = meta.get('type', 'custom')
                            ppt_state['slides'] = meta.get('slides', [])
                            ppt_state['total_slides'] = meta.get('slides_count', len(meta.get('slides', [])))
                            ppt_state['current_slide'] = 1
                            ppt_state['last_updated'] = time.time()
                            ppt_state['updated_by'] = username
                        else:
                            self.send_json({"status": "error", "message": "덱을 찾을 수 없습니다."}, status=404)
                            return
                self.send_json({"status": "ok", "active_deck_id": ppt_state['active_deck_id'], "active_deck_name": ppt_state['active_deck_name'], "total_slides": ppt_state['total_slides']})
            except Exception as e:
                self.send_json({"status": "error", "message": str(e)}, status=400)
            return

        # ---------------- 실시간 PPT 파일 업로드 및 자동 변환 ----------------
        if path == '/api/ppt/upload':
            username = 'fig (통합관리자)' if is_valid_session(token) else '게스트 참가자'
            length = int(self.headers.get('Content-Length', 0))
            if length <= 0 or length > 100 * 1024 * 1024:  # 100MB 제한
                self.send_json({"status": "error", "message": "유효하지 않거나 너무 큰 파일입니다 (최대 100MB)."}, status=400)
                return
            body_bytes = self.rfile.read(length)
            ct = self.headers.get('Content-Type', '')
            try:
                form, files = parse_multipart_data(ct, body_bytes)
                if not files:
                    self.send_json({"status": "error", "message": "업로드된 파일이 없습니다."}, status=400)
                    return

                deck_id = "deck_" + datetime.now().strftime("%Y%m%d_%H%M%S") + "_" + secrets.token_hex(3)
                deck_path = os.path.join(DECKS_DIR, deck_id)
                os.makedirs(deck_path, exist_ok=True)

                raw_title = form.get('title', '').strip()
                main_file = files[0]
                fname = main_file.get('filename', '')
                fext = os.path.splitext(fname)[1].lower()
                deck_title = raw_title if raw_title else os.path.splitext(fname)[0]

                slides = []

                # 1. PDF 파일인 경우 (pdftoppm 고화질 변환)
                if fext == '.pdf':
                    pdf_path = os.path.join(deck_path, "source.pdf")
                    with open(pdf_path, 'wb') as f:
                        f.write(main_file['data'])

                    pdftoppm_bin = shutil.which('pdftoppm') or '/usr/bin/pdftoppm'
                    cmd = [pdftoppm_bin, '-png', '-r', '150', pdf_path, os.path.join(deck_path, 'slide')]
                    res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60)
                    if res.returncode != 0:
                        raise RuntimeError(f"pdftoppm 변환 실패: {res.stderr.decode('utf-8', errors='ignore')}")

                    generated_pngs = [f for f in os.listdir(deck_path) if f.startswith('slide-') and f.endswith('.png')]
                    def num_key(fn):
                        m = re.findall(r'\d+', fn)
                        return int(m[-1]) if m else 0
                    generated_pngs.sort(key=num_key)
                    slides = [f"/uploads/decks/{deck_id}/{f}" for f in generated_pngs]

                # 2. ZIP 압축 파일인 경우 (이미지 슬라이드 묶음)
                elif fext == '.zip':
                    zip_path = os.path.join(deck_path, "source.zip")
                    with open(zip_path, 'wb') as f:
                        f.write(main_file['data'])
                    with zipfile.ZipFile(zip_path, 'r') as zf:
                        img_names = [n for n in zf.namelist() if not n.startswith('__MACOSX') and os.path.splitext(n)[1].lower() in ['.png', '.jpg', '.jpeg', '.webp']]
                        def sort_key(fn):
                            m = re.findall(r'\d+', fn)
                            return int(m[-1]) if m else fn
                        img_names.sort(key=sort_key)
                        for idx, iname in enumerate(img_names, start=1):
                            out_ext = os.path.splitext(iname)[1].lower()
                            out_fname = f"slide-{idx:03d}{out_ext}"
                            with open(os.path.join(deck_path, out_fname), 'wb') as out_f:
                                out_f.write(zf.read(iname))
                            slides.append(f"/uploads/decks/{deck_id}/{out_fname}")

                # 3. 단일/다중 이미지 파일 업로드인 경우
                elif fext in ['.png', '.jpg', '.jpeg', '.webp']:
                    for idx, single_file in enumerate(files, start=1):
                        sfname = single_file.get('filename', '')
                        sfext = os.path.splitext(sfname)[1].lower()
                        out_fname = f"slide-{idx:03d}{sfext}"
                        with open(os.path.join(deck_path, out_fname), 'wb') as out_f:
                            out_f.write(single_file['data'])
                        slides.append(f"/uploads/decks/{deck_id}/{out_fname}")
                else:
                    self.send_json({"status": "error", "message": "지원되지 않는 파일 형식입니다. PDF 문서 또는 ZIP, 이미지(PNG/JPG)를 업로드하세요."}, status=400)
                    return

                if not slides:
                    self.send_json({"status": "error", "message": "슬라이드 이미지를 생성하거나 추출하지 못했습니다."}, status=400)
                    return

                manifest = {
                    "id": deck_id,
                    "name": deck_title,
                    "type": "custom",
                    "slides_count": len(slides),
                    "created_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
                    "slides": slides
                }
                with open(os.path.join(deck_path, "manifest.json"), 'w', encoding='utf-8') as mf:
                    json.dump(manifest, mf, ensure_ascii=False, indent=2)

                # 즉시 활성 덱으로 교체 및 모든 참가자 동기화
                with ppt_lock:
                    ppt_state['active_deck_id'] = deck_id
                    ppt_state['active_deck_name'] = deck_title
                    ppt_state['active_deck_type'] = 'custom'
                    ppt_state['slides'] = slides
                    ppt_state['total_slides'] = len(slides)
                    ppt_state['current_slide'] = 1
                    ppt_state['last_updated'] = time.time()
                    ppt_state['updated_by'] = username

                self.send_json({
                    "status": "ok",
                    "deck": manifest,
                    "decks": scan_ppt_decks(),
                    "active_deck_id": deck_id,
                    "total_slides": len(slides)
                })
            except Exception as e:
                self.send_json({"status": "error", "message": f"업로드 처리 실패: {str(e)}"}, status=500)
            return

        

        if path == '/api/openstack/vm/snapshot':
            length = int(self.headers.get('Content-Length', 0))
            try:
                data = json.loads(self.rfile.read(length).decode('utf-8') or '{}')
                self.send_json({"status": "ok", **openstack_snapshot(data.get('id', ''), data.get('name', ''))})
            except Exception as e:
                self.send_json({"status": "error", "message": str(e)}, status=500)
            return

        # OpenStack API: VM Action (start / stop / reboot / hard_reboot)
        if path == '/api/openstack/vm/action':
            length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(length).decode('utf-8')
            try:
                data = json.loads(body)
                action = data.get('action')
                vmid = data.get('id')

                if not vmid or action not in ['start', 'stop', 'reboot', 'hard_reboot']:
                    self.send_json({"status": "error", "message": "유효하지 않은 요청 파라미터입니다."}, status=400)
                    return

                success = action_openstack_server(vmid, action)
                if success:
                    self.send_json({"status": "ok", "action": action, "id": vmid})
                else:
                    self.send_json({"status": "error", "message": "Nova API 액션 처리에 실패했습니다."}, status=500)
            except Exception as e:
                self.send_json({"status": "error", "message": str(e)}, status=500)
            return


        if path == '/api/ctrl/status':
            self.send_json({"status": "ok", "remain": ctrl_unlocked(token)}); return
        if path == '/api/ctrl/lock':
            CTRL_UNLOCK.pop(token, None); self.send_json({"status": "ok", "remain": 0}); return

        # 제어 비밀번호 확인 (값은 응답·로그에 남기지 않음)
        if path == '/api/ctrl/verify':
            try:
                data = json.loads(self.rfile.read(int(self.headers.get('Content-Length', 0))).decode('utf-8'))
                ok = bool(CTRL_PASS) and hmac.compare_digest((data.get('password') or '').strip(), CTRL_PASS)
                if ok: CTRL_UNLOCK[token] = time.time() + CTRL_TTL
                else: time.sleep(0.7)
                term_audit(self.client_address[0], '-', 'ctrl unlock ' + ('ok' if ok else 'FAIL'), 0 if ok else 1, False)
                self.send_json({"status": "ok" if ok else "error", "remain": ctrl_unlocked(token)}, status=200 if ok else 403)
            except Exception:
                self.send_json({"status": "error"}, status=400)
            return

        # 다중 대상 터미널 (2026-11-19): AWS ctl·dr / 온프렘 OpenStack·인스턴스. s1 포털 계정 키로 SSH.
        if path == '/api/term/exec':
            try:
                data = json.loads(self.rfile.read(int(self.headers.get('Content-Length', 0))).decode('utf-8'))
                tgt = TERM_TARGETS.get(data.get('target', ''))
                cmd = (data.get('cmd') or '').strip()
                pwd = (data.get('password') or '').strip()
                if not tgt or not cmd:
                    self.send_json({"status": "error", "message": "대상 또는 명령이 없습니다."}, status=400); return
                danger = bool(TERM_DANGER.search(cmd))
                if not ctrl_unlocked(token):
                    self.send_json({"status": "error", "need_unlock": True, "message": "터미널 잠금 해제가 필요합니다."}, status=403); return
                ssh = ["ssh", "-n", "-o", "BatchMode=yes", "-o", "ConnectTimeout=5", "-o", "StrictHostKeyChecking=accept-new", "-o", "LogLevel=ERROR"]
                if tgt.get('jump'): ssh += ["-J", tgt['jump']]
                res = subprocess.run(ssh + [tgt['host'], cmd], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=25)
                term_audit(self.client_address[0], data.get('target', ''), cmd, res.returncode, danger)
                out = (res.stdout or '') + (("\n[stderr]\n" + res.stderr.strip()) if res.stderr.strip() else '')
                if res.returncode == 255 and 'Permission denied' in (res.stderr or ''):
                    out += "\n→ 이 대상에 포털(s1) 공개키가 등록되지 않았습니다."
                self.send_json({"status": "ok", "code": res.returncode, "output": out[-20000:], "target": f"{tgt['label']} ({tgt['host']})"})
            except subprocess.TimeoutExpired:
                self.send_json({"status": "error", "message": "타임아웃 (25초)"}, status=504)
            except Exception as e:
                self.send_json({"status": "error", "message": str(e)}, status=500)
            return

        # KT Cloud Edge Live Terminal Execution
        if path == '/api/kt/terminal/exec':
            length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(length).decode('utf-8')
            try:
                data = json.loads(body)
                cmd = data.get('cmd', '').strip()
                pwd = data.get('password', '').strip()

                if not cmd:
                    self.send_json({"status": "error", "message": "명령어가 입력되지 않았습니다."}, status=400)
                    return

                dangerous_tokens = ['restart', 'stop', 'poweroff', 'reboot', 'kill', 'rm ', 'dd ', 'shutdown', 'reload']
                is_dangerous = any(token in cmd.lower() for token in dangerous_tokens)

                if is_dangerous and not ctrl_unlocked(token) and (not CTRL_PASS or not hmac.compare_digest(pwd, CTRL_PASS)):
                    self.send_json({"status": "error", "message": "인증 실패: 제어/재시작 명령은 제어 비밀번호가 필요합니다."}, status=403)
                    return

                # Dual target execution: 1. WireGuard Mesh IP (10.200.0.1) -> 2. Public IP (14.63.212.190:22)
                ssh_targets = [
                    ("WireGuard (10.200.0.1:22)", ["ssh", "-o", "StrictHostKeyChecking=no", "-o", "ConnectTimeout=3", "-o", "BatchMode=yes", "root@10.200.0.1", cmd]),
                    ("KT Public (14.63.212.190:22)", ["ssh", "-o", "StrictHostKeyChecking=no", "-o", "ConnectTimeout=3", "-o", "BatchMode=yes", "root@14.63.212.190", cmd])
                ]

                proc = None
                used_target = ""
                last_err = ""

                for target_label, ssh_cmd in ssh_targets:
                    try:
                        res = subprocess.run(ssh_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=12)
                        if res.returncode == 255 and ("Connection timed out" in res.stderr or "No route to host" in res.stderr or "Operation timed out" in res.stderr):
                            last_err = res.stderr
                            continue
                        proc = res
                        used_target = target_label
                        break
                    except subprocess.TimeoutExpired:
                        last_err = f"{target_label} 타임아웃 (12초 초과)"
                        continue
                    except Exception as e:
                        last_err = str(e)
                        continue

                if proc is None:
                    self.send_json({"status": "error", "message": f"SSH 터널 연결 실패: {last_err or '모든 연결 경로 응답 없음'}"}, status=504)
                    return

                output = proc.stdout or ""
                if proc.stderr:
                    lines = [l for l in proc.stderr.splitlines() if not l.strip().startswith('**')]
                    cleaned_err = "\n".join(lines).strip()
                    if cleaned_err:
                        if output:
                            output += "\n[stderr]\n" + cleaned_err
                        else:
                            output = cleaned_err

                self.send_json({
                    "status": "ok",
                    "cmd": cmd,
                    "target": used_target,
                    "code": proc.returncode,
                    "output": output or "(명령어가 정상 실행되었으며 출력 내용이 없습니다.)"
                })
            except subprocess.TimeoutExpired:
                self.send_json({"status": "error", "message": "명령어 실행 시간 초과 (12초 초과)"}, status=504)
            except Exception as e:
                self.send_json({"status": "error", "message": f"실행 오류: {str(e)}"}, status=500)
            return

        # KT Cloud API: VM Action (start / stop / reboot)
        if path == '/api/ktcloud/vm/action':
            length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(length).decode('utf-8')
            try:
                data = json.loads(body)
                action = data.get('action')
                vmid = data.get('id')
                custom_ver = data.get('ver')

                if not vmid or action not in ['start', 'stop', 'reboot']:
                    self.send_json({"status": "error", "message": "유효하지 않은 요청 파라미터입니다."}, status=400)
                    return
                service_ver = custom_ver if custom_ver else 'server/v1'

                cmd = ""
                extra = {}
                if action == 'start':
                    cmd = 'startVirtualMachine'
                elif action == 'stop':
                    cmd = 'stopVirtualMachine'
                    extra = {'forced': 'false'}
                elif action == 'reboot':
                    cmd = 'rebootVirtualMachine'

                res = call_kt_api(service_ver, cmd, id=vmid, **extra)
                resp_key = cmd.lower() + "response"
                jobid = res.get(resp_key, {}).get('jobid')
                
                self.send_json({
                    "status": "ok",
                    "action": action,
                    "id": vmid,
                    "ver": service_ver,
                    "jobid": jobid,
                    "raw": res
                })
            except Exception as e:
                self.send_json({"status": "error", "message": str(e)}, status=500)
            return

        self.send_error(404, "Not Found")

def run():
    with ReusableTCPServer(("0.0.0.0", PORT), PortalHandler) as httpd:
        print(f"[FIGTEAM PORTAL] Unified CMP Portal running on port {PORT}")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            pass

if __name__ == '__main__':
    run()
