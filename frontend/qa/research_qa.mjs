import fs from "node:fs";
import { launch, sleep, waitText, waitPath, btn, typeInto, summary } from "./lib.mjs";
const BASE = process.env.BASE; const setMode = (m) => fs.writeFileSync("/tmp/qa/provider_mode", m);
const { browser, page, log } = await launch(1440, 900);
const api = (m, p, b) => page.evaluate(async (m, p, b) => { const r = await fetch("/api" + p, { method: m, headers: { "Content-Type": "application/json" }, body: b ? JSON.stringify(b) : undefined }); return r.status === 204 ? null : r.json(); }, m, p, b);
setMode("ok");
await page.goto(BASE + "/register"); await typeInto(page, "Email", `qa-q-${Date.now()}@example.com`); await typeInto(page, "Password", "password123"); await btn(page, "Create account"); await waitPath(page, "^/projects$");
const mk = async (name, idea = true) => { const p = await api("POST", "/projects", { name }); if (idea) await api("PUT", `/projects/${p.id}/brain/idea`, { value: { raw: "A platform for local store owners.", product_name: "P", product_type: "t", problem: "Hard to sell online", features: ["Guided setup"], assumptions: ["No developer"], open_questions: [] } }); return p.id; };
const P = { empty: await mk("Empty"), draft: await mk("Draft"), review: await mk("Review"), approved: await mk("Approved"), failed: await mk("Failed") };
for (const k of ["draft", "review", "approved"]) await api("POST", `/projects/${P[k]}/research/generate`, {});
// long, unbroken content to exercise wrapping
const long = "x".repeat(160), st = await api("GET", `/projects/${P.draft}/research`); let h = st.current.content_hash;
let r = await api("POST", `/projects/${P.draft}/research/reports/1/findings`, { base_hash: h, topic: "risks", statement: long }); h = r.report.content_hash;
r = await api("POST", `/projects/${P.draft}/research/reports/1/sources`, { base_hash: h, title: "T".repeat(150), url: "https://example.com/" + "a".repeat(180), examined: true, accessed_on: "2026-10-01" });
for (const k of ["review", "approved"]) { const s = await api("GET", `/projects/${P[k]}/research`); await api("POST", `/projects/${P[k]}/research/reports/1/submit`, { base_hash: s.current.content_hash }); }
{ const s = await api("GET", `/projects/${P.approved}/research`); await api("POST", `/projects/${P.approved}/research/reports/1/approve`, { content_hash: s.current.content_hash, acknowledge_unverified: true }); }
setMode("unconfigured"); await api("POST", `/projects/${P.failed}/research/generate`, {}); setMode("ok");

const out = { axe: {}, overflow: {}, keyboard: {}, network: {} };
const url = (k) => `${BASE}/projects/${P[k]}/research`;
// network per fresh load (production build)
log.requests.length = 0; await page.goto(url("draft")); await sleep(1200); out.network.draft = summary(log).requests;
const axeOn = async (name) => { await page.addScriptTag({ path: "node_modules/axe-core/axe.min.js" }); const v = await page.evaluate(async () => (await axe.run()).violations.map((x) => ({ id: x.id, impact: x.impact, n: x.nodes.length, first: x.nodes[0].target.join(" ") }))); out.axe[name] = v.length ? v : "0 violations"; };
for (const k of ["empty", "draft", "review", "approved", "failed"]) { await page.goto(url(k)); await sleep(900); await axeOn(k); }
await page.goto(url("draft")); await sleep(700);
for (const [name, label] of [["finding-dialog", "Add finding"], ["source-dialog", "Add source"]]) { await btn(page, label); await page.waitForSelector("[role=dialog]"); await axeOn(name); await page.keyboard.press("Escape"); await page.waitForFunction(() => !document.querySelector("[role=dialog]")); }
await page.goto(url("review")); await sleep(700); await btn(page, "Approve version 1"); await page.waitForSelector("[role=dialog]"); await axeOn("approve-dialog"); await page.keyboard.press("Escape");
await page.goto(url("approved")); await sleep(700); await page.locator("::-p-aria(View version 1)").click(); await sleep(700); await axeOn("history-view");
// overflow inside <main> at 4 viewports
for (const [w, h2] of [[1440, 900], [1280, 720], [768, 1024], [390, 844]]) {
  await page.setViewport({ width: w, height: h2 });
  for (const k of ["empty", "draft", "review", "approved", "failed"]) {
    await page.goto(url(k)); await sleep(500);
    const m = await page.evaluate(() => { const main = document.querySelector("main"); return { main: main.scrollWidth - main.clientWidth, doc: document.documentElement.scrollWidth - innerWidth }; });
    if (m.main > 0 || m.doc > 0) out.overflow[`${w}/${k}`] = m;
    if (w === 390 && k === "draft") await page.screenshot({ path: "shots/r-390-draft.png" });
  }
}
await page.setViewport({ width: 1440, height: 900 });
// keyboard: tab order with visible focus, dialog trap / Escape / focus return
await page.goto(url("draft")); await page.waitForSelector("h1"); await page.evaluate(() => document.activeElement.blur());
const desc = () => page.evaluate(() => { const e = document.activeElement, cs = getComputedStyle(e); const ring = (cs.outlineStyle !== "none" && parseFloat(cs.outlineWidth) > 0) || cs.boxShadow !== "none"; return { el: `${e.tagName.toLowerCase()}:${(e.getAttribute("aria-label") || e.innerText || "").toString().replace(/\s+/g, " ").slice(0, 30)}`, ring, inDialog: !!e.closest("[role=dialog]") }; });
const stops = []; for (let i = 0; i < 30; i++) { await page.keyboard.press("Tab"); stops.push(await desc()); }
out.keyboard.noRing = stops.filter((s) => !s.ring).map((s) => s.el); out.keyboard.reachable = { submit: stops.some((s) => s.el.includes("Submit for review")), editFinding: stops.some((s) => s.el.includes("Edit finding f-1")), addSource: stops.some((s) => s.el.includes("Add source")) };
await page.focus('button[aria-label="Edit finding f-1"]'); await page.keyboard.press("Enter"); await page.waitForSelector("[role=dialog]");
const first = await desc(); const inside = []; for (let i = 0; i < 24; i++) { await page.keyboard.press("Tab"); inside.push((await desc()).inDialog); }
await page.keyboard.press("Escape"); await page.waitForFunction(() => !document.querySelector("[role=dialog]"));
out.keyboard.dialog = { firstFocusInside: first.inDialog, tabbingStaysInside: inside.every(Boolean), focusReturned: (await desc()).el };
await browser.close();
console.log(JSON.stringify({ ...out, pageerrors: log.pageerrors, consoleMsgs: [...new Set(log.console)] }, null, 1));
