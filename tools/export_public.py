"""생성된 backend/server.py 의 화면을 Pages용 정적 파일로 내보낸다.

public/index.html  — 통합 대시보드 / 랜딩 (LANDING_HTML 또는 PORTAL_HTML)
public/login.html  — 로그인 (LOGIN_HTML, 없으면 스킵)
"""
import re, pathlib

root = pathlib.Path(__file__).resolve().parent.parent
src = (root / 'backend' / 'server.py').read_text(encoding='utf-8')

def find_html(name):
    m = re.search(name + r' = """(.*?)\n"""', src, re.S)
    if m:
        return eval('"""' + m.group(1) + '\n"""')
    return None

portal = find_html('PORTAL_HTML') or find_html('LANDING_HTML')
assert portal, "PORTAL_HTML or LANDING_HTML must be present"

pub = root / 'public'
pub.mkdir(exist_ok=True)
(pub / 'index.html').write_text(portal, encoding='utf-8')

login = find_html('LOGIN_HTML')
if login:
    err = '<div class="error" id="login-error" hidden>아이디 또는 비밀번호가 일치하지 않습니다.</div>'
    login = login.replace('%%ERROR%%', err)
    login = login.replace('</body>', "  <script>if (new URLSearchParams(location.search).has('error')) document.getElementById('login-error').hidden = false;</script>\n</body>")
    (pub / 'login.html').write_text(login, encoding='utf-8')
    print('public/index.html', len(portal), 'bytes · public/login.html', len(login), 'bytes')
else:
    print('public/index.html', len(portal), 'bytes (login skipped)')

# CNAME 파일 작성 (GitHub Pages 및 Cloudflare Pages용)
(pub / 'CNAME').write_text('figteam.ktci5.kr\n', encoding='utf-8')

# robots.txt 작성: AI 에이전트(ChatGPT-User, Claude-User 등)의 접근을 전면 허용
robots_content = """User-agent: *
Allow: /

User-agent: ChatGPT-User
Allow: /

User-agent: GPTBot
Allow: /

User-agent: Claude-User
Allow: /

User-agent: ClaudeBot
Allow: /

User-agent: PerplexityBot
Allow: /

User-agent: Perplexity-User
Allow: /

User-agent: Google-Agent
Allow: /

User-agent: OAI-SearchBot
Allow: /

User-agent: Claude-SearchBot
Allow: /
"""
(pub / 'robots.txt').write_text(robots_content, encoding='utf-8')
