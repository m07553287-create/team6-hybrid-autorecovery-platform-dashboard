import pytest

from wiki.guard import find_secret, validate_body
from wiki.app import ApiError


def test_find_secret_wg_key():
    hit = find_secret({"config": [{"code": "PrivateKey = " + "A" * 43 + "="}]})
    assert hit["field"] == "body.config[0].code"


def test_find_secret_placeholder():
    assert find_secret({"code": "PrivateKey = <허브 개인키>"}) is None


def test_find_secret_env_var():
    assert find_secret({"code": 'MYSQL_PWD="$MYSQL_ROOT_PASSWORD"'}) is None


def test_find_secret_akia():
    assert find_secret({"x": "AKIAABCDEFGHIJKLMNOP"})


def test_find_secret_pem():
    assert find_secret({"x": "-----BEGIN OPENSSH PRIVATE KEY-----"})


def test_find_secret_password_value():
    assert find_secret({"x": "password=hunter22"})


def test_validate_area_domain():
    with pytest.raises(ApiError) as e:
        validate_body("area", {"name": "x", "domains": ["bogus"]})
    assert e.value.status == 422 and e.value.extra["field"] == "domains"


def test_validate_instance_title():
    with pytest.raises(ApiError):
        validate_body("instance", {})


def test_validate_korean_emoji():
    validate_body("cloud", {"name": "온프렘 🖥", "provider": "onprem"})


def test_health(client):
    assert client.get("/api/health").json() == {"ok": True}
