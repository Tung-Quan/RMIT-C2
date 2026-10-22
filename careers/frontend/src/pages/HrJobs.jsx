import { Edit, Eye, Trash2 } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";

import { normalizeMutationError } from "../api/client";
import { isIdempotencyReplay } from "../api/idempotency";
import {
  archiveJob,
  closeJob,
  deleteDraftJob,
  getHrJobs,
  publishJob,
  reopenJob
} from "../api/hr";
import { Alert } from "../components/Alert";
import { StatusBadge } from "../components/StatusBadge";
import { useIdempotencyKeys } from "../hooks/useIdempotencyKeys";

const jobCommandConfig = {
  publish: {
    label: "Publish",
    pendingLabel: "Publishing",
    success: "Job published.",
    run: publishJob
  },
  close: {
    label: "Close",
    pendingLabel: "Closing",
    success: "Job closed.",
    run: closeJob
  },
  reopen: {
    label: "Reopen",
    pendingLabel: "Reopening",
    success: "Job reopened.",
    run: reopenJob
  },
  archive: {
    label: "Archive",
    pendingLabel: "Archiving",
    success: "Job archived as closed.",
    run: archiveJob
  },
  "delete-draft": {
    label: "Delete draft",
    pendingLabel: "Deleting",
    success: "Draft deleted.",
    run: deleteDraftJob
  }
};

function commandsForJob(job) {
  if (job.status === "draft") return ["publish", "delete-draft"];
  if (job.status === "published") return ["close", "archive"];
  if (job.status === "closed") return ["reopen"];
  return [];
}

export function HrJobs() {
  const [jobs, setJobs] = useState([]);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [isLoading, setIsLoading] = useState(true);
  const pendingActionsRef = useRef(new Set());
  const [pendingActions, setPendingActions] = useState({});
  const { getKey, clearKey } = useIdempotencyKeys();

  async function loadJobs({ clearMessage = true, showLoading = true } = {}) {
    if (clearMessage) {
      setError("");
      setSuccess("");
    }
    if (showLoading) setIsLoading(true);
    try {
      const response = await getHrJobs();
      setJobs(response.data);
    } catch (err) {
      setError(normalizeMutationError(err).message);
    } finally {
      if (showLoading) setIsLoading(false);
    }
  }

  useEffect(() => {
    loadJobs();
  }, []);

  function setActionPending(actionId, isPending) {
    if (isPending) {
      pendingActionsRef.current.add(actionId);
    } else {
      pendingActionsRef.current.delete(actionId);
    }
    setPendingActions(
      Object.fromEntries([...pendingActionsRef.current].map((pendingActionId) => [pendingActionId, true]))
    );
  }

  function isJobCommandPending(jobId) {
    return [...pendingActionsRef.current].some((actionId) => actionId.startsWith(`job:${jobId}:`));
  }

  async function handleJobCommand(job, command) {
    const config = jobCommandConfig[command];
    const actionId = `job:${job.id}:${command}`;
    if (!config || isJobCommandPending(job.id)) return;
    if (!job.version) {
      setError("Refresh this job list before changing workflow state.");
      return;
    }
    if (
      command === "delete-draft" &&
      !window.confirm(
        "Permanently delete this draft? Only draft jobs without applications can be deleted."
      )
    ) {
      return;
    }
    if (
      command === "archive" &&
      !window.confirm("Archive preserves applications and moves this job into the closed lifecycle.")
    ) {
      return;
    }
    const idempotencyKey = getKey(actionId);
    setError("");
    setSuccess("");
    setActionPending(actionId, true);
    try {
      const response = await config.run(job.id, job.version, idempotencyKey);
      clearKey(actionId);
      if (command === "delete-draft") {
        setJobs((current) => current.filter((item) => item.id !== job.id));
      } else {
        setJobs((current) =>
          current.map((item) => (item.id === job.id ? response.data : item))
        );
      }
      setSuccess(isIdempotencyReplay(response) ? `${config.success} Retry completed.` : config.success);
    } catch (err) {
      const mutationError = normalizeMutationError(err);
      if (mutationError.type !== "network") clearKey(actionId);
      if (["stale", "invalid-transition"].includes(mutationError.type)) {
        await loadJobs({ clearMessage: false, showLoading: false });
      }
      setError(mutationError.message);
    } finally {
      setActionPending(actionId, false);
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-center">
        <div>
          <h1 className="text-2xl font-semibold text-zinc-950">Job postings</h1>
          <p className="mt-1 text-sm text-zinc-500">
            Draft, publish, and close job opportunities for your company.
          </p>
        </div>
        <Link
          to="/hr/jobs/new"
          className="inline-flex items-center justify-center rounded-lg bg-zinc-900 px-4 py-2.5 text-sm font-semibold text-white hover:bg-zinc-800"
        >
          New job
        </Link>
      </div>

      {error && <Alert>{error}</Alert>}
      {success && <Alert type="success">{success}</Alert>}

      <div className="overflow-hidden rounded-lg border border-zinc-200 bg-white shadow-sm">
        {isLoading ? (
          <p className="p-5 text-sm text-zinc-500">Loading jobs</p>
        ) : jobs.length === 0 ? (
          <p className="p-5 text-sm text-zinc-500">No jobs created yet.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-zinc-200 text-sm">
              <thead className="bg-zinc-50 text-left text-xs font-semibold uppercase text-zinc-500">
                <tr>
                  <th className="px-4 py-3">Title</th>
                  <th className="px-4 py-3">Location</th>
                  <th className="px-4 py-3">Status</th>
                  <th className="px-4 py-3">Deadline</th>
                  <th className="px-4 py-3 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-zinc-100">
                {jobs.map((job) => (
                  <tr key={job.id} className="hover:bg-zinc-50">
                    <td className="px-4 py-3 font-medium text-zinc-950">{job.title}</td>
                    <td className="px-4 py-3 text-zinc-600">{job.location || "Flexible"}</td>
                    <td className="px-4 py-3"><StatusBadge status={job.status} /></td>
                    <td className="px-4 py-3 text-zinc-600">{job.deadline || "None"}</td>
                    <td className="px-4 py-3">
                      <div className="flex justify-end gap-2">
                        <Link
                          to={`/hr/jobs/${job.id}`}
                          className="rounded-lg border border-zinc-200 p-2 text-zinc-700 hover:bg-zinc-100"
                          aria-label="View job"
                        >
                          <Eye className="h-4 w-4" />
                        </Link>
                        {job.status === "draft" && (
                          <Link
                            to={`/hr/jobs/${job.id}/edit`}
                            className="rounded-lg border border-zinc-200 p-2 text-zinc-700 hover:bg-zinc-100"
                            aria-label="Edit job"
                          >
                            <Edit className="h-4 w-4" />
                          </Link>
                        )}
                        {commandsForJob(job).map((command) => {
                          const config = jobCommandConfig[command];
                          const actionId = `job:${job.id}:${command}`;
                          const isPending = Boolean(pendingActions[actionId]);
                          const isRowPending = Object.keys(pendingActions).some((pendingId) =>
                            pendingId.startsWith(`job:${job.id}:`)
                          );
                          const isDelete = command === "delete-draft";
                          return (
                            <button
                              key={command}
                              type="button"
                              onClick={() => handleJobCommand(job, command)}
                              disabled={isRowPending}
                              className={`rounded-lg border px-3 py-2 text-xs font-semibold disabled:cursor-not-allowed disabled:opacity-60 ${
                                isDelete
                                  ? "border-rose-200 text-rose-700 hover:bg-rose-50"
                                  : "border-zinc-200 text-zinc-700 hover:bg-zinc-100"
                              }`}
                            >
                              {isDelete && !isPending ? (
                                <span className="inline-flex items-center gap-1">
                                  <Trash2 className="h-3.5 w-3.5" aria-hidden="true" />
                                  {config.label}
                                </span>
                              ) : isPending ? (
                                config.pendingLabel
                              ) : (
                                config.label
                              )}
                            </button>
                          );
                        })}
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
