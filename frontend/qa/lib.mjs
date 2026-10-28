import chromium from "@sparticuz/chromium";
import puppeteer from "puppeteer-core";
export const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
export async function launch(width = 1440, height = 900) {
  const browser = await puppeteer.launch({ executablePath: await chromium.executablePath(), args: [...chromium.args, "--no-sandbox"], headless: "shell", defaultViewport: { width, height } });
  const page = await browser.newPage();
  const log = { console: [], pageerrors: [], failed: [], requests: [] };
  page.on("console", (m) => { if (["error", "warning"].includes(m.type())) log.console.push(`${m.type()}: ${m.text()}`); });
  page.on("pageerror", (e) => log.pageerrors.push(String(e)));
  page.on("requestfailed", (r) => log.failed.push(`${r.method()} ${r.url()} ${r.failure()?.errorText}`));
  page.on("response", (r) => {
    const u = new URL(r.url());
    if (u.pathname.startsWith("/api")) log.requests.push({ m: r.request().method(), p: u.pathname, s: r.status(), body: r.request().postData() });
    else if (r.status() >= 400) log.failed.push(`${r.status()} ${r.url()}`);
  });
  return { browser, page, log };
}
export const waitText = (page, t, timeout = 8000) => page.waitForFunction((x) => document.body.innerText.includes(x), { timeout }, t);
export const waitPath = (page, re, timeout = 8000) => page.waitForFunction((s) => new RegExp(s).test(location.pathname), { timeout }, re);
export const btn = (page, name) => page.locator(`::-p-aria([role="button"][name="${name}"])`).setTimeout(6000).click();
export const typeInto = async (page, label, text) => { const el = await page.waitForSelector(`::-p-aria(${label})`); await el.focus(); await page.keyboard.down("Control"); await page.keyboard.press("a"); await page.keyboard.up("Control"); await page.keyboard.press("Backspace"); await el.type(text); };
export const overflow = (page) => page.evaluate(() => ({ scrollW: document.documentElement.scrollWidth, innerW: innerWidth, bodyScrollW: document.body.scrollWidth }));
export async function cookies(page) { const c = await page.createCDPSession(); return (await c.send("Network.getAllCookies")).cookies.map((x) => ({ name: x.name, httpOnly: x.httpOnly, path: x.path, sameSite: x.sameSite, secure: x.secure })); }
export const storage = (page) => page.evaluate(() => ({ local: { ...localStorage }, session: { ...sessionStorage }, documentCookie: document.cookie }));
export function summary(log) {
  const g = {}; for (const r of log.requests) { const k = `${r.m} ${r.p.replace(/[0-9a-f-]{36}/g, ":id")} → ${r.s}`; g[k] = (g[k] || 0) + 1; }
  return { console: log.console, pageerrors: log.pageerrors, failed: log.failed, requests: g };
}
