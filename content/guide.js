    // ===== 지침 기반 등록·수정·순서 편집 스튜디오 (content/guide.js) =====
    // 순수 파싱/검증/적용 엔진 (브라우저 전역 + Node 테스트 공용) + 스튜디오 UI + 편집기 인라인 연동
    var CFG_GUIDE_SCHEMA = 'fig-cfg-v1';
    var CFG_GUIDE_DOMAINS = ['network', 'security', 'web', 'compute', 'app', 'data', 'dr', 'ops'];
    var CFG_GUIDE_PROVIDERS = ['onprem', 'openstack', 'kt', 'aws', 'other'];
    var CFG_GUIDE_STATUS = ['live', 'design', 'nolook'];
    var CFG_GUIDE_CATS = ['설치', '적용', '조회', '검증'];

    var CFG_GUIDE_KIND_LABEL = {
      area: '서비스 영역 (area)',
      steps: '진행 순서 (steps)',
      instance: '인스턴스 (instance)',
      page: '참고 문서 (page)',
      cloud: '클라우드 (cloud)'
    };

    var CFG_GUIDE_SECRET_PATTERNS = [
      ['private-key-block', /-----BEGIN [A-Z ]*PRIVATE KEY-----/],
      ['wg-private-key', /PrivateKey\s*=\s*[A-Za-z0-9+/]{43}=/],
      ['aws-access-key', /AKIA[0-9A-Z]{16}/],
      ['github-token', /gh[pousr]_[A-Za-z0-9]{36}/],
      ['password-value', /(password|passwd|pwd|secret|token)\s*[:=]\s*(?![<$'"{])\S{6,}/i]
    ];

    function cfgGuideClone(v) {
      return v === undefined ? undefined : JSON.parse(JSON.stringify(v));
    }

    function cfgGuideFindSecret(v, path) {
      path = path || 'body';
      if (typeof v === 'string') {
        for (var i = 0; i < CFG_GUIDE_SECRET_PATTERNS.length; i++) {
          if (CFG_GUIDE_SECRET_PATTERNS[i][1].test(v)) {
            return { field: path, pattern: CFG_GUIDE_SECRET_PATTERNS[i][0] };
          }
        }
        return null;
      }
      if (Array.isArray(v)) {
        for (var j = 0; j < v.length; j++) {
          var hitA = cfgGuideFindSecret(v[j], path + '[' + j + ']');
          if (hitA) return hitA;
        }
        return null;
      }
      if (v && typeof v === 'object') {
        var keys = Object.keys(v);
        for (var k = 0; k < keys.length; k++) {
          var hitO = cfgGuideFindSecret(v[keys[k]], path + '.' + keys[k]);
          if (hitO) return hitO;
        }
      }
      return null;
    }

    // 1. 지침 결과(JSON 또는 마크다운 코드블록 포함 AI 응답)에서 JSON 추출
    function cfgGuideExtractJson(rawText) {
      var text = String(rawText == null ? '' : rawText).trim();
      if (!text) return { ok: false, error: '입력된 내용이 없습니다. 지침 결과 JSON 또는 AI 응답 전체를 붙여넣으세요.' };

      // 1) ```json ... ``` 또는 ``` ... ``` 코드블록 우선 시도
      var fenceRe = /```(?:json|jsonc)?\s*([\s\S]*?)```/gi;
      var matches = [];
      var m;
      while ((m = fenceRe.exec(text)) !== null) {
        if (m[1] && m[1].trim()) matches.push(m[1].trim());
      }
      for (var i = 0; i < matches.length; i++) {
        try {
          var parsedFence = JSON.parse(matches[i]);
          if (parsedFence && typeof parsedFence === 'object') return { ok: true, data: parsedFence, source: 'fence' };
        } catch (e) {}
      }

      // 2) 전체 문자열 직접 파싱
      try {
        var direct = JSON.parse(text);
        if (direct && typeof direct === 'object') return { ok: true, data: direct, source: 'direct' };
      } catch (e2) {}

      // 3) 본문 중 첫 {..} 또는 [..] 범위 추출
      var firstObj = text.indexOf('{');
      var firstArr = text.indexOf('[');
      var candidates = [];
      if (firstObj >= 0 && text.lastIndexOf('}') > firstObj) {
        candidates.push([firstObj, text.lastIndexOf('}')]);
      }
      if (firstArr >= 0 && text.lastIndexOf(']') > firstArr) {
        candidates.push([firstArr, text.lastIndexOf(']')]);
      }
      candidates.sort(function (a, b) { return a[0] - b[0]; });
      for (var c = 0; c < candidates.length; c++) {
        var slice = text.slice(candidates[c][0], candidates[c][1] + 1);
        try {
          var parsedSlice = JSON.parse(slice);
          if (parsedSlice && typeof parsedSlice === 'object') return { ok: true, data: parsedSlice, source: 'slice' };
        } catch (e3) {}
      }

      return { ok: false, error: '유효한 JSON 구조를 찾지 못했습니다. 따옴표나 쉼표 문법 오류 또는 ```json 코드블록 누락을 확인하세요.' };
    }

    function cfgGuideInferKindFromRaw(obj, ctx) {
      if (ctx && ctx.kind) return ctx.kind;
      if (!obj || typeof obj !== 'object') return 'area';
      if (Array.isArray(obj.items)) return 'steps';
      if (Array.isArray(obj.blocks)) return 'page';
      if (typeof obj.provider === 'string' && !obj.title && !Array.isArray(obj.domains)) return 'cloud';
      if (Array.isArray(obj.domains) || Array.isArray(obj.commands) || Array.isArray(obj.config)) return 'area';
      if (Array.isArray(obj.specs) || obj.short !== undefined || obj.steps !== undefined) return 'instance';
      if (obj.title !== undefined) return 'page';
      return 'area';
    }

    // 2. 다양한 입력 형태를 operation 배열로 정규화
    function cfgGuideNormalizeInput(parsed, ctx) {
      ctx = ctx || {};
      if (!parsed || typeof parsed !== 'object') {
        return { ok: false, error: 'JSON 최상위 구조는 객체 또는 배열이어야 합니다.', ops: [] };
      }
      if (Array.isArray(parsed)) {
        if (!parsed.length) return { ok: false, error: '작업 목록 배열이 비어 있습니다.', ops: [] };
        return { ok: true, ops: parsed };
      }
      if (Array.isArray(parsed.operations)) {
        if (!parsed.operations.length) return { ok: false, error: 'operations 배열이 비어 있습니다.', ops: [] };
        return {
          ok: true,
          ops: parsed.operations.map(function (o) {
            return Object.assign({ schema: parsed.schema || CFG_GUIDE_SCHEMA }, o);
          })
        };
      }
      if (Array.isArray(parsed.ops)) {
        if (!parsed.ops.length) return { ok: false, error: 'ops 배열이 비어 있습니다.', ops: [] };
        return {
          ok: true,
          ops: parsed.ops.map(function (o) {
            return Object.assign({ schema: parsed.schema || CFG_GUIDE_SCHEMA }, o);
          })
        };
      }
      var hasOpKeys = !!(parsed.action || parsed.patch || parsed.order || parsed.move ||
        parsed.sections || parsed.target !== undefined || parsed.doc_id !== undefined ||
        (parsed.body && typeof parsed.body === 'object' && parsed.kind));
      if (hasOpKeys) {
        return { ok: true, ops: [parsed] };
      }
      // Raw body JSON 직접 붙여넣기 폴백
      var kind = cfgGuideInferKindFromRaw(parsed, ctx);
      var wrapped = {
        schema: CFG_GUIDE_SCHEMA,
        action: ctx.docId ? 'update' : 'create',
        kind: kind,
        doc_id: ctx.docId || undefined,
        parent_id: ctx.parentId || undefined,
        body: parsed,
        message: ctx.docId ? 'JSON 본문 직접 수정 반영' : 'JSON 본문 직접 생성 반영'
      };
      return { ok: true, ops: [wrapped], inferredRaw: true };
    }

    function cfgGuideNormStr(s) {
      return String(s == null ? '' : s).trim().toLowerCase().replace(/\s+/g, ' ');
    }

    function cfgGuideFindCloud(ref, data) {
      var clouds = (data && data.clouds) || [];
      if (typeof ref === 'number') {
        return clouds.find(function (c) { return c.id === ref; }) || null;
      }
      var q = cfgGuideNormStr(ref);
      if (!q) return null;
      return clouds.find(function (c) {
        return cfgGuideNormStr(c.name) === q || cfgGuideNormStr(c.provider) === q || String(c.id) === q;
      }) || clouds.find(function (c) {
        return cfgGuideNormStr(c.name).indexOf(q) >= 0;
      }) || null;
    }

    function cfgGuideFindInstance(ref, data, cloudFilter) {
      var pages = (data && data.pages) || {};
      var instIds = (data && data.instances) || [];
      var list = instIds.map(function (pid) { return pages[pid]; }).filter(Boolean);
      if (cloudFilter) {
        var cf = cfgGuideNormStr(cloudFilter);
        list = list.filter(function (p) {
          return cfgGuideNormStr(p.cloudName) === cf || cfgGuideNormStr(p.cloud) === cf || String(p.cloudId) === cf;
        });
      }
      if (typeof ref === 'number') {
        return list.find(function (p) { return p.docId === ref; }) || null;
      }
      var q = cfgGuideNormStr(ref);
      if (!q) return null;
      return list.find(function (p) {
        return cfgGuideNormStr(p.short) === q || cfgGuideNormStr(p.title) === q ||
          ('inst-' + p.docId) === q || String(p.docId) === q;
      }) || list.find(function (p) {
        return cfgGuideNormStr(p.title).split(' (')[0].trim() === q;
      }) || list.find(function (p) {
        return cfgGuideNormStr(p.title).indexOf(q) >= 0 || cfgGuideNormStr(p.short).indexOf(q) >= 0;
      }) || null;
    }

    function cfgGuideResolveAreaRefs(items, data) {
      if (!Array.isArray(items)) return items;
      return items.map(function (it) {
        var row = cfgGuideClone(it) || {};
        if (!row.instance_id && row.instance) {
          var inst = cfgGuideFindInstance(row.instance, data);
          if (inst) row.instance_id = inst.docId;
        }
        if (!row.area_id && row.area && row.instance_id && data && data.pages) {
          var p = data.pages['inst-' + row.instance_id];
          if (p && Array.isArray(p.areas)) {
            var q = cfgGuideNormStr(row.area);
            var hit = p.areas.find(function (a) { return cfgGuideNormStr(a.name) === q; }) ||
              p.areas.find(function (a) { return cfgGuideNormStr(a.name).indexOf(q) >= 0; });
            if (hit) row.area_id = hit.docId;
          }
        }
        delete row.instance;
        delete row.area;
        return row;
      });
    }

    function cfgGuideFindParentId(kind, op, data, ctx) {
      if (kind === 'cloud' || kind === 'steps' || kind === 'page') return null;
      if (op.parent_id != null && op.parent_id !== '') return Number(op.parent_id);

      var parent = op.parent;
      if (kind === 'instance') {
        if (typeof parent === 'string' || typeof parent === 'number') {
          var cl = cfgGuideFindCloud(parent, data);
          if (cl) return cl.id;
        } else if (parent && typeof parent === 'object' && parent.cloud) {
          var cl2 = cfgGuideFindCloud(parent.cloud, data);
          if (cl2) return cl2.id;
        }
        if (ctx && ctx.cloudId) return Number(ctx.cloudId);
        if (ctx && ctx.parentId && data && data.byId && data.byId[ctx.parentId] && data.byId[ctx.parentId].kind === 'cloud') {
          return Number(ctx.parentId);
        }
        var clouds = (data && data.clouds) || [];
        if (clouds.length === 1) return clouds[0].id;
        return null;
      }

      if (kind === 'area') {
        if (typeof parent === 'string' || typeof parent === 'number') {
          var inst = cfgGuideFindInstance(parent, data);
          if (inst) return inst.docId;
        } else if (parent && typeof parent === 'object') {
          var inst2 = cfgGuideFindInstance(parent.instance || parent.short || parent.title, data, parent.cloud);
          if (inst2) return inst2.docId;
        }
        if (ctx && ctx.instanceDocId) return Number(ctx.instanceDocId);
        if (ctx && ctx.parentId && data && data.byId && data.byId[ctx.parentId] && data.byId[ctx.parentId].kind === 'instance') {
          return Number(ctx.parentId);
        }
        return null;
      }
      return null;
    }

    function cfgGuideFindTargetDoc(kind, op, data, ctx) {
      var byId = (data && data.byId) || {};
      if (kind === 'steps') {
        var sid = op.doc_id != null ? Number(op.doc_id) : (data && data.stepsDocId) || (ctx && ctx.docId);
        return (sid && byId[sid]) ? byId[sid] : null;
      }
      if (op.doc_id != null && op.doc_id !== '') {
        var d = byId[Number(op.doc_id)];
        if (d && d.kind === kind) return d;
        return d || null;
      }

      var target = op.target;
      if (target != null && target !== '') {
        if (kind === 'cloud') {
          var cl = cfgGuideFindCloud(typeof target === 'object' ? (target.cloud || target.name) : target, data);
          if (cl && byId[cl.id]) return byId[cl.id];
        }
        if (kind === 'instance') {
          var inst = typeof target === 'object'
            ? cfgGuideFindInstance(target.instance || target.short || target.title, data, target.cloud)
            : cfgGuideFindInstance(target, data);
          if (inst && byId[inst.docId]) return byId[inst.docId];
        }
        if (kind === 'area') {
          var instHint = null;
          var areaName = '';
          if (typeof target === 'string') {
            var sepIdx = target.indexOf('/') >= 0 ? target.indexOf('/') : target.indexOf('.');
            if (sepIdx > 0) {
              instHint = target.slice(0, sepIdx).trim();
              areaName = target.slice(sepIdx + 1).trim();
            } else {
              areaName = target.trim();
            }
          } else if (typeof target === 'object') {
            instHint = target.instance || target.short || '';
            areaName = target.area || target.name || '';
          }
          var pages = (data && data.pages) || {};
          var instIds = (data && data.instances) || [];
          var searchInsts = [];
          if (instHint) {
            var matchedInst = cfgGuideFindInstance(instHint, data, typeof target === 'object' ? target.cloud : null);
            if (matchedInst) searchInsts.push(matchedInst);
          } else if (ctx && ctx.instanceDocId && pages['inst-' + ctx.instanceDocId]) {
            searchInsts.push(pages['inst-' + ctx.instanceDocId]);
          } else {
            instIds.forEach(function (pid) { if (pages[pid]) searchInsts.push(pages[pid]); });
          }
          var aq = cfgGuideNormStr(areaName);
          for (var i = 0; i < searchInsts.length; i++) {
            var areas = searchInsts[i].areas || [];
            var exact = areas.find(function (a) { return cfgGuideNormStr(a.name) === aq || ('a' + a.docId) === aq || String(a.docId) === aq; });
            if (exact && byId[exact.docId]) return byId[exact.docId];
            var partial = areas.find(function (a) { return cfgGuideNormStr(a.name).indexOf(aq) >= 0; });
            if (partial && byId[partial.docId]) return byId[partial.docId];
          }
        }
        if (kind === 'page') {
          var pq = cfgGuideNormStr(typeof target === 'object' ? (target.title || target.name) : target);
          var allIds = Object.keys(byId);
          for (var k = 0; k < allIds.length; k++) {
            var pd = byId[allIds[k]];
            if (pd && pd.kind === 'page' && pd.body && cfgGuideNormStr(pd.body.title) === pq) return pd;
          }
          for (var m = 0; m < allIds.length; m++) {
            var pd2 = byId[allIds[m]];
            if (pd2 && pd2.kind === 'page' && pd2.body && cfgGuideNormStr(pd2.body.title).indexOf(pq) >= 0) return pd2;
          }
        }
      }

      if (ctx && ctx.docId && byId[ctx.docId] && byId[ctx.docId].kind === kind) {
        return byId[ctx.docId];
      }
      return null;
    }

    function cfgGuideMatchItem(section, item, matcher) {
      if (typeof matcher === 'number') return false;
      var q = cfgGuideNormStr(matcher);
      if (!q) return false;
      if (typeof item === 'string') return cfgGuideNormStr(item).indexOf(q) >= 0;
      if (Array.isArray(item)) {
        return item.some(function (cell) { return cfgGuideNormStr(cell).indexOf(q) >= 0; });
      }
      if (item && typeof item === 'object') {
        var fields = [item.no, item.label, item.title, item.name, item.text, item.code];
        return fields.some(function (f) { return f != null && cfgGuideNormStr(f).indexOf(q) >= 0; });
      }
      return false;
    }

    function cfgGuideFindIdx(arr, selector, section) {
      if (!Array.isArray(arr)) return -1;
      if (typeof selector === 'number') {
        return selector >= 0 && selector < arr.length ? selector : -1;
      }
      if (selector && typeof selector === 'object' && typeof selector.index === 'number') {
        return selector.index >= 0 && selector.index < arr.length ? selector.index : -1;
      }
      var m = selector && typeof selector === 'object' ? (selector.match != null ? selector.match : selector.no) : selector;
      if (m == null) return -1;
      if (section === 'items') {
        var nq = cfgGuideNormStr(m);
        var exactNo = arr.findIndex(function (it) { return it && cfgGuideNormStr(it.no) === nq; });
        if (exactNo >= 0) return exactNo;
      }
      return arr.findIndex(function (it) { return cfgGuideMatchItem(section, it, m); });
    }

    function cfgGuideReorderArray(arr, spec, section) {
      if (!Array.isArray(arr)) return [];
      var list = cfgGuideClone(arr);
      if (!spec) return list;

      // move: { from, to }
      if (spec.move && typeof spec.move === 'object') {
        var fromIdx = cfgGuideFindIdx(list, spec.move.from, section);
        var toIdx = typeof spec.move.to === 'number'
          ? Math.max(0, Math.min(list.length - 1, spec.move.to))
          : cfgGuideFindIdx(list, spec.move.to, section);
        if (fromIdx >= 0 && toIdx >= 0 && fromIdx !== toIdx) {
          var moved = list.splice(fromIdx, 1)[0];
          list.splice(toIdx, 0, moved);
        }
      }

      // order: [ ... ] (인덱스 또는 매칭 문자열/step 번호)
      if (Array.isArray(spec.order) && spec.order.length) {
        var used = {};
        var next = [];
        for (var i = 0; i < spec.order.length; i++) {
          var sel = spec.order[i];
          var idx = cfgGuideFindIdx(list, sel, section);
          if (idx >= 0 && !used[idx]) {
            used[idx] = true;
            next.push(list[idx]);
          }
        }
        // 누락된 기존 항목은 유실 방지를 위해 뒤에 보존
        for (var j = 0; j < list.length; j++) {
          if (!used[j]) next.push(list[j]);
        }
        list = next;
      }

      if (section === 'items' && spec.renumber === true) {
        list.forEach(function (it, i) { if (it && typeof it === 'object') it.no = 'S' + i; });
      }
      return list;
    }

    function cfgGuideApplyEditEntry(section, curItem, spec) {
      if (section === 'design') {
        if (typeof spec === 'string') return spec;
        if (spec && typeof spec === 'object') {
          return spec.value !== undefined ? String(spec.value) : (spec.text !== undefined ? String(spec.text) : curItem);
        }
        return curItem;
      }
      if (section === 'trouble' || section === 'specs') {
        if (Array.isArray(spec)) return spec.slice();
        var row = Array.isArray(curItem) ? curItem.slice() : (section === 'trouble' ? ['', '', '', ''] : ['', '']);
        if (spec && typeof spec === 'object') {
          if (Array.isArray(spec.value)) return spec.value.slice();
          var keyMap = section === 'trouble'
            ? { '0': 0, '1': 1, '2': 2, '3': 3, symptom: 0, cause: 1, check: 2, action: 3 }
            : { '0': 0, '1': 1, key: 0, name: 0, value: 1 };
          Object.keys(spec).forEach(function (k) {
            if (k === 'index' || k === 'match') return;
            if (keyMap[k] !== undefined) row[keyMap[k]] = spec[k];
          });
        }
        return row;
      }
      if (curItem && typeof curItem === 'object' && spec && typeof spec === 'object') {
        var out = cfgGuideClone(curItem);
        Object.keys(spec).forEach(function (k) {
          if (k === 'index' || k === 'match') return;
          out[k] = cfgGuideClone(spec[k]);
        });
        return out;
      }
      return spec;
    }

    function cfgGuideNormalizeAddItem(section, rawItem, data) {
      var item = cfgGuideClone(rawItem);
      if (item && typeof item === 'object' && !Array.isArray(item)) {
        var insertAt = typeof item.index === 'number' ? item.index : null;
        var val = item.value !== undefined ? item.value : item;
        if (val && typeof val === 'object' && !Array.isArray(val) && val.index !== undefined) {
          delete val.index;
        }
        if (section === 'items') val = cfgGuideResolveAreaRefs([val], data)[0];
        return { insertAt: insertAt, value: val };
      }
      return { insertAt: null, value: item };
    }

    function cfgGuideApplyPatch(kind, origBody, patch, data) {
      var next = cfgGuideClone(origBody) || {};
      if (!patch || typeof patch !== 'object') return next;

      // 1. set
      if (patch.set && typeof patch.set === 'object') {
        Object.keys(patch.set).forEach(function (k) {
          next[k] = k === 'items'
            ? cfgGuideResolveAreaRefs(patch.set[k], data)
            : cfgGuideClone(patch.set[k]);
        });
      }

      // 2. add
      if (patch.add && typeof patch.add === 'object') {
        Object.keys(patch.add).forEach(function (sec) {
          next[sec] = Array.isArray(next[sec]) ? next[sec] : [];
          var entries = Array.isArray(patch.add[sec]) ? patch.add[sec] : [patch.add[sec]];
          // specs/trouble 단일 배열 추가 구분: e.g. [["키","값"]] vs ["키","값"]
          if ((sec === 'specs' || sec === 'trouble') && entries.length && typeof entries[0] === 'string') {
            entries = [entries];
          }
          entries.forEach(function (entry) {
            var norm = cfgGuideNormalizeAddItem(sec, entry, data);
            if (norm.insertAt != null && norm.insertAt >= 0 && norm.insertAt <= next[sec].length) {
              next[sec].splice(norm.insertAt, 0, norm.value);
            } else {
              next[sec].push(norm.value);
            }
          });
        });
      }

      // 3. edit
      if (patch.edit && typeof patch.edit === 'object') {
        Object.keys(patch.edit).forEach(function (sec) {
          if (!Array.isArray(next[sec])) return;
          var entries = Array.isArray(patch.edit[sec]) ? patch.edit[sec] : [patch.edit[sec]];
          entries.forEach(function (entry) {
            var idx = cfgGuideFindIdx(next[sec], entry, sec);
            if (idx >= 0) {
              var updated = cfgGuideApplyEditEntry(sec, next[sec][idx], entry);
              if (sec === 'items') updated = cfgGuideResolveAreaRefs([updated], data)[0];
              next[sec][idx] = updated;
            }
          });
        });
      }

      // 4. remove
      if (patch.remove && typeof patch.remove === 'object') {
        Object.keys(patch.remove).forEach(function (sec) {
          if (!Array.isArray(next[sec])) return;
          var sels = Array.isArray(patch.remove[sec]) ? patch.remove[sec] : [patch.remove[sec]];
          var idxs = [];
          sels.forEach(function (sel) {
            var idx = cfgGuideFindIdx(next[sec], sel, sec);
            if (idx >= 0 && idxs.indexOf(idx) < 0) idxs.push(idx);
          });
          idxs.sort(function (a, b) { return b - a; }).forEach(function (idx) {
            next[sec].splice(idx, 1);
          });
        });
      }

      // 5. reorder inside patch
      if (patch.reorder && typeof patch.reorder === 'object') {
        next = cfgGuideApplyReorder(kind, next, patch.reorder);
      }

      return next;
    }

    function cfgGuideApplyReorder(kind, origBody, op) {
      var next = cfgGuideClone(origBody) || {};
      if (kind === 'steps') {
        if (op.body && Array.isArray(op.body.items)) {
          next.items = cfgGuideClone(op.body.items);
          if (op.renumber === true) {
            next.items.forEach(function (it, i) { if (it && typeof it === 'object') it.no = 'S' + i; });
          }
          return next;
        }
        next.items = cfgGuideReorderArray(next.items || [], op, 'items');
        return next;
      }
      if (kind === 'area') {
        if (op.sections && typeof op.sections === 'object') {
          Object.keys(op.sections).forEach(function (sec) {
            if (!Array.isArray(next[sec])) return;
            var s = op.sections[sec];
            next[sec] = cfgGuideReorderArray(next[sec], Array.isArray(s) ? { order: s } : s, sec);
          });
          return next;
        }
        var secName = op.section || (op.move && op.move.section) || 'commands';
        if (Array.isArray(next[secName])) {
          next[secName] = cfgGuideReorderArray(next[secName], op, secName);
        }
        return next;
      }
      if (kind === 'page') {
        next.blocks = cfgGuideReorderArray(next.blocks || [], op, 'blocks');
        return next;
      }
      if (kind === 'instance') {
        next.specs = cfgGuideReorderArray(next.specs || [], op, 'specs');
        return next;
      }
      return next;
    }

    function cfgGuideDefaultBody(kind) {
      if (kind === 'cloud') return { name: '', provider: 'openstack', desc: '' };
      if (kind === 'instance') return { title: '', short: '', tag: '', status: 'live', steps: '', desc: '', specs: [] };
      if (kind === 'area') return { name: '', status: 'live', domains: [], design: [], config: [], commands: [], verify: [], trouble: [] };
      if (kind === 'steps') return { items: [] };
      return { title: '', tag: '', desc: '', blocks: [] };
    }

    function cfgGuideValidateBody(kind, body, message) {
      var errs = [];
      if (!body || typeof body !== 'object') {
        errs.push('문서 body가 객체 형태가 아닙니다.');
        return errs;
      }
      var hasText = function (f) { return typeof body[f] === 'string' && body[f].trim() !== ''; };

      if (kind === 'cloud') {
        if (!hasText('name')) errs.push('클라우드 이름(name)을 입력하세요.');
        if (CFG_GUIDE_PROVIDERS.indexOf(body.provider) < 0) {
          errs.push('클라우드 종류(provider)는 ' + CFG_GUIDE_PROVIDERS.join(', ') + ' 중 하나여야 합니다.');
        }
      } else if (kind === 'instance') {
        if (!hasText('title')) errs.push('인스턴스 이름(title)을 입력하세요.');
        if (body.status && CFG_GUIDE_STATUS.indexOf(body.status) < 0) {
          errs.push('상태(status)는 live, design, nolook 중 하나여야 합니다.');
        }
      } else if (kind === 'area') {
        if (!hasText('name')) errs.push('서비스 영역 이름(name)을 입력하세요.');
        if (!Array.isArray(body.domains) || !body.domains.length) {
          errs.push('서비스 분류(domains)를 1개 이상 지정하세요 (' + CFG_GUIDE_DOMAINS.join(', ') + ').');
        } else {
          var badDom = body.domains.filter(function (d) { return CFG_GUIDE_DOMAINS.indexOf(d) < 0; });
          if (badDom.length) errs.push('허용되지 않은 서비스 분류: ' + badDom.join(', '));
        }
        if (body.status && CFG_GUIDE_STATUS.indexOf(body.status) < 0) {
          errs.push('상태(status)는 live, design, nolook 중 하나여야 합니다.');
        }
      } else if (kind === 'steps') {
        if (!Array.isArray(body.items)) errs.push('진행 순서 항목(items)은 배열이어야 합니다.');
      } else if (kind === 'page') {
        if (!hasText('title')) errs.push('문서 제목(title)을 입력하세요.');
      } else {
        errs.push('알 수 없는 문서 종류(kind): ' + kind);
      }

      if (message && String(message).length > 200) {
        errs.push('변경 메모(message)는 200자 이하로 입력하세요.');
      }

      var secBody = cfgGuideFindSecret(body, 'body');
      if (secBody) {
        errs.push('비밀값처럼 보이는 문자열이 감지되었습니다 (' + secBody.field + '). <비밀번호>, <개인키> 같은 자리표시로 바꾸세요.');
      }
      if (message) {
        var secMsg = cfgGuideFindSecret(message, 'message');
        if (secMsg) errs.push('변경 메모(message)에 비밀값 형태를 넣을 수 없습니다.');
      }
      return errs;
    }

    function cfgGuideSummarizeChanges(action, kind, origBody, nextBody, op) {
      if (action === 'create') {
        if (kind === 'area') {
          return '신규 영역 생성 — 설계 ' + (nextBody.design || []).length + ' · 설정 ' + (nextBody.config || []).length +
            ' · 명령어 ' + (nextBody.commands || []).length + ' · 검증 ' + (nextBody.verify || []).length +
            ' · 오류대응 ' + (nextBody.trouble || []).length;
        }
        if (kind === 'steps') return '진행 순서 생성 — ' + (nextBody.items || []).length + '단계';
        if (kind === 'page') return '참고 문서 생성 — 블록 ' + (nextBody.blocks || []).length + '개';
        if (kind === 'instance') return '인스턴스 생성 — 사양 ' + (nextBody.specs || []).length + '항목';
        return '클라우드 생성 (' + (nextBody.provider || '') + ')';
      }
      if (action === 'reorder') {
        if (kind === 'steps') return '진행 순서 재배치 (' + (nextBody.items || []).length + '단계' + (op.renumber ? ', 번호 재정렬' : '') + ')';
        if (kind === 'area') {
          var sec = op.sections ? Object.keys(op.sections).join(', ') : (op.section || (op.move && op.move.section) || 'commands');
          return '서비스 영역 내부 순서 변경 (' + sec + ')';
        }
        return '항목 순서 변경';
      }
      if (action === 'patch') {
        var parts = [];
        var p = op.patch || {};
        if (p.set) parts.push('속성 변경(' + Object.keys(p.set).join(', ') + ')');
        if (p.add) parts.push('항목 추가(' + Object.keys(p.add).join(', ') + ')');
        if (p.edit) parts.push('항목 수정(' + Object.keys(p.edit).join(', ') + ')');
        if (p.remove) parts.push('항목 삭제(' + Object.keys(p.remove).join(', ') + ')');
        if (p.reorder) parts.push('순서 변경');
        return parts.length ? parts.join(' · ') : '부분 수정';
      }
      return '전체 본문 덮어쓰기 수정';
    }

    // 3. 단일 operation 검증 및 실행 계획 산출
    function cfgGuideResolveOp(op, data, ctx) {
      ctx = ctx || {};
      var action = String((op && op.action) || (ctx.docId ? 'update' : 'create')).toLowerCase();
      var kind = (op && op.kind) || cfgGuideInferKindFromRaw((op && op.body) || op, ctx);
      var validActions = ['create', 'update', 'patch', 'reorder'];
      var errs = [];

      if (validActions.indexOf(action) < 0) {
        errs.push('지원하지 않는 action "' + action + '" 입니다. (create, update, patch, reorder 중 선택)');
      }

      var message = (op && op.message != null) ? String(op.message).slice(0, 200) : '';
      var parentId = null;
      var targetDoc = null;
      var origBody = null;
      var nextBody = null;

      if (action === 'create') {
        parentId = cfgGuideFindParentId(kind, op || {}, data, ctx);
        if ((kind === 'instance' || kind === 'area') && !parentId) {
          errs.push((kind === 'instance' ? '클라우드(parent)' : '인스턴스(parent)') + ' 대상을 찾지 못했습니다. parent 또는 parent_id를 명시하세요.');
        }
        if (kind === 'steps' && data && data.stepsDocId) {
          errs.push('진행 순서 문서는 팀에 하나만 둘 수 있습니다. action을 "patch", "update" 또는 "reorder"로 사용하세요.');
        }
        nextBody = Object.assign(cfgGuideDefaultBody(kind), cfgGuideClone((op && op.body) || {}) || {});
        if (kind === 'steps' && Array.isArray(nextBody.items)) {
          nextBody.items = cfgGuideResolveAreaRefs(nextBody.items, data);
        }
        if (!message) message = '지침 결과로 생성';
      } else {
        targetDoc = cfgGuideFindTargetDoc(kind, op || {}, data, ctx);
        if (!targetDoc) {
          errs.push('대상 문서(doc_id 또는 target)를 찾지 못했습니다.');
        } else {
          origBody = cfgGuideClone(targetDoc.body) || {};
          if (action === 'update') {
            nextBody = cfgGuideClone(origBody);
            var incoming = (op && op.body) || {};
            Object.keys(incoming).forEach(function (k) {
              nextBody[k] = k === 'items'
                ? cfgGuideResolveAreaRefs(incoming[k], data)
                : cfgGuideClone(incoming[k]);
            });
            if (!message) message = '지침 결과로 수정';
          } else if (action === 'patch') {
            nextBody = cfgGuideApplyPatch(kind, origBody, (op && op.patch) || {}, data);
            if (!message) message = '지침 결과로 부분 수정';
          } else if (action === 'reorder') {
            nextBody = cfgGuideApplyReorder(kind, origBody, op || {});
            if (!message) message = '지침 결과로 순서 변경';
          }
        }
      }

      if (nextBody) {
        errs = errs.concat(cfgGuideValidateBody(kind, nextBody, message));
      }

      var title = nextBody ? (nextBody.name || nextBody.title || (kind === 'steps' ? '진행 순서' : '')) : '';
      var targetLabel = title || (op && (typeof op.target === 'string' ? op.target : '')) || ('#' + ((targetDoc && targetDoc.id) || (op && op.doc_id) || ''));

      return {
        ok: errs.length === 0,
        action: action,
        kind: kind,
        docId: targetDoc ? targetDoc.id : null,
        baseRev: targetDoc ? targetDoc.rev : null,
        parentId: parentId,
        title: title,
        targetLabel: targetLabel,
        message: message,
        origBody: origBody,
        nextBody: nextBody,
        summary: nextBody ? cfgGuideSummarizeChanges(action, kind, origBody, nextBody, op || {}) : '',
        errors: errs
      };
    }

    // 4. 현재 환경 컨텍스트 및 지침 생성기
    function cfgGuideCurrentDoc(kind, opts, data) {
      opts = opts || {};
      data = data || (typeof CFG !== 'undefined' && CFG.data) || null;
      if (!data) return null;
      var byId = data.byId || {};
      if (opts.docId && byId[opts.docId]) return byId[opts.docId];
      if (kind === 'steps' && data.stepsDocId && byId[data.stepsDocId]) return byId[data.stepsDocId];
      if (typeof CFG !== 'undefined' && CFG.data === data) {
        if (kind === 'area' && typeof cfgCurrentArea === 'function') {
          var cur = cfgCurrentArea();
          if (cur && cur.area && byId[cur.area.docId]) return byId[cur.area.docId];
        }
        if (kind === 'instance' && CFG.major && data.pages && data.pages[CFG.major]) {
          var p = data.pages[CFG.major];
          if (p && byId[p.docId]) return byId[p.docId];
        }
        if (kind === 'page' && CFG.lens === 'ref' && CFG.major && data.pages && data.pages[CFG.major]) {
          var rp = data.pages[CFG.major];
          if (rp && byId[rp.docId]) return byId[rp.docId];
        }
      }
      return null;
    }

    function cfgGuideCurrentParentInfo(kind, opts, data) {
      opts = opts || {};
      data = data || (typeof CFG !== 'undefined' && CFG.data) || null;
      if (!data) return { parentId: null, parentName: '' };
      if (kind === 'area') {
        if (opts.parentId && data.byId && data.byId[opts.parentId]) {
          var b = data.byId[opts.parentId].body || {};
          return { parentId: Number(opts.parentId), parentName: b.short || b.title || String(opts.parentId) };
        }
        if (typeof CFG !== 'undefined' && CFG.major && data.pages && data.pages[CFG.major]) {
          var pg = data.pages[CFG.major];
          if (pg && pg.kind === 'instance') return { parentId: pg.docId, parentName: pg.short || pg.title };
        }
        if (data.instances && data.instances.length && data.pages && data.pages[data.instances[0]]) {
          var fp = data.pages[data.instances[0]];
          return { parentId: fp.docId, parentName: fp.short || fp.title };
        }
      }
      if (kind === 'instance') {
        if (opts.parentId && data.byId && data.byId[opts.parentId]) {
          var cb = data.byId[opts.parentId].body || {};
          return { parentId: Number(opts.parentId), parentName: cb.name || cb.provider || String(opts.parentId) };
        }
        var clouds = data.clouds || [];
        if (clouds.length) return { parentId: clouds[0].id, parentName: clouds[0].name };
      }
      return { parentId: null, parentName: '' };
    }

    function cfgGuideContextSummary(kind, doc, data) {
      if (!data) return '';
      var lines = ['## 현재 대시보드(#cfg) 등록 현황'];
      var clouds = data.clouds || [];
      if (clouds.length) {
        lines.push('- 클라우드 목록: ' + clouds.map(function (c) {
          return c.name + '(id:' + c.id + ', ' + c.provider + ')';
        }).join(', '));
      }
      var pages = data.pages || {};
      var instIds = data.instances || [];
      if (instIds.length) {
        lines.push('- 인스턴스 목록: ' + instIds.map(function (pid) {
          var p = pages[pid];
          return p ? (p.short + '(doc_id:' + p.docId + ', 영역 ' + (p.areas || []).length + '개)') : pid;
        }).join(', '));
      }
      if (doc && doc.body) {
        lines.push('');
        lines.push('## 현재 선택된 대상 문서 (doc_id: ' + doc.id + ', kind: "' + doc.kind + '", rev: ' + doc.rev + ')');
        if (doc.kind === 'area') {
          var b = doc.body;
          var summarize = function (arr, nameFn) {
            if (!Array.isArray(arr) || !arr.length) return '  (비어 있음)';
            return arr.map(function (x, i) { return '  [' + i + '] ' + nameFn(x); }).join('\n');
          };
          lines.push('이름: ' + (b.name || '') + ' | 상태: ' + (b.status || 'live') + ' | 분류: ' + (b.domains || []).join(', '));
          lines.push('- design 인덱스:\n' + summarize(b.design, function (x) { return String(x).slice(0, 70); }));
          lines.push('- config 인덱스:\n' + summarize(b.config, function (x) { return (x && x.label) || '(라벨 없음)'; }));
          lines.push('- commands 인덱스:\n' + summarize(b.commands, function (x) { return '[' + ((x && x.cat) || '') + '] ' + ((x && x.label) || ''); }));
          lines.push('- verify 인덱스:\n' + summarize(b.verify, function (x) { return (x && x.label) || '(라벨 없음)'; }));
          lines.push('- trouble 인덱스:\n' + summarize(b.trouble, function (x) { return (x && x[0]) || ''; }));
        } else if (doc.kind === 'steps') {
          var items = doc.body.items || [];
          lines.push('현재 단계 목록 (' + items.length + '개):');
          items.forEach(function (it, i) {
            lines.push('  [' + i + '] ' + it.no + ' : ' + it.title + ' (' + (it.where || '') + ')');
          });
        } else {
          lines.push('현재 JSON 본문:');
          lines.push(JSON.stringify(doc.body, null, 2));
        }
      }
      return lines.join('\n');
    }

    // 5. 문서 종류 × 작업 유형별 사용 예시 생성 (모든 예시는 cfgGuideResolveOp(ok:true) 자기 검증 통과)
    function cfgGuideExamples(kind, opts, data) {
      opts = opts || {};
      data = data || (typeof CFG !== 'undefined' && CFG.data) || null;
      var doc = cfgGuideCurrentDoc(kind, opts, data);
      var pInfo = cfgGuideCurrentParentInfo(kind, opts, data);
      var out = [];

      if (kind === 'area') {
        var areaTarget = doc ? { doc_id: doc.id } : { target: 'controller / OpenStack 핵심 서비스' };
        var areaBody = (doc && doc.body) || {};
        var cmdLen = Array.isArray(areaBody.commands) ? areaBody.commands.length : 0;
        var reorderExample = cmdLen >= 2
          ? {
              schema: CFG_GUIDE_SCHEMA,
              action: 'reorder',
              kind: 'area',
              doc_id: doc.id,
              section: 'commands',
              order: (function () {
                var arr = [];
                for (var i = 0; i < cmdLen; i++) arr.push(i);
                var tmp = arr[0]; arr[0] = arr[1]; arr[1] = tmp;
                return arr;
              })(),
              message: '명령어 0번과 1번 순서 교체'
            }
          : Object.assign({
              schema: CFG_GUIDE_SCHEMA,
              action: 'reorder',
              kind: 'area'
            }, areaTarget, {
              section: 'commands',
              move: { from: 1, to: 0 },
              message: '실행 명령어 우선순위 순서 조정'
            });

        out.push({
          mode: 'create',
          badge: '➕ 생성 예시',
          title: '새 서비스 영역(area) 등록',
          desc: '지정한 인스턴스(' + (pInfo.parentName || 'controller') + ') 아래에 설계·설정·명령어·검증·오류대응을 한 번에 생성합니다.',
          json: {
            schema: CFG_GUIDE_SCHEMA,
            action: 'create',
            kind: 'area',
            parent: pInfo.parentName || 'controller',
            message: '모니터링 exporter 서비스 영역 신규 등록',
            body: {
              name: 'Node Exporter 모니터링',
              status: 'live',
              domains: ['ops', 'compute'],
              design: [
                '시스템 CPU·메모리·디스크 메트릭을 9100 포트로 노출합니다.',
                'Prometheus가 WireGuard 또는 내부망을 통해 15초마다 수집합니다.'
              ],
              config: [
                {
                  label: '/etc/systemd/system/node_exporter.service',
                  code: '[Unit]\nDescription=Prometheus Node Exporter\nAfter=network.target\n\n[Service]\nExecStart=/usr/local/bin/node_exporter\n\n[Install]\nWantedBy=multi-user.target'
                }
              ],
              commands: [
                { cat: '조회', label: 'node_exporter 서비스 상태 확인', code: 'systemctl status node_exporter --no-pager' },
                { cat: '검증', label: '메트릭 엔드포인트 응답 확인', code: 'curl -s http://127.0.0.1:9100/metrics | head -n 10' }
              ],
              verify: [
                { label: '9100 포트 리스닝 확인', code: 'ss -tulnp | grep 9100', expect: '0.0.0.0:9100 LISTEN' }
              ],
              trouble: [
                ['9100 포트 접속 거부', 'systemd 서비스 중지 / 방화벽', 'systemctl status node_exporter', 'systemctl restart node_exporter 실행']
              ]
            }
          }
        });

        out.push({
          mode: 'patch',
          badge: '✏️ 수정 예시',
          title: '기존 서비스 영역 부분 수정 (명령어·원칙 추가)',
          desc: '기존 내용과 slug는 유지한 채 설계 원칙과 실행 명령어만 안전하게 추가·수정합니다.',
          json: Object.assign({
            schema: CFG_GUIDE_SCHEMA,
            action: 'patch',
            kind: 'area'
          }, areaTarget, {
            message: '점검 명령어 추가 및 상태 확인 보완',
            patch: {
              add: {
                design: '변경 작업 전 반드시 백업 설정 파일을 /tmp 에 사본 저장합니다.',
                commands: [
                  { cat: '조회', label: '최근 오류 로그 20줄 확인', code: 'journalctl -p err -n 20 --no-pager' }
                ]
              }
            }
          })
        });

        out.push({
          mode: 'reorder',
          badge: '↕️ 순서 편집 예시',
          title: '영역 내부 명령어 순서 재배치',
          desc: 'commands·config·design·verify 배열의 표시 순서를 인덱스 또는 move 규칙으로 바꿉니다.',
          json: reorderExample
        });
      } else if (kind === 'steps') {
        var stepsBody = (doc && doc.body) || {};
        var items = Array.isArray(stepsBody.items) ? stepsBody.items : [];
        var sampleOrder = items.length >= 2
          ? [items[1].no, items[0].no].concat(items.slice(2).map(function (x) { return x.no; }))
          : ['S0', 'S2', 'S1'];

        out.push({
          mode: 'create',
          badge: '➕ 단계 추가 예시',
          title: '진행 순서에 새 점검 단계 추가',
          desc: 'steps 문서의 items 배열 원하는 위치(index)에 새 단계를 삽입합니다.',
          json: {
            schema: CFG_GUIDE_SCHEMA,
            action: 'patch',
            kind: 'steps',
            message: 'DR 복구 훈련 검증 단계 추가',
            patch: {
              add: {
                items: {
                  index: items.length,
                  no: 'S' + items.length,
                  title: 'DR 페일오버 최종 점검',
                  where: 'aws-dr · kt-edge',
                  why: '장애 전환 후 외부 도메인 응답과 MySQL 복제 상태를 검증합니다.',
                  gate: 'curl -sI https://minwon.ktci5.kr | head -n 1',
                  instance: 'aws-dr'
                }
              }
            }
          }
        });

        out.push({
          mode: 'patch',
          badge: '✏️ 단계 수정 예시',
          title: '특정 단계 설명 및 통과 조건 수정',
          desc: '단계 번호(match: "S0")로 찾아 통과 조건(gate)이나 이유(why)만 수정합니다.',
          json: {
            schema: CFG_GUIDE_SCHEMA,
            action: 'patch',
            kind: 'steps',
            message: 'S0 접속 확인 설명 보완',
            patch: {
              edit: {
                items: {
                  match: items.length ? items[0].no : 'S0',
                  why: '모든 작업은 점프 호스트(s1)를 거쳐 OpenStack·K8s·DB로 연결되며 사전 SSH 응답 확인이 필수입니다.'
                }
              }
            }
          }
        });

        out.push({
          mode: 'reorder',
          badge: '↕️ 순서 편집 예시',
          title: '진행 순서 재배치 및 번호(S0..) 자동 정렬',
          desc: '단계 번호 배열(order) 순서대로 배치하고 renumber: true로 번호를 깔끔하게 다시 매깁니다.',
          json: {
            schema: CFG_GUIDE_SCHEMA,
            action: 'reorder',
            kind: 'steps',
            order: sampleOrder,
            renumber: false,
            message: '단계 순서 재조정'
          }
        });
      } else if (kind === 'instance') {
        var instTarget = doc ? { doc_id: doc.id } : { target: 'controller' };
        var specsLen = (doc && doc.body && Array.isArray(doc.body.specs)) ? doc.body.specs.length : 0;

        out.push({
          mode: 'create',
          badge: '➕ 생성 예시',
          title: '새 인스턴스 노드 등록',
          desc: '클라우드(' + (pInfo.parentName || 'OpenStack') + ') 아래에 신규 VM/서버를 등록합니다.',
          json: {
            schema: CFG_GUIDE_SCHEMA,
            action: 'create',
            kind: 'instance',
            parent: pInfo.parentName || 'OpenStack',
            message: '신규 워커 노드 인스턴스 등록',
            body: {
              title: 'k8s-w2 (K3s Worker 2)',
              short: 'w2',
              tag: '172.20.0.181 · 신규 확장',
              status: 'design',
              steps: 'S8 · S12',
              desc: '트래픽 증가에 대비한 온프렘 OpenStack 추가 K3s 워커 노드 설계안입니다.',
              specs: [
                ['내부 IP', '172.20.0.181'],
                ['역할', 'k3s-agent (minwon-app 파드 분산)']
              ]
            }
          }
        });

        out.push({
          mode: 'patch',
          badge: '✏️ 수정 예시',
          title: '인스턴스 사양(specs) 항목 추가',
          desc: '기존 인스턴스 개요와 기존 사양은 보존하고 사양 항목만 추가합니다.',
          json: Object.assign({
            schema: CFG_GUIDE_SCHEMA,
            action: 'patch',
            kind: 'instance'
          }, instTarget, {
            message: '모니터링 에이전트 사양 메모 추가',
            patch: {
              add: {
                specs: ['점검 포트', '9100 (node_exporter)']
              }
            }
          })
        });

        out.push({
          mode: 'reorder',
          badge: '↕️ 순서 편집 예시',
          title: '인스턴스 사양(specs) 표시 순서 변경',
          desc: 'specs 표의 행 순서를 위아래로 재배치합니다.',
          json: Object.assign({
            schema: CFG_GUIDE_SCHEMA,
            action: 'reorder',
            kind: 'instance'
          }, instTarget, {
            order: specsLen >= 2 ? [1, 0] : [0],
            message: '인스턴스 사양 표시 순서 조정'
          })
        });
      } else if (kind === 'page') {
        var pageTarget = doc ? { doc_id: doc.id } : { target: '전체 구성과 변수표' };
        var blkLen = (doc && doc.body && Array.isArray(doc.body.blocks)) ? doc.body.blocks.length : 0;

        out.push({
          mode: 'create',
          badge: '➕ 생성 예시',
          title: '새 참고 문서(page) 등록',
          desc: '소제목(h)·문단(p)·코드(code)·표(table) 블록으로 구성된 참고 문서를 만듭니다.',
          json: {
            schema: CFG_GUIDE_SCHEMA,
            action: 'create',
            kind: 'page',
            message: '장애 대응 체크리스트 문서 생성',
            body: {
              title: '긴급 장애 대응 체크리스트',
              tag: '운영 표준',
              desc: '서비스 응답 지연 또는 다운타임 발생 시 5분 내 원인 파악을 위한 1차 점검 절차입니다.',
              blocks: [
                { type: 'h', text: '1단계: 외부 진입 및 WAF 확인' },
                { type: 'p', text: 'KT Edge nginx 및 ModSecurity 상태와 upstream 응답 코드를 먼저 확인합니다.' },
                { type: 'code', label: 'KT Edge 헬스 체크', code: 'curl -sI https://minwon.ktci5.kr' },
                {
                  type: 'table',
                  head: ['구간', '확인 명령', '정상 기준'],
                  rows: [
                    ['WireGuard', 'wg show', 'latest handshake 2분 이내'],
                    ['K3s 노드', 'kubectl get nodes', '모든 노드 Ready']
                  ]
                }
              ]
            }
          }
        });

        out.push({
          mode: 'patch',
          badge: '✏️ 수정 예시',
          title: '참고 문서에 새 블록 추가',
          desc: '기존 문서 본문 뒤에 새 안내 문단 또는 코드 블록을 추가합니다.',
          json: Object.assign({
            schema: CFG_GUIDE_SCHEMA,
            action: 'patch',
            kind: 'page'
          }, pageTarget, {
            message: '참고 점검 명령 블록 추가',
            patch: {
              add: {
                blocks: [
                  { type: 'h', text: '추가 확인 사항' },
                  { type: 'code', label: '터널 핸드셰이크 빠른 확인', code: 'sudo wg show | grep -E "peer|latest handshake"' }
                ]
              }
            }
          })
        });

        out.push({
          mode: 'reorder',
          badge: '↕️ 순서 편집 예시',
          title: '참고 문서 블록 순서 편집',
          desc: '문서 내 blocks 배열의 표시 순서를 바꿉니다.',
          json: Object.assign({
            schema: CFG_GUIDE_SCHEMA,
            action: 'reorder',
            kind: 'page'
          }, pageTarget, {
            order: blkLen >= 2 ? [1, 0] : [0],
            message: '문서 블록 순서 조정'
          })
        });
      } else {
        // cloud
        var cloudTarget = doc ? { doc_id: doc.id } : { target: 'OpenStack' };
        out.push({
          mode: 'create',
          badge: '➕ 생성 예시',
          title: '새 클라우드 그룹 등록',
          desc: '사이드바 클라우드 기준 대분류에 새 클라우드 그룹을 추가합니다.',
          json: {
            schema: CFG_GUIDE_SCHEMA,
            action: 'create',
            kind: 'cloud',
            message: '신규 클라우드 그룹 생성',
            body: {
              name: 'Naver Cloud (예비)',
              provider: 'other',
              desc: '멀티클라우드 확장 대비 예비 환경입니다.'
            }
          }
        });

        out.push({
          mode: 'patch',
          badge: '✏️ 수정 예시',
          title: '클라우드 이름·설명 부분 수정',
          desc: '기존 클라우드의 이름(name)이나 설명(desc)을 수정합니다.',
          json: Object.assign({
            schema: CFG_GUIDE_SCHEMA,
            action: 'patch',
            kind: 'cloud'
          }, cloudTarget, {
            message: '클라우드 설명 보완',
            patch: {
              set: {
                desc: '온프레미스 OpenStack 하이브리드 클라우드 코어 영역입니다.'
              }
            }
          })
        });

        out.push({
          mode: 'update',
          badge: '📝 전체 수정 예시',
          title: '클라우드 정보 전체 갱신',
          desc: '클라우드 이름·종류(provider)·설명을 한 번에 갱신합니다.',
          json: Object.assign({
            schema: CFG_GUIDE_SCHEMA,
            action: 'update',
            kind: 'cloud'
          }, cloudTarget, {
            message: '클라우드 메타정보 갱신',
            body: {
              name: (doc && doc.body && doc.body.name) || 'OpenStack',
              provider: (doc && doc.body && doc.body.provider) || 'openstack',
              desc: (doc && doc.body && doc.body.desc) || 'OpenStack 클라우드 환경'
            }
          })
        });
      }

      return out;
    }

    // 6. AI 또는 팀원이 바로 복사해 사용할 수 있는 명확한 지침 생성
    function cfgGuideBuildPrompt(opts, data) {
      opts = opts || {};
      data = data || (typeof CFG !== 'undefined' && CFG.data) || null;
      var action = opts.action || 'create';
      var kind = opts.kind || 'area';
      var includeCurrent = opts.includeCurrent !== false;
      var doc = includeCurrent ? cfgGuideCurrentDoc(kind, opts, data) : null;
      var examples = cfgGuideExamples(kind, opts, data);
      var ex = examples.find(function (x) { return x.mode === action; }) || examples[0];

      var lines = [];
      lines.push('[figteam #cfg 구성 포털 등록/수정/순서편집 지침]');
      lines.push('');
      lines.push('1. 출력 형식 규칙 (필수)');
      lines.push('- 반드시 유효한 JSON 하나만 ```json ... ``` 코드블록으로 출력하세요.');
      lines.push('- 최상위에 "schema": "fig-cfg-v1" 을 포함하세요.');
      lines.push('- 여러 문서를 한 번에 처리할 때는 { "schema": "fig-cfg-v1", "operations": [ ... ] } 형태를 사용하세요.');
      lines.push('- action 값은 "create"(생성), "update"(전체 수정), "patch"(부분 추가·수정·삭제), "reorder"(순서 편집) 중 하나입니다.');
      lines.push('- kind 값은 "area"(서비스 영역), "steps"(진행 순서), "instance"(인스턴스), "page"(참고 문서), "cloud"(클라우드) 중 하나입니다.');
      lines.push('');
      lines.push('2. 보안 규칙 (위반 시 저장 차단)');
      lines.push('- 실제 비밀번호, API 키, 토큰, AWS 키, WireGuard PrivateKey를 절대 평문으로 쓰지 마세요.');
      lines.push('- 민감 값은 <비밀번호>, <개인키>, <토큰> 같은 자리표시로 적으세요.');
      lines.push('');
      lines.push('3. 허용 필드 값 기준');
      lines.push('- provider: onprem | openstack | kt | aws | other');
      lines.push('- status: live(실측) | design(설계·미적용) | nolook(미실측)');
      lines.push('- domains (area 필수, 1개 이상): network | security | web | compute | app | data | dr | ops');
      lines.push('- commands[].cat: 설치 | 적용 | 조회 | 검증');
      lines.push('- blocks[].type (page): h(소제목) | p(문단) | code(코드) | table(표)');

      if (includeCurrent && data) {
        lines.push('');
        lines.push(cfgGuideContextSummary(kind, doc, data));
      }

      lines.push('');
      lines.push('4. 이번 작업 목표: [' + (CFG_GUIDE_KIND_LABEL[kind] || kind) + '] / action="' + ex.mode + '"');
      lines.push('아래 JSON 형식을 그대로 따라 결과를 만들어 주세요:');
      lines.push('```json');
      lines.push(JSON.stringify(ex.json, null, 2));
      lines.push('```');
      lines.push('');
      lines.push('=== 아래에 반영할 내용이나 터미널 출력/메모를 붙여넣고 실행하세요 ===');
      return lines.join('\n');
    }

    // ---------- 7. 브라우저 스튜디오 UI & 위키 편집기 인라인 연동 ----------
    var CFG_GUIDE_STATE = {
      action: 'create',
      kind: 'area',
      includeCurrent: true,
      tab: 'prompt',
      docId: null,
      parentId: null,
      resolved: null,
      rawInput: ''
    };

    function cfgGuideCtxFromUi(opts) {
      opts = opts || {};
      var docId = opts.docId || null;
      var parentId = opts.parentId || null;
      var cloudId = null;
      var instanceDocId = null;
      if (typeof CFG !== 'undefined' && CFG.data) {
        if (!docId && typeof cfgCurrentArea === 'function') {
          var cur = cfgCurrentArea();
          if (cur) {
            if ((opts.kind || CFG_GUIDE_STATE.kind) === 'area') docId = cur.area.docId;
            instanceDocId = CFG.data.pages[cur.pid] ? CFG.data.pages[cur.pid].docId : null;
          }
        }
        if (CFG.major && CFG.data.pages && CFG.data.pages[CFG.major]) {
          var pg = CFG.data.pages[CFG.major];
          if (pg.kind === 'instance') {
            instanceDocId = instanceDocId || pg.docId;
            cloudId = pg.cloudId;
          } else if (pg.kind === 'doc' && !docId && (opts.kind || CFG_GUIDE_STATE.kind) === 'page') {
            docId = pg.docId;
          }
        }
        if ((opts.kind || CFG_GUIDE_STATE.kind) === 'steps' && CFG.data.stepsDocId) {
          docId = docId || CFG.data.stepsDocId;
        }
      }
      return {
        kind: opts.kind || CFG_GUIDE_STATE.kind,
        docId: docId,
        parentId: parentId,
        cloudId: cloudId,
        instanceDocId: instanceDocId
      };
    }

    function cfgGuideCopyText(text, btn, origLabel) {
      var done = function () {
        if (!btn) return;
        btn.textContent = '✓ 복사됨';
        setTimeout(function () { btn.textContent = origLabel || '복사'; }, 1400);
      };
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(text).then(done, function () { cfgCopyFallback(text, done); });
      } else if (typeof cfgCopyFallback === 'function') {
        cfgCopyFallback(text, done);
      }
    }

    function cfgGuideOpen(opts) {
      opts = opts || {};
      var old = document.getElementById('cfg-guide-modal');
      if (old) old.remove();

      CFG_GUIDE_STATE.kind = opts.kind || (CFG.lens === 'step' ? 'steps' : (CFG.lens === 'ref' ? 'page' : 'area'));
      CFG_GUIDE_STATE.action = opts.action || (opts.docId ? 'patch' : (CFG_GUIDE_STATE.kind === 'steps' ? 'reorder' : 'create'));
      CFG_GUIDE_STATE.docId = opts.docId || null;
      CFG_GUIDE_STATE.parentId = opts.parentId || null;
      CFG_GUIDE_STATE.includeCurrent = opts.includeCurrent !== false;
      CFG_GUIDE_STATE.tab = opts.tab || 'prompt';
      CFG_GUIDE_STATE.resolved = null;
      CFG_GUIDE_STATE.rawInput = opts.initialInput || '';

      var modal = document.createElement('div');
      modal.id = 'cfg-guide-modal';
      modal.className = 'cfg-modal-overlay';
      modal.innerHTML =
        '<div class="cfg-guide-card" role="dialog" aria-modal="true" aria-labelledby="cfg-guide-title">' +
          '<div class="cfg-guide-head">' +
            '<div>' +
              '<h2 id="cfg-guide-title">📋 #cfg 지침 스튜디오 — 복사 · 사용 예시 · 지침 결과 등록/수정/순서편집</h2>' +
              '<p>지침을 복사해 AI·팀원과 작업한 뒤, 나온 결과(JSON 또는 응답 전체)를 오른쪽에 붙여넣어 Diff 확인 후 즉시 반영하세요.</p>' +
            '</div>' +
            '<button type="button" class="cfg-win-btn btn-close" id="cfg-guide-close" title="닫기 (ESC)">✕</button>' +
          '</div>' +
          '<div class="cfg-guide-toolbar">' +
            '<div class="cfg-guide-mode-chips" role="group" aria-label="작업 유형">' +
              '<button type="button" class="cfg-guide-chip" data-act="create" onclick="cfgGuideSetAction(\'create\')">➕ 생성 (create)</button>' +
              '<button type="button" class="cfg-guide-chip" data-act="patch" onclick="cfgGuideSetAction(\'patch\')">✏️ 수정 (patch/update)</button>' +
              '<button type="button" class="cfg-guide-chip" data-act="reorder" onclick="cfgGuideSetAction(\'reorder\')">↕️ 순서 편집 (reorder)</button>' +
            '</div>' +
            '<label class="cfg-guide-kind-wrap">문서 종류 ' +
              '<select id="cfg-guide-kind" onchange="cfgGuideSetKind(this.value)">' +
                '<option value="area">서비스 영역 (area)</option>' +
                '<option value="steps">진행 순서 (steps)</option>' +
                '<option value="instance">인스턴스 (instance)</option>' +
                '<option value="page">참고 문서 (page)</option>' +
                '<option value="cloud">클라우드 (cloud)</option>' +
              '</select>' +
            '</label>' +
            '<label class="cfg-guide-ctx-chk"><input type="checkbox" id="cfg-guide-inc-cur" onchange="cfgGuideToggleCtx(this.checked)"> 현재 문서 컨텍스트 지침에 포함</label>' +
          '</div>' +
          '<div class="cfg-guide-split">' +
            '<section class="cfg-guide-pane cfg-guide-left">' +
              '<div class="cfg-guide-tabs">' +
                '<button type="button" class="cfg-guide-tab active" data-tab="prompt" onclick="cfgGuideSetTab(\'prompt\')">📋 지침 (바로 복사)</button>' +
                '<button type="button" class="cfg-guide-tab" data-tab="examples" onclick="cfgGuideSetTab(\'examples\')">💡 사용 예시 (생성·수정·순서)</button>' +
              '</div>' +
              '<div id="cfg-guide-left-body" class="cfg-guide-pane-body"></div>' +
            '</section>' +
            '<section class="cfg-guide-pane cfg-guide-right">' +
              '<div class="cfg-guide-right-head">' +
                '<b>📥 지침 결과 붙여넣기 &amp; 실시간 검증</b>' +
                '<div class="cfg-guide-right-acts">' +
                  '<button type="button" class="cfg-copy" onclick="cfgGuidePasteClipboard()">📋 붙여넣기</button>' +
                  '<button type="button" class="cfg-copy" onclick="cfgGuideClearInput()">🧹 비우기</button>' +
                  '<button type="button" class="cfg-run-btn cfg-run-safe" onclick="cfgGuideAnalyze()">🔍 분석·미리보기</button>' +
                '</div>' +
              '</div>' +
              '<textarea id="cfg-guide-input" class="cfg-guide-textarea" placeholder="지침대로 작성된 JSON 또는 ```json ... ``` 이 포함된 AI 응답 전체를 여기에 붙여넣으세요. 왼쪽 [사용 예시]의 [입력창에 넣기]로 바로 테스트해 볼 수도 있습니다." oninput="cfgGuideOnInput()"></textarea>' +
              '<div id="cfg-guide-preview" class="cfg-guide-preview"></div>' +
            '</section>' +
          '</div>' +
          '<div class="cfg-guide-foot">' +
            '<span class="cfg-guide-foot-note" id="cfg-guide-foot-status">지침 결과를 붙여넣으면 변경 Diff와 검증 상태가 여기에 표시됩니다.</span>' +
            '<div class="cfg-guide-foot-acts">' +
              '<button type="button" class="cfg-btn-cancel" id="cfg-guide-cancel">닫기</button>' +
              '<button type="button" class="wk-btn" id="cfg-guide-to-editor" onclick="cfgGuideOpenInWikiEditor()" disabled>📝 위키 편집기에 채워 열기</button>' +
              '<button type="button" class="cfg-btn-confirm" id="cfg-guide-apply" onclick="cfgGuideApplyModal()" style="background:#2563eb;border-color:#3b82f6;" disabled>🚀 지침 결과 즉시 적용 (서버 저장)</button>' +
            '</div>' +
          '</div>' +
        '</div>';

      document.body.appendChild(modal);

      var close = function () { modal.remove(); document.removeEventListener('keydown', onKey); };
      var onKey = function (e) { if (e.key === 'Escape') close(); };
      document.addEventListener('keydown', onKey);
      modal.querySelector('#cfg-guide-close').onclick = close;
      modal.querySelector('#cfg-guide-cancel').onclick = close;
      modal.onclick = function (e) { if (e.target === modal) close(); };

      modal.querySelector('#cfg-guide-kind').value = CFG_GUIDE_STATE.kind;
      modal.querySelector('#cfg-guide-inc-cur').checked = CFG_GUIDE_STATE.includeCurrent;
      if (CFG_GUIDE_STATE.rawInput) {
        modal.querySelector('#cfg-guide-input').value = CFG_GUIDE_STATE.rawInput;
      }

      cfgGuideSyncControls();
      cfgGuideRenderLeft();
      cfgGuideAnalyze();
    }

    function cfgGuideSyncControls() {
      var modal = document.getElementById('cfg-guide-modal');
      if (!modal) return;
      modal.querySelectorAll('.cfg-guide-chip').forEach(function (b) {
        b.classList.toggle('active', b.getAttribute('data-act') === CFG_GUIDE_STATE.action);
      });
      modal.querySelectorAll('.cfg-guide-tab').forEach(function (b) {
        b.classList.toggle('active', b.getAttribute('data-tab') === CFG_GUIDE_STATE.tab);
      });
    }

    function cfgGuideSetAction(act) {
      CFG_GUIDE_STATE.action = act;
      cfgGuideSyncControls();
      cfgGuideRenderLeft();
    }

    function cfgGuideSetKind(kind) {
      CFG_GUIDE_STATE.kind = kind;
      if (kind === 'steps' && CFG.data && CFG.data.stepsDocId) CFG_GUIDE_STATE.docId = CFG.data.stepsDocId;
      else if (kind !== 'area') CFG_GUIDE_STATE.docId = null;
      cfgGuideSyncControls();
      cfgGuideRenderLeft();
      cfgGuideAnalyze();
    }

    function cfgGuideToggleCtx(checked) {
      CFG_GUIDE_STATE.includeCurrent = !!checked;
      cfgGuideRenderLeft();
    }

    function cfgGuideSetTab(tab) {
      CFG_GUIDE_STATE.tab = tab;
      cfgGuideSyncControls();
      cfgGuideRenderLeft();
    }

    function cfgGuideRenderLeft() {
      var box = document.getElementById('cfg-guide-left-body');
      if (!box) return;
      var ctx = cfgGuideCtxFromUi({ kind: CFG_GUIDE_STATE.kind, docId: CFG_GUIDE_STATE.docId, parentId: CFG_GUIDE_STATE.parentId });
      if (CFG_GUIDE_STATE.tab === 'prompt') {
        var promptText = cfgGuideBuildPrompt({
          action: CFG_GUIDE_STATE.action,
          kind: CFG_GUIDE_STATE.kind,
          includeCurrent: CFG_GUIDE_STATE.includeCurrent,
          docId: ctx.docId,
          parentId: ctx.parentId
        }, CFG.data);
        var examples = cfgGuideExamples(CFG_GUIDE_STATE.kind, ctx, CFG.data);
        var ex = examples.find(function (x) { return x.mode === CFG_GUIDE_STATE.action; }) || examples[0];
        var tplText = JSON.stringify(ex.json, null, 2);
        box._promptText = promptText;
        box._tplText = tplText;
        box.innerHTML =
          '<div class="cfg-guide-left-acts">' +
            '<button type="button" class="cfg-run-btn cfg-run-safe" onclick="cfgGuideCopyPromptBtn(this)">📋 지침 전체 복사</button>' +
            '<button type="button" class="cfg-copy" onclick="cfgGuideCopyTplBtn(this)">📄 JSON 템플릿만 복사</button>' +
            '<button type="button" class="cfg-copy" onclick="cfgGuideUseExampleObj(null)">➡️ 템플릿 입력창에 넣기</button>' +
          '</div>' +
          '<p class="cfg-guide-hint">위 <b>[지침 전체 복사]</b>를 눌러 ChatGPT · Claude · Gemini 또는 팀원에게 그대로 전달하세요. 생성된 JSON 응답 전체를 오른쪽에 붙여넣으면 자동 해석됩니다.</p>' +
          '<pre class="cfg-guide-pre">' + cfgEsc(promptText) + '</pre>';
      } else {
        var exList = cfgGuideExamples(CFG_GUIDE_STATE.kind, ctx, CFG.data);
        box._examples = exList;
        box.innerHTML =
          '<p class="cfg-guide-hint">아래 예시 중 하나를 <b>[입력창에 넣기]</b>로 오른쪽에 넣으면 실제 변경 미리보기와 저장 동작을 즉시 확인·응용할 수 있습니다.</p>' +
          exList.map(function (item, idx) {
            return '<div class="cfg-guide-ex-card">' +
              '<div class="cfg-guide-ex-head">' +
                '<span class="cfg-guide-ex-badge">' + cfgEsc(item.badge) + '</span>' +
                '<b>' + cfgEsc(item.title) + '</b>' +
                '<div class="cfg-guide-ex-acts">' +
                  '<button type="button" class="cfg-copy" onclick="cfgGuideCopyExBtn(' + idx + ', this)">📋 복사</button>' +
                  '<button type="button" class="cfg-run-btn cfg-btn-view" onclick="cfgGuideUseExampleObj(' + idx + ')">➡️ 입력창에 넣기</button>' +
                '</div>' +
              '</div>' +
              '<p class="cfg-guide-ex-desc">' + cfgEsc(item.desc) + '</p>' +
              '<pre class="cfg-guide-ex-pre">' + cfgEsc(JSON.stringify(item.json, null, 2)) + '</pre>' +
            '</div>';
          }).join('');
      }
    }

    function cfgGuideCopyPromptBtn(btn) {
      var box = document.getElementById('cfg-guide-left-body');
      if (box && box._promptText) cfgGuideCopyText(box._promptText, btn, '📋 지침 전체 복사');
    }

    function cfgGuideCopyTplBtn(btn) {
      var box = document.getElementById('cfg-guide-left-body');
      if (box && box._tplText) cfgGuideCopyText(box._tplText, btn, '📄 JSON 템플릿만 복사');
    }

    function cfgGuideCopyExBtn(idx, btn) {
      var box = document.getElementById('cfg-guide-left-body');
      if (box && box._examples && box._examples[idx]) {
        cfgGuideCopyText(JSON.stringify(box._examples[idx].json, null, 2), btn, '📋 복사');
      }
    }

    function cfgGuideUseExampleObj(idx) {
      var inp = document.getElementById('cfg-guide-input');
      if (!inp) return;
      var box = document.getElementById('cfg-guide-left-body');
      var jsonStr = '';
      if (idx == null && box && box._tplText) jsonStr = box._tplText;
      else if (box && box._examples && box._examples[idx]) jsonStr = JSON.stringify(box._examples[idx].json, null, 2);
      if (!jsonStr) return;
      inp.value = jsonStr;
      cfgGuideAnalyze();
    }

    function cfgGuidePasteClipboard() {
      var inp = document.getElementById('cfg-guide-input');
      if (!inp) return;
      if (navigator.clipboard && navigator.clipboard.readText) {
        navigator.clipboard.readText().then(function (txt) {
          inp.value = txt;
          cfgGuideAnalyze();
        }, function () {
          inp.focus();
          if (typeof wikiToast === 'function') wikiToast('브라우저 붙여넣기 권한이 없어 입력창에 Ctrl/Cmd+V 해주세요.');
        });
      } else {
        inp.focus();
      }
    }

    function cfgGuideClearInput() {
      var inp = document.getElementById('cfg-guide-input');
      if (inp) { inp.value = ''; cfgGuideAnalyze(); inp.focus(); }
    }

    var CFG_GUIDE_TIMER = null;
    function cfgGuideOnInput() {
      clearTimeout(CFG_GUIDE_TIMER);
      CFG_GUIDE_TIMER = setTimeout(cfgGuideAnalyze, 180);
    }

    function cfgGuideAnalyze() {
      var inp = document.getElementById('cfg-guide-input');
      var prev = document.getElementById('cfg-guide-preview');
      var statusEl = document.getElementById('cfg-guide-foot-status');
      var btnApply = document.getElementById('cfg-guide-apply');
      var btnEditor = document.getElementById('cfg-guide-to-editor');
      if (!inp || !prev) return;

      var raw = inp.value || '';
      CFG_GUIDE_STATE.rawInput = raw;

      if (!raw.trim()) {
        CFG_GUIDE_STATE.resolved = null;
        prev.innerHTML = '<div class="cfg-guide-empty">오른쪽 입력창에 지침 결과 JSON(또는 AI 응답)을 붙여넣거나 왼쪽 예시의 <b>[입력창에 넣기]</b>를 눌러주세요.</div>';
        if (statusEl) statusEl.textContent = '지침 결과를 붙여넣으면 변경 Diff와 검증 상태가 여기에 표시됩니다.';
        if (btnApply) btnApply.disabled = true;
        if (btnEditor) btnEditor.disabled = true;
        return;
      }

      var ext = cfgGuideExtractJson(raw);
      if (!ext.ok) {
        CFG_GUIDE_STATE.resolved = null;
        prev.innerHTML = '<div class="cfg-guide-err-box"><b>JSON 해석 오류</b><p>' + cfgEsc(ext.error) + '</p></div>';
        if (statusEl) statusEl.textContent = '❌ JSON 형식을 확인해 주세요.';
        if (btnApply) btnApply.disabled = true;
        if (btnEditor) btnEditor.disabled = true;
        return;
      }

      var ctx = cfgGuideCtxFromUi({ kind: CFG_GUIDE_STATE.kind, docId: CFG_GUIDE_STATE.docId, parentId: CFG_GUIDE_STATE.parentId });
      var norm = cfgGuideNormalizeInput(ext.data, ctx);
      if (!norm.ok) {
        CFG_GUIDE_STATE.resolved = null;
        prev.innerHTML = '<div class="cfg-guide-err-box"><b>입력 구조 오류</b><p>' + cfgEsc(norm.error) + '</p></div>';
        if (statusEl) statusEl.textContent = '❌ ' + norm.error;
        if (btnApply) btnApply.disabled = true;
        if (btnEditor) btnEditor.disabled = true;
        return;
      }

      var resolvedOps = norm.ops.map(function (op) { return cfgGuideResolveOp(op, CFG.data, ctx); });
      CFG_GUIDE_STATE.resolved = resolvedOps;

      var allOk = resolvedOps.every(function (r) { return r.ok; });
      var okCount = resolvedOps.filter(function (r) { return r.ok; }).length;

      prev.innerHTML = resolvedOps.map(function (r, idx) {
        var diffHtml = '';
        if (r.nextBody) {
          if (r.action === 'create') {
            var lines = typeof bodyToText === 'function' ? bodyToText(r.kind, r.nextBody) : [JSON.stringify(r.nextBody, null, 2)];
            diffHtml = '<pre class="cfg-guide-create-pre">' + cfgEsc(lines.join('\n')) + '</pre>';
          } else if (r.origBody && typeof wikiDiffView === 'function' && typeof bodyToText === 'function') {
            diffHtml = wikiDiffView(bodyToText(r.kind, r.origBody), bodyToText(r.kind, r.nextBody), '현재 판 (' + (r.baseRev || '') + '판)', '적용 후');
          }
        }
        return '<div class="cfg-guide-op-card ' + (r.ok ? 'ok' : 'err') + '">' +
          '<div class="cfg-guide-op-head">' +
            '<span class="cfg-guide-op-badge ' + (r.ok ? 'ok' : 'err') + '">' + (r.ok ? '✓ 검증 통과' : '✕ 오류') + '</span>' +
            '<b>[' + (idx + 1) + '] ' + cfgEsc(r.action.toUpperCase()) + ' · ' + cfgEsc(r.kind) + '</b>' +
            '<span class="cfg-guide-op-target">' + cfgEsc(r.targetLabel || '') + (r.parentId ? ' (parent_id:' + r.parentId + ')' : '') + '</span>' +
          '</div>' +
          (r.summary ? '<div class="cfg-guide-op-sum">' + cfgEsc(r.summary) + '</div>' : '') +
          (r.errors.length ? '<ul class="cfg-guide-op-errs">' + r.errors.map(function (er) { return '<li>' + cfgEsc(er) + '</li>'; }).join('') + '</ul>' : '') +
          '<label class="cfg-guide-msg-row">변경 메모 <input type="text" value="' + cfgEsc(r.message || '') + '" maxlength="200" oninput="cfgGuideUpdateOpMsg(' + idx + ', this.value)"></label>' +
          diffHtml +
        '</div>';
      }).join('');

      if (statusEl) {
        statusEl.textContent = allOk
          ? ('✅ 총 ' + resolvedOps.length + '건 모두 검증을 통과했습니다. [즉시 적용] 또는 [위키 편집기 열기]가 가능합니다.')
          : ('⚠️ ' + resolvedOps.length + '건 중 ' + okCount + '건 통과, ' + (resolvedOps.length - okCount) + '건 오류가 있습니다.');
      }
      if (btnApply) btnApply.disabled = !allOk;
      if (btnEditor) btnEditor.disabled = !(allOk && resolvedOps.length === 1);
    }

    function cfgGuideUpdateOpMsg(idx, val) {
      if (CFG_GUIDE_STATE.resolved && CFG_GUIDE_STATE.resolved[idx]) {
        CFG_GUIDE_STATE.resolved[idx].message = String(val || '').slice(0, 200);
      }
    }

    function cfgGuideOpenInWikiEditor() {
      var ops = CFG_GUIDE_STATE.resolved;
      if (!ops || ops.length !== 1 || !ops[0].ok) return;
      var r = ops[0];
      if (typeof wikiOpenEditor !== 'function') {
        alert('위키 편집기 모듈을 찾을 수 없습니다.');
        return;
      }
      var modal = document.getElementById('cfg-guide-modal');
      if (modal) modal.remove();
      var meta = {
        kind: r.kind,
        docId: r.docId,
        parentId: r.parentId,
        baseRev: r.baseRev
      };
      var notice = '<p class="wk-note">지침 스튜디오 결과를 위키 편집기에 채웠습니다 (' + cfgEsc(r.summary) + '). 확인 후 아래 [저장]을 누르세요.</p>';
      wikiOpenEditor(meta, cfgGuideClone(r.nextBody), notice);
    }

    async function cfgGuideExecuteOps(ops) {
      if (!WIKI || !WIKI.ready) {
        alert('팀 위키 로그인 후 서버 저장이 가능합니다.');
        return false;
      }
      var lastKind = null;
      var lastId = null;
      var savedCount = 0;

      for (var i = 0; i < ops.length; i++) {
        var r = ops[i];
        if (!r.ok) {
          alert((i + 1) + '번째 작업에 검증 오류가 있습니다: ' + r.errors.join(', '));
          return false;
        }
        try {
          if (r.action === 'create') {
            var sibs = Object.values((CFG.data && CFG.data.byId) || {}).filter(function (d) {
              return d.kind === r.kind && d.parent_id === r.parentId;
            });
            var nextSort = sibs.length ? Math.max.apply(null, sibs.map(function (d) { return d.sort; })) + 1 : 0;
            var resC = await api('POST', '/api/docs', {
              kind: r.kind,
              parent_id: r.parentId,
              sort: nextSort,
              body: r.nextBody,
              message: r.message || '지침 결과로 생성'
            });
            lastKind = r.kind;
            lastId = resC.id;
          } else {
            await api('PUT', '/api/docs/' + r.docId, {
              base_rev: r.baseRev,
              body: r.nextBody,
              message: r.message || '지침 결과로 수정'
            });
            lastKind = r.kind;
            lastId = r.docId;
          }
          if (typeof wkRecordLocalAccess === 'function') {
            wkRecordLocalAccess(r.action === 'create' ? 'create' : 'edit', r.kind + ':' + (r.title || r.docId));
          }
          savedCount++;
        } catch (e) {
          if (e.status === 401) return false;
          if (e.status === 409) {
            alert('다른 팀원이 먼저 문서를 저장해 판 충돌(409)이 발생했습니다. 최신 문서를 다시 불러온 뒤 다시 적용해 주세요.');
            await wikiReload(true);
            return false;
          }
          alert('저장 오류: ' + (e.error || e.message || '요청 처리 실패'));
          return false;
        }
      }

      if (typeof wikiToast === 'function') wikiToast('지침 결과 ' + savedCount + '건을 서버에 저장했습니다.');
      await wikiReload(true);
      if (lastKind && lastId && typeof wkGoTo === 'function') wkGoTo(lastKind, lastId);
      return true;
    }

    async function cfgGuideApplyModal() {
      var ops = CFG_GUIDE_STATE.resolved;
      if (!ops || !ops.length) return;
      var btn = document.getElementById('cfg-guide-apply');
      if (btn) { btn.disabled = true; btn.textContent = '저장 중…'; }
      var ok = await cfgGuideExecuteOps(ops);
      if (ok) {
        var modal = document.getElementById('cfg-guide-modal');
        if (modal) modal.remove();
      } else if (btn) {
        btn.disabled = false;
        btn.textContent = '🚀 지침 결과 즉시 적용 (서버 저장)';
      }
    }

    // ---------- 8. 위키 편집기(wikiOpenEditor) 내 지침 인라인 패널 ----------
    function cfgGuideInlineHtml(meta) {
      if (!meta || !meta.kind) return '';
      var isNew = !meta.docId;
      return '<details class="cfg-guide-inline" id="cfg-guide-inline">' +
        '<summary>📋 지침 복사 · 예시 불러오기 · 지침 결과 JSON으로 이 편집 폼 자동 채우기 / 순서 편집</summary>' +
        '<div class="cfg-guide-inline-body">' +
          '<div class="cfg-guide-inline-acts">' +
            '<button type="button" class="cfg-run-btn cfg-run-safe" onclick="cfgGuideInlineCopyPrompt(this)">📋 현재 문서 지침 복사</button>' +
            '<button type="button" class="cfg-copy" onclick="cfgGuideInlineFillExample(\'' + (isNew ? 'create' : 'patch') + '\')">💡 ' + (isNew ? '생성 예시' : '수정 예시') + ' 넣기</button>' +
            (meta.kind !== 'cloud' ? '<button type="button" class="cfg-copy" onclick="cfgGuideInlineFillExample(\'reorder\')">↕️ 순서 편집 예시 넣기</button>' : '') +
            '<button type="button" class="cfg-copy" onclick="cfgGuideOpen({ kind:\'' + cfgEsc(meta.kind) + '\', docId:' + (meta.docId || 'null') + ', parentId:' + (meta.parentId || 'null') + ', action:\'' + (isNew ? 'create' : 'patch') + '\' })">🖥️ 스튜디오 크게 열기</button>' +
          '</div>' +
          '<textarea id="cfg-guide-inline-input" class="cfg-guide-textarea" style="min-height:110px;" placeholder="지침 결과 JSON (또는 ```json ... ``` 이 포함된 AI 응답 전체) 또는 순수 body JSON을 붙여넣으세요."></textarea>' +
          '<div id="cfg-guide-inline-msg" class="cfg-guide-inline-msg" hidden></div>' +
          '<div class="cfg-guide-inline-foot">' +
            '<button type="button" class="wk-btn wk-primary" onclick="cfgGuideApplyToEditor(false)">📥 이 편집 폼에 반영</button>' +
            '<button type="button" class="wk-btn" onclick="cfgGuideApplyToEditor(true)">🚀 검증 후 바로 서버 저장</button>' +
          '</div>' +
        '</div>' +
      '</details>';
    }

    function cfgGuideInlineCopyPrompt(btn) {
      if (!WIKI || !WIKI.editing) return;
      var meta = WIKI.editing.meta;
      var action = meta.docId ? (meta.kind === 'steps' ? 'reorder' : 'patch') : 'create';
      var text = cfgGuideBuildPrompt({
        action: action,
        kind: meta.kind,
        includeCurrent: true,
        docId: meta.docId,
        parentId: meta.parentId
      }, CFG.data);
      cfgGuideCopyText(text, btn, '📋 현재 문서 지침 복사');
    }

    function cfgGuideInlineFillExample(mode) {
      if (!WIKI || !WIKI.editing) return;
      var meta = WIKI.editing.meta;
      var inp = document.getElementById('cfg-guide-inline-input');
      if (!inp) return;
      var list = cfgGuideExamples(meta.kind, { docId: meta.docId, parentId: meta.parentId }, CFG.data);
      var ex = list.find(function (x) { return x.mode === mode; }) || list[0];
      if (!ex) return;
      inp.value = JSON.stringify(ex.json, null, 2);
      var msg = document.getElementById('cfg-guide-inline-msg');
      if (msg) {
        msg.hidden = false;
        msg.className = 'cfg-guide-inline-msg ok';
        msg.textContent = ex.badge + ' JSON을 채웠습니다. [이 편집 폼에 반영]을 눌러 결과를 확인하세요.';
      }
    }

    async function cfgGuideApplyToEditor(saveNow) {
      if (!WIKI || !WIKI.editing) return;
      var inp = document.getElementById('cfg-guide-inline-input');
      var msgEl = document.getElementById('cfg-guide-inline-msg');
      var showErr = function (txt) {
        if (!msgEl) return;
        msgEl.hidden = false;
        msgEl.className = 'cfg-guide-inline-msg err';
        msgEl.textContent = txt;
      };
      if (!inp || !inp.value.trim()) return showErr('반영할 지침 결과 JSON을 먼저 붙여넣으세요.');

      var ext = cfgGuideExtractJson(inp.value);
      if (!ext.ok) return showErr(ext.error);

      var meta = WIKI.editing.meta;
      var ctx = { kind: meta.kind, docId: meta.docId, parentId: meta.parentId };
      var norm = cfgGuideNormalizeInput(ext.data, ctx);
      if (!norm.ok || !norm.ops.length) return showErr(norm.error || '유효한 작업이 없습니다.');
      if (norm.ops.length > 1) return showErr('여러 작업이 포함된 배치 결과는 [스튜디오 크게 열기]에서 일괄 적용해 주세요.');

      var resolved = cfgGuideResolveOp(norm.ops[0], CFG.data, ctx);
      if (!resolved.ok) return showErr(resolved.errors.join(' / '));
      if (resolved.kind !== meta.kind) {
        return showErr('현재 편집 중인 문서 종류(' + meta.kind + ')와 결과의 kind(' + resolved.kind + ')가 다릅니다.');
      }

      if (saveNow) {
        resolved.docId = meta.docId;
        resolved.parentId = resolved.parentId != null ? resolved.parentId : meta.parentId;
        resolved.baseRev = meta.baseRev;
        await cfgGuideExecuteOps([resolved]);
        return;
      }

      var notice = '<p class="wk-note">지침 결과가 편집 폼에 반영되었습니다 (' + cfgEsc(resolved.summary) + '). 내용을 검토한 뒤 [저장]을 누르세요.</p>';
      wikiOpenEditor(meta, cfgGuideClone(resolved.nextBody), notice);
      var msgInp = document.querySelector('#wk-editor input[name="__message"]');
      if (msgInp && resolved.message) msgInp.value = resolved.message;
    }

    if (typeof module !== 'undefined') {
      module.exports = {
        CFG_GUIDE_SCHEMA: CFG_GUIDE_SCHEMA,
        CFG_GUIDE_DOMAINS: CFG_GUIDE_DOMAINS,
        CFG_GUIDE_PROVIDERS: CFG_GUIDE_PROVIDERS,
        CFG_GUIDE_STATUS: CFG_GUIDE_STATUS,
        CFG_GUIDE_CATS: CFG_GUIDE_CATS,
        cfgGuideExtractJson: cfgGuideExtractJson,
        cfgGuideNormalizeInput: cfgGuideNormalizeInput,
        cfgGuideResolveOp: cfgGuideResolveOp,
        cfgGuideValidateBody: cfgGuideValidateBody,
        cfgGuideBuildPrompt: cfgGuideBuildPrompt,
        cfgGuideExamples: cfgGuideExamples
      };
    }
