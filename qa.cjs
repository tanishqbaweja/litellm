const fs = require("node:fs/promises");
const path = require("node:path");
const assert = require("node:assert/strict");
const { chromium, expect, request } = require("/repo/tests/e2e/ui/node_modules/@playwright/test");
const mode = process.argv[2];
assert(["baseline", "fixed"].includes(mode));
const fixtureLabel = process.env.QA_FIXTURE_LABEL ?? mode;
const baseURL = "http://127.0.0.1:41475";
const masterKey = process.env.LITELLM_MASTER_KEY;
assert(masterKey);
const output = path.join(__dirname, `visual-${mode}`);
const visible = (page, id) => page.getByTestId(id).filter({ visible: true });

async function main() {
  await fs.mkdir(output, { recursive: true });
  const readiness = await request.newContext({ baseURL, extraHTTPHeaders: { Authorization: `Bearer ${masterKey}` } });
  try {
    await expect.poll(async () => {
      try { return (await readiness.get("/health/readiness", { timeout: 2000 })).status(); }
      catch { return 0; }
    }, { timeout: 60000, intervals: [1000, 2000] }).toBe(200);
  } finally {
    await readiness.dispose();
  }
  const fixture = JSON.parse(await fs.readFile(path.join(__dirname, `api-report-${fixtureLabel}.json`), "utf8"));
  assert.equal(fixture.cases.length, 6);
  const expectedRows = mode === "baseline" ? 2 : 6;
  assert.equal(fixture.spend_rows.length, expectedRows);
  const nativeCases = fixture.cases.filter(value => !value.case.endsWith("-control"));
  const selectedCases = mode === "baseline" ? fixture.cases.filter(value => value.case.endsWith("-control")) : fixture.cases;
  const browser = await chromium.launch({ headless: false });
  const report = { mode, sha: fixture.source_sha, browser: browser.version(), fixture: fixture.alias, startedAt: new Date().toISOString(), cases: [] };
  try {
    for (const spec of [{ name: "desktop", width: 1440, height: 900 }, { name: "phone", width: 390, height: 844 }]) {
      const context = await browser.newContext({
        baseURL, viewport: { width: spec.width, height: spec.height },
        isMobile: spec.name === "phone", hasTouch: spec.name === "phone", colorScheme: "light",
        recordVideo: { dir: path.join(output, "raw-video"), size: { width: spec.width, height: spec.height } },
      });
      const page = await context.newPage();
      const activate = locator => spec.name === "phone" ? locator.tap() : locator.click();
      const video = page.video();
      const result = { viewport: spec, screenshots: [], details: [], pageErrors: [], consoleErrors: [], serverErrors: [], missingResources: [] };
      report.cases.push(result);
      page.on("pageerror", error => result.pageErrors.push(error.message));
      page.on("console", message => { if (message.type() === "error") result.consoleErrors.push(message.text()); });
      page.on("response", response => {
        const pathname = new URL(response.url()).pathname;
        if (response.status() >= 500) result.serverErrors.push({ pathname, status: response.status() });
        if (response.status() === 404) result.missingResources.push(pathname);
      });
      const capture = async stage => {
        const file = `${spec.name}-${stage}.png`;
        await page.mouse.move(1, 1);
        await page.screenshot({ path: path.join(output, file), scale: "css" });
        result.screenshots.push(file);
      };
      const logRow = log => page.locator(`tr[data-row-id="${log.request_id}"]`).filter({ visible: true });
      const applyKeyFilter = async () => {
        await expect(visible(page, "datatable-search")).toBeVisible({ timeout: 30000 });
        const dismiss = page.getByText("Don't ask me again");
        if (await dismiss.isVisible()) await dismiss.click();
        await activate(visible(page, "datatable-filters-trigger"));
        const filters = page.getByRole("dialog", { name: "Filters", exact: true });
        await filters.getByRole("combobox", { name: "Search a key alias" }).click();
        await page.keyboard.type(fixture.alias);
        await page.getByRole("option", { name: fixture.alias, exact: true }).click();
        await activate(filters.getByRole("button", { name: "Apply Filters" }));
        await expect(filters).toBeHidden();
        await expect(visible(page, "pagination-range")).toHaveText(`Showing 1-${expectedRows} of ${expectedRows}`, { timeout: 30000 });
      };
      try {
        await page.goto("/ui/login");
        await page.getByPlaceholder("Enter your username").fill("admin");
        await page.getByPlaceholder("Enter your password").fill(masterKey);
        await page.getByRole("button", { name: "Login", exact: true }).click();
        await expect(page.getByRole("button", { name: "Launch Aria Agent" })).toBeVisible({ timeout: 30000 });
        await page.goto("/ui/?page=logs");
        await applyKeyFilter();
        for (const row of fixture.spend_rows) await expect(logRow(row)).toBeVisible();
        result.tableCount = expectedRows;
        result.tableBox = await page.getByRole("table").filter({ visible: true }).boundingBox();
        result.paginationBox = await visible(page, "pagination-range").boundingBox();
        await capture("table");
        if (mode === "baseline") {
          result.missingNativeEndpoints = nativeCases.map(value => value.endpoint);
        }
        for (const native of selectedCases) {
          const row = fixture.spend_rows.find(value => {
            if (native.case === "regular-embeddings-control") return value.call_type === "aembedding";
            if (value.call_type !== "allm_passthrough_route") return false;
            return new URL(value.api_base).pathname === native.endpoint.replace(/^\/vllm/, "");
          });
          assert(row, `Missing persisted row for ${native.case}`);
          const tokens = native.usage.prompt_tokens;
          assert.equal(row.prompt_tokens, tokens);
          assert.equal(row.completion_tokens, 0);
          assert.equal(row.total_tokens, native.usage.total_tokens);
          assert.equal(row.spend, tokens / 1_000_000);
          assert.equal(row.status, "success");
          await activate(logRow(row).getByRole("cell").first());
          const detail = page.getByRole("dialog").filter({ visible: true });
          if (spec.name === "phone") await activate(detail.getByRole("button", { name: "Collapse trace sidebar", exact: true }));
          const tokenMetric = detail.getByText("Tokens", { exact: true }).locator("..");
          const costMetric = detail.getByText("Cost", { exact: true }).locator("..");
          await expect(tokenMetric).toContainText(`${tokens} (${tokens} prompt tokens + 0 completion tokens)`);
          const costText = await costMetric.innerText();
          const cost = Number(costText.match(/\$([\d,.]+)/)[1].replaceAll(",", ""));
          assert.equal(cost, row.spend);
          await tokenMetric.scrollIntoViewIfNeeded();
          await capture(`${native.case}-metrics`);
          const detailResult = { case: native.case, rowId: row.request_id, promptTokens: tokens, completionTokens: 0, spend: cost };
          if (!native.case.endsWith("-control")) {
            await activate(detail.getByRole("tab", { name: "JSON", exact: true }));
            await activate(detail.getByRole("tab", { name: "Response", exact: true }));
            const responsePanel = detail.getByRole("tabpanel").filter({ visible: true }).last();
            await expect(responsePanel).toContainText(native.response_id);
            await expect(responsePanel).toContainText(native.response_model);
            await expect(responsePanel).toContainText("prompt_tokens");
            await expect(responsePanel).toContainText(native.case === "rerank" ? "relevance_score" : native.case === "score" ? "score" : native.case === "classify" ? "num_classes" : "pooling");
            await responsePanel.scrollIntoViewIfNeeded();
            await capture(`${native.case}-response`);
            detailResult.nativeResponseId = native.response_id;
            detailResult.nativeResponseVisible = true;
          }
          result.details.push(detailResult);
          await page.keyboard.press("Escape");
          await expect(detail).toHaveCount(0);
        }
        await page.goto("/ui/?page=logs");
        await applyKeyFilter();
        for (const row of fixture.spend_rows) await expect(logRow(row)).toBeVisible();
        await capture("table-after-reopen");
        result.reopenedCount = expectedRows;
        result.pageWidth = await page.evaluate(() => ({ viewport: innerWidth, document: document.documentElement.scrollWidth }));
        assert.equal(result.pageWidth.document, result.pageWidth.viewport);
        assert.deepEqual(result.pageErrors, []);
        assert.deepEqual(result.serverErrors, []);
        result.outcome = "passed";
      } catch (error) {
        await capture("unexpected-failure").catch(() => {});
        result.outcome = error.message;
        throw error;
      } finally {
        await context.close();
        await video.saveAs(path.join(output, `${spec.name}.webm`));
        report.updatedAt = new Date().toISOString();
        await fs.writeFile(path.join(output, "report.json"), JSON.stringify(report, null, 2) + "\n");
      }
      console.log(JSON.stringify({ viewport: spec.name, outcome: result.outcome, rows: result.tableCount, details: result.details.length }));
    }
  } finally {
    await browser.close();
  }
}
main().catch(error => { console.error(error); process.exitCode = 1; });
