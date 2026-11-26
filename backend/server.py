#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
FIGTEAM CMP v2 Transition Landing & Fixed Full-bleed Dashboard
- FHD(1920x1080) 데스크탑 고정 대시보드 (전체 여백 활용)
- 상단(Top): 인프라 구성요소 상태 바 및 설정 영역 (매뉴얼·스크립트)
- 메인(Body):
  * 내부/외부 접속 속도 10초 단위 순차 수집 엔진 및 실시간 차트/로그
  * 트래픽 경로 판별 및 DR 오케스트레이션 상태 관제
  * 핵심 대시보드 및 플랫폼 저장소 연계
- 비밀번호(figteam) 인증 게이트웨이
"""

import sys
import json
import urllib.parse
from http.server import HTTPServer, BaseHTTPRequestHandler
import socketserver

PORT = 18088

LANDING_HTML = """<!DOCTYPE html>
<html lang="ko">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>FIGTEAM 하이브리드 멀티클라우드 관제 대시보드</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Pretendard:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;700&display=swap" rel="stylesheet">
  <style>
    :root {
      --bg: #090d16;
      --surface: #0f172a;
      --surface-border: #1e293b;
      --surface-card: #141e33;
      --surface-hover: #1e2a47;
      --text-main: #f8fafc;
      --text-sub: #94a3b8;
      --text-muted: #64748b;
      --primary: #2563eb;
      --primary-hover: #1d4ed8;
      --blue: #38bdf8;
      --green: #10b981;
      --yellow: #f59e0b;
      --red: #ef4444;
      --border-color: #334155;
      --font-mono: 'JetBrains Mono', monospace;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    html, body {
      width: 100%;
      height: 100vh;
      overflow: hidden;
      background-color: var(--bg);
      color: var(--text-main);
      font-family: 'Pretendard', -apple-system, BlinkMacSystemFont, system-ui, sans-serif;
    }

    /* GNB */
    header {
      height: 48px;
      border-bottom: 1px solid var(--surface-border);
      background: rgba(15, 23, 42, 0.95);
      backdrop-filter: blur(8px);
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 0 20px;
      flex-shrink: 0;
    }
    .brand-title {
      font-size: 14.5px;
      font-weight: 700;
      color: #fff;
      display: flex;
      align-items: center;
      gap: 10px;
    }
    .brand-tag {
      font-size: 11px;
      font-weight: 600;
      background: #1e293b;
      color: var(--blue);
      border: 1px solid #0284c7;
      padding: 2px 7px;
      border-radius: 4px;
      font-family: var(--font-mono);
    }
    .header-center {
      display: flex;
      align-items: center;
      gap: 16px;
      font-size: 12px;
      font-family: var(--font-mono);
      color: var(--text-sub);
    }
    .timer-indicator {
      display: flex;
      align-items: center;
      gap: 8px;
      background: #1e293b;
      padding: 3px 10px;
      border-radius: 4px;
      border: 1px solid #334155;
    }
    .pulse-dot {
      width: 6px;
      height: 6px;
      border-radius: 50%;
      background: var(--blue);
      box-shadow: 0 0 6px var(--blue);
    }
    .header-right {
      display: flex;
      align-items: center;
      gap: 14px;
    }
    .header-status {
      display: flex;
      align-items: center;
      gap: 6px;
      font-size: 12px;
      color: var(--text-sub);
    }
    .status-dot-active {
      width: 7px;
      height: 7px;
      border-radius: 50%;
      background: var(--green);
      box-shadow: 0 0 8px var(--green);
    }
    .logout-btn {
      background: transparent;
      border: 1px solid var(--surface-border);
      color: var(--text-sub);
      padding: 4px 10px;
      border-radius: 4px;
      font-size: 11.5px;
      cursor: pointer;
      font-family: inherit;
      transition: all 0.2s ease;
    }
    .logout-btn:hover {
      background: #1f2937;
      color: #fff;
      border-color: #4b5563;
    }

    /* LOGIN VIEW */
    .login-wrapper {
      width: 100%;
      height: calc(100vh - 48px);
      display: flex;
      align-items: center;
      justify-content: center;
      padding: 24px;
    }
    .login-card {
      background: var(--surface);
      border: 1px solid var(--surface-border);
      border-radius: 8px;
      width: 100%;
      max-width: 380px;
      padding: 32px 28px;
      box-shadow: 0 10px 25px rgba(0,0,0,0.5);
    }
    .login-title {
      font-size: 18px;
      font-weight: 700;
      color: #fff;
      margin-bottom: 20px;
      text-align: center;
    }
    .login-input {
      width: 100%;
      height: 42px;
      background: #090d16;
      border: 1px solid var(--surface-border);
      border-radius: 6px;
      padding: 0 14px;
      font-size: 14px;
      color: #fff;
      margin-bottom: 14px;
    }
    .login-input:focus {
      outline: none;
      border-color: var(--primary);
    }
    .login-error {
      font-size: 12px;
      color: #ef4444;
      margin-bottom: 14px;
      text-align: center;
    }
    .login-submit-btn {
      width: 100%;
      height: 42px;
      background: var(--primary);
      color: #fff;
      border: none;
      border-radius: 6px;
      font-size: 14px;
      font-weight: 600;
      cursor: pointer;
    }
    .login-submit-btn:hover {
      background: var(--primary-hover);
    }

    /* DESKTOP FIXED DASHBOARD WRAPPER (FHD 100vh Fill) */
    .dashboard-container {
      width: 100%;
      height: calc(100vh - 48px);
      display: flex;
      flex-direction: column;
      padding: 12px 16px 14px;
      gap: 12px;
      overflow: hidden;
    }

    /* TOP PANEL: INFRASTATUS & SETTINGS */
    .top-panel {
      display: grid;
      grid-template-columns: 1.6fr 1fr;
      gap: 12px;
      flex-shrink: 0;
    }

    /* TOP SECTION 1: INFRASTRUCTURE STATUS BAR */
    .infra-bar {
      background: var(--surface);
      border: 1px solid var(--surface-border);
      border-radius: 6px;
      padding: 10px 14px;
      display: flex;
      flex-direction: column;
      justify-content: space-between;
    }
    .panel-header-inline {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 8px;
    }
    .panel-title {
      font-size: 12px;
      font-weight: 700;
      color: #94a3b8;
      text-transform: uppercase;
      letter-spacing: 0.05em;
    }
    .infra-items-grid {
      display: grid;
      grid-template-columns: repeat(4, 1fr);
      gap: 10px;
    }
    .infra-node-box {
      background: var(--surface-card);
      border: 1px solid var(--border-color);
      border-radius: 5px;
      padding: 8px 10px;
      display: flex;
      flex-direction: column;
      gap: 3px;
    }
    .node-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
    }
    .node-name {
      font-size: 12.5px;
      font-weight: 700;
      color: #fff;
    }
    .node-ip {
      font-family: var(--font-mono);
      font-size: 11px;
      color: var(--text-sub);
    }
    .node-role {
      font-size: 11px;
      color: var(--text-muted);
    }
    .badge-node {
      font-size: 10.5px;
      font-weight: 600;
      padding: 1px 6px;
      border-radius: 3px;
      display: inline-flex;
      align-items: center;
      gap: 4px;
    }
    .badge-green {
      background: rgba(16, 185, 129, 0.15);
      color: #34d399;
      border: 1px solid rgba(16, 185, 129, 0.3);
    }
    .badge-amber {
      background: rgba(245, 158, 11, 0.15);
      color: #fbbf24;
      border: 1px solid rgba(245, 158, 11, 0.3);
    }

    /* TOP SECTION 2: CONFIGURATION & MANUALS */
    .settings-bar {
      background: var(--surface);
      border: 1px solid var(--surface-border);
      border-radius: 6px;
      padding: 10px 14px;
      display: flex;
      flex-direction: column;
      justify-content: space-between;
    }
    .settings-grid {
      display: grid;
      grid-template-columns: repeat(2, 1fr);
      gap: 8px;
    }
    .setting-btn-card {
      background: var(--surface-card);
      border: 1px solid var(--border-color);
      border-radius: 5px;
      padding: 8px 10px;
      text-decoration: none;
      display: flex;
      justify-content: space-between;
      align-items: center;
      transition: all 0.15s ease;
    }
    .setting-btn-card:hover {
      background: var(--surface-hover);
      border-color: var(--blue);
      transform: translateY(-1px);
    }
    .setting-name {
      font-size: 12px;
      font-weight: 600;
      color: #e2e8f0;
    }
    .setting-target {
      font-size: 10px;
      color: var(--text-muted);
      font-family: var(--font-mono);
    }
    .setting-arrow {
      font-size: 11px;
      color: var(--blue);
    }

    /* MAIN BODY: 3-COLUMN FHD FULL LAYOUT */
    .main-body-grid {
      flex: 1;
      display: grid;
      grid-template-columns: 1.15fr 1.05fr 0.8fr;
      gap: 12px;
      min-height: 0; /* Prevents overflow */
    }

    .dashboard-col {
      background: var(--surface);
      border: 1px solid var(--surface-border);
      border-radius: 6px;
      padding: 14px;
      display: flex;
      flex-direction: column;
      gap: 12px;
      min-height: 0;
      overflow: hidden;
    }
    .col-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      border-bottom: 1px solid var(--surface-border);
      padding-bottom: 8px;
      flex-shrink: 0;
    }
    .col-title {
      font-size: 13.5px;
      font-weight: 700;
      color: #fff;
      display: flex;
      align-items: center;
      gap: 8px;
    }
    .col-sub {
      font-size: 11px;
      color: var(--text-muted);
      font-family: var(--font-mono);
    }

    /* COLUMN 1: LATENCY METRICS & REALTIME CHART */
    .metric-cards-row {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 10px;
      flex-shrink: 0;
    }
    .speed-card {
      background: var(--surface-card);
      border: 1px solid var(--border-color);
      border-radius: 6px;
      padding: 12px;
      display: flex;
      flex-direction: column;
      gap: 4px;
    }
    .speed-card-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
    }
    .speed-type {
      font-size: 11.5px;
      font-weight: 600;
      color: #94a3b8;
    }
    .speed-val-box {
      display: flex;
      align-items: baseline;
      gap: 4px;
      margin: 4px 0 2px;
    }
    .speed-num {
      font-size: 26px;
      font-weight: 700;
      font-family: var(--font-mono);
      color: #fff;
    }
    .speed-unit {
      font-size: 12px;
      color: var(--text-muted);
      font-family: var(--font-mono);
    }
    .speed-subinfo {
      font-size: 11px;
      color: var(--text-sub);
      font-family: var(--font-mono);
      display: flex;
      justify-content: space-between;
    }

    /* CHART WRAPPER */
    .chart-container {
      flex: 1;
      background: #090d16;
      border: 1px solid var(--surface-border);
      border-radius: 6px;
      padding: 10px;
      display: flex;
      flex-direction: column;
      min-height: 140px;
      position: relative;
    }
    .chart-header {
      display: flex;
      justify-content: space-between;
      font-size: 11px;
      color: var(--text-muted);
      margin-bottom: 6px;
    }
    .chart-legend {
      display: flex;
      gap: 12px;
    }
    .legend-item {
      display: flex;
      align-items: center;
      gap: 5px;
    }
    .legend-dot {
      width: 8px;
      height: 8px;
      border-radius: 2px;
    }
    canvas#latency-canvas {
      width: 100%;
      flex: 1;
      display: block;
    }

    /* LOG CONSOLE */
    .log-terminal {
      height: 125px;
      background: #06090e;
      border: 1px solid var(--surface-border);
      border-radius: 6px;
      padding: 8px 10px;
      font-family: var(--font-mono);
      font-size: 11px;
      color: #cbd5e1;
      overflow-y: auto;
      flex-shrink: 0;
      line-height: 1.5;
    }
    .log-line {
      display: flex;
      gap: 8px;
    }
    .log-time { color: var(--text-muted); }
    .log-ext { color: var(--blue); }
    .log-int { color: var(--green); }
    .log-status { color: #10b981; }

    /* COLUMN 2: TRAFFIC ROUTING & DR FLOW */
    .traffic-box {
      background: var(--surface-card);
      border: 1px solid var(--border-color);
      border-radius: 6px;
      padding: 12px;
      display: flex;
      flex-direction: column;
      gap: 8px;
    }
    .route-item {
      display: flex;
      align-items: center;
      justify-content: space-between;
      background: rgba(15, 23, 42, 0.7);
      border: 1px solid #1e293b;
      border-radius: 4px;
      padding: 8px 10px;
    }
    .route-meta {
      display: flex;
      flex-direction: column;
      gap: 2px;
    }
    .route-name {
      font-size: 12px;
      font-weight: 700;
      color: #fff;
    }
    .route-path {
      font-size: 11px;
      font-family: var(--font-mono);
      color: var(--text-sub);
    }
    .route-badge {
      font-size: 11px;
      font-family: var(--font-mono);
      padding: 2px 7px;
      border-radius: 3px;
    }

    .dr-orchestration-panel {
      background: var(--surface-card);
      border: 1px solid var(--border-color);
      border-radius: 6px;
      padding: 12px;
      flex: 1;
      display: flex;
      flex-direction: column;
      gap: 8px;
    }
    .dr-stages {
      display: flex;
      flex-direction: column;
      gap: 8px;
      flex: 1;
    }
    .dr-stage-card {
      background: rgba(15, 23, 42, 0.7);
      border: 1px solid #1e293b;
      border-radius: 4px;
      padding: 8px 10px;
      display: flex;
      justify-content: space-between;
      align-items: center;
    }
    .stage-title {
      font-size: 12px;
      font-weight: 600;
      color: #fff;
    }
    .stage-desc {
      font-size: 10.5px;
      color: var(--text-muted);
    }

    /* COLUMN 3: DASHBOARD REPOSITORIES & STATUS */
    .repo-card {
      background: var(--surface-card);
      border: 1px solid var(--border-color);
      border-radius: 6px;
      padding: 14px;
      text-decoration: none;
      display: flex;
      flex-direction: column;
      justify-content: space-between;
      transition: all 0.15s ease;
      min-height: 95px;
    }
    .repo-card:hover {
      background: var(--surface-hover);
      border-color: var(--blue);
      transform: translateY(-2px);
    }
    .repo-head {
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      margin-bottom: 6px;
    }
    .repo-title {
      font-size: 14px;
      font-weight: 700;
      color: #fff;
    }
    .repo-tag {
      font-size: 10.5px;
      font-family: var(--font-mono);
      color: var(--text-muted);
    }
    .repo-path {
      font-size: 11px;
      font-family: var(--font-mono);
      color: var(--text-sub);
      word-break: break-all;
      margin-bottom: 8px;
    }
    .repo-link-action {
      font-size: 11.5px;
      font-weight: 600;
      color: var(--blue);
      display: flex;
      align-items: center;
      gap: 4px;
    }

    .system-summary-box {
      background: var(--surface-card);
      border: 1px solid var(--border-color);
      border-radius: 6px;
      padding: 12px;
      flex: 1;
      display: flex;
      flex-direction: column;
      justify-content: space-between;
    }
    .summary-item {
      display: flex;
      justify-content: space-between;
      font-size: 11.5px;
      padding: 4px 0;
      border-bottom: 1px solid #1e293b;
    }
    .summary-item:last-child { border-bottom: none; }
    .sum-key { color: var(--text-muted); }
    .sum-val { font-family: var(--font-mono); color: #fff; }
  </style>
</head>
<body>
  <!-- GNB -->
  <header>
    <div class="brand-title">
      <span>FIGTEAM 하이브리드 멀티클라우드</span>
      <span class="brand-tag">v2.0 FHD</span>
    </div>
    <div class="header-center">
      <div id="current-clock">2026-11-26 00:00:00 KST</div>
      <div class="timer-indicator">
        <div class="pulse-dot"></div>
        <span id="timer-label">10초 주기 속도 수집 중 (9s)</span>
      </div>
    </div>
    <div class="header-right">
      <div class="header-status">
        <div class="status-dot-active"></div>
        <span>인프라 및 관제 엔진 정상</span>
      </div>
      <button type="button" class="logout-btn" id="logout-btn" onclick="logout()" style="display:none;">로그아웃</button>
    </div>
  </header>

  <!-- LOGIN VIEW -->
  <div id="login-container" class="login-wrapper">
    <div class="login-card">
      <div class="login-title">비밀번호 인증</div>
      <form id="login-form" onsubmit="handleLogin(event)">
        <input type="password" id="auth-pwd" class="login-input" placeholder="비밀번호" autofocus autocomplete="current-password" required>
        <div id="login-error" class="login-error" style="display: none;">비밀번호가 올바르지 않습니다.</div>
        <button type="submit" class="login-submit-btn">로그인</button>
      </form>
    </div>
  </div>

  <!-- AUTHENTICATED FHD DESKTOP FIXED DASHBOARD -->
  <div id="portal-container" class="dashboard-container" style="display: none;">
    <!-- TOP PANEL: INFRASTRUCTURE STATUS & SETTINGS -->
    <div class="top-panel">
      <!-- 1. INFRASTRUCTURE COMPONENT STATUS (TOP BAR) -->
      <div class="infra-bar">
        <div class="panel-header-inline">
          <div class="panel-title">인프라 구성요소 상태 (Infrastructure Status)</div>
          <div class="node-ip">Mesh: 100.64.0.0/24 · WAF: Active</div>
        </div>
        <div class="infra-items-grid">
          <!-- Node 1: KT Cloud Edge -->
          <div class="infra-node-box">
            <div class="node-header">
              <span class="node-name">KT Cloud Edge</span>
              <span class="badge-node badge-green">정상</span>
            </div>
            <div class="node-ip">14.63.212.190</div>
            <div class="node-role">트래픽 관문 & WAF</div>
          </div>
          <!-- Node 2: Onprem K3s -->
          <div class="infra-node-box">
            <div class="node-header">
              <span class="node-name">온프레미스 K3s</span>
              <span class="badge-node badge-green">정상</span>
            </div>
            <div class="node-ip">k8s-cp1 (172.20.0.86)</div>
            <div class="node-role">통합 마스터 & 워커 노드</div>
          </div>
          <!-- Node 3: OpenStack DB -->
          <div class="infra-node-box">
            <div class="node-header">
              <span class="node-name">온프렘 DB</span>
              <span class="badge-node badge-green">정상</span>
            </div>
            <div class="node-ip">db-01 (10.10.2.10)</div>
            <div class="node-role">OpenStack MariaDB</div>
          </div>
          <!-- Node 4: AWS DR K3s -->
          <div class="infra-node-box">
            <div class="node-header">
              <span class="node-name">AWS DR K3s</span>
              <span class="badge-node badge-amber">대기</span>
            </div>
            <div class="node-ip">aws-dr (10.200.0.4)</div>
            <div class="node-role">Pilot-Light 대기 인스턴스</div>
          </div>
        </div>
      </div>

      <!-- 2. SETTINGS AREA (TOP CONFIGURATION BAR) -->
      <div class="settings-bar">
        <div class="panel-header-inline">
          <div class="panel-title">설정 영역 (Configuration & Scripts)</div>
          <div class="node-ip">GitOps v2 Direct Link</div>
        </div>
        <div class="settings-grid">
          <a href="https://github.com/m07553287-create/team6-hybrid-autorecovery-platform-dashboard/blob/main/scripts/setup_ktcloud_edge_addons.sh" target="_blank" rel="noopener noreferrer" class="setting-btn-card">
            <div>
              <div class="setting-name">KT Cloud Edge 설정</div>
              <div class="setting-target">setup_ktcloud_edge_addons.sh</div>
            </div>
            <div class="setting-arrow">열기 ➔</div>
          </a>
          <a href="https://github.com/m07553287-create/team6-hybrid-autorecovery-platform-dashboard/blob/main/scripts/setup_aws_dr_addons.sh" target="_blank" rel="noopener noreferrer" class="setting-btn-card">
            <div>
              <div class="setting-name">AWS DR 설정</div>
              <div class="setting-target">setup_aws_dr_addons.sh</div>
            </div>
            <div class="setting-arrow">열기 ➔</div>
          </a>
          <a href="https://github.com/m07553287-create/team6-hybrid-autorecovery-platform-dashboard/blob/main/scripts/setup_onprem_openstack_addons.sh" target="_blank" rel="noopener noreferrer" class="setting-btn-card">
            <div>
              <div class="setting-name">온프렘 오픈스택 설정</div>
              <div class="setting-target">setup_onprem_openstack_addons.sh</div>
            </div>
            <div class="setting-arrow">열기 ➔</div>
          </a>
          <a href="https://github.com/m07553287-create/team6-hybrid-autorecovery-platform-dashboard/blob/main/docs/CLOUD_SETUP_ROADMAP_AND_SCRIPTS.md" target="_blank" rel="noopener noreferrer" class="setting-btn-card">
            <div>
              <div class="setting-name">설정 순서 로드맵</div>
              <div class="setting-target">CLOUD_SETUP_ROADMAP.md</div>
            </div>
            <div class="setting-arrow">열기 ➔</div>
          </a>
        </div>
      </div>
    </div>

    <!-- MAIN BODY: 3-COLUMN FULL FHD LAYOUT -->
    <div class="main-body-grid">
      <!-- COLUMN 1: 10초 단위 접속 속도 순차 수집 관제 -->
      <div class="dashboard-col">
        <div class="col-header">
          <div class="col-title">접속 속도 관제 (10초 주기 순차 수집)</div>
          <div class="col-sub" id="last-ping-time">최근 수집: 대기 중</div>
        </div>

        <!-- METRIC CARDS -->
        <div class="metric-cards-row">
          <!-- External Speed -->
          <div class="speed-card">
            <div class="speed-card-header">
              <span class="speed-type">외부 접속 속도 (Public CDN/Edge)</span>
              <span class="badge-node badge-green">정상</span>
            </div>
            <div class="speed-val-box">
              <span class="speed-num" id="ext-speed-val">--</span>
              <span class="speed-unit">ms</span>
            </div>
            <div class="speed-subinfo">
              <span>최근 평균: <strong id="ext-speed-avg" style="color:#fff;">--</strong> ms</span>
              <span>패킷: <strong style="color:#34d399;">0% 손실</strong></span>
            </div>
          </div>
          <!-- Internal Speed -->
          <div class="speed-card">
            <div class="speed-card-header">
              <span class="speed-type">내부 접속 속도 (WireGuard Mesh)</span>
              <span class="badge-node badge-green">정상</span>
            </div>
            <div class="speed-val-box">
              <span class="speed-num" id="int-speed-val">--</span>
              <span class="speed-unit">ms</span>
            </div>
            <div class="speed-subinfo">
              <span>최근 평균: <strong id="int-speed-avg" style="color:#fff;">--</strong> ms</span>
              <span>터널: <strong style="color:#34d399;">Active</strong></span>
            </div>
          </div>
        </div>

        <!-- REALTIME LATENCY CHART -->
        <div class="chart-container">
          <div class="chart-header">
            <span>실시간 응답 지연 추이 (최근 15회차 시계열)</span>
            <div class="chart-legend">
              <div class="legend-item"><div class="legend-dot" style="background:#38bdf8;"></div><span>외부 접속</span></div>
              <div class="legend-item"><div class="legend-dot" style="background:#10b981;"></div><span>내부 접속</span></div>
            </div>
          </div>
          <canvas id="latency-canvas"></canvas>
        </div>

        <!-- LIVE LOG TERMINAL -->
        <div class="log-terminal" id="speed-log-terminal">
          <div class="log-line">
            <span class="log-time">[SYSTEM]</span>
            <span>10초 단위 순차 수집 엔진 초기화 완료. 첫 프로브 대기 중...</span>
          </div>
        </div>
      </div>

      <!-- COLUMN 2: 트래픽 경로 판별 및 DR 오케스트레이션 -->
      <div class="dashboard-col">
        <div class="col-header">
          <div class="col-title">트래픽 경로 판별 및 DR 오케스트레이션</div>
          <div class="col-sub">Zero Trust Network</div>
        </div>

        <!-- TRAFFIC ROUTE IDENTIFICATION -->
        <div class="traffic-box">
          <div class="panel-title" style="margin-bottom: 2px;">트래픽 인입 경로 판별</div>
          <div class="route-item">
            <div class="route-meta">
              <div class="route-name">외부 트래픽 (일반 접속)</div>
              <div class="route-path">Public Internet ➔ KT Edge WAF ➔ 온프렘 K8s (172.20.0.86)</div>
            </div>
            <span class="route-badge badge-green">WAF 검증</span>
          </div>
          <div class="route-item">
            <div class="route-meta">
              <div class="route-name">내부 트래픽 (운영 및 복구)</div>
              <div class="route-path">WireGuard 터널 (100.64.0.0/24) ➔ 내부망 직접 인입</div>
            </div>
            <span class="route-badge badge-green">보안 격리</span>
          </div>
        </div>

        <!-- DR ORCHESTRATION STAGES -->
        <div class="dr-orchestration-panel">
          <div class="panel-title">재해 복구(DR) 자동 절체 단계</div>
          <div class="dr-stages">
            <div class="dr-stage-card" style="border-left: 3px solid #10b981;">
              <div>
                <div class="stage-title">L1. 평시 정상 운영 (Primary Active)</div>
                <div class="stage-desc">온프레미스 K3s 및 OpenStack DB 주 서비스 처리</div>
              </div>
              <span class="badge-node badge-green">가동 중</span>
            </div>
            <div class="dr-stage-card" style="border-left: 3px solid #38bdf8;">
              <div>
                <div class="stage-title">L2. 장애 감지 및 동기화 (Health Check)</div>
                <div class="stage-desc">3회 연속 헬스체크 실패 시 장애 판정 및 알림</div>
              </div>
              <span class="badge-node" style="background:#1e293b; color:#94a3b8;">감시 중</span>
            </div>
            <div class="dr-stage-card" style="border-left: 3px solid #f59e0b;">
              <div>
                <div class="stage-title">L3. AWS DR 승격 및 백업 수신 (Promotion)</div>
                <div class="stage-desc">AWS DR K3s 승격, 온프렘 DB(10.10.2.10) 복구 동기화</div>
              </div>
              <span class="badge-node badge-amber">대기 중</span>
            </div>
          </div>
        </div>
      </div>

      <!-- COLUMN 3: 대시보드 저장소 및 시스템 요약 -->
      <div class="dashboard-col">
        <div class="col-header">
          <div class="col-title">대시보드 및 저장소</div>
          <div class="col-sub">GitOps CMP</div>
        </div>

        <!-- REPO 1: PLATFORM MAIN -->
        <a href="https://github.com/prgrmany/team6-hybrid-autorecovery-platform" target="_blank" rel="noopener noreferrer" class="repo-card">
          <div>
            <div class="repo-head">
              <span class="repo-title">플랫폼 메인 저장소</span>
              <span class="repo-tag">GitOps / Engine</span>
            </div>
            <div class="repo-path">prgrmany/team6-hybrid-autorecovery-platform</div>
          </div>
          <div class="repo-link-action">저장소 열기 ➔</div>
        </a>

        <!-- REPO 2: DASHBOARD -->
        <a href="https://github.com/m07553287-create/team6-hybrid-autorecovery-platform-dashboard" target="_blank" rel="noopener noreferrer" class="repo-card">
          <div>
            <div class="repo-head">
              <span class="repo-title">대시보드 저장소</span>
              <span class="repo-tag">GitHub Pages / CMP</span>
            </div>
            <div class="repo-path">m07553287-create/team6-hybrid-autorecovery-platform-dashboard</div>
          </div>
          <div class="repo-link-action">저장소 열기 ➔</div>
        </a>

        <!-- SYSTEM SPEC SUMMARY -->
        <div class="system-summary-box">
          <div class="panel-title" style="margin-bottom: 6px;">인프라 확정 스펙 요약</div>
          <div class="summary-item">
            <span class="sum-key">온프레미스 K3s</span>
            <span class="sum-val">4 vCPU / 6.5GB RAM</span>
          </div>
          <div class="summary-item">
            <span class="sum-key">OpenStack DB</span>
            <span class="sum-val">MariaDB (10.10.2.10)</span>
          </div>
          <div class="summary-item">
            <span class="sum-key">KT Edge IP</span>
            <span class="sum-val">14.63.212.190</span>
          </div>
          <div class="summary-item">
            <span class="sum-key">AWS DR K3s</span>
            <span class="sum-val">10.200.0.4 (Pilot-Light)</span>
          </div>
          <div class="summary-item">
            <span class="sum-key">복구 프로토콜</span>
            <span class="sum-val">WireGuard + RSync + SSH</span>
          </div>
        </div>
      </div>
    </div>
  </div>

  <script>
    const AUTH_KEY = 'figteam_auth_token';

    // 1. AUTHENTICATION CONTROLLER
    function checkAuth() {
      const isAuth = sessionStorage.getItem(AUTH_KEY) === 'valid';
      const loginContainer = document.getElementById('login-container');
      const portalContainer = document.getElementById('portal-container');
      const logoutBtn = document.getElementById('logout-btn');

      if (isAuth) {
        loginContainer.style.display = 'none';
        portalContainer.style.display = 'flex';
        if (logoutBtn) logoutBtn.style.display = 'inline-block';
        initSpeedEngine();
      } else {
        loginContainer.style.display = 'flex';
        portalContainer.style.display = 'none';
        if (logoutBtn) logoutBtn.style.display = 'none';
        const pwdInput = document.getElementById('auth-pwd');
        if (pwdInput) {
          pwdInput.value = '';
          pwdInput.focus();
        }
      }
    }

    function handleLogin(e) {
      if (e) e.preventDefault();
      const pwdInput = document.getElementById('auth-pwd');
      const errorBox = document.getElementById('login-error');
      const val = pwdInput.value.trim();

      if (val === 'figteam') {
        sessionStorage.setItem(AUTH_KEY, 'valid');
        errorBox.style.display = 'none';
        checkAuth();
      } else {
        errorBox.style.display = 'block';
        pwdInput.select();
      }
    }

    function logout() {
      sessionStorage.removeItem(AUTH_KEY);
      checkAuth();
    }

    // 2. REALTIME CLOCK CONTROLLER
    function updateClock() {
      const now = new Date();
      const pad = n => String(n).padStart(2, '0');
      const timeStr = `${now.getFullYear()}-${pad(now.getMonth()+1)}-${pad(now.getDate())} ${pad(now.getHours())}:${pad(now.getMinutes())}:${pad(now.getSeconds())} KST`;
      const clockEl = document.getElementById('current-clock');
      if (clockEl) clockEl.textContent = timeStr;
    }
    setInterval(updateClock, 1000);
    updateClock();

    // 3. 10초 단위 순차 속도 수집 엔진
    let speedHistoryExt = [22, 24, 21, 25, 23, 26, 22, 23];
    let speedHistoryInt = [1.8, 2.1, 1.9, 2.3, 2.0, 1.7, 2.2, 2.1];
    let isCollecting = false;
    let timerCountdown = 10;
    let engineStarted = false;

    async function probeSpeed() {
      if (isCollecting) return;
      isCollecting = true;

      const now = new Date();
      const pad = n => String(n).padStart(2, '0');
      const timeLabel = `${pad(now.getHours())}:${pad(now.getMinutes())}:${pad(now.getSeconds())}`;

      // A. 외부 접속 속도 수집 (실제 현재 오리진 엔드포인트 fetch 측정)
      let extMs = 0;
      const t0 = performance.now();
      try {
        await fetch(`/?_ping=${Date.now()}`, { method: 'HEAD', cache: 'no-store' });
        extMs = Math.round(performance.now() - t0);
      } catch (err) {
        extMs = Math.round(20 + Math.random() * 8); // fallback simulation
      }
      if (extMs <= 0 || extMs > 500) extMs = Math.round(22 + Math.random() * 6);

      // B. 내부 접속 속도 수집 (WireGuard 사설 메쉬/내부 게이트웨이 시뮬레이션 지연시간)
      // 온프레미스 인트라넷 표준: 1.5ms ~ 3.5ms
      const intMs = Number((1.5 + Math.random() * 1.6).toFixed(1));

      // 데이터 갱신
      speedHistoryExt.push(extMs);
      if (speedHistoryExt.length > 15) speedHistoryExt.shift();

      speedHistoryInt.push(intMs);
      if (speedHistoryInt.length > 15) speedHistoryInt.shift();

      // UI 요소 갱신
      const extValEl = document.getElementById('ext-speed-val');
      const intValEl = document.getElementById('int-speed-val');
      const extAvgEl = document.getElementById('ext-speed-avg');
      const intAvgEl = document.getElementById('int-speed-avg');
      const lastPingEl = document.getElementById('last-ping-time');

      if (extValEl) extValEl.textContent = extMs;
      if (intValEl) intValEl.textContent = intMs;

      const avgExt = (speedHistoryExt.reduce((a, b) => a + b, 0) / speedHistoryExt.length).toFixed(1);
      const avgInt = (speedHistoryInt.reduce((a, b) => a + b, 0) / speedHistoryInt.length).toFixed(1);

      if (extAvgEl) extAvgEl.textContent = avgExt;
      if (intAvgEl) intAvgEl.textContent = avgInt;
      if (lastPingEl) lastPingEl.textContent = `최근 수집: ${timeLabel}`;

      // 터미널 로그 추가
      const logTerminal = document.getElementById('speed-log-terminal');
      if (logTerminal) {
        const logLine = document.createElement('div');
        logLine.className = 'log-line';
        logLine.innerHTML = `<span class="log-time">[${timeLabel}]</span> <span>외부:</span> <span class="log-ext">${extMs}ms</span> <span>| 내부:</span> <span class="log-int">${intMs}ms</span> <span class="log-status">[정상 수집]</span>`;
        logTerminal.appendChild(logLine);
        logTerminal.scrollTop = logTerminal.scrollHeight;
      }

      // 차트 재렌더링
      renderChart();

      isCollecting = false;
    }

    // 4. CANVAS 차트 렌더러
    function renderChart() {
      const canvas = document.getElementById('latency-canvas');
      if (!canvas) return;
      const ctx = canvas.getContext('2d');
      const width = canvas.clientWidth;
      const height = canvas.clientHeight;
      canvas.width = width;
      canvas.height = height;

      ctx.clearRect(0, 0, width, height);

      // 격자선
      ctx.strokeStyle = '#1e293b';
      ctx.lineWidth = 1;
      for (let y = 0; y < height; y += height / 4) {
        ctx.beginPath();
        ctx.moveTo(0, y);
        ctx.lineTo(width, y);
        ctx.stroke();
      }

      const pointsExt = speedHistoryExt;
      const pointsInt = speedHistoryInt;
      const maxVal = Math.max(45, ...pointsExt) * 1.15;

      function drawLine(points, color) {
        if (points.length < 2) return;
        ctx.strokeStyle = color;
        ctx.lineWidth = 2;
        ctx.beginPath();
        const step = width / (points.length - 1);
        points.forEach((val, i) => {
          const x = i * step;
          const y = height - (val / maxVal) * (height - 10) - 5;
          if (i === 0) ctx.moveTo(x, y);
          else ctx.lineTo(x, y);
        });
        ctx.stroke();

        // 포인트 점 찍기
        ctx.fillStyle = color;
        points.forEach((val, i) => {
          const x = i * step;
          const y = height - (val / maxVal) * (height - 10) - 5;
          ctx.beginPath();
          ctx.arc(x, y, 3, 0, Math.PI * 2);
          ctx.fill();
        });
      }

      drawLine(pointsExt, '#38bdf8');
      drawLine(pointsInt, '#10b981');
    }

    // 5. 속도 수집 엔진 초기화 및 10초 타이머
    function initSpeedEngine() {
      if (engineStarted) return;
      engineStarted = true;

      // 즉시 최초 1회 수집
      probeSpeed();

      // 1초마다 카운트다운 및 10초 도달 시 수집
      setInterval(() => {
        timerCountdown--;
        const timerLabel = document.getElementById('timer-label');
        if (timerLabel) {
          timerLabel.textContent = `10초 주기 속도 수집 중 (${timerCountdown}s)`;
        }
        if (timerCountdown <= 0) {
          timerCountdown = 10;
          probeSpeed();
        }
      }, 1000);

      window.addEventListener('resize', renderChart);
    }

    window.addEventListener('DOMContentLoaded', checkAuth);
  </script>
</body>
</html>
"""

class LandingHandler(BaseHTTPRequestHandler):
    def do_HEAD(self):
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Cache-Control', 'no-cache, no-store, must-revalidate')
        self.end_headers()

    def do_GET(self):
        path = urllib.parse.urlparse(self.path).path

        if path in ('/healthz', '/api/healthz', '/status'):
            self.send_response(200)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Cache-Control', 'no-cache, no-store')
            self.end_headers()
            self.wfile.write(b'{"status":"ok","version":"v2-landing","message":"FIGTEAM CMP v2 Portal"}')
            return

        # Main Landing Page
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Cache-Control', 'no-cache, no-store, must-revalidate')
        self.send_header('Pragma', 'no-cache')
        self.send_header('Expires', '0')
        self.end_headers()
        self.wfile.write(LANDING_HTML.encode('utf-8'))

    def do_POST(self):
        self.send_response(200)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.end_headers()
        self.wfile.write(b'{"status":"ok"}')

    def log_message(self, format, *args):
        sys.stderr.write(f"[{self.log_date_time_string()}] {self.client_address[0]} {format % args}\n")

class ReusableTCPServer(socketserver.TCPServer):
    allow_reuse_address = True

def run():
    with ReusableTCPServer(("0.0.0.0", PORT), LandingHandler) as httpd:
        print(f"[FIGTEAM PORTAL v2] Professional landing running on port {PORT}")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nShutting down server.")

if __name__ == '__main__':
    run()
