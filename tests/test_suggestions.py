import threading
import time

from cliffy_suggestions import SuggestionEngine


def wait_for(predicate, timeout=2):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(.005)
    assert predicate()


def test_trailing_edge_and_idle_completion():
    calls, published = [], []
    with_engine = SuggestionEngine(lambda text: (calls.append(text), text + ' done')[1],
                                   lambda text, value: published.append((text, value)), debounce=.07)
    try:
        with_engine.request('gi')
        time.sleep(.03)
        with_engine.request('git')
        wait_for(lambda: ('git', 'git done') in published)
        assert calls == ['git']
    finally:
        with_engine.close()


def test_stale_result_and_bounded_latest_pending():
    started, release = threading.Event(), threading.Event()
    calls, published = [], []

    def fetch(text):
        calls.append(text)
        if text == 'first':
            started.set()
            assert release.wait(2)
        return text + ' suffix'

    engine = SuggestionEngine(fetch, lambda text, value: published.append((text, value)), debounce=.02)
    try:
        engine.request('first')
        assert started.wait(2)
        for text in ('second', 'third', 'fourth'):
            engine.request(text)
        release.set()
        wait_for(lambda: ('fourth', 'fourth suffix') in published)
        assert calls == ['first', 'fourth']
        assert ('first', 'first suffix') not in published
    finally:
        release.set()
        engine.close()


def test_context_ttl_lru_prefix_and_duplicates():
    calls, published = [], []
    engine = SuggestionEngine(lambda text: (calls.append(text), text + ' tail')[1],
                              lambda text, value: published.append((text, value)),
                              debounce=.02, ttl=.08, max_cache=2)
    try:
        engine.request('git', 'a')
        engine.request('git', 'a')
        wait_for(lambda: engine.get_cached('git', 'a') == 'git tail')
        assert calls == ['git']
        assert engine.get_cached('git t', 'a') == 'git tail'
        assert engine.get_cached('git', 'b') == ''
        engine.request('grep', 'a')
        wait_for(lambda: engine.get_cached('grep', 'a') != '')
        engine.get_cached('git', 'a')
        engine.request('echo', 'a')
        wait_for(lambda: engine.get_cached('echo', 'a') != '')
        assert engine.get_cached('grep', 'a') == ''
        time.sleep(.1)
        assert engine.get_cached('git', 'a') == ''
    finally:
        engine.close()


def test_clear_close_failure_and_sanitization():
    started, release = threading.Event(), threading.Event()
    published = []

    def fetch(text):
        started.set()
        release.wait(2)
        return '```bash\n' + text + " 'quoted#value' # comment\n```"

    engine = SuggestionEngine(fetch, lambda text, value: published.append((text, value)), debounce=.01)
    engine.request('echo')
    assert started.wait(2)
    engine.clear()
    release.set()
    wait_for(lambda: published and published[-1] == ('', ''))
    assert engine.get_cached('echo') == ''
    engine.request('echo')
    wait_for(lambda: engine.get_cached('echo') != '')
    assert engine.get_cached('echo') == "echo 'quoted#value' # comment"
    engine.close()
    engine.request('unused')
    assert engine.get_cached('unused') == ''


def test_unsafe_inputs_and_invalid_results():
    calls = []
    engine = SuggestionEngine(lambda text: (calls.append(text), 'not a prefix')[1],
                              lambda *_: None, debounce=.01)
    try:
        for text in ('', 'x', '%time ls', '?help', 'exit', 'quit', 'status',
                     'echo a\nb', 'TOKEN=sk-abcdefghijklmnopqrstuvwxyz',
                     'curl -H "Authorization: Bearer secretvalue"'):
            engine.request(text)
        time.sleep(.06)
        assert calls == []
        engine.request('git')
        wait_for(lambda: calls == ['git'])
        assert engine.get_cached('git') == ''
    finally:
        engine.close()
