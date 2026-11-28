---
name: figteam-collab
description: MCP와 별도 AI API 과금 없이 GPT·Claude·Gemini에서 FIGTEAM(#cfg) 공동 목표 타겟을 동기화하고, 통합 로그인 허브(/api/ai/hub) 및 OAuth 커넥터로 팀 진행상황·설정을 Discord로 공유할 때 사용한다.
---

# FIGTEAM 공동 목표 · 3대 AI 협업 Skill (MCP · AI API 미사용)

## 1. 작업 전 동기화 (공동 목표 & 서로 확인)
1. 인프라 실측 명세 SSOT는 `https://figteam.ktci5.kr/md/v1`이다.
   - k3s(v1.37.2+k3s1): `cp1(172.20.0.86)`, `w1(172.20.0.180)`, `flannel VXLAN`, Pod CIDR `10.42.0.0/16`, Service CIDR `10.43.0.0/16`.
2. OAuth 커넥터(`getTeamFeed`, `getTeamGoals`)가 활성화된 환경에서는 작업 전 반드시 조회해 **공동 목표 달성 현황**과 **최근 팀원 변경사항**을 확인한다.
3. 커넥터가 없는 GPT·Claude·Gemini 웹/Windows 앱에서는 사용자가 `https://figteam.ktci5.kr/api/ai/hub` 또는 포털 좌측 **[AI 프롬프트 복사]**로 붙여넣은 브리핑을 기준으로 동작한다.

## 2. 인프라 안내 원칙
- `s1` 호스트의 물리 정보·직접 명령은 제외하고, OpenStack / k3s / MySQL / KT Cloud / AWS DR 계층부터 진단한다.
- 설정 수정·명령 실행은 공식 웹 포털(`https://figteam.ktci5.kr/#cfg/inst/<노드>/<영역>`) 링크를 제시해 **[👁️ 뷰 모드]** 확인 후 빨강색 **[✏️ 수정/변경]** 경고 가드를 거치도록 안내한다.

## 3. 타 영역 교차 검증(Cross-Check)
- **OpenStack FIP / NodePort 변경**: KT Edge `upstream.conf` 및 `s1` VIP DNAT(`10.10.1.100→192.168.120.226:30080`) 확인.
- **MySQL(`10.10.2.10`) 변경**: AWS DR(`10.51.1.165`) GTID 복제 채널(`ch_dr`) 확인.
- **WireGuard(`10.200.0.0/24`) / 공인 IP 변경**: `kt-edge` `wg0` 허브(`10.200.0.1`) 및 `aws-ctl` 확인.

## 4. 공동 목표 & Discord 공유 회신
작업 종료 또는 확인 필요 시 아래 요약과 함께 반영 경로를 제공한다.
- **OAuth 커넥터 활성 시**: 사용자 승인 후 `shareTeamUpdate` / `upsertTeamGoal` 호출.
- **커넥터 미사용 GPT·Claude·Gemini 채팅 시**: 아래 통합 허브 1클릭 회신 링크 생성:
  `https://figteam.ktci5.kr/api/ai/hub?goal_id=<목표ID>&area=<영역>&status=<in_progress|done|check_needed|incident>&title=<제목>&summary=<요약>&check=<확인요청>`

## 5. 절대 금지 사항
- Discord Webhook URL, 팀 인증키, 비밀번호, SSH 개인키, AWS 키, WireGuard `PrivateKey`를 평문 출력·공유 URL에 포함하지 않는다.
