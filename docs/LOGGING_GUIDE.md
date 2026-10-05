# 🔍 AI Connection Logging & Status Checking

## Overview

Cliffy now includes comprehensive logging and connection status checking to help you monitor and troubleshoot AI API connectivity.

## Features Added

### 1. **Automatic Connection Test on Startup** ✅
- Cliffy automatically tests the AI API connection when you start the shell
- Shows clear success/failure messages with emojis
- Logs the connection attempt for later review

### 2. **Real-time Logging** 📝
- All AI API calls are logged with timestamps
- Logs include INFO, ERROR, and DEBUG levels
- Log file location: `~/.ai_shell.log`

### 3. **Status Command** 📊
- Type `status` at any time to check AI connection status
- Shows:
  - ✅/❌ Connection status
  - 🕐 Last check timestamp
  - ⚠️ Error messages (if any)
  - 📝 Log file location
  - 🔧 API endpoint
  - 🔑 API key (masked for security)

### 4. **Smart Warnings** ⚠️
- Warnings appear when using AI features (%, %%, %%%) if not connected
- You can still attempt to use features (in case connection was restored)

## Usage Examples

### Check Connection Status
```bash
~/Desktop/cliffy $ status

=== AI Connection Status ===
✅ Status: Connected
🕐 Last check: 2025-11-11 22:20:31
📝 Log file: /home/user/.ai_shell.log
🔧 API endpoint: https://openrouter.ai/api/v1
🔑 API key: sk-or-v1-c19b12...c1b6

Test connection now? [y/N]: 
```

### View Logs
```bash
# View all logs
cat ~/.ai_shell.log

# View recent logs (last 20 lines)
tail -n 20 ~/.ai_shell.log

# View logs in real-time (while using another terminal)
tail -f ~/.ai_shell.log

# Search for errors
grep ERROR ~/.ai_shell.log

# Clear logs
rm ~/.ai_shell.log
```

### Log File Format
```
[2025-11-11 22:20:31] [INFO] Testing API connection...
[2025-11-11 22:20:31] [INFO] ✓ API connection successful
[2025-11-11 22:20:45] [DEBUG] Requesting suggestion for: git com
[2025-11-11 22:20:46] [DEBUG] Cache hit for: git com
[2025-11-11 22:21:00] [ERROR] API call failed: HTTP 401
```

## Log Levels

| Level | Description | Example |
|-------|-------------|---------|
| **INFO** | General information about operations | Connection tests, user requests |
| **ERROR** | Failed operations or API errors | Connection failures, API errors |
| **DEBUG** | Detailed debugging information | Cache hits, suggestion requests |

## Connection Status Object

The shell maintains a global connection status with:
- `connected`: Boolean - true if last connection was successful
- `last_check`: Timestamp - when connection was last tested
- `error_message`: String - error message if connection failed

## Troubleshooting

### Connection Failed on Startup
```
❌ AI API connection failed: HTTP 401
```
**Solution**: Check your API key in the configuration

### Connection Timeout
```
❌ AI API connection timeout
```
**Solution**: Check your internet connection and firewall settings

### Network Error
```
❌ Network connection error
```
**Solution**: Verify you have internet access and the API endpoint is reachable

## API Call Rate Limiting

To prevent overwhelming the API:
- Minimum 0.5 seconds between API calls
- Suggestions are cached (100 most recent)
- Debouncing delay of 0.8 seconds for auto-suggestions

## Testing Your Connection

Run the test script:
```bash
python3 test_connection.py
```

Expected output:
```
=== Testing AI Connection & Logging ===

Test 1: Logging functionality
--------------------------------------------------
✓ Log messages written to: /home/user/.ai_shell.log
✓ Log file created successfully
✓ Log file has 10 entries

Test 2: API Connection Test
--------------------------------------------------
🔄 Testing AI API connection...
✅ AI API connected successfully!

--------------------------------------------------
✅ All tests passed! AI is connected and logging works.
```

## Privacy & Security

- Logs are stored locally in your home directory
- API key is partially masked in status output (shows first 15 and last 4 chars)
- Logs can be deleted at any time: `rm ~/.ai_shell.log`
- No sensitive command content is logged (only metadata)

## Advanced Usage

### Monitor Logs in Real-time
```bash
# In terminal 1: Run Cliffy
python3 ai_shell_integration.py

# In terminal 2: Watch logs
tail -f ~/.ai_shell.log
```

### Analyze Log Statistics
```bash
# Count total API calls
grep "Requesting suggestion" ~/.ai_shell.log | wc -l

# Count cache hits
grep "Cache hit" ~/.ai_shell.log | wc -l

# Find all errors
grep ERROR ~/.ai_shell.log

# Connection success rate
echo "Successful: $(grep 'connection successful' ~/.ai_shell.log | wc -l)"
echo "Failed: $(grep 'connection failed' ~/.ai_shell.log | wc -l)"
```

## Configuration

Edit `ai_shell_integration.py` to customize:

```python
# Log file location
LOG_FILE = os.path.expanduser("~/.ai_shell.log")

# Minimum time between API calls (seconds)
MIN_API_CALL_INTERVAL = 0.5

# Cache size (number of suggestions to cache)
if len(suggestion_cache) > 100:  # Adjust this number
```

## What Gets Logged

✅ **Logged:**
- Connection test attempts and results
- API call failures with error messages
- Cache hits/misses for performance monitoring
- User requests for commands, tasks, or code

❌ **Not Logged:**
- Full command content (privacy)
- API response content (privacy)
- Your API key
- Sensitive file paths

## Integration with Your Workflow

1. **Start of Day**: Run Cliffy, check startup message confirms connection
2. **During Use**: Type `status` if suggestions stop working
3. **End of Day**: Review logs if you had any issues: `tail ~/.ai_shell.log`
4. **Weekly**: Clear old logs: `rm ~/.ai_shell.log`

## Error Codes

| Code | Meaning | Action |
|------|---------|--------|
| 200 | Success | ✅ Everything is working |
| 401 | Unauthorized | Check API key |
| 429 | Rate limited | Wait a moment, try again |
| 500 | Server error | OpenRouter issue, try later |
| Timeout | Network slow | Check internet connection |

---

**Pro Tip**: Keep a terminal window open with `tail -f ~/.ai_shell.log` to monitor Cliffy's AI interactions in real-time!
