# AI Shell Integration
import os
import re
import subprocess
import json
import threading
import shlex
import html
import time
import math
from pathlib import Path
from prompt_toolkit import PromptSession
from prompt_toolkit.auto_suggest import AutoSuggest, Suggestion
from prompt_toolkit.history import FileHistory, InMemoryHistory
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.styles import Style
from prompt_toolkit.completion import Completer, Completion
from cliffy_providers import AIClient, ProviderConfig, ProviderError
from cliffy_suggestions import SuggestionEngine

# ANSI colors for command display
COLOR_CMD = "\033[96m"
COLOR_RESET = "\033[0m"

# Import security configuration
from security_config import (
    DESTRUCTIVE_PATTERNS,
    AI_CHECK_TRIGGERS,
)

# Compatibility surface for external clients; the interactive runtime uses SuggestionEngine.
current_suggestion = ""
suggestion_lock = threading.Lock()
_ai_client = None
_ai_client_lock = threading.Lock()
_dotenv_loaded = False


def _load_runtime_env():
    """Read only the current project's .env, once, when runtime is invoked."""
    global _dotenv_loaded
    if _dotenv_loaded:
        return
    _dotenv_loaded = True
    if os.getenv('PYTHON_DOTENV_DISABLED', '').lower() in {'1', 'true', 'yes', 'on'}:
        return
    from dotenv import load_dotenv
    load_dotenv(dotenv_path=Path.cwd() / '.env', override=False)


def _bounded_env_float(name, default, low, high):
    value = os.getenv(name, str(default))
    try:
        number = float(value)
    except ValueError:
        raise ValueError(f'{name} must be a finite number between {low} and {high}') from None
    if not math.isfinite(number) or not low <= number <= high:
        raise ValueError(f'{name} must be a finite number between {low} and {high}')
    return number

class AIAutoSuggest(AutoSuggest):
    def get_suggestion(self, buffer, document):
        if document.cursor_position != len(document.text):
            return None
        with suggestion_lock:
            value = current_suggestion
        return Suggestion(value[len(document.text):]) if value.startswith(document.text) and len(value) > len(document.text) else None

def get_ai_suggestion(user_input):
    if len(user_input.strip()) < 2:
        return ""
    default_timeout = 10
    max_tokens = 96
    try:
        client = _get_ai_client()
        if client is not None and client.config.provider == 'apinex':
            default_timeout = client.config.timeout
            max_tokens = 256
    except ProviderError:
        pass
    value = clean_single_line(call_ai_api(
        f"Complete this shell command (respond with only the completed command): {user_input}",
        max_tokens=max_tokens, timeout=_bounded_env_float('CLIFFY_SUGGEST_TIMEOUT', default_timeout, 0.1, 300)))
    return value if value.startswith(user_input) and value != user_input else ""

class FileCompleter(Completer):
    """File and directory completer for prompt_toolkit"""
    
    def get_completions(self, document, complete_event):
        text = document.text_before_cursor
        
        # Get the word being completed
        word = text.split()[-1] if text.split() else ""
        
        try:
            if word:
                dirname = os.path.dirname(word) or '.'
                basename = os.path.basename(word)
            else:
                dirname = '.'
                basename = ''
            
            if os.path.isdir(dirname):
                for item in os.listdir(dirname):
                    if item.startswith(basename):
                        full_path = os.path.join(dirname, item)
                        if os.path.isdir(full_path):
                            yield Completion(item + '/', start_position=-len(basename))
                        else:
                            yield Completion(item, start_position=-len(basename))
        except (OSError, PermissionError):
            pass

# Configuration (resolved lazily so `cliffy --help` and offline imports are safe)
HISTORY_FILE = os.path.expanduser("~/.ai_shell_history")
LOG_FILE = os.path.expanduser("~/.ai_shell.log")


def _private_history():
    """Create local private history; fall back to memory for read-only homes."""
    try:
        descriptor = os.open(HISTORY_FILE, os.O_WRONLY | os.O_APPEND | os.O_CREAT | getattr(os, 'O_NOFOLLOW', 0), 0o600)
        with os.fdopen(descriptor, 'a', encoding='utf-8') as handle:
            os.fchmod(handle.fileno(), 0o600)
        return FileHistory(HISTORY_FILE)
    except OSError:
        print('History unavailable; using in-memory history for this session.')
        return InMemoryHistory()

# Security patterns now loaded from security_config.py
# This provides a comprehensive, centralized list of destructive command patterns

# Global connection status
api_connection_status = {"connected": False, "last_check": 0, "error_message": ""}

def log_message(message, level="INFO"):
    """Log messages to file with timestamp"""
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    log_entry = f"[{timestamp}] [{level}] {message}\n"
    try:
        descriptor = os.open(LOG_FILE, os.O_WRONLY | os.O_APPEND | os.O_CREAT | getattr(os, 'O_NOFOLLOW', 0), 0o600)
        with os.fdopen(descriptor, "a", encoding="utf-8") as f:
            os.fchmod(f.fileno(), 0o600)
            f.write(log_entry)
    except Exception:
        pass  # Silent fail if logging doesn't work

def test_api_connection():
    """Test the configured provider without exposing credentials."""
    _load_runtime_env()
    log_message("Testing API connection...", "INFO")
    print("🔄 Testing AI API connection...")
    
    try:
        probe_tokens = 256 if os.getenv('CLIFFY_PROVIDER', '').lower() == 'apinex' else 32
        result = call_ai_api("Reply with exactly Connected. Do not explain or reason.", max_tokens=probe_tokens)
        if result:
            api_connection_status["connected"] = True
            api_connection_status["last_check"] = time.time()
            api_connection_status["error_message"] = ""
            log_message("✓ API connection successful", "INFO")
            print("✅ AI API connected successfully!")
            return True
        error_msg = api_connection_status.get("error_message") or "Provider returned an empty response"
        api_connection_status["connected"] = False
        api_connection_status["last_check"] = time.time()
        log_message("API connection failed", "ERROR")
        print(f"❌ AI API connection failed: {error_msg}")
        return False

    except ProviderError as exc:
        error_msg = str(exc)
        api_connection_status["connected"] = False
        api_connection_status["last_check"] = time.time()
        api_connection_status["error_message"] = error_msg
        log_message(f"✗ API connection timeout", "ERROR")
        print(f"❌ AI API connection timeout")
        return False
        
    except Exception as e:
        error_msg = "Unexpected provider error"
        api_connection_status["connected"] = False
        api_connection_status["last_check"] = time.time()
        api_connection_status["error_message"] = error_msg
        log_message(f"✗ API connection error: {error_msg}", "ERROR")
        print(f"❌ AI API error: {error_msg}")
        return False

def _reset_ai_client_for_tests():
    """Reset lazy provider state; intentionally private and used by tests."""
    global _ai_client, _dotenv_loaded
    with _ai_client_lock:
        _ai_client = None
        _dotenv_loaded = False


def _get_ai_client():
    global _ai_client
    _load_runtime_env()
    with _ai_client_lock:
        if os.getenv("CLIFFY_NO_AI", "").strip().lower() in {"1", "true", "yes", "on"}:
            return None
        if _ai_client is None:
            _ai_client = AIClient(ProviderConfig.from_env())
        return _ai_client


CODE_GENERATION_SYSTEM = (
    "You are a programming assistant. Return complete code only; no shell commands, "
    "no reasoning, no explanation, and no markdown."
)


def call_ai_api(prompt, max_tokens=256, timeout=None, system=None):
    """Complete a prompt through the selected provider, returning empty on failure."""
    try:
        client = _get_ai_client()
        if client is None:
            return ""
        # APInex free DeepSeek/GLM routes count internal thinking toward the
        # output cap, even at low effort. Tiny visible replies can consume >256
        # tokens and otherwise return HTTP 200 with no usable content.
        model = client.config.model or ''
        if client.config.provider == 'apinex' and model.startswith(('free/deepseek', 'free/glm')):
            max_tokens = max(max_tokens, 1024)
        kwargs = {'max_tokens': max_tokens, 'timeout': timeout}
        if system is not None:
            kwargs['system'] = system
        content = client.complete(prompt, **kwargs)
        api_connection_status["connected"] = True
        api_connection_status["error_message"] = ""
        return content
    except ProviderError as exc:
        error_msg = str(exc)
        log_message("API call failed", "ERROR")
        api_connection_status["connected"] = False
        api_connection_status["error_message"] = error_msg
        return ""
    except Exception:
        log_message("API call exception: unexpected provider error", "ERROR")
        api_connection_status["connected"] = False
        api_connection_status["error_message"] = "Unexpected provider error"
        return ""


def check_command_safety(cmd):
    """Confirm deterministic hazards regardless of AI availability or command chaining."""
    try:
        lexer = shlex.shlex(cmd, posix=True, punctuation_chars='|;&<>')
        lexer.whitespace_split = True
        tokens = list(lexer)
    except ValueError:
        print("Unable to inspect command safely.")
        return input("Proceed anyway? [y/N] ").strip().lower() == 'y'
    risks = []
    separators = {';', '&&', '||', '|', '&'}
    segments, segment = [], []
    for token in tokens + [';']:
        if token in separators:
            if segment:
                segments.append(segment)
            segment = []
        else:
            segment.append(token)
    if re.search(r'\|\s*(?:ba)?sh\b', cmd):
        risks.append('Pipe to shell')
    for segment in segments:
        words = [x for x in segment if x not in {'>', '>>', '<', '2>', '2>>'}]
        if words and words[0] == 'sudo':
            risks.append('sudo command')
            words = words[1:]
        while words and (words[0] in {'env', 'command', 'builtin'} or re.fullmatch(r'[A-Za-z_]\w*=.*', words[0])):
            words = words[1:]
        if words and words[0] in {'rm', 'rmdir', 'shred'}:
            risks.append('Deletion command')
        for index, token in enumerate(segment):
            if token in {'>', '2>'}:
                if index + 1 >= len(segment):
                    risks.append('Unclear redirect target')
                else:
                    target = segment[index + 1]
                    if (target.startswith('/dev/') and target != '/dev/null') or os.path.exists(os.path.expanduser(target)) and target != '/dev/null':
                        risks.append(f'Overwrite or special target: {target}')
    for pattern, info in DESTRUCTIVE_PATTERNS.items():
        if pattern.lower() in cmd.lower():
            risks.append(info.get('description', 'Destructive command'))
    if risks:
        print('⚠️  Risk: ' + '; '.join(dict.fromkeys(risks)))
        return input('Proceed? [y/N] ').strip().lower() == 'y'
    operations = {word for segment in segments for word in segment[:1]}
    if operations.intersection(set(AI_CHECK_TRIGGERS) - {'>'}):
        response = call_ai_api(f'Analyze shell command risk. Respond SAFE or DANGEROUS: {cmd}')
        if not response or 'DANGEROUS' in response.upper() or not response.upper().startswith('SAFE'):
            return input('Safety uncertain. Proceed? [y/N] ').strip().lower() == 'y'
    return True

def interactive_coding(task):
    """Interactive code generation session"""
    print(f"Starting interactive coding for: {task}")
    
    intent = ai_parse_task_intent(task)
    directory = intent.get("dir_name") if intent.get("needs_dir") else ""
    if not directory:
        fallback_dir = extract_directory_name(task)
        if fallback_dir:
            directory = fallback_dir
    if not directory and re.search(r"\b(dir|directory|folder)\b", task, re.IGNORECASE):
        confirm = prompt_user_text("Create a new directory? [y/N] ")
        if confirm and confirm.lower() == "y":
            directory = prompt_inline_default("new_project", "Directory: ")
            if directory is None:
                print("\nReturning to main prompt...")
                return
            directory = directory.strip() or "new_project"
    if intent.get("needs_dir") and not directory:
        directory = prompt_inline_default("new_project", "Directory: ")
        if directory is None:
            print("\nReturning to main prompt...")
            return
        directory = directory.strip()
        if not directory:
            directory = "new_project"
    if directory:
        if not is_safe_project_path(directory):
            print("Unsafe directory name.")
            return
        os.makedirs(directory, exist_ok=True)

    file_suggestion = clean_single_line(call_ai_api(f"Suggest a filename for: {task}"), "generated_script.py")
    if not is_probable_filename(file_suggestion):
        file_suggestion = "server.py" if "server" in task.lower() else "main.py"
    filename = prompt_inline_default(file_suggestion, "")
    if filename is None:
        print("\nReturning to main prompt...")
        return
    filename = filename.strip()
    if filename.lower() == "y":
        filename = file_suggestion
    if not filename:
        filename = file_suggestion
    if directory:
        filename = os.path.join(directory, filename)

    file_plan = get_file_plan(task)
    file_plan = [f for f in file_plan if is_probable_filename(f)]
    # If the model doesn't suggest multiple files, treat as single-file
    if not file_plan or len(file_plan) == 1:
        response = call_ai_api(
            "Write the complete code for this task as a single file. "
            "Return ONLY code, no markdown, no explanation.\n\n"
            f"Task: {task}\nFilename: {filename}", max_tokens=4096,
            system=CODE_GENERATION_SYSTEM
        )
        code = extract_code_block(response)
        if not code:
            print("⚠️  No code returned. Try again.")
            return
        if save_generated_file(filename, code, project_root=directory or '.'):
            print(f"Auto-saved to {filename}")
        return

    # Multi-file: generate each file in one shot, per user approval
    for idx, suggested in enumerate(file_plan, start=1):
        if idx > 6:
            more = prompt_user_text("More files detected. Continue? [y/N] ")
            if not more or more.lower() != "y":
                print("Stopping additional files.")
                break
        suggested = clean_single_line(suggested, "generated_file.txt")
        target_file = prompt_inline_default(suggested, "Filename: ")
        if target_file is None:
            print("\nReturning to main prompt...")
            return
        target_file = target_file.strip()
        if target_file.lower() == "y":
            target_file = suggested
        if not target_file:
            target_file = suggested
        if directory:
            target_file = os.path.join(directory, target_file)
        confirm = prompt_user_text(f"Generate {target_file}? [y/N] ")
        if confirm is None:
            print("\nReturning to main prompt...")
            return
        if confirm.lower() != "y":
            print("Skipped.")
            continue
        response = call_ai_api(
            "Write the complete code for this file. Return ONLY code, no markdown, no explanation.\n\n"
            f"Task: {task}\nFilename: {target_file}", max_tokens=4096,
            system=CODE_GENERATION_SYSTEM
        )
        code = extract_code_block(response)
        if not code:
            print("⚠️  No code returned. Try again.")
            continue
        if save_generated_file(target_file, code, project_root=directory or '.'):
            print(f"Auto-saved to {target_file}")

def execute_task(task):
    """Execute a task directly using AI-generated commands"""
    print(f"Executing task: {task}")
    
    # Better prompt with more specific instructions
    command = call_ai_api(f"""Generate a single bash shell command to: {task}.

Examples:
- For "create a file named X": touch X
- For "create a folder named X": mkdir X  
- For "create multiple files": mkdir -p folder && touch folder/file{{1..10}}.txt

Use 'mkdir' for directories/folders, 'touch' for files.
Avoid sudo. Prefer user-level commands (ps, ss, lsof) and no password prompts.
Do NOT include destructive actions like kill/killall/pkill/rm unless explicitly asked.
Respond with only the command.""")
    
    if command:
        command = extract_code_block(command)
        
        steps = split_command_steps(command)
        if not steps:
            print("Sorry, couldn't generate a command for this task.")
            return
        for index, step in enumerate(steps):
            command_to_run = prompt_command_edit(step)
            if command_to_run is None:
                print("\nReturning to main prompt...")
                return
            if command_to_run == "":
                print("Step skipped.")
                continue
            try:
                explanation = call_ai_api(
                    "Explain what this command does in one short sentence. "
                    "No markdown, no bullets.\n"
                    f"Command: {command_to_run}"
                )
            except Exception:
                explanation = ""
            if explanation:
                print(f"Info: {explanation.strip()}")
            if "sudo" in command_to_run:
                warn = prompt_user_text("This step uses sudo. Proceed? [y/N] ")
                if not warn or warn.lower() != "y":
                    print("Step skipped.")
                    continue
            confirm = prompt_user_text("Execute this step? [y/N] ")
            if confirm is None:
                print("\nReturning to main prompt...")
                return
            if confirm.lower() == "y":
                if check_command_safety(command_to_run):
                    print(f"{COLOR_CMD}$ {command_to_run}{COLOR_RESET}")
                    status = execute_command(command_to_run)
                    if status and index < len(steps) - 1 and "&&" in command:
                        print("Stopping after failed command.")
                        break
            else:
                print("Step skipped.")
    else:
        print("Sorry, couldn't generate a command for this task.")

def extract_code_block(text):
    value = (text or '').strip()
    match = re.search(r'^```[^\n`]*\n(.*?)\n```[ \t]*$', value, re.DOTALL | re.MULTILINE)
    return (match.group(1) if match else value).strip()


def is_safe_project_path(name):
    if not isinstance(name, str) or not name or len(name) > 240 or any(ord(c) < 32 for c in name) or '\\' in name:
        return False
    path = Path(name)
    if path.is_absolute() or not path.parts or name in {'.', './'} or any(part in ('', '.', '..') for part in path.parts):
        return False
    return path.resolve().is_relative_to(Path.cwd().resolve())


def save_generated_file(name, code, *, unique=False, project_root='.'):
    if not is_safe_project_path(name):
        print('Unsafe output path.')
        return False
    target = Path(name)
    if not target.resolve().is_relative_to(Path(project_root).resolve()):
        print('Output escapes project directory.')
        return False
    if target.is_symlink():
        print('Refusing symlink output.')
        return False
    overwrite_approved = False
    if unique:
        target = Path(ensure_unique_filename(name))
    elif target.exists():
        if prompt_user_text(f'Overwrite {target}? [y/N] ') != 'y':
            return False
        overwrite_approved = True
    if not is_safe_project_path(str(target)):
        return False
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        flags = os.O_WRONLY | os.O_CREAT | getattr(os, 'O_NOFOLLOW', 0)
        flags |= os.O_TRUNC if overwrite_approved else os.O_EXCL
        descriptor = os.open(target, flags, 0o666)
        with os.fdopen(descriptor, 'w', encoding='utf-8') as output:
            output.write(code)
    except OSError as exc:
        print(f'Output could not be saved: {exc.strerror}')
        return False
    return True


def normalize_filename(name):
    name = (name or '').strip()
    return name if is_probable_filename(name) else 'generated_script.py'


def ensure_unique_filename(name):
    path = Path(name)
    if not path.exists():
        return str(path)
    for i in range(1, 10000):
        candidate = path.with_name(f'{path.stem}_{i}{path.suffix}')
        if not candidate.exists():
            return str(candidate)
    raise RuntimeError('No available filename')


def auto_code_task(task):
    filename = normalize_filename(clean_single_line(call_ai_api(
        f'Suggest a filename for this task. Return only filename. Task: {task}')))
    if not is_safe_project_path(filename):
        print('Unsafe filename.')
        return
    filename = ensure_unique_filename(filename)
    code = extract_code_block(call_ai_api(
        f'Write complete code for task: {task}\nFilename: {filename}. Return code only.',
        max_tokens=4096, system=CODE_GENERATION_SYSTEM))
    if code and save_generated_file(filename, code, unique=True):
        print(f'Code saved to {filename}')
    else:
        print('No code saved.')

def is_auto_code_request(user_input):
    """Detect natural language requests to auto-generate code."""
    text = user_input.strip().lower()
    if text.startswith("ai:") or text.startswith("code:"):
        return True
    starters = ("create ", "build ", "write ", "make ")
    if text.startswith(starters) and (" python" in text or "in python" in text or "python script" in text):
        return True
    return False

def execute_command(cmd):
    """Run simple parent builtins, passing shell grammar to Bash subprocess."""
    cmd = cmd.strip()
    if not cmd:
        return 0
    try:
        lexer = shlex.shlex(cmd, posix=True, punctuation_chars=';&|<>')
        lexer.whitespace_split = True
        parts = list(lexer)
    except ValueError as exc:
        print(f'Shell syntax error: {exc}')
        return 2
    if not parts:
        return 0
    complex_syntax = any(x in {';', '&&', '||', '|', '&', '>', '<', '>>', '<<', '(', ')'} for x in parts) or any(x in cmd for x in ('`', '$(', '${', '\n'))
    if not complex_syntax and parts[0] == 'cd':
        if len(parts) > 2:
            print('cd: too many arguments')
            return 1
        old = os.getcwd()
        destination = parts[1] if len(parts) == 2 else os.path.expanduser('~')
        if destination == '-':
            destination = os.environ.get('OLDPWD', '')
            if not destination:
                print('cd: OLDPWD not set')
                return 1
        if not re.fullmatch(r"cd\s+'[^']*'\s*", cmd):
            destination = os.path.expandvars(os.path.expanduser(destination))
        try:
            os.chdir(destination)
            os.environ['OLDPWD'] = old
            os.environ['PWD'] = os.getcwd()
            if len(parts) > 1 and parts[1] == '-':
                print(os.getcwd())
            return 0
        except OSError as exc:
            print(f'cd: {exc}')
            return 1
    if not complex_syntax and parts[0] == 'pwd' and len(parts) == 1:
        print(os.getcwd())
        return 0
    if not complex_syntax and parts[0] == 'export' and len(parts) > 1:
        literal_names = {match.group(1) for match in re.finditer(
            r"(?<!\S)([A-Za-z_]\w*)='[^']*'(?=\s|$)", cmd)}
        for assignment in parts[1:]:
            name, sep, value = assignment.partition('=')
            if not re.fullmatch(r'[A-Za-z_][A-Za-z_0-9]*', name):
                print('export: invalid variable name')
                return 1
            if sep:
                os.environ[name] = value if name in literal_names else os.path.expandvars(value)
            else:
                os.environ.setdefault(name, '')
        return 0
    if not complex_syntax and parts[0] == 'unset':
        for name in parts[1:]:
            if not re.fullmatch(r'[A-Za-z_][A-Za-z_0-9]*', name):
                print('unset: invalid variable name')
                return 1
            os.environ.pop(name, None)
        return 0
    if parts[0] in {'source', '.', 'alias', 'unalias'}:
        print('Note: shell changes made by this command do not persist in Cliffy.')
    try:
        return subprocess.run(['bash', '-c', cmd], check=False).returncode
    except OSError as exc:
        print(f'Command failed: {exc}')
        return 127

def prompt_plain_input(prompt_text=""):
    """PromptToolkit input without AI suggestions (supports arrows)."""
    try:
        edit_session = PromptSession(
            auto_suggest=None,
            completer=None,
            complete_while_typing=False
        )
        return edit_session.prompt(prompt_text)
    except (EOFError, KeyboardInterrupt):
        return None

def prompt_user_text(prompt_text):
    """Plain input prompt without AI suggestions (supports arrows)."""
    return prompt_plain_input(prompt_text)

def prompt_inline_default(default_text, prompt_text=""):
    """Inline editable prompt with a prefilled default."""
    try:
        edit_session = PromptSession(
            auto_suggest=None,
            completer=None,
            complete_while_typing=False
        )
        return edit_session.prompt(prompt_text, default=default_text)
    except (EOFError, KeyboardInterrupt):
        return None

def prompt_command_edit(suggested_command):
    """Show the suggested command inline and let the user edit before execution."""
    return prompt_inline_default(suggested_command, "")

def clean_single_line(text, fallback=""):
    text = (text or "").strip()
    if "```" in text:
        parts = text.split("```")
        if len(parts) >= 2:
            lines = parts[1].strip().splitlines()
            if lines and re.fullmatch(r"[A-Za-z0-9_+-]+", lines[0].strip()):
                lines = lines[1:]
            text = "\n".join(lines).strip()
    lines = text.splitlines()
    if not lines:
        return fallback
    text = lines[0].strip()
    return text or fallback

def get_file_plan(task):
    """Ask the model for a list of files to generate; return list of filenames."""
    response = call_ai_api(
        "List the files needed for this task. Return one file per line, no bullets, no extra text.\n"
        f"Task: {task}"
    )
    if not response:
        return []
    text = response.strip()
    text = re.sub(r"^```(?:json)?\s*\n|\n```$", "", text, flags=re.IGNORECASE)
    lines = []
    for line in text.splitlines():
        line = line.strip().strip("-").strip("*").strip()
        line = line.strip("`").strip()
        if line:
            lines.append(line)
    return lines

def is_probable_filename(name):
    if not name or len(name) > 120:
        return False
    path = Path(name)
    if path.is_absolute() or ".." in path.parts or any(part in ("", ".") for part in path.parts):
        return False
    if not is_safe_project_path(name):
        return False
    if " " in name and "/" not in name:
        return False
    if name.lower().startswith(("note", "for ", "if ", "depending", "examples")):
        return False
    return any(ch in name for ch in [".", "/"])

def extract_directory_name(task):
    match = re.search(r"new (?:directory|dir|folder) named\s+([A-Za-z0-9._-]+)", task, re.IGNORECASE)
    if match:
        return match.group(1)
    return None

def ai_parse_task_intent(task):
    """Use AI to parse whether a new directory is needed and its name."""
    response = call_ai_api(
        "Parse the task into JSON with keys: needs_dir (true/false), dir_name (string or empty). "
        "Return ONLY JSON.\n"
        f"Task: {task}"
    )
    if not response:
        return {"needs_dir": False, "dir_name": ""}
    text = response.strip()
    text = re.sub(r"^```(?:json)?\s*\n|\n```$", "", text, flags=re.IGNORECASE)
    try:
        data = json.loads(text)
        return {
            "needs_dir": bool(data.get("needs_dir")),
            "dir_name": (data.get("dir_name") or "").strip()
        }
    except Exception:
        return {"needs_dir": False, "dir_name": ""}

def split_command_steps(command):
    """Split a command string into steps on && or ; while respecting quotes."""
    # Mixed operators or embedded shell syntax must remain one reviewed Bash unit.
    if (';' in command and '&&' in command) or any(x in command for x in ('$(', '`', '{', '}', '\n', '||', 'for ', 'while ', 'if ')):
        return [command.strip()] if command.strip() else []
    steps = []
    buf = []
    in_single = False
    in_double = False
    escape = False
    i = 0
    while i < len(command):
        ch = command[i]
        if escape:
            buf.append(ch)
            escape = False
            i += 1
            continue
        if ch == "\\":
            buf.append(ch)
            escape = True
            i += 1
            continue
        if ch == "'" and not in_double:
            in_single = not in_single
            buf.append(ch)
            i += 1
            continue
        if ch == '"' and not in_single:
            in_double = not in_double
            buf.append(ch)
            i += 1
            continue
        if not in_single and not in_double:
            if command.startswith("&&", i):
                step = "".join(buf).strip()
                if step:
                    steps.append(step)
                buf = []
                i += 2
                continue
            if ch == ";":
                step = "".join(buf).strip()
                if step:
                    steps.append(step)
                buf = []
                i += 1
                continue
        buf.append(ch)
        i += 1
    last = "".join(buf).strip()
    if last:
        steps.append(last)
    return [command.strip()] if any(x in command for x in ("$", "`", "{", "}", "|", "\n", "for ", "while ", "if ")) else steps

def _suggestion_context():
    try:
        client = _get_ai_client()
    except ProviderError:
        return None
    if client is None or not client.config.api_key:
        return None
    return (os.getcwd(), client.config.provider, client.config.model)


def main():
    global current_suggestion
    try:
        _load_runtime_env()
        debounce = _bounded_env_float('CLIFFY_DEBOUNCE', .20, 0, 10)
        ttl = _bounded_env_float('CLIFFY_CACHE_TTL', 300, .1, 86400)
        _bounded_env_float('CLIFFY_SUGGEST_TIMEOUT', 10, .1, 300)
    except (ValueError, ImportError) as exc:
        print(f'AI suggestion configuration: {exc}')
        return 2
    style = Style.from_dict({'prompt': '#00aa00 bold', 'auto-suggestion': '#666666'})

    def get_prompt():
        cwd = os.getcwd()
        home = os.path.expanduser('~')
        if cwd == home or cwd.startswith(home + os.sep):
            cwd = '~' + cwd[len(home):]
        return HTML(f'<prompt>{html.escape(cwd)} $ </prompt>')

    session = PromptSession(get_prompt, auto_suggest=AIAutoSuggest(), completer=FileCompleter(),
                            history=_private_history(), style=style, complete_while_typing=True,
                            complete_in_thread=True)
    bindings = KeyBindings()
    generation = 0
    engine = None

    def clear():
        nonlocal generation
        global current_suggestion
        generation += 1
        with suggestion_lock:
            current_suggestion = ''
        if engine:
            engine.clear()
        buffer = session.default_buffer
        buffer.suggestion = None
        if session.app:
            session.app.invalidate()

    def publish(text, value):
        token = generation
        app = session.app
        if app is None or app.loop is None:
            return
        def apply():
            global current_suggestion
            if token != generation:
                return
            buffer = session.default_buffer
            doc = buffer.document
            valid = doc.text == text and doc.cursor_position == len(text) and value.startswith(text) and len(value) > len(text)
            suffix = value[len(text):] if valid else ''
            with suggestion_lock:
                current_suggestion = value if valid else ''
            buffer.suggestion = Suggestion(suffix) if suffix else None
            buffer.on_suggestion_set.fire()
            app.invalidate()
        app.loop.call_soon_threadsafe(apply)

    def fetch(text):
        return get_ai_suggestion(text)

    if _suggestion_context() is not None:
        engine = SuggestionEngine(fetch, publish, debounce=debounce, ttl=ttl)
    elif os.getenv('CLIFFY_NO_AI', '').lower() not in {'1', 'true', 'yes', 'on'}:
        print('AI unavailable: configure a provider API key, or run with --no-ai.')

    def accept(event):
        buffer = event.app.current_buffer
        if buffer.suggestion and buffer.document.cursor_position == len(buffer.text):
            buffer.insert_text(buffer.suggestion.text)
            clear()
            return True
        return False

    @bindings.add('tab')
    def _(event):
        if not accept(event):
            event.app.current_buffer.start_completion()

    @bindings.add('right')
    def _(event):
        if not accept(event):
            buffer = event.app.current_buffer
            buffer.cursor_position = min(len(buffer.text), buffer.cursor_position + 1)

    @bindings.add('c-c')
    def _(event):
        clear()
        event.app.exit(result='INTERRUPT')

    @bindings.add('escape')
    def _(event):
        clear()
        event.app.exit(result='ESCAPE_EXIT')

    session.key_bindings = bindings

    def on_text_changed(_):
        nonlocal generation
        generation += 1
        buffer = session.default_buffer
        if engine and _suggestion_context() is not None and buffer.document.cursor_position == len(buffer.text):
            engine.request(buffer.text, context=_suggestion_context())
        elif engine:
            engine.clear()
    session.default_buffer.on_text_changed += on_text_changed

    def on_cursor_changed(_):
        nonlocal generation
        buffer = session.default_buffer
        if buffer.document.cursor_position != len(buffer.text):
            generation += 1
            with suggestion_lock:
                global current_suggestion
                current_suggestion = ''
            buffer.suggestion = None
            if engine:
                engine.clear()
    session.default_buffer.on_cursor_position_changed += on_cursor_changed

    print('=== AI Shell ===')
    print('TAB accepts suggestions or completes files. RIGHT moves cursor or accepts an end-of-line suggestion.')
    if engine and os.getenv('CLIFFY_SKIP_STARTUP_CHECK', '').lower() not in {'1', 'true', 'yes', 'on'}:
        test_api_connection()
    try:
        while True:
            try:
                user_input = session.prompt()
                clear()
                if user_input in (None, 'INTERRUPT', 'ESCAPE_EXIT'):
                    continue
                user_input = user_input.strip()
                if user_input.lower() in ('exit', 'quit'):
                    break
                if user_input.lower() == 'status':
                    try:
                        client = _get_ai_client()
                    except ProviderError:
                        client = None
                    config = client.config if client else None
                    print('AI: ' + ('connected' if api_connection_status['connected'] else 'disconnected'))
                    print('Key: ' + ('configured' if config and config.api_key else 'not configured'))
                    if config:
                        print(f'Provider: {config.provider}; Model: {config.model}; Endpoint: {config.base_url}')
                    if api_connection_status['error_message']:
                        print('Error: ' + api_connection_status['error_message'])
                    if prompt_user_text('Test connection now? [y/N] ') == 'y' and client:
                        test_api_connection()
                    continue
                if user_input.startswith('%'):
                    if not engine:
                        print('AI is unavailable.')
                        continue
                    mode = len(user_input) - len(user_input.lstrip('%'))
                    if mode > 3:
                        print('Unknown mode.')
                        continue
                    task = user_input[mode:].strip() or prompt_user_text('Task: ')
                    if not task or task.lower() in {'exit', 'quit', 'back'}:
                        continue
                    if mode == 3:
                        interactive_coding(task)
                    elif mode == 2:
                        execute_task(task)
                    else:
                        suggestion = clean_single_line(call_ai_api(f'Generate a single shell command to: {task}'))
                        if suggestion:
                            edited = prompt_command_edit(suggestion)
                            if edited and prompt_user_text('Execute this command? [y/N] ').strip().lower() == 'y' and check_command_safety(edited):
                                execute_command(edited)
                    continue
                if not user_input:
                    continue
                if is_auto_code_request(user_input):
                    if engine:
                        auto_code_task(user_input)
                    else:
                        print('AI is unavailable.')
                elif check_command_safety(user_input):
                    status = execute_command(user_input)
                    if status:
                        print(f'Command exited with code {status}')
            except KeyboardInterrupt:
                clear()
                print('Use exit or quit to leave.')
            except EOFError:
                break
            except Exception:
                log_message('Runtime command failed', 'ERROR')
                print('Command failed.')
    finally:
        clear()
        if engine:
            engine.close()
        cwd_file = os.getenv('CLIFFY_CWD_FILE', '').strip()
        if cwd_file:
            try:
                Path(cwd_file).write_text(os.getcwd())
            except OSError:
                log_message('Failed to write cwd file', 'ERROR')

if __name__ == '__main__':
    main()
