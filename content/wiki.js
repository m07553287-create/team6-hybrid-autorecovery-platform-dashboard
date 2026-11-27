    // ===== 구성 위키: 서버 연결 · 팀 로그인 · 데이터 변환 (content/wiki.js) =====
    const WIKI = { ready: false, me: null, tree: null, staticCfg: null };
    const WIKI_ERR = {
      401: '팀 주소나 비밀번호가 맞지 않습니다',
      403: '팀 생성 암호가 맞지 않습니다',
      409: '이미 있는 팀 주소입니다',
      429: '시도가 많습니다. 10분 뒤 다시 시도하세요'
    };

    // fetch 래퍼: JSON 주고받기, 401 이면 로그인 화면
    async function api(method, path, body) {
      const opt = { method: method, headers: {}, credentials: 'same-origin', cache: 'no-store' };
      if (body !== undefined) { opt.headers['Content-Type'] = 'application/json'; opt.body = JSON.stringify(body); }
      let res;
      try { res = await fetch(path, opt); }
      catch (e) { throw { status: 0, error: '서버에 연결하지 못했습니다. 잠시 뒤 다시 시도하세요.' }; }
      let data = null;
      try { data = await res.json(); } catch (e) { data = null; }
      if (!res.ok) {
        const err = Object.assign({ status: res.status }, data || {});
        if (res.status === 401 && ['/api/login', '/api/me', '/api/team/password'].indexOf(path) < 0) {
          WIKI.ready = false;
          if (typeof wikiOnSessionLost === 'function') wikiOnSessionLost();
          else wikiShowLogin();
        }
        throw err;
      }
      return data;
    }

    function wikiStatic() {
      if (!WIKI.staticCfg) {
        const el = document.getElementById('cfg-data');
        WIKI.staticCfg = el ? JSON.parse(el.textContent) : { domains: [], extScripts: [], legacy: {} };
      }
      return WIKI.staticCfg;
    }

    // 설정 탭 진입: 로그인 상태 확인 → 트리 읽기 → 화면
    async function wikiInit() {
      try {
        WIKI.me = await api('GET', '/api/me');
      } catch (e) {
        wikiShowLogin(e.status === 401 ? '' : (e.error || '서버에 연결하지 못했습니다.'));
        return;
      }
      await wikiReload();
    }

    async function wikiReload(keepPlace) {
      const tree = await api('GET', '/api/tree');
      let scripts = [];
      try { scripts = await api('GET', '/api/scripts'); } catch (e) { scripts = []; }
      WIKI.tree = tree;
      CFG.data = treeToData(tree, wikiStatic(), scripts);
      CFG_SH_RE = null; CFG_SH_KEY = {};
      WIKI.ready = true;
      document.getElementById('view-settings').classList.remove('wiki-anon');
      const back = sessionStorage.getItem('fw_return');
      if (back) { sessionStorage.removeItem('fw_return'); history.replaceState(null, '', back); }
      if (keepPlace && CFG.lens) cfgSelect(CFG.lens, CFG.major, CFG.minor, true);
      else { CFG.lens = null; cfgInit(); }
    }

    // ---------- API 트리 → 기존 렌더러 모양(CFG.data) ----------
    function treeToData(tree, st, scripts) {
      const docs = tree.docs || [];
      const byId = {};
      docs.forEach(d => { byId[d.id] = d; });
      const kids = pid => docs.filter(d => d.parent_id === pid).sort((a, b) => a.sort - b.sort || a.id - b.id);
      const clouds = docs.filter(d => d.kind === 'cloud').sort((a, b) => a.sort - b.sort || a.id - b.id);
      const pages = {}, instances = [], legacy = {}, cloudList = [];
      clouds.forEach(c => {
        const entry = { id: c.id, rev: c.rev, name: c.body.name, provider: c.body.provider, desc: c.body.desc || '', instances: [] };
        kids(c.id).filter(d => d.kind === 'instance').forEach(i => {
          const pid = 'inst-' + i.id;
          const b = i.body;
          pages[pid] = {
            kind: 'instance', docId: i.id, rev: i.rev, cloud: c.body.provider, cloudId: c.id, cloudName: c.body.name,
            title: b.title, short: b.short || b.title, tag: b.tag || '', status: b.status || 'live',
            desc: b.desc || '', steps: b.steps || '', specs: b.specs || [],
            areas: kids(i.id).filter(d => d.kind === 'area').map(a => Object.assign({}, a.body, {
              id: 'a' + a.id, docId: a.id, rev: a.rev,
              design: a.body.design || [], config: a.body.config || [], commands: a.body.commands || [],
              verify: a.body.verify || [], trouble: a.body.trouble || [], domains: a.body.domains || []
            }))
          };
          instances.push(pid);
          entry.instances.push(pid);
          if (b.slug) legacy[b.slug] = pid;
          pages[pid].areas.forEach(a => { if (a.slug && b.slug) legacy[b.slug + '.' + a.slug] = pid + '.' + a.id; });
        });
        cloudList.push(entry);
      });
      const stepsDoc = docs.find(d => d.kind === 'steps');
      const steps = stepsDoc ? (stepsDoc.body.items || []).map(s => Object.assign({}, s, {
        page: 'inst-' + s.instance_id, area: 'a' + s.area_id
      })).filter(s => pages[s.page] && pages[s.page].areas.some(a => a.id === s.area)) : [];
      const reference = [];
      docs.filter(d => d.kind === 'page').sort((a, b) => a.sort - b.sort || a.id - b.id).forEach(p => {
        const id = 'page-' + p.id;
        pages[id] = Object.assign({ kind: 'doc', docId: p.id, rev: p.rev, blocks: [] }, p.body);
        reference.push([id, p.body.title]);
      });
      const first = instances.length ? pages[instances[0]] : null;
      return {
        team: tree.team, measured: st.measured || '', vars: [], nav: [],
        domains: st.domains, instances: instances, clouds: cloudList, pages: pages, steps: steps,
        stepsDocId: stepsDoc ? stepsDoc.id : null, stepsRev: stepsDoc ? stepsDoc.rev : null,
        reference: reference, legacy: legacy, byId: byId,
        scripts: (scripts || []).map(s => Object.assign({}, s)).concat(st.extScripts || []),
        default: first && first.areas.length ? { lens: 'inst', major: instances[0], minor: first.areas[0].id }
          : { lens: 'inst', major: instances[0] || '', minor: '' }
      };
    }

    // ---------- 로그인 화면 ----------
    function wikiShowLogin(msg) {
      WIKI.ready = false;
      const h = location.hash || '';
      if (h.indexOf('#cfg/') === 0 && !sessionStorage.getItem('fw_return')) sessionStorage.setItem('fw_return', h);
      document.getElementById('view-settings').classList.add('wiki-anon');
      document.getElementById('cfg-nav').innerHTML = '';
      const body = document.getElementById('manual-body-content');
      body.innerHTML =
        '<div class="wk-login">' +
          '<div class="wk-login-intro"><h2>팀 구성 위키</h2>' +
          '<p>팀 비밀번호로 들어가면 같은 팀의 클라우드·인스턴스·서비스 구성 문서를 함께 보고 고칠 수 있습니다. 고친 내용은 판으로 남아 언제든 비교하고 되돌릴 수 있습니다.</p>' +
          (msg ? '<p class="wk-error" role="alert">' + cfgEsc(msg) + '</p>' : '') + '</div>' +
          '<form class="wk-card" id="wk-login-form" onsubmit="wikiLogin(event)">' +
            '<h3>팀 들어가기</h3>' +
            '<label>팀 주소<input name="slug" required autocomplete="username" placeholder="예: figteam" pattern="[a-z0-9-]{3,32}"></label>' +
            '<label>팀 비밀번호<input name="password" type="password" required autocomplete="current-password"></label>' +
            '<label>내 이름 <span>(고친 기록에 남습니다)</span><input name="member" required maxlength="20" autocomplete="nickname"></label>' +
            '<p class="wk-error" id="wk-login-err" role="alert" hidden></p>' +
            '<button type="submit" class="wk-btn wk-primary">들어가기</button>' +
          '</form>' +
          '<form class="wk-card" id="wk-create-form" onsubmit="wikiCreateTeam(event)">' +
            '<h3>팀 만들기</h3>' +
            '<label>팀 이름<input name="name" required maxlength="40" placeholder="예: 3팀 하이브리드 DR"></label>' +
            '<label>팀 주소 <span>(영문 소문자·숫자·- 3~32자)</span><input name="slug" required pattern="[a-z0-9-]{3,32}"></label>' +
            '<label>팀 비밀번호 <span>(6자 이상)</span><input name="password" type="password" required minlength="6" autocomplete="new-password"></label>' +
            '<label>내 이름<input name="member" required maxlength="20"></label>' +
            '<label>팀 생성 암호 <span>(관리자에게 받은 암호)</span><input name="create_code" type="password" required></label>' +
            '<p class="wk-error" id="wk-create-err" role="alert" hidden></p>' +
            '<button type="submit" class="wk-btn">팀 만들기</button>' +
          '</form>' +
        '</div>';
      const last = localStorage.getItem('fw_last');
      if (last) {
        try { const v = JSON.parse(last); const f = document.getElementById('wk-login-form'); f.slug.value = v.slug || ''; f.member.value = v.member || ''; } catch (e) {}
      }
    }

    function wikiFormData(form) {
      const o = {};
      Array.prototype.forEach.call(form.elements, el => { if (el.name) o[el.name] = el.value.trim(); });
      return o;
    }

    async function wikiSubmit(ev, path, errId) {
      ev.preventDefault();
      const form = ev.target;
      const btn = form.querySelector('button[type=submit]');
      const err = document.getElementById(errId);
      const data = wikiFormData(form);
      err.hidden = true; btn.disabled = true;
      try {
        await api('POST', path, data);
        localStorage.setItem('fw_last', JSON.stringify({ slug: data.slug, member: data.member }));
        WIKI.me = await api('GET', '/api/me');
        await wikiReload();
        if (typeof wikiAfterLogin === 'function') wikiAfterLogin();
      } catch (e) {
        err.textContent = WIKI_ERR[e.status] && !(e.status === 422) ? WIKI_ERR[e.status] : (e.error || '처리하지 못했습니다');
        err.hidden = false;
      } finally { btn.disabled = false; }
    }
    function wikiLogin(ev) { return wikiSubmit(ev, '/api/login', 'wk-login-err'); }
    function wikiCreateTeam(ev) { return wikiSubmit(ev, '/api/teams', 'wk-create-err'); }

    async function wikiLogout() {
      try { await api('POST', '/api/logout', {}); } catch (e) {}
      WIKI.ready = false; WIKI.me = null; CFG.data = null; CFG.lens = null;
      history.replaceState(null, '', '#cfg/');
      wikiShowLogin();
    }

    function wikiTeamBar() {
      if (!WIKI.me) return '';
      return '<div class="wk-teambar"><div><b>' + cfgEsc(WIKI.me.team_name) + '</b><span>' + cfgEsc(WIKI.me.member) + ' 님</span></div>' +
        '<button type="button" class="cfg-copy" onclick="wikiLogout()">로그아웃</button></div>';
    }

    // ===== 만들기 · 편집 · 삭제 =====
    const WK_STATUS = [['live', '실측'], ['design', '설계 · 미적용'], ['nolook', '미실측']];
    const WK_PROVIDERS = [['onprem', '온프렘'], ['openstack', 'OpenStack'], ['kt', 'KT Cloud'], ['aws', 'AWS'], ['other', '기타']];
    const WK_CATS = ['설치', '적용', '조회', '검증'];
    const WK_KIND_NAME = { cloud: '클라우드', instance: '인스턴스', area: '서비스 영역', steps: '진행 순서', page: '참고 문서' };
    // 화면용 비밀값 검사 — 서버(wiki/guard.py)와 같은 패턴
    const WK_SECRET = [
      /-----BEGIN [A-Z ]*PRIVATE KEY-----/, /PrivateKey\s*=\s*[A-Za-z0-9+/]{43}=/, /AKIA[0-9A-Z]{16}/,
      /gh[pousr]_[A-Za-z0-9]{36}/, /(password|passwd|pwd|secret|token)\s*[:=]\s*(?![<$'"{])\S{6,}/i
    ];
    function wikiFindSecret(v, path) {
      path = path || 'body';
      if (typeof v === 'string') return WK_SECRET.some(p => p.test(v)) ? { field: path } : null;
      if (Array.isArray(v)) { for (let i = 0; i < v.length; i++) { const h = wikiFindSecret(v[i], path + '[' + i + ']'); if (h) return h; } return null; }
      if (v && typeof v === 'object') { for (const k in v) { const h = wikiFindSecret(v[k], path + '.' + k); if (h) return h; } }
      return null;
    }

    function wikiToast(msg) {
      let t = document.getElementById('wk-toast');
      if (!t) { t = document.createElement('div'); t.id = 'wk-toast'; t.setAttribute('role', 'status'); document.body.appendChild(t); }
      t.textContent = msg; t.classList.add('show');
      clearTimeout(t._h); t._h = setTimeout(() => t.classList.remove('show'), 2600);
    }

    // ---------- + 버튼 (렌더러 훅) ----------
    function wkAdd(label, js) {
      return '<button type="button" class="wk-add" onclick="' + js + '">+ ' + cfgEsc(label) + '</button>';
    }
    function wikiMajorTail() {
      if (!WIKI.ready) return '';
      if (CFG.lens === 'inst') return wkAdd('클라우드', "wikiCreate('cloud', null)");
      if (CFG.lens === 'ref') return wkAdd('문서', "wikiCreate('page', null)");
      return '';
    }
    function wikiGroupTail(cloudId) {
      if (!WIKI.ready || !cloudId) return '';
      return '<span class="wk-group-acts"><button type="button" class="wk-mini" title="클라우드 편집" onclick="event.stopPropagation();wikiEdit(' + cloudId + ')">편집</button>' +
        '<button type="button" class="wk-mini" onclick="event.stopPropagation();wikiCreate(\'instance\', ' + cloudId + ')">+ 인스턴스</button></span>';
    }
    function wikiMinorTail() {
      if (!WIKI.ready) return '';
      if (CFG.lens === 'inst' && cfgPage(CFG.major)) return wkAdd('서비스 영역', "wikiCreate('area', " + cfgPage(CFG.major).docId + ")");
      if (CFG.lens === 'step') return wkAdd('단계', 'wikiEditSteps(true)');
      return '';
    }
    function wikiEmptyActions(lens) {
      if (lens === 'inst') {
        if (cfgPage(CFG.major)) return wkAdd('서비스 영역', "wikiCreate('area', " + cfgPage(CFG.major).docId + ")");
        const c = CFG.data.clouds || [];
        return c.length ? c.map(x => wkAdd(x.name + ' 아래 인스턴스', "wikiCreate('instance', " + x.id + ")")).join(' ')
          : wkAdd('클라우드', "wikiCreate('cloud', null)");
      }
      if (lens === 'step') return wkAdd('단계', 'wikiEditSteps(true)');
      if (lens === 'ref') return wkAdd('문서', "wikiCreate('page', null)");
      return '';
    }
    function wikiActions(kind, docId) {
      if (!WIKI.ready) return '';
      if (kind === 'steps') return '<div class="wk-acts">' + (docId ? '<button type="button" class="wk-mini" onclick="wikiEditSteps(false)">순서 편집</button>' : '') + '</div>';
      if (!docId) return '';
      const name = WK_KIND_NAME[kind];
      return '<div class="wk-acts">' +
        '<button type="button" class="wk-mini" onclick="wikiEdit(' + docId + ')">' + name + ' 편집</button>' +
        (typeof wikiHistory === 'function' ? '<button type="button" class="wk-mini" onclick="wikiHistory(' + docId + ')">기록</button>' : '') +
        '<button type="button" class="wk-mini wk-danger" onclick="wikiDelete(' + docId + ', this)">삭제</button></div>';
    }

    // ---------- 편집기 ----------
    function wkDoc(id) { return CFG.data.byId[id]; }
    function wikiCreate(kind, parentId) {
      const blank = {
        cloud: { name: '', provider: 'openstack', desc: '' },
        instance: { title: '', short: '', tag: '', status: 'live', steps: '', desc: '', specs: [] },
        area: { name: '', status: 'live', domains: [], design: [], config: [], commands: [], verify: [], trouble: [] },
        page: { title: '', tag: '', desc: '', blocks: [] }
      }[kind];
      wikiOpenEditor({ kind: kind, docId: null, parentId: parentId, baseRev: null }, blank);
    }
    function wikiEdit(docId) {
      const d = wkDoc(docId);
      if (!d) return;
      wikiOpenEditor({ kind: d.kind, docId: d.id, parentId: d.parent_id, baseRev: d.rev }, JSON.parse(JSON.stringify(d.body)));
    }
    function wikiEditSteps(addRow) {
      const id = CFG.data.stepsDocId;
      const d = id ? wkDoc(id) : null;
      const body = d ? JSON.parse(JSON.stringify(d.body)) : { items: [] };
      if (addRow) body.items.push({ no: 'S' + body.items.length, title: '', where: '', why: '', gate: '', instance_id: null, area_id: null });
      wikiOpenEditor({ kind: 'steps', docId: d ? d.id : null, parentId: null, baseRev: d ? d.rev : null }, body);
    }

    // 필드 정의: [키, 라벨, 종류, 옵션]
    function wkFields(kind) {
      if (kind === 'cloud') return [['name', '클라우드 이름', 'text'], ['provider', '종류', 'select', WK_PROVIDERS], ['desc', '설명', 'textarea']];
      if (kind === 'instance') return [['title', '인스턴스 이름', 'text'], ['short', '짧은 이름 (매트릭스에 표시)', 'text'],
        ['tag', '주소·태그 (예: 172.20.0.86)', 'text'], ['status', '상태', 'select', WK_STATUS], ['steps', '진행 순서 표시 (예: S6 · S8)', 'text'],
        ['desc', '설명', 'textarea'], ['specs', '사양', 'rows', [['0', '항목', 'text'], ['1', '값', 'text']]]];
      if (kind === 'area') return [['name', '서비스 영역 이름', 'text'], ['status', '상태', 'select', WK_STATUS], ['domains', '서비스 분류 (하나 이상)', 'checks'],
        ['design', '설계 (한 줄에 하나)', 'lines'],
        ['config', '설정', 'rows', [['label', '라벨 (파일 경로 등)', 'text'], ['code', '내용', 'code']]],
        ['commands', '명령어', 'rows', [['cat', '분류', 'select', WK_CATS.map(c => [c, c])], ['label', '설명', 'text'], ['code', '명령', 'code']]],
        ['verify', '검증', 'rows', [['label', '설명', 'text'], ['code', '명령', 'code'], ['expect', '기대 결과', 'text']]],
        ['trouble', '오류 시 확인', 'rows', [['0', '증상', 'text'], ['1', '의심 변수·영역', 'text'], ['2', '확인 명령', 'text'], ['3', '조치', 'text']]]];
      if (kind === 'steps') return [['items', '단계', 'rows', [['no', '번호', 'text'], ['title', '제목', 'text'], ['where', '실행 위치', 'text'],
        ['why', '이유', 'textarea'], ['gate', '통과 조건 (명령)', 'code'], ['area_ref', '연결할 서비스 영역', 'arearef']]]];
      return [['title', '문서 제목', 'text'], ['tag', '태그', 'text'], ['desc', '설명', 'textarea'],
        ['blocks', '내용 블록', 'rows', [['type', '종류', 'select', [['h', '소제목'], ['p', '문단'], ['code', '코드'], ['table', '표']]],
          ['label', '코드 라벨 (코드일 때)', 'text'], ['text', '내용 (표는 한 줄에 한 행, 칸은 | 로 구분, 첫 줄은 제목)', 'code']]]];
    }

    function wkInput(name, def, val) {
      const type = def[2];
      const v = val == null ? '' : val;
      if (type === 'select') return '<select name="' + name + '">' + def[3].map(o => '<option value="' + cfgEsc(o[0]) + '"' + (o[0] === v ? ' selected' : '') + '>' + cfgEsc(o[1]) + '</option>').join('') + '</select>';
      if (type === 'textarea') return '<textarea name="' + name + '" rows="3">' + cfgEsc(v) + '</textarea>';
      if (type === 'code') return '<textarea name="' + name + '" rows="5" class="wk-code" spellcheck="false">' + cfgEsc(v) + '</textarea>';
      if (type === 'arearef') {
        const opts = ['<option value="">(연결 안 함)</option>'];
        CFG.data.instances.forEach(pid => { const p = cfgPage(pid); p.areas.forEach(a => opts.push('<option value="' + p.docId + ':' + a.docId + '"' + (v === p.docId + ':' + a.docId ? ' selected' : '') + '>' + cfgEsc(p.short + ' / ' + a.name) + '</option>')); });
        return '<select name="' + name + '">' + opts.join('') + '</select>';
      }
      return '<input name="' + name + '" value="' + cfgEsc(v) + '">';
    }

    function wkRow(fieldKey, cols, item, idx) {
      return '<div class="wk-row" data-field="' + fieldKey + '">' +
        '<div class="wk-row-cols">' + cols.map(c => '<label class="wk-field">' + cfgEsc(c[1]) + wkInput(fieldKey + '.' + c[0], c, item[c[0]]) + '</label>').join('') + '</div>' +
        '<div class="wk-row-tools"><button type="button" class="wk-mini" title="위로" onclick="wkMove(this,-1)">↑</button>' +
        '<button type="button" class="wk-mini" title="아래로" onclick="wkMove(this,1)">↓</button>' +
        '<button type="button" class="wk-mini wk-danger" title="이 줄 삭제" onclick="wkDelRow(this)">삭제</button></div></div>';
    }
    function wkRowItem(kind, key, raw) {
      // 저장된 값 → 행 편집용 객체
      if (key === 'specs' || key === 'trouble') return Object.assign({}, raw);
      if (kind === 'steps') return Object.assign({}, raw, { area_ref: raw.instance_id && raw.area_id ? raw.instance_id + ':' + raw.area_id : '' });
      if (kind === 'page' && key === 'blocks') {
        if (raw.type === 'table') return { type: 'table', label: '', text: [(raw.head || []).join(' | ')].concat((raw.rows || []).map(r => r.join(' | '))).join(WIKI_NL) };
        if (raw.type === 'code') return { type: 'code', label: raw.label || '', text: raw.code || '' };
        return { type: raw.type, label: '', text: raw.text || '' };
      }
      return Object.assign({}, raw);
    }

    function wikiOpenEditor(meta, body, notice) {
      WIKI.editing = { meta: meta, orig: body };
      const fields = wkFields(meta.kind);
      const isNew = !meta.docId;
      let parentLabel = '';
      if (meta.parentId && wkDoc(meta.parentId)) { const pb = wkDoc(meta.parentId).body; parentLabel = ' — ' + (pb.name || pb.title) + ' 아래'; }
      let html = '<form class="wk-editor" id="wk-editor" onsubmit="wikiSave(event)" oninput="wkSaveDraft()">' +
        '<div class="cfg-head"><h2 class="cfg-head-title">' + WK_KIND_NAME[meta.kind] + (isNew ? ' 만들기' : ' 편집') + cfgEsc(parentLabel) + '</h2>' +
        (meta.baseRev ? '<p class="manual-desc">' + meta.baseRev + '판을 고칩니다. 저장하면 ' + (meta.baseRev + 1) + '판이 됩니다.</p>' : '') + '</div>' +
        (notice || '') + '<p class="wk-error" id="wk-ed-err" role="alert" hidden></p>';
      fields.forEach(f => {
        const key = f[0], type = f[2], val = body[key];
        if (type === 'rows') {
          const items = Array.isArray(val) ? val : [];
          html += '<fieldset class="wk-set"><legend>' + cfgEsc(f[1]) + '</legend><div class="wk-rows" data-key="' + key + '">' +
            items.map((it, i) => wkRow(key, f[3], wkRowItem(meta.kind, key, it), i)).join('') + '</div>' +
            '<button type="button" class="wk-add" onclick="wkAddRow(\'' + key + '\')">+ ' + cfgEsc(f[1]) + ' 추가</button></fieldset>';
        } else if (type === 'checks') {
          html += '<fieldset class="wk-set" data-key="domains"><legend>' + cfgEsc(f[1]) + '</legend><div class="wk-checks">' +
            CFG.data.domains.map(d => '<label><input type="checkbox" name="domains" value="' + d.id + '"' + ((val || []).indexOf(d.id) >= 0 ? ' checked' : '') + '> ' + cfgEsc(d.name) + '</label>').join('') + '</div></fieldset>';
        } else if (type === 'lines') {
          html += '<label class="wk-field" data-key="' + key + '">' + cfgEsc(f[1]) + '<textarea name="' + key + '" rows="6">' + cfgEsc((val || []).join(WIKI_NL)) + '</textarea></label>';
        } else {
          html += '<label class="wk-field" data-key="' + key + '">' + cfgEsc(f[1]) + wkInput(key, f, val) + '</label>';
        }
      });
      html += '<label class="wk-field">변경 메모 <span>(선택 — 기록에 남습니다)</span><input name="__message" maxlength="200" placeholder="예: sg-db 규칙 추가 반영"></label>' +
        '<div class="wk-bar"><button type="submit" class="wk-btn wk-primary">저장</button>' +
        '<button type="button" class="wk-btn" onclick="wikiCancel()">취소</button></div></form>';
      const bodyEl = document.getElementById('manual-body-content');
      bodyEl.innerHTML = html;
      bodyEl.scrollTop = 0;
      wkSaveDraft();
    }

    function wkAddRow(key) {
      const f = wkFields(WIKI.editing.meta.kind).find(x => x[0] === key);
      const box = document.querySelector('.wk-rows[data-key="' + key + '"]');
      const blank = {};
      f[3].forEach(c => { blank[c[0]] = c[2] === 'select' ? c[3][0][0] : ''; });
      box.insertAdjacentHTML('beforeend', wkRow(key, f[3], blank, box.children.length));
      wkSaveDraft();
    }
    function wkDelRow(btn) { btn.closest('.wk-row').remove(); wkSaveDraft(); }
    function wkMove(btn, dir) {
      const row = btn.closest('.wk-row');
      const sib = dir < 0 ? row.previousElementSibling : row.nextElementSibling;
      if (sib) { if (dir < 0) sib.before(row); else sib.after(row); }
      wkSaveDraft();
    }

    // 양식 → body (원래 body 의 숨은 칸(slug 등)은 유지)
    function wkCollect() {
      const ed = WIKI.editing, form = document.getElementById('wk-editor');
      const body = JSON.parse(JSON.stringify(ed.orig || {}));
      wkFields(ed.meta.kind).forEach(f => {
        const key = f[0], type = f[2];
        if (type === 'rows') {
          body[key] = Array.prototype.map.call(form.querySelectorAll('.wk-rows[data-key="' + key + '"] > .wk-row'), row => {
            const o = {};
            f[3].forEach(c => { o[c[0]] = row.querySelector('[name="' + key + '.' + c[0] + '"]').value; });
            return o;
          }).map(o => wkRowBack(ed.meta.kind, key, o)).filter(o => o !== null);
        } else if (type === 'checks') {
          body[key] = Array.prototype.filter.call(form.querySelectorAll('input[name="domains"]'), x => x.checked).map(x => x.value);
        } else if (type === 'lines') {
          body[key] = form.elements[key].value.split(WIKI_NL).map(x => x.trim()).filter(Boolean);
        } else {
          body[key] = form.elements[key].value.trim();
        }
      });
      return body;
    }
    function wkRowBack(kind, key, o) {
      if (key === 'specs') return o['0'] || o['1'] ? [o['0'], o['1']] : null;
      if (key === 'trouble') return o['0'] || o['3'] ? [o['0'], o['1'], o['2'], o['3']] : null;
      if (kind === 'steps') {
        const ref = (o.area_ref || '').split(':');
        const out = { no: o.no, title: o.title, where: o.where, why: o.why, gate: o.gate,
          instance_id: ref[0] ? Number(ref[0]) : null, area_id: ref[1] ? Number(ref[1]) : null };
        return out.title || out.no ? out : null;
      }
      if (kind === 'page' && key === 'blocks') {
        if (o.type === 'table') {
          const ls = o.text.split(WIKI_NL).filter(l => l.trim()).map(l => l.split('|').map(x => x.trim()));
          return ls.length ? { type: 'table', head: ls[0], rows: ls.slice(1) } : null;
        }
        if (o.type === 'code') return o.text ? { type: 'code', label: o.label, code: o.text } : null;
        return o.text ? { type: o.type, text: o.text } : null;
      }
      return o;
    }

    function wkDraftKey() { const m = WIKI.editing.meta; return 'fw_editing'; }
    function wkSaveDraft() {
      if (!WIKI.editing || !document.getElementById('wk-editor')) return;
      try { sessionStorage.setItem(wkDraftKey(), JSON.stringify({ meta: WIKI.editing.meta, orig: WIKI.editing.orig, body: wkCollect() })); } catch (e) {}
    }
    function wikiCancel() {
      sessionStorage.removeItem('fw_editing');
      WIKI.editing = null;
      cfgRenderBody();
    }

    function wkShowError(msg, field) {
      const el = document.getElementById('wk-ed-err');
      el.textContent = msg; el.hidden = false;
      document.querySelectorAll('.wk-bad').forEach(x => x.classList.remove('wk-bad'));
      if (field) {
        const key = String(field).replace('body.', '').split(/[.[]/)[0];
        const tgt = document.querySelector('[data-key="' + key + '"]');
        if (tgt) { tgt.classList.add('wk-bad'); tgt.scrollIntoView({ block: 'center' }); }
      }
      el.scrollIntoView({ block: 'nearest' });
    }

    async function wikiSave(ev, force) {
      if (ev) ev.preventDefault();
      const ed = WIKI.editing;
      const body = force ? force.body : wkCollect();
      const msg = force ? force.message : (document.getElementById('wk-editor').elements.__message.value || '');
      const secret = wikiFindSecret(body);
      if (secret) return wkShowError('비밀값처럼 보이는 내용은 저장할 수 없습니다. <개인키> 처럼 자리표시로 바꾸세요.', secret.field);
      const baseRev = force ? force.baseRev : ed.meta.baseRev;
      try {
        let r, id = ed.meta.docId;
        if (!id) {
          r = await api('POST', '/api/docs', { kind: ed.meta.kind, parent_id: ed.meta.parentId, sort: wkNextSort(ed.meta), body: body, message: msg });
          id = r.id;
        } else {
          r = await api('PUT', '/api/docs/' + id, { base_rev: baseRev, body: body, message: msg });
        }
        sessionStorage.removeItem('fw_editing');
        WIKI.editing = null;
        wikiToast('저장했습니다 (' + r.rev + '판)');
        await wikiReload(true);
        wkGoTo(ed.meta.kind, id);
      } catch (e) {
        if (e.status === 401) return;  // 로그인 화면으로 — 초안은 sessionStorage 에 남아 있다
        if (e.status === 409 && e.current) return wikiConflict(body, msg, e.current);
        wkShowError(e.error || '저장하지 못했습니다', e.field);
      }
    }
    function wkNextSort(meta) {
      const sib = Object.values(CFG.data.byId).filter(d => d.kind === meta.kind && d.parent_id === meta.parentId);
      return sib.length ? Math.max.apply(null, sib.map(d => d.sort)) + 1 : 0;
    }
    function wkGoTo(kind, id) {
      if (kind === 'area') { const d = CFG.data.byId[id]; if (d) return cfgSelect('inst', 'inst-' + d.parent_id, 'a' + id); }
      if (kind === 'instance') return cfgSelect('inst', 'inst-' + id, '');
      if (kind === 'page') return cfgSelect('ref', 'page-' + id, '');
      if (kind === 'steps') return cfgSelect('step', 'all', '');
      cfgSelect(CFG.lens || 'inst', CFG.major, CFG.minor);
    }

    // 409: 내 초안 ↔ 최신 판 나란히
    function wikiConflict(myBody, myMsg, current) {
      const ed = WIKI.editing;
      WIKI.conflict = { body: myBody, message: myMsg, current: current };
      const html = '<div class="wk-conflict"><h3>다른 팀원이 먼저 저장했습니다</h3>' +
        '<p>' + cfgEsc(current.author) + ' 님이 ' + current.rev + '판을 저장했습니다. 왼쪽은 최신 판, 오른쪽은 내가 고친 내용입니다. 둘을 비교해 정하세요.</p>' +
        wikiDiffView(bodyToText(ed.meta.kind, current.body), bodyToText(ed.meta.kind, myBody), current.rev + '판 (최신)', '내 초안') +
        '<div class="wk-bar"><button type="button" class="wk-btn" onclick="wikiConflictReload()">최신 판으로 다시 편집</button>' +
        '<button type="button" class="wk-btn wk-primary" onclick="wikiConflictForce()">내 초안으로 저장</button></div></div>';
      const bodyEl = document.getElementById('manual-body-content');
      bodyEl.innerHTML = html; bodyEl.scrollTop = 0;
    }
    function wikiConflictReload() {
      const c = WIKI.conflict, m = WIKI.editing.meta;
      wikiOpenEditor(Object.assign({}, m, { baseRev: c.current.rev }), c.current.body);
    }
    function wikiConflictForce() {
      const c = WIKI.conflict;
      wikiSave(null, { body: c.body, message: c.message || '충돌 후 내 초안으로 저장', baseRev: c.current.rev });
    }

    // 나란히 비교 표 (Task 8 기록 화면도 사용)
    function wikiDiffView(aLines, bLines, aTitle, bTitle) {
      const d = diffLines(aLines, bLines);
      const rows = [];
      let i = 0;
      while (i < d.length) {
        if (d[i].op === 'same') {
          let j = i; while (j < d.length && d[j].op === 'same') j++;
          const run = d.slice(i, j);
          if (run.length > 6) {
            run.slice(0, 2).forEach(x => rows.push(['same', x.a, x.text, x.b, x.text]));
            rows.push(['fold', run.length - 4]);
            run.slice(-2).forEach(x => rows.push(['same', x.a, x.text, x.b, x.text]));
          } else run.forEach(x => rows.push(['same', x.a, x.text, x.b, x.text]));
          i = j;
        } else {
          const dels = [], adds = [];
          while (i < d.length && d[i].op !== 'same') { (d[i].op === 'del' ? dels : adds).push(d[i]); i++; }
          for (let k = 0; k < Math.max(dels.length, adds.length); k++) {
            const a = dels[k], b = adds[k];
            rows.push(['chg', a ? a.a : null, a ? a.text : null, b ? b.b : null, b ? b.text : null]);
          }
        }
      }
      const changed = d.filter(x => x.op !== 'same').length;
      return '<div class="wk-diff-wrap"><div class="wk-diff-sum">' + (changed ? '바뀐 줄 ' + changed + '개' : '두 판의 내용이 같습니다') + '</div>' +
        '<table class="wk-diff"><colgroup><col style="width:48px"><col><col style="width:48px"><col></colgroup><thead><tr><th colspan="2">' + cfgEsc(aTitle) + '</th><th colspan="2">' + cfgEsc(bTitle) + '</th></tr></thead><tbody>' +
        rows.map(r => {
          if (r[0] === 'fold') return '<tr class="wk-fold"><td colspan="4">같은 줄 ' + r[1] + '개</td></tr>';
          const left = r[2] === null ? '<td class="wk-ln"></td><td class="wk-empty"></td>' : '<td class="wk-ln">' + (r[1] + 1) + '</td><td class="' + (r[0] === 'chg' ? 'wk-del' : '') + '">' + cfgEsc(r[2]) + '</td>';
          const right = r[4] === null ? '<td class="wk-ln"></td><td class="wk-empty"></td>' : '<td class="wk-ln">' + (r[3] + 1) + '</td><td class="' + (r[0] === 'chg' ? 'wk-ins' : '') + '">' + cfgEsc(r[4]) + '</td>';
          return '<tr>' + left + right + '</tr>';
        }).join('') + '</tbody></table></div>';
    }

    // ---------- 삭제 (두 번 눌러 확인) ----------
    async function wikiDelete(docId, btn) {
      if (!btn.dataset.armed) {
        btn.dataset.armed = '1'; btn.textContent = '한 번 더 누르면 삭제';
        setTimeout(() => { if (btn.isConnected) { delete btn.dataset.armed; btn.textContent = '삭제'; } }, 4000);
        return;
      }
      const d = wkDoc(docId);
      try {
        const r = await api('DELETE', '/api/docs/' + docId, { base_rev: d.rev, message: '삭제' });
        wikiToast('삭제했습니다 (' + r.rev + '판, 기록에서 되돌릴 수 있습니다)');
        await wikiReload(true);
        cfgSelect(CFG.lens, '', '');
      } catch (e) {
        if (e.status === 401) return;
        wikiToast(e.status === 422 ? '하위 문서를 먼저 삭제하세요' : (e.error || '삭제하지 못했습니다'));
      }
    }

    // ---------- 세션이 끊겼을 때 초안 지키기 ----------
    function wikiOnSessionLost() {
      if (WIKI.editing && document.getElementById('wk-editor')) wkSaveDraft();
      wikiShowLogin('로그인이 끊겼습니다. 다시 들어오면 쓰던 내용을 이어서 편집할 수 있습니다.');
    }
    function wikiAfterLogin() {
      const raw = sessionStorage.getItem('fw_editing');
      if (!raw) return;
      try {
        const v = JSON.parse(raw);
        wikiOpenEditor(v.meta, Object.assign({}, v.orig, v.body), '<p class="wk-note">로그인 전에 쓰던 내용을 되살렸습니다. 확인하고 저장하세요.</p>');
        WIKI.editing.orig = v.orig;
      } catch (e) { sessionStorage.removeItem('fw_editing'); }
    }

    // ===== 기록 · 비교 · 되돌리기 · 최근 변경 =====
    function wkTime(sec) { return new Date(sec * 1000).toLocaleString('ko-KR', { hour12: false }); }
    function wkKindOf(docId, fallback) { const d = CFG.data.byId[docId]; return d ? d.kind : (fallback || 'page'); }
    function wkTitleOf(docId, fallback) { const d = CFG.data.byId[docId]; return d ? (d.body.name || d.body.title || '진행 순서') : (fallback || '삭제된 문서'); }
    const WK_REV_CACHE = {};
    async function wkRev(docId, rev) {
      const k = docId + ':' + rev;
      if (!WK_REV_CACHE[k]) WK_REV_CACHE[k] = await api('GET', '/api/docs/' + docId + '/revisions/' + rev);
      return WK_REV_CACHE[k];
    }

    // 기록 화면: 판 목록 + 두 판 비교 (기본: 바로 앞 판 ↔ 최신 판)
    async function wikiHistory(docId, revA, revB, kindHint, titleHint) {
      const bodyEl = document.getElementById('manual-body-content');
      bodyEl.innerHTML = '<p class="cfg-empty">기록을 불러오는 중…</p>';
      let revs;
      try { revs = await api('GET', '/api/docs/' + docId + '/revisions'); }
      catch (e) { if (e.status !== 401) bodyEl.innerHTML = '<p class="wk-error">' + cfgEsc(e.error || '기록을 불러오지 못했습니다') + '</p>'; return; }
      const latest = revs[0].rev;
      const b = revB || latest, a = revA || (b > 1 ? b - 1 : b);
      const kind = wkKindOf(docId, kindHint), title = wkTitleOf(docId, titleHint);
      WIKI.hist = { docId: docId, kind: kind, title: title, latest: latest };
      history.replaceState(null, '', '#cfg/hist/' + docId + '/' + a + '/' + b);
      const alive = !!CFG.data.byId[docId];
      bodyEl.innerHTML =
        '<nav class="cfg-crumb"><a href="javascript:void(0)" onclick="wkBackFromHistory()">← ' + (alive ? '문서로 돌아가기' : '목록으로') + '</a></nav>' +
        '<div class="cfg-head"><h2 class="cfg-head-title">' + cfgEsc(title) + ' — 기록 <span class="manual-tag">' + WK_KIND_NAME[kind] + '</span></h2>' +
        '<p class="manual-desc">판 ' + revs.length + '개. 비교할 두 판을 왼쪽(옛 판)·오른쪽(새 판)에서 고르세요.' + (alive ? '' : ' 이 문서는 삭제된 상태입니다. 판을 골라 되돌리면 다시 나타납니다.') + '</p></div>' +
        '<div class="cfg-table-wrap"><table class="cfg-table wk-revs"><thead><tr><th>왼쪽</th><th>오른쪽</th><th>판</th><th>작성자</th><th>시각</th><th>메모</th><th></th></tr></thead><tbody>' +
        revs.map(r => '<tr' + (r.deleted ? ' class="wk-rev-del"' : '') + '>' +
          '<td><input type="radio" name="wk-a" value="' + r.rev + '"' + (r.rev === a ? ' checked' : '') + ' aria-label="' + r.rev + '판을 왼쪽에"></td>' +
          '<td><input type="radio" name="wk-b" value="' + r.rev + '"' + (r.rev === b ? ' checked' : '') + ' aria-label="' + r.rev + '판을 오른쪽에"></td>' +
          '<td><b>' + r.rev + '판</b>' + (r.rev === latest ? ' <span class="cfg-badge cfg-st-live">현재</span>' : '') + (r.deleted ? ' <span class="cfg-badge cfg-st-nolook">삭제</span>' : '') + '</td>' +
          '<td>' + cfgEsc(r.author) + '</td><td>' + wkTime(r.created_at) + '</td><td>' + cfgEsc(r.message || '') + '</td>' +
          '<td>' + (r.rev !== latest || r.deleted ? '<button type="button" class="wk-mini" onclick="wikiRestore(' + docId + ',' + r.rev + ',this)">' + (r.deleted ? '' : '이 판으로 되돌리기') + '</button>' : '') + '</td></tr>').join('') +
        '</tbody></table></div>' +
        '<div class="wk-bar wk-bar-inline"><button type="button" class="wk-btn wk-primary" onclick="wkCompareSelected()">선택한 두 판 비교</button></div>' +
        '<div id="wk-compare"></div>';
      // 삭제 판 행의 버튼 문구는 바로 앞 살아 있던 판으로 되돌리기
      bodyEl.querySelectorAll('.wk-rev-del .wk-mini').forEach(btn => { btn.textContent = '되돌리기 (삭제 취소)'; });
      await wikiCompare(docId, a, b);
    }
    function wkCompareSelected() {
      const a = Number((document.querySelector('input[name="wk-a"]:checked') || {}).value);
      const b = Number((document.querySelector('input[name="wk-b"]:checked') || {}).value);
      if (a && b) wikiCompare(WIKI.hist.docId, Math.min(a, b), Math.max(a, b));
    }
    async function wikiCompare(docId, a, b) {
      const box = document.getElementById('wk-compare');
      if (!box) return wikiHistory(docId, a, b);
      box.innerHTML = '<p class="cfg-empty">비교하는 중…</p>';
      try {
        const A = await wkRev(docId, a), B = await wkRev(docId, b);
        const kind = WIKI.hist.kind;
        box.innerHTML = '<h3 class="cfg-h">' + a + '판 ↔ ' + b + '판</h3>' +
          wikiDiffView(bodyToText(kind, A.body), bodyToText(kind, B.body),
            a + '판 · ' + A.author + ' · ' + wkTime(A.created_at), b + '판 · ' + B.author + ' · ' + wkTime(B.created_at));
        history.replaceState(null, '', '#cfg/hist/' + docId + '/' + a + '/' + b);
      } catch (e) { if (e.status !== 401) box.innerHTML = '<p class="wk-error">' + cfgEsc(e.error || '비교하지 못했습니다') + '</p>'; }
    }
    async function wikiRestore(docId, rev, btn) {
      if (btn && !btn.dataset.armed) {
        btn.dataset.armed = '1'; const t = btn.textContent; btn.textContent = '한 번 더 누르면 되돌림';
        setTimeout(() => { if (btn.isConnected) { delete btn.dataset.armed; btn.textContent = t; } }, 4000);
        return;
      }
      try {
        let target = rev;
        const one = await wkRev(docId, rev);
        if (one.deleted) {  // 삭제 판을 누르면 그 직전(살아 있던) 판 내용으로
          const revs = await api('GET', '/api/docs/' + docId + '/revisions');
          const live = revs.find(r => r.rev < rev && !r.deleted);
          target = live ? live.rev : rev;
        }
        const r = await api('POST', '/api/docs/' + docId + '/restore', { rev: target, base_rev: WIKI.hist.latest, message: target + '판 내용으로 되돌림' });
        wikiToast(target + '판 내용으로 되돌렸습니다 (' + r.rev + '판)');
        await wikiReload(true);
        wikiHistory(docId, target, r.rev);
      } catch (e) {
        if (e.status === 401) return;
        if (e.status === 409) { wikiToast('그 사이 다른 팀원이 저장했습니다. 기록을 새로 불러옵니다.'); return wikiHistory(docId); }
        wikiToast(e.error || '되돌리지 못했습니다');
      }
    }
    function wkBackFromHistory() {
      const h = WIKI.hist;
      if (h && CFG.data.byId[h.docId]) return wkGoTo(h.kind, h.docId);
      cfgSelect('ref', '__changes', '');
    }

    // 해시 #cfg/hist/<id>/<a>/<b>
    function wikiRoute(h) {
      if (h[1] === 'hist' && h[2]) {
        if (!CFG.lens) { CFG.lens = 'ref'; CFG.major = '__changes'; CFG.minor = ''; }  // 기록 주소로 바로 들어온 경우
        cfgRenderNav();
        wikiHistory(Number(h[2]), Number(h[3]) || 0, Number(h[4]) || 0);
        return true;
      }
      return false;
    }

    // ---------- 최근 변경 (참고 > 최근 변경) ----------
    async function wikiChangesView(before) {
      const bodyEl = document.getElementById('manual-body-content');
      if (!before) bodyEl.innerHTML = cfgCrumb() + '<div class="cfg-head"><h2 class="cfg-head-title">최근 변경</h2>' +
        '<p class="manual-desc">팀 전체에서 저장·삭제·되돌린 기록입니다. 줄을 누르면 그 판과 바로 앞 판을 비교합니다.</p></div>' +
        '<div class="cfg-table-wrap"><table class="cfg-table wk-changes"><thead><tr><th>시각</th><th>작성자</th><th>문서</th><th>판</th><th>메모</th></tr></thead><tbody id="wk-ch-body"></tbody></table></div>' +
        '<div class="wk-bar wk-bar-inline"><button type="button" class="wk-btn" id="wk-ch-more" hidden>더 보기</button></div>';
      let list;
      try { list = await api('GET', '/api/changes?limit=50' + (before ? '&before=' + before : '')); }
      catch (e) { return; }
      const tb = document.getElementById('wk-ch-body');
      if (!tb) return;
      if (!list.length && !before) tb.innerHTML = '<tr><td colspan="5">아직 변경 기록이 없습니다.</td></tr>';
      tb.insertAdjacentHTML('beforeend', list.map(c =>
        '<tr class="wk-ch-row" tabindex="0" onclick="wikiHistory(' + c.doc_id + ',' + Math.max(1, c.rev - 1) + ',' + c.rev + ',\'' + c.kind + '\',' + cfgEsc(JSON.stringify(c.title)) + ')">' +
        '<td>' + wkTime(c.created_at) + '</td><td>' + cfgEsc(c.author) + '</td>' +
        '<td>' + WK_KIND_NAME[c.kind] + ' / <b>' + cfgEsc(c.title || '(제목 없음)') + '</b>' + (c.deleted ? ' <span class="cfg-badge cfg-st-nolook">삭제</span>' : '') + '</td>' +
        '<td>' + c.rev + '판</td><td>' + cfgEsc(c.message || '') + '</td></tr>').join(''));
      const more = document.getElementById('wk-ch-more');
      if (list.length === 50) { more.hidden = false; more.onclick = () => wikiChangesView(list[list.length - 1].created_at); }
      else more.hidden = true;
    }
