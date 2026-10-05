# 🎨 Cliffy Architecture & Workflow

## 🏗️ System Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        User Interface                        │
│                    (prompt_toolkit)                          │
│  • Command Input                                             │
│  • AI Suggestions (gray text)                                │
│  • File Completion                                           │
│  • Keyboard Shortcuts                                        │
└─────────────────┬───────────────────────────────────────────┘
                  │
┌─────────────────▼───────────────────────────────────────────┐
│                   Command Router                             │
│                                                              │
│  Regular Command ──► Normal Execution                       │
│  %  Mode        ──► AI Suggestion                           │
│  %% Mode        ──► Task Execution                          │
│  %%% Mode       ──► Interactive Coding                      │
└─────────────────┬───────────────────────────────────────────┘
                  │
      ┌───────────┴───────────┐
      │                       │
┌─────▼──────┐      ┌────────▼─────────┐
│   Safety   │      │   Command        │
│   Checker  │      │   Handler        │
│            │      │                  │
│ • Pattern  │      │ Parent Process:  │
│   Match    │      │ • cd, pwd        │
│ • AI       │      │ • export, unset  │
│   Analysis │      │                  │
│ • User     │      │ Subprocess:      │
│   Confirm  │      │ • All others     │
└─────┬──────┘      └────────┬─────────┘
      │                      │
      └──────────┬───────────┘
                 │
┌────────────────▼──────────────────────┐
│         Execution Layer               │
│                                       │
│  os.chdir()      ─► cd command        │
│  os.environ      ─► export/unset      │
│  subprocess.run  ─► other commands    │
└───────────────────────────────────────┘
```

---

## 🔄 Command Flow Diagrams

### Normal Command Flow
```
User types: ls -la
     │
     ▼
[AI Auto-suggest] ─► ls -la [cached/new suggestion]
     │
     ▼
[Safety Check] ─► Safe? Yes
     │
     ▼
[Execute via subprocess.run(['bash', '-c', 'ls -la'])]
     │
     ▼
Output to terminal
```

### Parent Process Command (cd)
```
User types: cd /tmp
     │
     ▼
[Command Router] ─► Detects 'cd'
     │
     ▼
[execute_command()] ─► base_cmd == 'cd'?
     │
     ▼
[os.chdir('/tmp')] ─► Changes Python process directory
     │
     ▼
Print: "Changed directory to: /tmp"
```

### AI Suggestion Mode (%)
```
User types: %
     │
     ▼
Prompt: "What command do you need?"
     │
     ▼
User: "find large files"
     │
     ▼
[call_ai_api()] ─► OpenRouter API
     │                  │
     │                  ▼
     │            GPT-4o-mini model
     │                  │
     │                  ▼
     │            "find . -size +100M"
     │◄─────────────────┘
     │
     ▼
Display suggestion
     │
     ▼
Prompt: "Execute? [y/N]"
     │
     ├─ y ─► [Safety Check] ─► Execute
     │
     └─ n ─► Return to main prompt
```

---

## 🧠 AI Integration Pipeline

```
┌────────────────────────────────────────────────┐
│          User Input Processing                 │
└────────────────┬───────────────────────────────┘
                 │
                 ▼
┌────────────────────────────────────────────────┐
│          Cache Check                           │
│  ┌──────────────────────────────┐              │
│  │  suggestion_cache (dict)     │              │
│  │  Key: user_input             │              │
│  │  Value: cached_suggestion    │              │
│  │  Max: 100 entries            │              │
│  └──────────────────────────────┘              │
└────────────────┬───────────────────────────────┘
                 │
         Cache Hit? ├─ Yes ─► Return cached
                 │
                 No
                 │
                 ▼
┌────────────────────────────────────────────────┐
│          Rate Limiter                          │
│  • MIN_API_CALL_INTERVAL = 0.5s                │
│  • api_call_lock (threading.Lock)              │
│  • Prevents API spam                           │
└────────────────┬───────────────────────────────┘
                 │
                 ▼
┌────────────────────────────────────────────────┐
│          OpenRouter API Call                   │
│                                                │
│  POST /chat/completions                        │
│  Model: gpt-4o-mini-2024-07-18                 │
│  Temperature: 0.1                              │
│  Max Tokens: 50-150                            │
│                                                │
└────────────────┬───────────────────────────────┘
                 │
                 ▼
┌────────────────────────────────────────────────┐
│          Response Processing                   │
│  • Clean markdown formatting                   │
│  • Remove explanations                         │
│  • Validate suggestion                         │
│  • Strip quotes                                │
└────────────────┬───────────────────────────────┘
                 │
                 ▼
┌────────────────────────────────────────────────┐
│          Cache & Return                        │
│  • Store in cache                              │
│  • Update UI (session.app.invalidate())        │
│  • Display as gray suggestion                  │
└────────────────────────────────────────────────┘
```

---

## 🛡️ Safety Check Pipeline

```
Command Input
     │
     ▼
┌────────────────────────────────────────┐
│  Stage 1: Pattern Matching            │
│                                        │
│  Dangerous patterns:                  │
│  • rm -rf                             │
│  • dd                                 │
│  • mkfs / format                      │
│  • git reset --hard                   │
│  • systemctl stop                     │
│  • etc.                               │
└────────────────┬───────────────────────┘
                 │
         Match? ─┼─ Yes ─► Show warning & file count
                 │         │
                 │         ▼
                 │    Prompt confirmation
                 │         │
                 │         ├─ y ─► Continue
                 │         └─ n ─► Abort
                 │
                 No
                 │
                 ▼
┌────────────────────────────────────────┐
│  Stage 2: File Overwrite Check        │
│                                        │
│  Pattern: ">" (not ">>")              │
│  • Check if target file exists        │
│  • Show file size                     │
│  • Prompt confirmation                │
└────────────────┬───────────────────────┘
                 │
         Match? ─┼─ Yes ─► Prompt confirmation
                 │
                 No
                 │
                 ▼
┌────────────────────────────────────────┐
│  Stage 3: AI Safety Analysis          │
│                                        │
│  Risky patterns:                      │
│  • rm, del, format, mkfs, dd, etc.   │
│                                        │
│  Ask AI: "Is this command destructive?"│
│  • Display AI assessment              │
└────────────────┬───────────────────────┘
                 │
                 ▼
            Execute Command
```

---

## 📊 Data Flow: Auto-Suggest Feature

```
┌────────────────────────────────────────────────┐
│  User types in terminal                        │
│  Example: "git co"                             │
└────────────────┬───────────────────────────────┘
                 │
                 ▼
┌────────────────────────────────────────────────┐
│  on_text_changed() event triggered             │
│  • Debounce: 0.8s delay                        │
│  • Min length: 2 characters                    │
└────────────────┬───────────────────────────────┘
                 │
                 ▼
┌────────────────────────────────────────────────┐
│  Background Thread (daemon=True)               │
│  fetch_suggestion_async(text, session)         │
└────────────────┬───────────────────────────────┘
                 │
                 ▼
┌────────────────────────────────────────────────┐
│  get_ai_suggestion("git co")                   │
│  • Check cache                                 │
│  • Rate limit check                            │
│  • API call if needed                          │
└────────────────┬───────────────────────────────┘
                 │
                 ▼
┌────────────────────────────────────────────────┐
│  Update global state (thread-safe)             │
│  with suggestion_lock:                         │
│      current_suggestion = "git commit -m"      │
└────────────────┬───────────────────────────────┘
                 │
                 ▼
┌────────────────────────────────────────────────┐
│  Invalidate UI (session.app.invalidate())      │
│  Triggers AIAutoSuggest.get_suggestion()       │
└────────────────┬───────────────────────────────┘
                 │
                 ▼
┌────────────────────────────────────────────────┐
│  Display suggestion in gray                    │
│  "git co|mmit -m"                              │
│         ^^^^^^^ (gray suggestion text)         │
└────────────────────────────────────────────────┘
```

---

## 🔄 Caching Strategy

```
┌─────────────────────────────────────────┐
│   Suggestion Cache (LRU-like)           │
│                                         │
│   Type: Dictionary                      │
│   Max Size: 100 entries                 │
│   Eviction: FIFO (oldest 20)            │
│                                         │
│   Structure:                            │
│   {                                     │
│     "git st": "git status",             │
│     "docker p": "docker ps -a",         │
│     "npm i": "npm install",             │
│     ...                                 │
│   }                                     │
│                                         │
│   Thread Safety: cache_lock             │
└─────────────────────────────────────────┘

Cache Hit Rate Optimization:
1. Exact match lookup (O(1))
2. No API call needed
3. Instant return
4. Better UX

Cache Miss Handling:
1. Make API call
2. Store in cache
3. Return result
4. Future hits will be instant
```

---

## 🎯 Key Components

### 1. AIAutoSuggest
- Custom `AutoSuggest` class
- Reads from `current_suggestion` global
- Returns `Suggestion` object
- Displays gray text in prompt

### 2. FileCompleter
- Custom `Completer` class
- Provides file/directory completion
- Works alongside AI suggestions
- Triggered by TAB key

### 3. Command Router
- Main event loop
- Routes to different modes
- Handles special commands
- Error handling & recovery

### 4. Safety Checker
- Multi-stage verification
- Pattern matching
- AI-powered analysis
- User confirmation prompts

### 5. Execution Layer
- Parent process commands (Python)
- Subprocess commands (bash -c)
- Environment management
- Error handling

---

## 🚀 Performance Characteristics

| Operation | First Time | Cached | Notes |
|-----------|-----------|---------|-------|
| Command suggestion | ~1-2s | <10ms | API vs cache |
| Safety check (pattern) | <1ms | N/A | Regex match |
| Safety check (AI) | ~1-2s | N/A | Only for risky |
| File completion | <10ms | N/A | Local filesystem |
| Command execution | Variable | N/A | Depends on command |

---

## 🔧 Threading Model

```
Main Thread
    │
    ├─► UI Event Loop (prompt_toolkit)
    │       │
    │       ├─► on_text_changed events
    │       └─► Keyboard handlers
    │
    └─► Background Threads (daemon)
            │
            ├─► fetch_suggestion_async()
            │       └─► API calls
            │
            └─► SuggestionThread()
                    └─► Command suggestions
```

All background threads are marked as `daemon=True` so they don't prevent program exit.

---

This architecture provides:
- ✅ Fast, responsive UI
- ✅ Thread-safe operations
- ✅ Intelligent caching
- ✅ Robust safety checks
- ✅ Seamless AI integration
