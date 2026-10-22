import { FileSearch, PlusCircle } from "lucide-react";
import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { createApplication, getApplications } from "../api/applications";
import { getErrorMessage } from "../api/client";
import { Alert } from "../components/Alert";
import { ApplicationForm } from "../components/ApplicationForm";
import { StatusBadge } from "../components/StatusBadge";
import { filterUserApplications } from "../utils/systemApplications";

export function AICVMatching() {
  const navigate = useNavigate();
  const [applications, setApplications] = useState([]);
  const [error, setError] = useState("");
  const [isLoading, setIsLoading] = useState(true);
  const [isCreating, setIsCreating] = useState(false);
  const [showCreateForm, setShowCreateForm] = useState(false);

  async function loadApplications() {
    setIsLoading(true);
    setError("");
    try {
      const response = await getApplications();
      const userApplications = filterUserApplications(response.data);
      setApplications(userApplications);
      setShowCreateForm(userApplications.length === 0);
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setIsLoading(false);
    }
  }

  useEffect(() => {
    loadApplications();
  }, []);

  async function handleCreateApplication(payload) {
    setError("");
    setIsCreating(true);
    try {
      const response = await createApplication(payload);
      navigate(`/applications/${response.data.id}#ai-cv-match`);
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setIsCreating(false);
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-center">
        <div>
          <h1 className="text-2xl font-semibold text-zinc-950">AI CV Matching</h1>
          <p className="mt-1 text-sm text-zinc-500">Compare a CV against one of your tracked roles.</p>
        </div>
        {applications.length > 0 && (
          <button
            type="button"
            onClick={() => setShowCreateForm((current) => !current)}
            className="inline-flex items-center justify-center gap-2 rounded-lg border border-zinc-200 bg-white px-4 py-2.5 text-sm font-semibold text-zinc-800 hover:bg-zinc-100"
          >
            <PlusCircle className="h-4 w-4" />
            {showCreateForm ? "Hide role form" : "Add tracked role"}
          </button>
        )}
      </div>

      {error && <Alert>{error}</Alert>}

      <section className="rounded-lg border border-zinc-200 bg-white p-5 shadow-sm">
        <div className="flex items-center gap-2">
          <FileSearch className="h-5 w-5 text-zinc-700" />
          <h2 className="text-base font-semibold text-zinc-950">Tracked roles</h2>
        </div>

        <div className="mt-4 divide-y divide-zinc-100">
          {isLoading ? (
            <p className="py-5 text-sm text-zinc-500">Loading tracked roles</p>
          ) : applications.length === 0 ? (
            <p className="py-5 text-sm text-zinc-500">No tracked roles yet.</p>
          ) : (
            applications.map((application) => (
              <div key={application.id} className="flex flex-col gap-3 py-4 sm:flex-row sm:items-center sm:justify-between">
                <div className="min-w-0">
                  <p className="truncate text-sm font-semibold text-zinc-950">{application.company_name}</p>
                  <p className="mt-1 truncate text-sm text-zinc-500">{application.position_title}</p>
                  <div className="mt-2 flex flex-wrap items-center gap-3">
                    <StatusBadge status={application.application_status} />
                    <span className="text-xs text-zinc-500">
                      Deadline: {application.deadline || "None"}
                    </span>
                  </div>
                </div>
                <Link
                  to={`/applications/${application.id}#ai-cv-match`}
                  className="inline-flex items-center justify-center gap-2 rounded-lg bg-zinc-900 px-4 py-2.5 text-sm font-semibold text-white hover:bg-zinc-800"
                >
                  <FileSearch className="h-4 w-4" />
                  Match CV
                </Link>
              </div>
            ))
          )}
        </div>
      </section>

      {showCreateForm && (
        <section className="space-y-4">
          <div>
            <h2 className="text-base font-semibold text-zinc-950">Add role for matching</h2>
            <p className="mt-1 text-sm text-zinc-500">Save the job details, then run the CV match.</p>
          </div>
          <ApplicationForm
            onSubmit={handleCreateApplication}
            isLoading={isCreating}
            submitLabel="Create and match CV"
          />
        </section>
      )}
    </div>
  );
}
