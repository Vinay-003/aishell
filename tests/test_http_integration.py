"""Real localhost HTTP round trips; never contact an external model service."""
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from cliffy_providers import AIClient, ProviderConfig, ProviderError


def test_real_custom_http_success_and_429_cooldown():
    import pytest
    seen = []
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass
        def do_POST(self):
            payload = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            seen.append((self.path, self.headers.get('Authorization'), payload))
            limited = payload['messages'][-1]['content'] == 'limit'
            self.send_response(429 if limited else 200)
            self.send_header('Content-Type', 'application/json')
            if limited:
                self.send_header('Retry-After', '30')
            self.end_headers()
            body = {'error': {'message': 'fixture'}} if limited else {'choices': [{'message': {'content': 'echo harmless'}, 'finish_reason': 'stop'}]}
            self.wfile.write(json.dumps(body).encode())

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        client = AIClient(ProviderConfig('custom', 'fixture-only', f'http://127.0.0.1:{server.server_port}/v1', 'mock', 2, .01))
        assert client.complete('command', max_tokens=30) == 'echo harmless'
        assert seen[0][0] == '/v1/chat/completions'
        assert seen[0][1] == 'Bearer fixture-only'
        assert seen[0][2]['model'] == 'mock'
        with pytest.raises(ProviderError, match='rate limit'):
            client.complete('limit')
        with pytest.raises(ProviderError, match='rate limit'):
            client.complete('command')
        assert len(seen) == 2
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=2)


def test_offline_pattern_reference_all_severities(capsys):
    import pattern_reference
    pattern_reference.show_patterns()
    output = capsys.readouterr().out
    assert 'CRITICAL' in output and 'HIGH' in output
    for severity in ('critical', 'high', 'medium', 'low'):
        pattern_reference.show_patterns(severity)
        assert 'Total:' in capsys.readouterr().out
