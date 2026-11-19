# 통합 터미널 (`/term`)

figteam 포털(s1 `/opt/figteam-portal`)의 「인프라 & 가상화 → 통합 터미널」 페이지.

- `term.html` → s1 `/opt/figteam-portal/term.html` 로 배포. 포털이 `GET /term` 으로 제공(로그인 필요), `#term` 메뉴는 iframe.
- 진입 시 제어 비밀번호로 잠금 해제 → 로그인 세션 60분 유지(서버 메모리). 잠금 상태에선 읽기 명령도 실행하지 않음.
- 터미널: 탭 / ⧉ 화면 위 창(드래그·크기·최소화·최대화) / ↗ 새 창(`/term?solo=<대상>`), 여러 개 동시.
- 추가: 영역(KT·AWS·온프렘) → 대상 → 「확인」·「⚠ 복구」 메뉴 + 명령 입력. 복구·위험 명령은 실행 전 확인.
- 대상 화이트리스트·실행·감사 로그는 포털 백엔드(`/api/term/exec`, `/api/ctrl/*`, `term-audit.log`).

## 포털 패치 (`portal-patches/`, 순서대로 1회)
1. `patch_term.py` — 다중 대상 터미널 API, 제어 비밀번호를 `portal_config.json` `ctrl_pass` 로 이동, KT 화면 평문 노출 제거
2. `patch_term2.py` — 세션 1회 잠금 해제·감사 로그·KT 대상 추가
3. `patch_term3.py` — `/term` 독립 페이지, 터미널 API 는 잠금 해제 세션 전용, `#term` = iframe

비밀값 없음. 포털 HTML 이 raw 가 아닌 Python 문자열이라 포털 안 JS 에는 역슬래시를 쓰지 않는다(그래서 터미널은 별도 파일).
