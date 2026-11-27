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
        if (res.status === 401 && path !== '/api/login' && path !== '/api/team/password') {
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
        if (e.status !== 401) wikiShowLogin(e.error || '서버에 연결하지 못했습니다.');
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
