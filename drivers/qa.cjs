const fs = require("node:fs/promises");
const path = require("node:path");
const assert = require("node:assert/strict");
const { chromium, expect } = require("/repo/tests/e2e/ui/node_modules/@playwright/test");

const revision = process.argv[2];
assert(["baseline", "fixed"].includes(revision));
const root = __dirname;
const output = path.join(root, "output", "playwright", `visual-${revision}-${Date.now()}`);
const baseURL = "http://127.0.0.1:41477";
const visible = locator => locator.filter({ visible: true }).first();
const lastId = "vs_qa38352_103";

async function main() {
  await fs.mkdir(output, { recursive: true });
  const privateData = JSON.parse(await fs.readFile(path.join(root, `live-${revision}.private.json`), "utf8"));
  const source = JSON.parse(await fs.readFile(path.join(root, `proxy-source-${revision}.json`), "utf8"));
  const expected = JSON.parse(await fs.readFile(path.join(root, revision === "baseline" ? "runtime.json" : "product.json"), "utf8"))[revision === "baseline" ? "base" : "head"];
  assert.equal(source.sha, expected);
  assert.equal(await fs.realpath(`/proc/${source.pid}/cwd`), source.source);
  const report = { revision, sourceSha: source.sha, output, startedAt: new Date().toISOString(), providerRequestsPerformed: false, viewports: [] };
  const browser = await chromium.launch({ headless: false });
  report.browser = browser.version();
  try {
    for (const viewport of [{ name: "desktop", width: 1440, height: 900 }, { name: "phone", width: 390, height: 844 }]) {
      const context = await browser.newContext({
        baseURL, viewport: { width: viewport.width, height: viewport.height },
        isMobile: viewport.name === "phone", hasTouch: viewport.name === "phone", colorScheme: "light",
        recordVideo: { dir: path.join(output, "raw-video"), size: { width: viewport.width, height: viewport.height } },
      });
      const page = await context.newPage();
      page.setDefaultTimeout(20000);
      const video = page.video();
      const result = { viewport, startedAt: new Date().toISOString(), steps: [], inventoryResponses: [], pageErrors: [], consoleErrors: [], failedResponses: [] };
      report.viewports.push(result);
      const pendingResponses = [];
      const activate = locator => viewport.name === "phone" ? locator.tap() : locator.click();
      const range = visible(page.getByTestId("pagination-range"));
      const capture = async (name, details = {}) => {
        await page.mouse.move(1, 1);
        await page.waitForTimeout(700);
        const screenshot = `${viewport.name}-${name}.png`;
        await page.screenshot({ path: path.join(output, screenshot), fullPage: true, scale: "css" });
        result.steps.push({ name, at: new Date().toISOString(), screenshot, ...details });
        console.log(JSON.stringify({ revision, viewport: viewport.name, step: name }));
      };
      page.on("pageerror", error => result.pageErrors.push(error.message));
      page.on("console", event => { if (event.type() === "error") result.consoleErrors.push(event.text()); });
      page.on("response", response => {
        const url = new URL(response.url());
        if (response.status() >= 400) result.failedResponses.push({ path: url.pathname, status: response.status() });
        if (url.pathname === "/vector_store/list") {
          pendingResponses.push((async () => {
            const body = await response.json();
            result.inventoryResponses.push({ path: url.pathname, query: Object.fromEntries(url.searchParams), status: response.status(), ids: body.data?.map(store => store.vector_store_id), total_count: body.total_count, current_page: body.current_page, total_pages: body.total_pages });
          })());
        }
        if (/\/vector_stores\/[^/]+\/search$/.test(url.pathname)) report.providerRequestsPerformed = true;
      });
      try {
        await page.goto("/ui/login");
        await page.getByPlaceholder("Enter your username").fill("admin");
        const password = page.getByPlaceholder("Enter your password");
        await expect(password).toHaveAttribute("type", "password");
        await password.fill(privateData.master_key);
        await activate(page.getByRole("button", { name: "Login", exact: true }));
        await expect(page.getByRole("button", { name: "Launch Aria Agent" })).toBeVisible({ timeout: 30000 });
        await page.goto("/ui/?page=vector-stores");
        const dismiss = page.getByText("Don't ask me again");
        if (await dismiss.isVisible()) await activate(dismiss);
        await expect(page.getByRole("heading", { name: "Vector Store Management", exact: true })).toBeVisible({ timeout: 30000 });
        await activate(page.getByRole("tab", { name: "Manage Vector Stores", exact: true }));
        await expect(range).toHaveText("Showing 1-25 of 103", { timeout: 30000 });
        await activate(visible(page.getByTestId("sort-header-vector_store_id")));
        await expect(visible(page.getByRole("button", { name: "vs_qa38352_001", exact: true }))).toBeVisible();
        await capture("first-page", { range: await range.innerText() });

        await activate(visible(page.getByRole("button", { name: "Go to last page", exact: true })));
        await expect(range).toHaveText("Showing 101-103 of 103");
        await expect(visible(page.getByTestId("pagination-page"))).toHaveText("Page 5 of 5");
        const lastStore = visible(page.getByRole("button", { name: lastId, exact: true }));
        await expect(lastStore).toBeVisible();
        await capture("last-page", { range: await range.innerText(), store: lastId });

        await activate(lastStore);
        await expect(page.getByRole("heading", { name: `Vector Store ID: ${lastId}`, exact: true })).toBeVisible();
        await expect(visible(page.getByText("Catalog 103", { exact: true }))).toBeVisible();
        await capture("store-details", { store: lastId });
        await activate(page.getByRole("button", { name: "Back to Vector Stores", exact: true }));
        await activate(page.getByRole("tab", { name: "Test Vector Store", exact: true }));
        const picker = visible(page.getByPlaceholder("Select a vector store"));
        await activate(picker);
        await picker.fill("Catalog 103");
        const option = visible(page.getByRole("option", { name: /Catalog 103.*vs_qa38352_103/ }));
        await expect(option).toBeVisible();
        await capture("selector-option", { store: lastId });
        await activate(option);
        await expect(picker).toHaveValue("Catalog 103");
        await expect(visible(page.getByText("Test your vector store by entering a search query below", { exact: true }))).toBeVisible();
        await capture("selected-store", { selected: await picker.inputValue() });

        await activate(page.getByRole("tab", { name: "Manage Vector Stores", exact: true }));
        const lastResponse = page.waitForResponse(response => {
          const url = new URL(response.url());
          return url.pathname === "/vector_store/list" && (revision === "baseline" || url.searchParams.get("page") === "2");
        });
        await activate(page.getByRole("button", { name: "Refresh", exact: true }));
        assert.equal((await lastResponse).status(), 200);
        await expect(range).toHaveText("Showing 1-25 of 103");
        await capture("refreshed-inventory", { range: await range.innerText() });

        await page.reload();
        await activate(page.getByRole("tab", { name: "Manage Vector Stores", exact: true }));
        await expect(range).toHaveText("Showing 1-25 of 103", { timeout: 30000 });
        await capture("reloaded-inventory", { range: await range.innerText() });
        await Promise.all(pendingResponses);
        assert(result.inventoryResponses.length > 0);
        assert(result.inventoryResponses.every(response => response.status === 200 && response.total_count === 103));
        if (revision === "fixed") {
          assert(result.inventoryResponses.some(response => response.current_page === 1 && response.ids.length === 100));
          assert(result.inventoryResponses.some(response => response.current_page === 2 && response.ids.length === 3 && response.ids.includes(lastId)));
          assert(result.inventoryResponses.every(response => response.ids.length <= 100));
        } else {
          assert(result.inventoryResponses.every(response => response.ids.length === 103));
        }
        assert.deepEqual(result.pageErrors, []);
        assert.deepEqual(result.failedResponses.filter(response => response.status >= 500), []);
        assert.equal(report.providerRequestsPerformed, false);
        result.result = "pass";
      } catch (error) {
        result.result = "fail";
        result.error = error.stack || String(error);
        await page.screenshot({ path: path.join(output, `${viewport.name}-failure.png`), fullPage: true, scale: "css" });
        await fs.writeFile(path.join(output, `${viewport.name}-failure.txt`), await page.locator("body").innerText());
        throw error;
      } finally {
        await Promise.allSettled(pendingResponses);
        await context.close();
        result.video = path.relative(output, await video.path());
        result.completedAt = new Date().toISOString();
        await fs.writeFile(path.join(root, `ui-report-${revision}.json`), JSON.stringify(report, null, 2) + "\n");
      }
    }
    report.completedAt = new Date().toISOString();
    await fs.writeFile(path.join(root, `ui-report-${revision}.json`), JSON.stringify(report, null, 2) + "\n");
    console.log(JSON.stringify(report.viewports.map(result => ({ viewport: result.viewport.name, result: result.result, steps: result.steps.length, inventoryResponses: result.inventoryResponses.length, pageErrors: result.pageErrors, failedResponses: result.failedResponses }))));
  } finally { await browser.close(); }
}

main().catch(error => { console.error(error.stack || String(error)); process.exitCode = 1; });
