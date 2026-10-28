import { execSync } from "node:child_process";
import { launch, sleep, waitText, waitPath, btn, typeInto, summary } from "./lib.mjs";
const BASE = process.env.BASE; const { browser, page, log } = await launch(1440, 900);
const r = {}; process.on('uncaughtException', (e) => { console.log('FAILED after', JSON.stringify(r), String(e.message).slice(0, 120)); page.screenshot({ path: 'shots/actions-fail.png' }).finally(() => process.exit(1)); });
await page.goto(BASE + "/register"); await typeInto(page, "Email", `qa-a-${Date.now()}@example.com`); await typeInto(page, "Password", "password123"); await btn(page, "Create account"); await waitPath(page, "^/projects$");
const api = (m, p, b) => page.evaluate(async (m, p, b) => { const x = await fetch("/api" + p, { method: m, headers: { "Content-Type": "application/json" }, body: b ? JSON.stringify(b) : undefined }); return x.status === 204 ? null : x.json(); }, m, p, b);
const alpha = (await api("POST", "/projects", { name: "Alpha", description: "first" })).id; const beta = (await api("POST", "/projects", { name: "Beta", description: "" })).id;
await page.reload(); await waitText(page, "Alpha");
// rename
await btn(page, "Rename Alpha"); await typeInto(page, "Project name", "Alpha renamed"); await btn(page, "Save"); await waitText(page, "Alpha renamed");
r.rename = { ui: true, db: (await api("GET", `/projects/${alpha}`)).name };
// archive / restore
await btn(page, "Archive Beta"); await waitText(page, "Archived"); r.archive = (await api("GET", `/projects/${beta}`)).status;
await btn(page, "Restore Beta"); await page.waitForFunction(() => !document.body.innerText.includes("Archived")); r.restore = (await api("GET", `/projects/${beta}`)).status;
// delete with confirmation (cancel first, then confirm)
await btn(page, "Delete Beta"); await btn(page, "Cancel"); r.cancelKeptProject = (await api("GET", "/projects")).length;
await btn(page, "Delete Beta"); await btn(page, "Delete project"); await page.waitForFunction(() => !document.body.innerText.includes("Beta"));
r.deleteBeta = { remaining: (await api("GET", "/projects")).length, getDeleted: (await api("GET", `/projects/${beta}`)).detail };
r.betaRowsLeftInDb = execSync(`PGPASSWORD=webforge psql -h 127.0.0.1 -U webforge -d webforge -tAc "select (select count(*) from project_brain_revisions where project_id='${beta}')+(select count(*) from project_stages where project_id='${beta}')"`).toString().trim();
await btn(page, "Delete Alpha renamed"); await btn(page, "Delete project"); await waitText(page, "No projects yet."); r.emptyAfterDeletes = true;
// loading state under latency
const cdp = await page.createCDPSession(); await cdp.send("Network.enable"); await cdp.send("Network.emulateNetworkConditions", { offline: false, latency: 1500, downloadThroughput: -1, uploadThroughput: -1 });
await page.goto(BASE + "/projects", { waitUntil: "domcontentloaded" });
r.loadingStates = []; for (let i = 0; i < 12; i++) { const t = await page.evaluate(() => document.body.innerText.replace(/\s+/g, " ").slice(0, 60)); if (!r.loadingStates.includes(t)) r.loadingStates.push(t); await sleep(500); }
await cdp.send("Network.emulateNetworkConditions", { offline: false, latency: 0, downloadThroughput: -1, uploadThroughput: -1 });
// not found
await page.goto(BASE + "/projects/00000000-0000-0000-0000-000000000000/overview"); await waitText(page, "Project not found"); r.notFound = true;
// backend down at startup -> error screen -> retry after recovery
execSync("kill $(pgrep -f '[u]vicorn app.main') || true"); await sleep(1500);
await page.goto(BASE + "/projects"); await sleep(1500);
r.backendDown = await page.evaluate(() => ({ text: document.body.innerText.replace(/\s+/g, " ").slice(0, 160), hasRetry: !![...document.querySelectorAll("button")].find((b) => b.textContent === "Retry"), leaksInternals: /Traceback|ECONNREFUSED|proxy/i.test(document.body.innerText) }));
await page.screenshot({ path: "shots/v-backend-down.png" });
execSync("/tmp/qa/stack.sh", { stdio: "ignore" }); await sleep(2000);
await btn(page, "Retry"); await waitText(page, "No projects yet.", 10000); r.retryRecovered = true;
await browser.close(); console.log(JSON.stringify({ r, pageerrors: log.pageerrors, patchBodies: log.requests.filter((x) => x.m === "PATCH").map((x) => x.body), failedNonLogout: log.failed.filter((f) => !f.includes("logout")) }, null, 1));
