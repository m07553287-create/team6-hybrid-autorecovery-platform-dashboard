---
name: figteam-collab
description: MCP와 별도 AI API 과금 없이 FIGTEAM(#cfg) 하이브리드 인프라 현황을 동기화하고, 웹 로그인 커넥터 또는 1클릭 공유 브리지를 통해 팀원 간 진행상황·설정 변경을 Discord로 공유할 때 사용한다.
---

# FIGTEAM 인프라 협업 Skill (MCP 미사용 · 웹 로그인 & Discord 연동)

## 1. 작업 전 동기화 (서로 확인)
1. 인프라 실측 명세 단일 진실 소스(SSOT)는 `https://figteam.ktci5.kr/md/v1`이다.
2. OAuth 커넥터(`getTeamFeed`)를 사용할 수 있으면 작업 시작 전 반드시 호출해 다른 팀원의 최근 진행상황과 위키 변경 이력을 확인한다.
3. 커넥터가 없는 웹/Windows 채팅창에서는 사용자에게 포털 좌측 **[AI용 현황 복사]** 버튼 결과를 붙여넣거나 `https://figteam.ktci5.kr/md/v1`의 5절(최신 팀 진행상황)을 함께 제공하도록 안내한다.

## 2. 인프라 안내 원칙
- `s1` 호스트의 물리 정보·직접 터미널 명령은 제외하고, OpenStack / k3s / MySQL / KT Cloud / AWS DR 계층부터 설계·진단한다.
- 설정 수정이나 명령어 실행은 AI가 대리 실행하지 말고, 공식 웹 포털 링크(`https://figteam.ktci5.kr/#cfg/inst/<노드>/<영역>`)를 제시해 **[👁️ 뷰 모드]** 확인 후 빨강색 **[✏️ 수정/변경]** 경고 가드를 거쳐 직접 수행하도록 안내한다.

## 3. 타 영역 교차 검증(Cross-Check)
- **OpenStack FIP / NodePort 변경**: KT Edge `upstream.conf` 및 `s1` VIP DNAT(`10.10.1.100→192.168.120.226:30080`) 영향 확인.
- **MySQL(`10.10.2.10`) 변경**: AWS DR(`10.51.1.165`) GTID 복제 채널(`ch_dr`) 확인.
- **WireGuard(`10.200.0.0/24`) / 공인 IP 변경**: `kt-edge` `wg0` 허브(`10.200.0.1`) 및 `aws-ctl` peer 확인.

## 4. 진행상황 · 설정 공유 (Discord 브리지)
작업이 끝나거나 확인이 필요하면 아래 항목으로 요약한 뒤 공유를 제안한다.
- **영역/노드**: 예) `inst-db01/mysql`
- **상태**: `in_progress` | `done` | `check_needed` | `incident` | `info`
- **제목 / 내용 / 타 영역 확인 요청 / 관련 `#cfg` 링크**

실제 전송 경로:
- **OAuth 커넥터 활성 시**: 사용자 승인 후 `shareTeamUpdate`(`POST /api/ai/share`) 호출.
- **커넥터 미사용 웹/앱 채팅 시**: 아래 1클릭 브리지 URL을 생성해 클릭하도록 안내한다.
  `https://figteam.ktci5.kr/api/ai/share-ui?area=<영역>&status=<상태>&title=<제목>&summary=<요약>&check=<확인요청>&cfg_url=<포털URL>`

## 5. 절대 금지 사항
- Discord Webhook URL, 팀 인증키, 비밀번호, SSH 개인키, AWS 키, WireGuard `PrivateKey`를 응답·공유 링크·요약에 평문으로 포함하지 않는다.
