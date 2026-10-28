export type ErrorKind =
  | "network" | "unauthorized" | "forbidden" | "not_found" | "conflict"
  | "validation" | "server" | "bad_gateway" | "unavailable" | "unknown";

export class ApiError extends Error {
  constructor(public status: number, message: string, public kind: ErrorKind, public detail?: unknown) {
    super(message);
    this.name = "ApiError";
  }
}

const KIND: Record<number, ErrorKind> = {
  401: "unauthorized", 403: "forbidden", 404: "not_found", 409: "conflict",
  422: "validation", 500: "server", 502: "bad_gateway", 503: "unavailable",
};
const FALLBACK: Record<ErrorKind, string> = {
  network: "Can't reach the WebForge server. Check your connection and try again.",
  unauthorized: "You need to sign in.",
  forbidden: "You don't have permission to do that.",
  not_found: "We couldn't find that.",
  conflict: "That action conflicts with the current state.",
  validation: "Some of the information isn't valid.",
  server: "Something went wrong on our side. Please try again.",
  bad_gateway: "An upstream service returned an invalid response.",
  unavailable: "This feature is temporarily unavailable.",
  unknown: "Something went wrong.",
};

/** Turn a FastAPI error body into one readable sentence. Never surfaces 5xx internals. */
function messageFrom(status: number, kind: ErrorKind, body: unknown): string {
  if (status >= 500 && status !== 502 && status !== 503) return FALLBACK[kind];
  const detail = (body as { detail?: unknown } | null)?.detail;
  if (typeof detail === "string") return detail;
  if (detail && typeof detail === "object" && "message" in detail && typeof (detail as { message?: unknown }).message === "string") {
    return (detail as { message: string }).message;
  }
  if (Array.isArray(detail) && detail.length) {
    const d = detail[0] as { msg?: string; loc?: unknown[] };
    const field = d.loc && d.loc.length > 1 ? String(d.loc[d.loc.length - 1]) : "";
    return field && d.msg ? `${field}: ${d.msg}` : d.msg ?? FALLBACK[kind];
  }
  return FALLBACK[kind];
}

type FetchLike = (input: string, init?: RequestInit) => Promise<Response>;
type Method = "GET" | "POST" | "PUT" | "PATCH" | "DELETE";

export interface ApiClientOptions {
  baseUrl: string;
  fetchImpl?: FetchLike;
  onUnauthenticated?: () => void;
}

export function createApiClient(opts: ApiClientOptions) {
  const base = opts.baseUrl.replace(/\/+$/, "");
  let onUnauthenticated = opts.onUnauthenticated;
  let refreshing: Promise<boolean> | null = null;
  const doFetch: FetchLike = (u, i) => (opts.fetchImpl ?? ((a, b) => globalThis.fetch(a, b)))(u, i);

  async function raw(method: Method, path: string, body?: unknown): Promise<Response> {
    try {
      return await doFetch(base + path, {
        method,
        credentials: "include",
        headers: body !== undefined ? { "Content-Type": "application/json" } : undefined,
        body: body !== undefined ? JSON.stringify(body) : undefined,
      });
    } catch {
      throw new ApiError(0, FALLBACK.network, "network");
    }
  }

  /** One shared refresh at a time; the backend rotates tokens, so concurrent refreshes would trip reuse detection. */
  function refresh(): Promise<boolean> {
    refreshing ??= raw("POST", "/auth/refresh")
      .then((r) => r.ok)
      .catch(() => false)
      .finally(() => { refreshing = null; });
    return refreshing;
  }

  async function request<T>(method: Method, path: string, body?: unknown): Promise<T> {
    let res = await raw(method, path, body);
    if (res.status === 401 && !path.startsWith("/auth/")) {
      if (await refresh()) res = await raw(method, path, body);
      if (res.status === 401) onUnauthenticated?.();
    }
    if (res.status === 204) return undefined as T;
    let data: unknown = null;
    try { data = await res.json(); } catch { /* non-JSON body */ }
    if (!res.ok) {
      const kind = KIND[res.status] ?? (res.status >= 500 ? "server" : "unknown");
      throw new ApiError(res.status, messageFrom(res.status, kind, data), kind, (data as { detail?: unknown } | null)?.detail);
    }
    return data as T;
  }

  return {
    get: <T>(p: string) => request<T>("GET", p),
    post: <T>(p: string, b?: unknown) => request<T>("POST", p, b ?? {}),
    put: <T>(p: string, b?: unknown) => request<T>("PUT", p, b ?? {}),
    patch: <T>(p: string, b?: unknown) => request<T>("PATCH", p, b ?? {}),
    delete: <T = void>(p: string) => request<T>("DELETE", p),
    refresh,
    setUnauthenticatedHandler: (fn: () => void) => { onUnauthenticated = fn; },
  };
}

export const api = createApiClient({ baseUrl: import.meta.env.VITE_API_BASE_URL ?? "/api" });
