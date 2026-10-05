"""Exercise native Bash on a controlling PTY, with localhost inference only."""
import errno
import json
import os
from pathlib import Path
import pty
import select
import signal
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

ROOT = Path(__file__).resolve().parents[1]


class Terminal:
    def __init__(self, tmp_path, env=None):
        (tmp_path / '.bashrc').write_text("PS1='native> '\nHISTFILE=/dev/null\n")
        child_env = dict(os.environ, HOME=str(tmp_path), TERM='dumb',
                         PYTHONPATH=str(ROOT), PYTHON_DOTENV_DISABLED='1')
        child_env.update(env or {})
        self.pid, self.fd = pty.fork()
        if self.pid == 0:
            import sys
            os.execve(sys.executable, [sys.executable, '-m', 'cliffy_cli', '--shell', 'bash'], child_env)
        self.buffer = b''
        self.expect(b'native> ')

    def send(self, value):
        os.write(self.fd, value.encode() if isinstance(value, str) else value)

    def expect(self, token, timeout=8):
        deadline = time.monotonic() + timeout
        while token not in self.buffer:
            remaining = deadline - time.monotonic()
            assert remaining > 0, f'Terminal did not produce {token!r}'
            ready, _, _ = select.select([self.fd], [], [], remaining)
            if ready:
                try:
                    data = os.read(self.fd, 65536)
                except OSError as exc:
                    if exc.errno == errno.EIO:
                        pytest.fail('Native session exited before expected output')
                    raise
                assert data, 'Native session closed unexpectedly'
                self.buffer += data
        end = self.buffer.index(token) + len(token)
        result, self.buffer = self.buffer[:end], self.buffer[end:]
        return result

    def command(self, text):
        self.send(text + '\n')
        return self.expect(b'native> ')

    def close(self):
        try:
            self.send('exit\n')
            deadline = time.monotonic() + 3
            while time.monotonic() < deadline:
                pid, status = os.waitpid(self.pid, os.WNOHANG)
                if pid:
                    return os.waitstatus_to_exitcode(status)
                time.sleep(.02)
            os.kill(self.pid, signal.SIGTERM)
            os.waitpid(self.pid, 0)
        finally:
            os.close(self.fd)


def test_native_shell_state_and_job_control_are_real(tmp_path):
    directory = tmp_path / 'project with spaces'
    directory.mkdir()
    activation = tmp_path / 'activate'
    activation.write_text("export ACTIVE_NATIVE=yes\nnative_function() { printf 'function-ok\\n'; }\n")
    terminal = Terminal(tmp_path, {'CLIFFY_NO_AI': '1'})
    try:
        terminal.command(f'cd "{directory}" && export NATIVE_STATE=persistent')
        output = terminal.command("printf 'STATE:%s:%s\\n' \"$PWD\" \"$NATIVE_STATE\"")
        assert f'STATE:{directory}:persistent'.encode() in output
        terminal.command(f'source "{activation}"')
        output = terminal.command("native_function; printf 'ACTIVE:%s\\n' \"$ACTIVE_NATIVE\"")
        assert b'function-ok' in output and b'ACTIVE:yes' in output
        terminal.command("alias native_alias='printf alias-ok'")
        assert b'alias-ok' in terminal.command('native_alias')
        terminal.command('umask 077')
        assert b'0077' in terminal.command('umask')
        terminal.send('sleep 30\n')
        terminal.expect(b'sleep 30\r\n')
        time.sleep(.1)  # Give Bash time to hand the foreground group to sleep.
        terminal.send(b'\x03')
        terminal.expect(b'native> ')
        terminal.command('sleep 30 &')
        assert b'Running' in terminal.command('jobs')
        terminal.send('fg\n')
        terminal.expect(b'sleep 30')
        time.sleep(.1)
        terminal.send(b'\x1a')
        terminal.expect(b'native> ')
        assert b'Stopped' in terminal.command('jobs')
        terminal.command('bg')
        terminal.send('fg\n')
        terminal.expect(b'sleep 30')
        time.sleep(.1)
        terminal.send(b'\x03')
        terminal.expect(b'native> ')
        assert b'ALIVE:yes' in terminal.command("printf 'ALIVE:%s\\n' yes")
    finally:
        terminal.close()
    assert os.getcwd() != str(directory)


def test_ctrl_g_inserts_local_api_draft_without_executing(tmp_path):
    marker = tmp_path / 'reviewed-marker'
    requests = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            requests.append(json.loads(self.rfile.read(int(self.headers['Content-Length']))))
            body = json.dumps({'choices': [{'message': {'content': f'touch "{marker}"'},
                                            'finish_reason': 'stop'}]}).encode()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    terminal = Terminal(tmp_path, {'CLIFFY_PROVIDER': 'custom', 'CLIFFY_MODEL': 'fixture',
                                   'CUSTOM_API_KEY': 'synthetic-local-key', 'CLIFFY_NO_AI': '0',
                                   'CLIFFY_BASE_URL': f'http://127.0.0.1:{server.server_port}/v1'})
    try:
        terminal.send('create a marker file')
        terminal.send(b'\x07')
        terminal.expect(b'review the draft')
        assert not marker.exists()
        assert len(requests) == 1
        assert 'synthetic-local-key' not in json.dumps(requests)
        terminal.send('\n')
        terminal.expect(b'native> ')
        assert marker.exists()
    finally:
        terminal.close()
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)
