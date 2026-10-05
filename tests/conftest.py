"""Keep every test's environment and runtime artifacts private and isolated."""
import os
from unittest.mock import patch
from urllib.parse import urlsplit

import pytest
import requests


@pytest.fixture(autouse=True)
def isolate_test_process(tmp_path, monkeypatch):
    # CLI flags and builtin export/unset deliberately mutate os.environ.
    # Restore the whole mapping, not just names known to monkeypatch.
    with patch.dict(os.environ, dict(os.environ), clear=True):
        monkeypatch.setenv('HOME', str(tmp_path))
        monkeypatch.setenv('PYTHON_DOTENV_DISABLED', '1')
        import ai_shell_integration as runtime
        monkeypatch.setattr(runtime, 'HISTORY_FILE', str(tmp_path / 'history'))
        monkeypatch.setattr(runtime, 'LOG_FILE', str(tmp_path / 'log'))
        runtime._reset_ai_client_for_tests()
        original = requests.post
        def local_only(url, *args, **kwargs):
            if urlsplit(url).hostname not in {'127.0.0.1', 'localhost', '::1'}:
                pytest.fail('Tests must mock external inference requests')
            return original(url, *args, **kwargs)
        monkeypatch.setattr(requests, 'post', local_only)
        yield
        runtime._reset_ai_client_for_tests()
