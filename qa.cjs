const fs = require("node:fs/promises");
const path = require("node:path");
const { randomUUID } = require("node:crypto");
const assert = require("node:assert/strict");
const { chromium, expect, request } = require("/repo/tests/e2e/ui/node_modules/@playwright/test");
const revision = process.argv[2];
assert(["baseline", "fixed"].includes(revision));
const root = __dirname;
const output = path.join(root, "output", "playwright", `visual-${revision}-${Date.now()}`);
const baseURL = "http://127.0.0.1:41475";
const masterKey = process.env.LITELLM_MASTER_KEY;
assert(masterKey);
const visible = locator => locator.filter({ visible: true }).first();
const normalized = text => text.replace(/\s+/g, " ").trim();
const rows = async kind => {
  try { return (await fs.readFile(path.join(root, `${kind}-${revision}.jsonl`), "utf8")).trim().split("\n").filter(Boolean).map(JSON.parse); }
  catch (error) { if (error.code === "ENOENT") return []; throw error; }
};
const bounded = async (promise, label) => {
  let timer;
  try {
    return await Promise.race([promise, new Promise((_, reject) => {
      timer = setTimeout(() => reject(new Error(`Timed out reading ${label}`)), 30000);
    })]);
  } finally { clearTimeout(timer); }
};

async function main() {
  await fs.mkdir(output, { recursive: true });
  const source = JSON.parse(await fs.readFile(path.join(root, `proxy-source-${revision}.json`), "utf8"));
  const expected = JSON.parse(await fs.readFile(path.join(root, revision === "baseline" ? "runtime.json" : "product.json"), "utf8"))[revision === "baseline" ? "base" : "head"];
  assert.equal(source.sha, expected);
  assert.equal(await fs.realpath(`/proc/${source.pid}/cwd`), source.source);
  assert.equal(Number(await fs.readFile(path.join(root, "proxy.pid"), "utf8")), source.pid);
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
      const beforeErrors = (await rows("callback-errors")).length;
      const beforeCallbacks = (await rows("callback-metadata")).length;
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
        const model = "qa-cost-35459";
        const prompt = "Reply with only: Routing works. Verification reference " + randomUUID().slice(0, 12);
        await activate(visible(page.getByRole("button", { name: "New chat", exact: true })));
        await activate(modelPicker);
        await visible(page.getByPlaceholder("Search models")).fill(model);
        await activate(visible(page.getByRole("option", { name: model, exact: true })));
        await expect(modelPicker).toContainText(model);
        const composer = visible(page.getByRole("group").filter({ has: page.getByRole("textbox", { name: "Message", exact: true }) }));
        await composer.getByRole("textbox", { name: "Message", exact: true }).fill(prompt);
        const [response] = await Promise.all([
          page.waitForResponse(response => /\/(?:v1\/)?chat\/completions$/.test(new URL(response.url()).pathname) && response.request().method() === "POST" && response.request().postDataJSON().model === model, { timeout: 120000 }),
          viewport.name === "phone" ? composer.getByRole("textbox", { name: "Message", exact: true }).press("Enter") : activate(composer.getByRole("button", { name: "Send message", exact: true })),
        ]);
        await bounded(response.finished(), "the completed streaming response");
        const body = await bounded(response.text(), "the streaming response body");
        assert.equal(response.status(), 200);
        assert.equal(response.headers()["x-litellm-model-id"], model + "-deployment");
        const events = body.split("\n").filter(line => line.startsWith("data: ") && !line.includes("[DONE]")).map(line => JSON.parse(line.slice(6)));
        assert(events.length > 0 && events.every(event => !event.error));
        const content = events.map(event => event.choices?.[0]?.delta?.content ?? "").join("");
        assert(content.trim().length > 0);
        const conversation = visible(page.getByLabel("Conversation", { exact: true }));
        await expect.poll(async () => normalized(await conversation.innerText()), { timeout: 15000 }).toContain(normalized(content));
        await expect(conversation.getByText("The request failed", { exact: true })).toHaveCount(0);
        await expect(page.getByText(/^Chat history cleared\.?$/).last()).toBeHidden({ timeout: 15000 });
        await page.mouse.move(1, 1);
        const chat = { kind: "routed-chat", status: response.status(), requestBody: response.request().postDataJSON(), responseBody: body, modelId: response.headers()["x-litellm-model-id"], generatedContent: content, visibleResult: normalized(await conversation.innerText()), conversationBox: await conversation.boundingBox(), screenshot: `${viewport.name}-routed-chat.png`, submitMethod: viewport.name === "phone" ? "Enter in the message field" : "Send message button" };
        result.cases.push(chat);
        await page.screenshot({ path: path.join(output, chat.screenshot), scale: "css" });
        await page.waitForTimeout(1000);

        await page.goto("/ui/?page=mcp-servers");
        await visible(page.getByPlaceholder("Search by name, alias, URL, or ID")).fill("math35459");
        await activate(visible(page.getByTestId("mcp-servers-grid").getByRole("button", { name: /math35459/ })));
        await activate(visible(page.getByRole("tab", { name: "MCP Tools", exact: true })));
        if (viewport.name === "phone") {
          const portraitTool = page.getByRole("heading", { name: /^(?:math35459-)?add$/, includeHidden: true }).first();
          await expect(portraitTool).toBeAttached({ timeout: 30000 });
          result.mcpPortraitObservation = { toolBox: await portraitTool.boundingBox(), screenshot: "phone-mcp-portrait-layout.png" };
          await page.screenshot({ path: path.join(output, result.mcpPortraitObservation.screenshot), fullPage: true, scale: "css" });
          await page.setViewportSize({ width: 844, height: 390 });
          result.mcpViewport = { width: 844, height: 390, orientation: "landscape" };
        }
        const tool = visible(page.getByRole("heading", { name: /^(?:math35459-)?add$/ }));
        await expect(tool).toBeVisible({ timeout: 30000 });
        await activate(tool);
        await visible(page.getByPlaceholder("Enter a", { exact: true })).fill("17");
        await visible(page.getByPlaceholder("Enter b", { exact: true })).fill("25");
        const [mcpResponse] = await Promise.all([
          page.waitForResponse(response => new URL(response.url()).pathname === "/mcp-rest/tools/call" && response.request().method() === "POST", { timeout: 60000 }),
          activate(visible(page.getByRole("button", { name: "Call Tool", exact: true }))),
        ]);
        const mcpBody = await bounded(mcpResponse.json(), "the tool response");
        assert.equal(mcpResponse.status(), 200);
        assert(JSON.stringify(mcpBody).includes('"text":"42"'), JSON.stringify(mcpBody));
        await expect(visible(page.getByText("Tool executed successfully", { exact: true }))).toBeVisible();
        await expect(visible(page.getByText("42", { exact: true }))).toBeVisible();
        await page.mouse.move(1, 1);
        const mcp = { kind: "mcp-tool", status: mcpResponse.status(), requestBody: mcpResponse.request().postDataJSON(), responseBody: mcpBody, visibleResult: normalized(await page.locator("body").innerText()), screenshot: `${viewport.name}-mcp-tool.png` };
        result.cases.push(mcp);
        await page.screenshot({ path: path.join(output, mcp.screenshot), fullPage: viewport.name === "phone", scale: "css" });
        await page.waitForTimeout(1000);
        result.callbacks = (await rows("callback-metadata")).slice(beforeCallbacks);
        result.callbackErrors = (await rows("callback-errors")).slice(beforeErrors);
        assert(result.callbacks.some(item => item.deployment_id === model + "-deployment"));
        if (revision === "fixed") assert.deepEqual(result.callbackErrors, []);
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
    console.log(JSON.stringify(report.viewports.map(item => ({ viewport: item.viewport, result: item.result, cases: item.cases.map(c => ({ kind: c.kind, status: c.status })), callbackErrors: item.callbackErrors.length, pageErrors: item.pageErrors }))));
  } finally { await browser.close(); }
}

main().catch(error => { console.error(error.stack || String(error)); process.exitCode = 1; });
