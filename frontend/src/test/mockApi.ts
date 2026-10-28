import { vi } from "vitest";

export interface Reply { status?: number; body?: unknown; networkError?: boolean }
type Req = { body: any; path: string; params: Record<string, string> };
type Handler = Reply | ((req: Req) => Reply | Promise<Reply>);

export const unhandled: string[] = [];

/** Stubs global fetch with route handlers ("METHOD /path/:param"). Unrouted requests are recorded and fail the test. */
export function mockApi(routes: Record<string, Handler>) {
  const compiled = Object.entries(routes).map(([key, h]) => {
    const [method, pattern] = key.split(" ");
    const names: string[] = [];
    const re = new RegExp("^" + pattern.replace(/:(\w+)/g, (_, n) => { names.push(n); return "([^/]+)"; }) + "$");
    return { method, re, names, h };
  });
  const calls: { method: string; path: string; body: any; query: string }[] = [];

  vi.stubGlobal("fetch", vi.fn(async (input: string, init?: RequestInit) => {
    const path = new URL(input, "http://localhost").pathname.replace(/^\/api/, "");
    const method = init?.method ?? "GET";
    const body = init?.body ? JSON.parse(String(init.body)) : undefined;
    calls.push({ method, path, body, query: new URL(input, "http://localhost").search });
    for (const r of compiled) {
      const m = r.method === method ? r.re.exec(path) : null;
      if (!m) continue;
      const params = Object.fromEntries(r.names.map((n, i) => [n, m[i + 1]]));
      const reply = typeof r.h === "function" ? await r.h({ body, path, params }) : r.h;
      if (reply.networkError) throw new TypeError("Failed to fetch");
      const status = reply.status ?? 200;
      return new Response(status === 204 ? null : JSON.stringify(reply.body ?? {}), { status, headers: { "Content-Type": "application/json" } });
    }
    unhandled.push(`${method} ${path}`);
    throw new Error(`Unhandled request: ${method} ${path}`);
  }));

  return {
    calls,
    count: (method: string, path: string) => calls.filter((c) => c.method === method && c.path === path).length,
    last: (method: string, path: string) => calls.filter((c) => c.method === method && c.path === path).at(-1),
  };
}
