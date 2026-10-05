# 📝 Cliffy Quick Reference Card

## 🚀 Quick Start
```bash
# Start Cliffy
python3 ai_shell_integration.py

# Exit
exit   # or type 'quit'
```

---

## 🎯 Command Modes

| Mode | Trigger | Description | Example |
|------|---------|-------------|---------|
| **Normal** | (default) | Standard shell commands | `ls -la`, `cd /tmp` |
| **AI Suggest** | `%` | Get AI command suggestion | `%` → "find large files" |
| **Execute Task** | `%%` | Direct AI task execution | `%%` → "create 10 files" |
| **Code Mode** | `%%%` | Interactive coding | `%%%` → "python calculator" |

---

## ⌨️ Keyboard Shortcuts

| Key | Action |
|-----|--------|
| `TAB` | Accept AI suggestion / File completion |
| `→` (Right Arrow) | Accept AI suggestion |
| `Ctrl+C` | Cancel input |
| `Ctrl+C` × 2 | Exit special mode |
| `ESC` | Exit special mode |

---

## 🔧 Special Commands (Work in Parent Process)

```bash
cd /path/to/dir      # Change directory ✓
pwd                  # Print working directory ✓
export VAR=value     # Set environment variable ✓
unset VAR            # Remove environment variable ✓
```

---

## 🛡️ Safety Features

### Dangerous Commands (Require Confirmation)
- `rm -rf` - File deletion
- `dd` - Disk operations
- `mkfs`/`format` - Formatting
- `git reset --hard` - Git history
- `chmod -R` - Recursive permissions
- `systemctl stop` - Service control

---

## 💡 Quick Examples

### Get Command Suggestion
```bash
$ %
What command do you need? list all python files recursively
Suggested: find . -name "*.py"
Execute? [y/N] y
```

### Auto-Complete
```bash
$ git com█              # AI suggests: git commit -m "message"
$ docker ps█            # AI suggests: docker ps -a
```

### Execute Task Directly
```bash
$ %%
What task? create folder structure for web project
Generated: mkdir -p project/{src,public,tests}
```

### Interactive Coding
```bash
$ %%%
What to code? python web scraper
[Step-by-step code generation with edits]
```

---

## 🔍 Useful Patterns

### File Operations
```bash
%  # find files modified in last 24 hours
%  # compress this folder into tar.gz
%  # count lines of code in all python files
```

### Git Operations
```bash
%  # show files changed in last commit
%  # undo last commit keeping changes
%  # list all branches sorted by date
```

### System Info
```bash
%  # show disk usage by directory
%  # find processes using most memory
%  # check open ports on system
```

---

## 🐛 Troubleshooting

| Issue | Solution |
|-------|----------|
| API not working | Check `.env` file has `deepseek_api=YOUR_KEY` |
| Slow suggestions | Normal - first call caches for speed |
| `cd` not working | Fixed in v1.1 - should work now! |
| No suggestions | Type at least 3 characters |

---

## 📦 Installation (Quick)

```bash
# Install dependencies
pip install requests prompt_toolkit python-dotenv

# Create API key file
echo "deepseek_api=YOUR_API_KEY" > .env

# Run
python3 ai_shell_integration.py
```

---

## 🎓 Tips

1. **Cache is Your Friend** - Repeated commands are instant
2. **Be Specific** - "create 5 test files" better than "make files"
3. **Review Before Execute** - Always check AI-generated commands
4. **Use Natural Language** - Don't know syntax? Just ask!
5. **Safety First** - Confirmations are there to protect you

---

## 📊 Performance

- **First suggestion**: ~1-2 seconds (API call)
- **Cached suggestion**: Instant
- **Rate limit**: 0.5s between API calls
- **Cache size**: Last 100 unique commands
- **Context memory**: Last 10 commands

---

## 🔗 Quick Links

- Full README: `README.md`
- Bug Fixes: `FIXES_APPLIED.md`
- Test Suite: `python3 test_fixes.py`

---

**Print this card and keep it handy! 📌**
