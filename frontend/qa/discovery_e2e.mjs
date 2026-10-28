import fs from "node:fs";
import { execSync } from "node:child_process";
import { launch, sleep, waitText, waitPath, btn, typeInto, summary } from "./lib.mjs";
const BASE = process.env.BASE; const MODE = "/tmp/qa/provider_mode";
const setMode = (m) => fs.writeFileSync(MODE, m);
const { browser, page, log } = await launch(1440, 900);
const R = {}; const shot = (n) => page.screenshot({ path: `shots/d-${n}.png` });
const sql = (q) => execSync(`PGPASSWORD=webforge psql -h 127.0.0.1 -U webforge -d webforge -tAc "${q}"`).toString().trim();
const api = (m, p, b) => page.evaluate(async (m, p, b) => { const r = await fetch("/api" + p, { method: m, headers: { "Content-Type": "application/json" }, body: b ? JSON.stringify(b) : undefined }); return { s: r.status, j: r.status === 204 ? null : await r.json() }; }, m, p, b);
const text = () => page.evaluate(() => document.body.innerText.replace(/\s+/g, " "));
const click = (label) => page.locator(`::-p-aria(${label})`).setTimeout(6000).click();
const counts = () => page.$eval('[aria-label="Discovery progress"]', (e) => e.innerText);

setMode("ok");
await page.goto(BASE + "/register"); await typeInto(page, "Email", `qa-d-${Date.now()}@example.com`); await typeInto(page, "Password", "password123"); await btn(page, "Create account"); await waitPath(page, "^/projects$");
await btn(page, "New project").catch(() => {}); await page.waitForSelector("[role=dialog]"); await typeInto(page, "Project name", "Local Store Builder"); await btn(page, "Create project"); await waitPath(page, "/overview$");
const pid = page.url().match(/projects\/([^/]+)\//)[1];
R.noCalloutBeforeIdea = !(await text()).includes("Discovery Answer a few");

// idea analysis through the real intake endpoint (test double provider)
await typeInto(page, "Product idea", "A platform that helps small local businesses create and manage online stores without technical knowledge.");
await btn(page, "Analyze idea"); await waitText(page, "Product idea"); await waitText(page, "Start discovery"); await shot("01-overview-callout");
R.calloutAfterIdea = (await text()).includes("Answer a few focused questions");

await click("Start discovery"); await waitPath(page, "/discovery$"); await waitText(page, "Start with a few focused questions");
// provider unavailable -> explained, nothing saved; no auto retry
setMode("unconfigured"); await btn(page, "Start discovery"); await waitText(page, "AI analysis is not configured yet."); await waitText(page, "Questions couldn't be generated");
R.unconfigured = { msgOk: true, leaksKey: /GOOGLE_AI_API_KEY/.test(await text()), state: (await api("GET", `/projects/${pid}/discovery`)).j.status, questionsInDb: sql("select count(*) from discovery_questions") };
await shot("02-failed");
setMode("malformed"); await btn(page, "Retry"); await waitText(page, "couldn't use the AI response"); R.malformed = (await api("GET", `/projects/${pid}/discovery`)).j.status;
const v0 = (await api("GET", `/projects/${pid}/brain`)).j.version;
setMode("ok"); await btn(page, "Retry"); await waitText(page, "Who will use the product first?");
R.afterRetry = { counts: await counts(), sessions: sql("select count(*) from discovery_sessions"), questions: sql("select count(*) from discovery_questions"), brainUnchangedByFailures: (await api("GET", `/projects/${pid}/brain`)).j.version === v0 };
await shot("03-questions");

// answer every type
await typeInto(page, "Who will use the product first?", "Independent shop owners; Local service businesses");
await click("Online booking"); await click("Stripe"); await click("Email");
await page.locator('::-p-aria(Yes)').click();
await btn(page, "Save answers"); await page.waitForFunction(() => document.querySelector('[aria-label="Discovery progress"]').innerText.includes("4 answered"));
R.saved = await counts();
const b1 = (await api("GET", `/projects/${pid}/brain`)).j;
R.brainAfterAnswers = { version: b1.version, target_users: b1.brain.target_users, mvp: b1.brain.product_strategy.mvp_scope, integrations: b1.brain.architecture.integrations, privacy: b1.brain.security.privacy_requirements, confirmed: b1.brain.discovery.confirmed.map((f) => `${f.source}:${f.target}`) };
// reload = resume the same session, answers pre-filled
await page.reload(); await waitText(page, "Who will use the product first?"); await sleep(300);
R.resume = { sameQuestions: sql("select count(*) from discovery_questions"), textarea: await page.$eval("textarea", (e) => e.value), booking: await page.$eval('input[value="booking"]', (e) => e.checked), stripe: await page.$eval('input[value="stripe"]', (e) => e.checked), saveDisabled: await page.$eval('::-p-aria([role="button"][name="Save answers"])', (e) => e.disabled) };
// skip the optional one, then next round (duplicate filtered), failure keeps state
await page.locator('::-p-aria(Skip: How will the product make money?)').click(); await page.waitForFunction(() => document.querySelector('[aria-label="Discovery progress"]').innerText.includes("1 skipped"));
setMode("error"); await btn(page, "Generate more questions"); await waitText(page, "couldn't use the AI response");
R.nextRoundFailure = { counts: await counts(), round: (await api("GET", `/projects/${pid}/discovery`)).j.round };
setMode("ok"); await btn(page, "Generate more questions"); await waitText(page, "What must a customer be able to do in one visit?");
const st2 = (await api("GET", `/projects/${pid}/discovery`)).j;
R.round2 = { round: st2.round, total: st2.counts.total, duplicateFiltered: st2.questions.filter((q) => q.prompt === "Who will use the product first?").length === 1, counts: await counts() }; await shot("04-round2");
// defer required, skip optional, review
await page.locator('::-p-aria(Answer later: What must a customer be able to do in one visit?)').click(); await page.waitForFunction(() => document.querySelector('[aria-label="Discovery progress"]').innerText.includes("1 deferred"));
await page.locator('::-p-aria(Skip: When do you want to launch?)').click(); await page.waitForFunction(() => document.querySelector('[aria-label="Discovery progress"]').innerText.includes("2 skipped"));
await btn(page, "Review summary"); await waitText(page, "Confirmed by you"); await shot("05-review");
const t = await text();
R.review = { confirmed: t.includes("Independent shop owners"), proposedAI: t.includes("Proposed by AI, awaiting your approval") && t.includes("Guided store setup"), assumptionAI: t.includes("Owners have no developer"), deferredListed: /Deferred for later.*What must a customer be able/.test(t), disclaimer: t.includes("not market validation") };
// complete is blocked until assumptions accepted
R.completeDisabled = await page.$eval('::-p-aria([role="button"][name="Complete discovery"])', (e) => e.disabled);
// correct an answer during review
const step = async (n, f) => { try { await f(); } catch (e) { console.log("STEP FAILED:", n, String(e.message).slice(0, 80)); console.log(await page.evaluate(() => [...document.querySelectorAll("button")].map((b) => `${b.textContent.trim()}${b.disabled ? "(disabled)" : ""}`).join(" | "))); await page.screenshot({ path: "shots/d-stuck.png" }); process.exit(1); } };
await step("edit", () => btn(page, "Edit answers")); await step("type", async () => { await page.waitForSelector("textarea"); await page.focus("textarea"); await page.keyboard.down("Control"); await page.keyboard.press("a"); await page.keyboard.up("Control"); await page.keyboard.press("Backspace"); await page.keyboard.type("Wedding photographers"); }); await step("save", () => btn(page, "Save answers")); await waitText(page, "Wedding photographers");
await page.evaluate(() => window.scrollTo(0, 0));
R.corrected = (await api("GET", `/projects/${pid}/brain`)).j.brain.discovery.confirmed.find((f) => f.target === "target_users").answer;
await page.locator("::-p-aria(Complete with documented assumptions. 1 question is unanswered or deferred and will be recorded as unverified assumptions.)").click().catch(async () => { await page.click('input[type=checkbox]'); });
await btn(page, "Complete discovery"); await waitText(page, "Discovery completed."); await shot("06-completed");
R.completed = { next: (await text()).includes("Research and PRD generation are not available yet"), noSave: !(await text()).includes("Save answers"), db: sql("select status from discovery_sessions"), revisions: sql(`select string_agg(change_type, ',' order by version) from project_brain_revisions where project_id='${pid}'`), assumptions: sql(`select count(*) from project_brain_revisions r, jsonb_array_elements(r.snapshot->'discovery'->'assumptions') a where r.project_id='${pid}' and r.version=(select max(version) from project_brain_revisions where project_id='${pid}')`) };
await page.locator("::-p-aria(Return to project overview)").click(); await waitPath(page, "/overview$"); await waitText(page, "Discovery is complete.");
R.overviewAfter = (await text()).includes("Discovery is complete. Research and PRD generation are not available yet.");
R.versionsContiguous = sql(`select string_agg(version::text, ',' order by version) from project_brain_revisions where project_id='${pid}'`);

// another user cannot see it
await btn(page, "Sign out"); await waitPath(page, "^/login$");
await page.goto(BASE + "/register"); await typeInto(page, "Email", `qa-d2-${Date.now()}@example.com`); await typeInto(page, "Password", "password123"); await btn(page, "Create account"); await waitPath(page, "^/projects$");
R.otherUser = { get: (await api("GET", `/projects/${pid}/discovery`)).s, start: (await api("POST", `/projects/${pid}/discovery`)).s, answer: (await api("POST", `/projects/${pid}/discovery/answers`, { answers: [{ question_id: "x", value: "y" }] })).s };
await browser.close();
console.log(JSON.stringify({ R, pid, pageerrors: log.pageerrors, failedNonUnexpected: log.failed.filter((f) => !/logout|ERR_ABORTED/.test(f)), consoleMsgs: [...new Set(log.console)], requests: summary(log).requests }, null, 1));
