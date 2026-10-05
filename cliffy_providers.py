"""Provider configuration and safe, synchronous completion transport."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import math
import os
import threading
import time
from urllib.parse import urlsplit

import requests


class ProviderError(Exception):
    """An actionable error without HTTP response content or credentials."""


_DEFAULTS = {
    'groq': ('https://api.groq.com/openai/v1', 'llama-3.1-8b-instant', 'GROQ_API_KEY'),
    'openai': ('https://api.openai.com/v1', 'gpt-4o-mini', 'OPENAI_API_KEY'),
    'anthropic': ('https://api.anthropic.com/v1', 'claude-sonnet-4-5', 'ANTHROPIC_API_KEY'),
    'gemini': ('https://generativelanguage.googleapis.com/v1beta', 'gemini-2.5-flash', 'GEMINI_API_KEY'),
    'custom': (None, None, 'CUSTOM_API_KEY'),
    'apinex': ('https://api.apinex.bond/v1', 'free/glm-5.3-flash', 'APINEX_API_KEY'),
}


def _environment_value(*keys):
    for key in keys:
        value = os.getenv(key, '').strip()
        if value:
            return value
    return None


@dataclass(frozen=True)
class ProviderConfig:
    provider: str = 'groq'
    api_key: str = field(default='', repr=False)
    base_url: str | None = None
    model: str | None = None
    timeout: float = 10.0
    min_interval: float = 0.1

    @classmethod
    def from_env(cls):
        provider = (_environment_value('CLIFFY_PROVIDER') or 'groq').lower()
        if provider not in _DEFAULTS:
            raise ProviderError('Unsupported AI provider.')
        default_url, default_model, key_name = _DEFAULTS[provider]
        prefix = provider.upper()
        base = _environment_value('CLIFFY_BASE_URL', f'{prefix}_API_ENDPOINT', f'{prefix}_BASE_URL')
        model = _environment_value('CLIFFY_MODEL', f'{prefix}_MODEL')
        # The budget includes request spacing. Free-tier APInex dispatches are
        # 12.1s apart, so a 10s default would reject follow-up calls immediately.
        timeout = _environment_value('CLIFFY_TIMEOUT') or ('30' if provider == 'apinex' else '10')
        # APInex's free tier is 5 requests/minute per IP, including all modes.
        interval = _environment_value('CLIFFY_MIN_INTERVAL') or ('12.1' if provider == 'apinex' else '0.1')
        try:
            config = cls(provider, _environment_value('CLIFFY_API_KEY', key_name, *(['GOOGLE_API_KEY'] if provider == 'gemini' else [])) or '',
                         base or default_url, model or default_model, float(timeout), float(interval))
        except ValueError:
            raise ProviderError('Invalid AI timeout or request interval.') from None
        config.validate()
        return config

    def validate(self):
        if self.provider not in _DEFAULTS:
            raise ProviderError('Unsupported AI provider.')
        if not isinstance(self.api_key, str) or not self.api_key.strip():
            raise ProviderError('AI API key is not configured.')
        if any(c in self.api_key for c in '\r\n'):
            raise ProviderError('Invalid AI API key.')
        if not isinstance(self.timeout, (int, float)) or not math.isfinite(self.timeout) or self.timeout <= 0:
            raise ProviderError('Invalid AI timeout.')
        if not isinstance(self.min_interval, (int, float)) or not math.isfinite(self.min_interval) or self.min_interval < 0:
            raise ProviderError('Invalid AI request interval.')
        url = self.base_url or _DEFAULTS[self.provider][0]
        if not isinstance(url, str) or not url:
            raise ProviderError('AI base URL is not configured.')
        try:
            parts = urlsplit(url)
            port = parts.port
        except ValueError:
            raise ProviderError('Invalid AI base URL.') from None
        if (parts.scheme != 'https' and not (self.provider == 'custom' and parts.scheme == 'http'
                                             and parts.hostname in ('localhost', '127.0.0.1', '::1'))):
            raise ProviderError('AI base URL must use HTTPS (except local custom endpoints).')
        if not parts.hostname or parts.username or parts.password or parts.query or parts.fragment or port == 0 or '\\' in url or any(c.isspace() for c in url):
            raise ProviderError('Invalid AI base URL.')
        if not (self.model or _DEFAULTS[self.provider][1]):
            raise ProviderError('AI model is not configured.')


def _retry_after(value):
    try:
        seconds = float(value)
        return min(max(seconds, 0), 3600) if math.isfinite(seconds) else 30
    except (TypeError, ValueError):
        try:
            date = parsedate_to_datetime(value)
            if date.tzinfo is None:
                date = date.replace(tzinfo=timezone.utc)
            return min(max((date - datetime.now(timezone.utc)).total_seconds(), 0), 3600)
        except (TypeError, ValueError, OverflowError):
            return 30


class AIClient:
    def __init__(self, config: ProviderConfig):
        config.validate()
        self.config = config
        self._lock = threading.Lock()
        self._next_request = 0.0
        self._cooldown_until = 0.0

    def _wait_for_slot(self, deadline):
        # Never sleep under the lock: 429 may arrive while another call waits.
        # Only reserve a slot at actual dispatch time to preserve start spacing.
        while True:
            with self._lock:
                now = time.monotonic()
                if now < self._cooldown_until:
                    raise ProviderError('AI rate limit reached; try again later.')
                delay = max(self._next_request - now, 0)
                if not delay:
                    if now >= deadline:
                        raise ProviderError('AI request timed out.')
                    self._next_request = now + self.config.min_interval
                    return
            if now + delay >= deadline:
                raise ProviderError('AI request timed out.')
            time.sleep(min(delay, deadline - now))

    def complete(self, prompt: str, system: str = 'You are a helpful shell command assistant.',
                 max_tokens: int = 256, timeout: float | None = None) -> str:
        if not isinstance(prompt, str) or not prompt.strip():
            raise ProviderError('AI prompt is empty.')
        if not isinstance(max_tokens, int) or isinstance(max_tokens, bool) or max_tokens <= 0:
            raise ProviderError('Invalid AI token limit.')
        duration = self.config.timeout if timeout is None else timeout
        if not isinstance(duration, (int, float)) or not math.isfinite(duration) or duration <= 0:
            raise ProviderError('Invalid AI timeout.')
        provider = self.config.provider
        url = (self.config.base_url or _DEFAULTS[provider][0]).rstrip('/')
        model = self.config.model or _DEFAULTS[provider][1]
        headers = {'Content-Type': 'application/json'}
        if provider == 'anthropic':
            url += '/messages'
            headers.update({'x-api-key': self.config.api_key, 'anthropic-version': '2023-06-01'})
            payload = {'model': model, 'max_tokens': max_tokens,
                       'system': system, 'messages': [{'role': 'user', 'content': prompt}]}
        elif provider == 'gemini':
            from urllib.parse import quote
            url += f'/models/{quote(model, safe="")}:generateContent'
            headers['x-goog-api-key'] = self.config.api_key
            payload = {'contents': [{'role': 'user', 'parts': [{'text': prompt}]}],
                       'systemInstruction': {'parts': [{'text': system}]},
                       'generationConfig': {'maxOutputTokens': max_tokens}}
        else:
            url += '/chat/completions'
            headers['Authorization'] = f'Bearer {self.config.api_key}'
            payload = {'model': model, 'messages': [{'role': 'system', 'content': system},
                                                    {'role': 'user', 'content': prompt}],
                       'max_tokens': max_tokens}
            # APInex documents low/medium/high reasoning for DeepSeek and GLM.
            # Shell completion should not spend its token budget on deep thinking.
            if provider == 'apinex' and any(family in model.lower() for family in ('deepseek', 'glm')):
                payload['reasoning_effort'] = 'low'
        deadline = time.monotonic() + duration
        self._wait_for_slot(deadline)
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise ProviderError('AI request timed out.')
        try:
            result = requests.post(url, headers=headers, json=payload, timeout=remaining, allow_redirects=False)
        except requests.Timeout:
            raise ProviderError('AI request timed out.') from None
        except requests.RequestException:
            raise ProviderError('AI network request failed.') from None
        if result.status_code == 429:
            cooldown = _retry_after(result.headers.get('Retry-After'))
            with self._lock:
                self._cooldown_until = max(self._cooldown_until, time.monotonic() + cooldown)
            raise ProviderError('AI rate limit reached; try again later.')
        if result.status_code in (401, 403):
            raise ProviderError('AI authentication or access failed.')
        if result.status_code != 200:
            raise ProviderError(f'AI HTTP request failed (status {result.status_code}).')
        try:
            data = result.json()
            if provider == 'anthropic':
                if data.get('stop_reason') == 'max_tokens':
                    raise ProviderError('AI response was truncated.')
                content = ''.join(block['text'] for block in data['content'] if block.get('type') == 'text')
            elif provider == 'gemini':
                candidate = data['candidates'][0]
                if candidate.get('finishReason') == 'MAX_TOKENS':
                    raise ProviderError('AI response was truncated.')
                content = ''.join(part['text'] for part in candidate['content']['parts'] if 'text' in part)
            else:
                choice = data['choices'][0]
                if choice.get('finish_reason') == 'length':
                    raise ProviderError('AI response was truncated.')
                content = choice['message']['content']
            if not isinstance(content, str) or not content.strip():
                raise ProviderError('AI response was empty.')
            return content.strip()
        except ProviderError:
            raise
        except (ValueError, TypeError, KeyError, IndexError, AttributeError):
            raise ProviderError('AI response was malformed.') from None
