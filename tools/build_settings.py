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
data = json.dumps(settings_guide.data(), ensure_ascii=False, separators=(',', ':')).replace('</', '<\\/')
blocks = {
    ('<!--CFG:BEGIN-->', '<!--CFG:END-->'):
        '<script type="application/json" id="cfg-data">' + data + '</script>',
    ('// CFGJS:BEGIN', '// CFGJS:END'):
        '\n' + (root / 'content' / 'settings.js').read_text(encoding='utf-8') + '    ',
    ('/* CFGCSS:BEGIN */', '/* CFGCSS:END */'):
        '\n' + (root / 'content' / 'settings.css').read_text(encoding='utf-8') + '    ',
}
for (beg, end), body in blocks.items():
    pat = re.compile(re.escape(beg) + '.*?' + re.escape(end), re.S)
    assert pat.search(src), beg
    src = pat.sub(lambda m: beg + py_safe(body) + end, src, count=1)

# 설정 탭으로 전환할 때 첫 화면 보장
if 'cfgInit(); // settings-tab' not in src:
    src = src.replace("        btnSet.classList.add('active');\n",
                      "        btnSet.classList.add('active');\n        cfgInit(); // settings-tab\n", 1)

srv_path.write_text(src, encoding='utf-8')
print('settings injected:', len(data), 'bytes json')

# ---- *.sh 사본을 public/scripts/ 로 (링크 대상) ----
import shutil  # noqa: E402
pub_scripts = root / 'public' / 'scripts'
if pub_scripts.exists():
    shutil.rmtree(pub_scripts)
src_scripts = root / 'content' / 'scripts'
shutil.copytree(src_scripts, pub_scripts)
for sc in settings_guide.SCRIPTS:
    if 'generate' in sc:   # 화면의 설정 코드에서 파일을 만든다(설계 스크립트)
        pid, aid, idx = sc['generate']
        area = next(a for a in settings_guide.PAGES[pid]['areas'] if a['id'] == aid)
        code = area['config'][idx]['code']
        lines = code.split('\n')
        lines.insert(1, '# 원본: 이 가이드의 설계안 (' + sc['path'] + ' 로 저장해 실행) · 아직 적용 전')
        out = pub_scripts / sc['file']
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text('\n'.join(lines) + '\n', encoding='utf-8')
    if 'file' in sc:
        assert (pub_scripts / sc['file']).is_file(), '스크립트 사본 없음: ' + sc['file']
secret = re.compile(r'(PASSWORD|PrivateKey|TOKEN)\s*=\s*[^\s<$"\']', re.I)
for f in pub_scripts.rglob('*.sh'):
    t = f.read_text(encoding='utf-8')
    assert not secret.search(t), '비밀값 의심: ' + str(f)
    assert 'fig-minwon-db-backup' not in t, '버킷 이름 노출: ' + str(f)
print('scripts copied:', len(list(pub_scripts.rglob('*.sh'))))
