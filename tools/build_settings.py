"""content/ 의 [설정] 화면 원본을 backend/server.py 의 LANDING_HTML 에 주입한다.

- content/settings_guide.py  → <script type="application/json" id="cfg-data">
- content/settings.js        → // CFGJS:BEGIN … // CFGJS:END
- content/settings.css       → /* CFGCSS:BEGIN */ … /* CFGCSS:END */
LANDING_HTML 은 일반(비 raw) 삼중따옴표 문자열이라 주입 텍스트의 역슬래시는 두 배로 만든다.
처음 실행 때만 옛 설정 화면(MANUAL_DATA·loadManual·사이드바 버튼)을 마커로 바꾼다.
"""
import json
import pathlib
import re
import sys

root = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root / 'content'))
import settings_guide  # noqa: E402

srv_path = root / 'backend' / 'server.py'
src = srv_path.read_text(encoding='utf-8')


def py_safe(text):
    assert '"""' not in text, 'content 에 """ 가 있으면 안 된다'
    return text.replace('\\', '\\\\')


# ---- 1회 변환: 옛 설정 화면 → 마커 ----
if '<!--CFG:BEGIN-->' not in src:
    a = src.index('  <!-- VIEW 2: SETTINGS SITE VIEW')
    b = src.index('  <!-- DETAIL MODAL POPUP')
    src = src[:a] + (
        '  <!-- VIEW 2: SETTINGS SITE VIEW (content/settings_guide.py 에서 생성) -->\n'
        '  <div id="view-settings" class="view-container">\n'
        '    <div class="settings-layout">\n'
        '      <nav class="settings-sidebar" id="cfg-nav"></nav>\n'
        '      <div class="settings-body" id="manual-body-content"></div>\n'
        '    </div>\n'
        '  </div>\n'
        '  <!--CFG:BEGIN--><!--CFG:END-->\n\n'
    ) + src[b:]
if '// CFGJS:BEGIN' not in src:
    a = src.index('    // 4. MANUAL & CONFIGURATION SITE DATA')
    b = src.index('    // 5. INSTANCE-SPECIFIC')
    src = src[:a] + '    // 4. SETTINGS VIEW\n    // CFGJS:BEGIN\n    // CFGJS:END\n\n' + src[b:]
if '/* CFGCSS:BEGIN */' not in src:
    a = src.index('  </style>\n</head>')
    src = src[:a] + '    /* CFGCSS:BEGIN */\n    /* CFGCSS:END */\n' + src[a:]
src = src.replace("loadManual('kt-edge');",
                  "cfgInit(); if ((location.hash || '').indexOf('#cfg/') === 0) switchView('settings');")

# ---- 매번: 마커 사이 다시 채우기 ----
# 공개 페이지에는 정적 설정만 (가이드 내용은 로그인 뒤 위키 서버에서 받는다)
data = json.dumps(settings_guide.static_config(), ensure_ascii=False, separators=(',', ':')).replace('</', '<\\/')
assert '"pages"' not in data and '"areas"' not in data, '공개 페이지에 가이드 데이터가 섞였습니다'
blocks = {
    ('<!--CFG:BEGIN-->', '<!--CFG:END-->'):
        '<script type="application/json" id="cfg-data">' + data + '</script>',
    ('// CFGJS:BEGIN', '// CFGJS:END'):
        '\n' + ''.join((root / 'content' / f).read_text(encoding='utf-8')
                       for f in ('diff.js', 'wiki.js', 'settings.js', 'console.js', 'dashboard.js')) + '    ',
    ('/* CFGCSS:BEGIN */', '/* CFGCSS:END */'):
        '\n' + ''.join((root / 'content' / f).read_text(encoding='utf-8')
                       for f in ('settings.css', 'console.css', 'dashboard.css')) + '    ',
}
for (beg, end), body in blocks.items():
    pat = re.compile(re.escape(beg) + '.*?' + re.escape(end), re.S)
    assert pat.search(src), beg
    src = pat.sub(lambda m: beg + py_safe(body) + end, src, count=1)

# 상단 [콘솔] 메뉴 (3대 영역) — 마커 사이를 매번 다시 만든다
import html as _html  # noqa: E402
if '<!--CONSOLES:BEGIN-->' not in src:
    btn = '<button type="button" class="nav-btn" id="btn-tab-settings" onclick="switchView(\'settings\')">설정</button>'
    assert btn in src, '설정 버튼을 찾지 못했습니다'
    src = src.replace(btn, btn + '\n      <!--CONSOLES:BEGIN--><!--CONSOLES:END-->', 1)
menu = ['<button type="button" class="nav-btn" id="btn-tab-console" onclick="switchView(\'console\')">콘솔</button>']
src = re.sub(r'<!--CONSOLES:BEGIN-->.*?<!--CONSOLES:END-->',
             lambda m: '<!--CONSOLES:BEGIN-->' + py_safe(''.join(menu)) + '<!--CONSOLES:END-->', src, count=1, flags=re.S)

# 메인 대시보드를 실측(dashboard.js)으로 — 예시 데이터 렌더러 앞에 위임 (1회)
for old, new in [
    ('    function applySortAndFilter() {\n', '    function applySortAndFilter() {\n      if (typeof dashRender === \'function\') return dashRender();\n'),
    ('    function openDetailModal(instKey, targetSvcName) {\n', '    function openDetailModal(instKey, targetSvcName) {\n      if (typeof dashModal === \'function\') return dashModal(instKey, targetSvcName);\n'),
    ('<span>5대 클라우드 인스턴스 서비스 매트릭스</span>', '<span>살아 있는 인스턴스 실측 현황</span>'),
    ('데스크탑 FHD 고정 뷰 · 순위 구분 없는 5대 기준 정렬 (종류별·서비스별·리소스크기별·이름별·실행시간별)', 's1 상태 수집기(20초) 기준 · 정렬: 종류·서비스·이상 우선·이름·실행 시간'),
]:
    if new not in src:
        assert old in src, old[:40]
        src = src.replace(old, new, 1)

# 사이트 입장 로그인을 서버 확인으로 · [콘솔] 본문 전환 (1회)
_login_old = src[src.index('    function handleLogin(e) {'):src.index('    function switchView(viewName) {')] if '    function handleLogin(e) {' in src else ''
_login_new = '''    async function handleLogin(e) {
      if (e) e.preventDefault();
      const pwdInput = document.getElementById('auth-pwd');
      const errorBox = document.getElementById('login-error');
      try {
        const r = await fetch('/console/api/unlock', { method: 'POST', credentials: 'same-origin',
          headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ password: pwdInput.value }) });
        if (r.ok) { sessionStorage.setItem(AUTH_KEY, 'valid'); errorBox.style.display = 'none'; checkAuth(); return; }
        errorBox.textContent = r.status === 429 ? '시도가 많습니다. 10분 뒤 다시 시도하세요.' : '비밀번호가 올바르지 않습니다.';
      } catch (err) { errorBox.textContent = '서버에 연결하지 못했습니다. 잠시 뒤 다시 시도하세요.'; }
      errorBox.style.display = 'block';
      pwdInput.select();
    }

    function logout() {
      fetch('/console/api/lock', { method: 'POST', credentials: 'same-origin' }).catch(() => {});
      sessionStorage.removeItem(AUTH_KEY);
      if (typeof csClose === 'function') csClose();
      checkAuth();
    }

'''
if _login_old and "pwdInput.value.trim() === 'figteam'" in _login_old:
    src = src.replace(_login_old, _login_new, 1)
assert "=== 'figteam'" not in src, '소스에 노출된 비밀번호 비교가 남아 있습니다'
src = src.replace("window.addEventListener('DOMContentLoaded', checkAuth);", "window.addEventListener('DOMContentLoaded', siteAuthBoot);")
src = src.replace(' onkeydown="if(event.key===\'Enter\') { handleLogin(event); }"', '')   # form submit 와 중복 전송 방지
if "csView(viewName)) return;" not in src:
    src = src.replace('    function switchView(viewName) {\n', "    function switchView(viewName) {\n      if (typeof csView === 'function' && csView(viewName)) return;\n", 1)
src = src.replace('onclick="csGo()" title="3대 영역 인스턴스에 실제 터미널로 접속">통합 터미널</button>',
                  'onclick="switchView(\'console\')" title="3대 영역 인스턴스에 바로 접속">콘솔</button>')

# 대시보드 왼쪽 [통합콘솔] 레일 버튼 (1회 삽입)
if '<!--CSRAIL-->' not in src:
    anchor = '<div id="view-dashboard" class="view-container">'
    assert anchor in src, '대시보드 뷰를 찾지 못했습니다'
    src = src.replace(anchor, anchor + '\n    <!--CSRAIL--><button type="button" class="cs-rail" onclick="switchView(\'console\')" title="3대 영역 인스턴스에 바로 접속">콘솔</button>', 1)
src = src.replace('onclick="csOpen()" title="3대 영역 인스턴스에 실제 터미널로 접속">통합콘솔</button>',
                  'onclick="csGo()" title="3대 영역 인스턴스에 실제 터미널로 접속">통합 터미널</button>')

# 설정 탭으로 전환할 때 첫 화면 보장
if 'cfgInit(); // settings-tab' not in src:
    src = src.replace("        btnSet.classList.add('active');\n",
                      "        btnSet.classList.add('active');\n        cfgInit(); // settings-tab\n", 1)

srv_path.write_text(src, encoding='utf-8')
print('settings injected:', len(data), 'bytes json')

# ---- 스크립트 사본은 위키 서버(로그인한 팀)에서만 제공 — 공개 public/scripts/ 는 두지 않는다 ----
import shutil  # noqa: E402
pub_scripts = root / 'public' / 'scripts'
if pub_scripts.exists():
    shutil.rmtree(pub_scripts)
secret = re.compile(r'(PASSWORD|PrivateKey|TOKEN)\s*=\s*[^\s<$"\']', re.I)
for f in (root / 'content' / 'scripts').rglob('*.sh'):   # 시드에 들어갈 사본 검사
    t = f.read_text(encoding='utf-8')
    assert not secret.search(t), '비밀값 의심: ' + str(f)
    assert 'fig-minwon-db-backup' not in t, '버킷 이름 노출: ' + str(f)

# ---- 통합 터미널 전용 페이지 public/term/index.html (페이지 이동 방식) ----
tpl = (root / 'content' / 'term_page.html').read_text(encoding='utf-8')
term_css = ''.join((root / 'content' / f).read_text(encoding='utf-8') for f in ('settings.css', 'console.css'))
term_js = (root / 'content' / 'console.js').read_text(encoding='utf-8')
page = tpl.replace('/*TERM_CSS*/', term_css).replace('/*TERM_JS*/', term_js)
(root / 'public' / 'term').mkdir(exist_ok=True)
(root / 'public' / 'term' / 'index.html').write_text(page, encoding='utf-8')
print('public/term/index.html', len(page), 'bytes')
