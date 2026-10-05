import { test, expect } from '@playwright/test';
import { mkdir } from 'node:fs/promises';

const evidence = '/tmp/opencode/cliffy-site';
const viewports = [
  { width: 390, height: 844 },
  { width: 768, height: 1024 },
  { width: 1440, height: 1000 },
  { width: 2560, height: 1600 },
];

for (const route of ['/', '/docs.html']) {
  for (const viewport of viewports) {
    test(`${route} fits ${viewport.width}px and captures evidence`, async ({ page }) => {
      await page.setViewportSize(viewport);
      const errors = [];
      page.on('pageerror', error => errors.push(error.message));
      await page.goto(route);
      await expect(page.locator('h1')).toBeVisible();
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
      expect(errors).toEqual([]);
      await mkdir(evidence, { recursive: true });
      const name = route === '/' ? 'landing' : 'docs';
      await page.screenshot({ path: `${evidence}/${name}-${viewport.width}.png`, fullPage: true, animations: 'disabled' });
    });
  }
}

test('keyboard navigation, menu and demo do not execute or contact providers', async ({ page }) => {
  await page.setViewportSize(viewports[0]);
  const external = [];
  page.on('request', request => {
    if (!request.url().startsWith('http://127.0.0.1:4173')) external.push(request.url());
  });
  await page.goto('/');
  await page.keyboard.press('Tab');
  await expect(page.getByRole('link', { name: 'Skip to content' })).toBeFocused();
  await page.keyboard.press('Enter');
  await expect(page.locator('main')).toBeFocused();
  const menu = page.getByRole('button', { name: /^Menu/ });
  await menu.focus();
  await page.keyboard.press('Enter');
  await expect(menu).toHaveAttribute('aria-expanded', 'true');
  await page.keyboard.press('Tab');
  await expect(page.getByRole('link', { name: 'How it works' })).toBeFocused();
  await page.keyboard.press('Escape');
  await expect(menu).toBeFocused();
  await expect(menu).toHaveAttribute('aria-expanded', 'false');
  const draft = page.getByRole('button', { name: /02 \/ DRAFT/ });
  await draft.focus();
  await page.keyboard.press('Enter');
  await expect(draft).toHaveAttribute('aria-pressed', 'true');
  await expect(page.locator('#demo-result')).toContainText('Nothing has run');
  expect(external).toEqual([]);
});

test('copy commands reports completion', async ({ browser }) => {
  const context = await browser.newContext({ permissions: ['clipboard-read', 'clipboard-write'] });
  const page = await context.newPage();
  await page.goto('/docs.html');
  const copy = page.getByRole('button', { name: 'Copy virtual environment commands' });
  await copy.click();
  await expect(copy).toHaveText('Copied');
  const text = await page.evaluate(() => navigator.clipboard.readText());
  expect(text).toContain('python3 -m venv .venv\n');
  expect(text).toContain('cliffy --version');
  await context.close();
});

test('no-JavaScript mobile content and navigation remain available', async ({ browser }) => {
  const context = await browser.newContext({ javaScriptEnabled: false, viewport: viewports[0] });
  const page = await context.newPage();
  for (const route of ['/', '/docs.html']) {
    await page.goto(route);
    await expect(page.locator('h1')).toBeVisible();
    await expect(page.locator('.site-nav')).toBeVisible();
    await expect(page.locator('[data-menu-toggle]')).toBeHidden();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  }
  await context.close();
});

test('reduced motion disables smooth scrolling', async ({ page }) => {
  await page.emulateMedia({ reducedMotion: 'reduce' });
  for (const route of ['/', '/docs.html']) {
    await page.goto(route);
    expect(await page.evaluate(() => getComputedStyle(document.documentElement).scrollBehavior)).toBe('auto');
  }
});

test('download buttons deliver the actual wheel and source archive', async ({ page, request }) => {
  await page.goto('/');
  for (const [name, filename] of [
    ['Download Python wheel', 'cliffy_ai-0.1.0-py3-none-any.whl'],
    ['Download source archive', 'cliffy_ai-0.1.0.tar.gz'],
  ]) {
    const ready = page.waitForEvent('download');
    await page.getByRole('link', { name, exact: false }).click();
    const download = await ready;
    expect(download.suggestedFilename()).toBe(filename);
    expect(await download.failure()).toBeNull();
  }
  const checksums = await request.get('/downloads/SHA256SUMS');
  expect(checksums.ok()).toBe(true);
  expect(await checksums.text()).toContain('cliffy_ai-0.1.0-py3-none-any.whl');
});
