import fs from "node:fs";
import { launch, sleep, waitText, waitPath, btn, typeInto, summary } from "./lib.mjs";
const BASE = process.env.BASE, TAG = process.env.TAG;
const { browser, page, log } = await launch(1440, 900);
const axeSrc = "node_modules/axe-core/axe.min.js";
const email = `qa-r-${Date.now()}@example.com`;
await page.goto(BASE + "/register"); await typeInto(page, "Email", email); await typeInto(page, "Password", "password123"); await btn(page, "Create account"); await waitPath(page, "^/projects$");
const mk = (name, description) => page.evaluate(async (n, d) => (await (await fetch("/api/projects", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ name: n, description: d }) })).json()).id, name, description);
const ids = [await mk("Local Store Builder", "A platform that helps small local businesses create and manage online stores without technical knowledge."),
  await mk("Enterprise multi-tenant storefront builder for independent local businesses across regions with localized payments, tax handling, shipping integrations and inventory sync for every channel", "x ".repeat(350).trim()),
  await mk("x".repeat(120), "")];
await page.evaluate(async (id) => { for (const [s, st] of [["research", "complete"], ["product", "complete"], ["ux", "in_progress"]]) await fetch(`/api/projects/${id}/stages/${s}`, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ status: st }) }); }, ids[0]);
await page.evaluate(async (id) => fetch(`/api/projects/${id}/stages/research`, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ status: "blocked" }) }), ids[2]);

const offenders = () => page.evaluate(() => {
  const W = innerWidth, out = [];
  for (const el of document.querySelectorAll("body *")) {
    const r = el.getBoundingClientRect(); if (!r.width || getComputedStyle(el).position === "fixed") continue;
    if (r.right > W + 1) { let p = el.parentElement, clipped = false; while (p) { const o = getComputedStyle(p).overflowX; if (o === "auto" || o === "scroll" || o === "hidden") { clipped = true; break; } p = p.parentElement; } if (!clipped) out.push(`${el.tagName}.${String(el.className).slice(0, 30)} right=${Math.round(r.right)}`); }
  }
  return out.slice(0, 5);
});
const pages = [["projects", "/projects"], ["overview", `/projects/${ids[0]}/overview`], ["overview-longname", `/projects/${ids[1]}/overview`], ["overview-nospace", `/projects/${ids[2]}/overview`], ["coming-soon", `/projects/${ids[0]}/research`], ["settings", "/settings"]];
const report = {};
for (const [w, h] of [[1440, 900], [1280, 720], [768, 1024], [390, 844]]) {
  await page.setViewport({ width: w, height: h });
  for (const [name, path] of pages) {
    await page.goto(BASE + path); await sleep(700); await page.waitForSelector("main h1, main h2", { timeout: 8000 });
    const sw = await page.evaluate(() => document.documentElement.scrollWidth - innerWidth);
    if (sw > 0 || (await offenders()).length) report[`${w}/${name}`] = { hOverflowPx: sw, offenders: await offenders() };
    await page.screenshot({ path: `shots/${TAG}-${w}-${name}.png`, fullPage: true });
  }
  // dialogs
  await page.goto(BASE + "/projects"); await waitText(page, "Local Store");
  try { await btn(page, "New project"); } catch (e) { report[`${w}/new-project-click`] = "FAILED: " + String(e.message).slice(0, 80); await page.screenshot({ path: `shots/${TAG}-${w}-FAIL.png` }); continue; }
  await sleep(300); await page.screenshot({ path: `shots/${TAG}-${w}-dialog-create.png` });
  const dsw = await page.evaluate(() => document.documentElement.scrollWidth - innerWidth); if (dsw > 0) report[`${w}/dialog`] = { hOverflowPx: dsw };
  await page.keyboard.press("Escape");
  if (w < 768) { await page.goto(BASE + `/projects/${ids[0]}/overview`); await sleep(600); await btn(page, "Toggle navigation"); await sleep(300); await page.screenshot({ path: `shots/${TAG}-${w}-sidebar-open.png` }); }
}
// axe at desktop
await page.setViewport({ width: 1440, height: 900 });
const axeResults = {};
const ctxs = [["projects", "/projects", null], ["projects+dialog", "/projects", "New project"], ["overview", `/projects/${ids[0]}/overview`, null], ["coming-soon", `/projects/${ids[0]}/research`, null], ["settings", "/settings", null]];
for (const [name, path, open] of ctxs) {
  await page.goto(BASE + path); await sleep(800); if (open) { await btn(page, open); await sleep(300); }
  await page.addScriptTag({ path: axeSrc });
  const r = await page.evaluate(async () => { const x = await axe.run(); return x.violations.map((v) => ({ id: v.id, impact: v.impact, n: v.nodes.length, first: v.nodes[0].target.join(" "), help: v.help })); });
  axeResults[name] = r; if (open) await page.keyboard.press("Escape");
}
for (const [name, path] of [["login", "/login"], ["register", "/register"]]) {
  await page.evaluate(() => fetch("/api/auth/logout", { method: "POST" })); await page.goto(BASE + path); await sleep(800);
  await page.addScriptTag({ path: axeSrc });
  axeResults[name] = await page.evaluate(async () => (await axe.run()).violations.map((v) => ({ id: v.id, impact: v.impact, n: v.nodes.length, first: v.nodes[0].target.join(" "), help: v.help })));
}
await browser.close();
console.log(JSON.stringify({ overflow: report, axe: axeResults, ...summary(log) }, null, 1));
