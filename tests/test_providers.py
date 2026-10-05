import threading
import time
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
import unittest
from unittest.mock import Mock, patch

import requests

from cliffy_providers import AIClient, ProviderConfig, ProviderError


def response(data=None, status=200, headers=None):
    result = Mock(status_code=status, headers=headers or {})
    result.json.return_value = data
    return result


class ProviderTests(unittest.TestCase):
    def test_gemini_google_key_fallback(self):
        with patch.dict('os.environ', {'CLIFFY_PROVIDER': 'gemini', 'GOOGLE_API_KEY': 'google'}, clear=True):
            self.assertEqual(ProviderConfig.from_env().api_key, 'google')

    def test_retry_after_variants_and_fail_fast(self):
        from cliffy_providers import _retry_after
        future = format_datetime(datetime.now(timezone.utc) + timedelta(seconds=42))
        self.assertAlmostEqual(_retry_after('4'), 4)
        self.assertGreater(_retry_after(future), 40)
        self.assertEqual(_retry_after('bogus'), 30)
        self.assertEqual(_retry_after(None), 30)
        client = AIClient(ProviderConfig('groq', 'private-secret', min_interval=0))
        with patch('cliffy_providers.requests.post', return_value=response(status=429)) as post:
            with self.assertRaises(ProviderError):
                client.complete('hi')
            start = time.monotonic()
            with self.assertRaises(ProviderError) as caught:
                client.complete('hi')
            self.assertLess(time.monotonic() - start, 0.2)
            self.assertEqual(post.call_count, 1)
            self.assertNotIn('private-secret', str(caught.exception))

    def test_spacing_consumes_timeout_budget(self):
        client = AIClient(ProviderConfig('groq', 'secret', min_interval=0.2))
        with patch('cliffy_providers.requests.post', return_value=response({'choices': [{'message': {'content': 'ok'}}]})) as post:
            client.complete('hi')
            with self.assertRaisesRegex(ProviderError, 'timed out'):
                client.complete('hi', timeout=0.02)
            self.assertEqual(post.call_count, 1)

    def test_cooldown_interrupts_waiting_caller(self):
        client = AIClient(ProviderConfig('groq', 'secret', min_interval=0.3))
        started = threading.Event()
        release = threading.Event()
        outcomes = []

        def fake_post(*args, **kwargs):
            started.set()
            release.wait(1)
            return response(status=429, headers={'Retry-After': '60'})

        def first():
            try:
                client.complete('first')
            except ProviderError as exc:
                outcomes.append(str(exc))

        with patch('cliffy_providers.requests.post', side_effect=fake_post) as post:
            worker = threading.Thread(target=first)
            worker.start()
            self.assertTrue(started.wait(1))
            timer = threading.Timer(0.02, release.set)
            timer.start()
            with self.assertRaisesRegex(ProviderError, 'rate limit'):
                client.complete('second', timeout=0.5)
            worker.join(1)
            timer.join(1)
            self.assertEqual(post.call_count, 1)
            self.assertEqual(len(outcomes), 1)

    def test_native_malformed_payloads(self):
        for provider, bodies in [('anthropic', [{}, {'content': []}, {'content': [{'type': 'text', 'text': ''}]}, {'stop_reason': 'max_tokens', 'content': [{'type': 'text', 'text': 'partial'}]}]),
                                 ('gemini', [{}, {'candidates': []}, {'candidates': [{'content': {'parts': []}}]}, {'candidates': [{'finishReason': 'MAX_TOKENS', 'content': {'parts': [{'text': 'partial'}]}}]}])]:
            for body in bodies:
                with self.subTest(provider=provider, body=body), patch('cliffy_providers.requests.post', return_value=response(body)):
                    with self.assertRaises(ProviderError):
                        AIClient(ProviderConfig(provider, 'secret')).complete('hi')

    def test_url_rejects_unsafe_authority(self):
        for url in ['https://example.org:bad/v1', 'https://example.org\\@evil.test/v1', 'https://example.org/v1#fragment', 'https://user:pass@example.org/v1', 'http://localhost.evil.test/v1', 'https://example.org/v1?key=secret']:
            with self.subTest(url=url), self.assertRaises(ProviderError):
                AIClient(ProviderConfig('custom', 'secret', url, 'model'))
    def test_env_precedence_and_legacy(self):
        with patch.dict('os.environ', {'GROQ_API_KEY': 'old', 'GROQ_MODEL': 'legacy'}, clear=True):
            config = ProviderConfig.from_env()
            self.assertEqual((config.provider, config.api_key, config.model), ('groq', 'old', 'legacy'))
        with patch.dict('os.environ', {'CLIFFY_PROVIDER': 'openai', 'CLIFFY_API_KEY': 'new', 'OPENAI_API_KEY': 'native', 'CLIFFY_MODEL': 'selected'}, clear=True):
            config = ProviderConfig.from_env()
            self.assertEqual((config.api_key, config.model), ('new', 'selected'))
            self.assertNotIn('new', repr(config))

    def test_provider_payloads(self):
        examples = [
            ('groq', 'https://api.groq.com/openai/v1/chat/completions', 'Authorization', 'Bearer secret', {'choices': [{'message': {'content': 'groq'}}]}, 'groq'),
            ('openai', 'https://api.openai.com/v1/chat/completions', 'Authorization', 'Bearer secret', {'choices': [{'message': {'content': 'openai'}}]}, 'openai'),
            ('anthropic', 'https://api.anthropic.com/v1/messages', 'x-api-key', 'secret', {'content': [{'type': 'text', 'text': 'anthropic'}]}, 'anthropic'),
            ('gemini', 'https://generativelanguage.googleapis.com/v1beta/models/test:generateContent', 'x-goog-api-key', 'secret', {'candidates': [{'content': {'parts': [{'text': 'gemini'}]}}]}, 'gemini'),
            ('custom', 'https://example.org/v1/chat/completions', 'Authorization', 'Bearer secret', {'choices': [{'message': {'content': 'custom'}}]}, 'custom'),
            ('apinex', 'https://api.apinex.bond/v1/chat/completions', 'Authorization', 'Bearer secret', {'choices': [{'message': {'content': 'apinex'}}]}, 'apinex'),
        ]
        for provider, url, auth, token, body, expected in examples:
            with self.subTest(provider=provider), patch('cliffy_providers.requests.post', return_value=response(body)) as post:
                base = 'https://example.org/v1' if provider == 'custom' else None
                client = AIClient(ProviderConfig(provider, 'secret', base, 'test', 7, 0))
                self.assertEqual(client.complete('hello', system='system', max_tokens=32, timeout=4), expected)
                args, kwargs = post.call_args
                self.assertEqual(args[0], url)
                self.assertEqual(kwargs['headers'][auth], token)
                self.assertGreater(kwargs['timeout'], 0)
                self.assertLessEqual(kwargs['timeout'], 4)
                self.assertFalse(kwargs['allow_redirects'])
                payload = kwargs['json']
                if provider == 'anthropic':
                    self.assertEqual(payload['system'], 'system')
                    self.assertEqual(payload['messages'][0]['content'], 'hello')
                elif provider == 'gemini':
                    self.assertEqual(payload['systemInstruction']['parts'][0]['text'], 'system')
                    self.assertEqual(payload['contents'][0]['parts'][0]['text'], 'hello')
                else:
                    self.assertEqual(payload['messages'][0]['role'], 'system')

    def test_invalid_config(self):
        for config in [ProviderConfig('unknown', 'secret'), ProviderConfig('custom', 'secret'), ProviderConfig('custom', 'secret', 'http://remote/v1'), ProviderConfig('groq', 'secret', timeout=0), ProviderConfig('groq', 'secret', min_interval=-1)]:
            with self.subTest(config=config), self.assertRaises(ProviderError):
                AIClient(config)
        with self.assertRaises(ProviderError):
            AIClient(ProviderConfig('groq', ''))

    def test_safe_errors_and_cooldown(self):
        client = AIClient(ProviderConfig('groq', 'private-secret', min_interval=0))
        cases = [(401, 'authentication'), (302, 'HTTP'), (500, 'HTTP'), (429, 'rate')]
        for status, word in cases:
            with self.subTest(status=status), patch('cliffy_providers.requests.post', return_value=response(status=status, headers={'Retry-After': '2'})):
                with self.assertRaises(ProviderError) as caught:
                    client.complete('hello')
                self.assertIn(word.lower(), str(caught.exception).lower())
                self.assertNotIn('private-secret', str(caught.exception))
        self.assertGreater(client._next_request, 0)
        client = AIClient(ProviderConfig('groq', 'private-secret', min_interval=0))
        with patch('cliffy_providers.requests.post', side_effect=requests.Timeout('private-secret')):
            with self.assertRaises(ProviderError) as caught:
                client.complete('hello', timeout=0.01)
            self.assertNotIn('private-secret', str(caught.exception))

    def test_malformed_empty_and_truncated(self):
        client = AIClient(ProviderConfig('openai', 'secret', min_interval=0))
        for body in [{}, {'choices': []}, {'choices': [{'finish_reason': 'length', 'message': {'content': 'partial'}}]}, {'choices': [{'message': {'content': '  '}}]}]:
            with self.subTest(body=body), patch('cliffy_providers.requests.post', return_value=response(body)):
                with self.assertRaises(ProviderError):
                    client.complete('hi')

    def test_concurrent_spacing(self):
        client = AIClient(ProviderConfig('groq', 'secret', min_interval=0.03))
        times = []
        lock = threading.Lock()

        def fake_post(*args, **kwargs):
            with lock:
                import time
                times.append(time.monotonic())
            return response({'choices': [{'message': {'content': 'ok'}}]})

        with patch('cliffy_providers.requests.post', side_effect=fake_post):
            threads = [threading.Thread(target=client.complete, args=('hi',)) for _ in range(4)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()
        self.assertEqual(len(times), 4)
        self.assertTrue(all(b - a >= 0.025 for a, b in zip(times, times[1:])))


if __name__ == '__main__':
    unittest.main()
