# Cliffy — AI-assisted interactive shell

Cliffy adds explicit AI command drafting to an opt-in **native Bash session**,
alongside a Python interactive assistant with optional AI suggestions,
natural-language command drafting, guided multi-step commands, and code
generation. The native mode preserves Bash state; the Python assistant is
**not** a full POSIX login shell. Neither mode is a sandbox. Review commands
and generated files before accepting them.

## Install (Python 3.10+)

Python packages are **not published to PyPI**. Download the
[source ZIP](https://github.com/Vinay-003/aishell/archive/refs/heads/master.zip)
or clone the repository, then install from the extracted project directory:

```bash
python3 -m pip install --user pipx
pipx install .
cliffy --help
```

Or use a virtual environment:

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install .
cliffy --version
```

To install a wheel built locally, run `python -m build` then
`pipx install dist/cliffy_ai-0.1.0-py3-none-any.whl` (or `python -m pip
install dist/cliffy_ai-0.1.0-py3-none-any.whl` in a venv). For development,
`python -m pip install -e '.[dev]'`. Existing `./cliffy` and
`source ./cliffy.sh` wrappers remain available when running from source;
the sourced wrapper can hand the final working directory back to the parent
shell. An installed `cliffy` process cannot change its parent shell's cwd.

## Provider setup

Select a provider explicitly. Supply a key through your environment; never
put keys into command-line arguments, shell history, screenshots, or committed
files. These examples prompt without echoing your secret (Bash):

```bash
export CLIFFY_PROVIDER=groq
read -rs -p 'Groq API key: ' GROQ_API_KEY; echo; export GROQ_API_KEY
cliffy --check-api  # optional: sends a small live request; may incur cost
cliffy
```

For other providers substitute the indicated name/key pair:

| `CLIFFY_PROVIDER` | Key variable | Default model (override with `CLIFFY_MODEL`) |
| --- | --- | --- |
| `groq` | `GROQ_API_KEY` | `llama-3.1-8b-instant` |
| `anthropic` | `ANTHROPIC_API_KEY` | `claude-sonnet-4-5` |
| `openai` | `OPENAI_API_KEY` | `gpt-4o-mini` |
| `gemini` | `GEMINI_API_KEY` | `gemini-2.5-flash` |
| `apinex` | `APINEX_API_KEY` | `free/glm-5.3-flash` |

For APInex: `export CLIFFY_PROVIDER=apinex`, then
`read -rs -p 'APInex API key: ' APINEX_API_KEY; echo; export APINEX_API_KEY`.
The default base URL is `https://api.apinex.bond/v1`. The `free/` prefix alone
does **not** guarantee no charge; verify current model availability and terms
with the provider before making requests.

APInex documents **5 requests/minute per IP** on the free tier and a standard
FIFO queue. Cliffy defaults to **12.1 seconds between dispatches** for APInex;
this covers suggestions, connectivity probes, code, and safety calls together.
For other providers the default is 0.1 seconds; tune it to your provider's
actual quota. Existing traffic from other apps on the same IP can still cause
429 responses. Cliffy honors `Retry-After`, makes cooldown calls fail fast, and
never automatically retries or switches to a paid model.

For casual free-tier use, avoid spending a request on startup:

```bash
cliffy --provider apinex --no-startup-check
```

The current APInex pricing UI labels `free/glm-5.3-flash` as free when
the public catalog's `provider` is `Free` and `allowFree` is true. The docs also
list dollar rates: confirm your account's entitlement. Sources:
[model API](https://apinex.bond/developers/models),
[limits](https://apinex.bond/developers/errors), and
[public catalog](https://apinex.bond/api/public/models).

Controlled APInex live tests passed the CLI connectivity probe,
fresh/cached terminal suggestions, `%`, `%%`, interactive code generation, and
unique-file auto-code using **free GLM-5.3 Flash**. This is the new APInex default;
existing Groq settings and explicit `CLIFFY_MODEL` choices are unchanged.
DeepSeek Flash authenticated and answered some requests, but intermittently
exhausted its output limit without usable content, so it is not the recommended
default. You can still select it explicitly with
`cliffy --provider apinex --model free/deepseek-v4.1-flash`.

Free GLM responses also occasionally hit limits on auxiliary filename/plan or
explanation requests; Cliffy handles these with safe fallbacks. Free-tier
APInex models can spend the output budget on hidden thinking. For free
DeepSeek/GLM routes, Cliffy requests low reasoning effort and gives short
requests 1024 tokens of headroom; code generation has a 4096-token cap and a
code-specific system prompt. Truncated code is rejected rather than saved or
retried automatically. No provider/model can guarantee a valid response.

For another OpenAI-compatible endpoint, set **all** fields:

```bash
export CLIFFY_PROVIDER=custom
export CLIFFY_BASE_URL='https://your-provider.example/v1'
export CLIFFY_MODEL='your-model-id'
read -rs -p 'Custom API key: ' CUSTOM_API_KEY; echo; export CUSTOM_API_KEY
cliffy
```

`CLIFFY_API_KEY` is an optional generic key override. You may copy
`.env.example` to a private `.env`; it is loaded only when the runtime starts,
not for `--help` or `--version`. Protect it from sharing and backups.

## Recommended: native Bash session

After exporting your own provider key and model, open a separate terminal tab:

```bash
cliffy --shell bash
```

Requires **Bash 4+** on Linux, macOS with a newer Bash installed, or WSL.
The launcher starts an independent interactive Bash, loads `~/.bashrc`, and
enables Cliffy for that child only. It does not edit profiles or switch your
normal shell. In Bash, type `show current directory` **without pressing Enter**,
then press **Ctrl+G**. Review the resulting `pwd`, edit if needed, and press Enter
to execute it. Cancel with Ctrl+C. AI output is never executed automatically.

Every ordinary command is interpreted by real Bash: `cd x && export MODE=dev`,
`source .venv/bin/activate`, aliases, functions, `umask`, and `jobs`/`fg`/`bg`
persist with native semantics. `exit` returns to your parent shell without
copying the child's directory or environment back. Files remain shared and
commands retain your user account's permissions. This is not folder isolation.

No AI request is made until you press Ctrl+G. The shortcut makes one synchronous
request; Ctrl+C cancels the helper. Empty input, invalid responses, or provider
errors retain the original line. The opt-in binding replaces Ctrl+G in Bash's
emacs and vi-insertion maps; other keys and native command syntax are unchanged.
Do not press Enter on your natural-language request if drafting fails.

For optional activation in an **existing Bash session** (affects that session):

```bash
source <(cliffy --shell-init bash)
```

For a printed draft without execution: `cliffy --draft 'show current directory'`.
Native drafting uses exported environment configuration, not project `.env`
loading. Never put an API key in a draft or command argument. The explicit task
and current directory are sent to the configured provider, not the whole shell
environment. Each native draft is a separate process: rate-spacing state is not
shared across invocations or terminal tabs, so respect your provider's quota.
There is no paid-model fallback or automatic retry.

Native-mode inline ghost text, Zsh integration, and native Windows are not
implemented. Use the existing assistant below for ghost text and coding modes.

## Existing interactive assistant

Launch `cliffy`, then enter ordinary shell commands. Prefix a natural-language
request with `%` to draft a single editable command, `%%` for a multi-step
task with per-step review/confirmation, or `%%%` for interactive coding.
Inline requests such as `% show current directory`, `%% inspect disk usage`,
and `%%% create a small Python script` are accepted; bare prefixes prompt for
a request. Generated content and shell commands can be wrong. Safety checks
and confirmation prompts are defense in depth, **not** a guarantee against
destructive operations, data disclosure, or prompt injection. Review every
proposed step and destination file path.

| Feature | How to use it |
| --- | --- |
| Inline command suggestion | Type at least two characters, pause, then accept ghost text with Tab or Right at end of line |
| File/directory completion | Tab when there is no AI suggestion; arrows navigate the completion menu |
| One AI command | `% <task>` or bare `%`; edit the draft, then explicitly confirm execution |
| Guided task | `%% <task>`; review and approve each simple step; compound shell syntax stays one reviewed unit |
| Interactive code | `%%% <task>`; review filenames, approve multi-file generation, confirm overwrites |
| One-shot code | `ai: <task>`, `code: <task>`, or “create a Python script…”; saves a unique file without executing it |
| Connection/status | `status`; see provider/model/endpoint, last result and optional retest (no key fragments) |
| Navigation/environment | Simple `cd`, `pwd`, `export`, `unset` persist inside Cliffy |
| History/exit | Up/Down for history; Ctrl+C cancels; Ctrl+D, `exit`, or `quit` leave |

Pipes, loops, brace expansion, and general commands run via Bash. A compound
`cd x && command` changes directory only in its subprocess; use separate `cd`
to persist it. `alias`, `source`, and other shell state do not persist between
subprocesses. Linux/macOS/WSL with Bash are the intended environments; native
Windows and a full login-shell replacement are not verified.

CLI options include `--help`, `--version`, `--shell bash`, `--shell-init bash`,
`--draft TASK`, `--check-api`, `--provider`,
`--model`, `--base-url`, `--timeout`, `--no-startup-check`, and `--no-ai`.
`--check-api` deliberately performs a live provider request; `--no-ai`
disables provider calls and a combined `--no-ai --check-api` returns failure
without a request. `--no-startup-check` skips only the initial connectivity
probe. `CLIFFY_NO_AI=1` opts out of AI suggestions and generation altogether.

## Privacy and tuning

Text typed for AI completion/generation may be sent to your provider. Never
type credentials or private data into AI prompts. The application may write
local `~/.ai_shell_history` and `~/.ai_shell.log`; keep these private and
inspect them before sharing diagnostics. No-AI mode avoids provider calls.
History is private (0600) but stores commands locally; do not share it. Logs
contain metadata/errors, not typed commands or model payloads. Secret-looking
input is excluded from automatic suggestions, but this is a heuristic, not a
data-loss-prevention system. Explicit AI prompts always send their supplied text.
Set `CLIFFY_DEBOUNCE` (seconds before a suggestion request),
`CLIFFY_CACHE_TTL` (seconds cached), `CLIFFY_MIN_INTERVAL` (seconds between
provider calls), and `CLIFFY_SUGGEST_TIMEOUT` (suggestion request seconds)
to tune responsiveness and usage. `CLIFFY_TIMEOUT` controls general request
timeout; `--timeout` overrides it for a CLI session. APInex defaults to 30s
including rate-spacing wait; other providers default to 10s. APInex suggestions
inherit that timeout unless `CLIFFY_SUGGEST_TIMEOUT` is explicitly set.

Suggestions use a single worker and trailing-edge debounce (default 0.20s),
with a 100-entry LRU cache expiring after 300s. Cache keys include directory,
provider, and model. Stale replies are discarded rather than overwriting a
newer edit. A fresh suggestion still depends on provider queue/network latency;
caching cannot make the first remote inference instantaneous. Use a small,
fast, non-reasoning model supported by your provider where possible.

If no suggestions appear: run `cliffy --check-api`, check model/key/endpoint,
type a non-secret partial command at end of line, and wait for the debounce plus
provider response. HTTP 401/403 means key/access trouble; 429 means cooldown;
timeouts may require `CLIFFY_SUGGEST_TIMEOUT=20`. Do not lower rate spacing below
your quota to hide latency. Ordinary commands still work with `cliffy --no-ai`.

## Verification and release

```bash
python -m pip install -e '.[dev]'
python -m pytest -q
python -m pytest --cov=ai_shell_integration --cov=cliffy_providers --cov=cliffy_suggestions --cov=cliffy_cli --cov=cliffy_native --cov-fail-under=80
python -m build
python -m twine check dist/*
```

Tests exercise provider contracts with fixtures/mocks; they do **not** establish
that official provider endpoints currently work live or are free. Before any
registry release, verify the proposed `cliffy-ai`
distribution name and owner account, review sdist/wheel contents for secrets,
and explicitly approve TestPyPI then PyPI upload. No upload or publication has
been performed. For a manually approved release only, use `python -m twine
upload --repository testpypi dist/*`, test installation from TestPyPI, then
`python -m twine upload dist/*` after review.

See `plan.md` for the audit, fixes, measured verification, and the remaining
live-provider/publication checks. The previous interview-oriented README is
preserved in `docs/INTERVIEW_GUIDE.md` as historical material; its old test and
security claims are not evidence for this release.

Licensed under the [MIT License](LICENSE). GitHub source downloads do not require
a Cliffy account; provider access, API keys, model choice, and any inference
charges remain the user's responsibility.
