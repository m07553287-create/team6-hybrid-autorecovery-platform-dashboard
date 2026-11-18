"""청사진 아이소메트릭 DR 토폴로지 SVG 생성기.
기존 상태 머신이 쓰는 path id(path-tunnel-a/b/c, path-db-sync)를 그대로 제공한다.
나머지 상태 표현은 <svg data-stage="..."> + CSS 로 처리한다.
"""
import math

U = 26                      # 그리드 1칸(px)
C30, S30 = math.cos(math.radians(30)), 0.5
OX, OY = 0, 0               # 나중에 viewBox 로 보정
_pts = []                   # bbox 계산용
ZONE_LABELS = []


def iso(x, y, z=0.0):
    sx = (x - y) * U * C30 + OX
    sy = (x + y) * U * S30 - z * U + OY
    _pts.append((sx, sy))
    return sx, sy


def P(*xyz):
    return '%.1f,%.1f' % iso(*xyz)


def poly(points, cls):
    return '<polygon class="%s" points="%s"/>' % (cls, ' '.join(P(*p) for p in points))


def box(x, y, z, w, d, h, cls='', id_=None, slots=0):
    """윗면 + 앞(좌하) 면 + 우측 면. slots: 앞면 랙 슬롯 줄 수."""
    t = z + h
    g = ['<g class="iso-box %s"%s>' % (cls, ' id="%s"' % id_ if id_ else '')]
    g.append(poly([(x, y + d, z), (x + w, y + d, z), (x + w, y + d, t), (x, y + d, t)], 'f-left'))
    g.append(poly([(x + w, y, z), (x + w, y + d, z), (x + w, y + d, t), (x + w, y, t)], 'f-right'))
    g.append(poly([(x, y, t), (x + w, y, t), (x + w, y + d, t), (x, y + d, t)], 'f-top'))
    for i in range(1, slots + 1):
        zz = z + h * i / (slots + 1)
        a, b = iso(x + 0.15 * w, y + d, zz), iso(x + 0.85 * w, y + d, zz)
        g.append('<line class="slot" x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f"/>' % (*a, *b))
        led = iso(x + 0.9 * w, y + d, zz)
        g.append('<circle class="led" cx="%.1f" cy="%.1f" r="1.6"/>' % led)
    g.append('</g>')
    return ''.join(g)


def cyl(cx, cy, z, r, h, cls='', id_=None, rings=2):
    rx, ry = r * U * C30 * math.sqrt(2), r * U * S30 * math.sqrt(2)
    bx, by = iso(cx, cy, z)
    tx, ty = iso(cx, cy, z + h)
    iso(cx + r, cy - r, z + h); iso(cx - r, cy + r, z)   # bbox
    g = ['<g class="iso-cyl %s"%s>' % (cls, ' id="%s"' % id_ if id_ else '')]
    g.append('<path class="f-left" d="M%.1f,%.1f L%.1f,%.1f A%.1f,%.1f 0 0 0 %.1f,%.1f L%.1f,%.1f A%.1f,%.1f 0 0 1 %.1f,%.1f Z"/>'
             % (tx - rx, ty, bx - rx, by, rx, ry, bx + rx, by, tx + rx, ty, rx, ry, tx - rx, ty))
    for i in range(1, rings + 1):
        yy = by - (by - ty) * i / (rings + 1)
        g.append('<path class="slot" d="M%.1f,%.1f A%.1f,%.1f 0 0 0 %.1f,%.1f"/>' % (bx - rx, yy, rx, ry, bx + rx, yy))
    g.append('<ellipse class="f-top" cx="%.1f" cy="%.1f" rx="%.1f" ry="%.1f"/>' % (tx, ty, rx, ry))
    g.append('</g>')
    return ''.join(g)


def slab(x, y, w, d, id_, title, sub, cls=''):
    """존 플랫폼 + 앞쪽 모서리 라벨."""
    g = ['<g class="iso-zone %s" id="%s">' % (cls, id_)]
    g.append(box(x, y, -0.35, w, d, 0.35, 'platform'))
    # 바닥 모눈 (도면 위의 도면)
    for i in range(1, int(w)):
        a, b = iso(x + i, y, 0), iso(x + i, y + d, 0)
        g.append('<line class="floor" x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f"/>' % (*a, *b))
    for j in range(1, int(d)):
        a, b = iso(x, y + j, 0), iso(x + w, y + j, 0)
        g.append('<line class="floor" x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f"/>' % (*a, *b))
    g.append('</g>')
    lx, ly = iso(x + w, y + d, -0.35)
    hw = max(tw(title, 17), tw(sub, 13)) / 2 + 4
    _pts.append((lx - hw, ly + 50)); _pts.append((lx + hw, ly + 50))
    ZONE_LABELS.append('<g class="zone-label" id="%s-label"><text class="zone-t" x="%.1f" y="%.1f" text-anchor="middle">%s</text>'
                       '<text class="zone-s" x="%.1f" y="%.1f" text-anchor="middle">%s</text></g>' % (id_, lx, ly + 24, title, lx, ly + 43, sub))
    return ''.join(g)


def tw(t, px):
    return sum(px * 0.92 if ord(ch) > 0x1100 else px * 0.56 for ch in t)


def label(at, dx, dy, title, sub='', cls='', id_=None):
    """도면식 인출선 주석."""
    x, y = at
    ex, ey = x + dx, y + dy
    anchor = 'start' if dx >= 0 else 'end'
    off = 6 if dx >= 0 else -6
    w = max(tw(title, 15), tw(sub, 13)) + 32
    _pts.append((ex + (w if dx >= 0 else -w), ey + 24)); _pts.append((ex, ey - 18))
    s = ['<g class="callout %s"%s>' % (cls, ' id="%s"' % id_ if id_ else '')]
    s.append('<circle class="pin" cx="%.1f" cy="%.1f" r="2.2"/>' % (x, y))
    s.append('<polyline class="leader" points="%.1f,%.1f %.1f,%.1f %.1f,%.1f"/>' % (x, y, ex, ey, ex + (24 if dx >= 0 else -24), ey))
    tx = ex + (24 if dx >= 0 else -24) + off
    s.append('<text class="c-t" x="%.1f" y="%.1f" text-anchor="%s">%s</text>' % (tx, ey + 4, anchor, title))
    if sub:
        s.append('<text class="c-s" x="%.1f" y="%.1f" text-anchor="%s">%s</text>' % (tx, ey + 22, anchor, sub))
    s.append('</g>')
    return ''.join(s)


def pipe(points, id_, cls, casing_id=None):
    d = 'M' + ' L'.join(P(*p) for p in points)
    return ('<path class="pipe-case"%s d="%s"/>' % (' id="%s"' % casing_id if casing_id else '', d) +
            '<path id="%s" class="%s" fill="none" d="%s"/>' % (id_, cls, d))


def cloud(cx, cy, z, id_):
    x, y = iso(cx, cy, z)
    return ('<g class="iso-cloud" id="%s"><path class="f-top" d="M%.1f,%.1f '
            'a14,14 0 0 1 10,-22 a20,20 0 0 1 36,-8 a16,16 0 0 1 26,10 a12,12 0 0 1 2,20 Z"/></g>'
            % (id_, x - 38, y + 10))


def person(cx, cy, z):
    x, y = iso(cx, cy, z)
    return ('<g class="iso-person"><circle class="f-top" cx="%.1f" cy="%.1f" r="6"/>'
            '<path class="f-left" d="M%.1f,%.1f q11,-16 22,0 v8 h-22 Z"/></g>' % (x, y - 18, x - 11, y + 2))


def build():
    _pts.clear(); ZONE_LABELS.clear()
    out = []
    # 존 원점 — 화면에서 서로 겹치지 않게 배치 (sx=(x-y)·22.5, sy=(x+y)·13)
    KT, ON, AW, GH = (-9.6, 1.1), (0.0, 0.0), (11.0, 2.2), (-0.5, -10.7)
    CF = (-9.6, -4.3, 3.6)
    def at(o, dx, dy):
        return o[0] + dx, o[1] + dy

    # ---- 존 플랫폼 (뒤 → 앞) ----
    out.append(slab(*GH, 3, 3, 'iso-gh', 'GitHub Pages', '0초 비상 접수 (dr.ktci5.kr)'))
    out.append(slab(*KT, 4, 4, 'iso-kt', 'KT Cloud', '입구 전용'))
    out.append(slab(*ON, 6, 6, 'iso-onprem', '온프레미스 OpenStack', 'Primary · K3s · MySQL'))
    out.append(slab(*AW, 5, 5, 'iso-aws', 'AWS', '관제 · DR 대기 · S3 백업'))

    # 장비 좌표
    edge = at(KT, 2.0, 1.2)            # 1.6 x 1.2
    wg = at(ON, 0.4, 2.2)              # 1.2 x 1.0
    ctl = at(AW, 0.9, 0.8)             # 1.4 x 1.2
    dbp = at(ON, 4.9, 4.2)
    dbr = at(AW, 2.9, 3.4)
    ghp = at(GH, 0.9, 0.8)

    # ---- 터널 ----
    z = 0.25
    out.append(pipe([(edge[0] + 1.6, edge[1] + 0.6, z), (wg[0], edge[1] + 0.6, z)], 'path-tunnel-a', 'flow-line line-yellow'))
    out.append(pipe([(ctl[0], ctl[1] + 0.6, z), (ON[0] + 7.0, ctl[1] + 0.6, z), (ON[0] + 7.0, ON[1] - 0.7, z),
                     (wg[0] + 0.6, ON[1] - 0.7, z), (wg[0] + 0.6, wg[1], z)], 'path-tunnel-b', 'flow-line line-blue'))
    out.append(pipe([(edge[0] + 0.3, edge[1] + 1.2, z), (edge[0] + 0.3, ON[1] + 7.4, z), (dbr[0] - 0.3, ON[1] + 7.4, z),
                     (dbr[0] - 0.3, AW[1] + 5.0, z)], 'path-tunnel-c', 'line-inactive'))
    out.append(pipe([(dbp[0] + 0.7, dbp[1], z), (AW[0] - 1.0, dbp[1], z), (AW[0] - 1.0, dbr[1], z), (dbr[0] - 0.65, dbr[1], z)],
                    'path-db-sync', 'flow-line line-yellow'))
    out.append(pipe([CF, (edge[0] + 0.8, edge[1] + 0.6, 1.5)], 'iso-path-ingress', 'flow-line line-blue'))
    out.append(pipe([CF, (ghp[0] + 0.6, ghp[1] + 0.6, 0.5)], 'iso-path-gh', 'line-inactive', casing_id='iso-case-gh'))

    # ---- 장비 (뒤 → 앞) ----
    out.append(box(*ghp, 0, 1.2, 1.2, 0.5, 'node', 'iso-ghpage'))
    out.append(box(*edge, 0, 1.6, 1.2, 1.5, 'node', 'iso-edge', slots=3))
    for i, nid in enumerate(['iso-k8s-cp1', 'iso-k8s-w1', 'iso-k8s-w2']):
        out.append(box(ON[0] + 2.4 + i * 1.15, ON[1] + 0.4, 0, 0.9, 1.1, 2.4, 'node rack', nid, slots=4))
    out.append(box(*wg, 0, 1.2, 1.0, 0.9, 'node', 'iso-wg', slots=1))
    for pid, px, py in [('iso-pod-web', 2.4, 2.6), ('iso-pod-api', 3.3, 2.6), ('iso-pod-notify', 2.4, 3.5), ('iso-pod-audit', 3.3, 3.5)]:
        out.append(box(ON[0] + px, ON[1] + py, 0, 0.6, 0.6, 0.6, 'pod', pid))
    out.append(cyl(*dbp, 0, 0.7, 1.5, 'db', 'iso-db-primary'))
    out.append(box(*ctl, 0, 1.4, 1.2, 1.7, 'node', 'iso-ctl', slots=3))
    out.append(cyl(AW[0] + 3.8, AW[1] + 1.0, 0, 0.45, 0.7, 'bucket', 'iso-s3', rings=1))
    out.append(cyl(*dbr, 0, 0.65, 1.4, 'db', 'iso-db-replica'))
    out.append(person(CF[0] - 2.2, CF[1] - 1.6, CF[2] - 0.2))
    out.append(cloud(*CF, 'iso-cf'))

    # ---- 터널 이름 · 절단 · 펜싱 ----
    ta = (KT[0] + 6.4, edge[1] + 0.6)
    for (tx, ty), t, cls in [(ta, '터널 A', 'ta'), ((ON[0] + 7.0, ON[1] + 1.0), '터널 B', 'tb'),
                             ((ON[0] + 5.5, ON[1] + 7.4), '터널 C · DR 우회', 'tc'), ((ON[0] + 6.8, dbp[1]), 'GTID 복제', 'tb')]:
        x, y = iso(tx, ty, z)
        out.append('<text class="tun-t %s" x="%.1f" y="%.1f" text-anchor="middle">%s</text>' % (cls, x, y - 8, t))
    x, y = iso(ta[0] + 1.2, ta[1], z)
    out.append('<g class="cut" id="iso-cut-a"><path d="M%.1f,%.1f l12,12 M%.1f,%.1f l-12,12"/></g>' % (x - 6, y - 6, x + 6, y - 6))
    x, y = iso(ON[0] + 3.0, ON[1] + 3.0, 0)
    out.append('<text class="stamp" id="iso-stamp-fenced" x="%.1f" y="%.1f" text-anchor="middle">FENCED · 쓰기 차단</text>' % (x, y + 6))

    # ---- 존 라벨 + 주석 ----
    out.extend(ZONE_LABELS)
    out.append(label(iso(CF[0] - 2.2, CF[1] - 1.6, CF[2] + 0.7), -30, -20, '사용자 민원 접수', 'HTTPS'))
    out.append(label(iso(CF[0] + 0.4, CF[1] - 0.4, CF[2] + 1.0), 40, -20, 'Cloudflare', 'Anycast WAF · Worker'))
    out.append(label(iso(edge[0], edge[1] + 0.6, 1.2), -24, 34, 'Edge-GW', 'Nginx WAF · 14.63.212.190'))
    out.append(label(iso(wg[0], wg[1] + 1.0, 0.5), -30, 70, 'WireGuard GW', 'Inbound 0 · 펜싱', id_='iso-c-wg'))
    out.append(label(iso(ON[0] + 2.4, ON[1] + 0.4, 2.4), -30, -50, 'K3s 노드 3대', 'cp1 · w1 · w2'))
    out.append(label(iso(ON[0] + 2.7, ON[1] + 4.1, 0.3), -130, 60, 'app 파드', 'web · api · notify · audit', id_='iso-c-pod'))
    out.append(label(iso(dbp[0] + 0.5, dbp[1] - 0.5, 1.5), 60, -40, 'MySQL 8.4 Primary', 'GTID · Read/Write', id_='iso-c-dbp'))
    out.append(label(iso(ctl[0] + 1.4, ctl[1], 1.7), 30, -40, 'Orchestrator', '3-Signal 판정', id_='iso-c-ctl'))
    out.append(label(iso(dbr[0] - 0.4, dbr[1] + 0.4, 0.5), -40, 80, 'MySQL Replica', 'GTID 비동기 수신', id_='iso-c-dbr'))
    out.append(label(iso(ghp[0], ghp[1], 0.5), -40, -30, '정적 비상 접수 폼', 'Black Sky 시 0초 노출', id_='iso-c-gh'))

    xs = [p[0] for p in _pts]; ys = [p[1] for p in _pts]
    pad = 6
    vb = (min(xs) - pad, min(ys) - pad, max(xs) - min(xs) + 2 * pad, max(ys) - min(ys) + 2 * pad)
    return ('<svg id="iso-scene" data-stage="normal" role="img" aria-label="하이브리드 멀티클라우드 아이소메트릭 토폴로지" '
            'viewBox="%.0f %.0f %.0f %.0f" preserveAspectRatio="xMidYMid meet">' % vb + ''.join(out) + '</svg>')


if __name__ == '__main__':
    print(build())
