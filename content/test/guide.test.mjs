import test from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const {
  CFG_GUIDE_SCHEMA,
  cfgGuideExtractJson,
  cfgGuideNormalizeInput,
  cfgGuideResolveOp,
  cfgGuideBuildPrompt,
  cfgGuideExamples
} = require('../guide.js');

function makeFixtureData() {
  const cloudDoc = {
    id: 1,
    kind: 'cloud',
    parent_id: null,
    sort: 0,
    rev: 1,
    body: { name: 'OpenStack', provider: 'openstack', desc: '온프레미스 OpenStack' }
  };
  const instDoc = {
    id: 2,
    kind: 'instance',
    parent_id: 1,
    sort: 0,
    rev: 2,
    body: {
      title: 'os-controller (OpenStack Controller)',
      short: 'controller',
      tag: '192.168.120.160',
      status: 'live',
      steps: 'S0 · S2',
      desc: 'OpenStack 컨트롤 플레인',
      specs: [['RAM', '14GB'], ['vCPU', '8']]
    }
  };
  const areaDoc = {
    id: 3,
    kind: 'area',
    parent_id: 2,
    sort: 0,
    rev: 4,
    body: {
      slug: 'svc',
      name: 'OpenStack 핵심 서비스',
      status: 'live',
      domains: ['compute', 'ops'],
      design: ['nova와 neutron 서비스가 정상 구동되어야 합니다.'],
      config: [{ label: '/etc/nova/nova.conf', code: '[DEFAULT]\nmy_ip = 192.168.120.160' }],
      commands: [
        { cat: '조회', label: '하이퍼바이저 목록 확인', code: 'openstack hypervisor list' },
        { cat: '검증', label: '컴퓨트 서비스 목록 확인', code: 'openstack compute service list' }
      ],
      verify: [{ label: '엔진 확인', code: 'openstack token issue', expect: 'id 발급 확인' }],
      trouble: [['nova-compute down', 'RAM 부족', 'systemctl status nova-compute', '서비스 재시작']]
    }
  };
  const stepsDoc = {
    id: 4,
    kind: 'steps',
    parent_id: null,
    sort: 0,
    rev: 3,
    body: {
      items: [
        { no: 'S0', title: '접속 경로 확보', where: '맥 → Controller', why: '기본 접속', gate: 'hostname', instance_id: 2, area_id: 3 },
        { no: 'S1', title: '서비스 확인', where: 'controller', why: '코어 서비스', gate: 'openstack service list', instance_id: 2, area_id: 3 },
        { no: 'S2', title: '네트워크 확인', where: 'controller', why: 'OVN 확인', gate: 'openstack network list', instance_id: 2, area_id: 3 }
      ]
    }
  };
  const pageDoc = {
    id: 5,
    kind: 'page',
    parent_id: null,
    sort: 0,
    rev: 1,
    body: {
      title: '전체 구성과 변수표',
      tag: '실측',
      desc: '팀 참고 문서',
      blocks: [
        { type: 'h', text: '트래픽 경로' },
        { type: 'p', text: 'KT Edge에서 s1을 경유합니다.' }
      ]
    }
  };

  return {
    clouds: [{ id: 1, rev: 1, name: 'OpenStack', provider: 'openstack', desc: '온프레미스 OpenStack' }],
    instances: ['inst-2'],
    pages: {
      'inst-2': {
        kind: 'instance',
        docId: 2,
        rev: 2,
        cloud: 'openstack',
        cloudId: 1,
        cloudName: 'OpenStack',
        title: instDoc.body.title,
        short: 'controller',
        tag: instDoc.body.tag,
        status: 'live',
        desc: instDoc.body.desc,
        steps: instDoc.body.steps,
        specs: instDoc.body.specs,
        areas: [{ ...areaDoc.body, id: 'a3', docId: 3, rev: 4 }]
      },
      'page-5': { kind: 'doc', docId: 5, rev: 1, ...pageDoc.body }
    },
    byId: { 1: cloudDoc, 2: instDoc, 3: areaDoc, 4: stepsDoc, 5: pageDoc },
    stepsDocId: 4,
    stepsRev: 3,
    domains: [
      { id: 'compute', name: '컴퓨트' },
      { id: 'ops', name: '운영' }
    ]
  };
}

test('cfgGuideExtractJson extracts fenced JSON from AI prose response', () => {
  const aiResp = [
    '요청하신 내용을 figteam 규격 JSON으로 정리했습니다.',
    '```json',
    '{"schema": "fig-cfg-v1", "action": "create", "kind": "cloud", "body": {"name": "KT", "provider": "kt"}}',
    '```',
    '위 결과를 붙여넣어 적용하세요.'
  ].join('\n');
  const r = cfgGuideExtractJson(aiResp);
  assert.equal(r.ok, true);
  assert.equal(r.source, 'fence');
  assert.equal(r.data.body.name, 'KT');

  const bad = cfgGuideExtractJson('아무 JSON 없는 텍스트');
  assert.equal(bad.ok, false);
});

test('create area resolves parent by instance name and validates domains and secrets', () => {
  const data = makeFixtureData();
  const op = {
    schema: CFG_GUIDE_SCHEMA,
    action: 'create',
    kind: 'area',
    parent: 'controller',
    body: {
      name: 'Cinder 볼륨',
      domains: ['data'],
      commands: [{ cat: '조회', label: '볼륨 목록', code: 'openstack volume list' }]
    }
  };
  const res = cfgGuideResolveOp(op, data, {});
  assert.equal(res.ok, true);
  assert.equal(res.parentId, 2);
  assert.equal(res.nextBody.name, 'Cinder 볼륨');

  const missingDom = cfgGuideResolveOp({ action: 'create', kind: 'area', parent: 'controller', body: { name: 'Bad', domains: [] } }, data, {});
  assert.equal(missingDom.ok, false);

  const secretHit = cfgGuideResolveOp({
    action: 'create',
    kind: 'area',
    parent: 'controller',
    body: { name: 'SecretTest', domains: ['ops'], config: [{ label: 'wg', code: 'PrivateKey = ' + 'A'.repeat(43) + '=' }] }
  }, data, {});
  assert.equal(secretHit.ok, false);
  assert.ok(secretHit.errors[0].includes('비밀값'));
});

test('patch area supports add, edit by match, remove, and preserves slug', () => {
  const data = makeFixtureData();
  const op = {
    schema: CFG_GUIDE_SCHEMA,
    action: 'patch',
    kind: 'area',
    target: 'controller / OpenStack 핵심 서비스',
    patch: {
      set: { status: 'design' },
      add: {
        design: '이중화 점검 원칙 추가',
        commands: [{ cat: '적용', label: '서비스 재기동', code: 'systemctl restart nova-api' }]
      },
      edit: {
        commands: [{ match: '하이퍼바이저', label: '하이퍼바이저 목록(실측)' }]
      },
      remove: {
        verify: [0]
      }
    }
  };
  const res = cfgGuideResolveOp(op, data, {});
  assert.equal(res.ok, true, res.errors.join('; '));
  assert.equal(res.docId, 3);
  assert.equal(res.nextBody.slug, 'svc');
  assert.equal(res.nextBody.status, 'design');
  assert.equal(res.nextBody.design.length, 2);
  assert.equal(res.nextBody.commands.length, 3);
  assert.equal(res.nextBody.commands[0].label, '하이퍼바이저 목록(실측)');
  assert.equal(res.nextBody.verify.length, 0);
});

test('reorder steps preserves omitted items and renumbers when requested', () => {
  const data = makeFixtureData();
  const res = cfgGuideResolveOp({
    schema: CFG_GUIDE_SCHEMA,
    action: 'reorder',
    kind: 'steps',
    order: ['S2', 'S0'],
    renumber: true
  }, data, {});
  assert.equal(res.ok, true);
  assert.equal(res.docId, 4);
  assert.deepEqual(res.nextBody.items.map(x => x.title), ['네트워크 확인', '접속 경로 확보', '서비스 확인']);
  assert.deepEqual(res.nextBody.items.map(x => x.no), ['S0', 'S1', 'S2']);
});

test('reorder area commands and page blocks work cleanly', () => {
  const data = makeFixtureData();
  const areaRes = cfgGuideResolveOp({
    action: 'reorder',
    kind: 'area',
    doc_id: 3,
    section: 'commands',
    order: [1, 0]
  }, data, {});
  assert.equal(areaRes.ok, true);
  assert.equal(areaRes.nextBody.commands[0].label, '컴퓨트 서비스 목록 확인');

  const pageRes = cfgGuideResolveOp({
    action: 'reorder',
    kind: 'page',
    doc_id: 5,
    move: { from: 1, to: 0 }
  }, data, {});
  assert.equal(pageRes.ok, true);
  assert.equal(pageRes.nextBody.blocks[0].type, 'p');
});

test('raw body fallback wraps un-enveloped body JSON using editor context', () => {
  const data = makeFixtureData();
  const rawBody = { name: '수정된 영역', status: 'live', domains: ['compute'], design: ['새 원칙'] };
  const norm = cfgGuideNormalizeInput(rawBody, { kind: 'area', docId: 3 });
  assert.equal(norm.ok, true);
  assert.equal(norm.inferredRaw, true);
  const res = cfgGuideResolveOp(norm.ops[0], data, { kind: 'area', docId: 3 });
  assert.equal(res.ok, true);
  assert.equal(res.action, 'update');
  assert.equal(res.nextBody.slug, 'svc');
  assert.equal(res.nextBody.name, '수정된 영역');
});

test('all built-in examples across every kind pass cfgGuideResolveOp self-consistency', () => {
  const data = makeFixtureData();
  for (const kind of ['area', 'steps', 'instance', 'page', 'cloud']) {
    const prompt = cfgGuideBuildPrompt({ action: 'create', kind, includeCurrent: true }, data);
    assert.ok(prompt.includes('fig-cfg-v1'));
    const examples = cfgGuideExamples(kind, {}, data);
    assert.equal(examples.length, 3, `expected 3 examples for ${kind}`);
    for (const ex of examples) {
      const res = cfgGuideResolveOp(ex.json, data, {});
      assert.equal(res.ok, true, `${kind}/${ex.mode} failed: ${res.errors.join(', ')}`);
    }
  }
});
