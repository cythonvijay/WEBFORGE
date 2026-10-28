import { useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { Alert } from "../components/ui/Alert";
import { Button } from "../components/ui/Button";
import { TextField } from "../components/ui/Fields";
import { useAuth } from "../features/auth/AuthProvider";

const EMAIL = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

export function AuthForm({ mode }: { mode: "login" | "register" }) {
  const { login, register } = useAuth();
  const navigate = useNavigate();
  const from = (useLocation().state as { from?: string } | null)?.from ?? "/projects";
  const isLogin = mode === "login";
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [errors, setErrors] = useState<{ email?: string; password?: string }>({});
  const [serverError, setServerError] = useState("");
  const [busy, setBusy] = useState(false);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    const next: typeof errors = {};
    if (!EMAIL.test(email.trim())) next.email = "Enter a valid email address.";
    if (!password) next.password = "Enter your password.";
    else if (!isLogin && password.length < 8) next.password = "Use at least 8 characters.";
    setErrors(next);
    setServerError("");
    if (next.email || next.password) return;
    setBusy(true);
    try {
      await (isLogin ? login : register)(email.trim(), password);
      navigate(from, { replace: true });
    } catch (err) {
      setServerError(err instanceof Error ? err.message : "Something went wrong.");
      setBusy(false);
    }
  }

  return (
    <main className="flex min-h-full items-center justify-center p-4">
      <div className="w-full max-w-sm">
        <p className="mb-6 text-center text-lg font-semibold tracking-tight">WebForge</p>
        <div className="rounded-lg border border-slate-200 bg-white p-6">
          <h1 className="mb-4 text-lg font-semibold">{isLogin ? "Welcome back" : "Create your WebForge account"}</h1>
          <form onSubmit={onSubmit} noValidate className="space-y-4">
            {serverError && <Alert tone="error">{serverError}</Alert>}
            <TextField label="Email" type="email" autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} error={errors.email} />
            <TextField label="Password" type="password" autoComplete={isLogin ? "current-password" : "new-password"} value={password}
              onChange={(e) => setPassword(e.target.value)} error={errors.password} hint={isLogin ? undefined : "At least 8 characters."} />
            <Button type="submit" variant="primary" loading={busy} className="w-full">
              {busy ? (isLogin ? "Signing in…" : "Creating account…") : isLogin ? "Sign in" : "Create account"}
            </Button>
          </form>
        </div>
        <p className="mt-4 text-center text-slate-600">
          {isLogin ? <>Don't have an account? <Link className="font-medium text-blue-700 underline" to="/register">Create one</Link></>
            : <>Already have an account? <Link className="font-medium text-blue-700 underline" to="/login">Sign in</Link></>}
        </p>
      </div>
    </main>
  );
}
