    // ===== 통합 콘솔: 3대 영역 → 인스턴스 → 실제 터미널 (content/console.js) =====
    // 서버: s1 figteam-console (/console/api/*, /console/ws/<대상>) · 콘솔 비밀번호로 잠금
    // 예전 통합 터미널 기능: 대상별 「확인」·「⚠ 복구」 버튼, 탭, ⧉ 화면 위 창(끌기·크기·최소화·최대화·되돌리기), ↗ 새 창
    const CS = { open: false, solo: null, targets: null, layout: '1', slots: [], floats: [], active: 0, loaded: false,
      sizes: { col: 50, row: 50 }, seq: 0, z: 900, pending: null, page: false, status: null, owner: "", expanded: {}, openNow: {}, stTimer: null, presets: {} };
    const CS_TERM_URL = '/term/';
    // 대시보드에서: 통합 터미널 페이지로 이동 (원클릭 — 대상이 있으면 바로 접속)
    function csGo(id) { location.href = CS_TERM_URL + (id ? '?t=' + encodeURIComponent(id) : ''); }
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
        const mine = CS.targets.filter(t => g[2].indexOf(t.area) >= 0);
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

    // ---------- 사용자 이름(세션 이어가기 열쇠) ----------
    function csOwnerName() { try { return CS.owner || localStorage.getItem('fig.term.user') || ''; } catch (e) { return CS.owner || ''; } }
    function csOwner(force) {
      let n = '';
      try { n = localStorage.getItem('fig.term.user') || ''; } catch (e) {}
      if (!n || force) {
        const v = (window.prompt('터미널 사용자 이름을 넣어 주세요.\n이 이름으로 세션이 저장돼, 새로고침해도 이어집니다.', n) || '').trim();
        if (v) { n = v; try { localStorage.setItem('fig.term.user', n); } catch (e) {} }
      }
      CS.owner = n || 'guest';
      const chip = document.getElementById('cs-owner-chip');
      if (chip) chip.textContent = CS.owner;
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
      const root = csRoot();
      if (CS.targets && root.querySelector('.cs-wrap') && !soloId) {   // 다른 화면에 갔다 와도 열린 터미널은 그대로
        root.hidden = false; document.body.classList.add('cs-on'); CS.open = true;
        csApplySizes(); csLoadStatus();
        if (CS.pending) { const id = CS.pending; CS.pending = null; csPick(id); }
        return;
      }
      CS.open = true; CS.solo = soloId || null;
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
      if (!CS.stTimer) CS.stTimer = setInterval(() => { if (CS.open && !csRoot().hidden) csLoadStatus(); }, 20000);
      if (CS.solo && !CS.slots[0].t) csConnectSlot(0, CS.solo);
      else if (CS.pending) { const id = CS.pending; CS.pending = null; if (CS.targets.some(t => t.id === id && !t.disabled)) csPick(id); }
      else await csResume();   // 새로고침·재진입 시 이 이름의 살아 있는 세션을 자동으로 다시 붙인다
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
      csRoot().innerHTML =
        '<div class="cs-unlock"><form class="wk-card" onsubmit="csUnlock(event)"><h3>통합 콘솔 잠금 해제</h3>' +
        '<p class="manual-desc">로그인이 만료되었습니다(12시간). 사이트 비밀번호를 다시 넣으면 이어서 접속합니다. 모든 입력과 출력은 기록됩니다.</p>' +
        '<label>사이트 비밀번호<input name="password" type="password" required autocomplete="current-password"></label>' +
        '<p class="wk-error" id="cs-unlock-err" role="alert"' + (msg ? '' : ' hidden') + '>' + cfgEsc(msg || '') + '</p>' +
        '<div class="wk-bar wk-bar-inline"><button type="submit" class="wk-btn wk-primary">잠금 해제</button>' +
        (CS.solo ? '' : '<button type="button" class="wk-btn" onclick="csBack()">대시보드로</button>') + '</div></form></div>';
      const f = csRoot().querySelector('input'); if (f) f.focus();
    }
    async function csUnlock(ev) {
      ev.preventDefault();
      const err = document.getElementById('cs-unlock-err');
      try { await csApi('POST', '/console/api/unlock', { password: ev.target.password.value }); csRoot().innerHTML = ''; csOpen(CS.solo); }
      catch (e) {
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
        (CS.page ? '' : '<button type="button" class="wk-mini" onclick="window.open(\'/term/\', \'_blank\')">새 창으로</button>') + '</div></aside>';
      const bar = CS.solo ? '' :
        '<div class="cs-bar"><div class="cs-layouts" role="group" aria-label="창 배치">' + CS_LAYOUTS.map(l =>
          '<button type="button" class="wk-mini' + (CS.layout === l[0] ? ' cs-on-btn' : '') + '" aria-pressed="' + (CS.layout === l[0]) + '" onclick="csLayout(\'' + l[0] + '\')">' + l[1] + '</button>').join('') +
        '</div><nav class="cs-tabs" id="cs-tabs" aria-label="열린 터미널"></nav></div>';
      const grid = '<div class="cs-grid cs-l' + (CS.solo ? '1' : CS.layout) + '" id="cs-grid">' +
        CS.slots.map((s, i) => '<section class="cs-pane' + (i === CS.active ? ' cs-active' : '') + '" data-i="' + i + '" onmousedown="csFocus(' + i + ')" id="cs-slot-' + i + '"></section>').join('') +
        csGutters() + '</div>';
      csRoot().innerHTML = '<div class="cs-wrap">' + drawer + '<div class="cs-main">' + bar + grid + '</div></div><div class="cs-float-layer" id="cs-float-layer"></div>';
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
      let i = CS.active;
      if (CS.slots[i].t) { const empty = CS.slots.findIndex(s => !s.t); if (empty >= 0) i = empty; }
      csConnectSlot(i, id);
    }
    function csConnectSlot(i, id) {
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
      if (CS.solo) return;   // 솔로(새 창)는 자체 ?solo= 로 복원
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

    // /term/ 페이지: ?t=<대상> 원클릭 접속, ?solo=<대상> 새 창. (예전 #console/<대상> 주소도 받음)
    window.addEventListener('load', () => {
      const q = new URLSearchParams(location.search), h = location.hash || '';
      if (document.body.dataset.page === 'term') {
        CS.page = true;
        CS.pending = q.get('t');
        csOpen(q.get('solo') || null);
      } else if (h.indexOf('#console/') === 0) {
        location.replace(CS_TERM_URL + '?solo=' + encodeURIComponent(decodeURIComponent(h.slice('#console/'.length))));
      }
    });

    // ===== 사이트 입장 로그인: s1 서버가 확인 (12시간). 로그인하면 콘솔은 비밀번호를 다시 묻지 않는다 =====
    async function siteAuthBoot() {
      try {
        const r = await fetch('/console/api/me', { credentials: 'same-origin', cache: 'no-store' });
        const d = await r.json();
        if (d.unlocked) sessionStorage.setItem(AUTH_KEY, 'valid'); else sessionStorage.removeItem(AUTH_KEY);
      } catch (e) { sessionStorage.removeItem(AUTH_KEY); }
      checkAuth();
    }

    document.addEventListener('keydown', e => { if (e.key === 'Escape') { const el = document.getElementById('cs-editor'); if (el && !el.hidden) csEdClose(); } });
