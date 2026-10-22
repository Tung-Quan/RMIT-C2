import { ShieldAlert } from "lucide-react";
import { Link } from "react-router-dom";

import { AppFooter } from "../components/AppFooter";

export function Unauthorized() {
  return (
    <div className="app-shell flex min-h-screen flex-col px-4 py-8">
      <div className="flex flex-1 items-center justify-center">
        <div className="w-full max-w-md rounded-2xl border border-[var(--atlas-line)] bg-[rgba(255,253,246,0.82)] p-6 text-center shadow-[var(--atlas-shadow)] backdrop-blur">
          <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-xl bg-rose-50 text-rose-700">
            <ShieldAlert className="h-6 w-6" />
          </div>
          <h1 className="mt-4 text-xl font-semibold text-[var(--atlas-night)]">Unauthorized</h1>
          <p className="mt-2 text-sm text-[var(--atlas-muted)]">
            Your account does not have access to that page.
          </p>
          <Link
            to="/"
            className="mt-5 inline-flex items-center justify-center rounded-lg bg-[var(--atlas-night)] px-4 py-2.5 text-sm font-semibold text-white hover:bg-[var(--candidate-primary-hover)]"
          >
            Go back
          </Link>
        </div>
      </div>
      <div className="mx-auto w-full max-w-5xl">
        <AppFooter tone="app" />
      </div>
    </div>
  );
}
