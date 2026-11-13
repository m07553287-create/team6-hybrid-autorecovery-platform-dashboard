"""운영 원본 server.py → 비밀값을 뺀 기준본(backend/server.base.py).

사용: python3 tools/sanitize.py <운영 원본 server.py> backend/server.base.py
- 포털 계정 · OpenStack 계정은 /opt/figteam-portal/portal_config.json 또는 환경변수에서 읽는다.
- Cloudflare Pages 연동용으로 /api/session 추가, 로그인 실패는 /login?error=1 로 되돌린다.
- 결과에 비밀값 형태(따옴표로 감싼 16자 이상 hex 등)가 남아 있으면 실패한다.
"""
import re, sys

src, dst = sys.argv[1], sys.argv[2]
s = open(src, encoding='utf-8').read()

def sub(old, new, count=1):
    global s
    n = s.count(old)
    assert n == count, 'expected %d, found %d: %r' % (count, n, old[:70])
    s = s.replace(old, new)

def sub_re(pattern, new):
    global s
    s, n = re.subn(pattern, new, s, count=1, flags=re.M)
    assert n == 1, 'pattern not found: %r' % pattern

CONFIG = '''PORTAL_CONFIG_PATH = os.environ.get("FIGTEAM_CONFIG", "/opt/figteam-portal/portal_config.json")

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
'''
# 1) 포털 계정
sub_re(r'^VALID_USER = "[^"]*"\nVALID_PASS = "[^"]*"\n', CONFIG)
# 2) OpenStack 계정 (Horizon SSO용 전역 + Nova API 기본값)
sub_re(r'^OS_USER = "[^"]*"\nOS_PASS = "[^"]*"\n',
       'OS_USER = os.environ.get("OS_USERNAME") or _PCFG.get("os_user", "admin")\n'
       'OS_PASS = os.environ.get("OS_PASSWORD") or _PCFG.get("os_pass", "")\n')
sub_re(r'^(\s+)"username": "admin",\n(\s+)"password": "[^"]*",\n', r'\1"username": OS_USER,\n\2"password": OS_PASS,\n')
# 3) 로그인: 상수시간 비교 · 실패 시 리다이렉트
sub("            if username == VALID_USER and password == VALID_PASS:",
    "            if VALID_USER and VALID_PASS and hmac.compare_digest(username, VALID_USER) and hmac.compare_digest(password, VALID_PASS):")
sub("""            else:
                self.send_response(200)
                self.send_header('Content-Type', 'text/html; charset=utf-8')
                self.end_headers()
                err = '<div class="error">아이디 또는 비밀번호가 일치하지 않습니다.</div>'
                self.wfile.write(LOGIN_HTML.replace('%%ERROR%%', err).encode('utf-8'))
            return""",
    """            else:
                self.redirect('/login?error=1')
            return""")
sub("""            self.wfile.write(LOGIN_HTML.replace('%%ERROR%%', '').encode('utf-8'))
            return""",
    """            err = '<div class="error">아이디 또는 비밀번호가 일치하지 않습니다.</div>' if 'error' in urllib.parse.parse_qs(parsed.query) else ''
            self.wfile.write(LOGIN_HTML.replace('%%ERROR%%', err).encode('utf-8'))
            return""")
# 4) 세션 확인 (Cloudflare Pages Function이 화면 제공 전 호출)
sub("""        # OpenStack API: List Servers and Hypervisors
        if path == '/api/openstack/vms':""",
    """        if path == '/api/session':
            self.send_json({"status": "ok", "user": VALID_USER})
            return

        # OpenStack API: List Servers and Hypervisors
        if path == '/api/openstack/vms':""")

# 비밀값 잔존 검사
left = re.findall(r"""["'][0-9a-f]{16,}["']""", s)
assert not left, 'secret-like literals remain: %r' % left
open(dst, 'w', encoding='utf-8').write(s)
print('sanitized ->', dst)
