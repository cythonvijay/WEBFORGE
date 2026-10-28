import { AuthProvider } from "../features/auth/AuthProvider";

export function Providers({ children }: { children: React.ReactNode }) {
  return <AuthProvider>{children}</AuthProvider>;
}
