const fs = require('node:fs/promises');
const path = require('node:path');
const assert = require('node:assert/strict');
const {chromium, expect} = require('/repo/tests/e2e/ui/node_modules/@playwright/test');
const mode = process.argv[2];
assert(['baseline', 'fixed'].includes(mode));
const expectedPremium = mode === 'fixed';
const sha = mode === 'baseline' ? 'dddbaa803d6e9fcc862ea7a5412f771cb1ae040e' : process.env.QA_SOURCE_SHA;
assert(sha);
const output = path.join(__dirname, `visual-${mode}`);
const masterKey = process.env.LITELLM_MASTER_KEY;
assert(masterKey);

async function main() {
  await fs.mkdir(output, {recursive:true});
  const api = JSON.parse(await fs.readFile(path.join(__dirname, `api-${mode}-dotted.json`), 'utf8'));
  assert.equal(api.source_sha, sha);
  const browser = await chromium.launch({headless:false});
  const report = {mode, sha, browser:browser.version(), api, cases:[]};
  try {
    for (const spec of [{name:'desktop', width:1440, height:900}, {name:'phone', width:390, height:844}]) {
      const context = await browser.newContext({
        baseURL:'http://127.0.0.1:41475', viewport:{width:spec.width, height:spec.height},
        isMobile:spec.name === 'phone', hasTouch:spec.name === 'phone', colorScheme:'light',
        recordVideo:{dir:path.join(output,'raw-video'),size:{width:spec.width,height:spec.height}},
      });
      const page = await context.newPage();
      const video = page.video();
      const result = {viewport:spec, screenshots:[], pageErrors:[], serverErrors:[], missingResources:[], consoleErrors:[], unexpectedWrites:[]};
      report.cases.push(result);
      page.on('pageerror', error => result.pageErrors.push(error.message));
      page.on('console', message => { if(message.type() === 'error') result.consoleErrors.push(message.text()); });
      page.on('response', response => {
        const pathname = new URL(response.url()).pathname;
        if(response.status() >= 500) result.serverErrors.push({pathname,status:response.status()});
        if(response.status() === 404) result.missingResources.push(pathname);
      });
      page.on('request', request => {
        const pathname = new URL(request.url()).pathname;
        if(/update.*sso|sso.*update/.test(pathname) && request.method() !== 'GET') result.unexpectedWrites.push(pathname);
      });
      const activate = locator => spec.name === 'phone' ? locator.tap() : locator.click();
      const capture = async stage => {
        const filename = `${spec.name}-${stage}.png`;
        await page.mouse.move(1,1);
        await page.screenshot({path:path.join(output,filename),animations:'disabled',scale:'css'});
        result.screenshots.push(filename);
      };
      const blocked = page.getByText('Only premium users can configure UI access control',{exact:true});
      const dialog = page.getByRole('dialog',{name:'UI Access Control Settings',exact:true});
      const checkOutcome = async stage => {
        await activate(page.getByRole('button',{name:'UI Access Control',exact:true}));
        if(expectedPremium) {
          await expect(dialog).toBeVisible();
          await expect(dialog.getByRole('combobox',{name:'UI Access Mode'})).toBeVisible();
          await expect(dialog.getByRole('button',{name:'Update UI Access Control',exact:true})).toBeVisible();
          await expect(dialog).toBeInViewport({ratio:1});
          await capture(stage);
          result[`${stage}Box`] = await dialog.boundingBox();
        } else {
          await expect(blocked).toBeVisible();
          await page.waitForTimeout(350);
          await expect(blocked).toBeInViewport({ratio:1});
          await expect(dialog).toBeHidden();
          await capture(stage);
          result[`${stage}Box`] = await blocked.boundingBox();
        }
      };
      try {
        await page.goto('/ui/login');
        await page.getByPlaceholder('Enter your username').fill('admin');
        await page.getByPlaceholder('Enter your password').fill(masterKey);
        const healthReply = page.waitForResponse(response => new URL(response.url()).pathname === '/health/license');
        await activate(page.getByRole('button',{name:'Login',exact:true}));
        await expect(page.getByRole('button',{name:'Launch Aria Agent'})).toBeVisible({timeout:30000});
        const browserHealth = await healthReply;
        assert.equal(browserHealth.status(),200);
        result.browserLicense = await browserHealth.json();
        assert.deepEqual(result.browserLicense,api.response);
        const token = (await context.cookies()).find(cookie => cookie.name === 'token');
        assert(token);
        const claims = JSON.parse(Buffer.from(token.value.split('.')[1],'base64url').toString('utf8'));
        result.premiumClaim = claims.premium_user;
        assert.equal(result.premiumClaim,expectedPremium);
        await page.goto('/ui/admin-panel');
        await activate(page.getByRole('tab',{name:'Security Settings',exact:true}));
        await expect(page.getByRole('button',{name:'UI Access Control',exact:true})).toBeVisible();
        await capture('security-settings');
        result.pageWidth = await page.evaluate(() => ({viewport:innerWidth,document:document.documentElement.scrollWidth}));
        await checkOutcome('result');
        if(expectedPremium) {
          await activate(dialog.getByRole('combobox',{name:'UI Access Mode'}));
          await activate(page.getByRole('option',{name:'Restricted SSO Group',exact:true}));
          await dialog.getByLabel('Restricted SSO Group',{exact:true}).fill('qa-license-reviewers');
          await dialog.getByLabel('SSO Group JWT Field').fill('groups');
          await expect(dialog.getByLabel('Restricted SSO Group',{exact:true})).toHaveValue('qa-license-reviewers');
          await expect(dialog.getByLabel('SSO Group JWT Field')).toHaveValue('groups');
          await capture('form-controls');
          await activate(dialog.getByRole('button',{name:'Close',exact:true}));
          await expect(dialog).toBeHidden();
        }
        await page.reload();
        await activate(page.getByRole('tab',{name:'Security Settings',exact:true}));
        await checkOutcome('after-reload');
        assert.equal(result.pageErrors.length,0);
        assert.equal(result.serverErrors.length,0);
        assert.equal(result.unexpectedWrites.length,0);
        result.passed = true;
        console.log(`${mode} ${spec.name}: premium=${result.premiumClaim}, gated screen ${expectedPremium ? 'opens' : 'rejects'}, reload verified`);
      } catch(error) {
        result.error = error.message;
        await capture('failure');
        throw error;
      } finally {
        await context.close();
        await fs.copyFile(await video.path(),path.join(output,`${spec.name}.webm`));
        await fs.writeFile(path.join(output,'report.json'),JSON.stringify(report,null,2)+'\n');
      }
    }
  } finally { await browser.close(); }
}
main().catch(error => { console.error(error.message); process.exitCode=1; });
