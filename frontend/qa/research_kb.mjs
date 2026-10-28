import fs from "node:fs";
import { launch, sleep, btn, typeInto, waitPath } from "./lib.mjs";
const BASE = process.env.BASE; fs.writeFileSync("/tmp/qa/provider_mode", "ok");
const { browser, page } = await launch(1440, 900);
const api = (m, p, b) => page.evaluate(async (m, p, b) => { const r = await fetch("/api" + p, { method: m, headers: { "Content-Type": "application/json" }, body: b ? JSON.stringify(b) : undefined }); return r.json(); }, m, p, b);
await page.goto(BASE + "/register"); await typeInto(page, "Email", `qa-k-${Date.now()}@example.com`); await typeInto(page, "Password", "password123"); await btn(page, "Create account"); await waitPath(page, "^/projects$");
const p = await api("POST", "/projects", { name: "KB" }); await api("PUT", `/projects/${p.id}/brain/idea`, { value: { raw: "A platform for local store owners.", product_name: "P", product_type: "t", problem: "x", features: [], assumptions: [], open_questions: [] } });
await api("POST", `/projects/${p.id}/research/generate`, {}); await page.goto(`${BASE}/projects/${p.id}/research`); await page.waitForSelector("h1"); await sleep(600);
await page.click("main h1");
const stops = []; for (let i = 0; i < 60; i++) { await page.keyboard.press("Tab"); stops.push(await page.evaluate(() => { const e = document.activeElement, cs = getComputedStyle(e); return { el: `${e.tagName.toLowerCase()}:${(e.getAttribute("aria-label") || e.innerText || "").replace(/\s+/g, " ").slice(0, 34)}`, ring: (cs.outlineStyle !== "none" && parseFloat(cs.outlineWidth) > 0) || cs.boxShadow !== "none" }; })); }
const has = (s) => stops.some((x) => x.el.includes(s));
console.log(JSON.stringify({ submit: has("Submit for review"), regenerate: has("Regenerate report"), editFinding: has("Edit finding f-1"), flag: has("Flag for follow-up"), deleteFinding: has("Delete finding f-1"), addFinding: has("Add finding"), addSource: has("Add source"), viewVersion: has("View version 1"), noRing: stops.filter((x) => !x.ring).map((x) => x.el), firstStops: stops.slice(0, 6).map((x) => x.el) }, null, 1));
await browser.close();
