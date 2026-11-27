"""인스턴스별 명령 버튼: 초안(targets.json 의 check/fix) + 사용자가 고친 목록(JSON 파일, 팀 공용)."""
import json
import os
import pathlib
import re
import tempfile
import threading

EMOJI = re.compile("[\U0001F000-\U0001FFFF←-⇿⌀-⏿①-⓿─-➿⤀-⥿⬀-⯿️‍]")
MAX_ITEMS, MAX_LABEL, MAX_CMD = 40, 30, 2000
KINDS = ("check", "fix")


class PresetError(ValueError):
    pass


def draft(target):
    out = []
    for kind in KINDS:
        for label, cmd in (target.get(kind) or {}).items():
            out.append({"label": label, "cmd": cmd, "kind": kind})
    return out


def validate(items):
    if not isinstance(items, list) or len(items) > MAX_ITEMS:
        raise PresetError(f"버튼은 {MAX_ITEMS}개까지입니다")
    clean = []
    for n, it in enumerate(items, 1):
        if not isinstance(it, dict):
            raise PresetError(f"{n}번째 항목 형식이 올바르지 않습니다")
        label, cmd, kind = str(it.get("label") or "").strip(), str(it.get("cmd") or "").strip(), it.get("kind")
        if not (1 <= len(label) <= MAX_LABEL):
            raise PresetError(f"{n}번째 버튼 이름은 1~{MAX_LABEL}자로 입력하세요")
        if EMOJI.search(label):
            raise PresetError(f"{n}번째 버튼 이름에 이모티콘·기호는 쓸 수 없습니다 (한글·영문)")
        if not (1 <= len(cmd) <= MAX_CMD):
            raise PresetError(f"{n}번째 명령은 1~{MAX_CMD}자로 입력하세요")
        if "\n" in cmd or "\r" in cmd:
            raise PresetError(f"{n}번째 명령은 한 줄로 입력하세요 (여러 명령은 ; 또는 && 로 잇기)")
        if kind not in KINDS:
            raise PresetError(f"{n}번째 종류는 확인 또는 복구여야 합니다")
        clean.append({"label": label, "cmd": cmd, "kind": kind})
    return clean


class PresetStore:
    def __init__(self, path, targets):
        self.path, self.targets = pathlib.Path(path), targets
        self.lock = threading.Lock()

    def _load(self):
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except (FileNotFoundError, ValueError):
            return {}

    def _save(self, data):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=self.path.parent, prefix=".presets-")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=1)
        os.replace(tmp, self.path)

    def all(self):
        saved = self._load()
        return {tid: {"custom": tid in saved, "items": saved[tid] if tid in saved else draft(t)}
                for tid, t in self.targets.items() if not t.get("disabled")}

    def put(self, tid, items):
        clean = validate(items)
        with self.lock:
            data = self._load(); data[tid] = clean; self._save(data)
        return clean

    def reset(self, tid):
        with self.lock:
            data = self._load(); data.pop(tid, None); self._save(data)
