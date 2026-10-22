import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { getErrorMessage } from "../api/client";
import { getHrJob, getHrJobApplications } from "../api/hr";
import { Alert } from "../components/Alert";
import { StatusBadge } from "../components/StatusBadge";

export function HrJobApplicants() {
  const { jobId } = useParams();
  const [job, setJob] = useState(null);
  const [applications, setApplications] = useState([]);
  const [error, setError] = useState("");
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    async function loadApplicants() {
      setError("");
      try {
        const [jobResponse, applicationsResponse] = await Promise.all([
          getHrJob(jobId),
          getHrJobApplications(jobId)
        ]);
        setJob(jobResponse.data);
        setApplications(applicationsResponse.data);
      } catch (err) {
        setError(getErrorMessage(err));
      } finally {
        setIsLoading(false);
      }
    }

    loadApplicants();
  }, [jobId]);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold text-zinc-950">Applicants</h1>
        <p className="mt-1 text-sm text-zinc-500">
          {job ? `${job.company.name} — ${job.title}` : "Review submitted candidates for this job."}
        </p>
      </div>

      {error && <Alert>{error}</Alert>}

      <div className="overflow-hidden rounded-lg border border-zinc-200 bg-white shadow-sm">
        {isLoading ? (
          <p className="p-5 text-sm text-zinc-500">Loading applicants</p>
        ) : applications.length === 0 ? (
          <p className="p-5 text-sm text-zinc-500">No applicants yet.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-zinc-200 text-sm">
              <thead className="bg-zinc-50 text-left text-xs font-semibold uppercase text-zinc-500">
                <tr>
                  <th className="px-4 py-3">Candidate</th>
                  <th className="px-4 py-3">Submitted</th>
                  <th className="px-4 py-3">Status</th>
                  <th className="px-4 py-3">Documents</th>
                  <th className="px-4 py-3 text-right">Details</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-zinc-100">
                {applications.map((application) => (
                  <tr key={application.id} className="hover:bg-zinc-50">
                    <td className="px-4 py-3">
                      <p className="font-medium text-zinc-950">{application.candidate_name}</p>
                      <p className="text-zinc-500">{application.candidate_email}</p>
                    </td>
                    <td className="px-4 py-3 text-zinc-600">
                      {new Date(application.submitted_at).toLocaleString()}
                    </td>
                    <td className="px-4 py-3"><StatusBadge status={application.status} /></td>
                    <td className="px-4 py-3 text-zinc-600">{application.attached_documents_count}</td>
                    <td className="px-4 py-3 text-right">
                      <Link
                        to={`/hr/applications/${application.id}`}
                        className="inline-flex rounded-lg border border-zinc-200 px-3 py-2 text-sm font-semibold text-zinc-700 hover:bg-zinc-100"
                      >
                        View
                      </Link>
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
