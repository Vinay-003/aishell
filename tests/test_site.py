"""Dependency-free landing-page contract and download integrity checks."""
from html.parser import HTMLParser
from pathlib import Path
import hashlib

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / 'site'


class Page(HTMLParser):
    def __init__(self, path):
        super().__init__()
        self.links, self.ids, self.tags = [], set(), []
        self.feed(path.read_text())

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        self.tags.append((tag, attrs))
        if 'id' in attrs:
            assert attrs['id'] not in self.ids, 'Duplicate DOM id'
            self.ids.add(attrs['id'])
        if tag == 'a' and 'href' in attrs:
            self.links.append(attrs['href'])


def test_landing_is_semantic_and_links_real_downloads():
    path = SITE / 'index.html'
    assert path.exists(), 'Missing product landing page'
    page = Page(path)
    for tag in ['header', 'nav', 'main', 'footer', 'h1']:
        assert any(t == tag for t, _ in page.tags)
    assert 'docs.html' in page.links
    assert any(link.endswith('.whl') for link in page.links)
    assert any(link.endswith('.tar.gz') for link in page.links)
    assert not any(t == 'input' for t, _ in page.tags), 'Website must not collect API keys'


def test_docs_explain_bring_your_own_key_and_native_limits():
    path = SITE / 'docs.html'
    assert path.exists(), 'Missing setup documentation'
    text = path.read_text()
    for required in ['CLIFFY_PROVIDER', 'CLIFFY_MODEL', 'GROQ_API_KEY',
                     'OPENAI_API_KEY', 'ANTHROPIC_API_KEY', 'GEMINI_API_KEY',
                     'APINEX_API_KEY', 'CUSTOM_API_KEY', 'CLIFFY_BASE_URL',
                     'cliffy --shell bash', 'Ctrl+G', 'Bash 4', '--check-api']:
        assert required in text
    assert 'PyPI' in text and 'not a sandbox' in text.lower()


def test_local_links_and_assets_resolve():
    assert (SITE / 'index.html').exists()
    for path in SITE.glob('*.html'):
        page = Page(path)
        for link in page.links:
            if link.startswith(('https:', 'http:', 'mailto:')):
                continue
            file, _, fragment = link.partition('#')
            destination = path.parent / file if file else path
            assert destination.exists(), f'{path.name}: missing {link}'
            if fragment and destination.suffix == '.html':
                assert fragment in Page(destination).ids, f'Missing anchor {link}'
        for tag, attrs in page.tags:
            value = attrs.get('src') if tag == 'script' else attrs.get('href') if tag == 'link' else None
            if value and not value.startswith(('http:', 'https:', 'data:')):
                assert (path.parent / value).exists(), f'Missing asset {value}'


def test_downloads_match_published_checksums():
    folder = SITE / 'downloads'
    manifest = folder / 'SHA256SUMS'
    assert manifest.exists(), 'Missing downloadable archives and checksums'
    for line in manifest.read_text().splitlines():
        digest, name = line.split(maxsplit=1)
        assert hashlib.sha256((folder / name).read_bytes()).hexdigest() == digest


def test_no_cdn_or_large_javascript_budget():
    assert (SITE / 'index.html').exists()
    for path in SITE.glob('*.html'):
        page = Page(path)
        assert not any(tag == 'script' and attrs.get('src', '').startswith('http')
                       for tag, attrs in page.tags)
    assert sum(len(p.read_bytes()) for p in SITE.glob('*.js')) < 10000


def test_pages_do_not_accept_keys_or_allow_network_inference():
    for name in ['index.html', 'docs.html']:
        page = Page(SITE / name)
        assert not any(tag in ['input', 'textarea', 'form'] for tag, _ in page.tags)
        policies = [attrs.get('content', '') for tag, attrs in page.tags
                    if tag == 'meta' and attrs.get('http-equiv') == 'Content-Security-Policy']
        assert any("connect-src 'none'" in policy for policy in policies)
