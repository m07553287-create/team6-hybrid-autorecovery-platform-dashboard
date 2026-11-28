import test from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const { wkGenAccessKey, wkNormalizeAccessKey, wkFormatAuthor, wkParseAuthor, wkIsRealName, wkResolveEntryName, wkHasValidAccessKey, wkBuildSiteVisitors, wkSummarizeVisitors } = require('../wiki.js');

test('wkGenAccessKey produces 6 unambiguous uppercase alphanumeric characters', () => {
  const key = wkGenAccessKey();
  assert.match(key, /^[A-HJ-NP-Z2-9]{6}$/);
});

test('wkFormatAuthor caps combined name#KEY within 20 chars for wiki check_member limit', () => {
  assert.equal(wkFormatAuthor('다운', 'k7m3p9'), '다운#K7M3P9');
  const longFormatted = wkFormatAuthor('매우긴사용자이름홍길동팀장님', 'K7M3P9');
  assert.ok(longFormatted.length <= 20, `length was ${longFormatted.length}`);
  assert.ok(longFormatted.endsWith('#K7M3P9'));
  // 기존에 #KEY가 붙어 있어도 중복 부착하지 않는다
  assert.equal(wkFormatAuthor('다운#OLDKEY', 'NEWKEY'), '다운#NEWKEY');
});

test('wkParseAuthor extracts accessKey and resolves keybook user mapping', () => {
  const keybook = {
    R4X8N2: { access_key: 'R4X8N2', member: '혜빈' },
    G99999: { access_key: 'G99999', member: '게스트' }
  };

  const p1 = wkParseAuthor('게스트#r4x8n2', '', keybook);
  assert.equal(p1.accessKey, 'R4X8N2');
  assert.equal(p1.matchedUser, '혜빈');
  assert.equal(p1.registered, true);
  assert.equal(p1.hasRealName, true);

  const p2 = wkParseAuthor('게스트#UNREG1', '', keybook);
  assert.equal(p2.accessKey, 'UNREG1');
  assert.equal(p2.matchedUser, '게스트');
  assert.equal(p2.registered, false);
  assert.equal(p2.hasRealName, false);

  const p3 = wkParseAuthor('다운', 'k7m3p9', {});
  assert.equal(p3.accessKey, 'K7M3P9');
  assert.equal(p3.matchedUser, '다운');
  assert.equal(p3.hasRealName, true);

  assert.equal(wkNormalizeAccessKey(' ab-12_cd!@# '), 'AB-12_CD');
});

test('wkIsRealName rejects placeholders and accepts real user names', () => {
  for (const placeholder of ['', '   ', '게스트', 'guest', 'Guest', 'seed', '미설정', null, undefined]) {
    assert.equal(wkIsRealName(placeholder), false);
  }
  assert.equal(wkIsRealName('다운'), true);
  assert.equal(wkIsRealName('홍길동'), true);
});

test('wkResolveEntryName shares real name across settings profile and console user', () => {
  // 아무 이름도 없으면 빈 문자열 → 최초 1회 입력 대상
  assert.equal(wkResolveEntryName({ profileMember: '게스트', termUser: 'guest', lastMember: '', meMember: 'seed' }), '');
  // 콘솔에만 이름이 저장된 경우(설계/설정 profile이 게스트여도 콘솔 이름을 우선 채택)
  assert.equal(wkResolveEntryName({ profileMember: '게스트', termUser: '홍길동', lastMember: '', meMember: '' }), '홍길동');
  // 설계/설정에만 이름이 저장된 경우
  assert.equal(wkResolveEntryName({ profileMember: '혜빈', termUser: '', lastMember: '', meMember: '' }), '혜빈');
  // fw_last에 name#KEY 형식으로 남은 경우
  assert.equal(wkResolveEntryName({ profileMember: '게스트', termUser: '', lastMember: '다운#K7M3P9', meMember: '' }), '다운');
});

test('wkHasValidAccessKey detects previous keyless sessions that must re-login', () => {
  assert.equal(wkHasValidAccessKey(null), false);
  assert.equal(wkHasValidAccessKey({}), false);
  assert.equal(wkHasValidAccessKey({ member: '홍길동', access_key: '' }), false);
  assert.equal(wkHasValidAccessKey({ member: '게스트', access_key: 'K7M3P9' }), false);
  assert.equal(wkHasValidAccessKey({ member: 'guest', access_key: 'K7M3P9' }), false);
  assert.equal(wkHasValidAccessKey({ member: '홍길동', access_key: 'K7M3P9' }), true);
});

test('wkBuildSiteVisitors merges wiki/console/local visits, deduplicates bucket, and summarizes KPIs', () => {
  const keybook = { K7M3P9: { access_key: 'K7M3P9', member: '다운' } };
  const wikiVis = [
    { ts: 1000, auth_state: 'visitor', path: '/', view: 'login', ip: '1.2.3.4', detail: '첫 방문' },
    { ts: 1010, auth_state: 'login_fail', path: '/', view: 'login', ip: '1.2.3.4', detail: '비번 오류' }
  ];
  const consoleVis = [
    { ts: 1020, auth_state: 'authenticated', path: '/term/', view: 'console', access_key: 'K7M3P9', ip: '5.6.7.8', detail: '콘솔 로그인' }
  ];
  // 동일 3초 버킷 내 로컬 중복 방문은 제거되고 새 expired 이벤트는 보존
  const localVis = [
    { ts: 1021, auth_state: 'authenticated', path: '/term/', view: 'console', access_key: 'K7M3P9', ip: '현재 브라우저' },
    { ts: 1030, auth_state: 'expired', path: '/', view: 'login', ip: '현재 브라우저', detail: '키 만료' }
  ];

  const rows = wkBuildSiteVisitors(wikiVis, consoleVis, localVis, keybook);
  assert.equal(rows.length, 4);
  assert.equal(rows[0].authState, 'expired');
  const authRow = rows.find(r => r.authState === 'authenticated');
  assert.equal(authRow.matchedUser, '다운');
  assert.equal(authRow.ip, '5.6.7.8');

  const sum = wkSummarizeVisitors(rows);
  assert.deepEqual(sum, { total: 4, authenticated: 1, anonymous: 1, expiredOrFail: 2, uniqueIps: 3 });
});
