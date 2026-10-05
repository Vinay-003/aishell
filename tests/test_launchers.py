import os
import shutil
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_sourced_launcher_works_from_other_directory_and_preserves_failure(tmp_path):
    source = tmp_path / 'source with spaces'
    source.mkdir()
    destination = tmp_path / 'destination with spaces'
    destination.mkdir()
    shutil.copy(ROOT / 'cliffy.sh', source / 'cliffy.sh')
    (source / 'ai_shell_integration.py').write_text('')
    tools = tmp_path / 'bin'
    tools.mkdir()
    fake_python = tools / 'python3'
    fake_python.write_text('#!/usr/bin/env bash\nprintf "%s" "$TARGET" > "$CLIFFY_CWD_FILE"\nexit "${FAKE_EXIT:-0}"\n')
    fake_python.chmod(0o755)
    env = {**os.environ, 'PATH': f'{tools}:{os.environ["PATH"]}', 'TARGET': str(destination)}
    command = 'source "$SOURCE"; result=$?; printf "RESULT=%s\\nCWD=%s\\n" "$result" "$PWD"'
    env['SOURCE'] = str(source / 'cliffy.sh')
    result = subprocess.run(['bash', '-c', command], cwd=tmp_path, env=env, capture_output=True, text=True)
    assert 'RESULT=0' in result.stdout
    assert f'CWD={destination}' in result.stdout
    failed = subprocess.run(['bash', '-c', command], cwd=tmp_path, env={**env, 'FAKE_EXIT': '7'}, capture_output=True, text=True)
    assert 'RESULT=7' in failed.stdout
    assert f'CWD={tmp_path}\n' in failed.stdout


def test_source_entrypoint_forwards_cli_arguments():
    result = subprocess.run(['bash', str(ROOT / 'cliffy'), '--version'], capture_output=True, text=True, timeout=5)
    assert result.returncode == 0
    assert 'cliffy 0.1.0' in result.stdout


def test_pattern_reference_invalid_severity_returns_nonzero():
    import sys
    result = subprocess.run([sys.executable, str(ROOT / 'pattern_reference.py'), 'unknown'], capture_output=True, text=True)
    assert result.returncode != 0
