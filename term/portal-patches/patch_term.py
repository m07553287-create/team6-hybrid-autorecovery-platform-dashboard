#!/usr/bin/env python3
# figteam-portal: AWS · 온프렘 다중 대상 터미널 + 프리셋 버튼, 제어 비밀번호 화면 비노출
import json, re, shutil, sys, time
F = '/opt/figteam-portal/server.py'
CFG = '/opt/figteam-portal/portal_config.json'
src = open(F, encoding='utf-8').read()
if '/api/term/exec' in src:
    print('already patched'); sys.exit(0)
shutil.copy2(F, F + '.bak-' + time.strftime('%Y%m%d-%H%M%S') + '-term')

# 0) 제어 비밀번호: 설정 파일로 (값은 기존과 같음, 화면·코드에 노출하지 않음)
cfg = json.load(open(CFG))
if 'ctrl_pass' not in cfg:
    m = re.search(r'pwd != "([^"]+)"', src)
    cfg['ctrl_pass'] = m.group(1)
    json.dump(cfg, open(CFG, 'w'), ensure_ascii=False, indent=2)
src = src.replace('VALID_PASS = os.environ.get("FIGTEAM_PASS") or _PCFG.get("portal_pass", "")',
                  'VALID_PASS = os.environ.get("FIGTEAM_PASS") or _PCFG.get("portal_pass", "")\n'
                  'CTRL_PASS = os.environ.get("FIGTEAM_CTRL_PASS") or _PCFG.get("ctrl_pass", "")', 1)
old_pw = cfg['ctrl_pass']
# 0-1) KT 화면 JS: 브라우저 비교 → 서버 검증, prompt(평문 표시) → 마스킹 모달
for fn in ['function toggleKtControlLock() {', 'function handleKtControlClick(type, param) {',
           'function promptAndExecKtTerminal(cmd) {', 'function submitKtTerminalInput() {']:
    assert fn in src, fn
    src = src.replace(fn, 'async ' + fn, 1)
src, n1 = re.subn(r"prompt\(`[^`]*비밀번호\(" + re.escape(old_pw) + r"\)[^`]*`, (?:\"\"|'')\)", "await mtAskPassword('KT 제어 인증')", src)
src, n2 = re.subn(r"if \(pwd === '" + re.escape(old_pw) + r"'\) \{", "if (await mtVerify(pwd)) { ktCtrlPwd = pwd;", src)
src, n3 = re.subn(r"execKtTerminal\((\w+), '" + re.escape(old_pw) + r"'\)", r"execKtTerminal(\1, ktCtrlPwd)", src)
src = src.replace("      } else {\n        isKtControlUnlocked = false;", "      } else {\n        isKtControlUnlocked = false; ktCtrlPwd = '';", 1)
print(f'KT JS: prompt {n1}, compare {n2}, exec {n3}')
src = src.replace(f'pwd != "{old_pw}"', '(not CTRL_PASS or not hmac.compare_digest(pwd, CTRL_PASS))')
src = src.replace(f'비밀번호({old_pw})', '제어 비밀번호')
src = src.replace(f'관리자 비밀번호({old_pw})', '제어 비밀번호')
src = src.replace(f'🔑 활성화 ({old_pw})', '🔑 제어 활성화')
src = src.replace(f" (올바른 비밀번호: {old_pw})", "")
src = src.replace(f"'🔑 활성화 ({old_pw})'", "'🔑 제어 활성화'")

# 1) 백엔드: /api/term/exec (화이트리스트 대상만)
backend = r'''
        # 제어 비밀번호 확인 (값은 응답·로그에 남기지 않음)
        if path == '/api/ctrl/verify':
            try:
                data = json.loads(self.rfile.read(int(self.headers.get('Content-Length', 0))).decode('utf-8'))
                ok = bool(CTRL_PASS) and hmac.compare_digest((data.get('password') or '').strip(), CTRL_PASS)
                if not ok: time.sleep(0.7)
                self.send_json({"status": "ok" if ok else "error"}, status=200 if ok else 403)
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
                if TERM_DANGER.search(cmd) and (not CTRL_PASS or not hmac.compare_digest(pwd, CTRL_PASS)):
                    self.send_json({"status": "error", "need_password": True, "message": "제어/변경 명령은 제어 비밀번호가 필요합니다."}, status=403); return
                ssh = ["ssh", "-n", "-o", "BatchMode=yes", "-o", "ConnectTimeout=5", "-o", "StrictHostKeyChecking=accept-new", "-o", "LogLevel=ERROR"]
                if tgt.get('jump'): ssh += ["-J", tgt['jump']]
                res = subprocess.run(ssh + [tgt['host'], cmd], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=25)
                out = (res.stdout or '') + (("\n[stderr]\n" + res.stderr.strip()) if res.stderr.strip() else '')
                if res.returncode == 255 and 'Permission denied' in (res.stderr or ''):
                    out += "\n→ 이 대상에 포털(s1) 공개키가 등록되지 않았습니다."
                self.send_json({"status": "ok", "code": res.returncode, "output": out[-20000:], "target": f"{tgt['label']} ({tgt['host']})"})
            except subprocess.TimeoutExpired:
                self.send_json({"status": "error", "message": "타임아웃 (25초)"}, status=504)
            except Exception as e:
                self.send_json({"status": "error", "message": str(e)}, status=500)
            return
'''
anchor = '        # KT Cloud Edge Live Terminal Execution\n'
assert anchor in src
src = src.replace(anchor, backend + '\n' + anchor, 1)

targets = r'''
# 다중 대상 터미널 대상 (화이트리스트). 비밀값 없음 — s1 포털 계정의 SSH 키 사용.
TERM_TARGETS = {
    'ctl':        {'label': 'AWS ctl (러너)',      'host': 'rocky@10.200.0.3'},
    'dr':         {'label': 'AWS dr (복구)',       'host': 'rocky@10.200.0.4'},
    'controller': {'label': 'OpenStack controller', 'host': 'root@192.168.120.160'},
    'compute1':   {'label': 'compute1 (워커1)',    'host': 'root@192.168.120.161'},
    'compute2':   {'label': 'compute2 (워커2)',    'host': 'root@192.168.120.162'},
    'compute3':   {'label': 'compute3 (k8s 마스터)', 'host': 'root@192.168.120.163'},
    'compute4':   {'label': 'compute4 (DB)',       'host': 'root@192.168.120.164'},
    'k8s-cp1':    {'label': 'k8s-cp1 (앱)',        'host': 'ubuntu@192.168.120.226'},
    'db-01':      {'label': 'db-01 (MySQL 원본)',  'host': 'ubuntu@10.10.2.10'},
    'k8s-w1':     {'label': 'k8s-w1',              'host': 'ubuntu@172.20.0.180', 'jump': 'ubuntu@192.168.120.226'},
    'k8s-w2':     {'label': 'k8s-w2',              'host': 'ubuntu@172.20.0.152', 'jump': 'ubuntu@192.168.120.226'},
}
TERM_DANGER = re.compile(r'restart|stop|poweroff|reboot|reload|shutdown|kill|\brm\s|\bdd\s|mkfs|systemctl\s+(start|enable|disable|mask)|'
                         r'\b(drop|delete|truncate|alter|update|insert|replace|grant|revoke|reset)\b|openstack\s+\S+\s+(create|delete|set|unset|migrate|resize|rebuild)|'
                         r'kubectl\s+(delete|apply|scale|edit|patch|drain|cordon)|wg\s+(set|syncconf)|wg-quick', re.I)
'''
anchor2 = 'def generate_session():'
assert anchor2 in src
src = src.replace(anchor2, targets + '\n' + anchor2, 1)
if not re.search(r'^import re\b|^import .*\bre\b', src, re.M):
    src = 'import re\n' + src

# 2) 화면: 각 패널 끝에 터미널 자리
src = src.replace('      </section>\n\n      <!-- AWS EC2 관리 (2026-11-18, PR #13·#14) -->',
                  '        <div class="mt-term" data-group="onprem"></div>\n      </section>\n\n      <!-- AWS EC2 관리 (2026-11-18, PR #13·#14) -->', 1)
src = src.replace('      </section>\n\n      <!-- OpenStack 구조 · 연결 (2026-11-18 #osvm에서 분리) -->',
                  '        <div class="mt-term" data-group="aws"></div>\n      </section>\n\n      <!-- OpenStack 구조 · 연결 (2026-11-18 #osvm에서 분리) -->', 1)
assert src.count('class="mt-term"') == 2

# 3) JS: 대상 선택 · 프리셋 · 입력 · 비밀번호 모달(type=password, 화면 비노출)
js = r'''
    // ===== 다중 대상 터미널 (AWS · 온프렘) 2026-11-19 =====
    let ktCtrlPwd = '';
    async function mtVerify(p) {
      if (!p) return false;
      try { const r = await fetch('/api/ctrl/verify', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ password: p }) }); return r.ok; }
      catch (e) { return false; }
    }
    const MT_COMMON = { '⏱ 상태': `hostname; uptime; free -h | sed -n 1,2p; df -h / | tail -1`, '🚫 실패 서비스': `systemctl --failed --no-legend || true` };
    const MT_GROUPS = {
      aws: { title: '☁️ AWS 터미널', targets: {
        'ctl': { '🤖 러너 healthz': `curl -s -m5 http://127.0.0.1:8080/healthz; echo`, '📜 러너 로그': `sudo journalctl -u orchestrator --no-pager -n 20 | cut -c1-200`, '🔐 WG': `sudo wg show wg0 latest-handshakes | awk -v n=$(date +%s) '{print $1, ($2 ? n-$2 " 초 전" : "없음")}'`, '🏠 온프렘 도달': `for u in http://192.168.120.226:8080/healthz http://10.10.1.100/healthz; do echo "$u $(curl -s -m4 -o /dev/null -w '%{http_code}' $u)"; done; ping -c1 -W2 10.10.2.10 >/dev/null && echo 'db-01 응답' || echo 'db-01 응답 없음'` },
        'dr': { '🧩 파드': `sudo /usr/local/bin/k3s kubectl -n minwon-dr get pods -o wide`, '🔁 복제 상태': `echo 'SHOW REPLICA STATUS' | sudo /usr/local/bin/k3s kubectl -n minwon-dr exec -i minwon-mysql-0 -- sh -c 'mysql -E -uroot -p"$MYSQL_ROOT_PASSWORD" 2>/dev/null' | grep -E 'Running:|Seconds_Behind|Last_(IO|SQL)_Error:|Source_Host'`, '💓 heartbeat': `echo 'SELECT ts, TIMESTAMPDIFF(SECOND, ts, UTC_TIMESTAMP(3)) AS lag_s FROM repl_check.heartbeat' | sudo /usr/local/bin/k3s kubectl -n minwon-dr exec -i minwon-mysql-0 -- sh -c 'mysql -E -uroot -p"$MYSQL_ROOT_PASSWORD" 2>/dev/null'`, '🩺 앱 healthz': `curl -s -m5 http://127.0.0.1:30080/healthz; echo`, '💾 백업 목록': `sudo ls -lh /var/backups/mysql | tail -5`, '🔐 WG': `sudo wg show wg0 latest-handshakes | awk -v n=$(date +%s) '{print $1, ($2 ? n-$2 " 초 전" : "없음")}'` },
      } },
      onprem: { title: '🖥️ 온프렘 터미널', targets: {
        'controller': { '🧮 compute 서비스': `source /root/keystonerc_admin; openstack compute service list -c Binary -c Host -c Status -c State`, '📦 인스턴스 배치': `source /root/keystonerc_admin; openstack server list --all-projects --long -c Name -c Status -c Host -c Networks`, '🌐 네트워크 에이전트': `source /root/keystonerc_admin; openstack network agent list -c Host -c Binary -c Alive -c State`, '🧭 라우터': `source /root/keystonerc_admin; for r in rt-edge rt-data; do echo "== $r"; openstack router show $r -f value -c external_gateway_info -c routes; done`, '🧠 메모리 상위': `free -m | sed -n 1,3p; ps -eo rss,comm --sort=-rss | head -8` },
        'compute1': { '🖥 VM': `virsh list --all`, '⚙ 서비스': `systemctl is-active openstack-nova-compute ovn-controller neutron-ovn-metadata-agent` },
        'compute2': { '🖥 VM': `virsh list --all`, '⚙ 서비스': `systemctl is-active openstack-nova-compute ovn-controller neutron-ovn-metadata-agent` },
        'compute3': { '🖥 VM': `virsh list --all`, '⚙ 서비스': `systemctl is-active openstack-nova-compute ovn-controller neutron-ovn-metadata-agent` },
        'compute4': { '🖥 VM': `virsh list --all`, '⚙ 서비스': `systemctl is-active openstack-nova-compute ovn-controller neutron-ovn-metadata-agent` },
        'k8s-cp1': { '🩺 앱 healthz': `curl -s -m5 http://127.0.0.1:8080/healthz; echo`, '📜 앱 로그': `sudo journalctl -u minwon-app --no-pager -n 15 | cut -c1-200`, '☸ k3s': `sudo k3s kubectl get nodes; sudo k3s kubectl get pods -A --no-headers | awk '{print $1, $2, $4}'`, '🛣 DB 경로': `ip route get 10.10.2.10 | head -1; timeout 3 bash -c '</dev/tcp/10.10.2.10/3306' && echo 'db-01:3306 열림' || echo 'db-01:3306 닫힘'` },
        'db-01': { '🗄 MySQL': `systemctl is-active mysql; sudo mysql -E -e 'SELECT @@version, @@server_id, @@gtid_mode, @@read_only, @@super_read_only'`, '🔁 복제 연결': `sudo mysql -e "SHOW REPLICAS; SELECT user, host, command, time FROM information_schema.processlist WHERE command LIKE 'Binlog%'"`, '📊 데이터': `sudo mysql -N -e "SELECT 'complaints', COUNT(*) FROM minwon_db.complaints; SELECT 'gtid', @@GLOBAL.gtid_executed"`, '💾 백업 목록': `sudo ls -lh /var/backups/mysql | tail -5; df -h /var/lib/mysql | tail -1` },
        'k8s-w1': { '☸ k3s-agent': `systemctl is-active k3s-agent || echo '클러스터 미가입'` },
        'k8s-w2': { '☸ k3s-agent': `systemctl is-active k3s-agent || echo '클러스터 미가입'` },
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
    async function mtExec(box, cmd, pwd) {
      const sel = box.querySelector('select'), scr = box.querySelector('.mt-screen'), t = sel.value;
      const label = sel.options[sel.selectedIndex].text;
      scr.insertAdjacentHTML('beforeend', `\n<span style="color:#9FD3F5">[${escapeHtml(label)}]$ ${escapeHtml(cmd)}</span>\n<span class="mt-wait" style="color:#B4C6D8">⏳ 실행 중...</span>\n`);
      scr.scrollTop = scr.scrollHeight;
      try {
        const r = await fetch('/api/term/exec', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ target: t, cmd, password: pwd || '' }) });
        const d = await r.json(); scr.querySelectorAll('.mt-wait').forEach(e => e.remove());
        if (d.need_password && !pwd) { const p = await mtAskPassword(cmd); if (p) return mtExec(box, cmd, p); scr.insertAdjacentHTML('beforeend', `<span style="color:#F4C95D">취소됨</span>` + String.fromCharCode(10)); return; }
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
      const draw = () => { pre.innerHTML = ''; Object.entries(Object.assign({}, MT_COMMON, g.targets[sel.value])).forEach(([n, c]) => {
        const b = document.createElement('button'); b.className = 'btn-top'; b.style.cssText = 'font-size:11px;padding:4px 9px'; b.textContent = n; b.title = c; b.onclick = () => mtExec(box, c); pre.appendChild(b); }); };
      sel.onchange = draw; draw();
      const run = () => { const c = inp.value.trim(); if (c) { mtExec(box, c); inp.value = ''; } };
      box.querySelector('.mt-run').onclick = run; inp.onkeydown = e => { if (e.key === 'Enter') run(); };
      box.querySelector('.mt-clr').onclick = () => { box.querySelector('.mt-screen').textContent = '[SYSTEM] 화면을 지웠습니다.'; };
    }
    document.addEventListener('DOMContentLoaded', () => document.querySelectorAll('.mt-term').forEach(mtRender));
    if (document.readyState !== 'loading') document.querySelectorAll('.mt-term').forEach(mtRender);
'''
anchor3 = '    // #osops 연결 점검 프리셋'
assert anchor3 in src
src = src.replace(anchor3, js + '\n' + anchor3, 1)

open(F, 'w', encoding='utf-8').write(src)
import re as _r
hits=[n+1 for n,l in enumerate(src.split('\n')) if _r.search("'"+_r.escape(old_pw)+"'|\\("+_r.escape(old_pw)+"\\)|\""+_r.escape(old_pw)+"\"", l)]
print('patched. 비밀번호 리터럴 남은 줄:', hits)
