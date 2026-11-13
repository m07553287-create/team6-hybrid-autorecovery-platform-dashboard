"""청사진(Blueprint) 테마를 server.py 에 적용한다.
사용: python3 theme/apply_theme.py server.py.orig server.py
"""
import re, sys, pathlib

src, dst = sys.argv[1], sys.argv[2]
here = pathlib.Path(__file__).parent
s = open(src, encoding='utf-8').read()

# 1) 로그인 페이지 교체
login = (here / 'login.html').read_text(encoding='utf-8')
s, n = re.subn(r'LOGIN_HTML = """.*?\n"""', lambda m: 'LOGIN_HTML = """' + login.rstrip('\n') + '\n"""', s, count=1, flags=re.S)
assert n == 1, 'LOGIN_HTML not found'

# 2) 포털 CSS 교체 + 폰트 링크
start = s.index('PORTAL_HTML = """')
end = s.index('\n"""', start)
portal = s[start:end]
css = (here / 'portal.css').read_text(encoding='utf-8') + (here / 'iso.css').read_text(encoding='utf-8')
fonts = ('  <link rel="preconnect" href="https://fonts.googleapis.com">\n'
         '  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>\n'
         '  <link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500&family=IBM+Plex+Sans+KR:wght@300;400;500;600&display=swap" rel="stylesheet">\n')
head, rest = portal.split('  <style>', 1)
_, body = rest.split('  </style>', 1)

# 3) 마크업·JS 안의 하드코딩 색을 청사진 팔레트로 매핑
CMAP = {
    # 표면
    '#090e17': '#0C2542', '#0b1120': '#0C2542', '#131c2e': '#0F2D4F', '#131d31': '#0F2D4F',
    '#0f172a': '#0F2D4F', '#1e293b': '#1D4A7A',
    # 선
    '#334155': '#4F739A', '#475569': '#6A8BAE',
    # 글자
    '#64748b': '#8AA5C2', '#94a3b8': '#B4C6D8', '#cbd5e1': '#D3E0EC', '#e2e8f0': '#E6EEF5', '#f8fafc': '#E6EEF5',
    # 강조 (청사진 위 대비 확보)
    '#38bdf8': '#9FD3F5', '#0284c7': '#3A78B5', '#0369a1': '#3A78B5',
    '#10b981': '#5FD39A', '#34d399': '#8FE0B4', '#059669': '#4CB985', '#047857': '#3E9E70',
    '#f59e0b': '#F4C95D', '#fbbf24': '#F7D684', '#d97706': '#D9A93A', '#b45309': '#C8962E', '#d4930f': '#D9A93A', '#fde68a': '#FBE6AE',
    '#ef4444': '#FF7A66', '#f87171': '#FF9E8C', '#dc2626': '#E8604C', '#e11d48': '#FF6B81', '#fda4af': '#FFC0C9',
    '#8b5cf6': '#B08CFF', '#a855f7': '#B08CFF', '#a78bfa': '#C3A6FF', '#9333ea': '#9A74F0', '#c084fc': '#C3A6FF',
}
RMAP = {
    'rgba(15, 23, 42,': 'rgba(15, 45, 79,', 'rgba(30, 41, 59,': 'rgba(29, 74, 122,',
    'rgba(16, 185, 129,': 'rgba(95, 211, 154,', 'rgba(245, 158, 11,': 'rgba(244, 201, 93,',
    'rgba(239, 68, 68,': 'rgba(255, 122, 102,', 'rgba(225, 29, 72,': 'rgba(255, 107, 129,',
    'rgba(139, 92, 246,': 'rgba(176, 140, 255,', 'rgba(168, 85, 247,': 'rgba(176, 140, 255,',
    'rgba(212, 147, 15,': 'rgba(244, 201, 93,', 'rgba(56, 189, 248,': 'rgba(159, 211, 245,',
}
counts = {}
def sub_hex(m):
    k = m.group(0).lower()
    if k in CMAP:
        counts[k] = counts.get(k, 0) + 1
        return CMAP[k]
    return m.group(0)
body = re.sub(r'#[0-9a-fA-F]{6}\b', sub_hex, body)
for a, b in RMAP.items():
    body = body.replace(a, b).replace(a.replace(', ', ','), b.replace(', ', ','))
# 하드코딩 border-radius 는 도면 언어에 맞게 0 으로 (원형 dot 50% 는 유지)
body = re.sub(r'border-radius:\s*\d+px', 'border-radius:0', body)

# 4) DR 패널: 아이소메트릭 장면 삽입 + 어긋난 고정좌표 오버레이 제거 + 상태 훅
sys.path.insert(0, str(here))
import iso_scene
# 시나리오 메뉴와 단계 상세 카드를 떼어 7:3 분할의 오른쪽(3)으로 옮긴다
m_menu = re.search(r'        <!-- 7-STAGE SCENARIO.*?(?=\n        <!-- MAIN ARCHITECTURE CANVAS)', body, re.S)
assert m_menu, 'scenario menu not found'
menu = m_menu.group(0)
body = body.replace(menu, '', 1)
m_card = re.search(r'        <!-- ORCHESTRATOR STATUS.*?(?=\n        <!-- ACTIONABLE DISASTER DRILL)', body, re.S)
assert m_card, 'status card not found'
card = m_card.group(0)
body = body.replace(card, '', 1)
# 카드 → 단계 헤더 / 상태 4칸 / SOP 로 분해
c_head = card[card.index('<div style="display:flex; justify-content:space-between'):card.index('<div class="kt-props-grid"')]
c_props = card[card.index('<div class="kt-props-grid"'):card.index('<!-- DETAILED SOP ACTIONS -->')]
c_sop = card[card.index('<!-- DETAILED SOP ACTIONS -->'):card.rindex('</div>')]
# 실시간 로그 콘솔을 콘솔 하단 띠로 이동
m_log = re.search(r'\s*<div class="kt-log-box" id="dr-log-console"[^>]*>\s*<div class="log-line">.*?</div>\s*</div>', body, re.S)
assert m_log, 'dr log not found'
log = m_log.group(0)
body = body.replace(log, '', 1)
# 메뉴: 짧은 버튼명(원문은 title 툴팁) + 머리말
SHORT = {'normal': '🟢 1 · 평시 NORMAL', 'l1': '🟡 2 · L1 Pod 자가치유', 'l2': '🟠 3 · L2 Ansible 재기동',
         'path': '🔵 4 · 경로장애 우회', 'l3': '🔴 5 · L3 AWS 승격', 'l4': '🟣 6 · L4 Failback', 'bs': '⚫ 7 · Black Sky 폴백'}
def _short(m):
    k = m.group(2); full = re.sub(r'\s+', ' ', m.group(4)).strip().replace('"', '&quot;')
    return '%s title="%s">%s</button>' % (m.group(1), full, SHORT[k])
menu, n = re.subn(r'(<button class="btn-top" id="btn-v3-(\w+)"([^>]*))>(.*?)</button>', _short, menu, flags=re.S)
assert n == 7, n
_bs = re.search(r'<button class="btn-top" id="btn-v3-bs".*?</button>', menu, re.S)
assert _bs
menu = menu.replace(_bs.group(0), _bs.group(0) + '\n            <button class="btn-top" id="btn-v3-surge" title="8. 접수 폭주: Edge 대기열 → 접수 테이블 우선 커밋 → 워커 순차 처리 · 초과분 비상 폼" onclick="setV3Stage(\'surge\')">🟤 8 · 접수 폭주</button>'
    + '\n            <button class="btn-top" id="btn-v3-mgmt" title="9. 관리 접속: 운영자 → Cloudflare → minwon-tunnel → 온프렘 cloudflared → 내부 서비스 · WG로 AWS/KT" onclick="setV3Stage(\'mgmt\')">⚪ 9 · 관리 접속 (Tunnel)</button>')
menu = re.sub(r'🎮 v3\.0 장애대응 사다리 & 상태 머신 시뮬레이션 \(시나리오를 클릭하세요\):', '장애대응 사다리 — 시나리오 선택', menu)
# 어긋난 오버레이 제거 후, 상세 구성(arch-container)을 떼어 콘솔 안으로
body, n = re.subn(r'\s*<!-- SVG DYNAMIC WIRE-GUARD.*?</svg>', '', body, count=1, flags=re.S)
assert n == 1, 'overlay not found'
m_drill = re.search(r'\s*<!-- ACTIONABLE DISASTER DRILL CONSOLE -->.*?(?=\n\s*</section>)', body, re.S)
assert m_drill, 'drill block not found'
drill = m_drill.group(0)
body = body.replace(drill, '\n', 1)
drill = re.sub(r'<div class="section-title"[^>]*>\s*<span>[^<]*</span>\s*</div>', '', drill, count=1)
m_arch = re.search(r'        <!-- MAIN ARCHITECTURE CANVAS.*?(?=\n\s*</section>)', body, re.S)
assert m_arch, 'arch not found'
arch = m_arch.group(0)
console = ('<div class="dr-console" id="dr-console">\n'
           '        <div class="dc-main">\n'
           '          <div class="iso-stage">\n'
           '            <div class="iso-stage-head"><h3>민원불패 v2.5.1 — 연결 구성도</h3>'
           '<p class="dc-hint">휠 확대 · 드래그 이동 · 장비 클릭 시 상세</p>'
           '<button class="btn-top dc-fs" id="dr-fs-btn" onclick="toggleDrFullscreen()">전체 화면</button></div>\n'
           '            <div class="t3-host" id="t3-host">' + iso_scene.build() + '</div>\n'
           '          </div>\n'
           '          <div class="dc-detail" id="dc-detail">\n'
           '            <div class="dc-detail-head">상세 구성 — 서브넷 · 파드 · DB</div>\n' + arch + '\n          </div>\n'
           '          <div class="dc-strip">\n' + c_props + '\n' + log + '\n          </div>\n'
           '        </div>\n'
           '        <div class="dc-side">\n' + menu + '\n'
           '          <div class="dc-stage">' + c_head + '</div>\n'
           '          <div class="dc-tabs" role="tablist">'
           '<button type="button" class="dc-tab" id="dc-tabbtn-flow" onclick="drTab(\'flow\')">흐름 단계</button>'
           '<button type="button" class="dc-tab on" id="dc-tabbtn-sop" onclick="drTab(\'sop\')">대응 절차</button>'
           '<button type="button" class="dc-tab" id="dc-tabbtn-drill" onclick="drTab(\'drill\')">모의훈련</button></div>\n'
           '          <div class="dc-tabpanel" id="dc-tab-flow" hidden><ol class="dc-flow" id="dc-flow">'
           '<li class="empty"><span>3D 엔진을 불러오는 중입니다. 불러오지 못하면 대응 절차 탭을 보세요.</span></li></ol></div>\n'
           '          <div class="dc-tabpanel dc-sop" id="dc-tab-sop">' + c_sop + '</div>\n'
           '          <div class="dc-tabpanel dc-drill" id="dc-tab-drill" hidden><p class="dc-drill-note">실제 클러스터에 영향을 주는 명령입니다. 실행 전 확인 창이 뜹니다.</p>' + drill + '</div>\n'
           '        </div>\n'
           '        </div>\n')
body = body.replace(arch, '        ' + console, 1)
# 제목 버전
t_old = '민원불패 — 통합 운영 대시보드 (실시간 동적 제어 & 관제)'
assert body.count(t_old) == 1
body = body.replace(t_old, '민원불패 — 통합 운영 대시보드 v2.5.1 (실시간 동적 제어 & 관제)')
hook = 'currentV3Stage = stage;'
assert body.count(hook) == 1
body = body.replace(hook, hook + "\n      const isoScene = document.getElementById('iso-scene');\n      if (isoScene) isoScene.setAttribute('data-stage', stage);\n      if (window.Topo2D) window.Topo2D.setStage(stage);")

# 5) 원본 버그 수정: addDrLog 가 정의되지 않아 DR 탭·시나리오마다 예외 발생 → #dr-log-console 및 모달 로거 추가
drlog = """    function addDrLog(msg, type = '') {
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

    function switchTab(key) {"""
if 'function addDrLog' not in body:
    assert body.count('    function switchTab(key) {') == 1
    body = body.replace('    function switchTab(key) {', drlog)

topo = (here / 'topo2d.js').read_text(encoding='utf-8')
assert '"""' not in topo
topo = topo.replace('\\', '\\\\')  # 파이썬 문자열 안에서도 JS 원문 그대로 나가도록
assert body.count('</body>') == 1
body = body.replace('</body>', '  <script>\n' + topo + '\n  </script>\n</body>')

# 7) #osvm 하단: OpenStack 구조 · 연결 (서비스 상태 · 네트워크 구성도 · 경로 추적 · 자원 · VM 도구)
osv = (here / 'osview.js').read_text(encoding='utf-8')
assert '"""' not in osv
osv = osv.replace('\\', '\\\\')
body, n = re.subn(r'(\n\s*</section>\s*\n\s*<!-- 4\. v3\.0 DRAWIO)', '\n        <div class="osx" id="osx"></div>' + r'\1', body, count=1)
assert n == 1, 'osvm panel end not found'
body = body.replace('</body>', '  <script>\n' + osv + '\n  </script>\n</body>')

# 6) v2.5.1 DB 최우선 정책 문구 (semi-sync · binlog 실시간 백업)
DBTXT = [
    ('온프렘 Primary로부터 GTID 비동기 수신', 'GTID semi-sync 수신 (AFTER_SYNC ACK)', 1),
    ('덤프 6시간 주기 · <b>binlog 15분 주기</b>', '<b>binlog 실시간 스트림</b> · 일일 스냅샷 · Object Lock', 1),
    ('비동기 복제되고 관제 메트릭이 수집됩니다', 'semi-sync 복제(ACK 후 커밋 확정)되고 binlog는 S3로 실시간 백업됩니다', 2),
    ('목표: ≤ 15분 · RPO: ≤ 15분', '목표: ≤ 15분 · RPO: 0 (semi-sync)', 1),
]
for old, new, cnt in DBTXT:
    assert body.count(old) == cnt, (old, body.count(old))
    body = body.replace(old, new)
portal = head + fonts + '  <style>\n' + css + '  </style>' + body
s = s[:start] + portal + s[end:]
open(dst, 'w', encoding='utf-8').write(s)
print('mapped:', sum(counts.values()), 'hex tokens')
