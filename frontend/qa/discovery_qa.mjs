import fs from "node:fs";
import { launch, sleep, waitText, waitPath, btn, typeInto, summary } from "./lib.mjs";
const BASE = process.env.BASE; const setMode = (m) => fs.writeFileSync("/tmp/qa/provider_mode", m);
const { browser, page, log } = await launch(1440, 900);
const api = (m, p, b) => page.evaluate(async (m, p, b) => { const r = await fetch("/api" + p, { method: m, headers: { "Content-Type": "application/json" }, body: b ? JSON.stringify(b) : undefined }); return r.status === 204 ? null : r.json(); }, m, p, b);
setMode("ok");
await page.goto(BASE + "/register"); await typeInto(page, "Email", `qa-q-${Date.now()}@example.com`); await typeInto(page, "Password", "password123"); await btn(page, "Create account"); await waitPath(page, "^/projects$");
const mk = async (name, withIdea = true) => { const p = await api("POST", "/projects", { name }); if (withIdea) await api("PUT", `/projects/${p.id}/brain/idea`, { value: { raw: "A platform for local store owners.", product_name: "P", product_type: "t", problem: "Hard to sell online", features: ["Guided setup"], assumptions: ["No developer"], open_questions: [] } }); return p.id; };
const val = (q) => ({ free_text: "Some text", single_choice: q.options[0]?.id, multiple_choice: q.options.slice(0, 1).map((o) => o.id), confirmation: true }[q.qtype]);
const P = { awaiting: await mk("Awaiting"), review: await mk("Review"), done: await mk("Done"), fresh: await mk("Fresh"), failed: await mk("Failed") };
for (const id of [P.awaiting, P.review, P.done]) await api("POST", `/projects/${id}/discovery`);
for (const id of [P.review, P.done]) { const st = await api("GET", `/projects/${id}/discovery`); const [a, b, ...rest] = st.questions; await api("POST", `/projects/${id}/discovery/answers`, { answers: [a, b].map((q) => ({ question_id: q.id, value: val(q) })) }); for (const q of rest) await api("POST", `/projects/${id}/discovery/questions/${q.id}/${q.required ? "defer" : "skip"}`); await api("POST", `/projects/${id}/discovery/review`); }
await api("POST", `/projects/${P.done}/discovery/complete`, { accept_assumptions: true });
setMode("unconfigured"); await api("POST", `/projects/${P.failed}/discovery`); setMode("ok");

const out = { overflow: {}, axe: {}, keyboard: {}, network: {} };
const states = [["awaiting", `/projects/${P.awaiting}/discovery`], ["review", `/projects/${P.review}/discovery`], ["completed", `/projects/${P.done}/discovery`], ["not_started", `/projects/${P.fresh}/discovery`], ["failed", `/projects/${P.failed}/discovery`], ["overview+callout", `/projects/${P.awaiting}/overview`]];
// network per fresh page load (production build => no StrictMode doubles)
for (const [name, path] of [states[0], states[5]]) { log.requests.length = 0; await page.goto(BASE + path); await sleep(1200); out.network[name] = summary(log).requests; }
// axe
for (const [name, path] of states) {
  await page.goto(BASE + path); await sleep(900);
  if (name === "review") { await btn(page, "Edit answers"); await sleep(300); }
  await page.addScriptTag({ path: "node_modules/axe-core/axe.min.js" });
  const v = await page.evaluate(async () => (await axe.run()).violations.map((x) => ({ id: x.id, impact: x.impact, n: x.nodes.length, first: x.nodes[0].target.join(" ") })));
  out.axe[name] = v.length ? v : "0 violations";
}
// overflow inside <main> at 4 viewports
for (const [w, h] of [[1440, 900], [1280, 720], [768, 1024], [390, 844]]) {
  await page.setViewport({ width: w, height: h });
  for (const [name, path] of states) {
    await page.goto(BASE + path); await sleep(500);
    const m = await page.evaluate(() => { const main = document.querySelector("main"); return { main: main.scrollWidth - main.clientWidth, doc: document.documentElement.scrollWidth - innerWidth }; });
    if (m.main > 0 || m.doc > 0) out.overflow[`${w}/${name}`] = m;
    if (w === 390 && (name === "awaiting" || name === "review")) await page.screenshot({ path: `shots/d-390-${name}.png` });
  }
}
await page.setViewport({ width: 1440, height: 900 });
// keyboard on the question form
await page.goto(BASE + states[0][1]); await page.waitForSelector("textarea"); await page.evaluate(() => document.activeElement.blur());
const stops = []; for (let i = 0; i < 40 && stops.filter((s) => s.startsWith("button:Review")).length === 0; i++) { await page.keyboard.press("Tab"); stops.push(await page.evaluate(() => { const e = document.activeElement, cs = getComputedStyle(e); const ring = (cs.outlineStyle !== "none" && parseFloat(cs.outlineWidth) > 0) || cs.boxShadow !== "none"; return `${e.tagName.toLowerCase()}:${(e.getAttribute("aria-label") || e.value || e.innerText || "").toString().slice(0, 30)}${ring ? "" : " [NO RING]"}`; })); }
out.keyboard.tabStops = stops.filter((s) => !s.startsWith("a:") && !s.startsWith("button:Sign") && !s.startsWith("button:Toggle"));
out.keyboard.noRing = stops.filter((s) => s.includes("NO RING"));
await page.focus('input[type=checkbox]'); await page.keyboard.press("Space"); out.keyboard.spaceTogglesCheckbox = await page.$eval("input[type=checkbox]", (e) => e.checked);
await page.focus('input[type=radio]'); await page.keyboard.press("ArrowDown"); out.keyboard.arrowMovesRadio = await page.evaluate(() => document.activeElement.type === "radio");
await browser.close();
console.log(JSON.stringify({ ...out, pageerrors: log.pageerrors, consoleMsgs: [...new Set(log.console)] }, null, 1));
