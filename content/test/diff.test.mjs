import test from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
const require = createRequire(import.meta.url);
const { diffLines, bodyToText } = require('../diff.js');

test('identical → all same', () => {
  const r = diffLines(['a', 'b'], ['a', 'b']);
  assert.deepEqual(r.map(x => x.op), ['same', 'same']);
});

test('one line changed → same,del,add,same', () => {
  const r = diffLines(['a', 'b', 'c'], ['a', 'x', 'c']);
  assert.deepEqual(r.map(x => x.op), ['same', 'del', 'add', 'same']);
  assert.equal(r[1].text, 'b'); assert.equal(r[2].text, 'x');
  assert.equal(r[1].a, 1); assert.equal(r[2].b, 1);
});

test('insert at top', () => {
  const r = diffLines(['b'], ['a', 'b']);
  assert.deepEqual(r.map(x => x.op), ['add', 'same']);
});

test('empty sides', () => {
  assert.deepEqual(diffLines([], ['a']).map(x => x.op), ['add']);
  assert.deepEqual(diffLines(['a'], []).map(x => x.op), ['del']);
});

test('bodyToText area order', () => {
  const t = bodyToText('area', { name: 'WG', status: 'live', domains: ['network'], design: ['d1'],
    config: [{ label: 'conf', code: 'x=1\ny=2' }], commands: [{ cat: '조회', label: 'show', code: 'wg show' }],
    verify: [{ label: 'v', code: 'ping', expect: 'ok' }], trouble: [['s', 'v', 'c', 'f']] });
  assert.equal(t[0], '## 기본');
  assert.ok(t.indexOf('## 설계') < t.indexOf('## 설정 / conf'));
  assert.ok(t.includes('y=2') && t.includes('기대: ok') && t.includes('s | v | c | f'));
});

test('2000-line diff under 200ms', () => {
  const a = Array.from({ length: 2000 }, (_, i) => 'line ' + i);
  const b = a.slice(); b[500] = 'changed'; b.splice(1500, 0, 'inserted');
  const t0 = performance.now(); const r = diffLines(a, b);
  assert.ok(performance.now() - t0 < 200);
  assert.equal(r.filter(x => x.op !== 'same').length, 3);
});
