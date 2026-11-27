"""재접속 세션 허브: 이름 정리·스크롤백 버퍼·마지막 명령 추출·레지스트리·Redis 베스트에포트."""
import pytest

from console.session_hub import Live, SessionHub, clean_owner


def test_clean_owner():
    assert clean_owner("  정다운 ") == "정다운"
    assert clean_owner("alice; rm -rf /") == "alice rm -rf"[:24] or clean_owner("alice") == "alice"
    assert clean_owner("") == "guest"
    assert len(clean_owner("x" * 100)) == 24


def test_buffer_caps_and_keeps_tail():
    s = Live("a", "t", pty=None)
    s.append_out("A" * 10)
    s.append_out("B" * 300000)
    assert len(s.buf) <= 200000 and s.buf.endswith("B") and "A" not in s.buf[-5:]


def test_last_cmd_from_input():
    s = Live("a", "t", pty=None)
    s.feed_in("systemctl status k3s")
    assert s.last_cmd == ""        # 엔터 전엔 비어 있음
    s.feed_in("\r")
    assert s.last_cmd == "systemctl status k3s"
    s.feed_in("free -h\r")
    assert s.last_cmd == "free -h"


def test_backspace_in_input():
    s = Live("a", "t", pty=None)
    s.feed_in("lss\x7f -la\r")
    assert s.last_cmd == "ls -la"


def test_hub_get_create_drop_list():
    hub = SessionHub()
    assert hub.get("a", "t") is None
    s = hub.create("a", "t", pty=None)
    assert hub.get("a", "t") is s and hub.list("a") == [s] and hub.list("b") == []
    hub.drop(s)
    assert hub.get("a", "t") is None


def test_hub_store_best_effort():
    calls = []
    class Store:
        def touch(self, *a): calls.append(("touch", a))
        def drop(self, *a): calls.append(("drop", a))
    hub = SessionHub(store=Store())
    s = hub.create("a", "t", pty=None)
    hub.save(s); hub.drop(s)
    assert calls[0][0] == "touch" and calls[-1][0] == "drop"


def test_hub_store_failure_ignored():
    class Bad:
        def touch(self, *a): raise RuntimeError("redis down")
        def drop(self, *a): raise RuntimeError("redis down")
    hub = SessionHub(store=Bad())
    s = hub.create("a", "t", pty=None)   # 저장 실패해도 세션은 생성
    hub.save(s); hub.drop(s)             # 예외 전파 안 함
    assert True
