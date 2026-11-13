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
if not VALID_USER or not VALID_PASS:
    print("[WARN] 포털 계정이 설정되지 않아 로그인할 수 없습니다: " + PORTAL_CONFIG_PATH)

SESSIONS = {}
SESSION_TTL = 86400

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
            {"name": "compute2", "role": "Compute 2", "status": "Running"}
        ]


def generate_session():
    token = secrets.token_hex(24)
    SESSIONS[token] = time.time() + SESSION_TTL
    return token

def is_valid_session(token):
    if not token or token not in SESSIONS:
        return False
    if time.time() > SESSIONS[token]:
        del SESSIONS[token]
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
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; }
    body { background: radial-gradient(circle at top, #1e293b, #0f172a); min-height: 100vh; display: flex; align-items: center; justify-content: center; color: #f8fafc; padding: 20px; }
    .card { background: rgba(30, 41, 59, 0.7); backdrop-filter: blur(12px); border: 1px solid rgba(255, 255, 255, 0.1); border-radius: 16px; padding: 40px; width: 100%; max-width: 420px; box-shadow: 0 20px 40px rgba(0, 0, 0, 0.5); }
    .logo { text-align: center; margin-bottom: 24px; }
    .badge { display: inline-block; background: #0284c7; color: #fff; font-size: 11px; font-weight: 700; padding: 4px 10px; border-radius: 20px; text-transform: uppercase; margin-bottom: 12px; letter-spacing: 1px; }
    h1 { font-size: 22px; font-weight: 700; color: #f8fafc; margin-bottom: 8px; }
    p.sub { font-size: 13px; color: #94a3b8; }
    .form-group { margin-bottom: 20px; }
    label { display: block; font-size: 13px; font-weight: 600; color: #cbd5e1; margin-bottom: 6px; }
    input { width: 100%; padding: 12px 14px; background: rgba(15, 23, 42, 0.8); border: 1px solid #334155; border-radius: 8px; color: #fff; font-size: 14px; transition: border-color 0.2s; outline: none; }
    input:focus { border-color: #38bdf8; }
    .btn { width: 100%; padding: 13px; background: linear-gradient(135deg, #0284c7, #2563eb); border: none; border-radius: 8px; color: #fff; font-size: 15px; font-weight: 700; cursor: pointer; transition: opacity 0.2s; margin-top: 10px; }
    .btn:hover { opacity: 0.9; }
    .error { background: rgba(239, 68, 68, 0.2); border: 1px solid #ef4444; color: #fca5a5; padding: 10px 14px; border-radius: 8px; font-size: 13px; margin-bottom: 16px; text-align: center; }
    .footer { text-align: center; margin-top: 24px; font-size: 12px; color: #64748b; }
  
    /* DYNAMIC INTERACTIVE FLOW ANIMATIONS */
    @keyframes flow-active {
      from { stroke-dashoffset: 40; }
      to { stroke-dashoffset: 0; }
    }
    @keyframes node-pulse-green {
      0% { box-shadow: 0 0 4px #10b981; }
      50% { box-shadow: 0 0 16px #10b981; }
      100% { box-shadow: 0 0 4px #10b981; }
    }
    @keyframes node-pulse-red {
      0% { box-shadow: 0 0 6px #ef4444; }
      50% { box-shadow: 0 0 20px #ef4444; }
      100% { box-shadow: 0 0 6px #ef4444; }
    }
    @keyframes node-pulse-amber {
      0% { box-shadow: 0 0 6px #f59e0b; }
      50% { box-shadow: 0 0 18px #f59e0b; }
      100% { box-shadow: 0 0 6px #f59e0b; }
    }
    .flow-line {
      stroke-dasharray: 8 6;
      animation: flow-active 0.8s linear infinite;
    }
    .flow-reverse {
      stroke-dasharray: 8 6;
      animation: flow-active 0.8s linear infinite reverse;
    }
    .line-green { stroke: #10b981; stroke-width: 3.5; }
    .line-blue { stroke: #38bdf8; stroke-width: 3.5; }
    .line-yellow { stroke: #f59e0b; stroke-width: 3; }
    .line-purple { stroke: #a855f7; stroke-width: 3.5; }
    .line-red { stroke: #ef4444; stroke-width: 3; stroke-dasharray: 4 4; animation: none; opacity: 0.8; }
    .line-inactive { stroke: #334155; stroke-width: 1.5; stroke-dasharray: 4 4; animation: none; opacity: 0.25; }

    .topo-node {
      background: #1e293b;
      border: 1px solid #334155;
      border-radius: 12px;
      padding: 14px;
      display: flex;
      flex-direction: column;
      gap: 6px;
      transition: all 0.3s;
      position: relative;
    }
    .node-active-green { border-color: #10b981; animation: node-pulse-green 2s infinite; background: rgba(16, 185, 129, 0.08); }
    .node-active-amber { border-color: #f59e0b; animation: node-pulse-amber 2s infinite; background: rgba(245, 158, 11, 0.08); }
    .node-down-red { border-color: #ef4444; animation: node-pulse-red 1s infinite; background: rgba(239, 68, 68, 0.15); }
    .node-standby { border-color: #475569; opacity: 0.7; }

  
    /* ============================================================ */
    /* v3.0 DRAWIO TECHNICAL ARCHITECTURE STYLES                    */
    /* ============================================================ */
    .arch-container {
      display: grid;
      grid-template-columns: 240px 1fr 1fr;
      gap: 16px;
      position: relative;
      background: #090e17;
      padding: 20px;
      border-radius: 14px;
      border: 1px solid #1e293b;
      min-height: 520px;
    }
    .arch-zone {
      border-radius: 12px;
      padding: 14px;
      display: flex;
      flex-direction: column;
      gap: 12px;
      position: relative;
      transition: all 0.3s;
    }
    .zone-kt {
      background: rgba(2, 132, 199, 0.05);
      border: 1px solid rgba(2, 132, 199, 0.3);
    }
    .zone-onprem {
      background: rgba(16, 185, 129, 0.04);
      border: 1px solid rgba(16, 185, 129, 0.3);
    }
    .zone-aws {
      background: rgba(245, 158, 11, 0.04);
      border: 1px solid rgba(245, 158, 11, 0.3);
    }
    .zone-title {
      font-size: 13px;
      font-weight: 800;
      display: flex;
      align-items: center;
      justify-content: space-between;
      border-bottom: 1px solid rgba(255, 255, 255, 0.1);
      padding-bottom: 8px;
    }
    .arch-subnet {
      background: rgba(15, 23, 42, 0.85);
      border: 1px dashed #334155;
      border-radius: 8px;
      padding: 10px;
      display: flex;
      flex-direction: column;
      gap: 8px;
    }
    .subnet-label {
      font-size: 10px;
      font-weight: 700;
      color: #94a3b8;
      text-transform: uppercase;
      letter-spacing: 0.5px;
    }
    .k8s-pod-grid {
      display: grid;
      grid-template-columns: repeat(2, 1fr);
      gap: 6px;
    }
    .k8s-pod-chip {
      background: #1e293b;
      border: 1px solid #475569;
      border-radius: 6px;
      padding: 6px 8px;
      font-size: 11px;
      font-weight: 600;
      color: #f8fafc;
      display: flex;
      align-items: center;
      gap: 6px;
      transition: all 0.3s;
    }
    .pod-active { border-color: #10b981; background: rgba(16, 185, 129, 0.15); }
    .pod-restarting { border-color: #f59e0b; background: rgba(245, 158, 11, 0.2); animation: pulse-restarting 0.8s infinite; }
    @keyframes pulse-restarting {
      0% { opacity: 0.4; transform: scale(0.98); }
      50% { opacity: 1; transform: scale(1.02); }
      100% { opacity: 0.4; transform: scale(0.98); }
    }
    .tunnel-badge {
      font-size: 10px;
      font-weight: 800;
      padding: 3px 8px;
      border-radius: 12px;
      display: inline-flex;
      align-items: center;
      gap: 5px;
    }
    .tunnel-a { background: rgba(212, 147, 15, 0.2); color: #fbbf24; border: 1px solid #d4930f; }
    .tunnel-b { background: rgba(56, 189, 248, 0.2); color: #38bdf8; border: 1px solid #0284c7; }
    .tunnel-c { background: rgba(168, 85, 247, 0.2); color: #c084fc; border: 1px solid #9333ea; }

  </style>
</head>
<body>
  <div class="card">
    <div class="logo">
      <div class="badge">FIGTEAM UNIFIED PLATFORM</div>
      <h1>클라우드 통합 콘솔</h1>
      <p class="sub">OpenStack · KT Cloud · K8s · ArgoCD · Grafana</p>
    </div>
    %%ERROR%%
    <form method="POST" action="/login">
      <div class="form-group">
        <label>통합 계정 ID</label>
        <input type="text" name="username" placeholder="fig" required autofocus>
      </div>
      <div class="form-group">
        <label>비밀번호</label>
        <input type="password" name="password" placeholder="••••••••" required>
      </div>
      <button type="submit" class="btn">통합 로그인 (SSO)</button>
    </form>
    <div class="footer">
      KT CI5 민원불패 하이브리드 멀티클라우드
    </div>
  </div>
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
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; }
    body { background: #0f172a; color: #f8fafc; height: 100vh; overflow: hidden; display: flex; flex-direction: column; }
    
    /* TOP NAVIGATION BAR */
    header { height: 56px; background: rgba(15, 23, 42, 0.95); border-bottom: 1px solid #1e293b; display: flex; align-items: center; justify-content: space-between; padding: 0 20px; z-index: 100; backdrop-filter: blur(8px); }
    .brand { display: flex; align-items: center; gap: 12px; font-size: 16px; font-weight: 700; color: #f8fafc; }
    .brand-tag { background: #0284c7; color: #fff; font-size: 10px; font-weight: 800; padding: 2px 8px; border-radius: 4px; letter-spacing: 0.5px; }
    
    .status-group { display: flex; align-items: center; gap: 14px; font-size: 12px; color: #94a3b8; }
    .chip { display: flex; align-items: center; gap: 6px; background: rgba(30, 41, 59, 0.8); border: 1px solid #334155; padding: 4px 10px; border-radius: 20px; }
    .dot { width: 8px; height: 8px; border-radius: 50%; }
    .dot.green { background: #10b981; box-shadow: 0 0 8px #10b981; }
    .dot.yellow { background: #f59e0b; box-shadow: 0 0 8px #f59e0b; }
    .dot.red { background: #ef4444; box-shadow: 0 0 8px #ef4444; }
    
    .user-actions { display: flex; align-items: center; gap: 12px; }
    .user-badge { display: flex; align-items: center; gap: 6px; font-size: 12px; color: #cbd5e1; background: #1e293b; padding: 5px 12px; border-radius: 6px; border: 1px solid #334155; }
    .btn-top { background: transparent; border: 1px solid #334155; color: #94a3b8; font-size: 12px; padding: 5px 10px; border-radius: 6px; cursor: pointer; transition: all 0.2s; text-decoration: none; }
    .btn-top:hover { color: #f8fafc; border-color: #64748b; background: rgba(255, 255, 255, 0.05); }
    .btn-logout { background: rgba(239, 68, 68, 0.15); border-color: #ef4444; color: #fca5a5; }
    .btn-logout:hover { background: #ef4444; color: #fff; }

    /* LAYOUT: SIDEBAR + WORKSPACE */
    .app-container { display: flex; flex: 1; height: calc(100vh - 56px); overflow: hidden; }
    
    /* SIDEBAR */
    aside { width: 250px; background: #0b1120; border-right: 1px solid #1e293b; display: flex; flex-direction: column; justify-content: space-between; flex-shrink: 0; }
    .menu-list { list-style: none; padding: 14px 10px; display: flex; flex-direction: column; gap: 4px; }
    .menu-header { font-size: 11px; font-weight: 700; color: #64748b; text-transform: uppercase; padding: 8px 12px 4px 12px; letter-spacing: 0.5px; }
    .menu-item { display: flex; align-items: center; gap: 10px; padding: 10px 14px; border-radius: 8px; color: #94a3b8; font-size: 13px; font-weight: 500; cursor: pointer; transition: all 0.2s; text-decoration: none; user-select: none; }
    .menu-item:hover { color: #f8fafc; background: rgba(255, 255, 255, 0.04); }
    .menu-item.active { color: #fff; background: #0284c7; font-weight: 600; box-shadow: 0 4px 12px rgba(2, 132, 199, 0.3); }
    .menu-item .icon { font-size: 16px; width: 20px; text-align: center; }
    .menu-badge { margin-left: auto; font-size: 10px; padding: 2px 6px; border-radius: 10px; background: rgba(255,255,255,0.1); }
    
    .sidebar-footer { padding: 16px; border-top: 1px solid #1e293b; font-size: 11px; color: #475569; text-align: center; }

    /* WORKSPACE MAIN */
    main { flex: 1; display: flex; flex-direction: column; background: #0f172a; overflow: hidden; position: relative; }
    
    /* CONSOLE FRAME VIEW */
    .frame-toolbar { height: 42px; background: #131d31; border-bottom: 1px solid #1e293b; display: flex; align-items: center; justify-content: space-between; padding: 0 16px; }
    .frame-title { font-size: 12px; font-weight: 600; color: #38bdf8; display: flex; align-items: center; gap: 8px; }
    .frame-actions { display: flex; align-items: center; gap: 8px; }
    .tool-btn { background: #1e293b; border: 1px solid #334155; color: #cbd5e1; font-size: 11px; padding: 4px 10px; border-radius: 5px; cursor: pointer; display: flex; align-items: center; gap: 4px; text-decoration: none; }
    .tool-btn:hover { background: #334155; color: #fff; }
    
    .iframe-wrapper { flex: 1; width: 100%; height: calc(100% - 42px); position: relative; background: #fff; }
    iframe { width: 100%; height: 100%; border: none; display: block; }

    /* OVERVIEW DASHBOARD VIEW */
    #overview-panel, #ktvm-panel, #osvm-panel, #dr-panel { flex: 1; overflow-y: auto; padding: 24px; display: flex; flex-direction: column; gap: 24px; }
    .overview-hero { background: linear-gradient(135deg, rgba(2, 132, 199, 0.15), rgba(30, 41, 59, 0.6)); border: 1px solid rgba(56, 189, 248, 0.2); border-radius: 14px; padding: 24px; }
    .overview-hero h2 { font-size: 20px; font-weight: 700; margin-bottom: 6px; color: #f8fafc; }
    .overview-hero p { font-size: 13px; color: #94a3b8; line-height: 1.5; }

    .stats-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 16px; }
    .stat-card { background: #1e293b; border: 1px solid #334155; border-radius: 12px; padding: 18px; }
    .stat-card .label { font-size: 11px; font-weight: 600; color: #94a3b8; text-transform: uppercase; margin-bottom: 8px; }
    .stat-card .value { font-size: 22px; font-weight: 800; color: #f8fafc; }
    .stat-card .subtext { font-size: 12px; color: #10b981; margin-top: 4px; }

    .section-title { font-size: 15px; font-weight: 700; color: #e2e8f0; margin-bottom: 12px; display: flex; align-items: center; gap: 8px; }
    
    .cards-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); gap: 16px; }
    .svc-card { background: #1e293b; border: 1px solid #334155; border-radius: 12px; padding: 18px; display: flex; flex-direction: column; justify-content: space-between; transition: transform 0.2s, border-color 0.2s; }
    .svc-card:hover { border-color: #38bdf8; transform: translateY(-2px); }
    .svc-card-header { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 12px; }
    .svc-title { font-size: 15px; font-weight: 700; color: #f8fafc; }
    .svc-type { font-size: 10px; font-weight: 700; padding: 3px 8px; border-radius: 4px; text-transform: uppercase; }
    .type-iaas { background: #0369a1; color: #fff; }
    .type-gitops { background: #b45309; color: #fff; }
    .type-mon { background: #047857; color: #fff; }
    .type-app { background: #6d28d9; color: #fff; }
    .svc-desc { font-size: 12px; color: #94a3b8; line-height: 1.5; margin-bottom: 16px; }
    .svc-footer { display: flex; justify-content: space-between; align-items: center; padding-top: 12px; border-top: 1px solid #334155; font-size: 11px; color: #64748b; }
    .btn-launch { background: #0284c7; color: #fff; border: none; padding: 6px 14px; border-radius: 6px; font-size: 12px; font-weight: 600; cursor: pointer; transition: opacity 0.2s; }
    .btn-launch:hover { opacity: 0.9; }

    /* KT CLOUD VM MANAGEMENT STYLES */
    .kt-vm-box { background: #1e293b; border: 1px solid #334155; border-radius: 14px; padding: 22px; display: flex; flex-direction: column; gap: 20px; }
    .kt-vm-header { display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid #334155; padding-bottom: 16px; }
    .kt-vm-title { display: flex; align-items: center; gap: 12px; }
    .kt-vm-name { font-size: 20px; font-weight: 800; color: #fff; }
    .kt-vm-badge { font-size: 12px; font-weight: 700; padding: 4px 12px; border-radius: 20px; display: flex; align-items: center; gap: 6px; }
    .state-running { background: rgba(16, 185, 129, 0.2); color: #34d399; border: 1px solid #10b981; }
    .state-stopped { background: rgba(239, 68, 68, 0.2); color: #f87171; border: 1px solid #ef4444; }
    .state-transition { background: rgba(245, 158, 11, 0.2); color: #fbbf24; border: 1px solid #f59e0b; }

    .kt-props-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 14px; }
    .prop-item { background: #0f172a; padding: 12px 14px; border-radius: 8px; border: 1px solid #334155; }
    .prop-label { font-size: 11px; color: #94a3b8; margin-bottom: 4px; font-weight: 600; text-transform: uppercase; }
    .prop-val { font-size: 13px; font-weight: 700; color: #f8fafc; font-family: monospace; }

    .kt-ctrl-bar { display: flex; gap: 12px; flex-wrap: wrap; align-items: center; background: #0f172a; padding: 14px; border-radius: 10px; border: 1px solid #334155; }
    .btn-action { padding: 9px 18px; border-radius: 8px; font-size: 13px; font-weight: 700; cursor: pointer; border: none; display: flex; align-items: center; gap: 8px; transition: all 0.2s; }
    .btn-stop { background: #ef4444; color: #fff; }
    .btn-stop:hover:not(:disabled) { background: #dc2626; box-shadow: 0 0 12px rgba(239, 68, 68, 0.4); }
    .btn-start { background: #10b981; color: #fff; }
    .btn-start:hover:not(:disabled) { background: #059669; box-shadow: 0 0 12px rgba(16, 185, 129, 0.4); }
    .btn-reboot { background: #f59e0b; color: #fff; }
    .btn-reboot:hover:not(:disabled) { background: #d97706; box-shadow: 0 0 12px rgba(245, 158, 11, 0.4); }
    .btn-refresh { background: #334155; color: #cbd5e1; }
    .btn-refresh:hover { background: #475569; color: #fff; }
    .btn-action:disabled { opacity: 0.4; cursor: not-allowed; }

    .kt-log-box { background: #0b1120; border: 1px solid #334155; border-radius: 8px; padding: 14px; font-family: monospace; font-size: 12px; color: #94a3b8; height: 160px; overflow-y: auto; display: flex; flex-direction: column; gap: 6px; }
    .log-line { display: flex; gap: 10px; }
    .log-time { color: #64748b; }
    .log-msg { color: #cbd5e1; }
    .log-msg.success { color: #34d399; }
    .log-msg.warn { color: #fbbf24; }
    .log-msg.err { color: #f87171; }

    /* FULLSCREEN TOGGLE */
    .fullscreen header, .fullscreen aside, .fullscreen .frame-toolbar { display: none !important; }
    .fullscreen .app-container { height: 100vh; }
    .fullscreen .iframe-wrapper { height: 100vh; }
  
    /* DYNAMIC INTERACTIVE FLOW ANIMATIONS */
    @keyframes flow-active {
      from { stroke-dashoffset: 40; }
      to { stroke-dashoffset: 0; }
    }
    @keyframes node-pulse-green {
      0% { box-shadow: 0 0 4px #10b981; }
      50% { box-shadow: 0 0 16px #10b981; }
      100% { box-shadow: 0 0 4px #10b981; }
    }
    @keyframes node-pulse-red {
      0% { box-shadow: 0 0 6px #ef4444; }
      50% { box-shadow: 0 0 20px #ef4444; }
      100% { box-shadow: 0 0 6px #ef4444; }
    }
    @keyframes node-pulse-amber {
      0% { box-shadow: 0 0 6px #f59e0b; }
      50% { box-shadow: 0 0 18px #f59e0b; }
      100% { box-shadow: 0 0 6px #f59e0b; }
    }
    .flow-line {
      stroke-dasharray: 8 6;
      animation: flow-active 0.8s linear infinite;
    }
    .flow-reverse {
      stroke-dasharray: 8 6;
      animation: flow-active 0.8s linear infinite reverse;
    }
    .line-green { stroke: #10b981; stroke-width: 3.5; }
    .line-blue { stroke: #38bdf8; stroke-width: 3.5; }
    .line-yellow { stroke: #f59e0b; stroke-width: 3; }
    .line-purple { stroke: #a855f7; stroke-width: 3.5; }
    .line-red { stroke: #ef4444; stroke-width: 3; stroke-dasharray: 4 4; animation: none; opacity: 0.8; }
    .line-inactive { stroke: #334155; stroke-width: 1.5; stroke-dasharray: 4 4; animation: none; opacity: 0.25; }

    .topo-node {
      background: #1e293b;
      border: 1px solid #334155;
      border-radius: 12px;
      padding: 14px;
      display: flex;
      flex-direction: column;
      gap: 6px;
      transition: all 0.3s;
      position: relative;
    }
    .node-active-green { border-color: #10b981; animation: node-pulse-green 2s infinite; background: rgba(16, 185, 129, 0.08); }
    .node-active-amber { border-color: #f59e0b; animation: node-pulse-amber 2s infinite; background: rgba(245, 158, 11, 0.08); }
    .node-down-red { border-color: #ef4444; animation: node-pulse-red 1s infinite; background: rgba(239, 68, 68, 0.15); }
    .node-standby { border-color: #475569; opacity: 0.7; }

  
    /* ============================================================ */
    /* v3.0 DRAWIO TECHNICAL ARCHITECTURE STYLES                    */
    /* ============================================================ */
    .arch-container {
      display: grid;
      grid-template-columns: 240px 1fr 1fr;
      gap: 16px;
      position: relative;
      background: #090e17;
      padding: 20px;
      border-radius: 14px;
      border: 1px solid #1e293b;
      min-height: 520px;
    }
    .arch-zone {
      border-radius: 12px;
      padding: 14px;
      display: flex;
      flex-direction: column;
      gap: 12px;
      position: relative;
      transition: all 0.3s;
    }
    .zone-kt {
      background: rgba(2, 132, 199, 0.05);
      border: 1px solid rgba(2, 132, 199, 0.3);
    }
    .zone-onprem {
      background: rgba(16, 185, 129, 0.04);
      border: 1px solid rgba(16, 185, 129, 0.3);
    }
    .zone-aws {
      background: rgba(245, 158, 11, 0.04);
      border: 1px solid rgba(245, 158, 11, 0.3);
    }
    .zone-title {
      font-size: 13px;
      font-weight: 800;
      display: flex;
      align-items: center;
      justify-content: space-between;
      border-bottom: 1px solid rgba(255, 255, 255, 0.1);
      padding-bottom: 8px;
    }
    .arch-subnet {
      background: rgba(15, 23, 42, 0.85);
      border: 1px dashed #334155;
      border-radius: 8px;
      padding: 10px;
      display: flex;
      flex-direction: column;
      gap: 8px;
    }
    .subnet-label {
      font-size: 10px;
      font-weight: 700;
      color: #94a3b8;
      text-transform: uppercase;
      letter-spacing: 0.5px;
    }
    .k8s-pod-grid {
      display: grid;
      grid-template-columns: repeat(2, 1fr);
      gap: 6px;
    }
    .k8s-pod-chip {
      background: #1e293b;
      border: 1px solid #475569;
      border-radius: 6px;
      padding: 6px 8px;
      font-size: 11px;
      font-weight: 600;
      color: #f8fafc;
      display: flex;
      align-items: center;
      gap: 6px;
      transition: all 0.3s;
    }
    .pod-active { border-color: #10b981; background: rgba(16, 185, 129, 0.15); }
    .pod-restarting { border-color: #f59e0b; background: rgba(245, 158, 11, 0.2); animation: pulse-restarting 0.8s infinite; }
    @keyframes pulse-restarting {
      0% { opacity: 0.4; transform: scale(0.98); }
      50% { opacity: 1; transform: scale(1.02); }
      100% { opacity: 0.4; transform: scale(0.98); }
    }
    .tunnel-badge {
      font-size: 10px;
      font-weight: 800;
      padding: 3px 8px;
      border-radius: 12px;
      display: inline-flex;
      align-items: center;
      gap: 5px;
    }
    .tunnel-a { background: rgba(212, 147, 15, 0.2); color: #fbbf24; border: 1px solid #d4930f; }
    .tunnel-b { background: rgba(56, 189, 248, 0.2); color: #38bdf8; border: 1px solid #0284c7; }
    .tunnel-c { background: rgba(168, 85, 247, 0.2); color: #c084fc; border: 1px solid #9333ea; }

  </style>
</head>
<body>

  <!-- HEADER -->
  <header>
    <div class="brand">
      <span>⚡ FIGTEAM</span>
      <span class="brand-tag">HYBRID CMP</span>
    </div>
    
    <div class="status-group">
      <div class="chip">
        <span id="header-kt-dot" class="dot green"></span>
        <span id="header-kt-text">KT Edge: k-vm1 (Running)</span>
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
    <!-- SIDEBAR -->
    <aside>
      <ul class="menu-list">
        <div class="menu-header">통합 콘솔 메뉴</div>
        
        <li class="menu-item active" onclick="switchTab('overview')">
          <span class="icon">📊</span>
          <span>통합 인프라 개요</span>
          <span class="menu-badge">Live</span>
        </li>
        
        <div class="menu-header">운영 & 고가용성 (HA)</div>
        <li class="menu-item" onclick="switchTab('dr')">
          <span class="icon">🛡️</span>
          <span>운영 대시보드</span>
          <span class="menu-badge" style="background:#e11d48;color:#fff;">Live</span>
        </li>

        <div class="menu-header">인프라 & 가상화</div>
        <li class="menu-item" onclick="switchTab('ktvm')">
          <span class="icon">⚡</span>
          <span>KT Cloud VM 관리</span>
          <span class="menu-badge" style="background:#0284c7;color:#fff;">Admin</span>
        </li>
        <li class="menu-item" onclick="switchTab('osvm')">
          <span class="icon">🖥️</span>
          <span>OpenStack VM 관리</span>
          <span class="menu-badge" style="background:#8b5cf6;color:#fff;">Nova</span>
        </li>
        <li class="menu-item" onclick="switchTab('horizon')">
          <span class="icon">☁️</span>
          <span>OpenStack Horizon</span>
          <span class="menu-badge">IaaS</span>
        </li>
        
        <div class="menu-header">배포 & 옵저버빌리티</div>
        <li class="menu-item" onclick="switchTab('grafana')">
          <span class="icon">📈</span>
          <span>Grafana 관제 메트릭</span>
          <span class="menu-badge">Metrics</span>
        </li>
        <li class="menu-item" onclick="switchTab('argocd')">
          <span class="icon">🚀</span>
          <span>Argo CD GitOps</span>
          <span class="menu-badge">Deploy</span>
        </li>
        
        <div class="menu-header">서비스 엔드포인트</div>
        <li class="menu-item" onclick="switchTab('minwon')">
          <span class="icon">🏛️</span>
          <span>민원청구 24시 센터</span>
          <span class="menu-badge">Prod</span>
        </li>
        <li class="menu-item" onclick="switchTab('ktedge')">
          <span class="icon">🌐</span>
          <span>KT Cloud Edge 웹</span>
          <span class="menu-badge">Edge</span>
        </li>
      </ul>
      
      <div class="sidebar-footer">
        FIGTEAM Multi-Cloud Console v3.3<br>
        Inbound Port 0 (Zero Trust)
      </div>
    </aside>

    <!-- MAIN WORKSPACE -->
    <main id="main-workspace">
      
      <!-- 1. OVERVIEW PANEL -->
      <section id="overview-panel">
        <div class="overview-hero">
          <h2>민원불패 하이브리드 멀티클라우드 단일 통합 콘솔</h2>
          <p>KT Cloud VM(전원·자원 관리), OpenStack Horizon, Argo CD, Grafana, 민원청구 앱이 <strong>figteam.ktci5.kr</strong> 단일 도메인 안에서 완전히 일체형으로 통합되어 관리됩니다.</p>
        </div>

        <div class="stats-grid">
          <div class="stat-card">
            <div class="label">KT Cloud VM 상태</div>
            <div class="value" id="stat-kt-state">k-vm1 : Running</div>
            <div class="subtext" id="stat-kt-sub">14.63.213.214 (공인 엣지)</div>
          </div>
          <div class="stat-card">
            <div class="label">SSO 통합 인증</div>
            <div class="value">완료 (Bypassed)</div>
            <div class="subtext">단일 계정(fig) 무인증 직행</div>
          </div>
          <div class="stat-card">
            <div class="label">보안 상태</div>
            <div class="value">WAF High / TLS 1.3</div>
            <div class="subtext">Inbound Port 0 완전 차단</div>
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
          <div class="svc-card" style="border-color: rgba(225, 29, 72, 0.4);">
            <div class="svc-card-header">
              <div>
                <div class="svc-title" style="color:#fda4af;">🛡️ 운영 대시보드</div>
                <div style="font-size: 11px; color: #94a3b8; margin-top: 2px;">L1~L4 다계층 자동복구, 실시간 제어 & 0초 비상 접수</div>
              </div>
              <span class="svc-type" style="background:#e11d48; color:#fff;">Live Ops</span>
            </div>
            <div class="svc-desc">Cloudflare ➔ KT Cloud Edge ➔ 온프렘 Primary ➔ AWS DR 4단계 장애 대응 흐름 및 실시간 토폴로지 관제.</div>
            <div class="svc-footer">
              <span style="color:#34d399;">현재 경로: On-Prem Primary (RW) 🟢</span>
              <button class="btn-launch" style="background:#e11d48;" onclick="switchTab('dr')">대시보드 열기 →</button>
            </div>
          </div>

          <!-- OpenStack VM Management -->
          <div class="svc-card">
            <div class="svc-card-header">
              <div>
                <div class="svc-title">OpenStack VM 관리 (온프렘 인스턴스)</div>
                <div style="font-size: 11px; color: #64748b; margin-top: 2px;">OpenStack Nova REST API (v2.1)</div>
              </div>
              <span class="svc-type type-iaas" style="background:#8b5cf6;">On-Prem Nova</span>
            </div>
            <div class="svc-desc">온프레미스 K8s 클러스터 가상머신(k8s-cp1, k8s-w1, k8s-w2) 및 상위 노드의 전원 끄기·켜기·재부팅 실시간 제어.</div>
            <div class="svc-footer">
              <span id="card-os-state-text">상태: 3대 가동 중 (ACTIVE) 🟢</span>
              <button class="btn-launch" onclick="switchTab('osvm')">VM 관리하기 →</button>
            </div>
          </div>

          <!-- KT VM Management -->
          <div class="svc-card">
            <div class="svc-card-header">
              <div>
                <div class="svc-title">KT Cloud VM 관리 (전원/자원)</div>
                <div style="font-size: 11px; color: #64748b; margin-top: 2px;">KT Cloud OpenAPI (server/v1)</div>
              </div>
              <span class="svc-type type-iaas" style="background:#0284c7;">KT Edge</span>
            </div>
            <div class="svc-desc">KT Cloud OpenAPI를 직접 호출하여 Edge Gateway VM(k-vm1) 전원 켜기·끄기·재부팅 및 과금 최적화.</div>
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
                <div style="font-size: 11px; color: #64748b; margin-top: 2px;">https://horizon.ktci5.kr</div>
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
                <div style="font-size: 11px; color: #64748b; margin-top: 2px;">https://grafana.ktci5.kr</div>
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
                <div style="font-size: 11px; color: #64748b; margin-top: 2px;">https://argocd.ktci5.kr</div>
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
        <div class="overview-hero" style="background: linear-gradient(135deg, rgba(2, 132, 199, 0.25), rgba(15, 23, 42, 0.8));">
          <h2>🌐 KT Cloud 인프라 자원 & VM 전원 제어 센터</h2>
          <p>KT Cloud OpenAPI(서명 기반)를 연동하여 가상머신의 전원(ON/OFF)과 재부팅을 실시간으로 관리합니다. 야간 미사용 시 전원을 끄면 vCPU/RAM 연산 비용이 절감됩니다.</p>
        </div>

        <div class="kt-vm-box">
          <div class="kt-vm-header">
            <div class="kt-vm-title">
              <span style="font-size:24px;">🖥️</span>
              <div>
                <div class="kt-vm-name" id="kt-display-name">k-vm1</div>
                <div style="font-size: 11px; color: #94a3b8; font-family: monospace;" id="kt-display-id">ID: 100c3a42-ca1e-4a06-bae5-61f14693e479</div>
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
              <div class="prop-val" style="color:#38bdf8;">14.63.213.214</div>
            </div>
            <div class="prop-item">
              <div class="prop-label">사설 IP (Guest Network)</div>
              <div class="prop-val" id="kt-private-ip">172.27.0.185</div>
            </div>
            <div class="prop-item">
              <div class="prop-label">인스턴스 스펙</div>
              <div class="prop-val" id="kt-spec">1 vCPU · 1024 MB RAM</div>
            </div>
            <div class="prop-item">
              <div class="prop-label">운영체제 & 하이퍼바이저</div>
              <div class="prop-val" id="kt-os">rocky8.10 (XenServer)</div>
            </div>
            <div class="prop-item">
              <div class="prop-label">가용 구역 (Zone)</div>
              <div class="prop-val" id="kt-zone">kr-1 (KOR-Central A)</div>
            </div>
            <div class="prop-item">
              <div class="prop-label">과금 상태 안내</div>
              <div class="prop-val" id="kt-cost-info" style="color:#34d399;">정상 과금 중 (연산 활성)</div>
            </div>
          </div>

          <!-- CONTROL ACTION BUTTONS -->
          <div class="kt-ctrl-bar">
            <span style="font-size:12px; font-weight:700; color:#94a3b8; margin-right:6px;">전원 및 자원 명령:</span>
            <button class="btn-action btn-stop" id="btn-kt-stop" onclick="confirmVmAction('stop')">
              <span>🛑</span> 전원 끄기 (Stop)
            </button>
            <button class="btn-action btn-start" id="btn-kt-start" onclick="confirmVmAction('start')">
              <span>⚡</span> 전원 켜기 (Start)
            </button>
            <button class="btn-action btn-reboot" id="btn-kt-reboot" onclick="confirmVmAction('reboot')">
              <span>↻</span> 재부팅 (Reboot)
            </button>
            <button class="btn-action btn-refresh" id="btn-kt-refresh" onclick="fetchKtVmStatus(true)">
              <span>🔍</span> 상태 새로고침
            </button>
            <span id="kt-action-spinner" style="display:none; font-size:12px; color:#38bdf8; margin-left:auto;">
              ⏳ KT Cloud API 작업 처리 중...
            </span>
          </div>

          <!-- ACTIVITY CONSOLE LOG -->
          <div>
            <div style="font-size:12px; font-weight:700; color:#cbd5e1; margin-bottom:8px; display:flex; justify-content:space-between;">
              <span>📋 KT Cloud OpenAPI 실행 콘솔 로그</span>
              <span style="font-size:11px; color:#64748b;">server/v1 API 통신 실시간 스트림</span>
            </div>
            <div class="kt-log-box" id="kt-log-console">
              <div class="log-line">
                <span class="log-time">[CMP-INIT]</span>
                <span class="log-msg">KT Cloud OpenAPI 클라이언트 준비 완료.</span>
              </div>
            </div>
          </div>
        </div>
      </section>

      <!-- 3. OPENSTACK VM MANAGEMENT PANEL (KT CLOUD STYLE UPGRADE) -->
      <section id="osvm-panel" style="display: none;">
        <div class="overview-hero" style="background: linear-gradient(135deg, rgba(139, 92, 246, 0.25), rgba(15, 23, 42, 0.8)); border: 1px solid rgba(167, 139, 250, 0.3);">
          <h2>🖥️ 온프레미스 OpenStack IaaS 가상머신 전원 & 자원 제어 센터</h2>
          <p>KT Cloud VM과 동일하게 OpenStack Nova REST API(v2.1)를 직접 연동하여 K8s 가상머신의 전원(ON/OFF)과 재부팅을 실시간으로 관리합니다. 가상머신을 선택하고 버튼 하나로 전원을 제어하세요.</p>
        </div>

        <!-- STATS OVERVIEW -->
        <div class="stats-grid">
          <div class="stat-card">
            <div class="label">총 오픈스택 VM 수</div>
            <div class="value" id="os-stat-total">3</div>
            <div class="subtext">K8s 클러스터 인벤토리</div>
          </div>
          <div class="stat-card">
            <div class="label">정상 가동 (ACTIVE)</div>
            <div class="value" id="os-stat-active" style="color:#34d399;">3</div>
            <div class="subtext">정상 서비스 처리 중</div>
          </div>
          <div class="stat-card">
            <div class="label">정지 상태 (SHUTOFF)</div>
            <div class="value" id="os-stat-shutoff" style="color:#f87171;">0</div>
            <div class="subtext">전원 차단 및 자원 회수</div>
          </div>
          <div class="stat-card">
            <div class="label">상위 호스트 VMware 노드</div>
            <div class="value" id="os-stat-vmware" style="color:#a78bfa;">3 노드</div>
            <div class="subtext">Controller 1 + Compute 2</div>
          </div>
        </div>

        <!-- VM SELECTOR TABS -->
        <div style="display:flex; align-items:center; gap:10px; margin-top:4px;">
          <span style="font-size:13px; font-weight:700; color:#cbd5e1;">🎯 제어 대상 가상머신 선택:</span>
          <div style="display:flex; gap:8px;" id="os-vm-tab-buttons">
            <button class="btn-top" id="btn-tab-cp1" style="background:#8b5cf6; color:#fff; font-weight:700;" onclick="selectOsVm('k8s-cp1')">k8s-cp1 (Master/DB)</button>
            <button class="btn-top" id="btn-tab-w1" onclick="selectOsVm('k8s-w1')">k8s-w1 (Worker 1)</button>
            <button class="btn-top" id="btn-tab-w2" onclick="selectOsVm('k8s-w2')">k8s-w2 (Worker 2)</button>
          </div>
          <button class="btn-action btn-refresh" style="margin-left:auto; font-size:11px; padding:6px 12px;" onclick="fetchOsVmStatus(true)">
            <span>🔍</span> 최신 상태 새로고침
          </button>
        </div>

        <!-- MAIN SELECTED VM CONTROL BOX (KT CLOUD STYLE) -->
        <div class="kt-vm-box" id="os-focused-box" style="border: 1px solid rgba(139, 92, 246, 0.4); box-shadow: 0 4px 20px rgba(0,0,0,0.3);">
          <div class="kt-vm-header">
            <div class="kt-vm-title">
              <span style="font-size:28px;">🖥️</span>
              <div>
                <div style="display:flex; align-items:center; gap:10px;">
                  <span class="kt-vm-name" id="os-display-name">k8s-cp1</span>
                  <span class="menu-badge" id="os-display-role" style="background:#b45309; color:#fff; font-size:11px; padding:3px 10px;">K8s Control Plane & Primary DB</span>
                </div>
                <div style="font-size: 11px; color: #94a3b8; font-family: monospace; margin-top:2px;" id="os-display-id">ID: dd0ee22c-caad-4f47-90ca-47c88d8e539f</div>
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
              <div class="prop-label">Floating IP (외부 공인/대민망)</div>
              <div class="prop-val" id="os-floating-ip" style="color:#38bdf8;">192.168.120.226</div>
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
              <div class="prop-val" id="os-host" style="color:#a78bfa;">compute1 (OpenStack Nova)</div>
            </div>
            <div class="prop-item">
              <div class="prop-label">전원 및 서비스 헬스 상태</div>
              <div class="prop-val" id="os-health" style="color:#34d399;">정상 가동 중 (Read/Write 활성)</div>
            </div>
          </div>

          <!-- CONTROL ACTION BUTTONS (IDENTICAL TO KT CLOUD) -->
          <div class="kt-ctrl-bar">
            <span style="font-size:12px; font-weight:700; color:#94a3b8; margin-right:6px;">전원 및 자원 명령:</span>
            <button class="btn-action btn-stop" id="btn-os-stop" onclick="confirmSelectedOsAction('stop')">
              <span>🛑</span> 전원 끄기 (Stop)
            </button>
            <button class="btn-action btn-start" id="btn-os-start" disabled onclick="confirmSelectedOsAction('start')">
              <span>⚡</span> 전원 켜기 (Start)
            </button>
            <button class="btn-action btn-reboot" id="btn-os-reboot" onclick="confirmSelectedOsAction('reboot')">
              <span>↻</span> 소프트 재부팅 (Reboot)
            </button>
            <button class="btn-action" id="btn-os-hard-reboot" style="background:#475569; color:#fff;" onclick="confirmSelectedOsAction('hard_reboot')">
              <span>⚡</span> 강제 재부팅 (Hard Reset)
            </button>
            <button class="btn-action btn-refresh" id="btn-os-refresh" onclick="fetchOsVmStatus(true)">
              <span>🔍</span> 상태 새로고침
            </button>
            <button class="btn-action" id="btn-os-reachability" style="background:#0284c7; color:#fff; font-weight:700;" onclick="openReachabilityModal()">
              <span>📡</span> Argo CD · Grafana 도달 범위 확인
            </button>
            <span id="os-action-spinner" style="display:none; font-size:12px; color:#a78bfa; margin-left:auto; font-weight:600;">
              ⏳ OpenStack Nova API 작업 처리 중...
            </span>
          </div>

          <!-- ACTIVITY CONSOLE LOG -->
          <div>
            <div style="font-size:12px; font-weight:700; color:#cbd5e1; margin-bottom:8px; display:flex; justify-content:space-between;">
              <span>📋 OpenStack Nova REST API 실행 콘솔 로그</span>
              <span style="font-size:11px; color:#64748b;">Nova v2.1 API 통신 실시간 스트림</span>
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
          <span>📋 온프레미스 전체 VM 인벤토리 요약</span>
        </div>
        <div class="cards-grid" id="os-vm-grid">
          <!-- Rendered dynamically by JS -->
        </div>

        <!-- VMWARE HYPERVISOR NODES -->
        <div class="kt-vm-box" style="margin-top: 4px;">
          <div class="kt-vm-header">
            <div class="kt-vm-title">
              <span style="font-size:22px;">🏢</span>
              <div>
                <div class="kt-vm-name" style="font-size:16px;">물리 호스트 VMware 노드 현황 (GPU 서버 10.10.10.8)</div>
                <div style="font-size: 11px; color: #94a3b8;">Workstation Hypervisor 레이어 (vmrun 호스트 제어 가능)</div>
              </div>
            </div>
            <span class="kt-vm-badge state-running"><span class="dot green"></span>Hypervisor Running</span>
          </div>
          <div class="kt-props-grid" id="vmware-nodes-grid">
            <div class="prop-item">
              <div class="prop-label">openstack (Controller VM)</div>
              <div class="prop-val" style="color:#38bdf8;">192.168.120.160 · Keystone / Nova / Horizon</div>
            </div>
            <div class="prop-item">
              <div class="prop-label">compute1 (Compute Node 1)</div>
              <div class="prop-val" style="color:#34d399;">가상 CPU / RAM 가상화 하이퍼바이저 활성</div>
            </div>
            <div class="prop-item">
              <div class="prop-label">compute2 (Compute Node 2)</div>
              <div class="prop-val" style="color:#34d399;">가상 CPU / RAM 가상화 하이퍼바이저 활성</div>
            </div>
          </div>
        </div>
      </section>

                  <!-- 4. v3.0 DRAWIO TECHNICAL ARCHITECTURE & OPERATION DASHBOARD -->
      <section id="dr-panel" style="display: none;">
        <div class="overview-hero" style="background: linear-gradient(135deg, rgba(212, 147, 15, 0.2), rgba(15, 23, 42, 0.85)); border: 1px solid rgba(212, 147, 15, 0.4);">
          <div style="display:flex; justify-content:space-between; align-items:flex-start; flex-wrap:wrap; gap:10px;">
            <div>
              <h2 style="color:#fde68a;">민원불패 — 통합 운영 대시보드 (실시간 동적 제어 & 관제)</h2>
              <p style="margin-top:4px;"><b>설계문서 v3.0 drawio</b> 명세 100% 구현: KT Cloud Edge-GW(입구) ↔ WireGuard 터널 3개 메쉬 ↔ 온프레미스 K8s MSA & MySQL Primary ↔ AWS DR 관제 스택 & Orchestrator 상태 머신.</p>
            </div>
            <div style="display:flex; gap:8px;">
              <span class="tunnel-badge tunnel-a">터널 A: 평시 요청 (KT↔온프렘)</span>
              <span class="tunnel-badge tunnel-b">터널 B: 복제·관측·L2복구 (AWS↔온프렘)</span>
              <span class="tunnel-badge tunnel-c">터널 C: DR 전환 (KT↔AWS)</span>
            </div>
          </div>
        </div>

        <!-- CONTROL BAR & FLOW VELOCITY CONTROLLER -->
        <div style="background:#0f172a; padding:14px 18px; border-radius:12px; border:1px solid #334155; margin-bottom:12px; display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:14px;">
          <div style="display:flex; align-items:center; gap:10px; flex-wrap:wrap;">
            <button id="btn-open-console" class="btn-top" style="background:#0284c7; color:#fff; font-weight:800; font-size:12.5px; padding:8px 16px; border-radius:6px; cursor:pointer; display:flex; align-items:center; gap:6px;" onclick="openConsoleModal()">
              <span>📋</span> 콘솔확인
            </button>
            <button id="btn-reach-toggle" class="btn-top" style="background:rgba(56,189,248,0.15); color:#38bdf8; border:1px solid #38bdf8; font-weight:700; font-size:12px; padding:7px 14px; border-radius:6px; cursor:pointer; display:flex; align-items:center; gap:6px;" onclick="window.toggleReachabilityOverlay && window.toggleReachabilityOverlay()">
              <span>📡</span> <span id="btn-reach-text">도달 범위 & 격리선 표시</span>
            </button>
            <button class="btn-top" style="background:rgba(195,166,255,0.15); color:#c3a6ff; border:1px solid #c3a6ff; font-weight:700; font-size:12px; padding:7px 14px; border-radius:6px; cursor:pointer; display:flex; align-items:center; gap:6px;" onclick="openReachModal()">
              <span>🗺️</span> 도달 범위 검증 모달
            </button>
            <div style="font-size:11px; color:#cbd5e1; background:rgba(30,41,59,0.7); padding:6px 12px; border-radius:6px; border:1px solid #475569;">
              💡 <b>방어 체계</b>: 1~2단계 <b>자가치유 장애복구</b> (Pod·Ansible) ➔ 3~4단계 <b>광역 DR 절체</b> (AWS Promotion)
            </div>
          </div>

          <!-- 동적 트래픽 흐름 속도 인디케이터 (Flow Velocity Gauge) -->
          <div style="display:flex; align-items:center; gap:16px;">
            <div style="text-align:right;">
              <div style="font-size:10px; color:#94a3b8; font-weight:700; text-transform:uppercase;">트래픽 흐름 속도 (Flow Velocity)</div>
              <div id="dr-velocity-text" style="font-size:12.5px; font-weight:800; color:#34d399;">⚡ 180 req/s · RTT 4.2ms [VERY FAST]</div>
            </div>
            <div id="dr-velocity-meter" style="display:flex; gap:3px; align-items:flex-end; height:24px;">
              <div class="meter-bar" id="v-bar-1" style="width:4px; height:8px; background:#34d399; border-radius:2px;"></div>
              <div class="meter-bar" id="v-bar-2" style="width:4px; height:14px; background:#34d399; border-radius:2px;"></div>
              <div class="meter-bar" id="v-bar-3" style="width:4px; height:20px; background:#34d399; border-radius:2px;"></div>
              <div class="meter-bar" id="v-bar-4" style="width:4px; height:24px; background:#34d399; border-radius:2px;"></div>
            </div>
          </div>
        </div>

        <!-- 7-STAGE SCENARIO CONTROLLER BUTTONS (v3.0 drawio Page 03 반영) -->
        <div style="background:#131c2e; padding:14px; border-radius:12px; border:1px solid #334155;">
          <div style="font-size:11px; font-weight:700; color:#94a3b8; margin-bottom:8px; text-transform:uppercase; letter-spacing:0.5px; display:flex; justify-content:space-between;">
            <span>🎮 단계별 시뮬레이션 (미선택 시 기본 전체 흐름 작동 ➔ 단계 선택 시 해당 단계 우선 작동):</span>
            <span style="color:#38bdf8; font-size:11px;">구성도의 각 컴포넌트를 클릭하면 실시간 제어 액션이 작동합니다.</span>
          </div>
          <div style="display:flex; gap:8px; flex-wrap:wrap;" id="dr-v3-btns">
            <button class="btn-top" id="btn-v3-normal" style="background:#10b981; color:#fff; font-weight:700;" onclick="setV3Stage('normal')">
              🌐 전체 통합 흐름 (기본 정상)
            </button>
            <button class="btn-top" id="btn-v3-l1" onclick="setV3Stage('l1')">
              🟡 2. L1: Pod 크래시 자가치유 (초 단위)
            </button>
            <button class="btn-top" id="btn-v3-l2" onclick="setV3Stage('l2')">
              🟠 3. L2: 서비스 1분 무응답 ➔ 터널 B Ansible 재기동 (≤3분)
            </button>
            <button class="btn-top" id="btn-v3-path" onclick="setV3Stage('path')">
              🔵 4. 경로장애: 터널 A 단절 (S1·S3 실패, S2 정상) ➔ 터널 C·B 우회 (DB 승격 금지)
            </button>
            <button class="btn-top" id="btn-v3-l3" onclick="setV3Stage('l3')">
              🔴 5. L3: 온프렘 마비 (S1∧S2∧S3 실패) ➔ 펜싱 확인 ➔ AWS Replica 승격
            </button>
            <button class="btn-top" id="btn-v3-l4" onclick="setV3Stage('l4')">
              🟣 6. L4: 복구 검증 ➔ 역방향 GTID 동기화 ➔ 온프렘 승격 (Failback)
            </button>
            <button class="btn-top" id="btn-v3-bs" onclick="setV3Stage('bs')">
              ⚫ 7. Black Sky: 전면 불능 ➔ Cloudflare ➔ GitHub Pages 0초 폴백
            </button>
          </div>
        </div>

        <!-- MAIN ARCHITECTURE CANVAS (v3.0 drawio 1:1 토폴로지 레이아웃) -->
        <div class="arch-container" id="arch-canvas">
          
          <!-- ======================================================== -->
          <!-- ZONE 1: KT CLOUD — 입구 전용 (VM 1대)                     -->
          <!-- ======================================================== -->
          <div class="arch-zone zone-kt" id="zone-kt-box">
            <div class="zone-title" style="color:#38bdf8;">
              <span>🌐 KT Cloud — 입구 전용</span>
              <span class="menu-badge" style="background:#0284c7; color:#fff;">Edge-GW 1대</span>
            </div>

            <!-- CITIZEN ACCESS -->
            <div style="background:#0f172a; border:1px solid #334155; border-radius:8px; padding:10px; text-align:center;">
              <div style="font-size:18px;">👤 ➔ 🛡️</div>
              <div style="font-size:12px; font-weight:800; color:#fff;">대민 사용자 & Cloudflare</div>
              <div style="font-size:10px; color:#94a3b8;">HTTPS Anycast WAF 종료</div>
            </div>

            <!-- Edge-GW VM -->
            <div class="arch-subnet" id="subnet-kt-edge" style="background:rgba(2, 132, 199, 0.1); border-color:#0284c7;">
              <div class="subnet-label" style="color:#38bdf8;">Edge-GW VM (k-vm1 · 공인 14.63.213.214)</div>
              <div style="font-size:11px; color:#cbd5e1; line-height:1.5;">
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
            <div style="background:#0f172a; border:1px solid #334155; border-radius:8px; padding:8px; font-size:11px;">
              <span style="font-weight:700; color:#94a3b8;">S3 프로브:</span>
              <span id="txt-s3-status" style="color:#34d399; font-weight:700;">정상 통과 🟢</span>
            </div>

            <!-- 0-SEC GITHUB PAGES FALLBACK PREVIEW -->
            <div class="arch-subnet" id="subnet-gh-fallback" style="border-color:#475569; opacity:0.6;">
              <div class="subnet-label">최후의 0초 방어선 (GitHub Pages)</div>
              <div style="font-size:11px; color:#94a3b8;">
                dr.ktci5.kr 정적 비상 접수처
              </div>
              <span class="menu-badge" id="gh-badge" style="background:#475569; color:#fff; width:fit-content;">STANDBY ⚪</span>
            </div>
          </div>

          <!-- ======================================================== -->
          <!-- ZONE 2: 온프레미스 OpenStack — 메인 (민원 서비스 Primary)    -->
          <!-- ======================================================== -->
          <div class="arch-zone zone-onprem" id="zone-onprem-box">
            <div class="zone-title" style="color:#34d399;">
              <span>🏢 온프레미스 OpenStack — 메인 (Primary)</span>
              <span class="menu-badge" id="badge-onprem-mode" style="background:#10b981; color:#fff;">PRIMARY RW 🟢</span>
            </div>

            <!-- 외부망 서브넷: WG GW -->
            <div class="arch-subnet" id="subnet-onprem-wg">
              <div class="subnet-label" style="color:#fbbf24; font-weight:800;">🌐 [외부망 DMZ] br-ex (FIP 10.11.0.0/24 · WG 터널 종단)</div>
              <div style="display:flex; justify-content:space-between; align-items:center;">
                <div style="font-size:12px; font-weight:800; color:#fff;">🔐 WireGuard 게이트웨이</div>
                <span style="font-size:10px; color:#10b981;">터널 A·B 발신 · Watchdog</span>
              </div>
              <div style="font-size:10px; color:#94a3b8;" id="txt-fencing">자가 펜싱 감시 중: 정상 (쓰기 허용)</div>
            </div>

            <!-- k8s 서브넷: K3s MSA -->
            <div class="arch-subnet" id="subnet-onprem-k8s" style="border-color:#10b981;">
              <div class="subnet-label" style="color:#34d399; font-weight:800;">🏢 [내부망 SERVICE] net-k3s (10.10.1.0/24 · K3s 클러스터)</div>
              <div style="font-size:11px; font-weight:700; color:#38bdf8; margin-bottom:2px;">
                ingress-nginx (MetalLB VIP · 경로 라우팅)
              </div>
              
              <!-- app 네임스페이스 -->
              <div style="background:#0b1120; padding:8px; border-radius:6px; margin-bottom:6px;">
                <div style="font-size:10px; font-weight:700; color:#a78bfa; margin-bottom:4px;">app 네임스페이스 (MSA 4개 서비스)</div>
                <div class="k8s-pod-grid">
                  <div class="k8s-pod-chip pod-active" id="pod-web">
                    <span>🖥️</span> <span>web ×2</span>
                  </div>
                  <div class="k8s-pod-chip pod-active" id="pod-api">
                    <span>⚙️</span> <span>minwon-api (HPA)</span>
                  </div>
                  <div class="k8s-pod-chip pod-active" id="pod-notify">
                    <span>🔔</span> <span>notify-worker</span>
                  </div>
                  <div class="k8s-pod-chip pod-active" id="pod-audit">
                    <span>📜</span> <span>audit-worker</span>
                  </div>
                </div>
              </div>

              <!-- data 네임스페이스 (DR 복제 안함) -->
              <div style="background:#0b1120; padding:6px 8px; border-radius:6px; display:flex; justify-content:space-between; font-size:11px;">
                <span style="color:#64748b;">로컬 캐시/큐:</span>
                <span style="color:#cbd5e1;">⚡ Redis · 🐰 RabbitMQ</span>
              </div>
            </div>

            <!-- data 서브넷: MySQL Primary -->
            <div class="arch-subnet" id="subnet-onprem-db" style="border-color:#ef4444; background:rgba(239, 68, 68, 0.05);">
              <div class="subnet-label" style="color:#f87171; font-weight:800;">🔒 [폐쇄망 ISOLATED] net-data (10.10.2.0/24 · No-Gateway 완전 격리)</div>
              <div style="display:flex; justify-content:space-between; align-items:center;">
                <div style="font-size:13px; font-weight:800; color:#fff;">🗄️ MySQL 8.4 Primary (Cinder 영속 볼륨)</div>
                <span class="menu-badge" id="badge-db-rw" style="background:#10b981; color:#fff;">Read / Write</span>
              </div>
              <div style="font-size:11px; color:#cbd5e1; line-height:1.4;">
                • 스키마: <code>minwon</code> · <code>notify</code> · <code>audit</code><br>
                • <b>L3 인터넷 단절</b> (외부 직접 인바운드/아웃바운드 100% 차단)<br>
                • 허용: 오직 내부망 <code>10.10.1.0/24:3306</code> 및 터널 B 복제만 허용
              </div>
            </div>

            <!-- ops 서브넷 -->
            <div class="arch-subnet">
              <div class="subnet-label">ops 서브넷 (프라이빗)</div>
              <div style="font-size:11px; color:#94a3b8;">⛵ Harbor (이미지 레지스트리) · 🐙 Argo CD (GitOps 배포)</div>
            </div>
          </div>

          <!-- ======================================================== -->
          <!-- ZONE 3: AWS — 관제 · DR 대기 · 백업 (제3 관측점)            -->
          <!-- ======================================================== -->
          <div class="arch-zone zone-aws" id="zone-aws-box">
            <div class="zone-title" style="color:#fbbf24;">
              <span>☁️ AWS — 관제 · DR 대기 (제3 관측점)</span>
              <span class="menu-badge" id="badge-aws-mode" style="background:#f59e0b; color:#fff;">PILOT-LIGHT RO 🟡</span>
            </div>

            <!-- 관제 서브넷: aws-ctl-01 -->
            <div class="arch-subnet" id="subnet-aws-ctl" style="border-color:#f59e0b;">
              <div class="subnet-label" style="color:#fbbf24;">관제 서브넷 (aws-ctl-01 · 제3 관측 판정)</div>
              <div style="display:flex; justify-content:space-between; align-items:center;">
                <div style="font-size:12px; font-weight:800; color:#fff;">📊 관제 스택 & Orchestrator</div>
                <span style="font-size:10px; color:#38bdf8;">Blackbox S1/S2 프로브</span>
              </div>
              <div style="font-size:11px; color:#cbd5e1; line-height:1.4;">
                • Prometheus · Grafana · Loki<br>
                • <b>Recovery Orchestrator 상태 머신</b><br>
                • 3-Signal 판정 ➔ L2 Ansible / L3 승격 통제
              </div>
              <!-- STATE MACHINE CURRENT STEP -->
              <div style="background:#0b1120; padding:6px 10px; border-radius:6px; font-size:11px; display:flex; justify-content:space-between; align-items:center;">
                <span style="color:#94a3b8;">오케스트레이터 상태:</span>
                <span id="txt-orch-state" style="font-weight:800; color:#10b981;">NORMAL (온프렘 가동)</span>
              </div>
            </div>

            <!-- DR 서브넷: Pilot-Light EC2 -->
            <div class="arch-subnet" id="subnet-aws-dr" style="border-color:#475569;">
              <div class="subnet-label" style="color:#fbbf24;">DR 서브넷 (프라이빗 Pilot-Light)</div>
              <div style="display:flex; justify-content:space-between; align-items:center;">
                <div style="font-size:13px; font-weight:800; color:#fff;">🗄️ MySQL 8.4 Replica</div>
                <span class="menu-badge" id="badge-aws-db-ro" style="background:#f59e0b; color:#fff;">super_read_only = ON</span>
              </div>
              <div style="font-size:11px; color:#cbd5e1; line-height:1.4;">
                • 평소 최소 사양 대기 ➔ L3 시 즉각 확장<br>
                • 온프렘 Primary로부터 GTID 비동기 수신<br>
                • L3 승격 시 쓰기 모드로 전환
              </div>
            </div>

            <!-- Amazon S3 백업 -->
            <div class="arch-subnet">
              <div class="subnet-label" style="color:#f59e0b;">Amazon S3 (불변 백업 스토리지)</div>
              <div style="font-size:11px; color:#cbd5e1;">
                • 덤프 6시간 주기 · <b>binlog 15분 주기</b><br>
                • L4 시점 복원(PITR) 소스
              </div>
            </div>

            <!-- Lambda + EventBridge -->
            <div class="arch-subnet">
              <div class="subnet-label">Dead-man Switch</div>
              <div style="font-size:10px; color:#94a3b8;">관제 Watchdog 끊김 시 Slack 즉각 사람 호출 (P7)</div>
            </div>
          </div>

          <!-- SVG DYNAMIC WIRE-GUARD & TRAFFIC MESH OVERLAY -->
          <svg style="position:absolute; top:0; left:0; width:100%; height:100%; pointer-events:none; z-index:5;" id="v3-svg-overlay">
            <!-- Tunnel A: KT Edge -> OnPrem (Yellow Dashed Laser) -->
            <path id="path-tunnel-a" d="M 230 180 C 260 180, 260 110, 275 110" class="flow-line line-yellow" fill="none" />
            <!-- Tunnel B: AWS -> OnPrem (Blue Dashed Laser) -->
            <path id="path-tunnel-b" d="M 525 150 C 490 150, 485 110, 470 110" class="flow-line line-blue" fill="none" />
            <!-- Tunnel C: KT Edge -> AWS DR (Purple Failover Line) -->
            <path id="path-tunnel-c" d="M 230 200 C 350 200, 400 320, 525 320" class="line-inactive" fill="none" />
            <!-- Internal DB Sync: OnPrem DB -> Tunnel B -> AWS Replica -->
            <path id="path-db-sync" d="M 470 380 C 490 380, 500 320, 525 320" class="flow-line line-yellow" fill="none" />
          </svg>
        </div>

        <!-- ORCHESTRATOR STATUS & RTO REAL-TIME VERIFICATION CARD -->
        <div class="kt-vm-box" style="margin-top:14px; background:#1e293b; border:1px solid #334155;">
          <div style="display:flex; justify-content:space-between; align-items:center; border-bottom:1px solid #334155; padding-bottom:12px; margin-bottom:12px;">
            <div>
              <div style="font-size:16px; font-weight:800; color:#fff;" id="v3-stage-title">
                🟢 NORMAL: 평시 온프렘 Primary 가동 (터널 A 요청 수용 + 터널 B GTID 복제)
              </div>
              <div style="font-size:12px; color:#94a3b8; margin-top:2px;" id="v3-stage-desc">
                v3.0 설계 원칙: 공개 지점은 KT Edge 1곳(443 + WG UDP), 모든 사이트 간 트래픽은 WireGuard로 상시 암호화됩니다.
              </div>
            </div>
            <span class="kt-vm-badge state-running" id="v3-status-badge"><span class="dot green"></span>NORMAL STATUS</span>
          </div>

          <div class="kt-props-grid" style="grid-template-columns: repeat(4, 1fr); margin-bottom:12px;">
            <div class="prop-item">
              <div class="prop-label">Orchestrator 상태 머신</div>
              <div class="prop-val" id="v3-prop-sm" style="color:#10b981;">NORMAL</div>
            </div>
            <div class="prop-item">
              <div class="prop-label">3-Signal 판정 결과</div>
              <div class="prop-val" id="v3-prop-signal" style="color:#38bdf8;">S1:정상 · S2:정상 · S3:정상</div>
            </div>
            <div class="prop-item">
              <div class="prop-label">목표 RTO / RPO 규격</div>
              <div class="prop-val" id="v3-prop-rto" style="color:#34d399;">RTO: 0초 · RPO: 0초</div>
            </div>
            <div class="prop-item">
              <div class="prop-label">WireGuard 터널 가동 상태</div>
              <div class="prop-val" id="v3-prop-tunnel" style="color:#fbbf24;">터널 A·B 활성 (C 대기)</div>
            </div>
          </div>

          <!-- DETAILED SOP ACTIONS -->
          <div style="background:#090e17; padding:12px 16px; border-radius:8px; border:1px solid #334155; font-size:12px; color:#cbd5e1; line-height:1.6;" id="v3-sop-text">
            <b>[v3.0 정상 가동 트래픽 & 보안 흐름]</b><br>
            • <b>대민 진입</b>: HTTPS 요청이 KT Edge-GW(14.63.213.214)에 도착하여 TLS 종료 및 Nginx WAF 검사를 받습니다.<br>
            • <b>터널 A 전송</b>: 온프렘 WireGuard 게이트웨이로 단방향 요청 전달 ➔ ingress-nginx ➔ <code>web ×2</code> ➔ <code>minwon-api ×2</code> ➔ <code>MySQL Primary</code> 커밋.<br>
            • <b>터널 B 복제</b>: MySQL GTID 이벤트가 터널 B를 타고 AWS Replica(super_read_only=ON)로 비동기 복제되고 관제 메트릭이 수집됩니다.
          </div>

          <!-- INDIVIDUAL POD & COMPONENT LEVEL DRILL-DOWN (개별/파드단위 상세 뷰) -->
          <div style="margin-top:14px; background:#0b1120; padding:14px; border-radius:8px; border:1px solid #334155;">
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:10px;">
              <span style="font-size:13px; font-weight:800; color:#e2e8f0;">🔍 개별 인스턴스 및 파드 단위(Pod Level) 실시간 상태</span>
              <span style="font-size:11px; color:#94a3b8;">자가치유 장애복구(L1·L2) vs 광역 DR(L3·L4) 단위별 추적</span>
            </div>
            <div style="display:grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap:10px;">
              <!-- Pod 1 -->
              <div style="background:#131d31; border:1px solid #334155; padding:10px; border-radius:6px;" id="pod-card-w1">
                <div style="display:flex; justify-content:space-between; align-items:center;">
                  <span style="font-size:11px; font-weight:700; color:#38bdf8;">os-a: k8s-w1 (Pod #1)</span>
                  <span class="menu-badge" id="badge-pod-w1" style="background:#10b981; color:#fff;">RUNNING 🟢</span>
                </div>
                <div style="font-size:11px; color:#94a3b8; margin-top:6px;">
                  • 역할: 민원 웹/API 컨테이너 #1<br>
                  • 상태: <span id="txt-pod-w1-status" style="color:#34d399;">정상 처리 중 (0 restart)</span>
                </div>
              </div>

              <!-- Pod 2 -->
              <div style="background:#131d31; border:1px solid #334155; padding:10px; border-radius:6px;" id="pod-card-w2">
                <div style="display:flex; justify-content:space-between; align-items:center;">
                  <span style="font-size:11px; font-weight:700; color:#38bdf8;">os-a: k8s-w2 (Pod #2)</span>
                  <span class="menu-badge" id="badge-pod-w2" style="background:#10b981; color:#fff;">RUNNING 🟢</span>
                </div>
                <div style="font-size:11px; color:#94a3b8; margin-top:6px;">
                  • 역할: 민원 웹/API 컨테이너 #2<br>
                  • 상태: <span id="txt-pod-w2-status" style="color:#34d399;">정상 트래픽 분산 (0 restart)</span>
                </div>
              </div>

              <!-- DB Primary -->
              <div style="background:#131d31; border:1px solid #334155; padding:10px; border-radius:6px;" id="pod-card-db">
                <div style="display:flex; justify-content:space-between; align-items:center;">
                  <span style="font-size:11px; font-weight:700; color:#34d399;">os-a: a-db-01 (MySQL)</span>
                  <span class="menu-badge" id="badge-pod-db" style="background:#10b981; color:#fff;">PRIMARY RW 🟢</span>
                </div>
                <div style="font-size:11px; color:#94a3b8; margin-top:6px;">
                  • 스토리지: Cinder 영속 볼륨 바인딩<br>
                  • 복제: <span id="txt-pod-db-status" style="color:#34d399;">GTID 스트리밍 송출 (Lag: 0s)</span>
                </div>
              </div>

              <!-- AWS DR Replica -->
              <div style="background:#131d31; border:1px solid #334155; padding:10px; border-radius:6px;" id="pod-card-aws">
                <div style="display:flex; justify-content:space-between; align-items:center;">
                  <span style="font-size:11px; font-weight:700; color:#fbbf24;">aws-dr-01 (Pilot-Light)</span>
                  <span class="menu-badge" id="badge-pod-aws" style="background:#475569; color:#fff;">STANDBY RO 🟡</span>
                </div>
                <div style="font-size:11px; color:#94a3b8; margin-top:6px;">
                  • 파드 상태: <span id="txt-pod-aws-pods" style="color:#94a3b8;">Replicas: 0 (L3 승격 대기)</span><br>
                  • DB 복제: <span id="txt-pod-aws-db" style="color:#38bdf8;">Semi-sync 수신 (ACK 확정)</span>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- ACTIONABLE DISASTER DRILL CONSOLE -->
        <div class="section-title" style="margin-top:6px;">
          <span>⚡ 실제 클러스터 카오스 모의훈련 및 긴급 명령</span>
        </div>
        <div class="kt-vm-box">
          <div style="display:flex; gap:10px; flex-wrap:wrap;">
            <button class="btn-action" style="background:#0284c7; color:#fff;" onclick="triggerChaosCrash()">
              <span>💥</span> L1: Pod 강제 크래시 모의 (/chaos/crash)
            </button>
            <button class="btn-action" style="background:#8b5cf6; color:#fff;" onclick="switchTab('osvm')">
              <span>🛑</span> L2: OpenStack 워커 노드 강제 정지 (VM)
            </button>
            <button class="btn-action" style="background:#f59e0b; color:#fff;" onclick="showL3Guide()">
              <span>⚠️</span> L3: AWS DR 수동 절체 표준 절차 (SOP)
            </button>
            <a href="https://figteam.ktci5.kr/fallback-preview" target="_blank" class="btn-action" style="background:#334155; color:#cbd5e1; text-decoration:none;">
              <span>📄</span> Black Sky: 0초 비상 접수처 열기 ↗
            </a>
          </div>

          <div class="kt-log-box" id="dr-log-console" style="margin-top:14px; height:120px;">
            <div class="log-line">
              <span class="log-time">[v3.0-ARCH]</span>
              <span class="log-msg">민원불패 v3.0 전문 아키텍처 다이어그램 캔버스가 활성화되었습니다. 상단 7개 시나리오를 선택하세요.</span>
            </div>
          </div>
        </div>
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
        <div id="frame-setup-guide" style="display:none; background:#0f172a; border-bottom:1px solid #334155; padding:14px 20px; font-size:12px; color:#cbd5e1;">
          <div style="display:flex; justify-content:space-between; align-items:flex-start; margin-bottom:8px;">
            <div>
              <span style="font-size:14px; font-weight:800; color:#fff;" id="guide-service-title">폐쇄망 서비스 기본 설정</span>
              <span class="menu-badge" id="guide-service-badge" style="background:#0284c7; color:#fff; margin-left:8px;">CLOSED-NETWORK</span>
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
        <div style="background:#0f172a; border:1px solid #38bdf8; width:92%; max-width:880px; max-height:90vh; border-radius:12px; overflow-y:auto; box-shadow:0 20px 40px rgba(0,0,0,0.6); display:flex; flex-direction:column;">
          <!-- Modal Header -->
          <div style="padding:16px 20px; border-bottom:1px solid #334155; display:flex; justify-content:space-between; align-items:center; background:#131c2e;">
            <div style="display:flex; align-items:center; gap:10px;">
              <span style="font-size:22px;">📡</span>
              <div>
                <div style="font-size:15px; font-weight:800; color:#fff;">폐쇄망·오픈스택 네트워크 격리 및 Argo CD · Grafana 도달 범위 검증</div>
                <div style="font-size:11px; color:#94a3b8;">WireGuard 10.200.0.0/24 풀메쉬 & OpenStack OVN (외부망·내부망·폐쇄망) 경로 추적</div>
              </div>
            </div>
            <button onclick="closeReachabilityModal()" style="background:transparent; border:none; color:#94a3b8; font-size:20px; cursor:pointer;">✕</button>
          </div>

          <!-- Modal Body -->
          <div style="padding:20px; display:flex; flex-direction:column; gap:18px;">
            <!-- Top Diagram Card -->
            <div style="background:#090e17; border:1px solid #334155; border-radius:8px; padding:16px;">
              <div style="font-size:13px; font-weight:700; color:#38bdf8; margin-bottom:10px;">🗺️ 영역별 도달 범위 토폴로지 (L2/L3 OVN & WireGuard 터널)</div>
              <div style="display:grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap:12px;">
                <!-- Argo CD Reachability -->
                <div style="background:#131d31; border:1px solid #334155; border-radius:6px; padding:12px;">
                  <div style="display:flex; justify-content:space-between; align-items:center;">
                    <span style="font-size:12px; font-weight:800; color:#f43f5e;">🚀 Argo CD Hub (b-k3s-01)</span>
                    <span class="menu-badge" style="background:#e11d48; color:#fff;">GitOps Hub</span>
                  </div>
                  <div style="font-size:11px; color:#cbd5e1; margin-top:8px; line-height:1.6;">
                    • <b>출발지 IP</b>: <code>10.21.0.10:8080</code> (os-b FIP)<br>
                    • ➔ <b>os-a k3s 마스터</b> (<code>10.10.1.10:6443</code>): <span style="color:#34d399; font-weight:700;">도달 가능 ✅</span> (파드 자동 배포)<br>
                    • ➔ <b>aws-dr k3s</b> (<code>10.200.0.22:6443</code>): <span style="color:#34d399; font-weight:700;">도달 가능 ✅</span> (DR 파드 동기화)<br>
                    • ➔ <b>폐쇄망 MySQL</b> (<code>10.10.2.10:3306</code>): <span style="color:#ef4444; font-weight:700;">도달 차단 🚫</span> (L3 No-Gateway)
                  </div>
                </div>

                <!-- Grafana Reachability -->
                <div style="background:#131d31; border:1px solid #334155; border-radius:6px; padding:12px;">
                  <div style="display:flex; justify-content:space-between; align-items:center;">
                    <span style="font-size:12px; font-weight:800; color:#f59e0b;">📈 Grafana 관제 (aws-ctl-01)</span>
                    <span class="menu-badge" style="background:#d97706; color:#fff;">Observability</span>
                  </div>
                  <div style="font-size:11px; color:#cbd5e1; margin-top:8px; line-height:1.6;">
                    • <b>출발지 IP</b>: <code>10.200.0.21:3000</code> (AWS WG IP)<br>
                    • ➔ <b>6노드 Node Exporter</b> (<code>:9100</code>): <span style="color:#34d399; font-weight:700;">도달 가능 ✅</span> (WG 풀메쉬 수집)<br>
                    • ➔ <b>k3s API & cAdvisor</b> (<code>:10250</code>): <span style="color:#34d399; font-weight:700;">도달 가능 ✅</span> (Pod 메트릭)<br>
                    • ➔ <b>폐쇄망 MySQL 포트</b> (<code>:3306</code>): <span style="color:#f59e0b; font-weight:700;">경유 수집 🟡</span> (mysqld_exporter 경유)
                  </div>
                </div>
              </div>
            </div>

            <!-- Reachability Matrix Table -->
            <div>
              <div style="font-size:13px; font-weight:700; color:#cbd5e1; margin-bottom:8px;">📊 오픈스택 망분리별 통신 허용 / 차단 매트릭스 (Security Group & OVN ACL)</div>
              <div style="overflow-x:auto;">
                <table style="width:100%; border-collapse:collapse; font-size:11.5px; text-align:left; color:#cbd5e1;">
                  <thead>
                    <tr style="background:#1e293b; color:#94a3b8; border-bottom:1px solid #475569;">
                      <th style="padding:8px 10px;">망 구분</th>
                      <th style="padding:8px 10px;">서브넷 대역</th>
                      <th style="padding:8px 10px;">배치 컴포넌트</th>
                      <th style="padding:8px 10px;">Argo CD 도달</th>
                      <th style="padding:8px 10px;">Grafana 도달</th>
                      <th style="padding:8px 10px;">외부 인터넷 (WAN)</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr style="border-bottom:1px solid #334155;">
                      <td style="padding:8px 10px; font-weight:700; color:#38bdf8;">1. 외부망 (br-ex)</td>
                      <td style="padding:8px 10px;"><code>10.11.0.0/24</code></td>
                      <td style="padding:8px 10px;">WG GW, Ingress VIP (MetalLB)</td>
                      <td style="padding:8px 10px; color:#34d399;">허용 (FIP 접근)</td>
                      <td style="padding:8px 10px; color:#34d399;">허용 (WG 터널)</td>
                      <td style="padding:8px 10px; color:#34d399;">NAT 허용</td>
                    </tr>
                    <tr style="border-bottom:1px solid #334155;">
                      <td style="padding:8px 10px; font-weight:700; color:#34d399;">2. 내부망 (net-k3s)</td>
                      <td style="padding:8px 10px;"><code>10.10.1.0/24</code></td>
                      <td style="padding:8px 10px;">k3s Master/Worker, MSA 웹/API Pods</td>
                      <td style="padding:8px 10px; color:#34d399; font-weight:700;">허용 (6443 API)</td>
                      <td style="padding:8px 10px; color:#34d399; font-weight:700;">허용 (9100/10250)</td>
                      <td style="padding:8px 10px; color:#f59e0b;">아웃바운드만 허용</td>
                    </tr>
                    <tr style="border-bottom:1px solid #334155; background:rgba(239, 68, 68, 0.08);">
                      <td style="padding:8px 10px; font-weight:700; color:#ef4444;">3. 폐쇄망 (net-data)</td>
                      <td style="padding:8px 10px;"><code>10.10.2.0/24</code></td>
                      <td style="padding:8px 10px;">MySQL Primary (Cinder 영속 볼륨)</td>
                      <td style="padding:8px 10px; color:#ef4444; font-weight:700;">완전 차단 🚫</td>
                      <td style="padding:8px 10px; color:#f59e0b; font-weight:700;">직접 접근 차단 🚫</td>
                      <td style="padding:8px 10px; color:#ef4444; font-weight:700;">완전 단절 (No GW)</td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>

            <!-- SSH Command Helper -->
            <div style="background:#090e17; padding:10px 14px; border-radius:6px; font-size:11px; color:#94a3b8; border:1px solid #334155;">
              <span style="font-weight:700; color:#cbd5e1;">💡 Mac 로컬에서 폐쇄망 콘솔 직접 터널링:</span><br>
              • Argo CD: <code>ssh -L 8080:10.21.0.10:8080 user@10.10.10.8</code> ➔ <code>http://localhost:8080</code><br>
              • Grafana: <code>ssh -L 3000:10.200.0.21:3000 user@10.10.10.8</code> ➔ <code>http://localhost:3000</code>
            </div>
          </div>

          <!-- Modal Footer -->
          <div style="padding:12px 20px; border-top:1px solid #334155; display:flex; justify-content:flex-end; background:#131c2e;">
            <button class="btn-action" style="background:#334155; color:#fff;" onclick="closeReachabilityModal()">닫기</button>
          </div>
        </div>
      </div>

      <!-- 5. LIVE OPERATION CONSOLE MODAL (콘솔 확인 팝업) -->
      <div id="console-modal" style="display:none; position:fixed; top:0; left:0; width:100%; height:100%; background:rgba(10,15,30,0.85); z-index:9999; backdrop-filter:blur(4px); align-items:center; justify-content:center;">
        <div style="background:#0f172a; border:1px solid #0284c7; width:92%; max-width:920px; max-height:90vh; border-radius:12px; overflow-y:auto; box-shadow:0 20px 40px rgba(0,0,0,0.6); display:flex; flex-direction:column;">
          <!-- Modal Header -->
          <div style="padding:16px 20px; border-bottom:1px solid #334155; display:flex; justify-content:space-between; align-items:center; background:#131c2e;">
            <div style="display:flex; align-items:center; gap:10px;">
              <span style="font-size:22px;">📋</span>
              <div>
                <div style="font-size:15px; font-weight:800; color:#fff;">통합 운영 콘솔 (Live Diagnostic & Activity Stream)</div>
                <div style="font-size:11px; color:#94a3b8;">오케스트레이터 상태 머신 · WireGuard 터널 헬스 · K8s 파드 이벤트 실시간 스트림</div>
              </div>
            </div>
            <button onclick="closeConsoleModal()" style="background:transparent; border:none; color:#94a3b8; font-size:20px; cursor:pointer;">✕</button>
          </div>

          <!-- Modal Body -->
          <div style="padding:20px; display:flex; flex-direction:column; gap:16px;">
            <!-- Real-time Diagnostic Grid -->
            <div style="display:grid; grid-template-columns:repeat(auto-fit, minmax(240px, 1fr)); gap:10px;">
              <div style="background:#131d31; border:1px solid #334155; border-radius:6px; padding:10px;">
                <div style="font-size:11px; font-weight:700; color:#38bdf8; margin-bottom:4px;">🔍 3-Signal 관제 프로브 상태</div>
                <div style="font-size:11px; color:#cbd5e1; line-height:1.5;">
                  • <b>S1 (공인 WAF 프로브)</b>: <span style="color:#34d399; font-weight:700;">PASS (HTTP 200)</span><br>
                  • <b>S2 (터널 B 사설 프로브)</b>: <span style="color:#34d399; font-weight:700;">PASS (RTT 1.8ms)</span><br>
                  • <b>S3 (터널 A 인그레스)</b>: <span style="color:#34d399; font-weight:700;">PASS (/readyz OK)</span>
                </div>
              </div>
              <div style="background:#131d31; border:1px solid #334155; border-radius:6px; padding:10px;">
                <div style="font-size:11px; font-weight:700; color:#fbbf24; margin-bottom:4px;">🌐 WireGuard 터널 핸드셰이크</div>
                <div style="font-size:11px; color:#cbd5e1; line-height:1.5;">
                  • <b>터널 A (KT↔온프렘)</b>: <span style="color:#34d399; font-weight:700;">ACTIVE (4s ago)</span><br>
                  • <b>터널 B (AWS↔온프렘)</b>: <span style="color:#34d399; font-weight:700;">ACTIVE (6s ago)</span><br>
                  • <b>터널 C (KT↔AWS)</b>: <span style="color:#94a3b8;">STANDBY (대기 중)</span>
                </div>
              </div>
              <div style="background:#131d31; border:1px solid #334155; border-radius:6px; padding:10px;">
                <div style="font-size:11px; font-weight:700; color:#34d399; margin-bottom:4px;">💾 MySQL 복제 & K8s 파드 상태</div>
                <div style="font-size:11px; color:#cbd5e1; line-height:1.5;">
                  • <b>GTID Replication Lag</b>: <span style="color:#34d399; font-weight:700;">0초 (동기화 완료)</span><br>
                  • <b>온프렘 파드 (Replicas)</b>: <span style="color:#34d399; font-weight:700;">2/2 RUNNING</span><br>
                  • <b>AWS Pilot-Light 파드</b>: <span style="color:#94a3b8;">0/2 (L3 대기)</span>
                </div>
              </div>
            </div>

            <!-- Terminal Output Box -->
            <div>
              <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:6px;">
                <span style="font-size:12px; font-weight:700; color:#e2e8f0;">📋 실시간 이벤트 및 명령어 실행 스트림 로그:</span>
                <button class="btn-top" style="padding:2px 8px; font-size:11px;" onclick="clearConsoleLog()">로그 지우기</button>
              </div>
              <div class="kt-log-box" id="modal-log-stream" style="height:260px; font-family:'IBM Plex Mono', monospace; font-size:11.5px; background:#070d17; border:1px solid #334155; padding:12px; border-radius:6px; overflow-y:auto;">
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
          <div style="padding:12px 20px; border-top:1px solid #334155; display:flex; justify-content:space-between; align-items:center; background:#131c2e;">
            <span style="font-size:11px; color:#94a3b8;">💡 각 컴포넌트의 액션 버튼을 클릭하면 여기에 결과가 실시간으로 기록됩니다.</span>
            <button class="btn-action" style="background:#334155; color:#fff;" onclick="closeConsoleModal()">닫기</button>
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
      dr: { title: "🛡️ 하이브리드 멀티클라우드 운영 대시보드", url: "" },
      horizon: { title: "☁️ OpenStack Horizon IaaS 콘솔", url: "https://horizon.ktci5.kr/dashboard/project/" },
      grafana: { title: "📈 Grafana 통합 관제 대시보드", url: "https://grafana.ktci5.kr" },
      argocd: { title: "🚀 Argo CD GitOps 배포 콘솔", url: "https://argocd.ktci5.kr" },
      minwon: { title: "🏛️ 민원청구 24시 센터 (대민 서비스)", url: "https://openstack.ktci5.kr" },
      ktedge: { title: "🌐 KT Cloud Edge 관리 콘솔", url: "https://kt-edge.ktci5.kr" }
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

    function switchTab(key) {
      if (!SERVICES[key]) return;
      currentTab = key;

      document.querySelectorAll('.menu-item').forEach(el => el.classList.remove('active'));
      const activeItem = Array.from(document.querySelectorAll('.menu-item')).find(el => {
        const text = el.innerText.toLowerCase();
        if (key === 'overview' && text.includes('개요')) return true;
        if (key === 'ktvm' && text.includes('kt cloud')) return true;
        if (key === 'osvm' && (text.includes('openstack') || text.includes('오픈스택'))) return true;
        if (key === 'dr' && text.includes('dr')) return true;
        if (key === 'horizon' && text.includes('horizon')) return true;
        if (key === 'grafana' && text.includes('grafana')) return true;
        if (key === 'argocd' && text.includes('argo')) return true;
        if (key === 'minwon' && text.includes('민원')) return true;
        if (key === 'ktedge' && text.includes('edge')) return true;
        return false;
      });
      if (activeItem) activeItem.classList.add('active');

      const overviewPanel = document.getElementById('overview-panel');
      const ktvmPanel = document.getElementById('ktvm-panel');
      const osvmPanel = document.getElementById('osvm-panel');
      const drPanel = document.getElementById('dr-panel');
      const iframePanel = document.getElementById('iframe-panel');
      const frame = document.getElementById('console-frame');
      const titleText = document.getElementById('frame-title-text');
      const extBtn = document.getElementById('external-link-btn');

      const setupGuide = document.getElementById('frame-setup-guide');
      const guideTitle = document.getElementById('guide-service-title');
      const guideBadge = document.getElementById('guide-service-badge');
      const guideBody = document.getElementById('guide-service-body');

      if (key === 'overview') {
        iframePanel.style.display = 'none';
        ktvmPanel.style.display = 'none';
        if (osvmPanel) osvmPanel.style.display = 'none';
        if (drPanel) drPanel.style.display = 'none';
        overviewPanel.style.display = 'flex';
        history.replaceState(null, '', '#overview');
      } else if (key === 'ktvm') {
        overviewPanel.style.display = 'none';
        iframePanel.style.display = 'none';
        if (osvmPanel) osvmPanel.style.display = 'none';
        if (drPanel) drPanel.style.display = 'none';
        ktvmPanel.style.display = 'flex';
        history.replaceState(null, '', '#ktvm');
        fetchKtVmStatus(true);
      } else if (key === 'osvm') {
        overviewPanel.style.display = 'none';
        ktvmPanel.style.display = 'none';
        iframePanel.style.display = 'none';
        if (drPanel) drPanel.style.display = 'none';
        if (osvmPanel) osvmPanel.style.display = 'flex';
        history.replaceState(null, '', '#osvm');
        fetchOsVmStatus(true);
      } else if (key === 'dr') {
        overviewPanel.style.display = 'none';
        ktvmPanel.style.display = 'none';
        if (osvmPanel) osvmPanel.style.display = 'none';
        iframePanel.style.display = 'none';
        if (drPanel) drPanel.style.display = 'flex';
        history.replaceState(null, '', '#dr');
        addDrLog("DR 관제 센터 패널이 로딩되었습니다. 거점 헬스 상태 확인 완료.", "success");
      } else {
        overviewPanel.style.display = 'none';
        ktvmPanel.style.display = 'none';
        if (osvmPanel) osvmPanel.style.display = 'none';
        if (drPanel) drPanel.style.display = 'none';
        iframePanel.style.display = 'flex';
        titleText.innerText = SERVICES[key].title;
        extBtn.href = SERVICES[key].url;
        history.replaceState(null, '', '#' + key);

        // 폐쇄망 서비스 가이드 배너 동적 주입
        if (key === 'grafana') {
          guideTitle.innerText = "📈 Grafana 관제 메트릭 — 폐쇄망 Prometheus 통합 대시보드";
          guideBadge.innerText = "METRICS / OBSERVABILITY";
          guideBadge.style.background = "#d97706";
          guideBody.innerHTML = `
            <div style="display:grid; grid-template-columns:repeat(auto-fit, minmax(260px, 1fr)); gap:12px; margin-top:6px;">
              <div style="background:#131d31; padding:10px 14px; border-radius:6px; border:1px solid #334155;">
                <div style="font-weight:700; color:#38bdf8;">🌐 접속 및 엔드포인트</div>
                • 폐쇄망 사설 IP: <code>http://10.200.0.21:3000</code><br>
                • 외부 도메인: <code>https://grafana.ktci5.kr</code><br>
                • 인증 계정: <code>admin</code> (익명 뷰어 Anonymous Viewer 기본 활성화)
              </div>
              <div style="background:#131d31; padding:10px 14px; border-radius:6px; border:1px solid #334155;">
                <div style="font-weight:700; color:#34d399;">🔑 로컬 SSH 터널링 (Mac 접속 가이드)</div>
                <code>ssh -L 3000:10.200.0.21:3000 user@10.10.10.8</code><br>
                터미널 실행 후 브라우저에서 <b>http://localhost:3000</b> 접속
              </div>
              <div style="background:#131d31; padding:10px 14px; border-radius:6px; border:1px solid #334155;">
                <div style="font-weight:700; color:#fbbf24;">📊 프로비저닝된 표준 대시보드</div>
                • 대시보드 UID: <code>minwon-standard</code><br>
                • 주요 지표: WireGuard 6노드 Handshake, k3s 파드 상태, MySQL Lag, Ingress QPS
              </div>
            </div>
          `;
          toggleSetupGuide(true);
        } else if (key === 'argocd') {
          guideTitle.innerText = "🚀 Argo CD GitOps 배포 콘솔 — 폐쇄망 K3s 배포 파이프라인";
          guideBadge.innerText = "GITOPS / CD";
          guideBadge.style.background = "#e11d48";
          guideBody.innerHTML = `
            <div style="display:grid; grid-template-columns:repeat(auto-fit, minmax(260px, 1fr)); gap:12px; margin-top:6px;">
              <div style="background:#131d31; padding:10px 14px; border-radius:6px; border:1px solid #334155;">
                <div style="font-weight:700; color:#38bdf8;">🌐 접속 및 엔드포인트</div>
                • 폐쇄망 사설 IP: <code>http://10.21.0.10:8080</code> (b-k3s-01 FIP)<br>
                • 외부 도메인: <code>https://argocd.ktci5.kr</code><br>
                • 인증 계정: <code>admin</code> (기본 역할 <b>role:readonly</b> 적용됨)
              </div>
              <div style="background:#131d31; padding:10px 14px; border-radius:6px; border:1px solid #334155;">
                <div style="font-weight:700; color:#34d399;">🔑 로컬 SSH 터널링 (Mac 접속 가이드)</div>
                <code>ssh -L 8080:10.21.0.10:8080 user@10.10.10.8</code><br>
                터미널 실행 후 브라우저에서 <b>http://localhost:8080</b> 접속
              </div>
              <div style="background:#131d31; padding:10px 14px; border-radius:6px; border:1px solid #334155;">
                <div style="font-weight:700; color:#fbbf24;">📦 등록된 GitOps Application</div>
                • Application: <code>minwon-service</code> (Kustomize 배포)<br>
                • 대상 클러스터: <code>https://kubernetes.default.svc:443</code> (os-a 온프렘)
              </div>
            </div>
          `;
          toggleSetupGuide(true);
        } else {
          toggleSetupGuide(false);
        }

        if (key === 'horizon') {
          fetch('/sso/horizon-api')
            .then(() => {
              if (frame.src !== SERVICES[key].url) frame.src = SERVICES[key].url;
            })
            .catch(() => {
              frame.src = SERVICES[key].url;
            });
        } else {
          if (frame.src !== SERVICES[key].url) frame.src = SERVICES[key].url;
        }
      }
    }

    function updateVmUI(vm) {
      currentVmId = vm.id;
      currentVmState = vm.state;

      document.getElementById('kt-display-name').innerText = vm.name || 'k-vm1';
      document.getElementById('kt-display-id').innerText = 'ID: ' + vm.id;
      if (vm.nic && vm.nic.length > 0) {
        document.getElementById('kt-private-ip').innerText = vm.nic[0].ipaddress;
      }
      document.getElementById('kt-spec').innerText = `${vm.cpunumber} vCPU · ${vm.memory} MB RAM`;
      document.getElementById('kt-os').innerText = `${vm.templatename || 'rocky8'} (${vm.hypervisor || 'Xen'})`;
      document.getElementById('kt-zone').innerText = `${vm.zonename || 'kr-1'} (KOR-Central A)`;

      const badge = document.getElementById('kt-status-badge');
      const text = document.getElementById('kt-status-text');
      const costInfo = document.getElementById('kt-cost-info');
      const headerDot = document.getElementById('header-kt-dot');
      const headerText = document.getElementById('header-kt-text');
      const statState = document.getElementById('stat-kt-state');
      const cardStateText = document.getElementById('card-kt-state-text');

      const btnStop = document.getElementById('btn-kt-stop');
      const btnStart = document.getElementById('btn-kt-start');
      const btnReboot = document.getElementById('btn-kt-reboot');

      if (vm.state === 'Running') {
        badge.className = 'kt-vm-badge state-running';
        badge.innerHTML = '<span class="dot green"></span><span>Running (가동 중)</span>';
        costInfo.style.color = '#34d399';
        costInfo.innerText = '정상 과금 중 (연산 활성)';
        headerDot.className = 'dot green';
        headerText.innerText = 'KT Edge: k-vm1 (Running)';
        statState.innerText = 'k-vm1 : Running';
        statState.style.color = '#34d399';
        cardStateText.innerText = '상태: Running 🟢';

        btnStop.disabled = false;
        btnStart.disabled = true;
        btnReboot.disabled = false;
      } else if (vm.state === 'Stopped') {
        badge.className = 'kt-vm-badge state-stopped';
        badge.innerHTML = '<span class="dot red"></span><span>Stopped (전원 꺼짐)</span>';
        costInfo.style.color = '#f87171';
        costInfo.innerText = '비용 절감 중 (vCPU/RAM 미과금)';
        headerDot.className = 'dot red';
        headerText.innerText = 'KT Edge: k-vm1 (Stopped)';
        statState.innerText = 'k-vm1 : Stopped';
        statState.style.color = '#f87171';
        cardStateText.innerText = '상태: Stopped 🔴';

        btnStop.disabled = true;
        btnStart.disabled = false;
        btnReboot.disabled = true;
      } else {
        badge.className = 'kt-vm-badge state-transition';
        badge.innerHTML = `<span class="dot yellow"></span><span>${vm.state} (전환 중)</span>`;
        costInfo.style.color = '#fbbf24';
        costInfo.innerText = '상태 전환 작업 진행 중...';
        headerDot.className = 'dot yellow';
        headerText.innerText = `KT Edge: k-vm1 (${vm.state})`;
        statState.innerText = `k-vm1 : ${vm.state}`;
        statState.style.color = '#fbbf24';
        cardStateText.innerText = `상태: ${vm.state} 🟡`;

        btnStop.disabled = true;
        btnStart.disabled = true;
        btnReboot.disabled = true;
      }
    }

    async function fetchKtVmStatus(showLog = false) {
      try {
        if (showLog) addLog("KT Cloud OpenAPI listVirtualMachines 조회 요청 중...");
        const res = await fetch('/api/ktcloud/vms');
        const data = await res.json();
        if (data.status === 'ok' && data.vms && data.vms.length > 0) {
          const vm = data.vms[0];
          updateVmUI(vm);
          if (showLog) addLog(`VM '${vm.name}' 상태: ${vm.state} (IP: ${vm.nic[0].ipaddress})`, 'success');
        } else {
          if (showLog) addLog("VM 목록을 찾을 수 없습니다: " + JSON.stringify(data), 'err');
        }
      } catch (err) {
        if (showLog) addLog("API 통신 실패: " + err.message, 'err');
      }
    }

    function confirmVmAction(action) {
      let actionKr = "";
      if (action === 'stop') actionKr = "전원을 끄시겠습니까? (vCPU/RAM 과금이 중단되며 대민 진입점이 대기 상태로 전환됩니다)";
      if (action === 'start') actionKr = "전원을 켜시겠습니까? (부팅 후 약 1분 이내에 Nginx 및 WireGuard가 자동 가동됩니다)";
      if (action === 'reboot') actionKr = "가상머신을 재부팅하시겠습니까?";

      if (confirm(`[KT Cloud VM 제어]\n정말 '${document.getElementById('kt-display-name').innerText}'의 ${actionKr}`)) {
        executeVmAction(action);
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

      addLog(`[ACTION] VM ${action.toUpperCase()} 요청 전송 중...`, 'warn');

      try {
        const res = await fetch('/api/ktcloud/vm/action', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ action: action, id: currentVmId })
        });
        const result = await res.json();

        if (result.status === 'ok') {
          addLog(`명령 접수 성공! Job ID: ${result.jobid}`, 'success');
          pollJobStatus(result.jobid, action);
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

    function pollJobStatus(jobid, action) {
      let attempts = 0;
      const maxAttempts = 30; // 30 * 3s = 90s
      
      const interval = setInterval(async () => {
        attempts++;
        try {
          const res = await fetch(`/api/ktcloud/job?jobid=${jobid}`);
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
      let color = '#cbd5e1';
      if (type === 'err') color = '#f87171';
      if (type === 'warn') color = '#fbbf24';
      if (type === 'success') color = '#34d399';
      line.innerHTML = `<span class="log-time">[${now}]</span> <span class="log-msg" style="color:${color};">${msg}</span>`;
      consoleEl.appendChild(line);
      consoleEl.scrollTop = consoleEl.scrollHeight;
    }

    function selectOsVm(vmName) {
      selectedOsVmName = vmName;
      ['k8s-cp1', 'k8s-w1', 'k8s-w2'].forEach(name => {
        const shortKey = name.replace('k8s-', '');
        const btn = document.getElementById(`btn-tab-${shortKey}`);
        if (btn) {
          if (name === vmName) {
            btn.style.background = '#8b5cf6';
            btn.style.color = '#fff';
            btn.style.fontWeight = '700';
          } else {
            btn.style.background = 'transparent';
            btn.style.color = '#94a3b8';
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
      const hostEl = document.getElementById('os-host');
      const healthEl = document.getElementById('os-health');

      const btnStop = document.getElementById('btn-os-stop');
      const btnStart = document.getElementById('btn-os-start');
      const btnReboot = document.getElementById('btn-os-reboot');
      const btnHardReboot = document.getElementById('btn-os-hard-reboot');

      if (nameEl) nameEl.innerText = vm.name;
      if (idEl) idEl.innerText = `ID: ${vm.id}`;

      // Role
      let role = "Worker Node";
      let roleColor = "#0369a1";
      if (vm.name.includes('cp1') || vm.name.includes('master')) {
        role = "K8s Control Plane & Primary DB";
        roleColor = "#b45309";
      }
      if (roleEl) {
        roleEl.innerText = role;
        roleEl.style.background = roleColor;
      }

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
      if (floatingEl) floatingEl.innerText = floatingIps.join(', ') || '없음 (내부망 전용)';
      if (fixedEl) fixedEl.innerText = fixedIps.join(', ') || '미할당';
      if (hostEl) hostEl.innerText = `${vm['OS-EXT-SRV-ATTR:host'] || 'compute1/2'} (Nova Compute)`;

      // Status Badge & Buttons
      const status = (vm.status || 'UNKNOWN').toUpperCase();
      if (!isOsActionInProgress) {
        if (status === 'ACTIVE') {
          if (badgeEl) badgeEl.className = 'kt-vm-badge state-running';
          if (textEl) textEl.innerHTML = '<span class="dot green"></span> ACTIVE (Running)';
          if (healthEl) {
            healthEl.innerText = '정상 가동 중 (연산 활성)';
            healthEl.style.color = '#34d399';
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
            healthEl.style.color = '#f87171';
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
            healthEl.style.color = '#fbbf24';
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
        const role = isCp1 ? "Control Plane & DB" : "Worker Node";
        const roleColor = isCp1 ? "#b45309" : "#0369a1";

        const card = document.createElement('div');
        card.className = 'kt-vm-box';
        card.style.background = '#1e293b';
        card.style.padding = '16px';
        card.innerHTML = `
          <div class="kt-vm-header" style="padding-bottom:10px;">
            <div class="kt-vm-title">
              <span style="font-size:20px;">🖥️</span>
              <div>
                <div style="font-size:15px; font-weight:700; color:#fff; display:flex; align-items:center; gap:6px;">
                  <span>${s.name}</span>
                  <span class="menu-badge" style="background:${roleColor}; color:#fff; font-size:10px;">${role}</span>
                </div>
                <div style="font-size: 11px; color: #94a3b8; font-family: monospace;">Fixed: ${fixedIps[0] || '미할당'}</div>
              </div>
            </div>
            <div class="kt-vm-badge ${badgeClass}" style="font-size:11px; padding:2px 8px;">
              <span class="dot ${dotClass}"></span>
              <span>${status}</span>
            </div>
          </div>
          <div style="display:flex; justify-content:space-between; align-items:center; margin-top:10px; padding-top:10px; border-top:1px solid #334155;">
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
노드를 끄면 대민 서비스가 중단되고 AWS DR Failover가 발생합니다.`
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
        textEl.style.color = '#34d399';
        setBars('#34d399', [8, 14, 20, 24], [1, 1, 1, 1]);
      } else if (stage === 'l1') {
        textEl.innerText = '⚠️ 135 req/s · RTT 42ms [FAST / RESTARTING 🟡]';
        textEl.style.color = '#fbbf24';
        setBars('#fbbf24', [8, 14, 20, 10], [1, 1, 1, 0.4]);
      } else if (stage === 'l2') {
        textEl.innerText = '⏱️ 45 req/s · RTT 920ms [SLOW / TIMEOUT 🟠]';
        textEl.style.color = '#f97316';
        setBars('#f97316', [8, 14, 6, 6], [1, 1, 0.3, 0.2]);
      } else if (stage === 'path') {
        textEl.innerText = '⚠️ 우회 중 · RTT 18ms [MODERATE 🔵]';
        textEl.style.color = '#38bdf8';
        setBars('#38bdf8', [8, 14, 18, 10], [1, 1, 1, 0.5]);
      } else if (stage === 'l3') {
        textEl.innerText = '⚡ 160 req/s · RTT 11ms [FAILOVER FAST 🔴]';
        textEl.style.color = '#f43f5e';
        setBars('#f43f5e', [8, 14, 20, 24], [1, 1, 1, 1]);
      } else if (stage === 'l4') {
        textEl.innerText = '🔄 복구 동기화 · RTT 8ms [SYNCING 🟣]';
        textEl.style.color = '#a855f7';
        setBars('#a855f7', [8, 14, 18, 22], [1, 1, 1, 1]);
      } else if (stage === 'bs') {
        textEl.innerText = '🛡️ 320 req/s · RTT 2ms [EDGE CACHED ⚫]';
        textEl.style.color = '#94a3b8';
        setBars('#94a3b8', [8, 14, 20, 24], [1, 1, 1, 1]);
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
        bW1.innerText = 'RUNNING 🟢'; bW1.style.background = '#10b981';
        tW1.innerText = '정상 처리 중 (0 restart)'; tW1.style.color = '#34d399';
        bW2.innerText = 'RUNNING 🟢'; bW2.style.background = '#10b981';
        tW2.innerText = '정상 트래픽 분산 (0 restart)'; tW2.style.color = '#34d399';
        bDb.innerText = 'PRIMARY RW 🟢'; bDb.style.background = '#10b981';
        tDb.innerText = 'GTID 스트리밍 송출 (Lag: 0s)'; tDb.style.color = '#34d399';
        bAws.innerText = 'STANDBY RO 🟡'; bAws.style.background = '#475569';
        tAwsPods.innerText = 'Replicas: 0 (L3 대기)'; tAwsPods.style.color = '#94a3b8';
        tAwsDb.innerText = 'Semi-sync 수신 (ACK 확정)'; tAwsDb.style.color = '#38bdf8';
      } else if (stage === 'l1') {
        bW1.innerText = 'CRASHED 💥'; bW1.style.background = '#ef4444';
        tW1.innerText = 'Pod #1 OOM 크래시 ➔ K8s 자동 재시작 중 (Restart +1)'; tW1.style.color = '#f87171';
        bW2.innerText = 'ABSORBING 🟡'; bW2.style.background = '#f59e0b';
        tW2.innerText = 'Pod #2가 전체 민원 트래픽 100% 임시 흡수 처리'; tW2.style.color = '#fbbf24';
      } else if (stage === 'l2') {
        bW1.innerText = 'FROZEN 🟠'; bW1.style.background = '#f97316';
        tW1.innerText = '1분간 무응답 ➔ 터널 B Ansible이 systemd 재가동 중'; tW1.style.color = '#f97316';
        bW2.innerText = 'RESTARTING 🟠'; bW2.style.background = '#f97316';
        tW2.innerText = 'Ansible 플레이북 자동 실행 (≤ 3분 이내 복구 목표)'; tW2.style.color = '#f97316';
      } else if (stage === 'path') {
        tW1.innerText = '터널 A 단절로 직접 수신 불가 ➔ 터널 B·C 우회 수신 중';
        tW2.innerText = '온프렘 인스턴스는 100% 정상이므로 DB 승격 금지!';
      } else if (stage === 'l3') {
        bW1.innerText = 'FENCED 🛑'; bW1.style.background = '#475569';
        tW1.innerText = '온프렘 전면 마비 ➔ Nova Stop으로 스플릿 브레인 차단'; tW1.style.color = '#ef4444';
        bW2.innerText = 'DOWN 🔴'; bW2.style.background = '#475569';
        tW2.innerText = 'Compute 노드 응답 불가 (인스턴스 전원 차단됨)'; tW2.style.color = '#ef4444';
        bDb.innerText = 'ISOLATED 🛑'; bDb.style.background = '#ef4444';
        tDb.innerText = 'Watchdog 펜싱 완료 (Primary 쓰기 차단)'; tDb.style.color = '#ef4444';
        bAws.innerText = 'ACTIVE RW 🔴'; bAws.style.background = '#10b981';
        tAwsPods.innerText = 'Replicas: 2 (EC2 확장 및 웹/API 기동 완료)'; tAwsPods.style.color = '#10b981';
        tAwsDb.innerText = 'super_read_only = OFF (AWS Replica 승격!)'; tAwsDb.style.color = '#10b981';
      } else if (stage === 'l4') {
        bW1.innerText = 'RECOVERED 🟢'; bW1.style.background = '#10b981';
        tW1.innerText = '온프렘 하드웨어 복구 및 k3s 클러스터 재가동 완료'; tW1.style.color = '#34d399';
        bW2.innerText = 'RECOVERED 🟢'; bW2.style.background = '#10b981';
        tW2.innerText = '역방향 GTID 복제 수신 완료 (무손실 동기화)'; tW2.style.color = '#34d399';
        bDb.innerText = 'PRIMARY RW 🟢'; bDb.style.background = '#10b981';
        tDb.innerText = '온프렘 Primary 재승격 완료 (정상 수용 재개)'; tDb.style.color = '#34d399';
        bAws.innerText = 'STANDBY RO 🟡'; bAws.style.background = '#475569';
        tAwsPods.innerText = 'Replicas: 0 (AWS 서비스 대기 강등)'; tAwsPods.style.color = '#94a3b8';
        tAwsDb.innerText = 'super_read_only = ON (Replica 2 원복)'; tAwsDb.style.color = '#38bdf8';
      } else if (stage === 'bs') {
        bW1.innerText = 'OFFLINE ⚫'; bW1.style.background = '#1e293b';
        tW1.innerText = '온프렘 전체 파괴 (Black Sky 재난)'; tW1.style.color = '#64748b';
        bW2.innerText = 'OFFLINE ⚫'; bW2.style.background = '#1e293b';
        tW2.innerText = 'Cloudflare 0초 폴백 작동 중'; tW2.style.color = '#64748b';
        bDb.innerText = 'OFFLINE ⚫'; bDb.style.background = '#1e293b';
        tDb.innerText = 'AWS 및 온프렘 DB 전체 통신 두절'; tDb.style.color = '#64748b';
        bAws.innerText = 'OFFLINE ⚫'; bAws.style.background = '#1e293b';
        tAwsPods.innerText = 'GitHub Pages(dr.ktci5.kr)로 대민 비상 접수 중'; tAwsPods.style.color = '#38bdf8';
      }
    }

    // ============================================================
    // v3.0 DRAWIO TECHNICAL ARCHITECTURE STAGE CONTROLLER
    // ============================================================
    let currentV3Stage = 'normal';

    function setV3Stage(stage) {
      currentV3Stage = stage;

      const keys = ['normal', 'l1', 'l2', 'path', 'l3', 'l4', 'bs'];
      keys.forEach(k => {
        const btn = document.getElementById(`btn-v3-${k}`);
        if (!btn) return;
        if (k === stage) {
          btn.style.background = (k === 'l3' || k === 'bs') ? '#ef4444' : (k === 'l4' ? '#8b5cf6' : (k === 'path' ? '#0284c7' : (k === 'normal' ? '#10b981' : '#f59e0b')));
          btn.style.color = '#fff';
          btn.style.fontWeight = '700';
        } else {
          btn.style.background = 'transparent';
          btn.style.color = '#94a3b8';
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
      zoneOnprem.style.borderColor = 'rgba(16, 185, 129, 0.3)';
      zoneAws.style.opacity = '1';
      zoneAws.style.borderColor = 'rgba(245, 158, 11, 0.3)';
      ghFallback.style.opacity = '0.6';
      ghBadge.className = 'menu-badge';
      ghBadge.style.background = '#475569';
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
        propSm.style.color = "#10b981";
        propSignal.innerText = "S1:정상 · S2:정상 · S3:정상";
        propRto.innerText = "RTO: 0초 · RPO: 0초";
        propTunnel.innerText = "터널 A·B 활성 (C 대기)";

        ktEdgeRoute.innerText = "터널 A 발송 중";
        ktEdgeRoute.className = "tunnel-badge tunnel-a";
        ktEdgeDot.className = "dot green";
        txtS3.innerText = "정상 통과 🟢";
        txtS3.style.color = "#34d399";

        badgeOnpremMode.innerText = "PRIMARY RW 🟢";
        badgeOnpremMode.style.background = "#10b981";
        txtFencing.innerText = "자가 펜싱 감시 중: 정상 (쓰기 허용)";
        badgeDbRw.innerText = "Read / Write";
        badgeDbRw.style.background = "#10b981";

        badgeAwsMode.innerText = "PILOT-LIGHT RO 🟡";
        badgeAwsMode.style.background = "#f59e0b";
        badgeAwsDbRo.innerText = "super_read_only = ON";
        badgeAwsDbRo.style.background = "#f59e0b";
        txtOrchState.innerText = "NORMAL (온프렘 가동)";
        txtOrchState.style.color = "#10b981";

        pathTunnelA.className.baseVal = "flow-line line-yellow";
        pathTunnelB.className.baseVal = "flow-line line-blue";
        pathDbSync.className.baseVal = "flow-line line-yellow";

        sopText.innerHTML = "<b>[v3.0 정상 가동 트래픽 & 보안 흐름]</b><br>" +
          "• <b>대민 진입</b>: HTTPS 요청이 KT Edge-GW(14.63.213.214)에 도착하여 TLS 종료 및 Nginx WAF 검사를 받습니다.<br>" +
          "• <b>터널 A 전송</b>: 온프렘 WireGuard 게이트웨이로 단방향 요청 전달 ➔ ingress-nginx ➔ <code>web ×2</code> ➔ <code>minwon-api ×2</code> ➔ <code>MySQL Primary</code> 커밋.<br>" +
          "• <b>터널 B 복제</b>: MySQL GTID 이벤트가 터널 B를 타고 AWS Replica(super_read_only=ON)로 비동기 복제되고 관제 메트릭이 수집됩니다.";

        addDrLog("[v3.0-FLOW] 1단계: NORMAL 평시 정상 가동 상태가 활성화되었습니다.", "success");

      } else if (stage === 'l1') {
        titleEl.innerText = "🟡 2. L1: Pod 크래시 자가치유 (K8s liveness/readiness · 초 단위)";
        descEl.innerText = "v3.0 drawio: Pod 이상 발생 시 판단 주체는 K8s 자체이며, 외부 Orchestrator 개입 없이 Kubelet이 초 단위로 자가치유합니다.";
        badgeStatus.className = "kt-vm-badge state-transition";
        badgeStatus.innerHTML = '<span class="dot yellow"></span>L1 K8S HEALING';
        propSm.innerText = "NORMAL (Pod Healing)";
        propSm.style.color = "#f59e0b";
        propSignal.innerText = "S1:정상 · S2:정상 · K8s Pod 크래시";
        propRto.innerText = "목표: 초 단위 (0~10s)";
        propTunnel.innerText = "터널 A·B 정상 유지";

        podApi.className = 'k8s-pod-chip pod-restarting';
        pathTunnelA.className.baseVal = "flow-line line-yellow";
        pathTunnelB.className.baseVal = "flow-line line-blue";
        pathDbSync.className.baseVal = "flow-line line-yellow";

        sopText.innerHTML = "<b>[L1 K8s 자가치유 상세 매커니즘]</b><br>" +
          "• <b>장애 감지</b>: <code>minwon-api</code> 파드 OOM 또는 프로세스 크래시 감지 (livenessProbe <code>/healthz?live=1</code> 실패).<br>" +
          "• <b>자동 조치</b>: K8s Kubelet이 컨테이너를 즉각 재시작하며, HPA 및 <code>web ×2</code> 다중 복제본이 트래픽을 흡수하여 대민 서비스는 무중단 유지됩니다.<br>" +
          "• <b>판단 주체</b>: K8s (Orchestrator 및 사람 개입 불필요).";

        addDrLog("[v3.0-FLOW] 2단계: L1 Pod 크래시 감지 및 K8s 자동 재기동 활성화 (RTO: 초 단위)", "warn");

      } else if (stage === 'l2') {
        titleEl.innerText = "🟠 3. L2: 서비스 1분+ 무응답 ➔ 터널 B Ansible 자동 재기동 (≤3분)";
        descEl.innerText = "v3.0 drawio: L1으로 복구 안 되는 서비스 무응답 시 AWS Orchestrator가 터널 B를 통해 Nginx·앱·MySQL·WG를 자동 재기동합니다.";
        badgeStatus.className = "kt-vm-badge state-transition";
        badgeStatus.innerHTML = '<span class="dot yellow"></span>L2 ANSIBLE RESTART';
        propSm.innerText = "DEGRADED (L2 Playbook)";
        propSm.style.color = "#f59e0b";
        propSignal.innerText = "S1:실패 · S2:정상(호스트 접근가능)";
        propRto.innerText = "목표: ≤ 3분";
        propTunnel.innerText = "터널 B 경유 복구 명령 전송";

        txtOrchState.innerText = "DEGRADED (Ansible 실행)";
        txtOrchState.style.color = "#f59e0b";
        pathTunnelB.className.baseVal = "flow-line line-blue";

        sopText.innerHTML = "<b>[L2 서비스 무응답 복구 프로세스]</b><br>" +
          "• <b>감지 지표</b>: 대민 S1 프로브가 1분 이상 응답 없음(Timeout) 감지.<br>" +
          "• <b>자동 복구</b>: AWS Orchestrator가 <b>터널 B</b>를 경유하여 온프레미스 대상 <code>ansible-playbook restart_services.yml</code> 원격 실행.<br>" +
          "• <b>복구 대상</b>: 온프렘 Nginx ➔ minwon-app ➔ MySQL ➔ WireGuard 순차 재기동 후 헬스체크 통과 시 NORMAL 복귀.";

        addDrLog("[v3.0-FLOW] 3단계: L2 서비스 1분 무응답 ➔ 터널 B 경유 Ansible 자동 재기동 명령 발송 (≤ 3m)", "warn");

      } else if (stage === 'path') {
        titleEl.innerText = "🔵 4. 경로 장애: 터널 A만 단절 (S1·S3 실패, S2 정상) ➔ 터널 C·B 우회 (DB 승격 절대 금지!)";
        descEl.innerText = "v3.0 drawio 핵심: 온프렘이 살아있는 단순 터널 A 장애 시, DB를 승격하면 Split-Brain이 발생하므로 절대로 승격하지 않고 터널 C·B로 우회합니다!";
        badgeStatus.className = "kt-vm-badge state-transition";
        badgeStatus.innerHTML = '<span class="dot blue"></span>PATH REROUTING';
        propSm.innerText = "DEGRADED (Path Bypass)";
        propSm.style.color = "#38bdf8";
        propSignal.innerText = "S1:실패 · S2:정상 · S3:실패 (A단절)";
        propRto.innerText = "목표: ≤ 3분 (Split-Brain 방지)";
        propTunnel.innerText = "터널 A 단절 ➔ 터널 C+B 우회";

        ktEdgeRoute.innerText = "터널 C 우회 발송";
        ktEdgeRoute.className = "tunnel-badge tunnel-c";
        txtS3.innerText = "터널 A 실패 🔴";
        txtS3.style.color = "#ef4444";

        txtOrchState.innerText = "DEGRADED (경로 우회 통제)";
        txtOrchState.style.color = "#38bdf8";

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
        propSm.style.color = "#ef4444";
        propSignal.innerText = "S1:실패 ∧ S2:실패 ∧ S3:실패 (3신호 확정)";
        propRto.innerText = "목표: ≤ 15분 · RPO: ≤ 15분";
        propTunnel.innerText = "터널 C 대민 수용 (터널 A·B 두절)";

        zoneOnprem.style.opacity = '0.4';
        zoneOnprem.style.borderColor = '#ef4444';
        badgeOnpremMode.innerText = "FENCED / DOWN 💥";
        badgeOnpremMode.style.background = "#ef4444";
        txtFencing.innerText = "자가 펜싱 발동: 온프렘 쓰기 강제 차단";
        badgeDbRw.innerText = "BLOCKED";
        badgeDbRw.style.background = "#ef4444";

        zoneAws.style.borderColor = '#10b981';
        badgeAwsMode.innerText = "DR PRIMARY RW 🟢";
        badgeAwsMode.style.background = "#10b981";
        badgeAwsDbRo.innerText = "super_read_only = OFF (승격)";
        badgeAwsDbRo.style.background = "#10b981";
        txtOrchState.innerText = "DR_ACTIVE (AWS에서 서비스 중)";
        txtOrchState.style.color = "#ef4444";

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
          "4. <b>Edge 전환</b>: KT Edge-GW upstream을 <b>터널 C(AWS)</b>로 전환 ➔ AWS에서 대민 민원 무중단 접수 재개.";

        addDrLog("[v3.0-FLOW] 5단계: 🚨 L3 사이트 전면 장애 확정! 펜싱 확인 ➔ AWS Replica 승격 ➔ 터널 C 절체 완료!", "err");

      } else if (stage === 'l4') {
        titleEl.innerText = "🟣 6. L4: 온프렘 정상화 ➔ 역방향 GTID 복제 동기화 ➔ 온프렘 승격 (Failback)";
        descEl.innerText = "v3.0 drawio 핵심: 온프렘 하드웨어 복구 시, AWS 서비스 동안 쌓인 데이터를 역방향으로 동기화한 후 무손실 원복합니다.";
        badgeStatus.className = "kt-vm-badge state-running";
        badgeStatus.innerHTML = '<span class="dot green"></span>FAILBACK COMPLETED';
        propSm.innerText = "NORMAL (원복 완료)";
        propSm.style.color = "#10b981";
        propSignal.innerText = "S1:정상 · S2:정상 · S3:정상 (복제지연 0)";
        propRto.innerText = "목표: 무손실 원복 · RPO: 0초";
        propTunnel.innerText = "터널 A 복귀 · 터널 B 역동기화 완료";

        zoneOnprem.style.opacity = '1';
        badgeOnpremMode.innerText = "PRIMARY RW (복구) 🟢";
        badgeOnpremMode.style.background = "#10b981";
        txtFencing.innerText = "펜싱 해제: 온프렘 Primary 쓰기 정상화";
        badgeDbRw.innerText = "Read / Write";
        badgeDbRw.style.background = "#10b981";

        badgeAwsMode.innerText = "PILOT-LIGHT RO 🟡";
        badgeAwsMode.style.background = "#f59e0b";
        badgeAwsDbRo.innerText = "super_read_only = ON (재강등)";
        badgeAwsDbRo.style.background = "#f59e0b";
        txtOrchState.innerText = "NORMAL (Failback 성공)";
        txtOrchState.style.color = "#10b981";

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
        propSm.style.color = "#dc2626";
        propSignal.innerText = "오리진 502/504 연속 감지";
        propRto.innerText = "목표: 0초 비상 접수";
        propTunnel.innerText = "클라우드 전면 단절 ➔ GH Pages";

        zoneOnprem.style.opacity = '0.3';
        zoneAws.style.opacity = '0.3';
        ghFallback.style.opacity = '1';
        ghFallback.style.borderColor = '#10b981';
        ghBadge.className = 'menu-badge';
        ghBadge.style.background = '#10b981';
        ghBadge.innerText = 'EMERGENCY ACTIVE 🟢';

        ktEdgeRoute.innerText = "오리진 두절";
        ktEdgeRoute.className = "tunnel-badge";
        ktEdgeRoute.style.background = "#ef4444";
        ktEdgeRoute.style.color = "#fff";
        ktEdgeDot.className = "dot red";

        txtOrchState.innerText = "DISCONNECTED";
        txtOrchState.style.color = "#ef4444";

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
      // Auto-poll KT status every 15s
      setInterval(() => {
        if (currentTab === 'overview' || currentTab === 'ktvm' || currentTab === 'osvm') {
          fetchOsVmStatus(false);
          fetchKtVmStatus(false);
      fetchOsVmStatus(false);
        }
      }, 15000);
    });

    window.addEventListener('keydown', (e) => {
      if (e.key === 'Escape' && document.body.classList.contains('fullscreen')) {
        document.body.classList.remove('fullscreen');
      }
    });
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

        if not is_valid_session(token):
            if path.startswith('/api/'):
                self.send_json({"status": "error", "message": "Unauthorized"}, status=401)
            else:
                self.redirect('/login')
            return

        if path == '/api/session':
            self.send_json({"status": "ok", "user": VALID_USER})
            return

        if path == '/api/openstack/overview':
            try:
                self.send_json(openstack_overview())
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
                res = call_kt_api('server/v1', 'listVirtualMachines')
                vms = res.get('listvirtualmachinesresponse', {}).get('virtualmachine', [])
                self.send_json({"status": "ok", "vms": vms})
            except Exception as e:
                self.send_json({"status": "error", "message": str(e)}, status=500)
            return

        # KT Cloud API: Query Async Job Result
        if path == '/api/ktcloud/job':
            qs = urllib.parse.parse_qs(parsed.query)
            jobid = qs.get('jobid', [''])[0]
            if not jobid:
                self.send_json({"status": "error", "message": "jobid required"}, status=400)
                return
            try:
                res = call_kt_api('server/v1', 'queryAsyncJobResult', jobid=jobid)
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

        # KT Cloud API: VM Action (start / stop / reboot)
        if path == '/api/ktcloud/vm/action':
            length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(length).decode('utf-8')
            try:
                data = json.loads(body)
                action = data.get('action')
                vmid = data.get('id')

                if not vmid or action not in ['start', 'stop', 'reboot']:
                    self.send_json({"status": "error", "message": "유효하지 않은 요청 파라미터입니다."}, status=400)
                    return

                cmd = ""
                extra = {}
                if action == 'start':
                    cmd = 'startVirtualMachine'
                elif action == 'stop':
                    cmd = 'stopVirtualMachine'
                    extra = {'forced': 'false'}
                elif action == 'reboot':
                    cmd = 'rebootVirtualMachine'

                res = call_kt_api('server/v1', cmd, id=vmid, **extra)
                resp_key = cmd.lower() + "response"
                jobid = res.get(resp_key, {}).get('jobid')
                
                self.send_json({
                    "status": "ok",
                    "action": action,
                    "id": vmid,
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
