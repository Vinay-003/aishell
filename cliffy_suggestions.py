"""Bounded asynchronous shell-command suggestions.

SuggestionEngine(fetch, publish, debounce=.20, ttl=300, max_cache=100) owns one
daemon worker. ``request(text, context='')`` schedules the latest eligible input
after a trailing-edge delay; ``clear()`` cancels pending work and publishes
``('', '')``; ``close()`` stops future requests without blocking on fetch.
``get_cached(text, context='')`` returns a valid exact or shorter-prefix result,
or an empty string. Context is an opaque key (include cwd/provider/model).
``fetch(text) -> str`` runs only on the worker; ``publish(text, suggestion)`` may
run on either the request caller or worker, and must marshal UI updates itself.
Fetch errors are ignored. In-flight network calls cannot be interrupted, but
their outdated results are never published or cached. No network or logging is
performed here.
"""

from collections import OrderedDict
import re
import threading
import time


_CREDENTIAL = re.compile(
    r"(?i)(?:\b[A-Za-z0-9_]*(?:API_KEY|TOKEN|SECRET|PASSWORD|PASSWD|SECRET_ACCESS_KEY)\s*=|\b(?:api[_-]?key|access[_-]?token|secret|password|passwd|authorization|bearer|credential|private[_-]?key)\b\s*(?:[:=]|\s+)\s*\S+|\b(?:sk-[A-Za-z0-9_-]{12,}|gh[pousr]_[A-Za-z0-9_]{12,}|AKIA[A-Z0-9]{16})\b)"
)


def _eligible(text):
    if not isinstance(text, str) or len(text.strip()) < 2 or '\n' in text or '\r' in text:
        return False
    stripped = text.lstrip()
    if stripped.startswith(('%', '?')) or stripped.lower().split(maxsplit=1)[0] in ('exit', 'quit', 'status'):
        return False
    return not _CREDENTIAL.search(text)


def _clean(value, text):
    if not isinstance(value, str):
        return ''
    value = value.strip('\r\n')
    fence = re.fullmatch(r'\s*```[^\n`]*\n(.*?)\n```\s*', value, flags=re.DOTALL)
    if fence:
        value = fence.group(1)
    # Never trim quotes, comments, or the typed whitespace itself.
    if '\n' in value or '\r' in value:
        return ''
    return value if value.startswith(text) and len(value) > len(text) else ''


class SuggestionEngine:
    def __init__(self, fetch, publish, debounce=.20, ttl=300, max_cache=100):
        if debounce < 0 or ttl <= 0 or max_cache < 1:
            raise ValueError('debounce >= 0, ttl > 0 and max_cache >= 1 required')
        self.fetch, self.publish = fetch, publish
        self.debounce, self.ttl, self.max_cache = debounce, ttl, max_cache
        self._cv = threading.Condition()
        self._cache = OrderedDict()
        self._pending = None
        self._current = None
        self._inflight = None
        self._generation = 0
        self._closed = False
        self._worker = threading.Thread(target=self._run, daemon=True, name='cliffy-suggestions')
        self._worker.start()

    def _lookup(self, text, context):
        now = time.monotonic()
        for key, (value, expiry) in tuple(self._cache.items()):
            if expiry <= now:
                del self._cache[key]
        key = (context, text)
        if key in self._cache:
            value = self._cache[key][0]
            self._cache.move_to_end(key)
            return value
        candidates = [(len(prefix), key, value) for key, (value, _) in self._cache.items()
                      for ctx, prefix in (key,) if ctx == context and len(prefix) < len(text)
                      and text.startswith(prefix) and value.startswith(text) and len(value) > len(text)]
        if candidates:
            _, key, value = max(candidates)
            self._cache.move_to_end(key)
            return value
        return ''

    def get_cached(self, text, context=''):
        with self._cv:
            return self._lookup(text, context) if _eligible(text) else ''

    def request(self, text, context=''):
        with self._cv:
            if self._closed:
                return
            key = (context, text)
            if key == self._current:
                return
            self._generation += 1
            generation = self._generation
            self._current = key
            self._pending = None
            cached = self._lookup(text, context) if _eligible(text) else ''
            if not cached and _eligible(text):
                self._pending = (key, generation, time.monotonic() + self.debounce)
            self._cv.notify()
        self._publish(text, cached, generation)

    def _publish(self, text, value, generation):
        with self._cv:
            if self._closed or generation != self._generation:
                return
            # Hold generation lock through callback to prevent a stale publish
            # from racing with clear/request on another thread.
            try:
                self.publish(text, value)
            except Exception:
                pass

    def clear(self):
        with self._cv:
            if self._closed:
                return
            self._generation += 1
            self._current = None
            self._pending = None
            self._cv.notify()
            self._publish('', '', self._generation)

    def close(self):
        with self._cv:
            self._closed = True
            self._generation += 1
            self._pending = None
            self._current = None
            self._cv.notify()

    def _run(self):
        while True:
            with self._cv:
                while not self._closed:
                    if self._pending is None:
                        self._cv.wait()
                        continue
                    key, generation, deadline = self._pending
                    remaining = deadline - time.monotonic()
                    if remaining > 0:
                        self._cv.wait(remaining)
                        continue
                    self._pending = None
                    self._inflight = key
                    break
                if self._closed:
                    return
            context, text = key
            try:
                value = _clean(self.fetch(text), text)
            except Exception:
                value = ''
            with self._cv:
                self._inflight = None
                if self._closed or generation != self._generation or self._current != key:
                    continue
                if value:
                    self._cache[key] = (value, time.monotonic() + self.ttl)
                    self._cache.move_to_end(key)
                    while len(self._cache) > self.max_cache:
                        self._cache.popitem(last=False)
                self._publish(text, value, generation)
