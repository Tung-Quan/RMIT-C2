import { Edit, Eye, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import {
  deleteApplication as deleteApplicationRequest,
  getApplications
} from "../api/applications";
import { getErrorMessage } from "../api/client";
import { Alert } from "../components/Alert";
import { StatusBadge } from "../components/StatusBadge";
import { filterUserApplications } from "../utils/systemApplications";

export function ApplicationsList() {
  const [applications, setApplications] = useState([]);
  const [error, setError] = useState("");
  const [isLoading, setIsLoading] = useState(true);

  async function loadApplications() {
    setIsLoading(true);
    setError("");
    try {
      const response = await getApplications();
      setApplications(filterUserApplications(response.data));
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setIsLoading(false);
    }
  }

  useEffect(() => {
    loadApplications();
  }, []);

  async function handleDeleteApplication(id) {
    if (!window.confirm("Delete this application?")) return;
    setError("");
    try {
      await deleteApplicationRequest(id);
      setApplications((current) => current.filter((application) => application.id !== id));
    } catch (err) {
      setError(getErrorMessage(err));
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-center">
        <div>
          <h1 className="text-2xl font-semibold text-zinc-950">Saved</h1>
          <p className="mt-1 text-sm text-zinc-500">Manage saved jobs and next steps</p>
        </div>
        <Link
          to="/applications/new"
          className="inline-flex items-center justify-center rounded-lg bg-zinc-900 px-4 py-2.5 text-sm font-semibold text-white hover:bg-zinc-800"
        >
          New saved application
        </Link>
      </div>

      {error && <Alert>{error}</Alert>}

      <div className="overflow-hidden rounded-lg border border-zinc-200 bg-white shadow-sm">
        {isLoading ? (
          <p className="p-5 text-sm text-zinc-500">Loading applications</p>
        ) : applications.length === 0 ? (
          <p className="p-5 text-sm text-zinc-500">No saved opportunities yet.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-zinc-200 text-sm">
              <thead className="bg-zinc-50 text-left text-xs font-semibold uppercase text-zinc-500">
                <tr>
                  <th className="px-4 py-3">Company</th>
                  <th className="px-4 py-3">Position</th>
                  <th className="px-4 py-3">Status</th>
                  <th className="px-4 py-3">Deadline</th>
                  <th className="px-4 py-3 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-zinc-100">
                {applications.map((application) => (
                  <tr key={application.id} className="hover:bg-zinc-50">
                    <td className="max-w-[220px] truncate px-4 py-3 font-medium text-zinc-950">{application.company_name}</td>
                    <td className="max-w-[260px] truncate px-4 py-3 text-zinc-600">{application.position_title}</td>
                    <td className="px-4 py-3"><StatusBadge status={application.application_status} /></td>
                    <td className="px-4 py-3 text-zinc-600">{application.deadline || "None"}</td>
                    <td className="px-4 py-3">
                      <div className="flex justify-end gap-2">
                        <Link
                          to={`/applications/${application.id}`}
                          className="rounded-lg border border-zinc-200 p-2 text-zinc-700 hover:bg-zinc-100"
                          aria-label="View application"
                        >
                          <Eye className="h-4 w-4" />
                        </Link>
                        <Link
                          to={`/applications/${application.id}/edit`}
                          className="rounded-lg border border-zinc-200 p-2 text-zinc-700 hover:bg-zinc-100"
                          aria-label="Edit application"
                        >
                          <Edit className="h-4 w-4" />
                        </Link>
                        <button
                          type="button"
                          onClick={() => handleDeleteApplication(application.id)}
                          className="rounded-lg border border-zinc-200 p-2 text-rose-700 hover:bg-rose-50"
                          aria-label="Delete application"
                        >
                          <Trash2 className="h-4 w-4" />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
