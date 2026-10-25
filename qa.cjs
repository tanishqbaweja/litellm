const fs = require("node:fs/promises");
const path = require("node:path");
const assert = require("node:assert/strict");
const { execFileSync, spawn } = require("node:child_process");
const { chromium, expect, request } = require("/repo/tests/e2e/ui/node_modules/@playwright/test");

async function main() {
  const build = process.argv[2];
  assert(["baseline", "fixed"].includes(build));
  const sourceSha = process.env.QA_SOURCE_SHA;
  assert(sourceSha && /^[a-f0-9]{40}$/.test(sourceSha));
  const output = path.join(__dirname, `visual-${build}`);
  await fs.mkdir(output, { recursive: true });
  const baseURL = "http://127.0.0.1:41475";
  const api = await request.newContext({ baseURL, extraHTTPHeaders: { Authorization: `Bearer ${process.env.LITELLM_MASTER_KEY}` } });
  await expect.poll(async () => {
    try { return (await api.get("/health/liveliness", { timeout: 2000 })).status(); } catch { return 0; }
  }, { timeout: 60000 }).toBe(200);
  const original = await (await api.get("/get/ui_theme_settings")).json();
  const reports = [];
  try {
    for (const viewport of [{ name: "desktop", width: 1440, height: 900, touch: false }, { name: "phone", width: 390, height: 844, touch: true }]) {
      const browser = await chromium.launch({ headless: false, args: ["--no-sandbox", `--window-size=${viewport.touch ? 500 : 1440},1000`, "--window-position=0,0"] });
      const context = await browser.newContext({ baseURL, viewport: { width: viewport.width, height: viewport.height }, isMobile: viewport.touch, hasTouch: viewport.touch });
      const page = await context.newPage();
      const report = { build, sourceSha, viewport, pageErrors: [], consoleErrors: [], httpErrors: [], screenshots: {}, steps: [] };
      page.on("pageerror", error => report.pageErrors.push(error.message));
      page.on("console", message => { if (message.type() === "error") report.consoleErrors.push(message.text()); });
      page.on("response", response => { if (response.status() >= 400) report.httpErrors.push({ path: new URL(response.url()).pathname, status: response.status() }); });
      const videoPath = path.join(output, `${viewport.name}.webm`);
      const video = spawn("ffmpeg", ["-y", "-loglevel", "error", "-f", "x11grab", "-video_size", "1600x1100", "-framerate", "10", "-i", `${process.env.DISPLAY}.0`, "-c:v", "libvpx-vp9", "-deadline", "realtime", "-cpu-used", "6", "-b:v", "0", "-crf", "40", videoPath]);
      let videoErrors = "";
      video.stderr.on("data", chunk => { videoErrors += chunk.toString(); });
      const videoClosed = new Promise(resolve => video.on("close", resolve));
      const click = async locator => viewport.touch ? locator.tap() : locator.click();
      const input = page.getByLabel("Custom Favicon URL", { exact: true });
      const iconInfo = async () => {
        const links = await page.locator('link[rel="icon"]').evaluateAll(icons => icons.map(icon => ({ href: icon.href, type: icon.type, sizes: String(icon.sizes) })));
        const resolved = [];
        for (const icon of links) {
          const response = await api.get(icon.href);
          resolved.push({ ...icon, status: response.status(), finalURL: response.url(), contentType: response.headers()["content-type"] });
        }
        assert(resolved.length > 0);
        return resolved;
      };
      const capture = async name => {
        await expect(page.locator("[data-sonner-toast]")).toHaveCount(0, { timeout: 15000 });
        await page.bringToFront();
        await page.waitForTimeout(1500);
        const cdp = await context.newCDPSession(page);
        const { bounds } = await cdp.send("Browser.getWindowForTarget");
        await cdp.detach();
        const region = `${bounds.left},${bounds.top},${bounds.width},${bounds.height}`;
        const temporary = execFileSync("/opt/litellm-venv/bin/python", [path.join(__dirname, "take_screenshot.py"), "--mode", "temp", "--region", region], { encoding: "utf8" }).trim();
        const windowFile = `${viewport.name}-${name}-window.png`;
        const pageFile = `${viewport.name}-${name}-page.png`;
        await fs.copyFile(temporary, path.join(output, windowFile));
        await page.screenshot({ path: path.join(output, pageFile), scale: "css" });
        report.screenshots[name] = { window: windowFile, page: pageFile, bounds, url: page.url(), icons: await iconInfo() };
      };
      const save = async value => {
        await input.fill(value);
        const response = page.waitForResponse(response => new URL(response.url()).pathname === "/update/ui_theme_settings" && response.request().method() === "PATCH");
        await click(page.getByRole("button", { name: "Save Changes", exact: true }));
        assert.equal((await response).status(), 200);
        assert.equal((await (await api.get("/get/ui_theme_settings")).json()).values.favicon_url, value);
      };
      const home = async () => {
        if (viewport.touch) await click(page.getByRole("button", { name: "Open navigation", exact: true }));
        await click(page.getByRole("link", { name: "Home", exact: true }));
        await expect(page.getByRole("heading", { name: "Home", exact: true })).toBeVisible();
        await expect(page).toHaveURL(/\/ui\/home\/?$/);
      };
      try {
        assert.equal((await api.patch("/update/ui_theme_settings", { data: { ...original.values, favicon_url: null } })).status(), 200);
        await page.goto("/ui/login");
        await page.getByPlaceholder("Enter your username").fill("admin");
        await page.getByPlaceholder("Enter your password").fill(process.env.LITELLM_MASTER_KEY);
        await click(page.getByRole("button", { name: "Login", exact: true }));
        await expect(page.getByRole("button", { name: "Launch Aria Agent" })).toBeVisible({ timeout: 30000 });
        await page.goto("/ui/ui-theme/");
        await expect(input).toHaveValue("");
        await capture("default");

        const firstURL = "http://127.0.0.1:51477/favicon.png";
        await save(firstURL);
        await capture("custom-saved");
        await page.reload();
        await expect(input).toHaveValue(firstURL);
        await capture("custom-reloaded");
        await home();
        await capture("custom-navigation");
        const firstIcons = report.screenshots["custom-navigation"].icons;
        if (build === "baseline") assert(firstIcons.some(icon => icon.status === 404));
        else assert(firstIcons.every(icon => icon.href === firstURL && icon.status === 200 && icon.finalURL === firstURL));
        report.steps.push(build === "baseline" ? "Client navigation restores a broken competing icon URL" : "The configured icon stays usable after client navigation");

        await page.goto("/ui/ui-theme/");
        await expect(input).toHaveValue(firstURL);
        const secondURL = "http://127.0.0.1:51477/favicon-alt.png";
        await save(secondURL);
        await capture("updated-saved");
        await home();
        await capture("updated-navigation");
        const secondIcons = report.screenshots["updated-navigation"].icons;
        if (build === "baseline") assert(secondIcons.some(icon => icon.status === 404));
        else assert(secondIcons.every(icon => icon.href === secondURL && icon.status === 200 && icon.finalURL === secondURL));
        report.steps.push("Saving a second URL persists the new favicon setting");

        await page.goto("/ui/ui-theme/");
        await expect(input).toHaveValue(secondURL);
        const reset = page.waitForResponse(response => new URL(response.url()).pathname === "/update/ui_theme_settings" && response.request().method() === "PATCH");
        await click(page.getByRole("button", { name: "Reset to Default", exact: true }));
        assert.equal((await reset).status(), 200);
        await expect(input).toHaveValue("");
        await page.reload();
        await expect(input).toHaveValue("");
        await capture("default-restored");
        const defaultIcons = report.screenshots["default-restored"].icons;
        if (build === "fixed") assert(defaultIcons.every(icon => icon.status === 200 && icon.contentType.startsWith("image/")));
        assert.equal((await api.get("/ui/favicon.ico")).status(), 200);
        report.steps.push("Reset and reload restore the default icon, and the default asset remains exported");
        assert.deepEqual(report.pageErrors, []);
        assert.deepEqual(report.httpErrors.filter(error => error.status >= 500), []);
        report.result = "pass";
      } catch (error) {
        report.result = "fail";
        report.error = String(error.stack || error);
        await page.screenshot({ path: path.join(output, `${viewport.name}-failure.png`) });
        throw error;
      } finally {
        video.kill("SIGINT");
        report.videoExit = await videoClosed;
        report.video = `${viewport.name}.webm`;
        if (videoErrors.trim()) report.videoMessages = videoErrors;
        report.restored = (await api.patch("/update/ui_theme_settings", { data: original.values })).status();
        reports.push(report);
        await fs.writeFile(path.join(output, "report.json"), JSON.stringify(reports, null, 2));
        await browser.close();
      }
    }
  } finally {
    await api.dispose();
  }
  console.log(JSON.stringify(reports.map(({ viewport, result, steps, restored }) => ({ viewport, result, steps, restored }))));
}

main().catch(error => { console.error(error); process.exitCode = 1; });
