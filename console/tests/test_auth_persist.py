"""세션이 서비스 재시작·IP 변경(IPv4↔IPv6)에도 유지되는지."""
import json
import time

from console.auth import Lock, hash_password

PW = "console-pass-1"


def make(tmp_path):
    h, s = hash_password(PW)
    return (lambda: Lock(h, s, tmp_path / "sessions.json")), tmp_path / "sessions.json"


def test_session_survives_restart(tmp_path):
    new, _ = make(tmp_path)
    tok = new().unlock(PW, "175.196.197.51", access_key="KEY123", member="다운")
    assert tok and new().check(tok, "175.196.197.51")


def test_session_not_bound_to_ip(tmp_path):
    new, _ = make(tmp_path)
    lock = new()
    tok = lock.unlock(PW, "175.196.197.51", access_key="KEY123")
    assert lock.check(tok, "2a09:bac3::1")


def test_store_has_no_raw_token(tmp_path):
    new, path = make(tmp_path)
    tok = new().unlock(PW, "1.2.3.4", access_key="KEY123")
    raw = path.read_text()
    assert tok not in raw and oct(path.stat().st_mode & 0o777) == "0o600"


def test_lock_removes_from_store(tmp_path):
    new, _ = make(tmp_path)
    tok = new().unlock(PW, "1.2.3.4", access_key="KEY123")
    new().lock(tok)
    assert not new().check(tok, "1.2.3.4")


def test_expired_and_keyless_legacy_dropped_on_load(tmp_path):
    new, path = make(tmp_path)
    path.write_text(json.dumps({
        "old": time.time() - 1,
        "legacy_nokey": time.time() + 60,
        "dict_nokey": {"exp": time.time() + 60, "access_key": ""},
        "live": {"exp": time.time() + 60, "access_key": "KEY123", "member": "다운"},
    }))
    assert list(new().sessions) == ["live"]


def test_check_detail_expires_in_memory_keyless_session(tmp_path):
    new, _ = make(tmp_path)
    lock = new()
    tok = "old-token-no-key"
    lock.sessions[lock._key(tok)] = {"exp": time.time() + 60, "access_key": "", "member": ""}
    status, _ = lock.check_detail(tok)
    assert status == "no_key"
    assert lock.check(tok) is False


def test_broken_store_ignored(tmp_path):
    new, path = make(tmp_path)
    path.write_text("{not json")
    lock = new()
    assert lock.sessions == {} and lock.unlock(PW, "1.2.3.4", access_key="KEY123")
