import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { ApiError, api } from "../../lib/api";
import type { User } from "../../types/auth";

type Status = "loading" | "authenticated" | "anonymous" | "error";
interface AuthValue {
  status: Status;
  user: User | null;
  /** True after a deliberate sign-out (as opposed to an expired session). */
  signedOut: boolean;
  retry: () => void;
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthValue | null>(null);

/** Session restore: /auth/me; on 401 try one refresh (httpOnly cookie, invisible to JS) and ask again. */
async function restore(): Promise<User | null> {
  try {
    return await api.get<User>("/auth/me");
  } catch (e) {
    if (e instanceof ApiError && e.kind === "unauthorized") {
      if (!(await api.refresh())) return null;
      try { return await api.get<User>("/auth/me"); } catch { return null; }
    }
    throw e;
  }
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [state, setState] = useState<{ status: Status; user: User | null; signedOut?: boolean }>({ status: "loading", user: null });
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let live = true;
    setState({ status: "loading", user: null });
    restore().then(
      (user) => live && setState({ status: user ? "authenticated" : "anonymous", user }),
      () => live && setState({ status: "error", user: null }),
    );
    return () => { live = false; };
  }, [attempt]);

  useEffect(() => {
    api.setUnauthenticatedHandler(() => setState({ status: "anonymous", user: null }));
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    const user = await api.post<User>("/auth/login", { email, password });
    setState({ status: "authenticated", user });
  }, []);
  const register = useCallback(async (email: string, password: string) => {
    const user = await api.post<User>("/auth/register", { email, password });
    setState({ status: "authenticated", user });
  }, []);
  const logout = useCallback(async () => {
    // Start cookie revocation before changing UI state, but never make navigation wait for the network.
    const revokeSession = api.post("/auth/logout");
    setState({ status: "anonymous", user: null, signedOut: true });
    try {
      await revokeSession;
    } catch {
      // Keep the local UI signed out even when the network cannot reach the API.
    }
  }, []);

  const value = useMemo<AuthValue>(
    () => ({ ...state, signedOut: !!state.signedOut, retry: () => setAttempt((a) => a + 1), login, register, logout }),
    [state, login, register, logout],
  );
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside AuthProvider");
  return ctx;
}
