const fs = require("node:fs/promises");
const path = require("node:path");
const assert = require("node:assert/strict");
const repo = process.env.LITELLM_REPO_ROOT || path.resolve(__dirname, "../litellm");
const { chromium, request, expect } = require(path.join(repo, "tests/e2e/ui/node_modules/@playwright/test"));
const mode = process.argv[2];
assert(["baseline", "fixed"].includes(mode));
const masterKey = process.env.LITELLM_MASTER_KEY;
assert(masterKey, "LITELLM_MASTER_KEY is required");
const baseURL = process.env.E2E_UI_BASE_URL || "http://127.0.0.1:41475";
const qaRoot = path.join(__dirname, "litellm-47520");
const output = path.join(qaRoot, `visual-${mode}${process.env.QA_CAPTURE_SUFFIX || ""}`);
const fixturePath = path.join(qaRoot, "visual-fixture.private.json");
const frontendSha = mode === "baseline" ? "dddbaa803d6e9fcc862ea7a5412f771cb1ae040e" : process.env.QA_HEAD_SHA;
assert(frontendSha, "QA_HEAD_SHA is required for final fixed verification");
const visible = (page, id) => page.getByTestId(id).filter({ visible: true });
const viewports = [
  { name: "desktop", viewport: { width: 1440, height: 900 } },
  { name: "phone", viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true },
  { name: "short-desktop", viewport: { width: 1280, height: 600 } },
];

async function main() {
  await fs.mkdir(output, { recursive: true });
  const api = await request.newContext({ baseURL, extraHTTPHeaders: { Authorization: `Bearer ${masterKey}` } });
  let fixture;
  try {
    fixture = JSON.parse(await fs.readFile(fixturePath, "utf8"));
    const info = await api.get(`/key/info?key=${encodeURIComponent(fixture.token)}`);
    assert(info.ok(), "The shared comparison key must still exist");
  } catch (error) {
    if (error.code !== "ENOENT") throw error;
    const alias = `qa-pagination-${Date.now()}`;
    const created = await api.post("/key/generate", { data: { key_alias: alias } });
    assert(created.ok(), `Key creation returned ${created.status()}`);
    const key = await created.json();
    const ids = await Promise.all(Array.from({ length: 26 }, async (_, index) => {
      const response = await api.post("/v1/chat/completions", {
        headers: { Authorization: `Bearer ${key.key}` },
        data: { model: "fake-openai-gpt-4", messages: [{ role: "user", content: `${alias}-${index}` }] },
      });
      assert(response.ok(), `Completion returned ${response.status()}`);
      const body = await response.json();
      assert.equal(body.choices[0].message.content, "This is a mock response.");
      return body.id;
    }));
    fixture = { alias, token: key.token ?? key.token_id, ids };
    await fs.writeFile(fixturePath, JSON.stringify(fixture, null, 2));
  }
  await expect.poll(async () => {
    const response = await api.get(`/spend/logs?request_id=${encodeURIComponent(fixture.ids.at(-1))}`);
    if (!response.ok()) return 0;
    const body = await response.json();
    return (Array.isArray(body) ? body : body.data ?? []).length;
  }, { timeout: 60000, intervals: [1000, 2000] }).toBeGreaterThan(0);

  const browser = await chromium.launch({ headless: true });
  const report = { mode, frontendSha, browser: browser.version(), fixtureAlias: fixture.alias, cases: [] };
  try {
    for (const spec of viewports) {
      const { name, ...options } = spec;
      const context = await browser.newContext({
        baseURL, ...options, colorScheme: "light",
        recordVideo: { dir: path.join(output, "raw-video"), size: spec.viewport },
      });
      const page = await context.newPage();
      const video = page.video();
      const pageErrors = [];
      const consoleErrors = [];
      const serverErrors = [];
      const missingResources = [];
      page.on("pageerror", error => pageErrors.push(error.message));
      page.on("console", message => { if (message.type() === "error") consoleErrors.push(message.text()); });
      page.on("response", response => {
        if (response.status() >= 500) serverErrors.push({ path: new URL(response.url()).pathname, status: response.status() });
        if (response.status() === 404) missingResources.push(new URL(response.url()).pathname);
      });
      const result = { name, viewport: spec.viewport, pageErrors, consoleErrors, serverErrors, missingResources };
      try {
        await page.goto("/ui/login");
        await page.getByPlaceholder("Enter your username").fill("admin");
        await page.getByPlaceholder("Enter your password").fill(masterKey);
        await page.getByRole("button", { name: "Login", exact: true }).click();
        await expect(page.getByRole("button", { name: "Launch Aria Agent" })).toBeVisible({ timeout: 30000 });
        await page.goto("/ui/?page=logs");
        await expect(visible(page, "datatable-search")).toBeVisible({ timeout: 20000 });
        const dismiss = page.getByText("Don't ask me again");
        if (await dismiss.isVisible()) await dismiss.click();
        await visible(page, "datatable-filters-trigger").click();
        const drawer = page.getByRole("dialog", { name: "Filters" });
        await drawer.getByRole("combobox", { name: "Search a key alias" }).click();
        await page.keyboard.type(fixture.alias);
        await page.getByRole("option", { name: fixture.alias, exact: true }).click();
        await drawer.getByRole("button", { name: "Apply Filters" }).click();
        await expect(drawer).toBeHidden();
        const setSize = async size => {
          await visible(page, "pagination-page-size").click();
          await page.getByRole("option", { name: size, exact: true }).click();
        };
        const range = visible(page, "pagination-range");
        await setSize("25");
        await expect(range).toHaveText("Showing 1-25 of 26", { timeout: 30000 });
        const launcher = page.getByRole("button", { name: "Launch Aria Agent" });
        await expect(launcher).toBeVisible();
        result.launcher = await launcher.boundingBox();
        result.next = await visible(page, "pagination-next").boundingBox();
        result.fit = await page.evaluate(() => ({ width: innerWidth, scrollWidth: document.documentElement.scrollWidth, height: innerHeight }));
        await page.mouse.move(1, 1);
        await page.screenshot({ path: path.join(output, `${name}.png`), scale: "css" });

        if (mode === "baseline") {
          let blocked;
          try { await visible(page, "pagination-next").click({ timeout: 3000 }); }
          catch (error) { blocked = error.message; }
          assert(blocked?.includes("intercepts pointer events") && blocked.includes("Aria Agent"), "Expected the real launcher to block pagination");
          await expect(range).toHaveText("Showing 1-25 of 26");
          result.pagination = "blocked by Aria Agent";
        } else {
          const activate = async id => spec.hasTouch ? visible(page, id).tap() : visible(page, id).click();
          await activate("pagination-next");
          await expect(range).toHaveText("Showing 26-26 of 26");
          await page.screenshot({ path: path.join(output, `${name}-next-page.png`), scale: "css" });
          await expect(visible(page, "pagination-next")).toBeDisabled();
          await expect(visible(page, "pagination-last")).toBeDisabled();
          await activate("pagination-prev");
          await expect(range).toHaveText("Showing 1-25 of 26");
          await activate("pagination-last");
          await expect(range).toHaveText("Showing 26-26 of 26");
          await activate("pagination-first");
          await expect(range).toHaveText("Showing 1-25 of 26");
          await setSize("50");
          await expect(range).toHaveText("Showing 1-26 of 26");
          await expect(visible(page, "pagination-next")).toBeDisabled();
          await expect(visible(page, "pagination-last")).toBeDisabled();
          await setSize("25");
          await expect(range).toHaveText("Showing 1-25 of 26");
          if (spec.hasTouch) await launcher.tap();
          else await launcher.click();
          const assistant = page.getByRole("dialog", { name: "Aria Agent", exact: true });
          await expect(assistant).toBeVisible();
          await expect(assistant).toHaveCSS("opacity", "1");
          await page.screenshot({ path: path.join(output, `${name}-assistant-open.png`), scale: "css" });
          if (spec.hasTouch) await assistant.getByRole("button", { name: "Close Aria Agent" }).tap();
          else await page.keyboard.press("Escape");
          await expect(assistant).toBeHidden();
          await expect(launcher).toBeFocused();
          await activate("pagination-next");
          await expect(range).toHaveText("Showing 26-26 of 26");
          await activate("pagination-first");
          await expect(range).toHaveText("Showing 1-25 of 26");
          result.pagination = "next, previous, last, first, page size and assistant round trip passed";
          await page.goto("/ui/?page=api-keys");
          const search = page.getByPlaceholder("Search by key alias or ID");
          await expect(search).toBeVisible();
          await search.fill(fixture.alias);
          await expect(page.getByRole("row").filter({ hasText: fixture.alias })).toBeVisible();
          await expect(visible(page, "pagination-range")).toHaveText("Showing 1-1 of 1");
          await expect(page.getByRole("row").filter({ hasText: "e2eUpdateLimitsKey" })).toHaveCount(0);
          await search.press("Tab");
          await page.screenshot({ path: path.join(output, `${name}-keys.png`), scale: "css" });
          result.keys = "key search passed after navigation";
          assert.equal(result.fit.scrollWidth, result.fit.width, "Page-level horizontal overflow");
          assert.equal(pageErrors.length, 0, "Uncaught application errors");
          assert.equal(serverErrors.length, 0, "Server errors during the workflow");
        }
        report.cases.push(result);
        await fs.writeFile(path.join(output, "report.json"), JSON.stringify(report, null, 2));
        console.log(JSON.stringify(result));
      } catch (error) {
        await page.screenshot({ path: path.join(output, `${name}-unexpected-failure.png`), scale: "css" }).catch(() => {});
        throw error;
      } finally {
        await context.close();
        await video.saveAs(path.join(output, `${name}.webm`));
      }
    }
  } finally {
    await browser.close();
    await api.dispose();
  }
}
main().catch(error => { console.error(error); process.exitCode = 1; });
