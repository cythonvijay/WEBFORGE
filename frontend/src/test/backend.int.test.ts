// @vitest-environment node
/**
 * Contract test: the real API client against a real running backend (no mocks).
 * Skipped unless WEBFORGE_API_URL is set, e.g. WEBFORGE_API_URL=http://127.0.0.1:8000/api npm run test:integration
 * The backend must be migrated and should have no AI key configured (the intake 503 case is asserted).
 */
import { describe, expect, it } from "vitest";
import { ApiError, createApiClient } from "../lib/api";

const URL_BASE = process.env.WEBFORGE_API_URL;

/** Minimal browser-like cookie jar: honours Path and Max-Age=0 so httpOnly cookie behaviour is exercised for real. */
function jarClient() {
  const jar = new Map<string, { value: string; path: string }>();
  const fetchImpl = async (url: string, init?: RequestInit) => {
    const path = new globalThis.URL(url).pathname;
    const cookie = [...jar].filter(([, c]) => path.startsWith(c.path)).map(([k, c]) => `${k}=${c.value}`).join("; ");
    const res = await fetch(url, { ...init, headers: { ...(init?.headers as Record<string, string>), ...(cookie ? { cookie } : {}) } });
    for (const sc of res.headers.getSetCookie()) {
      const [pair, ...attrs] = sc.split(";").map((x) => x.trim());
      const [name, ...v] = pair.split("=");
      const a = Object.fromEntries(attrs.map((x) => x.split("=")).map(([k, ...r]) => [k.toLowerCase(), r.join("=")]));
      if (a["max-age"] === "0" || v.join("=") === "" || v.join("=") === '""') jar.delete(name);
      else jar.set(name, { value: v.join("="), path: a.path ?? "/" });
    }
    return res;
  };
  return { api: createApiClient({ baseUrl: URL_BASE!, fetchImpl }), jar };
}

const errOf = (p: Promise<unknown>) => p.then(() => { throw new Error("expected an ApiError"); }, (e) => e as ApiError);

describe.skipIf(!URL_BASE)("real backend contract", () => {
  it("covers auth, projects, lifecycle, brain, intake failure and session refresh", async () => {
    const { api, jar } = jarClient();
    const email = `int-${Date.now()}@example.com`;

    expect(await errOf(api.get("/auth/me"))).toMatchObject({ kind: "unauthorized" });
    await api.post("/auth/register", { email, password: "password123" });
    expect(await api.get("/auth/me")).toMatchObject({ email });
    expect(await errOf(api.post("/auth/login", { email, password: "wrongwrong" }))).toMatchObject({ kind: "unauthorized", message: "Invalid email or password" });
    expect(await errOf(api.post("/auth/register", { email, password: "short" }))).toMatchObject({ kind: "validation" });

    const p = await api.post<{ id: string; status: string }>("/projects", { name: "Contract test", description: "" });
    expect(p.status).toBe("active");
    expect(await api.patch<{ name: string }>(`/projects/${p.id}`, { name: "Renamed" })).toMatchObject({ name: "Renamed" });

    // Overview shape the UI depends on (incl. dependency data the lifecycle map renders).
    const ov = await api.get<any>(`/projects/${p.id}/overview`);
    expect(ov.stages).toHaveLength(19);
    expect(ov.stages.find((s: any) => s.stage === "product")).toMatchObject({ status: "not_started", depends_on: ["research"], unmet_dependencies: ["research"] });
    expect(ov).toMatchObject({ progress: 0, completed: [], in_progress: [], needs_review: [], blocked: [], next_action: "research" });
    expect(ov.recent_changes[0]).toMatchObject({ version: 1, change_type: "created" });

    expect(await errOf(api.put(`/projects/${p.id}/stages/product`, { status: "in_progress" }))).toMatchObject({ kind: "conflict" });
    await api.put(`/projects/${p.id}/stages/research`, { status: "complete" });
    const ov2 = await api.get<any>(`/projects/${p.id}/overview`);
    expect(ov2).toMatchObject({ completed: ["research"], next_action: "product" });
    expect(ov2.progress).toBeGreaterThan(0);

    // Intake without an AI key: 503 and nothing persisted.
    const before = await api.get<any>(`/projects/${p.id}/brain`);
    expect(await errOf(api.post(`/projects/${p.id}/intake`, { idea: "A marketplace for local photographers" }))).toMatchObject({ status: 503, kind: "unavailable" });
    expect((await api.get<any>(`/projects/${p.id}/brain`)).version).toBe(before.version);

    // Research endpoints (no idea yet, no AI key): honest empty state, explicit refusal, nothing created.
    const rs0 = await api.get<any>(`/projects/${p.id}/research`);
    expect(rs0).toMatchObject({ status: "not_started", current: null, history: [], mode: "preliminary", can_generate: false });
    expect(rs0.limitations[0]).toMatch(/No web research was performed/);
    expect(await errOf(api.post(`/projects/${p.id}/research/generate`, { supersede: false }))).toMatchObject({ kind: "conflict" });
    expect(await errOf(api.get(`/projects/${p.id}/research/reports/1`))).toMatchObject({ kind: "not_found" });

    // Access token vanishes (expiry): the client must refresh via the httpOnly cookie and rotate it.
    const oldRefresh = jar.get("refresh_token")!.value;
    jar.delete("access_token");
    expect(await api.get<unknown[]>("/projects")).toHaveLength(1);
    expect(jar.get("refresh_token")!.value).not.toBe(oldRefresh);

    // Another user cannot see this project.
    const other = jarClient();
    await other.api.post("/auth/register", { email: `other-${Date.now()}@example.com`, password: "password123" });
    expect(await errOf(other.api.get(`/projects/${p.id}`))).toMatchObject({ kind: "not_found" });

    await api.delete(`/projects/${p.id}`);
    expect(await errOf(api.get(`/projects/${p.id}`))).toMatchObject({ kind: "not_found" });
    await api.post("/auth/logout");
    expect(await errOf(api.get("/auth/me"))).toMatchObject({ kind: "unauthorized" });
  });
});
