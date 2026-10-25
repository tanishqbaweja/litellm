const fs = require("node:fs/promises");
const path = require("node:path");
const { randomUUID } = require("node:crypto");
const assert = require("node:assert/strict");
const { chromium, expect, request } = require("/repo/tests/e2e/ui/node_modules/@playwright/test");
const revision = process.argv[2];
assert(["baseline", "fixed"].includes(revision));
const root = __dirname;
const output = path.join(root, `visual-${revision}-${Date.now()}`);
const baseURL = "http://127.0.0.1:41475";
const masterKey = process.env.LITELLM_MASTER_KEY;
assert(masterKey);
const visible = locator => locator.filter({ visible: true }).first();
const normalized = text => text.replace(/\s+/g, " ").trim();

async function main() {
  await fs.mkdir(output, { recursive: true });
  const source = JSON.parse(await fs.readFile(path.join(root, `proxy-source-${revision}.json`), "utf8"));
  const expected = JSON.parse(await fs.readFile(path.join(root, revision === "baseline" ? "runtime.json" : "product.json"), "utf8"))[revision === "baseline" ? "base" : "head"];
  assert.equal(source.sha, expected);
  const report = { revision, sourceSha: source.sha, output, startedAt: new Date().toISOString(), viewports: [] };
  const api = await request.newContext({ baseURL, extraHTTPHeaders: { Authorization: `Bearer ${masterKey}` } });
  await expect.poll(async () => {
    try { return (await api.get("/health/readiness", { timeout: 2000 })).status(); }
    catch { return 0; }
  }, { timeout: 60000, intervals: [1000, 2000] }).toBe(200);
  await api.dispose();
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
      const activate = locator => viewport.name === "phone" ? locator.tap() : locator.click();
      const result = { viewport, cases: [], pageErrors: [], consoleErrors: [], failedResponses: [] };
      report.viewports.push(result);
      page.on("pageerror", error => result.pageErrors.push(error.message));
      page.on("console", event => { if (event.type() === "error") result.consoleErrors.push(event.text()); });
      page.on("response", response => {
        if (response.status() >= 400) result.failedResponses.push({ path: new URL(response.url()).pathname, status: response.status() });
      });
      try {
        await page.goto("/ui/login");
        await page.getByPlaceholder("Enter your username").fill("admin");
        const password = page.getByPlaceholder("Enter your password");
        await expect(password).toHaveAttribute("type", "password");
        await password.fill(masterKey);
        await activate(page.getByRole("button", { name: "Login", exact: true }));
        await expect(page.getByRole("button", { name: "Launch Aria Agent" })).toBeVisible({ timeout: 30000 });
        await page.goto("/ui/?page=llm-playground");
        const dismiss = page.getByText("Don't ask me again");
        if (await dismiss.isVisible()) await activate(dismiss);
        const modelPicker = visible(page.getByRole("combobox", { name: "Model", exact: true }));
        await expect(modelPicker).toBeVisible({ timeout: 30000 });
        const hint = page.getByRole("button", { name: "Dismiss search hint" });
        if (await hint.isVisible()) await activate(hint);
        const prompt = "Reply with only: Cache works. Verification reference " + randomUUID().slice(0, 12);
        const model = "qa-cache-34681";
        for (const phase of ["first", "repeat"]) {
          await activate(visible(page.getByRole("button", { name: "New chat", exact: true })));
          await activate(modelPicker);
          await visible(page.getByPlaceholder("Search models")).fill(model);
          await activate(visible(page.getByRole("option", { name: model, exact: true })));
          await expect(modelPicker).toContainText(model);
          const composer = visible(page.getByRole("group").filter({ has: page.getByRole("textbox", { name: "Message", exact: true }) }));
          await composer.getByRole("textbox", { name: "Message", exact: true }).fill(prompt);
          const [response] = await Promise.all([
            page.waitForResponse(response => /\/(?:v1\/)?chat\/completions$/.test(new URL(response.url()).pathname) && response.request().method() === "POST", { timeout: 120000 }),
            viewport.name === "phone"
              ? composer.getByRole("textbox", { name: "Message", exact: true }).press("Enter")
              : activate(composer.getByRole("button", { name: "Send message", exact: true })),
          ]);
          await response.finished();
          const body = await response.text();
          const conversation = visible(page.getByLabel("Conversation", { exact: true }));
          await expect(composer.getByRole("button", { name: "Send message", exact: true })).toBeVisible({ timeout: 120000 });
          const item = { model, phase, submitMethod: viewport.name === "phone" ? "Enter in the message field" : "Send message button", status: response.status(), url: response.url(), requestBody: response.request().postDataJSON(), responseBody: body, screenshot: `${viewport.name}-${phase}.png` };
          result.cases.push(item);
          assert.equal(response.status(), 200);
          const events = body.split("\n").filter(line => line.startsWith("data: ") && !line.includes("[DONE]")).map(line => JSON.parse(line.slice(6)));
          assert(events.length > 0 && events.every(event => !event.error));
          const content = events.map(event => event.choices?.[0]?.delta?.content ?? "").join("");
          assert(content.trim().length > 0);
          item.generatedContent = content;
          item.usage = events.findLast(event => event.usage)?.usage;
          item.headers = Object.fromEntries(Object.entries(response.headers()).filter(([name]) => ["x-litellm-cache-key", "x-litellm-call-id", "x-litellm-response-cost"].includes(name)));
          await expect.poll(async () => normalized(await conversation.innerText()), { timeout: 15000 }).toContain(normalized(content));
          await expect(conversation.getByText("The request failed", { exact: true })).toHaveCount(0);
          item.visibleResult = normalized(await conversation.innerText());
          await expect(page.getByText(/^Chat history cleared\.?$/).last()).toBeHidden({ timeout: 15000 });
          await page.mouse.move(1, 1);
          item.conversationBox = await conversation.boundingBox();
          item.modelBox = await modelPicker.boundingBox();
          await page.screenshot({ path: path.join(output, item.screenshot), scale: "css" });
          await page.waitForTimeout(1000);
        }
        assert.equal(result.cases[0].generatedContent, result.cases[1].generatedContent);
        assert.deepEqual(result.pageErrors, []);
        assert.deepEqual(result.failedResponses.filter(value => value.status >= 500), []);
        result.result = "pass";
      } catch (error) {
        result.result = "fail";
        result.error = error.stack || String(error);
        await page.screenshot({ path: path.join(output, `${viewport.name}-failure.png`), fullPage: true });
        await fs.writeFile(path.join(output, `${viewport.name}-failure.txt`), await page.locator("body").innerText());
        throw error;
      } finally {
        await context.close();
        result.video = path.relative(output, await video.path());
        await fs.writeFile(path.join(root, `ui-report-${revision}.json`), JSON.stringify(report, null, 2));
      }
    }
    report.completedAt = new Date().toISOString();
    await fs.writeFile(path.join(root, `ui-report-${revision}.json`), JSON.stringify(report, null, 2));
    console.log(JSON.stringify(report.viewports.map(item => ({ viewport: item.viewport, result: item.result, cases: item.cases.map(c => ({ phase: c.phase, status: c.status, content: c.generatedContent })), pageErrors: item.pageErrors }))));
  } finally { await browser.close(); }
}

main().catch(error => { console.error(error.stack || String(error)); process.exitCode = 1; });
