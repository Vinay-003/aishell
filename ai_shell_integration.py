# AI Shell Integration
import os
import re
# import readline
import subprocess
import json
import requests
import threading
import queue
import time
from pathlib import Path
from prompt_toolkit import PromptSession
from prompt_toolkit.auto_suggest import AutoSuggest, Suggestion
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.styles import Style
from prompt_toolkit.completion import Completer, Completion

# ANSI colors for command display
COLOR_CMD = "\033[96m"
COLOR_RESET = "\033[0m"

# Import security configuration
from security_config import (
    DESTRUCTIVE_PATTERNS,
    AI_CHECK_TRIGGERS,
    SEVERITY_INFO,
    SAFE_COMMANDS
)

# Load .env if available (optional dependency)
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

# Global state for suggestions with caching
current_suggestion = ""
suggestion_lock = threading.Lock()
suggestion_cache = {}
cache_lock = threading.Lock()
last_api_call_time = 0
api_call_lock = threading.Lock()
MIN_API_CALL_INTERVAL = 0.1  # Minimum seconds between API calls (faster response)

class AIAutoSuggest(AutoSuggest):
    """Custom AutoSuggest class for AI-powered command completion."""
    def get_suggestion(self, _buffer, document):
        typed_text = document.text
        if not typed_text.strip():
            return None
            
        with suggestion_lock:
            suggestion = current_suggestion
        
        log_message(f"AIAutoSuggest: typed='{typed_text}', current_suggestion='{suggestion}'", "DEBUG")
            
        if suggestion and suggestion.startswith(typed_text) and suggestion != typed_text:
            result = Suggestion(suggestion[len(typed_text):])
            log_message(f"AIAutoSuggest: returning '{result.text}'", "DEBUG")
            return result
        return None

def get_cached_suggestion_for(text):
    """Return a cached suggestion that still matches the current text."""
    best_suggestion = ""
    best_key_len = -1
    with cache_lock:
        # Exact match first
        if text in suggestion_cache:
            return suggestion_cache[text]
        # Fallback: reuse a cached suggestion from a shorter prefix
        for key, suggestion in suggestion_cache.items():
            if not suggestion:
                continue
            if suggestion.startswith(text) and len(key) > best_key_len:
                best_suggestion = suggestion
                best_key_len = len(key)
    return best_suggestion

def get_ai_suggestion(user_input):
    """Get command completion suggestions with caching."""
    global last_api_call_time
    
    try:
        if len(user_input.strip()) < 2:
            return ""

        # Check cache first
        cached = get_cached_suggestion_for(user_input)
        if cached:
            log_message(f"Cache hit for: {user_input}", "DEBUG")
            return cached

        # Rate limiting to prevent too many API calls
        with api_call_lock:
            current_time = time.time()
            time_since_last_call = current_time - last_api_call_time
            if time_since_last_call < MIN_API_CALL_INTERVAL:
                time.sleep(MIN_API_CALL_INTERVAL - time_since_last_call)
            last_api_call_time = time.time()

        log_message(f"Requesting suggestion for: {user_input}", "DEBUG")
        
        # Better prompt instead of just "Complete: {input}"
        suggestion = call_ai_api(f"Complete this shell command (respond with only the completed command, no explanations): {user_input}")
        
        # Clean the response
        suggestion = suggestion.strip().split("\n")[0].split("#")[0].strip()
        suggestion = suggestion.strip('"').strip("'")
        
        if " - " in suggestion:
            suggestion = suggestion.split(" - ")[0].strip()
        
        # Validate
        if not suggestion or not suggestion.startswith(user_input) or suggestion == user_input:
            suggestion = ""
        
        # Cache the result
        with cache_lock:
            suggestion_cache[user_input] = suggestion
            # Keep cache size manageable
            if len(suggestion_cache) > 100:
                oldest_keys = list(suggestion_cache.keys())[:20]
                for key in oldest_keys:
                    del suggestion_cache[key]
        
        return suggestion
        
    except Exception as e:
        return ""

def fetch_suggestion_async(text, session):
    """Fetch suggestions asynchronously with debouncing."""
    global current_suggestion
    
    if len(text.strip()) < 2:
        with suggestion_lock:
            current_suggestion = ""
        return
    
    # Skip if command seems complete
    if text.endswith(" ") and len(text.strip().split()) >= 2:
        with suggestion_lock:
            current_suggestion = ""
        return

    # Reuse cached/previous suggestions when possible
    cached = get_cached_suggestion_for(text)
    if cached:
        with suggestion_lock:
            current_suggestion = cached
        if session.app:
            session.app.invalidate()
        return
    with suggestion_lock:
        if current_suggestion and current_suggestion.startswith(text):
            return
    
    log_message(f"Fetching suggestion for: '{text}'", "DEBUG")
    suggestion = get_ai_suggestion(text)
    log_message(f"Got suggestion: '{suggestion}'", "DEBUG")
    
    with suggestion_lock:
        current_suggestion = suggestion
    
    if session.app:
        session.app.invalidate()
    
    log_message(f"Updated current_suggestion to: '{current_suggestion}'", "DEBUG")

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

# Configuration
API_KEY = os.getenv("GROQ_API_KEY", "").strip()
API_ENDPOINT = os.getenv("GROQ_API_ENDPOINT", "https://api.groq.com/openai/v1").strip()
MODEL = os.getenv("GROQ_MODEL", "llama-3.1-8b-instant").strip()
HISTORY_FILE = os.path.expanduser("~/.ai_shell_history")
LOG_FILE = os.path.expanduser("~/.ai_shell.log")

# Security patterns now loaded from security_config.py
# This provides a comprehensive, centralized list of destructive command patterns

# Initialize history file
Path(HISTORY_FILE).touch(exist_ok=True)

# Global connection status
api_connection_status = {"connected": False, "last_check": 0, "error_message": ""}

def log_message(message, level="INFO"):
    """Log messages to file with timestamp"""
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    log_entry = f"[{timestamp}] [{level}] {message}\n"
    try:
        with open(LOG_FILE, "a") as f:
            f.write(log_entry)
    except Exception:
        pass  # Silent fail if logging doesn't work

def test_api_connection():
    """Test the API connection and log the result"""
    log_message("Testing API connection...", "INFO")
    print("🔄 Testing AI API connection...")
    
    try:
        if not API_KEY:
            raise ValueError("GROQ_API_KEY is not set")
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {API_KEY}"
        }
        data = {
            "model": MODEL,
            "messages": [
                {
                    "role": "system",
                    "content": "You are a helpful assistant."
                },
                {
                    "role": "user",
                    "content": "Say 'Connected' if you receive this message."
                }
            ],
            "max_tokens": 10
        }
        
        response = requests.post(f"{API_ENDPOINT}/chat/completions", 
                               headers=headers, json=data, timeout=10)
        
        if response.status_code == 200:
            result = response.json()
            api_connection_status["connected"] = True
            api_connection_status["last_check"] = time.time()
            api_connection_status["error_message"] = ""
            log_message("✓ API connection successful", "INFO")
            print("✅ AI API connected successfully!")
            return True
        else:
            error_msg = f"HTTP {response.status_code}: {response.text[:100]}"
            api_connection_status["connected"] = False
            api_connection_status["last_check"] = time.time()
            api_connection_status["error_message"] = error_msg
            log_message(f"✗ API connection failed: {error_msg}", "ERROR")
            print(f"❌ AI API connection failed: {error_msg}")
            return False
            
    except requests.exceptions.Timeout:
        error_msg = "Connection timeout (>10s)"
        api_connection_status["connected"] = False
        api_connection_status["last_check"] = time.time()
        api_connection_status["error_message"] = error_msg
        log_message(f"✗ API connection timeout", "ERROR")
        print(f"❌ AI API connection timeout")
        return False
        
    except requests.exceptions.ConnectionError:
        error_msg = "Network connection error"
        api_connection_status["connected"] = False
        api_connection_status["last_check"] = time.time()
        api_connection_status["error_message"] = error_msg
        log_message(f"✗ Network connection error", "ERROR")
        print(f"❌ Network connection error")
        return False
        
    except Exception as e:
        error_msg = str(e)
        api_connection_status["connected"] = False
        api_connection_status["last_check"] = time.time()
        api_connection_status["error_message"] = error_msg
        log_message(f"✗ API connection error: {error_msg}", "ERROR")
        print(f"❌ AI API error: {error_msg}")
        return False

def call_ai_api(prompt):
    """Make API call with better prompts for more specific responses"""
    if not API_KEY:
        log_message("GROQ_API_KEY is not set", "ERROR")
        return ""
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {API_KEY}"
    }
    data = {
        "model": MODEL,
        "messages": [
            {
                "role": "system",
                "content": "You are a helpful shell command assistant. Always provide specific, practical commands."
            },
            {
                "role": "user",
                "content": prompt
            }
        ],
        "max_tokens": 150
    }
    
    try:
        response = requests.post(f"{API_ENDPOINT}/chat/completions", 
                               headers=headers, json=data, timeout=10)
        
        if response.status_code == 200:
            result = response.json()
            content = result["choices"][0]["message"]["content"].strip()
            # Update connection status on successful call
            api_connection_status["connected"] = True
            api_connection_status["error_message"] = ""
            return content
        else:
            error_msg = f"API Error: {response.status_code}"
            log_message(f"API call failed: {error_msg}", "ERROR")
            api_connection_status["connected"] = False
            api_connection_status["error_message"] = error_msg
            return ""
    except Exception as e:
        error_msg = f"Request failed: {str(e)}"
        log_message(f"API call exception: {error_msg}", "ERROR")
        api_connection_status["connected"] = False
        api_connection_status["error_message"] = error_msg
        return ""


def suggest_command_threaded(task):
    """Get command suggestion from AI using threading"""
    result_queue = queue.Queue()
    thread = SuggestionThread(task, result_queue)
    thread.start()
    
    print("Getting suggestion...")
    
    try:
        # Wait for result with timeout
        result_type, result = result_queue.get(timeout=10)
        if result_type == 'success':
            return result
        else:
            return f"Error getting suggestion: {result}"
    except queue.Empty:
        return "Suggestion timed out"

def check_command_safety(cmd):
    """
    Two-stage safety check:
    STAGE 1: Fast pattern-based detection for known destructive commands
    STAGE 2: AI analysis for potentially risky commands not caught by patterns
    
    IMPORTANT: Safe command whitelist is NOT used to bypass checks.
    We check for dangerous patterns/operators FIRST, regardless of the base command.
    """
    # Handle sudo commands by extracting the actual command
    actual_cmd = cmd
    if cmd.strip().startswith('sudo '):
        actual_cmd = cmd.strip()[5:]  # Remove 'sudo ' prefix
        print("⚠️  WARNING: Running command with sudo privileges!")
    
    # ===================================================================
    # PRE-CHECK: Detect command chaining and dangerous operators
    # ===================================================================
    # Check for command chaining (;, &&, ||, |) that could combine safe + dangerous
    has_chaining = any(op in actual_cmd for op in [';', '&&', '||'])
    has_pipe = '|' in actual_cmd and not any(safe in actual_cmd for safe in ['||'])
    
    # If command has chaining or pipes, we CANNOT use safe whitelist
    # Example: "ls && rm -rf /" - "ls" is safe but the chain is dangerous
    can_use_whitelist = not (has_chaining or has_pipe)
    
    # Track if we've already handled the command
    overwrite_handled = False
    deletion_handled = False
    
    # ===================================================================
    # STAGE 1: Pattern-based detection (Fast, no AI needed)
    # ===================================================================
    pattern_matched = False
    matched_pattern = None
    pattern_info = None
    
    for pattern, info in DESTRUCTIVE_PATTERNS.items():
        # Use word boundaries for better matching
        if pattern in actual_cmd:
            pattern_matched = True
            matched_pattern = pattern
            pattern_info = info
            break
    
    if pattern_matched:
        # Display warning based on severity
        severity_emoji = {
            "critical": "🔴",
            "high": "🟠", 
            "medium": "🟡",
            "low": "🟢"
        }
        emoji = severity_emoji.get(pattern_info["severity"], "⚠️")
        
        print(f"\n{emoji} DANGER: {pattern_info['severity'].upper()} risk command detected!")
        print(f"Pattern: '{matched_pattern}'")
        print(f"Risk: {pattern_info['description']}")
        
        # Count affected files for rm commands
        if "rm" in actual_cmd:
            target_match = re.search(r'rm\s+(?:-[rf]*\s+)?(.+)', actual_cmd)
            if target_match:
                target = target_match.group(1).strip()
                try:
                    if os.path.exists(target):
                        if os.path.isfile(target):
                            print(f"📄 This will delete 1 file: {target}")
                        elif os.path.isdir(target):
                            result = subprocess.run(f"find '{target}' -type f 2>/dev/null | wc -l", 
                                                  shell=True, capture_output=True, text=True)
                            file_count = result.stdout.strip()
                            dir_result = subprocess.run(f"find '{target}' -type d 2>/dev/null | wc -l", 
                                                      shell=True, capture_output=True, text=True)
                            dir_count = int(dir_result.stdout.strip()) - 1
                            print(f"📁 This will delete {file_count} files in {dir_count} directories")
                    else:
                        print(f"❓ Target '{target}' does not exist")
                except Exception as e:
                    print(f"⚠️  Could not analyze target: {e}")
        
        print()
        confirm = input("⚙️  Do you want to proceed? (y/n): ")
        if confirm.lower() != "y":
            print("❌ Command cancelled.")
            return False
        print("✅ Proceeding...\n")
        return True
    
    # ===================================================================
    # Check for file overwrite operations (>)
    # ===================================================================
    overwrite_handled = False
    if ">" in actual_cmd and not ">>" in actual_cmd:
        target_match = re.search(r'>\s*([^\s|;&]+)', actual_cmd)
        if target_match:
            target_file = target_match.group(1).strip()
            
            # Check if redirecting to dangerous target (device, /dev/null, etc.)
            dangerous_targets = ['/dev/sd', '/dev/hd', '/dev/nvme', '/dev/null']
            is_dangerous_target = any(target_file.startswith(dt) for dt in dangerous_targets)
            
            # Only warn if file exists OR target is dangerous
            if os.path.exists(target_file) or is_dangerous_target:
                if os.path.exists(target_file):
                    file_size = os.path.getsize(target_file)
                    print(f"\n⚠️  WARNING: File overwrite detected!")
                    print(f"📄 Will overwrite: '{target_file}' ({file_size} bytes)")
                elif is_dangerous_target:
                    print(f"\n🔴 DANGER: Writing to device/special file!")
                    print(f"Target: '{target_file}'")
                
                confirm = input("⚙️  Do you want to proceed? (y/n): ")
                if confirm.lower() != "y":
                    print("❌ Command cancelled.")
                    return False
                print("✅ Proceeding...\n")
                overwrite_handled = True
            else:
                # Simple redirect to new file - no warning needed
                overwrite_handled = True
    
    # ===================================================================
    # Simple file deletion check (rm without dangerous flags)
    # ===================================================================
    deletion_handled = False
    if actual_cmd.strip().startswith('rm '):
        # Extract target file(s)
        target_match = re.search(r'rm\s+(?:-[^\s]*\s+)?(.+)', actual_cmd)
        if target_match:
            targets = target_match.group(1).strip().split()
            file_count = 0
            existing_files = []
            
            for target in targets:
                if os.path.exists(target):
                    if os.path.isfile(target):
                        file_count += 1
                        existing_files.append(target)
            
            if file_count > 0:
                print()
                if file_count == 1:
                    print(f"⚠️  Will delete 1 file: {existing_files[0]}")
                else:
                    print(f"⚠️  Will delete {file_count} files: {', '.join(existing_files[:3])}{' ...' if file_count > 3 else ''}")
                
                confirm = input("⚙️  Do you want to proceed? (y/n): ")
                if confirm.lower() != "y":
                    print("❌ Command cancelled.")
                    return False
                print("✅ Proceeding...\n")
                deletion_handled = True  # Mark that we already confirmed deletion
    
    # ===================================================================
    # STAGE 2: AI-based analysis (Only if needed)
    # ===================================================================
    # Check if command needs AI analysis
    needs_ai_check = False
    for trigger in AI_CHECK_TRIGGERS.keys():
        if trigger in actual_cmd.lower():
            needs_ai_check = True
            break
    
    # Skip AI check if:
    # 1. Pattern was already matched (already handled)
    # 2. Redirect was already handled (even with chaining, if only redirect danger)
    # 3. Deletion was already confirmed by user
    # 4. Command is obviously safe (no chaining, only basic redirect)
    # 
    # Logic: If we already warned and got user confirmation,
    # DON'T ask again with AI - that's terrible UX (double confirmation)
    skip_ai = pattern_matched or overwrite_handled or deletion_handled
    
    # Additional check: if chaining exists, check if non-redirect parts are safe
    if has_chaining and overwrite_handled and not pattern_matched:
        # Split command and check each part
        # If all parts are either handled redirects or safe commands, skip AI
        parts = []
        for sep in ['&&', '||', ';', '|']:
            if sep in actual_cmd:
                parts = [p.strip() for p in actual_cmd.split(sep)]
                break
        
        # Check if remaining parts are just echo/safe commands
        all_safe = True
        for part in parts:
            # Skip empty parts
            if not part:
                continue
            # Check if this part has dangerous patterns (not just >)
            has_danger = False
            for pattern in DESTRUCTIVE_PATTERNS.keys():
                if pattern in part and pattern != '>':
                    has_danger = True
                    break
            # If part has rm, mv, cp (dangerous file ops), needs checking
            if any(cmd in part.split()[0] if part.split() else '' 
                   for cmd in ['rm', 'mv', 'dd', 'shred', 'truncate']):
                has_danger = True
            
            if has_danger:
                all_safe = False
                break
        
        if all_safe:
            skip_ai = True
    
    if needs_ai_check and not skip_ai:
        log_message(f"Sending command for AI safety analysis: {actual_cmd}", "INFO")
        print("🤖 Running AI safety analysis...")
        
        safety_response = call_ai_api(
            f"Analyze this command for destructiveness. Respond ONLY with: SAFE or DANGEROUS: <one sentence reason>\nCommand: {actual_cmd}"
        )
        
        if safety_response and "DANGEROUS" in safety_response.upper():
            print(f"\n🤖 AI Safety Analysis: {safety_response}")
            confirm = input("⚙️  Do you want to proceed anyway? (y/n): ")
            if confirm.lower() != "y":
                print("❌ Command cancelled.")
                return False
            print("✅ Proceeding...\n")
        elif safety_response and "SAFE" in safety_response.upper():
            log_message(f"AI marked command as safe: {actual_cmd}", "INFO")
        else:
            log_message(f"AI analysis inconclusive: {actual_cmd}", "WARNING")
    
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

    def extract_code_block(text):
        text = (text or "").strip()
        if "```" in text:
            parts = text.split("```")
            if len(parts) >= 2:
                block = parts[1]
                lines = block.splitlines()
                if lines and lines[0].strip().isalpha():
                    lines = lines[1:]
                return "\n".join(lines).strip()
        return text

    file_plan = get_file_plan(task)
    file_plan = [f for f in file_plan if is_probable_filename(f)]
    # If the model doesn't suggest multiple files, treat as single-file
    if not file_plan or len(file_plan) == 1:
        response = call_ai_api(
            "Write the complete code for this task as a single file. "
            "Return ONLY code, no markdown, no explanation.\n\n"
            f"Task: {task}\nFilename: {filename}"
        )
        code = extract_code_block(response)
        if not code:
            print("⚠️  No code returned. Try again.")
            return
        with open(filename, "w") as f:
            f.write(code)
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
            f"Task: {task}\nFilename: {target_file}"
        )
        code = extract_code_block(response)
        if not code:
            print("⚠️  No code returned. Try again.")
            continue
        with open(target_file, "w") as f:
            f.write(code)
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
        # Clean markdown formatting
        command = command.strip()
        if command.startswith('```'):
            lines = command.split('\n')
            # Find the actual command line (skip ```bash or similar)
            for line in lines[1:]:
                if line.strip() and not line.startswith('```'):
                    command = line.strip()
                    break
        command = command.strip().strip("`")
        
        steps = split_command_steps(command)
        if not steps:
            print("Sorry, couldn't generate a command for this task.")
            return
        for step in steps:
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
                    execute_command(command_to_run)
            else:
                print("Step skipped.")
    else:
        print("Sorry, couldn't generate a command for this task.")

def normalize_filename(name):
    """Normalize and ensure a safe filename."""
    name = name.strip().strip('"').strip("'")
    name = re.sub(r"[^\w.\-]+", "_", name)
    return name or "generated_script.py"

def ensure_unique_filename(name):
    """Avoid overwriting existing files by generating a unique name."""
    path = Path(name)
    if not path.exists():
        return str(path)
    stem = path.stem
    suffix = path.suffix or ".py"
    for i in range(1, 1000):
        candidate = f"{stem}_{i}{suffix}"
        if not Path(candidate).exists():
            return candidate
    return f"{stem}_{int(time.time())}{suffix}"

def auto_code_task(task):
    """Automatically generate code for a task and save to a file."""
    print(f"Generating code for: {task}")
    file_suggestion = call_ai_api(
        f"Suggest a short, valid filename for this task. Return only the filename.\nTask: {task}"
    )
    filename = normalize_filename(file_suggestion or "generated_script.py")
    filename = ensure_unique_filename(filename)

    code = call_ai_api(
        f"Write complete, runnable code in a single file for this task. "
        f"Return only code, no explanations.\nTask: {task}\nFilename: {filename}"
    )

    if not code:
        print("Sorry, couldn't generate code for this task.")
        return

    with open(filename, "w") as f:
        f.write(code)
    print(f"✅ Code saved to {filename}")

def is_auto_code_request(user_input):
    """Detect natural language requests to auto-generate code."""
    text = user_input.strip().lower()
    if text.startswith("ai:") or text.startswith("code:"):
        return True
    starters = ("create ", "build ", "write ", "make ")
    if text.startswith(starters) and (" python" in text or "in python" in text or "python script" in text):
        return True
    return False

class SuggestionThread(threading.Thread):
    """Background thread for AI suggestions"""
    def __init__(self, task, result_queue):
        super().__init__(daemon=True)
        self.task = task
        self.result_queue = result_queue
        
    def run(self):
        try:
            suggestion = call_ai_api(f"Suggest a one-line terminal command to: {self.task}")
            self.result_queue.put(('success', suggestion))
        except Exception as e:
            self.result_queue.put(('error', str(e)))

def execute_command(cmd):
    """Execute command with proper handling of shell builtins and expansions"""
    cmd = cmd.strip()
    
    # List of commands that must run in parent process
    parent_process_commands = ['cd', 'pushd', 'popd', 'export', 'set', 'unset', 'alias', 'unalias', 'source', '.']
    
    # Check if command starts with any parent process command
    cmd_parts = cmd.split()
    if not cmd_parts:
        return
    
    base_cmd = cmd_parts[0]
    
    # Handle cd command
    if base_cmd == 'cd':
        path = cmd[2:].strip() if len(cmd) > 2 else ''
        if not path:  # cd with no arguments goes to home
            path = os.path.expanduser("~")
        else:
            path = os.path.expanduser(path)  # Handle ~ expansion
        
        try:
            os.chdir(path)
            print(f"Changed directory to: {os.getcwd()}")
        except FileNotFoundError:
            print(f"cd: {path}: No such file or directory")
        except PermissionError:
            print(f"cd: {path}: Permission denied")
        except Exception as e:
            print(f"cd: {e}")
        return
    
    # Handle pwd
    if base_cmd == 'pwd':
        print(os.getcwd())
        return
    
    # Handle export (set environment variables in parent process)
    if base_cmd == 'export':
        export_match = re.match(r'export\s+([A-Za-z_][A-Za-z0-9_]*)=(.+)', cmd)
        if export_match:
            var_name, var_value = export_match.groups()
            # Remove quotes if present
            var_value = var_value.strip().strip('"').strip("'")
            os.environ[var_name] = var_value
            print(f"Exported {var_name}={var_value}")
        else:
            # Just display environment variables
            subprocess.run(['bash', '-c', cmd], check=False)
        return
    
    # Handle unset
    if base_cmd == 'unset':
        if len(cmd_parts) > 1:
            var_name = cmd_parts[1]
            if var_name in os.environ:
                del os.environ[var_name]
                print(f"Unset {var_name}")
            else:
                print(f"unset: {var_name}: not set")
        return
    
    # Handle alias (store in a global dict for this session)
    if base_cmd == 'alias':
        if '=' in cmd:
            # Store alias (note: this won't persist, just for demo)
            print(f"Note: alias is set for this Python session only")
            subprocess.run(['bash', '-c', cmd], check=False)
        else:
            subprocess.run(['bash', '-c', cmd], check=False)
        return
    
    # Handle source/. (dot command)
    if base_cmd in ['source', '.']:
        print(f"Warning: '{base_cmd}' command affects only subprocess environment")
        print(f"Environment changes won't persist in parent shell")
        result = subprocess.run(['bash', '-c', cmd], check=False)
        return
    
    # For all other commands, use subprocess with bash to ensure proper expansion
    try:
        # Use bash explicitly to ensure brace expansion works
        result = subprocess.run(['bash', '-c', cmd], check=False)
        if result.returncode != 0:
            print(f"Command exited with code {result.returncode}")
    except Exception as e:
        print(f"Error executing command: {e}")

def agentic_edit_flow(target_path):
    """Edit a file based on a user-provided snippet and instructions."""
    if not os.path.exists(target_path):
        print(f"❌ File not found: {target_path}")
        return
    print("Paste the code snippet to change. End with a single line: END")
    snippet_lines = []
    while True:
        try:
            line = input()
        except (EOFError, KeyboardInterrupt):
            print("\nReturning to main prompt...")
            return
        if line.strip() == "END":
            break
        snippet_lines.append(line)
    snippet = "\n".join(snippet_lines).strip()
    if not snippet:
        print("❌ No snippet provided.")
        return
    instructions = prompt_user_text("Describe the changes you want: ")
    if instructions is None or not instructions.strip():
        print("❌ No instructions provided.")
        return
    with open(target_path, "r") as f:
        original = f.read()
    response = call_ai_api(
        "You are editing a file. Apply the requested changes to the provided snippet in context. "
        "Return ONLY the full updated file content, no markdown, no explanations.\n\n"
        f"File path: {target_path}\n"
        f"Instructions: {instructions}\n\n"
        f"Snippet to change:\n{snippet}\n\n"
        f"Current file content:\n{original}"
    )
    updated = response.strip() if response else ""
    if not updated:
        print("⚠️  No updated content returned.")
        return
    with open(target_path, "w") as f:
        f.write(updated)
    print(f"✅ Updated {target_path}")
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
            text = parts[1].strip()
    text = text.splitlines()[0].strip()
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
    if "```" in text:
        parts = text.split("```")
        if len(parts) >= 2:
            text = parts[1].strip()
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
    if "```" in text:
        parts = text.split("```")
        if len(parts) >= 2:
            text = parts[1].strip()
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
    return steps

def main():
    style = Style.from_dict({
        'prompt': '#00aa00 bold',
        'auto-suggestion': '#666666',  # Changed from 'suggestion' to 'auto-suggestion'
    })
    
    def get_prompt():
        cwd = os.getcwd()
        home = os.path.expanduser("~")
        if cwd.startswith(home):
            cwd = "~" + cwd[len(home):]
        return HTML(f'<prompt>{cwd} $ </prompt>')

    session = PromptSession(
        get_prompt,
        auto_suggest=AIAutoSuggest(),
        completer=FileCompleter(),
        style=style,
        complete_while_typing=True,
        complete_in_thread=True
    )
    
    bindings = KeyBindings()

    @bindings.add("tab")
    def _(event):
        buff = event.app.current_buffer
        if buff.suggestion:
            # If there's an AI suggestion, accept it
            buff.insert_text(buff.suggestion.text)
        else:
            # Otherwise, trigger file completion
            buff.start_completion()

    @bindings.add("right")
    def _(event):
        buff = event.app.current_buffer
        if buff.suggestion:
            buff.insert_text(buff.suggestion.text)

    @bindings.add("c-c")
    def _(event):
        # Gracefully interrupt without bubbling an exception through the event loop
        event.app.exit(result="INTERRUPT")

    @bindings.add("c-c", "c-c")  # Ctrl+C twice quickly
    def _(event):
        # Double Ctrl+C to exit special modes
        event.app.exit(result="DOUBLE_CTRL_C_EXIT")

    @bindings.add("escape")
    def _(event):
        # Escape to exit special modes
        event.app.exit(result="ESCAPE_EXIT")

    session.key_bindings = bindings

    last_fetch_time = 0
    
    def on_text_changed(_):
        nonlocal last_fetch_time
        current_time = time.time()
        
        if current_time - last_fetch_time < 0.15:  # Faster response while still debounced
            return
        
        last_fetch_time = current_time
        buffer_text = session.default_buffer.document.text
        
        if buffer_text.startswith("?") or len(buffer_text.strip()) < 2:
            return
        
        threading.Thread(
            target=fetch_suggestion_async,
            args=(buffer_text, session),
            daemon=True
        ).start()

    session.default_buffer.on_text_changed += on_text_changed

    print("=== AI Shell ===")
    print("AI-enhanced shell with caching enabled for faster suggestions")
    print("Press TAB for file completion or to accept AI suggestions, RIGHT ARROW to accept suggestions")
    print()
    print("Features:")
    print("- %  : ask for a single command suggestion and optionally run it")
    print("- %% : execute a multi-step task")
    print("- %%%: interactive coding mode")
    print("- status: show AI connection status")
    print()
    
    # Test API connection on startup
    test_api_connection()
    print()
    print(f"📝 Logs are saved to: {LOG_FILE}")
    print("💡 Type 'status' to check AI connection status")
    print()
    
    while True:
        try:
            user_input = session.prompt()
            
            with suggestion_lock:
                current_suggestion = ""

            if user_input in (None, "INTERRUPT"):
                print("\nUse 'exit' or 'quit' to exit")
                continue
            
            # Handle exit commands properly
            if user_input == "ESCAPE_EXIT":
                print("\nReturning to main prompt...")
                continue  # Go back to main loop
            if user_input == "DOUBLE_CTRL_C_EXIT":
                print("\nReturning to main prompt...")
                continue  # Go back to main loop
            if user_input.lower() in ("exit", "quit"):
                break
            
            elif user_input.lower() == "status":
                # Show API connection status
                print("\n=== AI Connection Status ===")
                if api_connection_status["connected"]:
                    print("✅ Status: Connected")
                    print(f"🕐 Last check: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(api_connection_status['last_check']))}")
                else:
                    print("❌ Status: Disconnected")
                    if api_connection_status["error_message"]:
                        print(f"⚠️  Error: {api_connection_status['error_message']}")
                    if api_connection_status["last_check"]:
                        print(f"🕐 Last check: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(api_connection_status['last_check']))}")
                
                print(f"📝 Log file: {LOG_FILE}")
                print(f"🔧 API endpoint: {API_ENDPOINT}")
                if API_KEY:
                    print(f"🔑 API key: {API_KEY[:6]}...{API_KEY[-4:]}")
                else:
                    print("🔑 API key: (not set)")
                print(f"🧠 Model: {MODEL}")
                
                # Offer to retest
                retest = input("\nTest connection now? [y/N]: ")
                if retest.lower() == 'y':
                    test_api_connection()
                print()
                continue
            
            elif user_input == "%":
                # Check if AI is connected
                if not api_connection_status["connected"]:
                    print("⚠️  Warning: AI is not connected. Type 'status' to check connection.")
                    print("Attempting to proceed anyway...")
                
                try:
                    task = prompt_user_text("What command do you need? ")
                    if task is None:
                        print("\nReturning to main prompt...")
                        continue
                    task = task.strip()
                    
                    # Allow exit from % mode
                    if task.lower() in ("exit", "quit", ""):
                        continue
                    
                    log_message(f"User requested command for: {task}", "INFO")
                    
                    # Better prompt for more specific commands
                    suggestion = call_ai_api(f"Generate a specific shell command to: {task}. For creating directories, use meaningful names like 'my_folder' or 'new_directory'. Respond with only the command.")
                    
                    if suggestion:
                        # Normalize accidental code fencing/backticks from the model
                        suggestion = suggestion.strip().strip("`")
                        try:
                            command_to_run = prompt_command_edit(suggestion)
                            if command_to_run is None:
                                print("\nReturning to main prompt...")
                            elif command_to_run == "":
                                print("Command not executed.")
                            else:
                                if check_command_safety(command_to_run):
                                    execute_command(command_to_run)
                        except (EOFError, KeyboardInterrupt):
                            print("\nReturning to main prompt...")
                    else:
                        print("Sorry, couldn't generate a suggestion.")
                except (EOFError, KeyboardInterrupt):
                    print("\nReturning to main prompt...")
            
            elif user_input == "%%":
                # Check if AI is connected
                if not api_connection_status["connected"]:
                    print("⚠️  Warning: AI is not connected. Type 'status' to check connection.")
                    print("Attempting to proceed anyway...")
                
                request = user_input[2:].strip()
                if not request:
                    try:
                        request = prompt_user_text("What task would you like to execute? ")
                        if request is None:
                            print("\nReturning to main prompt...")
                            continue
                        request = request.strip()
                        if request.lower() == "back":
                            print("\nReturning to main prompt...")
                            continue
                        if request.lower() not in ("exit", "quit", ""):
                            log_message(f"User requested task: {request}", "INFO")
                            execute_task(request)
                    except (EOFError, KeyboardInterrupt):
                        print("\nReturning to main prompt...")
                else:
                    execute_task(request)
            
            elif user_input == "%%%" or user_input.startswith("%%%"):
                # Check if AI is connected
                if not api_connection_status["connected"]:
                    print("⚠️  Warning: AI is not connected. Type 'status' to check connection.")
                    print("Attempting to proceed anyway...")
                
                try:
                    task = user_input[3:].strip() if user_input != "%%%" else ""
                    if not task:
                        task = prompt_user_text("What would you like to code? ")
                    if task is None:
                        print("\nReturning to main prompt...")
                        continue
                    task = task.strip()
                    if task.lower() not in ("exit", "quit", ""):
                        log_message(f"User requested coding: {task}", "INFO")
                        interactive_coding(task)
                except (EOFError, KeyboardInterrupt):
                    print("\nReturning to main prompt...")
            
            else:
                if is_auto_code_request(user_input):
                    auto_code_task(user_input)
                elif user_input.startswith("edit "):
                    target = user_input[5:].strip()
                    if not target:
                        print("Usage: edit <path>")
                    else:
                        agentic_edit_flow(target)
                elif check_command_safety(user_input):
                    execute_command(user_input)
            
        except KeyboardInterrupt:
            print("\nUse 'exit' or 'quit' to exit")
            continue
        except Exception as e:
            print(f"\nError: {e}")

    # Optional: allow a parent shell wrapper to update its cwd after exit
    cwd_file = os.getenv("CLIFFY_CWD_FILE", "").strip()
    if cwd_file:
        try:
            with open(cwd_file, "w") as f:
                f.write(os.getcwd())
        except Exception as e:
            log_message(f"Failed to write CLIFFY_CWD_FILE: {e}", "ERROR")

if __name__ == "__main__":
    main()
