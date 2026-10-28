import { Navigate, Outlet, useLocation } from "react-router-dom";
import { ErrorState, LoadingState } from "../../components/feedback/States";
import { useAuth } from "./AuthProvider";

export function RequireAuth() {
  const { status, signedOut, retry } = useAuth();
  const loc = useLocation();
  if (status === "loading") return <LoadingState label="Loading…" />;
  if (status === "error") return <div className="mx-auto max-w-md p-6"><ErrorState title="Can't reach WebForge" message="We couldn't check your session. Check your connection and try again." onRetry={retry} /></div>;
  if (status === "anonymous") return <Navigate to="/login" replace state={signedOut ? undefined : { from: loc.pathname }} />;
  return <Outlet />;
}

export function PublicOnly({ children }: { children: React.ReactNode }) {
  const { status } = useAuth();
  if (status === "loading") return <LoadingState label="Loading…" />;
  if (status === "authenticated") return <Navigate to="/projects" replace />;
  return <>{children}</>;
}
