"""Redis 연결 (위키 전용 인스턴스, 키 접두어 fw:).

키 구조
  fw:seq:{team,doc,script}            일련번호
  fw:team:<slug>        hash          id, slug, name, pw_hash, pw_salt, created_at
  fw:teamid:<id>        string        slug
  fw:sess:<sha256>      hash + TTL    team_id, member        (7일 뒤 자동 삭제)
  fw:sesslist:<team>    set           그 팀의 세션 키(비밀번호 변경 시 일괄 삭제)
  fw:rl:<key>           int + TTL     실패 횟수(10분)
  fw:docs:<team>        set           문서 id(삭제 포함)
  fw:doc:<id>           hash          team_id, kind, parent_id, sort, rev, body, deleted, created_at, updated_at
  fw:kids:<id>          set           살아 있는 하위 문서 id
  fw:revs:<id>          list          판 JSON(1판이 0번)
  fw:changes:<team>     zset          "<doc_id>:<rev>" , 점수 = 저장 시각(ms)
  fw:steps:<team>       string        진행 순서 문서 id
  fw:scripts:<team>     list          스크립트 id
  fw:script:<id>        hash          path, host, status, keys(JSON), text
"""
import os


def connect():
    import redis
    return redis.Redis.from_url(os.environ.get("REDIS_URL", "redis://127.0.0.1:6379/0"),
                                password=os.environ.get("REDIS_PASSWORD") or None,
                                decode_responses=True, socket_timeout=5)
