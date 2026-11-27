    // ===== 통합 콘솔: 3대 영역 → 인스턴스 → 실제 터미널 (content/console.js) =====
    // 서버: s1 figteam-console (/console/api/*, /console/ws/<대상>) · 콘솔 비밀번호로 잠금
    // 예전 통합 터미널 기능: 대상별 「확인」·「⚠ 복구」 버튼, 탭, ⧉ 화면 위 창(끌기·크기·최소화·최대화·되돌리기), ↗ 새 창
    const CS = { open: false, solo: null, targets: null, layout: '1', slots: [], floats: [], active: 0, loaded: false,
      sizes: { col: 50, row: 50 }, seq: 0, z: 900, pending: null, page: false };
    const CS_TERM_URL = '/term/';
    // 대시보드에서: 통합 터미널 페이지로 이동 (원클릭 — 대상이 있으면 바로 접속)
    function csGo(id) { location.href = CS_TERM_URL + (id ? '?t=' + encodeURIComponent(id) : ''); }
    const CS_AREAS = [['openstack', '온프렘 · OpenStack', ['onprem', 'openstack']], ['kt', 'KT Cloud', ['kt']], ['aws', 'AWS', ['aws']]];
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

    // ---------- 열기 · 닫기 · 잠금 ----------
    async function csOpen(soloId) {
      CS.open = true; CS.solo = soloId || null;
      const root = csRoot();
      root.hidden = false;
      root.classList.toggle('cs-solo', !!CS.solo);
      root.classList.toggle('cs-page', CS.page);
      document.body.classList.add('cs-on');
      if (!root.querySelector('.cs-wrap')) root.innerHTML = '<p class="cs-wait">통합 콘솔을 불러오는 중…</p>';
      try { await csLoadXterm(); }
      catch (e) { root.innerHTML = '<p class="cs-wait wk-error">터미널 화면 구성요소(xterm.js)를 불러오지 못했습니다. 인터넷 연결을 확인하세요.</p>'; return; }
      try { CS.targets = await csApi('GET', '/console/api/targets'); }
      catch (e) { return csShowUnlock(e.status === 401 ? '' : (e.error || '콘솔 서버에 연결하지 못했습니다 (' + e.status + ')')); }
      csRender();
      if (CS.solo && !CS.slots[0].t) csConnectSlot(0, CS.solo);
      else if (CS.pending) { const id = CS.pending; CS.pending = null; if (CS.targets.some(t => t.id === id && !t.disabled)) csPick(id); }
    }
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
        '<p class="manual-desc">실제 서버에 접속하는 터미널입니다. 콘솔 비밀번호를 넣으면 60분 동안 열립니다. 모든 입력과 출력은 기록됩니다.</p>' +
        '<label>콘솔 비밀번호<input name="password" type="password" required autocomplete="current-password"></label>' +
        '<p class="wk-error" id="cs-unlock-err" role="alert"' + (msg ? '' : ' hidden') + '>' + cfgEsc(msg || '') + '</p>' +
        '<div class="wk-bar wk-bar-inline"><button type="submit" class="wk-btn wk-primary">잠금 해제</button>' +
        (CS.solo ? '' : '<button type="button" class="wk-btn" onclick="csClose()">대시보드로</button>') + '</div></form></div>';
      const f = csRoot().querySelector('input'); if (f) f.focus();
    }
    async function csUnlock(ev) {
      ev.preventDefault();
      const err = document.getElementById('cs-unlock-err');
      try { await csApi('POST', '/console/api/unlock', { password: ev.target.password.value }); csRoot().innerHTML = ''; csOpen(CS.solo); }
      catch (e) {
        err.textContent = e.status === 401 ? '콘솔 비밀번호가 맞지 않습니다' : e.status === 429 ? '시도가 많습니다. 10분 뒤 다시 시도하세요' : (e.error || '잠금을 풀지 못했습니다');
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
        '<aside class="cs-drawer"><div class="cs-drawer-head"><b>통합 터미널</b><span>누르면 바로 접속 · 입력이 기록됩니다</span></div>' +
        CS_AREAS.map(a => '<div class="cs-area"><div class="cfg-group-head"><span class="cfg-dot cfg-c-' + a[0] + '"></span>' + a[1] + '</div>' +
          CS.targets.filter(t => a[2].indexOf(t.area) >= 0).map(t =>
            '<button type="button" class="cs-target"' + (t.disabled ? ' disabled title="' + cfgEsc(t.disabled) + '"' : '') +
            ' onclick="csPick(\'' + cfgEsc(t.id) + '\')"><b>' + cfgEsc(t.name) + '</b><span>' + cfgEsc(t.disabled || t.desc || '') + '</span></button>').join('') + '</div>').join('') +
        '<div class="cs-drawer-foot"><button type="button" class="wk-mini" onclick="csLock()">콘솔 잠그기</button>' +
        '<button type="button" class="wk-mini" onclick="csClose()">← 대시보드</button></div></aside>';
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
      const up = () => { document.removeEventListener('mousemove', move); document.removeEventListener('mouseup', up); document.body.classList.remove('cs-dragging'); };
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
    function csHeadHtml(t, inFloat) {
      const tg = csT(t.target);
      const pre = (label, kind) => Object.keys(tg[kind] || {}).map(k =>
        '<button type="button" class="cs-pre' + (kind === 'fix' ? ' cs-pre-fix' : '') + '" onclick="csPreset(' + t.uid + ',\'' + kind + '\',this)" data-k="' + cfgEsc(k) + '">' + cfgEsc(k) + '</button>').join('');
      return '<header class="cs-pane-head"><span class="cs-dot cs-dot-' + (t.stKind || 'wait') + '" id="cs-dot-' + t.uid + '"></span><b>' + cfgEsc(tg.name) + '</b>' +
        '<span class="cs-status" id="cs-st-' + t.uid + '">' + cfgEsc(t.stText || '') + '</span>' +
        '<span class="cs-pane-acts">' +
          (inFloat ? '<button type="button" class="wk-mini" title="최소화" onclick="csFloatMin(' + t.uid + ')">▁</button><button type="button" class="wk-mini" title="최대화" onclick="csFloatMax(' + t.uid + ')">▢</button>' +
            (CS.solo ? '' : '<button type="button" class="wk-mini" title="칸으로 되돌리기" onclick="csDock(' + t.uid + ')">⇲</button>')
            : (CS.solo ? '' : '<button type="button" class="wk-mini" title="화면 위에 띄우기" onclick="csFloat(' + t.uid + ')">⧉</button>')) +
          '<button type="button" class="wk-mini" title="다시 연결" onclick="csReconnect(' + t.uid + ')">⟳</button>' +
          (CS.solo ? '' : '<button type="button" class="wk-mini" title="새 창으로" onclick="csPopout(' + t.uid + ')">↗</button>') +
          '<button type="button" class="wk-mini" title="닫기" onclick="csCloseTerm(' + t.uid + ')">✕</button></span></header>' +
        (tg.check || tg.fix ? '<div class="cs-presets"><span class="cs-pre-lbl">확인</span>' + pre('확인', 'check') +
          (tg.fix ? '<span class="cs-pre-lbl cs-pre-warn">⚠ 복구</span>' + pre('복구', 'fix') : '') + '</div>' : '');
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
        '?cols=' + term.cols + '&rows=' + term.rows;
      const ws = new WebSocket(url);
      t.ws = ws;
      ws.onopen = () => { csStatus(t, 'ok', '연결됨'); term.focus(); };
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
    function csPreset(uid, kind, btn) {
      const f = csFind(uid); if (!f || !f.t.ws || f.t.ws.readyState !== 1) return;
      const tg = csT(f.t.target), label = btn.dataset.k, cmd = (tg[kind] || {})[label];
      if (!cmd) return;
      if (kind === 'fix' && !btn.dataset.armed) {   // 복구는 한 번 더 눌러야 실행
        btn.dataset.armed = '1'; btn.textContent = '한 번 더 누르면 실행: ' + label;
        setTimeout(() => { if (btn.isConnected) { delete btn.dataset.armed; btn.textContent = label; } }, 4000);
        return;
      }
      if (kind === 'fix') { delete btn.dataset.armed; btn.textContent = label; }
      f.t.ws.send(JSON.stringify({ t: 'i', d: cmd + '\r' }));
      f.t.term.focus();
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
      const head = el.querySelector('.cs-pane-head');
      head.addEventListener('mousedown', e => {
        if (e.target.closest('button') || el.classList.contains('cs-max')) return;
        const sx = e.clientX - el.offsetLeft, sy = e.clientY - el.offsetTop;
        const mv = ev => { el.style.left = Math.max(0, ev.clientX - sx) + 'px'; el.style.top = Math.max(0, ev.clientY - sy) + 'px'; };
        const up = () => { document.removeEventListener('mousemove', mv); document.removeEventListener('mouseup', up); document.body.classList.remove('cs-dragging'); };
        document.body.classList.add('cs-dragging');
        document.addEventListener('mousemove', mv); document.addEventListener('mouseup', up);
      });
      setTimeout(() => { try { t.fit.fit(); } catch (e) {} }, 0);
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
