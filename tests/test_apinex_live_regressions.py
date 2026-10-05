from unittest.mock import Mock

import ai_shell_integration as runtime
from cliffy_providers import ProviderConfig
from cliffy_providers import AIClient


def test_apinex_default_timeout_includes_request_spacing(monkeypatch):
    monkeypatch.setenv('CLIFFY_PROVIDER', 'apinex')
    monkeypatch.setenv('APINEX_API_KEY', 'fixture-key')
    monkeypatch.delenv('CLIFFY_TIMEOUT', raising=False)
    monkeypatch.delenv('CLIFFY_MIN_INTERVAL', raising=False)
    config = ProviderConfig.from_env()
    assert config.timeout >= config.min_interval + 10


def test_apinex_default_uses_live_verified_free_flash_model(monkeypatch):
    monkeypatch.setenv('CLIFFY_PROVIDER', 'apinex')
    monkeypatch.setenv('APINEX_API_KEY', 'fixture-key')
    monkeypatch.delenv('CLIFFY_MODEL', raising=False)
    monkeypatch.delenv('APINEX_MODEL', raising=False)
    assert ProviderConfig.from_env().model == 'free/glm-5.3-flash'


def test_apinex_suggestion_uses_provider_timeout_by_default(monkeypatch):
    config = ProviderConfig('apinex', 'fixture-key', model='free/deepseek-v4.1-flash', timeout=30, min_interval=12.1)
    monkeypatch.setattr(runtime, '_get_ai_client', lambda: Mock(config=config))
    complete = Mock(return_value='git status')
    monkeypatch.setattr(runtime, 'call_ai_api', complete)
    monkeypatch.delenv('CLIFFY_SUGGEST_TIMEOUT', raising=False)
    assert runtime.get_ai_suggestion('git st') == 'git status'
    assert complete.call_args.kwargs['timeout'] == 30


def test_explicit_suggestion_timeout_still_overrides_provider(monkeypatch):
    monkeypatch.setattr(runtime, '_get_ai_client', lambda: Mock(config=ProviderConfig('apinex', 'fixture-key', timeout=30)))
    complete = Mock(return_value='git status')
    monkeypatch.setattr(runtime, 'call_ai_api', complete)
    monkeypatch.setenv('CLIFFY_SUGGEST_TIMEOUT', '20')
    assert runtime.get_ai_suggestion('git st') == 'git status'
    assert complete.call_args.kwargs['timeout'] == 20


def test_connectivity_probe_has_room_for_a_complete_reply(monkeypatch):
    def complete(prompt, max_tokens=256, **kwargs):
        if max_tokens < 32:
            runtime.api_connection_status['error_message'] = 'AI response was truncated.'
            return ''
        return 'Connected'
    monkeypatch.setattr(runtime, 'call_ai_api', complete)
    assert runtime.test_api_connection() is True


def test_apinex_flash_requests_low_reasoning(monkeypatch):
    response = Mock(status_code=200)
    response.json.return_value = {'choices': [{'message': {'content': 'git status'}, 'finish_reason': 'stop'}]}
    post = Mock(return_value=response)
    monkeypatch.setattr('cliffy_providers.requests.post', post)
    AIClient(ProviderConfig('apinex', 'fixture-key', model='free/deepseek-v4.1-flash', min_interval=0)).complete('Complete git st')
    assert post.call_args.kwargs['json']['reasoning_effort'] == 'low'


def test_apinex_suggestion_budget_includes_thinking_tokens(monkeypatch):
    monkeypatch.setattr(runtime, '_get_ai_client', lambda: Mock(config=ProviderConfig('apinex', 'fixture-key', timeout=30)))
    complete = Mock(return_value='git status')
    monkeypatch.setattr(runtime, 'call_ai_api', complete)
    assert runtime.get_ai_suggestion('git st') == 'git status'
    assert complete.call_args.kwargs['max_tokens'] >= 256


def test_free_apinex_reasoning_models_get_bounded_thinking_headroom(monkeypatch):
    config = ProviderConfig('apinex', 'fixture-key', model='free/deepseek-v4.1-flash', timeout=30)
    client = Mock(config=config)
    client.complete.return_value = 'Connected'
    monkeypatch.setattr(runtime, '_get_ai_client', lambda: client)
    assert runtime.call_ai_api('Reply Connected', max_tokens=32) == 'Connected'
    assert client.complete.call_args.kwargs['max_tokens'] == 1024
    assert runtime.call_ai_api('Write complete code', max_tokens=4096) == 'Connected'
    assert client.complete.call_args.kwargs['max_tokens'] == 4096


def test_task_and_code_extract_fenced_content_surrounded_by_prose():
    response = "Here's the command:\n```bash\nmkdir -p demo && touch demo/marker.txt\n```\nThis creates the requested files."
    assert runtime.extract_code_block(response) == 'mkdir -p demo && touch demo/marker.txt'
    assert runtime.extract_code_block('The Python file:\n```python\nprint("hello")\n```\nDone.') == 'print("hello")'


def test_explicit_system_is_forwarded_without_changing_default_kwargs(monkeypatch):
    client = Mock(config=ProviderConfig('openai', 'fixture-key'))
    client.complete.return_value = 'code'
    monkeypatch.setattr(runtime, '_get_ai_client', lambda: client)
    assert runtime.call_ai_api('default') == 'code'
    assert client.complete.call_args.kwargs == {'max_tokens': 256, 'timeout': None}
    assert runtime.call_ai_api('code prompt', system='Programming assistant') == 'code'
    assert client.complete.call_args.kwargs['system'] == 'Programming assistant'


def test_interactive_code_generation_uses_programming_system(monkeypatch):
    requests = []

    def respond(prompt, **kwargs):
        requests.append((prompt, kwargs))
        return 'print("hello")' if 'Write the complete code' in prompt else 'main.py'

    monkeypatch.setattr(runtime, 'call_ai_api', respond)
    monkeypatch.setattr(runtime, 'ai_parse_task_intent', lambda task: {})
    monkeypatch.setattr(runtime, 'get_file_plan', lambda task: [])
    monkeypatch.setattr(runtime, 'prompt_inline_default', lambda default, prompt: default)
    monkeypatch.setattr(runtime, 'save_generated_file', lambda *args, **kwargs: True)
    runtime.interactive_coding('write hello in python')
    system = requests[-1][1]['system'].lower()
    assert 'programming' in system and 'code only' in system
    assert 'no shell' in system and 'no reasoning' in system and 'no explanation' in system
    assert 'system' not in requests[0][1]


def test_auto_code_generation_uses_programming_system(monkeypatch):
    requests = []

    def respond(prompt, **kwargs):
        requests.append((prompt, kwargs))
        return 'main.py' if 'Suggest a filename' in prompt else 'print("hello")'

    monkeypatch.setattr(runtime, 'call_ai_api', respond)
    monkeypatch.setattr(runtime, 'save_generated_file', lambda *args, **kwargs: True)
    runtime.auto_code_task('write hello in python')
    system = requests[-1][1]['system'].lower()
    assert 'programming' in system and 'code only' in system
    assert 'no shell' in system and 'no reasoning' in system and 'no explanation' in system
    assert 'system' not in requests[0][1]
