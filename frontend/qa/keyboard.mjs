import { launch, sleep, waitText, waitPath, btn, typeInto, cookies, summary } from "./lib.mjs";
const BASE = process.env.BASE;
const { browser, page, log } = await launch(1440, 900);
const out = {};
const desc = () => page.evaluate(() => { const e = document.activeElement; const cs = getComputedStyle(e);
  return { el: `${e.tagName.toLowerCase()}:${(e.getAttribute("aria-label") || e.innerText || e.id || "").trim().replace(/\s+/g, " ").slice(0, 28)}`, focusVisible: (cs.outlineStyle !== "none" && parseFloat(cs.outlineWidth) > 0) || cs.boxShadow !== "none", inDialog: !!e.closest("[role=dialog]") }; });
const tabs = async (n) => { const r = []; for (let i = 0; i < n; i++) { await page.keyboard.press("Tab"); r.push(await desc()); } return r; };

// login with keyboard only
await page.goto(BASE + "/register"); await sleep(600);
out.registerTabOrder = (await tabs(4)).map((x) => `${x.el}${x.focusVisible ? "" : " [NO FOCUS RING]"}`);
const email = `qa-k-${Date.now()}@example.com`;
await page.goto(BASE + "/register"); await sleep(500);
await page.keyboard.press("Tab"); await page.keyboard.type(email); await page.keyboard.press("Tab"); await page.keyboard.type("password123"); await page.keyboard.press("Enter");
await waitPath(page, "^/projects$"); out.keyboardRegister = "ok";
const mk = (n) => page.evaluate(async (name) => (await (await fetch("/api/projects", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ name, description: "d" }) })).json()).id, n);
const pid = await mk("Keyboard Project"); await mk("Second");
await page.goto(BASE + "/projects"); await waitText(page, "Keyboard Project");

// app shell tab order
await page.evaluate(() => document.activeElement.blur());
out.shellTabOrder = (await tabs(14)).map((x) => `${x.el}${x.focusVisible ? "" : " [NO FOCUS RING]"}`);

// delete dialog: open via keyboard, trap check, escape, focus return
await page.focus('button[aria-label="Delete Keyboard Project"]'); await page.keyboard.press("Enter"); await sleep(300);
out.deleteDialog = { opened: await page.$("[role=dialog]") !== null, firstFocus: await desc() };
const stops = []; for (let i = 0; i < 5; i++) { await page.keyboard.press("Tab"); stops.push(await desc()); }
out.deleteDialog.tabbingStaysInside = stops.map((s) => (s.inDialog ? "in" : "OUT:" + s.el));
await page.keyboard.press("Escape"); await sleep(300);
out.deleteDialog.closedByEscape = await page.$("[role=dialog]") === null;
out.deleteDialog.focusAfterEscape = (await desc()).el;
// create dialog: keyboard flow, cancel, focus return
await page.focus('::-p-aria([role="button"][name="New project"])'); await page.keyboard.press("Enter"); await sleep(300);
out.createDialog = { firstFocus: (await desc()).el };
await page.keyboard.type("Typed"); await page.keyboard.press("Escape"); await sleep(300);
out.createDialog.focusAfterEscape = (await desc()).el;
// click-outside closes
await btn(page, "New project"); await sleep(200); await page.mouse.click(10, 10); await sleep(200);
out.createDialog.closedByBackdropClick = await page.$("[role=dialog]") === null;

// lifecycle + intake reachable by keyboard
await page.goto(BASE + `/projects/${pid}/overview`); await waitText(page, "Lifecycle"); await sleep(400);
await page.evaluate(() => document.activeElement.blur());
const mainStops = new Set(); for (let i = 0; i < 70; i++) { await page.keyboard.press("Tab"); const d = await desc(); mainStops.add(d.el + (d.focusVisible ? "" : " [NO RING]")); }
out.overviewReachable = { selects: [...mainStops].filter((s) => s.startsWith("select:Set status")).length, intake: [...mainStops].some((s) => s.startsWith("textarea")), analyze: [...mainStops].some((s) => s.includes("Analyze idea")), noRing: [...mainStops].filter((s) => s.includes("NO RING")) };

// logout via UI without navigating away
await btn(page, "Sign out"); await sleep(1500);
out.logout = { path: await page.evaluate(() => location.pathname), cookies: await cookies(page), failedRequests: log.failed.filter((f) => f.includes("logout")) };

// mobile sidebar keyboard
await page.setViewport({ width: 390, height: 844 });
await page.goto(BASE + "/login"); await typeInto(page, "Email", email); await typeInto(page, "Password", "password123"); await page.keyboard.press("Enter"); try { await waitPath(page, "^/projects"); } catch (e) { console.log("MOBILE LOGIN STUCK", page.url(), await page.evaluate(() => document.body.innerText.slice(0, 300))); await page.screenshot({ path: "shots/stuck.png" }); throw e; }
await page.goto(BASE + `/projects/${pid}/overview`); await waitText(page, "Lifecycle");
await page.focus('button[aria-label="Toggle navigation"]'); await page.keyboard.press("Enter"); await sleep(300);
out.mobileSidebar = { expanded: await page.$eval('button[aria-label="Toggle navigation"]', (e) => e.getAttribute("aria-expanded")) };
await page.keyboard.press("Escape"); await sleep(200);
out.mobileSidebar.closesOnEscape = (await page.$eval('button[aria-label="Toggle navigation"]', (e) => e.getAttribute("aria-expanded"))) === "false";
await browser.close();
console.log(JSON.stringify({ out, console: log.console.length, pageerrors: log.pageerrors }, null, 1));
