"""운영자 도구: python3 -m wiki.admin reset-password <slug>   (REDIS_URL·REDIS_PASSWORD 환경변수)"""
import getpass
import sys

from wiki import store
from wiki.auth import reset_password


def main(argv):
    if len(argv) != 2 or argv[0] != "reset-password":
        print("사용법: python3 -m wiki.admin reset-password <팀주소>", file=sys.stderr)
        return 2
    pw = getpass.getpass("새 팀 비밀번호: ")
    if pw != getpass.getpass("한 번 더: "):
        print("두 입력이 다릅니다", file=sys.stderr)
        return 1
    reset_password(store.connect(), argv[1], pw)
    print("재설정했습니다. 기존 로그인은 모두 끊겼습니다.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
