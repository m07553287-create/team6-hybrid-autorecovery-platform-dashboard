#!/usr/bin/env python3
# figteam-portal: 통합 터미널 페이지(#term) — KT·AWS·온프렘, 세션 1회 잠금 해제(60분), 감사 로그
import re, shutil, sys, time
F = '/opt/figteam-portal/server.py'
src = open(F, encoding='utf-8').read()
if "term: { title:" in src:
    print('already patched'); sys.exit(0)
shutil.copy2(F, F + '.bak-' + time.strftime('%Y%m%d-%H%M%S') + '-term2')
def rep(old, new, cnt=1):
    global src
    assert src.count(old) >= 1, 'anchor missing: ' + old[:70]
    src = src.replace(old, new, cnt)

# ---------- 백엔드 ----------
rep("TERM_TARGETS = {\n", "TERM_TARGETS = {\n    'kt-edge':    {'label': 'KT Edge (허브·WAF)', 'host': 'root@10.200.0.1'},\n")
rep("def generate_session():", '''CTRL_UNLOCK = {}          # 세션 토큰 → 만료 시각 (제어 명령 1회 잠금 해제, 60분)
CTRL_TTL = 3600
TERM_AUDIT = '/opt/figteam-portal/term-audit.log'
def ctrl_unlocked(token):
    exp = CTRL_UNLOCK.get(token or '')
    if exp and exp > time.time(): return int(exp - time.time())
    CTRL_UNLOCK.pop(token or '', None); return 0
def term_audit(ip, target, cmd, rc, danger):
    try:
        with open(TERM_AUDIT, 'a', encoding='utf-8') as f:
            f.write(json.dumps({"t": time.strftime('%Y-%m-%d %H:%M:%S'), "ip": ip, "target": target, "danger": danger, "rc": rc, "cmd": cmd[:500]}, ensure_ascii=False) + "\\n")
    except Exception:
        pass

def generate_session():''')
# verify → 세션 해제 / lock / status
rep('''                ok = bool(CTRL_PASS) and hmac.compare_digest((data.get('password') or '').strip(), CTRL_PASS)
                if not ok: time.sleep(0.7)
                self.send_json({"status": "ok" if ok else "error"}, status=200 if ok else 403)''',
'''                ok = bool(CTRL_PASS) and hmac.compare_digest((data.get('password') or '').strip(), CTRL_PASS)
                if ok: CTRL_UNLOCK[token] = time.time() + CTRL_TTL
                else: time.sleep(0.7)
                term_audit(self.client_address[0], '-', 'ctrl unlock ' + ('ok' if ok else 'FAIL'), 0 if ok else 1, False)
                self.send_json({"status": "ok" if ok else "error", "remain": ctrl_unlocked(token)}, status=200 if ok else 403)''')
rep("        # 제어 비밀번호 확인 (값은 응답·로그에 남기지 않음)\n",
'''        if path == '/api/ctrl/status':
            self.send_json({"status": "ok", "remain": ctrl_unlocked(token)}); return
        if path == '/api/ctrl/lock':
            CTRL_UNLOCK.pop(token, None); self.send_json({"status": "ok", "remain": 0}); return

        # 제어 비밀번호 확인 (값은 응답·로그에 남기지 않음)
''')
# 다중 터미널: 해제 세션이면 비번 없이 허용 + 감사 로그
rep('''                if TERM_DANGER.search(cmd) and (not CTRL_PASS or not hmac.compare_digest(pwd, CTRL_PASS)):''',
'''                danger = bool(TERM_DANGER.search(cmd))
                if danger and not ctrl_unlocked(token) and (not CTRL_PASS or not hmac.compare_digest(pwd, CTRL_PASS)):''')
rep('''                res = subprocess.run(ssh + [tgt['host'], cmd], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=25)''',
'''                res = subprocess.run(ssh + [tgt['host'], cmd], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=25)
                term_audit(self.client_address[0], data.get('target', ''), cmd, res.returncode, danger)''')
# KT 기존 터미널도 세션 해제 인정
rep('''if is_dangerous and (not CTRL_PASS or not hmac.compare_digest(pwd, CTRL_PASS)):''',
    '''if is_dangerous and not ctrl_unlocked(token) and (not CTRL_PASS or not hmac.compare_digest(pwd, CTRL_PASS)):''')

# ---------- 화면: 메뉴 · 탭 · 패널 ----------
rep('''      awsvm: { title: "🟧 AWS EC2 관리", url: "" },''',
    '''      awsvm: { title: "🟧 AWS EC2 관리", url: "" },\n      term: { title: "⌨️ 통합 터미널 (KT · AWS · 온프렘)", url: "" },''')
rep("['osnet', 'osops', 'awsvm'].forEach(function (k) {", "['osnet', 'osops', 'awsvm', 'term'].forEach(function (k) {")
rep("} else if (key === 'osnet' || key === 'osops' || key === 'awsvm') {", "} else if (key === 'osnet' || key === 'osops' || key === 'awsvm' || key === 'term') {")
rep('''        <li class="menu-item" data-key="osops" onclick="switchTab('osops')">''',
'''        <li class="menu-item" data-key="term" onclick="switchTab('term')">
          <span class="icon">⌨️</span>
          <span>통합 터미널</span>
          <span class="menu-badge" style="background:#5FD39A;color:#04121F;">CLI</span>
        </li>
        <li class="menu-item" data-key="osops" onclick="switchTab('osops')">''')
# 기존 개별 페이지의 터미널 제거 → 통합 페이지
rep('        <div class="mt-term" data-group="onprem"></div>\n', '')
rep('        <div class="mt-term" data-group="aws"></div>\n', '')
rep('      <!-- OpenStack 구조 · 연결 (2026-11-18 #osvm에서 분리) -->',
'''      <!-- 통합 터미널 (2026-11-19): KT · AWS · 온프렘, 세션 1회 잠금 해제 -->
      <section id="term-panel" style="display: none; flex-direction: column; gap: 12px; padding-bottom: 24px;">
        <div class="overview-hero" style="padding:14px 18px;">
          <div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap">
            <b style="font-size:16px;color:#E6EEF5">⌨️ 통합 터미널</b>
            <span style="font-size:12px;color:#8AA5C2">읽기 명령은 바로 실행 · 편집/재시작/수동 복구는 잠금 해제 후 (로그인 세션 60분, 모든 실행은 감사 로그에 기록)</span>
          </div>
          <div id="mt-lockbar" style="display:flex;align-items:center;gap:8px;margin-top:10px;flex-wrap:wrap">
            <span id="mt-lockstate" style="font-weight:800;font-size:12.5px;color:#F4C95D">🔒 제어 잠김</span>
            <input id="mt-lockpw" type="password" autocomplete="off" placeholder="제어 비밀번호" style="background:#020617;border:1px solid #4F739A;color:#E6EEF5;padding:5px 8px;width:180px">
            <button class="btn-top" id="mt-unlock" style="background:#F4C95D;color:#000;font-weight:800;border:none">🔓 잠금 해제</button>
            <button class="btn-top" id="mt-lock" style="display:none">🔒 다시 잠금</button>
          </div>
        </div>
        <div class="mt-term" data-group="kt"></div>
        <div class="mt-term" data-group="aws"></div>
        <div class="mt-term" data-group="onprem"></div>
      </section>

      <!-- OpenStack 구조 · 연결 (2026-11-18 #osvm에서 분리) -->''')

# ---------- JS ----------
rep("    const MT_GROUPS = {\n", "    const MT_GROUPS = {\n      kt: { title: '⚡ KT Cloud 터미널', targets: { 'kt-edge': 'KT_PRESETS' } },\n")
rep("      const draw = () => { pre.innerHTML = ''; Object.entries(Object.assign({}, MT_COMMON, g.targets[sel.value])).forEach(([n, c]) => {",
'''      const KT_LABELS = { '▶ 전체 연결 점검': 'all', '🔐 WG 핸드셰이크': 'wg', '🛡️ DMZ 보호 설정': 'guard', '⏳ 대기 안내 (503)': 'waiting', '👤 실제 IP 로그': 'realip', '📊 Edge 처리 현황': 'status', '🚨 AWS 도달': 'aws', '🔏 인증서 만료': 'cert' };
      const presetsOf = t => { const p = g.targets[t]; if (p !== 'KT_PRESETS') return p; const o = {}; Object.entries(KT_LABELS).forEach(([n, k]) => { if (typeof KT_OSOPS_PRESETS !== 'undefined' && KT_OSOPS_PRESETS[k]) o[n] = KT_OSOPS_PRESETS[k]; }); return o; };
      const draw = () => { pre.innerHTML = ''; Object.entries(Object.assign({}, MT_COMMON, presetsOf(sel.value))).forEach(([n, c]) => {''')
# 실행: 해제 상태면 위험 명령 확인 후 실행, 잠김이면 잠금 해제 유도
rep("    async function mtExec(box, cmd, pwd) {",
'''    const MT_DANGER = new RegExp('restart|stop|poweroff|reboot|reload|shutdown|kill|[ ]rm[ ]|^rm[ ]|[ ]dd[ ]|mkfs|systemctl[ ]+(start|enable|disable|mask)|(drop|delete|truncate|alter|update|insert|replace|grant|revoke|reset)[ ]|openstack[ ]+[a-z]+[ ]+(create|delete|set|unset|migrate|resize|rebuild)|kubectl[ ]+(delete|apply|scale|edit|patch|drain|cordon)|wg[ ]+(set|syncconf)|wg-quick', 'i');
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
      if (!pwd && MT_DANGER.test(cmd) && mtRemain > 0 && !confirm('제어/변경 명령을 실행합니다. 계속할까요?' + String.fromCharCode(10, 10) + cmd)) return;''')
rep("        if (d.need_password && !pwd) { const p = await mtAskPassword(cmd); if (p) return mtExec(box, cmd, p);",
    "        if (d.need_password && !pwd) { const p = await mtAskPassword(cmd); if (p && await mtUnlock(p)) return mtExec(box, cmd, '');")
rep("    document.addEventListener('DOMContentLoaded', () => document.querySelectorAll('.mt-term').forEach(mtRender));\n    if (document.readyState !== 'loading') document.querySelectorAll('.mt-term').forEach(mtRender);",
    "    const mtBoot = () => { document.querySelectorAll('.mt-term').forEach(b => { if (!b.dataset.ready) { b.dataset.ready = '1'; mtRender(b); } }); mtInitLock(); };\n    document.addEventListener('DOMContentLoaded', mtBoot);\n    if (document.readyState !== 'loading') setTimeout(mtBoot, 0);")
open(F, 'w', encoding='utf-8').write(src)
print('patched term2')
