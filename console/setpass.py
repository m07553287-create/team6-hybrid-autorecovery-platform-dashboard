"""콘솔 비밀번호 설정: sudo python3 -m console.setpass  → /etc/figteam-console/env 에 해시만 기록."""
import getpass
import pathlib
import sys

from console.auth import hash_password

ENV = pathlib.Path("/etc/figteam-console/env")


def main():
    pw = getpass.getpass("새 콘솔 비밀번호(10자 이상): ")
    if len(pw) < 10:
        sys.exit("10자 이상이어야 합니다")
    if pw != getpass.getpass("한 번 더: "):
        sys.exit("두 입력이 다릅니다")
    h, salt = hash_password(pw)
    lines = [l for l in (ENV.read_text().splitlines() if ENV.exists() else [])
             if not l.startswith(("CONSOLE_PASS_HASH=", "CONSOLE_PASS_SALT="))]
    lines += [f"CONSOLE_PASS_HASH={h}", f"CONSOLE_PASS_SALT={salt}"]
    ENV.write_text("\n".join(lines) + "\n")
    print("설정했습니다. sudo systemctl restart figteam-console 로 반영하세요.")


if __name__ == "__main__":
    main()
