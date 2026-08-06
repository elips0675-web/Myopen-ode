"""Interactive shell process with input/output streaming for the WebSocket
terminal.

POSIX: a real PTY (pty.fork + TIOCSWINSZ resize).
Windows: subprocess pipes (a true ConPTY needs the `winpty` binary or a
package — pipes keep `python -u -i`, `cmd`, `powershell` usable instead).

Output accumulates in an internal buffer; the WebSocket layer polls
read_available() every ~50ms and forwards it.
"""
import logging
import os
import shlex
import subprocess
import threading

log = logging.getLogger('pty_shell')

_IS_POSIX = os.name == "posix"


class PtyShell:
    def __init__(self, cmd=None, cwd=None, cols=100, rows=30):
        self.cwd = str(cwd or os.getcwd())
        self.cols, self.rows = int(cols) or 100, int(rows) or 30
        self.buf = b""
        self.lock = threading.Lock()
        self.dead = False
        self.exit_code = None
        self._fd = None
        self._pid = None
        self._proc = None
        self._reader = None
        if _IS_POSIX:
            self._start_posix(cmd)
        else:
            self._start_win(cmd)

    # ─── POSIX: real PTY ───────────────────────────────────
    def _start_posix(self, cmd):
        import pty
        argv = shlex.split(cmd) if isinstance(cmd, str) else (cmd or ["bash"])
        try:
            pid, fd = pty.fork()
        except OSError as e:
            log.warning("pty.fork failed: %s", e)
            self.dead = True
            self.exit_code = -1
            return
        if pid == 0:  # child
            try:
                os.chdir(self.cwd)
            except OSError:
                pass
            try:
                os.execvp(argv[0], argv)
            except Exception as e:
                os.write(2, f"exec failed: {e}\n".encode())
                os._exit(127)
        self._pid, self._fd = pid, fd
        self.resize(self.cols, self.rows)
        self._reader = threading.Thread(target=self._read_loop_posix, daemon=True)
        self._reader.start()

    def _read_loop_posix(self):
        while True:
            try:
                data = os.read(self._fd, 4096)
            except OSError:
                break
            if not data:
                break
            with self.lock:
                self.buf += data
        self.dead = True
        try:
            _, status = os.waitpid(self._pid, 0)
            self.exit_code = os.waitstatus_to_exitcode(status)
        except Exception:
            pass

    # ─── Windows: subprocess pipes ─────────────────────────
    def _start_win(self, cmd):
        creation = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        if isinstance(cmd, str) and cmd.strip():
            argv = cmd
            shell = True
        else:
            argv = cmd or [os.environ.get("COMSPEC", "cmd.exe")]
            shell = False
        try:
            self._proc = subprocess.Popen(
                argv, shell=shell, cwd=self.cwd,
                stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT, creationflags=creation,
                env={**os.environ, "PYTHONUNBUFFERED": "1", "PYTHONIOENCODING": "utf-8"},
            )
        except OSError as e:
            log.warning("shell start failed: %s", e)
            self.dead = True
            self.exit_code = -1
            return
        self._reader = threading.Thread(target=self._read_loop_win, daemon=True)
        self._reader.start()

    def _read_loop_win(self):
        while True:
            line = self._proc.stdout.readline()
            if not line:
                break
            with self.lock:
                self.buf += line
        self.dead = True
        try:
            self.exit_code = self._proc.wait()
        except Exception:
            pass

    # ─── common API ────────────────────────────────────────
    def feed(self, data):
        """Send input to the process (str or bytes)."""
        if isinstance(data, str):
            data = data.encode("utf-8")
        try:
            if self._fd is not None:
                os.write(self._fd, data)
            elif self._proc is not None:
                self._proc.stdin.write(data)
                self._proc.stdin.flush()
        except (OSError, ValueError):
            pass

    def read_available(self, maxlen=65536):
        with self.lock:
            data, self.buf = self.buf, b""
        return data[:maxlen]

    def resize(self, cols, rows):
        self.cols, self.rows = int(cols) or self.cols, int(rows) or self.rows
        if self._fd is None:
            return
        try:
            import fcntl
            import struct
            import termios
            fcntl.ioctl(self._fd, termios.TIOCSWINSZ,
                        struct.pack("HHHH", self.rows, self.cols, 0, 0))
        except Exception:
            pass

    def kill(self):
        try:
            if self._fd is not None:
                os.kill(self._pid, 9)
                os.close(self._fd)
            elif self._proc is not None:
                self._proc.kill()
        except (OSError, ProcessLookupError):
            pass
