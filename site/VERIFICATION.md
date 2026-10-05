# Verification — 2026-10-06

## CLI

- `master` commit `90db801` was pushed to GitHub via existing SSH authentication
  and independently verified against `origin/master`.
- Native Bash uses an opt-in child session with reviewed Ctrl+G command
  insertion. No global shell profiles, provider keys, or account settings changed.
- CLI-only source run: **231 tests + 33 subtests**, **86.33% runtime coverage**.
- Source run including the website: **238 tests + 33 subtests**, same coverage.
- Clean installed wheel outside the checkout: **35 selected tests + 33 subtests**
  passed, including real PTY state/job-control and localhost draft insertion.
- Bash syntax, Python compilation, dependency consistency, wheel/sdist builds,
  Twine metadata, archive resources/license, and known-key-pattern/private-file
  exclusion checks passed. No PyPI upload or new live-model inference occurred.

## Website

- `npm test`: **13 browser checks passed** in Chromium/Google Chrome.
- Both pages captured at 390×844, 768×1024, 1440×1000, and 2560×1600.
- No document overflow at those sizes; no page errors during tested flows.
- Keyboard skip/menu/demo flow, clipboard multiline fidelity, real package
  downloads, no-JavaScript mobile content/navigation, and reduced motion passed.
- Demonstration interactions made no external network requests. There are no
  API-key inputs or forms, analytics, CDN dependencies, or inference callbacks.
- `main.js`: **3,223 bytes**. Content remains visible without JavaScript.
- `npm audit --audit-level=high`: **0 vulnerabilities** at verification time.
- SHA256 integrity and local page/asset/anchor contracts pass in the Python suite.

### Final local Lighthouse mobile runs

| Page | Performance | Accessibility | Best practices | SEO | Agentic browsing | LCP | CLS |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Landing | 100 | 100 | 100 | 100 | 100 | 0.9 s | 0 |
| Field manual | 100 | 100 | 100 | 100 | 100 | 1.1 s | 0 |

These are simulated local mobile audits, not real-user production measurements.
Automated accessibility scores do not replace assistive-technology testing.
The intermediate CSP blocked static discovery; the final policy allows same-origin
static requests while prohibiting external API connections. Final audits above
were rerun after the correction.

## Limits

- Remote CI is configured but not claimed as passed here.
- Website hosting is not deployed by this change; the preview is local.
- Native integration is Bash 4+ only. Zsh, native ghost text, native Windows,
  macOS runtime, Vim/SSH-specific behavior, and cross-platform terminal resize
  behavior were not verified in this run.
- Shells share filesystem permissions; this is not a sandbox. Native drafts use
  exported configuration and separate helper processes, without cross-session
  rate-spacing persistence. Users choose and pay for their provider/model.
- Official provider credentials were not used for these new tests; transport
  fixtures and localhost inference supplied repeatable coverage.
