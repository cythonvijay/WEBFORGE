import fs from "node:fs";
import { execSync } from "node:child_process";
import { launch, sleep, waitText, waitPath, btn, typeInto } from "./lib.mjs";
const BASE = process.env.BASE; const setMode = (m) => fs.writeFileSync("/tmp/qa/provider_mode", m);
const { browser, page, log } = await launch(1440, 900);
const R = {}; const shot = (n) => page.screenshot({ path: `shots/r-${n}.png` });
const sql = (q) => execSync(`PGPASSWORD=webforge psql -h 127.0.0.1 -U webforge -d webforge -tAc "${q}"`).toString().trim();
const api = (m, p, b) => page.evaluate(async (m, p, b) => { const r = await fetch("/api" + p, { method: m, headers: { "Content-Type": "application/json" }, body: b ? JSON.stringify(b) : undefined }); return { s: r.status, j: r.status === 204 ? null : await r.json() }; }, m, p, b);
const text = () => page.evaluate(() => document.body.innerText.replace(/\s+/g, " "));
const step = async (n, f) => { try { return await f(); } catch (e) { console.log("STEP FAILED:", n, String(e.message).slice(0, 100)); console.log((await text()).slice(0, 400)); await page.screenshot({ path: "shots/r-stuck.png" }); process.exit(1); } };
const stage = async (pid) => (await api("GET", `/projects/${pid}/overview`)).j.stages.find((s) => s.stage === "research").status;
const ctl = (label) => page.locator(`::-p-aria(${label})`).setTimeout(6000);
const dialogSubmit = () => page.click("[role=dialog] button[type=submit]");
const gone = () => page.waitForFunction(() => !document.querySelector("[role=dialog]"));

setMode("ok");
await page.goto(BASE + "/register"); await typeInto(page, "Email", `qa-r-${Date.now()}@example.com`); await typeInto(page, "Password", "password123"); await btn(page, "Create account"); await waitPath(page, "^/projects$");
await btn(page, "New project").catch(() => {}); await page.waitForSelector("[role=dialog]"); await typeInto(page, "Project name", "Local Store Builder"); await btn(page, "Create project"); await waitPath(page, "/overview$");
const pid = page.url().match(/projects\/([^/]+)\//)[1];
await typeInto(page, "Product idea", "A platform that helps small local businesses create and manage online stores without technical knowledge.");
await btn(page, "Analyze idea"); await waitText(page, "Start discovery");

await page.goto(BASE + `/projects/${pid}/research`); await waitText(page, "No research report yet"); await shot("01-empty");
const t0 = await text();
R.empty = { banner: t0.includes("no web research was performed"), missingInputs: t0.includes("Missing or unconfirmed inputs"), aiProposed: t0.includes("AI-proposed, unconfirmed"), noFindingsSection: !t0.includes("What the evidence labels mean"), stage: await stage(pid) };

const b0 = (await api("GET", `/projects/${pid}/brain`)).j.version;
setMode("unconfigured"); await btn(page, "Start preliminary research"); await waitText(page, "AI analysis is not configured yet.");
R.unconfigured = { status: sql("select string_agg(status,',') from research_reports"), leaksKey: /GOOGLE_AI_API_KEY/.test(await text()) };
setMode("malformed"); await btn(page, "Retry generating the report"); await waitText(page, "WebForge couldn't produce a valid research report.");
R.malformed = { rows: sql("select count(*) from research_reports"), status: sql("select string_agg(status,',') from research_reports"), brainUnchanged: (await api("GET", `/projects/${pid}/brain`)).j.version === b0, stage: await stage(pid) };

setMode("ok"); await btn(page, "Retry generating the report"); await waitText(page, "What the evidence labels mean"); await shot("02-draft");
const st = (await api("GET", `/projects/${pid}/research`)).j; const c = st.current;
R.generated = { rows: sql("select count(*) from research_reports"), version: c.version, status: st.status, evidence: c.content.findings.map((f) => f.evidence), downgraded: c.content.findings.filter((f) => f.note).map((f) => f.statement.slice(0, 28)), sources: c.content.sources.length,
  stageUnchanged: (await stage(pid)) === "not_started", brainUnchanged: (await api("GET", `/projects/${pid}/brain`)).j.version === b0, mode: c.mode };
const t1 = await text();
R.ui = { topics: ["User needs and pain points", "Market context", "Competitors and alternatives", "Risks", "Recommendations"].every((x) => t1.includes(x)), labels: ["Hypothesis", "AI suggestion", "Unsupported claim"].every((x) => t1.includes(x)), noSources: t1.includes("No sources attached."), warnings: t1.includes("What remains unverified") };

await step("add source", async () => {
  await btn(page, "Add source"); await page.waitForSelector("[role=dialog]");
  await typeInto(page, "Title", "Industry report"); await typeInto(page, "URL", "https://Example.com/report?utm_source=newsletter");
  await page.type('[role=dialog] input[type=date]', "10012026"); await page.click("[role=dialog] input[type=checkbox]");
  await dialogSubmit(); await gone(); await waitText(page, "Industry report");
});
await step("cite", async () => {
  await btn(page, "Edit finding f-1"); await page.waitForSelector("[role=dialog]");
  await btn(page, "Add citation"); await page.select('select[aria-label="Citation 1 source"]', "src-1"); await page.type('input[aria-label="Citation 1 claim supported"]', "Customers compare photographers mainly on price.");
  const sels = await page.$$("[role=dialog] select"); await sels[1].select("verified_source");
  await dialogSubmit(); await gone();
});
const cur2 = (await api("GET", `/projects/${pid}/research`)).j.current;
const link = await page.$eval('a[href="https://example.com/report"]', (a) => ({ href: a.href, rel: a.rel, target: a.target }));
R.cited = { storedUrl: cur2.content.sources[0].url, examinedBy: cur2.content.sources[0].examined_by, f1: cur2.content.findings[0].evidence, link, unverifiedNow: cur2.unverified_count };
await shot("03-cited");
await btn(page, "Add source"); await page.waitForSelector("[role=dialog]"); await typeInto(page, "Title", "Bad"); await typeInto(page, "URL", "javascript:alert(1)"); await dialogSubmit();
await waitText(page, "URL must start with http"); R.badUrl = { refused: true, sourcesStored: (await api("GET", `/projects/${pid}/research`)).j.current.content.sources.length, titleKept: await page.$eval('[role=dialog] input', (i) => i.value) }; await page.keyboard.press("Escape"); await gone();

await btn(page, "Submit for review"); await waitText(page, "Submitted for review");
R.submitted = { stage: await stage(pid), status: (await api("GET", `/projects/${pid}/research`)).j.status };
await btn(page, "Approve version 1"); await page.waitForSelector("[role=dialog]");
R.approveDisabledUntilAck = await page.$eval("[role=dialog] button[type=submit]", (b) => b.disabled); await shot("04-approve-dialog");
await page.click("[role=dialog] input[type=checkbox]"); await typeInto(page, "Approval note (optional)", "Reviewed with the team");
const bBefore = (await api("GET", `/projects/${pid}/brain`)).j;
await dialogSubmit(); await waitText(page, "Version 1 approved on"); await shot("05-approved");
const bAfter = (await api("GET", `/projects/${pid}/brain`)).j; const revs = (await api("GET", `/projects/${pid}/revisions`)).j;
R.approved = { stage: await stage(pid), brainVersion: [bBefore.version, bAfter.version], latestRevision: revs[0].change_type, patchKeys: Object.keys(revs[0].patch), pointer: { v: bAfter.brain.research.approved_version, ack: bAfter.brain.research.unverified_acknowledged, counts: bAfter.brain.research.finding_counts },
  confirmedUntouched: ["idea", "target_users", "discovery"].every((k) => JSON.stringify(bBefore.brain[k]) === JSON.stringify(bAfter.brain[k])) };
const v1hash = sql("select content_hash from research_reports where version=1");

await ctl("Flag for follow-up: finding f-1").click(); await waitText(page, "Saved as a new draft, version 2.");
R.copyOnWrite = { rows: sql("select count(*) from research_reports"), v1: sql("select status from research_reports where version=1"), v1HashSame: sql("select content_hash from research_reports where version=1") === v1hash, v2: sql("select status || ',' || created_via || ',v' || parent_version from research_reports where version=2"), stage: await stage(pid), pointerStillV1: (await api("GET", `/projects/${pid}/brain`)).j.brain.research.approved_version, headerShowsApproved: (await text()).includes("Approved version: 1") };
R.manualCompleteBlocked = (await api("PUT", `/projects/${pid}/stages/research`, { status: "complete" })).s;
await shot("06-v2-draft");

await ctl("View version 1").click(); await waitText(page, "Viewing version 1 (read-only)");
R.history = { readOnly: !(await text()).includes("Edit finding"), versionsListed: (await text()).includes("Version 1") && (await text()).includes("Version 2") }; await shot("07-history-view");
await btn(page, "Back to the current report");

await page.reload(); await waitText(page, "Approved version: 1"); R.reload = { persisted: (await text()).includes("Version 2") };
await btn(page, "Sign out"); await waitPath(page, "^/login$");
await page.goto(BASE + "/register"); await typeInto(page, "Email", `qa-r2-${Date.now()}@example.com`); await typeInto(page, "Password", "password123"); await btn(page, "Create account"); await waitPath(page, "^/projects$");
R.otherUser = { get: (await api("GET", `/projects/${pid}/research`)).s, generate: (await api("POST", `/projects/${pid}/research/generate`, {})).s, report: (await api("GET", `/projects/${pid}/research/reports/1`)).s };
await browser.close();
console.log(JSON.stringify({ R, pid, pageerrors: log.pageerrors, unexpectedFailed: log.failed.filter((f) => !/logout|ERR_ABORTED/.test(f)), consoleMsgs: [...new Set(log.console)] }, null, 1));
