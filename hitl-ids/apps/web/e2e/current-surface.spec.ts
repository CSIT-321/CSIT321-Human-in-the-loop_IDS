import { expect, test } from '@playwright/test';

test('all current role navigation and analyst responsive themes remain usable', async ({ browser }, info) => {
  test.setTimeout(180000);
  for (const [user, password, role] of [['alice','work-demo','analyst'], ['admin','admin-demo','admin'], ['observer','work-demo','evaluator']]) {
    const context = await browser.newContext();
    const page = await context.newPage();
    const errors: string[] = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.goto('/login');
    await page.getByLabel('Username').fill(user!);
    await page.getByLabel('Password', { exact: true }).fill(password!);
    await page.getByRole('button', { name: 'Sign in', exact: true }).click();
    await expect(page).not.toHaveURL(/\/login$/);
    const links = await page.getByRole('navigation', { name: 'Main', exact: true }).getByRole('link').evaluateAll(nodes => nodes.map(n => ({ href: n.getAttribute('href')!, label: n.textContent!.trim() })));
    if (role === 'analyst') expect(links.map(link => link.label)).toEqual(['Analyst Workstation','Tier 2 Cases','Triage Memory','Selective Review','Incoming Alerts']);
    for (const { href } of links) {
      await page.goto(href);
      await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
      await expect(page.getByRole('heading', { name: 'Page not found' })).toHaveCount(0);
      await expect(page.getByText('Advanced / Historical', { exact: true })).toHaveCount(0);
      // Let the current API reads settle before inspecting each page.
      await page.waitForLoadState('networkidle');
      if (role === 'analyst') for (const theme of ['light','dark']) for (const width of [1440,1024,390]) {
        await page.setViewportSize({ width, height: 900 });
        await page.evaluate(t => document.documentElement.dataset.theme = t, theme);
        await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
        expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true);
        await page.screenshot({ path: info.outputPath(`${href.split('/').at(-1)}-${theme}-${width}.png`), fullPage: true });
      }
    }
    expect(errors).toEqual([]);
    await context.close();
  }
});
