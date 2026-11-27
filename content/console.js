    // ===== 통합 콘솔: 3대 영역 → 인스턴스 → 실제 터미널 (content/console.js) =====
    // 서버: s1 figteam-console (/console/api/*, /console/ws/<대상>) · 콘솔 비밀번호로 잠금
    const CS = { open: false, solo: null, targets: null, layout: '1', panes: [], active: 0, loaded: false, sizes: { col: 50, row: 50 } };
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

    // 열기: 대시보드 왼쪽 버튼 또는 #console/<대상> (새 창)
    async function csOpen(soloId) {
      CS.open = true; CS.solo = soloId || null;
      const root = csRoot();
      root.hidden = false;
      root.classList.toggle('cs-solo', !!CS.solo);
      document.body.classList.add('cs-on');
      root.innerHTML = '<p class="cs-wait">통합 콘솔을 불러오는 중…</p>';
      try { await csLoadXterm(); }
      catch (e) { root.innerHTML = '<p class="cs-wait wk-error">터미널 화면 구성요소(xterm.js)를 불러오지 못했습니다. 인터넷 연결을 확인하세요.</p>'; return; }
      try { CS.targets = await csApi('GET', '/console/api/targets'); }
      catch (e) { return csShowUnlock(e.status === 401 ? '' : (e.error || '콘솔 서버에 연결하지 못했습니다 (' + e.status + ')')); }
      csRender();
      if (CS.solo) csConnect(0, CS.solo);
    }
    function csClose() {
      CS.panes.forEach(p => csDisconnect(p));
      CS.panes = []; CS.open = false;
      const root = csRoot(); root.hidden = true; root.innerHTML = '';
      document.body.classList.remove('cs-on');
      if ((location.hash || '').indexOf('#console') === 0) history.replaceState(null, '', location.pathname);
    }

    function csShowUnlock(msg) {
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
      try { await csApi('POST', '/console/api/unlock', { password: ev.target.password.value }); csOpen(CS.solo); }
      catch (e) {
        err.textContent = e.status === 401 ? '콘솔 비밀번호가 맞지 않습니다' : e.status === 429 ? '시도가 많습니다. 10분 뒤 다시 시도하세요' : (e.error || '잠금을 풀지 못했습니다');
        err.hidden = false;
      }
    }
    async function csLock() {
      try { await csApi('POST', '/console/api/lock', {}); } catch (e) {}
      CS.panes.forEach(p => csDisconnect(p)); CS.panes = [];
      csShowUnlock('콘솔을 잠갔습니다.');
    }

    // ---------- 화면 ----------
    function csPaneCount() { return { '1': 1, h: 2, v: 2, '4': 4 }[CS.layout]; }
    function csRender() {
      const n = CS.solo ? 1 : csPaneCount();
      while (CS.panes.length < n) CS.panes.push({ target: null });
      while (CS.panes.length > n) csDisconnect(CS.panes.pop());
      if (CS.active >= n) CS.active = 0;
      const drawer = CS.solo ? '' :
        '<aside class="cs-drawer"><div class="cs-drawer-head"><b>통합콘솔</b><span>실제 터미널 · 입력이 기록됩니다</span></div>' +
        CS_AREAS.map(a => '<div class="cs-area"><div class="cfg-group-head"><span class="cfg-dot cfg-c-' + a[0] + '"></span>' + a[1] + '</div>' +
          CS.targets.filter(t => a[2].indexOf(t.area) >= 0).map(t =>
            '<button type="button" class="cs-target"' + (t.disabled ? ' disabled title="' + cfgEsc(t.disabled) + '"' : '') +
            ' onclick="csPick(\'' + cfgEsc(t.id) + '\')"><b>' + cfgEsc(t.name) + '</b><span>' + cfgEsc(t.disabled || t.desc || '') + '</span></button>').join('') + '</div>').join('') +
        '<div class="cs-drawer-foot"><button type="button" class="wk-mini" onclick="csLock()">콘솔 잠그기</button>' +
        '<button type="button" class="wk-mini" onclick="csClose()">대시보드로</button></div></aside>';
      const bar = CS.solo ? '' :
        '<div class="cs-bar"><div class="cs-layouts" role="group" aria-label="창 배치">' + CS_LAYOUTS.map(l =>
          '<button type="button" class="wk-mini' + (CS.layout === l[0] ? ' cs-on-btn' : '') + '" aria-pressed="' + (CS.layout === l[0]) + '" onclick="csLayout(\'' + l[0] + '\')">' + l[1] + '</button>').join('') +
        '</div><span class="cs-hint">칸을 누른 뒤 왼쪽에서 인스턴스를 고르세요. 경계를 끌면 크기가 바뀝니다.</span></div>';
      const grid = '<div class="cs-grid cs-l' + (CS.solo ? '1' : CS.layout) + '" id="cs-grid">' +
        CS.panes.map((p, i) => '<section class="cs-pane' + (i === CS.active ? ' cs-active' : '') + '" data-i="' + i + '" onmousedown="csFocus(' + i + ')">' +
          '<header class="cs-pane-head"><span class="cs-dot" id="cs-dot-' + i + '"></span><b id="cs-name-' + i + '">' + (p.target ? cfgEsc(csT(p.target).name) : '빈 칸') + '</b>' +
          '<span class="cs-status" id="cs-st-' + i + '"></span>' +
          '<span class="cs-pane-acts"><button type="button" class="wk-mini" title="다시 연결" onclick="csReconnect(' + i + ')">⟳</button>' +
          (CS.solo ? '' : '<button type="button" class="wk-mini" title="새 창으로" onclick="csPopout(' + i + ')">↗</button>') +
          '<button type="button" class="wk-mini" title="닫기" onclick="csClosePane(' + i + ')">✕</button></span></header>' +
          '<div class="cs-term" id="cs-term-' + i + '">' + (p.target ? '' : '<p class="cs-empty">왼쪽에서 인스턴스를 고르면 이 칸에 터미널이 열립니다.</p>') + '</div></section>').join('') +
        csGutters() + '</div>';
      csRoot().innerHTML = '<div class="cs-wrap">' + drawer + '<div class="cs-main">' + bar + grid + '</div></div>';
      // 배치를 바꿔도 이미 열린 터미널은 다시 연결하지 않고 새 칸으로 옮긴다
      CS.panes.forEach((p, i) => {
        if (!p.target) return;
        if (p.term && p.box) { const slot = document.getElementById('cs-term-' + i); slot.innerHTML = ''; slot.appendChild(p.box); csStatus(i, p.stKind || 'ok', p.stText || ''); }
        else csMount(i);
      });
      csApplySizes();
    }
    function csT(id) { return (CS.targets || []).find(t => t.id === id) || { name: id }; }
    function csGutters() {
      const L = CS.solo ? '1' : CS.layout;
      return (L === 'h' || L === '4' ? '<div class="cs-gutter cs-gx" onmousedown="csDrag(event,\'col\')" title="좌우 크기 조절"></div>' : '') +
             (L === 'v' || L === '4' ? '<div class="cs-gutter cs-gy" onmousedown="csDrag(event,\'row\')" title="상하 크기 조절"></div>' : '');
    }
    function csApplySizes() {
      const g = document.getElementById('cs-grid'); if (!g) return;
      g.style.setProperty('--cs-col', CS.sizes.col + '%');
      g.style.setProperty('--cs-row', CS.sizes.row + '%');
      CS.panes.forEach(p => { if (p.fit) try { p.fit.fit(); } catch (e) {} });
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
    function csPick(id) {
      let i = CS.active;
      if (CS.panes[i].target) { const empty = CS.panes.findIndex(p => !p.target); if (empty >= 0) i = empty; }
      csConnect(i, id);
    }

    // ---------- 터미널 연결 ----------
    function csConnect(i, id) {
      const p = CS.panes[i];
      csDisconnect(p);
      p.target = id;
      document.getElementById('cs-name-' + i).textContent = csT(id).name;
      csFocus(i);
      csMount(i);
    }
    function csMount(i) {
      const p = CS.panes[i], slot = document.getElementById('cs-term-' + i);
      slot.innerHTML = '';
      const box = document.createElement('div');
      box.className = 'cs-term-inner';
      slot.appendChild(box);
      p.box = box;
      const term = new window.Terminal({ cursorBlink: true, fontFamily: "'JetBrains Mono', monospace", fontSize: 13, scrollback: 5000,
        theme: { background: '#06090e', foreground: '#e2e8f0', cursor: '#93c5fd', selectionBackground: '#1e3a8a' } });
      const fit = new window.FitAddon.FitAddon();
      term.loadAddon(fit); term.open(box);
      try { fit.fit(); } catch (e) {}
      p.term = term; p.fit = fit;
      csStatus(i, 'wait', '연결 중…');
      const url = (location.protocol === 'https:' ? 'wss://' : 'ws://') + location.host + '/console/ws/' + encodeURIComponent(p.target) +
        '?cols=' + term.cols + '&rows=' + term.rows;
      const ws = new WebSocket(url);
      p.ws = ws;
      ws.onopen = () => { csStatus(CS.panes.indexOf(p), 'ok', '연결됨'); term.focus(); };
      ws.onmessage = e => term.write(e.data);
      ws.onclose = e => {
        if (p.ws !== ws) return;
        const msg = CS_CLOSE_MSG[e.code] || (e.code === 1000 ? '세션이 끝났습니다' : '연결이 끊겼습니다 (' + e.code + ')');
        csStatus(CS.panes.indexOf(p), 'off', msg);
        term.write('\r\n\x1b[33m[' + msg + ' — ⟳ 로 다시 연결]\x1b[0m\r\n');
        if (e.code === 4401) csShowUnlock('잠금이 만료되었습니다. 다시 풀어 주세요.');
      };
      term.onData(d => { if (ws.readyState === 1) ws.send(JSON.stringify({ t: 'i', d: d })); });
      term.onResize(sz => { if (ws.readyState === 1) ws.send(JSON.stringify({ t: 'r', c: sz.cols, r: sz.rows })); });
      p.ro = new ResizeObserver(() => { try { fit.fit(); } catch (e) {} });
      p.ro.observe(box);
    }
    function csStatus(i, kind, text) {
      const p = CS.panes[i]; if (p) { p.stKind = kind; p.stText = text; }
      const d = document.getElementById('cs-dot-' + i), s = document.getElementById('cs-st-' + i);
      if (d) d.className = 'cs-dot cs-dot-' + kind;
      if (s) s.textContent = text;
    }
    function csDisconnect(p) {
      if (!p) return;
      if (p.ro) { p.ro.disconnect(); p.ro = null; }
      if (p.ws) { const w = p.ws; p.ws = null; try { w.close(); } catch (e) {} }
      if (p.term) { try { p.term.dispose(); } catch (e) {} p.term = null; p.fit = null; p.box = null; }
    }
    function csReconnect(i) { if (CS.panes[i].target) csConnect(i, CS.panes[i].target); }
    function csClosePane(i) {
      csDisconnect(CS.panes[i]);
      CS.panes[i] = { target: null };
      if (CS.solo) return window.close();
      csRender();
    }
    function csPopout(i) {
      const id = CS.panes[i].target;
      if (!id) return;
      window.open(location.pathname + '#console/' + encodeURIComponent(id), 'cs-' + id + '-' + Date.now(), 'width=1000,height=640');
      csClosePane(i);
    }

    // #console/<대상> 으로 들어온 새 창
    window.addEventListener('load', () => {
      const h = location.hash || '';
      if (h.indexOf('#console/') === 0 && sessionStorage.getItem('figteam_auth_token')) {
        setTimeout(() => csOpen(decodeURIComponent(h.slice('#console/'.length))), 300);
      }
    });
