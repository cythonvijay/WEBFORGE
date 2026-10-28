import { Button } from "../components/ui/Button";
import { useAuth } from "../features/auth/AuthProvider";

export default function SettingsPage() {
  const { user, logout } = useAuth();
  return (
    <div className="max-w-xl">
      <h1 className="mb-4 text-xl font-semibold">Settings</h1>
      <section className="rounded-lg border border-slate-200 bg-white p-4">
        <h2 className="text-sm font-semibold">Account</h2>
        <dl className="mt-2 grid grid-cols-[6rem_1fr] gap-y-1">
          <dt className="text-slate-500">Email</dt><dd>{user?.email}</dd>
        </dl>
        <Button className="mt-4" onClick={() => void logout()}>Sign out</Button>
      </section>
      <p className="mt-4 text-slate-600">More settings (AI provider, integrations) are not implemented yet.</p>
    </div>
  );
}
