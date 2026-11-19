#!/usr/bin/env python3
# figteam-portal: /term 독립 페이지(팝업·새 창·다중 터미널) + 터미널 API 는 잠금 해제 세션 전용
import re, shutil, sys, time
F = '/opt/figteam-portal/server.py'
src = open(F, encoding='utf-8').read()
if "path == '/term'" in src:
    print('already patched'); sys.exit(0)
shutil.copy2(F, F + '.bak-' + time.strftime('%Y%m%d-%H%M%S') + '-term3')
def rep(old, new):
    global src
    assert old in src, 'anchor missing: ' + old[:80]
    src = src.replace(old, new, 1)

# 1) GET /term — term.html 에 포털의 KT 프리셋 주입
rep("        # Main Console Portal\n", '''        # 통합 터미널 독립 페이지 (2026-11-19): 팝업·새 창·다중 터미널
        if path == '/term':
            try:
                page = open('/opt/figteam-portal/term.html', encoding='utf-8').read()
                m = re.search(r'const KT_OSOPS_PRESETS = (\\{.*?\\n    \\});', PORTAL_HTML, re.S)
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
''')
# 2) 터미널 API: 잠금 해제 세션만 (읽기 명령 포함)
rep("                if danger and not ctrl_unlocked(token) and (not CTRL_PASS or not hmac.compare_digest(pwd, CTRL_PASS)):\n"
    "                    self.send_json({\"status\": \"error\", \"need_password\": True, \"message\": \"제어/변경 명령은 제어 비밀번호가 필요합니다.\"}, status=403); return",
    "                if not ctrl_unlocked(token):\n"
    "                    self.send_json({\"status\": \"error\", \"need_unlock\": True, \"message\": \"터미널 잠금 해제가 필요합니다.\"}, status=403); return")
# 3) 포털 #term 패널 → /term iframe
s = src.index('      <section id="term-panel"'); e = src.index('      <!-- OpenStack 구조 · 연결 (2026-11-18 #osvm에서 분리) -->')
src = src[:s] + '''      <section id="term-panel" style="display: none; flex: 1; flex-direction: column; min-height: calc(100vh - 110px);">
        <iframe id="term-frame" src="/term" title="통합 터미널" style="flex: 1; width: 100%; min-height: calc(100vh - 110px); border: 0; background: #04121F;"></iframe>
      </section>

''' + src[e:]
open(F, 'w', encoding='utf-8').write(src)
print('patched term3')
