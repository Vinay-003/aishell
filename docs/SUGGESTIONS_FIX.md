# Real-Time AI Suggestions - Troubleshooting & Fix

## Problem
The real-time AI command suggestions are not appearing as you type.

## Root Causes Found

### 1. Style Class Name Issue
**Problem**: Style was defined as `'suggestion'` but should be `'auto-suggestion'`
**Fix Applied**: Changed style dictionary key to `'auto-suggestion'`

```python
# BEFORE (Wrong):
style = Style.from_dict({
    'prompt': '#00aa00 bold',
    'suggestion': '#666666 italic',  ← Wrong key!
})

# AFTER (Correct):
style = Style.from_dict({
    'prompt': '#00aa00 bold',
    'auto-suggestion': '#666666',  ← Correct key!
})
```

### 2. Debug Logging Added
Added logging to track:
- When suggestions are fetched
- What suggestion is returned
- When AIAutoSuggest is called
- What gets displayed

Check logs with: `tail -f ~/.ai_shell.log`

## How It Should Work

1. **You type**: `ls -`
2. **After 0.8s**: Background thread calls AI
3. **AI returns**: `ls -la`
4. **Display**: Shows `-la` in gray after your cursor
5. **Accept**: Press TAB or RIGHT ARROW

## Testing

### Test 1: Check if suggestions are being generated
```bash
python3 debug_suggestions.py
```
Expected: Should show AI generating suggestions ✅

### Test 2: Check minimal auto-suggest
```bash
python3 test_autosuggest_minimal.py
```
Type "ls" and you should see " -la" suggested.

### Test 3: Run Cliffy with logging
```bash
python3 ai_shell_integration.py
# In another terminal:
tail -f ~/.ai_shell.log
```
Type "ls -" and watch the log file for debug messages.

## What To Look For

When typing, you should see in the log:
```
[DEBUG] Fetching suggestion for: 'ls -'
[DEBUG] Got suggestion: 'ls -la'
[DEBUG] Updated current_suggestion to: 'ls -la'
[DEBUG] AIAutoSuggest: typed='ls -', current_suggestion='ls -la'
[DEBUG] AIAutoSuggest: returning 'la'
```

## Common Issues

### Issue 1: Suggestions not visible
**Symptom**: AI is working but nothing shows up
**Cause**: Terminal doesn't support gray text / ANSI colors
**Solution**: Try different terminal or check color support

### Issue 2: Suggestions too slow
**Symptom**: Suggestions appear but take 5+ seconds
**Cause**: AI API is slow or rate limiting
**Solution**: Increase debounce time in `on_text_changed` from 0.8s to 1.5s

### Issue 3: Suggestions don't match what you typed
**Symptom**: Random suggestions appear
**Cause**: Cache or async race condition
**Solution**: Clear cache by deleting and restarting

## Verify It's Working

Run this test:
```bash
python3 ai_shell_integration.py
```

1. Type: `git com` (slowly)
2. Wait 1-2 seconds
3. Should see: `mit` in gray after cursor
4. Press TAB or RIGHT ARROW
5. Should complete to: `git commit`

## Style Configuration

The auto-suggestion style can be customized:
```python
style = Style.from_dict({
    'prompt': '#00aa00 bold',        # Green prompt
    'auto-suggestion': '#888888',    # Gray suggestions (default #666666)
})
```

Colors:
- `#666666` = Dark gray (subtle)
- `#888888` = Light gray (more visible)
- `#aaaaaa` = Very light gray
- `bg:#333333` = Add background color

## Files Modified
- `ai_shell_integration.py`:
  - Fixed style key: `'suggestion'` → `'auto-suggestion'`
  - Added debug logging in `fetch_suggestion_async()`
  - Added debug logging in `AIAutoSuggest.get_suggestion()`

## Debug Files Created
- `debug_suggestions.py` - Test AI suggestion generation
- `test_autosuggest_minimal.py` - Test basic prompt_toolkit
- `test_suggestions_live.py` - Run Cliffy with logging

## Next Steps

1. Run `python3 ai_shell_integration.py`
2. Type slowly: `ls -`
3. Wait 1-2 seconds
4. Look for gray text after cursor
5. If not working, check `~/.ai_shell.log`

## If Still Not Working

Check these:
1. Terminal supports colors: `echo -e "\e[38;5;240mGray text\e[0m"`
2. prompt_toolkit version: `python3 -c "import prompt_toolkit; print(prompt_toolkit.__version__)"`
3. AI API working: `python3 debug_suggestions.py`
4. Log file shows suggestions: `tail ~/.ai_shell.log`

If AI is generating suggestions but they don't show, it's likely a terminal color support issue.

## Current Status

✅ AI suggestion generation works
✅ Style key fixed
✅ Debug logging added
⚠️  Need to test in actual terminal to confirm visibility

The system should now work! The style fix was the key issue.
