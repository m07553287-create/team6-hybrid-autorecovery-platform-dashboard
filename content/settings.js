    // ===== [설정] 화면: content/settings_guide.py → #cfg-data(JSON) 렌더러 =====
    // 원본 데이터는 content/settings_guide.py, 이 파일은 content/settings.js (tools/build_settings.py 가 주입)
    const CFG = { data: null, page: null, area: null, codes: [] };
    const CLOUD_NAME = { onprem: '온프렘', openstack: 'OpenStack', kt: 'KT Cloud', aws: 'AWS' };
    const STATUS_NAME = { live: '실측', design: '설계 · 미적용', nolook: '미실측' };
    const CAT_ORDER = ['설치', '적용', '조회', '검증'];

    function cfgEsc(t) {
      return String(t == null ? '' : t)
        .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
    }
    // `코드` 와 **굵게** 만 지원 (역슬래시 없는 분할 방식)
    function cfgFmt(t) {
      return cfgEsc(t).split('`').map((seg, i) => {
        if (i % 2 === 1) return '<code class="cfg-ic">' + seg + '</code>';
        return seg.split('**').map((s, j) => (j % 2 === 1 ? '<b>' + s + '</b>' : s)).join('');
      }).join('');
    }
    function cfgCode(code, label, cat) {
      const idx = CFG.codes.push(code) - 1;
      return '<div class="cfg-code">' +
        '<div class="cfg-code-head">' +
          (cat ? '<span class="cfg-cat cfg-cat-' + CAT_ORDER.indexOf(cat) + '">' + cfgEsc(cat) + '</span>' : '') +
          '<span class="cfg-code-label">' + cfgEsc(label || '') + '</span>' +
          '<button type="button" class="cfg-copy" onclick="cfgCopy(' + idx + ', this)">복사</button>' +
        '</div><pre>' + cfgEsc(code) + '</pre></div>';
    }
    function cfgCopy(idx, btn) {
      const text = CFG.codes[idx];
      const done = () => { btn.textContent = '복사됨'; setTimeout(() => { btn.textContent = '복사'; }, 1200); };
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(text).then(done, () => cfgCopyFallback(text, done));
      } else { cfgCopyFallback(text, done); }
    }
    function cfgCopyFallback(text, done) {
      const ta = document.createElement('textarea');
      ta.value = text; document.body.appendChild(ta); ta.select();
      try { document.execCommand('copy'); done(); } catch (e) {}
      ta.remove();
    }
    function cfgBadge(status) {
      if (!status) return '';
      return '<span class="cfg-badge cfg-st-' + status + '">' + cfgEsc(STATUS_NAME[status] || status) + '</span>';
    }
    function cfgTable(head, rows, cls) {
      return '<div class="cfg-table-wrap"><table class="cfg-table ' + (cls || '') + '"><thead><tr>' +
        head.map(h => '<th>' + cfgEsc(h) + '</th>').join('') + '</tr></thead><tbody>' +
        rows.map(r => '<tr>' + r.map(c => '<td>' + cfgFmt(c) + '</td>').join('') + '</tr>').join('') +
        '</tbody></table></div>';
    }

    function cfgInit() {
      if (!CFG.data) {
        const el = document.getElementById('cfg-data');
        if (!el) return;
        CFG.data = JSON.parse(el.textContent);
        cfgRenderNav();
      }
      const h = (location.hash || '').split('/');
      if (h[0] === '#cfg' && CFG.data.pages[h[1]]) cfgOpen(h[1], h[2], true);
      else if (!CFG.page) cfgOpen('overview', null, true);
    }

    function cfgRenderNav() {
      const nav = document.getElementById('cfg-nav');
      let html = '<div class="cfg-nav-top"><div class="cfg-nav-title">인스턴스 설정 · 구성 가이드</div>' +
        '<div class="cfg-nav-sub">실측 ' + cfgEsc(CFG.data.measured) + ' · 명령어 중심</div></div>';
      CFG.data.nav.forEach(g => {
        html += '<div class="sidebar-section-title">' +
          (g.cloud ? '<span class="cfg-dot cfg-c-' + g.cloud + '"></span>' : '') + cfgEsc(g.title) + '</div>';
        g.items.forEach(it => {
          const p = CFG.data.pages[it[0]] || {};
          html += '<button type="button" class="menu-item-btn" data-page="' + it[0] + '" onclick="cfgOpen(\'' + it[0] + '\')">' +
            '<div class="menu-item-name"><span>' + cfgEsc(it[1]) + '</span>' +
            (p.status && p.status !== 'live' ? cfgBadge(p.status) : '<span>➔</span>') + '</div>' +
            '<div class="menu-item-desc">' + cfgEsc(it[2]) + '</div></button>';
        });
      });
      nav.innerHTML = html;
    }

    function cfgOpen(pageId, areaId, keepHash) {
      const p = CFG.data.pages[pageId];
      if (!p) return;
      CFG.page = pageId;
      CFG.codes = [];
      document.querySelectorAll('#cfg-nav .menu-item-btn').forEach(b => {
        b.classList.toggle('active', b.getAttribute('data-page') === pageId);
      });
      const body = document.getElementById('manual-body-content');
      body.innerHTML = p.kind === 'instance' ? cfgInstance(p, areaId) : cfgDoc(p);
      body.scrollTop = 0;
      if (!keepHash || areaId) history.replaceState(null, '', '#cfg/' + pageId + (CFG.area && p.kind === 'instance' ? '/' + CFG.area : ''));
    }

    function cfgHeader(p) {
      return '<div class="manual-header">' +
        '<div class="manual-title"><span>' + cfgEsc(p.title) + '</span>' +
          (p.cloud ? '<span class="cfg-cloud cfg-c-' + p.cloud + '">' + cfgEsc(CLOUD_NAME[p.cloud]) + '</span>' : '') +
          '<span class="manual-tag">' + cfgEsc(p.tag || '') + '</span>' + cfgBadge(p.status) + '</div>' +
        (p.steps ? '<div class="cfg-steps-line">선행 순서: <b>' + cfgEsc(p.steps) + '</b> <a href="javascript:void(0)" onclick="cfgOpen(\'steps\')">순서표 보기</a></div>' : '') +
        '<div class="manual-desc">' + cfgFmt(p.desc) + '</div></div>';
    }

    function cfgInstance(p, areaId) {
      const area = p.areas.find(a => a.id === areaId) || p.areas[0];
      CFG.area = area.id;
      let html = cfgHeader(p);
      html += '<div class="spec-grid">' + p.specs.map(s =>
        '<div class="spec-item"><span class="spec-k">' + cfgEsc(s[0]) + '</span><span class="spec-v">' + cfgEsc(s[1]) + '</span></div>').join('') + '</div>';
      html += '<div class="cfg-area-tabs">' + p.areas.map(a =>
        '<button type="button" class="cfg-area-tab' + (a.id === area.id ? ' active' : '') + '" onclick="cfgOpen(\'' + CFG.page + '\', \'' + a.id + '\')">' +
        cfgEsc(a.name) + (a.status && a.status !== p.status ? ' ' + cfgBadge(a.status) : '') + '</button>').join('') + '</div>';
      html += cfgArea(area);
      return html;
    }

    function cfgArea(a) {
      const secs = [];
      if (a.design && a.design.length) secs.push(['설계', '<ul class="cfg-list">' + a.design.map(d => '<li>' + cfgFmt(d) + '</li>').join('') + '</ul>']);
      if (a.config && a.config.length) secs.push(['설정', a.config.map(c => cfgCode(c.code, c.label)).join('')]);
      if (a.commands && a.commands.length) {
        const sorted = a.commands.slice().sort((x, y) => CAT_ORDER.indexOf(x.cat) - CAT_ORDER.indexOf(y.cat));
        secs.push(['명령어', sorted.map(c => cfgCode(c.code, c.label, c.cat)).join('')]);
      }
      if (a.verify && a.verify.length) secs.push(['검증', a.verify.map(v =>
        cfgCode(v.code, v.label, '검증') + '<div class="cfg-expect">기대 결과 · ' + cfgFmt(v.expect) + '</div>').join('')]);
      if (a.trouble && a.trouble.length) secs.push(['오류 시 확인', cfgTable(['증상', '의심 변수·영역', '확인 명령', '조치'], a.trouble, 'cfg-trouble')]);
      const chips = '<div class="cfg-chips">' + secs.map((s, i) =>
        '<a href="javascript:void(0)" class="cfg-chip" onclick="document.getElementById(\'cfg-sec-' + i + '\').scrollIntoView({behavior:\'smooth\',block:\'start\'})">' + s[0] + '</a>').join('') + '</div>';
      return chips + secs.map((s, i) =>
        '<section class="manual-card-box" id="cfg-sec-' + i + '"><div class="box-title">' + s[0] + '</div>' + s[1] + '</section>').join('');
    }

    function cfgDoc(p) {
      let html = cfgHeader(p);
      p.blocks.forEach(b => {
        if (b.type === 'h') html += '<h3 class="cfg-h">' + cfgEsc(b.text) + '</h3>';
        else if (b.type === 'code') html += cfgCode(b.code, b.label);
        else if (b.type === 'table') html += cfgTable(b.head, b.rows);
        else if (b.type === 'vars') html += cfgTable(['변수', '값 (실측)', '사용처', '바뀌면 확인'], CFG.data.vars, 'cfg-vars');
        else if (b.type === 'legend') html += '<div class="cfg-legend">' +
          cfgBadge('live') + ' 현재 구성을 직접 조회해 확인한 값 ' + cfgBadge('design') + ' 적용 전 설계안(계획·영향 범위 확인 후 적용) ' +
          cfgBadge('nolook') + ' 접속 불가로 외부 응답·문서만 확인</div>';
        else if (b.type === 'steps') html += cfgSteps();
        else if (b.type === 'troubleall') html += cfgTroubleAll();
      });
      return html;
    }

    function cfgSteps() {
      return '<div class="cfg-step-list">' + CFG.data.steps.map(s => {
        const p = CFG.data.pages[s.page] || {};
        return '<div class="cfg-step">' +
          '<div class="cfg-step-no">' + cfgEsc(s.no) + '</div>' +
          '<div class="cfg-step-body">' +
            '<div class="cfg-step-title">' + cfgEsc(s.title) + ' <span class="cfg-step-where">' + cfgEsc(s.where) + '</span></div>' +
            '<div class="cfg-step-why">' + cfgFmt(s.why) + '</div>' +
            cfgCode(s.gate, '통과 조건', '검증') +
            '<a href="javascript:void(0)" class="cfg-step-link" onclick="cfgOpen(\'' + s.page + '\', \'' + s.area + '\')">' + cfgEsc(p.title || s.page) + ' 페이지로 ➔</a>' +
          '</div></div>';
      }).join('') + '</div>';
    }

    function cfgTroubleAll() {
      const rows = [];
      Object.keys(CFG.data.pages).forEach(id => {
        const p = CFG.data.pages[id];
        if (p.kind !== 'instance') return;
        p.areas.forEach(a => (a.trouble || []).forEach(t => rows.push([p.title + ' › ' + a.name, t[1], t[0], t[2], t[3]])));
      });
      return '<input type="search" class="cfg-search" placeholder="증상·변수·명령어로 거르기 (예: 6443, MTU, sg-db)" oninput="cfgFilterTable(this)">' +
        cfgTable(['위치', '변수·영역', '증상', '확인 명령', '조치'], rows, 'cfg-trouble cfg-filterable');
    }
    function cfgFilterTable(inp) {
      const q = inp.value.trim().toLowerCase();
      document.querySelectorAll('.cfg-filterable tbody tr').forEach(tr => {
        tr.style.display = !q || tr.textContent.toLowerCase().indexOf(q) >= 0 ? '' : 'none';
      });
    }
