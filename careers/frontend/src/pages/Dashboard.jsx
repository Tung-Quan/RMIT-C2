import { BarChart3, BriefcaseBusiness, FileText, Target } from "lucide-react";
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { getErrorMessage } from "../api/client";
import { getDashboardStats } from "../api/dashboard";
import { Alert } from "../components/Alert";
import { StatCard } from "../components/StatCard";
import { StatusBadge } from "../components/StatusBadge";
import { APPLICATION_STATUSES } from "../constants";

export function Dashboard() {
  const [stats, setStats] = useState(null);
  const [error, setError] = useState("");
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    async function loadStats() {
      setError("");
      try {
        const response = await getDashboardStats();
        setStats(response.data);
      } catch (err) {
        setError(getErrorMessage(err));
      } finally {
        setIsLoading(false);
      }
    }
    loadStats();
  }, []);

  if (isLoading) return <p className="text-sm text-zinc-500">Loading dashboard</p>;

  return (
    <div className="space-y-6">
      <div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-center">
        <div>
          <h1 className="text-2xl font-semibold text-zinc-950">Dashboard</h1>
          <p className="mt-1 text-sm text-zinc-500">Application pipeline and AI match overview</p>
        </div>
        <Link
          to="/applications/new"
          className="inline-flex items-center justify-center rounded-lg bg-zinc-900 px-4 py-2.5 text-sm font-semibold text-white hover:bg-zinc-800"
        >
          New application
        </Link>
      </div>

      {error && <Alert>{error}</Alert>}

      {stats && (
        <>
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            <StatCard icon={BriefcaseBusiness} label="Applications" value={stats.total_applications} />
            <StatCard icon={FileText} label="Documents" value={stats.uploaded_documents} tone="sky" />
            <StatCard icon={Target} label="Avg AI score" value={`${stats.average_ai_match_score}%`} tone="emerald" />
            <StatCard icon={BarChart3} label="Statuses" value={APPLICATION_STATUSES.length} tone="amber" />
          </div>

          <div className="grid gap-6 lg:grid-cols-[1fr_1.2fr]">
            <section className="rounded-lg border border-zinc-200 bg-white p-5 shadow-sm">
              <h2 className="text-base font-semibold text-zinc-950">Status counts</h2>
              <div className="mt-4 space-y-3">
                {APPLICATION_STATUSES.map((status) => (
                  <div key={status} className="flex items-center justify-between gap-4">
                    <StatusBadge status={status} />
                    <span className="text-sm font-semibold text-zinc-900">
                      {stats.applications_by_status[status] || 0}
                    </span>
                  </div>
                ))}
              </div>
            </section>

            <section className="rounded-lg border border-zinc-200 bg-white p-5 shadow-sm">
              <h2 className="text-base font-semibold text-zinc-950">Recent applications</h2>
              <div className="mt-4 divide-y divide-zinc-100">
                {stats.recent_applications.length === 0 && (
                  <p className="py-6 text-sm text-zinc-500">No applications yet.</p>
                )}
                {stats.recent_applications.map((application) => (
                  <Link
                    key={application.id}
                    to={`/applications/${application.id}`}
                    className="flex items-center justify-between gap-4 py-3 hover:bg-zinc-50"
                  >
                    <div className="min-w-0">
                      <p className="truncate text-sm font-semibold text-zinc-950">{application.company_name}</p>
                      <p className="truncate text-sm text-zinc-500">{application.position_title}</p>
                    </div>
                    <StatusBadge status={application.application_status} />
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
