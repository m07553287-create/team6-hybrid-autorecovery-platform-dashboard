    // ===== [설정] 화면: 보는 기준(렌즈) > 대분류 > 중분류 > 설명 =====
    // 원본: content/settings_guide.py (데이터) · content/settings.js (이 파일) — tools/build_settings.py 가 주입
    const CFG = { data: null, lens: null, major: null, minor: null, codes: [] };
    const CLOUD_NAME = { onprem: '온프렘', openstack: 'OpenStack', kt: 'KT Cloud', aws: 'AWS' };
    const STATUS_NAME = { live: '실측', design: '설계 · 미적용', nolook: '미실측', protected: '보호 구역 · 웹 조작 제외' };
    const CAT_ORDER = ['설치', '적용', '조회', '검증'];
    const LENSES = [
      { id: 'inst', name: '클라우드 기준', hint: '클라우드(AWS·KT·OpenStack)를 펼쳐 그 안 인스턴스의 영역을 봅니다' },
      { id: 'svc', name: '서비스 기준', hint: '보안·웹 같은 영역을 골라 맡은 인스턴스를 봅니다' },
      { id: 'zoom', name: '기준점', hint: 'AWS·KT·OpenStack·온프렘 각 클라우드 기준 전체 시스템이 어떻게 구성되는지 봅니다' },
      { id: 'step', name: '진행 순서', hint: '처음 구성할 때 지켜야 하는 순서와 통과 조건' },
      { id: 'ref', name: '참고', hint: '변수표·설계·오류 색인 같은 팀 참고 문서' }
    ];
    // 클라우드 대분류 순서: AWS → KT Cloud → OpenStack → 온프렘
    const CLOUD_ORDER = { aws: 0, kt: 1, openstack: 2, onprem: 3 };
    function cfgInstOrder() {
      return (CFG.data.instances || []).slice().sort((a, b) =>
        ((CLOUD_ORDER[cfgPage(a).cloud] ?? 9) - (CLOUD_ORDER[cfgPage(b).cloud] ?? 9)));
    }
    // 시점(입장) 렌즈: 각 클라우드에 서서 전체를 본다 — 연결 · 기대는 것 · 나에게 기대는 것 · 멈추면 · 확인
    const VIEW_FOREST = { id: 'forest', name: '전체', sub: '모든 클라우드와 연결 한 장' };
    function cfgViewPage(c) {   // 위키 참고 문서 '시점 · <클라우드>' (팀이 편집)
      const want = '시점 · ' + CLOUD_NAME[c];
      const ref = (CFG.data.reference || []).find(r => (r[1] || '') === want);
      return ref ? cfgPage(ref[0]) : null;
    }
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
    function cfgExtractFilePath(label, code) {
      const text = (label || '') + '\n' + (code || '');
      const m = text.match(/(?:(?:nano|vi|vim|cat|touch|mkdir|cp|mv)\s+)?((?:\/|~)[A-Za-z0-9_./-]+(?:\.[A-Za-z0-9_-]+|\/[A-Za-z0-9_.-]+))/);
      if (m && m[1]) return m[1];
      if (/^[A-Za-z0-9_./-]+\.(cnf|conf|yaml|yml|json|toml|service|sh|cfg|env|txt|ini)$/i.test((label || '').trim())) {
        return (label || '').trim();
      }
      return (label || '').trim();
    }

    function cfgCode(code, label, cat) {
      CFG.codeMeta = CFG.codeMeta || [];
      const idx = CFG.codes.push(code) - 1;
      CFG.codeMeta[idx] = { code: code, label: label, cat: cat };
      const isDang = cfgIsDangerous(code, cat);
      const isConfig = (cat === '설정' || /\b(cnf|conf|yaml|yml|json|toml|service|cfg|ini)\b/i.test(label || '') || /^\s*(\[|\{|\#|[A-Za-z0-9_-]+:)/.test(code || ''));

      let acts = '<button type="button" class="cfg-copy" onclick="cfgCopy(' + idx + ', this)">복사</button>';

      if (isConfig) {
        // 설정인 경우: 뷰 모드(안전 확인) + 빨강색 수정/변경(vi/nano) 버튼
        acts += '<button type="button" class="cfg-run-btn cfg-btn-view" onclick="cfgViewCode(' + idx + ')" title="안전한 뷰 모드로 설정 파일 내용 확인">👁️ 뷰 모드</button>';
        acts += '<button type="button" class="cfg-run-btn cfg-run-danger" onclick="cfgEditCode(' + idx + ')" title="경고: vi/nano 편집기 접근 및 설정 수정/변경 (확인 후 진행)">✏️ 수정/변경 (vi/nano)</button>';
      } else if (isDang || cat === '적용' || cat === '설치') {
        // 위험/적용/변경 명령어인 경우: 뷰 모드(사전 확인) + 빨강색 수정/변경 버튼
        acts += '<button type="button" class="cfg-run-btn cfg-btn-view" onclick="cfgViewCode(' + idx + ')" title="명령어 사전 확인 (뷰 모드)">👁️ 뷰 모드</button>';
        acts += '<button type="button" class="cfg-run-btn cfg-run-danger" onclick="cfgRunCode(' + idx + ')" title="경고: 시스템 설정 변경 및 서비스 영향 (확인 후 진행)">⚠️ 수정/변경</button>';
      } else {
        // 일반 조회/검증 안전 명령어: 복사 + 안전 실행
        acts += '<button type="button" class="cfg-run-btn cfg-run-safe" onclick="cfgRunCode(' + idx + ')" title="터미널에서 즉시 조회/검증 실행">▶ 뷰/확인</button>';
      }

      return '<div class="cfg-code"><div class="cfg-code-head">' +
        (cat ? '<span class="cfg-cat cfg-cat-' + CAT_ORDER.indexOf(cat) + '">' + cfgEsc(cat) + '</span>' : '') +
        '<span class="cfg-code-label">' + cfgLink(cfgEsc(label || '')) + '</span>' +
        '<div class="cfg-code-actions">' + acts + '</div>' +
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
      if (lens === 'zoom') return [VIEW_FOREST].concat(cfgClouds().map(c => ({ id: c, name: CLOUD_NAME[c], sub: cfgInstOrder().filter(pid => cfgPage(pid).cloud === c).length + '대 · 연결·의존·멈추면', cloud: c })));
      if (lens === 'step') return [{ id: 'all', name: '처음부터 끝까지', sub: d.steps.length ? d.steps.length + '단계' : '아직 단계가 없습니다' }];
      return d.reference.filter(r => !/^시점 · /.test(r[1] || '')).map(r => ({ id: r[0], name: r[1], sub: cfgPage(r[0]).tag }))
        .concat(typeof wikiChangesView === 'function' ? [{ id: '__changes', name: '최근 변경 · 접속 기록', sub: '키값·수정자 매칭 및 접속 이력' }] : []);
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
        if (!CLOUD_NAME[major]) return [];
        return [{ id: 'view', name: CLOUD_NAME[major] + ' 설계 기준', sub: '연결 · 의존 · 멈추면', cloud: major }]
          .concat(cfgInstOrder().filter(pid => cfgPage(pid).cloud === major).map(pid => { const p = cfgPage(pid); return { id: pid, name: p.short, sub: '서버 작업 · ' + p.tag, cloud: p.cloud }; }));
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
      CFG.treeOpen = CFG.treeOpen || {};
      CFG.treeOpen[major] = true;
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
      if (lens === 'inst' && CFG.lens === 'zoom' && cfgPage(CFG.minor)) return CFG.minor;
      if (cur && lens === 'zoom') return cfgPage(cur.pid).cloud;   // 보던 서버가 속한 클라우드 입장으로
      return cfgMajors(lens)[0].id;
    }
    function cfgCarryMinor(lens, major, minors) {
      const cur = cfgCurrentArea();
      if (cur && lens === 'zoom') {
        const want = major === 'forest' ? 'all' : cur.pid;
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

    // ---------- 왼쪽: 통합 사이드바 (대분류 > 중분류 아코디언 및 계단식 트리) ----------
    CFG.treeOpen = CFG.treeOpen || {};

    function cfgIsTreeOpen(majorId) {
      if (CFG.treeOpen[majorId] !== undefined) return CFG.treeOpen[majorId];
      return majorId === CFG.major;
    }

    function cfgToggleTree(ev, majorId) {
      if (ev) ev.stopPropagation();
      CFG.treeOpen[majorId] = !cfgIsTreeOpen(majorId);
      const el = document.getElementById('tree-node-' + majorId);
      if (el) el.classList.toggle('open', CFG.treeOpen[majorId]);
    }

    function cfgClickMajor(majorId) {
      CFG.treeOpen = CFG.treeOpen || {};
      CFG.treeOpen[majorId] = true;
      const minors = cfgMinors(CFG.lens, majorId);
      const targetMinor = minors.length ? minors[0].id : '';
      cfgSelect(CFG.lens, majorId, targetMinor);
    }

    function cfgRenderNav() {
      const nav = document.getElementById('cfg-nav');
      const lens = LENSES.find(l => l.id === CFG.lens);
      let lastGroup = null;

      // 1. 상단 렌즈 탭 & 지침 스튜디오 버튼 & 사용 매뉴얼 링크 & 힌트 & 매트릭스
      let html = wikiTeamBar() +
        (typeof cfgGuideOpen === 'function'
          ? '<button type="button" class="cfg-guide-launch-btn" onclick="cfgGuideOpen()"><span>📋 지침 복사 · 결과 등록/수정</span><small>생성·수정·순서</small></button>'
          : '') +
        '<a href="/manual/" target="_blank" rel="noopener" class="cfg-manual-link-btn"><span>📖 사용 매뉴얼 보기 (화면 클릭 안내)</span><small>새 탭</small></a>' +
        '<div class="cfg-lens" role="tablist" aria-label="보는 기준">' + LENSES.map(l =>
          '<button type="button" role="tab" aria-selected="' + (l.id === CFG.lens) + '" class="cfg-lens-btn' + (l.id === CFG.lens ? ' active' : '') +
          '" onclick="' + cfgGo(l.id, '', '') + '">' + cfgEsc(l.name) + '</button>').join('') + '</div>' +
        '<p class="cfg-lens-hint">' + cfgEsc(lens.hint) + '</p>' +
        (CFG.lens === 'inst' ? cfgMatrix() : '');

      // 2. 통합 내비게이션 트리 (대분류 > 중분류 계단식/아코디언)
      html += '<div class="cfg-col-head" style="margin-top:6px;">설계 및 설정 계층 트리</div>' +
        '<div class="cfg-tree-nav">';

      const majors = cfgMajors(CFG.lens);
      majors.forEach(m => {
        if (m.group !== undefined && m.group !== lastGroup) {
          lastGroup = m.group;
          html += cfgGroupHead(m);
        }
        const minors = cfgMinors(CFG.lens, m.id);
        const instAddAreaBtn = (CFG.lens === 'inst' && typeof WIKI !== 'undefined' && WIKI.ready && cfgPage(m.id) && cfgPage(m.id).docId)
          ? '<button type="button" class="wk-add cfg-tree-add-minor" onclick="event.stopPropagation();wikiCreate(\'area\', ' + cfgPage(m.id).docId + ')">+ 서비스 영역</button>'
          : '';
        const hasMinors = minors.length > 0 || !!instAddAreaBtn;
        const isCurrentMajor = (m.id === CFG.major);
        const isOpen = cfgIsTreeOpen(m.id);

        html += '<div class="cfg-tree-node' + (isOpen ? ' open' : '') + '" id="tree-node-' + m.id + '">' +
          '<div class="cfg-tree-major' + (isCurrentMajor ? ' active' : '') + '" onclick="cfgClickMajor(\'' + m.id + '\')">' +
          '<div class="cfg-tree-major-main">' +
          (hasMinors ? '<span class="cfg-tree-toggle" onclick="cfgToggleTree(event, \'' + m.id + '\')" title="하위 항목 접기/펼치기">▶</span>' : '<span style="width:18px;display:inline-block;"></span>') +
          (m.cloud ? '<span class="cfg-dot cfg-c-' + m.cloud + '"></span>' : '') +
          '<div class="cfg-tree-major-info">' +
          '<span class="cfg-tree-major-name">' + cfgEsc(m.name) + '</span>' +
          (m.sub ? '<span class="cfg-tree-major-sub">' + cfgEsc(m.sub) + '</span>' : '') +
          '</div>' +
          '</div>' +
          '<div class="cfg-tree-major-meta">' +
          (m.status && m.status !== 'live' ? cfgBadge(m.status) : '') +
          (minors.length ? '<span class="cfg-tree-badge-count">' + minors.length + '</span>' : '') +
          '</div>' +
          '</div>';

        // 하위 중분류 (계단식 인덴트) + 인스턴스별 서비스 영역 추가 버튼
        if (hasMinors) {
          html += '<div class="cfg-tree-minors">' +
            minors.map(sub => {
              const isCurrentMinor = isCurrentMajor && (sub.id === CFG.minor);
              return '<button type="button" class="cfg-tree-minor' + (isCurrentMinor ? ' active' : '') + '" onclick="' + cfgGo(CFG.lens, m.id, sub.id) + '">' +
                '<span class="cfg-tree-minor-name">' +
                (sub.cloud ? '<span class="cfg-dot cfg-c-' + sub.cloud + '"></span>' : '') +
                cfgEsc(sub.name) +
                (sub.status ? ' ' + cfgBadge(sub.status) : '') + '</span>' +
                (sub.sub ? '<span class="cfg-tree-minor-sub">' + cfgEsc(sub.sub) + '</span>' : '') +
                '</button>';
            }).join('') +
            instAddAreaBtn +
            '</div>';
        }

        html += '</div>';
      });

      if (CFG.lens === 'step' && typeof WIKI !== 'undefined' && WIKI.ready) {
        html += '<div class="cfg-tree-step-acts">' +
          '<button type="button" class="wk-add" onclick="wikiEditSteps(true)">+ 단계 추가</button>' +
          (typeof cfgGuideOpen === 'function' ? '<button type="button" class="wk-add" onclick="cfgGuideOpen({action:\'reorder\',kind:\'steps\',docId:' + (CFG.data.stepsDocId || 'null') + '})">↕️ 지침으로 순서 편집</button>' : '') +
          '</div>';
      }

      html += (typeof wikiMajorTail === 'function' ? wikiMajorTail() : '') + '</div>';
      nav.innerHTML = html;
    }

    function cfgGroupHead(m) {
      return '<div class="cfg-group-head">' + (m.cloud ? '<span class="cfg-dot cfg-c-' + m.cloud + '"></span>' : '') + cfgEsc(m.group) +
        (typeof wikiGroupTail === 'function' ? wikiGroupTail(m.groupId) : '') + '</div>';
    }

    function cfgColOn(dmId) { return CFG.lens === 'svc' && CFG.major === dmId; }
    // 인스턴스(행) × 서비스 영역(열). 행으로 읽으면 인스턴스 기준, 열로 읽으면 서비스 기준.
    function cfgMatrix() {
      const d = CFG.data;
      const cur = cfgCurrentArea();
      let html = '<div class="cfg-matrix" aria-label="인스턴스와 서비스 영역 지도"><div class="cfg-mx-row cfg-mx-headrow"><span class="cfg-mx-label"></span>' +
        d.domains.map(dm => '<span class="cfg-mx-col' + (cfgColOn(dm.id) ? ' on' : '') + '" title="' + cfgEsc(dm.name) + '">' + cfgEsc(dm.short) + '</span>').join('') + '</div>';
      cfgInstOrder().forEach(pid => {
        const p = cfgPage(pid);
        const rowOn = (CFG.lens === 'inst' && CFG.major === pid) || (CFG.lens === 'zoom' && CFG.minor === pid);
        html += '<div class="cfg-mx-row' + (rowOn ? ' on' : '') + '"><span class="cfg-mx-label">' + cfgEsc(p.short) + '</span>';
        d.domains.forEach(dm => {
          const areas = p.areas.filter(a => a.domains.indexOf(dm.id) >= 0);
          if (!areas.length) { html += '<span class="cfg-mx-cell"></span>'; return; }
          const colOn = cfgColOn(dm.id);
          const here = cur && cur.pid === pid && areas.some(a => a.id === cur.area.id);
          const go = CFG.lens === 'svc' ? cfgGo('svc', dm.id, pid + '.' + areas[0].id)
            : CFG.lens === 'zoom' ? cfgGo('zoom', p.cloud, pid) : cfgGo('inst', pid, areas[0].id);
          html += '<button type="button" class="cfg-mx-cell has' + (colOn || rowOn ? ' lit' : '') + (here ? ' here' : '') +
            (p.status === 'design' ? ' design' : '') + '" title="' + cfgEsc(p.short + ' / ' + dm.name + ': ' + areas.map(a => a.name).join(', ')) +
            '" aria-label="' + cfgEsc(p.short + ' ' + dm.name) + '" onclick="' + go + '"><i></i></button>';
        });
        html += '</div>';
      });
      return html + '</div>';
    }

    // ---------- 오른쪽: 설명 ----------
    // ---------- 오른쪽: 설명 & 상단 인터랙티브 브레드크럼 ----------
    function cfgCrumb() {
      const lensObj = LENSES.find(l => l.id === CFG.lens) || { name: '설정' };
      const majorObj = cfgMajors(CFG.lens).find(m => m.id === CFG.major);
      const minorObj = cfgMinors(CFG.lens, CFG.major).find(m => m.id === CFG.minor);

      let html = '<nav class="cfg-crumb" aria-label="현재 위치">';
      html += '<a href="javascript:void(0)" onclick="' + cfgGo(CFG.lens, '', '') + '">' + cfgEsc(lensObj.name) + '</a>';
      if (majorObj) {
        html += '<span class="cfg-crumb-sep">›</span>';
        html += '<a href="javascript:void(0)" onclick="cfgClickMajor(\'' + CFG.major + '\')">' + cfgEsc(majorObj.name) + '</a>';
      }
      if (minorObj) {
        html += '<span class="cfg-crumb-sep">›</span>';
        html += '<span class="cfg-crumb-current">' + cfgEsc(CFG.lens === 'svc' ? minorObj.name + ' / ' + minorObj.sub : minorObj.name) + '</span>';
      }
      html += '</nav>';
      return html;
    }

    function cfgScrollToSec(idx) {
      const body = document.getElementById('manual-body-content');
      const sec = document.getElementById('cfg-sec-' + idx);
      if (body && sec) {
        const pos = sec.offsetTop - body.offsetTop - 50;
        body.scrollTo({ top: Math.max(0, pos), behavior: 'smooth' });
      }
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
        else if (CFG.minor === 'view') html += cfgCloudView(CFG.major);
        else html += cfgZoomMember(CFG.minor);
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
      const isS1 = (pid === 'inst-s1' || (p && p.short === 's1') || (p && p.cloud === 'onprem'));
      let html = '';
      if (isS1 || p.status === 'protected') {
        html += '<div style="background:rgba(59,130,246,0.08); border:1px solid rgba(59,130,246,0.25); border-radius:8px; padding:14px 18px; margin-bottom:18px; color:#93c5fd; font-size:13px; line-height:1.6;">' +
          '<div style="font-weight:700; font-size:14px; margin-bottom:4px; color:#60a5fa;">💡 s1 가상화 기반 안내 (OpenStack 상위 호스트)</div>' +
          's1 영역은 OpenStack VM들이 구동되는 가상화 기반 호스트로, 프로젝트와 사실관계가 먼 물리 세부정보는 제외하고 상위 구성 관계만 간략히 표시합니다. (명령·연결·설정 조작 및 웹 콘솔 터미널 접근 제외)<br>' +
          '<b>본 프로젝트의 모든 실질적인 인프라 설계, 설정 및 명령어는 VM 위의 OpenStack 계층부터 시작됩니다.</b>' +
          '</div>';
      }
      html += '<div class="cfg-head">' + (typeof wikiActions === 'function' ? wikiActions('area', a.docId) : '') +
        '<div class="cfg-head-line">' + '<span class="cfg-cloud cfg-c-' + p.cloud + '">' + cfgEsc(CLOUD_NAME[p.cloud]) + '</span>' +
          '<span class="cfg-head-inst">' + cfgEsc(p.title) + '</span><span class="manual-tag">' + cfgEsc(p.tag) + '</span></div>' +
        '<h2 class="cfg-head-title">' + cfgEsc(a.name) + ' ' + cfgBadge(st) + '</h2>' +
        '<div class="cfg-head-domains">이 영역은 ' + a.domains.map(x =>
          '<a href="javascript:void(0)" class="cfg-dom-link" onclick="' + cfgGo('svc', x, pid + '.' + aid) + '">' + cfgEsc(cfgDomain(x).name) + '</a>').join(', ') +
          ' 서비스에 속합니다' + (p.steps ? '. 진행 순서 ' + cfgEsc(p.steps) : '') + '.</div>' + (isS1 ? '' : cfgConsoleBtn(p)) + '</div>';
      html += '<details class="cfg-inst"' + (specsOpen ? ' open' : '') + '><summary>인스턴스 개요와 사양 (간략 설명)</summary>' + (typeof wikiActions === 'function' ? wikiActions('instance', p.docId) : '') +
        '<p class="manual-desc">' + cfgFmt(p.desc) + '</p><div class="spec-grid">' + p.specs.map(s =>
          '<div class="spec-item"><span class="spec-k">' + cfgEsc(s[0]) + '</span><span class="spec-v">' + cfgEsc(s[1]) + '</span></div>').join('') + '</div></details>';
      return html + (isS1 ? cfgAreaShort(a) : cfgArea(a, pid, aid));
    }

    function cfgAreaShort(a) {
      if (!a.design || !a.design.length) return '';
      return '<section class="manual-card-box" id="cfg-sec-0"><h3 class="box-title">간략 설명</h3><ul class="cfg-list">' +
        a.design.map(d => '<li>' + cfgFmt(d) + '</li>').join('') + '</ul></section>';
    }

    function cfgStepHead(s) {
      return (typeof wikiActions === 'function' ? wikiActions('steps', CFG.data.stepsDocId) : '') + '<div class="cfg-head cfg-step-head"><div class="cfg-step-no">' + cfgEsc(s.no) + '</div><div>' +
        '<h2 class="cfg-head-title">' + cfgEsc(s.title) + '</h2>' +
        '<p class="manual-desc">' + cfgFmt(s.why) + ' 실행 위치: ' + cfgEsc(s.where) + '</p></div></div>' +
        cfgCode(s.gate, '통과 조건 (이게 나와야 다음 단계)', '검증');
    }

    // 서비스 영역 영속화 헬퍼 (로그인 시 Wiki API 서버 저장, 미로그인/정적 환경 시 로컬스토리지 폴백)
    function cfgLoadCustoms(pid, aid, a) {
      if (typeof WIKI !== 'undefined' && WIKI.ready && a && a.docId) return;
      try {
        const raw = localStorage.getItem('fig.cfg.custom_areas_v1');
        if (!raw) return;
        const map = JSON.parse(raw);
        const saved = map[pid + '__' + aid];
        if (saved) {
          if (saved.commands) a.commands = saved.commands;
          if (saved.config) a.config = saved.config;
          if (saved.design) a.design = saved.design;
          if (saved.verify) a.verify = saved.verify;
          if (saved.trouble) a.trouble = saved.trouble;
        }
      } catch (e) {}
    }

    function cfgSaveCustoms(pid, aid, a) {
      try {
        let map = {};
        const raw = localStorage.getItem('fig.cfg.custom_areas_v1');
        if (raw) map = JSON.parse(raw);
        map[pid + '__' + aid] = {
          commands: a.commands || [],
          config: a.config || [],
          design: a.design || [],
          verify: a.verify || [],
          trouble: a.trouble || []
        };
        localStorage.setItem('fig.cfg.custom_areas_v1', JSON.stringify(map));
      } catch (e) {}
    }

    async function cfgPersistArea(pid, aid, a, message) {
      if (typeof WIKI !== 'undefined' && WIKI.ready && a && a.docId && typeof wkDoc === 'function') {
        const d = wkDoc(a.docId);
        if (d) {
          const nextBody = JSON.parse(JSON.stringify(d.body || {}));
          nextBody.design = a.design || [];
          nextBody.config = a.config || [];
          nextBody.commands = a.commands || [];
          nextBody.verify = a.verify || [];
          nextBody.trouble = a.trouble || [];
          if (typeof wikiFindSecret === 'function') {
            const sec = wikiFindSecret(nextBody);
            if (sec) {
              alert('비밀값처럼 보이는 내용은 저장할 수 없습니다 (' + sec.field + '). <비밀번호>, <개인키> 같은 자리표시로 바꾸세요.');
              await wikiReload(true);
              return false;
            }
          }
          try {
            const r = await api('PUT', '/api/docs/' + a.docId, {
              base_rev: d.rev,
              body: nextBody,
              message: message || '서비스 영역 항목 수정'
            });
            if (typeof wkRecordLocalAccess === 'function') {
              wkRecordLocalAccess('edit', 'area:' + (nextBody.name || a.name || a.docId) + ' (' + r.rev + '판)');
            }
            if (typeof wikiToast === 'function') wikiToast('서버에 저장했습니다 (' + r.rev + '판)');
            await wikiReload(true);
            return true;
          } catch (e) {
            if (e.status === 401) return false;
            if (e.status === 409) {
              alert('다른 팀원이 먼저 수정해 판 충돌(409)이 발생했습니다. 최신 문서를 다시 불러옵니다.');
              await wikiReload(true);
              return false;
            }
            alert('저장하지 못했습니다: ' + (e.error || e.status || '오류'));
            await wikiReload(true);
            return false;
          }
        }
      }
      cfgSaveCustoms(pid, aid, a);
      cfgRenderBody();
      return true;
    }

    function cfgResetCustoms(pid, aid) {
      if (!confirm('현재 영역을 기본 실측 데이터로 되돌리시겠습니까?')) return;
      try {
        const raw = localStorage.getItem('fig.cfg.custom_areas_v1');
        if (raw) {
          const map = JSON.parse(raw);
          delete map[pid + '__' + aid];
          localStorage.setItem('fig.cfg.custom_areas_v1', JSON.stringify(map));
        }
      } catch (e) {}
      location.reload();
    }

    function cfgSectionKey(type) {
      return type === 'command' ? 'commands' : type;
    }

    async function cfgMoveBuilderItem(type, pid, aid, idx, dir) {
      const a = cfgAreaOf(pid, aid);
      if (!a) return;
      cfgLoadCustoms(pid, aid, a);
      const key = cfgSectionKey(type);
      const arr = a[key];
      if (!Array.isArray(arr)) return;
      const to = idx + dir;
      if (to < 0 || to >= arr.length) return;
      const tmp = arr[idx];
      arr[idx] = arr[to];
      arr[to] = tmp;
      await cfgPersistArea(pid, aid, a, '서비스 영역 ' + key + ' 순서 변경');
    }

    function cfgItemActsHtml(type, pid, aid, idx, len, editLabel) {
      return '<div class="cfg-item-acts">' +
        '<button type="button" class="cfg-item-btn" onclick="cfgMoveBuilderItem(\'' + type + '\',\'' + pid + '\',\'' + aid + '\',' + idx + ',-1)" title="위로 이동"' + (idx <= 0 ? ' disabled' : '') + '>↑</button>' +
        '<button type="button" class="cfg-item-btn" onclick="cfgMoveBuilderItem(\'' + type + '\',\'' + pid + '\',\'' + aid + '\',' + idx + ',1)" title="아래로 이동"' + (idx >= len - 1 ? ' disabled' : '') + '>↓</button>' +
        '<button type="button" class="cfg-item-btn" onclick="cfgOpenBuilderModal(\'' + type + '\',\'' + pid + '\',\'' + aid + '\',' + idx + ')" title="수정">' + (editLabel || '✏️') + '</button>' +
        '<button type="button" class="cfg-item-btn btn-del" onclick="cfgDeleteBuilderItem(\'' + type + '\',\'' + pid + '\',\'' + aid + '\',' + idx + ')" title="삭제">✕</button>' +
        '</div>';
    }

    // 서비스 영역 직관적 모듈형 렌더러 (설계 · 설정 · 명령어 · 검증 · 오류대응 + 빠른 추가/수정/순서이동)
    function cfgArea(a, pid, aid) {
      if (pid && aid) cfgLoadCustoms(pid, aid, a);
      const useLocalOnly = !(typeof WIKI !== 'undefined' && WIKI.ready && a.docId);
      const isCustomized = (useLocalOnly && pid && aid && localStorage.getItem('fig.cfg.custom_areas_v1') &&
        JSON.parse(localStorage.getItem('fig.cfg.custom_areas_v1'))[pid + '__' + aid]);

      const secs = [];

      // 1. 설계 원칙
      let designHtml = '';
      if (a.design && a.design.length) {
        designHtml += '<ul class="cfg-list">' + a.design.map((d, i) =>
          '<li class="cfg-list-row">' +
          '<div>' + cfgFmt(d) + '</div>' +
          cfgItemActsHtml('design', pid, aid, i, a.design.length, '✏️') +
          '</li>').join('') + '</ul>';
      } else {
        designHtml = '<p class="cfg-empty">등록된 설계 원칙이 없습니다. [+ 원칙 추가] 버튼으로 등록하세요.</p>';
      }
      secs.push([
        '설계',
        '<div class="cfg-sec-header"><span class="cfg-sec-title">📘 설계 원칙</span>' +
        '<div class="cfg-sec-acts">' +
        '<button type="button" class="cfg-btn-add" onclick="cfgOpenBuilderModal(\'design\',\'' + pid + '\',\'' + aid + '\',-1)">+ 원칙 추가</button>' +
        '</div></div>' + designHtml
      ]);

      // 2. 설정 파일
      let configHtml = '';
      if (a.config && a.config.length) {
        configHtml += a.config.map((c, i) =>
          '<div class="cfg-card-item">' +
          '<div class="cfg-card-bar"><span class="cfg-card-idx">설정 #' + (i + 1) + '</span>' +
          cfgItemActsHtml('config', pid, aid, i, a.config.length, '✏️ 수정') + '</div>' +
          cfgCode(c.code, c.label) +
          '</div>').join('');
      } else {
        configHtml = '<p class="cfg-empty">등록된 설정 파일이 없습니다. [+ 설정 추가]로 설정 파일 내용을 등록하세요.</p>';
      }
      secs.push([
        '설정',
        '<div class="cfg-sec-header"><span class="cfg-sec-title">⚙️ 설정 파일</span>' +
        '<div class="cfg-sec-acts">' +
        '<button type="button" class="cfg-btn-add" onclick="cfgOpenBuilderModal(\'config\',\'' + pid + '\',\'' + aid + '\',-1)">+ 설정 추가</button>' +
        '</div></div>' + configHtml
      ]);

      // 3. 명령어
      let cmdHtml = '';
      if (a.commands && a.commands.length) {
        cmdHtml += a.commands.map((c, i) =>
          '<div class="cfg-card-item">' +
          '<div class="cfg-card-bar"><span class="cfg-card-idx">명령 #' + (i + 1) + '</span>' +
          cfgItemActsHtml('command', pid, aid, i, a.commands.length, '✏️ 수정') + '</div>' +
          cfgCode(c.code, c.label, c.cat) +
          '</div>').join('');
      } else {
        cmdHtml = '<p class="cfg-empty">등록된 명령어가 없습니다. [+ 명령어 추가]로 터미널 명령어를 등록하세요.</p>';
      }
      secs.push([
        '명령어',
        '<div class="cfg-sec-header"><span class="cfg-sec-title">💻 실행 명령어</span>' +
        '<div class="cfg-sec-acts">' +
        '<button type="button" class="cfg-btn-add" onclick="cfgOpenBuilderModal(\'command\',\'' + pid + '\',\'' + aid + '\',-1)">+ 명령어 추가</button>' +
        '</div></div>' + cmdHtml
      ]);

      // 4. 검증
      let verifyHtml = '';
      if (a.verify && a.verify.length) {
        verifyHtml += a.verify.map((v, i) =>
          '<div class="cfg-card-item">' +
          '<div class="cfg-card-bar"><span class="cfg-card-idx">검증 #' + (i + 1) + '</span>' +
          cfgItemActsHtml('verify', pid, aid, i, a.verify.length, '✏️ 수정') + '</div>' +
          cfgCode(v.code, v.label, '검증') +
          '<div class="cfg-expect" style="margin-top:4px;"><b>기대 결과:</b> ' + cfgFmt(v.expect) + '</div></div>').join('');
      } else {
        verifyHtml = '<p class="cfg-empty">등록된 검증 항목이 없습니다. [+ 검증 추가]로 테스트 명령을 등록하세요.</p>';
      }
      secs.push([
        '검증',
        '<div class="cfg-sec-header"><span class="cfg-sec-title">✅ 검증 및 기대 결과</span>' +
        '<div class="cfg-sec-acts">' +
        '<button type="button" class="cfg-btn-add" onclick="cfgOpenBuilderModal(\'verify\',\'' + pid + '\',\'' + aid + '\',-1)">+ 검증 추가</button>' +
        '</div></div>' + verifyHtml
      ]);

      // 5. 오류 대응
      let troubleHtml = '';
      if (a.trouble && a.trouble.length) {
        const rowsWithActs = a.trouble.map((t, i) => [
          t[0], t[1], t[2],
          t[3] + '<div style="margin-top:4px;">' +
          cfgItemActsHtml('trouble', pid, aid, i, a.trouble.length, '✏️ 수정') +
          '</div>'
        ]);
        troubleHtml = cfgTable(['증상', '의심 변수·영역', '확인 명령', '조치 및 편집'], rowsWithActs, 'cfg-trouble');
      } else {
        troubleHtml = '<p class="cfg-empty">등록된 오류 대응 가이드가 없습니다. [+ 오류 대응 추가]로 등록하세요.</p>';
      }
      secs.push([
        '오류 시 확인',
        '<div class="cfg-sec-header"><span class="cfg-sec-title">⚠️ 오류 대응 가이드</span>' +
        '<div class="cfg-sec-acts">' +
        '<button type="button" class="cfg-btn-add" onclick="cfgOpenBuilderModal(\'trouble\',\'' + pid + '\',\'' + aid + '\',-1)">+ 오류 대응 추가</button>' +
        '</div></div>' + troubleHtml
      ]);

      // 상단 칩 내비게이션 및 빌더 제어 바
      const chips = '<div class="cfg-chips" style="align-items:center;">' +
        secs.map((s, i) =>
          '<button type="button" class="cfg-chip" onclick="cfgScrollToSec(' + i + ')">' + s[0] + '</button>').join('') +
        (typeof cfgGuideOpen === 'function' && a.docId
          ? '<button type="button" class="cfg-btn-add" style="margin-left:auto;" onclick="cfgGuideOpen({action:\'patch\',kind:\'area\',docId:' + a.docId + '})">📋 지침으로 이 영역 수정/순서편집</button>'
          : '') +
        (isCustomized ? '<button type="button" class="cfg-item-btn btn-del" style="' + (typeof cfgGuideOpen === 'function' && a.docId ? '' : 'margin-left:auto;') + 'padding:3px 8px;" onclick="cfgResetCustoms(\'' + pid + '\',\'' + aid + '\')">↺ 원본 실측값 복원</button>' : '') +
        '</div>';

      return chips + secs.map((s, i) =>
        '<section class="manual-card-box" id="cfg-sec-' + i + '">' + s[1] + '</section>').join('');
    }

    // 서비스 영역 직관적 카드 빌더 모달 (신규 등록 및 수정 팝업)
    function cfgOpenBuilderModal(type, pid, aid, idx) {
      const a = cfgAreaOf(pid, aid);
      if (!a) return;
      cfgLoadCustoms(pid, aid, a);

      const old = document.getElementById('cfg-builder-modal');
      if (old) old.remove();

      let modalTitle = '';
      let fieldsHtml = '';

      if (type === 'command') {
        const isEdit = (idx >= 0);
        const item = isEdit ? (a.commands && a.commands[idx]) : { cat: '조회', label: '', code: '' };
        modalTitle = isEdit ? '💻 명령어 수정' : '💻 새 명령어 등록';
        fieldsHtml =
          '<div class="cfg-builder-field">' +
          '<label class="cfg-builder-label">명령어 유형 (카테고리)</label>' +
          '<div class="cfg-cat-chips">' +
          ['설치', '적용', '조회', '검증'].map(cat =>
            '<label><input type="radio" name="bld-cat" value="' + cat + '" class="cfg-cat-chip-radio"' + (item.cat === cat ? ' checked' : '') + '>' +
            '<span class="cfg-cat-chip-label">' + cat + '</span></label>').join('') +
          '</div></div>' +
          '<div class="cfg-builder-field">' +
          '<label class="cfg-builder-label">명령어 설명 (라벨)</label>' +
          '<input type="text" id="bld-label" class="cfg-builder-input" value="' + cfgEsc(item.label || '') + '" placeholder="예: nova 서비스 구동 상태 확인">' +
          '</div>' +
          '<div class="cfg-builder-field">' +
          '<label class="cfg-builder-label">실행 명령어 (Shell / CLI)</label>' +
          '<textarea id="bld-code" class="cfg-builder-textarea" placeholder="실행할 명령어를 입력하세요 (예: systemctl status nova-compute)">' + cfgEsc(item.code || '') + '</textarea>' +
          '</div>';
      } else if (type === 'config') {
        const isEdit = (idx >= 0);
        const item = isEdit ? (a.config && a.config[idx]) : { label: '', code: '' };
        modalTitle = isEdit ? '⚙️ 설정 파일 수정' : '⚙️ 새 설정 파일 등록';
        fieldsHtml =
          '<div class="cfg-builder-field">' +
          '<label class="cfg-builder-label">설정 파일 경로 및 설명</label>' +
          '<input type="text" id="bld-label" class="cfg-builder-input" value="' + cfgEsc(item.label || '') + '" placeholder="예: /etc/nova/nova.conf (컴퓨트 설정)">' +
          '</div>' +
          '<div class="cfg-builder-field">' +
          '<label class="cfg-builder-label">설정 파일 내용 (Conf / YAML / Script)</label>' +
          '<textarea id="bld-code" class="cfg-builder-textarea" style="min-height:160px;" placeholder="파일 내용을 입력하세요">' + cfgEsc(item.code || '') + '</textarea>' +
          '</div>';
      } else if (type === 'design') {
        const isEdit = (idx >= 0);
        const item = isEdit ? (a.design && a.design[idx]) : '';
        modalTitle = isEdit ? '📘 설계 원칙 수정' : '📘 새 설계 원칙 등록';
        fieldsHtml =
          '<div class="cfg-builder-field">' +
          '<label class="cfg-builder-label">설계 원칙 및 아키텍처 설명</label>' +
          '<textarea id="bld-code" class="cfg-builder-textarea" style="min-height:90px;" placeholder="설계 원칙을 입력하세요 (예: nova-compute는 각 compute 노드에서 up 상태여야 인스턴스가 프로비저닝됩니다)">' + cfgEsc(item || '') + '</textarea>' +
          '</div>';
      } else if (type === 'verify') {
        const isEdit = (idx >= 0);
        const item = isEdit ? (a.verify && a.verify[idx]) : { label: '', code: '', expect: '' };
        modalTitle = isEdit ? '✅ 검증 항목 수정' : '✅ 새 검증 항목 등록';
        fieldsHtml =
          '<div class="cfg-builder-field">' +
          '<label class="cfg-builder-label">검증 항목 라벨</label>' +
          '<input type="text" id="bld-label" class="cfg-builder-input" value="' + cfgEsc(item.label || '') + '" placeholder="예: OpenStack 컴퓨트 서비스 상태 확인">' +
          '</div>' +
          '<div class="cfg-builder-field">' +
          '<label class="cfg-builder-label">검증 명령어</label>' +
          '<textarea id="bld-code" class="cfg-builder-textarea" placeholder="openstack compute service list">' + cfgEsc(item.code || '') + '</textarea>' +
          '</div>' +
          '<div class="cfg-builder-field">' +
          '<label class="cfg-builder-label">기대 결과 (Expectation)</label>' +
          '<input type="text" id="bld-expect" class="cfg-builder-input" value="' + cfgEsc(item.expect || '') + '" placeholder="예: 모든 compute 노드가 Status=enabled, State=up">' +
          '</div>';
      } else if (type === 'trouble') {
        const isEdit = (idx >= 0);
        const item = isEdit ? (a.trouble && a.trouble[idx]) : ['', '', '', ''];
        modalTitle = isEdit ? '⚠️ 오류 대응 수정' : '⚠️ 새 오류 대응 등록';
        fieldsHtml =
          '<div class="cfg-builder-field"><label class="cfg-builder-label">증상 (Symptom)</label>' +
          '<input type="text" id="bld-t0" class="cfg-builder-input" value="' + cfgEsc(item[0] || '') + '" placeholder="예: nova-compute 서비스 down"></div>' +
          '<div class="cfg-builder-field"><label class="cfg-builder-label">의심 변수 및 영역</label>' +
          '<input type="text" id="bld-t1" class="cfg-builder-input" value="' + cfgEsc(item[1] || '') + '" placeholder="예: RAM 부족, 192.168.120.x 통신"></div>' +
          '<div class="cfg-builder-field"><label class="cfg-builder-label">확인 명령</label>' +
          '<input type="text" id="bld-t2" class="cfg-builder-input" value="' + cfgEsc(item[2] || '') + '" placeholder="예: systemctl status nova-compute"></div>' +
          '<div class="cfg-builder-field"><label class="cfg-builder-label">조치 방안</label>' +
          '<input type="text" id="bld-t3" class="cfg-builder-input" value="' + cfgEsc(item[3] || '') + '" placeholder="예: 서비스 재시작 (systemctl restart nova-compute)"></div>';
      }

      const modal = document.createElement('div');
      modal.id = 'cfg-builder-modal';
      modal.className = 'cfg-modal-overlay';
      modal.innerHTML =
        '<div class="cfg-builder-modal-card" role="dialog" aria-modal="true">' +
        '<div class="cfg-builder-modal-head">' +
        '<span>' + modalTitle + '</span>' +
        '<button type="button" class="cfg-win-btn btn-close" id="bld-close" style="color:#cbd5e1;">✕</button>' +
        '</div>' +
        '<div class="cfg-builder-modal-body">' + fieldsHtml + '</div>' +
        '<div class="cfg-modal-foot">' +
        '<button type="button" class="cfg-btn-cancel" id="bld-cancel">취소</button>' +
        '<button type="button" class="cfg-btn-confirm" id="bld-save" style="background:#2563eb;border-color:#3b82f6;">저장 및 즉시 반영</button>' +
        '</div></div>';
      document.body.appendChild(modal);

      const close = () => { modal.remove(); document.removeEventListener('keydown', onKey); };
      const onKey = e => { if (e.key === 'Escape') close(); };
      document.addEventListener('keydown', onKey);

      modal.querySelector('#bld-close').onclick = close;
      modal.querySelector('#bld-cancel').onclick = close;
      modal.querySelector('#bld-save').onclick = async () => {
        if (type === 'command') {
          const cat = (modal.querySelector('input[name="bld-cat"]:checked') || {}).value || '조회';
          const label = (modal.querySelector('#bld-label').value || '').trim();
          const code = (modal.querySelector('#bld-code').value || '').trim();
          if (!code) { alert('명령어 내용을 입력해주세요.'); return; }
          a.commands = a.commands || [];
          if (idx >= 0) a.commands[idx] = { cat, label, code };
          else a.commands.push({ cat, label, code });
        } else if (type === 'config') {
          const label = (modal.querySelector('#bld-label').value || '').trim();
          const code = (modal.querySelector('#bld-code').value || '').trim();
          if (!code) { alert('설정 내용을 입력해주세요.'); return; }
          a.config = a.config || [];
          if (idx >= 0) a.config[idx] = { label, code };
          else a.config.push({ label, code });
        } else if (type === 'design') {
          const code = (modal.querySelector('#bld-code').value || '').trim();
          if (!code) { alert('설계 원칙 내용을 입력해주세요.'); return; }
          a.design = a.design || [];
          if (idx >= 0) a.design[idx] = code;
          else a.design.push(code);
        } else if (type === 'verify') {
          const label = (modal.querySelector('#bld-label').value || '').trim();
          const code = (modal.querySelector('#bld-code').value || '').trim();
          const expect = (modal.querySelector('#bld-expect').value || '').trim();
          if (!code) { alert('검증 명령어를 입력해주세요.'); return; }
          a.verify = a.verify || [];
          if (idx >= 0) a.verify[idx] = { label, code, expect };
          else a.verify.push({ label, code, expect });
        } else if (type === 'trouble') {
          const t0 = (modal.querySelector('#bld-t0').value || '').trim();
          const t1 = (modal.querySelector('#bld-t1').value || '').trim();
          const t2 = (modal.querySelector('#bld-t2').value || '').trim();
          const t3 = (modal.querySelector('#bld-t3').value || '').trim();
          if (!t0 || !t2) { alert('증상과 확인 명령을 입력해주세요.'); return; }
          a.trouble = a.trouble || [];
          if (idx >= 0) a.trouble[idx] = [t0, t1, t2, t3];
          else a.trouble.push([t0, t1, t2, t3]);
        }
        const saveBtn = modal.querySelector('#bld-save');
        if (saveBtn) { saveBtn.disabled = true; saveBtn.textContent = '저장 중…'; }
        const ok = await cfgPersistArea(pid, aid, a, '모듈 빌더 ' + type + (idx >= 0 ? ' 수정' : ' 추가'));
        if (ok) close();
        else if (saveBtn) { saveBtn.disabled = false; saveBtn.textContent = '저장 및 즉시 반영'; }
      };
      modal.onclick = e => { if (e.target === modal) close(); };
    }

    async function cfgDeleteBuilderItem(type, pid, aid, idx) {
      const a = cfgAreaOf(pid, aid);
      if (!a) return;
      cfgLoadCustoms(pid, aid, a);
      if (!confirm('선택한 항목을 삭제하시겠습니까?')) return;
      if (type === 'command' && a.commands) a.commands.splice(idx, 1);
      else if (type === 'config' && a.config) a.config.splice(idx, 1);
      else if (type === 'design' && a.design) a.design.splice(idx, 1);
      else if (type === 'verify' && a.verify) a.verify.splice(idx, 1);
      else if (type === 'trouble' && a.trouble) a.trouble.splice(idx, 1);
      await cfgPersistArea(pid, aid, a, '모듈 빌더 ' + type + ' 삭제');
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

    // ---------- 시점(입장) 렌즈: 전체 · AWS · KT · OpenStack · 온프렘 ----------
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
      const tabs = [VIEW_FOREST].concat(cfgClouds().map(c => ({ id: c, name: CLOUD_NAME[c], cloud: c })));
      return '<nav class="cfg-zoombar" aria-label="기준점 고르기">' + tabs.map(t =>
        '<button type="button" class="cfg-zoom-step' + (t.id === CFG.major ? ' on' : '') + '"' + (t.id === CFG.major ? ' aria-current="page"' : '') +
        ' onclick="' + cfgGo('zoom', t.id, t.id === 'forest' ? 'all' : 'view') + '">' +
        '<span class="cfg-zoom-t">' + (t.cloud ? '<span class="cfg-dot cfg-c-' + t.cloud + '"></span> ' : '') + cfgEsc(t.name) + '</span></button>').join('') + '</nav>';
    }
    function cfgTopologyPage() {
      const ref = (CFG.data.reference || []).find(r => /^전체 토폴로지/.test(r[1] || ''));
      return ref ? cfgPage(ref[0]) : null;
    }
    // 숲: 클라우드별 서버 지도 + 실측 토폴로지 문서(위키)
    function cfgZoomForest() {
      let html = '<div class="cfg-head"><h2 class="cfg-head-title">숲 · 전체 구성</h2><p class="manual-desc">세 클라우드와 그 안 서버가 한 화면에 보입니다. ' +
        '클라우드 이름을 누르면 해당 클라우드 기준 설계로, 서버를 누르면 그 서버의 실제 작업으로 갑니다.</p></div>';
      html += '<div class="cfg-forest">' + cfgClouds().map(c => {
        const list = cfgInstOrder().filter(pid => cfgPage(pid).cloud === c);
        return '<section class="cfg-forest-cloud"><button type="button" class="cfg-forest-name" onclick="' + cfgGo('zoom', c, 'view') + '">' +
          '<span class="cfg-dot cfg-c-' + c + '"></span>' + cfgEsc(CLOUD_NAME[c]) + '<small>' + list.length + '대</small></button>' +
          list.map(pid => {
            const p = cfgPage(pid);
            return '<button type="button" class="cfg-forest-inst" onclick="' + cfgGo('zoom', c, pid) + '"><b>' + cfgEsc(p.short) + '</b>' +
              (p.status && p.status !== 'live' ? ' ' + cfgBadge(p.status) : '') + '<span>' + cfgEsc(p.tag) + '</span></button>';
          }).join('') + '</section>';
      }).join('') + '</div>';
      const topo = cfgTopologyPage();
      return html + (topo ? cfgDoc(topo) : '<div class="cfg-empty-panel"><p>실측 토폴로지 문서(“전체 토폴로지 · 실측”)가 아직 없습니다. 참고 문서로 추가하면 여기에 나옵니다.</p></div>');
    }
    // 클라우드 입장: 위키의 '시점 · <클라우드>' 문서(실측 연결·의존·멈추면) + 이 클라우드 안 구성 요약
    function cfgCloudView(c) {
      const list = cfgInstOrder().filter(pid => cfgPage(pid).cloud === c);
      const vp = cfgViewPage(c);
      let html = vp ? cfgDoc(vp) : '<div class="cfg-empty-panel"><p>“시점 · ' + cfgEsc(CLOUD_NAME[c]) + '” 문서가 아직 없습니다. 참고 문서로 추가하면 여기에 나옵니다.</p></div>';
      if (!list.length) return html;
      const areas = [], troubles = [], doms = {};
      list.forEach(pid => { const p = cfgPage(pid); p.areas.forEach(a => {
        areas.push([p, a]); (a.trouble || []).forEach(t => troubles.push([p, a, t]));
        a.domains.forEach(d => { doms[d] = (doms[d] || 0) + 1; });
      }); });
      const first = t => { t = String(t || ''); const i = t.search(/[.。]\s/); return (i > 0 ? t.slice(0, i + 1) : t).slice(0, 120); };
      html += '<h3 class="cfg-h">이 클라우드 안 — 서버 ' + list.length + '대 · 서비스 영역 ' + areas.length + '개 · 알려진 오류 대응 ' + troubles.length + '건</h3>';
      html += '<section class="manual-card-box"><h3 class="box-title">서버별 역할</h3>' + cfgTable(['서버', '역할', '서비스 영역', '상태'], list.map(pid => {
        const p = cfgPage(pid);
        return [p.short, first(p.desc), p.areas.map(a => a.name).join(', '), STATUS_NAME[p.status] || p.status || ''];
      })) + '<div class="cfg-chips">' + list.map(pid => '<a href="javascript:void(0)" class="cfg-chip" onclick="' + cfgGo('zoom', c, pid) + '">' + cfgEsc(cfgPage(pid).short) + ' 작업 ›</a>').join('') + '</div></section>';
      html += '<section class="manual-card-box"><h3 class="box-title">맡은 서비스 분류</h3><div class="cfg-chips">' + Object.keys(doms).map(d =>
        '<a href="javascript:void(0)" class="cfg-chip" onclick="' + cfgGo('svc', d, '') + '">' + cfgEsc((cfgDomain(d) || { name: d }).name) + ' ' + doms[d] + '</a>').join('') + '</div></section>';
      if (troubles.length) html += '<section class="manual-card-box"><h3 class="box-title">알려진 오류 증상</h3>' +
        cfgTable(['서버 / 영역', '증상', '의심 지점', '조치'], troubles.slice(0, 12).map(x => [x[0].short + ' / ' + x[1].name, x[2][0], x[2][1], x[2][3]]), 'cfg-trouble') +
        (troubles.length > 12 ? '<p class="manual-desc">외 ' + (troubles.length - 12) + '건은 참고 › 오류 확인 색인에서 봅니다.</p>' : '') + '</section>';
      return html;
    }
    // 서버 작업: 서버 하나에서 실제로 실행하는 것 — 명령·검증 + 터미널 바로 열기
    function cfgZoomMember(pid) {
      const p = cfgPage(pid);
      if (!p) return '<div class="cfg-empty-panel"><p>서버를 고르세요.</p></div>';
      let html = '<div class="cfg-head"><div class="cfg-head-line"><span class="cfg-cloud cfg-c-' + p.cloud + '">' + cfgEsc(CLOUD_NAME[p.cloud]) + '</span>' +
        '<span class="cfg-head-inst">' + cfgEsc(p.title) + '</span><span class="manual-tag">서버 작업</span></div>' +
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

    // ===== [설정] 터미널 즉시 실행 러너 & 안전 가드 & 푸터 닥 & 플로팅 윈도우 =====
    const CFG_RUNNER = {
      sessions: {},    // id: { id, target, label, code, ws, term, fit, winEl, chipEl, status, x, y, w, h, min, max }
      zIndex: 1110,
      seq: 0,
      storageKey: 'fig.cfg.terminals_v1'
    };

    // 1. 위험 명령어 판별: 서비스 중지/재시작/종료/생성 등 파괴적 명령
    function cfgIsDangerous(code, cat) {
      const str = (code || '').trim();
      const dangerPatterns = [
        /\b(systemctl\s+(stop|restart|reload|disable|mask|poweroff|reboot))\b/i,
        /\b(service\s+\w+\s+(stop|restart|reload))\b/i,
        /\b(docker\s+(stop|restart|rm|kill|down))\b/i,
        /\b(kubectl\s+(delete|drain|cordon|scale|rollout\s+restart|apply|replace))\b/i,
        /\b(openstack-vm\.sh\s+(stop|restart))\b/i,
        /\b(virsh\s+(destroy|shutdown|reboot|undefine|reset))\b/i,
        /\b(openstack\s+\w+\s+(delete|set|create|remove|add))\b/i,
        /\b(stop\s+replica|reset\s+master|drop\s+database|drop\s+table|truncate|purge\s+binary)\b/i,
        /\b(rm\s+-[rf]|kill\s+-9|pkill|killall|reboot|shutdown|poweroff|halt)\b/i,
        /\b(iptables\s+-[fzxad]|ip\s+link\s+set.*down|wg-quick\s+down|mkfs|fdisk)\b/i
      ];
      for (let i = 0; i < dangerPatterns.length; i++) {
        if (dangerPatterns[i].test(str)) return true;
      }
      if ((cat === '적용' || cat === '설치') && /\b(sed\s+-i|tee|mv|cp|export|git\s+pull|curl.*\|\s*(bash|sh))\b/i.test(str)) {
        return true;
      }
      return false;
    }

    // 2. 대상 인스턴스/타겟 지능형 탐지
    function cfgDetectTarget(code, label, cat) {
      const text = ((code || '') + ' ' + (label || '')).toLowerCase();
      if (text.includes('160') || text.includes('keystonerc') || text.includes('openstack') || text.includes('nova') || text.includes('glance') || text.includes('neutron')) return 'controller';
      if (text.includes('161')) return 'compute1';
      if (text.includes('163')) return 'compute3';
      if (text.includes('164')) return 'compute4';
      if (text.includes('cp1') || text.includes('kubectl') || text.includes('k3s server') || text.includes('kube-vip')) return 'k8s-cp1';
      if (text.includes('w1') || text.includes('k3s agent')) return 'k8s-w1';
      if (text.includes('db-01') || text.includes('mysql') || text.includes('mariadb') || text.includes('gtid')) return 'db-01';
      if (text.includes('kt-edge') || text.includes('nginx') || text.includes('ktcloud') || text.includes('kt-')) return 'kt-edge';
      if (text.includes('aws-dr') || text.includes('dr-') || text.includes('minwon-mysql')) return 'aws-dr';
      if (text.includes('aws-ctl') || text.includes('prometheus') || text.includes('grafana')) return 'aws-ctl';

      const cur = (CFG.major || '').toLowerCase();
      if (cur.includes('controller')) return 'controller';
      if (cur.includes('compute1')) return 'compute1';
      if (cur.includes('compute3')) return 'compute3';
      if (cur.includes('compute4')) return 'compute4';
      if (cur.includes('cp1')) return 'k8s-cp1';
      if (cur.includes('w1')) return 'k8s-w1';
      if (cur.includes('db')) return 'db-01';
      if (cur.includes('kt')) return 'kt-edge';
      if (cur.includes('dr')) return 'aws-dr';
      if (cur.includes('ctl')) return 'aws-ctl';
      return 'controller';
    }

    // 3. 레이어 초기화 (body에 고정)
    function cfgEnsureLayers() {
      let fl = document.getElementById('cfg-float-layer');
      if (!fl) {
        fl = document.createElement('div');
        fl.id = 'cfg-float-layer';
        document.body.appendChild(fl);
      }
      let dock = document.getElementById('cfg-footer-dock');
      if (!dock) {
        dock = document.createElement('div');
        dock.id = 'cfg-footer-dock';
        dock.className = 'cfg-dock-hidden';
        dock.innerHTML = '<span class="cfg-dock-title">🖥️ 터미널 세션</span>' +
          '<div class="cfg-dock-list" id="cfg-dock-list"></div>' +
          '<div class="cfg-dock-acts">' +
          '<button type="button" class="cfg-dock-btn" onclick="cfgToggleAllMin(true)" title="모두 최소화">_ 숨김</button>' +
          '<button type="button" class="cfg-dock-btn" onclick="cfgToggleAllMin(false)" title="모두 펼치기">□ 표시</button>' +
          '<button type="button" class="cfg-dock-btn" onclick="cfgCloseAllTerms()" title="모두 닫기">✕ 종료</button>' +
          '</div>';
        document.body.appendChild(dock);
      }
      return { fl, dock };
    }

    // 4. 실행 버튼 핸들러 (뷰/확인 vs 수정/변경 분리)
    function cfgRunCode(idx) {
      const item = (CFG.codeMeta && CFG.codeMeta[idx]) || { code: CFG.codes[idx] || '', label: '', cat: '' };
      const target = cfgDetectTarget(item.code, item.label, item.cat);
      if (target === 's1') {
        alert('s1 호스트는 웹에서 콘솔 터미널 접근 및 명령 실행이 불가합니다.');
        return;
      }
      const isDangerous = cfgIsDangerous(item.code, item.cat) || item.cat === '적용' || item.cat === '설치';
      if (isDangerous) {
        cfgShowConfirm(item.code, target, item.label, () => {
          cfgOpenAndExec(item.code, target, item.label, true, null, 'modify');
        });
      } else {
        cfgOpenAndExec(item.code, target, item.label, true, null, 'view');
      }
    }

    // 4-1. 뷰 모드 팝업 (안전 확인 · 읽기 전용)
    function cfgViewCode(idx) {
      const item = (CFG.codeMeta && CFG.codeMeta[idx]) || { code: CFG.codes[idx] || '', label: '', cat: '' };
      const target = cfgDetectTarget(item.code, item.label, item.cat);
      const filePath = cfgExtractFilePath(item.label, item.code);

      const old = document.getElementById('cfg-view-modal');
      if (old) old.remove();

      const modal = document.createElement('div');
      modal.id = 'cfg-view-modal';
      modal.className = 'cfg-modal-overlay cfg-modal-view';
      modal.innerHTML = '<div class="cfg-modal-card" role="dialog" aria-modal="true">' +
        '<div class="cfg-modal-head"><span>👁️ 설정 및 명령어 확인 (뷰 모드 · 읽기 전용)</span><span style="font-size:12px;opacity:0.8;">ESC로 닫기</span></div>' +
        '<div class="cfg-modal-body">' +
        '<div class="cfg-modal-alert"><b>안내:</b> 본 뷰 모드는 시스템 변경 없이 안전하게 설정 파일 및 명령어 구성을 사전 확인·열람하는 모드입니다.</div>' +
        '<div class="cfg-modal-meta">대상 노드: <strong>' + cfgEsc(target) + '</strong> &nbsp;|&nbsp; 항목/파일: ' + cfgEsc(item.label || '설정') + '</div>' +
        '<pre class="cfg-modal-code" style="max-height:260px;">' + cfgEsc(item.code) + '</pre>' +
        '</div>' +
        '<div class="cfg-modal-foot">' +
        '<button type="button" class="cfg-btn-cancel" id="cfg-view-close">닫기</button>' +
        '<button type="button" class="cfg-run-btn cfg-btn-view" id="cfg-view-cat-run">터미널 cat 읽기 전용 확인</button>' +
        '</div>' +
        '</div>';
      document.body.appendChild(modal);

      const close = () => { modal.remove(); document.removeEventListener('keydown', onKey); };
      const onKey = e => { if (e.key === 'Escape') close(); };
      document.addEventListener('keydown', onKey);

      modal.querySelector('#cfg-view-close').onclick = close;
      modal.querySelector('#cfg-view-cat-run').onclick = () => {
        close();
        if (target === 's1') {
          alert('s1 호스트는 웹 콘솔 터미널 접근 불가 대상입니다.');
          return;
        }
        const catCmd = (filePath && filePath.startsWith('/')) ? ('cat ' + filePath) : item.code;
        cfgOpenAndExec(catCmd, target, (item.label || '') + ' (cat 확인)', true, null, 'view');
      };
      modal.onclick = e => { if (e.target === modal) close(); };
    }

    // 4-2. 빨강색 수정/변경(vi/nano) 핸들러 및 사전 경고 모달
    function cfgEditCode(idx) {
      const item = (CFG.codeMeta && CFG.codeMeta[idx]) || { code: CFG.codes[idx] || '', label: '', cat: '' };
      const target = cfgDetectTarget(item.code, item.label, item.cat);
      if (target === 's1') {
        alert('s1 호스트는 웹에서 콘솔 터미널 접근 및 설정 수정이 불가합니다.');
        return;
      }
      const filePath = cfgExtractFilePath(item.label, item.code);

      const old = document.getElementById('cfg-edit-modal');
      if (old) old.remove();

      const modal = document.createElement('div');
      modal.id = 'cfg-edit-modal';
      modal.className = 'cfg-modal-overlay cfg-modal-danger';
      modal.innerHTML = '<div class="cfg-modal-card" role="dialog" aria-modal="true">' +
        '<div class="cfg-modal-head">⚠️ 설정 파일 수정/변경 사전 확인 (vi / nano)</div>' +
        '<div class="cfg-modal-body">' +
        '<div class="cfg-modal-alert"><b>경고:</b> 운영 노드의 설정 파일을 직접 열어 수정하거나 구성을 변경합니다. 잘못된 설정 값이나 문법 오류는 서비스 다운타임의 원인이 될 수 있습니다. 사전 확인 후 신중히 진행하십시오.</div>' +
        '<div class="cfg-modal-meta">대상 노드: <strong>' + cfgEsc(target) + '</strong> &nbsp;|&nbsp; 대상 파일: <strong>' + cfgEsc(filePath) + '</strong></div>' +
        '<div style="font-size:12.5px;color:#cbd5e1;margin-top:2px;"><b>접근 편집기 방식 선택:</b></div>' +
        '<div style="display:flex;gap:14px;font-size:12.5px;color:#e2e8f0;background:#090d16;padding:10px 12px;border-radius:6px;border:1px solid #334155;flex-wrap:wrap;">' +
        '<label style="display:flex;align-items:center;gap:6px;cursor:pointer;"><input type="radio" name="cfg-editor" value="vi" checked> <b>vi 편집기</b> (sudo vi ' + cfgEsc(filePath) + ')</label>' +
        '<label style="display:flex;align-items:center;gap:6px;cursor:pointer;"><input type="radio" name="cfg-editor" value="nano"> <b>nano 편집기</b> (sudo nano ' + cfgEsc(filePath) + ')</label>' +
        '<label style="display:flex;align-items:center;gap:6px;cursor:pointer;"><input type="radio" name="cfg-editor" value="apply"> <b>직접 덮어쓰기 적용</b></label>' +
        '</div>' +
        '<pre class="cfg-modal-code" style="max-height:120px;">' + cfgEsc(item.code) + '</pre>' +
        '</div>' +
        '<div class="cfg-modal-foot">' +
        '<button type="button" class="cfg-btn-cancel" id="cfg-edit-cancel">취소</button>' +
        '<button type="button" class="cfg-btn-confirm" id="cfg-edit-ok" style="background:#dc2626;border-color:#ef4444;color:#fff;font-weight:700;">확인 후 편집 터미널 실행</button>' +
        '</div>' +
        '</div>';
      document.body.appendChild(modal);

      const close = () => { modal.remove(); document.removeEventListener('keydown', onKey); };
      const onKey = e => { if (e.key === 'Escape') close(); };
      document.addEventListener('keydown', onKey);

      modal.querySelector('#cfg-edit-cancel').onclick = close;
      modal.querySelector('#cfg-edit-ok').onclick = () => {
        const choice = modal.querySelector('input[name="cfg-editor"]:checked').value;
        close();
        let cmdToRun = '';
        if (choice === 'vi') cmdToRun = 'sudo vi ' + filePath;
        else if (choice === 'nano') cmdToRun = 'sudo nano ' + filePath;
        else cmdToRun = "sudo bash -c 'cat << \"EOF\" > " + filePath + "\n" + item.code.trim() + "\nEOF'";

        cfgOpenAndExec(cmdToRun, target, item.label + ' (' + choice + ' 수정)', true, null, 'modify');
      };
      modal.onclick = e => { if (e.target === modal) close(); };
    }

    // 5. 위험 명령어 사전 확인 모달 (빨강색 경고 확인)
    function cfgShowConfirm(code, target, label, onConfirm) {
      const old = document.getElementById('cfg-confirm-modal');
      if (old) old.remove();

      const modal = document.createElement('div');
      modal.id = 'cfg-confirm-modal';
      modal.className = 'cfg-modal-overlay cfg-modal-danger';
      modal.innerHTML = '<div class="cfg-modal-card" role="dialog" aria-modal="true">' +
        '<div class="cfg-modal-head">⚠️ 시스템 수정/변경 실행 사전 확인</div>' +
        '<div class="cfg-modal-body">' +
        '<div class="cfg-modal-alert"><b>경고:</b> 이 명령은 서비스 중지, 재시작, 삭제 또는 시스템 구성을 직접 변경할 수 있습니다. 운영 환경에 미치는 영향을 확인하신 후 신중히 실행해 주세요.</div>' +
        '<div class="cfg-modal-meta">대상 노드: <strong>' + cfgEsc(target) + '</strong> &nbsp;|&nbsp; 작업: ' + cfgEsc(label || '설정 수정/변경') + '</div>' +
        '<pre class="cfg-modal-code">' + cfgEsc(code) + '</pre>' +
        '</div>' +
        '<div class="cfg-modal-foot">' +
        '<button type="button" class="cfg-btn-cancel" id="cfg-modal-cancel">취소</button>' +
        '<button type="button" class="cfg-btn-confirm" id="cfg-modal-ok" style="background:#dc2626;border-color:#ef4444;color:#fff;font-weight:700;">확인 후 변경 실행</button>' +
        '</div>' +
        '</div>';
      document.body.appendChild(modal);

      const close = () => { modal.remove(); document.removeEventListener('keydown', onKey); };
      const onKey = e => { if (e.key === 'Escape') close(); };
      document.addEventListener('keydown', onKey);

      modal.querySelector('#cfg-modal-cancel').onclick = close;
      modal.querySelector('#cfg-modal-ok').onclick = () => {
        close();
        if (typeof onConfirm === 'function') onConfirm();
      };
      modal.onclick = e => { if (e.target === modal) close(); };
      modal.querySelector('#cfg-modal-ok').focus();
    }

    // 6. xterm fallback 로더
    async function cfgEnsureXterm() {
      if (typeof csLoadXterm === 'function') {
        await csLoadXterm();
        return;
      }
      if (window.Terminal && window.FitAddon) return;
      const add = (tag, attrs) => new Promise((ok, bad) => {
        const el = document.createElement(tag); Object.assign(el, attrs); el.onload = ok; el.onerror = bad; document.head.appendChild(el);
      });
      const CS_XTERM = 'https://cdn.jsdelivr.net/npm/@xterm/xterm@5.5.0';
      const CS_FIT = 'https://cdn.jsdelivr.net/npm/@xterm/addon-fit@0.10.0';
      await Promise.all([
        add('link', { rel: 'stylesheet', href: CS_XTERM + '/css/xterm.min.css' }),
        add('script', { src: CS_XTERM + '/lib/xterm.min.js' })
      ]);
      await add('script', { src: CS_FIT + '/lib/addon-fit.min.js' });
    }

    // 6-1. 세션 웹소켓 재연결 헬퍼
    function cfgReconnectAndSend(s, code) {
      const wsProto = location.protocol === 'https:' ? 'wss:' : 'ws:';
      const u = typeof csOwner === 'function' ? csOwner() : 'team';
      const wsUrl = wsProto + '//' + location.host + '/console/ws/' + encodeURIComponent(s.target) +
        '?cols=' + s.term.cols + '&rows=' + s.term.rows + '&u=' + encodeURIComponent(u);
      s.term.write('\r\n\x1b[33m[연결 재시도 중…]\x1b[0m\r\n');
      try {
        const ws = new WebSocket(wsUrl);
        s.ws = ws;
        ws.onopen = () => {
          s.status = 'ok';
          const statDot = s.winEl.querySelector('.cfg-win-status-dot');
          const statText = s.winEl.querySelector('.cfg-win-status-text');
          if (statDot) statDot.className = 'cfg-win-status-dot';
          if (statText) statText.textContent = '연결됨';
          cfgUpdateChipStatus(s.id, true);
          s.term.focus();
          try { s.fit.fit(); } catch (e) {}
          if (code) {
            setTimeout(() => {
              if (ws.readyState === 1) ws.send(JSON.stringify({ t: 'i', d: code.trim() + '\r' }));
            }, 500);
          }
        };
        ws.onmessage = e => s.term.write(e.data);
        ws.onclose = e => {
          s.status = 'off';
          const statDot = s.winEl.querySelector('.cfg-win-status-dot');
          const statText = s.winEl.querySelector('.cfg-win-status-text');
          if (statDot) statDot.className = 'cfg-win-status-dot off';
          if (statText) statText.textContent = '연결 끊김 (' + e.code + ')';
          cfgUpdateChipStatus(s.id, false);
        };
        s.term.onData(d => { if (s.ws && s.ws.readyState === 1) s.ws.send(JSON.stringify({ t: 'i', d: d })); });
        s.term.onResize(sz => { if (s.ws && s.ws.readyState === 1) s.ws.send(JSON.stringify({ t: 'r', c: sz.cols, r: sz.rows })); });
      } catch (err) {
        s.term.write('\r\n\x1b[31m[재연결 실패: ' + err.message + ']\x1b[0m\r\n');
      }
    }

    // 7. 터미널 윈도우 생성 및 명령 자동 실행 (뷰/수정 분리 및 기존 창 재사용)
    async function cfgOpenAndExec(code, target, label, autoExec = true, saved = null, mode = null) {
      try {
        await cfgEnsureXterm();
      } catch (err) {
        alert('터미널 화면(xterm.js) 로드에 실패했습니다. 네트워크 연결을 확인하세요.');
        return;
      }

      const { fl, dock } = cfgEnsureLayers();
      const actualMode = mode || (saved && saved.mode) || (cfgIsDangerous(code, '') || (label && (label.includes('수정') || label.includes('적용'))) ? 'modify' : 'view');
      const id = saved ? saved.id : ('term__' + target + '__' + actualMode);

      // 동일한 인스턴스/모드의 창이 이미 띄워져 있는 경우: 새 창을 열지 않고 그 창에서 실행!
      const existing = CFG_RUNNER.sessions[id];
      if (existing) {
        if (existing.min) {
          existing.min = false;
          existing.winEl.classList.remove('minimized');
        }
        cfgFocusWin(id);
        if (label) {
          existing.label = label;
          const titleText = existing.winEl.querySelector('.cfg-win-title-text');
          if (titleText) titleText.textContent = cfgEsc(label);
        }
        setTimeout(() => { try { existing.fit.fit(); } catch (e) {} }, 50);

        if (autoExec && code) {
          existing.code = code;
          const banner = '\r\n\x1b[36m[FIG Runner ⚡ ' + (actualMode === 'modify' ? '수정/변경' : '조회/확인') + ' 실행] ' + (label ? label + '\r\n' : '') + '\x1b[0m';
          existing.term.write(banner);

          if (existing.ws && existing.ws.readyState === 1) {
            existing.ws.send(JSON.stringify({ t: 'i', d: code.trim() + '\r' }));
          } else {
            cfgReconnectAndSend(existing, code);
          }
        }
        cfgRenderDock();
        cfgSaveState();
        return;
      }

      // 위치 및 크기 계산
      const count = Object.keys(CFG_RUNNER.sessions).length;
      const offset = (count % 6) * 30;
      const defaultW = Math.min(680, window.innerWidth - 40);
      const defaultH = Math.min(420, window.innerHeight - 100);
      const defaultX = Math.max(20, Math.min(window.innerWidth - defaultW - 30, 50 + offset));
      const defaultY = Math.max(30, Math.min(window.innerHeight - defaultH - 60, 60 + offset));

      const x = saved && saved.x != null ? saved.x : defaultX;
      const y = saved && saved.y != null ? saved.y : defaultY;
      const w = saved && saved.w != null ? saved.w : defaultW;
      const h = saved && saved.h != null ? saved.h : defaultH;
      const isMin = saved && saved.min ? true : false;
      const isMax = saved && saved.max ? true : false;

      // 윈도우 엘리먼트 생성
      const win = document.createElement('div');
      win.id = id;
      win.className = 'cfg-win' + (isMin ? ' minimized' : '') + (isMax ? ' maximized' : '');
      win.style.left = x + 'px';
      win.style.top = y + 'px';
      win.style.width = w + 'px';
      win.style.height = h + 'px';
      win.style.zIndex = String(++CFG_RUNNER.zIndex);

      const modeBadgeClass = actualMode === 'modify' ? 'cfg-badge-modify' : 'cfg-badge-view';
      const modeBadgeText = actualMode === 'modify' ? (target + ' · 수정/변경') : (target + ' · 뷰/확인');

      win.innerHTML = '<div class="cfg-win-head">' +
        '<div class="cfg-win-title">' +
        '<span class="cfg-win-badge ' + modeBadgeClass + '">' + cfgEsc(modeBadgeText) + '</span>' +
        '<span class="cfg-win-title-text">' + cfgEsc(label || '명령어 실행') + '</span>' +
        '</div>' +
        '<div class="cfg-win-ctrls">' +
        '<button type="button" class="cfg-win-btn btn-min" title="최소화">_</button>' +
        '<button type="button" class="cfg-win-btn btn-max" title="최대화">□</button>' +
        '<button type="button" class="cfg-win-btn btn-close" title="닫기">✕</button>' +
        '</div>' +
        '</div>' +
        '<div class="cfg-win-body"></div>' +
        '<div class="cfg-win-foot">' +
        '<div class="cfg-win-status">' +
        '<span class="cfg-win-status-dot wait"></span>' +
        '<span class="cfg-win-status-text">연결 준비 중…</span>' +
        '</div>' +
        '<span class="cfg-win-hint">자동 실행 & 터미널 상호작용 가능</span>' +
        '</div>';

      fl.appendChild(win);

      const winBody = win.querySelector('.cfg-win-body');
      const statDot = win.querySelector('.cfg-win-status-dot');
      const statText = win.querySelector('.cfg-win-status-text');

      // xterm 인스턴스 초기화
      const term = new window.Terminal({
        cursorBlink: true,
        fontFamily: "'JetBrains Mono', Consolas, monospace",
        fontSize: 13,
        scrollback: 5000,
        theme: {
          background: '#06090e',
          foreground: '#e2e8f0',
          cursor: '#93c5fd',
          selectionBackground: '#1e3a8a'
        }
      });
      const fit = new window.FitAddon.FitAddon();
      term.loadAddon(fit);
      term.open(winBody);
      setTimeout(() => { try { fit.fit(); } catch (e) {} }, 50);

      // 드래그 기능 (헤더 잡고 이동)
      const head = win.querySelector('.cfg-win-head');
      head.addEventListener('mousedown', e => {
        if (e.target.closest('.cfg-win-ctrls')) return;
        cfgFocusWin(id);
        if (win.classList.contains('maximized')) return;
        let startX = e.clientX, startY = e.clientY;
        let origX = win.offsetLeft, origY = win.offsetTop;
        const onMove = ev => {
          let nx = origX + (ev.clientX - startX);
          let ny = origY + (ev.clientY - startY);
          nx = Math.max(10, Math.min(window.innerWidth - 80, nx));
          ny = Math.max(10, Math.min(window.innerHeight - 80, ny));
          win.style.left = nx + 'px';
          win.style.top = ny + 'px';
          const s = CFG_RUNNER.sessions[id];
          if (s) { s.x = nx; s.y = ny; }
        };
        const onUp = () => {
          document.removeEventListener('mousemove', onMove);
          document.removeEventListener('mouseup', onUp);
          cfgSaveState();
        };
        document.addEventListener('mousemove', onMove);
        document.addEventListener('mouseup', onUp);
      });

      win.addEventListener('mousedown', () => cfgFocusWin(id));

      // 리사이즈 감지 (ResizeObserver)
      if (window.ResizeObserver) {
        const ro = new ResizeObserver(() => {
          if (!win.classList.contains('minimized')) {
            try { fit.fit(); } catch (e) {}
            const s = CFG_RUNNER.sessions[id];
            if (s && !win.classList.contains('maximized')) {
              s.w = win.offsetWidth;
              s.h = win.offsetHeight;
              cfgSaveState();
            }
          }
        });
        ro.observe(win);
      }

      // 컨트롤 버튼 이벤트
      win.querySelector('.btn-min').onclick = () => cfgToggleMin(id);
      win.querySelector('.btn-max').onclick = () => cfgToggleMax(id);
      win.querySelector('.btn-close').onclick = () => cfgCloseTerm(id);

      // 세션 등록
      const session = {
        id, target, mode: actualMode, label, code, term, fit, winEl: win,
        x, y, w, h, min: isMin, max: isMax,
        status: 'wait', autoExec
      };
      CFG_RUNNER.sessions[id] = session;

      // WebSocket 연결
      const wsProto = location.protocol === 'https:' ? 'wss:' : 'ws:';
      const u = typeof csOwner === 'function' ? csOwner() : 'team';
      const wsUrl = wsProto + '//' + location.host + '/console/ws/' + encodeURIComponent(target) +
        '?cols=' + term.cols + '&rows=' + term.rows + '&u=' + encodeURIComponent(u);
      
      let ws = null;
      try {
        ws = new WebSocket(wsUrl);
      } catch (e) {
        statDot.className = 'cfg-win-status-dot off';
        statText.textContent = '웹소켓 연결 오류';
        term.write('\r\n\x1b[31m[웹소켓 연결 실패: ' + e.message + ']\x1b[0m\r\n');
      }

      if (ws) {
        session.ws = ws;
        ws.onopen = () => {
          session.status = 'ok';
          statDot.className = 'cfg-win-status-dot';
          statText.textContent = '연결됨';
          cfgUpdateChipStatus(id, true);
          term.focus();
          try { fit.fit(); } catch (e) {}
          if (autoExec && code) {
            term.write('\r\n\x1b[36m[FIG Runner ⚡ ' + (actualMode === 'modify' ? '수정/변경' : '조회/확인') + ' 실행] 대상: ' + target + '\x1b[0m\r\n');
            setTimeout(() => {
              if (ws.readyState === 1) {
                ws.send(JSON.stringify({ t: 'i', d: code.trim() + '\r' }));
              }
            }, 600);
          }
        };
        ws.onmessage = e => term.write(e.data);
        ws.onclose = e => {
          session.status = 'off';
          statDot.className = 'cfg-win-status-dot off';
          const msg = e.code === 1000 ? '세션 종료' : ('연결 끊김 (' + e.code + ')');
          statText.textContent = msg;
          cfgUpdateChipStatus(id, false);
          term.write('\r\n\x1b[33m[' + msg + ']\x1b[0m\r\n');
        };
        term.onData(d => { if (ws.readyState === 1) ws.send(JSON.stringify({ t: 'i', d: d })); });
        term.onResize(sz => { if (ws.readyState === 1) ws.send(JSON.stringify({ t: 'r', c: sz.cols, r: sz.rows })); });
      }

      cfgRenderDock();
      cfgSaveState();
      cfgFocusWin(id);
    }

    // 8. 윈도우 포커스 처리
    function cfgFocusWin(id) {
      const s = CFG_RUNNER.sessions[id];
      if (!s) return;
      document.querySelectorAll('.cfg-win').forEach(w => w.classList.remove('cfg-focus'));
      s.winEl.classList.add('cfg-focus');
      s.winEl.style.zIndex = String(++CFG_RUNNER.zIndex);
      document.querySelectorAll('.cfg-dock-chip').forEach(c => c.classList.remove('active'));
      const chip = document.getElementById('chip-' + id);
      if (chip) chip.classList.add('active');
      if (s.term) s.term.focus();
    }

    // 9. 최소화 / 최대화 / 닫기
    function cfgToggleMin(id) {
      const s = CFG_RUNNER.sessions[id];
      if (!s) return;
      s.min = !s.min;
      s.winEl.classList.toggle('minimized', s.min);
      if (!s.min) {
        cfgFocusWin(id);
        setTimeout(() => { try { s.fit.fit(); } catch (e) {} }, 50);
      }
      cfgSaveState();
    }

    function cfgToggleMax(id) {
      const s = CFG_RUNNER.sessions[id];
      if (!s) return;
      s.max = !s.max;
      s.winEl.classList.toggle('maximized', s.max);
      setTimeout(() => { try { s.fit.fit(); } catch (e) {} }, 50);
      cfgSaveState();
    }

    function cfgCloseTerm(id) {
      const s = CFG_RUNNER.sessions[id];
      if (!s) return;
      if (s.ws) {
        try { s.ws.close(); } catch (e) {}
      }
      if (s.term) {
        try { s.term.dispose(); } catch (e) {}
      }
      if (s.winEl) s.winEl.remove();
      delete CFG_RUNNER.sessions[id];
      cfgRenderDock();
      cfgSaveState();
    }

    function cfgToggleAllMin(min) {
      Object.keys(CFG_RUNNER.sessions).forEach(id => {
        const s = CFG_RUNNER.sessions[id];
        s.min = min;
        s.winEl.classList.toggle('minimized', min);
      });
      cfgSaveState();
    }

    function cfgCloseAllTerms() {
      const ids = Object.keys(CFG_RUNNER.sessions);
      if (!ids.length) return;
      if (!confirm('열려 있는 모든 터미널 창(' + ids.length + '개)을 종료하시겠습니까?')) return;
      ids.forEach(id => cfgCloseTerm(id));
    }

    // 10. 하단 푸터 닥(Footer Dock) 렌더링 (뷰 / 수정 라벨 구분)
    function cfgRenderDock() {
      const dock = document.getElementById('cfg-footer-dock');
      const list = document.getElementById('cfg-dock-list');
      if (!dock || !list) return;

      const ids = Object.keys(CFG_RUNNER.sessions);
      if (ids.length === 0) {
        dock.classList.add('cfg-dock-hidden');
        list.innerHTML = '';
        return;
      }

      dock.classList.remove('cfg-dock-hidden');
      list.innerHTML = ids.map(id => {
        const s = CFG_RUNNER.sessions[id];
        const isOk = s.status === 'ok';
        const modeTxt = s.mode === 'modify' ? '수정' : '뷰';
        const chipCls = s.mode === 'modify' ? 'chip-modify' : 'chip-view';
        return '<div class="cfg-dock-chip ' + chipCls + '" id="chip-' + id + '" onclick="cfgOnChipClick(\'' + id + '\')">' +
          '<span class="cfg-dock-chip-dot ' + (isOk ? '' : 'off') + '"></span>' +
          '<span class="cfg-dock-chip-name">[' + cfgEsc(s.target) + ' · ' + modeTxt + '] ' + cfgEsc(s.label || '명령어') + '</span>' +
          '<span class="cfg-dock-chip-close" onclick="event.stopPropagation(); cfgCloseTerm(\'' + id + '\')" title="닫기">✕</span>' +
          '</div>';
      }).join('');
    }

    function cfgOnChipClick(id) {
      const s = CFG_RUNNER.sessions[id];
      if (!s) return;
      if (s.min) {
        s.min = false;
        s.winEl.classList.remove('minimized');
        cfgFocusWin(id);
        setTimeout(() => { try { s.fit.fit(); } catch (e) {} }, 50);
      } else {
        if (s.winEl.classList.contains('cfg-focus')) {
          cfgToggleMin(id);
        } else {
          cfgFocusWin(id);
        }
      }
      cfgSaveState();
    }

    function cfgUpdateChipStatus(id, isOk) {
      const chip = document.getElementById('chip-' + id);
      if (!chip) return;
      const dot = chip.querySelector('.cfg-dock-chip-dot');
      if (dot) dot.className = 'cfg-dock-chip-dot ' + (isOk ? '' : 'off');
    }

    // 11. localStorage 영속화 및 부팅 복원
    function cfgSaveState() {
      try {
        const payload = Object.keys(CFG_RUNNER.sessions).map(id => {
          const s = CFG_RUNNER.sessions[id];
          return {
            id: s.id, target: s.target, mode: s.mode, label: s.label, code: s.code,
            x: s.x, y: s.y, w: s.w, h: s.h, min: s.min, max: s.max
          };
        });
        localStorage.setItem(CFG_RUNNER.storageKey, JSON.stringify(payload));
      } catch (e) {}
    }

    async function cfgRunnerBoot() {
      cfgEnsureLayers();
      try {
        const raw = localStorage.getItem(CFG_RUNNER.storageKey);
        if (!raw) return;
        const list = JSON.parse(raw);
        if (!Array.isArray(list) || !list.length) return;
        for (const item of list) {
          // 새로고침 복원 시에는 명령어를 재실행하지 않고 터미널 세션 및 창 상태만 복원
          await cfgOpenAndExec(item.code, item.target, item.label, false, item, item.mode);
        }
      } catch (e) {
        console.error('Failed to restore terminal runner sessions', e);
      }
    }

    // 초기 로드 시 러너 복원 실행
    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', () => setTimeout(cfgRunnerBoot, 200));
    } else {
      setTimeout(cfgRunnerBoot, 200);
    }
