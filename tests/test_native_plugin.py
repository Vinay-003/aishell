"""The opt-in Bash editing hook never executes generated text."""
import os
import shlex
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / 'cliffy_shell' / 'bash.sh'


def run_hook(tmp_path, draft, output='pwd', status=0):
    stub = tmp_path / 'helper'
    stub.write_text('#!/bin/bash\nprintf "%s" "$*" > ' + shlex.quote(str(tmp_path / 'trace')) +
                    '\nprintf "%s" ' + shlex.quote(output) + '\nexit ' + str(status) + '\n')
    stub.chmod(0o755)
    script = 'source "$PLUGIN"; READLINE_LINE="$DRAFT"; READLINE_POINT=0; _cliffy_generate_draft; printf "RESULT:%s\\nPOINT:%s\\n" "$READLINE_LINE" "$READLINE_POINT"'
    env = dict(os.environ, PLUGIN=str(PLUGIN), DRAFT=draft, _cliffy_python=str(stub),
               _cliffy_cli_module_dir=str(ROOT))
    return subprocess.run(['bash', '--noprofile', '--norc', '-ic', script], env=env,
                          text=True, capture_output=True), tmp_path / 'trace'


def test_draft_replaces_buffer_without_running_it(tmp_path):
    marker = tmp_path / 'marker'
    result, trace = run_hook(tmp_path, f'create file {marker}', f'touch {marker}')
    assert 'RESULT:touch ' in result.stdout
    assert 'POINT:' + str(len(f'touch {marker}')) in result.stdout
    assert '--draft create file ' in trace.read_text()
    assert not marker.exists()
    assert 'review' in result.stderr.lower() and 'enter' in result.stderr.lower()


def test_normal_cli_newline_is_a_terminator_not_unsafe_input(tmp_path):
    result, _ = run_hook(tmp_path, 'show current directory', 'pwd\n')
    assert 'RESULT:pwd\nPOINT:3' in result.stdout


def test_extra_cli_newline_is_rejected(tmp_path):
    result, _ = run_hook(tmp_path, 'original words', 'pwd\n\n')
    assert 'RESULT:original words' in result.stdout


def test_keys_are_not_serialized_as_env_command_arguments():
    # Provider configuration is inherited by Python, not exposed through env argv.
    text = PLUGIN.read_text()
    assert 'env -i' not in text
    assert 'helper_env' not in text


@pytest.mark.parametrize('response,status', [('ignored', 1), ('one\ntwo', 0), ('cmd\r', 0),
                                               ('cmd\x1b[31m', 0), ('x' * 8193, 0)])
def test_invalid_or_failed_output_preserves_buffer(tmp_path, response, status):
    result, _ = run_hook(tmp_path, 'original words', response, status)
    assert 'RESULT:original words' in result.stdout
    assert 'POINT:0' in result.stdout


def test_empty_draft_does_not_invoke_helper(tmp_path):
    result, trace = run_hook(tmp_path, '   ')
    assert not trace.exists()
    assert 'RESULT:   ' in result.stdout
    assert 'type' in result.stderr.lower()


def test_sourcing_is_inert_in_noninteractive_shell():
    result = subprocess.run(['bash', '-c', 'source "$1"; declare -F _cliffy_generate_draft || :', '_', str(PLUGIN)],
                            capture_output=True, text=True)
    assert result.returncode == 0
    assert not result.stdout


def test_plugin_does_not_change_editing_mode_or_prompt():
    text = PLUGIN.read_text()
    assert 'emacs-standard' in text and 'vi-insert' in text
    assert ' -x ' in text
    assert 'PROMPT_COMMAND' not in text
    assert 'eval ' not in text


def test_both_keymaps_register_ctrl_g(tmp_path):
    result, _ = run_hook(tmp_path, 'a request')
    assert result.returncode == 0
    probe = subprocess.run(['bash', '--noprofile', '--norc', '-ic',
                            'source "$PLUGIN"; bind -m emacs-standard -X; bind -m vi-insert -X'],
                           env=dict(os.environ, PLUGIN=str(PLUGIN)), capture_output=True, text=True)
    assert probe.stdout.count('_cliffy_generate_draft') == 2
