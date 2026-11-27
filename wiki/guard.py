"""비밀값 차단과 문서 body 검사 (스펙 6.4)."""
import re

from wiki.errors import ApiError

DOMAINS = ["network", "security", "web", "compute", "app", "data", "dr", "ops"]
PROVIDERS = {"onprem", "openstack", "kt", "aws", "other"}

SECRET_PATTERNS = [
    ("private-key-block", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("wg-private-key", re.compile(r"PrivateKey\s*=\s*[A-Za-z0-9+/]{43}=")),
    ("aws-access-key", re.compile(r"AKIA[0-9A-Z]{16}")),
    ("github-token", re.compile(r"gh[pousr]_[A-Za-z0-9]{36}")),
    ("password-value", re.compile(r"(?i)(password|passwd|pwd|secret|token)\s*[:=]\s*(?![<$'\"{])\S{6,}")),
]


def find_secret(value, path="body"):
    """value 안 문자열에서 비밀값 형태를 찾으면 {'field', 'pattern'}, 없으면 None."""
    if isinstance(value, str):
        for name, pat in SECRET_PATTERNS:
            if pat.search(value):
                return {"field": path, "pattern": name}
        return None
    if isinstance(value, dict):
        items = ((f"{path}.{k}", v) for k, v in value.items())
    elif isinstance(value, list):
        items = ((f"{path}[{i}]", v) for i, v in enumerate(value))
    else:
        return None
    for p, v in items:
        hit = find_secret(v, p)
        if hit:
            return hit
    return None


def _need(body, field, ok, msg):
    if not ok:
        raise ApiError(422, msg, {"field": field})


def validate_body(kind, body):
    _need(body, "body", isinstance(body, dict), "body 는 객체여야 합니다")
    def text(f):
        v = body.get(f)
        return isinstance(v, str) and v.strip() != ""
    if kind == "cloud":
        _need(body, "name", text("name"), "클라우드 이름을 입력하세요")
        _need(body, "provider", body.get("provider") in PROVIDERS, "클라우드 종류가 올바르지 않습니다")
    elif kind == "instance":
        _need(body, "title", text("title"), "인스턴스 이름을 입력하세요")
    elif kind == "area":
        _need(body, "name", text("name"), "서비스 영역 이름을 입력하세요")
        d = body.get("domains")
        _need(body, "domains", isinstance(d, list) and len(d) > 0 and all(x in DOMAINS for x in d),
              "서비스 분류를 하나 이상 고르세요")
    elif kind == "steps":
        _need(body, "items", isinstance(body.get("items"), list), "단계 목록이 필요합니다")
    elif kind == "page":
        _need(body, "title", text("title"), "문서 제목을 입력하세요")
    else:
        raise ApiError(422, "알 수 없는 문서 종류입니다", {"field": "kind"})
