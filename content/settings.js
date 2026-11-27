    // ===== [설정] 화면: 보는 기준(렌즈) > 대분류 > 중분류 > 설명 =====
    // 원본: content/settings_guide.py (데이터) · content/settings.js (이 파일) — tools/build_settings.py 가 주입
    const CFG = { data: null, lens: null, major: null, minor: null, codes: [] };
    const CLOUD_NAME = { onprem: '온프렘', openstack: 'OpenStack', kt: 'KT Cloud', aws: 'AWS' };
    const STATUS_NAME = { live: '실측', design: '설계 · 미적용', nolook: '미실측' };
    const CAT_ORDER = ['설치', '적용', '조회', '검증'];
    const LENSES = [
      { id: 'inst', name: '클라우드 기준', hint: '클라우드(AWS·KT·OpenStack)를 펼쳐 그 안 인스턴스의 영역을 봅니다' },
      { id: 'svc', name: '서비스 기준', hint: '보안·웹 같은 영역을 골라 맡은 인스턴스를 봅니다' },
      { id: 'zoom', name: '시점(줌)', hint: '숲 → 부서장 → 팀장 → 팀원: 같은 시스템을 줌에 따라 봅니다' },
      { id: 'step', name: '진행 순서', hint: '처음 구성할 때 지켜야 하는 순서와 통과 조건' },
      { id: 'ref', name: '참고', hint: '변수표·설계·오류 색인 같은 팀 참고 문서' }
    ];
    // 클라우드 대분류 순서: AWS → KT Cloud → OpenStack → 온프렘
    const CLOUD_ORDER = { aws: 0, kt: 1, openstack: 2, onprem: 3 };
    function cfgInstOrder() {
      return (CFG.data.instances || []).slice().sort((a, b) =>
        ((CLOUD_ORDER[cfgPage(a).cloud] ?? 9) - (CLOUD_ORDER[cfgPage(b).cloud] ?? 9)));
    }
    // 시점(줌) 렌즈: 같은 데이터를 줌 단계별로 다시 묶어 보여준다
    const ZOOM_LEVELS = [
      { id: 'forest', name: '숲 · 전체', sub: '클라우드와 연결 구조 한 장', who: '처음 보는 사람 · 전원' },
      { id: 'dept', name: '부서장 · 클라우드', sub: '클라우드별 책임·구성·위험', who: '부서장' },
      { id: 'lead', name: '팀장 · 서비스 영역', sub: '영역별 설계와 맡은 인스턴스', who: '팀장' },
      { id: 'member', name: '팀원 · 인스턴스 작업', sub: '서버별 실제 명령·설정·검증', who: '팀원' }
    ];
    function cfgClouds() {   // 인스턴스가 있는 클라우드만, 정해진 순서로
      const seen = {};
      cfgInstOrder().forEach(pid => { seen[cfgPage(pid).cloud] = true; });
      return Object.keys(CLOUD_ORDER).filter(c => seen[c]);
    }

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
        return pre + '<a class="cfg-sh" href="javascript:void(0)" title="' + tip + '" onclick="cfgViewScript(' + CFG_SH_KEY[key] + '); return false;">' + key + '</a>';
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
            '<button type="button" class="cfg-copy" id="cfg-vw-dl" disabled>파일 받기</button>' +
            '<button type="button" class="cfg-copy" onclick="document.getElementById(&quot;cfg-viewer&quot;).close()">닫기</button>' +
          '</div></div>' +
        (used.length ? '<div class="cfg-vw-used">이 스크립트가 나오는 곳: ' + used.map(u =>
          '<a href="javascript:void(0)" onclick="document.getElementById(&quot;cfg-viewer&quot;).close();' + cfgGo('inst', u[0], u[1]) + '">' + cfgEsc(u[2]) + '</a>').join(', ') + '</div>' : '') +
        '<pre class="cfg-vw-body" id="cfg-vw-body">불러오는 중…</pre>' +
        '<p class="cfg-vw-note">' + (s.status === 'design'
          ? '이 가이드의 설계안에서 만든 파일입니다. 아직 서버에 적용되지 않았습니다.'
          : '서버에서 읽어 온 사본입니다(실측 ' + cfgEsc(CFG.data.measured) + '). 원본을 고치면 이 사본도 다시 받아야 합니다.') + '</p>';
      if (!dlg.open) dlg.showModal();
      api('GET', '/api/scripts/' + s.id)
        .then(r => {
          const text = r.text;
          const body = document.getElementById('cfg-vw-body');
          body.innerHTML = text.replace(/\n$/, '').split('\n').map(l => '<span class="cfg-ln">' + cfgLink(cfgEsc(l)) + '</span>').join('\n');
          const btn = document.getElementById('cfg-vw-copy');
          btn.disabled = false;
          btn.onclick = () => { const idx = CFG.codes.push(text) - 1; cfgCopy(idx, btn); };
          const dl = document.getElementById('cfg-vw-dl');
          dl.disabled = false;
          dl.onclick = () => {
            const a = document.createElement('a');
            a.href = URL.createObjectURL(new Blob([text], { type: 'text/plain' }));
            a.download = s.path.split('/').pop().split(' ')[0];
            a.click(); setTimeout(() => URL.revokeObjectURL(a.href), 2000);
          };
        })
        .catch(err => {
          document.getElementById('cfg-vw-body').textContent = '파일을 불러오지 못했습니다 (' + (err.error || err.status) + ').';
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
      if (lens === 'inst') return cfgInstOrder().map(pid => {
        const p = cfgPage(pid);
        return { id: pid, name: p.title.split(' (')[0], sub: p.tag, cloud: p.cloud, status: p.status, group: p.cloudName, groupId: p.cloudId };
      });
      if (lens === 'svc') return d.domains.map(dm => ({ id: dm.id, name: dm.name, sub: dm.desc, count: cfgMinors('svc', dm.id).length }));
      if (lens === 'zoom') return ZOOM_LEVELS.map(z => ({ id: z.id, name: z.name, sub: z.sub }));
      if (lens === 'step') return [{ id: 'all', name: '처음부터 끝까지', sub: d.steps.length ? d.steps.length + '단계' : '아직 단계가 없습니다' }];
      return d.reference.map(r => ({ id: r[0], name: r[1], sub: cfgPage(r[0]).tag }))
        .concat(typeof wikiChangesView === 'function' ? [{ id: '__changes', name: '최근 변경', sub: '팀 전체 변경 기록' }] : []);
    }
    function cfgMinors(lens, major) {
      const d = CFG.data;
      if (lens === 'inst') {
        const p = cfgPage(major);
        return p ? p.areas.map(a => ({ id: a.id, name: a.name, sub: a.domains.map(x => cfgDomain(x).name).join(', '), status: a.status !== p.status ? a.status : '' })) : [];
      }
      if (lens === "svc") {
        const out = [];
        cfgInstOrder().forEach(pid => {
          const p = cfgPage(pid);
          p.areas.forEach(a => {
            if (a.domains.indexOf(major) >= 0) out.push({ id: pid + '.' + a.id, name: p.short, sub: a.name, cloud: p.cloud, status: a.status === 'live' ? '' : a.status });
          });
        });
        return out;
      }
      if (lens === 'step') return d.steps.map(s => ({ id: s.no, name: s.no + '  ' + s.title, sub: s.where }));
      if (lens === 'zoom') {
        if (major === 'forest') return [{ id: 'all', name: '전체 토폴로지', sub: '진입 · 터널 · 서비스 · 복구 흐름' }];
        if (major === 'dept') return cfgClouds().map(c => {
          const n = cfgInstOrder().filter(pid => cfgPage(pid).cloud === c).length;
          return { id: c, name: CLOUD_NAME[c], sub: '인스턴스 ' + n + '대', cloud: c };
        });
        if (major === 'lead') return d.domains.map(dm => ({ id: dm.id, name: dm.name, sub: cfgMinors('svc', dm.id).length + '개 영역' }));
        if (major === 'member') return cfgInstOrder().map(pid => { const p = cfgPage(pid); return { id: pid, name: p.short, sub: p.tag, cloud: p.cloud }; });
      }
      return [];
    }

    // ---------- 선택·상태 ----------
    function cfgInit() {
      if (!WIKI.ready) { wikiInit(); return; }
      const h = (location.hash || '').split('/');
      const lg = CFG.data.legacy || {};
      if (h[0] === '#cfg' && h.length > 1 && h[1]) {
        let lens = h[1], major = h[2], minor = h[3];
        if (typeof wikiRoute === 'function' && wikiRoute(h)) return;
        if (['inst', 'svc', 'zoom', 'step', 'ref'].indexOf(lens) < 0 && lg[lens]) { major = lens; minor = h[2]; lens = 'inst'; }  // #cfg/inst-ktw1/join
        if (lens === 'inst' && major && !cfgPage(major) && lg[major]) {
          const am = lg[major + '.' + minor];
          major = lg[major]; minor = am ? am.split('.')[1] : '';
        }
        if (lens === 'svc' && minor && lg[minor]) minor = lg[minor];
        if (['inst', 'svc', 'zoom', 'step', 'ref'].indexOf(lens) >= 0) return cfgSelect(lens, major, minor, true);
      }
      if (!CFG.lens) { const df = CFG.data.default; cfgSelect(df.lens, df.major, df.minor, true); }
    }

    function cfgSelect(lens, major, minor, fromHash) {
      if (!CFG.data) return;
      const majors = cfgMajors(lens);
      if (!majors.length) {
        CFG.lens = lens; CFG.major = ''; CFG.minor = '';
        cfgRenderNav(); cfgRenderBody();
        history.replaceState(null, '', '#cfg/' + lens);
        return;
      }
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
      if (lens === 'inst' && CFG.lens === 'zoom' && CFG.major === 'member' && cfgPage(CFG.minor)) return CFG.minor;
      if (cur && lens === 'zoom') return 'member';   // 보던 서버의 "팀원 작업" 시점으로
      return cfgMajors(lens)[0].id;
    }
    function cfgCarryMinor(lens, major, minors) {
      const cur = cfgCurrentArea();
      if (cur && lens === 'zoom') {
        const want = major === 'member' ? cur.pid : major === 'dept' ? cfgPage(cur.pid).cloud : major === 'lead' ? cur.area.domains[0] : 'all';
        if (minors.find(m => m.id === want)) return want;
      }
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
      let lastGroup = null;
      let col1 = '<div class="cfg-col cfg-col-major">' + wikiTeamBar() +
        '<div class="cfg-lens" role="tablist" aria-label="보는 기준">' + LENSES.map(l =>
          '<button type="button" role="tab" aria-selected="' + (l.id === CFG.lens) + '" class="cfg-lens-btn' + (l.id === CFG.lens ? ' active' : '') +
          '" onclick="' + cfgGo(l.id, '', '') + '">' + cfgEsc(l.name) + '</button>').join('') + '</div>' +
        '<p class="cfg-lens-hint">' + cfgEsc(lens.hint) + '</p>' + cfgMatrix() +
        '<div class="cfg-col-head">대분류</div><div class="cfg-list-major">' +
        cfgMajors(CFG.lens).map(m => {
          let head = '';
          if (m.group !== undefined && m.group !== lastGroup) { lastGroup = m.group; head = cfgGroupHead(m); }
          return head + '<button type="button" class="cfg-item' + (m.id === CFG.major ? ' active' : '') + '" onclick="' + cfgGo(CFG.lens, m.id, '') + '">' +
          '<span class="cfg-item-name">' + (m.cloud ? '<span class="cfg-dot cfg-c-' + m.cloud + '"></span>' : '') + cfgEsc(m.name) +
          (m.status && m.status !== 'live' ? ' ' + cfgBadge(m.status) : '') + (m.count ? '<span class="cfg-count">' + m.count + '</span>' : '') + '</span>' +
          '<span class="cfg-item-sub">' + cfgEsc(m.sub) + '</span></button>';
        }).join('') + (typeof wikiMajorTail === 'function' ? wikiMajorTail() : '') + '</div></div>';
      const minors = cfgMinors(CFG.lens, CFG.major);
      let col2 = '<div class="cfg-col cfg-col-minor"><div class="cfg-col-head">중분류</div>';
      if (minors.length) {
        col2 += '<div class="cfg-list-minor">' + minors.map(m =>
          '<button type="button" class="cfg-item cfg-item-minor' + (m.id === CFG.minor ? ' active' : '') + '" onclick="' + cfgGo(CFG.lens, CFG.major, m.id) + '">' +
          '<span class="cfg-item-name">' + (m.cloud ? '<span class="cfg-dot cfg-c-' + m.cloud + '"></span>' : '') + cfgEsc(m.name) +
          (m.status ? ' ' + cfgBadge(m.status) : '') + '</span>' +
          '<span class="cfg-item-sub">' + cfgEsc(m.sub) + '</span></button>').join('') + '</div>';
      } else {
        col2 += '<p class="cfg-empty">' + (CFG.lens === 'ref' ? '이 항목은 하위 구분 없이 오른쪽에 바로 펼쳐집니다.' : '아직 항목이 없습니다.') + '</p>';
      }
      col2 += (typeof wikiMinorTail === 'function' ? wikiMinorTail() : '') + '</div>';
      nav.innerHTML = col1 + col2;
    }

    function cfgGroupHead(m) {
      return '<div class="cfg-group-head">' + (m.cloud ? '<span class="cfg-dot cfg-c-' + m.cloud + '"></span>' : '') + cfgEsc(m.group) +
        (typeof wikiGroupTail === 'function' ? wikiGroupTail(m.groupId) : '') + '</div>';
    }

    function cfgColOn(dmId) { return (CFG.lens === 'svc' && CFG.major === dmId) || (CFG.lens === 'zoom' && CFG.major === 'lead' && CFG.minor === dmId); }
    // 인스턴스(행) × 서비스 영역(열). 행으로 읽으면 인스턴스 기준, 열로 읽으면 서비스 기준.
    function cfgMatrix() {
      const d = CFG.data;
      const cur = cfgCurrentArea();
      let html = '<div class="cfg-matrix" aria-label="인스턴스와 서비스 영역 지도"><div class="cfg-mx-row cfg-mx-headrow"><span class="cfg-mx-label"></span>' +
        d.domains.map(dm => '<span class="cfg-mx-col' + (cfgColOn(dm.id) ? ' on' : '') + '" title="' + cfgEsc(dm.name) + '">' + cfgEsc(dm.short) + '</span>').join('') + '</div>';
      cfgInstOrder().forEach(pid => {
        const p = cfgPage(pid);
        const rowOn = (CFG.lens === 'inst' && CFG.major === pid) || (CFG.lens === 'zoom' && CFG.major === 'member' && CFG.minor === pid);
        html += '<div class="cfg-mx-row' + (rowOn ? ' on' : '') + '"><span class="cfg-mx-label">' + cfgEsc(p.short) + '</span>';
        d.domains.forEach(dm => {
          const areas = p.areas.filter(a => a.domains.indexOf(dm.id) >= 0);
          if (!areas.length) { html += '<span class="cfg-mx-cell"></span>'; return; }
          const colOn = cfgColOn(dm.id);
          const here = cur && cur.pid === pid && areas.some(a => a.id === cur.area.id);
          const go = CFG.lens === 'svc' ? cfgGo('svc', dm.id, pid + '.' + areas[0].id)
            : CFG.lens === 'zoom' ? (CFG.major === 'lead' ? cfgGo('zoom', 'lead', dm.id) : cfgGo('zoom', 'member', pid)) : cfgGo('inst', pid, areas[0].id);
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
      const empty = msg => '<div class="cfg-empty-panel"><p>' + msg + '</p>' +
        (typeof wikiEmptyActions === 'function' ? wikiEmptyActions(CFG.lens) : '') + '</div>';
      if (CFG.lens === 'ref' && CFG.major === '__changes') {
        body.innerHTML = ''; wikiChangesView(); return;
      } else if (CFG.lens === 'ref') {
        const p = cfgPage(CFG.major);
        html += p ? cfgDoc(p) : empty('아직 참고 문서가 없습니다.');
      } else if (CFG.lens === 'step') {
        const s = CFG.data.steps.find(x => x.no === CFG.minor);
        html += s ? cfgStepHead(s) + cfgAreaView(s.page, s.area, false) : empty('아직 진행 순서가 없습니다.');
      } else if (CFG.lens === 'zoom') {
        html += cfgZoomBar();
        if (CFG.major === 'forest') html += cfgZoomForest();
        else if (CFG.major === 'dept') html += cfgZoomDept(CFG.minor);
        else if (CFG.major === 'lead') html += cfgZoomLead(CFG.minor);
        else if (CFG.major === 'member') html += cfgZoomMember(CFG.minor);
      } else {
        const cur = cfgCurrentArea();
        if (CFG.lens === 'svc' && CFG.major) {
          const dm = cfgDomain(CFG.major);
          html += '<div class="cfg-domain-note"><b>' + cfgEsc(dm.name) + '</b> ' + cfgEsc(dm.desc) + '</div>';
        }
        if (cur) html += cfgAreaView(cur.pid, cur.area.id, CFG.lens === 'inst');
        else if (CFG.lens === 'inst' && cfgPage(CFG.major)) html += empty('이 인스턴스에 아직 서비스 영역이 없습니다.');
        else if (CFG.lens === 'inst') html += empty(CFG.data.clouds && CFG.data.clouds.length ? '클라우드 아래에 인스턴스를 만드세요.' : '클라우드부터 만드세요. 클라우드 → 인스턴스 → 서비스 영역 순서로 채워 갑니다.');
        else html += empty('이 서비스에 해당하는 영역이 아직 없습니다.');
      }
      html += cfgPager();
      body.innerHTML = html;
      body.scrollTop = 0;
    }

    function cfgAreaView(pid, aid, specsOpen) {
      const p = cfgPage(pid);
      const a = cfgAreaOf(pid, aid);
      const st = a.status || p.status;
      let html = '<div class="cfg-head">' + (typeof wikiActions === 'function' ? wikiActions('area', a.docId) : '') +
        '<div class="cfg-head-line">' + '<span class="cfg-cloud cfg-c-' + p.cloud + '">' + cfgEsc(CLOUD_NAME[p.cloud]) + '</span>' +
          '<span class="cfg-head-inst">' + cfgEsc(p.title) + '</span><span class="manual-tag">' + cfgEsc(p.tag) + '</span></div>' +
        '<h2 class="cfg-head-title">' + cfgEsc(a.name) + ' ' + cfgBadge(st) + '</h2>' +
        '<div class="cfg-head-domains">이 영역은 ' + a.domains.map(x =>
          '<a href="javascript:void(0)" class="cfg-dom-link" onclick="' + cfgGo('svc', x, pid + '.' + aid) + '">' + cfgEsc(cfgDomain(x).name) + '</a>').join(', ') +
          ' 서비스에 속합니다' + (p.steps ? '. 진행 순서 ' + cfgEsc(p.steps) : '') + '.</div>' + cfgConsoleBtn(p) + '</div>';
      html += '<details class="cfg-inst"' + (specsOpen ? ' open' : '') + '><summary>인스턴스 개요와 사양</summary>' + (typeof wikiActions === 'function' ? wikiActions('instance', p.docId) : '') +
        '<p class="manual-desc">' + cfgFmt(p.desc) + '</p><div class="spec-grid">' + p.specs.map(s =>
          '<div class="spec-item"><span class="spec-k">' + cfgEsc(s[0]) + '</span><span class="spec-v">' + cfgEsc(s[1]) + '</span></div>').join('') + '</div></details>';
      return html + cfgArea(a);
    }

    function cfgStepHead(s) {
      return (typeof wikiActions === 'function' ? wikiActions('steps', CFG.data.stepsDocId) : '') + '<div class="cfg-head cfg-step-head"><div class="cfg-step-no">' + cfgEsc(s.no) + '</div><div>' +
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

    // ---------- 시점(줌) 렌즈: 숲 → 부서장 → 팀장 → 팀원 ----------
    // 설계 문서의 서버 → 통합 콘솔 대상 (s1 은 정책상 터미널 없음, kt-w1 은 콘솔 대상 아님)
    const CFG_CONSOLE = { 'controller': 'controller', 'cp1': 'k8s-cp1', 'w1': 'k8s-w1', 'db-01': 'db-01', 'kt-edge': 'kt-edge', 'aws-dr': 'aws-dr', 'aws-ctl': 'aws-ctl' };
    function cfgConsoleId(p) { return (p && CFG_CONSOLE[p.short]) || null; }
    function cfgOpenConsole(id) {
      if (typeof CS !== 'undefined') CS.pending = id;
      if (typeof switchView === 'function') switchView('console');
    }
    function cfgConsoleBtn(p) {
      const id = cfgConsoleId(p);
      return id ? '<button type="button" class="wk-btn cfg-term-btn" onclick="cfgOpenConsole(&quot;' + cfgEsc(id) + '&quot;)">이 서버 터미널 열기</button>' : '';
    }
    function cfgZoomBar() {
      const lv = ZOOM_LEVELS.findIndex(z => z.id === CFG.major);
      return '<nav class="cfg-zoombar" aria-label="줌 단계">' + ZOOM_LEVELS.map((z, i) =>
        '<button type="button" class="cfg-zoom-step' + (i === lv ? ' on' : '') + (i < lv ? ' past' : '') + '"' + (i === lv ? ' aria-current="step"' : '') +
        ' onclick="' + cfgGo('zoom', z.id, '') + '"><span class="cfg-zoom-n">' + (i + 1) + '</span><span class="cfg-zoom-t">' + cfgEsc(z.name) +
        '</span><span class="cfg-zoom-who">' + cfgEsc(z.who) + '</span></button>').join('<span class="cfg-zoom-sep" aria-hidden="true">›</span>') + '</nav>';
    }
    function cfgTopologyPage() {
      const ref = (CFG.data.reference || []).find(r => /^전체 토폴로지/.test(r[1] || ''));
      return ref ? cfgPage(ref[0]) : null;
    }
    // 숲: 클라우드별 서버 지도 + 실측 토폴로지 문서(위키)
    function cfgZoomForest() {
      let html = '<div class="cfg-head"><h2 class="cfg-head-title">숲 · 전체 구성</h2><p class="manual-desc">세 클라우드와 그 안 서버가 한 화면에 보입니다. ' +
        '클라우드 이름을 누르면 부서장 시점으로, 서버를 누르면 팀원 시점(실제 작업)으로 내려갑니다.</p></div>';
      html += '<div class="cfg-forest">' + cfgClouds().map(c => {
        const list = cfgInstOrder().filter(pid => cfgPage(pid).cloud === c);
        return '<section class="cfg-forest-cloud"><button type="button" class="cfg-forest-name" onclick="' + cfgGo('zoom', 'dept', c) + '">' +
          '<span class="cfg-dot cfg-c-' + c + '"></span>' + cfgEsc(CLOUD_NAME[c]) + '<small>' + list.length + '대</small></button>' +
          list.map(pid => {
            const p = cfgPage(pid);
            return '<button type="button" class="cfg-forest-inst" onclick="' + cfgGo('zoom', 'member', pid) + '"><b>' + cfgEsc(p.short) + '</b>' +
              (p.status && p.status !== 'live' ? ' ' + cfgBadge(p.status) : '') + '<span>' + cfgEsc(p.tag) + '</span></button>';
          }).join('') + '</section>';
      }).join('') + '</div>';
      const topo = cfgTopologyPage();
      return html + (topo ? cfgDoc(topo) : '<div class="cfg-empty-panel"><p>실측 토폴로지 문서(“전체 토폴로지 · 실측”)가 아직 없습니다. 참고 문서로 추가하면 여기에 나옵니다.</p></div>');
    }
    // 부서장: 클라우드 하나가 책임지는 것 — 분류 분포·서버별 역할·위험
    function cfgZoomDept(c) {
      const list = cfgInstOrder().filter(pid => cfgPage(pid).cloud === c);
      if (!list.length) return '<div class="cfg-empty-panel"><p>이 클라우드에 서버가 없습니다.</p></div>';
      const areas = [], troubles = [], doms = {};
      list.forEach(pid => { const p = cfgPage(pid); p.areas.forEach(a => {
        areas.push([p, a]); (a.trouble || []).forEach(t => troubles.push([p, a, t]));
        a.domains.forEach(d => { doms[d] = (doms[d] || 0) + 1; });
      }); });
      const first = t => { t = String(t || ''); const i = t.search(/[.。]\s/); return (i > 0 ? t.slice(0, i + 1) : t).slice(0, 120); };
      let html = '<div class="cfg-head"><div class="cfg-head-line"><span class="cfg-cloud cfg-c-' + c + '">' + cfgEsc(CLOUD_NAME[c]) + '</span><span class="manual-tag">부서장 시점</span></div>' +
        '<h2 class="cfg-head-title">' + cfgEsc(CLOUD_NAME[c]) + ' 이(가) 책임지는 것</h2>' +
        '<p class="manual-desc">서버 ' + list.length + '대 · 서비스 영역 ' + areas.length + '개 · 알려진 오류 대응 ' + troubles.length + '건. 분류를 누르면 팀장 시점으로 내려갑니다.</p></div>';
      html += '<section class="manual-card-box"><h3 class="box-title">맡은 서비스 분류</h3><div class="cfg-chips">' + Object.keys(doms).map(d =>
        '<a href="javascript:void(0)" class="cfg-chip" onclick="' + cfgGo('zoom', 'lead', d) + '">' + cfgEsc((cfgDomain(d) || { name: d }).name) + ' ' + doms[d] + '</a>').join('') + '</div></section>';
      html += '<section class="manual-card-box"><h3 class="box-title">서버별 역할</h3>' + cfgTable(['서버', '역할', '서비스 영역', '상태'], list.map(pid => {
        const p = cfgPage(pid);
        return [p.short, first(p.desc), p.areas.map(a => a.name).join(', '), STATUS_NAME[p.status] || p.status || ''];
      })) + '</section>';
      if (troubles.length) html += '<section class="manual-card-box"><h3 class="box-title">위험 — 알려진 오류 증상</h3>' +
        cfgTable(['서버 / 영역', '증상', '의심 지점', '조치'], troubles.slice(0, 12).map(x => [x[0].short + ' / ' + x[1].name, x[2][0], x[2][1], x[2][3]]), 'cfg-trouble') +
        (troubles.length > 12 ? '<p class="manual-desc">외 ' + (troubles.length - 12) + '건은 참고 › 오류 확인 색인에서 봅니다.</p>' : '') + '</section>';
      return html;
    }
    // 팀장: 서비스 분류 하나 — 영역별 설계와 맡은 서버
    function cfgZoomLead(dmId) {
      const dm = cfgDomain(dmId);
      if (!dm) return '<div class="cfg-empty-panel"><p>분류를 고르세요.</p></div>';
      const rows = [];
      cfgInstOrder().forEach(pid => { const p = cfgPage(pid); p.areas.forEach(a => { if (a.domains.indexOf(dmId) >= 0) rows.push([pid, p, a]); }); });
      let html = '<div class="cfg-head"><div class="cfg-head-line"><span class="manual-tag">팀장 시점</span></div>' +
        '<h2 class="cfg-head-title">' + cfgEsc(dm.name) + ' — 설계와 담당</h2><p class="manual-desc">' + cfgEsc(dm.desc) + ' 이 분류에 속한 영역 ' + rows.length + '개.</p></div>';
      if (!rows.length) return html + '<div class="cfg-empty-panel"><p>이 분류에 속한 영역이 아직 없습니다.</p></div>';
      html += '<section class="manual-card-box"><h3 class="box-title">맡은 서버</h3>' + cfgTable(['클라우드', '서버', '영역'], rows.map(r => [CLOUD_NAME[r[1].cloud], r[1].short, r[2].name])) + '</section>';
      return html + rows.map(r =>
        '<section class="manual-card-box"><h3 class="box-title"><span class="cfg-dot cfg-c-' + r[1].cloud + '"></span>' + cfgEsc(r[1].short) + ' · ' + cfgEsc(r[2].name) +
        (r[2].status && r[2].status !== 'live' ? ' ' + cfgBadge(r[2].status) : '') +
        ' <a href="javascript:void(0)" class="cfg-dom-link" onclick="' + cfgGo('zoom', 'member', r[0]) + '">팀원 작업 ›</a></h3>' +
        (r[2].design && r[2].design.length ? '<ul class="cfg-list">' + r[2].design.map(d => '<li>' + cfgFmt(d) + '</li>').join('') + '</ul>' : '<p class="manual-desc">설계 설명이 아직 없습니다.</p>') +
        '</section>').join('');
    }
    // 팀원: 서버 하나에서 실제로 실행하는 것 — 명령·검증 + 터미널 바로 열기
    function cfgZoomMember(pid) {
      const p = cfgPage(pid);
      if (!p) return '<div class="cfg-empty-panel"><p>서버를 고르세요.</p></div>';
      let html = '<div class="cfg-head"><div class="cfg-head-line"><span class="cfg-cloud cfg-c-' + p.cloud + '">' + cfgEsc(CLOUD_NAME[p.cloud]) + '</span>' +
        '<span class="cfg-head-inst">' + cfgEsc(p.title) + '</span><span class="manual-tag">팀원 시점</span></div>' +
        '<h2 class="cfg-head-title">' + cfgEsc(p.short) + ' 에서 하는 일</h2><p class="manual-desc">' + cfgFmt(p.desc) + '</p>' + cfgConsoleBtn(p) + '</div>';
      if (!p.areas.length) return html + '<div class="cfg-empty-panel"><p>이 서버에 서비스 영역이 아직 없습니다.</p></div>';
      return html + p.areas.map(a => {
        const cmds = (a.commands || []).slice().sort((x, y) => CAT_ORDER.indexOf(x.cat) - CAT_ORDER.indexOf(y.cat));
        const ver = (a.verify || []).map(v => cfgCode(v.code, v.label, '검증') + '<div class="cfg-expect">기대 결과: ' + cfgFmt(v.expect) + '</div>').join('');
        return '<section class="manual-card-box"><h3 class="box-title">' + cfgEsc(a.name) + (a.status && a.status !== 'live' ? ' ' + cfgBadge(a.status) : '') +
          ' <a href="javascript:void(0)" class="cfg-dom-link" onclick="' + cfgGo('inst', pid, a.id) + '">설계·설정·오류까지 ›</a></h3>' +
          cmds.map(c => cfgCode(c.code, c.label, c.cat)).join('') + ver +
          (!cmds.length && !ver ? '<p class="manual-desc">이 영역에 실행 명령이 아직 없습니다.</p>' : '') + '</section>';
      }).join('');
    }

    // ---------- 참고 문서 ----------
    function cfgDoc(p) {
      let html = '<div class="cfg-head">' + (typeof wikiActions === 'function' ? wikiActions('page', p.docId) : '') + '<h2 class="cfg-head-title">' + cfgEsc(p.title) + ' <span class="manual-tag">' + cfgEsc(p.tag || '') + '</span></h2>' +
        '<p class="manual-desc">' + cfgFmt(p.desc) + '</p></div>';
      p.blocks.forEach(b => {
        if (b.type === 'h') html += '<h3 class="cfg-h">' + cfgEsc(b.text) + '</h3>';
        else if (b.type === 'p') html += '<p class="manual-desc">' + cfgFmt(b.text) + '</p>';
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

    // ===== 상단 [콘솔] 메뉴 =====
    function cnToggle(ev) {
      ev.stopPropagation();
      const m = document.getElementById('cn-menu'), b = document.getElementById('cn-btn');
      const open = m.hidden;
      m.hidden = !open; b.setAttribute('aria-expanded', String(open));
      if (open) { const f = m.querySelector('a'); if (f) f.focus(); }
    }
    document.addEventListener('click', e => {
      const m = document.getElementById('cn-menu');
      if (m && !m.hidden && !e.target.closest('.cn-wrap')) { m.hidden = true; document.getElementById('cn-btn').setAttribute('aria-expanded', 'false'); }
    });
    document.addEventListener('keydown', e => {
      const m = document.getElementById('cn-menu');
      if (e.key === 'Escape' && m && !m.hidden) { m.hidden = true; const b = document.getElementById('cn-btn'); b.setAttribute('aria-expanded', 'false'); b.focus(); }
    });
