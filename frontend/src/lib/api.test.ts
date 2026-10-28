import { describe, expect, it, vi } from "vitest";
import { ApiError, createApiClient } from "./api";

const fail = (p: Promise<unknown>) => p.then(() => { throw new Error("expected an ApiError"); }, (e) => e as ApiError);
const res = (status: number, body?: unknown) => new Response(status === 204 ? null : JSON.stringify(body ?? {}), { status });

function client(responses: Array<Response | Error>, onUnauthenticated = vi.fn()) {
  const queue = [...responses];
  const fetchImpl = vi.fn(async (_url: string, _init?: RequestInit) => { const r = queue.shift(); if (!r) throw new Error("unexpected extra request"); if (r instanceof Error) throw r; return r; });
  return { api: createApiClient({ baseUrl: "/api/", fetchImpl, onUnauthenticated }), fetchImpl, onUnauthenticated };
}
const urls = (f: ReturnType<typeof vi.fn>) => f.mock.calls.map((c) => `${(c[1] as RequestInit).method} ${c[0]}`);

describe("api client errors", () => {
  it("turns FastAPI validation arrays into one readable message", async () => {
    const { api } = client([res(422, { detail: [{ loc: ["body", "password"], msg: "String should have at least 8 characters" }] })]);
    const e = await fail(api.post("/auth/register", {}));
    expect(e).toBeInstanceOf(ApiError);
    expect(e).toMatchObject({ status: 422, kind: "validation", message: "password: String should have at least 8 characters" });
  });
  it.each([[409, "conflict"], [404, "not_found"], [503, "unavailable"], [502, "bad_gateway"], [403, "forbidden"]])("classifies %i as %s and keeps the backend message", async (status, kind) => {
    const { api } = client([res(status, { detail: "backend says no" })]);
    expect(await fail(api.get("/x"))).toMatchObject({ status, kind, message: "backend says no" });
  });
  it("never shows 500 internals", async () => {
    const { api } = client([res(500, { detail: "Traceback (most recent call last): ..." })]);
    const e = await fail(api.get("/x"));
    expect(e.kind).toBe("server");
    expect(e.message).not.toMatch(/Traceback/);
  });
  it("reports network failures", async () => {
    const { api } = client([new TypeError("Failed to fetch")]);
    expect(await fail(api.get("/x"))).toMatchObject({ status: 0, kind: "network" });
  });
  it("returns undefined for 204", async () => {
    const { api } = client([res(204)]);
    expect(await api.delete("/x")).toBeUndefined();
  });
});

describe("api client session refresh", () => {
  it("refreshes once on 401 and retries the original request", async () => {
    const { api, fetchImpl } = client([res(401), res(200, { ok: true }), res(200, [{ id: "p1" }])]);
    expect(await api.get("/projects")).toEqual([{ id: "p1" }]);
    expect(urls(fetchImpl)).toEqual(["GET /api/projects", "POST /api/auth/refresh", "GET /api/projects"]);
  });
  it("signals unauthenticated when refresh fails", async () => {
    const { api, onUnauthenticated } = client([res(401), res(401, { detail: "Invalid refresh token" }), ]);
    const e = await fail(api.get("/projects"));
    expect(e.kind).toBe("unauthorized");
    expect(onUnauthenticated).toHaveBeenCalledTimes(1);
  });
  it("shares one refresh between concurrent 401s (tokens rotate, so double refresh would break the session)", async () => {
    let refreshCalls = 0;
    const fetchImpl = vi.fn(async (url: string, init?: RequestInit) => {
      if (url.endsWith("/auth/refresh")) { refreshCalls++; await new Promise((r) => setTimeout(r, 10)); return res(200); }
      return refreshCalls === 0 ? res(401) : res(200, { ok: url });
    });
    const api = createApiClient({ baseUrl: "/api", fetchImpl });
    await Promise.all([api.get("/a"), api.get("/b")]);
    expect(refreshCalls).toBe(1);
  });
  it("never tries to refresh for /auth/* calls (a wrong password is not an expired session)", async () => {
    const { api, fetchImpl } = client([res(401, { detail: "Invalid email or password" })]);
    expect(await fail(api.post("/auth/login", {}))).toMatchObject({ kind: "unauthorized", message: "Invalid email or password" });
    expect(fetchImpl).toHaveBeenCalledTimes(1);
  });
  it("sends credentials so httpOnly cookies are used", async () => {
    const { api, fetchImpl } = client([res(200, {})]);
    await api.get("/x");
    expect((fetchImpl.mock.calls[0][1] as RequestInit).credentials).toBe("include");
  });
});
