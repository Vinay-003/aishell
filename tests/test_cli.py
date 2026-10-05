import os
from unittest.mock import Mock
import pytest

import cliffy_cli
import ai_shell_integration as shell


@pytest.fixture(autouse=True)
def private_runtime(tmp_path, monkeypatch):
    monkeypatch.setenv('HOME', str(tmp_path))
    monkeypatch.setenv('CLIFFY_NO_AI', '')
    monkeypatch.setenv('CLIFFY_PROVIDER', 'groq')
    monkeypatch.delenv('CLIFFY_BASE_URL', raising=False)
    monkeypatch.setenv('PYTHON_DOTENV_DISABLED', '1')
    monkeypatch.setattr(shell, 'HISTORY_FILE', str(tmp_path / 'history'))
    monkeypatch.setattr(shell, 'LOG_FILE', str(tmp_path / 'log'))
    monkeypatch.setattr('requests.post', lambda *a, **k: pytest.fail('Live HTTP request'))
    shell._reset_ai_client_for_tests()
    yield
    shell._reset_ai_client_for_tests()


def test_cli_flags_are_forwarded_without_network(monkeypatch):
    runtime = Mock(return_value=0)
    monkeypatch.setattr(cliffy_cli, 'run_runtime', runtime)
    for key in ('CLIFFY_NO_AI', 'CLIFFY_SKIP_STARTUP_CHECK', 'CLIFFY_PROVIDER', 'CLIFFY_MODEL'):
        monkeypatch.setenv(key, '')
    assert cliffy_cli.main(['--no-ai', '--no-startup-check', '--provider', 'openai', '--model', 'test']) == 0
    assert os.environ['CLIFFY_NO_AI'] == '1'
    assert os.environ['CLIFFY_SKIP_STARTUP_CHECK'] == '1'
    assert os.environ['CLIFFY_PROVIDER'] == 'openai'
    runtime.assert_called_once()


def test_main_percent_routes_and_explicit_confirmation(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv('CLIFFY_SKIP_STARTUP_CHECK', '1')
    monkeypatch.setenv('CLIFFY_NO_AI', '1')
    class FakeConfig:
        provider = 'custom'
        model = 'fake'
        api_key = 'fake'
    monkeypatch.setattr(shell, '_get_ai_client', lambda: Mock(config=FakeConfig()))
    requested = []
    monkeypatch.setattr(shell, 'SuggestionEngine', lambda fetch, publish, **kwargs: Mock())
    monkeypatch.setattr(shell, 'interactive_coding', lambda task: requested.append(('code', task)))
    monkeypatch.setattr(shell, 'execute_task', lambda task: requested.append(('task', task)))
    monkeypatch.setattr(shell, 'call_ai_api', lambda prompt, **kw: 'echo reviewed')
    monkeypatch.setattr(shell, 'prompt_command_edit', lambda suggested: suggested)
    monkeypatch.setattr(shell, 'prompt_user_text', lambda _: 'n')
    monkeypatch.setattr(shell, 'execute_command', lambda command: requested.append(('exec', command)))
    class Session:
        def __init__(self, *args, **kwargs):
            from prompt_toolkit.buffer import Buffer
            self.default_buffer = Buffer()
            self.app = None
        def prompt(self):
            return next(inputs)
    inputs = iter(['%%% code', '%% task', '% command', 'exit'])
    monkeypatch.setattr(shell, 'PromptSession', Session)
    shell.main()
    assert requested == [('code', 'code'), ('task', 'task')]


def test_terminal_suggestion_refresh_and_tab(monkeypatch, tmp_path):
    import asyncio
    from prompt_toolkit.input.defaults import create_pipe_input
    from prompt_toolkit.output import DummyOutput
    from prompt_toolkit import PromptSession
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv('CLIFFY_SKIP_STARTUP_CHECK', '1')
    class Config:
        api_key = 'configured'
        provider = 'custom'
        model = 'mock'
    monkeypatch.setattr(shell, '_get_ai_client', lambda: Mock(config=Config()))
    monkeypatch.setattr(shell, 'execute_command', lambda cmd: executed.append(cmd))
    monkeypatch.setattr(shell, 'check_command_safety', lambda _: True)
    executed = []
    class Engine:
        def __init__(self, fetch, publish, **kwargs):
            self.publish = publish
        def request(self, text, context=''):
            if text == 'ec':
                self.publish(text, 'echo hi')
        def clear(self):
            pass
        def close(self):
            pass
    monkeypatch.setattr(shell, 'SuggestionEngine', Engine)
    with create_pipe_input() as pipe:
        monkeypatch.setattr(shell, 'PromptSession', lambda *args, **kwargs: PromptSession(*args, input=pipe, output=DummyOutput(), **kwargs))
        async def drive():
            future = asyncio.to_thread(shell.main)
            task = asyncio.create_task(future)
            await asyncio.sleep(.1)
            pipe.send_text('ec')
            await asyncio.sleep(.2)
            pipe.send_bytes(b'\t\r')
            await asyncio.sleep(.1)
            pipe.send_text('exit\r')
            await asyncio.wait_for(task, 3)
        asyncio.run(drive())
    assert executed == ['echo hi']


def test_no_ai_skips_startup_and_suggestion_workers(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv('CLIFFY_NO_AI', '1')
    monkeypatch.delenv('CLIFFY_SKIP_STARTUP_CHECK', raising=False)
    monkeypatch.setattr(shell, 'SuggestionEngine', Mock(side_effect=AssertionError('worker started')))
    monkeypatch.setattr(shell, 'test_api_connection', Mock(side_effect=AssertionError('network attempted')))
    class Session:
        def __init__(self, *args, **kwargs):
            from prompt_toolkit.buffer import Buffer
            self.default_buffer = Buffer()
            self.app = None
        def prompt(self):
            return 'exit'
    monkeypatch.setattr(shell, 'PromptSession', Session)
    shell._reset_ai_client_for_tests()
    shell.main()


def test_unescaped_cwd_is_safe_prompt_markup(monkeypatch, tmp_path):
    from prompt_toolkit.formatted_text import to_formatted_text
    cwd = tmp_path / '<&>'
    cwd.mkdir()
    monkeypatch.chdir(cwd)
    monkeypatch.setenv('CLIFFY_NO_AI', '1')
    class Session:
        def __init__(self, message, *args, **kwargs):
            from prompt_toolkit.buffer import Buffer
            self.message = message
            self.default_buffer = Buffer()
            self.app = None
        def prompt(self):
            assert '<&>' in ''.join(text for _, text in to_formatted_text(self.message()))
            return 'exit'
    monkeypatch.setattr(shell, 'PromptSession', Session)
    shell.main()


def test_real_engine_async_terminal_right_arrow(monkeypatch, tmp_path):
    import asyncio
    from prompt_toolkit.input.defaults import create_pipe_input
    from prompt_toolkit.output import DummyOutput
    from prompt_toolkit import PromptSession
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv('CLIFFY_SKIP_STARTUP_CHECK', '1')
    monkeypatch.setenv('CLIFFY_DEBOUNCE', '.01')
    monkeypatch.setenv('CLIFFY_CACHE_TTL', '.2')
    monkeypatch.setenv('CLIFFY_SUGGEST_TIMEOUT', '1')
    class Config:
        api_key = 'fake'
        provider = 'custom'
        model = 'mock'
    monkeypatch.setattr(shell, '_get_ai_client', lambda: Mock(config=Config()))
    queries = []
    monkeypatch.setattr(shell, 'call_ai_api', lambda prompt, **kw: queries.append(prompt) or 'echo hi')
    executed = []
    monkeypatch.setattr(shell, 'execute_command', lambda cmd: executed.append(cmd) or 0)
    monkeypatch.setattr(shell, 'check_command_safety', lambda _: True)
    with create_pipe_input() as pipe:
        monkeypatch.setattr(shell, 'PromptSession', lambda *args, **kwargs: PromptSession(*args, input=pipe, output=DummyOutput(), **kwargs))
        async def drive():
            task = asyncio.create_task(asyncio.to_thread(shell.main))
            await asyncio.sleep(.1)
            pipe.send_text('ec')
            await asyncio.sleep(.25)
            pipe.send_bytes(b'\x1b[C\r')
            await asyncio.sleep(.15)
            pipe.send_text('exit\r')
            await asyncio.wait_for(task, 3)
        asyncio.run(drive())
    assert executed == ['echo hi']
    assert len(queries) >= 1


def test_status_and_bare_mode_cancellation(monkeypatch, tmp_path, capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv('CLIFFY_SKIP_STARTUP_CHECK', '1')
    class Config:
        api_key = 'SECRET_SHOULD_NEVER_APPEAR'
        provider = 'custom'
        model = 'mock'
        base_url = 'https://example.invalid/v1'
    monkeypatch.setattr(shell, '_get_ai_client', lambda: Mock(config=Config()))
    monkeypatch.setattr(shell, 'SuggestionEngine', lambda *a, **k: Mock())
    prompts = iter(['n', None, None, None])
    monkeypatch.setattr(shell, 'prompt_user_text', lambda _: next(prompts))
    class Session:
        def __init__(self, *a, **k):
            from prompt_toolkit.buffer import Buffer
            self.default_buffer = Buffer()
            self.app = None
        def prompt(self):
            return next(inputs)
    inputs = iter(['status', '%', '%%', '%%%', 'exit'])
    monkeypatch.setattr(shell, 'PromptSession', Session)
    shell.main()
    output = capsys.readouterr().out
    assert 'configured' in output and 'https://example.invalid/v1' in output
    assert 'SECRET_SHOULD_NEVER_APPEAR' not in output


def test_offline_auto_code_not_executed_as_shell(monkeypatch, tmp_path, capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv('CLIFFY_NO_AI', '1')
    monkeypatch.setenv('CLIFFY_SKIP_STARTUP_CHECK', '1')
    monkeypatch.setattr(shell, 'execute_command', Mock(side_effect=AssertionError('executed')))
    class Session:
        def __init__(self, *a, **k):
            from prompt_toolkit.buffer import Buffer
            self.default_buffer = Buffer()
            self.app = None
        def prompt(self):
            return next(inputs)
    inputs = iter(['ai: generate code', 'exit'])
    monkeypatch.setattr(shell, 'PromptSession', Session)
    shell.main()
    assert 'unavailable' in capsys.readouterr().out


def test_percent_approval_and_status_retest(monkeypatch, tmp_path, capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv('CLIFFY_SKIP_STARTUP_CHECK', '1')
    class Config:
        api_key = 'never_print_this_secret'
        provider = 'custom'
        model = 'mock'
        base_url = 'https://example.invalid/v1'
    monkeypatch.setattr(shell, '_get_ai_client', lambda: Mock(config=Config()))
    monkeypatch.setattr(shell, 'SuggestionEngine', lambda *a, **k: Mock())
    monkeypatch.setattr(shell, 'call_ai_api', lambda *a, **k: '```bash\necho approved\n```')
    monkeypatch.setattr(shell, 'test_api_connection', lambda: True)
    monkeypatch.setattr(shell, 'prompt_command_edit', lambda suggested: suggested)
    replies = iter(['y', 'y'])
    monkeypatch.setattr(shell, 'prompt_user_text', lambda _: next(replies))
    executed = []
    monkeypatch.setattr(shell, 'check_command_safety', lambda _: True)
    monkeypatch.setattr(shell, 'execute_command', lambda cmd: executed.append(cmd) or 0)
    class Session:
        def __init__(self, *a, **k):
            from prompt_toolkit.buffer import Buffer
            self.default_buffer = Buffer()
            self.app = None
        def prompt(self):
            return next(inputs)
    inputs = iter(['status', '% create output', 'exit'])
    monkeypatch.setattr(shell, 'PromptSession', Session)
    shell.main()
    assert executed == ['echo approved']
    assert 'never_print_this_secret' not in capsys.readouterr().out


def test_nonzero_and_eof_do_not_crash(monkeypatch, tmp_path, capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv('CLIFFY_NO_AI', '1')
    monkeypatch.setattr(shell, 'check_command_safety', lambda _: True)
    monkeypatch.setattr(shell, 'execute_command', lambda _: 9)
    class Session:
        def __init__(self, *a, **k):
            from prompt_toolkit.buffer import Buffer
            self.default_buffer = Buffer()
            self.app = None
        def prompt(self):
            return next(inputs)
    inputs = iter(['false', EOFError()])
    def prompt(self):
        answer = next(inputs)
        if isinstance(answer, BaseException):
            raise answer
        return answer
    Session.prompt = prompt
    monkeypatch.setattr(shell, 'PromptSession', Session)
    shell.main()
    assert 'code 9' in capsys.readouterr().out


def test_queued_ui_callback_is_invalidated_after_cursor_move(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv('CLIFFY_SKIP_STARTUP_CHECK', '1')
    class Config:
        api_key = 'fake'
        provider = 'custom'
        model = 'mock'
    monkeypatch.setattr(shell, '_get_ai_client', lambda: Mock(config=Config()))
    callback_queue = []
    made = []
    class Engine:
        def __init__(self, fetch, publish, **kwargs):
            self.publish = publish
        def request(self, text, context=''):
            if text == 'ec':
                self.publish('ec', 'echo hi')
        def clear(self):
            pass
        def close(self):
            pass
    monkeypatch.setattr(shell, 'SuggestionEngine', Engine)
    class Session:
        def __init__(self, *a, **k):
            from prompt_toolkit.buffer import Buffer
            self.default_buffer = Buffer()
            self.app = Mock()
            self.app.loop.call_soon_threadsafe.side_effect = callback_queue.append
            made.append(self)
        def prompt(self):
            if not self.default_buffer.text:
                self.default_buffer.insert_text('ec')
                self.default_buffer.cursor_position = 1
                while callback_queue:
                    callback_queue.pop(0)()
                assert self.default_buffer.suggestion is None
            return 'exit'
    monkeypatch.setattr(shell, 'PromptSession', Session)
    shell.main()
    assert made[0].default_buffer.suggestion is None


def test_terminal_right_moves_cursor_without_suggestion(monkeypatch, tmp_path):
    import asyncio
    from prompt_toolkit.input.defaults import create_pipe_input
    from prompt_toolkit.output import DummyOutput
    from prompt_toolkit import PromptSession
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv('CLIFFY_NO_AI', '1')
    monkeypatch.setenv('CLIFFY_SKIP_STARTUP_CHECK', '1')
    commands = []
    monkeypatch.setattr(shell, 'check_command_safety', lambda _: True)
    monkeypatch.setattr(shell, 'execute_command', lambda cmd: commands.append(cmd) or 0)
    with create_pipe_input() as pipe:
        monkeypatch.setattr(shell, 'PromptSession', lambda *a, **k: PromptSession(*a, input=pipe, output=DummyOutput(), **k))
        async def drive():
            task = asyncio.create_task(asyncio.to_thread(shell.main))
            await asyncio.sleep(.1)
            pipe.send_text('echo')
            await asyncio.sleep(.1)
            pipe.send_bytes(b'\x1b[D\x1b[D\x1b[C')
            await asyncio.sleep(.1)
            pipe.send_text('X\r')
            await asyncio.sleep(.1)
            pipe.send_text('exit\r')
            await asyncio.wait_for(task, 3)
        asyncio.run(drive())
    assert commands == ['echXo']
