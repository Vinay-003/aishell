import io
import os
from unittest.mock import Mock

import pytest

import cliffy_cli
import cliffy_native


@pytest.mark.parametrize('answer', ['echo ok', '```bash\necho ok\n```'])
def test_draft_single_command(monkeypatch, capsys, answer):
    client = Mock()
    client.complete.return_value = answer
    monkeypatch.setattr('cliffy_providers.ProviderConfig.from_env', lambda: Mock())
    monkeypatch.setattr('cliffy_providers.AIClient', lambda _: client)
    monkeypatch.delenv('CLIFFY_NO_AI', raising=False)
    assert cliffy_cli.main(['--draft', 'list files']) == 0
    assert capsys.readouterr().out == 'echo ok\n'
    client.complete.assert_called_once()


@pytest.mark.parametrize('answer', ['', 'echo a\necho b', 'Here is a command: echo hi', 'echo hi\x00', '```bash\necho a\necho b\n```'])
def test_draft_rejects_unsafe_output(monkeypatch, capsys, answer):
    client = Mock()
    client.complete.return_value = answer
    monkeypatch.setattr('cliffy_providers.ProviderConfig.from_env', lambda: Mock())
    monkeypatch.setattr('cliffy_providers.AIClient', lambda _: client)
    monkeypatch.delenv('CLIFFY_NO_AI', raising=False)
    assert cliffy_native.draft('task') == 1
    assert capsys.readouterr().out == ''


def test_native_refuses_non_tty(monkeypatch, capsys):
    monkeypatch.setattr(cliffy_native.sys.stdin, 'isatty', lambda: False)
    assert cliffy_native.launch_bash() == 1
    assert 'terminal' in capsys.readouterr().err


def test_actions_exclusive():
    with pytest.raises(SystemExit):
        cliffy_cli.main(['--draft', 'task', '--shell', 'bash'])


def test_shell_init_quotes_interpreter_and_directory(monkeypatch, capsys):
    monkeypatch.setattr(cliffy_native.sys, 'executable', "/tmp/python's path")
    result = cliffy_native.shell_init()
    assert "_cliffy_python='/tmp/python'\"'\"'s path'" in result
    assert 'READLINE_LINE' in result


def test_launcher_owns_tty_and_cleans_private_rc(monkeypatch, tmp_path):
    monkeypatch.setattr(cliffy_native.sys.stdin, 'isatty', lambda: True)
    monkeypatch.setattr(cliffy_native.sys.stdout, 'isatty', lambda: True)
    monkeypatch.setattr(cliffy_native.Path, 'home', lambda: tmp_path)
    (tmp_path / '.bashrc').write_text('export USER_RC_LOADED=yes\n')
    observed = []

    class Child:
        def wait(self):
            return 7

    def spawn(argv):
        rc = cliffy_native.Path(argv[-2])
        observed.append((argv[:], rc.read_text(), rc.stat().st_mode & 0o777))
        return Child()

    monkeypatch.setattr(cliffy_native.subprocess, 'Popen', spawn)
    assert cliffy_native.launch_bash() == 7
    argv, content, mode = observed[0]
    assert argv[:3] == ['bash', '--noprofile', '--rcfile']
    assert 'USER_RC_LOADED' not in content  # sourced, not copied
    assert 'source ' in content and 'READLINE_LINE' in content
    assert 'BASH_VERSINFO[0]' in content and 'exit 1' in content
    assert mode == 0o600
    assert not cliffy_native.Path(argv[-2]).exists()


def test_launcher_missing_bash_reports_failure(monkeypatch, capsys):
    monkeypatch.setattr(cliffy_native.sys.stdin, 'isatty', lambda: True)
    monkeypatch.setattr(cliffy_native.sys.stdout, 'isatty', lambda: True)
    monkeypatch.setattr(cliffy_native.subprocess, 'Popen', Mock(side_effect=OSError('secret')))
    assert cliffy_native.launch_bash() == 1
    assert 'secret' not in capsys.readouterr().err


def test_draft_missing_provider_and_invalid_task(monkeypatch, capsys):
    monkeypatch.delenv('CLIFFY_NO_AI', raising=False)
    assert cliffy_native.draft('') == 1
    monkeypatch.setattr('cliffy_providers.ProviderConfig.from_env', Mock(side_effect=__import__('cliffy_providers').ProviderError('SECRET')))
    assert cliffy_native.draft('list files') == 1
    captured = capsys.readouterr()
    assert captured.out == '' and 'SECRET' not in captured.err


@pytest.mark.parametrize('answer', ['x' * 8193, '\tprintf ok', 'printf ok\x1f'],
                         ids=['oversized', 'leading-tab', 'trailing-control'])
def test_draft_rejects_oversized_or_edge_control_output(answer):
    assert cliffy_native._command(answer) is None
