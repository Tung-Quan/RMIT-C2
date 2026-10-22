import { useEffect, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { normalizeMutationError } from "../api/client";
import { isIdempotencyReplay } from "../api/idempotency";
import { archiveJob, closeJob, deleteDraftJob, getHrJob, publishJob, reopenJob } from "../api/hr";
import { employmentTypeLabel } from "../constants";
import { Alert } from "../components/Alert";
import { StatusBadge } from "../components/StatusBadge";
import { useIdempotencyKeys } from "../hooks/useIdempotencyKeys";

const jobCommandConfig = {
  publish: { label: "Publish", pendingLabel: "Publishing", success: "Job published.", run: publishJob },
  close: { label: "Close job", pendingLabel: "Closing", success: "Job closed.", run: closeJob },
  reopen: { label: "Reopen", pendingLabel: "Reopening", success: "Job reopened.", run: reopenJob },
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

export function HrJobDetail() {
  const { jobId } = useParams();
  const navigate = useNavigate();
  const [job, setJob] = useState(null);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [isLoading, setIsLoading] = useState(true);
  const pendingActionRef = useRef("");
  const [pendingActionId, setPendingActionId] = useState("");
  const { getKey, clearKey } = useIdempotencyKeys();

  async function loadJob({ clearMessage = true } = {}) {
    if (clearMessage) {
      setError("");
      setSuccess("");
    }
    try {
      const response = await getHrJob(jobId);
      setJob(response.data);
      return response.data;
    } catch (err) {
      setError(normalizeMutationError(err).message);
      return null;
    } finally {
      setIsLoading(false);
    }
  }

  useEffect(() => {
    loadJob();
  }, [jobId]);

  async function handleJobCommand(command) {
    if (!job) return;
    const config = jobCommandConfig[command];
    const actionId = `job:${job.id}:${command}`;
    if (!config || pendingActionRef.current) return;
    if (!job.version) {
      setError("Refresh this job before changing workflow state.");
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
    pendingActionRef.current = actionId;
    setPendingActionId(actionId);
    try {
      const response = await config.run(job.id, job.version, idempotencyKey);
      clearKey(actionId);
      if (command === "delete-draft") {
        setSuccess(config.success);
        navigate("/hr/jobs");
        return;
      }
      setJob(response.data);
      setSuccess(isIdempotencyReplay(response) ? `${config.success} Retry completed.` : config.success);
    } catch (err) {
      const mutationError = normalizeMutationError(err);
      if (mutationError.type !== "network") clearKey(actionId);
      if (["stale", "invalid-transition"].includes(mutationError.type)) {
        await loadJob({ clearMessage: false });
      }
      setError(mutationError.message);
    } finally {
      pendingActionRef.current = "";
      setPendingActionId("");
    }
  }

  if (isLoading) return <p className="text-sm text-zinc-500">Loading job</p>;

  return (
    <div className="space-y-6">
      {error && <Alert>{error}</Alert>}
      {success && <Alert type="success">{success}</Alert>}

      {job && (
        <>
          <div className="rounded-lg border border-zinc-200 bg-white p-6 shadow-sm">
            <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
              <div>
                <p className="text-sm font-semibold uppercase tracking-wide text-zinc-500">
                  {job.company.name}
                </p>
                <h1 className="mt-2 text-2xl font-semibold text-zinc-950">{job.title}</h1>
                <p className="mt-2 text-sm text-zinc-500">
                  {job.location || "Flexible"} · {job.work_mode} · {employmentTypeLabel(job.employment_type)}
                </p>
              </div>
              <div className="flex flex-col items-start gap-3 lg:items-end">
                <StatusBadge status={job.status} />
                <div className="flex flex-wrap gap-2">
                  {job.status === "draft" && (
                    <Link
                      to={`/hr/jobs/${job.id}/edit`}
                      className="rounded-lg border border-zinc-200 px-4 py-2 text-sm font-semibold text-zinc-800 hover:bg-zinc-100"
                    >
                      Edit
                    </Link>
                  )}
                  <Link
                    to={`/hr/jobs/${job.id}/applicants`}
                    className="rounded-lg border border-zinc-200 px-4 py-2 text-sm font-semibold text-zinc-800 hover:bg-zinc-100"
                  >
                    View applicants
                  </Link>
                  {commandsForJob(job).map((command) => {
                    const config = jobCommandConfig[command];
                    const actionId = `job:${job.id}:${command}`;
                    const isPending = pendingActionId === actionId;
                    const isPrimary = command === "publish" || command === "reopen";
                    const isDanger = command === "close" || command === "delete-draft";
                    return (
                      <button
                        key={command}
                        type="button"
                        onClick={() => handleJobCommand(command)}
                        disabled={Boolean(pendingActionId)}
                        className={`rounded-lg px-4 py-2 text-sm font-semibold disabled:cursor-not-allowed disabled:opacity-60 ${
                          isPrimary
                            ? "bg-zinc-900 text-white hover:bg-zinc-800"
                            : isDanger
                              ? "border border-rose-200 text-rose-700 hover:bg-rose-50"
                              : "border border-zinc-200 text-zinc-800 hover:bg-zinc-100"
                        }`}
                      >
                        {isPending ? config.pendingLabel : config.label}
                      </button>
                    );
                  })}
                  {job.status === "published" && (
                    <p className="basis-full text-xs text-zinc-500">
                      Archive preserves applications and records this job in the closed lifecycle.
                    </p>
                  )}
                  {job.status === "draft" && (
                    <p className="basis-full text-xs text-zinc-500">
                      Draft deletion is permanent and only allowed before applications exist.
                    </p>
                  )}
                </div>
              </div>
            </div>
          </div>

          <div className="grid gap-6 xl:grid-cols-[1.3fr_0.9fr]">
            <section className="rounded-lg border border-zinc-200 bg-white p-5 shadow-sm">
              <h2 className="text-base font-semibold text-zinc-950">Description</h2>
              <p className="mt-3 whitespace-pre-wrap text-sm leading-6 text-zinc-700">{job.description}</p>
              {job.requirements && (
                <>
                  <h3 className="mt-5 text-sm font-semibold text-zinc-950">Requirements</h3>
                  <p className="mt-2 whitespace-pre-wrap text-sm leading-6 text-zinc-700">{job.requirements}</p>
                </>
              )}
              {job.responsibilities && (
                <>
                  <h3 className="mt-5 text-sm font-semibold text-zinc-950">Responsibilities</h3>
                  <p className="mt-2 whitespace-pre-wrap text-sm leading-6 text-zinc-700">{job.responsibilities}</p>
                </>
              )}
            </section>

            <section className="rounded-lg border border-zinc-200 bg-white p-5 shadow-sm">
              <h2 className="text-base font-semibold text-zinc-950">Posting details</h2>
              <div className="mt-4 space-y-2 text-sm text-zinc-700">
                <p>Deadline: {job.deadline || "Not set"}</p>
                <p>Salary min: {job.salary_min ?? "—"}</p>
                <p>Salary max: {job.salary_max ?? "—"}</p>
                <p>Work mode: {job.work_mode}</p>
                <p>Employment type: {employmentTypeLabel(job.employment_type)}</p>
              </div>
            </section>
          </div>
        </>
      )}
    </div>
  );
}
