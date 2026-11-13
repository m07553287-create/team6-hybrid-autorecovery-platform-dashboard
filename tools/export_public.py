"""생성된 backend/server.py 의 화면을 Cloudflare Pages용 정적 파일로 내보낸다.

public/index.html  — 통합 대시보드 (PORTAL_HTML)
public/login.html  — 로그인 (LOGIN_HTML, ?error=1 이면 오류 문구 표시)
"""
import re, pathlib

root = pathlib.Path(__file__).resolve().parent.parent
src = (root / 'backend' / 'server.py').read_text(encoding='utf-8')

def html(name):
    m = re.search(name + r' = """(.*?)\n"""', src, re.S)
    assert m, name
    return eval('"""' + m.group(1) + '\n"""')  # 파이썬이 실제로 내보내는 문자열과 동일하게

portal = html('PORTAL_HTML')
login = html('LOGIN_HTML')
err = '<div class="error" id="login-error" hidden>아이디 또는 비밀번호가 일치하지 않습니다.</div>'
login = login.replace('%%ERROR%%', err)
login = login.replace('</body>', "  <script>if (new URLSearchParams(location.search).has('error')) document.getElementById('login-error').hidden = false;</script>\n</body>")
assert '%%ERROR%%' not in login
pub = root / 'public'
pub.mkdir(exist_ok=True)
(pub / 'index.html').write_text(portal, encoding='utf-8')
(pub / 'login.html').write_text(login, encoding='utf-8')
print('public/index.html', len(portal), 'bytes · public/login.html', len(login), 'bytes')
