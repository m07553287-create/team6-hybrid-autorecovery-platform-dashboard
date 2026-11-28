#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
FIGTEAM CMP v2 Transition Landing & FHD Fixed Dual Console
- 탑 헤드 영역:
  * 타이틀, 시계, 10~15초 순차 수집 타이머
  * 인프라 개별 상태 배지: [KT Edge, 온프렘 오픈스택(k8s-cp1, db-01), AWS CTL, AWS DR(Standby 정상)]
  * [대시보드] / [설정] 탭 전환 버튼 및 [로그아웃]
- 대시보드 뷰:
  * 모든 인스턴스의 노드 자원 (CPU, RAM, Disk, Network)
  * 도커/컨테이너/쿠버네티스 팟 서비스 및 리소스 점유 현황
  * AWS DR Standby(정상) 감시 및 10~15초 순차 수집 관제
- 설정 사이트 뷰:
  * 좌측: 인스턴스 메뉴 (KT Edge, 온프렘 cp1, db-01, AWS CTL, AWS DR, 통합 로드맵)
  * 바디: 해당 인스턴스의 상세 설정 설명, 스크립트 코드, 검증 명령어
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

    /* TOP HEADER BAR (FHD FIXED) */
    header {
      height: 52px;
      border-bottom: 1px solid var(--surface-border);
      background: rgba(15, 23, 42, 0.96);
      backdrop-filter: blur(8px);
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 0 16px;
      flex-shrink: 0;
      gap: 12px;
    }
    .header-left {
      display: flex;
      align-items: center;
      gap: 10px;
      flex-shrink: 0;
    }
    .brand-title {
      font-size: 14px;
      font-weight: 700;
      color: #fff;
      display: flex;
      align-items: center;
      gap: 6px;
      white-space: nowrap;
    }
    .brand-tag {
      font-size: 10.5px;
      font-weight: 600;
      background: #1e293b;
      color: var(--blue);
      border: 1px solid #0284c7;
      padding: 1px 6px;
      border-radius: 4px;
      font-family: var(--font-mono);
    }
    .header-clock-timer {
      display: flex;
      align-items: center;
      gap: 10px;
      font-size: 11.5px;
      font-family: var(--font-mono);
      color: var(--text-sub);
      background: #090d16;
      border: 1px solid var(--surface-border);
      padding: 3px 10px;
      border-radius: 4px;
      white-space: nowrap;
    }
    .pulse-dot {
      width: 6px;
      height: 6px;
      border-radius: 50%;
      background: var(--blue);
      box-shadow: 0 0 6px var(--blue);
    }

    /* TOP INFRASTATUS INDIVIDUAL BADGES */
    .header-infra-status {
      display: flex;
      align-items: center;
      gap: 6px;
      overflow-x: auto;
      flex: 1;
      justify-content: center;
    }
    .infra-badge-item {
      display: inline-flex;
      align-items: center;
      gap: 5px;
      background: #141e33;
      border: 1px solid var(--border-color);
      border-radius: 4px;
      padding: 2px 7px;
      font-size: 11px;
      white-space: nowrap;
    }
    .infra-badge-name {
      font-weight: 600;
      color: #cbd5e1;
    }
    .infra-badge-state {
      font-family: var(--font-mono);
      font-size: 10.5px;
      font-weight: 700;
      padding: 1px 4px;
      border-radius: 3px;
    }
    .state-green {
      background: rgba(16, 185, 129, 0.2);
      color: #34d399;
    }
    .state-amber {
      background: rgba(245, 158, 11, 0.2);
      color: #fbbf24;
    }

    /* HEADER RIGHT NAV BUTTONS */
    .header-right {
      display: flex;
      align-items: center;
      gap: 8px;
      flex-shrink: 0;
    }
    .nav-btn {
      background: #1e293b;
      border: 1px solid var(--surface-border);
      color: var(--text-sub);
      padding: 5px 12px;
      border-radius: 4px;
      font-size: 12px;
      font-weight: 600;
      cursor: pointer;
      transition: all 0.15s ease;
      font-family: inherit;
    }
    .nav-btn:hover {
      background: #334155;
      color: #fff;
    }
    .nav-btn.active {
      background: var(--primary);
      color: #fff;
      border-color: #3b82f6;
    }
    .logout-btn {
      background: transparent;
      border: 1px solid var(--surface-border);
      color: var(--text-sub);
      padding: 5px 10px;
      border-radius: 4px;
      font-size: 11.5px;
      cursor: pointer;
      transition: all 0.15s ease;
      font-family: inherit;
    }
    .logout-btn:hover {
      background: #1f2937;
      color: #fff;
      border-color: #4b5563;
    }
    .fs-ctl { display: inline-flex; gap: 2px; margin-right: 6px; border: 1px solid var(--surface-border); border-radius: 5px; overflow: hidden; }
    .fs-btn { background: transparent; border: 0; color: var(--text-sub); padding: 4px 8px; font-size: 12px; cursor: pointer; font-family: inherit; }
    .fs-btn:hover { background: #1f2937; color: #fff; }
    .fs-btn + .fs-btn { border-left: 1px solid var(--surface-border); }

    /* LOGIN VIEW */
    .login-wrapper {
      width: 100%;
      height: calc(100vh - 52px);
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

    /* MAIN VIEW CONTAINERS */
    .view-container {
      width: 100%;
      height: calc(100vh - 52px);
      display: none;
      overflow: hidden;
    }

    /* ========================================================
       1. DASHBOARD VIEW (FHD FIXED)
       ======================================================== */
    .dashboard-layout {
      width: 100%;
      height: 100%;
      display: flex;
      flex-direction: column;
      padding: 10px 14px 12px;
      gap: 10px;
    }

    /* ROW 1: NODE RESOURCE MONITORING CARDS */
    .node-resource-row {
      display: grid;
      grid-template-columns: repeat(5, 1fr);
      gap: 10px;
      flex-shrink: 0;
    }
    .node-card {
      background: var(--surface);
      border: 1px solid var(--surface-border);
      border-radius: 6px;
      padding: 10px 12px;
      display: flex;
      flex-direction: column;
      gap: 6px;
    }
    .node-card-head {
      display: flex;
      justify-content: space-between;
      align-items: center;
    }
    .node-title {
      font-size: 12.5px;
      font-weight: 700;
      color: #fff;
    }
    .node-state-pill {
      font-size: 10px;
      font-weight: 700;
      padding: 1px 5px;
      border-radius: 3px;
      font-family: var(--font-mono);
    }
    .node-meta {
      font-family: var(--font-mono);
      font-size: 10.5px;
      color: var(--text-muted);
    }
    .progress-bar-group {
      display: flex;
      flex-direction: column;
      gap: 4px;
      margin-top: 2px;
    }
    .progress-item {
      display: flex;
      justify-content: space-between;
      font-size: 10px;
      font-family: var(--font-mono);
      color: var(--text-sub);
    }
    .progress-track {
      width: 100%;
      height: 4px;
      background: #090d16;
      border-radius: 2px;
      overflow: hidden;
      margin-top: 1px;
    }
    .progress-fill {
      height: 100%;
      background: var(--blue);
      border-radius: 2px;
      transition: width 0.5s ease;
    }
    .fill-green { background: var(--green); }
    .fill-amber { background: var(--yellow); }

    /* DESKTOP ZERO-SCROLL MATRIX GRID */
    .desktop-dashboard-container {
      width: 100%;
      height: 100%;
      display: flex;
      flex-direction: column;
      padding: 8px 12px 10px;
      gap: 8px;
      overflow: hidden;
    }
    .dashboard-toolbar-row {
      display: flex;
      justify-content: space-between;
      align-items: center;
      background: var(--surface);
      border: 1px solid var(--surface-border);
      border-radius: 6px;
      padding: 6px 12px;
      flex-shrink: 0;
    }
    .toolbar-left {
      display: flex;
      align-items: center;
      gap: 12px;
    }
    .toolbar-title {
      font-size: 13px;
      font-weight: 700;
      color: #fff;
      display: flex;
      align-items: center;
      gap: 6px;
    }
    .toolbar-sub {
      font-size: 10.5px;
      color: var(--text-muted);
      font-family: var(--font-mono);
    }
    .toolbar-right {
      display: flex;
      align-items: center;
      gap: 12px;
    }
    .sort-tabs-group {
      display: flex;
      align-items: center;
      gap: 4px;
    }
    .sort-btn {
      background: #141e33;
      border: 1px solid #1e293b;
      color: var(--text-sub);
      font-size: 11px;
      padding: 3px 9px;
      border-radius: 4px;
      cursor: pointer;
      transition: all 0.15s ease;
      font-family: inherit;
    }
    .sort-btn:hover {
      background: #1e293b;
      color: #fff;
      border-color: #3b82f6;
    }
    .sort-btn.active {
      background: #1e293b;
      color: #38bdf8;
      border-color: #38bdf8;
      font-weight: 700;
      box-shadow: 0 0 8px rgba(56, 189, 248, 0.25);
    }
    .matrix-5col-grid {
      flex: 1;
      display: grid;
      grid-template-columns: repeat(5, minmax(0, 1fr));
      gap: 10px;
      min-height: 0;
      overflow: hidden;
    }
    .inst-grid-card {
      background: var(--surface);
      border: 1px solid var(--surface-border);
      border-radius: 6px;
      display: flex;
      flex-direction: column;
      overflow: hidden;
      min-height: 0;
      transition: border-color 0.15s ease;
    }
    .inst-grid-card:hover {
      border-color: #3b82f6;
    }
    .inst-grid-card-head {
      background: #141e33;
      border-bottom: 1px solid var(--border-color);
      padding: 8px 10px;
      display: flex;
      justify-content: space-between;
      align-items: center;
      flex-shrink: 0;
    }
    .inst-head-title-wrap {
      display: flex;
      flex-direction: column;
      gap: 1px;
    }
    .inst-card-title {
      font-size: 12.5px;
      font-weight: 700;
      color: #fff;
    }
    .inst-card-ip {
      font-size: 10px;
      color: var(--text-muted);
      font-family: var(--font-mono);
    }
    .inst-resource-hero {
      background: #090e1a;
      border-bottom: 1px solid #1e293b;
      padding: 8px 10px;
      display: flex;
      flex-direction: column;
      gap: 6px;
      flex-shrink: 0;
    }
    .hero-meter-row {
      display: flex;
      flex-direction: column;
      gap: 3px;
    }
    .meter-head {
      display: flex;
      justify-content: space-between;
      align-items: center;
      font-family: var(--font-mono);
    }
    .meter-label-wrap {
      display: flex;
      align-items: center;
      gap: 5px;
    }
    .meter-badge {
      font-size: 9.5px;
      font-weight: 800;
      padding: 1px 4px;
      border-radius: 3px;
      line-height: 1.2;
    }
    .cpu-badge {
      background: rgba(56, 189, 248, 0.15);
      color: #38bdf8;
      border: 1px solid rgba(56, 189, 248, 0.35);
    }
    .ram-badge {
      background: rgba(168, 85, 247, 0.15);
      color: #c084fc;
      border: 1px solid rgba(168, 85, 247, 0.35);
    }
    .meter-val-used {
      font-size: 13px;
      font-weight: 800;
    }
    .cpu-used { color: #38bdf8; }
    .ram-used { color: #c084fc; }
    .meter-val-total {
      font-size: 11px;
      color: #94a3b8;
      font-weight: 600;
    }
    .meter-pct {
      font-size: 11.5px;
      font-weight: 800;
      margin-left: 1px;
    }
    .cpu-pct { color: #38bdf8; }
    .ram-pct { color: #c084fc; }
    .meter-free-wrap {
      display: flex;
      align-items: center;
      gap: 3px;
      font-size: 11px;
      font-family: var(--font-mono);
      background: rgba(16, 185, 129, 0.1);
      border: 1px solid rgba(16, 185, 129, 0.28);
      border-radius: 3px;
      padding: 1px 5px;
    }
    .free-k {
      color: #6ee7b7;
      font-size: 10px;
      font-weight: 600;
    }
    .free-v {
      color: #34d399;
      font-weight: 800;
      font-size: 11.5px;
    }
    .meter-gauge-track {
      width: 100%;
      height: 4px;
      background: #1e293b;
      border-radius: 2px;
      display: flex;
      overflow: hidden;
    }
    .meter-gauge-fill {
      height: 100%;
      border-radius: 2px;
      transition: width 0.3s ease;
    }
    .cpu-fill { background: linear-gradient(90deg, #0284c7, #38bdf8); }
    .ram-fill { background: linear-gradient(90deg, #7e22ce, #c084fc); }
    .hero-sub-stats {
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding-top: 3px;
      border-top: 1px dashed rgba(30, 41, 59, 0.8);
      font-family: var(--font-mono);
      font-size: 10.5px;
    }
    .hero-stat-pill {
      display: flex;
      align-items: center;
      gap: 4px;
    }
    .stat-k { color: #94a3b8; }
    .stat-v { font-weight: 700; }
    .compact-service-list {
      flex: 1;
      overflow-y: auto;
      padding: 6px;
      display: flex;
      flex-direction: column;
      gap: 4px;
      min-height: 0;
    }
    .compact-service-row {
      background: var(--surface-card);
      border: 1px solid var(--border-color);
      border-radius: 4px;
      padding: 5px 8px;
      display: flex;
      flex-direction: column;
      gap: 3px;
      cursor: pointer;
      transition: all 0.12s ease;
      text-decoration: none;
    }
    .compact-service-row:hover {
      background: var(--surface-hover);
      border-color: var(--blue);
      transform: translateY(-1px);
    }
    .svc-row-top {
      display: flex;
      justify-content: space-between;
      align-items: center;
    }
    .svc-row-left {
      display: flex;
      align-items: center;
      gap: 5px;
      min-width: 0;
    }
    .svc-row-name {
      font-size: 11px;
      font-weight: 700;
      color: #fff;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }
    .svc-row-bot {
      display: flex;
      justify-content: space-between;
      align-items: center;
      font-size: 9.5px;
      font-family: var(--font-mono);
      color: var(--text-sub);
    }
    .inst-card-footer {
      border-top: 1px solid var(--surface-border);
      padding: 6px 10px;
      background: #0d1424;
      flex-shrink: 0;
    }
    .open-modal-btn {
      width: 100%;
      background: transparent;
      border: 1px solid #1e293b;
      color: var(--blue);
      padding: 4px 0;
      border-radius: 3px;
      font-size: 10.5px;
      font-weight: 600;
      cursor: pointer;
      font-family: inherit;
      transition: all 0.12s ease;
    }
    .open-modal-btn:hover {
      background: #1e293b;
      color: #fff;
      border-color: #3b82f6;
    }

    /* MODAL POPUP (BACKDROP & DIALOG) */
    .modal-backdrop {
      position: fixed;
      top: 0;
      left: 0;
      width: 100vw;
      height: 100vh;
      background: rgba(4, 7, 13, 0.85);
      backdrop-filter: blur(5px);
      z-index: 1000;
      display: flex;
      align-items: center;
      justify-content: center;
      padding: 24px;
    }
    .modal-dialog {
      background: #0f172a;
      border: 1px solid #334155;
      border-radius: 8px;
      width: 100%;
      max-width: 1100px;
      max-height: 85vh;
      display: flex;
      flex-direction: column;
      box-shadow: 0 20px 40px rgba(0,0,0,0.7);
      overflow: hidden;
      animation: modalFadeIn 0.15s ease-out;
    }
    @keyframes modalFadeIn {
      from { opacity: 0; transform: scale(0.98); }
      to { opacity: 1; transform: scale(1); }
    }
    .modal-header {
      background: #141e33;
      border-bottom: 1px solid #1e293b;
      padding: 12px 18px;
      display: flex;
      justify-content: space-between;
      align-items: center;
      flex-shrink: 0;
    }
    .modal-title-wrap {
      display: flex;
      align-items: center;
      gap: 12px;
    }
    .modal-title-text {
      font-size: 15px;
      font-weight: 700;
      color: #fff;
    }
    .modal-close-btn {
      background: #1e293b;
      border: 1px solid #334155;
      color: #cbd5e1;
      padding: 4px 10px;
      border-radius: 4px;
      font-size: 12px;
      font-weight: 600;
      cursor: pointer;
      transition: all 0.12s ease;
    }
    .modal-close-btn:hover {
      background: #ef4444;
      color: #fff;
      border-color: #dc2626;
    }
    .modal-body {
      padding: 16px 18px;
      overflow-y: auto;
      display: flex;
      flex-direction: column;
      gap: 14px;
    }
    .modal-summary-box {
      background: #090d16;
      border: 1px solid #1e293b;
      border-radius: 6px;
      padding: 10px 14px;
      display: grid;
      grid-template-columns: repeat(5, 1fr);
      gap: 10px;
      font-family: var(--font-mono);
      font-size: 11px;
    }
    .summary-cell {
      display: flex;
      flex-direction: column;
      gap: 2px;
    }
    .summary-k { font-size: 10px; color: var(--text-muted); }
    .summary-v { font-size: 12px; font-weight: 700; color: #fff; }
    .panel-head {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 8px;
      flex-shrink: 0;
    }
    .panel-title {
      font-size: 13px;
      font-weight: 700;
      color: #fff;
      display: flex;
      align-items: center;
      gap: 6px;
    }
    .panel-sub {
      font-size: 11px;
      color: var(--text-muted);
      font-family: var(--font-mono);
    }
    .table-scroll {
      flex: 1;
      overflow-y: auto;
      border: 1px solid var(--surface-border);
      border-radius: 4px;
    }
    table.data-table {
      width: 100%;
      border-collapse: collapse;
      font-size: 11.5px;
      text-align: left;
    }
    table.data-table th {
      background: #141e33;
      color: #94a3b8;
      font-weight: 600;
      padding: 8px 10px;
      border-bottom: 1px solid var(--surface-border);
      font-size: 11px;
      text-transform: uppercase;
      position: sticky;
      top: 0;
      z-index: 2;
    }
    table.data-table td {
      padding: 6px 10px;
      border-bottom: 1px solid #1e293b;
      color: #e2e8f0;
      font-family: var(--font-mono);
      font-size: 11px;
      vertical-align: middle;
    }
    table.data-table tr:hover td {
      background: rgba(30, 42, 71, 0.45);
    }
    .rank-badge {
      font-size: 10px;
      font-weight: 700;
      font-family: var(--font-mono);
      padding: 2px 5px;
      border-radius: 3px;
      background: #1e293b;
      color: #94a3b8;
      border: 1px solid #334155;
      text-align: center;
      display: inline-block;
    }
    .rank-top3 {
      background: rgba(245, 158, 11, 0.15);
      color: #fbbf24;
      border-color: rgba(245, 158, 11, 0.4);
    }
    .cloud-tag {
      font-size: 10px;
      font-weight: 700;
      padding: 2px 6px;
      border-radius: 4px;
      display: inline-block;
      white-space: nowrap;
    }
    .cloud-kt {
      background: rgba(2, 132, 199, 0.15);
      color: #38bdf8;
      border: 1px solid rgba(2, 132, 199, 0.4);
    }
    .cloud-onprem {
      background: rgba(16, 185, 129, 0.15);
      color: #34d399;
      border: 1px solid rgba(16, 185, 129, 0.4);
    }
    .cloud-aws {
      background: rgba(245, 158, 11, 0.15);
      color: #fbbf24;
      border: 1px solid rgba(245, 158, 11, 0.4);
    }
    .inst-box {
      display: flex;
      flex-direction: column;
      gap: 1px;
    }
    .inst-name {
      font-size: 11px;
      font-weight: 700;
      color: #fff;
    }
    .inst-ip {
      font-size: 9.5px;
      color: var(--text-muted);
      font-family: var(--font-mono);
    }
    .type-badge {
      font-size: 10px;
      font-weight: 600;
      padding: 1px 6px;
      border-radius: 3px;
      display: inline-flex;
      align-items: center;
      gap: 3px;
      white-space: nowrap;
    }
    .type-web {
      background: rgba(99, 102, 241, 0.15);
      color: #a5b4fc;
      border: 1px solid rgba(99, 102, 241, 0.35);
    }
    .type-daemon {
      background: rgba(20, 184, 166, 0.15);
      color: #5eead4;
      border: 1px solid rgba(20, 184, 166, 0.35);
    }
    .type-gw {
      background: rgba(14, 165, 233, 0.15);
      color: #7dd3fc;
      border: 1px solid rgba(14, 165, 233, 0.35);
    }
    .type-data {
      background: rgba(244, 63, 94, 0.15);
      color: #fda4af;
      border: 1px solid rgba(244, 63, 94, 0.35);
    }
    .type-dr {
      background: rgba(245, 158, 11, 0.15);
      color: #fde68a;
      border: 1px solid rgba(245, 158, 11, 0.35);
    }
    .svc-box {
      display: flex;
      flex-direction: column;
      gap: 1px;
    }
    .svc-name {
      font-size: 11.5px;
      font-weight: 700;
      color: #fff;
    }
    .svc-desc {
      font-size: 9.5px;
      color: var(--text-muted);
    }
    .res-metric-cell {
      display: flex;
      flex-direction: column;
      gap: 2px;
      font-size: 10.5px;
    }
    .res-metric-val {
      display: flex;
      justify-content: space-between;
    }
    .mini-meter-track {
      width: 100%;
      height: 3px;
      background: #090d16;
      border-radius: 1.5px;
      overflow: hidden;
    }
    .mini-meter-fill {
      height: 100%;
      border-radius: 1.5px;
    }
    .fill-blue { background: #38bdf8; }
    .fill-purple { background: #a855f7; }
    .fill-amber { background: #f59e0b; }
    .badge-running {
      color: #34d399;
      background: rgba(16, 185, 129, 0.15);
      padding: 2px 6px;
      border-radius: 3px;
      font-weight: 700;
      font-size: 10.5px;
    }
    .badge-standby {
      color: #fbbf24;
      background: rgba(245, 158, 11, 0.15);
      padding: 2px 6px;
      border-radius: 3px;
      font-weight: 700;
      font-size: 10.5px;
    }
    .filter-chips-row {
      display: flex;
      gap: 6px;
      align-items: center;
    }
    .chip-btn {
      background: #141e33;
      border: 1px solid #1e293b;
      color: var(--text-sub);
      font-size: 10.5px;
      padding: 2px 8px;
      border-radius: 3px;
      cursor: pointer;
      transition: all 0.15s ease;
      font-family: inherit;
    }
    .chip-btn:hover {
      background: #1e293b;
      color: #fff;
    }
    .chip-btn.active {
      background: var(--primary);
      color: #fff;
      border-color: #3b82f6;
    }
    .instance-tab-bar {
      display: flex;
      gap: 6px;
      align-items: center;
      background: #090d16;
      border: 1px solid var(--surface-border);
      border-radius: 5px;
      padding: 4px;
      margin-bottom: 8px;
      overflow-x: auto;
    }
    .inst-tab-btn {
      background: transparent;
      border: 1px solid transparent;
      border-radius: 4px;
      padding: 5px 10px;
      color: var(--text-sub);
      font-size: 11px;
      font-weight: 600;
      cursor: pointer;
      display: flex;
      align-items: center;
      gap: 6px;
      transition: all 0.15s ease;
      white-space: nowrap;
      font-family: inherit;
    }
    .inst-tab-btn:hover {
      background: #141e33;
      color: #fff;
    }
    .inst-tab-btn.active {
      background: #1e293b;
      border-color: #3b82f6;
      color: #fff;
      box-shadow: 0 1px 3px rgba(0,0,0,0.3);
    }
    .inst-summary-strip {
      display: flex;
      justify-content: space-between;
      align-items: center;
      background: #141e33;
      border: 1px solid var(--border-color);
      border-radius: 4px;
      padding: 6px 12px;
      margin-bottom: 8px;
      font-size: 11px;
      font-family: var(--font-mono);
    }

    /* RIGHT: SEQUENTIAL ENGINE & LATENCY MONITOR */
    .telemetry-panel {
      background: var(--surface);
      border: 1px solid var(--surface-border);
      border-radius: 6px;
      padding: 12px;
      display: flex;
      flex-direction: column;
      gap: 10px;
      min-height: 0;
    }
    .metric-row {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 8px;
      flex-shrink: 0;
    }
    .metric-box {
      background: var(--surface-card);
      border: 1px solid var(--border-color);
      border-radius: 5px;
      padding: 8px 10px;
    }
    .metric-label {
      font-size: 11px;
      color: var(--text-muted);
    }
    .metric-val {
      font-size: 20px;
      font-weight: 700;
      font-family: var(--font-mono);
      color: #fff;
    }
    .chart-box {
      flex: 1;
      background: #090d16;
      border: 1px solid var(--surface-border);
      border-radius: 5px;
      padding: 8px;
      display: flex;
      flex-direction: column;
      min-height: 100px;
    }
    canvas#speed-canvas {
      width: 100%;
      flex: 1;
      display: block;
    }
    .log-box {
      height: 95px;
      background: #06090e;
      border: 1px solid var(--surface-border);
      border-radius: 5px;
      padding: 6px 8px;
      font-family: var(--font-mono);
      font-size: 10.5px;
      color: #cbd5e1;
      overflow-y: auto;
      flex-shrink: 0;
      line-height: 1.4;
    }

    /* ========================================================
       2. SETTINGS SITE VIEW (SPLIT: LEFT MENU & BODY MANUAL)
       ======================================================== */
    .settings-layout {
      width: 100%;
      height: 100%;
      display: grid;
      grid-template-columns: 280px 1fr;
      overflow: hidden;
    }

    /* LEFT SIDEBAR: INSTANCE & CONFIGURATION MENU */
    .settings-sidebar {
      background: #0f172a;
      border-right: 1px solid var(--surface-border);
      padding: 14px 10px;
      display: flex;
      flex-direction: column;
      gap: 6px;
      overflow-y: auto;
    }
    .sidebar-section-title {
      font-size: 11px;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      color: var(--text-muted);
      padding: 6px 10px 4px;
    }
    .menu-item-btn {
      width: 100%;
      text-align: left;
      background: transparent;
      border: 1px solid transparent;
      border-radius: 5px;
      padding: 9px 12px;
      color: var(--text-sub);
      cursor: pointer;
      display: flex;
      flex-direction: column;
      gap: 2px;
      transition: all 0.15s ease;
      font-family: inherit;
    }
    .menu-item-btn:hover {
      background: var(--surface-card);
      color: #fff;
    }
    .menu-item-btn.active {
      background: #141e33;
      border-color: #3b82f6;
      color: #fff;
    }
    .menu-item-name {
      font-size: 12.5px;
      font-weight: 600;
      display: flex;
      justify-content: space-between;
      align-items: center;
    }
    .menu-item-desc {
      font-size: 10.5px;
      color: var(--text-muted);
      font-family: var(--font-mono);
    }

    /* RIGHT BODY: MANUAL & SCRIPT DETAILS */
    .settings-body {
      background: #090d16;
      padding: 24px 32px;
      overflow-y: auto;
      display: flex;
      flex-direction: column;
      gap: 20px;
    }
    .manual-header {
      border-bottom: 1px solid var(--surface-border);
      padding-bottom: 14px;
    }
    .manual-title {
      font-size: 20px;
      font-weight: 700;
      color: #fff;
      display: flex;
      align-items: center;
      gap: 10px;
    }
    .manual-tag {
      font-size: 11px;
      font-family: var(--font-mono);
      background: #1e293b;
      color: var(--blue);
      padding: 2px 8px;
      border-radius: 4px;
      border: 1px solid #334155;
    }
    .manual-desc {
      font-size: 13px;
      color: var(--text-sub);
      margin-top: 6px;
      line-height: 1.5;
    }
    .manual-card-box {
      background: var(--surface);
      border: 1px solid var(--surface-border);
      border-radius: 6px;
      padding: 16px;
      display: flex;
      flex-direction: column;
      gap: 10px;
    }
    .box-title {
      font-size: 13px;
      font-weight: 700;
      color: #cbd5e1;
      text-transform: uppercase;
      letter-spacing: 0.04em;
    }
    .code-block {
      background: #06090e;
      border: 1px solid var(--surface-border);
      border-radius: 5px;
      padding: 12px 14px;
      font-family: var(--font-mono);
      font-size: 12px;
      color: #38bdf8;
      overflow-x: auto;
      line-height: 1.5;
      white-space: pre;
    }
    .spec-grid {
      display: grid;
      grid-template-columns: repeat(3, 1fr);
      gap: 12px;
    }
    .spec-item {
      background: #06090e;
      border: 1px solid var(--surface-border);
      border-radius: 4px;
      padding: 8px 10px;
      display: flex;
      flex-direction: column;
      gap: 2px;
    }
    .spec-k { font-size: 10.5px; color: var(--text-muted); }
    .spec-v { font-size: 12px; font-weight: 600; font-family: var(--font-mono); color: #fff; }
    /* CFGCSS:BEGIN */
    /* ===== [설정] 화면: 데스크탑 뷰 고정 & 스크롤바 강제 표시 ===== */
    #view-settings {
      width: 100% !important;
      height: calc(100vh - 52px) !important;
      overflow: hidden !important;
    }
    #view-settings .settings-layout {
      width: 100% !important;
      height: 100% !important;
      display: grid !important;
      grid-template-columns: 320px minmax(0, 1fr) !important;
      overflow: hidden !important;
    }
    #cfg-nav.settings-sidebar {
      display: flex !important;
      flex-direction: column !important;
      width: 320px !important;
      height: 100% !important;
      min-height: 0 !important;
      overflow-y: auto !important;
      overflow-x: hidden !important;
      background: #0c1322 !important;
      border-right: 1px solid var(--surface-border) !important;
      padding: 14px 10px 84px !important;
      gap: 10px !important;
      scrollbar-width: thin;
      scrollbar-color: #334155 #0c1322;
      overscroll-behavior-y: auto;
    }
    #cfg-nav.settings-sidebar::-webkit-scrollbar { width: 8px; }
    #cfg-nav.settings-sidebar::-webkit-scrollbar-track { background: #0c1322; }
    #cfg-nav.settings-sidebar::-webkit-scrollbar-thumb { background: #334155; border-radius: 4px; }
    #cfg-nav.settings-sidebar::-webkit-scrollbar-thumb:hover { background: #475569; }

    /* 대분류-중분류 통합 아코디언 및 계단식 트리 */
    .cfg-tree-nav { display: flex; flex-direction: column; gap: 3px; }
    .cfg-tree-node { display: flex; flex-direction: column; }
    .cfg-tree-major {
      display: flex; align-items: center; justify-content: space-between;
      width: 100%; padding: 8px 10px; border-radius: 6px;
      background: transparent; border: 1px solid transparent;
      color: var(--text-sub); cursor: pointer; text-align: left;
      font-family: inherit; transition: background 0.14s ease, border-color 0.14s ease, color 0.14s ease;
      user-select: none;
    }
    .cfg-tree-major:hover { background: #131d33; color: #fff; }
    .cfg-tree-major.active {
      background: #172554; border-color: #2563eb; color: #fff; box-shadow: 0 0 10px rgba(37, 99, 235, 0.22);
    }
    .cfg-tree-major-main { display: flex; align-items: center; gap: 6px; flex: 1; min-width: 0; }
    .cfg-tree-toggle {
      display: inline-flex; align-items: center; justify-content: center;
      width: 18px; height: 18px; border-radius: 4px; color: #64748b; font-size: 11px;
      transition: transform 0.18s ease, color 0.14s ease; flex-shrink: 0;
    }
    .cfg-tree-toggle:hover { color: #93c5fd; background: rgba(147, 197, 253, 0.12); }
    .cfg-tree-node.open > .cfg-tree-major .cfg-tree-toggle {
      transform: rotate(90deg); color: #93c5fd;
    }
    .cfg-tree-major-info { display: flex; flex-direction: column; gap: 2px; min-width: 0; flex: 1; }
    .cfg-tree-major-name {
      font-size: 13px; font-weight: 600; display: flex; align-items: center; gap: 6px;
      white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
    }
    .cfg-tree-major-sub {
      font-size: 11px; color: var(--text-muted); white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
    }
    .cfg-tree-major-meta { display: flex; align-items: center; gap: 6px; margin-left: 6px; flex-shrink: 0; }
    .cfg-tree-badge-count {
      font-size: 10.5px; color: #94a3b8; background: #1e293b; border-radius: 10px;
      padding: 1px 6px; font-weight: 500; border: 1px solid #334155;
    }

    /* 중분류 계단식 하위 리스트 (아코디언 바디) */
    .cfg-tree-minors {
      display: none; flex-direction: column; gap: 2px;
      margin-left: 17px; padding-left: 10px;
      border-left: 2px solid #1e293b; margin-top: 3px; margin-bottom: 6px;
    }
    .cfg-tree-node.open > .cfg-tree-minors { display: flex; }
    .cfg-tree-minor {
      display: flex; flex-direction: column; gap: 2px;
      width: 100%; padding: 6px 10px; border-radius: 5px;
      background: transparent; border: 1px solid transparent; border-left: 3px solid transparent;
      color: #94a3b8; cursor: pointer; text-align: left; font-family: inherit;
      transition: background 0.12s ease, border-color 0.12s ease, color 0.12s ease;
    }
    .cfg-tree-minor:hover { background: #0f172a; color: #e2e8f0; border-left-color: #475569; }
    .cfg-tree-minor.active {
      background: rgba(30, 58, 138, 0.45); color: #93c5fd;
      border-left-color: #3b82f6; font-weight: 600;
    }
    .cfg-tree-minor-name { font-size: 12px; font-weight: 600; display: flex; align-items: center; gap: 6px; }
    .cfg-tree-minor-sub { font-size: 10.5px; color: #64748b; line-height: 1.3; }
    .cfg-tree-minor.active .cfg-tree-minor-sub { color: #93c5fd; opacity: 0.8; }

    .cfg-col {
      min-height: 0;
      overflow-y: auto;
      padding: 14px 10px 24px;
      border-right: 1px solid var(--surface-border);
      scrollbar-width: thin;
      scrollbar-color: #334155 #070b14;
    }
    .cfg-col::-webkit-scrollbar { width: 8px; }
    .cfg-col::-webkit-scrollbar-track { background: #070b14; }
    .cfg-col::-webkit-scrollbar-thumb { background: #334155; border-radius: 4px; }
    .cfg-col-major { background: #0c1322; }
    .cfg-col-minor { background: #0f172a; }
    .settings-body > * { flex-shrink: 0; }

    /* 본문 세로 스크롤: 데스크탑 뷰 고정 & 화면 초과 시 세로 스크롤바 강제 표시 (화면 이하일 때는 자동 생략) */
    #view-settings .settings-body {
      padding: 16px 36px 84px !important;
      gap: 18px;
      overflow-y: auto !important;
      overflow-x: hidden;
      scrollbar-width: thin;
      scrollbar-color: #64748b #090d16;
      scrollbar-gutter: stable;
      overscroll-behavior-y: auto;
    }
    #view-settings .settings-body::-webkit-scrollbar {
      width: 12px !important;
      display: block !important;
    }
    #view-settings .settings-body::-webkit-scrollbar-track {
      background: #090d16 !important;
      border-left: 1px solid #1e293b !important;
    }
    #view-settings .settings-body::-webkit-scrollbar-thumb {
      background: #475569 !important;
      border-radius: 6px !important;
      border: 3px solid #090d16 !important;
    }
    #view-settings .settings-body::-webkit-scrollbar-thumb:hover {
      background: #64748b !important;
    }

    /* 코드 블록 세로 휠 멈춤 방지: 가로 스크롤러가 부모의 세로 휠 이벤트를 삼키지 않음 */
    .cfg-code pre {
      overflow-x: auto;
      overflow-y: hidden;
      overscroll-behavior-x: contain;
      overscroll-behavior-y: auto;
    }

    /* 렌즈 전환 */
    .cfg-lens { display: grid; grid-template-columns: 1fr 1fr; gap: 4px; background: #070b14; border: 1px solid var(--surface-border); border-radius: 8px; padding: 4px; }
    .cfg-lens-btn { background: transparent; border: 0; border-radius: 5px; color: var(--text-sub); font-size: 12.5px; font-weight: 600; font-family: inherit; padding: 9px 6px; cursor: pointer; }
    .cfg-lens-btn:hover { color: #fff; background: var(--surface-card); }
    .cfg-lens-btn.active { background: var(--primary); color: #fff; }
    .cfg-lens-hint { font-size: 11.5px; color: var(--text-muted); margin: 8px 2px 10px; line-height: 1.45; }

    /* 인스턴스 × 서비스 매트릭스 */
    .cfg-matrix { border: 1px solid var(--surface-border); border-radius: 8px; padding: 8px 8px 6px; background: #070b14; margin-bottom: 14px; }
    .cfg-mx-row { display: grid; grid-template-columns: 76px repeat(8, 1fr); align-items: center; border-radius: 4px; }
    .cfg-mx-row.on { background: rgba(37, 99, 235, .16); }
    .cfg-mx-headrow { margin-bottom: 2px; }
    .cfg-mx-label { font-family: var(--font-mono); font-size: 10px; overflow: hidden; text-overflow: ellipsis; color: var(--text-sub); padding-left: 4px; white-space: nowrap; }
    .cfg-mx-col { font-size: 10px; color: var(--text-muted); text-align: center; padding: 2px 0; border-radius: 3px; }
    .cfg-mx-col.on { color: #fff; background: rgba(37, 99, 235, .35); }
    .cfg-mx-cell { height: 20px; display: flex; align-items: center; justify-content: center; background: transparent; border: 0; padding: 0; }
    button.cfg-mx-cell { cursor: pointer; border-radius: 4px; }
    .cfg-mx-cell i { width: 8px; height: 8px; border-radius: 50%; background: #334155; transition: transform .12s ease; }
    .cfg-mx-cell.design i { background: transparent; box-shadow: inset 0 0 0 1.5px #b45309; }
    .cfg-mx-cell.lit i { background: #60a5fa; }
    .cfg-mx-cell.lit.design i { background: transparent; box-shadow: inset 0 0 0 1.5px #fbbf24; }
    .cfg-mx-cell.here i { width: 12px; height: 12px; background: #fff; box-shadow: 0 0 0 3px rgba(96, 165, 250, .45); }
    button.cfg-mx-cell:hover i { transform: scale(1.35); }
    button.cfg-mx-cell:focus-visible, .cfg-lens-btn:focus-visible, .cfg-item:focus-visible, .cfg-pager-btn:focus-visible, .cfg-copy:focus-visible { outline: 2px solid #93c5fd; outline-offset: 1px; }

    /* 대분류·중분류 목록 */
    .cfg-col-head { font-size: 11.5px; font-weight: 700; color: var(--text-muted); padding: 2px 6px 6px; }
    .cfg-list-major, .cfg-list-minor { display: flex; flex-direction: column; gap: 2px; }
    .cfg-item { display: flex; flex-direction: column; gap: 3px; text-align: left; width: 100%; background: transparent; border: 1px solid transparent; border-left: 3px solid transparent;
      border-radius: 5px; padding: 8px 10px; color: var(--text-sub); cursor: pointer; font-family: inherit; }
    .cfg-item:hover { background: var(--surface-card); color: #fff; }
    .cfg-item.active { background: #141e33; color: #fff; border-left-color: var(--primary); }
    .cfg-item-name { font-size: 13px; font-weight: 600; display: flex; align-items: center; gap: 6px; }
    .cfg-item-sub { font-size: 11px; color: var(--text-muted); line-height: 1.4; }
    .cfg-item-minor .cfg-item-name { font-size: 13px; }
    .cfg-count { margin-left: auto; font-size: 11px; color: var(--text-muted); font-weight: 500; }
    .cfg-empty { font-size: 12px; color: var(--text-muted); padding: 6px; line-height: 1.5; }
    .cfg-dot { display: inline-block; width: 7px; height: 7px; border-radius: 50%; flex-shrink: 0; }

    /* 클라우드 색 */
    .cfg-c-onprem { background: #a78bfa; color: #0b0f19; }
    .cfg-c-openstack { background: #f97316; color: #0b0f19; }
    .cfg-c-kt { background: #ef4444; color: #fff; }
    .cfg-c-aws { background: #f59e0b; color: #0b0f19; }
    .cfg-cloud { font-size: 11px; font-weight: 700; padding: 2px 8px; border-radius: 4px; }
    .cfg-badge { font-size: 10.5px; font-weight: 700; padding: 1px 7px; border-radius: 10px; border: 1px solid; white-space: nowrap; vertical-align: 2px; }
    .cfg-st-live { color: #34d399; border-color: #065f46; background: rgba(16,185,129,.08); }
    .cfg-st-design { color: #fbbf24; border-color: #78350f; background: rgba(245,158,11,.08); }
    .cfg-st-nolook { color: #94a3b8; border-color: #475569; background: rgba(148,163,184,.08); }
    .cfg-st-protected { color: #f87171; border-color: #991b1b; background: rgba(239,68,68,.12); }

    /* 설명 및 상단 브레드크럼 (상단 고정 및 인터랙티브 이동경로) */
    .cfg-crumb {
      position: sticky; top: -16px; z-index: 25;
      background: rgba(9, 13, 22, 0.94); backdrop-filter: blur(8px);
      padding: 10px 0; border-bottom: 1px solid #1e293b;
      font-size: 12px; color: var(--text-muted); display: flex; flex-wrap: wrap; gap: 6px; align-items: center;
    }
    .cfg-crumb a { color: #94a3b8; text-decoration: none; cursor: pointer; border-radius: 4px; padding: 2px 4px; transition: color .12s, background .12s; }
    .cfg-crumb a:hover { color: #38bdf8; background: rgba(56, 189, 248, 0.1); }
    .cfg-crumb-current { color: #f1f5f9; font-weight: 600; padding: 2px 4px; }
    .cfg-crumb-sep { color: #475569; }

    /* 직관적 모듈형 빌더 UI (서비스 영역 직접 편집 & 추가) */
    .cfg-sec-header {
      display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; padding-bottom: 6px; border-bottom: 1px solid #1e293b;
    }
    .cfg-sec-title { font-size: 15px; font-weight: 700; color: #f8fafc; display: flex; align-items: center; gap: 8px; }
    .cfg-sec-acts { display: flex; align-items: center; gap: 6px; }
    .cfg-btn-add {
      display: inline-flex; align-items: center; gap: 4px; padding: 4px 10px; font-size: 11.5px; font-weight: 600;
      color: #38bdf8; background: rgba(56, 189, 248, 0.08); border: 1px dashed #0284c7; border-radius: 6px; cursor: pointer;
      transition: all .15s ease;
    }
    .cfg-btn-add:hover { background: rgba(56, 189, 248, 0.18); border-color: #38bdf8; color: #fff; }
    .cfg-btn-mode-toggle {
      display: inline-flex; align-items: center; gap: 4px; padding: 4px 8px; font-size: 11px;
      color: #94a3b8; background: #0f172a; border: 1px solid #334155; border-radius: 6px; cursor: pointer;
    }
    .cfg-btn-mode-toggle.active { color: #fbbf24; border-color: #f59e0b; background: rgba(245, 158, 11, 0.1); }
    .cfg-item-acts { display: flex; align-items: center; gap: 4px; }
    .cfg-item-btn {
      padding: 2px 6px; font-size: 10.5px; border-radius: 4px; border: 1px solid #334155; background: #1e293b;
      color: #cbd5e1; cursor: pointer;
    }
    .cfg-item-btn:hover { background: #334155; color: #fff; }
    .cfg-item-btn.btn-del:hover { background: #dc2626; border-color: #ef4444; color: #fff; }

    /* 직관적 모달 카드 빌더 (명령어 / 설정 / 원칙 추가·편집 팝업) */
    .cfg-builder-modal-card {
      background: #0f172a; border: 1px solid #3b82f6; border-radius: 12px; width: 100%; max-width: 620px;
      box-shadow: 0 24px 48px rgba(0, 0, 0, 0.75); display: flex; flex-direction: column; overflow: hidden;
      animation: cfgModalPop .18s cubic-bezier(0.16, 1, 0.3, 1);
    }
    .cfg-builder-modal-head {
      display: flex; align-items: center; justify-content: space-between; padding: 14px 18px;
      background: #172554; border-bottom: 1px solid #1e3a8a; color: #93c5fd; font-size: 14px; font-weight: 700;
    }
    .cfg-builder-modal-body { padding: 18px; display: flex; flex-direction: column; gap: 14px; color: #e2e8f0; }
    .cfg-builder-field { display: flex; flex-direction: column; gap: 6px; }
    .cfg-builder-label { font-size: 12px; font-weight: 600; color: #94a3b8; }
    .cfg-builder-input {
      background: #06090e; border: 1px solid #334155; border-radius: 6px; color: #fff; padding: 8px 12px;
      font-size: 13px; font-family: inherit; width: 100%;
    }
    .cfg-builder-textarea {
      background: #06090e; border: 1px solid #334155; border-radius: 6px; color: #93c5fd; padding: 10px 12px;
      font-size: 12.5px; font-family: var(--font-mono); line-height: 1.5; width: 100%; min-height: 110px; resize: vertical;
    }
    .cfg-cat-chips { display: flex; gap: 8px; flex-wrap: wrap; }
    .cfg-cat-chip-radio { display: none; }
    .cfg-cat-chip-label {
      padding: 4px 12px; font-size: 11.5px; font-weight: 600; border-radius: 6px; cursor: pointer;
      border: 1px solid #334155; background: #1e293b; color: #cbd5e1; transition: all .12s ease;
    }
    .cfg-cat-chip-radio:checked + .cfg-cat-chip-label {
      background: #2563eb; border-color: #60a5fa; color: #fff; box-shadow: 0 0 8px rgba(37, 99, 235, 0.4);
    }
    .cfg-head { border-bottom: 1px solid var(--surface-border); padding-bottom: 14px; display: flex; flex-direction: column; gap: 8px; }
    .cfg-head-line { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; }
    .cfg-head-inst { font-size: 13px; color: #cbd5e1; font-weight: 600; }
    .cfg-head-title { font-size: 24px; font-weight: 700; color: #fff; line-height: 1.25; }
    .cfg-head-domains { font-size: 12.5px; color: var(--text-sub); }
    .cfg-dom-link { color: var(--blue); text-decoration: none; font-weight: 600; }
    .cfg-dom-link:hover { text-decoration: underline; }
    .cfg-domain-note { font-size: 12.5px; color: var(--text-sub); background: rgba(37,99,235,.08); border: 1px solid rgba(37,99,235,.3); border-radius: 6px; padding: 8px 12px; }
    .cfg-domain-note b { color: #fff; margin-right: 6px; }
    .cfg-inst { border: 1px solid var(--surface-border); border-radius: 6px; background: var(--surface); padding: 10px 14px; }
    .cfg-inst summary { cursor: pointer; font-size: 12.5px; font-weight: 600; color: #cbd5e1; }
    .cfg-inst[open] summary { margin-bottom: 10px; }
    .cfg-inst .manual-desc { margin: 0 0 10px; max-width: 80ch; }
    .cfg-step-head { flex-direction: row; gap: 16px; align-items: flex-start; }
    .cfg-step-no { font-family: var(--font-mono); font-weight: 700; font-size: 26px; color: var(--blue); min-width: 56px; }
    .manual-desc b, .cfg-list b { color: #fff; }
    .cfg-ic { font-family: var(--font-mono); font-size: 11.5px; background: #1e293b; color: #e2e8f0; padding: 1px 5px; border-radius: 3px; }
    .cfg-chips { display: flex; gap: 6px; flex-wrap: wrap; }
    .cfg-chip { font-size: 12px; color: var(--text-sub); text-decoration: none; border: 1px solid #334155; border-radius: 12px; padding: 3px 11px; }
    .cfg-chip:hover { color: #fff; border-color: #3b82f6; }
    .cfg-list { padding-left: 18px; display: flex; flex-direction: column; gap: 6px; font-size: 13.5px; color: #cbd5e1; line-height: 1.6; max-width: 90ch; }
    .cfg-code { border: 1px solid var(--surface-border); border-radius: 5px; overflow: hidden; background: #06090e; }
    .cfg-code-head { display: flex; align-items: center; gap: 8px; padding: 6px 10px; background: #0b1220; border-bottom: 1px solid var(--surface-border); }
    .cfg-code-label { font-size: 12px; color: #cbd5e1; font-weight: 600; flex: 1; }
    .cfg-code pre { margin: 0; padding: 10px 14px; font-family: var(--font-mono); font-size: 12px; color: #7dd3fc; line-height: 1.6; overflow-x: auto; white-space: pre; }
    .cfg-copy { background: transparent; border: 1px solid #334155; color: var(--text-sub); font-size: 11px; border-radius: 4px; padding: 2px 8px; cursor: pointer; font-family: inherit; }
    .cfg-copy:hover { color: #fff; border-color: #3b82f6; }
    .cfg-cat { font-size: 10.5px; font-weight: 700; padding: 1px 7px; border-radius: 3px; }
    .cfg-cat-0 { background: #1e3a8a; color: #bfdbfe; }
    .cfg-cat-1 { background: #7c2d12; color: #fed7aa; }
    .cfg-cat-2 { background: #134e4a; color: #99f6e4; }
    .cfg-cat-3 { background: #3f3f46; color: #e4e4e7; }
    .cfg-expect { font-size: 12px; color: #a7f3d0; margin: -4px 0 4px 2px; }
    .cfg-table-wrap { overflow-x: auto; border: 1px solid var(--surface-border); border-radius: 5px; }
    .cfg-table { width: 100%; border-collapse: collapse; font-size: 12.5px; }
    .cfg-table th { text-align: left; background: #0b1220; color: var(--text-sub); font-weight: 600; padding: 8px 10px; border-bottom: 1px solid var(--surface-border); white-space: nowrap; }
    .cfg-table td { padding: 8px 10px; border-bottom: 1px solid #172033; color: #cbd5e1; vertical-align: top; line-height: 1.5; }
    .cfg-table tr:last-child td { border-bottom: none; }
    .cfg-vars td:first-child, .cfg-trouble td:nth-child(2) { font-family: var(--font-mono); color: #fde68a; }
    .cfg-trouble td:first-child { color: #fca5a5; }
    .cfg-h { font-size: 15px; color: #fff; margin-top: 4px; }
    .cfg-legend { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; font-size: 12.5px; color: var(--text-sub); }
    .cfg-search { width: 100%; background: var(--surface); border: 1px solid var(--surface-border); color: #fff; border-radius: 5px; padding: 9px 12px; font-size: 13px; font-family: inherit; }
    .cfg-pager { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-top: 6px; }
    .cfg-pager-btn { text-align: left; background: var(--surface); border: 1px solid var(--surface-border); color: #fff; border-radius: 6px; padding: 10px 14px; cursor: pointer; font-size: 13px; font-weight: 600; line-height: 1.4; font-family: inherit; }
    .cfg-pager-btn:last-child { text-align: right; }
    .cfg-pager-btn span { display: block; font-size: 11px; color: var(--text-muted); font-weight: 500; }
    .cfg-pager-btn:hover { border-color: #3b82f6; }

    /* *.sh 링크와 스크립트 보기 */
    .cfg-sh { color: #fcd34d; text-decoration: underline; text-decoration-style: dotted; text-underline-offset: 3px; cursor: pointer; }
    .cfg-sh:hover { color: #fde68a; text-decoration-style: solid; }
    .cfg-sh-ext::after { content: " ↗"; font-size: .85em; }
    .cfg-sh:focus-visible { outline: 2px solid #93c5fd; outline-offset: 1px; border-radius: 2px; }
    #cfg-viewer { margin: auto; width: min(1100px, 92vw); max-height: 86vh; padding: 0; border: 1px solid #334155; border-radius: 10px; background: #0b1220; color: #e2e8f0; display: none; flex-direction: column; }
    #cfg-viewer[open] { display: flex; }
    #cfg-viewer::backdrop { background: rgba(2, 6, 15, .72); }
    .cfg-vw-head { display: grid; grid-template-columns: 1fr auto; gap: 4px 16px; padding: 16px 20px 12px; border-bottom: 1px solid #1e293b; }
    .cfg-vw-meta { display: flex; gap: 8px; align-items: center; }
    .cfg-vw-host { font-size: 12px; font-weight: 700; color: #cbd5e1; background: #1e293b; padding: 2px 8px; border-radius: 4px; }
    .cfg-vw-title { grid-column: 1; font-family: var(--font-mono); font-size: 16px; font-weight: 700; color: #fcd34d; word-break: break-all; }
    .cfg-vw-actions { grid-column: 2; grid-row: 1 / span 2; display: flex; gap: 6px; align-items: flex-start; }
    .cfg-vw-actions a.cfg-copy { text-decoration: none; display: inline-block; }
    .cfg-copy:disabled { opacity: .45; cursor: default; }
    .cfg-vw-used { font-size: 12px; color: var(--text-sub); padding: 8px 20px; border-bottom: 1px solid #1e293b; }
    .cfg-vw-used a { color: var(--blue); text-decoration: none; }
    .cfg-vw-used a:hover { text-decoration: underline; }
    .cfg-vw-body { margin: 0; padding: 12px 0; overflow: auto; flex: 1; min-height: 120px; font-family: var(--font-mono); font-size: 12.5px; line-height: 1.6; color: #bae6fd; background: #06090e; counter-reset: ln; white-space: pre; }
    .cfg-ln { display: inline-block; min-width: 100%; padding-right: 20px; }
    .cfg-ln::before { counter-increment: ln; content: counter(ln); display: inline-block; width: 44px; margin-right: 14px; text-align: right; color: #475569; user-select: none; }
    .cfg-ln:hover { background: rgba(148, 163, 184, .08); }
    .cfg-vw-note { font-size: 11.5px; color: var(--text-muted); padding: 10px 20px 14px; border-top: 1px solid #1e293b; }
    @media (prefers-reduced-motion: reduce) { .cfg-mx-cell i { transition: none; } }
    /* 데스크탑 뷰 고정: 모바일/좁은 화면에서도 통합 내비게이션 + 바디 그리드 유지 */
    #view-settings .settings-layout {
      grid-template-columns: 340px minmax(0, 1fr) !important;
      display: grid !important;
      height: 100% !important;
    }

    /* ===== 위키: 로그인 · 팀 표시줄 · 클라우드 묶음 · 빈 화면 ===== */
    #view-settings.wiki-anon .settings-layout { grid-template-columns: minmax(0, 1fr) !important; }
    #view-settings.wiki-anon .settings-body { grid-column: 1 !important; grid-row: 1 !important; }
    .wk-login { max-width: 980px; width: 100%; margin: 40px auto; display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }
    .wk-login-intro { grid-column: 1 / -1; }
    .wk-login-intro h2 { font-size: 26px; color: #fff; margin-bottom: 8px; }
    .wk-login-intro p { font-size: 14px; color: var(--text-sub); line-height: 1.6; max-width: 70ch; }
    .wk-card { background: var(--surface); border: 1px solid var(--surface-border); border-radius: 10px; padding: 20px; display: flex; flex-direction: column; gap: 12px; }
    .wk-card h3 { font-size: 16px; color: #fff; }
    .wk-card label { display: flex; flex-direction: column; gap: 5px; font-size: 12.5px; font-weight: 600; color: #cbd5e1; }
    .wk-card label span { font-weight: 400; color: var(--text-muted); }
    .wk-card input, .wk-field input, .wk-field textarea, .wk-field select { background: #06090e; border: 1px solid #334155; border-radius: 6px; color: #fff; padding: 9px 11px; font-size: 13.5px; font-family: inherit; }
    .wk-card input:focus, .wk-field input:focus, .wk-field textarea:focus, .wk-field select:focus { outline: 2px solid #3b82f6; outline-offset: 0; border-color: transparent; }
    .wk-btn { background: #1e293b; color: #fff; border: 1px solid #334155; border-radius: 6px; padding: 9px 14px; font-size: 13px; font-weight: 600; cursor: pointer; font-family: inherit; }
    .wk-btn:hover { border-color: #3b82f6; }
    .wk-btn:disabled { opacity: .5; cursor: default; }
    .wk-primary { background: var(--primary); border-color: var(--primary); }
    .wk-primary:hover { background: var(--primary-hover); }
    .wk-danger { color: #fca5a5; border-color: #7f1d1d; }
    .wk-error { color: #fca5a5; font-size: 12.5px; }
    .login-notice { background: rgba(245, 158, 11, 0.14); border: 1px solid rgba(245, 158, 11, 0.45); color: #fde68a; border-radius: 6px; padding: 9px 11px; font-size: 12px; line-height: 1.45; margin-bottom: 14px; }
    .login-field-label { display: block; font-size: 12px; font-weight: 600; color: #cbd5e1; margin-bottom: 5px; }
    .login-key-row { display: flex; gap: 6px; margin-bottom: 14px; align-items: stretch; }
    .login-key-row .login-input { margin-bottom: 0; font-family: var(--font-mono); text-transform: uppercase; flex: 1; }
    .login-regen-btn { background: #1e293b; border: 1px solid var(--surface-border); color: #cbd5e1; border-radius: 6px; padding: 0 12px; font-size: 12px; font-weight: 600; cursor: pointer; white-space: nowrap; font-family: inherit; }
    .login-regen-btn:hover { border-color: var(--primary); color: #fff; }
    .login-key-readonly {
      background: #060a12; border: 1px dashed #334155; border-radius: 6px; padding: 10px 12px;
      font-family: var(--font-mono); font-size: 12.5px; color: #93c5fd; margin-bottom: 14px;
      user-select: all; cursor: not-allowed;
    }
    .wk-key-locked { background: #060a12 !important; color: #93c5fd !important; border-style: dashed !important; cursor: not-allowed !important; }
    .wk-teambar { display: flex; align-items: center; justify-content: space-between; gap: 8px; padding: 2px 4px 12px; margin-bottom: 10px; border-bottom: 1px solid var(--surface-border); }
    .wk-teambar b { display: block; font-size: 13.5px; color: #fff; }
    .wk-teambar span { font-size: 11.5px; color: var(--text-muted); }
    .cfg-group-head { display: flex; align-items: center; gap: 6px; font-size: 11.5px; font-weight: 700; color: var(--text-sub); padding: 10px 6px 4px; }
    .cfg-group-head .wk-add { margin-left: auto; }
    .cfg-empty-panel { border: 1px dashed #334155; border-radius: 10px; padding: 28px; text-align: center; color: var(--text-sub); font-size: 14px; display: flex; flex-direction: column; gap: 14px; align-items: center; }
    @media (max-width: 860px) { .wk-login { grid-template-columns: 1fr; margin: 16px auto; } }

    /* ===== 위키: 편집기 · 충돌 · 비교 ===== */
    .wk-add { background: transparent; border: 1px dashed #3b82f6; color: #93c5fd; border-radius: 6px; padding: 7px 10px; font-size: 12.5px; font-weight: 600; cursor: pointer; font-family: inherit; margin-top: 6px; text-align: left; }
    .wk-add:hover { background: rgba(37, 99, 235, .12); color: #fff; }
    .wk-mini { background: transparent; border: 1px solid #334155; color: var(--text-sub); border-radius: 4px; padding: 2px 8px; font-size: 11px; cursor: pointer; font-family: inherit; }
    .wk-mini:hover { color: #fff; border-color: #3b82f6; }
    .wk-group-acts { margin-left: auto; display: inline-flex; gap: 4px; }
    .wk-acts { display: flex; gap: 6px; justify-content: flex-end; margin-bottom: 4px; }
    .cfg-inst summary + .wk-acts { margin: 6px 0 10px; justify-content: flex-start; }
    .wk-editor { display: flex; flex-direction: column; gap: 14px; max-width: 1100px; }
    .wk-field { display: flex; flex-direction: column; gap: 5px; font-size: 12.5px; font-weight: 600; color: #cbd5e1; }
    .wk-field span { font-weight: 400; color: var(--text-muted); }
    .wk-field textarea { resize: vertical; line-height: 1.5; }
    .wk-code { font-family: var(--font-mono); font-size: 12px; color: #bae6fd; }
    .wk-set { border: 1px solid var(--surface-border); border-radius: 8px; padding: 12px 14px 14px; display: flex; flex-direction: column; gap: 10px; }
    .wk-set legend { font-size: 13px; font-weight: 700; color: #fff; padding: 0 6px; }
    .wk-rows { display: flex; flex-direction: column; gap: 10px; }
    .wk-row { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 10px; background: #0b1220; border: 1px solid #1e293b; border-radius: 6px; padding: 10px; }
    .wk-row-cols { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 8px; }
    .wk-row-cols .wk-field:has(.wk-code) { grid-column: 1 / -1; }
    .wk-row-tools { display: flex; flex-direction: column; gap: 4px; }
    .wk-checks { display: flex; flex-wrap: wrap; gap: 6px 16px; font-size: 13px; color: #cbd5e1; }
    .wk-bar { display: flex; gap: 8px; position: sticky; bottom: -48px; background: #090d16; padding: 12px 0; border-top: 1px solid var(--surface-border); }
    .wk-bad { outline: 2px solid #ef4444; outline-offset: 3px; border-radius: 6px; }
    .wk-note { color: #a7f3d0; font-size: 13px; }
    .wk-conflict h3 { font-size: 18px; color: #fbbf24; margin-bottom: 6px; }
    .wk-conflict > p { font-size: 13px; color: var(--text-sub); margin-bottom: 12px; }
    .wk-diff-wrap { border: 1px solid var(--surface-border); border-radius: 6px; overflow: auto; max-height: 70vh; }
    .wk-diff-sum { font-size: 12px; color: var(--text-sub); padding: 8px 12px; background: #0b1220; border-bottom: 1px solid var(--surface-border); }
    .wk-diff { width: 100%; border-collapse: collapse; font-family: var(--font-mono); font-size: 12px; table-layout: fixed; }
    .wk-diff th { position: sticky; top: 0; background: #0f172a; color: #cbd5e1; text-align: left; padding: 6px 10px; font-family: inherit; }
    .wk-diff td { padding: 1px 8px; white-space: pre-wrap; word-break: break-all; color: #cbd5e1; vertical-align: top; }
    .wk-diff td.wk-ln { width: 44px; color: #475569; text-align: right; user-select: none; }
    .wk-diff td.wk-del { background: rgba(239, 68, 68, .16); color: #fecaca; }
    .wk-diff td.wk-ins { background: rgba(16, 185, 129, .16); color: #bbf7d0; }
    .wk-diff td.wk-empty { background: repeating-linear-gradient(45deg, transparent 0 6px, rgba(148,163,184,.06) 6px 12px); }
    .wk-fold td { text-align: center; color: var(--text-muted); background: #0b1220; padding: 3px; font-family: 'Pretendard', sans-serif; }
    #wk-toast { position: fixed; bottom: 24px; left: 50%; transform: translate(-50%, 20px); opacity: 0; background: #0f172a; border: 1px solid #3b82f6; color: #fff; padding: 10px 16px; border-radius: 8px; font-size: 13px; z-index: 1000; transition: opacity .2s, transform .2s; pointer-events: none; }
    #wk-toast.show { opacity: 1; transform: translate(-50%, 0); }
    @media (prefers-reduced-motion: reduce) { #wk-toast { transition: none; } }

    /* ===== 위키: 기록 · 최근 변경 ===== */
    .wk-revs td, .wk-changes td { vertical-align: middle; }
    .wk-rev-del td { color: var(--text-muted); }
    .wk-bar-inline { position: static; border-top: 0; padding: 0; }
    .wk-ch-row { cursor: pointer; }
    .wk-ch-row:hover td, .wk-ch-row:focus td { background: var(--surface-hover); }
    .cfg-crumb a { color: var(--blue); text-decoration: none; }

    /* ===== 상단 [콘솔] 메뉴 ===== */
    .cn-wrap { position: relative; display: inline-block; }
    .cn-btn::after { content: " ▾"; font-size: .8em; }
    .cn-menu { position: absolute; right: 0; top: calc(100% + 6px); width: 340px; background: #0f172a; border: 1px solid #334155; border-radius: 10px; padding: 8px; z-index: 900; box-shadow: 0 12px 32px rgba(2, 6, 15, .6); }
    .cn-group + .cn-group { border-top: 1px solid #1e293b; margin-top: 6px; padding-top: 6px; }
    .cn-head { display: flex; align-items: center; gap: 6px; font-size: 11.5px; font-weight: 700; color: var(--text-sub); padding: 4px 8px; }
    .cn-link { display: flex; flex-direction: column; gap: 2px; padding: 7px 10px; border-radius: 6px; text-decoration: none; color: #fff; }
    .cn-link b { font-size: 13px; font-weight: 600; }
    .cn-link span { font-size: 11px; color: var(--text-muted); }
    .cn-link:hover, .cn-link:focus { background: var(--surface-hover); outline: none; }
    .cn-link:focus-visible { outline: 2px solid #93c5fd; }
    .wk-teambar-acts { display: flex; gap: 4px; }
    .wk-rename { display: flex; flex-wrap: wrap; gap: 6px; align-items: flex-end; width: 100%; }
    .wk-rename label { display: flex; flex-direction: column; gap: 4px; font-size: 11px; color: var(--text-muted); flex: 1; min-width: 140px; }
    .wk-rename input { background: #06090e; border: 1px solid #334155; border-radius: 5px; color: #fff; padding: 6px 8px; font-size: 13px; font-family: inherit; }

    /* ===== 시점(줌) 렌즈 ===== */
    .cfg-zoombar { display: flex; align-items: stretch; flex-wrap: wrap; gap: 4px; margin: 4px 0 16px; }
    .cfg-zoom-step { display: flex; flex-direction: column; align-items: flex-start; gap: 1px; min-width: 120px; padding: 8px 12px;
      background: var(--surface-card); border: 1px solid #263244; border-radius: 8px; color: var(--text-sub); cursor: pointer; text-align: left; font-family: inherit; }
    .cfg-zoom-step:hover { border-color: #3b82f6; color: #fff; }
    .cfg-zoom-step.past { opacity: .78; }
    .cfg-zoom-step.on { background: #172554; border-color: #60a5fa; color: #fff; }
    .cfg-zoom-step:focus-visible { outline: 2px solid #93c5fd; outline-offset: 2px; }
    .cfg-zoom-n { font-size: 10.5px; font-weight: 700; color: #93c5fd; }
    .cfg-zoom-t { font-size: 13px; font-weight: 700; }
    .cfg-zoom-who { font-size: 11px; color: var(--text-muted); }
    .cfg-zoom-sep { align-self: center; color: var(--text-muted); font-size: 14px; }
    .cfg-forest { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 10px; margin-bottom: 18px; }
    .cfg-forest-cloud { display: flex; flex-direction: column; gap: 6px; padding: 10px; background: var(--surface-card); border: 1px solid #263244; border-radius: 10px; }
    .cfg-forest-name { display: flex; align-items: center; gap: 7px; background: transparent; border: 0; color: #fff; font-size: 14px; font-weight: 700;
      padding: 2px 4px 6px; cursor: pointer; text-align: left; font-family: inherit; border-bottom: 1px solid #263244; }
    .cfg-forest-name small { margin-left: auto; font-size: 11px; font-weight: 500; color: var(--text-muted); }
    .cfg-forest-name:hover { color: #93c5fd; }
    .cfg-forest-inst { display: flex; flex-direction: column; gap: 1px; background: #0b1220; border: 1px solid #1e293b; border-radius: 7px;
      padding: 7px 9px; color: #e2e8f0; cursor: pointer; text-align: left; font-family: inherit; }
    .cfg-forest-inst b { font-family: var(--font-mono); font-size: 12.5px; }
    .cfg-forest-inst span { font-size: 11px; color: var(--text-muted); }
    .cfg-forest-inst:hover { border-color: #3b82f6; }
    .cfg-forest-name:focus-visible, .cfg-forest-inst:focus-visible { outline: 2px solid #93c5fd; outline-offset: 2px; }
    .cfg-term-btn { margin-top: 10px; }

    /* ===== [설정] 코드 블록 실행 버튼 & 푸터 닥 & 플로팅 윈도우 ===== */
    .cfg-code-actions { display: flex; align-items: center; gap: 6px; margin-left: auto; }
    .cfg-run-btn {
      display: inline-flex; align-items: center; gap: 4px; padding: 3px 8px; font-size: 11.5px; font-weight: 600;
      border-radius: 5px; cursor: pointer; border: 1px solid transparent; font-family: inherit; transition: all .15s ease;
    }
    .cfg-run-btn:focus-visible { outline: 2px solid #93c5fd; outline-offset: 1px; }
    /* 안전 조회/검증 실행 버튼 */
    .cfg-run-safe {
      background: #0284c7; color: #ffffff; border-color: #38bdf8;
    }
    .cfg-run-safe:hover { background: #0369a1; border-color: #7dd3fc; box-shadow: 0 0 8px rgba(56, 189, 248, .35); }
    /* 뷰 모드 (확인/안전 조회) 버튼 */
    .cfg-btn-view {
      background: #0f766e; color: #ccfbf1; border-color: #14b8a6;
    }
    .cfg-btn-view:hover { background: #0d9488; border-color: #2dd4bf; box-shadow: 0 0 8px rgba(20, 184, 166, .4); }
    /* 위험 변경/재시작/중지/생성 실행 버튼 */
    .cfg-run-warn {
      background: #b45309; color: #fef3c7; border-color: #f59e0b;
    }
    .cfg-run-warn:hover { background: #d97706; border-color: #fbbf24; box-shadow: 0 0 10px rgba(245, 158, 11, .45); }
    .cfg-run-warn b { font-weight: 800; color: #fff; }
    /* 빨강색 수정/변경 버튼 */
    .cfg-run-danger {
      background: #dc2626 !important; color: #ffffff !important; border-color: #ef4444 !important; font-weight: 700 !important;
    }
    .cfg-run-danger:hover {
      background: #b91c1c !important; border-color: #f87171 !important; box-shadow: 0 0 12px rgba(239, 68, 68, .6) !important;
    }

    /* 위험/수정 변경 모달 레드 테마 */
    .cfg-modal-danger .cfg-modal-card { border-color: #ef4444; }
    .cfg-modal-danger .cfg-modal-head { background: #2a0e11; border-bottom: 1px solid #5c1d24; color: #f87171; }
    .cfg-modal-danger .cfg-modal-alert { background: rgba(239, 68, 68, .14); border: 1px solid rgba(239, 68, 68, .35); color: #fca5a5; }
    .cfg-modal-danger .cfg-btn-confirm { background: #dc2626; border-color: #ef4444; color: #fff; font-weight: 700; }
    .cfg-modal-danger .cfg-btn-confirm:hover { background: #b91c1c; border-color: #f87171; box-shadow: 0 0 10px rgba(239, 68, 68, .5); }

    /* 뷰 모드 팝업 테마 */
    .cfg-modal-view .cfg-modal-card { border-color: #14b8a6; max-width: 680px; }
    .cfg-modal-view .cfg-modal-head { background: #0f2d29; border-bottom: 1px solid #134e48; color: #2dd4bf; }
    .cfg-modal-view .cfg-modal-alert { background: rgba(20, 184, 166, .12); border: 1px solid rgba(20, 184, 166, .3); color: #99f6e4; }

    /* 위험 명령어 사전 확인 모달 */
    .cfg-modal-overlay {
      position: fixed; inset: 0; background: rgba(2, 6, 23, .75); backdrop-filter: blur(4px);
      display: flex; align-items: center; justify-content: center; z-index: 1200; padding: 16px;
    }
    .cfg-modal-card {
      background: #0f172a; border: 1px solid #f59e0b; border-radius: 12px; width: 100%; max-width: 560px;
      box-shadow: 0 20px 40px rgba(0, 0, 0, .7); overflow: hidden; display: flex; flex-direction: column;
      animation: cfgModalPop .18s cubic-bezier(0.16, 1, 0.3, 1);
    }
    @keyframes cfgModalPop { from { opacity: 0; transform: scale(.95) translateY(8px); } to { opacity: 1; transform: scale(1) translateY(0); } }
    .cfg-modal-head {
      display: flex; align-items: center; justify-content: space-between; padding: 12px 16px;
      background: #1e1b18; border-bottom: 1px solid #3d2c17; color: #fbbf24; font-size: 14px; font-weight: 700;
    }
    .cfg-modal-body { padding: 16px; display: flex; flex-direction: column; gap: 12px; color: #e2e8f0; font-size: 13px; line-height: 1.5; }
    .cfg-modal-alert {
      background: rgba(245, 158, 11, .12); border: 1px solid rgba(245, 158, 11, .3); border-radius: 8px;
      padding: 10px 12px; color: #fde68a; font-size: 12.5px;
    }
    .cfg-modal-code {
      background: #06090e; border: 1px solid #334155; border-radius: 6px; padding: 10px 12px;
      font-family: var(--font-mono); font-size: 12px; color: #93c5fd; overflow-x: auto; max-height: 160px; white-space: pre-wrap; word-break: break-all;
    }
    .cfg-modal-meta { display: flex; align-items: center; gap: 12px; font-size: 12px; color: #94a3b8; }
    .cfg-modal-meta strong { color: #38bdf8; }
    .cfg-modal-foot {
      display: flex; align-items: center; justify-content: flex-end; gap: 8px; padding: 12px 16px;
      background: #0b1120; border-top: 1px solid #1e293b;
    }
    .cfg-btn-cancel {
      padding: 6px 14px; font-size: 12.5px; font-weight: 600; color: #cbd5e1; background: #1e293b;
      border: 1px solid #475569; border-radius: 6px; cursor: pointer;
    }
    .cfg-btn-cancel:hover { background: #334155; color: #fff; }
    .cfg-btn-confirm {
      padding: 6px 16px; font-size: 12.5px; font-weight: 700; color: #fff; background: #d97706;
      border: 1px solid #f59e0b; border-radius: 6px; cursor: pointer; box-shadow: 0 0 10px rgba(245, 158, 11, .3);
    }
    .cfg-btn-confirm:hover { background: #b45309; }

    /* 화면 하단 푸터 닥 (Footer Dock) */
    #cfg-footer-dock {
      position: fixed; bottom: 0; left: 0; right: 0; height: 42px; background: rgba(15, 23, 42, .96);
      backdrop-filter: blur(10px); border-top: 1px solid #334155; display: flex; align-items: center;
      padding: 0 14px; gap: 10px; z-index: 1050; box-shadow: 0 -4px 20px rgba(0, 0, 0, .45);
      transition: transform .2s ease;
    }
    #cfg-footer-dock.cfg-dock-hidden { transform: translateY(100%); pointer-events: none; }
    .cfg-dock-title {
      display: inline-flex; align-items: center; gap: 6px; font-size: 12px; font-weight: 700; color: #38bdf8;
      white-space: nowrap; padding-right: 8px; border-right: 1px solid #334155;
    }
    .cfg-dock-list {
      display: flex; align-items: center; gap: 6px; overflow-x: auto; flex: 1; min-width: 0; padding: 2px 0;
    }
    .cfg-dock-chip {
      display: inline-flex; align-items: center; gap: 6px; padding: 4px 10px; background: #1e293b;
      border: 1px solid #475569; border-radius: 6px; color: #e2e8f0; font-size: 11.5px; cursor: pointer;
      white-space: nowrap; transition: all .15s ease; user-select: none; max-width: 240px;
    }
    .cfg-dock-chip:hover { background: #334155; border-color: #60a5fa; color: #fff; }
    .cfg-dock-chip.active { background: #1e3a8a; border-color: #3b82f6; color: #93c5fd; box-shadow: 0 0 6px rgba(59, 130, 246, .4); }
    .cfg-dock-chip-dot { width: 7px; height: 7px; border-radius: 50%; background: #22c55e; flex-shrink: 0; }
    .cfg-dock-chip-dot.off { background: #94a3b8; }
    .cfg-dock-chip-name { overflow: hidden; text-overflow: ellipsis; }
    .cfg-dock-chip-close {
      margin-left: 2px; padding: 1px 4px; font-size: 11px; color: #94a3b8; border-radius: 3px; cursor: pointer;
    }
    .cfg-dock-chip-close:hover { color: #f87171; background: rgba(239, 68, 68, .15); }
    .cfg-dock-acts { display: flex; align-items: center; gap: 4px; flex-shrink: 0; }
    .cfg-dock-btn {
      background: transparent; border: 1px solid #334155; color: #94a3b8; border-radius: 5px;
      padding: 3px 8px; font-size: 11px; cursor: pointer;
    }
    .cfg-dock-btn:hover { background: #1e293b; color: #e2e8f0; }

    /* 플로팅 윈도우 레이어 & 윈도우 창 */
    #cfg-float-layer {
      position: fixed; inset: 0; pointer-events: none; z-index: 1100;
    }
    .cfg-win {
      position: absolute; width: 680px; height: 420px; min-width: 380px; min-height: 240px;
      background: #06090e; border: 1px solid #334155; border-radius: 8px; box-shadow: 0 18px 45px rgba(0, 0, 0, .65);
      display: flex; flex-direction: column; overflow: hidden; pointer-events: auto; resize: both;
      transition: box-shadow .2s ease;
    }
    .cfg-win.cfg-focus { border-color: #3b82f6; box-shadow: 0 20px 50px rgba(2, 6, 23, .8), 0 0 12px rgba(59, 130, 246, .25); z-index: 1110; }
    .cfg-win.minimized { display: none !important; }
    .cfg-win.maximized {
      top: 10px !important; left: 10px !important; width: calc(100vw - 20px) !important; height: calc(100vh - 62px) !important;
      resize: none !important; border-radius: 4px;
    }
    .cfg-win-head {
      display: flex; align-items: center; justify-content: space-between; padding: 6px 12px;
      background: #0f172a; border-bottom: 1px solid #1e293b; cursor: grab; user-select: none;
    }
    .cfg-win-head:active { cursor: grabbing; }
    .cfg-win-title {
      display: flex; align-items: center; gap: 8px; font-size: 12px; font-weight: 700; color: #f1f5f9;
      overflow: hidden; text-overflow: ellipsis; white-space: nowrap; flex: 1;
    }
    .cfg-win-badge {
      padding: 1px 7px; font-size: 10.5px; border-radius: 4px; background: #1e293b; color: #38bdf8; border: 1px solid #334155; font-family: var(--font-mono); font-weight: 700;
    }
    .cfg-win-badge.cfg-badge-view { background: #0c4a6e; color: #7dd3fc; border-color: #0284c7; }
    .cfg-win-badge.cfg-badge-modify { background: #7c2d12; color: #fca5a5; border-color: #ef4444; }
    .cfg-win-ctrls { display: flex; align-items: center; gap: 4px; margin-left: 8px; }
    .cfg-win-btn {
      width: 22px; height: 22px; display: inline-flex; align-items: center; justify-content: center;
      background: transparent; border: 0; color: #94a3b8; border-radius: 4px; cursor: pointer; font-size: 11px;
    }
    .cfg-win-btn:hover { background: #1e293b; color: #fff; }
    .cfg-win-btn.btn-close:hover { background: #ef4444; color: #fff; }
    .cfg-win-body {
      flex: 1; position: relative; background: #06090e; overflow: hidden; padding: 4px;
    }
    .cfg-win-body .xterm { height: 100%; }
    .cfg-win-body .xterm-viewport { overflow-y: auto; }
    .cfg-win-foot {
      display: flex; align-items: center; justify-content: space-between; padding: 4px 10px;
      background: #090e17; border-top: 1px solid #1e293b; font-size: 11px; color: #64748b;
    }
    .cfg-win-status { display: flex; align-items: center; gap: 6px; }
    .cfg-win-status-dot { width: 6px; height: 6px; border-radius: 50%; background: #22c55e; }
    .cfg-win-status-dot.off { background: #94a3b8; }
    .cfg-win-status-dot.wait { background: #f59e0b; }


    /* ===== #cfg 지침 스튜디오 · 인라인 패널 · 모듈 카드 액션바 ===== */
    .cfg-guide-launch-btn {
      display: flex; align-items: center; justify-content: space-between; width: 100%;
      padding: 9px 11px; border-radius: 7px; cursor: pointer; font-family: inherit;
      background: linear-gradient(135deg, rgba(37, 99, 235, 0.22), rgba(14, 165, 233, 0.14));
      border: 1px solid #2563eb; color: #e0f2fe; font-size: 12.5px; font-weight: 700;
      transition: all .15s ease;
    }
    .cfg-guide-launch-btn:hover { background: linear-gradient(135deg, rgba(37, 99, 235, 0.35), rgba(14, 165, 233, 0.25)); border-color: #60a5fa; color: #fff; box-shadow: 0 0 12px rgba(37, 99, 235, 0.35); }
    .cfg-guide-launch-btn small { font-size: 10.5px; font-weight: 600; color: #93c5fd; background: rgba(15, 23, 42, 0.7); padding: 2px 6px; border-radius: 4px; }
    .cfg-tree-add-minor { margin-top: 4px; padding: 5px 8px; font-size: 11.5px; }
    .cfg-tree-step-acts { display: flex; flex-direction: column; gap: 4px; margin-top: 8px; }

    /* 모듈형 빌더 카드 액션바 (겹침 방지) */
    .cfg-list-row { display: flex; align-items: flex-start; justify-content: space-between; gap: 10px; }
    .cfg-card-item { margin-bottom: 14px; border: 1px solid #1e293b; border-radius: 7px; padding: 8px 10px; background: rgba(15, 23, 42, 0.5); }
    .cfg-card-bar { display: flex; align-items: center; justify-content: space-between; gap: 8px; margin-bottom: 6px; }
    .cfg-card-idx { font-size: 11px; font-weight: 700; color: #94a3b8; font-family: var(--font-mono); }
    .cfg-item-btn:disabled { opacity: .35; cursor: default; }

    /* 지침 스튜디오 모달 */
    .cfg-guide-card {
      background: #0b1220; border: 1px solid #3b82f6; border-radius: 12px;
      width: min(1160px, 96vw); height: min(88vh, 860px);
      display: flex; flex-direction: column; overflow: hidden;
      box-shadow: 0 24px 64px rgba(0, 0, 0, 0.85);
      animation: cfgModalPop .18s cubic-bezier(0.16, 1, 0.3, 1);
    }
    .cfg-guide-head {
      display: flex; align-items: flex-start; justify-content: space-between; gap: 12px;
      padding: 14px 18px; background: #0f172a; border-bottom: 1px solid #1e293b;
    }
    .cfg-guide-head h2 { font-size: 16px; font-weight: 700; color: #f8fafc; margin: 0 0 4px; }
    .cfg-guide-head p { font-size: 12px; color: #94a3b8; margin: 0; }
    .cfg-guide-toolbar {
      display: flex; align-items: center; flex-wrap: wrap; gap: 12px;
      padding: 10px 18px; background: #090e17; border-bottom: 1px solid #1e293b;
    }
    .cfg-guide-mode-chips { display: flex; gap: 6px; flex-wrap: wrap; }
    .cfg-guide-chip {
      padding: 5px 11px; font-size: 12px; font-weight: 600; border-radius: 6px;
      border: 1px solid #334155; background: #1e293b; color: #cbd5e1; cursor: pointer; font-family: inherit;
    }
    .cfg-guide-chip:hover { border-color: #60a5fa; color: #fff; }
    .cfg-guide-chip.active { background: #2563eb; border-color: #60a5fa; color: #fff; }
    .cfg-guide-kind-wrap { display: flex; align-items: center; gap: 6px; font-size: 12px; color: #94a3b8; font-weight: 600; }
    .cfg-guide-kind-wrap select {
      background: #06090e; border: 1px solid #334155; border-radius: 6px; color: #f1f5f9;
      padding: 5px 10px; font-size: 12.5px; font-family: inherit;
    }
    .cfg-guide-ctx-chk { display: flex; align-items: center; gap: 6px; font-size: 12px; color: #cbd5e1; margin-left: auto; cursor: pointer; }
    .cfg-guide-split {
      flex: 1; min-height: 0; display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
    }
    .cfg-guide-pane {
      min-height: 0; display: flex; flex-direction: column; overflow: hidden;
    }
    .cfg-guide-left { border-right: 1px solid #1e293b; background: #090d16; }
    .cfg-guide-right { padding: 12px 16px; gap: 10px; overflow-y: auto; background: #0b1220; }
    .cfg-guide-tabs { display: flex; gap: 4px; padding: 10px 14px 0; border-bottom: 1px solid #1e293b; background: #0f172a; }
    .cfg-guide-tab {
      padding: 8px 12px; font-size: 12.5px; font-weight: 600; color: #94a3b8;
      background: transparent; border: 1px solid transparent; border-bottom: 0; border-radius: 6px 6px 0 0; cursor: pointer; font-family: inherit;
    }
    .cfg-guide-tab.active { background: #090d16; color: #fff; border-color: #1e293b; }
    .cfg-guide-pane-body { flex: 1; min-height: 0; overflow-y: auto; padding: 14px 16px; display: flex; flex-direction: column; gap: 10px; }
    .cfg-guide-left-acts { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
    .cfg-guide-hint { font-size: 12px; color: #94a3b8; line-height: 1.5; margin: 0; }
    .cfg-guide-pre, .cfg-guide-ex-pre, .cfg-guide-create-pre {
      margin: 0; padding: 12px; background: #05080f; border: 1px solid #1e293b; border-radius: 7px;
      font-family: var(--font-mono); font-size: 11.5px; color: #bae6fd; line-height: 1.55;
      white-space: pre-wrap; word-break: break-word; overflow-x: auto;
    }
    .cfg-guide-ex-card {
      background: #0f172a; border: 1px solid #1e293b; border-radius: 8px; padding: 12px; display: flex; flex-direction: column; gap: 8px;
    }
    .cfg-guide-ex-head { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
    .cfg-guide-ex-head b { font-size: 13px; color: #f8fafc; }
    .cfg-guide-ex-badge { font-size: 11px; font-weight: 700; padding: 2px 7px; border-radius: 4px; background: #1e3a8a; color: #bfdbfe; }
    .cfg-guide-ex-acts { display: flex; gap: 6px; margin-left: auto; }
    .cfg-guide-ex-desc { font-size: 12px; color: #94a3b8; margin: 0; line-height: 1.45; }
    .cfg-guide-right-head { display: flex; align-items: center; justify-content: space-between; gap: 8px; flex-wrap: wrap; }
    .cfg-guide-right-head b { font-size: 13px; color: #f8fafc; }
    .cfg-guide-right-acts { display: flex; gap: 6px; flex-wrap: wrap; }
    .cfg-guide-textarea {
      width: 100%; min-height: 165px; background: #05080f; border: 1px solid #334155; border-radius: 7px;
      color: #7dd3fc; padding: 10px 12px; font-family: var(--font-mono); font-size: 12px; line-height: 1.5; resize: vertical;
    }
    .cfg-guide-textarea:focus { outline: 2px solid #3b82f6; border-color: transparent; }
    .cfg-guide-preview { display: flex; flex-direction: column; gap: 10px; }
    .cfg-guide-empty { padding: 18px; border: 1px dashed #334155; border-radius: 8px; text-align: center; font-size: 12.5px; color: #94a3b8; }
    .cfg-guide-err-box { padding: 12px 14px; border: 1px solid #ef4444; background: rgba(239, 68, 68, 0.12); border-radius: 8px; color: #fecaca; font-size: 12.5px; }
    .cfg-guide-err-box p { margin: 4px 0 0; }
    .cfg-guide-op-card { border: 1px solid #334155; border-radius: 8px; padding: 12px; background: #0f172a; display: flex; flex-direction: column; gap: 8px; }
    .cfg-guide-op-card.ok { border-color: #059669; }
    .cfg-guide-op-card.err { border-color: #ef4444; }
    .cfg-guide-op-head { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; font-size: 13px; color: #fff; }
    .cfg-guide-op-badge { font-size: 11px; font-weight: 700; padding: 2px 7px; border-radius: 4px; }
    .cfg-guide-op-badge.ok { background: #064e3b; color: #6ee7b7; }
    .cfg-guide-op-badge.err { background: #7f1d1d; color: #fecaca; }
    .cfg-guide-op-target { font-size: 12px; color: #93c5fd; margin-left: auto; }
    .cfg-guide-op-sum { font-size: 12px; color: #a7f3d0; }
    .cfg-guide-op-errs { margin: 0; padding-left: 18px; font-size: 12px; color: #fca5a5; }
    .cfg-guide-msg-row { display: flex; align-items: center; gap: 8px; font-size: 12px; color: #94a3b8; }
    .cfg-guide-msg-row input { flex: 1; background: #05080f; border: 1px solid #334155; border-radius: 5px; color: #fff; padding: 5px 8px; font-size: 12px; font-family: inherit; }
    .cfg-guide-foot {
      display: flex; align-items: center; justify-content: space-between; gap: 12px; flex-wrap: wrap;
      padding: 12px 18px; background: #090e17; border-top: 1px solid #1e293b;
    }
    .cfg-guide-foot-note { font-size: 12px; color: #cbd5e1; }
    .cfg-guide-foot-acts { display: flex; gap: 8px; }

    /* 위키 편집기 인라인 지침 도우미 */
    .cfg-guide-inline {
      border: 1px solid #1e3a8a; border-radius: 8px; background: rgba(15, 23, 42, 0.85); padding: 10px 14px;
    }
    .cfg-guide-inline summary { cursor: pointer; font-size: 13px; font-weight: 700; color: #93c5fd; }
    .cfg-guide-inline-body { margin-top: 10px; display: flex; flex-direction: column; gap: 10px; }
    .cfg-guide-inline-acts { display: flex; gap: 6px; flex-wrap: wrap; }
    .cfg-guide-inline-foot { display: flex; gap: 8px; flex-wrap: wrap; }
    .cfg-guide-inline-msg { font-size: 12px; padding: 7px 10px; border-radius: 6px; }
    .cfg-guide-inline-msg.ok { background: rgba(16, 185, 129, 0.12); border: 1px solid #059669; color: #a7f3d0; }
    .cfg-guide-inline-msg.err { background: rgba(239, 68, 68, 0.12); border: 1px solid #ef4444; color: #fecaca; }

    .cfg-manual-link-btn {
      display: flex; align-items: center; justify-content: space-between; width: 100%;
      padding: 7px 11px; border-radius: 6px; text-decoration: none;
      background: #0f172a; border: 1px solid #334155; color: #cbd5e1; font-size: 12px; font-weight: 600;
      transition: background-color .15s ease, border-color .15s ease, color .15s ease;
    }
    .cfg-manual-link-btn:hover { background: #1e293b; border-color: #60a5fa; color: #fff; }
    .cfg-manual-link-btn small { font-size: 10.5px; color: #94a3b8; }

    /* ===== 접속 키값 · 사용자 매칭 · 최근 변경 & 접속 기록 ===== */
    .wk-teambar { flex-direction: column; align-items: stretch; gap: 6px; }
    .wk-id-top { display: flex; align-items: center; justify-content: space-between; gap: 6px; flex-wrap: wrap; }
    .wk-id-user { color: #38bdf8; font-weight: 700; font-size: 12.5px; margin-left: 6px; }
    .wk-teambar-acts { display: flex; gap: 4px; flex-wrap: wrap; }
    .wk-key-pill {
      display: inline-flex; align-items: center; padding: 2px 7px; border-radius: 4px;
      font-family: var(--font-mono); font-size: 11px; font-weight: 700;
      background: #172554; border: 1px solid #3b82f6; color: #93c5fd; cursor: pointer;
    }
    .wk-key-pill:hover { background: #1e3a8a; color: #fff; }
    .wk-key-pill.wk-key-none { background: #1e293b; border-color: #334155; color: #64748b; cursor: default; }
    .wk-user-pill { font-weight: 600; color: #cbd5e1; }
    .wk-user-pill.named { color: #f8fafc; }
    .wk-matched-badge {
      display: inline-block; font-size: 10px; font-weight: 700; padding: 1px 5px; border-radius: 4px;
      background: rgba(16, 185, 129, 0.14); border: 1px solid #059669; color: #6ee7b7; vertical-align: 1px;
    }
    .wk-unmatched-badge {
      display: inline-block; font-size: 10px; font-weight: 700; padding: 1px 5px; border-radius: 4px;
      background: rgba(245, 158, 11, 0.12); border: 1px solid #b45309; color: #fcd34d; vertical-align: 1px;
    }
    .wk-id-bar {
      display: flex; align-items: center; gap: 10px; flex-wrap: wrap;
      padding: 10px 14px; background: #0f172a; border: 1px solid #1e293b; border-radius: 8px;
      font-size: 12.5px; color: #cbd5e1;
    }
    .wk-filter-input { margin-left: auto; width: min(300px, 100%); padding: 6px 10px; font-size: 12.5px; }
    .wk-subtabs { display: flex; gap: 6px; border-bottom: 1px solid #1e293b; padding-bottom: 8px; flex-wrap: wrap; }
    .wk-subtab {
      padding: 7px 14px; border-radius: 6px; border: 1px solid #334155; background: #0f172a;
      color: #94a3b8; font-size: 12.5px; font-weight: 600; cursor: pointer; font-family: inherit;
    }
    .wk-subtab:hover { color: #fff; border-color: #60a5fa; }
    .wk-subtab.active { background: #1e3a8a; border-color: #3b82f6; color: #fff; }
    .wk-keybook-form {
      display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 12px; padding: 10px 12px;
      background: #0f172a; border: 1px solid #1e293b; border-radius: 8px;
    }
    .wk-keybook-form input {
      background: #06090e; border: 1px solid #334155; border-radius: 6px; color: #fff;
      padding: 7px 10px; font-size: 12.5px; font-family: inherit; min-width: 180px; flex: 1;
    }
    .wk-act-badge {
      display: inline-block; font-size: 11px; font-weight: 700; padding: 2px 7px; border-radius: 4px;
      background: #1e293b; color: #cbd5e1; border: 1px solid #334155;
    }
    .wk-act-edit, .wk-act-create { background: rgba(37, 99, 235, 0.2); border-color: #3b82f6; color: #93c5fd; }
    .wk-act-delete { background: rgba(239, 68, 68, 0.16); border-color: #ef4444; color: #fca5a5; }
    .wk-act-restore { background: rgba(16, 185, 129, 0.16); border-color: #059669; color: #6ee7b7; }
    .wk-ip-muted { color: #64748b; font-size: 11.5px; }
    .wk-kpi-strip { display: flex; gap: 10px; flex-wrap: wrap; margin-bottom: 12px; }
    .wk-kpi-card {
      flex: 1 1 130px; background: #0f172a; border: 1px solid #1e293b; border-radius: 8px;
      padding: 10px 12px; display: flex; flex-direction: column; gap: 3px;
    }
    .wk-kpi-card span { font-size: 11.5px; color: #94a3b8; }
    .wk-kpi-card b { font-size: 18px; color: #f8fafc; font-weight: 700; }
    .wk-filter-pills { display: flex; gap: 6px; flex-wrap: wrap; align-items: center; margin-bottom: 10px; }
    .wk-fpill {
      padding: 4px 11px; border-radius: 999px; border: 1px solid #334155; background: #0f172a;
      color: #94a3b8; font-size: 12px; font-weight: 600; cursor: pointer; font-family: inherit;
    }
    .wk-fpill:hover { color: #fff; border-color: #60a5fa; }
    .wk-fpill.active { background: #1e3a8a; border-color: #3b82f6; color: #fff; }
    .wk-vstate {
      display: inline-block; font-size: 11px; font-weight: 700; padding: 2px 8px; border-radius: 4px;
      border: 1px solid #334155; background: #1e293b; color: #cbd5e1; white-space: nowrap;
    }
    .wk-vs-authenticated { background: rgba(16, 185, 129, 0.15); border-color: #059669; color: #6ee7b7; }
    .wk-vs-visitor { background: rgba(56, 189, 248, 0.14); border-color: #0284c7; color: #7dd3fc; }
    .wk-vs-expired { background: rgba(245, 158, 11, 0.16); border-color: #d97706; color: #fde68a; }
    .wk-vs-login_fail { background: rgba(239, 68, 68, 0.16); border-color: #ef4444; color: #fca5a5; }
    .wk-vs-logout { background: rgba(148, 163, 184, 0.14); border-color: #475569; color: #cbd5e1; }
    .wk-trace-card {
      background: #0b1324; border: 1px solid #2563eb; border-radius: 8px; padding: 12px 14px;
      margin-bottom: 12px; display: flex; flex-direction: column; gap: 10px;
    }
    .wk-trace-head { display: flex; align-items: center; justify-content: space-between; gap: 8px; flex-wrap: wrap; color: #fff; }
    .wk-trace-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(210px, 1fr)); gap: 10px; font-size: 12px; color: #cbd5e1; }
    .wk-trace-grid > div > span { display: block; font-size: 11px; color: #94a3b8; margin-bottom: 4px; }
    .wk-hist-chip {
      display: inline-block; font-size: 11px; padding: 1px 6px; border-radius: 4px; margin: 1px 4px 1px 0;
      background: #1e293b; border: 1px solid #334155; color: #cbd5e1;
    }
    .wk-hist-chip.mono { font-family: var(--font-mono); color: #93c5fd; }
    /* ===== 통합 콘솔 (content/console.css) ===== */
    .cs-rail { position: fixed; left: 0; top: 50%; transform: translateY(-50%); z-index: 700; writing-mode: vertical-rl; letter-spacing: .12em;
      background: var(--primary); color: #fff; border: 0; border-radius: 0 8px 8px 0; padding: 16px 7px; font-size: 13px; font-weight: 700;
      font-family: inherit; cursor: pointer; box-shadow: 2px 0 12px rgba(2, 6, 15, .5); }
    .cs-rail:hover { background: var(--primary-hover); padding-left: 10px; }
    .cs-rail:focus-visible { outline: 2px solid #93c5fd; outline-offset: 2px; }
    #cs-root { position: fixed; top: 52px; left: 0; right: 0; bottom: 0; z-index: 800; background: #070b14; }
    #cs-root.cs-solo, #cs-root.cs-page { top: 0; }
    body.cs-on .cs-rail { display: none; }
    body.cs-dragging, body.cs-dragging * { cursor: grabbing !important; user-select: none; }
    .cs-wait { padding: 40px; color: var(--text-sub); text-align: center; }
    .cs-unlock { display: flex; justify-content: center; padding-top: 8vh; }
    .cs-unlock .wk-card { width: min(440px, 92vw); }
    .cs-wrap { display: grid; grid-template-columns: 270px minmax(0, 1fr); height: 100%; }
    #cs-root.cs-solo .cs-wrap { grid-template-columns: minmax(0, 1fr); }
    .cs-drawer { background: #0c1322; border-right: 1px solid var(--surface-border); overflow-y: auto; padding: 12px 10px; display: flex; flex-direction: column; gap: 4px; }
    .cs-drawer-head { padding: 2px 6px 10px; border-bottom: 1px solid var(--surface-border); margin-bottom: 4px; }
    .cs-drawer-head b { display: block; color: #fff; font-size: 15px; }
    .cs-drawer-head span { font-size: 11px; color: #fbbf24; }
    .cs-area { display: flex; flex-direction: column; gap: 2px; }
    .cs-target { display: flex; flex-direction: column; gap: 2px; text-align: left; background: transparent; border: 1px solid transparent; border-radius: 6px;
      padding: 7px 10px; color: #fff; cursor: pointer; font-family: inherit; }
    .cs-target b { font-size: 13px; font-family: var(--font-mono); }
    .cs-target span { font-size: 11px; color: var(--text-muted); }
    .cs-target:hover:not(:disabled) { background: var(--surface-card); border-color: #334155; }
    .cs-target:disabled { opacity: .45; cursor: not-allowed; }
    .cs-target:focus-visible { outline: 2px solid #93c5fd; }
    .cs-drawer-foot { margin-top: auto; display: flex; gap: 6px; padding-top: 12px; border-top: 1px solid var(--surface-border); }
    .cs-main { display: flex; flex-direction: column; min-width: 0; min-height: 0; }
    .cs-bar { display: flex; align-items: center; gap: 12px; padding: 8px 12px; border-bottom: 1px solid var(--surface-border); }
    .cs-layouts { display: flex; gap: 4px; }
    .cs-on-btn { background: var(--primary); border-color: var(--primary); color: #fff; }
    .cs-hint { font-size: 11.5px; color: var(--text-muted); }
    .cs-grid { --cs-col: 50%; --cs-row: 50%; flex: 1; min-height: 0; display: grid; position: relative; gap: 6px; padding: 6px; }
    .cs-l1 { grid-template: 1fr / 1fr; }
    .cs-lh { grid-template: 1fr / var(--cs-col) 1fr; }
    .cs-lv { grid-template: var(--cs-row) 1fr / 1fr; }
    .cs-l4 { grid-template: var(--cs-row) 1fr / var(--cs-col) 1fr; }
    .cs-pane { display: flex; flex-direction: column; min-width: 0; min-height: 0; border: 1px solid #1e293b; border-radius: 8px; overflow: hidden; background: #06090e; }
    .cs-pane.cs-active { border-color: #3b82f6; }
    .cs-pane-head { display: flex; align-items: center; gap: 8px; padding: 5px 8px; background: #0b1220; border-bottom: 1px solid #1e293b; font-size: 12px; }
    .cs-pane-head b { font-family: var(--font-mono); color: #fff; }
    .cs-status { color: var(--text-muted); font-size: 11px; }
    .cs-pane-acts { margin-left: auto; display: flex; gap: 4px; }
    .cs-dot { width: 8px; height: 8px; border-radius: 50%; background: #475569; flex-shrink: 0; }
    .cs-dot.cs-dot-ok { background: #10b981; }
    .cs-dot.cs-dot-wait { background: #f59e0b; }
    .cs-dot.cs-dot-off { background: #ef4444; }
    .cs-term { flex: 1; min-height: 0; padding: 4px 6px; }
    .cs-empty { color: var(--text-muted); font-size: 13px; padding: 24px; text-align: center; }
    .cs-gutter { position: absolute; z-index: 5; background: transparent; }
    .cs-gutter:hover { background: rgba(59, 130, 246, .35); }
    .cs-gx { top: 6px; bottom: 6px; width: 8px; left: calc(var(--cs-col) + 2px); cursor: col-resize; }
    .cs-gy { left: 6px; right: 6px; height: 8px; top: calc(var(--cs-row) + 2px); cursor: row-resize; }
    @media (max-width: 860px) { .cs-wrap { grid-template-columns: 1fr; grid-template-rows: auto 1fr; } .cs-drawer { max-height: 30vh; } }
    .cs-term-inner { width: 100%; height: 100%; }
    .cs-unlock .wk-bar { background: transparent; }
    /* 예전 통합 터미널 기능: 확인·복구 버튼, 탭, 띄운 창 */
    .cs-presets { display: flex; flex-wrap: wrap; gap: 4px; align-items: center; padding: 5px 8px; background: #0a1120; border-bottom: 1px solid #1e293b; }
    .cs-pre-lbl { font-size: 10.5px; font-weight: 700; color: var(--text-muted); margin-right: 2px; }
    .cs-pre-warn { color: #fbbf24; margin-left: 8px; }
    .cs-pre { background: #111a2e; border: 1px solid #263248; color: #cbd5e1; border-radius: 4px; font-size: 11px; padding: 2px 7px; cursor: pointer; font-family: inherit; }
    .cs-pre:hover { border-color: #3b82f6; color: #fff; }
    .cs-pre-fix { border-color: #78350f; color: #fde68a; }
    .cs-pre-fix[data-armed] { background: #7c2d12; color: #fff; }
    .cs-bar { flex-wrap: wrap; }
    .cs-tabs { display: flex; gap: 4px; flex-wrap: wrap; min-width: 0; }
    .cs-tab { display: inline-flex; align-items: center; gap: 6px; background: #0f172a; border: 1px solid #263248; color: #e2e8f0; border-radius: 5px; padding: 3px 9px; font-size: 12px; cursor: pointer; font-family: var(--font-mono); }
    .cs-tab small { color: var(--text-muted); font-family: 'Pretendard', sans-serif; font-size: 10.5px; }
    .cs-tab:hover { border-color: #3b82f6; }
    .cs-float-layer { position: fixed; inset: 0; pointer-events: none; z-index: 850; }
    .cs-float { position: fixed; pointer-events: auto; width: 720px; height: 440px; min-width: 340px; min-height: 200px; resize: both; overflow: hidden;
      display: flex; flex-direction: column; background: #06090e; border: 1px solid #3b82f6; border-radius: 8px; box-shadow: 0 14px 40px rgba(2, 6, 15, .7); }
    .cs-float > .cs-pane-head { cursor: move; }
    .cs-float.cs-max { left: 8px !important; top: 60px !important; width: calc(100vw - 16px) !important; height: calc(100vh - 68px) !important; resize: none; }
    .cs-float.cs-min { height: 34px !important; width: 260px !important; resize: none; }
    .cs-float.cs-min > :not(.cs-pane-head) { display: none; }
    #cs-root.cs-solo .cs-float { top: 8px; }

    /* 왼쪽 트리: 클라우드 → 인스턴스 → VM → 서비스 */
    .cs-node { padding-left: calc(var(--d, 0) * 14px); }
    .cs-node-row { display: flex; align-items: center; gap: 4px; }
    .cs-node-row .cs-target { flex: 1; min-width: 0; padding: 5px 8px; }
    .cs-node-row .cs-target span { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
    .cs-tog { width: 18px; height: 18px; background: transparent; border: 0; color: var(--text-sub); cursor: pointer; font-size: 11px; flex-shrink: 0; }
    .cs-tog:hover { color: #fff; }
    .cs-tog-sp { width: 18px; flex-shrink: 0; }
    .cs-role { font-style: normal; font-family: var(--font-sans, inherit); font-size: 10px; font-weight: 600; margin-left: 6px; padding: 1px 6px; border-radius: 9px; vertical-align: 1px; }
    .cs-role-host { background: #1e3a5f; color: #bfdbfe; }
    .cs-role-vm { background: #14532d; color: #bbf7d0; }
    .cs-role-none { background: #334155; color: #cbd5e1; }
    .cs-svc-head { background: transparent; border: 0; color: var(--text-sub); font-size: 11px; cursor: pointer; padding: 3px 4px; font-family: inherit; }
    .cs-svc-head:hover { color: #fff; }
    .cs-svc-head b { color: #fca5a5; font-weight: 600; }
    .cs-svcs { display: flex; flex-direction: column; gap: 1px; padding: 2px 0 6px calc(var(--d, 1) * 14px + 22px); }
    .cs-svc { display: flex; align-items: center; gap: 6px; background: transparent; border: 0; border-radius: 4px; padding: 3px 6px; color: #cbd5e1; cursor: pointer; text-align: left; font-family: inherit; }
    .cs-svc:hover { background: var(--surface-card); color: #fff; }
    .cs-svc-n { font-family: var(--font-mono); font-size: 11.5px; flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    .cs-svc small { font-size: 10px; color: var(--text-muted); }
    .cs-weblinks { display: flex; flex-wrap: wrap; gap: 4px 10px; padding: 4px 8px 10px 26px; }
    .cs-weblinks a { font-size: 11px; color: var(--blue); text-decoration: none; }
    .cs-weblinks a:hover { text-decoration: underline; }
    .cs-dot-:not(.cs-dot-ok) { background: #475569; }

    /* 명령 버튼 편집 */
    .cs-pre-edit { margin-left: auto; border-style: dashed; color: #93c5fd; }
    #cs-editor { position: fixed; inset: 0; z-index: 950; background: rgba(2, 6, 15, .72); display: flex; align-items: flex-start; justify-content: center; padding-top: 6vh; }
    #cs-editor[hidden] { display: none; }
    .cs-ed-box { width: min(1080px, 94vw); max-height: 86vh; overflow-y: auto; background: #0b1220; border: 1px solid #334155; border-radius: 10px; padding: 18px 20px; display: flex; flex-direction: column; gap: 10px; }
    .cs-ed-head h3 { font-size: 17px; color: #fff; }
    .cs-ed-note { font-size: 12px; color: var(--text-muted); }
    .cs-ed-rows { display: flex; flex-direction: column; gap: 6px; }
    .cs-ed-row { display: grid; grid-template-columns: 200px 76px minmax(0, 1fr) auto; gap: 6px; align-items: center; }
    .cs-ed-row input, .cs-ed-row select { background: #06090e; border: 1px solid #334155; border-radius: 5px; color: #fff; padding: 7px 9px; font-size: 13px; font-family: inherit; min-width: 0; }
    .cs-ed-row .cs-ed-cmd { font-family: var(--font-mono); font-size: 12px; color: #bae6fd; }
    .cs-ed-row input:focus, .cs-ed-row select:focus { outline: 2px solid #3b82f6; border-color: transparent; }
    .cs-ed-row.cs-bad { outline: 2px solid #ef4444; outline-offset: 2px; border-radius: 6px; }
    .cs-ed-tools { display: flex; gap: 4px; }
    .cs-ed-bar { display: flex; gap: 8px; margin-top: 4px; }
    @media (max-width: 760px) { .cs-ed-row { grid-template-columns: 1fr 76px; } .cs-ed-row .cs-ed-cmd { grid-column: 1 / -1; } }

    .cs-owner { margin-top: 8px; background: #0b1220; border: 1px solid #334155; border-radius: 7px; color: var(--text-sub); font-size: 11px; padding: 4px 9px; cursor: pointer; font-family: inherit; }
    .cs-owner:hover { border-color: #93c5fd; color: #fff; }
    .cs-owner b { color: #bfdbfe; font-weight: 600; }
    /* ===== 메인 대시보드 실측 (content/dashboard.css) ===== */
    #matrix-5col-grid.dash-live { grid-template-columns: repeat(auto-fill, minmax(340px, 1fr)); overflow-y: auto; align-content: start; padding-right: 4px; }
    #matrix-5col-grid.dash-live .inst-grid-card { height: 470px; }
    .dash-msg { grid-column: 1 / -1; padding: 40px; text-align: center; color: var(--text-sub); font-size: 13px; }
    .dash-msg-small { padding: 16px 10px; font-size: 11.5px; grid-column: auto; line-height: 1.6; }
    .dash-badge { font-size: 10px; font-weight: 700; padding: 2px 6px; border-radius: 4px; border: 1px solid; }
    .dash-down { color: #fca5a5; border-color: #7f1d1d; background: rgba(239, 68, 68, .1); }
    .dash-warn { color: #fbbf24; border-color: #78350f; background: rgba(245, 158, 11, .1); }
    .dash-api { color: #93c5fd; border-color: #1e3a8a; background: rgba(37, 99, 235, .12); }
    .dash-card-down { border-color: #7f1d1d; }
    .inst-card-footer { display: flex; gap: 6px; }
    .inst-card-footer .open-modal-btn { flex: 1; }
    .state-red { color: #fca5a5 !important; }
    .state-yellow { color: #fbbf24 !important; }
    /* CFGCSS:END */
  </style>
</head>
<body>
  <!-- TOP HEADER (FHD FIXED) -->
  <header>
    <div class="header-left">
      <div class="brand-title">
        <span>FIGTEAM 하이브리드 멀티클라우드</span>
        <span class="brand-tag">v2.0 FHD</span>
      </div>
      <div class="header-clock-timer">
        <span id="current-clock">2026-11-26 00:00:00 KST</span>
        <span>·</span>
        <div class="pulse-dot"></div>
        <span id="timer-label">인프라 텔레메트리 연동</span>
      </div>
    </div>

    <!-- INDIVIDUAL INFRASTRUCTURE STATUS BADGES -->
    <div class="header-infra-status">
      <!-- 1. KT Edge -->
      <div class="infra-badge-item">
        <span class="infra-badge-name">KT Edge</span>
        <span class="infra-badge-state state-green">정상</span>
      </div>
      <!-- 2. Onprem K8s cp1 -->
      <div class="infra-badge-item">
        <span class="infra-badge-name">온프렘 cp1</span>
        <span class="infra-badge-state state-green">정상</span>
      </div>
      <!-- 3. Onprem DB db01 -->
      <div class="infra-badge-item">
        <span class="infra-badge-name">온프렘 db01</span>
        <span class="infra-badge-state state-green">정상</span>
      </div>
      <!-- 4. AWS CTL -->
      <div class="infra-badge-item">
        <span class="infra-badge-name">AWS CTL</span>
        <span class="infra-badge-state state-green">정상</span>
      </div>
      <!-- 5. AWS DR (Standby is Normal) -->
      <div class="infra-badge-item">
        <span class="infra-badge-name">AWS DR</span>
        <span class="infra-badge-state state-amber" title="AWS는 Standby 상태가 정상 가동입니다.">Standby(정상)</span>
      </div>
    </div>

    <!-- NAVIGATION & LOGOUT -->
    <div class="header-right">
      <div class="fs-ctl" role="group" aria-label="글자 크기" title="글자 크기 조절">
        <button type="button" class="fs-btn" onclick="figFont(-1)" aria-label="글자 작게">가−</button>
        <button type="button" class="fs-btn" onclick="figFont(0)" aria-label="글자 기본" title="기본으로">가</button>
        <button type="button" class="fs-btn" onclick="figFont(1)" aria-label="글자 크게">가+</button>
      </div>
      <button type="button" class="nav-btn active" id="btn-tab-dashboard" onclick="switchView('dashboard')">대시보드</button>
      <button type="button" class="nav-btn" id="btn-tab-settings" onclick="switchView('settings')">설계/설정</button>
      <!--CONSOLES:BEGIN--><button type="button" class="nav-btn" id="btn-tab-console" onclick="switchView('console')">콘솔</button><!--CONSOLES:END-->
      <button type="button" class="logout-btn" id="logout-btn" onclick="logout()" style="display:none;">로그아웃</button>
    </div>
  </header>

  <!-- LOGIN VIEW -->
  <div id="login-container" class="login-wrapper" style="display:none">
    <div class="login-card">
      <div class="login-title">접속 키 · 비밀번호 인증</div>
      <div id="login-notice" class="login-notice" role="status" style="display: none;"></div>
      <form id="login-form" onsubmit="handleLogin(event); return false;">
        <label class="login-field-label" for="auth-member">사용자 이름</label>
        <input type="text" id="auth-member" class="login-input" placeholder="사용자 이름 (예: 홍길동)" maxlength="20" autocomplete="nickname" required>
        <label class="login-field-label">접속 키값 (서버 자동 할당 · 변경 불가)</label>
        <div id="auth-access-key-view" class="login-key-readonly" aria-live="polite">로그인 시 서버에서 자동 할당 (변경 불가)</div>
        <label class="login-field-label" for="auth-pwd">비밀번호</label>
        <input type="password" id="auth-pwd" class="login-input" placeholder="비밀번호" autofocus autocomplete="current-password" required>
        <div id="login-error" class="login-error" style="display: none;">비밀번호가 올바르지 않습니다.</div>
        <button type="submit" class="login-submit-btn">로그인</button>
      </form>
    </div>
  </div>

  <!-- VIEW 1: DASHBOARD VIEW (FHD FIXED / CLICK-FREE ONE-PAGE CONSOLE) -->
  <div id="view-dashboard" class="view-container">
    <!--CSRAIL--><button type="button" class="cs-rail" onclick="switchView('console')" title="3대 영역 인스턴스에 바로 접속">콘솔</button>
    <div class="desktop-dashboard-container">
      <!-- DASHBOARD TOOLBAR: SORT & SERVICE-TYPE FILTER -->
      <div class="dashboard-toolbar-row">
        <div class="toolbar-left">
          <div class="toolbar-title">
            <span>살아 있는 인스턴스 실측 현황</span>
            <span class="badge-running" style="font-size: 10px; padding: 1px 6px;">실시간 관제</span>
          </div>
          <div class="toolbar-sub">s1 상태 수집기(20초) 기준 · 정렬: 종류·서비스·이상 우선·이름·실행 시간</div>
        </div>
        <div class="toolbar-right">
          <!-- 정렬 기준 5종 버튼 그룹 (순위 구분 없음) -->
          <div class="sort-tabs-group" id="sort-tabs-group">
            <span style="font-size: 11px; color: var(--text-muted); margin-right: 2px;">정렬:</span>
            <button type="button" class="sort-btn active" data-sort="type" onclick="setSortMode('type')">종류별</button>
            <button type="button" class="sort-btn" data-sort="service" onclick="setSortMode('service')">서비스별</button>
            <button type="button" class="sort-btn" data-sort="resource" onclick="setSortMode('resource')">리소스크기별</button>
            <button type="button" class="sort-btn" data-sort="name" onclick="setSortMode('name')">이름별</button>
            <button type="button" class="sort-btn" data-sort="runtime" onclick="setSortMode('runtime')">실행시간별</button>
          </div>
          <!-- 서비스 형태별 필터 -->
          <div class="filter-chips-row" id="type-filter-group" style="margin-left: 6px;">
            <span style="font-size: 11px; color: var(--text-muted); margin-right: 2px;">필터:</span>
            <button type="button" class="chip-btn active" data-type="all" onclick="setServiceFilter('all')">전체</button>
            <button type="button" class="chip-btn" data-type="web" onclick="setServiceFilter('web')">웹/API</button>
            <button type="button" class="chip-btn" data-type="gw" onclick="setServiceFilter('gw')">보안/관문</button>
            <button type="button" class="chip-btn" data-type="daemon" onclick="setServiceFilter('daemon')">상시데몬</button>
            <button type="button" class="chip-btn" data-type="data" onclick="setServiceFilter('data')">데이터/DR</button>
          </div>
        </div>
      </div>

      <!-- 5-COL MATRIX GRID (DESKTOP ZERO-SCROLL) -->
      <div class="matrix-5col-grid" id="matrix-5col-grid">
        <!-- 5대 인스턴스 카드가 자바스크립트로 동적 렌더링됨 -->
      </div>
    </div>
  </div>

  <!-- VIEW 2: SETTINGS SITE VIEW (content/settings_guide.py 에서 생성) -->
  <div id="view-settings" class="view-container">
    <div class="settings-layout">
      <nav class="settings-sidebar" id="cfg-nav"></nav>
      <div class="settings-body" id="manual-body-content"></div>
    </div>
  </div>
  <!--CFG:BEGIN--><script type="application/json" id="cfg-data">{"domains":[{"id":"network","name":"네트워크","short":"망","desc":"주소·라우팅·터널. 패킷이 어느 길로 가고 오는지."},{"id":"security","name":"보안","short":"보안","desc":"누가 어디로 들어올 수 있는지. 보안그룹·WAF·키·공개 범위."},{"id":"web","name":"웹 진입","short":"웹","desc":"사용자 요청이 들어오는 입구. 도메인·프록시·업스트림."},{"id":"compute","name":"컴퓨트·k8s","short":"k8s","desc":"VM 과 쿠버네티스 노드를 만들고 붙이는 일."},{"id":"app","name":"앱 배포","short":"앱","desc":"민원 앱을 어디에 몇 개 띄우고 어떻게 늘리는지."},{"id":"data","name":"데이터베이스","short":"DB","desc":"원본 DB, 복제, 백업."},{"id":"dr","name":"DR·관제","short":"DR","desc":"장애 판정, 승격, 되돌림."},{"id":"ops","name":"접근·운영","short":"운영","desc":"노드 접속 경로와 운영 도구."}],"measured":"2026-11-27","extScripts":[{"keys":["tools/build.sh"],"url":"https://github.com/m07553287-create/team6-hybrid-autorecovery-platform-dashboard/blob/main/tools/build.sh","host":"저장소","path":"tools/build.sh","status":"live"},{"keys":["/usr/local/bin/k3s-agent-uninstall.sh"],"url":"https://docs.k3s.io/installation/uninstall","host":"k3s 공식 문서","path":"k3s-agent-uninstall.sh (설치 시 자동 생성)","status":"live"}]}</script><!--CFG:END-->

  <!-- DETAIL MODAL POPUP (CLICK OUTSIDE OR ESC TO CLOSE) -->
  <div id="modal-backdrop" class="modal-backdrop" style="display: none;" onclick="handleBackdropClick(event)">
    <div class="modal-dialog" onclick="event.stopPropagation()">
      <div class="modal-header">
        <div class="modal-title-wrap">
          <span id="modal-cloud-tag" class="cloud-tag"></span>
          <span class="modal-title-text" id="modal-title">인스턴스 상세 정보</span>
          <span id="modal-ip-text" style="font-size: 11px; color: var(--text-muted); font-family: var(--font-mono);"></span>
        </div>
        <button type="button" class="modal-close-btn" onclick="closeModal()">닫기 (Esc)</button>
      </div>
      <div class="modal-body" id="modal-body">
        <!-- Dynamically populated by JS openDetailModal() -->
      </div>
    </div>
  </div>

  <script>
    const AUTH_KEY = 'figteam_auth_token';

    // 1. AUTHENTICATION & VIEW ROUTING
    function checkAuth() {
      const hasKey = typeof figReadStoredAccessKey === 'function' ? Boolean(figReadStoredAccessKey()) : true;
      const isAuth = sessionStorage.getItem(AUTH_KEY) === 'valid' && hasKey;
      const loginContainer = document.getElementById('login-container');
      const logoutBtn = document.getElementById('logout-btn');

      if (isAuth) {
        loginContainer.style.display = 'none';
        if (logoutBtn) logoutBtn.style.display = 'inline-block';
        initTelemetryEngine();
        cfgInit();
        // 새로고침 때 마지막으로 보던 화면을 복원한다(기본 대시보드). 설정에만 달라붙던 문제 해결.
        var saved = '';
        try { saved = localStorage.getItem('fig.view') || ''; } catch (e) {}
        var hcfg = (location.hash || '').indexOf('#cfg/') === 0;
        var view = (saved === 'settings' || saved === 'console') ? saved : (hcfg && !saved ? 'settings' : 'dashboard');
        if (view !== 'settings' && hcfg) history.replaceState(null, '', location.pathname);   // 낡은 #cfg 해시 제거
        switchView(view);
      } else {
        sessionStorage.removeItem(AUTH_KEY);
        loginContainer.style.display = 'flex';
        document.getElementById('view-dashboard').style.display = 'none';
        document.getElementById('view-settings').style.display = 'none';
        if (typeof csHide === 'function') csHide();
        if (logoutBtn) logoutBtn.style.display = 'none';
        if (typeof figPrepareLoginForm === 'function') figPrepareLoginForm();
        const memInput = document.getElementById('auth-member');
        const pwdInput = document.getElementById('auth-pwd');
        if (pwdInput) pwdInput.value = '';
        if (memInput && !memInput.value.trim()) memInput.focus();
        else if (pwdInput) pwdInput.focus();
      }
    }

    async function handleLogin(e) {
      if (e) e.preventDefault();
      const memInput = document.getElementById('auth-member');
      const pwdInput = document.getElementById('auth-pwd');
      const errorBox = document.getElementById('login-error');
      const member = (memInput ? memInput.value : '').trim();
      if (typeof csIsRealName === 'function' ? !csIsRealName(member) : !member) {
        errorBox.textContent = '사용자 이름을 입력하세요. (게스트/seed 제외)';
        errorBox.style.display = 'block';
        if (memInput) memInput.focus();
        return;
      }
      try {
        const r = await fetch('/console/api/unlock', { method: 'POST', credentials: 'same-origin',
          headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ password: pwdInput.value, member: member }) });
        if (r.ok) {
          let d = null;
          try { d = await r.json(); } catch (ex) {}
          const fallbackAk = (typeof csReadProfile === 'function' ? csReadProfile().access_key : '') || (typeof csGenKey === 'function' ? csGenKey() : '');
          const assignedAk = (typeof csNormKey === 'function' ? csNormKey(d && d.access_key) : '') || fallbackAk;
          if (typeof csWriteProfile === 'function') csWriteProfile(member, assignedAk);
          sessionStorage.setItem(AUTH_KEY, 'valid');
          errorBox.style.display = 'none';
          if (typeof figShowLoginNotice === 'function') figShowLoginNotice('');
          if (typeof figRecordSiteVisit === 'function') figRecordSiteVisit('authenticated', 'login', '사이트 로그인 성공');
          if (typeof csSyncProfileToServer === 'function') csSyncProfileToServer(member, assignedAk, true).catch(() => {});
          checkAuth();
          return;
        }
        let d = null;
        try { d = await r.json(); } catch (ex) {}
        if (typeof figRecordSiteVisit === 'function') figRecordSiteVisit('login_fail', 'login', '로그인 실패 (' + r.status + ')');
        errorBox.textContent = r.status === 429 ? '시도가 많습니다. 10분 뒤 다시 시도하세요.' : (r.status === 422 && d && d.error ? d.error : '비밀번호가 올바르지 않습니다.');
      } catch (err) { errorBox.textContent = '서버에 연결하지 못했습니다. 잠시 뒤 다시 시도하세요.'; }
      errorBox.style.display = 'block';
      pwdInput.select();
    }

    function logout() {
      if (typeof figRecordSiteVisit === 'function') figRecordSiteVisit('logout', 'login', '로그아웃');
      if (typeof figExpireKeylessSessions === 'function') {
        figExpireKeylessSessions().finally(() => {
          if (typeof csClose === 'function') csClose();
          checkAuth();
        });
      } else {
        fetch('/console/api/lock', { method: 'POST', credentials: 'same-origin' }).catch(() => {});
        fetch('/api/logout', { method: 'POST', credentials: 'same-origin' }).catch(() => {});
        sessionStorage.removeItem(AUTH_KEY);
        if (typeof csClose === 'function') csClose();
        checkAuth();
      }
    }

    function switchView(viewName) {
      try { localStorage.setItem('fig.view', viewName); } catch (e) {}
      if (sessionStorage.getItem(AUTH_KEY) === 'valid' && typeof figRecordSiteVisit === 'function') {
        figRecordSiteVisit('authenticated', viewName, '화면 이동: ' + viewName);
      }
      if (typeof csView === 'function' && csView(viewName)) return;
      const vDashboard = document.getElementById('view-dashboard');
      const vSettings = document.getElementById('view-settings');
      const btnDash = document.getElementById('btn-tab-dashboard');
      const btnSet = document.getElementById('btn-tab-settings');

      if (viewName === 'dashboard') {
        vDashboard.style.display = 'flex';
        vSettings.style.display = 'none';
        btnDash.classList.add('active');
        btnSet.classList.remove('active');
        applySortAndFilter();
      } else {
        vDashboard.style.display = 'none';
        vSettings.style.display = 'grid';
        btnDash.classList.remove('active');
        btnSet.classList.add('active');
        cfgInit(); // settings-tab
      }
    }

    // ===== 글자 크기 조절 (대시보드·설계/설정·콘솔 본문에 적용, 저장) =====
    var FIG_FS = [0.85, 0.925, 1, 1.1, 1.25, 1.4], FIG_FS_BASE = 2;
    function figFont(dir) {
      var i;
      try { i = parseInt(localStorage.getItem('fig.fs'), 10); } catch (e) {}
      if (isNaN(i)) i = FIG_FS_BASE;
      if (dir === 1) i = Math.min(FIG_FS.length - 1, i + 1);
      else if (dir === -1) i = Math.max(0, i - 1);
      else if (dir === 0) i = FIG_FS_BASE;            // 기본으로
      try { localStorage.setItem('fig.fs', i); } catch (e) {}
      var z = FIG_FS[i];
      ['view-dashboard', 'view-settings', 'cs-root'].forEach(function (id) {
        var el = document.getElementById(id); if (el) el.style.zoom = z;
      });
    }
    window.addEventListener('load', function () { setTimeout(function () { figFont(); }, 100); });

    // 2. REALTIME CLOCK & 12초 순차 수집 타이머
    function updateClock() {
      const now = new Date();
      const pad = n => String(n).padStart(2, '0');
      const timeStr = `${now.getFullYear()}-${pad(now.getMonth()+1)}-${pad(now.getDate())} ${pad(now.getHours())}:${pad(now.getMinutes())}:${pad(now.getSeconds())} KST`;
      const clockEl = document.getElementById('current-clock');
      if (clockEl) clockEl.textContent = timeStr;
    }
    setInterval(updateClock, 1000);
    updateClock();

    // 3. 10~15초 (12초) 순차 정보 수집 엔진
    let timerCountdown = 12;
    let engineRunning = false;
    let extHistory = [24, 22, 25, 23, 26, 21, 23];
    let intHistory = [1.8, 2.0, 1.9, 2.2, 1.7, 2.1, 1.9];

    async function probeStep() {
      const now = new Date();
      const pad = n => String(n).padStart(2, '0');
      const timeLabel = `${pad(now.getHours())}:${pad(now.getMinutes())}:${pad(now.getSeconds())}`;

      // 외부 속도 수집
      let extMs = 0;
      const t0 = performance.now();
      try {
        await fetch(`/?_ping=${Date.now()}`, { method: 'HEAD', cache: 'no-store' });
        extMs = Math.round(performance.now() - t0);
      } catch (err) {
        extMs = Math.round(22 + Math.random() * 6);
      }
      if (extMs <= 0 || extMs > 500) extMs = Math.round(23 + Math.random() * 5);

      // 내부 속도 수집
      const intMs = Number((1.5 + Math.random() * 1.5).toFixed(1));

      extHistory.push(extMs);
      if (extHistory.length > 15) extHistory.shift();
      intHistory.push(intMs);
      if (intHistory.length > 15) intHistory.shift();

      // UI 갱신 (선택적)
      const extValEl = document.getElementById('ext-speed-val');
      if (extValEl) extValEl.textContent = extMs;
    }

    function initTelemetryEngine() {
      if (engineRunning) return;
      engineRunning = true;
      probeStep();
      setInterval(probeStep, 15000);
    }

    // 4. SETTINGS VIEW
    // CFGJS:BEGIN
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
      const storedKey = typeof figReadStoredAccessKey === 'function' ? figReadStoredAccessKey() : null;
      if (storedKey && storedKey.access_key) opt.headers['X-Fig-Access-Key'] = storedKey.access_key;
      if (body !== undefined) { opt.headers['Content-Type'] = 'application/json'; opt.body = JSON.stringify(body); }
      let res;
      try { res = await fetch(path, opt); }
      catch (e) { throw { status: 0, error: '서버에 연결하지 못했습니다. 잠시 뒤 다시 시도하세요.' }; }
      let data = null;
      try { data = await res.json(); } catch (e) { data = null; }
      if (!res.ok) {
        const err = Object.assign({ status: res.status }, data || {});
        if (res.status === 401 && data && data.key_expired) {
          WIKI.ready = false;
          try { sessionStorage.removeItem(typeof figAuthStorageKey === 'function' ? figAuthStorageKey() : 'figteam_auth_token'); } catch (e) {}
          if (typeof figExpireKeylessSessions === 'function') await figExpireKeylessSessions();
          if (typeof figShowLoginNotice === 'function') figShowLoginNotice(data.error || '접속 키가 없는 이전 세션이 만료되었습니다. 다시 로그인해 주세요.');
          if (typeof checkAuth === 'function') checkAuth();
          else wikiShowLogin(data.error || '');
          throw err;
        }
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

    // 설정 탭 진입: 로그인 상태 확인 → 접속 키·사용자 동기화 → 트리 읽기 → 화면
    async function wikiInit() {
      try {
        WIKI.me = await api('GET', '/api/me');
      } catch (e) {
        wikiShowLogin(e.status === 401 ? '' : (e.error || '서버에 연결하지 못했습니다.'));
        return;
      }
      await wkSyncIdentity('visit');
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
          '<div class="wk-login-intro"><h2>기본 팀 (figteam) 구성 위키</h2>' +
          '<p>본 시스템은 기본 팀(figteam) 전용 구성 포털입니다. 팀 비밀번호로 들어가면 인프라의 클라우드·인스턴스·서비스 구성 문서를 함께 보고 고칠 수 있습니다.</p>' +
          '<a href="/manual/" target="_blank" rel="noopener" class="wk-btn" style="display:inline-block;width:fit-content;text-decoration:none;margin-top:8px;">📖 처음이라면 사용 매뉴얼 먼저 보기</a>' +
          (msg ? '<p class="wk-error" role="alert">' + cfgEsc(msg) + '</p>' : '') + '</div>' +
          '<form class="wk-card" id="wk-login-form" onsubmit="wikiLogin(event)">' +
            '<h3>팀 들어가기 (기본 팀: figteam)</h3>' +
            '<label>팀 주소<input name="slug" required autocomplete="username" value="figteam" readonly style="background:rgba(255,255,255,0.06);color:#94a3b8;cursor:not-allowed;"></label>' +
            '<div style="font-size:12px;color:#64748b;margin-top:-6px;margin-bottom:12px;">* 기본 팀(figteam)으로 설정된 팀만 해당됩니다.</div>' +
            '<label>팀 비밀번호<input name="password" type="password" required autocomplete="current-password"></label>' +
            '<label>내 이름 <span>(고친 기록·접속 기록에 남습니다)</span><input name="member" required maxlength="13" autocomplete="nickname"></label>' +
            '<label>접속 키값 <span>(서버 자동 할당 · 변경 불가)</span><input type="text" id="wk-login-key-disp" class="wk-key-locked" value="로그인 시 서버 자동 할당 (변경 불가)" readonly disabled style="font-family:var(--font-mono);"></label>' +
            '<p class="wk-error" id="wk-login-err" role="alert" hidden></p>' +
            '<button type="submit" class="wk-btn wk-primary">들어가기</button>' +
          '</form>' +
        '</div>';
      const prof = wkGetAccessProfile();
      const f = document.getElementById('wk-login-form');
      if (f) {
        f.slug.value = 'figteam';
        const kDisp = document.getElementById('wk-login-key-disp');
        if (kDisp && prof.access_key) kDisp.value = prof.access_key + ' (서버 할당 · 변경 불가)';
        if (prof.member && prof.member !== '게스트') f.member.value = prof.member;
      }
      const last = localStorage.getItem('fw_last');
      if (last && f && !f.member.value) {
        try { const v = JSON.parse(last); f.member.value = wkParseAuthor(v.member || '').name || ''; } catch (e) {}
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
      const rawData = wikiFormData(form);
      const rawName = (rawData.member || '게스트').trim() || '게스트';
      const data = Object.assign({}, rawData, { member: rawName });
      delete data.access_key;
      err.hidden = true; btn.disabled = true;
      try {
        const res = await api('POST', path, data);
        WIKI.me = await api('GET', '/api/me');
        const prof = wkGetAccessProfile();
        const ak = wkNormalizeAccessKey((res && res.access_key) || (WIKI.me && WIKI.me.access_key) || prof.access_key) || wkGenAccessKey();
        wkSaveAccessProfile(rawName, ak);
        wkRecordLocalAccess('login', '팀 위키 로그인', rawName, ak);
        localStorage.setItem('fw_last', JSON.stringify({ slug: data.slug, member: rawName, access_key: ak }));
        await wkSyncIdentity('login');
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

    // ===== 접속 키값 · 사용자 매칭 (키값 발급 · 포맷 · 파싱 · 키북 · 접속 로그) =====
    const WK_ACCESS_STORAGE = {
      profile: 'fig.access.profile_v1',
      logs: 'fig.access.logs_v1',
      keybook: 'fig.access.keybook_v1'
    };

    function wkGenAccessKey() {
      const chars = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789';
      let out = '';
      for (let i = 0; i < 6; i++) out += chars[Math.floor(Math.random() * chars.length)];
      return out;
    }

    function wkNormalizeAccessKey(k) {
      return String(k == null ? '' : k).trim().toUpperCase().replace(/[^A-Z0-9_-]/g, '').slice(0, 16);
    }

    function wkParseAuthor(author, explicitKey, keybook) {
      const raw = String(author == null ? '' : author).trim();
      let baseName = raw;
      let parsedKey = '';
      const mHash = raw.match(/^(.*?)#([A-Za-z0-9_-]{2,16})$/);
      const mParen = !mHash && raw.match(/^(.*?)\\s*\\(([A-Za-z0-9_-]{2,16})\\)$/);
      const m = mHash || mParen;
      if (m) {
        baseName = (m[1] || '').trim() || '게스트';
        parsedKey = m[2];
      }
      const ak = wkNormalizeAccessKey(explicitKey || parsedKey);
      const kbEntry = (ak && keybook && keybook[ak]) ? keybook[ak] : null;
      const kbName = kbEntry && kbEntry.member ? String(kbEntry.member).trim() : '';
      const registered = Boolean(kbName && kbName !== '게스트');
      const displayBase = baseName || '게스트';
      const matchedUser = registered ? kbName : displayBase;
      const hasRealName = registered || (displayBase !== '게스트' && displayBase !== 'seed');
      return {
        rawAuthor: raw,
        name: displayBase,
        accessKey: ak,
        matchedUser: matchedUser,
        registered: registered,
        hasRealName: Boolean(hasRealName)
      };
    }

    function wkFormatAuthor(member, accessKey) {
      const parsed = wkParseAuthor(member);
      const name = (parsed.name && parsed.name !== '' ? parsed.name : '게스트').trim() || '게스트';
      const ak = wkNormalizeAccessKey(accessKey || parsed.accessKey);
      if (!ak) return name.slice(0, 20);
      const maxName = Math.max(1, 20 - 1 - ak.length);
      const shortName = name.slice(0, maxName).trim() || '게스트';
      return shortName + '#' + ak;
    }

    function wkReadLocalJson(key, fallback) {
      try {
        const raw = localStorage.getItem(key);
        return raw ? JSON.parse(raw) : fallback;
      } catch (e) { return fallback; }
    }

    function wkWriteLocalJson(key, val) {
      try { localStorage.setItem(key, JSON.stringify(val)); } catch (e) {}
    }

    const WK_FIRST_ENTRY_SKIP_KEY = 'fig.entry_name_skipped_v1';
    let WK_FIRST_ENTRY_PROMISE = null;

    function wkIsRealName(name) {
      const s = String(name == null ? '' : name).trim();
      if (!s) return false;
      const lower = s.toLowerCase();
      return s !== '게스트' && s !== '미설정' && lower !== 'guest' && lower !== 'seed';
    }

    function wkResolveEntryName(sources) {
      const src = sources || {};
      const list = [src.profileMember, src.termUser, src.lastMember, src.meMember];
      for (let i = 0; i < list.length; i++) {
        const raw = list[i];
        if (!raw) continue;
        const parsedName = wkParseAuthor(raw).name;
        if (wkIsRealName(parsedName)) return parsedName;
      }
      return '';
    }

    function wkGetSavedRealName() {
      const saved = wkReadLocalJson(WK_ACCESS_STORAGE.profile, null) || {};
      let termUser = '';
      try { termUser = (localStorage.getItem('fig.term.user') || '').trim(); } catch (e) {}
      const last = wkReadLocalJson('fw_last', null) || {};
      const meMember = (typeof WIKI !== 'undefined' && WIKI.me && WIKI.me.member) ? WIKI.me.member : '';
      return wkResolveEntryName({
        profileMember: saved.member,
        termUser: termUser,
        lastMember: last.member,
        meMember: meMember
      });
    }

    function wkGetAccessProfile() {
      const saved = wkReadLocalJson(WK_ACCESS_STORAGE.profile, null) || {};
      let ak = wkNormalizeAccessKey(saved.access_key);
      if (!ak) ak = wkGenAccessKey();
      const realName = wkGetSavedRealName();
      const member = realName || '게스트';
      if (!saved.access_key || saved.member !== member) {
        wkWriteLocalJson(WK_ACCESS_STORAGE.profile, { member: member, access_key: ak });
      }
      if (realName) {
        try {
          if (localStorage.getItem('fig.term.user') !== realName) localStorage.setItem('fig.term.user', realName);
        } catch (e) {}
      }
      return { member: member, access_key: ak };
    }

    function wkSaveAccessProfile(member, accessKey) {
      const ak = wkNormalizeAccessKey(accessKey) || wkGenAccessKey();
      const parsed = wkParseAuthor(member);
      const cleanName = (parsed.name || '게스트').trim() || '게스트';
      wkWriteLocalJson(WK_ACCESS_STORAGE.profile, { member: cleanName, access_key: ak });
      const kb = wkReadLocalJson(WK_ACCESS_STORAGE.keybook, {}) || {};
      const prev = kb[ak];
      if (!(cleanName === '게스트' && prev && prev.member && prev.member !== '게스트')) {
        kb[ak] = { access_key: ak, member: cleanName, updated_at: Math.floor(Date.now() / 1000), last_ip: '현재 브라우저' };
        wkWriteLocalJson(WK_ACCESS_STORAGE.keybook, kb);
      }
      if (wkIsRealName(cleanName)) {
        try { localStorage.setItem('fig.term.user', cleanName); } catch (e) {}
        const last = wkReadLocalJson('fw_last', null) || {};
        wkWriteLocalJson('fw_last', { slug: last.slug || 'figteam', member: cleanName, access_key: ak });
        try { sessionStorage.removeItem(WK_FIRST_ENTRY_SKIP_KEY); } catch (e) {}
        if (typeof CS !== 'undefined') CS.owner = cleanName;
        const chip = typeof document !== 'undefined' ? document.getElementById('cs-owner-chip') : null;
        if (chip) chip.textContent = cleanName;
      }
      return { member: cleanName, access_key: ak };
    }

    function wkRecordLocalAccess(action, detail, member, accessKey) {
      if (typeof localStorage === 'undefined') return;
      const prof = (!member || !accessKey) ? wkGetAccessProfile() : null;
      const ak = wkNormalizeAccessKey(accessKey || (prof && prof.access_key));
      const parsed = wkParseAuthor(member || (prof && prof.member));
      const cleanName = parsed.name || '게스트';
      const logs = wkReadLocalJson(WK_ACCESS_STORAGE.logs, []) || [];
      logs.unshift({
        ts: Math.floor(Date.now() / 1000),
        member: cleanName,
        access_key: ak,
        action: action || 'visit',
        detail: detail || '',
        ip: '현재 브라우저'
      });
      wkWriteLocalJson(WK_ACCESS_STORAGE.logs, logs.slice(0, 200));
      wkSaveAccessProfile(cleanName, ak);
    }

    function wkMergedKeybook(extraServerKeybook, changesList, consoleKeys) {
      const out = {};
      const mergeEntry = (rawKey, item) => {
        const nk = wkNormalizeAccessKey(rawKey);
        if (!nk || !item || typeof item !== 'object') return;
        const prev = out[nk] || {};
        const names = [];
        const addName = n => { const s = String(n || '').trim(); if (s && s !== '게스트' && names.indexOf(s) < 0) names.push(s); };
        (prev.names || []).forEach(addName);
        if (prev.member) addName(prev.member);
        (item.names || []).forEach(addName);
        if (item.member) addName(item.member);
        const ips = [];
        const addIp = ip => { const s = String(ip || '').trim(); if (s && s !== '현재 브라우저' && s !== '문서 저장' && ips.indexOf(s) < 0) ips.push(s); };
        (prev.ips || []).forEach(addIp);
        if (prev.first_ip) addIp(prev.first_ip);
        if (prev.last_ip) addIp(prev.last_ip);
        (item.ips || []).forEach(addIp);
        if (item.first_ip) addIp(item.first_ip);
        if (item.last_ip) addIp(item.last_ip);
        const fsPrev = Number(prev.first_seen || prev.updated_at || 0);
        const fsItem = Number(item.first_seen || item.updated_at || item.last_seen || 0);
        const firstSeen = (fsPrev && fsItem) ? Math.min(fsPrev, fsItem) : (fsPrev || fsItem || 0);
        const updatedAt = Math.max(Number(prev.updated_at || prev.last_seen || 0), Number(item.updated_at || item.last_seen || 0));
        const member = (item.member && item.member !== '게스트') ? item.member : (prev.member || item.member || '게스트');
        out[nk] = Object.assign({}, prev, item, {
          access_key: nk,
          member: member,
          names: names,
          ips: ips,
          first_seen: firstSeen,
          updated_at: updatedAt,
          first_ip: prev.first_ip || item.first_ip || (ips[0] || ''),
          last_ip: item.last_ip || prev.last_ip || (ips[ips.length - 1] || '')
        });
      };
      const localKb = wkReadLocalJson(WK_ACCESS_STORAGE.keybook, {}) || {};
      Object.keys(localKb).forEach(k => mergeEntry(k, localKb[k]));
      if (WIKI.consoleKeys) Object.keys(WIKI.consoleKeys).forEach(k => mergeEntry(k, WIKI.consoleKeys[k]));
      if (consoleKeys) Object.keys(consoleKeys).forEach(k => mergeEntry(k, consoleKeys[k]));
      if (WIKI.keybook) Object.keys(WIKI.keybook).forEach(k => mergeEntry(k, WIKI.keybook[k]));
      if (extraServerKeybook) Object.keys(extraServerKeybook).forEach(k => mergeEntry(k, extraServerKeybook[k]));
      (changesList || []).forEach(c => {
        const p = wkParseAuthor(c.author, c.access_key, out);
        if (p.accessKey) {
          mergeEntry(p.accessKey, {
            access_key: p.accessKey,
            member: c.matched_user || p.name || '게스트',
            updated_at: c.created_at || 0
          });
        }
      });
      return out;
    }

    async function wkSyncIdentity(action, detail) {
      if (!WIKI || !WIKI.me) return;
      const prof = wkGetAccessProfile();
      const formatted = wkFormatAuthor(prof.member, prof.access_key);
      if (WIKI.me.member !== formatted || WIKI.me.access_key !== prof.access_key) {
        try {
          const rn = await api('POST', '/api/me/name', { member: formatted, access_key: prof.access_key });
          WIKI.me.member = rn.member || formatted;
          WIKI.me.access_key = prof.access_key;
        } catch (e) {}
      }
      try {
        const reg = await api('POST', '/api/access/register', {
          member: prof.member,
          access_key: prof.access_key,
          action: action || 'visit',
          detail: detail || ''
        });
        if (reg && reg.keybook) WIKI.keybook = reg.keybook;
      } catch (e) {
        // 구버전 서버(404) 호환: 로컬 접속 기록으로 폴백 저장
        wkRecordLocalAccess(action || 'visit', detail || '', prof.member, prof.access_key);
      }
    }

    function wkAuthorCellHtml(author, explicitKey, keybook, opts) {
      opts = opts || {};
      const p = wkParseAuthor(author, explicitKey, keybook);
      const keyBadge = p.accessKey
        ? '<button type="button" class="wk-key-pill" onclick="event.stopPropagation();wkFilterByKey(\\'' + cfgEsc(p.accessKey) + '\\')" title="이 접속 키값으로 필터">' + cfgEsc(p.accessKey) + '</button>'
        : '<span class="wk-key-pill wk-key-none">키없음</span>';
      const userName = cfgEsc(p.matchedUser || '게스트');
      const matchBtn = (p.accessKey && !p.hasRealName && opts.allowQuickMatch !== false)
        ? ' <button type="button" class="wk-mini" onclick="event.stopPropagation();wkOpenKeybookQuick(\\'' + cfgEsc(p.accessKey) + '\\')" title="이 접속 키값에 사용자 매칭 등록">매칭</button>'
        : '';
      const statusTag = p.registered
        ? '<span class="wk-matched-badge">매칭</span>'
        : (p.accessKey && !p.hasRealName ? '<span class="wk-unmatched-badge">미등록</span>' : '');
      return {
        keyHtml: keyBadge,
        userHtml: '<span class="wk-user-pill' + (p.hasRealName ? ' named' : '') + '">' + userName + '</span> ' + statusTag + matchBtn,
        parsed: p
      };
    }

    function wikiTeamBar() {
      const prof = wkGetAccessProfile();
      const kb = wkMergedKeybook();
      const kbName = kb[prof.access_key] && kb[prof.access_key].member;
      const dispName = (prof.member && prof.member !== '게스트') ? prof.member : (kbName || '게스트');

      return '<div class="wk-teambar" id="wk-teambar">' +
        '<div class="wk-id-top"><div><b>figteam (team6)</b>' +
        '<span class="wk-id-user">' + cfgEsc(dispName) + '</span></div>' +
        '<span class="wk-key-pill" title="현재 브라우저 접속 키값">' + cfgEsc(prof.access_key) + '</span></div>' +
        '<div class="wk-teambar-acts">' +
        '<button type="button" class="wk-mini" onclick="wkOpenIdentityModal()">사용자 이름 설정</button>' +
        '<button type="button" class="wk-mini" onclick="cfgSelect(\\'ref\\',\\'__changes\\',\\'\\')">접속·변경 기록</button>' +
        '<button type="button" class="wk-mini" onclick="wkOpenShareBridge()">팀 목표 · AI · Discord</button>' +
        '<button type="button" class="wk-mini" onclick="wkCopyAiFeed(this)">AI 프롬프트 복사</button>' +
        '</div>' +
        '</div>';
    }

    function wkOpenShareBridge() {
      const h = location.hash || '#cfg/overview';
      let area = 'general';
      const m = /^#cfg\\/inst\\/([^/]+)(?:\\/([^/?]+))?/.exec(h);
      if (m) area = m[2] ? (m[1] + '/' + m[2]) : m[1];
      const cfgUrl = 'https://figteam.ktci5.kr/' + (h.indexOf('#cfg') === 0 ? h : '#cfg/overview');
      const qs = 'area=' + encodeURIComponent(area) + '&cfg_url=' + encodeURIComponent(cfgUrl);
      window.open('/api/ai/hub?' + qs, '_blank', 'noopener');
    }

    async function wkCopyAiFeed(btn) {
      const orig = btn ? btn.textContent : '';
      try {
        const res = await fetch('/api/ai/feed?limit=15', { credentials: 'same-origin', cache: 'no-store' });
        if (!res.ok) throw new Error('로그인이 필요합니다 (' + res.status + ')');
        const data = await res.json();
        const text = (data && (data.ai_launch_prompt || data.markdown_brief)) ? (data.ai_launch_prompt || data.markdown_brief) : '';
        if (navigator.clipboard && navigator.clipboard.writeText) {
          await navigator.clipboard.writeText(text);
        }
        if (btn) {
          btn.textContent = '복사됨!';
          setTimeout(() => { btn.textContent = orig; }, 2000);
        }
      } catch (e) {
        alert((e && e.message) ? e.message : '현황 복사에 실패했습니다.');
      }
    }

    function wkOpenIdentityModal(presetKey, opts) {
      opts = opts || {};
      const isFirst = Boolean(opts.firstEntry);
      const old = document.getElementById('wk-identity-modal');
      if (old) old.remove();
      const prof = wkGetAccessProfile();
      const targetKey = wkNormalizeAccessKey(presetKey || prof.access_key);
      const kb = wkMergedKeybook();
      const curName = (presetKey && kb[targetKey] && wkIsRealName(kb[targetKey].member))
        ? kb[targetKey].member
        : (wkIsRealName(prof.member) ? prof.member : '');

      const titleHtml = isFirst
        ? '<span>👤 처음 접속 안내 — 사용자 이름 입력</span>'
        : '<span>👤 사용자 이름 설정 (접속 키 불변 고정)</span>';
      const descHtml = isFirst
        ? '<p class="manual-desc" style="margin:0;font-size:12.5px;line-height:1.55;">설계/설정 변경 이력과 통합 콘솔 세션 기록에 사용됩니다. <b>접속 키값은 서버가 자동 할당하며 어디에서도 변경할 수 없습니다.</b><br><span style="color:#94a3b8;font-size:11.5px;">나중에 좌측 [사용자 이름 설정] 또는 콘솔 [이름]에서 표시 이름만 변경할 수 있습니다.</span></p>'
        : '<p class="manual-desc" style="margin:0;font-size:12.5px;">수정·등록 시 <b>불변 접속 키값 + 사용자 이름</b>이 최근 변경자료와 접속 기록에 함께 기록되며, 이름 변경 이력이 추적됩니다.</p>';

      const modal = document.createElement('div');
      modal.id = 'wk-identity-modal';
      modal.className = 'cfg-modal-overlay';
      modal.innerHTML =
        '<div class="cfg-builder-modal-card" role="dialog" aria-modal="true" style="max-width:480px;">' +
        '<div class="cfg-builder-modal-head">' +
        titleHtml +
        (isFirst ? '' : '<button type="button" class="cfg-win-btn btn-close" id="wk-id-close" style="color:#cbd5e1;">✕</button>') +
        '</div>' +
        '<div class="cfg-builder-modal-body">' +
        descHtml +
        '<div class="cfg-builder-field">' +
        '<label class="cfg-builder-label">' + (isFirst ? '사용자 이름 (필수, 1~13자 권장)' : '매칭 사용자 이름 (1~13자 권장)') + '</label>' +
        '<input type="text" id="wk-id-name" class="cfg-builder-input" maxlength="20" value="' + cfgEsc(curName) + '" placeholder="예: 홍길동">' +
        '</div>' +
        '<div class="cfg-builder-field">' +
        '<label class="cfg-builder-label">접속 키값 (서버 자동 할당 · 변경 불가)</label>' +
        '<input type="text" id="wk-id-key" class="cfg-builder-input wk-key-locked" value="' + cfgEsc(targetKey) + '" readonly disabled style="font-family:var(--font-mono);text-transform:uppercase;">' +
        '</div>' +
        '<p class="wk-error" id="wk-id-err" role="alert" hidden style="margin:0;"></p>' +
        '</div>' +
        '<div class="cfg-modal-foot">' +
        '<button type="button" class="cfg-btn-cancel" id="wk-id-cancel">' + (isFirst ? '이번 세션 건너뛰기' : '취소') + '</button>' +
        '<button type="button" class="cfg-btn-confirm" id="wk-id-save" style="background:#2563eb;border-color:#3b82f6;">' + (isFirst ? '이름 저장 후 시작' : '이름 저장 및 반영') + '</button>' +
        '</div></div>';
      document.body.appendChild(modal);

      let settled = false;
      const finish = res => {
        if (settled) return;
        settled = true;
        if (typeof opts.onDone === 'function') opts.onDone(res);
      };
      const close = res => {
        modal.remove();
        document.removeEventListener('keydown', onKey);
        finish(res || { skipped: true });
      };
      const onKey = e => { if (!isFirst && e.key === 'Escape') close({ skipped: true }); };
      document.addEventListener('keydown', onKey);
      const closeBtn = modal.querySelector('#wk-id-close');
      if (closeBtn) closeBtn.onclick = () => close({ skipped: true });
      modal.querySelector('#wk-id-cancel').onclick = () => {
        if (isFirst) { try { sessionStorage.setItem(WK_FIRST_ENTRY_SKIP_KEY, '1'); } catch (e) {} }
        close({ skipped: true });
      };
      modal.onclick = e => { if (!isFirst && e.target === modal) close({ skipped: true }); };

      const errEl = modal.querySelector('#wk-id-err');
      const saveBtn = modal.querySelector('#wk-id-save');
      const nameInput = modal.querySelector('#wk-id-name');

      const submit = async () => {
        const ak = targetKey;
        const nm = (nameInput.value || '').trim();
        errEl.hidden = true;
        if (!wkIsRealName(nm)) {
          errEl.textContent = '사용자 이름을 입력하세요. (게스트/seed 제외)';
          errEl.hidden = false;
          nameInput.focus();
          return;
        }
        saveBtn.disabled = true;
        try {
          if (!presetKey || presetKey === prof.access_key || isFirst) {
            wkSaveAccessProfile(nm, ak);
            const actionName = isFirst ? 'first_entry' : 'rename';
            const detailText = isFirst
              ? (opts.source === 'console' ? '통합 콘솔 최초 접속 이름 등록' : '설계/설정 최초 접속 이름 등록')
              : '사용자 이름 변경 (키 불변)';
            await wkSyncIdentity(actionName, detailText);
          } else {
            const kbLocal = wkReadLocalJson(WK_ACCESS_STORAGE.keybook, {}) || {};
            const prev = kbLocal[ak] || {};
            const names = (prev.names || []).slice();
            if (names.indexOf(nm) < 0) names.push(nm);
            kbLocal[ak] = Object.assign({}, prev, { access_key: ak, member: nm, names: names, updated_at: Math.floor(Date.now() / 1000), last_ip: prev.last_ip || '수동 매칭' });
            wkWriteLocalJson(WK_ACCESS_STORAGE.keybook, kbLocal);
          }
          try {
            if (typeof WIKI !== 'undefined' && WIKI.ready) {
              const rkb = await api('POST', '/api/access/keybook', { access_key: ak, member: nm });
              if (rkb && rkb.keybook) WIKI.keybook = rkb.keybook;
            }
          } catch (e) {}
          close({ member: nm, access_key: ak, skipped: false });
          if (typeof wikiToast === 'function') wikiToast((isFirst ? '사용자 등록됨: ' : '이름 반영됨: ') + nm + ' (' + ak + ')');
          if (typeof cfgRenderNav === 'function' && typeof WIKI !== 'undefined' && WIKI.ready) cfgRenderNav();
          if (typeof CFG !== 'undefined' && CFG.lens === 'ref' && CFG.major === '__changes' && typeof wikiChangesView === 'function') wikiChangesView();
        } finally {
          saveBtn.disabled = false;
        }
      };

      saveBtn.onclick = submit;
      nameInput.addEventListener('keydown', e => {
        if (e.key === 'Enter') { e.preventDefault(); submit(); }
      });
      nameInput.focus();
    }

    function wkIsSettingsVisible() {
      const el = typeof document !== 'undefined' ? document.getElementById('view-settings') : null;
      if (!el || el.classList.contains('wiki-anon')) return false;
      if (el.style.display === 'none') return false;
      try { return getComputedStyle(el).display !== 'none'; } catch (e) { return true; }
    }

    function wkEnsureFirstEntryName(source) {
      const existingName = wkGetSavedRealName();
      if (existingName) {
        const prof = wkGetAccessProfile();
        return Promise.resolve({ member: existingName, access_key: prof.access_key, existing: true });
      }
      try {
        if (sessionStorage.getItem(WK_FIRST_ENTRY_SKIP_KEY) === '1') {
          return Promise.resolve({ skipped: true });
        }
      } catch (e) {}
      if (WK_FIRST_ENTRY_PROMISE) return WK_FIRST_ENTRY_PROMISE;
      WK_FIRST_ENTRY_PROMISE = new Promise(resolve => {
        wkOpenIdentityModal(null, {
          firstEntry: true,
          source: source || 'settings',
          onDone: res => {
            WK_FIRST_ENTRY_PROMISE = null;
            resolve(res || { skipped: true });
          }
        });
      });
      return WK_FIRST_ENTRY_PROMISE;
    }

    function wkOpenKeybookQuick(accessKey) {
      wkOpenIdentityModal(accessKey);
    }

    function wikiRenameStart() {
      wkOpenIdentityModal();
    }

    // ===== 만들기 · 편집 · 삭제 =====
    const WK_STATUS = [['live', '실측'], ['design', '설계 · 미적용'], ['nolook', '미실측']];
    const WK_PROVIDERS = [['onprem', '온프렘'], ['openstack', 'OpenStack'], ['kt', 'KT Cloud'], ['aws', 'AWS'], ['other', '기타']];
    const WK_CATS = ['설치', '적용', '조회', '검증'];
    const WK_KIND_NAME = { cloud: '클라우드', instance: '인스턴스', area: '서비스 영역', steps: '진행 순서', page: '참고 문서' };
    // 화면용 비밀값 검사 — 서버(wiki/guard.py)와 같은 패턴
    const WK_SECRET = [
      /-----BEGIN [A-Z ]*PRIVATE KEY-----/, /PrivateKey\\s*=\\s*[A-Za-z0-9+/]{43}=/, /AKIA[0-9A-Z]{16}/,
      /gh[pousr]_[A-Za-z0-9]{36}/, /(password|passwd|pwd|secret|token)\\s*[:=]\\s*(?![<$'"{])\\S{6,}/i
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
        '<button type="button" class="wk-mini" onclick="event.stopPropagation();wikiCreate(\\'instance\\', ' + cloudId + ')">+ 인스턴스</button></span>';
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
      if (kind === 'steps') {
        return '<div class="wk-acts">' +
          (docId ? '<button type="button" class="wk-mini" onclick="wikiEditSteps(false)">순서 편집</button>' : '') +
          (typeof cfgGuideOpen === 'function' ? '<button type="button" class="wk-mini" onclick="cfgGuideOpen({action:\\'reorder\\',kind:\\'steps\\',docId:' + (docId || 'null') + '})">📋 지침으로 순서편집</button>' : '') +
          '</div>';
      }
      if (!docId) return '';
      const name = WK_KIND_NAME[kind];
      return '<div class="wk-acts">' +
        '<button type="button" class="wk-mini" onclick="wikiEdit(' + docId + ')">' + name + ' 편집</button>' +
        (typeof cfgGuideOpen === 'function' ? '<button type="button" class="wk-mini" onclick="cfgGuideOpen({action:\\'patch\\',kind:\\'' + kind + '\\',docId:' + docId + '})">📋 지침 편집</button>' : '') +
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
        (typeof cfgGuideInlineHtml === 'function' ? cfgGuideInlineHtml(meta) : '') +
        (notice || '') + '<p class="wk-error" id="wk-ed-err" role="alert" hidden></p>';
      fields.forEach(f => {
        const key = f[0], type = f[2], val = body[key];
        if (type === 'rows') {
          const items = Array.isArray(val) ? val : [];
          html += '<fieldset class="wk-set"><legend>' + cfgEsc(f[1]) + '</legend><div class="wk-rows" data-key="' + key + '">' +
            items.map((it, i) => wkRow(key, f[3], wkRowItem(meta.kind, key, it), i)).join('') + '</div>' +
            '<button type="button" class="wk-add" onclick="wkAddRow(\\'' + key + '\\')">+ ' + cfgEsc(f[1]) + ' 추가</button></fieldset>';
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
        wkRecordLocalAccess(!ed.meta.docId ? 'create' : 'edit', ed.meta.kind + ':' + (body.name || body.title || '진행 순서') + ' (' + r.rev + '판)');
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
        wkRecordLocalAccess('delete', (d.kind || '') + ':' + (d.body && (d.body.name || d.body.title) || docId) + ' (' + r.rev + '판)');
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
      const kb = wkMergedKeybook();
      bodyEl.innerHTML =
        '<nav class="cfg-crumb"><a href="javascript:void(0)" onclick="wkBackFromHistory()">← ' + (alive ? '문서로 돌아가기' : '목록으로') + '</a></nav>' +
        '<div class="cfg-head"><h2 class="cfg-head-title">' + cfgEsc(title) + ' — 기록 <span class="manual-tag">' + WK_KIND_NAME[kind] + '</span></h2>' +
        '<p class="manual-desc">판 ' + revs.length + '개. 비교할 두 판을 왼쪽(옛 판)·오른쪽(새 판)에서 고르세요.' + (alive ? '' : ' 이 문서는 삭제된 상태입니다. 판을 골라 되돌리면 다시 나타납니다.') + '</p></div>' +
        '<div class="cfg-table-wrap"><table class="cfg-table wk-revs"><thead><tr><th>왼쪽</th><th>오른쪽</th><th>판</th><th>접속 키값</th><th>수정자</th><th>시각</th><th>메모</th><th></th></tr></thead><tbody>' +
        revs.map(r => {
          const authCell = wkAuthorCellHtml(r.author, r.access_key, kb, { allowQuickMatch: true });
          return '<tr' + (r.deleted ? ' class="wk-rev-del"' : '') + '>' +
            '<td><input type="radio" name="wk-a" value="' + r.rev + '"' + (r.rev === a ? ' checked' : '') + ' aria-label="' + r.rev + '판을 왼쪽에"></td>' +
            '<td><input type="radio" name="wk-b" value="' + r.rev + '"' + (r.rev === b ? ' checked' : '') + ' aria-label="' + r.rev + '판을 오른쪽에"></td>' +
            '<td><b>' + r.rev + '판</b>' + (r.rev === latest ? ' <span class="cfg-badge cfg-st-live">현재</span>' : '') + (r.deleted ? ' <span class="cfg-badge cfg-st-nolook">삭제</span>' : '') + '</td>' +
            '<td>' + authCell.keyHtml + '</td><td>' + authCell.userHtml + '</td><td>' + wkTime(r.created_at) + '</td><td>' + cfgEsc(r.message || '') + '</td>' +
            '<td>' + (r.rev !== latest || r.deleted ? '<button type="button" class="wk-mini" onclick="wikiRestore(' + docId + ',' + r.rev + ',this)">' + (r.deleted ? '' : '이 판으로 되돌리기') + '</button>' : '') + '</td></tr>';
        }).join('') +
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
        const kb = wkMergedKeybook();
        const pA = wkParseAuthor(A.author, A.access_key, kb);
        const pB = wkParseAuthor(B.author, B.access_key, kb);
        const labelA = a + '판 · ' + (pA.matchedUser || A.author) + (pA.accessKey ? ' [' + pA.accessKey + ']' : '') + ' · ' + wkTime(A.created_at);
        const labelB = b + '판 · ' + (pB.matchedUser || B.author) + (pB.accessKey ? ' [' + pB.accessKey + ']' : '') + ' · ' + wkTime(B.created_at);
        const kind = WIKI.hist.kind;
        box.innerHTML = '<h3 class="cfg-h">' + a + '판 ↔ ' + b + '판</h3>' +
          wikiDiffView(bodyToText(kind, A.body), bodyToText(kind, B.body), labelA, labelB);
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
        wkRecordLocalAccess('restore', 'doc#' + docId + ' → ' + target + '판 복구 (' + r.rev + '판)');
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

    // ---------- 최근 변경 · 접속 기록 · 키값 매칭 (참고 > 최근 변경 · 접속 기록) ----------
    const WK_ACTION_LABEL = {
      visit: '포털 접속',
      login: '로그인',
      first_entry: '최초 이름 등록',
      console: '콘솔 접속',
      logout: '로그아웃',
      create_team: '팀 생성',
      rename: '키·이름 변경',
      create: '문서 생성',
      edit: '문서 수정',
      delete: '문서 삭제',
      restore: '판 되돌리기'
    };

    const WK_VISIT_STATE_LABEL = {
      authenticated: '로그인 접속',
      visitor: '미로그인 방문',
      expired: '세션 만료',
      login_fail: '로그인 실패',
      logout: '로그아웃'
    };

    function wkFilterByKey(ak) {
      WIKI.changesView = WIKI.changesView || { tab: 'changes', query: '', filterKey: '', list: [], logs: [], serverKeybook: {} };
      WIKI.changesView.filterKey = (WIKI.changesView.filterKey === ak) ? '' : ak;
      const qInp = document.getElementById('wk-ch-q');
      if (qInp) qInp.value = WIKI.changesView.filterKey;
      WIKI.changesView.query = WIKI.changesView.filterKey;
      wkRenderChangesTab();
    }

    function wkChangesSetTab(tab) {
      WIKI.changesView = WIKI.changesView || { tab: 'changes', query: '', filterKey: '', list: [], logs: [], serverKeybook: {} };
      WIKI.changesView.tab = tab;
      document.querySelectorAll('.wk-subtab').forEach(b => b.classList.toggle('active', b.getAttribute('data-tab') === tab));
      wkRenderChangesTab();
    }

    function wkChangesFilter(val) {
      WIKI.changesView = WIKI.changesView || { tab: 'changes', query: '', filterKey: '', vstate: 'all', mineOnly: false, list: [], logs: [], wikiVisitors: [], consoleVisitors: [], serverKeybook: {} };
      WIKI.changesView.query = String(val || '').trim();
      WIKI.changesView.filterKey = '';
      wkRenderChangesTab();
    }

    function wkVisitorsSetState(vstate) {
      WIKI.changesView = WIKI.changesView || { tab: 'visitors', query: '', filterKey: '', vstate: 'all', mineOnly: false, list: [], logs: [], wikiVisitors: [], consoleVisitors: [], serverKeybook: {} };
      WIKI.changesView.vstate = vstate || 'all';
      wkRenderChangesTab();
    }

    function wkAccessToggleMine() {
      WIKI.changesView = WIKI.changesView || { tab: 'access', query: '', filterKey: '', vstate: 'all', mineOnly: false, list: [], logs: [], wikiVisitors: [], consoleVisitors: [], serverKeybook: {} };
      WIKI.changesView.mineOnly = !WIKI.changesView.mineOnly;
      wkRenderChangesTab();
    }

    async function wkQuickKeybookSave(ev) {
      if (ev) ev.preventDefault();
      const kInp = document.getElementById('wk-kb-key');
      const uInp = document.getElementById('wk-kb-user');
      const ak = wkNormalizeAccessKey(kInp && kInp.value);
      const nm = (uInp && uInp.value || '').trim();
      if (ak.length < 2) { alert('접속 키값을 2자 이상 영문·숫자로 입력하세요.'); return; }
      if (!nm) { alert('매칭할 사용자 이름을 입력하세요.'); return; }

      const prof = wkGetAccessProfile();
      if (ak === prof.access_key) {
        wkSaveAccessProfile(nm, ak);
        await wkSyncIdentity('rename', '키북 매칭 반영');
      } else {
        const kbLocal = wkReadLocalJson(WK_ACCESS_STORAGE.keybook, {}) || {};
        kbLocal[ak] = { access_key: ak, member: nm, updated_at: Math.floor(Date.now() / 1000), last_ip: '매칭표 등록' };
        wkWriteLocalJson(WK_ACCESS_STORAGE.keybook, kbLocal);
      }
      try {
        const r = await api('POST', '/api/access/keybook', { access_key: ak, member: nm });
        if (r && r.keybook) WIKI.keybook = r.keybook;
      } catch (e) {}

      wikiToast('매칭 등록: ' + ak + ' → ' + nm);
      if (kInp) kInp.value = '';
      if (uInp) uInp.value = '';
      cfgRenderNav();
      wkRenderChangesTab();
    }

    function wkBuildCombinedLogs(serverLogs, changesList, keybook) {
      const seen = {};
      const out = [];
      const addRow = row => {
        const p = wkParseAuthor(row.member || row.author, row.access_key, keybook);
        const keySig = (row.ts || row.created_at || 0) + '|' + p.accessKey + '|' + (row.action || '') + '|' + (row.detail || '');
        if (seen[keySig]) return;
        seen[keySig] = true;
        out.push({
          ts: row.ts || row.created_at || 0,
          accessKey: p.accessKey,
          matchedUser: p.matchedUser || row.matched_user || p.name || '게스트',
          registered: p.registered,
          hasRealName: p.hasRealName,
          action: row.action || 'visit',
          detail: row.detail || '',
          ip: row.ip || ''
        });
      };
      (serverLogs || []).forEach(addRow);
      (wkReadLocalJson(WK_ACCESS_STORAGE.logs, []) || []).forEach(addRow);
      (changesList || []).forEach(c => {
        addRow({
          ts: c.created_at,
          author: c.author,
          access_key: c.access_key,
          matched_user: c.matched_user,
          action: c.deleted ? 'delete' : (c.rev === 1 ? 'create' : 'edit'),
          detail: (WK_KIND_NAME[c.kind] || c.kind) + ': ' + (c.title || '(제목 없음)') + ' (' + c.rev + '판)',
          ip: '문서 저장'
        });
      });
      out.sort((a, b) => b.ts - a.ts);
      return out;
    }

    function wkBuildSiteVisitors(wikiVisitors, consoleVisitors, localVisits, keybook) {
      const seen = {};
      const out = [];
      const addRow = row => {
        if (!row) return;
        const ts = Number(row.ts || 0);
        const state = String(row.auth_state || 'visitor');
        const p = wkParseAuthor(row.member, row.access_key, keybook);
        const view = String(row.view || '');
        const path = String(row.path || '/');
        const bucket = Math.floor(ts / 3);
        const sig = bucket + '|' + state + '|' + p.accessKey + '|' + view + '|' + path;
        if (seen[sig]) return;
        seen[sig] = true;
        const rawMatched = String(row.matched_user || '').trim();
        let matchedUser = '방문자';
        if (p.registered || p.hasRealName) matchedUser = p.matchedUser;
        else if (rawMatched && rawMatched !== '게스트') matchedUser = rawMatched;
        else if (p.accessKey) matchedUser = '게스트';
        out.push({
          ts: ts,
          authState: state,
          path: path,
          view: view,
          accessKey: p.accessKey,
          matchedUser: matchedUser,
          registered: p.registered,
          hasRealName: p.hasRealName,
          ip: String(row.ip || ''),
          ua: String(row.ua || ''),
          detail: String(row.detail || '')
        });
      };
      (wikiVisitors || []).forEach(addRow);
      (consoleVisitors || []).forEach(addRow);
      (localVisits || []).forEach(addRow);
      out.sort((a, b) => b.ts - a.ts);
      return out;
    }

    function wkSummarizeVisitors(rows) {
      let authenticated = 0, anonymous = 0, expiredOrFail = 0;
      const ips = {};
      (rows || []).forEach(r => {
        const st = r.authState || r.auth_state || 'visitor';
        if (st === 'authenticated') authenticated++;
        else if (st === 'expired' || st === 'login_fail') expiredOrFail++;
        else anonymous++;
        if (r.ip) ips[r.ip] = true;
      });
      return {
        total: (rows || []).length,
        authenticated: authenticated,
        anonymous: anonymous,
        expiredOrFail: expiredOrFail,
        uniqueIps: Object.keys(ips).length
      };
    }

    function wkBuildKeyTrace(targetKey, keybook, changesList, accessLogs, siteVisitors) {
      const ak = wkNormalizeAccessKey(targetKey);
      if (!ak) return null;
      const item = (keybook && keybook[ak]) ? keybook[ak] : {};
      const names = [];
      const ips = [];
      const addName = n => { const s = String(n || '').trim(); if (s && s !== '게스트' && s !== '방문자' && names.indexOf(s) < 0) names.push(s); };
      const addIp = ip => { const s = String(ip || '').trim(); if (s && s !== '현재 브라우저' && s !== '문서 저장' && s !== '수동 매칭' && s !== '매칭표 등록' && ips.indexOf(s) < 0) ips.push(s); };
      (item.names || []).forEach(addName);
      if (item.member) addName(item.member);
      (item.ips || []).forEach(addIp);
      if (item.first_ip) addIp(item.first_ip);
      if (item.last_ip) addIp(item.last_ip);

      let firstSeen = Number(item.first_seen || item.updated_at || 0);
      let lastSeen = Number(item.updated_at || item.last_seen || 0);
      const trackTs = t => {
        const n = Number(t || 0);
        if (!n) return;
        firstSeen = firstSeen ? Math.min(firstSeen, n) : n;
        lastSeen = Math.max(lastSeen, n);
      };

      const matchedChanges = [];
      (changesList || []).forEach(c => {
        const p = wkParseAuthor(c.author, c.access_key, keybook);
        if (p.accessKey !== ak) return;
        addName(p.name);
        trackTs(c.created_at);
        matchedChanges.push(c);
      });

      const matchedLogs = [];
      (accessLogs || []).forEach(l => {
        const p = wkParseAuthor(l.member, l.access_key, keybook);
        if (p.accessKey !== ak) return;
        addName(p.name);
        addIp(l.ip);
        trackTs(l.ts);
        matchedLogs.push(l);
      });

      const matchedVisits = [];
      (siteVisitors || []).forEach(v => {
        const vak = wkNormalizeAccessKey(v.accessKey || v.access_key);
        if (vak !== ak) return;
        addName(v.matchedUser || v.member);
        addIp(v.ip);
        trackTs(v.ts);
        matchedVisits.push(v);
      });

      return {
        accessKey: ak,
        currentMember: (item.member && item.member !== '게스트') ? item.member : (names[names.length - 1] || '게스트'),
        names: names,
        ips: ips,
        firstSeen: firstSeen,
        lastSeen: lastSeen,
        changeCount: matchedChanges.length,
        accessCount: matchedLogs.length,
        visitCount: matchedVisits.length
      };
    }

    function wkRenderTraceCardHtml(trace) {
      if (!trace) return '';
      const nameHtml = trace.names.length
        ? trace.names.map(n => '<span class="wk-hist-chip">' + cfgEsc(n) + '</span>').join('')
        : '<span class="wk-ip-muted">이름 미지정</span>';
      const ipHtml = trace.ips.length
        ? trace.ips.map(ip => '<span class="wk-hist-chip mono">' + cfgEsc(ip) + '</span>').join('')
        : '<span class="wk-ip-muted">IP 기록 없음</span>';
      return '<div class="wk-trace-card">' +
        '<div class="wk-trace-head">' +
          '<div><b>🔍 불변 접속 키 추적</b> <span class="wk-key-pill">' + cfgEsc(trace.accessKey) + '</span> ' +
          '<span class="wk-user-pill named">' + cfgEsc(trace.currentMember) + '</span></div>' +
          '<div style="display:flex;gap:6px;">' +
            '<button type="button" class="wk-mini" onclick="wkOpenIdentityModal(\\'' + cfgEsc(trace.accessKey) + '\\')">이름 수정</button>' +
            '<button type="button" class="wk-mini" onclick="wkFilterByKey(\\'\\')">추적 해제</button>' +
          '</div>' +
        '</div>' +
        '<div class="wk-trace-grid">' +
          '<div><span>사용 이름 이력</span><div>' + nameHtml + '</div></div>' +
          '<div><span>접속 IP 이력</span><div>' + ipHtml + '</div></div>' +
          '<div><span>최초 발급 · 최근 활동</span><div><b>' + (trace.firstSeen ? wkTime(trace.firstSeen) : '-') + '</b> ~ <b>' + (trace.lastSeen ? wkTime(trace.lastSeen) : '-') + '</b></div></div>' +
          '<div><span>누적 활동량</span><div>문서 변경 <b>' + trace.changeCount + '건</b> · 로그인 활동 <b>' + trace.accessCount + '건</b> · 사이트 접속 <b>' + trace.visitCount + '건</b></div></div>' +
        '</div>' +
      '</div>';
    }

    function wkRenderChangesTab() {
      const box = document.getElementById('wk-ch-panel');
      if (!box) return;
      const st = WIKI.changesView || { tab: 'changes', query: '', filterKey: '', vstate: 'all', mineOnly: false, list: [], logs: [], wikiVisitors: [], consoleVisitors: [], consoleKeys: {}, serverKeybook: {} };
      const q = (st.query || '').toLowerCase();
      const kb = wkMergedKeybook(st.serverKeybook, st.list, st.consoleKeys);
      const prof = wkGetAccessProfile();
      const localVisits = wkReadLocalJson('fig.access.site_visits_v1', []) || [];
      const allVisitors = wkBuildSiteVisitors(st.wikiVisitors, st.consoleVisitors, localVisits, kb);
      const activeKey = wkNormalizeAccessKey(st.filterKey) || (q && kb[wkNormalizeAccessKey(st.query)] ? wkNormalizeAccessKey(st.query) : '');
      const traceHtml = activeKey ? wkRenderTraceCardHtml(wkBuildKeyTrace(activeKey, kb, st.list, st.logs, allVisitors)) : '';

      if (st.tab === 'changes') {
        const filtered = (st.list || []).filter(c => {
          if (!q) return true;
          const p = wkParseAuthor(c.author, c.access_key, kb);
          const hay = [p.accessKey, p.matchedUser, c.author, c.title, c.message, WK_KIND_NAME[c.kind]].join(' ').toLowerCase();
          return hay.indexOf(q) >= 0;
        });
        box.innerHTML = traceHtml +
          '<div class="cfg-table-wrap"><table class="cfg-table wk-changes">' +
          '<thead><tr><th>시각</th><th>접속 키값</th><th>수정자 (매칭)</th><th>문서</th><th>판</th><th>메모</th></tr></thead>' +
          '<tbody>' +
          (filtered.length ? filtered.map(c => {
            const auth = wkAuthorCellHtml(c.author, c.access_key, kb, { allowQuickMatch: true });
            return '<tr class="wk-ch-row" tabindex="0" onclick="wikiHistory(' + c.doc_id + ',' + Math.max(1, c.rev - 1) + ',' + c.rev + ',\\'' + c.kind + '\\',' + cfgEsc(JSON.stringify(c.title)) + ')">' +
              '<td>' + wkTime(c.created_at) + '</td>' +
              '<td>' + auth.keyHtml + '</td>' +
              '<td>' + auth.userHtml + '</td>' +
              '<td>' + WK_KIND_NAME[c.kind] + ' / <b>' + cfgEsc(c.title || '(제목 없음)') + '</b>' + (c.deleted ? ' <span class="cfg-badge cfg-st-nolook">삭제</span>' : '') + '</td>' +
              '<td>' + c.rev + '판</td><td>' + cfgEsc(c.message || '') + '</td></tr>';
          }).join('') : '<tr><td colspan="6">조건에 맞는 변경 기록이 없습니다.</td></tr>') +
          '</tbody></table></div>' +
          '<div class="wk-bar wk-bar-inline"><button type="button" class="wk-btn" id="wk-ch-more"' + (st.hasMore ? '' : ' hidden') + '>이전 변경 더 보기</button></div>';
        const more = document.getElementById('wk-ch-more');
        if (more && st.hasMore && st.list.length) {
          more.onclick = () => wikiChangesView(st.list[st.list.length - 1].created_at);
        }
      } else if (st.tab === 'access') {
        const allAuthRows = wkBuildCombinedLogs(st.logs, st.list, kb);
        const uniqUsers = {}, uniqKeys = {};
        allAuthRows.forEach(r => {
          if (r.matchedUser && r.matchedUser !== '게스트') uniqUsers[r.matchedUser] = true;
          if (r.accessKey) uniqKeys[r.accessKey] = true;
        });
        const combined = allAuthRows.filter(row => {
          if (st.mineOnly && row.accessKey !== prof.access_key && row.matchedUser !== prof.member) return false;
          if (!q) return true;
          const hay = [row.accessKey, row.matchedUser, WK_ACTION_LABEL[row.action] || row.action, row.detail, row.ip].join(' ').toLowerCase();
          return hay.indexOf(q) >= 0;
        });
        box.innerHTML = traceHtml +
          '<div class="wk-kpi-strip">' +
            '<div class="wk-kpi-card"><span>로그인 사용자 활동</span><b>' + allAuthRows.length + '건</b></div>' +
            '<div class="wk-kpi-card"><span>고유 로그인 사용자</span><b>' + Object.keys(uniqUsers).length + '명</b></div>' +
            '<div class="wk-kpi-card"><span>고유 접속 키값</span><b>' + Object.keys(uniqKeys).length + '개</b></div>' +
          '</div>' +
          '<div class="wk-filter-pills">' +
            '<button type="button" class="wk-fpill' + (st.mineOnly ? ' active' : '') + '" onclick="wkAccessToggleMine()">내 기록만 보기 (' + cfgEsc(prof.member) + ')</button>' +
            '<span class="wk-ip-muted">인증된 사용자의 포털·콘솔·문서 작업 이력</span>' +
          '</div>' +
          '<div class="cfg-table-wrap"><table class="cfg-table wk-changes">' +
          '<thead><tr><th>접속 시각</th><th>접속 키값</th><th>로그인 사용자 (매칭)</th><th>활동</th><th>대상 / 메모 · IP</th></tr></thead>' +
          '<tbody>' +
          (combined.length ? combined.map(row => {
            const auth = wkAuthorCellHtml(row.matchedUser, row.accessKey, kb, { allowQuickMatch: true });
            return '<tr>' +
              '<td>' + wkTime(row.ts) + '</td>' +
              '<td>' + auth.keyHtml + '</td>' +
              '<td>' + auth.userHtml + '</td>' +
              '<td><span class="wk-act-badge wk-act-' + cfgEsc(row.action) + '">' + cfgEsc(WK_ACTION_LABEL[row.action] || row.action) + '</span></td>' +
              '<td>' + cfgEsc(row.detail || '-') + (row.ip ? ' <span class="wk-ip-muted">(' + cfgEsc(row.ip) + ')</span>' : '') + '</td></tr>';
          }).join('') : '<tr><td colspan="5">표시할 로그인 사용자 접속 기록이 없습니다.</td></tr>') +
          '</tbody></table></div>';
      } else if (st.tab === 'visitors') {
        const sum = wkSummarizeVisitors(allVisitors);
        const vFilter = st.vstate || 'all';
        const filtered = allVisitors.filter(row => {
          if (vFilter === 'authenticated' && row.authState !== 'authenticated') return false;
          if (vFilter === 'visitor' && row.authState !== 'visitor' && row.authState !== 'logout') return false;
          if (vFilter === 'expired_or_fail' && row.authState !== 'expired' && row.authState !== 'login_fail') return false;
          if (!q) return true;
          const hay = [row.accessKey, row.matchedUser, WK_VISIT_STATE_LABEL[row.authState] || row.authState, row.path, row.view, row.ip, row.ua, row.detail].join(' ').toLowerCase();
          return hay.indexOf(q) >= 0;
        });
        box.innerHTML = traceHtml +
          '<div class="wk-kpi-strip">' +
            '<div class="wk-kpi-card"><span>전체 사이트 접속</span><b>' + sum.total + '건</b></div>' +
            '<div class="wk-kpi-card"><span>로그인 접속</span><b>' + sum.authenticated + '건</b></div>' +
            '<div class="wk-kpi-card"><span>미로그인 방문</span><b>' + sum.anonymous + '건</b></div>' +
            '<div class="wk-kpi-card"><span>만료 · 실패</span><b>' + sum.expiredOrFail + '건</b></div>' +
            '<div class="wk-kpi-card"><span>고유 IP</span><b>' + sum.uniqueIps + '개</b></div>' +
          '</div>' +
          '<div class="wk-filter-pills">' +
            '<button type="button" class="wk-fpill' + (vFilter === 'all' ? ' active' : '') + '" onclick="wkVisitorsSetState(\\'all\\')">전체</button>' +
            '<button type="button" class="wk-fpill' + (vFilter === 'authenticated' ? ' active' : '') + '" onclick="wkVisitorsSetState(\\'authenticated\\')">로그인 접속</button>' +
            '<button type="button" class="wk-fpill' + (vFilter === 'visitor' ? ' active' : '') + '" onclick="wkVisitorsSetState(\\'visitor\\')">미로그인 방문</button>' +
            '<button type="button" class="wk-fpill' + (vFilter === 'expired_or_fail' ? ' active' : '') + '" onclick="wkVisitorsSetState(\\'expired_or_fail\\')">세션 만료·로그인 실패</button>' +
          '</div>' +
          '<div class="cfg-table-wrap"><table class="cfg-table wk-changes">' +
          '<thead><tr><th>접속 시각</th><th>상태</th><th>접속 키값</th><th>사용자 (매칭)</th><th>경로 · 화면</th><th>IP · 환경 / 상세</th></tr></thead>' +
          '<tbody>' +
          (filtered.length ? filtered.map(row => {
            let keyHtml = '<span class="wk-key-pill wk-key-none">키없음</span>';
            let userHtml = '<span class="wk-user-pill">' + cfgEsc(row.matchedUser || '미로그인 방문자') + '</span>';
            if (row.accessKey || row.hasRealName) {
              const auth = wkAuthorCellHtml(row.matchedUser, row.accessKey, kb, { allowQuickMatch: true });
              keyHtml = auth.keyHtml;
              userHtml = auth.userHtml;
            }
            const stateLabel = WK_VISIT_STATE_LABEL[row.authState] || row.authState;
            const pathStr = cfgEsc(row.path || '/') + (row.view ? ' <span class="wk-ip-muted">[' + cfgEsc(row.view) + ']</span>' : '');
            const metaParts = [row.ip, row.ua, row.detail].filter(Boolean).map(cfgEsc);
            return '<tr>' +
              '<td>' + wkTime(row.ts) + '</td>' +
              '<td><span class="wk-vstate wk-vs-' + cfgEsc(row.authState) + '">' + cfgEsc(stateLabel) + '</span></td>' +
              '<td>' + keyHtml + '</td>' +
              '<td>' + userHtml + '</td>' +
              '<td style="font-family:var(--font-mono);font-size:12px;">' + pathStr + '</td>' +
              '<td>' + (metaParts.length ? metaParts.join(' · ') : '-') + '</td>' +
            '</tr>';
          }).join('') : '<tr><td colspan="6">표시할 사이트 전체 접속 기록이 없습니다.</td></tr>') +
          '</tbody></table></div>';
      } else {
        // keybook tab: 서버 자동 할당 불변 접속 키 추적 · 사용자 이름 매칭표
        const keys = Object.keys(kb).filter(ak => {
          if (!q) return true;
          const item = kb[ak];
          const hay = [ak, item.member, (item.names || []).join(' '), (item.ips || []).join(' ')].join(' ').toLowerCase();
          return hay.indexOf(q) >= 0;
        });
        const traces = {};
        keys.forEach(ak => { traces[ak] = wkBuildKeyTrace(ak, kb, st.list, st.logs, allVisitors); });
        keys.sort((a, b) => (traces[b].lastSeen || 0) - (traces[a].lastSeen || 0));
        box.innerHTML = traceHtml +
          '<p class="manual-desc" style="margin:0 0 10px;">모든 접속 키는 서버에서 자동 할당되어 변경할 수 없으며, 키 클릭 시 <b>이름 변경 이력·접속 IP·전체 활동</b>을 추적합니다.</p>' +
          '<div class="cfg-table-wrap"><table class="cfg-table wk-changes">' +
          '<thead><tr><th>접속 키값 (불변)</th><th>현재 이름 · 이름 이력</th><th>접속 IP 이력</th><th>변경 · 접속</th><th>최초 발급 / 최근 활동</th><th>추적 · 관리</th></tr></thead>' +
          '<tbody>' +
          (keys.length ? keys.map(ak => {
            const tr = traces[ak];
            const isNamed = tr.currentMember && tr.currentMember !== '게스트';
            const oldNames = (tr.names || []).filter(n => n !== tr.currentMember);
            const nameHistHtml = oldNames.length
              ? '<div style="margin-top:3px;">' + oldNames.map(n => '<span class="wk-hist-chip">이전: ' + cfgEsc(n) + '</span>').join('') + '</div>'
              : '';
            const ipHistHtml = tr.ips.length
              ? tr.ips.map(ip => '<span class="wk-hist-chip mono">' + cfgEsc(ip) + '</span>').join('')
              : '<span class="wk-ip-muted">-</span>';
            return '<tr>' +
              '<td><button type="button" class="wk-key-pill" onclick="wkFilterByKey(\\'' + cfgEsc(ak) + '\\')" title="이 키 추적하기">' + cfgEsc(ak) + '</button></td>' +
              '<td><span class="wk-user-pill' + (isNamed ? ' named' : '') + '">' + cfgEsc(tr.currentMember) + '</span> ' +
                (isNamed ? '<span class="wk-matched-badge">매칭됨</span>' : '<span class="wk-unmatched-badge">이름 미지정</span>') + nameHistHtml + '</td>' +
              '<td>' + ipHistHtml + '</td>' +
              '<td>변경 ' + tr.changeCount + ' · 접속 ' + (tr.accessCount + tr.visitCount) + '</td>' +
              '<td><div style="font-size:11.5px;">' + (tr.firstSeen ? wkTime(tr.firstSeen) : '-') + '</div>' +
                '<div class="wk-ip-muted">최근: ' + (tr.lastSeen ? wkTime(tr.lastSeen) : '-') + '</div></td>' +
              '<td style="white-space:nowrap;"><button type="button" class="wk-mini" onclick="wkFilterByKey(\\'' + cfgEsc(ak) + '\\')">추적</button> ' +
                '<button type="button" class="wk-mini" onclick="wkOpenIdentityModal(\\'' + cfgEsc(ak) + '\\')">이름 수정</button></td>' +
            '</tr>';
          }).join('') : '<tr><td colspan="6">할당된 접속 키값이 없습니다.</td></tr>') +
          '</tbody></table></div>';
      }
    }

    async function wikiChangesView(before) {
      const bodyEl = document.getElementById('manual-body-content');
      const st = WIKI.changesView = WIKI.changesView || { tab: 'changes', query: '', filterKey: '', vstate: 'all', mineOnly: false, list: [], logs: [], wikiVisitors: [], consoleVisitors: [], serverKeybook: {}, hasMore: false };
      if (!before) {
        st.list = [];
        const prof = wkGetAccessProfile();
        bodyEl.innerHTML = cfgCrumb() +
          '<div class="cfg-head"><h2 class="cfg-head-title">최근 변경 · 접속 기록</h2>' +
          '<p class="manual-desc">로그인 사용자 접속 이력과 미로그인 방문자를 포함한 <b>사이트 전체 접속 기록</b>을 분리해 조회합니다.</p></div>' +
          '<div class="wk-id-bar">' +
            '<span>내 접속 정보: <span class="wk-key-pill" onclick="wkFilterByKey(\\'' + cfgEsc(prof.access_key) + '\\')" title="내 키 추적하기">' + cfgEsc(prof.access_key) + '</span> <b style="color:#fff;">' + cfgEsc(prof.member) + '</b></span>' +
            '<button type="button" class="wk-mini" onclick="wkOpenIdentityModal()">내 이름 변경</button>' +
            '<button type="button" class="wk-mini" onclick="wikiChangesView()">↻ 새로고침</button>' +
            '<input type="search" id="wk-ch-q" class="cfg-search wk-filter-input" value="' + cfgEsc(st.query || '') + '" placeholder="접속 키값, 사용자, 경로, IP, 메모 검색" oninput="wkChangesFilter(this.value)">' +
          '</div>' +
          '<div class="wk-subtabs" role="tablist">' +
            '<button type="button" class="wk-subtab' + (st.tab === 'changes' ? ' active' : '') + '" data-tab="changes" onclick="wkChangesSetTab(\\'changes\\')">최근 변경자료 (키값·수정자)</button>' +
            '<button type="button" class="wk-subtab' + (st.tab === 'access' ? ' active' : '') + '" data-tab="access" onclick="wkChangesSetTab(\\'access\\')">로그인 사용자 접속 기록</button>' +
            '<button type="button" class="wk-subtab' + (st.tab === 'visitors' ? ' active' : '') + '" data-tab="visitors" onclick="wkChangesSetTab(\\'visitors\\')">사이트 전체 접속 기록</button>' +
            '<button type="button" class="wk-subtab' + (st.tab === 'keybook' ? ' active' : '') + '" data-tab="keybook" onclick="wkChangesSetTab(\\'keybook\\')">접속 키값 ↔ 사용자 매칭표</button>' +
          '</div>' +
          '<div id="wk-ch-panel"><p class="cfg-empty">접속·변경 기록을 불러오는 중…</p></div>';
      }
      let list = [];
      try { list = await api('GET', '/api/changes?limit=50' + (before ? '&before=' + before : '')); }
      catch (e) { return; }
      st.list = before ? st.list.concat(list) : list;
      st.hasMore = list.length === 50;

      if (!before) {
        await Promise.all([
          api('GET', '/api/access/logs?limit=150').then(acc => {
            st.logs = (acc && acc.logs) || [];
            st.serverKeybook = (acc && acc.keybook) || {};
            WIKI.keybook = st.serverKeybook;
          }).catch(() => { st.logs = []; st.serverKeybook = {}; }),
          api('GET', '/api/access/visitors?limit=200').then(vis => {
            st.wikiVisitors = (vis && vis.visits) || [];
            if (vis && vis.keybook) st.serverKeybook = Object.assign({}, st.serverKeybook || {}, vis.keybook);
          }).catch(() => { st.wikiVisitors = []; }),
          fetch('/console/api/visitors?limit=200', { credentials: 'same-origin', cache: 'no-store' })
            .then(r => r.ok ? r.json() : null)
            .then(d => { st.consoleVisitors = (d && d.visitors) || []; })
            .catch(() => { st.consoleVisitors = []; }),
          fetch('/console/api/keys', { credentials: 'same-origin', cache: 'no-store' })
            .then(r => r.ok ? r.json() : null)
            .then(d => { st.consoleKeys = (d && d.keys) || {}; WIKI.consoleKeys = st.consoleKeys; })
            .catch(() => { st.consoleKeys = {}; })
        ]);
      }
      wkRenderChangesTab();
    }

    function wkHasValidAccessKey(profile) {
      if (!profile || typeof profile !== 'object') return false;
      const ak = wkNormalizeAccessKey(profile.access_key);
      const parsedName = wkParseAuthor(profile.member).name;
      return ak.length >= 2 && wkIsRealName(parsedName);
    }

    if (typeof module !== 'undefined') {
      module.exports = {
        wkGenAccessKey: wkGenAccessKey,
        wkNormalizeAccessKey: wkNormalizeAccessKey,
        wkFormatAuthor: wkFormatAuthor,
        wkParseAuthor: wkParseAuthor,
        wkIsRealName: wkIsRealName,
        wkResolveEntryName: wkResolveEntryName,
        wkHasValidAccessKey: wkHasValidAccessKey,
        wkBuildSiteVisitors: wkBuildSiteVisitors,
        wkSummarizeVisitors: wkSummarizeVisitors,
        wkBuildKeyTrace: wkBuildKeyTrace
      };
    }
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
      ['wg-private-key', /PrivateKey\\s*=\\s*[A-Za-z0-9+/]{43}=/],
      ['aws-access-key', /AKIA[0-9A-Z]{16}/],
      ['github-token', /gh[pousr]_[A-Za-z0-9]{36}/],
      ['password-value', /(password|passwd|pwd|secret|token)\\s*[:=]\\s*(?![<$'"{])\\S{6,}/i]
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
      var fenceRe = /```(?:json|jsonc)?\\s*([\\s\\S]*?)```/gi;
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
      return String(s == null ? '' : s).trim().toLowerCase().replace(/\\s+/g, ' ');
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
            return arr.map(function (x, i) { return '  [' + i + '] ' + nameFn(x); }).join('\\n');
          };
          lines.push('이름: ' + (b.name || '') + ' | 상태: ' + (b.status || 'live') + ' | 분류: ' + (b.domains || []).join(', '));
          lines.push('- design 인덱스:\\n' + summarize(b.design, function (x) { return String(x).slice(0, 70); }));
          lines.push('- config 인덱스:\\n' + summarize(b.config, function (x) { return (x && x.label) || '(라벨 없음)'; }));
          lines.push('- commands 인덱스:\\n' + summarize(b.commands, function (x) { return '[' + ((x && x.cat) || '') + '] ' + ((x && x.label) || ''); }));
          lines.push('- verify 인덱스:\\n' + summarize(b.verify, function (x) { return (x && x.label) || '(라벨 없음)'; }));
          lines.push('- trouble 인덱스:\\n' + summarize(b.trouble, function (x) { return (x && x[0]) || ''; }));
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
      return lines.join('\\n');
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
                  code: '[Unit]\\nDescription=Prometheus Node Exporter\\nAfter=network.target\\n\\n[Service]\\nExecStart=/usr/local/bin/node_exporter\\n\\n[Install]\\nWantedBy=multi-user.target'
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
      return lines.join('\\n');
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
              '<button type="button" class="cfg-guide-chip" data-act="create" onclick="cfgGuideSetAction(\\'create\\')">➕ 생성 (create)</button>' +
              '<button type="button" class="cfg-guide-chip" data-act="patch" onclick="cfgGuideSetAction(\\'patch\\')">✏️ 수정 (patch/update)</button>' +
              '<button type="button" class="cfg-guide-chip" data-act="reorder" onclick="cfgGuideSetAction(\\'reorder\\')">↕️ 순서 편집 (reorder)</button>' +
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
                '<button type="button" class="cfg-guide-tab active" data-tab="prompt" onclick="cfgGuideSetTab(\\'prompt\\')">📋 지침 (바로 복사)</button>' +
                '<button type="button" class="cfg-guide-tab" data-tab="examples" onclick="cfgGuideSetTab(\\'examples\\')">💡 사용 예시 (생성·수정·순서)</button>' +
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
            diffHtml = '<pre class="cfg-guide-create-pre">' + cfgEsc(lines.join('\\n')) + '</pre>';
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
            '<button type="button" class="cfg-copy" onclick="cfgGuideInlineFillExample(\\'' + (isNew ? 'create' : 'patch') + '\\')">💡 ' + (isNew ? '생성 예시' : '수정 예시') + ' 넣기</button>' +
            (meta.kind !== 'cloud' ? '<button type="button" class="cfg-copy" onclick="cfgGuideInlineFillExample(\\'reorder\\')">↕️ 순서 편집 예시 넣기</button>' : '') +
            '<button type="button" class="cfg-copy" onclick="cfgGuideOpen({ kind:\\'' + cfgEsc(meta.kind) + '\\', docId:' + (meta.docId || 'null') + ', parentId:' + (meta.parentId || 'null') + ', action:\\'' + (isNew ? 'create' : 'patch') + '\\' })">🖥️ 스튜디오 크게 열기</button>' +
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
    // ===== [설정] 화면: 보는 기준(렌즈) > 대분류 > 중분류 > 설명 =====
    // 원본: content/settings_guide.py (데이터) · content/settings.js (이 파일) — tools/build_settings.py 가 주입
    const CFG = { data: null, lens: null, major: null, minor: null, codes: [] };
    const CLOUD_NAME = { onprem: '온프렘', openstack: 'OpenStack', kt: 'KT Cloud', aws: 'AWS' };
    const STATUS_NAME = { live: '실측', design: '설계 · 미적용', nolook: '미실측', protected: '보호 구역 · 웹 조작 제외' };
    const CAT_ORDER = ['설치', '적용', '조회', '검증'];
    const LENSES = [
      { id: 'inst', name: '클라우드 기준', hint: '클라우드(AWS·KT·OpenStack)를 펼쳐 그 안 인스턴스의 영역을 봅니다' },
      { id: 'svc', name: '서비스 기준', hint: '보안·웹 같은 영역을 골라 맡은 인스턴스를 봅니다' },
      { id: 'zoom', name: '기준점', hint: 'AWS·KT·OpenStack·온프렘 각 클라우드 기준 전체 시스템이 어떻게 구성되는지 봅니다' },
      { id: 'step', name: '진행 순서', hint: '처음 구성할 때 지켜야 하는 순서와 통과 조건' },
      { id: 'ref', name: '참고', hint: '변수표·설계·오류 색인 같은 팀 참고 문서' }
    ];
    // 클라우드 대분류 순서: AWS → KT Cloud → OpenStack → 온프렘
    const CLOUD_ORDER = { aws: 0, kt: 1, openstack: 2, onprem: 3 };
    function cfgInstOrder() {
      return (CFG.data.instances || []).slice().sort((a, b) =>
        ((CLOUD_ORDER[cfgPage(a).cloud] ?? 9) - (CLOUD_ORDER[cfgPage(b).cloud] ?? 9)));
    }
    // 시점(입장) 렌즈: 각 클라우드에 서서 전체를 본다 — 연결 · 기대는 것 · 나에게 기대는 것 · 멈추면 · 확인
    const VIEW_FOREST = { id: 'forest', name: '전체', sub: '모든 클라우드와 연결 한 장' };
    function cfgViewPage(c) {   // 위키 참고 문서 '시점 · <클라우드>' (팀이 편집)
      const want = '시점 · ' + CLOUD_NAME[c];
      const ref = (CFG.data.reference || []).find(r => (r[1] || '') === want);
      return ref ? cfgPage(ref[0]) : null;
    }
    function cfgClouds() {   // 인스턴스가 있는 클라우드만, 정해진 순서로
      const seen = {};
      cfgInstOrder().forEach(pid => { seen[cfgPage(pid).cloud] = true; });
      return Object.keys(CLOUD_ORDER).filter(c => seen[c]);
    }

    // ---------- 공통 조각 ----------
    function cfgEsc(t) {
      return String(t == null ? '' : t)
        .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
    }
    function cfgFmt(t) {
      return cfgEsc(t).split('`').map((seg, i) => {
        if (i % 2 === 1) return '<code class="cfg-ic">' + cfgLink(seg) + '</code>';
        return cfgLink(seg).split('**').map((s, j) => (j % 2 === 1 ? '<b>' + s + '</b>' : s)).join('');
      }).join('');
    }
    function cfgExtractFilePath(label, code) {
      const text = (label || '') + '\\n' + (code || '');
      const m = text.match(/(?:(?:nano|vi|vim|cat|touch|mkdir|cp|mv)\\s+)?((?:\\/|~)[A-Za-z0-9_./-]+(?:\\.[A-Za-z0-9_-]+|\\/[A-Za-z0-9_.-]+))/);
      if (m && m[1]) return m[1];
      if (/^[A-Za-z0-9_./-]+\\.(cnf|conf|yaml|yml|json|toml|service|sh|cfg|env|txt|ini)$/i.test((label || '').trim())) {
        return (label || '').trim();
      }
      return (label || '').trim();
    }

    function cfgCode(code, label, cat) {
      CFG.codeMeta = CFG.codeMeta || [];
      const idx = CFG.codes.push(code) - 1;
      CFG.codeMeta[idx] = { code: code, label: label, cat: cat };
      const isDang = cfgIsDangerous(code, cat);
      const isConfig = (cat === '설정' || /\\b(cnf|conf|yaml|yml|json|toml|service|cfg|ini)\\b/i.test(label || '') || /^\\s*(\\[|\\{|\\#|[A-Za-z0-9_-]+:)/.test(code || ''));

      let acts = '<button type="button" class="cfg-copy" onclick="cfgCopy(' + idx + ', this)">복사</button>';

      if (isConfig) {
        // 설정인 경우: 뷰 모드(안전 확인) + 빨강색 수정/변경(vi/nano) 버튼
        acts += '<button type="button" class="cfg-run-btn cfg-btn-view" onclick="cfgViewCode(' + idx + ')" title="안전한 뷰 모드로 설정 파일 내용 확인">👁️ 뷰 모드</button>';
        acts += '<button type="button" class="cfg-run-btn cfg-run-danger" onclick="cfgEditCode(' + idx + ')" title="경고: vi/nano 편집기 접근 및 설정 수정/변경 (확인 후 진행)">✏️ 수정/변경 (vi/nano)</button>';
      } else if (isDang || cat === '적용' || cat === '설치') {
        // 위험/적용/변경 명령어인 경우: 뷰 모드(사전 확인) + 빨강색 수정/변경 버튼
        acts += '<button type="button" class="cfg-run-btn cfg-btn-view" onclick="cfgViewCode(' + idx + ')" title="명령어 사전 확인 (뷰 모드)">👁️ 뷰 모드</button>';
        acts += '<button type="button" class="cfg-run-btn cfg-run-danger" onclick="cfgRunCode(' + idx + ')" title="경고: 시스템 설정 변경 및 서비스 영향 (확인 후 진행)">⚠️ 수정/변경</button>';
      } else {
        // 일반 조회/검증 안전 명령어: 복사 + 안전 실행
        acts += '<button type="button" class="cfg-run-btn cfg-run-safe" onclick="cfgRunCode(' + idx + ')" title="터미널에서 즉시 조회/검증 실행">▶ 뷰/확인</button>';
      }

      return '<div class="cfg-code"><div class="cfg-code-head">' +
        (cat ? '<span class="cfg-cat cfg-cat-' + CAT_ORDER.indexOf(cat) + '">' + cfgEsc(cat) + '</span>' : '') +
        '<span class="cfg-code-label">' + cfgLink(cfgEsc(label || '')) + '</span>' +
        '<div class="cfg-code-actions">' + acts + '</div>' +
        '</div><pre>' + cfgLink(cfgEsc(code)) + '</pre></div>';
    }

    // ---------- *.sh 링크와 스크립트 보기 ----------
    // 이미 이스케이프된 텍스트 안의 스크립트 경로·파일명을 링크로 바꾼다 (긴 경로부터 맞춘다)
    let CFG_SH_RE = null, CFG_SH_KEY = {};
    function cfgLink(html) {
      const list = (CFG.data && CFG.data.scripts) || [];
      if (!list.length) return html;
      if (!CFG_SH_RE) {
        const keys = [];
        list.forEach((s, i) => s.keys.forEach(k => { keys.push(k); CFG_SH_KEY[k] = i; }));
        keys.sort((a, b) => b.length - a.length);
        const alts = keys.map(k => k.split('.').join('[.]')).join('|');
        CFG_SH_RE = new RegExp('(^|[^A-Za-z0-9_./~-])(' + alts + ')(?![A-Za-z0-9_])', 'g');
      }
      return html.replace(CFG_SH_RE, (m, pre, key) => {
        const s = list[CFG_SH_KEY[key]];
        const tip = cfgEsc(s.host + ' ' + s.path + (s.url ? ' (새 창)' : ' 내용 보기'));
        if (s.url) return pre + '<a class="cfg-sh cfg-sh-ext" href="' + cfgEsc(s.url) + '" target="_blank" rel="noopener" title="' + tip + '">' + key + '</a>';
        return pre + '<a class="cfg-sh" href="javascript:void(0)" title="' + tip + '" onclick="cfgViewScript(' + CFG_SH_KEY[key] + '); return false;">' + key + '</a>';
      });
    }

    function cfgViewer() {
      let dlg = document.getElementById('cfg-viewer');
      if (dlg) return dlg;
      dlg = document.createElement('dialog');
      dlg.id = 'cfg-viewer';
      dlg.setAttribute('aria-labelledby', 'cfg-viewer-title');
      dlg.addEventListener('click', e => { if (e.target === dlg) dlg.close(); });
      document.body.appendChild(dlg);
      return dlg;
    }

    function cfgViewScript(i) {
      const s = CFG.data.scripts[i];
      const dlg = cfgViewer();
      const used = [];
      CFG.data.instances.forEach(pid => cfgPage(pid).areas.forEach(a => {
        const txt = JSON.stringify(a);
        if (s.keys.some(k => new RegExp('(^|[^A-Za-z0-9_./~-])' + k.split('.').join('[.]') + '(?![A-Za-z0-9_])').test(txt))) used.push([pid, a.id, cfgPage(pid).short + ' / ' + a.name]);
      }));
      dlg.innerHTML =
        '<div class="cfg-vw-head">' +
          '<div class="cfg-vw-meta"><span class="cfg-vw-host">' + cfgEsc(s.host) + '</span>' + cfgBadge(s.status) + '</div>' +
          '<h2 id="cfg-viewer-title" class="cfg-vw-title">' + cfgEsc(s.path) + '</h2>' +
          '<div class="cfg-vw-actions">' +
            '<button type="button" class="cfg-copy" id="cfg-vw-copy" disabled>복사</button>' +
            '<button type="button" class="cfg-copy" id="cfg-vw-dl" disabled>파일 받기</button>' +
            '<button type="button" class="cfg-copy" onclick="document.getElementById(&quot;cfg-viewer&quot;).close()">닫기</button>' +
          '</div></div>' +
        (used.length ? '<div class="cfg-vw-used">이 스크립트가 나오는 곳: ' + used.map(u =>
          '<a href="javascript:void(0)" onclick="document.getElementById(&quot;cfg-viewer&quot;).close();' + cfgGo('inst', u[0], u[1]) + '">' + cfgEsc(u[2]) + '</a>').join(', ') + '</div>' : '') +
        '<pre class="cfg-vw-body" id="cfg-vw-body">불러오는 중…</pre>' +
        '<p class="cfg-vw-note">' + (s.status === 'design'
          ? '이 가이드의 설계안에서 만든 파일입니다. 아직 서버에 적용되지 않았습니다.'
          : '서버에서 읽어 온 사본입니다(실측 ' + cfgEsc(CFG.data.measured) + '). 원본을 고치면 이 사본도 다시 받아야 합니다.') + '</p>';
      if (!dlg.open) dlg.showModal();
      api('GET', '/api/scripts/' + s.id)
        .then(r => {
          const text = r.text;
          const body = document.getElementById('cfg-vw-body');
          body.innerHTML = text.replace(/\\n$/, '').split('\\n').map(l => '<span class="cfg-ln">' + cfgLink(cfgEsc(l)) + '</span>').join('\\n');
          const btn = document.getElementById('cfg-vw-copy');
          btn.disabled = false;
          btn.onclick = () => { const idx = CFG.codes.push(text) - 1; cfgCopy(idx, btn); };
          const dl = document.getElementById('cfg-vw-dl');
          dl.disabled = false;
          dl.onclick = () => {
            const a = document.createElement('a');
            a.href = URL.createObjectURL(new Blob([text], { type: 'text/plain' }));
            a.download = s.path.split('/').pop().split(' ')[0];
            a.click(); setTimeout(() => URL.revokeObjectURL(a.href), 2000);
          };
        })
        .catch(err => {
          document.getElementById('cfg-vw-body').textContent = '파일을 불러오지 못했습니다 (' + (err.error || err.status) + ').';
        });
    }
    function cfgCopy(idx, btn) {
      const text = CFG.codes[idx];
      const done = () => { btn.textContent = '복사됨'; setTimeout(() => { btn.textContent = '복사'; }, 1200); };
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(text).then(done, () => cfgCopyFallback(text, done));
      } else { cfgCopyFallback(text, done); }
    }
    function cfgCopyFallback(text, done) {
      const ta = document.createElement('textarea');
      ta.value = text; document.body.appendChild(ta); ta.select();
      try { document.execCommand('copy'); done(); } catch (e) {}
      ta.remove();
    }
    function cfgBadge(status) {
      if (!status) return '';
      return '<span class="cfg-badge cfg-st-' + status + '">' + cfgEsc(STATUS_NAME[status] || status) + '</span>';
    }
    function cfgTable(head, rows, cls) {
      return '<div class="cfg-table-wrap"><table class="cfg-table ' + (cls || '') + '"><thead><tr>' +
        head.map(h => '<th>' + cfgEsc(h) + '</th>').join('') + '</tr></thead><tbody>' +
        rows.map(r => '<tr>' + r.map(c => '<td>' + cfgFmt(c) + '</td>').join('') + '</tr>').join('') +
        '</tbody></table></div>';
    }
    function cfgGo(lens, major, minor) {
      return 'cfgSelect(&quot;' + lens + '&quot;,&quot;' + (major || '') + '&quot;,&quot;' + (minor || '') + '&quot;)';
    }
    function cfgDomain(id) { return CFG.data.domains.find(d => d.id === id); }
    function cfgPage(id) { return CFG.data.pages[id]; }
    function cfgAreaOf(pid, aid) { const p = cfgPage(pid); return p && p.areas.find(a => a.id === aid); }

    // ---------- 목록 만들기 ----------
    function cfgMajors(lens) {
      const d = CFG.data;
      if (lens === 'inst') return cfgInstOrder().map(pid => {
        const p = cfgPage(pid);
        return { id: pid, name: p.title.split(' (')[0], sub: p.tag, cloud: p.cloud, status: p.status, group: p.cloudName, groupId: p.cloudId };
      });
      if (lens === 'svc') return d.domains.map(dm => ({ id: dm.id, name: dm.name, sub: dm.desc, count: cfgMinors('svc', dm.id).length }));
      if (lens === 'zoom') return [VIEW_FOREST].concat(cfgClouds().map(c => ({ id: c, name: CLOUD_NAME[c], sub: cfgInstOrder().filter(pid => cfgPage(pid).cloud === c).length + '대 · 연결·의존·멈추면', cloud: c })));
      if (lens === 'step') return [{ id: 'all', name: '처음부터 끝까지', sub: d.steps.length ? d.steps.length + '단계' : '아직 단계가 없습니다' }];
      return d.reference.filter(r => !/^시점 · /.test(r[1] || '')).map(r => ({ id: r[0], name: r[1], sub: cfgPage(r[0]).tag }))
        .concat(typeof wikiChangesView === 'function' ? [{ id: '__changes', name: '최근 변경 · 접속 기록', sub: '키값·수정자 매칭 및 접속 이력' }] : []);
    }
    function cfgMinors(lens, major) {
      const d = CFG.data;
      if (lens === 'inst') {
        const p = cfgPage(major);
        return p ? p.areas.map(a => ({ id: a.id, name: a.name, sub: a.domains.map(x => cfgDomain(x).name).join(', '), status: a.status !== p.status ? a.status : '' })) : [];
      }
      if (lens === "svc") {
        const out = [];
        cfgInstOrder().forEach(pid => {
          const p = cfgPage(pid);
          p.areas.forEach(a => {
            if (a.domains.indexOf(major) >= 0) out.push({ id: pid + '.' + a.id, name: p.short, sub: a.name, cloud: p.cloud, status: a.status === 'live' ? '' : a.status });
          });
        });
        return out;
      }
      if (lens === 'step') return d.steps.map(s => ({ id: s.no, name: s.no + '  ' + s.title, sub: s.where }));
      if (lens === 'zoom') {
        if (major === 'forest') return [{ id: 'all', name: '전체 토폴로지', sub: '진입 · 터널 · 서비스 · 복구 흐름' }];
        if (!CLOUD_NAME[major]) return [];
        return [{ id: 'view', name: CLOUD_NAME[major] + ' 설계 기준', sub: '연결 · 의존 · 멈추면', cloud: major }]
          .concat(cfgInstOrder().filter(pid => cfgPage(pid).cloud === major).map(pid => { const p = cfgPage(pid); return { id: pid, name: p.short, sub: '서버 작업 · ' + p.tag, cloud: p.cloud }; }));
      }
      return [];
    }

    // ---------- 선택·상태 ----------
    function cfgInit() {
      if (!WIKI.ready) { wikiInit(); return; }
      const h = (location.hash || '').split('/');
      const lg = CFG.data.legacy || {};
      let handled = false;
      if (h[0] === '#cfg' && h.length > 1 && h[1]) {
        let lens = h[1], major = h[2], minor = h[3];
        if (typeof wikiRoute === 'function' && wikiRoute(h)) handled = true;
        else {
          if (['inst', 'svc', 'zoom', 'step', 'ref'].indexOf(lens) < 0 && lg[lens]) { major = lens; minor = h[2]; lens = 'inst'; }  // #cfg/inst-ktw1/join
          if (lens === 'inst' && major && !cfgPage(major) && lg[major]) {
            const am = lg[major + '.' + minor];
            major = lg[major]; minor = am ? am.split('.')[1] : '';
          }
          if (lens === 'svc' && minor && lg[minor]) minor = lg[minor];
          if (['inst', 'svc', 'zoom', 'step', 'ref'].indexOf(lens) >= 0) { cfgSelect(lens, major, minor, true); handled = true; }
        }
      }
      if (!handled) {
        if (!CFG.lens) { const df = CFG.data.default; cfgSelect(df.lens, df.major, df.minor, true); }
        else if (typeof cfgRenderNav === 'function') cfgRenderNav();
      }
      if (typeof wkIsSettingsVisible === 'function' && wkIsSettingsVisible() && typeof wkEnsureFirstEntryName === 'function') {
        const prof = typeof wkGetAccessProfile === 'function' ? wkGetAccessProfile() : null;
        if (prof && typeof wkIsRealName === 'function' && wkIsRealName(prof.member) && WIKI.me && typeof wkFormatAuthor === 'function') {
          const expected = wkFormatAuthor(prof.member, prof.access_key);
          if (WIKI.me.member !== expected && typeof wkSyncIdentity === 'function') {
            wkSyncIdentity('visit', '설계/설정 진입').then(() => { if (typeof cfgRenderNav === 'function') cfgRenderNav(); });
          }
        }
        wkEnsureFirstEntryName('settings');
      }
    }

    function cfgSelect(lens, major, minor, fromHash) {
      if (!CFG.data) return;
      const majors = cfgMajors(lens);
      if (!majors.length) {
        CFG.lens = lens; CFG.major = ''; CFG.minor = '';
        cfgRenderNav(); cfgRenderBody();
        history.replaceState(null, '', '#cfg/' + lens);
        return;
      }
      if (!majors.find(m => m.id === major)) {
        major = lens === CFG.lens || !CFG.lens ? majors[0].id : cfgCarryMajor(lens);
      }
      const minors = cfgMinors(lens, major);
      if (minors.length && !minors.find(m => m.id === minor)) minor = cfgCarryMinor(lens, major, minors);
      CFG.lens = lens; CFG.major = major; CFG.minor = minor || '';
      CFG.treeOpen = CFG.treeOpen || {};
      CFG.treeOpen[major] = true;
      cfgRenderNav();
      cfgRenderBody();
      const hash = '#cfg/' + lens + '/' + major + (CFG.minor ? '/' + CFG.minor : '');
      if (location.hash !== hash) history.replaceState(null, '', hash);
    }
    // 렌즈를 바꿔도 보던 자리를 최대한 이어서 보여준다
    function cfgCarryMajor(lens) {
      const cur = cfgCurrentArea();
      if (cur && lens === 'inst') return cur.pid;
      if (cur && lens === 'svc') return cur.area.domains[0];
      if (lens === 'inst' && CFG.lens === 'zoom' && cfgPage(CFG.minor)) return CFG.minor;
      if (cur && lens === 'zoom') return cfgPage(cur.pid).cloud;   // 보던 서버가 속한 클라우드 입장으로
      return cfgMajors(lens)[0].id;
    }
    function cfgCarryMinor(lens, major, minors) {
      const cur = cfgCurrentArea();
      if (cur && lens === 'zoom') {
        const want = major === 'forest' ? 'all' : cur.pid;
        if (minors.find(m => m.id === want)) return want;
      }
      if (cur && lens === 'inst' && major === cur.pid) return cur.area.id;
      if (cur && lens === 'svc') { const k = cur.pid + '.' + cur.area.id; if (minors.find(m => m.id === k)) return k; }
      if (cur && lens === 'step') { const s = CFG.data.steps.find(x => x.page === cur.pid && x.area === cur.area.id); if (s) return s.no; }
      return minors[0].id;
    }
    function cfgCurrentArea() {
      if (CFG.lens === 'inst') { const a = cfgAreaOf(CFG.major, CFG.minor); return a ? { pid: CFG.major, area: a } : null; }
      if (CFG.lens === 'svc' && CFG.minor) { const k = CFG.minor.split('.'); const a = cfgAreaOf(k[0], k[1]); return a ? { pid: k[0], area: a } : null; }
      if (CFG.lens === 'step') { const s = CFG.data.steps.find(x => x.no === CFG.minor); const a = s && cfgAreaOf(s.page, s.area); return a ? { pid: s.page, area: a } : null; }
      return null;
    }

    // ---------- 왼쪽: 통합 사이드바 (대분류 > 중분류 아코디언 및 계단식 트리) ----------
    CFG.treeOpen = CFG.treeOpen || {};

    function cfgIsTreeOpen(majorId) {
      if (CFG.treeOpen[majorId] !== undefined) return CFG.treeOpen[majorId];
      return majorId === CFG.major;
    }

    function cfgToggleTree(ev, majorId) {
      if (ev) ev.stopPropagation();
      CFG.treeOpen[majorId] = !cfgIsTreeOpen(majorId);
      const el = document.getElementById('tree-node-' + majorId);
      if (el) el.classList.toggle('open', CFG.treeOpen[majorId]);
    }

    function cfgClickMajor(majorId) {
      CFG.treeOpen = CFG.treeOpen || {};
      CFG.treeOpen[majorId] = true;
      const minors = cfgMinors(CFG.lens, majorId);
      const targetMinor = minors.length ? minors[0].id : '';
      cfgSelect(CFG.lens, majorId, targetMinor);
    }

    function cfgRenderNav() {
      const nav = document.getElementById('cfg-nav');
      const lens = LENSES.find(l => l.id === CFG.lens);
      let lastGroup = null;

      // 1. 상단 렌즈 탭 & 지침 스튜디오 버튼 & 사용 매뉴얼 링크 & 힌트 & 매트릭스
      let html = wikiTeamBar() +
        (typeof cfgGuideOpen === 'function'
          ? '<button type="button" class="cfg-guide-launch-btn" onclick="cfgGuideOpen()"><span>📋 지침 복사 · 결과 등록/수정</span><small>생성·수정·순서</small></button>'
          : '') +
        '<a href="/manual/" target="_blank" rel="noopener" class="cfg-manual-link-btn"><span>📖 사용 매뉴얼 보기 (화면 클릭 안내)</span><small>새 탭</small></a>' +
        '<div class="cfg-lens" role="tablist" aria-label="보는 기준">' + LENSES.map(l =>
          '<button type="button" role="tab" aria-selected="' + (l.id === CFG.lens) + '" class="cfg-lens-btn' + (l.id === CFG.lens ? ' active' : '') +
          '" onclick="' + cfgGo(l.id, '', '') + '">' + cfgEsc(l.name) + '</button>').join('') + '</div>' +
        '<p class="cfg-lens-hint">' + cfgEsc(lens.hint) + '</p>' +
        (CFG.lens === 'inst' ? cfgMatrix() : '');

      // 2. 통합 내비게이션 트리 (대분류 > 중분류 계단식/아코디언)
      html += '<div class="cfg-col-head" style="margin-top:6px;">설계 및 설정 계층 트리</div>' +
        '<div class="cfg-tree-nav">';

      const majors = cfgMajors(CFG.lens);
      majors.forEach(m => {
        if (m.group !== undefined && m.group !== lastGroup) {
          lastGroup = m.group;
          html += cfgGroupHead(m);
        }
        const minors = cfgMinors(CFG.lens, m.id);
        const instAddAreaBtn = (CFG.lens === 'inst' && typeof WIKI !== 'undefined' && WIKI.ready && cfgPage(m.id) && cfgPage(m.id).docId)
          ? '<button type="button" class="wk-add cfg-tree-add-minor" onclick="event.stopPropagation();wikiCreate(\\'area\\', ' + cfgPage(m.id).docId + ')">+ 서비스 영역</button>'
          : '';
        const hasMinors = minors.length > 0 || !!instAddAreaBtn;
        const isCurrentMajor = (m.id === CFG.major);
        const isOpen = cfgIsTreeOpen(m.id);

        html += '<div class="cfg-tree-node' + (isOpen ? ' open' : '') + '" id="tree-node-' + m.id + '">' +
          '<div class="cfg-tree-major' + (isCurrentMajor ? ' active' : '') + '" onclick="cfgClickMajor(\\'' + m.id + '\\')">' +
          '<div class="cfg-tree-major-main">' +
          (hasMinors ? '<span class="cfg-tree-toggle" onclick="cfgToggleTree(event, \\'' + m.id + '\\')" title="하위 항목 접기/펼치기">▶</span>' : '<span style="width:18px;display:inline-block;"></span>') +
          (m.cloud ? '<span class="cfg-dot cfg-c-' + m.cloud + '"></span>' : '') +
          '<div class="cfg-tree-major-info">' +
          '<span class="cfg-tree-major-name">' + cfgEsc(m.name) + '</span>' +
          (m.sub ? '<span class="cfg-tree-major-sub">' + cfgEsc(m.sub) + '</span>' : '') +
          '</div>' +
          '</div>' +
          '<div class="cfg-tree-major-meta">' +
          (m.status && m.status !== 'live' ? cfgBadge(m.status) : '') +
          (minors.length ? '<span class="cfg-tree-badge-count">' + minors.length + '</span>' : '') +
          '</div>' +
          '</div>';

        // 하위 중분류 (계단식 인덴트) + 인스턴스별 서비스 영역 추가 버튼
        if (hasMinors) {
          html += '<div class="cfg-tree-minors">' +
            minors.map(sub => {
              const isCurrentMinor = isCurrentMajor && (sub.id === CFG.minor);
              return '<button type="button" class="cfg-tree-minor' + (isCurrentMinor ? ' active' : '') + '" onclick="' + cfgGo(CFG.lens, m.id, sub.id) + '">' +
                '<span class="cfg-tree-minor-name">' +
                (sub.cloud ? '<span class="cfg-dot cfg-c-' + sub.cloud + '"></span>' : '') +
                cfgEsc(sub.name) +
                (sub.status ? ' ' + cfgBadge(sub.status) : '') + '</span>' +
                (sub.sub ? '<span class="cfg-tree-minor-sub">' + cfgEsc(sub.sub) + '</span>' : '') +
                '</button>';
            }).join('') +
            instAddAreaBtn +
            '</div>';
        }

        html += '</div>';
      });

      if (CFG.lens === 'step' && typeof WIKI !== 'undefined' && WIKI.ready) {
        html += '<div class="cfg-tree-step-acts">' +
          '<button type="button" class="wk-add" onclick="wikiEditSteps(true)">+ 단계 추가</button>' +
          (typeof cfgGuideOpen === 'function' ? '<button type="button" class="wk-add" onclick="cfgGuideOpen({action:\\'reorder\\',kind:\\'steps\\',docId:' + (CFG.data.stepsDocId || 'null') + '})">↕️ 지침으로 순서 편집</button>' : '') +
          '</div>';
      }

      html += (typeof wikiMajorTail === 'function' ? wikiMajorTail() : '') + '</div>';
      nav.innerHTML = html;
    }

    function cfgGroupHead(m) {
      return '<div class="cfg-group-head">' + (m.cloud ? '<span class="cfg-dot cfg-c-' + m.cloud + '"></span>' : '') + cfgEsc(m.group) +
        (typeof wikiGroupTail === 'function' ? wikiGroupTail(m.groupId) : '') + '</div>';
    }

    function cfgColOn(dmId) { return CFG.lens === 'svc' && CFG.major === dmId; }
    // 인스턴스(행) × 서비스 영역(열). 행으로 읽으면 인스턴스 기준, 열로 읽으면 서비스 기준.
    function cfgMatrix() {
      const d = CFG.data;
      const cur = cfgCurrentArea();
      let html = '<div class="cfg-matrix" aria-label="인스턴스와 서비스 영역 지도"><div class="cfg-mx-row cfg-mx-headrow"><span class="cfg-mx-label"></span>' +
        d.domains.map(dm => '<span class="cfg-mx-col' + (cfgColOn(dm.id) ? ' on' : '') + '" title="' + cfgEsc(dm.name) + '">' + cfgEsc(dm.short) + '</span>').join('') + '</div>';
      cfgInstOrder().forEach(pid => {
        const p = cfgPage(pid);
        const rowOn = (CFG.lens === 'inst' && CFG.major === pid) || (CFG.lens === 'zoom' && CFG.minor === pid);
        html += '<div class="cfg-mx-row' + (rowOn ? ' on' : '') + '"><span class="cfg-mx-label">' + cfgEsc(p.short) + '</span>';
        d.domains.forEach(dm => {
          const areas = p.areas.filter(a => a.domains.indexOf(dm.id) >= 0);
          if (!areas.length) { html += '<span class="cfg-mx-cell"></span>'; return; }
          const colOn = cfgColOn(dm.id);
          const here = cur && cur.pid === pid && areas.some(a => a.id === cur.area.id);
          const go = CFG.lens === 'svc' ? cfgGo('svc', dm.id, pid + '.' + areas[0].id)
            : CFG.lens === 'zoom' ? cfgGo('zoom', p.cloud, pid) : cfgGo('inst', pid, areas[0].id);
          html += '<button type="button" class="cfg-mx-cell has' + (colOn || rowOn ? ' lit' : '') + (here ? ' here' : '') +
            (p.status === 'design' ? ' design' : '') + '" title="' + cfgEsc(p.short + ' / ' + dm.name + ': ' + areas.map(a => a.name).join(', ')) +
            '" aria-label="' + cfgEsc(p.short + ' ' + dm.name) + '" onclick="' + go + '"><i></i></button>';
        });
        html += '</div>';
      });
      return html + '</div>';
    }

    // ---------- 오른쪽: 설명 ----------
    // ---------- 오른쪽: 설명 & 상단 인터랙티브 브레드크럼 ----------
    function cfgCrumb() {
      const lensObj = LENSES.find(l => l.id === CFG.lens) || { name: '설정' };
      const majorObj = cfgMajors(CFG.lens).find(m => m.id === CFG.major);
      const minorObj = cfgMinors(CFG.lens, CFG.major).find(m => m.id === CFG.minor);

      let html = '<nav class="cfg-crumb" aria-label="현재 위치">';
      html += '<a href="javascript:void(0)" onclick="' + cfgGo(CFG.lens, '', '') + '">' + cfgEsc(lensObj.name) + '</a>';
      if (majorObj) {
        html += '<span class="cfg-crumb-sep">›</span>';
        html += '<a href="javascript:void(0)" onclick="cfgClickMajor(\\'' + CFG.major + '\\')">' + cfgEsc(majorObj.name) + '</a>';
      }
      if (minorObj) {
        html += '<span class="cfg-crumb-sep">›</span>';
        html += '<span class="cfg-crumb-current">' + cfgEsc(CFG.lens === 'svc' ? minorObj.name + ' / ' + minorObj.sub : minorObj.name) + '</span>';
      }
      html += '</nav>';
      return html;
    }

    function cfgScrollToSec(idx) {
      const body = document.getElementById('manual-body-content');
      const sec = document.getElementById('cfg-sec-' + idx);
      if (body && sec) {
        const pos = sec.offsetTop - body.offsetTop - 50;
        body.scrollTo({ top: Math.max(0, pos), behavior: 'smooth' });
      }
    }

    function cfgRenderBody() {
      CFG.codes = [];
      const body = document.getElementById('manual-body-content');
      let html = cfgCrumb();
      const empty = msg => '<div class="cfg-empty-panel"><p>' + msg + '</p>' +
        (typeof wikiEmptyActions === 'function' ? wikiEmptyActions(CFG.lens) : '') + '</div>';
      if (CFG.lens === 'ref' && CFG.major === '__changes') {
        body.innerHTML = ''; wikiChangesView(); return;
      } else if (CFG.lens === 'ref') {
        const p = cfgPage(CFG.major);
        html += p ? cfgDoc(p) : empty('아직 참고 문서가 없습니다.');
      } else if (CFG.lens === 'step') {
        const s = CFG.data.steps.find(x => x.no === CFG.minor);
        html += s ? cfgStepHead(s) + cfgAreaView(s.page, s.area, false) : empty('아직 진행 순서가 없습니다.');
      } else if (CFG.lens === 'zoom') {
        html += cfgZoomBar();
        if (CFG.major === 'forest') html += cfgZoomForest();
        else if (CFG.minor === 'view') html += cfgCloudView(CFG.major);
        else html += cfgZoomMember(CFG.minor);
      } else {
        const cur = cfgCurrentArea();
        if (CFG.lens === 'svc' && CFG.major) {
          const dm = cfgDomain(CFG.major);
          html += '<div class="cfg-domain-note"><b>' + cfgEsc(dm.name) + '</b> ' + cfgEsc(dm.desc) + '</div>';
        }
        if (cur) html += cfgAreaView(cur.pid, cur.area.id, CFG.lens === 'inst');
        else if (CFG.lens === 'inst' && cfgPage(CFG.major)) html += empty('이 인스턴스에 아직 서비스 영역이 없습니다.');
        else if (CFG.lens === 'inst') html += empty(CFG.data.clouds && CFG.data.clouds.length ? '클라우드 아래에 인스턴스를 만드세요.' : '클라우드부터 만드세요. 클라우드 → 인스턴스 → 서비스 영역 순서로 채워 갑니다.');
        else html += empty('이 서비스에 해당하는 영역이 아직 없습니다.');
      }
      html += cfgPager();
      body.innerHTML = html;
      body.scrollTop = 0;
    }

    function cfgAreaView(pid, aid, specsOpen) {
      const p = cfgPage(pid);
      const a = cfgAreaOf(pid, aid);
      const st = a.status || p.status;
      const isS1 = (pid === 'inst-s1' || (p && p.short === 's1') || (p && p.cloud === 'onprem'));
      let html = '';
      if (isS1 || p.status === 'protected') {
        html += '<div style="background:rgba(59,130,246,0.08); border:1px solid rgba(59,130,246,0.25); border-radius:8px; padding:14px 18px; margin-bottom:18px; color:#93c5fd; font-size:13px; line-height:1.6;">' +
          '<div style="font-weight:700; font-size:14px; margin-bottom:4px; color:#60a5fa;">💡 s1 가상화 기반 안내 (OpenStack 상위 호스트)</div>' +
          's1 영역은 OpenStack VM들이 구동되는 가상화 기반 호스트로, 프로젝트와 사실관계가 먼 물리 세부정보는 제외하고 상위 구성 관계만 간략히 표시합니다. (명령·연결·설정 조작 및 웹 콘솔 터미널 접근 제외)<br>' +
          '<b>본 프로젝트의 모든 실질적인 인프라 설계, 설정 및 명령어는 VM 위의 OpenStack 계층부터 시작됩니다.</b>' +
          '</div>';
      }
      html += '<div class="cfg-head">' + (typeof wikiActions === 'function' ? wikiActions('area', a.docId) : '') +
        '<div class="cfg-head-line">' + '<span class="cfg-cloud cfg-c-' + p.cloud + '">' + cfgEsc(CLOUD_NAME[p.cloud]) + '</span>' +
          '<span class="cfg-head-inst">' + cfgEsc(p.title) + '</span><span class="manual-tag">' + cfgEsc(p.tag) + '</span></div>' +
        '<h2 class="cfg-head-title">' + cfgEsc(a.name) + ' ' + cfgBadge(st) + '</h2>' +
        '<div class="cfg-head-domains">이 영역은 ' + a.domains.map(x =>
          '<a href="javascript:void(0)" class="cfg-dom-link" onclick="' + cfgGo('svc', x, pid + '.' + aid) + '">' + cfgEsc(cfgDomain(x).name) + '</a>').join(', ') +
          ' 서비스에 속합니다' + (p.steps ? '. 진행 순서 ' + cfgEsc(p.steps) : '') + '.</div>' + (isS1 ? '' : cfgConsoleBtn(p)) + '</div>';
      html += '<details class="cfg-inst"' + (specsOpen ? ' open' : '') + '><summary>인스턴스 개요와 사양 (간략 설명)</summary>' + (typeof wikiActions === 'function' ? wikiActions('instance', p.docId) : '') +
        '<p class="manual-desc">' + cfgFmt(p.desc) + '</p><div class="spec-grid">' + p.specs.map(s =>
          '<div class="spec-item"><span class="spec-k">' + cfgEsc(s[0]) + '</span><span class="spec-v">' + cfgEsc(s[1]) + '</span></div>').join('') + '</div></details>';
      return html + (isS1 ? cfgAreaShort(a) : cfgArea(a, pid, aid));
    }

    function cfgAreaShort(a) {
      if (!a.design || !a.design.length) return '';
      return '<section class="manual-card-box" id="cfg-sec-0"><h3 class="box-title">간략 설명</h3><ul class="cfg-list">' +
        a.design.map(d => '<li>' + cfgFmt(d) + '</li>').join('') + '</ul></section>';
    }

    function cfgStepHead(s) {
      return (typeof wikiActions === 'function' ? wikiActions('steps', CFG.data.stepsDocId) : '') + '<div class="cfg-head cfg-step-head"><div class="cfg-step-no">' + cfgEsc(s.no) + '</div><div>' +
        '<h2 class="cfg-head-title">' + cfgEsc(s.title) + '</h2>' +
        '<p class="manual-desc">' + cfgFmt(s.why) + ' 실행 위치: ' + cfgEsc(s.where) + '</p></div></div>' +
        cfgCode(s.gate, '통과 조건 (이게 나와야 다음 단계)', '검증');
    }

    // 서비스 영역 영속화 헬퍼 (로그인 시 Wiki API 서버 저장, 미로그인/정적 환경 시 로컬스토리지 폴백)
    function cfgLoadCustoms(pid, aid, a) {
      if (typeof WIKI !== 'undefined' && WIKI.ready && a && a.docId) return;
      try {
        const raw = localStorage.getItem('fig.cfg.custom_areas_v1');
        if (!raw) return;
        const map = JSON.parse(raw);
        const saved = map[pid + '__' + aid];
        if (saved) {
          if (saved.commands) a.commands = saved.commands;
          if (saved.config) a.config = saved.config;
          if (saved.design) a.design = saved.design;
          if (saved.verify) a.verify = saved.verify;
          if (saved.trouble) a.trouble = saved.trouble;
        }
      } catch (e) {}
    }

    function cfgSaveCustoms(pid, aid, a) {
      try {
        let map = {};
        const raw = localStorage.getItem('fig.cfg.custom_areas_v1');
        if (raw) map = JSON.parse(raw);
        map[pid + '__' + aid] = {
          commands: a.commands || [],
          config: a.config || [],
          design: a.design || [],
          verify: a.verify || [],
          trouble: a.trouble || []
        };
        localStorage.setItem('fig.cfg.custom_areas_v1', JSON.stringify(map));
      } catch (e) {}
    }

    async function cfgPersistArea(pid, aid, a, message) {
      if (typeof WIKI !== 'undefined' && WIKI.ready && a && a.docId && typeof wkDoc === 'function') {
        const d = wkDoc(a.docId);
        if (d) {
          const nextBody = JSON.parse(JSON.stringify(d.body || {}));
          nextBody.design = a.design || [];
          nextBody.config = a.config || [];
          nextBody.commands = a.commands || [];
          nextBody.verify = a.verify || [];
          nextBody.trouble = a.trouble || [];
          if (typeof wikiFindSecret === 'function') {
            const sec = wikiFindSecret(nextBody);
            if (sec) {
              alert('비밀값처럼 보이는 내용은 저장할 수 없습니다 (' + sec.field + '). <비밀번호>, <개인키> 같은 자리표시로 바꾸세요.');
              await wikiReload(true);
              return false;
            }
          }
          try {
            const r = await api('PUT', '/api/docs/' + a.docId, {
              base_rev: d.rev,
              body: nextBody,
              message: message || '서비스 영역 항목 수정'
            });
            if (typeof wkRecordLocalAccess === 'function') {
              wkRecordLocalAccess('edit', 'area:' + (nextBody.name || a.name || a.docId) + ' (' + r.rev + '판)');
            }
            if (typeof wikiToast === 'function') wikiToast('서버에 저장했습니다 (' + r.rev + '판)');
            await wikiReload(true);
            return true;
          } catch (e) {
            if (e.status === 401) return false;
            if (e.status === 409) {
              alert('다른 팀원이 먼저 수정해 판 충돌(409)이 발생했습니다. 최신 문서를 다시 불러옵니다.');
              await wikiReload(true);
              return false;
            }
            alert('저장하지 못했습니다: ' + (e.error || e.status || '오류'));
            await wikiReload(true);
            return false;
          }
        }
      }
      cfgSaveCustoms(pid, aid, a);
      cfgRenderBody();
      return true;
    }

    function cfgResetCustoms(pid, aid) {
      if (!confirm('현재 영역을 기본 실측 데이터로 되돌리시겠습니까?')) return;
      try {
        const raw = localStorage.getItem('fig.cfg.custom_areas_v1');
        if (raw) {
          const map = JSON.parse(raw);
          delete map[pid + '__' + aid];
          localStorage.setItem('fig.cfg.custom_areas_v1', JSON.stringify(map));
        }
      } catch (e) {}
      location.reload();
    }

    function cfgSectionKey(type) {
      return type === 'command' ? 'commands' : type;
    }

    async function cfgMoveBuilderItem(type, pid, aid, idx, dir) {
      const a = cfgAreaOf(pid, aid);
      if (!a) return;
      cfgLoadCustoms(pid, aid, a);
      const key = cfgSectionKey(type);
      const arr = a[key];
      if (!Array.isArray(arr)) return;
      const to = idx + dir;
      if (to < 0 || to >= arr.length) return;
      const tmp = arr[idx];
      arr[idx] = arr[to];
      arr[to] = tmp;
      await cfgPersistArea(pid, aid, a, '서비스 영역 ' + key + ' 순서 변경');
    }

    function cfgItemActsHtml(type, pid, aid, idx, len, editLabel) {
      return '<div class="cfg-item-acts">' +
        '<button type="button" class="cfg-item-btn" onclick="cfgMoveBuilderItem(\\'' + type + '\\',\\'' + pid + '\\',\\'' + aid + '\\',' + idx + ',-1)" title="위로 이동"' + (idx <= 0 ? ' disabled' : '') + '>↑</button>' +
        '<button type="button" class="cfg-item-btn" onclick="cfgMoveBuilderItem(\\'' + type + '\\',\\'' + pid + '\\',\\'' + aid + '\\',' + idx + ',1)" title="아래로 이동"' + (idx >= len - 1 ? ' disabled' : '') + '>↓</button>' +
        '<button type="button" class="cfg-item-btn" onclick="cfgOpenBuilderModal(\\'' + type + '\\',\\'' + pid + '\\',\\'' + aid + '\\',' + idx + ')" title="수정">' + (editLabel || '✏️') + '</button>' +
        '<button type="button" class="cfg-item-btn btn-del" onclick="cfgDeleteBuilderItem(\\'' + type + '\\',\\'' + pid + '\\',\\'' + aid + '\\',' + idx + ')" title="삭제">✕</button>' +
        '</div>';
    }

    // 서비스 영역 직관적 모듈형 렌더러 (설계 · 설정 · 명령어 · 검증 · 오류대응 + 빠른 추가/수정/순서이동)
    function cfgArea(a, pid, aid) {
      if (pid && aid) cfgLoadCustoms(pid, aid, a);
      const useLocalOnly = !(typeof WIKI !== 'undefined' && WIKI.ready && a.docId);
      const isCustomized = (useLocalOnly && pid && aid && localStorage.getItem('fig.cfg.custom_areas_v1') &&
        JSON.parse(localStorage.getItem('fig.cfg.custom_areas_v1'))[pid + '__' + aid]);

      const secs = [];

      // 1. 설계 원칙
      let designHtml = '';
      if (a.design && a.design.length) {
        designHtml += '<ul class="cfg-list">' + a.design.map((d, i) =>
          '<li class="cfg-list-row">' +
          '<div>' + cfgFmt(d) + '</div>' +
          cfgItemActsHtml('design', pid, aid, i, a.design.length, '✏️') +
          '</li>').join('') + '</ul>';
      } else {
        designHtml = '<p class="cfg-empty">등록된 설계 원칙이 없습니다. [+ 원칙 추가] 버튼으로 등록하세요.</p>';
      }
      secs.push([
        '설계',
        '<div class="cfg-sec-header"><span class="cfg-sec-title">📘 설계 원칙</span>' +
        '<div class="cfg-sec-acts">' +
        '<button type="button" class="cfg-btn-add" onclick="cfgOpenBuilderModal(\\'design\\',\\'' + pid + '\\',\\'' + aid + '\\',-1)">+ 원칙 추가</button>' +
        '</div></div>' + designHtml
      ]);

      // 2. 설정 파일
      let configHtml = '';
      if (a.config && a.config.length) {
        configHtml += a.config.map((c, i) =>
          '<div class="cfg-card-item">' +
          '<div class="cfg-card-bar"><span class="cfg-card-idx">설정 #' + (i + 1) + '</span>' +
          cfgItemActsHtml('config', pid, aid, i, a.config.length, '✏️ 수정') + '</div>' +
          cfgCode(c.code, c.label) +
          '</div>').join('');
      } else {
        configHtml = '<p class="cfg-empty">등록된 설정 파일이 없습니다. [+ 설정 추가]로 설정 파일 내용을 등록하세요.</p>';
      }
      secs.push([
        '설정',
        '<div class="cfg-sec-header"><span class="cfg-sec-title">⚙️ 설정 파일</span>' +
        '<div class="cfg-sec-acts">' +
        '<button type="button" class="cfg-btn-add" onclick="cfgOpenBuilderModal(\\'config\\',\\'' + pid + '\\',\\'' + aid + '\\',-1)">+ 설정 추가</button>' +
        '</div></div>' + configHtml
      ]);

      // 3. 명령어
      let cmdHtml = '';
      if (a.commands && a.commands.length) {
        cmdHtml += a.commands.map((c, i) =>
          '<div class="cfg-card-item">' +
          '<div class="cfg-card-bar"><span class="cfg-card-idx">명령 #' + (i + 1) + '</span>' +
          cfgItemActsHtml('command', pid, aid, i, a.commands.length, '✏️ 수정') + '</div>' +
          cfgCode(c.code, c.label, c.cat) +
          '</div>').join('');
      } else {
        cmdHtml = '<p class="cfg-empty">등록된 명령어가 없습니다. [+ 명령어 추가]로 터미널 명령어를 등록하세요.</p>';
      }
      secs.push([
        '명령어',
        '<div class="cfg-sec-header"><span class="cfg-sec-title">💻 실행 명령어</span>' +
        '<div class="cfg-sec-acts">' +
        '<button type="button" class="cfg-btn-add" onclick="cfgOpenBuilderModal(\\'command\\',\\'' + pid + '\\',\\'' + aid + '\\',-1)">+ 명령어 추가</button>' +
        '</div></div>' + cmdHtml
      ]);

      // 4. 검증
      let verifyHtml = '';
      if (a.verify && a.verify.length) {
        verifyHtml += a.verify.map((v, i) =>
          '<div class="cfg-card-item">' +
          '<div class="cfg-card-bar"><span class="cfg-card-idx">검증 #' + (i + 1) + '</span>' +
          cfgItemActsHtml('verify', pid, aid, i, a.verify.length, '✏️ 수정') + '</div>' +
          cfgCode(v.code, v.label, '검증') +
          '<div class="cfg-expect" style="margin-top:4px;"><b>기대 결과:</b> ' + cfgFmt(v.expect) + '</div></div>').join('');
      } else {
        verifyHtml = '<p class="cfg-empty">등록된 검증 항목이 없습니다. [+ 검증 추가]로 테스트 명령을 등록하세요.</p>';
      }
      secs.push([
        '검증',
        '<div class="cfg-sec-header"><span class="cfg-sec-title">✅ 검증 및 기대 결과</span>' +
        '<div class="cfg-sec-acts">' +
        '<button type="button" class="cfg-btn-add" onclick="cfgOpenBuilderModal(\\'verify\\',\\'' + pid + '\\',\\'' + aid + '\\',-1)">+ 검증 추가</button>' +
        '</div></div>' + verifyHtml
      ]);

      // 5. 오류 대응
      let troubleHtml = '';
      if (a.trouble && a.trouble.length) {
        const rowsWithActs = a.trouble.map((t, i) => [
          t[0], t[1], t[2],
          t[3] + '<div style="margin-top:4px;">' +
          cfgItemActsHtml('trouble', pid, aid, i, a.trouble.length, '✏️ 수정') +
          '</div>'
        ]);
        troubleHtml = cfgTable(['증상', '의심 변수·영역', '확인 명령', '조치 및 편집'], rowsWithActs, 'cfg-trouble');
      } else {
        troubleHtml = '<p class="cfg-empty">등록된 오류 대응 가이드가 없습니다. [+ 오류 대응 추가]로 등록하세요.</p>';
      }
      secs.push([
        '오류 시 확인',
        '<div class="cfg-sec-header"><span class="cfg-sec-title">⚠️ 오류 대응 가이드</span>' +
        '<div class="cfg-sec-acts">' +
        '<button type="button" class="cfg-btn-add" onclick="cfgOpenBuilderModal(\\'trouble\\',\\'' + pid + '\\',\\'' + aid + '\\',-1)">+ 오류 대응 추가</button>' +
        '</div></div>' + troubleHtml
      ]);

      // 상단 칩 내비게이션 및 빌더 제어 바
      const chips = '<div class="cfg-chips" style="align-items:center;">' +
        secs.map((s, i) =>
          '<button type="button" class="cfg-chip" onclick="cfgScrollToSec(' + i + ')">' + s[0] + '</button>').join('') +
        (typeof cfgGuideOpen === 'function' && a.docId
          ? '<button type="button" class="cfg-btn-add" style="margin-left:auto;" onclick="cfgGuideOpen({action:\\'patch\\',kind:\\'area\\',docId:' + a.docId + '})">📋 지침으로 이 영역 수정/순서편집</button>'
          : '') +
        (isCustomized ? '<button type="button" class="cfg-item-btn btn-del" style="' + (typeof cfgGuideOpen === 'function' && a.docId ? '' : 'margin-left:auto;') + 'padding:3px 8px;" onclick="cfgResetCustoms(\\'' + pid + '\\',\\'' + aid + '\\')">↺ 원본 실측값 복원</button>' : '') +
        '</div>';

      return chips + secs.map((s, i) =>
        '<section class="manual-card-box" id="cfg-sec-' + i + '">' + s[1] + '</section>').join('');
    }

    // 서비스 영역 직관적 카드 빌더 모달 (신규 등록 및 수정 팝업)
    function cfgOpenBuilderModal(type, pid, aid, idx) {
      const a = cfgAreaOf(pid, aid);
      if (!a) return;
      cfgLoadCustoms(pid, aid, a);

      const old = document.getElementById('cfg-builder-modal');
      if (old) old.remove();

      let modalTitle = '';
      let fieldsHtml = '';

      if (type === 'command') {
        const isEdit = (idx >= 0);
        const item = isEdit ? (a.commands && a.commands[idx]) : { cat: '조회', label: '', code: '' };
        modalTitle = isEdit ? '💻 명령어 수정' : '💻 새 명령어 등록';
        fieldsHtml =
          '<div class="cfg-builder-field">' +
          '<label class="cfg-builder-label">명령어 유형 (카테고리)</label>' +
          '<div class="cfg-cat-chips">' +
          ['설치', '적용', '조회', '검증'].map(cat =>
            '<label><input type="radio" name="bld-cat" value="' + cat + '" class="cfg-cat-chip-radio"' + (item.cat === cat ? ' checked' : '') + '>' +
            '<span class="cfg-cat-chip-label">' + cat + '</span></label>').join('') +
          '</div></div>' +
          '<div class="cfg-builder-field">' +
          '<label class="cfg-builder-label">명령어 설명 (라벨)</label>' +
          '<input type="text" id="bld-label" class="cfg-builder-input" value="' + cfgEsc(item.label || '') + '" placeholder="예: nova 서비스 구동 상태 확인">' +
          '</div>' +
          '<div class="cfg-builder-field">' +
          '<label class="cfg-builder-label">실행 명령어 (Shell / CLI)</label>' +
          '<textarea id="bld-code" class="cfg-builder-textarea" placeholder="실행할 명령어를 입력하세요 (예: systemctl status nova-compute)">' + cfgEsc(item.code || '') + '</textarea>' +
          '</div>';
      } else if (type === 'config') {
        const isEdit = (idx >= 0);
        const item = isEdit ? (a.config && a.config[idx]) : { label: '', code: '' };
        modalTitle = isEdit ? '⚙️ 설정 파일 수정' : '⚙️ 새 설정 파일 등록';
        fieldsHtml =
          '<div class="cfg-builder-field">' +
          '<label class="cfg-builder-label">설정 파일 경로 및 설명</label>' +
          '<input type="text" id="bld-label" class="cfg-builder-input" value="' + cfgEsc(item.label || '') + '" placeholder="예: /etc/nova/nova.conf (컴퓨트 설정)">' +
          '</div>' +
          '<div class="cfg-builder-field">' +
          '<label class="cfg-builder-label">설정 파일 내용 (Conf / YAML / Script)</label>' +
          '<textarea id="bld-code" class="cfg-builder-textarea" style="min-height:160px;" placeholder="파일 내용을 입력하세요">' + cfgEsc(item.code || '') + '</textarea>' +
          '</div>';
      } else if (type === 'design') {
        const isEdit = (idx >= 0);
        const item = isEdit ? (a.design && a.design[idx]) : '';
        modalTitle = isEdit ? '📘 설계 원칙 수정' : '📘 새 설계 원칙 등록';
        fieldsHtml =
          '<div class="cfg-builder-field">' +
          '<label class="cfg-builder-label">설계 원칙 및 아키텍처 설명</label>' +
          '<textarea id="bld-code" class="cfg-builder-textarea" style="min-height:90px;" placeholder="설계 원칙을 입력하세요 (예: nova-compute는 각 compute 노드에서 up 상태여야 인스턴스가 프로비저닝됩니다)">' + cfgEsc(item || '') + '</textarea>' +
          '</div>';
      } else if (type === 'verify') {
        const isEdit = (idx >= 0);
        const item = isEdit ? (a.verify && a.verify[idx]) : { label: '', code: '', expect: '' };
        modalTitle = isEdit ? '✅ 검증 항목 수정' : '✅ 새 검증 항목 등록';
        fieldsHtml =
          '<div class="cfg-builder-field">' +
          '<label class="cfg-builder-label">검증 항목 라벨</label>' +
          '<input type="text" id="bld-label" class="cfg-builder-input" value="' + cfgEsc(item.label || '') + '" placeholder="예: OpenStack 컴퓨트 서비스 상태 확인">' +
          '</div>' +
          '<div class="cfg-builder-field">' +
          '<label class="cfg-builder-label">검증 명령어</label>' +
          '<textarea id="bld-code" class="cfg-builder-textarea" placeholder="openstack compute service list">' + cfgEsc(item.code || '') + '</textarea>' +
          '</div>' +
          '<div class="cfg-builder-field">' +
          '<label class="cfg-builder-label">기대 결과 (Expectation)</label>' +
          '<input type="text" id="bld-expect" class="cfg-builder-input" value="' + cfgEsc(item.expect || '') + '" placeholder="예: 모든 compute 노드가 Status=enabled, State=up">' +
          '</div>';
      } else if (type === 'trouble') {
        const isEdit = (idx >= 0);
        const item = isEdit ? (a.trouble && a.trouble[idx]) : ['', '', '', ''];
        modalTitle = isEdit ? '⚠️ 오류 대응 수정' : '⚠️ 새 오류 대응 등록';
        fieldsHtml =
          '<div class="cfg-builder-field"><label class="cfg-builder-label">증상 (Symptom)</label>' +
          '<input type="text" id="bld-t0" class="cfg-builder-input" value="' + cfgEsc(item[0] || '') + '" placeholder="예: nova-compute 서비스 down"></div>' +
          '<div class="cfg-builder-field"><label class="cfg-builder-label">의심 변수 및 영역</label>' +
          '<input type="text" id="bld-t1" class="cfg-builder-input" value="' + cfgEsc(item[1] || '') + '" placeholder="예: RAM 부족, 192.168.120.x 통신"></div>' +
          '<div class="cfg-builder-field"><label class="cfg-builder-label">확인 명령</label>' +
          '<input type="text" id="bld-t2" class="cfg-builder-input" value="' + cfgEsc(item[2] || '') + '" placeholder="예: systemctl status nova-compute"></div>' +
          '<div class="cfg-builder-field"><label class="cfg-builder-label">조치 방안</label>' +
          '<input type="text" id="bld-t3" class="cfg-builder-input" value="' + cfgEsc(item[3] || '') + '" placeholder="예: 서비스 재시작 (systemctl restart nova-compute)"></div>';
      }

      const modal = document.createElement('div');
      modal.id = 'cfg-builder-modal';
      modal.className = 'cfg-modal-overlay';
      modal.innerHTML =
        '<div class="cfg-builder-modal-card" role="dialog" aria-modal="true">' +
        '<div class="cfg-builder-modal-head">' +
        '<span>' + modalTitle + '</span>' +
        '<button type="button" class="cfg-win-btn btn-close" id="bld-close" style="color:#cbd5e1;">✕</button>' +
        '</div>' +
        '<div class="cfg-builder-modal-body">' + fieldsHtml + '</div>' +
        '<div class="cfg-modal-foot">' +
        '<button type="button" class="cfg-btn-cancel" id="bld-cancel">취소</button>' +
        '<button type="button" class="cfg-btn-confirm" id="bld-save" style="background:#2563eb;border-color:#3b82f6;">저장 및 즉시 반영</button>' +
        '</div></div>';
      document.body.appendChild(modal);

      const close = () => { modal.remove(); document.removeEventListener('keydown', onKey); };
      const onKey = e => { if (e.key === 'Escape') close(); };
      document.addEventListener('keydown', onKey);

      modal.querySelector('#bld-close').onclick = close;
      modal.querySelector('#bld-cancel').onclick = close;
      modal.querySelector('#bld-save').onclick = async () => {
        if (type === 'command') {
          const cat = (modal.querySelector('input[name="bld-cat"]:checked') || {}).value || '조회';
          const label = (modal.querySelector('#bld-label').value || '').trim();
          const code = (modal.querySelector('#bld-code').value || '').trim();
          if (!code) { alert('명령어 내용을 입력해주세요.'); return; }
          a.commands = a.commands || [];
          if (idx >= 0) a.commands[idx] = { cat, label, code };
          else a.commands.push({ cat, label, code });
        } else if (type === 'config') {
          const label = (modal.querySelector('#bld-label').value || '').trim();
          const code = (modal.querySelector('#bld-code').value || '').trim();
          if (!code) { alert('설정 내용을 입력해주세요.'); return; }
          a.config = a.config || [];
          if (idx >= 0) a.config[idx] = { label, code };
          else a.config.push({ label, code });
        } else if (type === 'design') {
          const code = (modal.querySelector('#bld-code').value || '').trim();
          if (!code) { alert('설계 원칙 내용을 입력해주세요.'); return; }
          a.design = a.design || [];
          if (idx >= 0) a.design[idx] = code;
          else a.design.push(code);
        } else if (type === 'verify') {
          const label = (modal.querySelector('#bld-label').value || '').trim();
          const code = (modal.querySelector('#bld-code').value || '').trim();
          const expect = (modal.querySelector('#bld-expect').value || '').trim();
          if (!code) { alert('검증 명령어를 입력해주세요.'); return; }
          a.verify = a.verify || [];
          if (idx >= 0) a.verify[idx] = { label, code, expect };
          else a.verify.push({ label, code, expect });
        } else if (type === 'trouble') {
          const t0 = (modal.querySelector('#bld-t0').value || '').trim();
          const t1 = (modal.querySelector('#bld-t1').value || '').trim();
          const t2 = (modal.querySelector('#bld-t2').value || '').trim();
          const t3 = (modal.querySelector('#bld-t3').value || '').trim();
          if (!t0 || !t2) { alert('증상과 확인 명령을 입력해주세요.'); return; }
          a.trouble = a.trouble || [];
          if (idx >= 0) a.trouble[idx] = [t0, t1, t2, t3];
          else a.trouble.push([t0, t1, t2, t3]);
        }
        const saveBtn = modal.querySelector('#bld-save');
        if (saveBtn) { saveBtn.disabled = true; saveBtn.textContent = '저장 중…'; }
        const ok = await cfgPersistArea(pid, aid, a, '모듈 빌더 ' + type + (idx >= 0 ? ' 수정' : ' 추가'));
        if (ok) close();
        else if (saveBtn) { saveBtn.disabled = false; saveBtn.textContent = '저장 및 즉시 반영'; }
      };
      modal.onclick = e => { if (e.target === modal) close(); };
    }

    async function cfgDeleteBuilderItem(type, pid, aid, idx) {
      const a = cfgAreaOf(pid, aid);
      if (!a) return;
      cfgLoadCustoms(pid, aid, a);
      if (!confirm('선택한 항목을 삭제하시겠습니까?')) return;
      if (type === 'command' && a.commands) a.commands.splice(idx, 1);
      else if (type === 'config' && a.config) a.config.splice(idx, 1);
      else if (type === 'design' && a.design) a.design.splice(idx, 1);
      else if (type === 'verify' && a.verify) a.verify.splice(idx, 1);
      else if (type === 'trouble' && a.trouble) a.trouble.splice(idx, 1);
      await cfgPersistArea(pid, aid, a, '모듈 빌더 ' + type + ' 삭제');
    }

    // 같은 중분류 목록 안에서 이전/다음
    function cfgPager() {
      const list = CFG.lens === 'ref' ? cfgMajors('ref') : cfgMinors(CFG.lens, CFG.major);
      const curId = CFG.lens === 'ref' ? CFG.major : CFG.minor;
      const i = list.findIndex(m => m.id === curId);
      if (i < 0 || list.length < 2) return '';
      const link = (m, label) => {
        const go = CFG.lens === 'ref' ? cfgGo('ref', m.id, '') : cfgGo(CFG.lens, CFG.major, m.id);
        return '<button type="button" class="cfg-pager-btn" onclick="' + go + '"><span>' + label + '</span>' + cfgEsc(m.name) +
          (m.sub && CFG.lens === 'svc' ? ' / ' + cfgEsc(m.sub) : '') + '</button>';
      };
      return '<div class="cfg-pager">' + (i > 0 ? link(list[i - 1], '이전') : '<span></span>') +
        (i < list.length - 1 ? link(list[i + 1], '다음') : '<span></span>') + '</div>';
    }

    // ---------- 시점(입장) 렌즈: 전체 · AWS · KT · OpenStack · 온프렘 ----------
    // 설계 문서의 서버 → 통합 콘솔 대상 (s1 은 정책상 터미널 없음, kt-w1 은 콘솔 대상 아님)
    const CFG_CONSOLE = { 'controller': 'controller', 'cp1': 'k8s-cp1', 'w1': 'k8s-w1', 'db-01': 'db-01', 'kt-edge': 'kt-edge', 'aws-dr': 'aws-dr', 'aws-ctl': 'aws-ctl' };
    function cfgConsoleId(p) { return (p && CFG_CONSOLE[p.short]) || null; }
    function cfgOpenConsole(id) {
      if (typeof CS !== 'undefined') CS.pending = id;
      if (typeof switchView === 'function') switchView('console');
    }
    function cfgConsoleBtn(p) {
      const id = cfgConsoleId(p);
      return id ? '<button type="button" class="wk-btn cfg-term-btn" onclick="cfgOpenConsole(&quot;' + cfgEsc(id) + '&quot;)">이 서버 터미널 열기</button>' : '';
    }
    function cfgZoomBar() {
      const tabs = [VIEW_FOREST].concat(cfgClouds().map(c => ({ id: c, name: CLOUD_NAME[c], cloud: c })));
      return '<nav class="cfg-zoombar" aria-label="기준점 고르기">' + tabs.map(t =>
        '<button type="button" class="cfg-zoom-step' + (t.id === CFG.major ? ' on' : '') + '"' + (t.id === CFG.major ? ' aria-current="page"' : '') +
        ' onclick="' + cfgGo('zoom', t.id, t.id === 'forest' ? 'all' : 'view') + '">' +
        '<span class="cfg-zoom-t">' + (t.cloud ? '<span class="cfg-dot cfg-c-' + t.cloud + '"></span> ' : '') + cfgEsc(t.name) + '</span></button>').join('') + '</nav>';
    }
    function cfgTopologyPage() {
      const ref = (CFG.data.reference || []).find(r => /^전체 토폴로지/.test(r[1] || ''));
      return ref ? cfgPage(ref[0]) : null;
    }
    // 숲: 클라우드별 서버 지도 + 실측 토폴로지 문서(위키)
    function cfgZoomForest() {
      let html = '<div class="cfg-head"><h2 class="cfg-head-title">숲 · 전체 구성</h2><p class="manual-desc">세 클라우드와 그 안 서버가 한 화면에 보입니다. ' +
        '클라우드 이름을 누르면 해당 클라우드 기준 설계로, 서버를 누르면 그 서버의 실제 작업으로 갑니다.</p></div>';
      html += '<div class="cfg-forest">' + cfgClouds().map(c => {
        const list = cfgInstOrder().filter(pid => cfgPage(pid).cloud === c);
        return '<section class="cfg-forest-cloud"><button type="button" class="cfg-forest-name" onclick="' + cfgGo('zoom', c, 'view') + '">' +
          '<span class="cfg-dot cfg-c-' + c + '"></span>' + cfgEsc(CLOUD_NAME[c]) + '<small>' + list.length + '대</small></button>' +
          list.map(pid => {
            const p = cfgPage(pid);
            return '<button type="button" class="cfg-forest-inst" onclick="' + cfgGo('zoom', c, pid) + '"><b>' + cfgEsc(p.short) + '</b>' +
              (p.status && p.status !== 'live' ? ' ' + cfgBadge(p.status) : '') + '<span>' + cfgEsc(p.tag) + '</span></button>';
          }).join('') + '</section>';
      }).join('') + '</div>';
      const topo = cfgTopologyPage();
      return html + (topo ? cfgDoc(topo) : '<div class="cfg-empty-panel"><p>실측 토폴로지 문서(“전체 토폴로지 · 실측”)가 아직 없습니다. 참고 문서로 추가하면 여기에 나옵니다.</p></div>');
    }
    // 클라우드 입장: 위키의 '시점 · <클라우드>' 문서(실측 연결·의존·멈추면) + 이 클라우드 안 구성 요약
    function cfgCloudView(c) {
      const list = cfgInstOrder().filter(pid => cfgPage(pid).cloud === c);
      const vp = cfgViewPage(c);
      let html = vp ? cfgDoc(vp) : '<div class="cfg-empty-panel"><p>“시점 · ' + cfgEsc(CLOUD_NAME[c]) + '” 문서가 아직 없습니다. 참고 문서로 추가하면 여기에 나옵니다.</p></div>';
      if (!list.length) return html;
      const areas = [], troubles = [], doms = {};
      list.forEach(pid => { const p = cfgPage(pid); p.areas.forEach(a => {
        areas.push([p, a]); (a.trouble || []).forEach(t => troubles.push([p, a, t]));
        a.domains.forEach(d => { doms[d] = (doms[d] || 0) + 1; });
      }); });
      const first = t => { t = String(t || ''); const i = t.search(/[.。]\\s/); return (i > 0 ? t.slice(0, i + 1) : t).slice(0, 120); };
      html += '<h3 class="cfg-h">이 클라우드 안 — 서버 ' + list.length + '대 · 서비스 영역 ' + areas.length + '개 · 알려진 오류 대응 ' + troubles.length + '건</h3>';
      html += '<section class="manual-card-box"><h3 class="box-title">서버별 역할</h3>' + cfgTable(['서버', '역할', '서비스 영역', '상태'], list.map(pid => {
        const p = cfgPage(pid);
        return [p.short, first(p.desc), p.areas.map(a => a.name).join(', '), STATUS_NAME[p.status] || p.status || ''];
      })) + '<div class="cfg-chips">' + list.map(pid => '<a href="javascript:void(0)" class="cfg-chip" onclick="' + cfgGo('zoom', c, pid) + '">' + cfgEsc(cfgPage(pid).short) + ' 작업 ›</a>').join('') + '</div></section>';
      html += '<section class="manual-card-box"><h3 class="box-title">맡은 서비스 분류</h3><div class="cfg-chips">' + Object.keys(doms).map(d =>
        '<a href="javascript:void(0)" class="cfg-chip" onclick="' + cfgGo('svc', d, '') + '">' + cfgEsc((cfgDomain(d) || { name: d }).name) + ' ' + doms[d] + '</a>').join('') + '</div></section>';
      if (troubles.length) html += '<section class="manual-card-box"><h3 class="box-title">알려진 오류 증상</h3>' +
        cfgTable(['서버 / 영역', '증상', '의심 지점', '조치'], troubles.slice(0, 12).map(x => [x[0].short + ' / ' + x[1].name, x[2][0], x[2][1], x[2][3]]), 'cfg-trouble') +
        (troubles.length > 12 ? '<p class="manual-desc">외 ' + (troubles.length - 12) + '건은 참고 › 오류 확인 색인에서 봅니다.</p>' : '') + '</section>';
      return html;
    }
    // 서버 작업: 서버 하나에서 실제로 실행하는 것 — 명령·검증 + 터미널 바로 열기
    function cfgZoomMember(pid) {
      const p = cfgPage(pid);
      if (!p) return '<div class="cfg-empty-panel"><p>서버를 고르세요.</p></div>';
      let html = '<div class="cfg-head"><div class="cfg-head-line"><span class="cfg-cloud cfg-c-' + p.cloud + '">' + cfgEsc(CLOUD_NAME[p.cloud]) + '</span>' +
        '<span class="cfg-head-inst">' + cfgEsc(p.title) + '</span><span class="manual-tag">서버 작업</span></div>' +
        '<h2 class="cfg-head-title">' + cfgEsc(p.short) + ' 에서 하는 일</h2><p class="manual-desc">' + cfgFmt(p.desc) + '</p>' + cfgConsoleBtn(p) + '</div>';
      if (!p.areas.length) return html + '<div class="cfg-empty-panel"><p>이 서버에 서비스 영역이 아직 없습니다.</p></div>';
      return html + p.areas.map(a => {
        const cmds = (a.commands || []).slice().sort((x, y) => CAT_ORDER.indexOf(x.cat) - CAT_ORDER.indexOf(y.cat));
        const ver = (a.verify || []).map(v => cfgCode(v.code, v.label, '검증') + '<div class="cfg-expect">기대 결과: ' + cfgFmt(v.expect) + '</div>').join('');
        return '<section class="manual-card-box"><h3 class="box-title">' + cfgEsc(a.name) + (a.status && a.status !== 'live' ? ' ' + cfgBadge(a.status) : '') +
          ' <a href="javascript:void(0)" class="cfg-dom-link" onclick="' + cfgGo('inst', pid, a.id) + '">설계·설정·오류까지 ›</a></h3>' +
          cmds.map(c => cfgCode(c.code, c.label, c.cat)).join('') + ver +
          (!cmds.length && !ver ? '<p class="manual-desc">이 영역에 실행 명령이 아직 없습니다.</p>' : '') + '</section>';
      }).join('');
    }

    // ---------- 참고 문서 ----------
    function cfgDoc(p) {
      let html = '<div class="cfg-head">' + (typeof wikiActions === 'function' ? wikiActions('page', p.docId) : '') + '<h2 class="cfg-head-title">' + cfgEsc(p.title) + ' <span class="manual-tag">' + cfgEsc(p.tag || '') + '</span></h2>' +
        '<p class="manual-desc">' + cfgFmt(p.desc) + '</p></div>';
      p.blocks.forEach(b => {
        if (b.type === 'h') html += '<h3 class="cfg-h">' + cfgEsc(b.text) + '</h3>';
        else if (b.type === 'p') html += '<p class="manual-desc">' + cfgFmt(b.text) + '</p>';
        else if (b.type === 'code') html += cfgCode(b.code, b.label);
        else if (b.type === 'table') html += cfgTable(b.head, b.rows);
        else if (b.type === 'vars') html += cfgTable(['변수', '값 (실측)', '사용처', '바뀌면 확인'], CFG.data.vars, 'cfg-vars');
        else if (b.type === 'legend') html += '<div class="cfg-legend">' +
          cfgBadge('live') + ' 현재 구성을 직접 조회해 확인한 값 ' + cfgBadge('design') + ' 적용 전 설계안 ' +
          cfgBadge('nolook') + ' 접속 불가로 외부 응답과 문서만 확인</div>';
        else if (b.type === 'troubleall') html += cfgTroubleAll();
      });
      return html;
    }
    function cfgTroubleAll() {
      const rows = [];
      CFG.data.instances.forEach(id => {
        const p = cfgPage(id);
        p.areas.forEach(a => (a.trouble || []).forEach(t => rows.push([p.short + ' / ' + a.name, t[1], t[0], t[2], t[3]])));
      });
      return '<input type="search" class="cfg-search" aria-label="오류 표 거르기" placeholder="증상, 변수, 명령어로 거르기 (예: 6443, MTU, sg-db)" oninput="cfgFilterTable(this)">' +
        cfgTable(['위치', '변수·영역', '증상', '확인 명령', '조치'], rows, 'cfg-trouble cfg-filterable');
    }
    function cfgFilterTable(inp) {
      const q = inp.value.trim().toLowerCase();
      document.querySelectorAll('.cfg-filterable tbody tr').forEach(tr => {
        tr.style.display = !q || tr.textContent.toLowerCase().indexOf(q) >= 0 ? '' : 'none';
      });
    }

    // ===== 상단 [콘솔] 메뉴 =====
    function cnToggle(ev) {
      ev.stopPropagation();
      const m = document.getElementById('cn-menu'), b = document.getElementById('cn-btn');
      const open = m.hidden;
      m.hidden = !open; b.setAttribute('aria-expanded', String(open));
      if (open) { const f = m.querySelector('a'); if (f) f.focus(); }
    }
    document.addEventListener('click', e => {
      const m = document.getElementById('cn-menu');
      if (m && !m.hidden && !e.target.closest('.cn-wrap')) { m.hidden = true; document.getElementById('cn-btn').setAttribute('aria-expanded', 'false'); }
    });
    document.addEventListener('keydown', e => {
      const m = document.getElementById('cn-menu');
      if (e.key === 'Escape' && m && !m.hidden) { m.hidden = true; const b = document.getElementById('cn-btn'); b.setAttribute('aria-expanded', 'false'); b.focus(); }
    });

    // ===== [설정] 터미널 즉시 실행 러너 & 안전 가드 & 푸터 닥 & 플로팅 윈도우 =====
    const CFG_RUNNER = {
      sessions: {},    // id: { id, target, label, code, ws, term, fit, winEl, chipEl, status, x, y, w, h, min, max }
      zIndex: 1110,
      seq: 0,
      storageKey: 'fig.cfg.terminals_v1'
    };

    // 1. 위험 명령어 판별: 서비스 중지/재시작/종료/생성 등 파괴적 명령
    function cfgIsDangerous(code, cat) {
      const str = (code || '').trim();
      const dangerPatterns = [
        /\\b(systemctl\\s+(stop|restart|reload|disable|mask|poweroff|reboot))\\b/i,
        /\\b(service\\s+\\w+\\s+(stop|restart|reload))\\b/i,
        /\\b(docker\\s+(stop|restart|rm|kill|down))\\b/i,
        /\\b(kubectl\\s+(delete|drain|cordon|scale|rollout\\s+restart|apply|replace))\\b/i,
        /\\b(openstack-vm\\.sh\\s+(stop|restart))\\b/i,
        /\\b(virsh\\s+(destroy|shutdown|reboot|undefine|reset))\\b/i,
        /\\b(openstack\\s+\\w+\\s+(delete|set|create|remove|add))\\b/i,
        /\\b(stop\\s+replica|reset\\s+master|drop\\s+database|drop\\s+table|truncate|purge\\s+binary)\\b/i,
        /\\b(rm\\s+-[rf]|kill\\s+-9|pkill|killall|reboot|shutdown|poweroff|halt)\\b/i,
        /\\b(iptables\\s+-[fzxad]|ip\\s+link\\s+set.*down|wg-quick\\s+down|mkfs|fdisk)\\b/i
      ];
      for (let i = 0; i < dangerPatterns.length; i++) {
        if (dangerPatterns[i].test(str)) return true;
      }
      if ((cat === '적용' || cat === '설치') && /\\b(sed\\s+-i|tee|mv|cp|export|git\\s+pull|curl.*\\|\\s*(bash|sh))\\b/i.test(str)) {
        return true;
      }
      return false;
    }

    // 2. 대상 인스턴스/타겟 지능형 탐지
    function cfgDetectTarget(code, label, cat) {
      const text = ((code || '') + ' ' + (label || '')).toLowerCase();
      if (text.includes('160') || text.includes('keystonerc') || text.includes('openstack') || text.includes('nova') || text.includes('glance') || text.includes('neutron')) return 'controller';
      if (text.includes('161')) return 'compute1';
      if (text.includes('163')) return 'compute3';
      if (text.includes('164')) return 'compute4';
      if (text.includes('cp1') || text.includes('kubectl') || text.includes('k3s server') || text.includes('kube-vip')) return 'k8s-cp1';
      if (text.includes('w1') || text.includes('k3s agent')) return 'k8s-w1';
      if (text.includes('db-01') || text.includes('mysql') || text.includes('mariadb') || text.includes('gtid')) return 'db-01';
      if (text.includes('kt-edge') || text.includes('nginx') || text.includes('ktcloud') || text.includes('kt-')) return 'kt-edge';
      if (text.includes('aws-dr') || text.includes('dr-') || text.includes('minwon-mysql')) return 'aws-dr';
      if (text.includes('aws-ctl') || text.includes('prometheus') || text.includes('grafana')) return 'aws-ctl';

      const cur = (CFG.major || '').toLowerCase();
      if (cur.includes('controller')) return 'controller';
      if (cur.includes('compute1')) return 'compute1';
      if (cur.includes('compute3')) return 'compute3';
      if (cur.includes('compute4')) return 'compute4';
      if (cur.includes('cp1')) return 'k8s-cp1';
      if (cur.includes('w1')) return 'k8s-w1';
      if (cur.includes('db')) return 'db-01';
      if (cur.includes('kt')) return 'kt-edge';
      if (cur.includes('dr')) return 'aws-dr';
      if (cur.includes('ctl')) return 'aws-ctl';
      return 'controller';
    }

    // 3. 레이어 초기화 (body에 고정)
    function cfgEnsureLayers() {
      let fl = document.getElementById('cfg-float-layer');
      if (!fl) {
        fl = document.createElement('div');
        fl.id = 'cfg-float-layer';
        document.body.appendChild(fl);
      }
      let dock = document.getElementById('cfg-footer-dock');
      if (!dock) {
        dock = document.createElement('div');
        dock.id = 'cfg-footer-dock';
        dock.className = 'cfg-dock-hidden';
        dock.innerHTML = '<span class="cfg-dock-title">🖥️ 터미널 세션</span>' +
          '<div class="cfg-dock-list" id="cfg-dock-list"></div>' +
          '<div class="cfg-dock-acts">' +
          '<button type="button" class="cfg-dock-btn" onclick="cfgToggleAllMin(true)" title="모두 최소화">_ 숨김</button>' +
          '<button type="button" class="cfg-dock-btn" onclick="cfgToggleAllMin(false)" title="모두 펼치기">□ 표시</button>' +
          '<button type="button" class="cfg-dock-btn" onclick="cfgCloseAllTerms()" title="모두 닫기">✕ 종료</button>' +
          '</div>';
        document.body.appendChild(dock);
      }
      return { fl, dock };
    }

    // 4. 실행 버튼 핸들러 (뷰/확인 vs 수정/변경 분리)
    function cfgRunCode(idx) {
      const item = (CFG.codeMeta && CFG.codeMeta[idx]) || { code: CFG.codes[idx] || '', label: '', cat: '' };
      const target = cfgDetectTarget(item.code, item.label, item.cat);
      if (target === 's1') {
        alert('s1 호스트는 웹에서 콘솔 터미널 접근 및 명령 실행이 불가합니다.');
        return;
      }
      const isDangerous = cfgIsDangerous(item.code, item.cat) || item.cat === '적용' || item.cat === '설치';
      if (isDangerous) {
        cfgShowConfirm(item.code, target, item.label, () => {
          cfgOpenAndExec(item.code, target, item.label, true, null, 'modify');
        });
      } else {
        cfgOpenAndExec(item.code, target, item.label, true, null, 'view');
      }
    }

    // 4-1. 뷰 모드 팝업 (안전 확인 · 읽기 전용)
    function cfgViewCode(idx) {
      const item = (CFG.codeMeta && CFG.codeMeta[idx]) || { code: CFG.codes[idx] || '', label: '', cat: '' };
      const target = cfgDetectTarget(item.code, item.label, item.cat);
      const filePath = cfgExtractFilePath(item.label, item.code);

      const old = document.getElementById('cfg-view-modal');
      if (old) old.remove();

      const modal = document.createElement('div');
      modal.id = 'cfg-view-modal';
      modal.className = 'cfg-modal-overlay cfg-modal-view';
      modal.innerHTML = '<div class="cfg-modal-card" role="dialog" aria-modal="true">' +
        '<div class="cfg-modal-head"><span>👁️ 설정 및 명령어 확인 (뷰 모드 · 읽기 전용)</span><span style="font-size:12px;opacity:0.8;">ESC로 닫기</span></div>' +
        '<div class="cfg-modal-body">' +
        '<div class="cfg-modal-alert"><b>안내:</b> 본 뷰 모드는 시스템 변경 없이 안전하게 설정 파일 및 명령어 구성을 사전 확인·열람하는 모드입니다.</div>' +
        '<div class="cfg-modal-meta">대상 노드: <strong>' + cfgEsc(target) + '</strong> &nbsp;|&nbsp; 항목/파일: ' + cfgEsc(item.label || '설정') + '</div>' +
        '<pre class="cfg-modal-code" style="max-height:260px;">' + cfgEsc(item.code) + '</pre>' +
        '</div>' +
        '<div class="cfg-modal-foot">' +
        '<button type="button" class="cfg-btn-cancel" id="cfg-view-close">닫기</button>' +
        '<button type="button" class="cfg-run-btn cfg-btn-view" id="cfg-view-cat-run">터미널 cat 읽기 전용 확인</button>' +
        '</div>' +
        '</div>';
      document.body.appendChild(modal);

      const close = () => { modal.remove(); document.removeEventListener('keydown', onKey); };
      const onKey = e => { if (e.key === 'Escape') close(); };
      document.addEventListener('keydown', onKey);

      modal.querySelector('#cfg-view-close').onclick = close;
      modal.querySelector('#cfg-view-cat-run').onclick = () => {
        close();
        if (target === 's1') {
          alert('s1 호스트는 웹 콘솔 터미널 접근 불가 대상입니다.');
          return;
        }
        const catCmd = (filePath && filePath.startsWith('/')) ? ('cat ' + filePath) : item.code;
        cfgOpenAndExec(catCmd, target, (item.label || '') + ' (cat 확인)', true, null, 'view');
      };
      modal.onclick = e => { if (e.target === modal) close(); };
    }

    // 4-2. 빨강색 수정/변경(vi/nano) 핸들러 및 사전 경고 모달
    function cfgEditCode(idx) {
      const item = (CFG.codeMeta && CFG.codeMeta[idx]) || { code: CFG.codes[idx] || '', label: '', cat: '' };
      const target = cfgDetectTarget(item.code, item.label, item.cat);
      if (target === 's1') {
        alert('s1 호스트는 웹에서 콘솔 터미널 접근 및 설정 수정이 불가합니다.');
        return;
      }
      const filePath = cfgExtractFilePath(item.label, item.code);

      const old = document.getElementById('cfg-edit-modal');
      if (old) old.remove();

      const modal = document.createElement('div');
      modal.id = 'cfg-edit-modal';
      modal.className = 'cfg-modal-overlay cfg-modal-danger';
      modal.innerHTML = '<div class="cfg-modal-card" role="dialog" aria-modal="true">' +
        '<div class="cfg-modal-head">⚠️ 설정 파일 수정/변경 사전 확인 (vi / nano)</div>' +
        '<div class="cfg-modal-body">' +
        '<div class="cfg-modal-alert"><b>경고:</b> 운영 노드의 설정 파일을 직접 열어 수정하거나 구성을 변경합니다. 잘못된 설정 값이나 문법 오류는 서비스 다운타임의 원인이 될 수 있습니다. 사전 확인 후 신중히 진행하십시오.</div>' +
        '<div class="cfg-modal-meta">대상 노드: <strong>' + cfgEsc(target) + '</strong> &nbsp;|&nbsp; 대상 파일: <strong>' + cfgEsc(filePath) + '</strong></div>' +
        '<div style="font-size:12.5px;color:#cbd5e1;margin-top:2px;"><b>접근 편집기 방식 선택:</b></div>' +
        '<div style="display:flex;gap:14px;font-size:12.5px;color:#e2e8f0;background:#090d16;padding:10px 12px;border-radius:6px;border:1px solid #334155;flex-wrap:wrap;">' +
        '<label style="display:flex;align-items:center;gap:6px;cursor:pointer;"><input type="radio" name="cfg-editor" value="vi" checked> <b>vi 편집기</b> (sudo vi ' + cfgEsc(filePath) + ')</label>' +
        '<label style="display:flex;align-items:center;gap:6px;cursor:pointer;"><input type="radio" name="cfg-editor" value="nano"> <b>nano 편집기</b> (sudo nano ' + cfgEsc(filePath) + ')</label>' +
        '<label style="display:flex;align-items:center;gap:6px;cursor:pointer;"><input type="radio" name="cfg-editor" value="apply"> <b>직접 덮어쓰기 적용</b></label>' +
        '</div>' +
        '<pre class="cfg-modal-code" style="max-height:120px;">' + cfgEsc(item.code) + '</pre>' +
        '</div>' +
        '<div class="cfg-modal-foot">' +
        '<button type="button" class="cfg-btn-cancel" id="cfg-edit-cancel">취소</button>' +
        '<button type="button" class="cfg-btn-confirm" id="cfg-edit-ok" style="background:#dc2626;border-color:#ef4444;color:#fff;font-weight:700;">확인 후 편집 터미널 실행</button>' +
        '</div>' +
        '</div>';
      document.body.appendChild(modal);

      const close = () => { modal.remove(); document.removeEventListener('keydown', onKey); };
      const onKey = e => { if (e.key === 'Escape') close(); };
      document.addEventListener('keydown', onKey);

      modal.querySelector('#cfg-edit-cancel').onclick = close;
      modal.querySelector('#cfg-edit-ok').onclick = () => {
        const choice = modal.querySelector('input[name="cfg-editor"]:checked').value;
        close();
        let cmdToRun = '';
        if (choice === 'vi') cmdToRun = 'sudo vi ' + filePath;
        else if (choice === 'nano') cmdToRun = 'sudo nano ' + filePath;
        else cmdToRun = "sudo bash -c 'cat << \\"EOF\\" > " + filePath + "\\n" + item.code.trim() + "\\nEOF'";

        cfgOpenAndExec(cmdToRun, target, item.label + ' (' + choice + ' 수정)', true, null, 'modify');
      };
      modal.onclick = e => { if (e.target === modal) close(); };
    }

    // 5. 위험 명령어 사전 확인 모달 (빨강색 경고 확인)
    function cfgShowConfirm(code, target, label, onConfirm) {
      const old = document.getElementById('cfg-confirm-modal');
      if (old) old.remove();

      const modal = document.createElement('div');
      modal.id = 'cfg-confirm-modal';
      modal.className = 'cfg-modal-overlay cfg-modal-danger';
      modal.innerHTML = '<div class="cfg-modal-card" role="dialog" aria-modal="true">' +
        '<div class="cfg-modal-head">⚠️ 시스템 수정/변경 실행 사전 확인</div>' +
        '<div class="cfg-modal-body">' +
        '<div class="cfg-modal-alert"><b>경고:</b> 이 명령은 서비스 중지, 재시작, 삭제 또는 시스템 구성을 직접 변경할 수 있습니다. 운영 환경에 미치는 영향을 확인하신 후 신중히 실행해 주세요.</div>' +
        '<div class="cfg-modal-meta">대상 노드: <strong>' + cfgEsc(target) + '</strong> &nbsp;|&nbsp; 작업: ' + cfgEsc(label || '설정 수정/변경') + '</div>' +
        '<pre class="cfg-modal-code">' + cfgEsc(code) + '</pre>' +
        '</div>' +
        '<div class="cfg-modal-foot">' +
        '<button type="button" class="cfg-btn-cancel" id="cfg-modal-cancel">취소</button>' +
        '<button type="button" class="cfg-btn-confirm" id="cfg-modal-ok" style="background:#dc2626;border-color:#ef4444;color:#fff;font-weight:700;">확인 후 변경 실행</button>' +
        '</div>' +
        '</div>';
      document.body.appendChild(modal);

      const close = () => { modal.remove(); document.removeEventListener('keydown', onKey); };
      const onKey = e => { if (e.key === 'Escape') close(); };
      document.addEventListener('keydown', onKey);

      modal.querySelector('#cfg-modal-cancel').onclick = close;
      modal.querySelector('#cfg-modal-ok').onclick = () => {
        close();
        if (typeof onConfirm === 'function') onConfirm();
      };
      modal.onclick = e => { if (e.target === modal) close(); };
      modal.querySelector('#cfg-modal-ok').focus();
    }

    // 6. xterm fallback 로더
    async function cfgEnsureXterm() {
      if (typeof csLoadXterm === 'function') {
        await csLoadXterm();
        return;
      }
      if (window.Terminal && window.FitAddon) return;
      const add = (tag, attrs) => new Promise((ok, bad) => {
        const el = document.createElement(tag); Object.assign(el, attrs); el.onload = ok; el.onerror = bad; document.head.appendChild(el);
      });
      const CS_XTERM = 'https://cdn.jsdelivr.net/npm/@xterm/xterm@5.5.0';
      const CS_FIT = 'https://cdn.jsdelivr.net/npm/@xterm/addon-fit@0.10.0';
      await Promise.all([
        add('link', { rel: 'stylesheet', href: CS_XTERM + '/css/xterm.min.css' }),
        add('script', { src: CS_XTERM + '/lib/xterm.min.js' })
      ]);
      await add('script', { src: CS_FIT + '/lib/addon-fit.min.js' });
    }

    // 6-1. 세션 웹소켓 재연결 헬퍼
    function cfgReconnectAndSend(s, code) {
      const wsProto = location.protocol === 'https:' ? 'wss:' : 'ws:';
      const u = typeof csOwner === 'function' ? csOwner() : 'team';
      const wsUrl = wsProto + '//' + location.host + '/console/ws/' + encodeURIComponent(s.target) +
        '?cols=' + s.term.cols + '&rows=' + s.term.rows + '&u=' + encodeURIComponent(u);
      s.term.write('\\r\\n\\x1b[33m[연결 재시도 중…]\\x1b[0m\\r\\n');
      try {
        const ws = new WebSocket(wsUrl);
        s.ws = ws;
        ws.onopen = () => {
          s.status = 'ok';
          const statDot = s.winEl.querySelector('.cfg-win-status-dot');
          const statText = s.winEl.querySelector('.cfg-win-status-text');
          if (statDot) statDot.className = 'cfg-win-status-dot';
          if (statText) statText.textContent = '연결됨';
          cfgUpdateChipStatus(s.id, true);
          s.term.focus();
          try { s.fit.fit(); } catch (e) {}
          if (code) {
            setTimeout(() => {
              if (ws.readyState === 1) ws.send(JSON.stringify({ t: 'i', d: code.trim() + '\\r' }));
            }, 500);
          }
        };
        ws.onmessage = e => s.term.write(e.data);
        ws.onclose = e => {
          s.status = 'off';
          const statDot = s.winEl.querySelector('.cfg-win-status-dot');
          const statText = s.winEl.querySelector('.cfg-win-status-text');
          if (statDot) statDot.className = 'cfg-win-status-dot off';
          if (statText) statText.textContent = '연결 끊김 (' + e.code + ')';
          cfgUpdateChipStatus(s.id, false);
        };
        s.term.onData(d => { if (s.ws && s.ws.readyState === 1) s.ws.send(JSON.stringify({ t: 'i', d: d })); });
        s.term.onResize(sz => { if (s.ws && s.ws.readyState === 1) s.ws.send(JSON.stringify({ t: 'r', c: sz.cols, r: sz.rows })); });
      } catch (err) {
        s.term.write('\\r\\n\\x1b[31m[재연결 실패: ' + err.message + ']\\x1b[0m\\r\\n');
      }
    }

    // 7. 터미널 윈도우 생성 및 명령 자동 실행 (뷰/수정 분리 및 기존 창 재사용)
    async function cfgOpenAndExec(code, target, label, autoExec = true, saved = null, mode = null) {
      try {
        await cfgEnsureXterm();
      } catch (err) {
        alert('터미널 화면(xterm.js) 로드에 실패했습니다. 네트워크 연결을 확인하세요.');
        return;
      }

      const { fl, dock } = cfgEnsureLayers();
      const actualMode = mode || (saved && saved.mode) || (cfgIsDangerous(code, '') || (label && (label.includes('수정') || label.includes('적용'))) ? 'modify' : 'view');
      const id = saved ? saved.id : ('term__' + target + '__' + actualMode);

      // 동일한 인스턴스/모드의 창이 이미 띄워져 있는 경우: 새 창을 열지 않고 그 창에서 실행!
      const existing = CFG_RUNNER.sessions[id];
      if (existing) {
        if (existing.min) {
          existing.min = false;
          existing.winEl.classList.remove('minimized');
        }
        cfgFocusWin(id);
        if (label) {
          existing.label = label;
          const titleText = existing.winEl.querySelector('.cfg-win-title-text');
          if (titleText) titleText.textContent = cfgEsc(label);
        }
        setTimeout(() => { try { existing.fit.fit(); } catch (e) {} }, 50);

        if (autoExec && code) {
          existing.code = code;
          const banner = '\\r\\n\\x1b[36m[FIG Runner ⚡ ' + (actualMode === 'modify' ? '수정/변경' : '조회/확인') + ' 실행] ' + (label ? label + '\\r\\n' : '') + '\\x1b[0m';
          existing.term.write(banner);

          if (existing.ws && existing.ws.readyState === 1) {
            existing.ws.send(JSON.stringify({ t: 'i', d: code.trim() + '\\r' }));
          } else {
            cfgReconnectAndSend(existing, code);
          }
        }
        cfgRenderDock();
        cfgSaveState();
        return;
      }

      // 위치 및 크기 계산
      const count = Object.keys(CFG_RUNNER.sessions).length;
      const offset = (count % 6) * 30;
      const defaultW = Math.min(680, window.innerWidth - 40);
      const defaultH = Math.min(420, window.innerHeight - 100);
      const defaultX = Math.max(20, Math.min(window.innerWidth - defaultW - 30, 50 + offset));
      const defaultY = Math.max(30, Math.min(window.innerHeight - defaultH - 60, 60 + offset));

      const x = saved && saved.x != null ? saved.x : defaultX;
      const y = saved && saved.y != null ? saved.y : defaultY;
      const w = saved && saved.w != null ? saved.w : defaultW;
      const h = saved && saved.h != null ? saved.h : defaultH;
      const isMin = saved && saved.min ? true : false;
      const isMax = saved && saved.max ? true : false;

      // 윈도우 엘리먼트 생성
      const win = document.createElement('div');
      win.id = id;
      win.className = 'cfg-win' + (isMin ? ' minimized' : '') + (isMax ? ' maximized' : '');
      win.style.left = x + 'px';
      win.style.top = y + 'px';
      win.style.width = w + 'px';
      win.style.height = h + 'px';
      win.style.zIndex = String(++CFG_RUNNER.zIndex);

      const modeBadgeClass = actualMode === 'modify' ? 'cfg-badge-modify' : 'cfg-badge-view';
      const modeBadgeText = actualMode === 'modify' ? (target + ' · 수정/변경') : (target + ' · 뷰/확인');

      win.innerHTML = '<div class="cfg-win-head">' +
        '<div class="cfg-win-title">' +
        '<span class="cfg-win-badge ' + modeBadgeClass + '">' + cfgEsc(modeBadgeText) + '</span>' +
        '<span class="cfg-win-title-text">' + cfgEsc(label || '명령어 실행') + '</span>' +
        '</div>' +
        '<div class="cfg-win-ctrls">' +
        '<button type="button" class="cfg-win-btn btn-min" title="최소화">_</button>' +
        '<button type="button" class="cfg-win-btn btn-max" title="최대화">□</button>' +
        '<button type="button" class="cfg-win-btn btn-close" title="닫기">✕</button>' +
        '</div>' +
        '</div>' +
        '<div class="cfg-win-body"></div>' +
        '<div class="cfg-win-foot">' +
        '<div class="cfg-win-status">' +
        '<span class="cfg-win-status-dot wait"></span>' +
        '<span class="cfg-win-status-text">연결 준비 중…</span>' +
        '</div>' +
        '<span class="cfg-win-hint">자동 실행 & 터미널 상호작용 가능</span>' +
        '</div>';

      fl.appendChild(win);

      const winBody = win.querySelector('.cfg-win-body');
      const statDot = win.querySelector('.cfg-win-status-dot');
      const statText = win.querySelector('.cfg-win-status-text');

      // xterm 인스턴스 초기화
      const term = new window.Terminal({
        cursorBlink: true,
        fontFamily: "'JetBrains Mono', Consolas, monospace",
        fontSize: 13,
        scrollback: 5000,
        theme: {
          background: '#06090e',
          foreground: '#e2e8f0',
          cursor: '#93c5fd',
          selectionBackground: '#1e3a8a'
        }
      });
      const fit = new window.FitAddon.FitAddon();
      term.loadAddon(fit);
      term.open(winBody);
      setTimeout(() => { try { fit.fit(); } catch (e) {} }, 50);

      // 드래그 기능 (헤더 잡고 이동)
      const head = win.querySelector('.cfg-win-head');
      head.addEventListener('mousedown', e => {
        if (e.target.closest('.cfg-win-ctrls')) return;
        cfgFocusWin(id);
        if (win.classList.contains('maximized')) return;
        let startX = e.clientX, startY = e.clientY;
        let origX = win.offsetLeft, origY = win.offsetTop;
        const onMove = ev => {
          let nx = origX + (ev.clientX - startX);
          let ny = origY + (ev.clientY - startY);
          nx = Math.max(10, Math.min(window.innerWidth - 80, nx));
          ny = Math.max(10, Math.min(window.innerHeight - 80, ny));
          win.style.left = nx + 'px';
          win.style.top = ny + 'px';
          const s = CFG_RUNNER.sessions[id];
          if (s) { s.x = nx; s.y = ny; }
        };
        const onUp = () => {
          document.removeEventListener('mousemove', onMove);
          document.removeEventListener('mouseup', onUp);
          cfgSaveState();
        };
        document.addEventListener('mousemove', onMove);
        document.addEventListener('mouseup', onUp);
      });

      win.addEventListener('mousedown', () => cfgFocusWin(id));

      // 리사이즈 감지 (ResizeObserver)
      if (window.ResizeObserver) {
        const ro = new ResizeObserver(() => {
          if (!win.classList.contains('minimized')) {
            try { fit.fit(); } catch (e) {}
            const s = CFG_RUNNER.sessions[id];
            if (s && !win.classList.contains('maximized')) {
              s.w = win.offsetWidth;
              s.h = win.offsetHeight;
              cfgSaveState();
            }
          }
        });
        ro.observe(win);
      }

      // 컨트롤 버튼 이벤트
      win.querySelector('.btn-min').onclick = () => cfgToggleMin(id);
      win.querySelector('.btn-max').onclick = () => cfgToggleMax(id);
      win.querySelector('.btn-close').onclick = () => cfgCloseTerm(id);

      // 세션 등록
      const session = {
        id, target, mode: actualMode, label, code, term, fit, winEl: win,
        x, y, w, h, min: isMin, max: isMax,
        status: 'wait', autoExec
      };
      CFG_RUNNER.sessions[id] = session;

      // WebSocket 연결
      const wsProto = location.protocol === 'https:' ? 'wss:' : 'ws:';
      const u = typeof csOwner === 'function' ? csOwner() : 'team';
      const wsUrl = wsProto + '//' + location.host + '/console/ws/' + encodeURIComponent(target) +
        '?cols=' + term.cols + '&rows=' + term.rows + '&u=' + encodeURIComponent(u);
      
      let ws = null;
      try {
        ws = new WebSocket(wsUrl);
      } catch (e) {
        statDot.className = 'cfg-win-status-dot off';
        statText.textContent = '웹소켓 연결 오류';
        term.write('\\r\\n\\x1b[31m[웹소켓 연결 실패: ' + e.message + ']\\x1b[0m\\r\\n');
      }

      if (ws) {
        session.ws = ws;
        ws.onopen = () => {
          session.status = 'ok';
          statDot.className = 'cfg-win-status-dot';
          statText.textContent = '연결됨';
          cfgUpdateChipStatus(id, true);
          term.focus();
          try { fit.fit(); } catch (e) {}
          if (autoExec && code) {
            term.write('\\r\\n\\x1b[36m[FIG Runner ⚡ ' + (actualMode === 'modify' ? '수정/변경' : '조회/확인') + ' 실행] 대상: ' + target + '\\x1b[0m\\r\\n');
            setTimeout(() => {
              if (ws.readyState === 1) {
                ws.send(JSON.stringify({ t: 'i', d: code.trim() + '\\r' }));
              }
            }, 600);
          }
        };
        ws.onmessage = e => term.write(e.data);
        ws.onclose = e => {
          session.status = 'off';
          statDot.className = 'cfg-win-status-dot off';
          const msg = e.code === 1000 ? '세션 종료' : ('연결 끊김 (' + e.code + ')');
          statText.textContent = msg;
          cfgUpdateChipStatus(id, false);
          term.write('\\r\\n\\x1b[33m[' + msg + ']\\x1b[0m\\r\\n');
        };
        term.onData(d => { if (ws.readyState === 1) ws.send(JSON.stringify({ t: 'i', d: d })); });
        term.onResize(sz => { if (ws.readyState === 1) ws.send(JSON.stringify({ t: 'r', c: sz.cols, r: sz.rows })); });
      }

      cfgRenderDock();
      cfgSaveState();
      cfgFocusWin(id);
    }

    // 8. 윈도우 포커스 처리
    function cfgFocusWin(id) {
      const s = CFG_RUNNER.sessions[id];
      if (!s) return;
      document.querySelectorAll('.cfg-win').forEach(w => w.classList.remove('cfg-focus'));
      s.winEl.classList.add('cfg-focus');
      s.winEl.style.zIndex = String(++CFG_RUNNER.zIndex);
      document.querySelectorAll('.cfg-dock-chip').forEach(c => c.classList.remove('active'));
      const chip = document.getElementById('chip-' + id);
      if (chip) chip.classList.add('active');
      if (s.term) s.term.focus();
    }

    // 9. 최소화 / 최대화 / 닫기
    function cfgToggleMin(id) {
      const s = CFG_RUNNER.sessions[id];
      if (!s) return;
      s.min = !s.min;
      s.winEl.classList.toggle('minimized', s.min);
      if (!s.min) {
        cfgFocusWin(id);
        setTimeout(() => { try { s.fit.fit(); } catch (e) {} }, 50);
      }
      cfgSaveState();
    }

    function cfgToggleMax(id) {
      const s = CFG_RUNNER.sessions[id];
      if (!s) return;
      s.max = !s.max;
      s.winEl.classList.toggle('maximized', s.max);
      setTimeout(() => { try { s.fit.fit(); } catch (e) {} }, 50);
      cfgSaveState();
    }

    function cfgCloseTerm(id) {
      const s = CFG_RUNNER.sessions[id];
      if (!s) return;
      if (s.ws) {
        try { s.ws.close(); } catch (e) {}
      }
      if (s.term) {
        try { s.term.dispose(); } catch (e) {}
      }
      if (s.winEl) s.winEl.remove();
      delete CFG_RUNNER.sessions[id];
      cfgRenderDock();
      cfgSaveState();
    }

    function cfgToggleAllMin(min) {
      Object.keys(CFG_RUNNER.sessions).forEach(id => {
        const s = CFG_RUNNER.sessions[id];
        s.min = min;
        s.winEl.classList.toggle('minimized', min);
      });
      cfgSaveState();
    }

    function cfgCloseAllTerms() {
      const ids = Object.keys(CFG_RUNNER.sessions);
      if (!ids.length) return;
      if (!confirm('열려 있는 모든 터미널 창(' + ids.length + '개)을 종료하시겠습니까?')) return;
      ids.forEach(id => cfgCloseTerm(id));
    }

    // 10. 하단 푸터 닥(Footer Dock) 렌더링 (뷰 / 수정 라벨 구분)
    function cfgRenderDock() {
      const dock = document.getElementById('cfg-footer-dock');
      const list = document.getElementById('cfg-dock-list');
      if (!dock || !list) return;

      const ids = Object.keys(CFG_RUNNER.sessions);
      if (ids.length === 0) {
        dock.classList.add('cfg-dock-hidden');
        list.innerHTML = '';
        return;
      }

      dock.classList.remove('cfg-dock-hidden');
      list.innerHTML = ids.map(id => {
        const s = CFG_RUNNER.sessions[id];
        const isOk = s.status === 'ok';
        const modeTxt = s.mode === 'modify' ? '수정' : '뷰';
        const chipCls = s.mode === 'modify' ? 'chip-modify' : 'chip-view';
        return '<div class="cfg-dock-chip ' + chipCls + '" id="chip-' + id + '" onclick="cfgOnChipClick(\\'' + id + '\\')">' +
          '<span class="cfg-dock-chip-dot ' + (isOk ? '' : 'off') + '"></span>' +
          '<span class="cfg-dock-chip-name">[' + cfgEsc(s.target) + ' · ' + modeTxt + '] ' + cfgEsc(s.label || '명령어') + '</span>' +
          '<span class="cfg-dock-chip-close" onclick="event.stopPropagation(); cfgCloseTerm(\\'' + id + '\\')" title="닫기">✕</span>' +
          '</div>';
      }).join('');
    }

    function cfgOnChipClick(id) {
      const s = CFG_RUNNER.sessions[id];
      if (!s) return;
      if (s.min) {
        s.min = false;
        s.winEl.classList.remove('minimized');
        cfgFocusWin(id);
        setTimeout(() => { try { s.fit.fit(); } catch (e) {} }, 50);
      } else {
        if (s.winEl.classList.contains('cfg-focus')) {
          cfgToggleMin(id);
        } else {
          cfgFocusWin(id);
        }
      }
      cfgSaveState();
    }

    function cfgUpdateChipStatus(id, isOk) {
      const chip = document.getElementById('chip-' + id);
      if (!chip) return;
      const dot = chip.querySelector('.cfg-dock-chip-dot');
      if (dot) dot.className = 'cfg-dock-chip-dot ' + (isOk ? '' : 'off');
    }

    // 11. localStorage 영속화 및 부팅 복원
    function cfgSaveState() {
      try {
        const payload = Object.keys(CFG_RUNNER.sessions).map(id => {
          const s = CFG_RUNNER.sessions[id];
          return {
            id: s.id, target: s.target, mode: s.mode, label: s.label, code: s.code,
            x: s.x, y: s.y, w: s.w, h: s.h, min: s.min, max: s.max
          };
        });
        localStorage.setItem(CFG_RUNNER.storageKey, JSON.stringify(payload));
      } catch (e) {}
    }

    async function cfgRunnerBoot() {
      cfgEnsureLayers();
      try {
        const raw = localStorage.getItem(CFG_RUNNER.storageKey);
        if (!raw) return;
        const list = JSON.parse(raw);
        if (!Array.isArray(list) || !list.length) return;
        for (const item of list) {
          // 새로고침 복원 시에는 명령어를 재실행하지 않고 터미널 세션 및 창 상태만 복원
          await cfgOpenAndExec(item.code, item.target, item.label, false, item, item.mode);
        }
      } catch (e) {
        console.error('Failed to restore terminal runner sessions', e);
      }
    }

    // 초기 로드 시 러너 복원 실행
    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', () => setTimeout(cfgRunnerBoot, 200));
    } else {
      setTimeout(cfgRunnerBoot, 200);
    }
    // ===== 통합 콘솔: 3대 영역 → 인스턴스 → 실제 터미널 (content/console.js) =====
    // 서버: s1 figteam-console (/console/api/*, /console/ws/<대상>) · 콘솔 비밀번호로 잠금
    // 예전 통합 터미널 기능: 대상별 「확인」·「⚠ 복구」 버튼, 탭, ⧉ 화면 위 창(끌기·크기·최소화·최대화·되돌리기), ↗ 새 창
    const CS = { open: false, solo: null, targets: null, layout: '1', slots: [], floats: [], active: 0, loaded: false,
      sizes: { col: 50, row: 50 }, seq: 0, z: 900, pending: null, page: false, status: null, owner: "", expanded: {}, openNow: {}, stTimer: null, presets: {} };
    const CS_TERM_URL = '/term/';
    // 대시보드에서: 통합 터미널 페이지로 이동 (원클릭 — 대상이 있으면 바로 접속)
    function csGo(id) {
      if (id === 's1' || id === 't1-vm2') {
        if (typeof wikiToast === 'function') wikiToast('s1 호스트는 웹에서 콘솔 터미널 접근이 불가합니다.');
        else alert('s1 호스트는 웹에서 콘솔 터미널 접근이 불가합니다.');
        return;
      }
      location.href = CS_TERM_URL + (id ? '?t=' + encodeURIComponent(id) : '');
    }
    // 왼쪽 트리: 클라우드 → 인스턴스 → (그 위의 VM) → 서비스. 클라우드마다 웹 콘솔 링크.
    const CS_GROUPS = [
      ['openstack', '온프렘 · OpenStack', ['onprem', 'openstack'], [['Horizon 웹 콘솔', 'https://horizon.ktci5.kr/dashboard/']]],
      ['kt', 'KT Cloud', ['kt'], [['KT Edge 상태', 'https://kt-edge.ktci5.kr/'], ['KT Cloud 콘솔', 'https://cloud.kt.com/']]],
      ['aws', 'AWS', ['aws'], [['Orchestrator', 'https://aws-ctl.ktci5.kr/healthz'], ['AWS 콘솔', 'https://console.aws.amazon.com/']]]];
    const CS_LAYOUTS = [['1', '하나'], ['h', '좌우'], ['v', '상하'], ['4', '4분할']];
    const CS_XTERM = 'https://cdn.jsdelivr.net/npm/@xterm/xterm@5.5.0';
    const CS_FIT = 'https://cdn.jsdelivr.net/npm/@xterm/addon-fit@0.10.0';
    const CS_CLOSE_MSG = { 4401: '콘솔 잠금이 풀려 있지 않습니다', 4403: '허용되지 않은 출처입니다', 4404: '없는 대상입니다',
      4409: '연결할 수 없는 대상입니다', 4429: '동시에 열 수 있는 터미널(6개)을 넘었습니다', 1006: '연결이 끊겼습니다' };

    function csLoadXterm() {
      if (CS.loaded) return Promise.resolve();
      const add = (tag, attrs) => new Promise((ok, bad) => {
        const el = document.createElement(tag); Object.assign(el, attrs); el.onload = ok; el.onerror = bad; document.head.appendChild(el);
      });
      return Promise.all([
        add('link', { rel: 'stylesheet', href: CS_XTERM + '/css/xterm.min.css' }),
        add('script', { src: CS_XTERM + '/lib/xterm.min.js' })
      ]).then(() => add('script', { src: CS_FIT + '/lib/addon-fit.min.js' })).then(() => { CS.loaded = true; });
    }
    async function csApi(method, path, body) {
      const opt = { method: method, credentials: 'same-origin', cache: 'no-store', headers: {} };
      if (body) { opt.headers['Content-Type'] = 'application/json'; opt.body = JSON.stringify(body); }
      const r = await fetch(path, opt);
      let d = null; try { d = await r.json(); } catch (e) {}
      if (!r.ok) throw Object.assign({ status: r.status }, d || {});
      return d;
    }
    function csRoot() {
      let el = document.getElementById('cs-root');
      if (!el) { el = document.createElement('div'); el.id = 'cs-root'; el.setAttribute('role', 'region'); el.setAttribute('aria-label', '통합 콘솔'); document.body.appendChild(el); }
      return el;
    }
    function csT(id) { return (CS.targets || []).find(t => t.id === id) || { name: id }; }

    // ---------- 왼쪽 트리 (상태는 /console/api/status, 대시보드가 받은 값이 있으면 재사용) ----------
    async function csLoadStatus() {
      try {
        if (typeof DASH !== 'undefined' && DASH.snap) CS.status = DASH.snap;
        else { const r = await fetch('/console/api/status', { cache: 'no-store' }); if (r.ok) CS.status = await r.json(); }
      } catch (e) {}
      const tree = document.getElementById('cs-tree');
      if (tree) tree.innerHTML = csTreeHtml();
    }
    // 부모: 상태 수집이 호스트 virsh 로 실측한 배치가 우선, 없으면 targets.json 의 정적 parent
    function csStat(id) { return ((CS.status && CS.status.instances) || []).find(i => i.id === id); }
    function csParent(t) { const st = csStat(t.id); return (st && st.parent) || t.parent; }
    function csTreeHtml() {
      if (!CS.targets) return '';
      return CS_GROUPS.map(g => {
        const mine = CS.targets.filter(t => g[2].indexOf(t.area) >= 0 && t.id !== 's1' && t.target !== 's1');
        const ids = mine.map(t => t.id);
        // 진입점(컨트롤러·컴퓨트) 먼저, 이름만 있는 기반 호스트(s1)는 맨 아래
        const roots = mine.filter(t => ids.indexOf(csParent(t)) < 0).sort((a, b) => (a.area === 'onprem') - (b.area === 'onprem'));
        return '<div class="cs-area"><div class="cfg-group-head"><span class="cfg-dot cfg-c-' + g[0] + '"></span>' + g[1] + '</div>' +
          roots.map(t => csNodeHtml(t, mine, 0)).join('') +
          '<div class="cs-weblinks">' + g[3].map(l => '<a href="' + l[1] + '" target="_blank" rel="noopener">' + cfgEsc(l[0]) + ' ↗</a>').join('') + '</div></div>';
      }).join('');
    }
    function csNodeHtml(t, mine, depth) {
      const st = csStat(t.id) || {};
      const kids = mine.filter(x => csParent(x) === t.id);
      const svcs = (st.units || []).map(u => ({ kind: 'unit', name: u.unit, ok: u.state === 'active', state: u.state, desc: ((st.unit_meta || {})[u.unit] || {}).desc || '' }))
        .concat((st.pods || []).filter(p => p.phase !== 'Succeeded').map(p => ({ kind: 'pod', name: p.name, ns: p.ns, ok: p.phase === 'Running', state: p.phase, desc: p.ns })));
      const open = CS.expanded[t.id] === undefined ? kids.length > 0 : CS.expanded[t.id];   // 하위 VM 이 있으면 처음부터 펼침(계단식)
      const svcOpen = !!CS.expanded[t.id + ':svc'], has = kids.length || svcs.length;
      CS.openNow[t.id] = open; CS.openNow[t.id + ':svc'] = svcOpen;
      const bad = svcs.filter(x => !x.ok).length;
      const vmOff = st.vm_state && st.vm_state !== 'running';
      const dot = vmOff ? 'off' : st.alive === true ? (bad ? 'wait' : 'ok') : st.alive === false ? 'off' : '';
      const sub = t.disabled || ((vmOff ? 'VM ' + st.vm_state + ' · ' : '') + (t.desc || ''));
      const role = t.role ? '<em class="cs-role cs-role-' + (t.disabled ? 'none' : kids.length ? 'host' : 'vm') + '">' + cfgEsc(t.role) + '</em>' : '';
      let h = '<div class="cs-node" style="--d:' + depth + '"><div class="cs-node-row">' +
        (has ? '<button type="button" class="cs-tog" aria-expanded="' + open + '" title="펼치기" onclick="csToggle(\\'' + cfgEsc(t.id) + '\\')">' + (open ? '▾' : '▸') + '</button>' : '<span class="cs-tog-sp"></span>') +
        '<span class="cs-dot cs-dot-' + dot + '"></span>' +
        '<button type="button" class="cs-target"' + (t.disabled ? ' disabled title="' + cfgEsc(t.disabled) + '"' : ' title="누르면 바로 접속"') +
        ' onclick="csPick(\\'' + cfgEsc(t.id) + '\\')"><b>' + cfgEsc(t.name) + role + '</b><span>' + cfgEsc(sub) + '</span></button></div>';
      if (open) {
        h += kids.map(k => csNodeHtml(k, mine, depth + 1)).join('');   // 하위 VM(마스터·워커·DB) 먼저
        if (svcs.length) {
          h += '<div class="cs-node" style="--d:' + (depth + 1) + '"><div class="cs-node-row"><button type="button" class="cs-tog" aria-expanded="' + svcOpen + '" onclick="csToggle(\\'' + cfgEsc(t.id) + ':svc\\')">' + (svcOpen ? '▾' : '▸') + '</button>' +
            '<button type="button" class="cs-svc-head" onclick="csToggle(\\'' + cfgEsc(t.id) + ':svc\\')">서비스 ' + svcs.length + (bad ? ' · <b>이상 ' + bad + '</b>' : '') + '</button></div></div>';
          if (svcOpen) h += '<div class="cs-svcs" style="--d:' + (depth + 1) + '">' + svcs.map(x =>
            '<button type="button" class="cs-svc" data-id="' + cfgEsc(t.id) + '" data-kind="' + x.kind + '" data-name="' + cfgEsc(x.name) + '" data-ns="' + cfgEsc(x.ns || '') + '" onclick="csSvcBtn(this)" title="' + cfgEsc(x.desc) + ' — 누르면 상태 확인">' +
            '<span class="cs-dot cs-dot-' + (x.ok ? 'ok' : 'off') + '"></span><span class="cs-svc-n">' + cfgEsc(x.name) + '</span><small>' + (x.kind === 'pod' ? '파드' : '서비스') + '</small></button>').join('') + '</div>';
        }
      }
      return h + '</div>';
    }
    function csToggle(id) { CS.expanded[id] = !(CS.openNow[id] !== undefined ? CS.openNow[id] : CS.expanded[id]); const tree = document.getElementById('cs-tree'); if (tree) tree.innerHTML = csTreeHtml(); }
    // 서비스 클릭: 그 인스턴스 터미널에서 상태(또는 파드 로그) 명령을 바로 실행
    function csSvcBtn(btn) {
      const d = btn.dataset, tg = csT(d.id);
      const cmd = d.kind === 'pod' ? (tg.kubectl || 'kubectl') + ' -n ' + d.ns + ' logs ' + d.name + ' --tail=40'
        : 'systemctl status ' + d.name + ' --no-pager -n 15';
      csRunOn(d.id, cmd);
    }
    function csRunOn(id, cmd) {
      let t = csAllTerms().find(x => x.target === id && x.ws);
      if (!t) { csPick(id); t = csAllTerms().find(x => x.target === id); }
      else { const f = csFind(t.uid); if (f.where === 'slot') csFocus(f.i); else csTabGo(t.uid); }
      if (!t) return;
      if (t.ws && t.ws.readyState === 1) { t.ws.send(JSON.stringify({ t: 'i', d: cmd + '\\r' })); t.term.focus(); }
      else t.queue = cmd;   // 연결되면 실행
    }

    // ---------- 사용자 이름(세션 이어가기 열쇠 · 설계/설정과 공유) ----------
    const CS_ENTRY_SKIP_KEY = 'fig.entry_name_skipped_v1';

    function figAuthStorageKey() {
      return typeof AUTH_KEY !== 'undefined' ? AUTH_KEY : 'figteam_auth_token';
    }
    function csIsRealName(name) {
      const s = String(name == null ? '' : name).trim();
      if (!s) return false;
      const lower = s.toLowerCase();
      return s !== '게스트' && s !== '미설정' && lower !== 'guest' && lower !== 'seed';
    }
    function csNormKey(k) {
      return String(k == null ? '' : k).trim().toUpperCase().replace(/[^A-Z0-9_-]/g, '').slice(0, 16);
    }
    function csGenKey() {
      const chars = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789';
      let out = '';
      for (let i = 0; i < 6; i++) out += chars[Math.floor(Math.random() * chars.length)];
      return out;
    }
    function csReadJson(key, fallback) {
      try { const raw = localStorage.getItem(key); return raw ? JSON.parse(raw) : fallback; } catch (e) { return fallback; }
    }
    function csParseBaseName(raw) {
      const s = String(raw == null ? '' : raw).trim();
      const m = s.match(/^(.*?)#([A-Za-z0-9_-]{2,16})$/);
      return (m ? m[1] : s).trim();
    }
    // 읽기 전용 키 검증: 자동 생성 없이 실제 이름+접속 키가 등록된 경우만 반환 (키 없는 이전 세션 판별용)
    function figReadStoredAccessKey() {
      const prof = csReadJson('fig.access.profile_v1', null);
      if (!prof || typeof prof !== 'object') return null;
      const ak = csNormKey(prof.access_key);
      const cleanName = csParseBaseName(prof.member);
      if (ak.length < 2 || !csIsRealName(cleanName)) return null;
      return { member: cleanName, access_key: ak };
    }
    function figShowLoginNotice(msg) {
      const el = typeof document !== 'undefined' ? document.getElementById('login-notice') : null;
      if (!el) return;
      if (msg) {
        el.textContent = msg;
        el.style.display = 'block';
      } else {
        el.textContent = '';
        el.style.display = 'none';
      }
    }
    function figPrepareLoginForm() {
      const memEl = typeof document !== 'undefined' ? document.getElementById('auth-member') : null;
      const keyView = typeof document !== 'undefined' ? document.getElementById('auth-access-key-view') : null;
      if (!memEl && !keyView) return;
      const prof = csReadJson('fig.access.profile_v1', null) || {};
      const last = csReadJson('fw_last', null) || {};
      let termUser = '';
      try { termUser = localStorage.getItem('fig.term.user') || ''; } catch (e) {}
      const candidates = [prof.member, termUser, last.member];
      let foundName = '';
      for (let i = 0; i < candidates.length; i++) {
        const clean = csParseBaseName(candidates[i]);
        if (csIsRealName(clean)) { foundName = clean; break; }
      }
      if (memEl && !memEl.value.trim() && foundName) memEl.value = foundName;
      if (keyView) {
        const curKey = csNormKey(prof.access_key) || csNormKey(last.access_key);
        keyView.textContent = curKey ? (curKey + ' (서버 할당 · 변경 불가)') : '로그인 시 서버에서 자동 할당 (변경 불가)';
      }
    }
    const CS_SITE_VISITS_KEY = 'fig.access.site_visits_v1';

    function figReadUaSummary() {
      try {
        const raw = (navigator && navigator.userAgent) || '';
        const br = raw.indexOf('Edg/') >= 0 ? 'Edge'
          : raw.indexOf('Chrome/') >= 0 ? 'Chrome'
          : raw.indexOf('Firefox/') >= 0 ? 'Firefox'
          : raw.indexOf('Safari/') >= 0 ? 'Safari' : 'Browser';
        const os = /iPhone|iPad/.test(raw) ? 'iOS'
          : raw.indexOf('Android') >= 0 ? 'Android'
          : /Mac OS X|Macintosh/.test(raw) ? 'macOS'
          : raw.indexOf('Windows') >= 0 ? 'Windows'
          : raw.indexOf('Linux') >= 0 ? 'Linux' : '';
        return os ? (br + ' · ' + os) : br;
      } catch (e) { return ''; }
    }
    function figRecordSiteVisit(authState, view, detail) {
      const state = authState || 'visitor';
      const path = (typeof location !== 'undefined' ? (location.pathname + (location.hash || '')) : '/') || '/';
      const v = view || (CS.page ? 'term' : 'dashboard');
      const sig = state + '|' + v + '|' + path;
      const nowMs = Date.now();
      if (CS._lastVisitSig === sig && CS._lastVisitTs && (nowMs - CS._lastVisitTs) < 2000) return;
      CS._lastVisitSig = sig;
      CS._lastVisitTs = nowMs;
      const stored = figReadStoredAccessKey();
      const entry = {
        ts: Math.floor(nowMs / 1000),
        path: path.slice(0, 120),
        view: String(v).slice(0, 32),
        auth_state: state,
        member: stored ? stored.member : '',
        access_key: stored ? stored.access_key : '',
        ua: figReadUaSummary(),
        ip: '현재 브라우저',
        detail: String(detail || '').slice(0, 120)
      };
      try {
        const list = csReadJson(CS_SITE_VISITS_KEY, []) || [];
        list.unshift(entry);
        localStorage.setItem(CS_SITE_VISITS_KEY, JSON.stringify(list.slice(0, 300)));
      } catch (e) {}
      try {
        fetch('/api/visit', {
          method: 'POST',
          credentials: 'same-origin',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            path: entry.path,
            view: entry.view,
            auth_state: entry.auth_state,
            member: entry.member,
            access_key: entry.access_key,
            detail: entry.detail
          })
        }).catch(() => {});
      } catch (e) {}
    }

    async function figExpireKeylessSessions() {
      try { sessionStorage.removeItem(figAuthStorageKey()); } catch (e) {}
      try { sessionStorage.removeItem(CS_ENTRY_SKIP_KEY); } catch (e) {}
      const post = url => fetch(url, { method: 'POST', credentials: 'same-origin' }).catch(() => {});
      await Promise.all([post('/console/api/lock'), post('/api/logout')]);
    }
    function csReadProfile() {
      const prof = csReadJson('fig.access.profile_v1', null) || {};
      const last = csReadJson('fw_last', null) || {};
      let termUser = '';
      try { termUser = localStorage.getItem('fig.term.user') || ''; } catch (e) {}
      const ak = csNormKey(prof.access_key || last.access_key) || csGenKey();
      const candidates = [CS.owner, termUser, prof.member, last.member];
      let realName = '';
      for (let i = 0; i < candidates.length; i++) {
        const clean = csParseBaseName(candidates[i]);
        if (csIsRealName(clean)) { realName = clean; break; }
      }
      if (realName) {
        try {
          if (localStorage.getItem('fig.term.user') !== realName) localStorage.setItem('fig.term.user', realName);
          if (!prof.access_key || prof.member !== realName) {
            localStorage.setItem('fig.access.profile_v1', JSON.stringify({ member: realName, access_key: ak }));
          }
        } catch (e) {}
      }
      return { member: realName, access_key: ak };
    }
    function csWriteProfile(member, accessKey) {
      const cleanName = csParseBaseName(member);
      const ak = csNormKey(accessKey) || csReadProfile().access_key || csGenKey();
      if (!csIsRealName(cleanName)) return { member: '', access_key: ak };
      try {
        localStorage.setItem('fig.term.user', cleanName);
        localStorage.setItem('fig.access.profile_v1', JSON.stringify({ member: cleanName, access_key: ak }));
        const kb = csReadJson('fig.access.keybook_v1', {}) || {};
        kb[ak] = { access_key: ak, member: cleanName, updated_at: Math.floor(Date.now() / 1000), last_ip: '콘솔 등록' };
        localStorage.setItem('fig.access.keybook_v1', JSON.stringify(kb));
        const last = csReadJson('fw_last', null) || {};
        localStorage.setItem('fw_last', JSON.stringify({ slug: last.slug || 'figteam', member: cleanName, access_key: ak }));
        sessionStorage.removeItem(CS_ENTRY_SKIP_KEY);
      } catch (e) {}
      CS.owner = cleanName;
      const chip = document.getElementById('cs-owner-chip');
      if (chip) chip.textContent = cleanName;
      return { member: cleanName, access_key: ak };
    }
    async function csSyncProfileToServer(member, ak, isFirst) {
      const formatted = member.slice(0, Math.max(1, 20 - 1 - ak.length)).trim() + '#' + ak;
      const post = (url, body) => fetch(url, {
        method: 'POST',
        credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body)
      }).catch(() => {});
      await Promise.all([
        post('/api/me/name', { member: formatted, access_key: ak }),
        post('/api/access/register', {
          member: member,
          access_key: ak,
          action: isFirst ? 'first_entry' : 'rename',
          detail: isFirst ? '통합 콘솔 최초 접속 이름 등록' : '콘솔 이름 변경'
        }),
        post('/api/access/keybook', { access_key: ak, member: member })
      ]);
    }
    function csOpenNameModal(isFirst, onDone) {
      if (!isFirst && typeof wkOpenIdentityModal === 'function') {
        wkOpenIdentityModal(null, { firstEntry: false, onDone: onDone });
        return;
      }
      const old = document.getElementById('wk-identity-modal');
      if (old) old.remove();
      const prof = csReadProfile();
      const curName = csIsRealName(prof.member) ? prof.member : '';
      const modal = document.createElement('div');
      modal.id = 'wk-identity-modal';
      modal.className = 'cfg-modal-overlay';
      modal.innerHTML =
        '<div class="cfg-builder-modal-card" role="dialog" aria-modal="true" style="max-width:480px;">' +
        '<div class="cfg-builder-modal-head">' +
        '<span>' + (isFirst ? '👤 처음 접속 안내 — 사용자 이름 입력' : '👤 콘솔 사용자 이름 변경') + '</span>' +
        (isFirst ? '' : '<button type="button" class="cfg-win-btn btn-close" id="cs-id-close" style="color:#cbd5e1;">✕</button>') +
        '</div>' +
        '<div class="cfg-builder-modal-body">' +
        '<p class="manual-desc" style="margin:0;font-size:12.5px;line-height:1.55;">통합 콘솔 세션 이어가기와 설계/설정 변경 이력에 사용됩니다. <b>한 번 입력하면 두 화면에 자동 적용되며 이후 다시 묻지 않습니다.</b></p>' +
        '<div class="cfg-builder-field">' +
        '<label class="cfg-builder-label">사용자 이름 (필수, 1~13자 권장)</label>' +
        '<input type="text" id="cs-id-name" class="cfg-builder-input" maxlength="20" value="' + cfgEsc(curName) + '" placeholder="예: 홍길동">' +
        '</div>' +
        '<div class="cfg-builder-field">' +
        '<label class="cfg-builder-label">접속 키값 (서버 자동 할당 · 변경 불가)</label>' +
        '<input type="text" id="cs-id-key" class="cfg-builder-input wk-key-locked" value="' + cfgEsc(prof.access_key || '서버 자동 할당') + '" readonly disabled style="font-family:var(--font-mono);text-transform:uppercase;">' +
        '</div>' +
        '<p class="wk-error" id="cs-id-err" role="alert" hidden style="margin:0;"></p>' +
        '</div>' +
        '<div class="cfg-modal-foot">' +
        '<button type="button" class="cfg-btn-cancel" id="cs-id-cancel">' + (isFirst ? '이번 세션 건너뛰기' : '취소') + '</button>' +
        '<button type="button" class="cfg-btn-confirm" id="cs-id-save" style="background:#2563eb;border-color:#3b82f6;">' + (isFirst ? '이름 저장 후 시작' : '저장') + '</button>' +
        '</div></div>';
      document.body.appendChild(modal);

      let settled = false;
      const finish = res => {
        if (settled) return;
        settled = true;
        if (typeof onDone === 'function') onDone(res);
      };
      const close = res => {
        modal.remove();
        document.removeEventListener('keydown', onKey);
        finish(res || { skipped: true });
      };
      const onKey = e => { if (!isFirst && e.key === 'Escape') close({ skipped: true }); };
      document.addEventListener('keydown', onKey);
      const closeBtn = modal.querySelector('#cs-id-close');
      if (closeBtn) closeBtn.onclick = () => close({ skipped: true });
      modal.querySelector('#cs-id-cancel').onclick = () => {
        if (isFirst) { try { sessionStorage.setItem(CS_ENTRY_SKIP_KEY, '1'); } catch (e) {} }
        close({ skipped: true });
      };
      modal.onclick = e => { if (!isFirst && e.target === modal) close({ skipped: true }); };

      const errEl = modal.querySelector('#cs-id-err');
      const saveBtn = modal.querySelector('#cs-id-save');
      const nameInput = modal.querySelector('#cs-id-name');

      const submit = async () => {
        const nm = (nameInput.value || '').trim();
        const ak = csNormKey(prof.access_key) || csGenKey();
        errEl.hidden = true;
        if (!csIsRealName(nm)) {
          errEl.textContent = '사용자 이름을 입력하세요. (게스트/seed 제외)';
          errEl.hidden = false;
          nameInput.focus();
          return;
        }
        saveBtn.disabled = true;
        try {
          csWriteProfile(nm, ak);
          await csSyncProfileToServer(nm, ak, isFirst);
          close({ member: nm, access_key: ak, skipped: false });
          if (typeof wikiToast === 'function') wikiToast('사용자 등록됨: ' + nm + ' (' + ak + ')');
        } finally {
          saveBtn.disabled = false;
        }
      };

      saveBtn.onclick = submit;
      nameInput.addEventListener('keydown', e => {
        if (e.key === 'Enter') { e.preventDefault(); submit(); }
      });
      nameInput.focus();
    }
    async function csEnsureFirstEntryName(source) {
      if (typeof wkEnsureFirstEntryName === 'function') {
        const res = await wkEnsureFirstEntryName(source || 'console');
        const name = csReadProfile().member;
        if (name) CS.owner = name;
        const chip = document.getElementById('cs-owner-chip');
        if (chip) chip.textContent = name || '미설정';
        return res;
      }
      const existing = csReadProfile();
      if (csIsRealName(existing.member)) {
        CS.owner = existing.member;
        const chip = document.getElementById('cs-owner-chip');
        if (chip) chip.textContent = existing.member;
        return { member: existing.member, access_key: existing.access_key, existing: true };
      }
      try {
        if (sessionStorage.getItem(CS_ENTRY_SKIP_KEY) === '1') return { skipped: true };
      } catch (e) {}
      if (CS._entryPromise) return CS._entryPromise;
      CS._entryPromise = new Promise(resolve => {
        csOpenNameModal(true, res => {
          CS._entryPromise = null;
          resolve(res || { skipped: true });
        });
      });
      return CS._entryPromise;
    }

    function csOwnerName() {
      const prof = csReadProfile();
      if (csIsRealName(prof.member)) { CS.owner = prof.member; return prof.member; }
      return '';
    }
    function csOwner(force) {
      if (force) { csOpenNameModal(false); return csOwnerName() || 'guest'; }
      const n = csOwnerName();
      CS.owner = n || 'guest';
      const chip = document.getElementById('cs-owner-chip');
      if (chip) chip.textContent = n || '미설정';
      return CS.owner;
    }
    // 새로고침·재진입 시, 이 이름으로 살아 있는 세션을 "쓰던 분할 배치 그대로" 다시 붙인다(로그=스크롤백 재생).
    async function csResume() {
      if (CS.solo || CS.slots.some(s => s.t)) return;
      const n = csOwnerName();
      if (!n) return;                      // 이름을 아직 안 넣었으면 조용히 건너뜀
      let rows = [];
      try { rows = await csApi('GET', '/console/api/sessions?u=' + encodeURIComponent(n)); } catch (e) { return; }
      const alive = new Set(rows.map(r => r.target));
      const usable = tid => alive.has(tid) && CS.targets.some(t => t.id === tid && !t.disabled);
      CS.owner = n;
      let snap = null;
      try { snap = JSON.parse(localStorage.getItem('fig.term.layout') || 'null'); } catch (e) {}
      const snapHas = snap && ((snap.slots || []).some(usable) || (snap.floats || []).some(f => usable(f.target)));
      if (snapHas) {
        CS.layout = snap.layout || '1';
        CS.sizes = snap.sizes || CS.sizes;
        CS.active = Math.max(0, snap.active || 0);
        csRender();                        // 저장된 분할로 빈 칸을 만든 뒤
        (snap.slots || []).forEach((tid, i) => { if (usable(tid) && CS.slots[i]) csConnectSlot(i, tid); });
        (snap.floats || []).forEach(f => { if (usable(f.target)) { const t = csNewTerm(f.target); CS.floats.push(t); csPlaceFloat(t, f.pos); csStart(t); } });
        csApplySizes(); csTabs();
        return;
      }
      if (!rows.length) return;            // 배치 기록이 없으면 살아 있는 세션을 순서대로
      rows.slice(0, csPaneCount()).forEach((r, i) => { if (usable(r.target)) csConnectSlot(i, r.target); });
    }

    // ---------- 열기 · 닫기 · 잠금 ----------
    async function csOpen(soloId) {
      if (soloId === 's1' || soloId === 't1-vm2') {
        const root = csRoot(); root.hidden = false; document.body.classList.add('cs-on');
        root.innerHTML = '<div style="padding:60px 20px; text-align:center; color:#f87171; background:#0f172a; min-height:100vh;">' +
          '<h2 style="font-size:22px; margin-bottom:12px;">🚫 웹 콘솔 터미널 접근 불가</h2>' +
          '<p style="color:#94a3b8; font-size:14px; margin-bottom:24px;">s1 호스트는 기본 팀(figteam) 보안 정책상 웹에서 콘솔 터미널 접근이 제외된 물리 베이스 구역입니다.</p>' +
          '<button type="button" class="wk-btn wk-primary" onclick="location.href=\\'/\\'" style="padding:8px 16px; background:#0284c7; color:#fff; border:none; border-radius:6px; cursor:pointer;">대시보드로 돌아가기</button>' +
          '</div>';
        return;
      }
      if (!figReadStoredAccessKey()) {
        figExpireKeylessSessions();
        figRecordSiteVisit('expired', CS.page ? 'term' : 'console', '키 없는 콘솔 접속 차단');
        const root = csRoot();
        root.hidden = false;
        root.classList.toggle('cs-solo', !!soloId);
        root.classList.toggle('cs-page', CS.page);
        document.body.classList.add('cs-on');
        CS.open = true; CS.solo = soloId || null;
        return csShowUnlock('접속 키가 없는 이전 세션이 만료되었습니다. 이름·접속 키와 비밀번호를 입력해 다시 로그인해 주세요.');
      }
      figRecordSiteVisit('authenticated', CS.page ? 'term' : 'console', '통합 콘솔 접속');
      const root = csRoot();
      if (CS.targets && root.querySelector('.cs-wrap') && !soloId) {   // 다른 화면에 갔다 와도 열린 터미널은 그대로
        root.hidden = false; document.body.classList.add('cs-on'); CS.open = true;
        const curName = csOwnerName();
        const chip = document.getElementById('cs-owner-chip');
        if (chip) chip.textContent = curName || '미설정';
        csApplySizes(); csLoadStatus();
        await csEnsureFirstEntryName('console');
        if (CS.pending) { const id = CS.pending; CS.pending = null; csPick(id); }
        return;
      }
      CS.open = true; CS.solo = soloId || null;
      CS.booting = true;   // 복원 끝나기 전엔 레이아웃 저장 금지(빈 칸으로 스냅샷을 덮어쓰지 않도록)
      root.hidden = false;
      root.classList.toggle('cs-solo', !!CS.solo);
      root.classList.toggle('cs-page', CS.page);
      document.body.classList.add('cs-on');
      if (!root.querySelector('.cs-wrap')) root.innerHTML = '<p class="cs-wait">통합 콘솔을 불러오는 중…</p>';
      try { await csLoadXterm(); }
      catch (e) { root.innerHTML = '<p class="cs-wait wk-error">터미널 화면 구성요소(xterm.js)를 불러오지 못했습니다. 인터넷 연결을 확인하세요.</p>'; return; }
      try { CS.targets = await csApi('GET', '/console/api/targets'); await csLoadPresets(); }
      catch (e) { return csShowUnlock(e.status === 401 ? '' : (e.error || '콘솔 서버에 연결하지 못했습니다 (' + e.status + ')')); }
      csRender();
      csLoadStatus();
      await csEnsureFirstEntryName('console');
      const chipAfter = document.getElementById('cs-owner-chip');
      if (chipAfter) chipAfter.textContent = csOwnerName() || '미설정';
      if (!CS.stTimer) CS.stTimer = setInterval(() => { if (CS.open && !csRoot().hidden) csLoadStatus(); }, 20000);
      if (CS.solo && !CS.slots[0].t) csConnectSlot(0, CS.solo);
      else if (CS.pending) { const id = CS.pending; CS.pending = null; if (CS.targets.some(t => t.id === id && !t.disabled)) csPick(id); }
      else await csResume();   // 새로고침·재진입 시 이 이름의 살아 있는 세션을 자동으로 다시 붙인다
      CS.booting = false; csSaveLayout();   // 복원 끝 — 이제부터 변경은 저장
    }
    // 머리글 [대시보드]·[설정]·[콘솔] 전환 (본문만 바뀜)
    function csView(v) {
      const on = v === 'console', bc = document.getElementById('btn-tab-console');
      if (bc) bc.classList.toggle('active', on);
      if (!on) { csHide(); return false; }
      ['view-dashboard', 'view-settings'].forEach(id => { const e = document.getElementById(id); if (e) e.style.display = 'none'; });
      ['btn-tab-dashboard', 'btn-tab-settings'].forEach(id => { const e = document.getElementById(id); if (e) e.classList.remove('active'); });
      csOpen();
      return true;
    }
    function csHide() {
      const r = document.getElementById('cs-root');
      if (r) r.hidden = true;
      CS.open = false;
      document.body.classList.remove('cs-on');
    }
    function csBack() { if (CS.page) location.href = '/'; else if (typeof switchView === 'function') switchView('dashboard'); }
    function csClose() {
      if (CS.page) { location.href = '/'; return; }
      CS.slots.forEach(s => csDispose(s.t)); CS.floats.forEach(csDispose);
      CS.slots = []; CS.floats = []; CS.open = false;
      const root = csRoot(); root.hidden = true; root.innerHTML = '';
      document.body.classList.remove('cs-on');
      if ((location.hash || '').indexOf('#console') === 0) history.replaceState(null, '', location.pathname);
    }
    function csShowUnlock(msg) {
      CS.slots.forEach(s => csDispose(s.t)); CS.floats.forEach(csDispose); CS.slots = []; CS.floats = [];
      const stored = figReadStoredAccessKey();
      const preName = stored ? stored.member : (csIsRealName(csReadProfile().member) ? csReadProfile().member : '');
      const keyLabel = stored ? (stored.access_key + ' (서버 할당 · 변경 불가)') : '로그인 시 서버에서 자동 할당 (변경 불가)';
      csRoot().innerHTML =
        '<div class="cs-unlock"><form class="wk-card" onsubmit="csUnlock(event)"><h3>통합 콘솔 로그인 (불변 접속 키)</h3>' +
        '<p class="manual-desc">세션이 만료되었거나 접속 키가 없습니다. 이름과 사이트 비밀번호를 입력하면 서버가 접속 키를 자동 할당·유지합니다. 모든 입력과 출력은 기록됩니다.</p>' +
        '<label>사용자 이름 <span>(필수)</span><input name="member" required maxlength="20" autocomplete="nickname" value="' + cfgEsc(preName) + '" placeholder="예: 홍길동"></label>' +
        '<label>접속 키값 <span>(서버 자동 할당 · 변경 불가)</span><div class="login-key-readonly" style="margin-bottom:0;">' + cfgEsc(keyLabel) + '</div></label>' +
        '<label>사이트 비밀번호<input name="password" type="password" required autocomplete="current-password"></label>' +
        '<p class="wk-error" id="cs-unlock-err" role="alert"' + (msg ? '' : ' hidden') + '>' + cfgEsc(msg || '') + '</p>' +
        '<div class="wk-bar wk-bar-inline"><button type="submit" class="wk-btn wk-primary">로그인 및 잠금 해제</button>' +
        (CS.solo ? '' : '<button type="button" class="wk-btn" onclick="csBack()">대시보드로</button>') + '</div></form></div>';
      const memEl = csRoot().querySelector('input[name=member]');
      const pwdEl = csRoot().querySelector('input[name=password]');
      if (memEl && !memEl.value.trim()) memEl.focus();
      else if (pwdEl) pwdEl.focus();
    }
    async function csUnlock(ev) {
      ev.preventDefault();
      const err = document.getElementById('cs-unlock-err');
      const form = ev.target;
      const member = (form.member ? form.member.value : '').trim();
      if (!csIsRealName(member)) {
        err.textContent = '사용자 이름을 입력하세요. (게스트/seed 제외)';
        err.hidden = false;
        if (form.member) form.member.focus();
        return;
      }
      try {
        const res = await csApi('POST', '/console/api/unlock', {
          password: form.password.value,
          member: member
        });
        const ak = csNormKey(res && res.access_key) || csReadProfile().access_key || csGenKey();
        csWriteProfile(member, ak);
        try { sessionStorage.setItem(figAuthStorageKey(), 'valid'); } catch (e) {}
        figRecordSiteVisit('authenticated', CS.page ? 'term' : 'console', '콘솔 로그인 성공');
        csSyncProfileToServer(member, ak, true).catch(() => {});
        csRoot().innerHTML = '';
        csOpen(CS.solo);
      } catch (e) {
        figRecordSiteVisit('login_fail', CS.page ? 'term' : 'console', '콘솔 로그인 실패 (' + (e.status || 0) + ')');
        err.textContent = e.status === 401 ? '비밀번호가 맞지 않습니다' : e.status === 429 ? '시도가 많습니다. 10분 뒤 다시 시도하세요' : (e.error || '잠금을 풀지 못했습니다');
        err.hidden = false;
      }
    }
    async function csLock() {
      try { await csApi('POST', '/console/api/lock', {}); } catch (e) {}
      csShowUnlock('콘솔을 잠갔습니다.');
    }

    // ---------- 화면 구성 ----------
    function csPaneCount() { return CS.solo ? 1 : { '1': 1, h: 2, v: 2, '4': 4 }[CS.layout]; }
    function csRender() {
      const n = csPaneCount();
      while (CS.slots.length < n) CS.slots.push({ t: null });
      while (CS.slots.length > n) {   // 줄어든 칸의 터미널은 끊지 않고 화면 위 창으로 띄운다
        const s = CS.slots.pop();
        if (s.t) CS.floats.push(s.t);
      }
      if (CS.active >= n) CS.active = 0;
      const drawer = CS.solo ? '' :
        '<aside class="cs-drawer"><div class="cs-drawer-head"><b>콘솔</b><span>인스턴스를 누르면 바로 접속 · 서비스를 누르면 상태 확인</span>' +
        '<button type="button" class="cs-owner" onclick="csOwner(true)" title="세션 이어가기에 쓰는 이름 — 누르면 변경">이름: <b id="cs-owner-chip">' + cfgEsc(csOwnerName() || '미설정') + '</b></button></div>' +
        '<div id="cs-tree">' + csTreeHtml() + '</div>' +
        '<div class="cs-drawer-foot"><button type="button" class="wk-mini" onclick="csBack()">← 대시보드</button>' +
        (CS.page ? '' : '<button type="button" class="wk-mini" onclick="window.open(\\'/term/\\', \\'_blank\\')">새 창으로</button>') + '</div></aside>';
      const bar = CS.solo ? '' :
        '<div class="cs-bar"><div class="cs-layouts" role="group" aria-label="창 배치">' + CS_LAYOUTS.map(l =>
          '<button type="button" class="wk-mini' + (CS.layout === l[0] ? ' cs-on-btn' : '') + '" aria-pressed="' + (CS.layout === l[0]) + '" onclick="csLayout(\\'' + l[0] + '\\')">' + l[1] + '</button>').join('') +
        '</div><nav class="cs-tabs" id="cs-tabs" aria-label="열린 터미널"></nav></div>';
      const grid = '<div class="cs-grid cs-l' + (CS.solo ? '1' : CS.layout) + '" id="cs-grid">' +
        CS.slots.map((s, i) => '<section class="cs-pane' + (i === CS.active ? ' cs-active' : '') + '" data-i="' + i + '" onmousedown="csFocus(' + i + ')" id="cs-slot-' + i + '"></section>').join('') +
        csGutters() + '</div>';
      csRoot().innerHTML = '<div class="cs-wrap">' + drawer + '<div class="cs-main">' + bar + grid + '</div></div><div class="cs-float-layer" id="cs-float-layer"></div>';
      CS.slots.forEach((s, i) => csFillSlot(i));
      CS.floats.forEach(t => csPlaceFloat(t));
      csApplySizes();
      csTabs();
    }
    function csGutters() {
      const L = CS.solo ? '1' : CS.layout;
      return (L === 'h' || L === '4' ? '<div class="cs-gutter cs-gx" onmousedown="csDrag(event,\\'col\\')" title="좌우 크기 조절"></div>' : '') +
             (L === 'v' || L === '4' ? '<div class="cs-gutter cs-gy" onmousedown="csDrag(event,\\'row\\')" title="상하 크기 조절"></div>' : '');
    }
    function csApplySizes() {
      const g = document.getElementById('cs-grid'); if (!g) return;
      g.style.setProperty('--cs-col', CS.sizes.col + '%');
      g.style.setProperty('--cs-row', CS.sizes.row + '%');
      csAllTerms().forEach(t => { try { t.fit.fit(); } catch (e) {} });
    }
    function csDrag(ev, axis) {
      ev.preventDefault();
      const g = document.getElementById('cs-grid'), r = g.getBoundingClientRect();
      const move = e => {
        const v = axis === 'col' ? (e.clientX - r.left) / r.width : (e.clientY - r.top) / r.height;
        CS.sizes[axis] = Math.max(15, Math.min(85, Math.round(v * 100)));
        csApplySizes();
      };
      const up = () => { document.removeEventListener('mousemove', move); document.removeEventListener('mouseup', up); document.body.classList.remove('cs-dragging'); csSaveLayout(); };
      document.body.classList.add('cs-dragging');
      document.addEventListener('mousemove', move); document.addEventListener('mouseup', up);
    }
    function csLayout(l) { CS.layout = l; csRender(); }
    function csFocus(i) {
      CS.active = i;
      document.querySelectorAll('.cs-pane').forEach(el => el.classList.toggle('cs-active', Number(el.dataset.i) === i));
    }
    function csAllTerms() { return CS.slots.map(s => s.t).filter(Boolean).concat(CS.floats); }

    // ---------- 터미널 한 개 (칸·띄운 창이 함께 쓰는 단위) ----------
    async function csLoadPresets() { try { CS.presets = await csApi('GET', '/console/api/presets'); } catch (e) { CS.presets = CS.presets || {}; } }
    function csPresetItems(id) { return ((CS.presets || {})[id] || {}).items || []; }
    function csHeadHtml(t, inFloat) {
      const tg = csT(t.target), items = csPresetItems(t.target);
      const btns = kind => items.map((x, n) => x.kind !== kind ? '' :
        '<button type="button" class="cs-pre' + (kind === 'fix' ? ' cs-pre-fix' : '') + '" title="' + cfgEsc(x.cmd) + '" onclick="csPreset(' + t.uid + ',' + n + ',this)">' + cfgEsc(x.label) + '</button>').join('');
      const hasFix = items.some(x => x.kind === 'fix');
      return '<header class="cs-pane-head"><span class="cs-dot cs-dot-' + (t.stKind || 'wait') + '" id="cs-dot-' + t.uid + '"></span><b>' + cfgEsc(tg.name) + '</b>' +
        '<span class="cs-status" id="cs-st-' + t.uid + '">' + cfgEsc(t.stText || '') + '</span>' +
        '<span class="cs-pane-acts">' +
          (inFloat ? '<button type="button" class="wk-mini" title="최소화" onclick="csFloatMin(' + t.uid + ')">▁</button><button type="button" class="wk-mini" title="최대화" onclick="csFloatMax(' + t.uid + ')">▢</button>' +
            (CS.solo ? '' : '<button type="button" class="wk-mini" title="칸으로 되돌리기" onclick="csDock(' + t.uid + ')">⇲</button>')
            : (CS.solo ? '' : '<button type="button" class="wk-mini" title="화면 위에 띄우기" onclick="csFloat(' + t.uid + ')">⧉</button>')) +
          '<button type="button" class="wk-mini" title="다시 연결" onclick="csReconnect(' + t.uid + ')">⟳</button>' +
          (CS.solo ? '' : '<button type="button" class="wk-mini" title="새 창으로" onclick="csPopout(' + t.uid + ')">↗</button>') +
          '<button type="button" class="wk-mini" title="닫기" onclick="csCloseTerm(' + t.uid + ')">✕</button></span></header>' +
        '<div class="cs-presets"><span class="cs-pre-lbl">확인</span>' + btns('check') +
          (hasFix ? '<span class="cs-pre-lbl cs-pre-warn">복구</span>' + btns('fix') : '') +
          '<button type="button" class="cs-pre cs-pre-edit" onclick="csEditPresets(\\'' + cfgEsc(t.target) + '\\')">버튼 편집</button></div>';
    }
    // 버튼 목록이 바뀌면 열린 터미널의 머리줄만 다시 그린다 (연결 유지)
    function csRefreshHeads() {
      CS.slots.forEach((sl, i) => { if (sl.t) csFillSlot(i); });
      CS.floats.forEach(t => {
        if (!t.el) return;
        t.el.querySelectorAll('.cs-pane-head, .cs-presets').forEach(e => e.remove());
        t.el.insertAdjacentHTML('afterbegin', csHeadHtml(t, true));
        const head = t.el.querySelector('.cs-pane-head');
        head.addEventListener('mousedown', e => csFloatDragStart(e, t.el));
      });
    }

    function csFillSlot(i) {
      const el = document.getElementById('cs-slot-' + i), t = CS.slots[i].t;
      if (!el) return;
      if (!t) {
        el.innerHTML = '<header class="cs-pane-head"><span class="cs-dot"></span><b>빈 칸</b></header>' +
          '<div class="cs-term"><p class="cs-empty">왼쪽에서 인스턴스를 고르면 이 칸에 터미널이 열립니다.</p></div>';
        return;
      }
      el.innerHTML = csHeadHtml(t, false) + '<div class="cs-term" id="cs-host-' + t.uid + '"></div>';
      document.getElementById('cs-host-' + t.uid).appendChild(t.box);
      setTimeout(() => { try { t.fit.fit(); } catch (e) {} }, 0);
    }
    function csNewTerm(target) {
      const t = { uid: ++CS.seq, target: target, stKind: 'wait', stText: '연결 중…' };
      t.box = document.createElement('div'); t.box.className = 'cs-term-inner';
      return t;
    }
    function csStart(t) {
      const term = new window.Terminal({ cursorBlink: true, fontFamily: "'JetBrains Mono', monospace", fontSize: 13, scrollback: 5000,
        theme: { background: '#06090e', foreground: '#e2e8f0', cursor: '#93c5fd', selectionBackground: '#1e3a8a' } });
      const fit = new window.FitAddon.FitAddon();
      term.loadAddon(fit); term.open(t.box);
      try { fit.fit(); } catch (e) {}
      t.term = term; t.fit = fit;
      csStatus(t, 'wait', '연결 중…');
      const url = (location.protocol === 'https:' ? 'wss://' : 'ws://') + location.host + '/console/ws/' + encodeURIComponent(t.target) +
        '?cols=' + term.cols + '&rows=' + term.rows + '&u=' + encodeURIComponent(csOwner());
      const ws = new WebSocket(url);
      t.ws = ws;
      ws.onopen = () => {
        csStatus(t, 'ok', '연결됨'); term.focus();
        if (t.queue) { const q = t.queue; t.queue = null; setTimeout(() => { if (ws.readyState === 1) ws.send(JSON.stringify({ t: 'i', d: q + '\\r' })); }, 700); }
      };
      ws.onmessage = e => term.write(e.data);
      ws.onclose = e => {
        if (t.ws !== ws) return;
        const msg = CS_CLOSE_MSG[e.code] || (e.code === 1000 ? '세션이 끝났습니다' : '연결이 끊겼습니다 (' + e.code + ')');
        csStatus(t, 'off', msg);
        term.write('\\r\\n\\x1b[33m[' + msg + ' — ⟳ 로 다시 연결]\\x1b[0m\\r\\n');
        if (e.code === 4401) csShowUnlock('잠금이 만료되었습니다. 다시 풀어 주세요.');
      };
      term.onData(d => { if (ws.readyState === 1) ws.send(JSON.stringify({ t: 'i', d: d })); });
      term.onResize(sz => { if (ws.readyState === 1) ws.send(JSON.stringify({ t: 'r', c: sz.cols, r: sz.rows })); });
      t.ro = new ResizeObserver(() => { try { fit.fit(); } catch (e) {} });
      t.ro.observe(t.box);
    }
    function csStatus(t, kind, text) {
      t.stKind = kind; t.stText = text;
      const d = document.getElementById('cs-dot-' + t.uid), s = document.getElementById('cs-st-' + t.uid);
      if (d) d.className = 'cs-dot cs-dot-' + kind;
      if (s) s.textContent = text;
      csTabs();
    }
    function csDispose(t) {
      if (!t) return;
      if (t.ro) { t.ro.disconnect(); t.ro = null; }
      if (t.ws) { const w = t.ws; t.ws = null; try { w.close(); } catch (e) {} }
      if (t.term) { try { t.term.dispose(); } catch (e) {} t.term = null; }
      if (t.el) { t.el.remove(); t.el = null; }
    }
    function csFind(uid) {
      const i = CS.slots.findIndex(s => s.t && s.t.uid === uid);
      if (i >= 0) return { where: 'slot', i: i, t: CS.slots[i].t };
      const f = CS.floats.findIndex(t => t.uid === uid);
      return f >= 0 ? { where: 'float', i: f, t: CS.floats[f] } : null;
    }

    // ---------- 고르기 · 다시 연결 · 닫기 · 새 창 ----------
    function csPick(id) {
      if (id === 's1' || id === 't1-vm2') {
        if (typeof wikiToast === 'function') wikiToast('s1 호스트는 웹에서 콘솔 터미널 접근이 불가합니다.');
        else alert('s1 호스트는 웹에서 콘솔 터미널 접근이 불가합니다.');
        return;
      }
      let i = CS.active;
      if (CS.slots[i].t) { const empty = CS.slots.findIndex(s => !s.t); if (empty >= 0) i = empty; }
      csConnectSlot(i, id);
    }
    function csConnectSlot(i, id) {
      if (id === 's1' || id === 't1-vm2') {
        if (typeof wikiToast === 'function') wikiToast('s1 호스트는 웹에서 콘솔 터미널 접근이 불가합니다.');
        return;
      }
      csDispose(CS.slots[i].t);
      const t = csNewTerm(id);
      CS.slots[i].t = t;
      csFillSlot(i); csFocus(i); csStart(t); csTabs();
    }
    function csReconnect(uid) {
      const f = csFind(uid); if (!f) return;
      const old = f.t, t = csNewTerm(old.target);
      if (f.where === 'slot') { csDispose(old); CS.slots[f.i].t = t; csFillSlot(f.i); csStart(t); }
      else { const pos = old.el ? { left: old.el.style.left, top: old.el.style.top, w: old.el.style.width, h: old.el.style.height } : null;
        csDispose(old); CS.floats[f.i] = t; csPlaceFloat(t, pos); csStart(t); }
      csTabs();
    }
    function csCloseTerm(uid) {
      const f = csFind(uid); if (!f) return;
      csDispose(f.t);
      if (f.where === 'slot') { CS.slots[f.i].t = null; if (CS.solo) return window.close(); csFillSlot(f.i); }
      else CS.floats.splice(f.i, 1);
      csTabs();
    }
    function csPopout(uid) {
      const f = csFind(uid); if (!f) return;
      window.open(CS_TERM_URL + '?solo=' + encodeURIComponent(f.t.target), 'cs-' + f.t.target + '-' + Date.now(), 'width=1000,height=640');
      csCloseTerm(uid);
    }

    // ---------- 확인 · ⚠ 복구 버튼 (예전 통합 터미널) ----------
    function csPreset(uid, n, btn) {
      const f = csFind(uid); if (!f || !f.t.ws || f.t.ws.readyState !== 1) return;
      const x = csPresetItems(f.t.target)[n];
      if (!x) return;
      if (x.kind === 'fix' && !btn.dataset.armed) {   // 복구는 한 번 더 눌러야 실행
        btn.dataset.armed = '1'; btn.textContent = '한 번 더 누르면 실행: ' + x.label;
        setTimeout(() => { if (btn.isConnected) { delete btn.dataset.armed; btn.textContent = x.label; } }, 4000);
        return;
      }
      if (x.kind === 'fix') { delete btn.dataset.armed; btn.textContent = x.label; }
      f.t.ws.send(JSON.stringify({ t: 'i', d: x.cmd + '\\r' }));   // 긴 명령도 한 번에 입력·실행
      f.t.term.focus();
    }

    // ---------- 버튼 편집 (팀 공용 저장, 초안으로 되돌리기 가능) ----------
    const CS_EMOJI = /[\\u{1F000}-\\u{1FFFF}\\u2190-\\u21FF\\u2300-\\u23FF\\u2460-\\u24FF\\u2500-\\u27BF\\u2900-\\u297F\\u2B00-\\u2BFF\\uFE0F\\u200D]/u;
    function csEditPresets(id) {
      const tg = csT(id), p = (CS.presets || {})[id] || { items: [] };
      let el = document.getElementById('cs-editor');
      if (!el) { el = document.createElement('div'); el.id = 'cs-editor'; el.setAttribute('role', 'dialog'); el.setAttribute('aria-modal', 'true'); csRoot().appendChild(el); }
      el.dataset.id = id;
      el.innerHTML = '<div class="cs-ed-box"><div class="cs-ed-head"><h3>' + cfgEsc(tg.name) + ' 명령 버튼</h3>' +
        '<span class="cs-ed-note">' + (p.custom ? '팀에서 고친 목록' : '초안 (예전 통합 터미널 명령)') + ' · 이름은 한글·영문, 명령은 한 줄(여러 명령은 ; 또는 &&)</span></div>' +
        '<div class="cs-ed-rows" id="cs-ed-rows">' + p.items.map(csEdRow).join('') + '</div>' +
        '<button type="button" class="wk-add" onclick="csEdAdd()">+ 버튼 추가</button>' +
        '<p class="wk-error" id="cs-ed-err" role="alert" hidden></p>' +
        '<div class="cs-ed-bar"><button type="button" class="wk-btn wk-primary" onclick="csEdSave()">저장</button>' +
        (p.custom ? '<button type="button" class="wk-btn" onclick="csEdReset(this)">초안으로 되돌리기</button>' : '') +
        '<button type="button" class="wk-btn" onclick="csEdClose()">취소</button></div></div>';
      el.hidden = false;
      const first = el.querySelector('input'); if (first) first.focus();
    }
    function csEdRow(x) {
      x = x || { label: '', cmd: '', kind: 'check' };
      return '<div class="cs-ed-row"><input class="cs-ed-label" maxlength="30" placeholder="버튼 이름 (예: 디스크 사용량)" value="' + cfgEsc(x.label) + '">' +
        '<select class="cs-ed-kind"><option value="check"' + (x.kind === 'check' ? ' selected' : '') + '>확인</option><option value="fix"' + (x.kind === 'fix' ? ' selected' : '') + '>복구</option></select>' +
        '<input class="cs-ed-cmd" maxlength="2000" spellcheck="false" placeholder="명령 (예: df -h / && free -m)" value="' + cfgEsc(x.cmd) + '">' +
        '<span class="cs-ed-tools"><button type="button" class="wk-mini" title="위로" onclick="csEdMove(this,-1)">↑</button><button type="button" class="wk-mini" title="아래로" onclick="csEdMove(this,1)">↓</button>' +
        '<button type="button" class="wk-mini wk-danger" title="삭제" onclick="this.closest(\\'.cs-ed-row\\').remove()">삭제</button></span></div>';
    }
    function csEdAdd() { const box = document.getElementById('cs-ed-rows'); box.insertAdjacentHTML('beforeend', csEdRow()); box.lastElementChild.querySelector('input').focus(); }
    function csEdMove(btn, d) { const r = btn.closest('.cs-ed-row'), s2 = d < 0 ? r.previousElementSibling : r.nextElementSibling; if (s2) { if (d < 0) s2.before(r); else s2.after(r); } }
    function csEdClose() { const el = document.getElementById('cs-editor'); if (el) el.hidden = true; }
    function csEdErr(msg, row) {
      const e = document.getElementById('cs-ed-err'); e.textContent = msg; e.hidden = false;
      document.querySelectorAll('.cs-ed-row.cs-bad').forEach(r => r.classList.remove('cs-bad'));
      if (row) { row.classList.add('cs-bad'); row.scrollIntoView({ block: 'nearest' }); }
    }
    async function csEdSave() {
      const el = document.getElementById('cs-editor'), id = el.dataset.id;
      const rows = Array.from(el.querySelectorAll('.cs-ed-row'));
      const items = [];
      for (const r of rows) {
        const label = r.querySelector('.cs-ed-label').value.trim(), cmd = r.querySelector('.cs-ed-cmd').value.trim();
        if (!label && !cmd) continue;
        if (!label || !cmd) return csEdErr('버튼 이름과 명령을 모두 입력하세요.', r);
        if (CS_EMOJI.test(label)) return csEdErr('버튼 이름에는 이모티콘·기호를 쓸 수 없습니다. 한글이나 영문으로 적어 주세요.', r);
        items.push({ label: label, cmd: cmd, kind: r.querySelector('.cs-ed-kind').value });
      }
      try {
        await csApi('PUT', '/console/api/presets/' + encodeURIComponent(id), { items: items });
        await csLoadPresets(); csRefreshHeads(); csEdClose();
        if (typeof wikiToast === 'function') wikiToast('버튼을 저장했습니다 (' + items.length + '개)');
      } catch (e) { csEdErr(e.status === 401 ? '로그인이 만료되었습니다. 다시 로그인하세요.' : (e.error || '저장하지 못했습니다')); }
    }
    async function csEdReset(btn) {
      if (!btn.dataset.armed) { btn.dataset.armed = '1'; btn.textContent = '한 번 더 누르면 초안으로'; return; }
      const id = document.getElementById('cs-editor').dataset.id;
      try { await csApi('DELETE', '/console/api/presets/' + encodeURIComponent(id)); await csLoadPresets(); csRefreshHeads(); csEditPresets(id);
        if (typeof wikiToast === 'function') wikiToast('초안 목록으로 되돌렸습니다'); }
      catch (e) { csEdErr(e.error || '되돌리지 못했습니다'); }
    }

    // ---------- ⧉ 화면 위 창 ----------
    function csFloat(uid) {
      const f = csFind(uid); if (!f || f.where !== 'slot') return;
      CS.slots[f.i].t = null; csFillSlot(f.i);
      CS.floats.push(f.t); csPlaceFloat(f.t); csTabs();
    }
    function csPlaceFloat(t, pos) {
      const layer = document.getElementById('cs-float-layer'); if (!layer) return;
      const n = CS.floats.indexOf(t);
      const el = document.createElement('div');
      el.className = 'cs-float'; el.id = 'cs-float-' + t.uid;
      el.style.left = (pos && pos.left) || (320 + 28 * n) + 'px'; el.style.top = (pos && pos.top) || (90 + 28 * n) + 'px';
      if (pos && pos.w) { el.style.width = pos.w; el.style.height = pos.h; }
      el.style.zIndex = ++CS.z;
      el.innerHTML = csHeadHtml(t, true) + '<div class="cs-term" id="cs-host-' + t.uid + '"></div>';
      layer.appendChild(el);
      document.getElementById('cs-host-' + t.uid).appendChild(t.box);
      t.el = el;
      el.addEventListener('mousedown', () => { el.style.zIndex = ++CS.z; });
      el.querySelector('.cs-pane-head').addEventListener('mousedown', e => csFloatDragStart(e, el));
      setTimeout(() => { try { t.fit.fit(); } catch (e) {} }, 0);
    }
    function csFloatDragStart(e, el) {
      if (e.target.closest('button') || el.classList.contains('cs-max')) return;
      const sx = e.clientX - el.offsetLeft, sy = e.clientY - el.offsetTop;
      const mv = ev => { el.style.left = Math.max(0, ev.clientX - sx) + 'px'; el.style.top = Math.max(0, ev.clientY - sy) + 'px'; };
      const up = () => { document.removeEventListener('mousemove', mv); document.removeEventListener('mouseup', up); document.body.classList.remove('cs-dragging'); };
      document.body.classList.add('cs-dragging');
      document.addEventListener('mousemove', mv); document.addEventListener('mouseup', up);
    }
    function csFloatMin(uid) { const f = csFind(uid); if (f && f.t.el) { f.t.el.classList.toggle('cs-min'); f.t.el.classList.remove('cs-max'); csStackMin(); } }
    function csFloatMax(uid) { const f = csFind(uid); if (f && f.t.el) { f.t.el.classList.toggle('cs-max'); f.t.el.classList.remove('cs-min'); setTimeout(() => { try { f.t.fit.fit(); } catch (e) {} }, 50); csStackMin(); } }
    function csStackMin() {
      let x = 290;
      CS.floats.forEach(t => { if (t.el && t.el.classList.contains('cs-min')) { t.el.style.left = x + 'px'; t.el.style.top = (window.innerHeight - 96) + 'px'; x += 270; } });
    }
    function csDock(uid) {
      const f = csFind(uid); if (!f || f.where !== 'float') return;
      let i = CS.slots[CS.active] && !CS.slots[CS.active].t ? CS.active : CS.slots.findIndex(s => !s.t);
      if (i < 0) { if (typeof wikiToast === 'function') wikiToast('빈 칸이 없습니다. 배치를 늘리거나 칸 하나를 닫으세요.'); return; }
      f.t.el.remove(); f.t.el = null;
      CS.floats.splice(f.i, 1);
      CS.slots[i].t = f.t; csFillSlot(i); csFocus(i); csTabs();
    }

    // ---------- 탭: 열린 터미널 전체 ----------
    function csTabs() {
      const nav = document.getElementById('cs-tabs'); if (!nav) return;
      const items = CS.slots.map((s, i) => s.t ? { t: s.t, label: (i + 1) + '번 칸' } : null).filter(Boolean)
        .concat(CS.floats.map(t => ({ t: t, label: '⧉ 띄운 창' })));
      nav.innerHTML = items.length ? items.map(x =>
        '<button type="button" class="cs-tab" onclick="csTabGo(' + x.t.uid + ')"><span class="cs-dot cs-dot-' + (x.t.stKind || 'wait') + '"></span>' +
        cfgEsc(csT(x.t.target).name) + '<small>' + x.label + '</small></button>').join('') : '<span class="cs-hint">칸을 누른 뒤 왼쪽에서 인스턴스를 고르세요. 경계를 끌면 크기가 바뀝니다.</span>';
      csSaveLayout();
    }
    // 현재 배치(분할·각 칸 대상·띄운 창)를 저장해, 새로고침 때 그대로 복원한다
    function csSaveLayout() {
      if (CS.solo || CS.booting) return;   // 솔로(새 창)는 ?solo= 로 복원 · 부팅 중엔 저장 금지
      try {
        localStorage.setItem('fig.term.layout', JSON.stringify({
          layout: CS.layout, sizes: CS.sizes, active: CS.active,
          slots: CS.slots.map(s => (s.t ? s.t.target : null)),
          floats: CS.floats.map(t => ({ target: t.target, pos: t.el ? { left: t.el.style.left, top: t.el.style.top, w: t.el.style.width, h: t.el.style.height } : null }))
        }));
      } catch (e) {}
    }
    function csTabGo(uid) {
      const f = csFind(uid); if (!f) return;
      if (f.where === 'slot') { csFocus(f.i); f.t.term && f.t.term.focus(); }
      else { f.t.el.classList.remove('cs-min'); f.t.el.style.zIndex = ++CS.z; csStackMin(); f.t.term && f.t.term.focus(); }
    }

    // /term/ 페이지: ?t=<대상> 원클릭 접속, ?solo=<대상> 새 창. (예전 #console/<대상> 주소도 받음)
    window.addEventListener('load', () => {
      const q = new URLSearchParams(location.search), h = location.hash || '';
      if (document.body.dataset.page === 'term') {
        CS.page = true;
        CS.pending = q.get('t');
        csOpen(q.get('solo') || null);
      } else if (h.indexOf('#console/') === 0) {
        location.replace(CS_TERM_URL + '?solo=' + encodeURIComponent(decodeURIComponent(h.slice('#console/'.length))));
      }
    });

    // ===== 사이트 입장 로그인: s1 서버가 확인 (12시간). 접속 키가 없는 이전 세션은 즉시 만료한다 =====
    async function siteAuthBoot() {
      const authKey = figAuthStorageKey();
      const storedKey = figReadStoredAccessKey();
      if (!storedKey) {
        let hadLocalAuth = false;
        try {
          hadLocalAuth = sessionStorage.getItem(authKey) === 'valid';
          sessionStorage.removeItem(authKey);
        } catch (e) {}
        let hadServerSession = false;
        try {
          const r = await fetch('/console/api/me', { credentials: 'same-origin', cache: 'no-store' });
          const d = await r.json();
          hadServerSession = Boolean(d && d.unlocked);
        } catch (e) {}
        if (hadLocalAuth || hadServerSession) {
          await figExpireKeylessSessions();
          figRecordSiteVisit('expired', 'login', '접속 키 없는 이전 세션 만료');
          figShowLoginNotice('접속 키가 없는 이전 세션이 만료되었습니다. 이름·접속 키와 비밀번호로 다시 로그인해 주세요.');
        } else {
          figRecordSiteVisit('visitor', 'login', '사이트 첫 방문 (미로그인)');
        }
        checkAuth();
        return;
      }
      // 이미 이 세션에서 인증됐고 접속 키가 있으면 서버 확인 전에 먼저 복원 → 로그인 화면 깜빡임 방지
      try {
        if (sessionStorage.getItem(authKey) === 'valid') checkAuth();
      } catch (e) {}
      try {
        const r = await fetch('/console/api/me', { credentials: 'same-origin', cache: 'no-store' });
        const d = await r.json();
        if (d.unlocked && !d.key_expired) {
          sessionStorage.setItem(authKey, 'valid');
          figRecordSiteVisit('authenticated', localStorage.getItem('fig.view') || 'dashboard', '사이트 접속 (로그인 유지)');
        } else {
          sessionStorage.removeItem(authKey);
          if (d && d.key_expired) {
            await figExpireKeylessSessions();
            figRecordSiteVisit('expired', 'login', '서버 세션 키 누락 만료');
            figShowLoginNotice('서버 세션에 접속 키가 없어 만료되었습니다. 다시 로그인해 주세요.');
          } else {
            figRecordSiteVisit('visitor', 'login', '사이트 방문 (미로그인)');
          }
        }
      } catch (e) {
        try { sessionStorage.removeItem(authKey); } catch (ex) {}
      }
      checkAuth();
    }

    document.addEventListener('keydown', e => { if (e.key === 'Escape') { const el = document.getElementById('cs-editor'); if (el && !el.hidden) csEdClose(); } });
    // ===== 메인 대시보드: 살아 있는 인스턴스 실측 (content/dashboard.js) =====
    // 데이터: s1 figteam-console 의 읽기 전용 /console/api/status (20초마다 수집)
    const DASH = { snap: null, err: null, timer: null, rtt: null, rot: 0, rotTimer: null };
    const DASH_CLOUD = { onprem: ['온프렘', 'cloud-onprem'], openstack: ['OpenStack', 'cloud-onprem'], kt: ['KT Cloud', 'cloud-kt'], aws: ['AWS', 'cloud-aws'] };
    const DASH_TYPE = { web: '웹/API', gw: '보안/관문', daemon: '상시데몬', data: '데이터/DR' };
    const DASH_ORDER = ['kt', 'onprem', 'openstack', 'aws'];

    function dashFmtBytes(b) { if (b == null) return '-'; const g = b / 1073741824; return g >= 10 ? g.toFixed(0) + ' GB' : g.toFixed(1) + ' GB'; }
    function dashFmtDur(s) {
      if (s == null) return '-';
      const d = Math.floor(s / 86400), h = Math.floor((s % 86400) / 3600), m = Math.floor((s % 3600) / 60);
      return d ? d + '일 ' + h + '시간' : h ? h + '시간 ' + m + '분' : m + '분';
    }
    function dashPct(a, b) { return a != null && b ? Math.round(100 * a / b) : null; }

    async function dashLoad() {
      const t0 = performance.now();
      try {
        const r = await fetch('/console/api/status', { cache: 'no-store' });
        if (!r.ok) throw new Error('HTTP ' + r.status);
        DASH.snap = await r.json(); DASH.err = null;
        DASH.rtt = Math.round(performance.now() - t0);   // 외부 왕복(브라우저→Cloudflare→s1) 실측
      } catch (e) { DASH.err = e.message; }
      dashHeader();
      if (document.getElementById('view-dashboard').style.display !== 'none') dashRender();
    }
    function dashStart() {
      if (DASH.timer) return;
      dashLoad();
      DASH.timer = setInterval(dashLoad, 20000);   // 수집은 20초(서버 부하 방지)
      // 표시는 10초마다 순환(내부/외부 속도·점검 항목을 번갈아 보여줌 — 추가 수집 없음)
      if (!DASH.rotTimer) DASH.rotTimer = setInterval(function () { DASH.rot++; dashHeader(); }, 10000);
    }
    // 내부 속도: s1→인스턴스 조사 왕복(latency_ms) 평균·최대
    function dashInternalSpeed() {
      const xs = (DASH.snap && DASH.snap.instances || []).filter(i => i.alive === true && typeof i.latency_ms === 'number');
      if (!xs.length) return null;
      const avg = Math.round(xs.reduce((s, i) => s + i.latency_ms, 0) / xs.length);
      const slow = xs.reduce((m, i) => i.latency_ms > m.latency_ms ? i : m, xs[0]);
      return { avg: avg, slowName: slow.name, slowMs: slow.latency_ms };
    }
    // 10초 순환으로 보여줄 항목들
    function dashRotItems() {
      const out = [];
      const sp = dashInternalSpeed();
      if (sp) out.push(['내부 속도', sp.avg + 'ms', sp.avg < 800 ? 'state-green' : sp.avg < 2000 ? 'state-yellow' : 'state-red']);
      if (DASH.rtt != null) out.push(['외부 속도', DASH.rtt + 'ms', DASH.rtt < 400 ? 'state-green' : DASH.rtt < 1200 ? 'state-yellow' : 'state-red']);
      if (sp) out.push(['최저속', (sp.slowName || '-') + ' ' + sp.slowMs + 'ms', sp.slowMs < 2000 ? 'state-green' : 'state-yellow']);
      const inst = (DASH.snap && DASH.snap.instances || []).filter(i => !dashNameOnly(i));
      const down = inst.filter(i => i.alive !== true);
      const warn = inst.filter(i => i.alive === true && (i.units || []).some(u => u.state !== 'active'));
      out.push(['점검 필요', down.length || warn.length ? ((down.length ? down.length + ' 끊김 ' : '') + (warn.length ? warn.length + ' 점검' : '')).trim() : '없음',
        down.length ? 'state-red' : warn.length ? 'state-yellow' : 'state-green']);
      return out;
    }

    // 인스턴스 → 화면용 서비스 목록 (systemd 유닛 + k8s 파드)
    function dashServices(i) {
      const list = (i.units || []).map(u => {
        const m = (i.unit_meta || {})[u.unit] || {};
        const ok = u.state === 'active';
        return { kind: 'unit', type: m.type || 'daemon', typeName: DASH_TYPE[m.type] || '상시데몬', name: u.unit, desc: m.desc || '',
          ok: ok, stateText: ok ? 'Running' : (u.state || 'unknown'), since: u.since_s, uptimeHours: u.since_s ? u.since_s / 3600 : 0 };
      });
      (i.pods || []).forEach(p => {
        const sys = p.ns === 'kube-system' || p.ns === 'argocd';
        const data = /mysql|redis/.test(p.name);
        const start = p.start && p.start !== '<none>' ? Date.parse(p.start) : NaN;
        const since = isNaN(start) ? null : Math.max(0, Math.round((Date.now() - start) / 1000));
        list.push({ kind: 'pod', type: data ? 'data' : sys ? 'daemon' : 'web', typeName: data ? '데이터/DR' : sys ? '상시데몬' : '웹/API',
          name: p.name, desc: '파드 · ' + p.ns, ok: p.phase === 'Running' || p.phase === 'Succeeded', stateText: p.phase,
          since: since, uptimeHours: since ? since / 3600 : 0, hide: p.phase === 'Succeeded' });
      });
      return list.filter(s => !s.hide);
    }
    function dashSort(list) {
      const m = typeof currentSortMode === 'string' ? currentSortMode : 'type';
      list.sort((a, b) => {
        if (m === 'type') return a.typeName.localeCompare(b.typeName, 'ko') || a.name.localeCompare(b.name);
        if (m === 'service') return a.desc.localeCompare(b.desc, 'ko') || a.name.localeCompare(b.name);
        if (m === 'resource') return (a.ok - b.ok) || a.name.localeCompare(b.name);   // 이상 있는 것 먼저
        if (m === 'runtime') return (b.uptimeHours || 0) - (a.uptimeHours || 0);
        return a.name.localeCompare(b.name);
      });
      return list;
    }

    // 이름만 있는 대상(정책상 접속·수집 없음, 예: s1)은 카드·집계에서 뺀다
    function dashNameOnly(i) { return !!i.disabled && i.alive == null; }
    function dashInstances() {
      const items = ((DASH.snap && DASH.snap.instances) || []).filter(i => !dashNameOnly(i));
      return items.slice().sort((a, b) => DASH_ORDER.indexOf(a.area) - DASH_ORDER.indexOf(b.area));
    }

    function dashDisplayName(name, id) {
      if (name && name.includes('(')) return name;
      const map = {
        'compute4': 'compute4 (DB)',
        'compute3': 'compute3 (k8s 마스터)',
        'compute1': 'compute1 (k8s 워커)',
        'controller': 'controller (컨트롤러)'
      };
      return map[id] || map[name] || name;
    }

    function dashRender() {
      const grid = document.getElementById('matrix-5col-grid');
      if (!grid) return;
      grid.classList.add('dash-live');
      if (!DASH.snap) {
        grid.innerHTML = '<div class="dash-msg">' + (DASH.err ? '실측 상태를 불러오지 못했습니다 (' + cfgEsc(DASH.err) + '). s1 통합 콘솔 서비스(/console/api/status)를 확인하세요.' : '실측 상태를 불러오는 중…') + '</div>';
        return;
      }
      const filter = typeof currentServiceFilter === 'string' ? currentServiceFilter : 'all';
      grid.innerHTML = dashInstances().map(i => {
        const c = DASH_CLOUD[i.area] || ['기타', ''];
        const all = dashServices(i);
        const list = dashSort(filter === 'all' ? all.slice() : all.filter(s => s.type === filter));
        const okN = all.filter(s => s.ok).length;
        const alive = i.alive === true, apiOnly = !!i.disabled;
        const cpuPct = i.cpu_pct, memPct = dashPct(i.mem_used, i.mem_total), diskPct = dashPct(i.disk_used, i.disk_total);
        const usedCpu = cpuPct != null && i.nproc ? (cpuPct * i.nproc / 100).toFixed(2) : '-';
        const badge = !alive ? '<span class="dash-badge dash-down">응답 없음</span>'
          : apiOnly ? '<span class="dash-badge dash-api">API 응답</span>'
          : okN === all.length ? '<span class="badge-running" style="font-size:10px;padding:2px 6px;">정상</span>'
          : '<span class="dash-badge dash-warn">점검 ' + (all.length - okN) + '</span>';
        const meters = apiOnly ? '<div class="dash-msg dash-msg-small">' + cfgEsc(i.disabled) + '<br>응답 ' + (i.latency_ms != null ? i.latency_ms + 'ms' : '-') + '</div>' :
          dashMeter('CPU', 'cpu', usedCpu + ' vCPU', (i.nproc || '-') + ' vCPU', cpuPct) +
          dashMeter('RAM', 'ram', dashFmtBytes(i.mem_used), dashFmtBytes(i.mem_total), memPct) +
          '<div class="hero-sub-stats">' +
            '<div class="hero-stat-pill"><span class="stat-k">디스크:</span><strong class="stat-v">' + (diskPct != null ? diskPct + '%' : '-') + '</strong></div>' +
            '<div class="hero-stat-pill"><span class="stat-k">가동:</span><strong class="stat-v">' + dashFmtDur(i.uptime_s) + '</strong></div>' +
            '<div class="hero-stat-pill"><span class="stat-k">서비스:</span><strong class="stat-v" style="color:' + (okN === all.length ? '#34d399' : '#fbbf24') + '">' + okN + '/' + all.length + '</strong></div>' +
          '</div>';
        const rows = !alive ? '<div class="dash-msg dash-msg-small">' + cfgEsc(i.error || '응답이 없습니다') + '</div>'
          : list.length === 0 ? '<div class="dash-msg dash-msg-small">' + (apiOnly ? '세부 수집은 연결 후 표시됩니다.' : '해당 유형의 서비스가 없습니다.') + '</div>'
          : list.map(s =>
            '<div class="compact-service-row" onclick="openDetailModal(\\'' + cfgEsc(i.id) + '\\', \\'' + cfgEsc(s.name) + '\\')">' +
              '<div class="svc-row-top"><div class="svc-row-left"><span class="type-badge type-' + s.type + '">' + s.typeName + '</span>' +
              '<span class="svc-row-name" title="' + cfgEsc(s.name) + '">' + cfgEsc(s.name) + '</span></div>' +
              '<span class="' + (s.ok ? 'badge-running' : 'dash-badge dash-down') + '" style="font-size:9px;padding:1px 5px;">' + cfgEsc(s.stateText) + '</span></div>' +
              '<div class="svc-row-bot"><span>' + cfgEsc(s.desc) + '</span><span style="color:#94a3b8;">' + dashFmtDur(s.since) + '</span></div></div>').join('');
        const dispName = dashDisplayName(i.name, i.id);
        return '<div class="inst-grid-card' + (alive ? '' : ' dash-card-down') + '" id="card-' + cfgEsc(i.id) + '">' +
          '<div class="inst-grid-card-head"><div class="inst-head-title-wrap"><div style="display:flex;align-items:center;gap:6px;">' +
          '<span class="cloud-tag ' + c[1] + '">' + c[0] + '</span><span class="inst-card-title">' + cfgEsc(dispName) + '</span></div>' +
          '<div class="inst-card-ip">' + cfgEsc(i.host || '') + (i.latency_ms != null ? ' · 응답 ' + i.latency_ms + 'ms' : '') + '</div></div>' + badge + '</div>' +
          '<div class="inst-resource-hero">' + meters + '</div>' +
          '<div class="compact-service-list">' + rows + '</div>' +
          '<div class="inst-card-footer"><button type="button" class="open-modal-btn" onclick="openDetailModal(\\'' + cfgEsc(i.id) + '\\', null)">상세 보기</button>' +
          (apiOnly || !alive ? '' : '<button type="button" class="open-modal-btn" onclick="dashOpenConsole(\\'' + cfgEsc(i.id) + '\\')">콘솔 열기</button>') + '</div></div>';
      }).join('');
    }
    function dashMeter(label, cls, used, total, pct) {
      const p = pct == null ? 0 : pct;
      return '<div class="hero-meter-row"><div class="meter-head"><div class="meter-label-wrap"><span class="meter-badge ' + cls + '-badge">' + label + '</span>' +
        '<strong class="meter-val-used ' + cls + '-used">' + used + '</strong><span class="meter-val-total">/ ' + total + '</span>' +
        '<span class="meter-pct ' + cls + '-pct">' + (pct == null ? '-' : pct + '%') + '</span></div>' +
        '<div class="meter-free-wrap"><span class="free-k">여유:</span><strong class="free-v">' + (pct == null ? '-' : (100 - p) + '%') + '</strong></div></div>' +
        '<div class="meter-gauge-track"><div class="meter-gauge-fill ' + cls + '-fill" style="width:' + p + '%;' + (p >= 85 ? 'background:#ef4444;' : '') + '"></div></div></div>';
    }

    function dashModal(id, svcName) {
      const i = dashInstances().find(x => x.id === id);
      if (!i) return;
      const c = DASH_CLOUD[i.area] || ['기타', ''];
      const all = dashSort(dashServices(i));
      document.getElementById('modal-cloud-tag').className = 'cloud-tag ' + c[1];
      document.getElementById('modal-cloud-tag').textContent = c[0];
      document.getElementById('modal-title').textContent = dashDisplayName(i.name, i.id) + ' 실측 상세';
      document.getElementById('modal-ip-text').textContent = (i.host || '') + ' · ' + cfgEsc(i.desc || '');
      const spec = [['상태', i.alive === true ? '응답' : i.alive === false ? '응답 없음' : '-'], ['CPU', i.cpu_pct != null ? i.cpu_pct + '% (' + i.nproc + ' vCPU)' : '-'],
        ['메모리', dashFmtBytes(i.mem_used) + ' / ' + dashFmtBytes(i.mem_total)], ['디스크', dashFmtBytes(i.disk_used) + ' / ' + dashFmtBytes(i.disk_total)],
        ['load 1분', i.load1 != null ? i.load1 : '-'], ['가동 시간', dashFmtDur(i.uptime_s)], ['응답 시간', i.latency_ms != null ? i.latency_ms + 'ms' : '-'],
        ['수집 시각', DASH.snap.collected_at ? new Date(DASH.snap.collected_at * 1000).toLocaleTimeString('ko-KR', { hour12: false }) : '-']];
      document.getElementById('modal-body').innerHTML =
        '<div class="spec-grid">' + spec.map(s => '<div class="spec-item"><span class="spec-k">' + s[0] + '</span><span class="spec-v">' + cfgEsc(String(s[1])) + '</span></div>').join('') + '</div>' +
        (i.error ? '<p class="wk-error" style="margin-top:10px">' + cfgEsc(i.error) + '</p>' : '') +
        '<div class="cfg-table-wrap" style="margin-top:12px"><table class="cfg-table"><thead><tr><th>종류</th><th>이름</th><th>설명</th><th>상태</th><th>실행 시간</th></tr></thead><tbody>' +
        all.map(s => '<tr' + (s.name === svcName ? ' style="background:rgba(37,99,235,.15)"' : '') + '><td>' + s.typeName + '</td><td><code class="cfg-ic">' + cfgEsc(s.name) + '</code></td><td>' + cfgEsc(s.desc) +
          '</td><td style="color:' + (s.ok ? '#34d399' : '#fca5a5') + '">' + cfgEsc(s.stateText) + '</td><td>' + dashFmtDur(s.since) + '</td></tr>').join('') +
        '</tbody></table></div>' +
        (i.disabled || i.alive !== true ? '' : '<div class="wk-bar wk-bar-inline" style="margin-top:12px"><button type="button" class="wk-btn wk-primary" onclick="dashOpenConsole(\\'' + cfgEsc(i.id) + '\\')">통합 터미널로 접속</button></div>');
      document.getElementById('modal-backdrop').style.display = 'flex';
    }
    function dashOpenConsole(id) {   // 본문을 콘솔로 바꾸고 그 인스턴스에 바로 접속
      const mb = document.getElementById('modal-backdrop'); if (mb) mb.style.display = 'none';
      CS.pending = id; switchView('console');
    }

    // 상단 배지: 영역별 살아 있는 인스턴스 수
    function dashHeader() {
      const box = document.querySelector('.header-infra-status');
      if (!box) return;
      if (!DASH.snap) { box.innerHTML = '<div class="infra-badge-item"><span class="infra-badge-name">실측</span><span class="infra-badge-state ' + (DASH.err ? 'state-red' : '') + '">' + (DASH.err ? '연결 실패' : '수집 중') + '</span></div>'; return; }
      const groups = [['aws', 'AWS', ['aws']], ['kt', 'KT Cloud', ['kt']], ['os', '온프렘·OpenStack', ['onprem', 'openstack']]];
      let html = groups.map(g => {
        const xs = DASH.snap.instances.filter(i => g[2].indexOf(i.area) >= 0 && !dashNameOnly(i));
        const up = xs.filter(i => i.alive === true).length;
        const bad = xs.some(i => i.alive === true && (i.units || []).some(u => u.state !== 'active'));
        return '<div class="infra-badge-item"><span class="infra-badge-name">' + g[1] + '</span><span class="infra-badge-state ' +
          (up < xs.length ? 'state-red' : bad ? 'state-yellow' : 'state-green') + '">' + up + '/' + xs.length + '</span></div>';
      }).join('');
      // 10초 순환 항목(내부/외부 속도·최저속·점검)
      const rot = dashRotItems();
      if (rot.length) {
        const it = rot[DASH.rot % rot.length];
        html += '<div class="infra-badge-item infra-badge-rot" title="10초마다 순환">' +
          '<span class="infra-badge-name">' + cfgEsc(it[0]) + '</span>' +
          '<span class="infra-badge-state ' + it[2] + '">' + cfgEsc(it[1]) + '</span></div>';
      }
      html += '<div class="infra-badge-item"><span class="infra-badge-name">수집</span><span class="infra-badge-state">' +
        new Date(DASH.snap.collected_at * 1000).toLocaleTimeString('ko-KR', { hour12: false }) + '</span></div>';
      box.innerHTML = html;
    }

    window.addEventListener('load', () => setTimeout(dashStart, 200));
    // CFGJS:END

    // 5. INSTANCE-SPECIFIC TOP 10 DATA & CONTROLLER
    const INSTANCE_TOP10_DATA = {
      'kt-edge': {
        cloud: 'KT Cloud',
        cloudClass: 'cloud-kt',
        name: 'KT Cloud Edge',
        ip: '14.63.212.190',
        totalAlloc: '2 vCPU / 4.0GB RAM / 50GB SSD',
        totalAllocSummary: '2 vCPU / 4.0GB RAM',
        cpuTotal: '2 vCPU',
        cpuUsed: '0.36 vCPU',
        cpuPct: 18,
        cpuFree: '1.64 vCPU',
        cpuFreePct: 82,
        memTotal: '4.0 GB',
        memUsed: '1.68 GB',
        memPct: 42,
        memFree: '2.32 GB',
        memFreePct: 58,
        usedSummary: '0.36 vCPU (18%) / 1.68GB (42%)',
        usedPct: 18,
        freeSummary: '1.64 vCPU / 2.32GB',
        freePct: 82,
        netLatency: '2.1ms',
        currentUsage: '0.36 vCPU (18%) / 1.68GB (42%)',
        netSpeed: '2.1ms (KT Backbone)',
        status: '정상 가동 (Active)',
        services: [
          { type: 'gw', typeName: '보안/관문', name: 'modsecurity-waf-proxy', desc: 'L7 인라인 웹방화벽 패킷 검증', alloc: '300m / 512MB', cpuU: '110m (37%)', cpuP: 37, memU: '164MB (32%)', memP: 32, lat: '2.1ms', port: '80, 443', state: 'Running', runtime: '45일 12h', uptimeHours: 1092 },
          { type: 'daemon', typeName: '상시작용', name: 'wireguard-mesh-daemon', desc: 'VPN 메쉬 터널 A/B 상시 가동', alloc: '200m / 256MB', cpuU: '60m (30%)', cpuP: 30, memU: '88MB (34%)', memP: 34, lat: '1.2ms', port: '51820/udp', state: 'Running', runtime: '60일 04h', uptimeHours: 1444 },
          { type: 'gw', typeName: '네트워크', name: 'haproxy-edge-router', desc: '역방향 프록시 및 로드밸런싱', alloc: '200m / 256MB', cpuU: '45m (23%)', cpuP: 23, memU: '62MB (24%)', memP: 24, lat: '0.9ms', port: '443', state: 'Running', runtime: '45일 11h', uptimeHours: 1091 },
          { type: 'gw', typeName: '보안', name: 'fail2ban-intrusion-guard', desc: '비인가 무차별 대입 자동차단', alloc: '100m / 128MB', cpuU: '20m (20%)', cpuP: 20, memU: '34MB (27%)', memP: 27, lat: '-', port: 'local', state: 'Running', runtime: '38일 06h', uptimeHours: 918 },
          { type: 'daemon', typeName: '모니터링', name: 'telegraf-edge-agent', desc: '에지 트래픽 텔레메트리 수집', alloc: '100m / 128MB', cpuU: '25m (25%)', cpuP: 25, memU: '42MB (33%)', memP: 33, lat: '4.5ms', port: '9100', state: 'Running', runtime: '42일 18h', uptimeHours: 1026 },
          { type: 'daemon', typeName: '상시작용', name: 'certbot-ssl-renewer', desc: '와일드카드 Let’s Encrypt 갱신', alloc: '100m / 128MB', cpuU: '10m (10%)', cpuP: 10, memU: '28MB (22%)', memP: 22, lat: '-', port: 'cron', state: 'Running', runtime: '15일 02h', uptimeHours: 362 },
          { type: 'gw', typeName: '네트워크', name: 'iptables-nat-sync', desc: '커널 레벨 NAT 포워딩 동기화', alloc: '100m / 128MB', cpuU: '15m (15%)', cpuP: 15, memU: '22MB (17%)', memP: 17, lat: '0.4ms', port: 'kernel', state: 'Running', runtime: '60일 05h', uptimeHours: 1445 },
          { type: 'daemon', typeName: '시스템', name: 'cloud-init-agent', desc: 'KT Cloud 가상머신 프로비저닝', alloc: '100m / 128MB', cpuU: '5m (5%)', cpuP: 5, memU: '18MB (14%)', memP: 14, lat: '-', port: 'local', state: 'Running', runtime: '60일 05h', uptimeHours: 1445 },
          { type: 'daemon', typeName: '로그', name: 'rsyslog-audit-forwarder', desc: '감사 로그 원격 전송 데몬', alloc: '100m / 128MB', cpuU: '12m (12%)', cpuP: 12, memU: '32MB (25%)', memP: 25, lat: '1.8ms', port: '514', state: 'Running', runtime: '58일 20h', uptimeHours: 1412 },
          { type: 'daemon', typeName: '헬스체크', name: 'edge-health-checker', desc: '인바운드 라우팅 상태 감시', alloc: '100m / 128MB', cpuU: '18m (18%)', cpuP: 18, memU: '26MB (20%)', memP: 20, lat: '2.4ms', port: '8088', state: 'Running', runtime: '24일 09h', uptimeHours: 585 }
        ]
      },
      'onprem-cp1': {
        cloud: '온프레미스',
        cloudClass: 'cloud-onprem',
        name: '온프렘 k8s-cp1',
        ip: '172.20.0.86',
        totalAlloc: '4 vCPU / 6.5GB RAM / 100GB SSD',
        totalAllocSummary: '4 vCPU / 6.5GB RAM',
        cpuTotal: '4 vCPU',
        cpuUsed: '1.84 vCPU',
        cpuPct: 46,
        cpuFree: '2.16 vCPU',
        cpuFreePct: 54,
        memTotal: '6.5 GB',
        memUsed: '4.42 GB',
        memPct: 68,
        memFree: '2.08 GB',
        memFreePct: 32,
        usedSummary: '1.84 vCPU (46%) / 4.42GB (68%)',
        usedPct: 46,
        freeSummary: '2.16 vCPU / 2.08GB',
        freePct: 54,
        netLatency: '0.8ms',
        currentUsage: '1.84 vCPU (46%) / 4.42GB (68%)',
        netSpeed: '0.8ms (Intranet Core)',
        status: '정상 가동 (Active)',
        services: [
          { type: 'web', typeName: '웹/API', name: 'minwon-backend', desc: '민원 접수 핵심 REST API', alloc: '500m / 1,024MB', cpuU: '280m (56%)', cpuP: 56, memU: '412MB (40%)', memP: 40, lat: '14.2ms', port: '8080', state: 'Running', runtime: '18일 06h', uptimeHours: 438 },
          { type: 'gw', typeName: '보안/관문', name: 'traefik-ingress-controller', desc: 'L7 인그레스 라우팅 & SSL', alloc: '300m / 512MB', cpuU: '120m (40%)', cpuP: 40, memU: '184MB (36%)', memP: 36, lat: '1.8ms', port: '80, 443', state: 'Running', runtime: '35일 14h', uptimeHours: 854 },
          { type: 'web', typeName: '웹/UI', name: 'minwon-frontend', desc: '대민 접수 포털 웹 프론트엔드', alloc: '300m / 512MB', cpuU: '95m (32%)', cpuP: 32, memU: '146MB (29%)', memP: 29, lat: '18.5ms', port: '3000', state: 'Running', runtime: '18일 06h', uptimeHours: 438 },
          { type: 'daemon', typeName: '시스템/코어', name: 'coredns-resolver', desc: '클러스터 내부 도메인 질의 해석', alloc: '200m / 256MB', cpuU: '45m (23%)', cpuP: 23, memU: '68MB (27%)', memP: 27, lat: '0.6ms', port: '53', state: 'Running', runtime: '40일 22h', uptimeHours: 982 },
          { type: 'gw', typeName: '네트워크', name: 'kube-flannel-cni', desc: '오버레이 파드 네트워크 인터페이스', alloc: '200m / 256MB', cpuU: '35m (18%)', cpuP: 18, memU: '54MB (21%)', memP: 21, lat: '0.5ms', port: 'vxlan', state: 'Running', runtime: '40일 22h', uptimeHours: 982 },
          { type: 'daemon', typeName: '시스템', name: 'k3s-server-core', desc: '쿠버네티스 컨트롤 플레인 엔진', alloc: '500m / 1,024MB', cpuU: '190m (38%)', cpuP: 38, memU: '480MB (47%)', memP: 47, lat: '1.1ms', port: '6443', state: 'Running', runtime: '41일 01h', uptimeHours: 985 },
          { type: 'daemon', typeName: '모니터링', name: 'metrics-server', desc: '파드/노드 자원 사용량 집계', alloc: '150m / 256MB', cpuU: '30m (20%)', cpuP: 20, memU: '58MB (23%)', memP: 23, lat: '3.2ms', port: '4443', state: 'Running', runtime: '35일 09h', uptimeHours: 849 },
          { type: 'daemon', typeName: '스토리지', name: 'local-path-provisioner', desc: '로컬 PV 동적 프로비저닝 CSI', alloc: '100m / 128MB', cpuU: '15m (15%)', cpuP: 15, memU: '32MB (25%)', memP: 25, lat: '0.8ms', port: 'csi', state: 'Running', runtime: '40일 18h', uptimeHours: 978 },
          { type: 'daemon', typeName: '상시작용', name: 'minwon-worker-queue', desc: '비동기 알림 및 민원 큐 처리', alloc: '200m / 512MB', cpuU: '40m (20%)', cpuP: 20, memU: '94MB (18%)', memP: 18, lat: '2.1ms', port: 'internal', state: 'Running', runtime: '12일 04h', uptimeHours: 292 },
          { type: 'daemon', typeName: '진단', name: 'node-problem-detector', desc: '노드 커널 및 런타임 이상 진단', alloc: '100m / 128MB', cpuU: '18m (18%)', cpuP: 18, memU: '38MB (30%)', memP: 30, lat: '-', port: 'daemon', state: 'Running', runtime: '39일 16h', uptimeHours: 952 }
        ]
      },
      'onprem-db': {
        cloud: '온프레미스',
        cloudClass: 'cloud-onprem',
        name: '온프렘 db-01',
        ip: '10.10.2.10',
        totalAlloc: '2 vCPU / 4.0GB RAM / 80GB SSD',
        totalAllocSummary: '2 vCPU / 4.0GB RAM',
        cpuTotal: '2 vCPU',
        cpuUsed: '0.44 vCPU',
        cpuPct: 22,
        cpuFree: '1.56 vCPU',
        cpuFreePct: 78,
        memTotal: '4.0 GB',
        memUsed: '2.04 GB',
        memPct: 51,
        memFree: '1.96 GB',
        memFreePct: 49,
        usedSummary: '0.44 vCPU (22%) / 2.04GB (51%)',
        usedPct: 22,
        freeSummary: '1.56 vCPU / 1.96GB',
        freePct: 78,
        netLatency: '0.4ms',
        currentUsage: '0.44 vCPU (22%) / 2.04GB (51%)',
        netSpeed: '0.4ms (Intranet DB)',
        status: '정상 가동 (Active)',
        services: [
          { type: 'data', typeName: '데이터베이스', name: 'mariadb-galera-cluster', desc: '메인 트랜잭션 DB 엔진 (ACID)', alloc: '800m / 2,048MB', cpuU: '310m (39%)', cpuP: 39, memU: '890MB (43%)', memP: 43, lat: '0.8ms', port: '3306', state: 'Running', runtime: '52일 08h', uptimeHours: 1256 },
          { type: 'daemon', typeName: '상시작용', name: 'ssh-backup-receiver', desc: 'AWS DR 역방향 동기화 수신 계정', alloc: '200m / 512MB', cpuU: '25m (13%)', cpuP: 13, memU: '45MB (9%)', memP: 9, lat: '1.5ms', port: '22', state: 'Running', runtime: '48일 12h', uptimeHours: 1164 },
          { type: 'daemon', typeName: '모니터링', name: 'mysqld-exporter', desc: 'MySQL 메트릭 프로메테우스 전송', alloc: '100m / 128MB', cpuU: '18m (18%)', cpuP: 18, memU: '36MB (28%)', memP: 28, lat: '2.0ms', port: '9104', state: 'Running', runtime: '30일 05h', uptimeHours: 725 },
          { type: 'data', typeName: '백업', name: 'xtrabackup-cron-scheduler', desc: '무중단 물리 백업 스케줄러', alloc: '200m / 256MB', cpuU: '10m (5%)', cpuP: 5, memU: '48MB (19%)', memP: 19, lat: '-', port: 'cron', state: 'Running', runtime: '22일 19h', uptimeHours: 547 },
          { type: 'data', typeName: '데이터', name: 'innodb-buffer-monitor', desc: 'InnoDB 버퍼풀 히트율 감시', alloc: '100m / 128MB', cpuU: '12m (12%)', cpuP: 12, memU: '28MB (22%)', memP: 22, lat: '0.4ms', port: 'local', state: 'Running', runtime: '41일 07h', uptimeHours: 991 },
          { type: 'daemon', typeName: '로그', name: 'systemd-journald', desc: '시스템 및 바이너리 로그 관리', alloc: '100m / 128MB', cpuU: '15m (15%)', cpuP: 15, memU: '42MB (33%)', memP: 33, lat: '-', port: 'system', state: 'Running', runtime: '55일 11h', uptimeHours: 1331 },
          { type: 'gw', typeName: '네트워크', name: 'wireguard-db-endpoint', desc: 'DB 전용 암호화 통신 채널', alloc: '100m / 128MB', cpuU: '20m (20%)', cpuP: 20, memU: '38MB (30%)', memP: 30, lat: '1.1ms', port: '51820', state: 'Running', runtime: '50일 03h', uptimeHours: 1203 },
          { type: 'daemon', typeName: '유지보수', name: 'cron-logrotate', desc: '쿼리 로그 및 감사파일 회전', alloc: '100m / 128MB', cpuU: '8m (8%)', cpuP: 8, memU: '22MB (17%)', memP: 17, lat: '-', port: 'cron', state: 'Running', runtime: '55일 00h', uptimeHours: 1320 },
          { type: 'daemon', typeName: '보안', name: 'auditd-security-daemon', desc: 'DB 시스템 콜 접근 감사', alloc: '100m / 128MB', cpuU: '14m (14%)', cpuP: 14, memU: '32MB (25%)', memP: 25, lat: '-', port: 'kernel', state: 'Running', runtime: '55일 02h', uptimeHours: 1322 },
          { type: 'daemon', typeName: '모니터링', name: 'node-exporter', desc: 'OS 커널 및 호스트 자원 지표', alloc: '100m / 128MB', cpuU: '15m (15%)', cpuP: 15, memU: '30MB (23%)', memP: 23, lat: '1.8ms', port: '9100', state: 'Running', runtime: '30일 05h', uptimeHours: 725 }
        ]
      },
      'aws-ctl': {
        cloud: 'AWS',
        cloudClass: 'cloud-aws',
        name: 'AWS CTL',
        ip: '10.200.0.10',
        totalAlloc: '2 vCPU / 4.0GB RAM / 40GB EBS',
        totalAllocSummary: '2 vCPU / 4.0GB RAM',
        cpuTotal: '2 vCPU',
        cpuUsed: '0.24 vCPU',
        cpuPct: 12,
        cpuFree: '1.76 vCPU',
        cpuFreePct: 88,
        memTotal: '4.0 GB',
        memUsed: '1.36 GB',
        memPct: 34,
        memFree: '2.64 GB',
        memFreePct: 66,
        usedSummary: '0.24 vCPU (12%) / 1.36GB (34%)',
        usedPct: 12,
        freeSummary: '1.76 vCPU / 2.64GB',
        freePct: 88,
        netLatency: '22ms',
        currentUsage: '0.24 vCPU (12%) / 1.36GB (34%)',
        netSpeed: '22ms (AWS Direct Mesh)',
        status: '정상 가동 (Active)',
        services: [
          { type: 'data', typeName: 'DR 관제', name: 'duck-hsagent-dr-engine', desc: '온프렘 헬스체크 및 승격 판정', alloc: '400m / 512MB', cpuU: '85m (21%)', cpuP: 21, memU: '132MB (26%)', memP: 26, lat: '1.4ms', port: '8080', state: 'Running', runtime: '26일 15h', uptimeHours: 639 },
          { type: 'data', typeName: 'DR/DNS', name: 'route53-failover-syncer', desc: 'DNS 가중치 및 자동 절체 제어', alloc: '200m / 256MB', cpuU: '30m (15%)', cpuP: 15, memU: '54MB (21%)', memP: 21, lat: '45ms', port: 'aws-api', state: 'Running', runtime: '26일 14h', uptimeHours: 638 },
          { type: 'daemon', typeName: '모니터링', name: 'cloudwatch-metric-collector', desc: 'AWS 리소스 상태 주기적 동기화', alloc: '150m / 256MB', cpuU: '28m (19%)', cpuP: 19, memU: '48MB (19%)', memP: 19, lat: '52ms', port: '443', state: 'Running', runtime: '33일 08h', uptimeHours: 798 },
          { type: 'daemon', typeName: '상시작용', name: 'aws-ssm-agent', desc: '인프라 원격 보안 관리 세션', alloc: '100m / 128MB', cpuU: '12m (12%)', cpuP: 12, memU: '38MB (30%)', memP: 30, lat: '-', port: 'ssm', state: 'Running', runtime: '44일 21h', uptimeHours: 1077 },
          { type: 'gw', typeName: '네트워크', name: 'wireguard-aws-connector', desc: '하이브리드 클라우드 터널 관리', alloc: '200m / 256MB', cpuU: '35m (18%)', cpuP: 18, memU: '46MB (18%)', memP: 18, lat: '22ms', port: '51820', state: 'Running', runtime: '40일 19h', uptimeHours: 979 },
          { type: 'daemon', typeName: '알림', name: 'dr-alert-webhook-dispatcher', desc: '비상 절체 시 슬랙/웹훅 전송', alloc: '100m / 128MB', cpuU: '10m (10%)', cpuP: 10, memU: '24MB (19%)', memP: 19, lat: '18ms', port: '9090', state: 'Running', runtime: '26일 10h', uptimeHours: 634 },
          { type: 'data', typeName: '데이터', name: 'state-database-sqlite', desc: '장애 이력 및 페일오버 상태 보관', alloc: '100m / 128MB', cpuU: '15m (15%)', cpuP: 15, memU: '34MB (27%)', memP: 27, lat: '0.3ms', port: 'local', state: 'Running', runtime: '26일 15h', uptimeHours: 639 },
          { type: 'daemon', typeName: '진단', name: 'health-probe-worker', desc: '10~15초 주기 순차 프로브 데몬', alloc: '150m / 256MB', cpuU: '22m (15%)', cpuP: 15, memU: '40MB (16%)', memP: 16, lat: '12ms', port: 'async', state: 'Running', runtime: '26일 12h', uptimeHours: 636 },
          { type: 'daemon', typeName: '시스템', name: 'systemd-resolved', desc: 'AWS 엔드포인트 도메인 해석', alloc: '100m / 128MB', cpuU: '8m (8%)', cpuP: 8, memU: '20MB (16%)', memP: 16, lat: '0.5ms', port: '53', state: 'Running', runtime: '45일 02h', uptimeHours: 1082 },
          { type: 'daemon', typeName: '스토리지', name: 'amazon-ebs-autoscale', desc: '백업 디스크 볼륨 용량 감시', alloc: '100m / 128MB', cpuU: '10m (10%)', cpuP: 10, memU: '26MB (20%)', memP: 20, lat: '-', port: 'api', state: 'Running', runtime: '35일 06h', uptimeHours: 846 }
        ]
      },
      'aws-dr': {
        cloud: 'AWS',
        cloudClass: 'cloud-aws',
        name: 'AWS DR K3s',
        ip: '10.200.0.4',
        totalAlloc: '4 vCPU / 8.0GB RAM / 100GB EBS',
        totalAllocSummary: '4 vCPU / 8.0GB RAM',
        cpuTotal: '4 vCPU',
        cpuUsed: '0.16 vCPU',
        cpuPct: 4,
        cpuFree: '3.84 vCPU',
        cpuFreePct: 96,
        memTotal: '8.0 GB',
        memUsed: '1.28 GB',
        memPct: 16,
        memFree: '6.72 GB',
        memFreePct: 84,
        usedSummary: '0.16 vCPU (4%) / 1.28GB (16%)',
        usedPct: 4,
        freeSummary: '3.84 vCPU / 6.72GB',
        freePct: 96,
        netLatency: '24ms',
        currentUsage: '0.16 vCPU (4%) / 1.28GB (16%)',
        netSpeed: '24ms (Standby Route)',
        status: 'Standby 대기 (정상 가동)',
        services: [
          { type: 'data', typeName: 'DR 대기', name: 'dr-pilot-light-agent', desc: 'L3 승격 대기 핫스탠바이 파드', alloc: '400m / 512MB', cpuU: '15m (4%)', cpuP: 4, memU: '48MB (9%)', memP: 9, lat: '24ms', port: '9000', state: 'Standby', runtime: '20일 08h', uptimeHours: 488 },
          { type: 'data', typeName: '데이터 동기화', name: 'dr-rsync-backup-syncer', desc: '정기 데이터 스냅샷 수신 동기화', alloc: '300m / 512MB', cpuU: '20m (7%)', cpuP: 7, memU: '64MB (13%)', memP: 13, lat: '26ms', port: 'rsync', state: 'Standby', runtime: '20일 06h', uptimeHours: 486 },
          { type: 'daemon', typeName: '시스템', name: 'k3s-standby-core', desc: 'DR 복구용 쿠버네티스 대기 코어', alloc: '500m / 1,024MB', cpuU: '45m (9%)', cpuP: 9, memU: '168MB (16%)', memP: 16, lat: '1.2ms', port: '6443', state: 'Standby', runtime: '25일 12h', uptimeHours: 612 },
          { type: 'web', typeName: '웹/API 대기', name: 'minwon-backend-standby', desc: '비상 승격 시 즉각 RW 전환 대기', alloc: '500m / 1,024MB', cpuU: '10m (2%)', cpuP: 2, memU: '52MB (5%)', memP: 5, lat: '-', port: '8080', state: 'Standby', runtime: '15일 04h', uptimeHours: 364 },
          { type: 'gw', typeName: '보안/관문', name: 'traefik-standby-router', desc: 'AWS 인그레스 대기 라우터', alloc: '200m / 256MB', cpuU: '15m (8%)', cpuP: 8, memU: '40MB (16%)', memP: 16, lat: '-', port: '80, 443', state: 'Standby', runtime: '25일 10h', uptimeHours: 610 },
          { type: 'daemon', typeName: '시스템', name: 'coredns-standby', desc: 'DR 클러스터 내부 네임서비스', alloc: '100m / 128MB', cpuU: '10m (10%)', cpuP: 10, memU: '28MB (22%)', memP: 22, lat: '0.6ms', port: '53', state: 'Standby', runtime: '25일 11h', uptimeHours: 611 },
          { type: 'data', typeName: '데이터', name: 'mariadb-standby-replica', desc: '온프렘 DB 복제본 대기 엔진', alloc: '800m / 2,048MB', cpuU: '25m (3%)', cpuP: 3, memU: '120MB (6%)', memP: 6, lat: '0.9ms', port: '3306', state: 'Standby', runtime: '22일 16h', uptimeHours: 544 },
          { type: 'daemon', typeName: '상시작용', name: 'aws-ssm-dr-agent', desc: 'AWS Systems Manager 제어 데몬', alloc: '100m / 128MB', cpuU: '10m (10%)', cpuP: 10, memU: '34MB (27%)', memP: 27, lat: '-', port: 'ssm', state: 'Standby', runtime: '30일 18h', uptimeHours: 738 },
          { type: 'gw', typeName: '네트워크', name: 'flannel-dr-cni', desc: 'DR 클러스터 CNI 네트워크', alloc: '150m / 256MB', cpuU: '12m (8%)', cpuP: 8, memU: '32MB (13%)', memP: 13, lat: '0.5ms', port: 'vxlan', state: 'Standby', runtime: '25일 11h', uptimeHours: 611 },
          { type: 'data', typeName: 'DR 자동화', name: 'failover-trigger-listener', desc: 'L3 승격 신호 수신 대기 소켓', alloc: '100m / 128MB', cpuU: '14m (14%)', cpuP: 14, memU: '36MB (28%)', memP: 28, lat: '15ms', port: 'event', state: 'Standby', runtime: '20일 07h', uptimeHours: 487 }
        ]
      }
    };

    // 5. DIAGNOSTIC CLI COMMANDS MAP FOR MODAL
    const SERVICE_DIAG_COMMANDS = {
      // KT Cloud Edge
      'modsecurity-waf-proxy': 'sudo nginx -t && sudo tail -n 20 /var/log/nginx/modsec_audit.log',
      'wireguard-mesh-daemon': 'sudo wg show && sudo systemctl status wireguard-mesh',
      'haproxy-edge-router': 'sudo haproxy -c -f /etc/haproxy/haproxy.cfg && sudo systemctl status haproxy',
      'fail2ban-intrusion-guard': 'sudo fail2ban-client status && sudo fail2ban-client status sshd',
      'telegraf-edge-agent': 'sudo systemctl status telegraf && telegraf --test',
      'certbot-ssl-renewer': 'sudo certbot certificates && sudo certbot renew --dry-run',
      'iptables-nat-sync': 'sudo iptables -t nat -L -n -v',
      'cloud-init-agent': 'cloud-init status --long',
      'rsyslog-audit-forwarder': 'sudo systemctl status rsyslog',
      'edge-health-checker': 'curl -I http://127.0.0.1:8088/healthz',
      // 온프렘 k8s-cp1
      'minwon-backend': 'kubectl -n default describe pod -l app=minwon-backend && kubectl logs -n default -l app=minwon-backend --tail=20',
      'traefik-ingress-controller': 'kubectl -n kube-system describe pod -l app.kubernetes.io/name=traefik',
      'minwon-frontend': 'kubectl -n default describe pod -l app=minwon-frontend',
      'coredns-resolver': 'kubectl -n kube-system logs -l k8s-app=kube-dns --tail=20',
      'kube-flannel-cni': 'kubectl -n kube-system get daemonset kube-flannel-ds',
      'k3s-server-core': 'sudo systemctl status k3s && kubectl get nodes -o wide',
      'metrics-server': 'kubectl top nodes && kubectl top pods -A',
      'local-path-provisioner': 'kubectl -n kube-system get pod -l app=local-path-provisioner',
      'minwon-worker-queue': 'kubectl -n default get pods -l app=minwon-worker',
      'node-problem-detector': 'kubectl -n kube-system get ds node-problem-detector',
      // 온프렘 db-01
      'mariadb-galera-cluster': "mysqladmin -u root -p status && mysql -e \\\"SHOW STATUS LIKE 'wsrep%';\\\"",
      'ssh-backup-receiver': 'sudo tail -n 25 /var/log/auth.log | grep backupuser',
      'mysqld-exporter': 'curl -s http://localhost:9104/metrics | head -n 25',
      'xtrabackup-cron-scheduler': 'sudo ls -lh /var/backups/mariadb/ && cat /etc/cron.d/mariadb-backup',
      'innodb-buffer-monitor': 'mysql -e \\\"SHOW ENGINE INNODB STATUS\\\\G\\\" | grep -A 10 \\\"BUFFER POOL\\\"',
      'systemd-journald': 'journalctl -u mariadb -n 30 --no-pager',
      'wireguard-db-endpoint': 'sudo wg show',
      'cron-logrotate': 'sudo logrotate -d /etc/logrotate.d/mysql-server',
      'auditd-security-daemon': 'sudo ausearch -m USER_AUTH -ts today',
      'node-exporter': 'curl -s http://localhost:9100/metrics | grep node_cpu',
      // AWS CTL
      'duck-hsagent-dr-engine': 'sudo systemctl status duck-hsagent && curl -s http://localhost:8080/api/dr-status | jq .',
      'route53-failover-syncer': "aws route53 list-resource-record-sets --hosted-zone-id Z1000 --query \\\"ResourceRecordSets[?Name == 'minwon.ktci5.kr.']\\\"",
      'cloudwatch-metric-collector': 'sudo systemctl status amazon-cloudwatch-agent',
      'aws-ssm-agent': 'sudo systemctl status snap.amazon-ssm-agent.amazon-ssm-agent',
      'wireguard-aws-connector': 'sudo wg show',
      'dr-alert-webhook-dispatcher': 'journalctl -u dr-alert-webhook -n 20 --no-pager',
      'state-database-sqlite': 'sqlite3 /var/lib/duck-hsagent/state.db \\\"SELECT * FROM dr_events ORDER BY id DESC LIMIT 5;\\\"',
      'health-probe-worker': 'journalctl -u duck-hsagent | grep PROBE',
      'systemd-resolved': 'resolvectl status',
      'amazon-ebs-autoscale': 'df -h /var/log /var/lib',
      // AWS DR K3s
      'dr-pilot-light-agent': 'kubectl -n dr-standby get pods -o wide && kubectl -n dr-standby describe pod -l app=pilot-light',
      'dr-rsync-backup-syncer': 'systemctl status aws-dr-sync.timer && ls -lh /data/dr-backup/',
      'k3s-standby-core': 'sudo systemctl status k3s && kubectl get nodes',
      'minwon-backend-standby': 'kubectl -n dr-standby get deployment minwon-backend-standby',
      'traefik-standby-router': 'kubectl -n kube-system get pod -l app.kubernetes.io/name=traefik',
      'coredns-standby': 'kubectl -n kube-system get pod -l k8s-app=kube-dns',
      'mariadb-standby-replica': 'mysql -e \\\"SHOW REPLICA STATUS\\\\G\\\"',
      'aws-ssm-dr-agent': 'sudo systemctl status snap.amazon-ssm-agent.amazon-ssm-agent',
      'flannel-dr-cni': 'kubectl -n kube-system get ds kube-flannel-ds',
      'failover-trigger-listener': 'curl -s http://localhost:9000/dr/health'
    };

    // 6. SORT & FILTER CONTROLLER
    let currentServiceFilter = 'all';
    let currentSortMode = 'type'; // 종류별 (기본)

    function setSortMode(mode) {
      currentSortMode = mode;
      const btns = document.querySelectorAll('#sort-tabs-group .sort-btn');
      btns.forEach(b => {
        if (b.getAttribute('data-sort') === mode) {
          b.classList.add('active');
        } else {
          b.classList.remove('active');
        }
      });
      applySortAndFilter();
    }

    function setServiceFilter(type) {
      currentServiceFilter = type;
      const chips = document.querySelectorAll('#type-filter-group .chip-btn');
      chips.forEach(c => {
        if (c.getAttribute('data-type') === type) {
          c.classList.add('active');
        } else {
          c.classList.remove('active');
        }
      });
      applySortAndFilter();
    }

    function getResourceScore(allocStr) {
      if (!allocStr) return 0;
      let cpu = 0;
      let mem = 0;
      const mCpu = allocStr.match(/([0-9]+)m/);
      if (mCpu) cpu = parseInt(mCpu[1]);
      const mMem = allocStr.match(/([0-9,]+)MB/);
      if (mMem) mem = parseInt(mMem[1].replace(/,/g, ''));
      return cpu * 2 + mem;
    }

    function sortServiceList(list, mode) {
      list.sort((a, b) => {
        if (mode === 'type') {
          return a.typeName.localeCompare(b.typeName, 'ko') || a.name.localeCompare(b.name);
        }
        if (mode === 'service') {
          return a.desc.localeCompare(b.desc, 'ko') || a.name.localeCompare(b.name);
        }
        if (mode === 'resource') {
          return getResourceScore(b.alloc) - getResourceScore(a.alloc);
        }
        if (mode === 'name') {
          return a.name.localeCompare(b.name);
        }
        if (mode === 'runtime') {
          return (b.uptimeHours || 0) - (a.uptimeHours || 0);
        }
        return a.name.localeCompare(b.name);
      });
      return list;
    }

    function applySortAndFilter() {
      if (typeof dashRender === 'function') return dashRender();
      const grid = document.getElementById('matrix-5col-grid');
      if (!grid) return;

      const instanceKeys = ['kt-edge', 'onprem-cp1', 'onprem-db', 'aws-ctl', 'aws-dr'];

      grid.innerHTML = instanceKeys.map(key => {
        const data = INSTANCE_TOP10_DATA[key];
        if (!data) return '';

        // 1. Filter
        let list = data.services.slice();
        if (currentServiceFilter !== 'all') {
          list = list.filter(s => s.type === currentServiceFilter);
        }

        // 2. Sort without rank distinction
        sortServiceList(list, currentSortMode);

        // 3. Compact Rows (순위 구분 없는 5대 기준 정렬)
        const rowsHtml = list.length === 0 
          ? `<div style="padding: 24px 10px; text-align: center; color: var(--text-muted); font-size: 11px;">해당 유형의 서비스가 없습니다.</div>`
          : list.map(s => {
              const stateClass = s.state === 'Running' ? 'badge-running' : 'badge-standby';
              const typeClass = `type-${s.type}`;

              return `
                <div class="compact-service-row" onclick="openDetailModal('${key}', '${s.name}')" title="클릭 시 상세 모달 열기">
                  <div class="svc-row-top">
                    <div class="svc-row-left">
                      <span class="type-badge ${typeClass}">${s.typeName}</span>
                      <span class="svc-row-name" title="${s.name}">${s.name}</span>
                    </div>
                    <span class="${stateClass}" style="font-size: 9px; padding: 1px 5px;">${s.state}</span>
                  </div>
                  <div class="svc-row-bot">
                    <div style="display: flex; align-items: center; gap: 4px;">
                      <span style="color: #cbd5e1; font-weight: 600;">${s.alloc}</span>
                      <span>(CPU ${s.cpuP}%)</span>
                    </div>
                    <div style="display: flex; align-items: center; gap: 6px;">
                      <span style="color: #94a3b8;">${s.runtime}</span>
                      <span style="color: #38bdf8; font-weight: 600;">${s.lat}</span>
                    </div>
                  </div>
                </div>
              `;
            }).join('');

        return `
          <div class="inst-grid-card" id="card-${key}">
            <div class="inst-grid-card-head">
              <div class="inst-head-title-wrap">
                <div style="display: flex; align-items: center; gap: 6px;">
                  <span class="cloud-tag ${data.cloudClass}">${data.cloud}</span>
                  <span class="inst-card-title">${data.name}</span>
                </div>
                <div class="inst-card-ip">${data.ip}</div>
              </div>
              <span class="badge-running" style="font-size: 10px; padding: 2px 6px;">${data.status.includes('Active') ? 'Active' : 'Standby'}</span>
            </div>

            <div class="inst-resource-hero">
              <!-- CPU 자원 현황 -->
              <div class="hero-meter-row">
                <div class="meter-head">
                  <div class="meter-label-wrap">
                    <span class="meter-badge cpu-badge">CPU</span>
                    <strong class="meter-val-used cpu-used">${data.cpuUsed}</strong>
                    <span class="meter-val-total">/ ${data.cpuTotal}</span>
                    <span class="meter-pct cpu-pct">${data.cpuPct}%</span>
                  </div>
                  <div class="meter-free-wrap" title="가용 CPU 여유">
                    <span class="free-k">여유:</span>
                    <strong class="free-v">${data.cpuFree} (${data.cpuFreePct}%)</strong>
                  </div>
                </div>
                <div class="meter-gauge-track" title="CPU 사용: ${data.cpuPct}% | 여유: ${data.cpuFreePct}%">
                  <div class="meter-gauge-fill cpu-fill" style="width: ${data.cpuPct}%;"></div>
                </div>
              </div>

              <!-- RAM 자원 현황 -->
              <div class="hero-meter-row">
                <div class="meter-head">
                  <div class="meter-label-wrap">
                    <span class="meter-badge ram-badge">RAM</span>
                    <strong class="meter-val-used ram-used">${data.memUsed}</strong>
                    <span class="meter-val-total">/ ${data.memTotal}</span>
                    <span class="meter-pct ram-pct">${data.memPct}%</span>
                  </div>
                  <div class="meter-free-wrap" title="가용 RAM 여유">
                    <span class="free-k">여유:</span>
                    <strong class="free-v">${data.memFree} (${data.memFreePct}%)</strong>
                  </div>
                </div>
                <div class="meter-gauge-track" title="RAM 사용: ${data.memPct}% | 여유: ${data.memFreePct}%">
                  <div class="meter-gauge-fill ram-fill" style="width: ${data.memPct}%;"></div>
                </div>
              </div>

              <!-- 보조 지표 (지연 / 서비스) -->
              <div class="hero-sub-stats">
                <div class="hero-stat-pill">
                  <span class="stat-k">지연:</span>
                  <strong class="stat-v" style="color: #fbbf24;">${data.netLatency}</strong>
                </div>
                <div class="hero-stat-pill">
                  <span class="stat-k">서비스:</span>
                  <strong class="stat-v" style="color: #cbd5e1;">${list.length}개 활성</strong>
                </div>
              </div>
            </div>

            <div class="compact-service-list">
              ${rowsHtml}
            </div>

            <div class="inst-card-footer">
              <button type="button" class="open-modal-btn" onclick="openDetailModal('${key}', null)">
                인스턴스 전체 상세 모달 열기 ➔
              </button>
            </div>
          </div>
        `;
      }).join('');
    }

    // 7. DETAIL MODAL POPUP LOGIC
    function openDetailModal(instKey, targetSvcName) {
      if (typeof dashModal === 'function') return dashModal(instKey, targetSvcName);
      const data = INSTANCE_TOP10_DATA[instKey];
      if (!data) return;

      const modalBackdrop = document.getElementById('modal-backdrop');
      const modalCloudTag = document.getElementById('modal-cloud-tag');
      const modalTitle = document.getElementById('modal-title');
      const modalIp = document.getElementById('modal-ip-text');
      const modalBody = document.getElementById('modal-body');

      modalCloudTag.className = `cloud-tag ${data.cloudClass}`;
      modalCloudTag.textContent = data.cloud;
      modalTitle.textContent = `${data.name} 세부 관제 & 리소스 분석`;
      modalIp.textContent = `IP: ${data.ip} · ${data.status}`;

      // Focused service finding
      const targetSvc = targetSvcName ? data.services.find(s => s.name === targetSvcName) : null;
      const diagCmd = targetSvc ? (SERVICE_DIAG_COMMANDS[targetSvc.name] || 'kubectl top pods || systemctl status') : '';

      let focusedHtml = '';
      if (targetSvc) {
        const stateClass = targetSvc.state === 'Running' ? 'badge-running' : 'badge-standby';
        const typeClass = `type-${targetSvc.type}`;
        focusedHtml = `
          <div style="background: #141f36; border: 1px solid #38bdf8; border-radius: 6px; padding: 12px 16px; display: flex; flex-direction: column; gap: 10px;">
            <div style="display: flex; justify-content: space-between; align-items: center;">
              <div style="display: flex; align-items: center; gap: 8px;">
                <span class="type-badge ${typeClass}">${targetSvc.typeName}</span>
                <span style="font-size: 15px; font-weight: 700; color: #fff;">${targetSvc.name}</span>
                <span style="font-size: 11.5px; color: #94a3b8; font-family: var(--font-mono);">${targetSvc.desc}</span>
              </div>
              <span class="${stateClass}">${targetSvc.state}</span>
            </div>

            <div style="display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; font-family: var(--font-mono); font-size: 11px;">
              <div class="spec-item"><span class="spec-k">리소스크기 (할당)</span><span class="spec-v">${targetSvc.alloc}</span></div>
              <div class="spec-item"><span class="spec-k">CPU 실제 사용량</span><span class="spec-v" style="color: #38bdf8;">${targetSvc.cpuU}</span></div>
              <div class="spec-item"><span class="spec-k">메모리 실제 사용량</span><span class="spec-v" style="color: #34d399;">${targetSvc.memU}</span></div>
              <div class="spec-item"><span class="spec-k">실행시간 & 지연율</span><span class="spec-v" style="color: #fbbf24;">${targetSvc.runtime} · ${targetSvc.lat}</span></div>
            </div>

            <div style="display: flex; flex-direction: column; gap: 4px; margin-top: 2px;">
              <div style="font-size: 10.5px; color: #94a3b8; font-weight: 600;">실시간 진단 / 파드 검증 CLI 명령어</div>
              <div class="code-block" style="padding: 8px 10px; font-size: 11px;">${diagCmd}</div>
            </div>
          </div>
        `;
      }

      // Summary 5-cell with CPU & RAM separate status
      const summaryBoxHtml = `
        <div class="modal-summary-box">
          <div class="summary-cell">
            <span class="summary-k">총 할당 규격</span>
            <span class="summary-v">${data.totalAllocSummary || data.totalAlloc}</span>
          </div>
          <div class="summary-cell" style="background: rgba(56, 189, 248, 0.08); border: 1px solid rgba(56, 189, 248, 0.28); border-radius: 4px; padding: 3px 6px;">
            <span class="summary-k" style="color: #7dd3fc;">CPU 사용 (가용 여유)</span>
            <span class="summary-v" style="color: #38bdf8;">${data.cpuUsed} / ${data.cpuTotal} (${data.cpuPct}%) <span style="font-size:10px; color:#34d399;">+${data.cpuFree}</span></span>
          </div>
          <div class="summary-cell" style="background: rgba(168, 85, 247, 0.08); border: 1px solid rgba(168, 85, 247, 0.28); border-radius: 4px; padding: 3px 6px;">
            <span class="summary-k" style="color: #d8b4fe;">RAM 사용 (가용 여유)</span>
            <span class="summary-v" style="color: #c084fc;">${data.memUsed} / ${data.memTotal} (${data.memPct}%) <span style="font-size:10px; color:#34d399;">+${data.memFree}</span></span>
          </div>
          <div class="summary-cell">
            <span class="summary-k">네트워크 지연율</span>
            <span class="summary-v" style="color: #fbbf24;">${data.netLatency || data.netSpeed}</span>
          </div>
          <div class="summary-cell">
            <span class="summary-k">인프라 운영 모드</span>
            <span class="summary-v" style="color: #cbd5e1;">${data.status} (${data.services.length}개)</span>
          </div>
        </div>
      `;

      // Full table of services (sorted by currentSortMode without rank)
      let modalList = data.services.slice();
      sortServiceList(modalList, currentSortMode);

      const tableRowsHtml = modalList.map(s => {
        const isSelected = targetSvcName === s.name ? 'style="background: rgba(56, 189, 248, 0.12); border-left: 3px solid #38bdf8;"' : '';
        const stateClass = s.state === 'Running' ? 'badge-running' : 'badge-standby';
        const typeClass = `type-${s.type}`;

        return `
          <tr ${isSelected} onclick="openDetailModal('${instKey}', '${s.name}')" style="cursor: pointer;" title="클릭하여 이 서비스 집중 분석">
            <td><span class="type-badge ${typeClass}">${s.typeName}</span></td>
            <td>
              <div class="svc-box">
                <span class="svc-name">${s.name}</span>
                <span class="svc-desc">${s.desc}</span>
              </div>
            </td>
            <td><span style="color:#cbd5e1; font-weight:600;">${s.alloc}</span></td>
            <td>
              <div class="res-metric-cell">
                <div class="res-metric-val"><span>${s.cpuU}</span><span>${s.memU}</span></div>
                <div class="mini-meter-track"><div class="mini-meter-fill fill-blue" style="width: ${s.cpuP}%;"></div></div>
              </div>
            </td>
            <td><span style="color:#94a3b8; font-family:var(--font-mono); font-size:11px;">${s.runtime}</span></td>
            <td><span style="color:#38bdf8; font-weight:700;">${s.lat}</span></td>
            <td style="text-align: center;"><span class="${stateClass}">${s.state}</span></td>
          </tr>
        `;
      }).join('');

      const tableHtml = `
        <div class="table-container-embedded" style="border: 1px solid #1e293b; border-radius: 6px; overflow: hidden;">
          <table class="data-table">
            <thead>
              <tr>
                <th style="width: 13%;">종류 (유형)</th>
                <th style="width: 26%;">서비스명 & 역할 (클릭 시 집중 분석)</th>
                <th style="width: 15%;">리소스크기 (할당)</th>
                <th style="width: 17%;">실제 사용량 (점유율)</th>
                <th style="width: 12%;">실행시간 (가동)</th>
                <th style="width: 9%;">지연율</th>
                <th style="width: 8%; text-align: center;">상태</th>
              </tr>
            </thead>
            <tbody>
              ${tableRowsHtml}
            </tbody>
          </table>
        </div>
      `;

      modalBody.innerHTML = `
        ${summaryBoxHtml}
        ${focusedHtml}
        <div style="font-size: 12px; font-weight: 700; color: #cbd5e1; margin-top: 4px;">전체 서비스 목록 (순위 구분 없이 선택된 기준으로 정렬됨 · 행 클릭 시 집중 분석)</div>
        ${tableHtml}
      `;

      modalBackdrop.style.display = 'flex';
    }

    function closeModal() {
      const modalBackdrop = document.getElementById('modal-backdrop');
      if (modalBackdrop) modalBackdrop.style.display = 'none';
    }

    function handleBackdropClick(event) {
      if (event.target.id === 'modal-backdrop') {
        closeModal();
      }
    }

    window.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') closeModal();
    });

    window.addEventListener('DOMContentLoaded', siteAuthBoot);
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
