import { BriefcaseBusiness, Building2, Users } from "lucide-react";
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { getErrorMessage } from "../api/client";
import { getHrDashboard } from "../api/hr";
import { Alert } from "../components/Alert";
import { StatCard } from "../components/StatCard";
import { StatusBadge } from "../components/StatusBadge";

export function HrDashboard() {
  const [dashboard, setDashboard] = useState(null);
  const [error, setError] = useState("");
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    async function loadDashboard() {
      setError("");
      try {
        const response = await getHrDashboard();
        setDashboard(response.data);
      } catch (err) {
        setError(getErrorMessage(err));
      } finally {
        setIsLoading(false);
      }
    }

    loadDashboard();
  }, []);

  if (isLoading) return <p className="text-sm text-zinc-500">Loading HR dashboard</p>;

  return (
    <div className="space-y-6">
      <div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-center">
        <div>
          <h1 className="text-2xl font-semibold text-zinc-950">HR dashboard</h1>
          <p className="mt-1 text-sm text-zinc-500">
            Manage company jobs, review applicants, and move people through the hiring pipeline.
          </p>
        </div>
        <Link
          to="/hr/jobs/new"
          className="inline-flex items-center justify-center rounded-lg bg-zinc-900 px-4 py-2.5 text-sm font-semibold text-white hover:bg-zinc-800"
        >
          New job posting
        </Link>
      </div>

      {error && <Alert>{error}</Alert>}

      {dashboard && (
        <>
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            <StatCard icon={Building2} label="Company profile" value={dashboard.company ? "Ready" : "Missing"} />
            <StatCard icon={BriefcaseBusiness} label="Total jobs" value={dashboard.total_jobs} tone="sky" />
            <StatCard icon={BriefcaseBusiness} label="Published jobs" value={dashboard.published_jobs} tone="emerald" />
            <StatCard icon={Users} label="Applicants" value={dashboard.total_applicants} tone="amber" />
          </div>

          {!dashboard.company && (
            <Alert>
              Create your company profile before publishing jobs or reviewing applicants.
            </Alert>
          )}

          <div className="grid gap-6 xl:grid-cols-[0.9fr_1.1fr]">
            <section className="rounded-lg border border-zinc-200 bg-white p-5 shadow-sm">
              <div className="flex items-center justify-between gap-4">
                <h2 className="text-base font-semibold text-zinc-950">Company</h2>
                <Link to="/hr/company" className="text-sm font-medium text-zinc-700 hover:text-zinc-950">
                  {dashboard.company ? "Manage" : "Create"}
                </Link>
              </div>
              {dashboard.company ? (
                <div className="mt-4 space-y-2 text-sm text-zinc-700">
                  <p className="text-base font-semibold text-zinc-950">{dashboard.company.name}</p>
                  <p>{dashboard.company.industry || "Industry not listed"}</p>
                  <p>{dashboard.company.location || "Location not listed"}</p>
                  <p className="text-zinc-600">{dashboard.company.description || "No company description yet."}</p>
                </div>
              ) : (
                <p className="mt-4 text-sm text-zinc-500">No company profile yet.</p>
              )}
            </section>

            <section className="rounded-lg border border-zinc-200 bg-white p-5 shadow-sm">
              <div className="flex items-center justify-between gap-4">
                <h2 className="text-base font-semibold text-zinc-950">Recent applicants</h2>
                <Link to="/hr/jobs" className="text-sm font-medium text-zinc-700 hover:text-zinc-950">
                  View jobs
                </Link>
              </div>
              <div className="mt-4 divide-y divide-zinc-100">
                {dashboard.recent_applications.length === 0 && (
                  <p className="py-6 text-sm text-zinc-500">No applicants yet.</p>
                )}
                {dashboard.recent_applications.map((application) => (
                  <Link
                    key={application.id}
                    to={`/hr/applications/${application.id}`}
                    className="flex items-center justify-between gap-4 py-3 hover:bg-zinc-50"
                  >
                    <div className="min-w-0">
                      <p className="truncate text-sm font-semibold text-zinc-950">{application.candidate_name}</p>
                      <p className="truncate text-sm text-zinc-500">{application.candidate_email}</p>
                    </div>
                    <StatusBadge status={application.status} />
                  </Link>
                ))}
              </div>
            </section>
          </div>
        </>
      )}
    </div>
  );
}
