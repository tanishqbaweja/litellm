const fs = require("node:fs/promises");
const path = require("node:path");
const assert = require("node:assert/strict");
const { randomUUID } = require("node:crypto");
const repoRoot = process.env.LITELLM_REPO ?? "/repo";
const { chromium, expect, request } = require(path.join(repoRoot, "tests/e2e/ui/node_modules/@playwright/test"));

const [build, headerMode] = process.argv.slice(2);
assert(["baseline", "fixed"].includes(build));
assert(["custom", "default"].includes(headerMode));
const sourceSha = build === "baseline" ? "dddbaa803d6e9fcc862ea7a5412f771cb1ae040e" : process.env.QA_SOURCE_SHA;
assert(sourceSha);
const baseURL = process.env.LITELLM_BASE_URL ?? "http://127.0.0.1:41475";
const headerName = headerMode === "custom" ? "x-litellm-api-key" : "Authorization";
const masterKey = process.env.LITELLM_MASTER_KEY;
assert(masterKey);
const output = path.join(__dirname, `visual-${build}-${headerMode}`);
const successExpected = build === "fixed" || headerMode === "default";
const runId = Date.now().toString(36);
const viewports = [{ name: "desktop", width: 1440, height: 900, touch: false }, { name: "phone", width: 390, height: 844, touch: true }];

async function main() {
  await fs.mkdir(output, { recursive: true });
  const api = await request.newContext({ baseURL, extraHTTPHeaders: { [headerName]: `Bearer ${masterKey}` } });
  await expect.poll(async () => {
    try { return (await api.get("/health/liveliness", { timeout: 2000 })).status(); }
    catch { return 0; }
  }, { timeout: 90000, intervals: [1000, 2000] }).toBe(200);
  const post = async (route, data, headers) => {
    const response = await api.post(route, { data, ...(headers ? { headers } : {}) });
    assert.equal(response.status(), 200, `${route} fixture request returned ${response.status()}`);
    return response.json();
  };
  const browser = await chromium.launch({ headless: false });
  const reports = [];
  try {
    for (const viewport of viewports) {
      for (const variant of ["signup", "reset_password"]) {
        const name = `${viewport.name}-${variant}`;
        const userEmail = `qa-34659-${name}@example.test`;
        const user = await post("/user/new", { user_email: userEmail, user_role: "internal_user", auto_create_key: false, send_invite_email: false });
        const report = { name, sourceSha, headerMode, viewport, runId, outcome: null, claim: null, keyLists: [], screenshots: {}, pageErrors: [], consoleErrors: [], httpErrors: [], cleanup: null };
        reports.push(report);
        const context = await browser.newContext({
          baseURL, viewport: { width: viewport.width, height: viewport.height },
          hasTouch: viewport.touch, isMobile: viewport.touch,
          recordVideo: { dir: path.join(output, "videos"), size: { width: viewport.width, height: viewport.height } },
        });
        const page = await context.newPage();
        page.on("pageerror", error => report.pageErrors.push(error.message));
        page.on("console", message => { if (message.type() === "error") report.consoleErrors.push(message.text()); });
        page.on("response", response => {
          if (response.status() >= 400) report.httpErrors.push({ path: new URL(response.url()).pathname, status: response.status() });
          if (new URL(response.url()).pathname === "/key/list") report.keyLists.push({ context: "after-claim", status: response.status() });
        });
        const shoot = async (stage, capturedPage = page) => {
          const filename = `${name}-${stage}.png`;
          await capturedPage.screenshot({ path: path.join(output, filename), fullPage: true });
          report.screenshots[stage] = filename;
          if (stage === "result") {
            const target = successExpected
              ? capturedPage.getByRole("main").getByRole("heading", { name: "Virtual Keys", exact: true })
              : capturedPage.getByText("Missing onboarding session for invitation link.", { exact: false }).first();
            report.highlight = await target.boundingBox();
          }
          await capturedPage.waitForTimeout(1000);
        };
        const openKeys = async targetPage => {
          const virtualKeys = targetPage.getByRole("complementary").getByRole("link", { name: "Virtual Keys", exact: true });
          if (viewport.touch && !(await virtualKeys.isVisible())) {
            await targetPage.getByRole("button", { name: "Open navigation", exact: true }).tap();
          }
          if (viewport.touch) await virtualKeys.tap(); else await virtualKeys.click();
          await expect(targetPage.getByRole("main").getByRole("heading", { name: "Virtual Keys", exact: true })).toBeVisible();
          await expect(targetPage.getByText("No keys found", { exact: true })).toBeVisible({ timeout: 15000 });
        };
        try {
          if (variant === "reset_password") {
            const initialInvite = await post("/invitation/new", { user_id: user.user_id });
            const onboarding = await api.get("/onboarding/get_token", { params: { invite_link: initialInvite.id } });
            assert(onboarding.ok());
            const payload = JSON.parse(Buffer.from((await onboarding.json()).token.split(".")[1], "base64url").toString());
            await post("/onboarding/claim_token", {
              invitation_link: initialInvite.id, user_id: user.user_id, password: `Qa!${randomUUID()}A1`,
            }, { [headerName]: `Bearer ${payload.key}` });
          }
          const invitation = await post("/invitation/new", { user_id: user.user_id });
          const password = `Qa!${randomUUID()}B2`;
          const action = variant === "reset_password" ? "&action=reset_password" : "";
          await page.goto(`/ui/onboarding/?invitation_id=${invitation.id}${action}`);
          await expect(page.getByLabel("Email Address", { exact: true })).toHaveValue(userEmail);
          const passwordInput = page.getByLabel("Password", { exact: true });
          await passwordInput.fill(password);
          await shoot("before-submit");
          const claimPromise = page.waitForResponse(response => new URL(response.url()).pathname === "/onboarding/claim_token" && response.request().method() === "POST");
          const submit = page.getByRole("button", { name: variant === "reset_password" ? "Reset Password" : "Sign Up", exact: true });
          if (viewport.touch) await submit.tap(); else await submit.click();
          const claim = await claimPromise;
          const headers = await claim.request().allHeaders();
          report.claim = { status: claim.status(), authorizationPresent: Boolean(headers.authorization), customHeaderPresent: Boolean(headers["x-litellm-api-key"]) };
          if (!successExpected) {
            assert.equal(claim.status(), 401);
            assert.equal(report.claim.authorizationPresent, true);
            assert.equal(report.claim.customHeaderPresent, false);
            await expect(page.getByText("Missing onboarding session for invitation link.", { exact: false }).first()).toBeVisible();
            await shoot("result");
            report.outcome = "reproduced_missing_onboarding_session";
          } else {
            assert.equal(claim.status(), 200);
            assert.equal(report.claim.authorizationPresent, headerMode === "default");
            assert.equal(report.claim.customHeaderPresent, headerMode === "custom");
            await expect.poll(async () => (await context.cookies()).some(cookie => cookie.name === "token")).toBe(true);
            const finalToken = (await context.cookies()).find(cookie => cookie.name === "token").value;
            const session = JSON.parse(Buffer.from(finalToken.split(".")[1], "base64url").toString());
            assert.equal(session.user_id, user.user_id);
            assert.equal(session.auth_header_name, headerName);
            await page.waitForURL(url => url.pathname.startsWith("/ui") && !url.pathname.includes("onboarding"));
            await openKeys(page);
            const ownUser = await api.get("/user/info", { headers: { [headerName]: `Bearer ${session.key}` }, params: { user_id: user.user_id } });
            assert.equal(ownUser.status(), 200);
            assert.equal((await ownUser.json()).user_id, user.user_id);
            await shoot("result");
            report.ownUserReadStatus = ownUser.status();
            const loginContext = await browser.newContext({
              baseURL, viewport: { width: viewport.width, height: viewport.height },
              hasTouch: viewport.touch, isMobile: viewport.touch,
            });
            const loginPage = await loginContext.newPage();
            try {
              loginPage.on("pageerror", error => report.pageErrors.push(error.message));
              loginPage.on("response", response => {
                if (response.status() >= 400) report.httpErrors.push({ path: new URL(response.url()).pathname, status: response.status() });
                if (new URL(response.url()).pathname === "/key/list") report.keyLists.push({ context: "fresh-login", status: response.status() });
              });
              await loginPage.goto("/ui/login");
              await loginPage.getByPlaceholder("Enter your username").fill(userEmail);
              await loginPage.getByPlaceholder("Enter your password").fill(password);
              await loginPage.getByRole("button", { name: "Login", exact: true }).click();
              await loginPage.waitForURL(url => url.pathname.startsWith("/ui") && !url.pathname.includes("/login"));
              const tokenCookie = (await loginContext.cookies()).find(cookie => cookie.name === "token");
              assert(tokenCookie);
              assert.equal(JSON.parse(Buffer.from(tokenCookie.value.split(".")[1], "base64url").toString()).user_id, user.user_id);
              report.freshLoginLandingPath = new URL(loginPage.url()).pathname;
              await openKeys(loginPage);
              await shoot("new-login", loginPage);
              report.freshLoginWithNewPassword = true;
            } catch (error) {
              await shoot("new-login-failure", loginPage);
              throw error;
            } finally { await loginContext.close(); }
            report.outcome = "signup_or_reset_and_new_login_passed";
            assert(report.keyLists.some(response => response.context === "after-claim" && response.status === 200));
            assert(report.keyLists.some(response => response.context === "fresh-login" && response.status === 200));
            assert(report.keyLists.every(response => response.status === 200));
          }
          assert.deepEqual(report.pageErrors, []);
          assert.deepEqual(report.httpErrors.filter(response => response.status >= 500), []);
          if (successExpected) assert.deepEqual(report.httpErrors.filter(response => response.path === "/onboarding/claim_token"), []);
        } catch (error) {
          report.error = String(error);
          await shoot("failure");
          throw error;
        } finally {
          await context.close();
          await page.video().saveAs(path.join(output, `${name}.webm`));
          const deleted = await api.post("/user/delete", { data: { user_ids: [user.user_id] } });
          report.cleanup = deleted.status();
          assert(deleted.ok());
          await fs.writeFile(path.join(output, "report.json"), JSON.stringify({ build, headerMode, sourceSha, runId, baseURL, browserVersion: browser.version(), reports }, null, 2));
        }
        console.log(`${build} ${headerMode} ${name}: ${report.outcome}`);
      }
    }
  } finally {
    await browser.close();
    await api.dispose();
  }
}

main().catch(error => { console.error(error); process.exitCode = 1; });
