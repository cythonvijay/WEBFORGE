import { launch, sleep, waitText, waitPath, btn, typeInto, overflow, cookies, storage, summary } from "./lib.mjs";
const BASE = process.env.BASE, TAG = process.env.TAG;
const { browser, page, log } = await launch(1440, 900);
const shot = (n) => page.screenshot({ path: `shots/${TAG}-${n}.png` });
const out = {};
const email = `qa-${Date.now()}@example.com`, pw = "password123";

await page.goto(BASE + "/projects"); await waitPath(page, "^/login$");
out.anonRedirect = page.url().replace(BASE, ""); await shot("01-login");

await page.goto(BASE + "/register"); await shot("02-register");
await typeInto(page, "Email", email); await typeInto(page, "Password", pw); await btn(page, "Create account");
await waitPath(page, "^/projects$"); await waitText(page, "No projects yet."); await shot("03-projects-empty");
out.afterRegister = { url: page.url().replace(BASE, ""), storage: await storage(page), cookies: await cookies(page) };

await page.reload(); await waitText(page, "No projects yet."); out.reloadStillAuthed = page.url().replace(BASE, "");
await btn(page, "Sign out"); await waitPath(page, "^/login$");
await page.goto(BASE + "/projects"); await waitPath(page, "^/login$"); out.afterLogoutProtected = page.url().replace(BASE, "");
await typeInto(page, "Email", email); await typeInto(page, "Password", pw); await btn(page, "Sign in");
await waitPath(page, "^/projects$"); out.loginAgain = "ok";

async function createProject(name, desc) {
  await page.evaluate(() => document.querySelectorAll("[role=dialog]").forEach(() => 0));
  await btn(page, "New project"); await typeInto(page, "Project name", name);
  if (desc) await typeInto(page, "Description", desc);
  await shot("04-create-dialog-" + name.slice(0, 3).trim());
  await btn(page, "Create project"); await waitPath(page, "/overview$"); await waitText(page, name.slice(0, 10));
}
await createProject("Local Store Builder", "A platform that helps small local businesses create and manage online stores without technical knowledge.");
const pid = page.url().match(/projects\/([^/]+)\//)[1];
await shot("05-overview-new");

// lifecycle: blocked then valid transition
await page.select('select[aria-label="Set status for Frontend"]', "in_progress");
await page.waitForSelector("[role=alert]"); out.conflictMessage = await page.$eval("[role=alert]", (e) => e.innerText); await shot("06-lifecycle-conflict");
await page.select('select[aria-label="Set status for Research"]', "complete");
await page.waitForFunction(() => document.querySelector('[role=progressbar]').getAttribute('aria-valuenow') !== '0');
out.progressAfter = await page.$eval("[role=progressbar]", (e) => e.getAttribute("aria-valuenow"));
await page.select('select[aria-label="Set status for Product"]', "in_progress");
await page.waitForFunction(() => /Continue Product/.test(document.body.innerText));
await page.reload(); await waitText(page, "Lifecycle");
out.persisted = await page.$eval('select[aria-label="Set status for Research"]', (e) => e.value) + "/" + await page.$eval('select[aria-label="Set status for Product"]', (e) => e.value);
await shot("07-overview-progress");

// intake without provider
await typeInto(page, "Product idea", "A platform that helps small local businesses create and manage online stores without technical knowledge.");
const before = await page.evaluate(async (id) => (await (await fetch(`/api/projects/${id}/brain`)).json()).version, pid);
await btn(page, "Analyze idea"); await waitText(page, "AI analysis is not configured yet."); await shot("08-intake-503");
const after = await page.evaluate(async (id) => (await (await fetch(`/api/projects/${id}/brain`)).json()).version, pid);
out.intake = { text: await page.evaluate(() => document.body.innerText.includes("Your project has not been modified")), brainBefore: before, brainAfter: after, textKept: await page.$eval("textarea", (e) => e.value.length > 0) };

// projects: variants
await page.goto(BASE + "/projects"); await waitText(page, "Local Store Builder");
await createProject("Enterprise multi-tenant storefront builder for independent local businesses across regions with localized payments, tax handling, shipping integrations and inventory sync for every channel", "x ".repeat(350).trim());
await page.goto(BASE + "/projects"); await waitText(page, "Local Store");
await createProject("x".repeat(120), "");
await page.goto(BASE + "/projects"); await waitText(page, "Local Store"); await shot("09-projects-variants");
out.projectsOverflow1440 = await overflow(page);
out.rows = await page.$$eval("tbody tr", (r) => r.length);
await browser.close();
console.log(JSON.stringify({ out, ...summary(log) }, null, 1));
