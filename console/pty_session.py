"""대상 명령을 PTY 로 띄우고 입출력을 비동기로 잇는다."""
import asyncio
import codecs
import fcntl
import os
import pty
import signal
import struct
import termios
import time
import warnings


class PtySession:
    def __init__(self, argv, cols, rows, on_output, log_file=None):
        self.argv, self.on_output, self.log = argv, on_output, log_file
        self.cols, self.rows = cols, rows
        self.pid = self.fd = None
        self.closed = asyncio.Event()
        self.decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
        self.last_input = time.time()

    def start(self):
        env = dict(os.environ, TERM="xterm-256color", LANG=os.environ.get("LANG", "C.UTF-8"))
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)   # 스레드가 있는 프로세스에서의 fork 경고
            pid, fd = pty.fork()
        if pid == 0:  # 자식
            try:
                os.execvpe(self.argv[0], self.argv, env)
            finally:
                os._exit(127)
        self.pid, self.fd = pid, fd
        self.resize(self.cols, self.rows)
        os.set_blocking(fd, False)
        asyncio.get_running_loop().add_reader(fd, self._readable)

    def _readable(self):
        try:
            data = os.read(self.fd, 65536)
        except (BlockingIOError, InterruptedError):
            return
        except OSError:
            data = b""
        if not data:
            self._finish()
            return
        if self.log:
            self.log.write(data)
        text = self.decoder.decode(data)
        if text:
            asyncio.ensure_future(self.on_output(text))

    def write(self, text):
        if self.fd is None:
            return
        self.last_input = time.time()
        b = text.encode("utf-8", errors="replace")
        if self.log:
            self.log.write(b"\n[IN " + time.strftime("%H:%M:%S").encode() + b"] " + repr(text).encode() + b"\n")
        try:
            os.write(self.fd, b)
        except OSError:
            self._finish()

    def resize(self, cols, rows):
        cols, rows = max(10, min(int(cols), 500)), max(4, min(int(rows), 200))
        self.cols, self.rows = cols, rows
        if self.fd is not None:
            fcntl.ioctl(self.fd, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))

    def _finish(self):
        if self.fd is not None:
            try:
                asyncio.get_running_loop().remove_reader(self.fd)
            except Exception:
                pass
        self.closed.set()

    def close(self):
        self._finish()
        if self.pid:
            for sig in (signal.SIGHUP, signal.SIGKILL):
                try:
                    os.kill(self.pid, sig)
                except ProcessLookupError:
                    break
                try:
                    if os.waitpid(self.pid, os.WNOHANG)[0]:
                        break
                except ChildProcessError:
                    break
                time.sleep(0.05)
            try:
                os.waitpid(self.pid, os.WNOHANG)
            except ChildProcessError:
                pass
            self.pid = None
        if self.fd is not None:
            try:
                os.close(self.fd)
            except OSError:
                pass
            self.fd = None
        if self.log:
            self.log.close()
            self.log = None
