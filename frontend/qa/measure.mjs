import { launch, sleep, waitText, waitPath, btn, typeInto } from "./lib.mjs";
const BASE = process.env.BASE;
const { browser, page, log } = await launch(1440, 900);
const email = `qa-m-${Date.now()}@example.com`;
await page.goto(BASE + "/register"); await typeInto(page, "Email", email); await typeInto(page, "Password", "password123"); await btn(page, "Create account"); await waitPath(page, "^/projects$");
const mk = (n, d) => page.evaluate(async (name, description) => (await (await fetch("/api/projects", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ name, description }) })).json()).id, n, d);
const ids = [await mk("Local Store Builder", "A platform that helps small local businesses create and manage online stores."), await mk("Enterprise multi-tenant storefront builder for independent local businesses across regions with localized payments, tax handling, shipping integrations and inventory sync for every channel", "x ".repeat(350).trim()), await mk("x".repeat(120), "")];
const pages = [["projects", "/projects"], ["overview", `/projects/${ids[0]}/overview`], ["overview-longname", `/projects/${ids[1]}/overview`], ["overview-nospace", `/projects/${ids[2]}/overview`], ["coming-soon", `/projects/${ids[0]}/research`], ["settings", "/settings"]];
const res = {};
for (const [w, h] of [[1440, 900], [1280, 720], [768, 1024], [390, 844]]) {
  await page.setViewport({ width: w, height: h });
  for (const [name, path] of pages) {
    await page.goto(BASE + path); await page.waitForSelector("main h1, main h2"); await sleep(500);
    const m = await page.evaluate(() => { const main = document.querySelector("main"); const over = []; for (const el of main.querySelectorAll("*")) { const r = el.getBoundingClientRect(); const mr = main.getBoundingClientRect(); if (r.width && r.right > mr.right + 1) { let p = el.parentElement, clipped = false; while (p && p !== main) { const o = getComputedStyle(p).overflowX; if (o === "auto" || o === "scroll" || o === "hidden") { clipped = true; break; } p = p.parentElement; } if (!clipped) over.push(`${el.tagName}.${String(el.className).slice(0, 25)}`); } } return { mainOverflowPx: main.scrollWidth - main.clientWidth, docOverflowPx: document.documentElement.scrollWidth - innerWidth, offenders: over.slice(0, 3) }; });
    if (m.mainOverflowPx > 0 || m.docOverflowPx > 0 || m.offenders.length) res[`${w}/${name}`] = m;
  }
}
// 204 + ERR_ABORTED check without navigating away
await page.setViewport({ width: 1440, height: 900 }); await page.goto(BASE + "/settings"); await waitText(page, "Account");
log.failed.length = 0; await btn(page, "Sign out"); await sleep(2000);
res.uiLogoutFailedRequests = [...log.failed];
await browser.close(); console.log(JSON.stringify(res, null, 1));
