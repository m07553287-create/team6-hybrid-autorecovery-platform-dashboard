(function () {
  'use strict';
  // ===== 민원불패 v2.5.1 — OpenStack 구조 · 연결 (#osvm 하단) =====
  var root = document.getElementById('osx');
  if (!root) return;
  var NS = 'http://www.w3.org/2000/svg';
  var DATA = null, loading = false, lastLoad = 0;

  function h(tag, cls, text, parent) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text != null) e.textContent = text;
    if (parent) parent.appendChild(e);
    return e;
  }
  function s(tag, attrs, parent, text) {
    var e = document.createElementNS(NS, tag);
    for (var k in attrs) e.setAttribute(k, attrs[k]);
    if (text != null) e.textContent = text;
    if (parent) parent.appendChild(e);
    return e;
  }
  function pct(a, b) { return b ? Math.min(100, Math.round(a / b * 100)) : 0; }
  function gb(bytes) { return bytes == null ? '-' : (bytes / 1073741824).toFixed(bytes > 1073741824 ? 1 : 2) + ' GB'; }

  // ---------- 골격 ----------
  var head = h('div', 'osx-head', null, root);
  h('h3', null, 'OpenStack 구조 · 연결', head);
  var meta = h('p', 'osx-meta', '불러오는 중…', head);
  var refresh = h('button', 'btn-top', '새로고침', head); refresh.type = 'button';
  var tabs = h('div', 'osx-tabs', null, root); tabs.setAttribute('role', 'tablist');
  var panes = {};
  // 재배치: 작은 정보는 좁게, 큰 구성도는 한 화면에
  var panel = document.getElementById('osvm-panel');
  var mapPane = h('div', 'osx-mappane', null, null);
  panes.map = mapPane;
  (function layout() {
    if (!panel) return;
    var hero = panel.querySelector('.overview-hero'), stats = panel.querySelector('.stats-grid');
    var focused = document.getElementById('os-focused-box');
    var selector = focused ? focused.previousElementSibling : null;
    var grid = document.getElementById('os-vm-grid');
    var invTitle = grid ? grid.previousElementSibling : null;
    var host = grid ? grid.nextElementSibling : null;
    while (host && !(host.classList && host.classList.contains('kt-vm-box'))) host = host.nextElementSibling;
    panel.classList.add('osv-on');
    var top = document.createElement('div'); top.className = 'osv-top';
    if (hero) top.appendChild(hero);
    if (stats) top.appendChild(stats);
    top.appendChild(head);
    var main = document.createElement('div'); main.className = 'osv-main';
    var mapCol = h('div', 'osv-mapcol', null, main);
    mapCol.appendChild(mapPane);
    var side = h('div', 'osv-side', null, main);
    if (selector) side.appendChild(selector);
    if (focused) side.appendChild(focused);
    panel.insertBefore(top, panel.firstChild);
    panel.insertBefore(main, top.nextSibling);
    mapCol.appendChild(root);
    panes.inv = h('div', 'osx-pane', null, null); panes.inv.dataset.p = 'inv'; panes.inv.hidden = true;
    if (invTitle && invTitle.classList.contains('section-title')) invTitle.remove();
    if (grid) panes.inv.appendChild(grid);
    panes.host = h('div', 'osx-pane', null, null); panes.host.dataset.p = 'host'; panes.host.hidden = true;
    if (host) panes.host.appendChild(host);
  })();
  [['svc', '서비스 상태'], ['res', '자원 현황'], ['ops', 'VM 도구'], ['inv', 'VM 인벤토리'], ['host', '물리 호스트']].forEach(function (t, i) {
    var b = h('button', 'osx-tab' + (i ? '' : ' on'), t[1], tabs); b.type = 'button'; b.dataset.p = t[0]; b.setAttribute('role', 'tab');
    var p = panes[t[0]] || h('div', 'osx-pane', null, null);
    p.dataset.p = t[0]; p.hidden = !!i; root.appendChild(p);
    panes[t[0]] = p;
  });
  tabs.addEventListener('click', function (e) {
    var k = e.target.dataset && e.target.dataset.p; if (!k) return;
    Array.prototype.forEach.call(tabs.children, function (b) { b.classList.toggle('on', b.dataset.p === k); });
    Object.keys(panes).forEach(function (p) { if (p !== 'map') panes[p].hidden = p !== k; });
  });
  refresh.addEventListener('click', function () { load(true); });

  function errBox(parent, key) {
    if (DATA && DATA.errors && DATA.errors[key]) h('p', 'osx-err', '불러오지 못함 (' + key + '): ' + DATA.errors[key], parent);
  }

  // ---------- 데이터 ----------
  function load(force) {
    if (loading || (!force && Date.now() - lastLoad < 20000)) return;
    loading = true; meta.textContent = '불러오는 중…';
    fetch('/api/openstack/overview', { credentials: 'same-origin' })
      .then(function (r) { return r.json().then(function (j) { return { ok: r.ok, j: j }; }); })
      .then(function (x) {
        loading = false; lastLoad = Date.now();
        if (!x.ok || x.j.status !== 'ok') { meta.textContent = 'OpenStack 정보를 불러오지 못했습니다: ' + (x.j.message || ('HTTP ' + x.ok)); return; }
        DATA = x.j;
        var ne = Object.keys(DATA.errors || {}).length;
        meta.textContent = '갱신 ' + new Date(DATA.generated * 1000).toLocaleTimeString() + ' · VM ' + (DATA.servers || []).length + '대 · 네트워크 ' + (DATA.networks || []).length + '개' + (ne ? ' · 일부 항목 실패 ' + ne + '건' : '');
        render();
      })
      .catch(function (e) { loading = false; meta.textContent = 'OpenStack 정보를 불러오지 못했습니다: ' + e.message; });
  }
  function render() { renderMap(); renderSvc(); renderRes(); renderOps(); }

  // ---------- 1·3. 구성도 + 경로 추적 ----------
  var mapWrap, svg, traceList, traceCap, traceIdx = -1, traceTimer = null, HOPS = [];
  function renderMap() {
    var p = panes.map; p.textContent = '';
    var d = DATA, nets = d.networks || [], subnets = {}, ports = d.ports || [], servers = d.servers || [];
    (d.subnets || []).forEach(function (x) { subnets[x.id] = x; });
    var ext = nets.filter(function (n) { return n['router:external']; });
    var intn = nets.filter(function (n) { return !n['router:external']; });
    // 네트워크 정보가 없으면 VM 주소의 네트워크 이름으로 대체
    if (!nets.length) {
      var names = {};
      servers.forEach(function (v) { Object.keys(v.addresses || {}).forEach(function (k) { names[k] = 1; }); });
      intn = Object.keys(names).map(function (k) { return { id: 'name:' + k, name: k, subnets: [] }; });
    }
    var cidr = function (n) { return (n.subnets || []).map(function (id) { return subnets[id] ? subnets[id].cidr : ''; }).filter(Boolean).join(', '); };
    var hosts = (d.hypervisors || []).map(function (x) { return x.hypervisor_hostname; });
    servers.forEach(function (v) { if (v.host && hosts.indexOf(v.host) < 0 && hosts.indexOf((v.host || '').split('.')[0]) < 0) hosts.push(v.host); });
    if (servers.some(function (v) { return !v.host; })) hosts.push('(배치 정보 없음)');
    var byHost = {};
    hosts.forEach(function (hn) { byHost[hn] = []; });
    servers.forEach(function (v) {
      var key = hosts.filter(function (hn) { return v.host && (hn === v.host || hn.split('.')[0] === v.host.split('.')[0]); })[0] || '(배치 정보 없음)';
      (byHost[key] = byHost[key] || []).push(v);
    });
    var fipByFixed = {};
    (d.floatingips || []).forEach(function (f) { if (f.fixed_ip_address) fipByFixed[f.fixed_ip_address] = f; });

    // 배치 (열: 외부 경로 | 외부망 | 라우터 | 내부망 | Compute)
    var X_EXTCHAIN = 20, X_EXT = 230, X_RT = 360, X_INT = 660, INT_GAP = 80;
    var X_HOST = X_INT + Math.max(1, intn.length) * INT_GAP + 60, HOST_W = 340, ROW = 64, TOP = 60;
    var y = TOP, frames = [];
    hosts.forEach(function (hn) {
      var list = byHost[hn] || [];
      var hgt = 54 + Math.max(1, list.length) * ROW;
      frames.push({ host: hn, y: y, h: hgt, vms: list });
      y += hgt + 24;
    });
    var H = Math.max(y, TOP + 4 * 90 + 30), W = X_HOST + HOST_W + 120;
    mapWrap = h('div', 'osx-map', null, p);
    svg = s('svg', { viewBox: '0 0 ' + W + ' ' + H, 'class': 'osx-svg', role: 'img', 'aria-label': 'OpenStack 네트워크 구성도', preserveAspectRatio: 'xMidYMid meet' }, mapWrap);
    var gL = s('g', {}, svg), gN = s('g', {}, svg);
    var el = {};

    function box(id, x, y0, w, hh, title, sub, cls) {
      var g = s('g', { 'class': 'osx-node ' + (cls || ''), 'data-id': id }, gN);
      s('rect', { x: x, y: y0, width: w, height: hh }, g);
      s('text', { x: x + w / 2, y: y0 + (sub ? hh / 2 - 5 : hh / 2 + 5), 'text-anchor': 'middle', 'class': 't' }, g, title);
      if (sub) s('text', { x: x + w / 2, y: y0 + hh / 2 + 16, 'text-anchor': 'middle', 'class': 's' }, g, sub);
      el[id] = g; return g;
    }
    function line(id, pts, cls, label, lx, ly, anchor) {
      var g = s('g', { 'class': 'osx-link ' + (cls || ''), 'data-id': id }, gL);
      s('path', { d: 'M' + pts.map(function (q) { return q.join(','); }).join(' L') }, g);
      if (label) s('text', { x: lx, y: ly, 'text-anchor': anchor || 'start', 'class': 'l' }, g, label);
      el[id] = g; return g;
    }
    // 외부 경로 체인
    var chain = [['ext-cf', 'Cloudflare', 'Anycast · WAF'], ['ext-kt', 'KT Edge', '14.63.212.190'], ['ext-wg', 'WG 터널 A', 'KT ↔ 온프렘'], ['ext-host', '온프렘 호스트', '10.10.10.8 · VMware']];
    chain.forEach(function (c, i) {
      box(c[0], X_EXTCHAIN, TOP + i * 90, 150, 56, c[1], c[2], 'ext');
      if (i) line('l-' + c[0], [[X_EXTCHAIN + 75, TOP + (i - 1) * 90 + 56], [X_EXTCHAIN + 75, TOP + i * 90]], 'ext');
    });
    s('text', { x: X_EXTCHAIN, y: TOP - 20, 'class': 'osx-col' }, gN, 'OpenStack 밖 (대민 경로)');
    // 외부망 막대
    var extBars = {};
    var extList = ext.length ? ext : [{ id: 'ext:none', name: '외부망 정보 없음', subnets: [] }];
    extList.forEach(function (n, i) {
      var x = X_EXT + i * 18;
      extBars[n.id] = x;
      var g = s('g', { 'class': 'osx-bar ext', 'data-id': 'net-' + n.id }, gN);
      s('rect', { x: x - 5, y: TOP - 10, width: 10, height: H - TOP - 20 }, g);
      s('text', { x: x, y: TOP - 18, 'text-anchor': 'middle', 'class': 'b' }, g, n.name || n.id.slice(0, 8));
      s('text', { x: x + 12, y: H - 16, 'class': 's' }, g, cidr(n));
      el['net-' + n.id] = g;
    });
    var firstExt = extList[0].id;
    line('l-host-ext', [[X_EXTCHAIN + 150, TOP + 3 * 90 + 28], [extBars[firstExt] - 5, TOP + 3 * 90 + 28]], 'ext', '브리지', X_EXTCHAIN + 156, TOP + 3 * 90 + 22);
    // 내부망 막대
    var intBars = {};
    intn.forEach(function (n, i) {
      var x = X_INT + i * INT_GAP;
      intBars[n.id] = x; intBars['name:' + n.name] = x;
      var g = s('g', { 'class': 'osx-bar', 'data-id': 'net-' + n.id }, gN);
      s('rect', { x: x - 5, y: TOP - 10, width: 10, height: H - TOP - 20 }, g);
      s('text', { x: x, y: TOP - 18, 'text-anchor': 'middle', 'class': 'b' }, g, n.name || n.id.slice(0, 8));
      s('text', { x: x + 10, y: H - 16, 'class': 's' }, g, cidr(n));
      el['net-' + n.id] = g;
    });
    // 라우터
    var routers = d.routers || [];
    routers.forEach(function (r, i) {
      var ry = TOP + 40 + i * 120;
      box('rt-' + r.id, X_RT, ry, 150, 56, r.name || '라우터', 'OVN · NAT', 'rt');
      var gw = r.external_gateway_info || {};
      var gwip = ((gw.external_fixed_ips || [])[0] || {}).ip_address || '';
      var ex = extBars[gw.network_id] != null ? extBars[gw.network_id] : extBars[firstExt];
      line('l-gw-' + r.id, [[ex + 5, ry + 20], [X_RT, ry + 20]], 'gw', gwip, ex + 14, ry + 14);
      ports.filter(function (pt) { return pt.device_id === r.id && /router_interface/.test(pt.device_owner || ''); }).forEach(function (pt, k) {
        var ix = intBars[pt.network_id]; if (ix == null) return;
        var ip = ((pt.fixed_ips || [])[0] || {}).ip_address || '';
        var yy = ry + 36 + k * 10;
        line('l-if-' + pt.id, [[X_RT + 150, yy], [ix - 5, yy]], 'if', ip, X_RT + 160, yy - 5);
        el['l-if-net-' + pt.network_id] = el['l-if-' + pt.id];
      });
    });
    // Compute 프레임 + VM
    frames.forEach(function (f, fi) {
      var g = s('g', { 'class': 'osx-host', 'data-id': 'host-' + f.host }, gN);
      s('rect', { x: X_HOST, y: f.y, width: HOST_W, height: f.h }, g);
      var hv = (d.hypervisors || []).filter(function (x) { return x.hypervisor_hostname === f.host; })[0];
      s('text', { x: X_HOST + 10, y: f.y + 20, 'class': 'b' }, g, f.host);
      if (hv) s('text', { x: X_HOST + 10, y: f.y + 42, 'class': 's' }, g, (hv.host_ip || '') + ' · vCPU ' + hv.vcpus_used + '/' + hv.vcpus + ' · RAM ' + Math.round(hv.memory_mb_used / 1024) + '/' + Math.round(hv.memory_mb / 1024) + 'G');
      el['host-' + f.host] = g;
      f.vms.forEach(function (v, i) {
        var vy = f.y + 54 + i * ROW;
        var ips = [];
        Object.keys(v.addresses || {}).forEach(function (nn) { (v.addresses[nn] || []).forEach(function (a) { ips.push({ net: nn, ip: a.addr, type: a['OS-EXT-IPS:type'] }); }); });
        var fixed = ips.filter(function (a) { return a.type !== 'floating'; });
        var fip = ips.filter(function (a) { return a.type === 'floating'; }).map(function (a) { return a.ip; })[0] ||
          fixed.map(function (a) { return fipByFixed[a.ip] && fipByFixed[a.ip].floating_ip_address; }).filter(Boolean)[0];
        var st = (v.status || '').toUpperCase();
        box('vm-' + v.id, X_HOST + 20, vy, 170, 50, v.name, (v.flavor || '') + ' · ' + st, 'vm st-' + (st === 'ACTIVE' ? 'ok' : st === 'SHUTOFF' ? 'off' : 'warn'));
        if (fip) {
          var fg = s('g', { 'class': 'osx-fip', 'data-id': 'fip-' + v.id }, gN);
          s('rect', { x: X_HOST + 200, y: vy + 13, width: 124, height: 24 }, fg);
          s('text', { x: X_HOST + 262, y: vy + 29, 'text-anchor': 'middle' }, fg, fip);
          el['fip-' + v.id] = fg;
        }
        fixed.forEach(function (a, k) {
          var net = intn.filter(function (n) { return n.name === a.net; })[0];
          var bx = net ? intBars[net.id] : intBars['name:' + a.net];
          if (bx == null) return;
          var yy = vy + 18 + k * 12;
          line('l-vm-' + v.id + '-' + k, [[bx + 5, yy], [X_HOST + 20, yy]], 'vm', a.ip, bx + 10, yy - 5);
          if (!k) el['l-vm-' + v.id] = el['l-vm-' + v.id + '-' + k];
        });
      });
      if (fi > 0) {
        var prev = frames[fi - 1];
        line('l-geneve-' + fi, [[X_HOST + HOST_W + 14, prev.y + prev.h / 2], [X_HOST + HOST_W + 14, f.y + f.h / 2]], 'geneve', 'OVN Geneve', X_HOST + HOST_W + 22, (prev.y + prev.h / 2 + f.y + f.h / 2) / 2 + 4, 'start');
      }
    });
    s('text', { x: X_HOST, y: TOP - 20, 'class': 'osx-col' }, gN, 'Compute 노드 · VM (Nova 배치)');
    errBox(p, 'networks'); errBox(p, 'routers'); errBox(p, 'servers');

    // 경로 추적 (실데이터 기반)
    var trace = h('div', 'osx-trace', null, p);
    var bar = h('div', 'osx-tbar', null, trace);
    h('strong', null, '전체 경로 추적', bar);
    traceCap = h('span', 'osx-tcap', '단계를 고르거나 재생하세요', bar);
    var bPrev = h('button', 'btn-top', '◀ 이전', bar), bPlay = h('button', 'btn-top', '재생', bar), bNext = h('button', 'btn-top', '다음 ▶', bar);
    [bPrev, bPlay, bNext].forEach(function (b) { b.type = 'button'; });
    traceList = h('ol', 'osx-tlist compact', null, bar);
    var target = servers.filter(function (v) { return el['fip-' + v.id]; })[0] || servers[0];
    var rt = routers[0];
    var tNet = target ? intn.filter(function (n) { return (target.addresses || {})[n.name]; })[0] : null;
    var tFixed = target ? ((((target.addresses || {})[tNet ? tNet.name : Object.keys(target.addresses || {})[0]] || [])[0]) || {}).addr : '';
    var tFip = target && el['fip-' + target.id] ? el['fip-' + target.id].textContent : '';
    HOPS = [
      ['Cloudflare 애니캐스트: 가장 가까운 엣지가 요청 수신 (WAF)', ['ext-cf']],
      ['KT Edge(14.63.212.190): TLS 종료 · 접수 대기열', ['ext-kt', 'l-ext-kt']],
      ['WireGuard 터널 A → 온프렘 호스트', ['ext-wg', 'l-ext-wg']],
      ['온프렘 호스트(10.10.10.8) → VMware 브리지 → 외부망', ['ext-host', 'l-ext-host', 'l-host-ext', 'net-' + firstExt]],
      [tFip ? 'Floating IP ' + tFip + ' → 라우터 (OVN NAT)' : '외부망 → 라우터 게이트웨이 (OVN NAT)', rt ? ['l-gw-' + rt.id, 'rt-' + rt.id].concat(target ? ['fip-' + target.id] : []) : []],
      [tNet ? '라우터 → ' + tNet.name + ' (게이트웨이 인터페이스)' : '라우터 → 내부망', tNet ? ['l-if-net-' + tNet.id, 'net-' + tNet.id] : []],
      [target ? tNet ? tNet.name + ' → ' + target.name + ' (' + tFixed + ' · ' + (target.host || '') + ')' : target.name : 'VM 정보 없음', target ? ['l-vm-' + target.id, 'vm-' + target.id, 'host-' + (frames.filter(function (f) { return f.vms.indexOf(target) >= 0; })[0] || {}).host] : []]
    ];
    if (frames.length > 1) HOPS.push(['다른 Compute의 VM과는 OVN Geneve 터널로 통신', ['l-geneve-1']]);
    HOPS.forEach(function (hp, i) {
      var li = h('li', null, null, traceList); li.dataset.i = i; li.title = hp[0]; li.tabIndex = 0;
      h('i', null, String(i + 1), li); h('span', null, hp[0], li);
      li.addEventListener('keydown', function (e) { if (e.key === 'Enter') { stop(); go(i); } });
      li.addEventListener('click', function () { stop(); go(i); });
    });
    function go(i) {
      traceIdx = Math.max(0, Math.min(HOPS.length - 1, i));
      Object.keys(el).forEach(function (k) { if (el[k]) el[k].classList.remove('hl', 'done'); });
      HOPS.forEach(function (hp, j) { if (j <= traceIdx) hp[1].forEach(function (id) { if (el[id]) el[id].classList.add(j === traceIdx ? 'hl' : 'done'); }); });
      Array.prototype.forEach.call(traceList.children, function (li) { li.classList.toggle('active', +li.dataset.i === traceIdx); li.classList.toggle('done', +li.dataset.i < traceIdx); });
      traceCap.textContent = (traceIdx + 1) + '. ' + HOPS[traceIdx][0];
    }
    function stop() { if (traceTimer) { clearInterval(traceTimer); traceTimer = null; } bPlay.textContent = '재생'; }
    bPrev.addEventListener('click', function () { stop(); go(traceIdx - 1); });
    bNext.addEventListener('click', function () { stop(); go(traceIdx + 1); });
    bPlay.addEventListener('click', function () {
      if (traceTimer) { stop(); return; }
      bPlay.textContent = '일시정지';
      if (traceIdx >= HOPS.length - 1) traceIdx = -1;
      go(traceIdx + 1);
      traceTimer = setInterval(function () { if (traceIdx >= HOPS.length - 1) { stop(); return; } go(traceIdx + 1); }, 1600);
    });
  }

  // ---------- 2. 서비스 상태 ----------
  function renderSvc() {
    var p = panes.svc; p.textContent = '';
    var d = DATA, byHost = {};
    function add(host, name, up, src) { (byHost[host || '?'] = byHost[host || '?'] || []).push({ name: name, up: up, src: src }); }
    (d.nova_services || []).forEach(function (x) { add(x.host, x.binary, x.state === 'up' && x.status === 'enabled', 'Nova'); });
    (d.agents || []).forEach(function (x) { add(x.host, x.binary || x.agent_type, !!x.alive && x.admin_state_up !== false, 'Neutron'); });
    (d.cinder_services || []).forEach(function (x) { add((x.host || '').split('@')[0], x.binary, x.state === 'up' && x.status === 'enabled', 'Cinder'); });
    var all = [].concat.apply([], Object.keys(byHost).map(function (k) { return byHost[k]; }));
    var down = all.filter(function (x) { return !x.up; }).length;
    h('p', 'osx-sum ' + (down ? 'bad' : 'good'), down ? '서비스 ' + all.length + '개 중 ' + down + '개 비정상' : '서비스 ' + all.length + '개 모두 정상', p);
    var grid = h('div', 'osx-hosts', null, p);
    Object.keys(byHost).sort().forEach(function (host) {
      var c = h('div', 'osx-card', null, grid);
      h('h4', null, host, c);
      var ul = h('ul', null, null, c);
      byHost[host].forEach(function (x) {
        var li = h('li', x.up ? 'up' : 'down', null, ul);
        h('span', 'dot ' + (x.up ? 'green' : 'red'), null, li);
        h('b', null, x.name, li); h('em', null, x.src + (x.up ? '' : ' · 비정상'), li);
      });
    });
    ['nova_services', 'agents', 'cinder_services'].forEach(function (k) { errBox(p, k); });
    if ((d.catalog || []).length) {
      h('h4', 'osx-sub', 'Keystone 서비스 카탈로그', p);
      var cg = h('div', 'osx-chips', null, p);
      d.catalog.forEach(function (c) {
        var chip = h('div', 'osx-chip', null, cg);
        h('b', null, c.type, chip); h('span', null, c.name, chip); h('em', null, (d.endpoints || {})[c.type] || '', chip);
        chip.title = (c.interfaces || []).join(' · ');
      });
    }
  }

  // ---------- 4. 자원 현황 ----------
  function meter(parent, label, used, total, unit) {
    var m = h('div', 'osx-meter', null, parent);
    h('span', 'lb', label, m);
    var b = h('div', 'bar', null, m); var f = h('i', null, null, b);
    var v = pct(used, total); f.style.width = v + '%'; if (v >= 85) f.className = 'hot';
    h('b', null, (used == null ? '-' : used) + '/' + (total == null ? '-' : total) + (unit || ''), m);
  }
  function list(parent, rows, empty) {
    var ul = h('ul', 'osx-list', null, parent);
    if (!rows.length) { h('li', 'empty', empty || '없음', ul); return; }
    rows.forEach(function (r) { var li = h('li', null, null, ul); h('b', null, r[0], li); h('span', null, r[1], li); if (r[2]) li.title = r[2]; });
  }
  function renderRes() {
    var p = panes.res; p.textContent = '';
    var d = DATA, names = {};
    (d.servers || []).forEach(function (v) { names[v.id] = v.name; });
    var g = h('div', 'osx-resgrid', null, p);
    var c1 = h('section', null, null, g); h('h4', 'osx-sub', 'Compute 노드', c1);
    (d.hypervisors || []).forEach(function (x) {
      var c = h('div', 'osx-hv', null, c1);
      var t = h('div', 't', null, c); h('b', null, x.hypervisor_hostname, t); h('span', null, (x.host_ip || '') + ' · VM ' + (x.running_vms || 0), t);
      meter(c, 'vCPU', x.vcpus_used, x.vcpus);
      meter(c, 'RAM', Math.round(x.memory_mb_used / 1024), Math.round(x.memory_mb / 1024), 'G');
      meter(c, '디스크', x.local_gb_used, x.local_gb, 'G');
    });
    errBox(c1, 'hypervisors');
    var L = d.limits || {};
    var c2 = h('section', null, null, g); h('h4', 'osx-sub', '프로젝트 쿼터', c2);
    if (L.maxTotalCores) {
      meter(c2, '인스턴스', L.totalInstancesUsed, L.maxTotalInstances);
      meter(c2, 'vCPU', L.totalCoresUsed, L.maxTotalCores);
      meter(c2, 'RAM', Math.round(L.totalRAMUsed / 1024), Math.round(L.maxTotalRAMSize / 1024), 'G');
    } else h('p', 'osx-meta', '쿼터 정보 없음', c2);
    errBox(c2, 'limits');
    var c3 = h('section', null, null, g); h('h4', 'osx-sub', 'Cinder 볼륨 · Swift', c3);
    list(c3, (d.volumes || []).map(function (v) {
      var at = (v.attachments || []).map(function (a) { return (names[a.server_id] || '') + ' ' + (a.device || ''); }).join(', ');
      return [v.name || v.id.slice(0, 8), v.size + 'GB · ' + v.status + (at ? ' · ' + at : ''), v.volume_type];
    }), '볼륨 없음');
    if (d.swift) list(c3, d.swift.map(function (c) { return ['🗄 ' + c.name, c.count + '개 · ' + gb(c.bytes)]; }));
    errBox(c3, 'volumes'); errBox(c3, 'swift');
    var c4 = h('section', null, null, g); h('h4', 'osx-sub', 'Glance 이미지', c4);
    list(c4, (d.images || []).map(function (i) { return [i.name, (i.disk_format || '') + ' · ' + gb(i.size) + ' · ' + (i.status || ''), i.visibility]; }), '이미지 없음');
    errBox(c4, 'images');
  }

  // ---------- 5. VM 도구 ----------
  function renderOps() {
    var p = panes.ops; p.textContent = '';
    var vms = DATA.servers || [];
    var row = h('div', 'osx-ops', null, p);
    h('label', null, '대상 VM', row).htmlFor = 'osx-vm';
    var sel = h('select', null, null, row); sel.id = 'osx-vm';
    vms.forEach(function (v) { var o = h('option', null, v.name + ' (' + v.status + ' · ' + (v.host || '-') + ')', sel); o.value = v.id; });
    var bLog = h('button', 'btn-top', '콘솔 로그 보기', row), bSnap = h('button', 'btn-top', '스냅샷 만들기', row);
    var aHz = h('a', 'btn-top', 'Horizon에서 열기 ↗', row); aHz.target = '_blank'; aHz.rel = 'noopener';
    [bLog, bSnap].forEach(function (b) { b.type = 'button'; });
    function syncLink() { aHz.href = 'https://horizon.ktci5.kr/dashboard/project/instances/' + encodeURIComponent(sel.value) + '/'; }
    sel.addEventListener('change', syncLink); syncLink();
    var confirmBox = h('div', 'osx-confirm', null, p); confirmBox.hidden = true;
    var out = h('pre', 'osx-log', '콘솔 로그(부팅 · 커널 메시지 최근 80줄)를 볼 VM을 고르세요.', p);
    h('p', 'osx-note', '원격 콘솔(noVNC)은 Controller 내부 6080 포트를 쓰므로 외부에서는 Horizon 콘솔 탭이 열리지 않을 수 있습니다. 삭제 · 네트워크 변경은 Horizon에서 하세요.', p);
    bLog.addEventListener('click', function () {
      out.textContent = '불러오는 중…';
      fetch('/api/openstack/console-log?id=' + encodeURIComponent(sel.value), { credentials: 'same-origin' })
        .then(function (r) { return r.json(); })
        .then(function (j) { out.textContent = j.status === 'ok' ? (j.output || '(출력 없음)') : '불러오지 못함: ' + j.message; })
        .catch(function (e) { out.textContent = '불러오지 못함: ' + e.message; });
    });
    bSnap.addEventListener('click', function () {
      var v = vms.filter(function (x) { return x.id === sel.value; })[0]; if (!v) return;
      confirmBox.textContent = ''; confirmBox.hidden = false;
      h('p', null, v.name + ' 스냅샷을 만듭니다. Glance 이미지로 저장되며 디스크 용량을 사용합니다.', confirmBox);
      var inp = h('input', null, null, confirmBox); inp.value = v.name + '-snap-' + new Date().toISOString().slice(0, 16).replace(/[-:T]/g, ''); inp.setAttribute('aria-label', '스냅샷 이름');
      var ok = h('button', 'btn-top primary', '스냅샷 만들기', confirmBox), no = h('button', 'btn-top', '취소', confirmBox);
      ok.type = no.type = 'button';
      no.addEventListener('click', function () { confirmBox.hidden = true; });
      ok.addEventListener('click', function () {
        ok.disabled = true; ok.textContent = '요청 중…';
        fetch('/api/openstack/vm/snapshot', { method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ id: v.id, name: inp.value }) })
          .then(function (r) { return r.json(); })
          .then(function (j) { confirmBox.textContent = j.status === 'ok' ? '스냅샷 요청됨: ' + j.name + ' (Glance에서 진행 상태 확인)' : '스냅샷 실패: ' + j.message; })
          .catch(function (e) { confirmBox.textContent = '스냅샷 실패: ' + e.message; });
      });
    });
  }

  // ---------- 탭 진입 시 불러오기 ----------
  var orig = window.switchTab;
  if (typeof orig === 'function') {
    window.switchTab = function (k) { orig(k); if (k === 'osvm') load(false); };
  }
  if ((location.hash || '').replace('#', '') === 'osvm') load(false);
  setInterval(function () { var pnl = document.getElementById('osvm-panel'); if (pnl && pnl.style.display !== 'none' && !document.hidden) load(false); }, 60000);
  window.OSView = { load: load };
})();
