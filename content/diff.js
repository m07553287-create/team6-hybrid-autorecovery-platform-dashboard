    // ===== 위키 판 비교 (content/diff.js) — 브라우저 전역 + node 시험 공용 =====
    var WIKI_NL = String.fromCharCode(10);

    // 줄 단위 비교: 앞뒤 공통 줄을 잘라낸 뒤 가운데만 LCS 표로 계산한다
    function diffLines(a, b) {
      var out = [], pre = 0, suf = 0;
      while (pre < a.length && pre < b.length && a[pre] === b[pre]) pre++;
      while (suf < a.length - pre && suf < b.length - pre && a[a.length - 1 - suf] === b[b.length - 1 - suf]) suf++;
      for (var i = 0; i < pre; i++) out.push({ op: 'same', a: i, b: i, text: a[i] });
      var A = a.slice(pre, a.length - suf), B = b.slice(pre, b.length - suf);
      var n = A.length, m = B.length, w = m + 1;
      var L = new Int32Array((n + 1) * (m + 1));
      for (var x = n - 1; x >= 0; x--) {
        for (var y = m - 1; y >= 0; y--) {
          L[x * w + y] = A[x] === B[y] ? L[(x + 1) * w + y + 1] + 1 : Math.max(L[(x + 1) * w + y], L[x * w + y + 1]);
        }
      }
      var p = 0, q = 0;
      while (p < n || q < m) {
        if (p < n && q < m && A[p] === B[q]) { out.push({ op: 'same', a: pre + p, b: pre + q, text: A[p] }); p++; q++; }
        else if (q < m && (p === n || L[p * w + q + 1] >= L[(p + 1) * w + q])) {
          // 삭제를 먼저 보여 주려고, 같은 길이면 del 을 앞에 둔다
          if (p < n && L[(p + 1) * w + q] === L[p * w + q + 1]) { out.push({ op: 'del', a: pre + p, text: A[p] }); p++; }
          else { out.push({ op: 'add', b: pre + q, text: B[q] }); q++; }
        } else { out.push({ op: 'del', a: pre + p, text: A[p] }); p++; }
      }
      for (var k = 0; k < suf; k++) {
        var ia = a.length - suf + k, ib = b.length - suf + k;
        out.push({ op: 'same', a: ia, b: ib, text: a[ia] });
      }
      return out;
    }

    // 문서 body 를 사람이 읽는 줄로 펼친다 (판 비교의 대상)
    function bodyToText(kind, body) {
      body = body || {};
      var t = [];
      function lines(s) { String(s == null ? '' : s).split(WIKI_NL).forEach(function (l) { t.push(l); }); }
      function list(v) { return Array.isArray(v) ? v : []; }
      if (kind === 'cloud') {
        t.push('이름: ' + (body.name || ''), '종류: ' + (body.provider || ''), '설명:'); lines(body.desc);
      } else if (kind === 'instance') {
        t.push('제목: ' + (body.title || ''), '짧은 이름: ' + (body.short || ''), '태그: ' + (body.tag || ''),
          '상태: ' + (body.status || ''), '진행 순서: ' + (body.steps || ''), '설명:');
        lines(body.desc);
        t.push('사양:'); list(body.specs).forEach(function (s) { t.push('  ' + s[0] + ': ' + s[1]); });
      } else if (kind === 'area') {
        t.push('## 기본', '이름: ' + (body.name || ''), '상태: ' + (body.status || ''), '서비스: ' + list(body.domains).join(', '));
        t.push('## 설계'); list(body.design).forEach(function (d) { t.push('- ' + d); });
        list(body.config).forEach(function (c) { t.push('## 설정 / ' + (c.label || '')); lines(c.code); });
        list(body.commands).forEach(function (c) { t.push('## 명령어 [' + (c.cat || '') + '] ' + (c.label || '')); lines(c.code); });
        list(body.verify).forEach(function (v) { t.push('## 검증 ' + (v.label || '')); lines(v.code); t.push('기대: ' + (v.expect || '')); });
        t.push('## 오류 시 확인'); list(body.trouble).forEach(function (r) { t.push(list(r).join(' | ')); });
      } else if (kind === 'steps') {
        list(body.items).forEach(function (s) {
          t.push('## ' + (s.no || '') + ' ' + (s.title || ''), '위치: ' + (s.where || ''), '이유: ' + (s.why || ''), '통과 조건:');
          lines(s.gate);
        });
      } else {
        t.push('제목: ' + (body.title || ''), '태그: ' + (body.tag || ''), '설명:'); lines(body.desc);
        list(body.blocks).forEach(function (b) {
          if (b.type === 'h') t.push('## ' + b.text);
          else if (b.type === 'p') lines(b.text);
          else if (b.type === 'code') { t.push('### ' + (b.label || '코드')); lines(b.code); }
          else if (b.type === 'table') { t.push(list(b.head).join(' | ')); list(b.rows).forEach(function (r) { t.push(list(r).join(' | ')); }); }
          else t.push('[' + b.type + ']');
        });
      }
      return t;
    }

    if (typeof module !== 'undefined') module.exports = { diffLines: diffLines, bodyToText: bodyToText };
