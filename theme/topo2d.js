(function () {
  'use strict';
  // ===== 민원불패 v2.5.1 — 2D 평면 연결 구성도 (청사진, 순수 SVG) =====
  var host = document.getElementById('t3-host');
  var stageEl = document.querySelector('.dc-main .iso-stage');
  if (!host || !stageEl) return;
  var NS = 'http://www.w3.org/2000/svg';
  var VB0 = { x: 10, y: 46, w: 1600, h: 716 };
  var vb = { x: VB0.x, y: VB0.y, w: VB0.w, h: VB0.h };

  function el(tag, attrs, parent) {
    var e = document.createElementNS(NS, tag);
    for (var k in attrs) e.setAttribute(k, attrs[k]);
    if (parent) parent.appendChild(e);
    return e;
  }
  function txt(parent, x, y, s, cls, anchor) {
    var t = el('text', { x: x, y: y, 'class': cls || '', 'text-anchor': anchor || 'start' }, parent);
    t.textContent = s;
    return t;
  }

  var svg = el('svg', { 'class': 't2-svg', role: 'img', 'aria-label': '민원불패 v2.5.1 2D 연결 구성도', preserveAspectRatio: 'xMidYMid meet' });
  host.appendChild(svg);
  var gZones = el('g', {}, svg), gLinks = el('g', {}, svg), gNodes = el('g', {}, svg), gMarks = el('g', {}, svg), gFx = el('g', {}, svg);
  function applyVB() { svg.setAttribute('viewBox', vb.x + ' ' + vb.y + ' ' + vb.w + ' ' + vb.h); }
  applyVB();

  // ---------- 구성 요소 ----------
  var nodes = {}, links = {}, zones = {};
  function zone(id, x, y, w, h, title, sub) {
    var g = el('g', { 'class': 't2-zone', id: 't2-' + id }, gZones);
    el('rect', { x: x, y: y, width: w, height: h }, g);
    txt(g, x + 12, y + 24, title, 't2-zone-t');
    if (sub) txt(g, x + 12, y + 42, sub, 't2-zone-s');
    zones[id] = g;
    return g;
  }
  function subnet(x, y, w, h, title, tone) {
    var g = el('g', { 'class': 't2-subnet ' + (tone || '') }, gZones);
    el('rect', { x: x, y: y, width: w, height: h }, g);
    txt(g, x + 8, y + 16, title, 't2-subnet-t');
  }
  function node(id, x, y, w, h, title, sub, info, kind) {
    var g = el('g', { 'class': 't2-node' + (kind ? ' ' + kind : ''), id: 't2n-' + id, tabindex: '0' }, gNodes);
    if (kind === 'db') {
      var ry = 9;
      el('path', { 'class': 'body', d: 'M' + x + ',' + (y + ry) + ' L' + x + ',' + (y + h - ry) + ' A' + (w / 2) + ',' + ry + ' 0 0 0 ' + (x + w) + ',' + (y + h - ry) + ' L' + (x + w) + ',' + (y + ry) }, g);
      el('ellipse', { 'class': 'top', cx: x + w / 2, cy: y + ry, rx: w / 2, ry: ry }, g);
      el('path', { 'class': 'ring', d: 'M' + x + ',' + (y + h * 0.45) + ' A' + (w / 2) + ',' + ry + ' 0 0 0 ' + (x + w) + ',' + (y + h * 0.45) }, g);
    } else {
      el('rect', { 'class': 'body', x: x, y: y, width: w, height: h }, g);
    }
    var cy = y + h / 2 + (sub && h >= 52 ? -3 : 5);
    txt(g, x + w / 2, cy, title, 't2-node-t', 'middle');
    if (sub && h >= 52) txt(g, x + w / 2, cy + 18, sub, 't2-node-s', 'middle');
    nodes[id] = { g: g, x: x, y: y, w: w, h: h, info: Object.assign({ title: title, sub: sub }, info || {}) };
    g.addEventListener('click', function (e) { e.stopPropagation(); showCard(id); });
    g.addEventListener('keydown', function (e) { if (e.key === 'Enter') showCard(id); });
    return nodes[id];
  }
  function link(id, pts, kind, label) {
    var d = 'M' + pts.map(function (p) { return p[0] + ',' + p[1]; }).join(' L');
    var g = el('g', { 'class': 't2-link k-' + kind + (/^t[ABC]$/.test(id) ? ' tunnel' : ''), id: 't2l-' + id }, gLinks);
    if (/^t[ABC]$/.test(id)) el('path', { 'class': 'band', d: d }, g);
    var p = el('path', { 'class': 'line', d: d }, g);
    if (label) { var t = txt(g, label[0], label[1], label[2], 't2-tun-t', label[3] || 'start'); t.setAttribute('class', 't2-tun-t k-' + kind); }
    links[id] = { g: g, path: p, len: 0, kind: kind };
    return links[id];
  }

  // 존 · 서브넷
  txt(gZones, 40, 66, '인터넷', 't2-zone-t');
  zone('gh', 20, 560, 190, 185, 'GitHub Pages', '0초 비상 접수');
  zone('kt', 235, 190, 200, 400, 'KT Cloud', '입구 전용 · VM 1대');
  zone('on', 475, 90, 640, 620, '온프레미스 OpenStack', 'Primary · K3s · MySQL');
  zone('aws', 1160, 90, 420, 620, 'AWS', '관제 · DR 대기 · 백업');
  subnet(250, 232, 170, 345, 'Edge-GW VM · k-vm1');
  subnet(490, 124, 610, 84, '외부망 서브넷 · Outbound만', 'warm');
  subnet(490, 224, 405, 384, 'k8s 서브넷 · K3s', 'ok');
  subnet(635, 252, 245, 222, 'app 네임스페이스', 'violet');
  subnet(635, 490, 245, 108, 'data 네임스페이스');
  subnet(910, 224, 190, 384, 'data 서브넷 · DB 원장', 'ok');
  subnet(490, 624, 610, 72, 'ops 서브넷');
  subnet(1175, 124, 390, 84, 'WG 서브넷');
  subnet(1175, 224, 190, 190, '관제 서브넷 · aws-ctl-01', 'warm');
  subnet(1380, 224, 185, 190, '리전 서비스');
  subnet(1175, 430, 390, 180, 'DR 서브넷 · Pilot-Light', 'warm');

  // 터널 · 연결 (먼저 그려서 노드 아래로)
  link('cit_cf', [[115, 136], [115, 290]], 'req');
  link('cf_ng', [[190, 325], [222, 325], [222, 294], [265, 294]], 'req');
  link('cf_gh', [[115, 360], [115, 615]], 'fb');
  link('q_cf', [[265, 384], [230, 384], [230, 345], [190, 345]], 'warn');
  link('ng_q', [[335, 323], [335, 355]], 'req');
  link('q_wg', [[335, 413], [335, 445]], 'req');
  link('tA', [[405, 474], [452, 474], [452, 216], [708, 216], [708, 168], [720, 168]], 'ta', [460, 330, '터널 A']);
  link('tB', [[1190, 152], [880, 152]], 'tb', [1035, 142, '터널 B', 'middle']);
  link('tC', [[335, 503], [335, 752], [1598, 752], [1598, 165], [1330, 165]], 'tc', [900, 742, '터널 C · KT ↔ AWS', 'middle']);
  link('wg_ing', [[745, 190], [745, 240], [562, 240], [562, 270]], 'req');
  link('ing_web', [[620, 304], [650, 304]], 'req');
  link('web_api', [[750, 304], [765, 304]], 'req');
  link('web_api2', [[750, 318], [757, 318], [757, 362], [765, 362]], 'req');
  link('api_db', [[865, 298], [930, 298]], 'data');
  link('api2_db', [[865, 358], [930, 358]], 'data');
  link('api_mq', [[865, 314], [886, 314], [886, 547], [865, 547]], 'req');
  link('mq_worker', [[765, 540], [757, 540], [757, 432], [750, 432]], 'req');
  link('worker_db', [[700, 454], [700, 474], [1005, 474], [1005, 366]], 'data');
  link('mq_na', [[815, 525], [815, 454]], 'req');
  link('db_wg', [[1005, 270], [1005, 180], [880, 180]], 'repl');
  link('aws_rep', [[1300, 190], [1300, 214], [1372, 214], [1372, 448], [1472, 448], [1472, 468]], 'repl');
  link('aws_s3', [[1330, 180], [1472, 180], [1472, 262]], 'backup');
  link('aws_ctl', [[1222, 190], [1222, 262]], 'ctrl');
  link('aws_ec2', [[1190, 176], [1168, 176], [1168, 511], [1190, 511]], 'req');
  link('ec2_rep', [[1340, 511], [1395, 511]], 'data');
  link('ctl_cf', [[1355, 262], [1355, 58], [205, 58], [205, 300], [190, 300]], 'ctrl');
  link('cf_cfd', [[590, 140], [590, 76], [28, 76], [28, 322], [40, 322]], 'cft', [300, 70, 'minwon-tunnel · Cloudflare Tunnel (아웃바운드)', 'middle']);
  link('cfd_wg', [[680, 152], [720, 152]], 'cft');
  link('cfd_argocd', [[505, 182], [482, 182], [482, 690], [700, 690], [700, 680]], 'cft');
  link('ops_cf', [[162, 440], [162, 360]], 'cft');
  link('bypass', [[190, 108], [335, 108], [335, 265]], 'risk', [262, 100, 'origin-kt · DNS 전용', 'middle']);

  txt(gLinks, 122, 214, 'minwon.ktci5.kr', 't2-dns');
  txt(gLinks, 122, 230, '프록시 → 14.63.213.214', 't2-dns s');
  // 노드
  node('citizen', 40, 80, 150, 56, '시민', 'HTTPS 민원 접수', { zone: '인터넷', lines: ['https://minwon.ktci5.kr 접속'] });
  node('cf', 40, 290, 150, 70, 'Cloudflare', 'WAF · 봇/IP 제한', { zone: '인터넷 엣지', lines: ['minwon.ktci5.kr → 14.63.213.214 (프록시 · WAF/DDoS)', 'origin-kt.ktci5.kr → 같은 IP (DNS 전용 · 오리진 노출)', '터널 호스트명 8개 → minwon-tunnel', 'Edge 503 · 오리진 장애 시 Worker가 비상 폼 안내'] });
  node('ops', 125, 440, 75, 44, '운영자', '', { zone: '인터넷', lines: ['관리 화면은 Cloudflare Tunnel로만 접속', 'figteam.ktci5.kr 통합 로그인(SSO)'] });
  node('gh', 40, 615, 150, 70, '비상 접수 폼', 'dr.ktci5.kr', { zone: 'GitHub Pages', subnet: 'subnet-gh-fallback', lines: ['폭주 초과분 · Black Sky 시 0초 노출', '민원 데이터 비상 보관'] });
  node('nginx', 265, 265, 140, 58, 'Nginx TLS·WAF', '10초 마이크로캐시', { zone: 'KT Cloud', subnet: 'subnet-kt-edge', lines: ['TLS 종료 · ModSecurity WAF', 'GET 응답 10초 캐시 (무상태)'] });
  node('queue', 265, 355, 140, 58, '접수 대기열', 'limit_req 버스트', { zone: 'KT Cloud', subnet: 'subnet-kt-edge', lines: ['총량 제한: 허용 속도로만 온프렘 전달', '버스트 내 요청은 순서대로 지연', '초과분 503 + Retry-After → 비상 폼'] });
  node('wgkt', 265, 445, 140, 58, 'WG 종단', '터널 A · C', { zone: 'KT Cloud', subnet: 'subnet-kt-edge', lines: ['WireGuard 터널 A (온프렘) · C (AWS)'] });
  node('gpu', 505, 140, 175, 50, 'cloudflared · 포털', '', { zone: '온프레미스 · GPU 서버 ktci5 (10.10.10.8)', lines: ['minwon-tunnel 커넥터 (아웃바운드만 · 인바운드 0)', 'figteam 통합 포털 :18088', '호스트명 라우팅: figteam · app · argocd · grafana · horizon · openstack', 'aws-ctl → WG 터널 B · kt-edge → WG 터널 A'] });
  node('onwg', 720, 140, 160, 50, 'WireGuard GW', '', { zone: '온프레미스', subnet: 'subnet-onprem-wg', lines: ['공인 IP 없음 · Outbound만', '터널 A · B 종단', '자가 펜싱 Watchdog'] });
  node('ingress', 505, 270, 115, 50, 'ingress-nginx', '', { zone: '온프레미스', subnet: 'subnet-onprem-k8s', lines: ['MetalLB VIP · 경로 라우팅'] });
  node('web1', 650, 282, 100, 44, 'web-1', '', { zone: '온프레미스 · app', subnet: 'subnet-onprem-k8s', lines: ['web Deployment 1/2'] });
  node('web2', 650, 340, 100, 44, 'web-2', '', { zone: '온프레미스 · app', subnet: 'subnet-onprem-k8s', lines: ['web Deployment 2/2'] });
  node('api1', 765, 282, 100, 44, 'intake-api-1', '', { zone: '온프레미스 · app', subnet: 'subnet-onprem-k8s', lines: ['접수 테이블 INSERT 1건 → 202 접수번호', 'livenessProbe /healthz?live=1'] });
  node('api2', 765, 340, 100, 44, 'intake-api-2', '', { zone: '온프레미스 · app', subnet: 'subnet-onprem-k8s', lines: ['HPA replica 2'] });
  node('worker', 650, 410, 100, 44, 'intake-worker', '', { zone: '온프레미스 · app', subnet: 'subnet-onprem-k8s', lines: ['접수 테이블 미처리 건을 순차 처리 (Outbox)', '큐 길이 기반 확장'] });
  node('na', 765, 410, 100, 44, 'notify·audit', '', { zone: '온프레미스 · app', subnet: 'subnet-onprem-k8s', lines: ['알림 · 감사 로그 워커'] });
  node('redis', 650, 525, 100, 44, 'Redis', '', { zone: '온프레미스 · data', subnet: 'subnet-onprem-k8s', lines: ['로컬 캐시 (DR 복제 안 함)'] });
  node('rabbit', 765, 525, 100, 44, 'RabbitMQ', '', { zone: '온프레미스 · data', subnet: 'subnet-onprem-k8s', lines: ['처리 알림만 전달 — 원본은 MySQL 접수 테이블'] });
  node('mysql', 930, 270, 150, 96, 'MySQL Primary', 'semi-sync · GTID', { zone: '온프레미스', subnet: 'subnet-onprem-db', lines: ['minwon · intake(Outbox) · notify · audit', 'AFTER_SYNC: AWS ACK 후 커밋 확정', 'binlog 실시간 스트림 → S3'] }, 'db');
  node('harbor', 505, 640, 120, 40, 'Harbor', '', { zone: '온프레미스 · ops', lines: ['이미지 레지스트리'] });
  node('argocd', 640, 640, 120, 40, 'Argo CD', '', { zone: '온프레미스 · ops', lines: ['GitOps 배포'] });
  node('awswg', 1190, 140, 140, 50, 'AWS WG', '', { zone: 'AWS', lines: ['WireGuard 터널 B · C 종단'] });
  node('ctl', 1190, 262, 160, 62, 'Orchestrator', '3-Signal 판정', { zone: 'AWS', subnet: 'subnet-aws-ctl', lines: ['Prometheus · Grafana · Loki', 'S1/S2 프로브 · semi-sync 강등 경보', 'L2 Ansible · L3 승격 통제'] });
  node('lambda', 1190, 345, 160, 44, 'Dead-man 스위치', '', { zone: 'AWS', lines: ['관제 끊김 → Slack 호출'] });
  node('s3', 1395, 262, 155, 72, 'S3 백업', 'binlog 실시간', { zone: 'AWS', lines: ['binlog 실시간 스트림 + 일일 스냅샷', 'Object Lock · 버전관리 · KMS', '시점 복원(PITR) 소스'] });
  node('ec2', 1190, 480, 150, 62, 'Pilot-Light EC2', 'L3 시 확장', { zone: 'AWS', subnet: 'subnet-aws-dr', lines: ['평소 최소 사양 대기', 'L3 시 확장 · k3s 앱 기동'] });
  node('replica', 1395, 468, 155, 96, 'MySQL Replica', 'semi-sync ACK', { zone: 'AWS', subnet: 'subnet-aws-dr', lines: ['relay log 기록 후 ACK 반환', '사이트 장애 시 RPO 0 (ACK된 커밋 보유)', 'L3 승격: super_read_only = OFF'] }, 'db');

  Object.keys(links).forEach(function (k) { links[k].len = links[k].path.getTotalLength(); });

  // 표시 마크
  var cut = el('g', { 'class': 't2-cut', transform: 'translate(452,330)' }, gMarks);
  el('path', { d: 'M-9,-9 L9,9 M9,-9 L-9,9' }, cut);
  txt(cut, 14, 5, '단절', 't2-cut-t');
  var fence = txt(gMarks, 795, 690, 'FENCED · 쓰기 차단', 't2-fence', 'middle');
  var note = el('g', { 'class': 't2-note' }, gMarks);
  var noteR = el('rect', {}, note), noteT = txt(note, 0, 0, '', '', 'middle');

  // 흐름 패킷 · 캡션
  var halo = el('circle', { r: 12, 'class': 't2-halo' }, gFx);
  var pkt = el('circle', { r: 6.5, 'class': 't2-pkt' }, gFx);
  var bgP = [0, 1, 2].map(function () { return el('circle', { r: 4.5, 'class': 't2-bgpkt' }, gFx); });
  var cap = el('g', { 'class': 't2-cap' }, gFx);
  var capR = el('rect', {}, cap), capN = el('rect', { 'class': 'n' }, cap);
  var capNT = txt(cap, 0, 0, '', 'nt', 'middle'), capT = txt(cap, 0, 0, '');

  // ===== 시나리오별 흐름 =====  [링크 | null, 방향, 설명, 노드]
  var F = {
    normal: { hops: [
      ['cit_cf', 1, '시민 → Cloudflare · HTTPS, WAF'],
      ['cf_ng', 1, 'Cloudflare → KT Edge Nginx · TLS 종료'],
      ['ng_q', 1, 'Nginx → 접수 대기열 (평시엔 즉시 통과)'],
      ['q_wg', 1, '대기열 → WG 종단'],
      ['tA', 1, '터널 A → 온프렘 WireGuard GW'],
      ['wg_ing', 1, 'WG GW → ingress-nginx (MetalLB VIP)'],
      ['ing_web', 1, 'ingress → web-1'],
      ['web_api', 1, 'web-1 → intake-api-1'],
      ['api_db', 1, 'intake-api → MySQL · 접수 테이블 INSERT'],
      ['db_wg', 1, 'binlog → WG GW (semi-sync 전송)'],
      ['tB', -1, '터널 B → AWS'],
      ['aws_rep', 1, 'AWS Replica · relay log 기록'],
      ['tB', 1, 'Replica ACK → 커밋 확정 (AFTER_SYNC · 무손실)'],
      [null, 0, '202 Accepted · 접수번호 즉시 응답', 'api1'],
      ['api_mq', 1, 'intake-api → RabbitMQ · 처리 알림'],
      ['mq_worker', 1, 'RabbitMQ → intake-worker'],
      ['worker_db', 1, 'worker → MySQL · 처리 상태 커밋'],
      ['mq_na', 1, 'RabbitMQ → notify·audit']
    ], bg: [['db_wg', 1], ['tB', -1], ['aws_s3', 1]], bgCap: 'binlog 실시간 스트림 → 터널 B → S3 (즉시 백업)' },
    l1: { hops: [
      [null, 0, 'intake-api-1 OOM · livenessProbe 실패', 'api1'],
      [null, 0, 'kubelet이 컨테이너 즉시 재시작 (초 단위)', 'api1'],
      ['tA', 1, '요청 계속 유입 · 터널 A 정상'],
      ['wg_ing', 1, 'WG GW → ingress'],
      ['ing_web', 1, 'ingress → web-1'],
      ['web_api2', 1, 'web → intake-api-2 (정상 replica가 흡수)'],
      ['api2_db', 1, 'api-2 → MySQL · 접수 INSERT (semi-sync)'],
      [null, 0, '서비스 무중단 · 접수 데이터 손실 없음', 'mysql']
    ], bg: [['db_wg', 1], ['tB', -1], ['aws_rep', 1]], bgCap: 'semi-sync 복제 → AWS Replica (상시)' },
    l2: { hops: [
      ['ctl_cf', 1, 'S1 공인 프로브 1분 이상 무응답'],
      [null, 0, 'Orchestrator 판정: S1 실패 · S2 정상 → L2', 'ctl'],
      ['aws_ctl', -1, 'Orchestrator → AWS WG · Ansible 실행'],
      ['tB', 1, '터널 B → 온프렘 WG GW · restart_services.yml'],
      ['wg_ing', 1, '서비스 순차 재기동 (Nginx → 앱 → MySQL → WG)'],
      [null, 0, 'MySQL은 재기동 전 semi-sync 상태 확인 · 데이터 우선', 'mysql'],
      [null, 0, '헬스체크 통과 → NORMAL 복귀 (≤ 3분)', 'web1']
    ], bg: [] },
    path: { hops: [
      ['cit_cf', 1, '시민 → Cloudflare'],
      ['cf_ng', 1, 'Cloudflare → KT Edge'],
      ['ng_q', 1, 'Nginx → 접수 대기열'],
      [null, 0, '터널 A 단절 · S1·S3 실패, S2 정상 → 온프렘 생존', 'wgkt'],
      ['tC', 1, '터널 C 우회 → AWS WG'],
      ['tB', 1, '터널 B → 온프렘 진입 (DB 승격 금지 · Split-Brain 방지)'],
      ['wg_ing', 1, 'WG GW → ingress'],
      ['ing_web', 1, 'ingress → web'],
      ['web_api', 1, 'web → intake-api'],
      ['api_db', 1, 'intake-api → MySQL Primary (유일한 쓰기 지점)']
    ], bg: [['db_wg', 1], ['tB', -1], ['aws_rep', 1]], bgCap: 'semi-sync 복제 유지 (터널 B 정상)' },
    l3: { hops: [
      [null, 0, '3-Signal: S1 ∧ S2 ∧ S3 연속 실패 → 사이트 장애 확정', 'ctl'],
      [null, 0, '온프렘 자가 펜싱 · Primary 쓰기 차단', 'onwg'],
      [null, 0, 'Replica가 마지막 ACK GTID까지 적용 확인 (RPO 0)', 'replica'],
      ['aws_s3', 1, 'S3 binlog와 대조 · 누락 0 검증'],
      [null, 0, 'Replica 승격 · super_read_only = OFF', 'replica'],
      [null, 0, 'Pilot-Light EC2 확장 · 앱 기동', 'ec2'],
      ['cit_cf', 1, '시민 → Cloudflare'],
      ['cf_ng', 1, 'Cloudflare → KT Edge (upstream 전환)'],
      ['tC', 1, '터널 C → AWS WG'],
      ['aws_ec2', 1, 'AWS WG → Pilot-Light EC2'],
      ['ec2_rep', 1, 'EC2 앱 → 승격된 MySQL에 쓰기']
    ], bg: [] },
    l4: { hops: [
      [null, 0, '온프렘 복구 · 온프렘 DB를 AWS의 Replica로 재구성', 'mysql'],
      ['aws_rep', -1, 'AWS MySQL → AWS WG (역방향 GTID)'],
      ['tB', 1, '터널 B → 온프렘 WG GW'],
      ['db_wg', -1, 'WG GW → 온프렘 MySQL · 누적 데이터 따라잡기'],
      [null, 0, '지연 0 · 체크섬 일치 → AWS 쓰기 차단, 온프렘 승격', 'mysql'],
      [null, 0, 'semi-sync 방향 원복 (온프렘 → AWS ACK)', 'replica'],
      ['tA', 1, 'Edge upstream 터널 A 복귀'],
      ['wg_ing', 1, 'WG GW → ingress'],
      ['web_api', 1, 'web → intake-api'],
      ['api_db', 1, 'intake-api → MySQL Primary (원복 완료)']
    ], bg: [] },
    bs: { hops: [
      ['cit_cf', 1, '시민 → Cloudflare'],
      ['cf_ng', 1, 'Origin 502/504 연속 (온프렘 · AWS 전면 두절)'],
      [null, 0, 'Cloudflare Worker가 오류를 가로챔', 'cf'],
      ['cf_gh', 1, 'GitHub Pages 비상 접수 폼 0초 노출 · 민원 비상 보관'],
      [null, 0, '복구 후 비상 보관분을 접수 테이블로 일괄 이관', 'gh']
    ], bg: [] },
    surge: { hops: [
      ['cit_cf', 1, '민원 폭주 · 초당 요청 급증'],
      [null, 0, 'Cloudflare: 봇 차단 · IP 단위 제한', 'cf'],
      ['cf_ng', 1, '통과분 → KT Edge Nginx'],
      ['ng_q', 1, 'Nginx → 접수 대기열'],
      [null, 0, '버스트 범위 내 요청은 순서대로 지연 (DB 보호 속도)', 'queue'],
      ['q_wg', 1, '허용 속도로만 WG 종단 전달'],
      ['tA', 1, '터널 A → 온프렘'],
      ['wg_ing', 1, 'WG GW → ingress'],
      ['web_api', 1, 'web → intake-api'],
      ['api_db', 1, '접수 테이블 INSERT 1건 (semi-sync ACK 후 커밋)'],
      [null, 0, '202 접수번호 즉시 응답 · 처리는 비동기', 'api1'],
      ['api_mq', 1, 'RabbitMQ에 처리 알림'],
      ['mq_worker', 1, 'intake-worker가 DB 한도 안에서 순차 처리'],
      ['worker_db', 1, '처리 상태 커밋 · 큐 길이 기반 워커 확장'],
      [null, 0, '버스트 초과분 → 503 + Retry-After', 'queue'],
      ['q_cf', 1, 'Edge 503 → Cloudflare Worker'],
      ['cf_gh', 1, '대기 안내 · 비상 접수 폼 (민원 유실 0)'],
      ['bypass', 1, '⚠ origin-kt(DNS 전용) 직접 요청은 Cloudflare 제한 우회 → Edge는 Cloudflare IP만 허용해야 함']
    ], bg: [['db_wg', 1], ['tB', -1], ['aws_s3', 1]], bgCap: 'binlog 실시간 스트림 → S3 (폭주 중에도 즉시 백업)' },
    mgmt: { hops: [
      ['ops_cf', 1, '운영자 → Cloudflare · figteam.ktci5.kr 로그인'],
      [null, 0, 'Cloudflare: 터널 호스트명 → minwon-tunnel', 'cf'],
      ['cf_cfd', -1, 'minwon-tunnel → 온프렘 cloudflared (아웃바운드 연결 · 인바운드 0)'],
      [null, 0, 'cloudflared가 호스트명별 내부 서비스로 전달 · 포털 :18088', 'gpu'],
      ['cfd_argocd', 1, 'argocd.ktci5.kr → Argo CD (k8s-cp1:30800)'],
      ['cfd_wg', 1, 'aws-ctl · kt-edge 호스트명 → WireGuard GW'],
      ['tB', -1, '터널 B → AWS (aws-ctl.ktci5.kr)'],
      ['aws_ctl', 1, 'AWS WG → Orchestrator · Prometheus/Grafana'],
      ['tA', -1, '터널 A → KT Edge (kt-edge.ktci5.kr)'],
      [null, 0, '관리 경로는 대민 경로(minwon.ktci5.kr)와 분리 · 공인 포트 노출 없음', 'gpu']
    ], bg: [] }
  };
  var STATE = {
    normal: { tun: { tA: 'on', tB: 'on', tC: 'idle' } },
    l1: { tun: { tA: 'on', tB: 'on', tC: 'idle' }, warn: ['api1'] },
    l2: { tun: { tA: 'on', tB: 'on', tC: 'idle' }, warn: ['ctl', 'onwg'], fail: ['web1', 'web2', 'api1', 'api2'] },
    path: { tun: { tA: 'fail', tB: 'on', tC: 'on' }, cut: true, note: ['replica', 'DB 승격 금지'] },
    l3: { tun: { tA: 'fail', tB: 'fail', tC: 'on' }, fence: true, ok: ['replica', 'ec2'], warn: ['ctl'], note: ['replica', 'Primary 승격 · RPO 0'] },
    l4: { tun: { tA: 'on', tB: 'on', tC: 'idle' }, ok: ['mysql'], note: ['mysql', 'Primary 복귀'] },
    bs: { tun: { tA: 'fail', tB: 'fail', tC: 'fail' }, dark: true, ok: ['gh', 'cf'] },
    surge: { tun: { tA: 'on', tB: 'on', tC: 'idle' }, warn: ['queue', 'rabbit', 'worker'], ok: ['mysql'], note: ['mysql', 'DB 우선 · 커밋 보장'] },
    mgmt: { tun: { tA: 'on', tB: 'on', tC: 'idle' }, ok: ['gpu', 'ops'] }
  };
  var ON_IDS = ['gpu', 'onwg', 'ingress', 'web1', 'web2', 'api1', 'api2', 'worker', 'na', 'redis', 'rabbit', 'mysql', 'harbor', 'argocd'];
  var stage = 'normal', hopIdx = 0, hopT = 0, playing = true, pauseT = 0;
  var HOP = 1.15, NODE_T = 1.4, END = 1.0;
  var flowList = document.getElementById('dc-flow');

  function cls(e, c, on) { if (on) e.classList.add(c); else e.classList.remove(c); }
  function applyState() {
    var st = STATE[stage] || STATE.normal;
    Object.keys(nodes).forEach(function (k) { ['st-warn', 'st-fail', 'st-ok', 'st-dim', 'pulse'].forEach(function (c) { nodes[k].g.classList.remove(c); }); });
    Object.keys(zones).forEach(function (k) { zones[k].classList.remove('fenced', 'dim', 'lit'); });
    nodes.gh.g.classList.add('st-dim'); zones.gh.classList.add('dim');
    if (st.fence) { ON_IDS.forEach(function (k) { nodes[k].g.classList.add('st-dim'); }); zones.on.classList.add('fenced'); }
    if (st.dark) {
      Object.keys(nodes).forEach(function (k) { if (['citizen', 'cf', 'gh'].indexOf(k) < 0) nodes[k].g.classList.add('st-dim'); });
      ['kt', 'on', 'aws'].forEach(function (k) { zones[k].classList.add('dim'); });
    }
    if (stage === 'surge' || st.dark) { zones.gh.classList.remove('dim'); nodes.gh.g.classList.remove('st-dim'); }
    (st.warn || []).forEach(function (k) { nodes[k].g.classList.add('st-warn'); });
    (st.fail || []).forEach(function (k) { nodes[k].g.classList.add('st-fail'); });
    (st.ok || []).forEach(function (k) { nodes[k].g.classList.remove('st-dim'); nodes[k].g.classList.add('st-ok'); });
    Object.keys(st.tun).forEach(function (k) {
      var g = links[k].g; ['tun-on', 'tun-fail', 'tun-idle'].forEach(function (c) { g.classList.remove(c); }); g.classList.add('tun-' + st.tun[k]);
    });
    cls(cut, 'show', !!st.cut);
    cls(fence, 'show', !!st.fence);
    cls(note, 'show', !!st.note);
    if (st.note) {
      var n = nodes[st.note[0]];
      noteT.textContent = st.note[1];
      var cx = n.x + n.w / 2, cy = n.y + n.h + 22;
      noteT.setAttribute('x', cx); noteT.setAttribute('y', cy + 4);
      var bb = noteT.getBBox();
      noteR.setAttribute('x', bb.x - 8); noteR.setAttribute('y', bb.y - 4); noteR.setAttribute('width', bb.width + 16); noteR.setAttribute('height', bb.height + 8);
    }
  }

  function renderFlowList() {
    if (!flowList) return;
    flowList.textContent = '';
    var f = F[stage];
    f.hops.forEach(function (h, i) {
      var li = document.createElement('li'); li.dataset.i = i;
      var n = document.createElement('i'); n.textContent = String(i + 1);
      var t = document.createElement('span'); t.textContent = h[2];
      li.appendChild(n); li.appendChild(t);
      li.addEventListener('click', function () { hopIdx = i; hopT = 0; pauseT = 0; playing = false; syncPlay(); markFlow(); });
      flowList.appendChild(li);
    });
    if (f.bgCap) {
      var li = document.createElement('li'); li.className = 'bg';
      var n = document.createElement('i'); n.textContent = '∞';
      var t = document.createElement('span'); t.textContent = f.bgCap;
      li.appendChild(n); li.appendChild(t); flowList.appendChild(li);
    }
  }
  function markFlow() {
    if (!flowList) return;
    var items = flowList.querySelectorAll('li[data-i]');
    for (var j = 0; j < items.length; j++) {
      var i = +items[j].dataset.i;
      cls(items[j], 'done', i < hopIdx); cls(items[j], 'active', i === hopIdx);
    }
    var a = flowList.querySelector('li.active'), p = flowList.parentElement;
    if (a && p) { if (a.offsetTop < p.scrollTop || a.offsetTop > p.scrollTop + p.clientHeight - 40) p.scrollTop = a.offsetTop - 40; }
  }

  function placeCap(text, n, x, y) {
    capNT.textContent = String(n);
    capT.textContent = text;
    capT.setAttribute('x', 0); capT.setAttribute('y', 0);
    var tb = capT.getBBox();
    var w = tb.width + 44, h = 30;
    var cx = Math.max(vb.x + 6, Math.min(x - w / 2, vb.x + vb.w - w - 6));
    var sc = toSvg(0, 0).s, barH = (bar && bar.offsetHeight ? bar.offsetHeight + 18 : 0) * sc;
    var cy = Math.max(vb.y + 6, Math.min(y - h - 14, vb.y + vb.h - h - 6 - barH));
    capR.setAttribute('x', cx); capR.setAttribute('y', cy); capR.setAttribute('width', w); capR.setAttribute('height', h);
    capN.setAttribute('x', cx); capN.setAttribute('y', cy); capN.setAttribute('width', 28); capN.setAttribute('height', h);
    capNT.setAttribute('x', cx + 14); capNT.setAttribute('y', cy + 20);
    capT.setAttribute('x', cx + 36); capT.setAttribute('y', cy + 20);
    cap.classList.add('show');
  }

  function frame(dt) {
    var f = F[stage], hops = f.hops;
    Object.keys(links).forEach(function (k) { links[k].g.classList.remove('active', 'done', 'used', 'bg'); });
    hops.forEach(function (h, i) { if (h[0]) { links[h[0]].g.classList.add('used'); if (i < hopIdx) links[h[0]].g.classList.add('done'); } });
    (f.bg || []).forEach(function (b) { links[b[0]].g.classList.add('bg'); });
    Object.keys(nodes).forEach(function (k) { nodes[k].g.classList.remove('pulse'); });

    if (pauseT > 0) {
      pauseT -= dt;
      pkt.style.display = halo.style.display = 'none'; cap.classList.remove('show');
      if (pauseT <= 0) { hopIdx = 0; hopT = 0; markFlow(); }
    } else {
      var h = hops[hopIdx];
      if (playing) hopT += dt / (h[0] ? HOP : NODE_T);
      var t = Math.min(hopT, 1);
      if (h[0]) {
        var L = links[h[0]];
        L.g.classList.add('active');
        var u = h[1] < 0 ? 1 - t : t;
        var p = L.path.getPointAtLength(u * L.len);
        pkt.setAttribute('cx', p.x); pkt.setAttribute('cy', p.y);
        halo.setAttribute('cx', p.x); halo.setAttribute('cy', p.y);
        pkt.setAttribute('class', 't2-pkt k-' + (L.g.classList.contains('tun-fail') ? 'fail' : L.kind));
        halo.setAttribute('class', 't2-halo k-' + (L.g.classList.contains('tun-fail') ? 'fail' : L.kind));
        pkt.style.display = halo.style.display = '';
        var m = L.path.getPointAtLength(L.len / 2);
        placeCap(h[2], hopIdx + 1, m.x, m.y);
      } else {
        pkt.style.display = halo.style.display = 'none';
        var n = nodes[h[3]];
        if (n) { n.g.classList.add('pulse'); placeCap(h[2], hopIdx + 1, n.x + n.w / 2, n.y); }
      }
      if (playing && hopT >= 1) {
        hopIdx++; hopT = 0;
        if (hopIdx >= hops.length) { hopIdx = hops.length - 1; pauseT = END; }
        markFlow();
      }
    }
    var bg = f.bg || [];
    if (bg.length) {
      var total = bg.reduce(function (s, b) { return s + links[b[0]].len; }, 0);
      var now = performance.now() / 1000;
      bgP.forEach(function (c, k) {
        var d = (now * 140 + k * total / 3) % total;
        for (var j = 0; j < bg.length; j++) {
          var L2 = links[bg[j][0]];
          if (d <= L2.len) { var u2 = d / L2.len; var q = L2.path.getPointAtLength((bg[j][1] < 0 ? 1 - u2 : u2) * L2.len); c.setAttribute('cx', q.x); c.setAttribute('cy', q.y); break; }
          d -= L2.len;
        }
        c.style.display = '';
      });
    } else bgP.forEach(function (c) { c.style.display = 'none'; });
  }

  // ---------- 확대 · 이동 ----------
  function toSvg(cx, cy) {
    var r = svg.getBoundingClientRect();
    var s = Math.max(vb.w / r.width, vb.h / r.height);
    var ox = (r.width - vb.w / s) / 2, oy = (r.height - vb.h / s) / 2;
    return { x: vb.x + (cx - r.left - ox) * s, y: vb.y + (cy - r.top - oy) * s, s: s };
  }
  function zoomAt(f, cx, cy) {
    var nw = Math.min(VB0.w * 1.4, Math.max(VB0.w / 6, vb.w / f));
    var k = nw / vb.w;
    var p = (cx == null) ? { x: vb.x + vb.w / 2, y: vb.y + vb.h / 2 } : toSvg(cx, cy);
    vb.x = p.x - (p.x - vb.x) * k; vb.y = p.y - (p.y - vb.y) * k; vb.w *= k; vb.h *= k;
    applyVB();
  }
  svg.addEventListener('wheel', function (e) { e.preventDefault(); zoomAt(e.deltaY < 0 ? 1.15 : 1 / 1.15, e.clientX, e.clientY); }, { passive: false });
  var drag = null;
  svg.addEventListener('pointerdown', function (e) { drag = { x: e.clientX, y: e.clientY, vx: vb.x, vy: vb.y, moved: false }; svg.setPointerCapture(e.pointerId); });
  svg.addEventListener('pointermove', function (e) {
    if (!drag) return;
    var dx = e.clientX - drag.x, dy = e.clientY - drag.y;
    if (Math.abs(dx) + Math.abs(dy) > 4) drag.moved = true;
    if (!drag.moved) return;
    var s = toSvg(0, 0).s;
    vb.x = drag.vx - dx * s; vb.y = drag.vy - dy * s; applyVB();
    svg.classList.add('grabbing');
  });
  svg.addEventListener('pointerup', function (e) {
    var moved = drag && drag.moved; drag = null; svg.classList.remove('grabbing');
    if (!moved && e.target === svg) card.hidden = true;
  });
  // 드래그 직후 클릭이 노드 카드로 번지지 않게
  svg.addEventListener('click', function (e) { if (svg.classList.contains('grabbing')) e.stopPropagation(); }, true);
  function fitView() { vb = { x: VB0.x, y: VB0.y, w: VB0.w, h: VB0.h }; applyVB(); }

  // ---------- 툴바 ----------
  var bar = document.createElement('div'); bar.className = 't3-bar';
  var B = [['zin', '+', '확대'], ['zout', '−', '축소'], ['fit', '맞춤', '전체 보기'], ['sep'],
    ['prev', '◀ 이전', '이전 단계'], ['play', '일시정지', '흐름 재생 / 일시정지'], ['next', '다음 ▶', '다음 단계'], ['sep'],
    ['detail', '상세 구성', '서브넷 · 파드 · DB 상세 펼치기']];
  var btn = {};
  B.forEach(function (b) {
    if (b[0] === 'sep') { var s = document.createElement('span'); s.className = 'sep'; bar.appendChild(s); return; }
    var x = document.createElement('button'); x.type = 'button'; x.textContent = b[1]; x.title = b[2]; x.setAttribute('aria-label', b[2]); x.dataset.k = b[0];
    bar.appendChild(x); btn[b[0]] = x;
  });
  host.appendChild(bar);
  function syncPlay() { btn.play.textContent = playing ? '일시정지' : '재생'; cls(btn.play, 'on', !playing); }
  function syncDetail() { var c = document.getElementById('dr-console'); cls(btn.detail, 'on', !!(c && c.classList.contains('show-detail'))); }
  bar.addEventListener('click', function (e) {
    var k = e.target.dataset && e.target.dataset.k; if (!k) return;
    if (k === 'zin') zoomAt(1.25);
    if (k === 'zout') zoomAt(0.8);
    if (k === 'fit') fitView();
    if (k === 'play') { playing = !playing; syncPlay(); }
    if (k === 'prev') { playing = false; pauseT = 0; hopIdx = Math.max(0, hopIdx - 1); hopT = 0; markFlow(); syncPlay(); }
    if (k === 'next') { playing = false; pauseT = 0; hopIdx = Math.min(F[stage].hops.length - 1, hopIdx + 1); hopT = 0; markFlow(); syncPlay(); }
    if (k === 'detail') { if (window.toggleDrDetail) window.toggleDrDetail(); syncDetail(); }
  });

  // ---------- 장비 정보 카드 ----------
  var card = document.createElement('div'); card.className = 't3-card'; card.hidden = true; host.appendChild(card);
  function showCard(id) {
    var n = nodes[id]; if (!n) return;
    var i = n.info;
    card.textContent = '';
    var h = document.createElement('h4'); h.textContent = i.title; card.appendChild(h);
    var z = document.createElement('p'); z.className = 'z'; z.textContent = [i.zone, i.sub].filter(Boolean).join(' · '); card.appendChild(z);
    var ul = document.createElement('ul');
    (i.lines || []).forEach(function (t) { var li = document.createElement('li'); li.textContent = t; ul.appendChild(li); });
    card.appendChild(ul);
    var row = document.createElement('div'); row.className = 'row';
    if (i.subnet && document.getElementById(i.subnet)) {
      var b = document.createElement('button'); b.type = 'button'; b.textContent = '상세 구성에서 보기';
      b.addEventListener('click', function () { if (window.showDrDetail) window.showDrDetail(i.subnet); syncDetail(); });
      row.appendChild(b);
    }
    var x = document.createElement('button'); x.type = 'button'; x.textContent = '닫기';
    x.addEventListener('click', function () { card.hidden = true; });
    row.appendChild(x); card.appendChild(row);
    card.hidden = false;
  }

  // ---------- 접수 폭주(8) 시나리오: 기존 상태 머신 확장 ----------
  var origSet = window.setV3Stage;
  if (typeof origSet === 'function') {
    // 원본 상태 머신은 단계마다 상세 배지를 초기화하지 않아 이전 단계 문구가 남음 → 평시 값으로 먼저 초기화
    var RESET = [
      ['kt-edge-route', '터널 A 발송 중', null, 'tunnel-badge tunnel-a'], ['kt-edge-dot', null, null, 'dot green'],
      ['txt-s3-status', '정상 통과 🟢', '#8FE0B4'], ['badge-onprem-mode', 'PRIMARY RW 🟢', null, null, '#5FD39A'],
      ['txt-fencing', '자가 펜싱 감시 중: 정상 (쓰기 허용)'], ['badge-db-rw', 'Read / Write', null, null, '#5FD39A'],
      ['badge-aws-mode', 'PILOT-LIGHT RO 🟡', null, null, '#F4C95D'], ['badge-aws-db-ro', 'super_read_only = ON', null, null, '#F4C95D'],
      ['txt-orch-state', 'NORMAL (온프렘 가동)', '#5FD39A']
    ];
    function resetDetail() {
      RESET.forEach(function (r) {
        var e = document.getElementById(r[0]); if (!e) return;
        if (r[1] != null) e.innerText = r[1];
        if (r[2]) e.style.color = r[2];
        if (r[3]) { e.className = r[3]; e.style.background = ''; e.style.color = ''; }
        if (r[4]) e.style.background = r[4];
      });
    }
    window.setV3Stage = function (s) {
      resetDetail();
      origSet(s);
      [['btn-v3-surge', 'surge', '#C8962E'], ['btn-v3-mgmt', 'mgmt', '#C9874F']].forEach(function (b) {
        var e = document.getElementById(b[0]); if (!e) return;
        var on = s === b[1];
        e.style.background = on ? b[2] : 'transparent'; e.style.color = on ? '#fff' : '#B4C6D8'; e.style.fontWeight = on ? '700' : '500';
      });
      function set(id, v, color) { var e = document.getElementById(id); if (e) { e.innerText = v; if (color) e.style.color = color; } }
      if (s === 'mgmt') {
        set('v3-stage-title', '⚪ 9. 관리 접속: 운영자 → Cloudflare → minwon-tunnel → 온프렘 cloudflared → 내부 서비스 · WG로 AWS/KT');
        set('v3-stage-desc', '관리 화면 8개 호스트명은 Cloudflare Tunnel로만 들어옵니다. 온프렘은 인바운드 포트 0, aws-ctl · kt-edge는 WireGuard 터널을 경유합니다.');
        var mb = document.getElementById('v3-status-badge');
        if (mb) { mb.className = 'kt-vm-badge state-running'; mb.innerHTML = '<span class="dot green"></span>MGMT · TUNNEL'; }
        set('v3-prop-sm', 'NORMAL', '#5FD39A');
        set('v3-prop-signal', 'S1:정상 · S2:정상 · S3:정상');
        set('v3-prop-rto', '대민 경로 영향 없음');
        set('v3-prop-tunnel', 'minwon-tunnel + 터널 A·B');
        var ms = document.getElementById('v3-sop-text');
        if (ms) ms.innerHTML = '<b>[Cloudflare DNS 기준 접속 경로]</b><br>' +
          '• <b>대민</b>: <code>minwon.ktci5.kr</code> A 14.63.213.214 (프록시) → KT Edge → 터널 A → 온프렘.<br>' +
          '• <b>관리</b>: <code>figteam · app · argocd · grafana · horizon · openstack · aws-ctl · kt-edge</code>.ktci5.kr → <b>minwon-tunnel</b> → 온프렘 cloudflared (GPU 서버) → 내부 서비스. aws-ctl은 터널 B, kt-edge는 터널 A 경유.<br>' +
          '• <b>⚠ 위험</b>: <code>origin-kt.ktci5.kr</code> A 14.63.213.214 <b>DNS 전용</b> — 오리진 IP가 공개되어 Cloudflare WAF·제한을 우회한 직접 접속이 가능. KT Edge 443을 Cloudflare IP 대역만 허용하거나 레코드 정리 필요.';
        if (window.addDrLog) window.addDrLog('[v2.5.1-FLOW] 9단계: 관리 접속 — Cloudflare Tunnel(minwon-tunnel) → 온프렘 cloudflared → WG 경유', 'success');
        return;
      }
      if (s !== 'surge') return;
      set('v3-stage-title', '🟤 8. 접수 폭주: Edge 대기열 → 접수 테이블(202 접수번호) → 워커 순차 처리 · 초과분 비상 폼');
      set('v3-stage-desc', 'v2.5.1: DB가 최우선입니다. Edge는 허용 속도로만 전달하고, 접수는 MySQL에 먼저 커밋(semi-sync)한 뒤 처리는 비동기로 진행합니다.');
      var b = document.getElementById('v3-status-badge');
      if (b) { b.className = 'kt-vm-badge state-transition'; b.innerHTML = '<span class="dot yellow"></span>SURGE · QUEUEING'; }
      set('v3-prop-sm', 'NORMAL (Surge 제어)', '#F4C95D');
      set('v3-prop-signal', 'S1:지연 · S2:정상 · S3:정상');
      set('v3-prop-rto', '접수 RPO 0 · 처리 지연 허용');
      set('v3-prop-tunnel', '터널 A 총량 제한 · B 복제/백업');
      set('kt-edge-route', '터널 A 총량 제한 발송');
      set('txt-orch-state', 'NORMAL (폭주 감시 · semi-sync 정상)', '#F4C95D');
      set('badge-aws-db-ro', 'semi-sync ACK 중');
      var sop = document.getElementById('v3-sop-text');
      if (sop) sop.innerHTML = '<b>[접수 폭주 대응 — DB 최우선]</b><br>' +
        '• <b>① Cloudflare</b>: 봇 차단 · IP 단위 제한으로 비정상 트래픽 선차단.<br>' +
        '• <b>② KT Edge 대기열</b>: <code>limit_req</code> 총량 제한, 버스트 범위는 순서대로 지연 전달, 초과분은 503 + Retry-After.<br>' +
        '• <b>③ 접수 테이블</b>: intake-api가 INSERT 1건 후 202 접수번호 응답. semi-sync ACK 후 커밋이라 접수된 민원은 AWS에도 존재.<br>' +
        '• <b>④ 워커</b>: RabbitMQ 알림으로 intake-worker가 DB 한도 안에서 순차 처리 (큐 길이 기반 확장).<br>' +
        '• <b>⑤ 초과분</b>: Cloudflare Worker가 대기 안내 · GitHub Pages 비상 접수 폼 제공 → 복구 후 접수 테이블로 이관.<br>' +
        '• <b>백업</b>: binlog 실시간 스트림으로 S3에 즉시 보관.';
      if (window.addDrLog) window.addDrLog('[v2.5.1-FLOW] 8단계: 접수 폭주 — Edge 대기열 · 접수 테이블 우선 커밋 · 워커 순차 처리 활성화', 'warn');
    };
  }

  // ---------- 루프 · 공개 API ----------
  var last = performance.now();
  function loop(now) {
    requestAnimationFrame(loop);
    var dt = Math.min((now - last) / 1000, 0.1); last = now;
    if (!host.clientWidth) return;
    frame(dt);
  }
  function setStage(s) {
    if (!F[s]) s = 'normal';
    stage = s; hopIdx = 0; hopT = 0; pauseT = 0; playing = true;
    card.hidden = true;
    applyState(); renderFlowList(); markFlow(); syncPlay();
  }
  window.Topo2D = { setStage: setStage, fit: fitView, resize: function () {} };
  stageEl.classList.add('has-2d');
  setStage(typeof currentV3Stage !== 'undefined' ? currentV3Stage : 'normal');
  if (window.drTab) window.drTab('flow');
  syncDetail();
  requestAnimationFrame(loop);
})();
