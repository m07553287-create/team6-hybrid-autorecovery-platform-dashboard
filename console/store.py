"""콘솔 세션 메타정보를 wiki-01 Redis 에 베스트에포트로 기록.

키 (접두어 fc:)
  fc:sess:<owner>:<target>   hash + TTL   owner, target, last_cmd, started, last_at, host
  fc:owner:<owner>           set  + TTL    그 이름의 활성 대상 집합

연결 설정은 환경변수. 실패하면 조용히 무시한다(터미널은 Redis 없이도 동작).
  CONSOLE_REDIS_URL   (예: redis://10.10.4.10:6379/1)  없으면 store 비활성
  CONSOLE_REDIS_PASSWORD
"""
import os
import socket
import time

TTL = 12 * 3600


def from_env():
    url = os.environ.get("CONSOLE_REDIS_URL")
    if not url:
        return None
    try:
        import redis
        r = redis.Redis.from_url(url, password=os.environ.get("CONSOLE_REDIS_PASSWORD") or None,
                                 decode_responses=True, socket_timeout=3, socket_connect_timeout=3)
        return Store(r)
    except Exception:
        return None


class Store:
    def __init__(self, client, host=None):
        self.r = client
        self.host = host or socket.gethostname()

    def _k(self, owner, target):
        return f"fc:sess:{owner}:{target}"

    def touch(self, owner, target, last_cmd, started, last_at):
        p = self.r.pipeline()
        p.hset(self._k(owner, target), mapping={
            "owner": owner, "target": target, "last_cmd": last_cmd or "",
            "started": int(started), "last_at": int(last_at), "host": self.host})
        p.expire(self._k(owner, target), TTL)
        p.sadd(f"fc:owner:{owner}", target)
        p.expire(f"fc:owner:{owner}", TTL)
        p.execute()

    def drop(self, owner, target):
        p = self.r.pipeline()
        p.delete(self._k(owner, target))
        p.srem(f"fc:owner:{owner}", target)
        p.execute()

    def list(self, owner):
        out = []
        for target in self.r.smembers(f"fc:owner:{owner}") or []:
            h = self.r.hgetall(self._k(owner, target))
            if h:
                out.append(h)
        return out
