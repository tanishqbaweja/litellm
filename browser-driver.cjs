const fs = require("node:fs/promises");
const path = require("node:path");
const assert = require("node:assert/strict");
const { chromium, request, expect } = require("../litellm/tests/e2e/ui/node_modules/@playwright/test");

const build = process.argv[2];
assert(["baseline", "fixed"].includes(build));
const root = path.join(__dirname, "litellm-26473");
const output = path.join(root, build === "fixed" ? "visual-fixed-final" : "visual-baseline");
const baseURL = "http://127.0.0.1:41475";
const masterKey = process.env.LITELLM_MASTER_KEY;
assert(masterKey);
const primary = "fake-openai-gpt-4";
const backup = "fake-anthropic-claude";
const sibling = "qa-fallback-26473";
const override = {
  model: backup,
  reasoning_effort: "none",
  api_key: "qa-override-not-a-provider-secret",
  extra_headers: { "X-QA-Sentinel": "preserve-me" },
};
const initialFallbacks = [{ [primary]: [override, sibling] }, { [sibling]: [backup] }];
const viewports = [
  { name: "desktop", width: 1440, height: 900, touch: false },
  { name: "phone", width: 390, height: 844, touch: true },
];

async function main() {
  await fs.mkdir(output, { recursive: true });
  const api = await request.newContext({ baseURL, extraHTTPHeaders: { Authorization: `Bearer ${masterKey}` } });
  await expect.poll(async () => {
    try { return (await api.get("/health/liveliness", { timeout: 2000 })).status(); }
    catch { return 0; }
  }, { timeout: 90000, intervals: [1000, 2000] }).toBe(200);

  const getFallbacks = async () => {
    const response = await api.get("/get/config/callbacks");
    assert(response.ok(), `Configuration read returned ${response.status()}`);
    return (await response.json()).router_settings.fallbacks;
  };
  const assertFallbacks = async expected => {
    await expect.poll(getFallbacks, { timeout: 30000, intervals: [500, 1000] }).toEqual(expected);
  };
  const resetFallbacks = async () => {
    const response = await api.post("/config/update", { data: { router_settings: { fallbacks: initialFallbacks } } });
    assert(response.ok(), `Configuration seed returned ${response.status()}`);
    await assertFallbacks(initialFallbacks);
  };

  const fixturePath = path.join(root, "model-fixture.private.json");
  try {
    await fs.access(fixturePath);
  } catch (error) {
    if (error.code !== "ENOENT") throw error;
    const response = await api.post("/model/new", { data: {
      model_name: sibling,
      litellm_params: { model: "openai/fake-gpt-4", api_base: "http://127.0.0.1:51475/v1", api_key: "fake-key" },
      model_info: {},
    } });
    assert(response.ok(), `Model fixture creation returned ${response.status()}`);
    const created = await response.json();
    const modelId = created.model_id ?? created.model_info?.id;
    assert(modelId, `Missing model ID, response keys ${Object.keys(created).join(", ")}`);
    await fs.writeFile(fixturePath, JSON.stringify({ modelId, modelName: sibling }, null, 2), { flag: "wx" });
  }
  await expect.poll(async () => {
    const response = await api.get("/model_group/info");
    return response.ok() && JSON.stringify(await response.json()).includes(sibling);
  }, { timeout: 60000, intervals: [1000, 2000] }).toBe(true);

  const browser = await chromium.launch({ headless: true });
  const reports = [];
  try {
    for (const viewport of viewports) {
      await resetFallbacks();
      const context = await browser.newContext({
        baseURL, viewport: { width: viewport.width, height: viewport.height },
        hasTouch: viewport.touch, isMobile: viewport.touch,
        recordVideo: { dir: path.join(output, "videos"), size: { width: viewport.width, height: viewport.height } },
      });
      const page = await context.newPage();
      const report = { build, viewport, url: `${baseURL}/ui/router-settings/`, pageErrors: [], httpErrors: [], steps: [], screenshots: {} };
      page.on("pageerror", error => report.pageErrors.push(error.message));
      page.on("response", response => {
        if (response.status() >= 400) report.httpErrors.push({ url: new URL(response.url()).pathname, status: response.status() });
      });
      const shoot = async (name, target) => {
        await expect(page.locator("[data-sonner-toast]")).toHaveCount(0, { timeout: 10000 });
        if (target) await target.scrollIntoViewIfNeeded();
        report.screenshots[name] = { path: `${viewport.name}-${name}.png`, box: target ? await target.boundingBox() : null };
        await page.screenshot({ path: path.join(output, `${viewport.name}-${name}.png`), scale: "css" });
      };
      const row = model => page.locator("table tbody tr").filter({
        has: page.locator("td:first-child").getByText(model, { exact: true }),
      });
      const click = async locator => viewport.touch ? locator.tap() : locator.click();
      const modalSettled = async modal => {
        await expect(modal).toBeVisible();
        await expect.poll(() => modal.evaluate(el => getComputedStyle(el).opacity)).toBe("1");
      };
      const preserve = async expected => {
        await assertFallbacks(expected);
        assert.deepEqual((await getFallbacks())[0][primary], [override, sibling]);
      };

      try {
        await page.goto("/ui/login");
        await page.getByPlaceholder("Enter your username").fill("admin");
        await page.getByPlaceholder("Enter your password").fill(masterKey);
        await click(page.getByRole("button", { name: "Login", exact: true }));
        await expect(page.getByRole("button", { name: "Launch Aria Agent" })).toBeVisible({ timeout: 30000 });
        await page.goto("/ui/router-settings/");
        if (build === "baseline") {
          await expect.poll(() => report.pageErrors.some(error => /Minified React error #31|Objects are not valid as a React child/.test(error)), { timeout: 20000 }).toBe(true);
          await expect(page.getByText("This page couldn’t load", { exact: true })).toBeVisible();
          await shoot("crash", page.getByText("This page couldn’t load", { exact: true }));
          report.steps.push("Opening Router Settings crashes before the Fallbacks tab can be used");
          await preserve(initialFallbacks);
        } else {
          await expect(page.getByRole("tab", { name: "Loadbalancing", exact: true })).toBeVisible({ timeout: 30000 });
          await expect(page.getByRole("tab", { name: "Loadbalancing", exact: true })).toHaveAttribute("aria-selected", "true");
          await shoot("loadbalancing", page.getByRole("tab", { name: "Loadbalancing", exact: true }));
          await click(page.getByRole("tab", { name: "Fallbacks", exact: true }));
          const objectRow = row(primary);
          await expect(objectRow).toHaveCount(1);
          await expect(objectRow.getByText(backup, { exact: true })).toBeVisible();
          await expect(objectRow.getByText(sibling, { exact: true })).toBeVisible();
          await expect(objectRow.getByText("Overrides", { exact: true })).toBeVisible();
          for (const [model, labels] of [[primary, [backup, sibling, "Overrides"]], [sibling, [backup]]]) {
            const targetCell = row(model).getByRole("cell").nth(1);
            const cellBox = await targetCell.boundingBox();
            assert(cellBox);
            for (const label of labels) {
              const labelBox = await targetCell.getByText(label, { exact: true }).boundingBox();
              assert(labelBox);
              assert(labelBox.x >= cellBox.x && labelBox.x + labelBox.width <= cellBox.x + cellBox.width + 1,
                `Fallback label ${label} overlaps another column at ${viewport.width}px`);
            }
          }
          await expect(objectRow.getByTestId("edit-fallback-button")).toHaveAttribute("aria-disabled", "true");
          assert(!(await page.locator("body").innerText()).includes(override.api_key));
          assert(!(await page.locator("body").innerText()).includes(override.extra_headers["X-QA-Sentinel"]));
          await shoot("fallbacks", objectRow.getByRole("cell").nth(1));
          const objectEdit = objectRow.getByTestId("edit-fallback-button");
          await objectEdit.focus();
          await objectEdit.press("Enter");
          await expect(page.getByRole("dialog", { name: "Configure Model Fallbacks" })).toHaveCount(0);
          if (!viewport.touch) {
            await objectEdit.hover();
            await expect(page.locator('[data-slot="tooltip-content"]')).toContainText("Edit parameter overrides through the API or config file");
            await shoot("override-hint", objectEdit);
            await page.mouse.move(0, 0);
          }
          report.steps.push("Loadbalancing and mixed fallback chains render without column overlap, override values stay hidden, object editing is disabled");

          await click(row(sibling).getByTestId("edit-fallback-button"));
          const editModal = page.getByRole("dialog", { name: "Configure Model Fallbacks" });
          await modalSettled(editModal);
          await expect(editModal.getByRole("list", { name: "Fallback chain" })).toContainText(backup);
          await shoot("edit-sibling", editModal);
          await click(editModal.getByRole("button", { name: "Save Changes", exact: true }));
          await expect(editModal).not.toBeVisible();
          await preserve(initialFallbacks);
          report.steps.push("Saving the ordinary sibling chain preserves the complete override object");

          await click(row(sibling).getByTestId("delete-fallback-button"));
          const deleteModal = page.getByRole("dialog", { name: "Delete Fallback?" });
          await modalSettled(deleteModal);
          await click(deleteModal.getByRole("button", { name: "Delete", exact: true }));
          await expect(deleteModal).not.toBeVisible();
          await expect(row(sibling)).toHaveCount(0);
          await preserve([initialFallbacks[0]]);
          await shoot("sibling-deleted", objectRow);
          report.steps.push("Deleting the sibling preserves the complete override object");

          await click(page.getByRole("button", { name: /Add Fallbacks/ }));
          const addModal = page.getByRole("dialog", { name: "Configure Model Fallbacks" });
          await modalSettled(addModal);
          await click(addModal.getByRole("combobox", { name: /Primary Model/ }));
          await page.keyboard.type(sibling);
          await click(page.getByRole("option", { name: sibling, exact: true }));
          await expect(addModal.getByRole("tab", { name: sibling })).toBeVisible();
          await click(addModal.getByRole("combobox", { name: /Select fallback models/ }));
          await page.keyboard.type(backup);
          await click(page.getByRole("option", { name: backup, exact: true }));
          await expect(addModal.getByText("(1/10 used)")).toBeVisible();
          const fallbackPicker = addModal.getByRole("combobox", { name: /Select fallback models/ });
          if (await fallbackPicker.getAttribute("aria-expanded") === "true") await page.keyboard.press("Escape");
          await expect(fallbackPicker).toHaveAttribute("aria-expanded", "false");
          await expect(page.getByRole("listbox")).toHaveCount(0);
          await shoot("add-sibling", addModal);
          await click(addModal.getByRole("button", { name: "Save All Configurations", exact: true }));
          await expect(addModal).not.toBeVisible();
          await expect(row(sibling)).toHaveCount(1);
          await preserve(initialFallbacks);
          report.steps.push("Adding the sibling back preserves the complete override object");

          await page.reload();
          await click(page.getByRole("tab", { name: "Fallbacks", exact: true }));
          await expect(row(primary).getByText("Overrides", { exact: true })).toBeVisible();
          await expect(row(sibling)).toHaveCount(1);
          await preserve(initialFallbacks);
          await shoot("persisted", row(primary));
          await page.waitForTimeout(1500);
          report.steps.push("Reloading shows both persisted chains and unchanged override parameters");
          const dimensions = await page.evaluate(() => ({ width: innerWidth, scrollWidth: document.documentElement.scrollWidth }));
          assert(dimensions.scrollWidth <= dimensions.width + 1, JSON.stringify(dimensions));
          report.dimensions = dimensions;
          assert.deepEqual(report.pageErrors, []);
          assert.deepEqual(report.httpErrors.filter(error => error.status >= 500), []);
        }
        report.result = "pass";
      } catch (error) {
        report.result = "fail";
        report.failure = String(error.stack ?? error);
        await shoot("failure").catch(() => {});
        await fs.writeFile(path.join(output, `${viewport.name}-failure-body.txt`), await page.locator("body").innerText()).catch(() => {});
        throw error;
      } finally {
        const video = page.video();
        await context.close();
        await video.saveAs(path.join(output, `${viewport.name}.webm`));
        reports.push(report);
        await fs.writeFile(path.join(output, "report.json"), JSON.stringify(reports, null, 2));
        console.log(JSON.stringify({ build, viewport: viewport.name, result: report.result, steps: report.steps, pageErrors: report.pageErrors, httpErrors: report.httpErrors }));
      }
    }
  } finally {
    await browser.close();
    await api.dispose();
  }
}
main().catch(error => { console.error(error); process.exitCode = 1; });
