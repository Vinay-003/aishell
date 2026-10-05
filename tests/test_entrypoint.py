"""Offline entrypoint contract: metadata operations never import the REPL."""

import os
import subprocess
import sys


def cli(*args, **env):
    values = os.environ.copy()
    values.update(env)
    return subprocess.run(
        [sys.executable, "-m", "cliffy_cli", *args],
        capture_output=True,
        text=True,
        env=values,
        timeout=10,
    )


def test_help_without_runtime_or_home_files(tmp_path):
    result = cli("--help", HOME=str(tmp_path), CLIFFY_API_KEY="")
    assert result.returncode == 0
    assert "--check-api" in result.stdout
    assert "--no-ai" in result.stdout
    assert "--api-key" not in result.stdout
    assert list(tmp_path.iterdir()) == []


def test_version_without_runtime(tmp_path):
    result = cli("--version", HOME=str(tmp_path))
    assert result.returncode == 0
    assert "cliffy" in result.stdout.lower()
    assert list(tmp_path.iterdir()) == []


def test_bad_provider_rejected_without_runtime(tmp_path):
    result = cli("--provider", "definitely-invalid", HOME=str(tmp_path))
    assert result.returncode != 0
    assert "error" in result.stderr.lower()
    assert list(tmp_path.iterdir()) == []


def test_bad_timeout_rejected_without_runtime(tmp_path):
    result = cli("--timeout", "0", HOME=str(tmp_path))
    assert result.returncode != 0
    assert list(tmp_path.iterdir()) == []


def test_check_api_lazily_imports_runtime_to_allow_dotenv(monkeypatch):
    import cliffy_cli
    import types

    # Key may be supplied by runtime's dotenv loader; do not preflight env.
    sentinel = types.ModuleType("ai_shell_integration")
    sentinel.test_api_connection = lambda: True
    monkeypatch.delenv("CLIFFY_NO_AI", raising=False)
    previous = sys.modules.get("ai_shell_integration")
    sys.modules["ai_shell_integration"] = sentinel
    try:
        assert cliffy_cli.main(["--check-api", "--provider", "openai"]) == 0
    finally:
        if previous is None:
            del sys.modules["ai_shell_integration"]
        else:
            sys.modules["ai_shell_integration"] = previous


def test_apinex_provider_is_supported(monkeypatch):
    import cliffy_cli

    called = []
    monkeypatch.setattr(cliffy_cli, "run_runtime", lambda: called.append(os.environ["CLIFFY_PROVIDER"]))
    assert cliffy_cli.main(["--provider", "apinex"]) == 0
    assert called == ["apinex"]


def test_no_ai_check_does_not_import_runtime(monkeypatch):
    import cliffy_cli

    import builtins

    original_import = builtins.__import__

    def blocked_import(name, *args, **kwargs):
        if name == "ai_shell_integration":
            raise AssertionError("runtime imported")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", blocked_import)
    assert cliffy_cli.main(["--no-ai", "--check-api"]) != 0


def test_no_ai_and_startup_check_flags_are_forwarded(monkeypatch):
    import cliffy_cli

    called = []
    monkeypatch.setattr(cliffy_cli, "run_runtime", lambda: called.append(dict(os.environ)))
    assert cliffy_cli.main(["--no-ai", "--no-startup-check", "--provider", "gemini", "--model", "gemini-2.5-flash", "--base-url", "https://example.invalid/v1", "--timeout", "4"]) == 0
    assert called[0]["CLIFFY_NO_AI"] == "1"
    assert called[0]["CLIFFY_SKIP_STARTUP_CHECK"] == "1"
    assert called[0]["CLIFFY_PROVIDER"] == "gemini"
    assert called[0]["CLIFFY_MODEL"] == "gemini-2.5-flash"
    assert called[0]["CLIFFY_BASE_URL"] == "https://example.invalid/v1"
    assert called[0]["CLIFFY_TIMEOUT"] == "4"
