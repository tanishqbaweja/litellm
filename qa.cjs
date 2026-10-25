const fs = require("node:fs/promises");
const path = require("node:path");
const assert = require("node:assert/strict");
const { chromium, expect, request } = require(path.join(process.env.LITELLM_REPO ?? "/repo", "tests/e2e/ui/node_modules/@playwright/test"));
const mode = process.argv[2];
assert(["baseline", "fixed"].includes(mode));
const sha = mode === "baseline" ? "dddbaa803d6e9fcc862ea7a5412f771cb1ae040e" : process.env.QA_SOURCE_SHA;
assert(sha);
const baseURL = process.env.LITELLM_BASE_URL ?? "http://127.0.0.1:41475";
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
  const fixture = JSON.parse(await fs.readFile(path.join(__dirname, `fixture-report-${mode}.json`), "utf8"));
  assert.equal(fixture.grouped_rows.length, 4);
  const group = fixture.grouped_rows.find(row => row.session_total_count === 3);
  const hit = fixture.grouped_rows.find(row => row.session_total_count === 1 && row.cache_hit === "True");
  const miss = fixture.grouped_rows.find(row => row.session_total_count === 1 && row.cache_hit === "None" && row.cache_key !== "Cache OFF");
  const off = fixture.grouped_rows.find(row => row.cache_key === "Cache OFF");
  assert(group && hit && miss && off);
  assert.equal(group.session_cache_hit_count, 2);
  const browser = await chromium.launch({ headless: false });
  const report = { mode, sha, browser: browser.version(), fixture: fixture.alias, cases: [] };
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
      const result = { viewport: spec, screenshots: [], pageErrors: [], consoleErrors: [], serverErrors: [], missingResources: [] };
      report.cases.push(result);
      page.on("pageerror", error => result.pageErrors.push(error.message));
      page.on("console", message => {
        if (message.type() === "error") result.consoleErrors.push(message.text());
      });
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
      try {
        await page.goto("/ui/login");
        await page.getByPlaceholder("Enter your username").fill("admin");
        await page.getByPlaceholder("Enter your password").fill(masterKey);
        await page.getByRole("button", { name: "Login", exact: true }).click();
        await expect(page.getByRole("button", { name: "Launch Aria Agent" })).toBeVisible({ timeout: 30000 });
        await page.goto("/ui/?page=logs");
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
        await expect(visible(page, "pagination-range")).toHaveText("Showing 1-4 of 4", { timeout: 30000 });
        await expect(logRow(group)).toBeVisible();
        await capture("table");
        const heading = page.getByRole("columnheader", { name: "Cache Hit", exact: true }).filter({ visible: true });
        if (mode === "baseline") {
          await expect(heading).toHaveCount(0);
          result.column = "absent";
          await page.getByRole("columnheader", { name: "Status", exact: true }).filter({ visible: true }).scrollIntoViewIfNeeded();
        } else {
          await expect(heading).toBeVisible();
          const headers = await page.getByRole("columnheader").filter({ visible: true }).allTextContents();
          const index = headers.findIndex(value => value.trim() === "Cache Hit");
          assert(index >= 0);
          for (const [log, expected] of [[group, "2 hits"], [hit, "Yes"], [miss, "No"], [off, "-"]]) {
            await expect(logRow(log).getByRole("cell").nth(index)).toHaveText(expected);
          }
          result.values = { session: "2 hits", cacheHit: "Yes", cacheMiss: "No", cacheOff: "-" };
          await heading.scrollIntoViewIfNeeded();
        }
        const focusHeader = mode === "baseline"
          ? page.getByRole("columnheader", { name: "Status", exact: true }).filter({ visible: true })
          : heading;
        const headerBox = await focusHeader.boundingBox();
        const bottomRow = await logRow(off).boundingBox();
        result.focusBox = { x: headerBox.x, y: headerBox.y, width: headerBox.width, height: bottomRow.y + bottomRow.height - headerBox.y };
        await capture("cache-column");
        await activate(logRow(hit).getByRole("cell").first());
        const detail = page.getByRole("dialog").filter({ visible: true });
        if (spec.name === "phone") await activate(detail.getByRole("button", { name: "Collapse trace sidebar", exact: true }));
        await expect(detail.getByText("Response Cache", { exact: true })).toBeVisible({ timeout: 15000 });
        await expect(detail.getByText("Hit", { exact: true })).toBeVisible();
        await detail.getByText("Response Cache", { exact: true }).scrollIntoViewIfNeeded();
        await expect(detail.getByText("Hit", { exact: true })).toBeInViewport({ ratio: 1 });
        await capture("hit-detail");
        await page.keyboard.press("Escape");
        await expect(detail).toHaveCount(0);
        await activate(logRow(miss).getByRole("cell").first());
        if (spec.name === "phone") await activate(detail.getByRole("button", { name: "Collapse trace sidebar", exact: true }));
        await expect(detail.getByText("Response Cache", { exact: true })).toBeVisible({ timeout: 15000 });
        await expect(detail.getByText("Miss", { exact: true })).toBeVisible();
        await detail.getByText("Response Cache", { exact: true }).scrollIntoViewIfNeeded();
        await expect(detail.getByText("Miss", { exact: true })).toBeInViewport({ ratio: 1 });
        await capture("miss-detail");
        await page.keyboard.press("Escape");
        await expect(detail).toHaveCount(0);
        await activate(visible(page, "datatable-filters-trigger"));
        await activate(filters.getByRole("combobox").filter({ hasText: "All Requests" }));
        await activate(page.getByRole("option", { name: "Cache Hit", exact: true }));
        await activate(filters.getByRole("button", { name: "Apply Filters" }));
        await expect(filters).toBeHidden();
        await expect(visible(page, "pagination-range")).toHaveText("Showing 1-2 of 2");
        if (mode === "fixed") await heading.scrollIntoViewIfNeeded();
        await capture("hit-filter");
        await activate(visible(page, "datatable-filters-trigger"));
        await activate(filters.getByRole("combobox").filter({ hasText: "Cache Hit" }));
        await activate(page.getByRole("option", { name: "All Requests", exact: true }));
        await activate(filters.getByRole("button", { name: "Apply Filters" }));
        await expect(filters).toBeHidden();
        await expect(visible(page, "pagination-range")).toHaveText("Showing 1-4 of 4");
        result.cacheFilter = "hit filter and reset passed";
        result.pageWidth = await page.evaluate(() => ({ viewport: innerWidth, document: document.documentElement.scrollWidth }));
        assert.equal(result.pageWidth.document, result.pageWidth.viewport);
        assert.deepEqual(result.pageErrors, []);
        assert.deepEqual(result.serverErrors, []);
        result.outcome = "passed";
      } catch (error) {
        await capture("unexpected-failure").catch(() => {});
        result.outcome = error.message;
        await fs.writeFile(path.join(output, "report.json"), JSON.stringify(report, null, 2) + "\n");
        throw error;
      } finally {
        await context.close();
        try { await video.saveAs(path.join(output, `${spec.name}.webm`)); }
        catch (error) {
          result.videoError = error.message;
          if (result.outcome === "passed") throw error;
        }
        await fs.writeFile(path.join(output, "report.json"), JSON.stringify(report, null, 2) + "\n");
      }
      console.log(JSON.stringify({ viewport: spec.name, outcome: result.outcome, column: result.column, values: result.values }));
    }
  } finally {
    await browser.close();
  }
}
main().catch(error => { console.error(error); process.exitCode = 1; });
