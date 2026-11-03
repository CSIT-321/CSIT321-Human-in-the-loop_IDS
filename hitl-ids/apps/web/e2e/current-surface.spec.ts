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

test('Analyst Tour stays read-only across current pages and responsive themes', async ({ page }, info) => {
  test.setTimeout(120000);
  await page.goto('/login');
  await page.getByLabel('Username').fill('alice');
  await page.getByLabel('Password', { exact: true }).fill('work-demo');
  await page.getByRole('button', { name: 'Sign in', exact: true }).click();
  await expect(page).toHaveURL(/\/analyst\//);
  const writes: string[] = [];
  page.on('request', request => { if (request.method() !== 'GET') writes.push(`${request.method()} ${request.url()}`); });
  await page.getByRole('button', { name: 'Start tour' }).click();
  const tour = page.getByRole('region', { name: 'Analyst feature tour' });
  const titles = [
    'Your Analyst Workstation', 'Find the next alert', 'Claim shared work', 'Overview and routing',
    'Evidence', 'Context and review', 'Analyst Verdict', 'Triage Memory for this alert',
    'History and notes', 'Technical snapshots', 'Tier 2 Cases', 'Tier 2 investigation and closure',
    'Triage Memory library', 'Selective Review queue', 'Incoming Alerts', 'Ready to work',
  ];
  for (const width of [1440, 1024, 390]) for (const theme of ['dark', 'light']) {
    await page.setViewportSize({ width, height: 900 });
    await page.evaluate(value => { document.documentElement.dataset.theme = value; }, theme);
    await expect(tour.getByRole('heading', { name: titles[0] })).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1), `${width}px ${theme}`).toBe(true);
    await page.screenshot({ path: info.outputPath(`analyst-tour-${theme}-${width}.png`), fullPage: true });
  }
  await page.setViewportSize({ width: 1440, height: 900 });
  for (const [index, title] of titles.entries()) {
    await expect(tour.getByRole('heading', { name: title })).toBeVisible();
    if (index >= 3 && index <= 9) {
      const tab = ['Overview', 'Evidence', 'Context & Review', 'Analyst Verdict', 'Triage Memory', 'History & Notes', 'Technical'][index - 3];
      await expect(page.getByRole('tablist', { name: 'Operational alert sections' }).getByRole('tab', { name: tab })).toHaveAttribute('aria-selected', 'true');
    }
    if (index === 10) await expect(page).toHaveURL(/\/analyst\/tier2-cases$/);
    if (index === 14) await expect(page).toHaveURL(/\/analyst\/external-admission$/);
    if (index < titles.length - 1) await tour.getByRole('button', { name: 'Next' }).click();
  }
  await tour.getByRole('button', { name: 'Finish' }).click();
  await expect(tour).toHaveCount(0);
  await expect(page).toHaveURL(/\/analyst\/operations$/);
  expect(writes).toEqual([]);
});
