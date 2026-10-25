const fs = require("node:fs/promises");
const path = require("node:path");
const assert = require("node:assert/strict");
const { chromium, expect, request } = require("../litellm/tests/e2e/ui/node_modules/@playwright/test");

const build = process.argv[2];
assert(["baseline", "fixed"].includes(build));
const root = path.join(__dirname, "litellm-34927");
const output = path.join(root, `visual-${build}`);
const baseURL = "http://127.0.0.1:41475";
const serviceURL = "http://127.0.0.1:51476";
const key = process.env.LITELLM_MASTER_KEY;
assert(key);
const runId = Date.now().toString(36);
const sourceSha = build === "baseline" ? "dddbaa803d6e9fcc862ea7a5412f771cb1ae040e" : "219212f7532165a3a579de9cb930b634b3ea9055";
const viewports = [{ name: "desktop", width: 1440, height: 900, touch: false }, { name: "phone", width: 390, height: 844, touch: true }];

async function main() {
  await fs.mkdir(output, { recursive: true });
  const api = await request.newContext({ baseURL, extraHTTPHeaders: { Authorization: `Bearer ${key}` } });
  await expect.poll(async () => {
    try { return (await api.get("/health/liveliness", { timeout: 2000 })).status(); }
    catch { return 0; }
  }, { timeout: 90000, intervals: [1000, 2000] }).toBe(200);
  const paramsResponse = await api.get("/guardrails/ui/provider_specific_params");
  assert(paramsResponse.ok());
  const providerFields = (await paramsResponse.json()).generic_guardrail_api;
  assert.equal(Object.hasOwn(providerFields, "api_base"), build === "fixed");
  assert.equal(Object.hasOwn(providerFields, "api_key"), build === "fixed");
  const guardrails = async () => {
    const response = await api.get("/v2/guardrails/list");
    assert(response.ok());
    return (await response.json()).guardrails;
  };
  const remove = async name => {
    for (const row of (await guardrails()).filter(row => row.guardrail_name === name)) {
      const response = await api.delete(`/guardrails/${row.guardrail_id}`);
      assert(response.ok(), `Fixture cleanup returned ${response.status()}`);
    }
  };
  const serviceEvents = async () => (await fs.readFile(path.join(root, "service-events.jsonl"), "utf8"))
    .trim().split("\n").filter(Boolean).map(line => JSON.parse(line));
  const browser = await chromium.launch({ headless: true });
  const reports = [];
  try {
    for (const viewport of viewports) {
      const name = `qa-generic-34927-${viewport.name}`;
      await remove(name);
      const context = await browser.newContext({
        baseURL, viewport: { width: viewport.width, height: viewport.height },
        hasTouch: viewport.touch, isMobile: viewport.touch,
        recordVideo: { dir: path.join(output, "videos"), size: { width: viewport.width, height: viewport.height } },
      });
      const page = await context.newPage();
      const report = { build, sourceSha, runId, viewport, url: `${baseURL}/ui/guardrails/`, providerFields, pageErrors: [], consoleErrors: [], httpErrors: [], steps: [], screenshots: {} };
      page.on("pageerror", error => report.pageErrors.push(error.message));
      page.on("console", message => { if (message.type() === "error") report.consoleErrors.push(message.text()); });
      page.on("response", response => {
        if (response.status() >= 400) report.httpErrors.push({ path: new URL(response.url()).pathname, status: response.status() });
      });
      const click = async locator => viewport.touch ? locator.tap() : locator.click();
      const shoot = async (stage, targets = []) => {
        await expect(page.locator('[role="listbox"]')).toHaveCount(0);
        await expect(page.locator("[data-sonner-toast]")).toHaveCount(0, { timeout: 15000 });
        const boxes = [];
        for (const target of targets) boxes.push(await target.boundingBox());
        report.screenshots[stage] = { path: `${viewport.name}-${stage}.png`, boxes };
        await page.screenshot({ path: path.join(output, `${viewport.name}-${stage}.png`), scale: "css" });
      };
      const checkSaved = async url => {
        await expect.poll(async () => {
          const saved = (await guardrails()).find(row => row.guardrail_name === name);
          return saved?.litellm_params?.api_base;
        }, { timeout: 30000, intervals: [500, 1000] }).toBe(url);
        report.steps.push(`Saved connection URL ${url} is readable from the real proxy`);
      };
      const exercise = async version => {
        await page.goto("/ui/guardrails/");
        await click(page.getByRole("tab", { name: "Test Playground", exact: true }));
        const panel = page.getByRole("tabpanel", { name: "Test Playground" });
        await panel.getByPlaceholder("Search guardrails...").fill(name);
        await click(panel.getByText(name, { exact: true }));
        const input = panel.getByPlaceholder("Enter text to test with guardrails...");
        for (const blocked of [false, true]) {
          const text = `QA ${viewport.name} ${version} ${blocked ? "qa-blocked-34927" : "allowed"} ${runId}`;
          await input.fill(text);
          await click(panel.getByRole("button", { name: /^Test 1 guardrail$/ }));
          const result = blocked
            ? panel.getByText("Blocked by the local QA guardrail", { exact: false })
            : panel.getByText(text, { exact: true }).last();
          if (blocked) {
            await expect(result).toBeVisible({ timeout: 20000 });
          } else {
            await expect(result).toBeVisible({ timeout: 20000 });
            await expect(panel.getByText(`${name} - Error`, { exact: true })).toHaveCount(0);
          }
          await expect.poll(async () => (await serviceEvents()).filter(event => event.texts.includes(text)), { timeout: 10000 }).not.toEqual([]);
          const events = (await serviceEvents()).filter(event => event.texts.includes(text));
          assert(events.every(event => event.authorized));
          assert(events.every(event => event.path === `${version === "updated" ? "/updated" : ""}/beta/litellm_basic_guardrail_api`));
          report.steps.push(`${version} settings send the configured key to the ${version} URL and ${blocked ? "block" : "allow"} the test text`);
          await result.evaluate(element => element.scrollIntoView({ block: "center", inline: "nearest" }));
          await shoot(`${version}-${blocked ? "blocked" : "allowed"}`, [result]);
        }
      };
      try {
        await page.goto("/ui/login");
        await page.getByPlaceholder("Enter your username").fill("admin");
        await page.getByPlaceholder("Enter your password").fill(key);
        await click(page.getByRole("button", { name: "Login", exact: true }));
        await expect(page.getByRole("button", { name: "Launch Aria Agent" })).toBeVisible({ timeout: 30000 });
        await page.goto("/ui/guardrails/");
        await click(page.getByRole("button", { name: "Add New Guardrail" }));
        await click(page.getByRole("menuitem", { name: "Add Provider Guardrail" }));
        const wizard = page.getByRole("dialog", { name: "Create guardrail" });
        await expect(wizard).toBeVisible();
        await wizard.getByRole("textbox", { name: "Guardrail Name" }).fill(name);
        await click(wizard.getByRole("combobox", { name: "Guardrail Provider" }));
        await click(page.getByRole("option", { name: /Generic Guardrail API/ }));
        await expect(page.locator('[role="listbox"]')).toHaveCount(0);
        await shoot("provider-selected", [wizard.getByRole("combobox", { name: "Guardrail Provider" })]);
        const baseInput = wizard.getByLabel("api_base", { exact: true });
        const keyInput = wizard.getByLabel("api_key", { exact: true });
        if (build === "baseline") {
          await expect(baseInput).toHaveCount(0);
          await expect(keyInput).toHaveCount(0);
          await wizard.getByRole("combobox", { name: "Skip tool messages in guardrail" }).scrollIntoViewIfNeeded();
          await shoot("connection-fields", [wizard]);
          report.steps.push("Selecting Generic Guardrail API provides no URL or API-key inputs");
          await click(wizard.getByRole("button", { name: "Next", exact: true }));
          await expect(wizard.getByText("unreachable_fallback", { exact: true })).toBeVisible();
          await shoot("optional-settings", [wizard]);
          report.steps.push("Optional settings already render in the separate Provider Configuration step");
        } else {
          await baseInput.fill(serviceURL);
          await keyInput.fill("qa-generic-local-key");
          await expect(keyInput).toHaveAttribute("type", "password");
          await keyInput.evaluate(element => element.scrollIntoView({ block: "center", inline: "nearest" }));
          await shoot("connection-fields", [baseInput, keyInput]);
          report.steps.push("The URL and masked API-key inputs render and accept values");
          await click(wizard.getByRole("button", { name: "Next", exact: true }));
          await expect(wizard.getByText("unreachable_fallback", { exact: true })).toBeVisible();
          await shoot("optional-settings", [wizard]);
          const createdResponse = page.waitForResponse(response => new URL(response.url()).pathname === "/guardrails" && response.request().method() === "POST");
          await click(wizard.getByRole("button", { name: "Create Guardrail", exact: true }));
          const created = await createdResponse;
          assert(created.ok(), `Create guardrail returned ${created.status()}`);
          const submitted = created.request().postDataJSON().guardrail.litellm_params;
          assert.equal(submitted.api_base, serviceURL);
          assert.equal(submitted.api_key, "qa-generic-local-key");
          await expect(wizard).toHaveCount(0, { timeout: 20000 });
          await checkSaved(serviceURL);
          await exercise("initial");

          await page.goto("/ui/guardrails/");
          const row = page.getByRole("row").filter({ hasText: name });
          await expect(row).toBeVisible({ timeout: 15000 });
          await click(row.locator("td").first().getByRole("button").first());
          await click(page.getByRole("tab", { name: "Settings", exact: true }));
          await click(page.getByRole("button", { name: "Edit Settings", exact: true }));
          const editBase = page.getByLabel("api_base", { exact: true });
          const editKey = page.getByLabel("api_key", { exact: true });
          await expect(editBase).toHaveValue(serviceURL);
          await expect(editKey).toHaveAttribute("type", "password");
          await editBase.fill(`${serviceURL}/updated`);
          await editKey.fill("qa-generic-updated-key");
          await editKey.evaluate(element => element.scrollIntoView({ block: "center", inline: "nearest" }));
          await shoot("edit-settings", [editBase, editKey]);
          const updatedResponse = page.waitForResponse(response => new URL(response.url()).pathname.startsWith("/guardrails/") && response.request().method() === "PATCH");
          const refreshedResponse = page.waitForResponse(response => /^\/guardrails\/[a-f0-9-]+\/info$/i.test(new URL(response.url()).pathname) && response.request().method() === "GET");
          await click(page.getByRole("button", { name: "Save Changes", exact: true }));
          const updated = await updatedResponse;
          assert(updated.ok(), `Update guardrail returned ${updated.status()}`);
          assert.equal(updated.request().postDataJSON().litellm_params.api_base, `${serviceURL}/updated`);
          assert.equal(updated.request().postDataJSON().litellm_params.api_key, "qa-generic-updated-key");
          const refreshed = await refreshedResponse;
          assert(refreshed.ok(), `Reloading saved guardrail returned ${refreshed.status()}`);
          await refreshed.finished();
          await expect(page.getByRole("button", { name: "Save Changes", exact: true })).toHaveCount(0);
          await expect(page.getByRole("tab", { name: "Overview", exact: true })).toBeVisible();
          await checkSaved(`${serviceURL}/updated`);
          await exercise("updated");
          report.serviceEvents = (await serviceEvents()).filter(event => event.texts.some(text => text.startsWith(`QA ${viewport.name} `) && text.endsWith(runId)));
        }
        assert.deepEqual(report.pageErrors, []);
        assert.deepEqual(report.httpErrors.filter(error => error.status >= 500), []);
        report.result = "pass";
        await page.waitForTimeout(1500);
      } catch (error) {
        report.result = "fail";
        report.error = error.stack || String(error);
        await page.screenshot({ path: path.join(output, `${viewport.name}-failure.png`), fullPage: true });
        await fs.writeFile(path.join(output, `${viewport.name}-failure.txt`), await page.locator("body").innerText());
        throw error;
      } finally {
        reports.push(report);
        await context.close();
        report.video = path.relative(output, await page.video().path());
        await fs.writeFile(path.join(output, "report.json"), JSON.stringify(reports, null, 2));
        await remove(name);
      }
    }
    console.log(JSON.stringify(reports.map(({ viewport, result, steps, pageErrors }) => ({ viewport, result, steps, pageErrors }))));
  } finally { await browser.close(); await api.dispose(); }
}
main().catch(error => { console.log(error.stack || String(error)); process.exitCode = 1; });
