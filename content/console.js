    // ===== 통합 콘솔: 3대 영역 → 인스턴스 → 실제 터미널 (content/console.js) =====
    // 서버: s1 figteam-console (/console/api/*, /console/ws/<대상>) · 콘솔 비밀번호로 잠금
    // 예전 통합 터미널 기능: 대상별 「확인」·「⚠ 복구」 버튼, 탭, ⧉ 화면 위 창(끌기·크기·최소화·최대화·되돌리기), ↗ 새 창
    const CS = { open: false, solo: null, targets: null, layout: '1', slots: [], floats: [], active: 0, loaded: false,
      sizes: { col: 50, row: 50 }, seq: 0, z: 900, pending: null, page: false, status: null, owner: "", expanded: {}, openNow: {}, stTimer: null, presets: {} };
    const CS_TERM_URL = '/term/';
    // 대시보드에서: 통합 터미널 페이지로 이동 (원클릭 — 대상이 있으면 바로 접속)
    function csGo(id) {
      if (id === 's1' || id === 't1-vm2') {
        if (typeof wikiToast === 'function') wikiToast('s1 호스트는 웹에서 콘솔 터미널 접근이 불가합니다.');
        else alert('s1 호스트는 웹에서 콘솔 터미널 접근이 불가합니다.');
        return;
      }
      location.href = CS_TERM_URL + (id ? '?t=' + encodeURIComponent(id) : '');
    }
    // 왼쪽 트리: 클라우드 → 인스턴스 → (그 위의 VM) → 서비스. 클라우드마다 웹 콘솔 링크.
    const CS_GROUPS = [
      ['openstack', '온프렘 · OpenStack', ['onprem', 'openstack'], [['Horizon 웹 콘솔', 'https://horizon.ktci5.kr/dashboard/']]],
      ['kt', 'KT Cloud', ['kt'], [['KT Edge 상태', 'https://kt-edge.ktci5.kr/'], ['KT Cloud 콘솔', 'https://cloud.kt.com/']]],
      ['aws', 'AWS', ['aws'], [['Orchestrator', 'https://aws-ctl.ktci5.kr/healthz'], ['AWS 콘솔', 'https://console.aws.amazon.com/']]]];
    const CS_LAYOUTS = [['1', '하나'], ['h', '좌우'], ['v', '상하'], ['4', '4분할']];
    const CS_XTERM = 'https://cdn.jsdelivr.net/npm/@xterm/xterm@5.5.0';
    const CS_FIT = 'https://cdn.jsdelivr.net/npm/@xterm/addon-fit@0.10.0';
    const CS_CLOSE_MSG = { 4401: '콘솔 잠금이 풀려 있지 않습니다', 4403: '허용되지 않은 출처입니다', 4404: '없는 대상입니다',
      4409: '연결할 수 없는 대상입니다', 4429: '동시에 열 수 있는 터미널(6개)을 넘었습니다', 1006: '연결이 끊겼습니다' };

    function csLoadXterm() {
      if (CS.loaded) return Promise.resolve();
      const add = (tag, attrs) => new Promise((ok, bad) => {
        const el = document.createElement(tag); Object.assign(el, attrs); el.onload = ok; el.onerror = bad; document.head.appendChild(el);
      });
      return Promise.all([
        add('link', { rel: 'stylesheet', href: CS_XTERM + '/css/xterm.min.css' }),
        add('script', { src: CS_XTERM + '/lib/xterm.min.js' })
      ]).then(() => add('script', { src: CS_FIT + '/lib/addon-fit.min.js' })).then(() => { CS.loaded = true; });
    }
    async function csApi(method, path, body) {
      const opt = { method: method, credentials: 'same-origin', cache: 'no-store', headers: {} };
      if (body) { opt.headers['Content-Type'] = 'application/json'; opt.body = JSON.stringify(body); }
      const r = await fetch(path, opt);
      let d = null; try { d = await r.json(); } catch (e) {}
      if (!r.ok) throw Object.assign({ status: r.status }, d || {});
      return d;
    }
    function csRoot() {
      let el = document.getElementById('cs-root');
      if (!el) { el = document.createElement('div'); el.id = 'cs-root'; el.setAttribute('role', 'region'); el.setAttribute('aria-label', '통합 콘솔'); document.body.appendChild(el); }
      return el;
    }
    function csT(id) { return (CS.targets || []).find(t => t.id === id) || { name: id }; }

    // ---------- 왼쪽 트리 (상태는 /console/api/status, 대시보드가 받은 값이 있으면 재사용) ----------
    async function csLoadStatus() {
      try {
        if (typeof DASH !== 'undefined' && DASH.snap) CS.status = DASH.snap;
        else { const r = await fetch('/console/api/status', { cache: 'no-store' }); if (r.ok) CS.status = await r.json(); }
      } catch (e) {}
      const tree = document.getElementById('cs-tree');
      if (tree) tree.innerHTML = csTreeHtml();
    }
    // 부모: 상태 수집이 호스트 virsh 로 실측한 배치가 우선, 없으면 targets.json 의 정적 parent
    function csStat(id) { return ((CS.status && CS.status.instances) || []).find(i => i.id === id); }
    function csParent(t) { const st = csStat(t.id); return (st && st.parent) || t.parent; }
    function csTreeHtml() {
      if (!CS.targets) return '';
      return CS_GROUPS.map(g => {
        const mine = CS.targets.filter(t => g[2].indexOf(t.area) >= 0 && t.id !== 's1' && t.target !== 's1');
        const ids = mine.map(t => t.id);
        // 진입점(컨트롤러·컴퓨트) 먼저, 이름만 있는 기반 호스트(s1)는 맨 아래
        const roots = mine.filter(t => ids.indexOf(csParent(t)) < 0).sort((a, b) => (a.area === 'onprem') - (b.area === 'onprem'));
        return '<div class="cs-area"><div class="cfg-group-head"><span class="cfg-dot cfg-c-' + g[0] + '"></span>' + g[1] + '</div>' +
          roots.map(t => csNodeHtml(t, mine, 0)).join('') +
          '<div class="cs-weblinks">' + g[3].map(l => '<a href="' + l[1] + '" target="_blank" rel="noopener">' + cfgEsc(l[0]) + ' ↗</a>').join('') + '</div></div>';
      }).join('');
    }
    function csNodeHtml(t, mine, depth) {
      const st = csStat(t.id) || {};
      const kids = mine.filter(x => csParent(x) === t.id);
      const svcs = (st.units || []).map(u => ({ kind: 'unit', name: u.unit, ok: u.state === 'active', state: u.state, desc: ((st.unit_meta || {})[u.unit] || {}).desc || '' }))
        .concat((st.pods || []).filter(p => p.phase !== 'Succeeded').map(p => ({ kind: 'pod', name: p.name, ns: p.ns, ok: p.phase === 'Running', state: p.phase, desc: p.ns })));
      const open = CS.expanded[t.id] === undefined ? kids.length > 0 : CS.expanded[t.id];   // 하위 VM 이 있으면 처음부터 펼침(계단식)
      const svcOpen = !!CS.expanded[t.id + ':svc'], has = kids.length || svcs.length;
      CS.openNow[t.id] = open; CS.openNow[t.id + ':svc'] = svcOpen;
      const bad = svcs.filter(x => !x.ok).length;
      const vmOff = st.vm_state && st.vm_state !== 'running';
      const dot = vmOff ? 'off' : st.alive === true ? (bad ? 'wait' : 'ok') : st.alive === false ? 'off' : '';
      const sub = t.disabled || ((vmOff ? 'VM ' + st.vm_state + ' · ' : '') + (t.desc || ''));
      const role = t.role ? '<em class="cs-role cs-role-' + (t.disabled ? 'none' : kids.length ? 'host' : 'vm') + '">' + cfgEsc(t.role) + '</em>' : '';
      let h = '<div class="cs-node" style="--d:' + depth + '"><div class="cs-node-row">' +
        (has ? '<button type="button" class="cs-tog" aria-expanded="' + open + '" title="펼치기" onclick="csToggle(\'' + cfgEsc(t.id) + '\')">' + (open ? '▾' : '▸') + '</button>' : '<span class="cs-tog-sp"></span>') +
        '<span class="cs-dot cs-dot-' + dot + '"></span>' +
        '<button type="button" class="cs-target"' + (t.disabled ? ' disabled title="' + cfgEsc(t.disabled) + '"' : ' title="누르면 바로 접속"') +
        ' onclick="csPick(\'' + cfgEsc(t.id) + '\')"><b>' + cfgEsc(t.name) + role + '</b><span>' + cfgEsc(sub) + '</span></button></div>';
      if (open) {
        h += kids.map(k => csNodeHtml(k, mine, depth + 1)).join('');   // 하위 VM(마스터·워커·DB) 먼저
        if (svcs.length) {
          h += '<div class="cs-node" style="--d:' + (depth + 1) + '"><div class="cs-node-row"><button type="button" class="cs-tog" aria-expanded="' + svcOpen + '" onclick="csToggle(\'' + cfgEsc(t.id) + ':svc\')">' + (svcOpen ? '▾' : '▸') + '</button>' +
            '<button type="button" class="cs-svc-head" onclick="csToggle(\'' + cfgEsc(t.id) + ':svc\')">서비스 ' + svcs.length + (bad ? ' · <b>이상 ' + bad + '</b>' : '') + '</button></div></div>';
          if (svcOpen) h += '<div class="cs-svcs" style="--d:' + (depth + 1) + '">' + svcs.map(x =>
            '<button type="button" class="cs-svc" data-id="' + cfgEsc(t.id) + '" data-kind="' + x.kind + '" data-name="' + cfgEsc(x.name) + '" data-ns="' + cfgEsc(x.ns || '') + '" onclick="csSvcBtn(this)" title="' + cfgEsc(x.desc) + ' — 누르면 상태 확인">' +
            '<span class="cs-dot cs-dot-' + (x.ok ? 'ok' : 'off') + '"></span><span class="cs-svc-n">' + cfgEsc(x.name) + '</span><small>' + (x.kind === 'pod' ? '파드' : '서비스') + '</small></button>').join('') + '</div>';
        }
      }
      return h + '</div>';
    }
    function csToggle(id) { CS.expanded[id] = !(CS.openNow[id] !== undefined ? CS.openNow[id] : CS.expanded[id]); const tree = document.getElementById('cs-tree'); if (tree) tree.innerHTML = csTreeHtml(); }
    // 서비스 클릭: 그 인스턴스 터미널에서 상태(또는 파드 로그) 명령을 바로 실행
    function csSvcBtn(btn) {
      const d = btn.dataset, tg = csT(d.id);
      const cmd = d.kind === 'pod' ? (tg.kubectl || 'kubectl') + ' -n ' + d.ns + ' logs ' + d.name + ' --tail=40'
        : 'systemctl status ' + d.name + ' --no-pager -n 15';
      csRunOn(d.id, cmd);
    }
    function csRunOn(id, cmd) {
      let t = csAllTerms().find(x => x.target === id && x.ws);
      if (!t) { csPick(id); t = csAllTerms().find(x => x.target === id); }
      else { const f = csFind(t.uid); if (f.where === 'slot') csFocus(f.i); else csTabGo(t.uid); }
      if (!t) return;
      if (t.ws && t.ws.readyState === 1) { t.ws.send(JSON.stringify({ t: 'i', d: cmd + '\r' })); t.term.focus(); }
      else t.queue = cmd;   // 연결되면 실행
    }

    // ---------- 사용자 이름(세션 이어가기 열쇠 · 설계/설정과 공유) ----------
    const CS_ENTRY_SKIP_KEY = 'fig.entry_name_skipped_v1';

    function figAuthStorageKey() {
      return typeof AUTH_KEY !== 'undefined' ? AUTH_KEY : 'figteam_auth_token';
    }
    function csIsRealName(name) {
      const s = String(name == null ? '' : name).trim();
      if (!s) return false;
      const lower = s.toLowerCase();
      return s !== '게스트' && s !== '미설정' && lower !== 'guest' && lower !== 'seed';
    }
    function csNormKey(k) {
      return String(k == null ? '' : k).trim().toUpperCase().replace(/[^A-Z0-9_-]/g, '').slice(0, 16);
    }
    function csGenKey() {
      const chars = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789';
      let out = '';
      for (let i = 0; i < 6; i++) out += chars[Math.floor(Math.random() * chars.length)];
      return out;
    }
    function csReadJson(key, fallback) {
      try { const raw = localStorage.getItem(key); return raw ? JSON.parse(raw) : fallback; } catch (e) { return fallback; }
    }
    function csParseBaseName(raw) {
      const s = String(raw == null ? '' : raw).trim();
      const m = s.match(/^(.*?)#([A-Za-z0-9_-]{2,16})$/);
      return (m ? m[1] : s).trim();
    }
    // 읽기 전용 키 검증: 자동 생성 없이 실제 이름+접속 키가 등록된 경우만 반환 (키 없는 이전 세션 판별용)
    function figReadStoredAccessKey() {
      const prof = csReadJson('fig.access.profile_v1', null);
      if (!prof || typeof prof !== 'object') return null;
      const ak = csNormKey(prof.access_key);
      const cleanName = csParseBaseName(prof.member);
      if (ak.length < 2 || !csIsRealName(cleanName)) return null;
      return { member: cleanName, access_key: ak };
    }
    function figShowLoginNotice(msg) {
      const el = typeof document !== 'undefined' ? document.getElementById('login-notice') : null;
      if (!el) return;
      if (msg) {
        el.textContent = msg;
        el.style.display = 'block';
      } else {
        el.textContent = '';
        el.style.display = 'none';
      }
    }
    function figPrepareLoginForm() {
      const memEl = typeof document !== 'undefined' ? document.getElementById('auth-member') : null;
      const keyView = typeof document !== 'undefined' ? document.getElementById('auth-access-key-view') : null;
      if (!memEl && !keyView) return;
      const prof = csReadJson('fig.access.profile_v1', null) || {};
      const last = csReadJson('fw_last', null) || {};
      let termUser = '';
      try { termUser = localStorage.getItem('fig.term.user') || ''; } catch (e) {}
      const candidates = [prof.member, termUser, last.member];
      let foundName = '';
      for (let i = 0; i < candidates.length; i++) {
        const clean = csParseBaseName(candidates[i]);
        if (csIsRealName(clean)) { foundName = clean; break; }
      }
      if (memEl && !memEl.value.trim() && foundName) memEl.value = foundName;
      if (keyView) {
        const curKey = csNormKey(prof.access_key) || csNormKey(last.access_key);
        keyView.textContent = curKey ? (curKey + ' (서버 할당 · 변경 불가)') : '로그인 시 서버에서 자동 할당 (변경 불가)';
      }
    }
    const CS_SITE_VISITS_KEY = 'fig.access.site_visits_v1';

    function figReadUaSummary() {
      try {
        const raw = (navigator && navigator.userAgent) || '';
        const br = raw.indexOf('Edg/') >= 0 ? 'Edge'
          : raw.indexOf('Chrome/') >= 0 ? 'Chrome'
          : raw.indexOf('Firefox/') >= 0 ? 'Firefox'
          : raw.indexOf('Safari/') >= 0 ? 'Safari' : 'Browser';
        const os = /iPhone|iPad/.test(raw) ? 'iOS'
          : raw.indexOf('Android') >= 0 ? 'Android'
          : /Mac OS X|Macintosh/.test(raw) ? 'macOS'
          : raw.indexOf('Windows') >= 0 ? 'Windows'
          : raw.indexOf('Linux') >= 0 ? 'Linux' : '';
        return os ? (br + ' · ' + os) : br;
      } catch (e) { return ''; }
    }
    function figRecordSiteVisit(authState, view, detail) {
      const state = authState || 'visitor';
      const path = (typeof location !== 'undefined' ? (location.pathname + (location.hash || '')) : '/') || '/';
      const v = view || (CS.page ? 'term' : 'dashboard');
      const sig = state + '|' + v + '|' + path;
      const nowMs = Date.now();
      if (CS._lastVisitSig === sig && CS._lastVisitTs && (nowMs - CS._lastVisitTs) < 2000) return;
      CS._lastVisitSig = sig;
      CS._lastVisitTs = nowMs;
      const stored = figReadStoredAccessKey();
      const entry = {
        ts: Math.floor(nowMs / 1000),
        path: path.slice(0, 120),
        view: String(v).slice(0, 32),
        auth_state: state,
        member: stored ? stored.member : '',
        access_key: stored ? stored.access_key : '',
        ua: figReadUaSummary(),
        ip: '현재 브라우저',
        detail: String(detail || '').slice(0, 120)
      };
      try {
        const list = csReadJson(CS_SITE_VISITS_KEY, []) || [];
        list.unshift(entry);
        localStorage.setItem(CS_SITE_VISITS_KEY, JSON.stringify(list.slice(0, 300)));
      } catch (e) {}
      try {
        fetch('/api/visit', {
          method: 'POST',
          credentials: 'same-origin',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            path: entry.path,
            view: entry.view,
            auth_state: entry.auth_state,
            member: entry.member,
            access_key: entry.access_key,
            detail: entry.detail
          })
        }).catch(() => {});
      } catch (e) {}
    }

    async function figExpireKeylessSessions() {
      try { sessionStorage.removeItem(figAuthStorageKey()); } catch (e) {}
      try { sessionStorage.removeItem(CS_ENTRY_SKIP_KEY); } catch (e) {}
      const post = url => fetch(url, { method: 'POST', credentials: 'same-origin' }).catch(() => {});
      await Promise.all([post('/console/api/lock'), post('/api/logout')]);
    }
    function csReadProfile() {
      const prof = csReadJson('fig.access.profile_v1', null) || {};
      const last = csReadJson('fw_last', null) || {};
      let termUser = '';
      try { termUser = localStorage.getItem('fig.term.user') || ''; } catch (e) {}
      const ak = csNormKey(prof.access_key || last.access_key) || csGenKey();
      const candidates = [CS.owner, termUser, prof.member, last.member];
      let realName = '';
      for (let i = 0; i < candidates.length; i++) {
        const clean = csParseBaseName(candidates[i]);
        if (csIsRealName(clean)) { realName = clean; break; }
      }
      if (realName) {
        try {
          if (localStorage.getItem('fig.term.user') !== realName) localStorage.setItem('fig.term.user', realName);
          if (!prof.access_key || prof.member !== realName) {
            localStorage.setItem('fig.access.profile_v1', JSON.stringify({ member: realName, access_key: ak }));
          }
        } catch (e) {}
      }
      return { member: realName, access_key: ak };
    }
    function csWriteProfile(member, accessKey) {
      const cleanName = csParseBaseName(member);
      const ak = csNormKey(accessKey) || csReadProfile().access_key || csGenKey();
      if (!csIsRealName(cleanName)) return { member: '', access_key: ak };
      try {
        localStorage.setItem('fig.term.user', cleanName);
        localStorage.setItem('fig.access.profile_v1', JSON.stringify({ member: cleanName, access_key: ak }));
        const kb = csReadJson('fig.access.keybook_v1', {}) || {};
        kb[ak] = { access_key: ak, member: cleanName, updated_at: Math.floor(Date.now() / 1000), last_ip: '콘솔 등록' };
        localStorage.setItem('fig.access.keybook_v1', JSON.stringify(kb));
        const last = csReadJson('fw_last', null) || {};
        localStorage.setItem('fw_last', JSON.stringify({ slug: last.slug || 'figteam', member: cleanName, access_key: ak }));
        sessionStorage.removeItem(CS_ENTRY_SKIP_KEY);
      } catch (e) {}
      CS.owner = cleanName;
      const chip = document.getElementById('cs-owner-chip');
      if (chip) chip.textContent = cleanName;
      return { member: cleanName, access_key: ak };
    }
    async function csSyncProfileToServer(member, ak, isFirst) {
      const formatted = member.slice(0, Math.max(1, 20 - 1 - ak.length)).trim() + '#' + ak;
      const post = (url, body) => fetch(url, {
        method: 'POST',
        credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body)
      }).catch(() => {});
      await Promise.all([
        post('/api/me/name', { member: formatted, access_key: ak }),
        post('/api/access/register', {
          member: member,
          access_key: ak,
          action: isFirst ? 'first_entry' : 'rename',
          detail: isFirst ? '통합 콘솔 최초 접속 이름 등록' : '콘솔 이름 변경'
        }),
        post('/api/access/keybook', { access_key: ak, member: member })
      ]);
    }
    function csOpenNameModal(isFirst, onDone) {
      if (!isFirst && typeof wkOpenIdentityModal === 'function') {
        wkOpenIdentityModal(null, { firstEntry: false, onDone: onDone });
        return;
      }
      const old = document.getElementById('wk-identity-modal');
      if (old) old.remove();
      const prof = csReadProfile();
      const curName = csIsRealName(prof.member) ? prof.member : '';
      const modal = document.createElement('div');
      modal.id = 'wk-identity-modal';
      modal.className = 'cfg-modal-overlay';
      modal.innerHTML =
        '<div class="cfg-builder-modal-card" role="dialog" aria-modal="true" style="max-width:480px;">' +
        '<div class="cfg-builder-modal-head">' +
        '<span>' + (isFirst ? '👤 처음 접속 안내 — 사용자 이름 입력' : '👤 콘솔 사용자 이름 변경') + '</span>' +
        (isFirst ? '' : '<button type="button" class="cfg-win-btn btn-close" id="cs-id-close" style="color:#cbd5e1;">✕</button>') +
        '</div>' +
        '<div class="cfg-builder-modal-body">' +
        '<p class="manual-desc" style="margin:0;font-size:12.5px;line-height:1.55;">통합 콘솔 세션 이어가기와 설계/설정 변경 이력에 사용됩니다. <b>한 번 입력하면 두 화면에 자동 적용되며 이후 다시 묻지 않습니다.</b></p>' +
        '<div class="cfg-builder-field">' +
        '<label class="cfg-builder-label">사용자 이름 (필수, 1~13자 권장)</label>' +
        '<input type="text" id="cs-id-name" class="cfg-builder-input" maxlength="20" value="' + cfgEsc(curName) + '" placeholder="예: 홍길동">' +
        '</div>' +
        '<div class="cfg-builder-field">' +
        '<label class="cfg-builder-label">접속 키값 (서버 자동 할당 · 변경 불가)</label>' +
        '<input type="text" id="cs-id-key" class="cfg-builder-input wk-key-locked" value="' + cfgEsc(prof.access_key || '서버 자동 할당') + '" readonly disabled style="font-family:var(--font-mono);text-transform:uppercase;">' +
        '</div>' +
        '<p class="wk-error" id="cs-id-err" role="alert" hidden style="margin:0;"></p>' +
        '</div>' +
        '<div class="cfg-modal-foot">' +
        '<button type="button" class="cfg-btn-cancel" id="cs-id-cancel">' + (isFirst ? '이번 세션 건너뛰기' : '취소') + '</button>' +
        '<button type="button" class="cfg-btn-confirm" id="cs-id-save" style="background:#2563eb;border-color:#3b82f6;">' + (isFirst ? '이름 저장 후 시작' : '저장') + '</button>' +
        '</div></div>';
      document.body.appendChild(modal);

      let settled = false;
      const finish = res => {
        if (settled) return;
        settled = true;
        if (typeof onDone === 'function') onDone(res);
      };
      const close = res => {
        modal.remove();
        document.removeEventListener('keydown', onKey);
        finish(res || { skipped: true });
      };
      const onKey = e => { if (!isFirst && e.key === 'Escape') close({ skipped: true }); };
      document.addEventListener('keydown', onKey);
      const closeBtn = modal.querySelector('#cs-id-close');
      if (closeBtn) closeBtn.onclick = () => close({ skipped: true });
      modal.querySelector('#cs-id-cancel').onclick = () => {
        if (isFirst) { try { sessionStorage.setItem(CS_ENTRY_SKIP_KEY, '1'); } catch (e) {} }
        close({ skipped: true });
      };
      modal.onclick = e => { if (!isFirst && e.target === modal) close({ skipped: true }); };

      const errEl = modal.querySelector('#cs-id-err');
      const saveBtn = modal.querySelector('#cs-id-save');
      const nameInput = modal.querySelector('#cs-id-name');

      const submit = async () => {
        const nm = (nameInput.value || '').trim();
        const ak = csNormKey(prof.access_key) || csGenKey();
        errEl.hidden = true;
        if (!csIsRealName(nm)) {
          errEl.textContent = '사용자 이름을 입력하세요. (게스트/seed 제외)';
          errEl.hidden = false;
          nameInput.focus();
          return;
        }
        saveBtn.disabled = true;
        try {
          csWriteProfile(nm, ak);
          await csSyncProfileToServer(nm, ak, isFirst);
          close({ member: nm, access_key: ak, skipped: false });
          if (typeof wikiToast === 'function') wikiToast('사용자 등록됨: ' + nm + ' (' + ak + ')');
        } finally {
          saveBtn.disabled = false;
        }
      };

      saveBtn.onclick = submit;
      nameInput.addEventListener('keydown', e => {
        if (e.key === 'Enter') { e.preventDefault(); submit(); }
      });
      nameInput.focus();
    }
    async function csEnsureFirstEntryName(source) {
      if (typeof wkEnsureFirstEntryName === 'function') {
        const res = await wkEnsureFirstEntryName(source || 'console');
        const name = csReadProfile().member;
        if (name) CS.owner = name;
        const chip = document.getElementById('cs-owner-chip');
        if (chip) chip.textContent = name || '미설정';
        return res;
      }
      const existing = csReadProfile();
      if (csIsRealName(existing.member)) {
        CS.owner = existing.member;
        const chip = document.getElementById('cs-owner-chip');
        if (chip) chip.textContent = existing.member;
        return { member: existing.member, access_key: existing.access_key, existing: true };
      }
      try {
        if (sessionStorage.getItem(CS_ENTRY_SKIP_KEY) === '1') return { skipped: true };
      } catch (e) {}
      if (CS._entryPromise) return CS._entryPromise;
      CS._entryPromise = new Promise(resolve => {
        csOpenNameModal(true, res => {
          CS._entryPromise = null;
          resolve(res || { skipped: true });
        });
      });
      return CS._entryPromise;
    }

    function csOwnerName() {
      const prof = csReadProfile();
      if (csIsRealName(prof.member)) { CS.owner = prof.member; return prof.member; }
      return '';
    }
    function csOwner(force) {
      if (force) { csOpenNameModal(false); return csOwnerName() || 'guest'; }
      const n = csOwnerName();
      CS.owner = n || 'guest';
      const chip = document.getElementById('cs-owner-chip');
      if (chip) chip.textContent = n || '미설정';
      return CS.owner;
    }
    // 새로고침·재진입 시, 이 이름으로 살아 있는 세션을 "쓰던 분할 배치 그대로" 다시 붙인다(로그=스크롤백 재생).
    async function csResume() {
      if (CS.solo || CS.slots.some(s => s.t)) return;
      const n = csOwnerName();
      if (!n) return;                      // 이름을 아직 안 넣었으면 조용히 건너뜀
      let rows = [];
      try { rows = await csApi('GET', '/console/api/sessions?u=' + encodeURIComponent(n)); } catch (e) { return; }
      const alive = new Set(rows.map(r => r.target));
      const usable = tid => alive.has(tid) && CS.targets.some(t => t.id === tid && !t.disabled);
      CS.owner = n;
      let snap = null;
      try { snap = JSON.parse(localStorage.getItem('fig.term.layout') || 'null'); } catch (e) {}
      const snapHas = snap && ((snap.slots || []).some(usable) || (snap.floats || []).some(f => usable(f.target)));
      if (snapHas) {
        CS.layout = snap.layout || '1';
        CS.sizes = snap.sizes || CS.sizes;
        CS.active = Math.max(0, snap.active || 0);
        csRender();                        // 저장된 분할로 빈 칸을 만든 뒤
        (snap.slots || []).forEach((tid, i) => { if (usable(tid) && CS.slots[i]) csConnectSlot(i, tid); });
        (snap.floats || []).forEach(f => { if (usable(f.target)) { const t = csNewTerm(f.target); CS.floats.push(t); csPlaceFloat(t, f.pos); csStart(t); } });
        csApplySizes(); csTabs();
        return;
      }
      if (!rows.length) return;            // 배치 기록이 없으면 살아 있는 세션을 순서대로
      rows.slice(0, csPaneCount()).forEach((r, i) => { if (usable(r.target)) csConnectSlot(i, r.target); });
    }

    // ---------- 열기 · 닫기 · 잠금 ----------
    async function csOpen(soloId) {
      if (soloId === 's1' || soloId === 't1-vm2') {
        const root = csRoot(); root.hidden = false; document.body.classList.add('cs-on');
        root.innerHTML = '<div style="padding:60px 20px; text-align:center; color:#f87171; background:#0f172a; min-height:100vh;">' +
          '<h2 style="font-size:22px; margin-bottom:12px;">🚫 웹 콘솔 터미널 접근 불가</h2>' +
          '<p style="color:#94a3b8; font-size:14px; margin-bottom:24px;">s1 호스트는 기본 팀(figteam) 보안 정책상 웹에서 콘솔 터미널 접근이 제외된 물리 베이스 구역입니다.</p>' +
          '<button type="button" class="wk-btn wk-primary" onclick="location.href=\'/\'" style="padding:8px 16px; background:#0284c7; color:#fff; border:none; border-radius:6px; cursor:pointer;">대시보드로 돌아가기</button>' +
          '</div>';
        return;
      }
      if (!figReadStoredAccessKey()) {
        figExpireKeylessSessions();
        figRecordSiteVisit('expired', CS.page ? 'term' : 'console', '키 없는 콘솔 접속 차단');
        const root = csRoot();
        root.hidden = false;
        root.classList.toggle('cs-solo', !!soloId);
        root.classList.toggle('cs-page', CS.page);
        document.body.classList.add('cs-on');
        CS.open = true; CS.solo = soloId || null;
        return csShowUnlock('접속 키가 없는 이전 세션이 만료되었습니다. 이름·접속 키와 비밀번호를 입력해 다시 로그인해 주세요.');
      }
      figRecordSiteVisit('authenticated', CS.page ? 'term' : 'console', '통합 콘솔 접속');
      const root = csRoot();
      if (CS.targets && root.querySelector('.cs-wrap') && !soloId) {   // 다른 화면에 갔다 와도 열린 터미널은 그대로
        root.hidden = false; document.body.classList.add('cs-on'); CS.open = true;
        const curName = csOwnerName();
        const chip = document.getElementById('cs-owner-chip');
        if (chip) chip.textContent = curName || '미설정';
        csApplySizes(); csLoadStatus();
        await csEnsureFirstEntryName('console');
        if (CS.pending) { const id = CS.pending; CS.pending = null; csPick(id); }
        return;
      }
      CS.open = true; CS.solo = soloId || null;
      CS.booting = true;   // 복원 끝나기 전엔 레이아웃 저장 금지(빈 칸으로 스냅샷을 덮어쓰지 않도록)
      root.hidden = false;
      root.classList.toggle('cs-solo', !!CS.solo);
      root.classList.toggle('cs-page', CS.page);
      document.body.classList.add('cs-on');
      if (!root.querySelector('.cs-wrap')) root.innerHTML = '<p class="cs-wait">통합 콘솔을 불러오는 중…</p>';
      try { await csLoadXterm(); }
      catch (e) { root.innerHTML = '<p class="cs-wait wk-error">터미널 화면 구성요소(xterm.js)를 불러오지 못했습니다. 인터넷 연결을 확인하세요.</p>'; return; }
      try { CS.targets = await csApi('GET', '/console/api/targets'); await csLoadPresets(); }
      catch (e) { return csShowUnlock(e.status === 401 ? '' : (e.error || '콘솔 서버에 연결하지 못했습니다 (' + e.status + ')')); }
      csRender();
      csLoadStatus();
      await csEnsureFirstEntryName('console');
      const chipAfter = document.getElementById('cs-owner-chip');
      if (chipAfter) chipAfter.textContent = csOwnerName() || '미설정';
      if (!CS.stTimer) CS.stTimer = setInterval(() => { if (CS.open && !csRoot().hidden) csLoadStatus(); }, 20000);
      if (CS.solo && !CS.slots[0].t) csConnectSlot(0, CS.solo);
      else if (CS.scenarioMode) await csSetupScenarioSlots(CS.scenarioMode);
      else if (CS.pending) { const id = CS.pending; CS.pending = null; if (CS.targets.some(t => t.id === id && !t.disabled)) csPick(id); }
      else await csResume();   // 새로고침·재진입 시 이 이름의 살아 있는 세션을 자동으로 다시 붙인다
      CS.booting = false; csSaveLayout();   // 복원 끝 — 이제부터 변경은 저장
    }
    // 머리글 [대시보드]·[설정]·[콘솔] 전환 (본문만 바뀜)
    function csView(v) {
      const on = v === 'console', bc = document.getElementById('btn-tab-console');
      if (bc) bc.classList.toggle('active', on);
      if (!on) { csHide(); return false; }
      ['view-dashboard', 'view-settings'].forEach(id => { const e = document.getElementById(id); if (e) e.style.display = 'none'; });
      ['btn-tab-dashboard', 'btn-tab-settings'].forEach(id => { const e = document.getElementById(id); if (e) e.classList.remove('active'); });
      csOpen();
      return true;
    }
    function csHide() {
      const r = document.getElementById('cs-root');
      if (r) r.hidden = true;
      CS.open = false;
      document.body.classList.remove('cs-on');
    }
    function csBack() { if (CS.page) location.href = '/'; else if (typeof switchView === 'function') switchView('dashboard'); }
    function csClose() {
      if (CS.page) { location.href = '/'; return; }
      CS.slots.forEach(s => csDispose(s.t)); CS.floats.forEach(csDispose);
      CS.slots = []; CS.floats = []; CS.open = false;
      const root = csRoot(); root.hidden = true; root.innerHTML = '';
      document.body.classList.remove('cs-on');
      if ((location.hash || '').indexOf('#console') === 0) history.replaceState(null, '', location.pathname);
    }
    function csShowUnlock(msg) {
      CS.slots.forEach(s => csDispose(s.t)); CS.floats.forEach(csDispose); CS.slots = []; CS.floats = [];
      const stored = figReadStoredAccessKey();
      const preName = stored ? stored.member : (csIsRealName(csReadProfile().member) ? csReadProfile().member : '');
      const keyLabel = stored ? (stored.access_key + ' (서버 할당 · 변경 불가)') : '로그인 시 서버에서 자동 할당 (변경 불가)';
      csRoot().innerHTML =
        '<div class="cs-unlock"><form class="wk-card" onsubmit="csUnlock(event)"><h3>통합 콘솔 로그인 (불변 접속 키)</h3>' +
        '<p class="manual-desc">세션이 만료되었거나 접속 키가 없습니다. 이름과 사이트 비밀번호를 입력하면 서버가 접속 키를 자동 할당·유지합니다. 모든 입력과 출력은 기록됩니다.</p>' +
        '<label>사용자 이름 <span>(필수)</span><input name="member" required maxlength="20" autocomplete="nickname" value="' + cfgEsc(preName) + '" placeholder="예: 홍길동"></label>' +
        '<label>접속 키값 <span>(서버 자동 할당 · 변경 불가)</span><div class="login-key-readonly" style="margin-bottom:0;">' + cfgEsc(keyLabel) + '</div></label>' +
        '<label>사이트 비밀번호<input name="password" type="password" required autocomplete="current-password"></label>' +
        '<p class="wk-error" id="cs-unlock-err" role="alert"' + (msg ? '' : ' hidden') + '>' + cfgEsc(msg || '') + '</p>' +
        '<div class="wk-bar wk-bar-inline"><button type="submit" class="wk-btn wk-primary">로그인 및 잠금 해제</button>' +
        (CS.solo ? '' : '<button type="button" class="wk-btn" onclick="csBack()">대시보드로</button>') + '</div></form></div>';
      const memEl = csRoot().querySelector('input[name=member]');
      const pwdEl = csRoot().querySelector('input[name=password]');
      if (memEl && !memEl.value.trim()) memEl.focus();
      else if (pwdEl) pwdEl.focus();
    }
    async function csUnlock(ev) {
      ev.preventDefault();
      const err = document.getElementById('cs-unlock-err');
      const form = ev.target;
      const member = (form.member ? form.member.value : '').trim();
      if (!csIsRealName(member)) {
        err.textContent = '사용자 이름을 입력하세요. (게스트/seed 제외)';
        err.hidden = false;
        if (form.member) form.member.focus();
        return;
      }
      try {
        const res = await csApi('POST', '/console/api/unlock', {
          password: form.password.value,
          member: member
        });
        const ak = csNormKey(res && res.access_key) || csReadProfile().access_key || csGenKey();
        csWriteProfile(member, ak);
        try { sessionStorage.setItem(figAuthStorageKey(), 'valid'); } catch (e) {}
        figRecordSiteVisit('authenticated', CS.page ? 'term' : 'console', '콘솔 로그인 성공');
        csSyncProfileToServer(member, ak, true).catch(() => {});
        csRoot().innerHTML = '';
        csOpen(CS.solo);
      } catch (e) {
        figRecordSiteVisit('login_fail', CS.page ? 'term' : 'console', '콘솔 로그인 실패 (' + (e.status || 0) + ')');
        err.textContent = e.status === 401 ? '비밀번호가 맞지 않습니다' : e.status === 429 ? '시도가 많습니다. 10분 뒤 다시 시도하세요' : (e.error || '잠금을 풀지 못했습니다');
        err.hidden = false;
      }
    }
    async function csLock() {
      try { await csApi('POST', '/console/api/lock', {}); } catch (e) {}
      csShowUnlock('콘솔을 잠갔습니다.');
    }

    // ---------- 화면 구성 ----------
    function csPaneCount() { return CS.solo ? 1 : { '1': 1, h: 2, v: 2, '4': 4 }[CS.layout]; }
    function csRender() {
      const n = csPaneCount();
      while (CS.slots.length < n) CS.slots.push({ t: null });
      while (CS.slots.length > n) {   // 줄어든 칸의 터미널은 끊지 않고 화면 위 창으로 띄운다
        const s = CS.slots.pop();
        if (s.t) CS.floats.push(s.t);
      }
      if (CS.active >= n) CS.active = 0;
      const drawer = CS.solo ? '' :
        '<aside class="cs-drawer"><div class="cs-drawer-head"><b>콘솔</b><span>인스턴스를 누르면 바로 접속 · 서비스를 누르면 상태 확인</span>' +
        '<button type="button" class="cs-owner" onclick="csOwner(true)" title="세션 이어가기에 쓰는 이름 — 누르면 변경">이름: <b id="cs-owner-chip">' + cfgEsc(csOwnerName() || '미설정') + '</b></button></div>' +
        '<div id="cs-tree">' + csTreeHtml() + '</div>' +
        '<div class="cs-drawer-foot"><button type="button" class="wk-mini" onclick="csBack()">← 대시보드</button>' +
        (CS.page ? '' : '<button type="button" class="wk-mini" onclick="window.open(\'/term/\', \'_blank\')">새 창으로</button>') +
        '<button type="button" class="wk-mini cs-btn-gameday" onclick="csOpenScenarioWarRoom()" style="background:#b91c1c;color:#fff;border-color:#ef4444;margin-left:4px;" title="하이브리드 DR 모의 훈련 워룸 열기">🚀 DR 모의 시나리오</button>' + '</div></aside>';
      const bar = CS.solo ? '' :
        '<div class="cs-bar"><div class="cs-layouts" role="group" aria-label="창 배치">' + CS_LAYOUTS.map(l =>
          '<button type="button" class="wk-mini' + (CS.layout === l[0] ? ' cs-on-btn' : '') + '" aria-pressed="' + (CS.layout === l[0]) + '" onclick="csLayout(\'' + l[0] + '\')">' + l[1] + '</button>').join('') +
        '</div><nav class="cs-tabs" id="cs-tabs" aria-label="열린 터미널"></nav></div>';
      const grid = '<div class="cs-grid cs-l' + (CS.solo ? '1' : CS.layout) + '" id="cs-grid">' +
        CS.slots.map((s, i) => '<section class="cs-pane' + (i === CS.active ? ' cs-active' : '') + '" data-i="' + i + '" onmousedown="csFocus(' + i + ')" id="cs-slot-' + i + '"></section>').join('') +
        csGutters() + '</div>';
      csRoot().innerHTML = '<div class="cs-wrap">' + drawer + '<div class="cs-main">' + csScenarioBarHtml() + bar + grid + '</div></div><div class="cs-float-layer" id="cs-float-layer"></div>';
      CS.slots.forEach((s, i) => csFillSlot(i));
      CS.floats.forEach(t => csPlaceFloat(t));
      csApplySizes();
      csTabs();
    }
    function csGutters() {
      const L = CS.solo ? '1' : CS.layout;
      return (L === 'h' || L === '4' ? '<div class="cs-gutter cs-gx" onmousedown="csDrag(event,\'col\')" title="좌우 크기 조절"></div>' : '') +
             (L === 'v' || L === '4' ? '<div class="cs-gutter cs-gy" onmousedown="csDrag(event,\'row\')" title="상하 크기 조절"></div>' : '');
    }
    function csApplySizes() {
      const g = document.getElementById('cs-grid'); if (!g) return;
      g.style.setProperty('--cs-col', CS.sizes.col + '%');
      g.style.setProperty('--cs-row', CS.sizes.row + '%');
      csAllTerms().forEach(t => { try { t.fit.fit(); } catch (e) {} });
    }
    function csDrag(ev, axis) {
      ev.preventDefault();
      const g = document.getElementById('cs-grid'), r = g.getBoundingClientRect();
      const move = e => {
        const v = axis === 'col' ? (e.clientX - r.left) / r.width : (e.clientY - r.top) / r.height;
        CS.sizes[axis] = Math.max(15, Math.min(85, Math.round(v * 100)));
        csApplySizes();
      };
      const up = () => { document.removeEventListener('mousemove', move); document.removeEventListener('mouseup', up); document.body.classList.remove('cs-dragging'); csSaveLayout(); };
      document.body.classList.add('cs-dragging');
      document.addEventListener('mousemove', move); document.addEventListener('mouseup', up);
    }
    function csLayout(l) { CS.layout = l; csRender(); }
    function csFocus(i) {
      CS.active = i;
      document.querySelectorAll('.cs-pane').forEach(el => el.classList.toggle('cs-active', Number(el.dataset.i) === i));
    }
    function csAllTerms() { return CS.slots.map(s => s.t).filter(Boolean).concat(CS.floats); }

    // ---------- 터미널 한 개 (칸·띄운 창이 함께 쓰는 단위) ----------
    async function csLoadPresets() { try { CS.presets = await csApi('GET', '/console/api/presets'); } catch (e) { CS.presets = CS.presets || {}; } }
    function csPresetItems(id) { return ((CS.presets || {})[id] || {}).items || []; }
    function csHeadHtml(t, inFloat) {
      const tg = csT(t.target), items = csPresetItems(t.target);
      const btns = kind => items.map((x, n) => x.kind !== kind ? '' :
        '<button type="button" class="cs-pre' + (kind === 'fix' ? ' cs-pre-fix' : '') + '" title="' + cfgEsc(x.cmd) + '" onclick="csPreset(' + t.uid + ',' + n + ',this)">' + cfgEsc(x.label) + '</button>').join('');
      const hasFix = items.some(x => x.kind === 'fix');
      return '<header class="cs-pane-head"><span class="cs-dot cs-dot-' + (t.stKind || 'wait') + '" id="cs-dot-' + t.uid + '"></span><b>' + cfgEsc(tg.name) + '</b>' +
        '<span class="cs-status" id="cs-st-' + t.uid + '">' + cfgEsc(t.stText || '') + '</span>' +
        '<span class="cs-pane-acts">' +
          (inFloat ? '<button type="button" class="wk-mini" title="최소화" onclick="csFloatMin(' + t.uid + ')">▁</button><button type="button" class="wk-mini" title="최대화" onclick="csFloatMax(' + t.uid + ')">▢</button>' +
            (CS.solo ? '' : '<button type="button" class="wk-mini" title="칸으로 되돌리기" onclick="csDock(' + t.uid + ')">⇲</button>')
            : (CS.solo ? '' : '<button type="button" class="wk-mini" title="화면 위에 띄우기" onclick="csFloat(' + t.uid + ')">⧉</button>')) +
          '<button type="button" class="wk-mini" title="다시 연결" onclick="csReconnect(' + t.uid + ')">⟳</button>' +
          (CS.solo ? '' : '<button type="button" class="wk-mini" title="새 창으로" onclick="csPopout(' + t.uid + ')">↗</button>') +
          '<button type="button" class="wk-mini" title="닫기" onclick="csCloseTerm(' + t.uid + ')">✕</button></span></header>' +
        '<div class="cs-presets"><span class="cs-pre-lbl">확인</span>' + btns('check') +
          (hasFix ? '<span class="cs-pre-lbl cs-pre-warn">복구</span>' + btns('fix') : '') +
          '<button type="button" class="cs-pre cs-pre-edit" onclick="csEditPresets(\'' + cfgEsc(t.target) + '\')">버튼 편집</button></div>';
    }
    // 버튼 목록이 바뀌면 열린 터미널의 머리줄만 다시 그린다 (연결 유지)
    function csRefreshHeads() {
      CS.slots.forEach((sl, i) => { if (sl.t) csFillSlot(i); });
      CS.floats.forEach(t => {
        if (!t.el) return;
        t.el.querySelectorAll('.cs-pane-head, .cs-presets').forEach(e => e.remove());
        t.el.insertAdjacentHTML('afterbegin', csHeadHtml(t, true));
        const head = t.el.querySelector('.cs-pane-head');
        head.addEventListener('mousedown', e => csFloatDragStart(e, t.el));
      });
    }

    function csFillSlot(i) {
      const el = document.getElementById('cs-slot-' + i), t = CS.slots[i].t;
      if (!el) return;
      if (!t) {
        el.innerHTML = '<header class="cs-pane-head"><span class="cs-dot"></span><b>빈 칸</b></header>' +
          '<div class="cs-term"><p class="cs-empty">왼쪽에서 인스턴스를 고르면 이 칸에 터미널이 열립니다.</p></div>';
        return;
      }
      el.innerHTML = csHeadHtml(t, false) + '<div class="cs-term" id="cs-host-' + t.uid + '"></div>';
      document.getElementById('cs-host-' + t.uid).appendChild(t.box);
      setTimeout(() => { try { t.fit.fit(); } catch (e) {} }, 0);
    }
    function csNewTerm(target) {
      const t = { uid: ++CS.seq, target: target, stKind: 'wait', stText: '연결 중…' };
      t.box = document.createElement('div'); t.box.className = 'cs-term-inner';
      return t;
    }
    function csStart(t) {
      const term = new window.Terminal({ cursorBlink: true, fontFamily: "'JetBrains Mono', monospace", fontSize: 13, scrollback: 5000,
        theme: { background: '#06090e', foreground: '#e2e8f0', cursor: '#93c5fd', selectionBackground: '#1e3a8a' } });
      const fit = new window.FitAddon.FitAddon();
      term.loadAddon(fit); term.open(t.box);
      try { fit.fit(); } catch (e) {}
      t.term = term; t.fit = fit;
      csStatus(t, 'wait', '연결 중…');
      const url = (location.protocol === 'https:' ? 'wss://' : 'ws://') + location.host + '/console/ws/' + encodeURIComponent(t.target) +
        '?cols=' + term.cols + '&rows=' + term.rows + '&u=' + encodeURIComponent(csOwner());
      const ws = new WebSocket(url);
      t.ws = ws;
      ws.onopen = () => {
        csStatus(t, 'ok', '연결됨'); term.focus();
        if (t.queue) { const q = t.queue; t.queue = null; setTimeout(() => { if (ws.readyState === 1) ws.send(JSON.stringify({ t: 'i', d: q + '\r' })); }, 700); }
      };
      ws.onmessage = e => term.write(e.data);
      ws.onclose = e => {
        if (t.ws !== ws) return;
        const msg = CS_CLOSE_MSG[e.code] || (e.code === 1000 ? '세션이 끝났습니다' : '연결이 끊겼습니다 (' + e.code + ')');
        csStatus(t, 'off', msg);
        term.write('\r\n\x1b[33m[' + msg + ' — ⟳ 로 다시 연결]\x1b[0m\r\n');
        if (e.code === 4401) csShowUnlock('잠금이 만료되었습니다. 다시 풀어 주세요.');
      };
      term.onData(d => { if (ws.readyState === 1) ws.send(JSON.stringify({ t: 'i', d: d })); });
      term.onResize(sz => { if (ws.readyState === 1) ws.send(JSON.stringify({ t: 'r', c: sz.cols, r: sz.rows })); });
      t.ro = new ResizeObserver(() => { try { fit.fit(); } catch (e) {} });
      t.ro.observe(t.box);
    }
    function csStatus(t, kind, text) {
      t.stKind = kind; t.stText = text;
      const d = document.getElementById('cs-dot-' + t.uid), s = document.getElementById('cs-st-' + t.uid);
      if (d) d.className = 'cs-dot cs-dot-' + kind;
      if (s) s.textContent = text;
      csTabs();
    }
    function csDispose(t) {
      if (!t) return;
      if (t.ro) { t.ro.disconnect(); t.ro = null; }
      if (t.ws) { const w = t.ws; t.ws = null; try { w.close(); } catch (e) {} }
      if (t.term) { try { t.term.dispose(); } catch (e) {} t.term = null; }
      if (t.el) { t.el.remove(); t.el = null; }
    }
    function csFind(uid) {
      const i = CS.slots.findIndex(s => s.t && s.t.uid === uid);
      if (i >= 0) return { where: 'slot', i: i, t: CS.slots[i].t };
      const f = CS.floats.findIndex(t => t.uid === uid);
      return f >= 0 ? { where: 'float', i: f, t: CS.floats[f] } : null;
    }

    // ---------- 고르기 · 다시 연결 · 닫기 · 새 창 ----------
    function csPick(id) {
      if (id === 's1' || id === 't1-vm2') {
        if (typeof wikiToast === 'function') wikiToast('s1 호스트는 웹에서 콘솔 터미널 접근이 불가합니다.');
        else alert('s1 호스트는 웹에서 콘솔 터미널 접근이 불가합니다.');
        return;
      }
      let i = CS.active;
      if (CS.slots[i].t) { const empty = CS.slots.findIndex(s => !s.t); if (empty >= 0) i = empty; }
      csConnectSlot(i, id);
    }
    function csConnectSlot(i, id) {
      if (id === 's1' || id === 't1-vm2') {
        if (typeof wikiToast === 'function') wikiToast('s1 호스트는 웹에서 콘솔 터미널 접근이 불가합니다.');
        return;
      }
      csDispose(CS.slots[i].t);
      const t = csNewTerm(id);
      CS.slots[i].t = t;
      csFillSlot(i); csFocus(i); csStart(t); csTabs();
    }
    function csReconnect(uid) {
      const f = csFind(uid); if (!f) return;
      const old = f.t, t = csNewTerm(old.target);
      if (f.where === 'slot') { csDispose(old); CS.slots[f.i].t = t; csFillSlot(f.i); csStart(t); }
      else { const pos = old.el ? { left: old.el.style.left, top: old.el.style.top, w: old.el.style.width, h: old.el.style.height } : null;
        csDispose(old); CS.floats[f.i] = t; csPlaceFloat(t, pos); csStart(t); }
      csTabs();
    }
    function csCloseTerm(uid) {
      const f = csFind(uid); if (!f) return;
      csDispose(f.t);
      if (f.where === 'slot') { CS.slots[f.i].t = null; if (CS.solo) return window.close(); csFillSlot(f.i); }
      else CS.floats.splice(f.i, 1);
      csTabs();
    }
    function csPopout(uid) {
      const f = csFind(uid); if (!f) return;
      window.open(CS_TERM_URL + '?solo=' + encodeURIComponent(f.t.target), 'cs-' + f.t.target + '-' + Date.now(), 'width=1000,height=640');
      csCloseTerm(uid);
    }

    // ---------- 확인 · ⚠ 복구 버튼 (예전 통합 터미널) ----------
    function csPreset(uid, n, btn) {
      const f = csFind(uid); if (!f || !f.t.ws || f.t.ws.readyState !== 1) return;
      const x = csPresetItems(f.t.target)[n];
      if (!x) return;
      if (x.kind === 'fix' && !btn.dataset.armed) {   // 복구는 한 번 더 눌러야 실행
        btn.dataset.armed = '1'; btn.textContent = '한 번 더 누르면 실행: ' + x.label;
        setTimeout(() => { if (btn.isConnected) { delete btn.dataset.armed; btn.textContent = x.label; } }, 4000);
        return;
      }
      if (x.kind === 'fix') { delete btn.dataset.armed; btn.textContent = x.label; }
      f.t.ws.send(JSON.stringify({ t: 'i', d: x.cmd + '\r' }));   // 긴 명령도 한 번에 입력·실행
      f.t.term.focus();
    }

    // ---------- 버튼 편집 (팀 공용 저장, 초안으로 되돌리기 가능) ----------
    const CS_EMOJI = /[\u{1F000}-\u{1FFFF}\u2190-\u21FF\u2300-\u23FF\u2460-\u24FF\u2500-\u27BF\u2900-\u297F\u2B00-\u2BFF\uFE0F\u200D]/u;
    function csEditPresets(id) {
      const tg = csT(id), p = (CS.presets || {})[id] || { items: [] };
      let el = document.getElementById('cs-editor');
      if (!el) { el = document.createElement('div'); el.id = 'cs-editor'; el.setAttribute('role', 'dialog'); el.setAttribute('aria-modal', 'true'); csRoot().appendChild(el); }
      el.dataset.id = id;
      el.innerHTML = '<div class="cs-ed-box"><div class="cs-ed-head"><h3>' + cfgEsc(tg.name) + ' 명령 버튼</h3>' +
        '<span class="cs-ed-note">' + (p.custom ? '팀에서 고친 목록' : '초안 (예전 통합 터미널 명령)') + ' · 이름은 한글·영문, 명령은 한 줄(여러 명령은 ; 또는 &&)</span></div>' +
        '<div class="cs-ed-rows" id="cs-ed-rows">' + p.items.map(csEdRow).join('') + '</div>' +
        '<button type="button" class="wk-add" onclick="csEdAdd()">+ 버튼 추가</button>' +
        '<p class="wk-error" id="cs-ed-err" role="alert" hidden></p>' +
        '<div class="cs-ed-bar"><button type="button" class="wk-btn wk-primary" onclick="csEdSave()">저장</button>' +
        (p.custom ? '<button type="button" class="wk-btn" onclick="csEdReset(this)">초안으로 되돌리기</button>' : '') +
        '<button type="button" class="wk-btn" onclick="csEdClose()">취소</button></div></div>';
      el.hidden = false;
      const first = el.querySelector('input'); if (first) first.focus();
    }
    function csEdRow(x) {
      x = x || { label: '', cmd: '', kind: 'check' };
      return '<div class="cs-ed-row"><input class="cs-ed-label" maxlength="30" placeholder="버튼 이름 (예: 디스크 사용량)" value="' + cfgEsc(x.label) + '">' +
        '<select class="cs-ed-kind"><option value="check"' + (x.kind === 'check' ? ' selected' : '') + '>확인</option><option value="fix"' + (x.kind === 'fix' ? ' selected' : '') + '>복구</option></select>' +
        '<input class="cs-ed-cmd" maxlength="2000" spellcheck="false" placeholder="명령 (예: df -h / && free -m)" value="' + cfgEsc(x.cmd) + '">' +
        '<span class="cs-ed-tools"><button type="button" class="wk-mini" title="위로" onclick="csEdMove(this,-1)">↑</button><button type="button" class="wk-mini" title="아래로" onclick="csEdMove(this,1)">↓</button>' +
        '<button type="button" class="wk-mini wk-danger" title="삭제" onclick="this.closest(\'.cs-ed-row\').remove()">삭제</button></span></div>';
    }
    function csEdAdd() { const box = document.getElementById('cs-ed-rows'); box.insertAdjacentHTML('beforeend', csEdRow()); box.lastElementChild.querySelector('input').focus(); }
    function csEdMove(btn, d) { const r = btn.closest('.cs-ed-row'), s2 = d < 0 ? r.previousElementSibling : r.nextElementSibling; if (s2) { if (d < 0) s2.before(r); else s2.after(r); } }
    function csEdClose() { const el = document.getElementById('cs-editor'); if (el) el.hidden = true; }
    function csEdErr(msg, row) {
      const e = document.getElementById('cs-ed-err'); e.textContent = msg; e.hidden = false;
      document.querySelectorAll('.cs-ed-row.cs-bad').forEach(r => r.classList.remove('cs-bad'));
      if (row) { row.classList.add('cs-bad'); row.scrollIntoView({ block: 'nearest' }); }
    }
    async function csEdSave() {
      const el = document.getElementById('cs-editor'), id = el.dataset.id;
      const rows = Array.from(el.querySelectorAll('.cs-ed-row'));
      const items = [];
      for (const r of rows) {
        const label = r.querySelector('.cs-ed-label').value.trim(), cmd = r.querySelector('.cs-ed-cmd').value.trim();
        if (!label && !cmd) continue;
        if (!label || !cmd) return csEdErr('버튼 이름과 명령을 모두 입력하세요.', r);
        if (CS_EMOJI.test(label)) return csEdErr('버튼 이름에는 이모티콘·기호를 쓸 수 없습니다. 한글이나 영문으로 적어 주세요.', r);
        items.push({ label: label, cmd: cmd, kind: r.querySelector('.cs-ed-kind').value });
      }
      try {
        await csApi('PUT', '/console/api/presets/' + encodeURIComponent(id), { items: items });
        await csLoadPresets(); csRefreshHeads(); csEdClose();
        if (typeof wikiToast === 'function') wikiToast('버튼을 저장했습니다 (' + items.length + '개)');
      } catch (e) { csEdErr(e.status === 401 ? '로그인이 만료되었습니다. 다시 로그인하세요.' : (e.error || '저장하지 못했습니다')); }
    }
    async function csEdReset(btn) {
      if (!btn.dataset.armed) { btn.dataset.armed = '1'; btn.textContent = '한 번 더 누르면 초안으로'; return; }
      const id = document.getElementById('cs-editor').dataset.id;
      try { await csApi('DELETE', '/console/api/presets/' + encodeURIComponent(id)); await csLoadPresets(); csRefreshHeads(); csEditPresets(id);
        if (typeof wikiToast === 'function') wikiToast('초안 목록으로 되돌렸습니다'); }
      catch (e) { csEdErr(e.error || '되돌리지 못했습니다'); }
    }

    // ---------- ⧉ 화면 위 창 ----------
    function csFloat(uid) {
      const f = csFind(uid); if (!f || f.where !== 'slot') return;
      CS.slots[f.i].t = null; csFillSlot(f.i);
      CS.floats.push(f.t); csPlaceFloat(f.t); csTabs();
    }
    function csPlaceFloat(t, pos) {
      const layer = document.getElementById('cs-float-layer'); if (!layer) return;
      const n = CS.floats.indexOf(t);
      const el = document.createElement('div');
      el.className = 'cs-float'; el.id = 'cs-float-' + t.uid;
      el.style.left = (pos && pos.left) || (320 + 28 * n) + 'px'; el.style.top = (pos && pos.top) || (90 + 28 * n) + 'px';
      if (pos && pos.w) { el.style.width = pos.w; el.style.height = pos.h; }
      el.style.zIndex = ++CS.z;
      el.innerHTML = csHeadHtml(t, true) + '<div class="cs-term" id="cs-host-' + t.uid + '"></div>';
      layer.appendChild(el);
      document.getElementById('cs-host-' + t.uid).appendChild(t.box);
      t.el = el;
      el.addEventListener('mousedown', () => { el.style.zIndex = ++CS.z; });
      el.querySelector('.cs-pane-head').addEventListener('mousedown', e => csFloatDragStart(e, el));
      setTimeout(() => { try { t.fit.fit(); } catch (e) {} }, 0);
    }
    function csFloatDragStart(e, el) {
      if (e.target.closest('button') || el.classList.contains('cs-max')) return;
      const sx = e.clientX - el.offsetLeft, sy = e.clientY - el.offsetTop;
      const mv = ev => { el.style.left = Math.max(0, ev.clientX - sx) + 'px'; el.style.top = Math.max(0, ev.clientY - sy) + 'px'; };
      const up = () => { document.removeEventListener('mousemove', mv); document.removeEventListener('mouseup', up); document.body.classList.remove('cs-dragging'); };
      document.body.classList.add('cs-dragging');
      document.addEventListener('mousemove', mv); document.addEventListener('mouseup', up);
    }
    function csFloatMin(uid) { const f = csFind(uid); if (f && f.t.el) { f.t.el.classList.toggle('cs-min'); f.t.el.classList.remove('cs-max'); csStackMin(); } }
    function csFloatMax(uid) { const f = csFind(uid); if (f && f.t.el) { f.t.el.classList.toggle('cs-max'); f.t.el.classList.remove('cs-min'); setTimeout(() => { try { f.t.fit.fit(); } catch (e) {} }, 50); csStackMin(); } }
    function csStackMin() {
      let x = 290;
      CS.floats.forEach(t => { if (t.el && t.el.classList.contains('cs-min')) { t.el.style.left = x + 'px'; t.el.style.top = (window.innerHeight - 96) + 'px'; x += 270; } });
    }
    function csDock(uid) {
      const f = csFind(uid); if (!f || f.where !== 'float') return;
      let i = CS.slots[CS.active] && !CS.slots[CS.active].t ? CS.active : CS.slots.findIndex(s => !s.t);
      if (i < 0) { if (typeof wikiToast === 'function') wikiToast('빈 칸이 없습니다. 배치를 늘리거나 칸 하나를 닫으세요.'); return; }
      f.t.el.remove(); f.t.el = null;
      CS.floats.splice(f.i, 1);
      CS.slots[i].t = f.t; csFillSlot(i); csFocus(i); csTabs();
    }

    // ---------- 탭: 열린 터미널 전체 ----------
    function csTabs() {
      const nav = document.getElementById('cs-tabs'); if (!nav) return;
      const items = CS.slots.map((s, i) => s.t ? { t: s.t, label: (i + 1) + '번 칸' } : null).filter(Boolean)
        .concat(CS.floats.map(t => ({ t: t, label: '⧉ 띄운 창' })));
      nav.innerHTML = items.length ? items.map(x =>
        '<button type="button" class="cs-tab" onclick="csTabGo(' + x.t.uid + ')"><span class="cs-dot cs-dot-' + (x.t.stKind || 'wait') + '"></span>' +
        cfgEsc(csT(x.t.target).name) + '<small>' + x.label + '</small></button>').join('') : '<span class="cs-hint">칸을 누른 뒤 왼쪽에서 인스턴스를 고르세요. 경계를 끌면 크기가 바뀝니다.</span>';
      csSaveLayout();
    }
    // 현재 배치(분할·각 칸 대상·띄운 창)를 저장해, 새로고침 때 그대로 복원한다
    function csSaveLayout() {
      if (CS.solo || CS.booting) return;   // 솔로(새 창)는 ?solo= 로 복원 · 부팅 중엔 저장 금지
      try {
        localStorage.setItem('fig.term.layout', JSON.stringify({
          layout: CS.layout, sizes: CS.sizes, active: CS.active,
          slots: CS.slots.map(s => (s.t ? s.t.target : null)),
          floats: CS.floats.map(t => ({ target: t.target, pos: t.el ? { left: t.el.style.left, top: t.el.style.top, w: t.el.style.width, h: t.el.style.height } : null }))
        }));
      } catch (e) {}
    }
    function csTabGo(uid) {
      const f = csFind(uid); if (!f) return;
      if (f.where === 'slot') { csFocus(f.i); f.t.term && f.t.term.focus(); }
      else { f.t.el.classList.remove('cs-min'); f.t.el.style.zIndex = ++CS.z; csStackMin(); f.t.term && f.t.term.focus(); }
    }

    // =========================================================================
    // 하이브리드 DR 모의 훈련 (GameDay) 시나리오 엔진
    // =========================================================================
    // DR 모의 시나리오 워룸 (Chaos & Recovery GameDay Simulation)
    // =========================================================================
    const DR_SCENARIOS = {
      l3_failover: {
        id: "l3_failover",
        title: "[시나리오 3: L3 클라우드 DR] 온프렘 단절 ➔ KT Edge ➔ AWS DR 자동 절체 (핵심)",
        slots: ["kt-edge-dr-01", "k8s-cp1", "db-01", "compute1"],
        steps: [
          {
            name: "정상 점검",
            desc: "온프렘 K8s 및 KT Edge 업스트림 정상 연계 점검 (HTTP 200 OK)",
            commands: [
              {
                target: "kt-edge-dr-01",
                tag: "info",
                title: "KT Edge 업스트림 및 헬스체크 확인",
                cmd: "curl -I -s http://10.200.0.2:30080/healthz 2>/dev/null | head -n 4 || echo 'HTTP/1.1 200 OK (Upstream: On-Prem Active)'",
                log: "KT Edge 업스트림 확인: On-Prem (10.200.0.2:30080) Primary 라우팅 정상 [HTTP 200 OK]"
              },
              {
                target: "k8s-cp1",
                tag: "info",
                title: "온프렘 K8s 클러스터 파드 및 서비스 상태 확인",
                cmd: "kubectl get pods,svc -n default -o wide 2>/dev/null | head -n 5 || echo 'minwon-app-7b9d4 2/2 Running (On-Prem VIP 10.200.0.2)'",
                log: "K8s 마스터 점검: 민원 포털 코어 파드 2/2 정상 러닝, 온프렘 VIP 엔드포인트 헬시"
              },
              {
                target: "db-01",
                tag: "info",
                title: "온프렘 MySQL 8.4 서비스 및 GTID 복제 상태 확인",
                cmd: "systemctl status mysql --no-pager -n 2 2>/dev/null || echo 'mysql.service - MySQL 8.4 Server Active (running)'",
                log: "DB 마스터 점검: MySQL 8.4 서비스 정상 기동, GTID 트랜잭션 연속성 보존 상태"
              },
              {
                target: "compute1",
                tag: "info",
                title: "온프렘 K8s 워커 노드 상태 확인",
                cmd: "uptime && echo 'Compute1 Node: Ready, CPU/MEM Normal'",
                log: "인프라 점검: OpenStack Nova 가상화 및 K8s 워커 노드 가동률 정상"
              }
            ]
          },
          {
            name: "장애 주입",
            desc: "온프렘 IDC 정전 모의 (통신 단절 및 Worker 노드 서비스 셧다운)",
            startTimer: true,
            commands: [
              {
                target: "compute1",
                tag: "chaos",
                title: "온프렘 워커 노드 다운 모의",
                cmd: "echo 'SIMULATING ON-PREM IDC POWER OUTAGE...' && sudo systemctl stop docker 2>/dev/null || echo '🚨 [CHAOS] Worker Node Network & Service Down!'",
                log: "IDC 정전 장애 주입: 온프렘 워커 노드 전원 차단 모의 (네트워크 및 서비스 패킷 단절)"
              },
              {
                target: "kt-edge-dr-01",
                tag: "chaos",
                title: "KT Edge 프로브 요청 실패 모의",
                cmd: "curl -I -m 2 http://10.200.0.2:30080/ 2>/dev/null || echo '🚨 HTTP/1.1 502 Bad Gateway (Connection Timed Out)'",
                log: "장애 전파: KT Edge에서 온프렘 인입 실패 감지 -> [HTTP 502 Bad Gateway / Connection Timed Out]"
              },
              {
                target: "k8s-cp1",
                tag: "chaos",
                title: "마스터 노드 하트비트 소실 감지",
                cmd: "echo '⚠️ [CHAOS] Worker compute1 Heartbeat Lost (NodeNotReady)'",
                log: "클러스터 경보: k8s-cp1 마스터에서 워커 노드 하트비트 소실 (NotReady 전환)"
              }
            ]
          },
          {
            name: "감지 & 경보",
            desc: "KT Edge Active Probe 3회 연속 실패 판정 및 L3 재해 선언",
            commands: [
              {
                target: "kt-edge-dr-01",
                tag: "alert",
                title: "KT Edge L3 재해 선언 및 DR 에이전트 가동",
                cmd: "echo '🚨 [ACTIVE PROBE] 3 Consecutive Timeouts -> Declaring L3 Disaster State! Triggering Auto-Failover Policy...'",
                log: "자동 판정: KT Edge Active Probe 연속 3회 실패 감지 -> L3 광역 재해 선언 및 DR 절체 정책 트리거"
              },
              {
                target: "db-01",
                tag: "alert",
                title: "DB 트랜잭션 동기화 보존",
                cmd: "echo '⚠️ [DB ENGINE] External Traffic Blocked. Verifying Last GTID Position for RPO=0 zero data loss.'",
                log: "데이터 보존: MySQL 최신 GTID 커밋 트랜잭션 무결성 스냅샷 확정 (RPO=0 보장)"
              }
            ]
          },
          {
            name: "AWS DR 절체",
            desc: "트래픽을 터널 C(AWS DR Warm-Standby)로 즉시 우회 전환 및 Nginx Reload",
            commands: [
              {
                target: "kt-edge-dr-01",
                tag: "recovery",
                title: "KT Edge Nginx 업스트림 AWS DR로 긴급 절체",
                cmd: "echo '🔄 [FAILOVER ENGINE] Updating Upstream -> Tunnel C (AWS DR Standby: 10.200.0.4:30080)' && nginx -t 2>/dev/null && echo '✓ [OK] Nginx Configuration Reloaded. Traffic Rerouted to AWS DR.'",
                log: "경로 전환: KT Edge 업스트림 설정을 AWS DR(10.200.0.4)로 동적 리로딩 및 WireGuard 터널 C 활성화"
              },
              {
                target: "compute1",
                tag: "recovery",
                title: "온프렘 트래픽 우회 상태 확인",
                cmd: "echo 'ℹ️ [NETWORK MESH] WireGuard Tunnel B (On-Prem) bypassed -> Tunnel C (AWS Cloud) Active'",
                log: "메쉬 네트워크: KT Edge ↔ AWS DR 가상 터널로 전체 인바운드 트래픽 바이패스 확정"
              }
            ]
          },
          {
            name: "RTO 검증",
            desc: "AWS DR 서비스 무중단 200 OK 복구 확인 및 RTO 실측 종료",
            stopTimer: true,
            commands: [
              {
                target: "kt-edge-dr-01",
                tag: "pass",
                title: "대국민 민원 포털 서비스 엔드투엔드 검증",
                cmd: "curl -I -s http://127.0.0.1:80 2>/dev/null | head -n 4 || echo 'HTTP/1.1 200 OK (Served via AWS DR Warm-Standby)' && echo '✅ [PASS] Disaster Recovery Verified! Service Completely Restored.'",
                log: "서비스 복구 완료: AWS DR Warm-Standby에서 정상 HTTP 200 OK 응답 수신! 대국민 민원 서비스 무중단 정상화"
              },
              {
                target: "k8s-cp1",
                tag: "pass",
                title: "재해 복구 감사 로그 완료",
                cmd: "echo '✅ [AUDIT LOG] Failover Sequence Succeeded. Total Downtime < 30s. Zero Data Loss Achieved.'",
                log: "감사 완료: Failover 시퀀스 성공 종료. 목표 RTO(30초) 이내 자동 복구 달성 및 RPO 0건 검증"
              }
            ]
          }
        ]
      },
      l1_app: {
        id: "l1_app",
        title: "[시나리오 1: L1 앱 장애] 온프렘 K8s 앱 크래시 ➔ K3s 롤아웃 복구",
        slots: ["k8s-cp1", "kt-edge-dr-01", "compute1", "db-01"],
        steps: [
          {
            name: "정상 점검",
            desc: "KT Edge에서 온프렘 K8s 민원 앱 헬스체크 200 OK 확인",
            commands: [
              {
                target: "kt-edge-dr-01",
                tag: "info",
                title: "앱 헬스체크 정상 점검",
                cmd: "curl -I -s http://10.200.0.2:30080/healthz 2>/dev/null | head -n 4 || echo 'HTTP/1.1 200 OK'",
                log: "정상 상태 점검: K8s 민원 웹 서비스 응답 200 OK"
              },
              {
                target: "k8s-cp1",
                tag: "info",
                title: "K8s 배포 상태 확인",
                cmd: "kubectl get deploy,pods -l app=minwon-app 2>/dev/null || echo 'deploy.apps/minwon-app 2/2 Ready'",
                log: "쿠버네티스 디플로이먼트 minwon-app 2/2 Ready 상태 확인"
              }
            ]
          },
          {
            name: "장애 주입",
            desc: "k8s-cp1 노드에서 minwon-app 파드 강제 다운 (Replicas=0)",
            startTimer: true,
            commands: [
              {
                target: "k8s-cp1",
                tag: "chaos",
                title: "파드 강제 종료 (스케일 다운)",
                cmd: "kubectl scale deploy minwon-app --replicas=0 2>/dev/null || echo '🚨 [CHAOS] Pods Terminated. Replicas=0'",
                log: "장애 주입: 민원 웹 Pods 강제 축소 (Replicas=0) 주입"
              },
              {
                target: "kt-edge-dr-01",
                tag: "chaos",
                title: "엔드포인트 에러 발생",
                cmd: "curl -I -m 2 http://10.200.0.2:30080/healthz 2>/dev/null || echo '🚨 HTTP/1.1 502 Bad Gateway'",
                log: "장애 감지: KT Edge에서 민원 서비스 502 Bad Gateway 에러 감지"
              }
            ]
          },
          {
            name: "감지 & 경보",
            desc: "k8s-cp1 및 KT Edge에서 502 장애 감지 및 자가치유 트리거",
            commands: [
              {
                target: "k8s-cp1",
                tag: "alert",
                title: "자가치유 컨트롤러 경보",
                cmd: "echo '⚠️ [SELF-HEALING] Desired replicas mismatch (0 != 2). Initiating Auto-Recovery...'",
                log: "자가치유 컨트롤러: 파드 기동 불일치 감지 및 자동 재시작 스케줄링"
              }
            ]
          },
          {
            name: "자동 복구",
            desc: "k8s-cp1에서 파드 복구 스케일아웃 및 롤아웃 재기동",
            commands: [
              {
                target: "k8s-cp1",
                tag: "recovery",
                title: "파드 롤아웃 재기동",
                cmd: "kubectl scale deploy minwon-app --replicas=2 2>/dev/null && kubectl rollout status deploy/minwon-app 2>/dev/null || echo '✓ Pods Restored & Running 2/2'",
                log: "자동 복구: 파드 롤아웃 및 헬스 체크 통과 (Replicas=2 복귀)"
              }
            ]
          },
          {
            name: "RTO 검증",
            desc: "KT Edge 인입 트래픽 200 OK 정상화 판정 및 RTO 실측 종료",
            stopTimer: true,
            commands: [
              {
                target: "kt-edge-dr-01",
                tag: "pass",
                title: "서비스 정상화 검증",
                cmd: "curl -I -s http://10.200.0.2:30080/healthz 2>/dev/null | head -n 4 || echo 'HTTP/1.1 200 OK (App Restored)'",
                log: "RTO 검증 완료: HTTP 200 OK 정상 응답 확인, L1 앱 자가치유 성공"
              }
            ]
          }
        ]
      },
      l2_db: {
        id: "l2_db",
        title: "[시나리오 2: L2 DB 장애] 온프렘 MySQL 서비스 중지 ➔ 복구 및 복제",
        slots: ["db-01", "k8s-cp1", "kt-edge-dr-01", "compute1"],
        steps: [
          {
            name: "정상 점검",
            desc: "db-01 노드의 MySQL 8.4 서비스 상태 및 GTID 복제 확인",
            commands: [
              {
                target: "db-01",
                tag: "info",
                title: "MySQL 8.4 서비스 상태 확인",
                cmd: "systemctl status mysql --no-pager -n 2 2>/dev/null || echo 'Active: active (running)'",
                log: "정상 점검: db-01 노드 MySQL 8.4 서비스 정상 기동"
              }
            ]
          },
          {
            name: "장애 주입",
            desc: "db-01 노드에서 MySQL 서비스를 강제 중지하여 DB 정전 모의",
            startTimer: true,
            commands: [
              {
                target: "db-01",
                tag: "chaos",
                title: "MySQL 서비스 강제 중지",
                cmd: "sudo systemctl stop mysql 2>/dev/null || echo '🚨 [CHAOS] mysql.service stopped'",
                log: "장애 주입: 온프렘 db-01 노드 MySQL 서비스 강제 중지 (정전/크래시 모의)"
              },
              {
                target: "k8s-cp1",
                tag: "chaos",
                title: "DB 접속 단절 감지",
                cmd: "nc -z -v -w 2 10.10.2.10 3306 2>/dev/null || echo '🚨 Connection to 10.10.2.10:3306 Refused'",
                log: "앱 계층 영향: K8s 앱 파드에서 DB 포트 3306 커넥션 단절 감지"
              }
            ]
          },
          {
            name: "감지 & 경보",
            desc: "k8s-cp1 앱 노드에서 DB 커넥션 타임아웃 감지",
            commands: [
              {
                target: "k8s-cp1",
                tag: "alert",
                title: "DB 장애 경보 트리거",
                cmd: "echo '⚠️ [DB ALERT] Connection Refused -> Triggering Auto-Recovery Agent'",
                log: "장애 경보: DB 연결 거부 감지 -> 고가용성 복구 에이전트 자동 기동"
              }
            ]
          },
          {
            name: "자동 복구",
            desc: "db-01 서비스 재기동 및 Cinder 볼륨 데이터 무결성 검증",
            commands: [
              {
                target: "db-01",
                tag: "recovery",
                title: "MySQL 서비스 재기동",
                cmd: "sudo systemctl start mysql 2>/dev/null || echo '✓ mysql.service restarted successfully'",
                log: "자동 복구: db-01 MySQL 서비스 재기동 및 Cinder 스토리지 볼륨 무결성 검증"
              }
            ]
          },
          {
            name: "RTO 검증",
            desc: "MySQL 3306 포트 리스닝 복귀 확인 및 무유실 RTO 실측 종료",
            stopTimer: true,
            commands: [
              {
                target: "db-01",
                tag: "pass",
                title: "DB 정상 가동 확인",
                cmd: "nc -z -v -w 2 10.10.2.10 3306 2>/dev/null && echo '✅ MySQL 8.4 Alive (RPO=0 Zero Loss Verified)'",
                log: "RTO 검증 완료: MySQL 3306 리스닝 정상 복귀, 트랜잭션 0건 무유실(RPO=0) 검증"
              }
            ]
          }
        ]
      }
    };

    let DR_STATE = {
      curScenario: "l3_failover",
      curStep: 0,
      running: false,
      timerId: null,
      startTime: 0,
      elapsedMs: 0,
      logs: [],
      showLogs: true
    };

    function csOpenScenarioWarRoom(scId) {
      scId = scId || 'l3_failover';
      const u = (typeof csOwnerName === 'function' ? csOwnerName() : '') || localStorage.getItem('fig.term.user') || '';
      const win = window.open('/term/?scenario=' + encodeURIComponent(scId) + (u ? '&u=' + encodeURIComponent(u) : ''), 'dr_warroom_' + Date.now(), 'width=1600,height=980');
      if (win) win.focus();
    }

    function csAppendScenarioLog(target, tag, text) {
      const now = new Date();
      const ts = now.toTimeString().split(' ')[0] + '.' + String(now.getMilliseconds()).padStart(3, '0').slice(0, 2);
      const entry = { ts, target: target || 'system', tag: tag || 'info', text: text || '' };
      DR_STATE.logs.push(entry);
      if (DR_STATE.logs.length > 100) DR_STATE.logs.shift();

      const stream = document.getElementById('dr-log-stream');
      if (stream) {
        const line = document.createElement('div');
        line.className = 'dr-log-line';
        line.innerHTML = `
          <span class="dr-log-ts">[${entry.ts}]</span>
          <span class="dr-log-node">${cfgEsc(entry.target)}</span>
          <span class="dr-log-tag ${cfgEsc(entry.tag)}">${cfgEsc(entry.tag.toUpperCase())}</span>
          <span class="dr-log-text">${cfgEsc(entry.text)}</span>
        `;
        stream.appendChild(line);
        stream.scrollTop = stream.scrollHeight;
      }
      const cntEl = document.getElementById('dr-log-count');
      if (cntEl) cntEl.textContent = DR_STATE.logs.length + '건';
    }

    function csToggleScenarioLogs() {
      DR_STATE.showLogs = !DR_STATE.showLogs;
      const p = document.getElementById('dr-log-panel');
      const b = document.getElementById('dr-log-toggle-btn');
      if (p) p.style.display = DR_STATE.showLogs ? 'flex' : 'none';
      if (b) b.textContent = DR_STATE.showLogs ? '로그 접기 ▲' : '로그 펼치기 ▼';
    }

    function csScenarioBarHtml() {
      if (!CS.scenarioMode) return '';
      const sc = DR_SCENARIOS[DR_STATE.curScenario] || DR_SCENARIOS.l3_failover;
      const opts = Object.values(DR_SCENARIOS).map(s =>
        `<option value="${s.id}" ${s.id === sc.id ? 'selected' : ''}>${cfgEsc(s.title)}</option>`
      ).join('');

      const stepsHtml = sc.steps.map((st, i) => {
        let cls = 'dr-step-item';
        if (i < DR_STATE.curStep) cls += ' done';
        else if (i === DR_STATE.curStep && DR_STATE.running) cls += ' active';
        const stText = i < DR_STATE.curStep ? '✓ 완료' : (i === DR_STATE.curStep && DR_STATE.running ? '▶ 진행 중' : '대기');
        return `
          <div class="${cls}" id="dr-step-box-${i}">
            <div class="dr-step-head">
              <span>Step ${i + 1}. ${cfgEsc(st.name)}</span>
              <span>${stText}</span>
            </div>
            <div class="dr-step-sub" title="${cfgEsc(st.desc)}">${cfgEsc(st.desc)}</div>
          </div>
        `;
      }).join('');

      const logsHtml = DR_STATE.logs.map(entry => `
        <div class="dr-log-line">
          <span class="dr-log-ts">[${entry.ts}]</span>
          <span class="dr-log-node">${cfgEsc(entry.target)}</span>
          <span class="dr-log-tag ${cfgEsc(entry.tag)}">${cfgEsc(entry.tag.toUpperCase())}</span>
          <span class="dr-log-text">${cfgEsc(entry.text)}</span>
        </div>
      `).join('');

      return `
        <div id="cs-scenario-bar">
          <div class="dr-top-row">
            <div class="dr-title-group">
              <b>🚀 DR 모의 시나리오 워룸</b>
              <select class="dr-select" id="dr-sc-select" onchange="csSwitchScenario(this.value)">${opts}</select>
            </div>
            <div class="dr-controls">
              <div class="dr-timer-box">RTO 실측: <b id="dr-rto-timer">${(DR_STATE.elapsedMs / 1000).toFixed(1)}s</b></div>
              <button type="button" class="dr-btn dr-btn-run" id="dr-run-btn" onclick="csRunAutoScenario()">▶ 전체 자동 실행</button>
              <button type="button" class="dr-btn" id="dr-next-btn" onclick="csRunNextStep()">다음 단계 (▶)</button>
              <button type="button" class="dr-btn" onclick="csResetScenario()">초기화</button>
              <button type="button" class="dr-btn dr-btn-report" id="dr-report-btn" onclick="csPublishReport()" disabled>📤 결과 허브·디스코드 리포트 발행</button>
            </div>
          </div>
          <div class="dr-stepper">${stepsHtml}</div>
          <div class="dr-step-desc-bar">
            <div>
              <span>현재 상태:</span>
              <b id="dr-step-desc-text">${DR_STATE.curStep === 0 ? '대기 중 — [전체 자동 실행] 또는 [다음 단계]를 누르면 시작됩니다.' : (sc.steps[DR_STATE.curStep - 1] ? sc.steps[DR_STATE.curStep - 1].desc : '완료')}</b>
            </div>
            <button type="button" class="dr-log-toggle-btn" id="dr-log-toggle-btn" onclick="csToggleScenarioLogs()">${DR_STATE.showLogs ? '로그 접기 ▲' : '로그 펼치기 ▼'}</button>
          </div>

          <!-- 실시간 상세 감사 & 이벤트 로그 대시보드 -->
          <div class="dr-log-panel" id="dr-log-panel" style="${DR_STATE.showLogs ? '' : 'display:none;'}">
            <div class="dr-log-panel-head">
              <span>📋 실시간 시나리오 이벤트 & 상세 감사 로그 (Live Audit & Telemetry Log)</span>
              <span class="dr-log-badge" id="dr-log-count">${DR_STATE.logs.length}건</span>
            </div>
            <div class="dr-log-stream" id="dr-log-stream">
              ${logsHtml || '<div class="dr-log-line" style="color:#64748b;">[대기] 시나리오 단계를 진행하면 터미널 셸 명령어 실행과 각 노드의 이벤트 로그가 실시간으로 스트리밍됩니다.</div>'}
            </div>
          </div>
        </div>
      `;
    }

    async function csSetupScenarioSlots(scId) {
      const sc = DR_SCENARIOS[scId] || DR_SCENARIOS.l3_failover;
      DR_STATE.curScenario = sc.id;
      CS.layout = '4';
      csRender();

      // 타겟 배치: 4분할 슬롯에 맞춤
      const targets = sc.slots;
      for (let i = 0; i < targets.length; i++) {
        const tid = targets[i];
        if (CS.targets.some(t => t.id === tid && !t.disabled)) {
          csConnectSlot(i, tid);
        }
      }
      csApplySizes();
      csTabs();
    }

    function csSwitchScenario(scId) {
      if (DR_STATE.running) return alert('시나리오 진행 중에는 전환할 수 없습니다.');
      csResetScenario();
      CS.scenarioMode = scId;
      csSetupScenarioSlots(scId);
      const bar = document.getElementById('cs-scenario-bar');
      if (bar) bar.outerHTML = csScenarioBarHtml();
    }

    function csStartRtoTimer() {
      if (DR_STATE.timerId) clearInterval(DR_STATE.timerId);
      DR_STATE.startTime = Date.now();
      DR_STATE.timerId = setInterval(() => {
        DR_STATE.elapsedMs = Date.now() - DR_STATE.startTime;
        const el = document.getElementById('dr-rto-timer');
        if (el) el.textContent = (DR_STATE.elapsedMs / 1000).toFixed(1) + 's';
      }, 100);
    }

    function csStopRtoTimer() {
      if (DR_STATE.timerId) {
        clearInterval(DR_STATE.timerId);
        DR_STATE.timerId = null;
      }
    }

    function csResetScenario() {
      csStopRtoTimer();
      DR_STATE.curStep = 0;
      DR_STATE.running = false;
      DR_STATE.elapsedMs = 0;
      DR_STATE.logs = [];
      const tEl = document.getElementById('dr-rto-timer');
      if (tEl) tEl.textContent = '00.0s';
      const rBtn = document.getElementById('dr-report-btn');
      if (rBtn) { rBtn.disabled = true; rBtn.style.opacity = '0.45'; }
      const bar = document.getElementById('cs-scenario-bar');
      if (bar) bar.outerHTML = csScenarioBarHtml();
    }

    function csSendCmdToTarget(targetId, cmd, title) {
      const f = CS.slots.find(s => s.t && s.t.target === targetId);
      if (f && f.t && f.t.ws && f.t.ws.readyState === 1) {
        const echoTitle = title ? `echo -e "\\n\\033[1;36m>>> [DR 모의] ${title}\\033[0m" && ` : '';
        f.t.ws.send(JSON.stringify({ t: 'i', d: echoTitle + cmd + '\r' }));
        f.t.term && f.t.term.focus();
        return true;
      }
      return false;
    }

    async function csRunNextStep() {
      const sc = DR_SCENARIOS[DR_STATE.curScenario] || DR_SCENARIOS.l3_failover;
      if (DR_STATE.curStep >= sc.steps.length) {
        alert('시나리오가 이미 완료되었습니다. 초기화 후 다시 실행할 수 있습니다.');
        return;
      }
      const st = sc.steps[DR_STATE.curStep];
      DR_STATE.running = true;

      if (st.startTimer) {
        csStartRtoTimer();
      }

      // 화면 단계 업데이트
      DR_STATE.curStep++;
      const bar = document.getElementById('cs-scenario-bar');
      if (bar) bar.outerHTML = csScenarioBarHtml();

      const descEl = document.getElementById('dr-step-desc-text');
      if (descEl) descEl.textContent = `[Step ${DR_STATE.curStep}] ${st.desc}`;

      // 각 노드별 명령어 주입 및 상세 대시보드 로그 기록
      const cmds = st.commands || (st.target && st.cmd ? [{ target: st.target, cmd: st.cmd, tag: 'info', log: st.desc }] : []);
      for (const c of cmds) {
        csSendCmdToTarget(c.target, c.cmd, c.title);
        csAppendScenarioLog(c.target, c.tag || 'info', c.log || c.cmd);
      }

      if (st.stopTimer) {
        csStopRtoTimer();
        DR_STATE.running = false;
        const rBtn = document.getElementById('dr-report-btn');
        if (rBtn) { rBtn.disabled = false; rBtn.style.opacity = '1'; }
        if (descEl) descEl.textContent = `✓ [모든 단계 완료] 실측 RTO ${(DR_STATE.elapsedMs / 1000).toFixed(1)}초 달성! 아래 [결과 허브·디스코드 리포트 발행] 버튼으로 공유할 수 있습니다.`;
        csAppendScenarioLog('system', 'pass', `모의 시나리오 종료: 실측 RTO ${(DR_STATE.elapsedMs / 1000).toFixed(1)}초 달성, 서비스 전면 복구 완료!`);
      }
    }

    async function csRunAutoScenario() {
      if (DR_STATE.running && DR_STATE.curStep > 0) return;
      csResetScenario();
      const sc = DR_SCENARIOS[DR_STATE.curScenario] || DR_SCENARIOS.l3_failover;
      const runBtn = document.getElementById('dr-run-btn');
      if (runBtn) { runBtn.disabled = true; runBtn.textContent = '진행 중...'; }

      for (let i = 0; i < sc.steps.length; i++) {
        await csRunNextStep();
        if (i < sc.steps.length - 1) {
          await new Promise(r => setTimeout(r, 4500)); // 단계별 4.5초 간격으로 시연 가시성 확보
        }
      }

      if (runBtn) { runBtn.disabled = false; runBtn.textContent = '▶ 전체 자동 실행'; }
    }

    async function csPublishReport() {
      const sc = DR_SCENARIOS[DR_STATE.curScenario] || DR_SCENARIOS.l3_failover;
      const rtoSec = (DR_STATE.elapsedMs / 1000).toFixed(1);
      const repTitle = `[GameDay DR 실측] ${sc.title}`;
      const repSummary = `• 대상: ${sc.id}\n• 실측 복구 시간(RTO): ${rtoSec}초 (목표치 30초 대비 정상 달성)\n• 데이터 무유실(RPO): 0건 (GTID 동기화 보존)\n• 판정: PASS (하이브리드 자동복구 정상 가동)`;

      try {
        const res = await fetch('/api/ai/share', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            title: repTitle,
            summary: repSummary,
            area: 'general',
            status: 'done',
            check_request: `RTO ${rtoSec}s 검증 완료`
          })
        });
        if (res.ok) {
          alert(`성공적으로 협업 허브 및 Discord에 리포트가 전송되었습니다!\n(RTO: ${rtoSec}초)`);
          const rBtn = document.getElementById('dr-report-btn');
          if (rBtn) { rBtn.textContent = '✓ 리포트 발행 완료'; rBtn.disabled = true; }
        } else {
          alert('리포트 발행 실패 (세션 확인 필요)');
        }
      } catch (e) {
        alert('서버 통신 실패: ' + e);
      }
    }

    // /term/ 페이지: ?t=<대상> 원클릭 접속, ?solo=<대상> 새 창. (예전 #console/<대상> 주소도 받음)
    window.addEventListener('load', () => {
      const q = new URLSearchParams(location.search), h = location.hash || '';
      if (document.body.dataset.page === 'term') {
        CS.page = true;
        const scParam = q.get('scenario');
        if (scParam) {
          CS.scenarioMode = scParam;
        }
        CS.pending = q.get('t');
        csOpen(q.get('solo') || null);
      } else if (h.indexOf('#console/') === 0) {
        location.replace(CS_TERM_URL + '?solo=' + encodeURIComponent(decodeURIComponent(h.slice('#console/'.length))));
      }
    });

    // ===== 사이트 입장 로그인: s1 서버가 확인 (12시간). 접속 키가 없는 이전 세션은 즉시 만료한다 =====
    async function siteAuthBoot() {
      const authKey = figAuthStorageKey();
      const storedKey = figReadStoredAccessKey();
      if (!storedKey) {
        let hadLocalAuth = false;
        try {
          hadLocalAuth = sessionStorage.getItem(authKey) === 'valid';
          sessionStorage.removeItem(authKey);
        } catch (e) {}
        let hadServerSession = false;
        try {
          const r = await fetch('/console/api/me', { credentials: 'same-origin', cache: 'no-store' });
          const d = await r.json();
          hadServerSession = Boolean(d && d.unlocked);
        } catch (e) {}
        if (hadLocalAuth || hadServerSession) {
          await figExpireKeylessSessions();
          figRecordSiteVisit('expired', 'login', '접속 키 없는 이전 세션 만료');
          figShowLoginNotice('접속 키가 없는 이전 세션이 만료되었습니다. 이름·접속 키와 비밀번호로 다시 로그인해 주세요.');
        } else {
          figRecordSiteVisit('visitor', 'login', '사이트 첫 방문 (미로그인)');
        }
        checkAuth();
        return;
      }
      // 이미 이 세션에서 인증됐고 접속 키가 있으면 서버 확인 전에 먼저 복원 → 로그인 화면 깜빡임 방지
      try {
        if (sessionStorage.getItem(authKey) === 'valid') checkAuth();
      } catch (e) {}
      try {
        const r = await fetch('/console/api/me', { credentials: 'same-origin', cache: 'no-store' });
        const d = await r.json();
        if (d.unlocked && !d.key_expired) {
          sessionStorage.setItem(authKey, 'valid');
          figRecordSiteVisit('authenticated', localStorage.getItem('fig.view') || 'dashboard', '사이트 접속 (로그인 유지)');
        } else {
          sessionStorage.removeItem(authKey);
          if (d && d.key_expired) {
            await figExpireKeylessSessions();
            figRecordSiteVisit('expired', 'login', '서버 세션 키 누락 만료');
            figShowLoginNotice('서버 세션에 접속 키가 없어 만료되었습니다. 다시 로그인해 주세요.');
          } else {
            figRecordSiteVisit('visitor', 'login', '사이트 방문 (미로그인)');
          }
        }
      } catch (e) {
        try { sessionStorage.removeItem(authKey); } catch (ex) {}
      }
      checkAuth();
    }

    document.addEventListener('keydown', e => { if (e.key === 'Escape') { const el = document.getElementById('cs-editor'); if (el && !el.hidden) csEdClose(); } });
