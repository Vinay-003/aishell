import os
import time
from pathlib import Path
from unittest.mock import Mock

import ai_shell_integration as runtime
import cliffy_cli
from cliffy_providers import ProviderConfig
from cliffy_suggestions import SuggestionEngine


def test_apinex_defaults_match_documented_free_rpm(monkeypatch):
    monkeypatch.setenv('CLIFFY_PROVIDER', 'apinex')
    monkeypatch.setenv('APINEX_API_KEY', 'fixture-key')
    monkeypatch.delenv('CLIFFY_MIN_INTERVAL', raising=False)
    config = ProviderConfig.from_env()
    assert config.min_interval >= 12


def test_cli_propagates_runtime_configuration_error(monkeypatch):
    monkeypatch.setattr(runtime, 'main', lambda: 2)
    assert cliffy_cli.run_runtime() == 2


def test_secret_env_assignment_is_never_suggested():
    calls = []
    engine = SuggestionEngine(lambda text: calls.append(text) or text + ' suffix', lambda *a: None, debounce=.01)
    try:
        for text in ('export GROQ_API_KEY=privatevalue', 'export OPENAI_API_KEY=privatevalue',
                     'export MY_TOKEN=privatevalue', 'export AWS_SECRET_ACCESS_KEY=privatevalue',
                     'export TOKEN=privatevalue'):
            engine.request(text)
            time.sleep(.02)
        assert calls == []
    finally:
        engine.close()


def test_racing_new_generated_file_does_not_get_overwritten(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    real_mkdir = Path.mkdir
    def race(parent, *args, **kwargs):
        real_mkdir(parent, *args, **kwargs)
        Path('main.py').write_text('existing data')
    monkeypatch.setattr(Path, 'mkdir', race)
    assert runtime.save_generated_file('main.py', 'new code') is False
    assert Path('main.py').read_text() == 'existing data'


def test_private_log_is_not_world_readable(monkeypatch, tmp_path):
    target = tmp_path / 'private-log'
    monkeypatch.setattr(runtime, 'LOG_FILE', str(target))
    runtime.log_message('metadata only')
    assert target.stat().st_mode & 0o777 == 0o600


def test_private_history_is_not_world_readable(monkeypatch, tmp_path):
    target = tmp_path / 'private-history'
    monkeypatch.setattr(runtime, 'HISTORY_FILE', str(target))
    history = runtime._private_history()
    history.append_string('echo harmless')
    assert target.stat().st_mode & 0o777 == 0o600
