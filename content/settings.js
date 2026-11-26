    // ===== [설정] 화면: 보는 기준(렌즈) > 대분류 > 중분류 > 설명 =====
    // 원본: content/settings_guide.py (데이터) · content/settings.js (이 파일) — tools/build_settings.py 가 주입
    const CFG = { data: null, lens: null, major: null, minor: null, codes: [] };
    const CLOUD_NAME = { onprem: '온프렘', openstack: 'OpenStack', kt: 'KT Cloud', aws: 'AWS' };
    const STATUS_NAME = { live: '실측', design: '설계 · 미적용', nolook: '미실측' };
    const CAT_ORDER = ['설치', '적용', '조회', '검증'];
    const LENSES = [
      { id: 'inst', name: '인스턴스 기준', hint: '서버 하나를 골라 그 안의 서비스 영역을 봅니다' },
      { id: 'svc', name: '서비스 기준', hint: '보안·웹 같은 영역을 골라 맡은 인스턴스를 봅니다' },
      { id: 'step', name: '진행 순서', hint: '처음 구성할 때 지켜야 하는 S0~S12 순서' },
      { id: 'ref', name: '참고', hint: '변수표, KT 확장 설계, 오류 색인' }
    ];

    // ---------- 공통 조각 ----------
    function cfgEsc(t) {
      return String(t == null ? '' : t)
        .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
    }
    function cfgFmt(t) {
      return cfgEsc(t).split('`').map((seg, i) => {
        if (i % 2 === 1) return '<code class="cfg-ic">' + cfgLink(seg) + '</code>';
        return cfgLink(seg).split('**').map((s, j) => (j % 2 === 1 ? '<b>' + s + '</b>' : s)).join('');
      }).join('');
    }
    function cfgCode(code, label, cat) {
      const idx = CFG.codes.push(code) - 1;
      return '<div class="cfg-code"><div class="cfg-code-head">' +
        (cat ? '<span class="cfg-cat cfg-cat-' + CAT_ORDER.indexOf(cat) + '">' + cfgEsc(cat) + '</span>' : '') +
        '<span class="cfg-code-label">' + cfgLink(cfgEsc(label || '')) + '</span>' +
        '<button type="button" class="cfg-copy" onclick="cfgCopy(' + idx + ', this)">복사</button>' +
        '</div><pre>' + cfgLink(cfgEsc(code)) + '</pre></div>';
    }

    // ---------- *.sh 링크와 스크립트 보기 ----------
    // 이미 이스케이프된 텍스트 안의 스크립트 경로·파일명을 링크로 바꾼다 (긴 경로부터 맞춘다)
    let CFG_SH_RE = null, CFG_SH_KEY = {};
    function cfgLink(html) {
      const list = (CFG.data && CFG.data.scripts) || [];
      if (!list.length) return html;
      if (!CFG_SH_RE) {
        const keys = [];
        list.forEach((s, i) => s.keys.forEach(k => { keys.push(k); CFG_SH_KEY[k] = i; }));
        keys.sort((a, b) => b.length - a.length);
        const alts = keys.map(k => k.split('.').join('[.]')).join('|');
        CFG_SH_RE = new RegExp('(^|[^A-Za-z0-9_./~-])(' + alts + ')(?![A-Za-z0-9_])', 'g');
      }
      return html.replace(CFG_SH_RE, (m, pre, key) => {
        const s = list[CFG_SH_KEY[key]];
        const tip = cfgEsc(s.host + ' ' + s.path + (s.url ? ' (새 창)' : ' 내용 보기'));
        if (s.url) return pre + '<a class="cfg-sh cfg-sh-ext" href="' + cfgEsc(s.url) + '" target="_blank" rel="noopener" title="' + tip + '">' + key + '</a>';
        return pre + '<a class="cfg-sh" href="scripts/' + cfgEsc(s.file) + '" title="' + tip + '" onclick="cfgViewScript(' + CFG_SH_KEY[key] + '); return false;">' + key + '</a>';
      });
    }

    function cfgViewer() {
      let dlg = document.getElementById('cfg-viewer');
      if (dlg) return dlg;
      dlg = document.createElement('dialog');
      dlg.id = 'cfg-viewer';
      dlg.setAttribute('aria-labelledby', 'cfg-viewer-title');
      dlg.addEventListener('click', e => { if (e.target === dlg) dlg.close(); });
      document.body.appendChild(dlg);
      return dlg;
    }

    function cfgViewScript(i) {
      const s = CFG.data.scripts[i];
      const dlg = cfgViewer();
      const used = [];
      CFG.data.instances.forEach(pid => cfgPage(pid).areas.forEach(a => {
        const txt = JSON.stringify(a);
        if (s.keys.some(k => new RegExp('(^|[^A-Za-z0-9_./~-])' + k.split('.').join('[.]') + '(?![A-Za-z0-9_])').test(txt))) used.push([pid, a.id, cfgPage(pid).short + ' / ' + a.name]);
      }));
      dlg.innerHTML =
        '<div class="cfg-vw-head">' +
          '<div class="cfg-vw-meta"><span class="cfg-vw-host">' + cfgEsc(s.host) + '</span>' + cfgBadge(s.status) + '</div>' +
          '<h2 id="cfg-viewer-title" class="cfg-vw-title">' + cfgEsc(s.path) + '</h2>' +
          '<div class="cfg-vw-actions">' +
            '<button type="button" class="cfg-copy" id="cfg-vw-copy" disabled>복사</button>' +
            '<a class="cfg-copy" href="scripts/' + cfgEsc(s.file) + '" target="_blank" rel="noopener">파일 받기</a>' +
            '<button type="button" class="cfg-copy" onclick="document.getElementById(&quot;cfg-viewer&quot;).close()">닫기</button>' +
          '</div></div>' +
        (used.length ? '<div class="cfg-vw-used">이 스크립트가 나오는 곳: ' + used.map(u =>
          '<a href="javascript:void(0)" onclick="document.getElementById(&quot;cfg-viewer&quot;).close();' + cfgGo('inst', u[0], u[1]) + '">' + cfgEsc(u[2]) + '</a>').join(', ') + '</div>' : '') +
        '<pre class="cfg-vw-body" id="cfg-vw-body">불러오는 중…</pre>' +
        '<p class="cfg-vw-note">' + (s.status === 'design'
          ? '이 가이드의 설계안에서 만든 파일입니다. 아직 서버에 적용되지 않았습니다.'
          : '서버에서 읽어 온 사본입니다(실측 ' + cfgEsc(CFG.data.measured) + '). 원본을 고치면 이 사본도 다시 받아야 합니다.') + '</p>';
      if (!dlg.open) dlg.showModal();
      fetch('scripts/' + s.file, { cache: 'no-store' })
        .then(r => { if (!r.ok) throw new Error('HTTP ' + r.status); return r.text(); })
        .then(text => {
          const body = document.getElementById('cfg-vw-body');
          body.innerHTML = text.replace(/\n$/, '').split('\n').map(l => '<span class="cfg-ln">' + cfgLink(cfgEsc(l)) + '</span>').join('\n');
          const btn = document.getElementById('cfg-vw-copy');
          btn.disabled = false;
          btn.onclick = () => { const idx = CFG.codes.push(text) - 1; cfgCopy(idx, btn); };
        })
        .catch(err => {
          document.getElementById('cfg-vw-body').textContent =
            '파일을 불러오지 못했습니다 (' + err.message + '). 스크립트 사본은 figteam.ktci5.kr 배포본의 scripts/ 경로에서 제공합니다.';
        });
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
    function cfgGo(lens, major, minor) {
      return 'cfgSelect(&quot;' + lens + '&quot;,&quot;' + (major || '') + '&quot;,&quot;' + (minor || '') + '&quot;)';
    }
    function cfgDomain(id) { return CFG.data.domains.find(d => d.id === id); }
    function cfgPage(id) { return CFG.data.pages[id]; }
    function cfgAreaOf(pid, aid) { const p = cfgPage(pid); return p && p.areas.find(a => a.id === aid); }

    // ---------- 목록 만들기 ----------
    function cfgMajors(lens) {
      const d = CFG.data;
      if (lens === 'inst') return d.instances.map(pid => {
        const p = cfgPage(pid);
        return { id: pid, name: p.title.split(' (')[0], sub: CLOUD_NAME[p.cloud] + ' / ' + p.tag, cloud: p.cloud, status: p.status };
      });
      if (lens === 'svc') return d.domains.map(dm => ({ id: dm.id, name: dm.name, sub: dm.desc, count: cfgMinors('svc', dm.id).length }));
      if (lens === 'step') return [{ id: 'all', name: '처음부터 끝까지', sub: 'S0 접속 경로 확보부터 S12 KT 워커 조인까지' }];
      return d.reference.map(r => ({ id: r[0], name: r[1], sub: cfgPage(r[0]).tag }));
    }
    function cfgMinors(lens, major) {
      const d = CFG.data;
      if (lens === 'inst') {
        const p = cfgPage(major);
        return p ? p.areas.map(a => ({ id: a.id, name: a.name, sub: a.domains.map(x => cfgDomain(x).name).join(', '), status: a.status !== p.status ? a.status : '' })) : [];
      }
      if (lens === 'svc') {
        const out = [];
        d.instances.forEach(pid => {
          const p = cfgPage(pid);
          p.areas.forEach(a => {
            if (a.domains.indexOf(major) >= 0) out.push({ id: pid + '.' + a.id, name: p.short, sub: a.name, cloud: p.cloud, status: a.status === 'live' ? '' : a.status });
          });
        });
        return out;
      }
      if (lens === 'step') return d.steps.map(s => ({ id: s.no, name: s.no + '  ' + s.title, sub: s.where }));
      return [];
    }

    // ---------- 선택·상태 ----------
    function cfgInit() {
      if (!CFG.data) {
        const el = document.getElementById('cfg-data');
        if (!el) return;
        CFG.data = JSON.parse(el.textContent);
      }
      const h = (location.hash || '').split('/');
      if (h[0] === '#cfg' && h.length > 1) {
        if (['inst', 'svc', 'step', 'ref'].indexOf(h[1]) >= 0) return cfgSelect(h[1], h[2], h[3], true);
        if (cfgPage(h[1])) {   // 예전 주소(#cfg/inst-ktw1/join) 호환
          const p = cfgPage(h[1]);
          return p.kind === 'instance' ? cfgSelect('inst', h[1], h[2], true) : cfgSelect('ref', h[1], '', true);
        }
      }
      if (!CFG.lens) { const df = CFG.data.default; cfgSelect(df.lens, df.major, df.minor, true); }
    }

    function cfgSelect(lens, major, minor, fromHash) {
      if (!CFG.data) return;
      const majors = cfgMajors(lens);
      if (!majors.find(m => m.id === major)) {
        major = lens === CFG.lens || !CFG.lens ? majors[0].id : cfgCarryMajor(lens);
      }
      const minors = cfgMinors(lens, major);
      if (minors.length && !minors.find(m => m.id === minor)) minor = cfgCarryMinor(lens, major, minors);
      CFG.lens = lens; CFG.major = major; CFG.minor = minor || '';
      cfgRenderNav();
      cfgRenderBody();
      const hash = '#cfg/' + lens + '/' + major + (CFG.minor ? '/' + CFG.minor : '');
      if (location.hash !== hash) history.replaceState(null, '', hash);
    }
    // 렌즈를 바꿔도 보던 자리를 최대한 이어서 보여준다
    function cfgCarryMajor(lens) {
      const cur = cfgCurrentArea();
      if (cur && lens === 'inst') return cur.pid;
      if (cur && lens === 'svc') return cur.area.domains[0];
      return cfgMajors(lens)[0].id;
    }
    function cfgCarryMinor(lens, major, minors) {
      const cur = cfgCurrentArea();
      if (cur && lens === 'inst' && major === cur.pid) return cur.area.id;
      if (cur && lens === 'svc') { const k = cur.pid + '.' + cur.area.id; if (minors.find(m => m.id === k)) return k; }
      if (cur && lens === 'step') { const s = CFG.data.steps.find(x => x.page === cur.pid && x.area === cur.area.id); if (s) return s.no; }
      return minors[0].id;
    }
    function cfgCurrentArea() {
      if (CFG.lens === 'inst') { const a = cfgAreaOf(CFG.major, CFG.minor); return a ? { pid: CFG.major, area: a } : null; }
      if (CFG.lens === 'svc' && CFG.minor) { const k = CFG.minor.split('.'); const a = cfgAreaOf(k[0], k[1]); return a ? { pid: k[0], area: a } : null; }
      if (CFG.lens === 'step') { const s = CFG.data.steps.find(x => x.no === CFG.minor); const a = s && cfgAreaOf(s.page, s.area); return a ? { pid: s.page, area: a } : null; }
      return null;
    }

    // ---------- 왼쪽: 렌즈 · 매트릭스 · 대분류 · 중분류 ----------
    function cfgRenderNav() {
      const nav = document.getElementById('cfg-nav');
      const lens = LENSES.find(l => l.id === CFG.lens);
      let col1 = '<div class="cfg-col cfg-col-major">' +
        '<div class="cfg-lens" role="tablist" aria-label="보는 기준">' + LENSES.map(l =>
          '<button type="button" role="tab" aria-selected="' + (l.id === CFG.lens) + '" class="cfg-lens-btn' + (l.id === CFG.lens ? ' active' : '') +
          '" onclick="' + cfgGo(l.id, '', '') + '">' + cfgEsc(l.name) + '</button>').join('') + '</div>' +
        '<p class="cfg-lens-hint">' + cfgEsc(lens.hint) + '</p>' + cfgMatrix() +
        '<div class="cfg-col-head">대분류</div><div class="cfg-list-major">' +
        cfgMajors(CFG.lens).map(m =>
          '<button type="button" class="cfg-item' + (m.id === CFG.major ? ' active' : '') + '" onclick="' + cfgGo(CFG.lens, m.id, '') + '">' +
          '<span class="cfg-item-name">' + (m.cloud ? '<span class="cfg-dot cfg-c-' + m.cloud + '"></span>' : '') + cfgEsc(m.name) +
          (m.status && m.status !== 'live' ? ' ' + cfgBadge(m.status) : '') + (m.count ? '<span class="cfg-count">' + m.count + '</span>' : '') + '</span>' +
          '<span class="cfg-item-sub">' + cfgEsc(m.sub) + '</span></button>').join('') + '</div></div>';
      const minors = cfgMinors(CFG.lens, CFG.major);
      let col2 = '<div class="cfg-col cfg-col-minor"><div class="cfg-col-head">중분류</div>';
      if (minors.length) {
        col2 += '<div class="cfg-list-minor">' + minors.map(m =>
          '<button type="button" class="cfg-item cfg-item-minor' + (m.id === CFG.minor ? ' active' : '') + '" onclick="' + cfgGo(CFG.lens, CFG.major, m.id) + '">' +
          '<span class="cfg-item-name">' + (m.cloud ? '<span class="cfg-dot cfg-c-' + m.cloud + '"></span>' : '') + cfgEsc(m.name) +
          (m.status ? ' ' + cfgBadge(m.status) : '') + '</span>' +
          '<span class="cfg-item-sub">' + cfgEsc(m.sub) + '</span></button>').join('') + '</div>';
      } else {
        col2 += '<p class="cfg-empty">이 항목은 하위 구분 없이 오른쪽에 바로 펼쳐집니다.</p>';
      }
      col2 += '</div>';
      nav.innerHTML = col1 + col2;
    }

    // 인스턴스(행) × 서비스 영역(열). 행으로 읽으면 인스턴스 기준, 열로 읽으면 서비스 기준.
    function cfgMatrix() {
      const d = CFG.data;
      const cur = cfgCurrentArea();
      let html = '<div class="cfg-matrix" aria-label="인스턴스와 서비스 영역 지도"><div class="cfg-mx-row cfg-mx-headrow"><span class="cfg-mx-label"></span>' +
        d.domains.map(dm => '<span class="cfg-mx-col' + (CFG.lens === 'svc' && CFG.major === dm.id ? ' on' : '') + '" title="' + cfgEsc(dm.name) + '">' + cfgEsc(dm.short) + '</span>').join('') + '</div>';
      d.instances.forEach(pid => {
        const p = cfgPage(pid);
        const rowOn = CFG.lens === 'inst' && CFG.major === pid;
        html += '<div class="cfg-mx-row' + (rowOn ? ' on' : '') + '"><span class="cfg-mx-label">' + cfgEsc(p.short) + '</span>';
        d.domains.forEach(dm => {
          const areas = p.areas.filter(a => a.domains.indexOf(dm.id) >= 0);
          if (!areas.length) { html += '<span class="cfg-mx-cell"></span>'; return; }
          const colOn = CFG.lens === 'svc' && CFG.major === dm.id;
          const here = cur && cur.pid === pid && areas.some(a => a.id === cur.area.id);
          const go = CFG.lens === 'svc' ? cfgGo('svc', dm.id, pid + '.' + areas[0].id) : cfgGo('inst', pid, areas[0].id);
          html += '<button type="button" class="cfg-mx-cell has' + (colOn || rowOn ? ' lit' : '') + (here ? ' here' : '') +
            (p.status === 'design' ? ' design' : '') + '" title="' + cfgEsc(p.short + ' / ' + dm.name + ': ' + areas.map(a => a.name).join(', ')) +
            '" aria-label="' + cfgEsc(p.short + ' ' + dm.name) + '" onclick="' + go + '"><i></i></button>';
        });
        html += '</div>';
      });
      return html + '</div>';
    }

    // ---------- 오른쪽: 설명 ----------
    function cfgCrumb() {
      const lens = LENSES.find(l => l.id === CFG.lens).name;
      const major = (cfgMajors(CFG.lens).find(m => m.id === CFG.major) || {}).name;
      const minor = (cfgMinors(CFG.lens, CFG.major).find(m => m.id === CFG.minor) || {});
      const parts = [lens, major];
      if (minor.name) parts.push(CFG.lens === 'svc' ? minor.name + ' / ' + minor.sub : minor.name);
      return '<nav class="cfg-crumb" aria-label="현재 위치">' + parts.filter(Boolean).map(cfgEsc).join('<span class="cfg-crumb-sep">›</span>') + '</nav>';
    }

    function cfgRenderBody() {
      CFG.codes = [];
      const body = document.getElementById('manual-body-content');
      let html = cfgCrumb();
      if (CFG.lens === 'ref') {
        html += cfgDoc(cfgPage(CFG.major));
      } else if (CFG.lens === 'step') {
        const s = CFG.data.steps.find(x => x.no === CFG.minor);
        html += cfgStepHead(s) + cfgAreaView(s.page, s.area, false);
      } else {
        const cur = cfgCurrentArea();
        if (CFG.lens === 'svc') {
          const dm = cfgDomain(CFG.major);
          html += '<div class="cfg-domain-note"><b>' + cfgEsc(dm.name) + '</b> ' + cfgEsc(dm.desc) + '</div>';
        }
        html += cfgAreaView(cur.pid, cur.area.id, CFG.lens === 'inst');
      }
      html += cfgPager();
      body.innerHTML = html;
      body.scrollTop = 0;
    }

    function cfgAreaView(pid, aid, specsOpen) {
      const p = cfgPage(pid);
      const a = cfgAreaOf(pid, aid);
      const st = a.status || p.status;
      let html = '<div class="cfg-head">' +
        '<div class="cfg-head-line">' + '<span class="cfg-cloud cfg-c-' + p.cloud + '">' + cfgEsc(CLOUD_NAME[p.cloud]) + '</span>' +
          '<span class="cfg-head-inst">' + cfgEsc(p.title) + '</span><span class="manual-tag">' + cfgEsc(p.tag) + '</span></div>' +
        '<h2 class="cfg-head-title">' + cfgEsc(a.name) + ' ' + cfgBadge(st) + '</h2>' +
        '<div class="cfg-head-domains">이 영역은 ' + a.domains.map(x =>
          '<a href="javascript:void(0)" class="cfg-dom-link" onclick="' + cfgGo('svc', x, pid + '.' + aid) + '">' + cfgEsc(cfgDomain(x).name) + '</a>').join(', ') +
          ' 서비스에 속합니다' + (p.steps ? '. 진행 순서 ' + cfgEsc(p.steps) : '') + '.</div></div>';
      html += '<details class="cfg-inst"' + (specsOpen ? ' open' : '') + '><summary>인스턴스 개요와 사양</summary>' +
        '<p class="manual-desc">' + cfgFmt(p.desc) + '</p><div class="spec-grid">' + p.specs.map(s =>
          '<div class="spec-item"><span class="spec-k">' + cfgEsc(s[0]) + '</span><span class="spec-v">' + cfgEsc(s[1]) + '</span></div>').join('') + '</div></details>';
      return html + cfgArea(a);
    }

    function cfgStepHead(s) {
      return '<div class="cfg-head cfg-step-head"><div class="cfg-step-no">' + cfgEsc(s.no) + '</div><div>' +
        '<h2 class="cfg-head-title">' + cfgEsc(s.title) + '</h2>' +
        '<p class="manual-desc">' + cfgFmt(s.why) + ' 실행 위치: ' + cfgEsc(s.where) + '</p></div></div>' +
        cfgCode(s.gate, '통과 조건 (이게 나와야 다음 단계)', '검증');
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
        cfgCode(v.code, v.label, '검증') + '<div class="cfg-expect">기대 결과: ' + cfgFmt(v.expect) + '</div>').join('')]);
      if (a.trouble && a.trouble.length) secs.push(['오류 시 확인', cfgTable(['증상', '의심 변수·영역', '확인 명령', '조치'], a.trouble, 'cfg-trouble')]);
      const chips = '<div class="cfg-chips">' + secs.map((s, i) =>
        '<a href="javascript:void(0)" class="cfg-chip" onclick="document.getElementById(&quot;cfg-sec-' + i + '&quot;).scrollIntoView({behavior:&quot;smooth&quot;,block:&quot;start&quot;})">' + s[0] + '</a>').join('') + '</div>';
      return chips + secs.map((s, i) =>
        '<section class="manual-card-box" id="cfg-sec-' + i + '"><h3 class="box-title">' + s[0] + '</h3>' + s[1] + '</section>').join('');
    }

    // 같은 중분류 목록 안에서 이전/다음
    function cfgPager() {
      const list = CFG.lens === 'ref' ? cfgMajors('ref') : cfgMinors(CFG.lens, CFG.major);
      const curId = CFG.lens === 'ref' ? CFG.major : CFG.minor;
      const i = list.findIndex(m => m.id === curId);
      if (i < 0 || list.length < 2) return '';
      const link = (m, label) => {
        const go = CFG.lens === 'ref' ? cfgGo('ref', m.id, '') : cfgGo(CFG.lens, CFG.major, m.id);
        return '<button type="button" class="cfg-pager-btn" onclick="' + go + '"><span>' + label + '</span>' + cfgEsc(m.name) +
          (m.sub && CFG.lens === 'svc' ? ' / ' + cfgEsc(m.sub) : '') + '</button>';
      };
      return '<div class="cfg-pager">' + (i > 0 ? link(list[i - 1], '이전') : '<span></span>') +
        (i < list.length - 1 ? link(list[i + 1], '다음') : '<span></span>') + '</div>';
    }

    // ---------- 참고 문서 ----------
    function cfgDoc(p) {
      let html = '<div class="cfg-head"><h2 class="cfg-head-title">' + cfgEsc(p.title) + ' <span class="manual-tag">' + cfgEsc(p.tag || '') + '</span></h2>' +
        '<p class="manual-desc">' + cfgFmt(p.desc) + '</p></div>';
      p.blocks.forEach(b => {
        if (b.type === 'h') html += '<h3 class="cfg-h">' + cfgEsc(b.text) + '</h3>';
        else if (b.type === 'code') html += cfgCode(b.code, b.label);
        else if (b.type === 'table') html += cfgTable(b.head, b.rows);
        else if (b.type === 'vars') html += cfgTable(['변수', '값 (실측)', '사용처', '바뀌면 확인'], CFG.data.vars, 'cfg-vars');
        else if (b.type === 'legend') html += '<div class="cfg-legend">' +
          cfgBadge('live') + ' 현재 구성을 직접 조회해 확인한 값 ' + cfgBadge('design') + ' 적용 전 설계안 ' +
          cfgBadge('nolook') + ' 접속 불가로 외부 응답과 문서만 확인</div>';
        else if (b.type === 'troubleall') html += cfgTroubleAll();
      });
      return html;
    }
    function cfgTroubleAll() {
      const rows = [];
      CFG.data.instances.forEach(id => {
        const p = cfgPage(id);
        p.areas.forEach(a => (a.trouble || []).forEach(t => rows.push([p.short + ' / ' + a.name, t[1], t[0], t[2], t[3]])));
      });
      return '<input type="search" class="cfg-search" aria-label="오류 표 거르기" placeholder="증상, 변수, 명령어로 거르기 (예: 6443, MTU, sg-db)" oninput="cfgFilterTable(this)">' +
        cfgTable(['위치', '변수·영역', '증상', '확인 명령', '조치'], rows, 'cfg-trouble cfg-filterable');
    }
    function cfgFilterTable(inp) {
      const q = inp.value.trim().toLowerCase();
      document.querySelectorAll('.cfg-filterable tbody tr').forEach(tr => {
        tr.style.display = !q || tr.textContent.toLowerCase().indexOf(q) >= 0 ? '' : 'none';
      });
    }
