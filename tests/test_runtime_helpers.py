import os
from pathlib import Path
from unittest.mock import patch, Mock
import pytest

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


def test_clean_single_line_handles_empty_and_fenced_commands():
    assert shell.clean_single_line('', 'fallback') == 'fallback'
    assert shell.clean_single_line('```bash\necho hi\n```') == 'echo hi'


def test_generated_paths_cannot_escape_project():
    assert shell.is_probable_filename('main.py')
    assert shell.is_probable_filename('src/main.py')
    assert not shell.is_probable_filename('/tmp/out.py')
    assert not shell.is_probable_filename('../out.py')
    assert not shell.is_probable_filename('src/../../out.py')


def test_remote_script_pipe_requires_confirmation():
    with patch.object(shell, 'call_ai_api', return_value=''), patch('builtins.input', return_value='n'):
        assert shell.check_command_safety('curl https://example.invalid/install.sh | bash') is False


def test_no_ai_mode_does_not_call_provider():
    with patch.dict(os.environ, {'CLIFFY_NO_AI': '1'}), patch('ai_shell_integration.AIClient') as client:
        shell._reset_ai_client_for_tests()
        assert shell.call_ai_api('hello') == ''
        client.assert_not_called()
        shell._reset_ai_client_for_tests()


def test_builtins_and_compound_shell_semantics(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / 'with spaces').mkdir()
    assert shell.execute_command('cd "with spaces"') == 0
    assert Path.cwd() == tmp_path / 'with spaces'
    assert shell.execute_command('cd -') == 0
    assert Path.cwd() == tmp_path
    assert shell.execute_command('export CLIFFY_TEST_VALUE="hello world" CLIFFY_TEST_EMPTY=') == 0
    assert os.environ['CLIFFY_TEST_VALUE'] == 'hello world'
    assert os.environ['CLIFFY_TEST_EMPTY'] == ''
    assert shell.execute_command('unset CLIFFY_TEST_VALUE CLIFFY_TEST_EMPTY') == 0
    assert 'CLIFFY_TEST_VALUE' not in os.environ
    assert shell.execute_command('cd "with spaces" && pwd > result') == 0
    assert Path.cwd() == tmp_path
    assert (tmp_path / 'with spaces' / 'result').exists()
    assert shell.execute_command('false') == 1


def test_safety_checks_all_targets_and_rm_flags(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / 'one').write_text('one')
    (tmp_path / 'two').write_text('two')
    with patch('builtins.input', return_value='n'), patch.object(shell, 'call_ai_api', return_value=''):
        assert shell.check_command_safety('echo x > new && rm -r -f one') is False
        assert shell.check_command_safety('echo x > new > "two"') is False
        assert shell.check_command_safety('echo x | sh') is False


def test_generated_path_guards_and_fenced_code(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / 'outside').symlink_to(tmp_path.parent, target_is_directory=True)
    assert not shell.is_probable_filename('outside/escaped.py')
    assert not shell.is_probable_filename('x\n.py')
    assert not shell.is_probable_filename('..\\escaped.py')
    assert shell.extract_code_block('```python\nprint(1)\n```') == 'print(1)'
    with patch.object(shell, 'call_ai_api', side_effect=['main.py', '```python\nprint(1)\n```']):
        shell.auto_code_task('example')
    assert (tmp_path / 'main.py').read_text() == 'print(1)'


def test_execute_task_stops_after_failed_and_step(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(shell, 'call_ai_api', lambda *a, **k: 'false && touch should_not_exist' if 'Generate a single' in a[0] else '')
    monkeypatch.setattr(shell, 'prompt_command_edit', lambda value: value)
    monkeypatch.setattr(shell, 'prompt_user_text', lambda _: 'y')
    monkeypatch.setattr(shell, 'check_command_safety', lambda _: True)
    shell.execute_task('fail first')
    assert not (tmp_path / 'should_not_exist').exists()


def test_env_loading_current_directory_once_and_disabled(tmp_path, monkeypatch):
    monkeypatch.delenv('PYTHON_DOTENV_DISABLED')
    monkeypatch.chdir(tmp_path)
    load = __import__('dotenv').load_dotenv
    calls = []
    monkeypatch.setattr('dotenv.load_dotenv', lambda **kw: calls.append(kw))
    shell._load_runtime_env()
    shell._load_runtime_env()
    assert calls == [{'dotenv_path': tmp_path / '.env', 'override': False}]
    assert not (tmp_path / '.env').exists()
    shell._reset_ai_client_for_tests()
    monkeypatch.setenv('PYTHON_DOTENV_DISABLED', '1')
    shell._load_runtime_env()
    assert len(calls) == 1


@pytest.mark.parametrize('key,value', [
    ('CLIFFY_DEBOUNCE', 'nan'), ('CLIFFY_DEBOUNCE', '-1'),
    ('CLIFFY_CACHE_TTL', 'inf'), ('CLIFFY_CACHE_TTL', '0'),
    ('CLIFFY_SUGGEST_TIMEOUT', 'bogus'), ('CLIFFY_SUGGEST_TIMEOUT', '301'),
])
def test_invalid_timing_config_is_actionable(key, value, monkeypatch, capsys):
    monkeypatch.setenv(key, value)
    assert shell.main() == 2
    assert key in capsys.readouterr().out


def test_cached_provider_honors_no_ai(monkeypatch):
    fake = object()
    monkeypatch.setattr(shell, '_ai_client', fake)
    monkeypatch.setenv('CLIFFY_NO_AI', 'yes')
    assert shell._get_ai_client() is None
    assert shell.call_ai_api('nothing') == ''


def test_api_connection_failure_and_success_are_scrubbed(monkeypatch, capsys):
    status = shell.api_connection_status
    monkeypatch.setattr(shell, 'call_ai_api', lambda *a, **k: '')
    status.update(connected=False, error_message='AI API key is not configured.')
    assert shell.test_api_connection() is False
    assert 'configured' in capsys.readouterr().out
    monkeypatch.setattr(shell, 'call_ai_api', lambda *a, **k: 'Connected')
    assert shell.test_api_connection() is True
    assert status['connected']


def test_suggestion_clean_prefix_and_timeout(monkeypatch):
    calls = []
    monkeypatch.setattr(shell, 'call_ai_api', lambda prompt, **kw: calls.append(kw) or '```bash\necho hi\n```')
    assert shell.get_ai_suggestion('ec') == 'echo hi'
    assert calls[0]['timeout'] == 10
    assert shell.get_ai_suggestion('xyz') == ''
    assert shell.get_ai_suggestion('x') == ''
    assert len(calls) == 2


def test_completion_file_and_directory(tmp_path, monkeypatch):
    from prompt_toolkit.document import Document
    monkeypatch.chdir(tmp_path)
    (tmp_path / 'src').mkdir()
    (tmp_path / 'script.py').write_text('')
    matches = [x.text for x in shell.FileCompleter().get_completions(Document('sc'), None)]
    assert matches == ['script.py']
    assert [x.text for x in shell.FileCompleter().get_completions(Document('sr'), None)] == ['src/']


def test_interactive_code_single_and_multifile(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(shell, 'ai_parse_task_intent', lambda task: {'needs_dir': True, 'dir_name': 'pkg'})
    monkeypatch.setattr(shell, 'prompt_inline_default', lambda default, prompt='': default)
    monkeypatch.setattr(shell, 'prompt_user_text', lambda prompt: 'y')
    monkeypatch.setattr(shell, 'get_file_plan', lambda task: ['main.py'])
    monkeypatch.setattr(shell, 'call_ai_api', lambda *a, **k: '```python\nprint(1)\n```' if 'Write the complete code' in a[0] else 'main.py')
    shell.interactive_coding('single file')
    assert (tmp_path / 'pkg' / 'main.py').read_text() == 'print(1)'
    monkeypatch.setattr(shell, 'get_file_plan', lambda task: ['src/a.py', 'src/b.py'])
    monkeypatch.setattr(shell, 'call_ai_api', lambda *a, **k: '```python\nprint(2)\n```' if 'Write the complete code' in a[0] else 'main.py')
    shell.interactive_coding('multi file')
    assert (tmp_path / 'pkg' / 'src' / 'a.py').read_text() == 'print(2)'
    assert (tmp_path / 'pkg' / 'src' / 'b.py').read_text() == 'print(2)'


def test_output_symlinks_and_unique_files(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / 'main.py').write_text('old')
    assert shell.ensure_unique_filename('main.py') == 'main_1.py'
    assert shell.save_generated_file('main.py', 'new', unique=True)
    assert (tmp_path / 'main_1.py').read_text() == 'new'
    (tmp_path / 'link.py').symlink_to(tmp_path / 'main.py')
    assert not shell.save_generated_file('link.py', 'bad')
    assert not shell.save_generated_file('.', 'bad')
    assert not shell.save_generated_file('else.py', 'bad', project_root='nested')
    assert (tmp_path / 'main.py').read_text() == 'old'


@pytest.mark.parametrize('command', [
    'curl https://example.invalid/install | bash', 'echo x | sh',
    'echo x && rm -f file', 'rm -r -f file', 'rm -fr file',
    'echo ok && env MODE=x rm -r -f file',
    'echo x > /dev/sda', 'echo x > new > existing',
])
def test_risky_commands_require_confirmation_without_ai(command, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / 'existing').write_text('old')
    monkeypatch.setattr(shell, 'call_ai_api', lambda *a, **k: '')
    monkeypatch.setattr('builtins.input', lambda _: 'n')
    assert shell.check_command_safety(command) is False


@pytest.mark.parametrize('pattern', sorted(shell.DESTRUCTIVE_PATTERNS))
def test_every_configured_destructive_pattern_rejected_without_approval(pattern, monkeypatch):
    monkeypatch.setattr(shell, 'call_ai_api', lambda *a, **k: '')
    monkeypatch.setattr('builtins.input', lambda _: 'n')
    assert shell.check_command_safety(pattern) is False


def test_new_redirect_and_printf_are_not_risky(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(shell, 'call_ai_api', lambda *a, **k: pytest.fail('Unnecessary AI'))
    monkeypatch.setattr('builtins.input', lambda _: pytest.fail('Unnecessary confirmation'))
    assert shell.check_command_safety('printf format > new')
    assert shell.check_command_safety('echo x > /dev/null')


def test_json_fence_and_shell_step_parsing(monkeypatch):
    monkeypatch.setattr(shell, 'call_ai_api', lambda *a, **kw: '```json\n{"needs_dir": true, "dir_name": "nested"}\n```')
    assert shell.ai_parse_task_intent('test')['dir_name'] == 'nested'
    monkeypatch.setattr(shell, 'call_ai_api', lambda *a, **kw: '```json\nnot json\n```')
    assert shell.ai_parse_task_intent('test')['needs_dir'] is False
    assert shell.split_command_steps('echo "a && b" && false') == ['echo "a && b"', 'false']
    assert shell.split_command_steps('false && echo x; echo y') == ['false && echo x; echo y']
    assert shell.split_command_steps('for i in 1 2; do echo $i; done') == ['for i in 1 2; do echo $i; done']


def test_prompt_helpers_and_interrupt(monkeypatch):
    values = iter(['value', 'edited', EOFError(), KeyboardInterrupt()])
    class Session:
        def __init__(self, **kwargs):
            assert kwargs['auto_suggest'] is None
        def prompt(self, text, **kwargs):
            result = next(values)
            if isinstance(result, BaseException):
                raise result
            return result
    monkeypatch.setattr(shell, 'PromptSession', Session)
    assert shell.prompt_user_text('text') == 'value'
    assert shell.prompt_command_edit('original') == 'edited'
    assert shell.prompt_plain_input('text') is None
    assert shell.prompt_inline_default('original', 'text') is None


def test_shell_parent_builtins_and_failures(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv('OLDPWD', raising=False)
    assert shell.execute_command('cd -') == 1
    assert shell.execute_command('cd nowhere') == 1
    assert shell.execute_command('cd a b') == 1
    assert shell.execute_command('export BAD-NAME=1') == 1
    assert shell.execute_command('unset BAD-NAME') == 1
    assert shell.execute_command('') == 0
    assert shell.execute_command('export CLIFFY_TEST_LITERAL=') == 0
    assert os.environ['CLIFFY_TEST_LITERAL'] == ''
    assert shell.execute_command("export CLIFFY_TEST_LITERAL='$HOME'") == 0
    assert os.environ['CLIFFY_TEST_LITERAL'] == '$HOME'
    (tmp_path / '$HOME').mkdir()
    assert shell.execute_command("cd '$HOME'") == 0
    assert Path.cwd() == tmp_path / '$HOME'
    assert shell.execute_command('pwd') == 0
    assert str(tmp_path / '$HOME') in capsys.readouterr().out
    assert shell.execute_command('cd ..') == 0
    assert shell.execute_command('bash -c "exit 7"') == 7
    assert shell.execute_command('alias x="echo x"') == 0
    assert 'do not persist' in capsys.readouterr().out


def test_code_generation_cancel_overwrite_and_empty(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / 'main.py').write_text('old')
    monkeypatch.setattr(shell, 'prompt_user_text', lambda _: 'n')
    assert not shell.save_generated_file('main.py', 'new')
    assert (tmp_path / 'main.py').read_text() == 'old'
    monkeypatch.setattr(shell, 'prompt_user_text', lambda _: 'y')
    assert shell.save_generated_file('main.py', 'new')
    assert (tmp_path / 'main.py').read_text() == 'new'
    monkeypatch.setattr(shell, 'call_ai_api', lambda *a, **k: '')
    shell.auto_code_task('empty response')
    assert not (tmp_path / 'generated_script.py').exists()


def test_interactive_code_rejects_unsafe_generated_directory(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(shell, 'ai_parse_task_intent', lambda task: {'needs_dir': True, 'dir_name': '../escape'})
    monkeypatch.setattr(shell, 'call_ai_api', lambda *a, **k: pytest.fail('No more calls'))
    shell.interactive_coding('do not escape')
    assert not (tmp_path.parent / 'escape').exists()


def test_execute_task_single_compound_reviewed_once(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(shell, 'call_ai_api', lambda *a, **kw: 'echo "a && b" && false; touch yes' if 'Generate a single' in a[0] else '')
    edits = []
    monkeypatch.setattr(shell, 'prompt_command_edit', lambda step: edits.append(step) or step)
    monkeypatch.setattr(shell, 'prompt_user_text', lambda _: 'y')
    monkeypatch.setattr(shell, 'check_command_safety', lambda _: True)
    shell.execute_task('mixed')
    assert edits == ['echo "a && b" && false; touch yes']
    assert (tmp_path / 'yes').exists()


def test_execute_task_keeps_fenced_multiline_as_one_reviewed_unit(monkeypatch):
    monkeypatch.setattr(shell, 'call_ai_api', lambda *a, **k: '```bash\necho first\necho second\n```' if 'Generate a single' in a[0] else '')
    seen = []
    monkeypatch.setattr(shell, 'prompt_command_edit', lambda command: seen.append(command) or '')
    shell.execute_task('multiple shell lines')
    assert seen == ['echo first\necho second']


def test_safety_inconclusive_risky_operation_requires_confirmation(monkeypatch):
    monkeypatch.setattr(shell, 'call_ai_api', lambda *a, **kw: '')
    monkeypatch.setattr('builtins.input', lambda _: 'n')
    assert not shell.check_command_safety('mv old new')
    assert not shell.check_command_safety('broken "unterminated')


def test_ai_client_error_is_nonsecret(monkeypatch):
    monkeypatch.setenv('CLIFFY_API_KEY', 'dummy')
    monkeypatch.setattr(shell, 'AIClient', Mock(side_effect=shell.ProviderError('AI API key is not configured.')))
    assert shell.call_ai_api('any') == ''
    assert shell.api_connection_status['error_message'] == 'AI API key is not configured.'


@pytest.mark.parametrize('response,edit,expected', [
    ('', 'ignored', 0), ('echo x', None, 0), ('echo x', '', 0),
    ('echo x', 'echo x', 1),
])
def test_execute_task_review_boundaries(response, edit, expected, monkeypatch):
    monkeypatch.setattr(shell, 'call_ai_api', lambda *a, **k: response if 'Generate a single' in a[0] else 'Explanation')
    monkeypatch.setattr(shell, 'prompt_command_edit', lambda _: edit)
    monkeypatch.setattr(shell, 'prompt_user_text', lambda _: 'y')
    monkeypatch.setattr(shell, 'check_command_safety', lambda _: True)
    run = Mock(return_value=0)
    monkeypatch.setattr(shell, 'execute_command', run)
    shell.execute_task('review')
    assert run.call_count == expected


def test_execute_task_sudo_and_confirmation(monkeypatch):
    monkeypatch.setattr(shell, 'call_ai_api', lambda *a, **k: 'sudo echo hi' if 'Generate a single' in a[0] else '')
    monkeypatch.setattr(shell, 'prompt_command_edit', lambda x: x)
    monkeypatch.setattr(shell, 'prompt_user_text', lambda _: 'n')
    monkeypatch.setattr(shell, 'execute_command', Mock(side_effect=AssertionError('executed')))
    shell.execute_task('test')
    monkeypatch.setattr(shell, 'call_ai_api', lambda *a, **k: 'echo hi' if 'Generate a single' in a[0] else '')
    shell.execute_task('test')


def test_interactive_coding_declines_and_fallbacks(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(shell, 'ai_parse_task_intent', lambda _: {'needs_dir': False, 'dir_name': ''})
    monkeypatch.setattr(shell, 'prompt_user_text', lambda _: 'n')
    monkeypatch.setattr(shell, 'prompt_inline_default', lambda default, prompt='': default)
    monkeypatch.setattr(shell, 'get_file_plan', lambda _: ['a.py', 'b.py'])
    monkeypatch.setattr(shell, 'call_ai_api', lambda prompt, **kwargs: 'main.py')
    shell.interactive_coding('multiple files')
    assert not (tmp_path / 'a.py').exists()
    monkeypatch.setattr(shell, 'prompt_user_text', lambda _: 'y')
    monkeypatch.setattr(shell, 'call_ai_api', lambda prompt, **kwargs: '')
    shell.interactive_coding('multiple files')
    assert not (tmp_path / 'a.py').exists()


def test_interactive_coding_cancel_after_directory_prompt(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(shell, 'ai_parse_task_intent', lambda _: {'needs_dir': True, 'dir_name': ''})
    monkeypatch.setattr(shell, 'prompt_inline_default', lambda default, prompt='': None)
    shell.interactive_coding('build file')
    assert list(tmp_path.iterdir()) == []


def test_single_code_filename_cancel_and_no_response(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(shell, 'ai_parse_task_intent', lambda _: {'needs_dir': False, 'dir_name': ''})
    monkeypatch.setattr(shell, 'call_ai_api', lambda prompt, **kwargs: 'main.py' if prompt.startswith('Suggest') else '')
    monkeypatch.setattr(shell, 'get_file_plan', lambda _: [])
    monkeypatch.setattr(shell, 'prompt_inline_default', lambda default, prompt='': None)
    shell.interactive_coding('single')
    monkeypatch.setattr(shell, 'prompt_inline_default', lambda default, prompt='': default)
    shell.interactive_coding('single')
    assert list(tmp_path.iterdir()) == []


def test_auto_suggest_cursor_guard(monkeypatch):
    from prompt_toolkit.document import Document
    monkeypatch.setattr(shell, 'current_suggestion', 'echo hi')
    suggest = shell.AIAutoSuggest()
    assert suggest.get_suggestion(None, Document('ec', cursor_position=1)) is None
    assert suggest.get_suggestion(None, Document('ec')).text == 'ho hi'
    assert suggest.get_suggestion(None, Document('xyz')) is None


def test_interactive_coding_directory_fallback_and_multifile_limit(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(shell, 'ai_parse_task_intent', lambda _: {'needs_dir': False, 'dir_name': ''})
    monkeypatch.setattr(shell, 'prompt_inline_default', lambda default, prompt='': default)
    monkeypatch.setattr(shell, 'get_file_plan', lambda _: [f'file{i}.py' for i in range(8)])
    monkeypatch.setattr(shell, 'call_ai_api', lambda prompt, **kwargs: 'print(1)' if 'Write the complete code' in prompt else 'main.py')
    monkeypatch.setattr(shell, 'prompt_user_text', lambda prompt: 'n' if 'More files' in prompt else 'y')
    shell.interactive_coding('new folder named package')
    assert len(list((tmp_path / 'package').glob('file*.py'))) == 6
    assert not (tmp_path / 'package' / 'file6.py').exists()


def test_interactive_coding_directory_confirmation_cancel(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(shell, 'ai_parse_task_intent', lambda _: {'needs_dir': False, 'dir_name': ''})
    monkeypatch.setattr(shell, 'prompt_user_text', lambda _: 'y')
    monkeypatch.setattr(shell, 'prompt_inline_default', lambda default, prompt='': None)
    shell.interactive_coding('create directory')
    assert not list(tmp_path.iterdir())
