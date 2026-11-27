    // ===== 메인 대시보드: 살아 있는 인스턴스 실측 (content/dashboard.js) =====
    // 데이터: s1 figteam-console 의 읽기 전용 /console/api/status (20초마다 수집)
    const DASH = { snap: null, err: null, timer: null };
    const DASH_CLOUD = { onprem: ['온프렘', 'cloud-onprem'], openstack: ['OpenStack', 'cloud-onprem'], kt: ['KT Cloud', 'cloud-kt'], aws: ['AWS', 'cloud-aws'] };
    const DASH_TYPE = { web: '웹/API', gw: '보안/관문', daemon: '상시데몬', data: '데이터/DR' };
    const DASH_ORDER = ['kt', 'onprem', 'openstack', 'aws'];

    function dashFmtBytes(b) { if (b == null) return '-'; const g = b / 1073741824; return g >= 10 ? g.toFixed(0) + ' GB' : g.toFixed(1) + ' GB'; }
    function dashFmtDur(s) {
      if (s == null) return '-';
      const d = Math.floor(s / 86400), h = Math.floor((s % 86400) / 3600), m = Math.floor((s % 3600) / 60);
      return d ? d + '일 ' + h + '시간' : h ? h + '시간 ' + m + '분' : m + '분';
    }
    function dashPct(a, b) { return a != null && b ? Math.round(100 * a / b) : null; }

    async function dashLoad() {
      try {
        const r = await fetch('/console/api/status', { cache: 'no-store' });
        if (!r.ok) throw new Error('HTTP ' + r.status);
        DASH.snap = await r.json(); DASH.err = null;
      } catch (e) { DASH.err = e.message; }
      dashHeader();
      if (document.getElementById('view-dashboard').style.display !== 'none') dashRender();
    }
    function dashStart() {
      if (DASH.timer) return;
      dashLoad();
      DASH.timer = setInterval(dashLoad, 20000);
    }

    // 인스턴스 → 화면용 서비스 목록 (systemd 유닛 + k8s 파드)
    function dashServices(i) {
      const list = (i.units || []).map(u => {
        const m = (i.unit_meta || {})[u.unit] || {};
        const ok = u.state === 'active';
        return { kind: 'unit', type: m.type || 'daemon', typeName: DASH_TYPE[m.type] || '상시데몬', name: u.unit, desc: m.desc || '',
          ok: ok, stateText: ok ? 'Running' : (u.state || 'unknown'), since: u.since_s, uptimeHours: u.since_s ? u.since_s / 3600 : 0 };
      });
      (i.pods || []).forEach(p => {
        const sys = p.ns === 'kube-system' || p.ns === 'argocd';
        const data = /mysql|redis/.test(p.name);
        const start = p.start && p.start !== '<none>' ? Date.parse(p.start) : NaN;
        const since = isNaN(start) ? null : Math.max(0, Math.round((Date.now() - start) / 1000));
        list.push({ kind: 'pod', type: data ? 'data' : sys ? 'daemon' : 'web', typeName: data ? '데이터/DR' : sys ? '상시데몬' : '웹/API',
          name: p.name, desc: '파드 · ' + p.ns, ok: p.phase === 'Running' || p.phase === 'Succeeded', stateText: p.phase,
          since: since, uptimeHours: since ? since / 3600 : 0, hide: p.phase === 'Succeeded' });
      });
      return list.filter(s => !s.hide);
    }
    function dashSort(list) {
      const m = typeof currentSortMode === 'string' ? currentSortMode : 'type';
      list.sort((a, b) => {
        if (m === 'type') return a.typeName.localeCompare(b.typeName, 'ko') || a.name.localeCompare(b.name);
        if (m === 'service') return a.desc.localeCompare(b.desc, 'ko') || a.name.localeCompare(b.name);
        if (m === 'resource') return (a.ok - b.ok) || a.name.localeCompare(b.name);   // 이상 있는 것 먼저
        if (m === 'runtime') return (b.uptimeHours || 0) - (a.uptimeHours || 0);
        return a.name.localeCompare(b.name);
      });
      return list;
    }

    // 이름만 있는 대상(정책상 접속·수집 없음, 예: s1)은 카드·집계에서 뺀다
    function dashNameOnly(i) { return !!i.disabled && i.alive == null; }
    function dashInstances() {
      const items = ((DASH.snap && DASH.snap.instances) || []).filter(i => !dashNameOnly(i));
      return items.slice().sort((a, b) => DASH_ORDER.indexOf(a.area) - DASH_ORDER.indexOf(b.area));
    }

    function dashRender() {
      const grid = document.getElementById('matrix-5col-grid');
      if (!grid) return;
      grid.classList.add('dash-live');
      if (!DASH.snap) {
        grid.innerHTML = '<div class="dash-msg">' + (DASH.err ? '실측 상태를 불러오지 못했습니다 (' + cfgEsc(DASH.err) + '). s1 통합 콘솔 서비스(/console/api/status)를 확인하세요.' : '실측 상태를 불러오는 중…') + '</div>';
        return;
      }
      const filter = typeof currentServiceFilter === 'string' ? currentServiceFilter : 'all';
      grid.innerHTML = dashInstances().map(i => {
        const c = DASH_CLOUD[i.area] || ['기타', ''];
        const all = dashServices(i);
        const list = dashSort(filter === 'all' ? all.slice() : all.filter(s => s.type === filter));
        const okN = all.filter(s => s.ok).length;
        const alive = i.alive === true, apiOnly = !!i.disabled;
        const cpuPct = i.cpu_pct, memPct = dashPct(i.mem_used, i.mem_total), diskPct = dashPct(i.disk_used, i.disk_total);
        const usedCpu = cpuPct != null && i.nproc ? (cpuPct * i.nproc / 100).toFixed(2) : '-';
        const badge = !alive ? '<span class="dash-badge dash-down">응답 없음</span>'
          : apiOnly ? '<span class="dash-badge dash-api">API 응답</span>'
          : okN === all.length ? '<span class="badge-running" style="font-size:10px;padding:2px 6px;">정상</span>'
          : '<span class="dash-badge dash-warn">점검 ' + (all.length - okN) + '</span>';
        const meters = apiOnly ? '<div class="dash-msg dash-msg-small">' + cfgEsc(i.disabled) + '<br>응답 ' + (i.latency_ms != null ? i.latency_ms + 'ms' : '-') + '</div>' :
          dashMeter('CPU', 'cpu', usedCpu + ' vCPU', (i.nproc || '-') + ' vCPU', cpuPct) +
          dashMeter('RAM', 'ram', dashFmtBytes(i.mem_used), dashFmtBytes(i.mem_total), memPct) +
          '<div class="hero-sub-stats">' +
            '<div class="hero-stat-pill"><span class="stat-k">디스크:</span><strong class="stat-v">' + (diskPct != null ? diskPct + '%' : '-') + '</strong></div>' +
            '<div class="hero-stat-pill"><span class="stat-k">가동:</span><strong class="stat-v">' + dashFmtDur(i.uptime_s) + '</strong></div>' +
            '<div class="hero-stat-pill"><span class="stat-k">서비스:</span><strong class="stat-v" style="color:' + (okN === all.length ? '#34d399' : '#fbbf24') + '">' + okN + '/' + all.length + '</strong></div>' +
          '</div>';
        const rows = !alive ? '<div class="dash-msg dash-msg-small">' + cfgEsc(i.error || '응답이 없습니다') + '</div>'
          : list.length === 0 ? '<div class="dash-msg dash-msg-small">' + (apiOnly ? '세부 수집은 연결 후 표시됩니다.' : '해당 유형의 서비스가 없습니다.') + '</div>'
          : list.map(s =>
            '<div class="compact-service-row" onclick="openDetailModal(\'' + cfgEsc(i.id) + '\', \'' + cfgEsc(s.name) + '\')">' +
              '<div class="svc-row-top"><div class="svc-row-left"><span class="type-badge type-' + s.type + '">' + s.typeName + '</span>' +
              '<span class="svc-row-name" title="' + cfgEsc(s.name) + '">' + cfgEsc(s.name) + '</span></div>' +
              '<span class="' + (s.ok ? 'badge-running' : 'dash-badge dash-down') + '" style="font-size:9px;padding:1px 5px;">' + cfgEsc(s.stateText) + '</span></div>' +
              '<div class="svc-row-bot"><span>' + cfgEsc(s.desc) + '</span><span style="color:#94a3b8;">' + dashFmtDur(s.since) + '</span></div></div>').join('');
        return '<div class="inst-grid-card' + (alive ? '' : ' dash-card-down') + '" id="card-' + cfgEsc(i.id) + '">' +
          '<div class="inst-grid-card-head"><div class="inst-head-title-wrap"><div style="display:flex;align-items:center;gap:6px;">' +
          '<span class="cloud-tag ' + c[1] + '">' + c[0] + '</span><span class="inst-card-title">' + cfgEsc(i.name) + '</span></div>' +
          '<div class="inst-card-ip">' + cfgEsc(i.host || '') + (i.latency_ms != null ? ' · 응답 ' + i.latency_ms + 'ms' : '') + '</div></div>' + badge + '</div>' +
          '<div class="inst-resource-hero">' + meters + '</div>' +
          '<div class="compact-service-list">' + rows + '</div>' +
          '<div class="inst-card-footer"><button type="button" class="open-modal-btn" onclick="openDetailModal(\'' + cfgEsc(i.id) + '\', null)">상세 보기</button>' +
          (apiOnly || !alive ? '' : '<button type="button" class="open-modal-btn" onclick="dashOpenConsole(\'' + cfgEsc(i.id) + '\')">콘솔 열기</button>') + '</div></div>';
      }).join('');
    }
    function dashMeter(label, cls, used, total, pct) {
      const p = pct == null ? 0 : pct;
      return '<div class="hero-meter-row"><div class="meter-head"><div class="meter-label-wrap"><span class="meter-badge ' + cls + '-badge">' + label + '</span>' +
        '<strong class="meter-val-used ' + cls + '-used">' + used + '</strong><span class="meter-val-total">/ ' + total + '</span>' +
        '<span class="meter-pct ' + cls + '-pct">' + (pct == null ? '-' : pct + '%') + '</span></div>' +
        '<div class="meter-free-wrap"><span class="free-k">여유:</span><strong class="free-v">' + (pct == null ? '-' : (100 - p) + '%') + '</strong></div></div>' +
        '<div class="meter-gauge-track"><div class="meter-gauge-fill ' + cls + '-fill" style="width:' + p + '%;' + (p >= 85 ? 'background:#ef4444;' : '') + '"></div></div></div>';
    }

    function dashModal(id, svcName) {
      const i = dashInstances().find(x => x.id === id);
      if (!i) return;
      const c = DASH_CLOUD[i.area] || ['기타', ''];
      const all = dashSort(dashServices(i));
      document.getElementById('modal-cloud-tag').className = 'cloud-tag ' + c[1];
      document.getElementById('modal-cloud-tag').textContent = c[0];
      document.getElementById('modal-title').textContent = i.name + ' 실측 상세';
      document.getElementById('modal-ip-text').textContent = (i.host || '') + ' · ' + cfgEsc(i.desc || '');
      const spec = [['상태', i.alive === true ? '응답' : i.alive === false ? '응답 없음' : '-'], ['CPU', i.cpu_pct != null ? i.cpu_pct + '% (' + i.nproc + ' vCPU)' : '-'],
        ['메모리', dashFmtBytes(i.mem_used) + ' / ' + dashFmtBytes(i.mem_total)], ['디스크', dashFmtBytes(i.disk_used) + ' / ' + dashFmtBytes(i.disk_total)],
        ['load 1분', i.load1 != null ? i.load1 : '-'], ['가동 시간', dashFmtDur(i.uptime_s)], ['응답 시간', i.latency_ms != null ? i.latency_ms + 'ms' : '-'],
        ['수집 시각', DASH.snap.collected_at ? new Date(DASH.snap.collected_at * 1000).toLocaleTimeString('ko-KR', { hour12: false }) : '-']];
      document.getElementById('modal-body').innerHTML =
        '<div class="spec-grid">' + spec.map(s => '<div class="spec-item"><span class="spec-k">' + s[0] + '</span><span class="spec-v">' + cfgEsc(String(s[1])) + '</span></div>').join('') + '</div>' +
        (i.error ? '<p class="wk-error" style="margin-top:10px">' + cfgEsc(i.error) + '</p>' : '') +
        '<div class="cfg-table-wrap" style="margin-top:12px"><table class="cfg-table"><thead><tr><th>종류</th><th>이름</th><th>설명</th><th>상태</th><th>실행 시간</th></tr></thead><tbody>' +
        all.map(s => '<tr' + (s.name === svcName ? ' style="background:rgba(37,99,235,.15)"' : '') + '><td>' + s.typeName + '</td><td><code class="cfg-ic">' + cfgEsc(s.name) + '</code></td><td>' + cfgEsc(s.desc) +
          '</td><td style="color:' + (s.ok ? '#34d399' : '#fca5a5') + '">' + cfgEsc(s.stateText) + '</td><td>' + dashFmtDur(s.since) + '</td></tr>').join('') +
        '</tbody></table></div>' +
        (i.disabled || i.alive !== true ? '' : '<div class="wk-bar wk-bar-inline" style="margin-top:12px"><button type="button" class="wk-btn wk-primary" onclick="dashOpenConsole(\'' + cfgEsc(i.id) + '\')">통합 터미널로 접속</button></div>');
      document.getElementById('modal-backdrop').style.display = 'flex';
    }
    function dashOpenConsole(id) {   // 본문을 콘솔로 바꾸고 그 인스턴스에 바로 접속
      const mb = document.getElementById('modal-backdrop'); if (mb) mb.style.display = 'none';
      CS.pending = id; switchView('console');
    }

    // 상단 배지: 영역별 살아 있는 인스턴스 수
    function dashHeader() {
      const box = document.querySelector('.header-infra-status');
      if (!box) return;
      if (!DASH.snap) { box.innerHTML = '<div class="infra-badge-item"><span class="infra-badge-name">실측</span><span class="infra-badge-state ' + (DASH.err ? 'state-red' : '') + '">' + (DASH.err ? '연결 실패' : '수집 중') + '</span></div>'; return; }
      const groups = [['kt', 'KT Cloud', ['kt']], ['os', '온프렘·OpenStack', ['onprem', 'openstack']], ['aws', 'AWS', ['aws']]];
      box.innerHTML = groups.map(g => {
        const xs = DASH.snap.instances.filter(i => g[2].indexOf(i.area) >= 0 && !dashNameOnly(i));
        const up = xs.filter(i => i.alive === true).length;
        const bad = xs.some(i => i.alive === true && (i.units || []).some(u => u.state !== 'active'));
        return '<div class="infra-badge-item"><span class="infra-badge-name">' + g[1] + '</span><span class="infra-badge-state ' +
          (up < xs.length ? 'state-red' : bad ? 'state-yellow' : 'state-green') + '">' + up + '/' + xs.length + '</span></div>';
      }).join('') + '<div class="infra-badge-item"><span class="infra-badge-name">수집</span><span class="infra-badge-state">' +
        new Date(DASH.snap.collected_at * 1000).toLocaleTimeString('ko-KR', { hour12: false }) + '</span></div>';
    }

    window.addEventListener('load', () => setTimeout(dashStart, 200));
