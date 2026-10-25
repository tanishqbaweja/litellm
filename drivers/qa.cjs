const fs = require('node:fs/promises');
const path = require('node:path');
const assert = require('node:assert/strict');
const { chromium, expect } = require('/repo/tests/e2e/ui/node_modules/@playwright/test');

const revision = process.argv[2];
assert(['baseline', 'fixed'].includes(revision));
const root = __dirname;
const output = path.join(root, 'output', 'playwright', `visual-${revision}-${Date.now()}`);
const baseURL = 'http://127.0.0.1:41478';
const visible = locator => locator.filter({ visible: true }).first();

async function main() {
  await fs.mkdir(output, { recursive: true });
  const privateData = JSON.parse(await fs.readFile(path.join(root, `live-${revision}.private.json`), 'utf8'));
  const source = JSON.parse(await fs.readFile(path.join(root, `proxy-source-${revision}.json`), 'utf8'));
  const metadata = JSON.parse(await fs.readFile(path.join(root, revision === 'baseline' ? 'runtime.json' : 'product.json'), 'utf8'));
  assert.equal(source.sha, metadata[revision === 'baseline' ? 'base' : 'head']);
  assert.equal(await fs.realpath(`/proc/${source.pid}/cwd`), source.source);
  const report = { revision, sourceSha: source.sha, uiSourceSha: source.ui_source_sha, output, startedAt: new Date().toISOString(), providerRequestsPerformed: false, viewports: [] };
  const browser = await chromium.launch({ headless: false });
  report.browser = browser.version();
  try {
    for (const viewport of [{ name: 'desktop', width: 1440, height: 900 }, { name: 'phone', width: 390, height: 844 }]) {
      const context = await browser.newContext({
        baseURL, viewport: { width: viewport.width, height: viewport.height },
        isMobile: viewport.name === 'phone', hasTouch: viewport.name === 'phone', colorScheme: 'light',
        recordVideo: { dir: path.join(output, 'raw-video'), size: { width: viewport.width, height: viewport.height } },
      });
      const page = await context.newPage();
      page.setDefaultTimeout(20000);
      const video = page.video();
      const budgetId = `qa38759-${viewport.name}`;
      const result = { viewport, budgetId, startedAt: new Date().toISOString(), steps: [], mutations: [], readbacks: [], pageErrors: [], consoleErrors: [], failedResponses: [] };
      report.viewports.push(result);
      const activate = locator => viewport.name === 'phone' ? locator.tap() : locator.click();
      const capture = async (name, details = {}) => {
        await page.mouse.move(1, 1);
        await page.waitForTimeout(700);
        const screenshot = `${viewport.name}-${name}.png`;
        await page.screenshot({ path: path.join(output, screenshot), fullPage: true, scale: 'css' });
        result.steps.push({ name, at: new Date().toISOString(), screenshot, ...details });
        console.log(JSON.stringify({ revision, viewport: viewport.name, step: name }));
      };
      const readBudget = async () => {
        const response = await page.request.post('/budget/info', { headers: { Authorization: `Bearer ${privateData.master_key}` }, data: { budgets: [budgetId] } });
        assert.equal(response.status(), 200, await response.text());
        const values = await response.json();
        result.readbacks.push(values);
        return values;
      };
      const mutate = async (route, action) => {
        const responsePromise = page.waitForResponse(response => new URL(response.url()).pathname === route && response.request().method() === 'POST');
        await action();
        const response = await responsePromise;
        const body = await response.json();
        const request = response.request().postDataJSON();
        result.mutations.push({ path: route, status: response.status(), request, response: body });
        assert.equal(response.status(), 200, JSON.stringify(body));
        return { request, body };
      };
      const search = async () => {
        const searchInput = page.getByPlaceholder('Search by budget ID');
        const responsePromise = page.waitForResponse(response => {
          const url = new URL(response.url());
          return url.pathname === '/management/v1/budgets' && url.searchParams.get('q') === budgetId;
        });
        await searchInput.fill(budgetId);
        assert.equal((await responsePromise).status(), 200);
      };
      const row = () => visible(page.getByRole('row').filter({ hasText: budgetId }));
      const openEdit = async () => {
        await activate(visible(page.getByTestId(`budget-actions-${budgetId}`)));
        await activate(page.getByTestId('budget-action-edit'));
        const modal = page.getByRole('dialog', { name: /Edit budget/i });
        await expect(modal).toBeVisible();
        return modal;
      };
      page.on('pageerror', error => result.pageErrors.push(error.message));
      page.on('console', event => { if (event.type() === 'error') result.consoleErrors.push(event.text()); });
      page.on('response', response => {
        if (response.status() >= 400) result.failedResponses.push({ path: new URL(response.url()).pathname, status: response.status() });
      });
      try {
        await page.goto('/ui/login');
        await page.getByPlaceholder('Enter your username').fill('admin');
        const password = page.getByPlaceholder('Enter your password');
        await expect(password).toHaveAttribute('type', 'password');
        await password.fill(privateData.master_key);
        await activate(page.getByRole('button', { name: 'Login', exact: true }));
        await expect(page.getByRole('button', { name: 'Launch Aria Agent' })).toBeVisible({ timeout: 30000 });
        await page.goto('/ui/?page=budgets');
        const dismiss = page.getByText("Don't ask me again");
        if (await dismiss.isVisible()) await activate(dismiss);
        await expect(page.getByRole('heading', { name: 'Budgets', exact: true })).toBeVisible({ timeout: 30000 });
        await capture('budgets-page');

        await activate(page.getByRole('button', { name: 'Create Budget', exact: true }));
        const create = page.getByRole('dialog', { name: /Create budget/i });
        await expect(create).toBeVisible();
        await create.getByRole('textbox', { name: 'Budget ID' }).fill(budgetId);
        await create.getByRole('spinbutton', { name: 'Spend limit' }).fill('20');
        await create.getByRole('spinbutton', { name: 'Tokens per minute', exact: true }).fill('1000');
        await create.getByRole('spinbutton', { name: 'Requests per minute', exact: true }).fill('60');
        await activate(create.getByRole('combobox', { name: 'Reset period' }));
        await activate(page.getByRole('option', { name: 'per month', exact: true }));
        await capture('create-form');
        await mutate('/budget/new', () => activate(create.getByRole('button', { name: /Create budget/i })));
        await expect(create).not.toBeVisible();
        await search();
        await expect(row()).toContainText('$20.00');
        const [created] = await readBudget();
        assert.equal(created.max_budget, 20);
        assert.equal(created.tpm_limit, 1000);
        assert.equal(created.rpm_limit, 60);
        assert.equal(created.budget_duration, '30d');
        await capture('created-budget', { row: await row().innerText() });

        const edit = await openEdit();
        await expect(edit.getByRole('spinbutton', { name: 'Spend limit' })).toHaveValue('20');
        await edit.getByRole('spinbutton', { name: 'Spend limit' }).fill('99');
        await capture('edit-form');
        const update = await mutate('/budget/update', () => activate(edit.getByRole('button', { name: 'Save', exact: true })));
        assert.deepEqual(update.request, { budget_id: budgetId, max_budget: 99 });
        await expect(edit).not.toBeVisible();
        await expect(row()).toContainText('$99.00');
        const [raised] = await readBudget();
        assert.deepEqual(raised, { ...created, max_budget: 99, updated_at: raised.updated_at });
        await capture('edited-budget', { row: await row().innerText() });

        const clear = await openEdit();
        await clear.getByRole('spinbutton', { name: 'Spend limit' }).fill('');
        await capture('clear-spend-form');
        const clearResponse = await mutate('/budget/update', () => activate(clear.getByRole('button', { name: 'Save', exact: true })));
        assert.deepEqual(clearResponse.request, { budget_id: budgetId, max_budget: null });
        await expect(clear).not.toBeVisible();
        await expect(row()).toContainText('Unlimited');
        const [cleared] = await readBudget();
        assert.deepEqual(cleared, { ...raised, max_budget: null, updated_at: cleared.updated_at });
        await capture('cleared-spend-budget', { row: await row().innerText() });

        await page.reload();
        await expect(page.getByRole('heading', { name: 'Budgets', exact: true })).toBeVisible();
        if (await page.getByPlaceholder('Search by budget ID').inputValue() !== budgetId) await search();
        await expect(row()).toContainText('Unlimited');
        const [reloaded] = await readBudget();
        assert.deepEqual(reloaded, cleared);
        await capture('reloaded-budget', { row: await row().innerText() });

        await activate(visible(page.getByTestId(`budget-actions-${budgetId}`)));
        await activate(page.getByTestId('budget-action-delete'));
        const confirm = page.getByRole('dialog', { name: 'Delete Budget?' });
        await expect(confirm).toBeVisible();
        await mutate('/budget/delete', () => activate(confirm.getByRole('button', { name: 'Delete', exact: true })));
        await expect(page.getByRole('row').filter({ hasText: budgetId })).toHaveCount(0);
        assert.deepEqual(await readBudget(), []);
        await capture('deleted-budget');
        assert.deepEqual(result.pageErrors, []);
        assert.deepEqual(result.failedResponses.filter(response => response.status >= 500), []);
        result.result = 'pass';
      } catch (error) {
        result.result = 'fail';
        result.error = error.stack || String(error);
        await page.screenshot({ path: path.join(output, `${viewport.name}-failure.png`), fullPage: true, scale: 'css' });
        await fs.writeFile(path.join(output, `${viewport.name}-failure.txt`), await page.locator('body').innerText());
        throw error;
      } finally {
        const cleanupRead = await readBudget();
        if (cleanupRead.length) {
          const cleanup = await page.request.post('/budget/delete', { headers: { Authorization: `Bearer ${privateData.master_key}` }, data: { id: budgetId } });
          result.fallbackCleanupStatus = cleanup.status();
        }
        await context.close();
        result.video = path.relative(output, await video.path());
        result.completedAt = new Date().toISOString();
        await fs.writeFile(path.join(root, `ui-report-${revision}.json`), JSON.stringify(report, null, 2) + '\n');
      }
    }
    report.completedAt = new Date().toISOString();
    await fs.writeFile(path.join(root, `ui-report-${revision}.json`), JSON.stringify(report, null, 2) + '\n');
    console.log(JSON.stringify(report.viewports.map(result => ({ viewport: result.viewport.name, result: result.result, steps: result.steps.length, mutations: result.mutations.length, pageErrors: result.pageErrors, failedResponses: result.failedResponses }))));
  } finally {
    await browser.close();
  }
}
main().catch(error => { console.error(error.stack || String(error)); process.exitCode = 1; });
