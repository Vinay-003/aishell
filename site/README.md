# Cliffy product site

Static, dependency-free-at-runtime landing page and setup manual. The site lives
on `feat/cliffy-landing-page`; the CLI implementation is on `master`.

## Preview

From the repository root:

```bash
python3 -m http.server 4173 --bind 127.0.0.1 --directory site
```

Open http://localhost:4173. `index.html` is the landing page; `docs.html` covers
installation, all provider variables, native Bash, alternate assistant modes,
privacy, troubleshooting, and removal. All users supply their own provider,
model, and API key. The website neither collects keys nor makes inference calls.

## Test

The Node dependencies are **development tools only**, not runtime dependencies.

```bash
cd site
npm ci
npx playwright install chromium
npm test
npm audit --audit-level=high
```

The test runner starts/reuses a local Python static server. It uses installed
Google Chrome on Linux if available, otherwise Playwright's Chromium. Set
`CLIFFY_BROWSER_EXECUTABLE` to choose another local Chromium binary.
Screenshots are written to `/tmp/opencode/cliffy-site/` for both pages at
390, 768, 1440, and 2560×1600. Keyboard, clipboard, download, reduced-motion,
JavaScript-disabled, overflow, and external-request checks are included.

With the preview running, `npm run audit` audits the landing page. To audit docs:

```bash
npx lighthouse http://127.0.0.1:4173/docs.html \
  --chrome-flags='--headless --no-sandbox' --output=json \
  --output-path=/tmp/opencode/cliffy-docs-lighthouse.json --quiet
```

Python source checks also validate page links, provider documentation, CSP,
download hashes, and a single-digit-KB JavaScript budget:
`env/bin/python -m pytest tests/test_site.py -q` from the repository root.

## Downloads and hosting

`downloads/` contains the tested 0.1.0 CLI wheel and source distribution, plus
`SHA256SUMS`. These are intentionally included public deliverables, not secrets
or private configurations. They were built from the native CLI implementation;
website files and Node tooling are not required to install Cliffy.

Publish the **contents of `site/`** to a static HTTPS host. No build step,
environment variables, provider key, or backend is required. Relative links
work when the site is hosted under a path such as GitHub Pages. Do not upload
`node_modules/`, `checks/`, `test-results/`, or development reports. Public
hosting is not configured by this change; a repository push is not a deployment.
Use HTTPS for clipboard support outside localhost. CSP is embedded in both
HTML pages and permits only local resources/static discovery, not remote APIs.

When replacing downloads, build/review the CLI packages, copy only the wheel
and source distribution into `downloads/`, and regenerate hashes from that
folder: `sha256sum *.whl *.tar.gz > SHA256SUMS`. Run both test suites afterward.

## Design references

Concept: **the shell field manual**. Paper, charcoal, phosphor green; editorial
serif display typography and a layered terminal figure. Both gsap.com and
21st.dev were scraped on 2026-10-06. GSAP informed the charcoal/cream contrast
and strong type hierarchy; 21st.dev informed clear component rhythm. These are
inspirations, not copied components. GSAP/Three.js libraries are not used.
Entry motion uses IntersectionObserver and opacity/translation only; native
terminal examples are illustrations, not a live shell or AI widget.

See `VERIFICATION.md` for actual checks and remaining limits.
