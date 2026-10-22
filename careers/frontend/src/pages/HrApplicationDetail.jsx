import {downloadDocument} from "../api/documents";
import { FileText } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useParams } from "react-router-dom";

import { normalizeMutationError, resolveApiUrl } from "../api/client";
import { isIdempotencyReplay } from "../api/idempotency";
import { advanceApplication, getHrApplication, getHrDocumentDownloadUrl, rejectApplication } from "../api/hr";
import { Alert } from "../components/Alert";
import { StatusBadge } from "../components/StatusBadge";
import { useIdempotencyKeys } from "../hooks/useIdempotencyKeys";
import { clearFieldError, fieldError, validateForm, workflowNoteSchema } from "../validation/forms";

const applicationStages = ["submitted", "under_review", "shortlisted", "interview", "offered"];
const rejectableStatuses = new Set(["submitted", "under_review", "shortlisted", "interview"]);

function nextApplicationStage(status) {
  const index = applicationStages.indexOf(status);
  if (index < 0 || index >= applicationStages.length - 1) return null;
  return applicationStages[index + 1];
}

export function HrApplicationDetail() {
  const { applicationId } = useParams();
  const [application, setApplication] = useState(null);
  const [note, setNote] = useState("");
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [fieldErrors, setFieldErrors] = useState({});
  const [isLoading, setIsLoading] = useState(true);
  const pendingCommandRef = useRef("");
  const [pendingCommand, setPendingCommand] = useState("");
  const [activeDocumentId, setActiveDocumentId] = useState(null);
  const { getKey, clearKey } = useIdempotencyKeys();

  async function loadApplication({ clearMessage = true } = {}) {
    if (clearMessage) {
      setError("");
      setSuccess("");
    }
    try {
      const response = await getHrApplication(applicationId);
      setApplication(response.data);
      return response.data;
    } catch (err) {
      setError(normalizeMutationError(err).message);
      return null;
    } finally {
      setIsLoading(false);
    }
  }

  useEffect(() => {
    loadApplication();
  }, [applicationId]);

  async function handleDownload(documentId) {
    setError("");
    setActiveDocumentId(documentId);
    try {
      await downloadDocument(documentId);
    } catch (err) {
      setError(normalizeMutationError(err).message);
    } finally {
      setActiveDocumentId(null);
    }
  }

  async function handleWorkflowSubmit(event, command) {
    event.preventDefault();
    if (pendingCommandRef.current) return;
    if (!application?.version) {
      setError("Refresh this application before changing workflow state.");
      return;
    }
    const targetStage = command === "advance" ? nextApplicationStage(application.status) : null;
    if (command === "advance" && !targetStage) return;
    if (
      command === "reject" &&
      !window.confirm("Reject this application? This records a terminal status for the candidate.")
    ) {
      return;
    }
    const validation = validateForm(workflowNoteSchema, { note });
    if (!validation.data) {
      setFieldErrors(validation.errors);
      setError(validation.formError);
      return;
    }
    setFieldErrors({});
    const actionId = `application:${application.id}:${command}`;
    const idempotencyKey = getKey(actionId);
    setError("");
    setSuccess("");
    pendingCommandRef.current = command;
    setPendingCommand(command);
    try {
      const response =
        command === "advance"
          ? await advanceApplication(
              applicationId,
              {
                expectedVersion: application.version,
                targetStage,
                note: validation.data.note
              },
              idempotencyKey
            )
          : await rejectApplication(
              applicationId,
              {
                expectedVersion: application.version,
                reason: validation.data.note
              },
              idempotencyKey
            );
      clearKey(actionId);
      setApplication(response.data);
      setNote("");
      const baseMessage =
        command === "advance"
          ? `Application advanced to ${targetStage}.`
          : "Application rejected.";
      setSuccess(isIdempotencyReplay(response) ? `${baseMessage} Retry completed.` : baseMessage);
    } catch (err) {
      const mutationError = normalizeMutationError(err);
      if (mutationError.type !== "network") clearKey(actionId);
      if (["stale", "invalid-transition"].includes(mutationError.type)) {
        await loadApplication({ clearMessage: false });
      }
      setError(mutationError.message);
    } finally {
      pendingCommandRef.current = "";
      setPendingCommand("");
    }
  }

  if (isLoading) return <p className="text-sm text-zinc-500">Loading applicant detail</p>;
  const nextStage = application ? nextApplicationStage(application.status) : null;
  const canReject = application ? rejectableStatuses.has(application.status) : false;

  return (
    <div className="space-y-6">
      {error && <Alert>{error}</Alert>}
      {success && <Alert type="success">{success}</Alert>}

      {application && (
        <>
          <div className="rounded-lg border border-zinc-200 bg-white p-6 shadow-sm">
            <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
              <div>
                <p className="text-sm font-semibold uppercase tracking-wide text-zinc-500">
                  {application.job_posting.company.name}
                </p>
                <h1 className="mt-2 text-2xl font-semibold text-zinc-950">
                  {application.candidate.full_name || application.candidate.email}
                </h1>
                <p className="mt-1 text-sm text-zinc-500">{application.candidate.email}</p>
                <p className="mt-3 text-sm text-zinc-600">
                  Applied for {application.job_posting.title} on {new Date(application.submitted_at).toLocaleString()}
                </p>
              </div>
              <StatusBadge status={application.status} />
            </div>
          </div>

          <div className="grid gap-6 xl:grid-cols-[0.9fr_1.1fr]">
            <aside className="space-y-6">
              <section className="rounded-lg border border-zinc-200 bg-white p-5 shadow-sm">
                <h2 className="text-base font-semibold text-zinc-950">Candidate profile</h2>
                <div className="mt-4 space-y-2 text-sm text-zinc-700">
                  <p><span className="font-medium text-zinc-950">Name:</span> {application.candidate.profile?.full_name || application.candidate.full_name || "Not provided"}</p>
                  <p><span className="font-medium text-zinc-950">University:</span> {application.candidate.profile?.university || "Not provided"}</p>
                  <p><span className="font-medium text-zinc-950">Major:</span> {application.candidate.profile?.major || "Not provided"}</p>
                  <p><span className="font-medium text-zinc-950">Location:</span> {application.candidate.profile?.location || "Not provided"}</p>
                  <p><span className="font-medium text-zinc-950">Phone:</span> {application.candidate.profile?.phone || "Not provided"}</p>
                </div>
              </section>

              <section className="rounded-lg border border-zinc-200 bg-white p-5 shadow-sm">
                <h2 className="text-base font-semibold text-zinc-950">Attached documents</h2>
                <div className="mt-4 space-y-3">
                  {application.attached_documents.map((document) => (
                    <div key={document.id} className="flex items-center justify-between gap-4 rounded-lg border border-zinc-200 p-4">
                      <div className="min-w-0">
                        <p className="truncate text-sm font-semibold text-zinc-950">{document.file_name}</p>
                        <p className="mt-1 text-xs text-zinc-500">{document.document_type}</p>
                      </div>
                      <button
                        type="button"
                        onClick={() => handleDownload(document.document_id)}
                        disabled={activeDocumentId === document.document_id}
                        className="rounded-lg border border-zinc-200 p-2 text-zinc-700 hover:bg-zinc-100 disabled:cursor-not-allowed disabled:opacity-60"
                        title="Download attached document"
                      >
                        <FileText className="h-4 w-4" />
                      </button>
                    </div>
                  ))}
                </div>
              </section>
            </aside>

            <div className="space-y-6">
              <section className="rounded-lg border border-zinc-200 bg-white p-5 shadow-sm">
                <h2 className="text-base font-semibold text-zinc-950">Application content</h2>
                <div className="mt-4 space-y-5">
                  <div>
                    <h3 className="text-sm font-semibold text-zinc-950">Cover letter</h3>
                    <p className="mt-2 whitespace-pre-wrap text-sm leading-6 text-zinc-700">
                      {application.cover_letter_text || "No cover letter submitted."}
                    </p>
                  </div>
                  <div>
                    <h3 className="text-sm font-semibold text-zinc-950">Candidate note</h3>
                    <p className="mt-2 whitespace-pre-wrap text-sm leading-6 text-zinc-700">
                      {application.candidate_note || "No note submitted."}
                    </p>
                  </div>
                </div>
              </section>

              <section className="rounded-lg border border-zinc-200 bg-white p-5 shadow-sm">
                <h2 className="text-base font-semibold text-zinc-950">Workflow actions</h2>
                <form className="mt-4 space-y-4">
                  <p className="text-sm text-zinc-600">
                    Current state: <span className="font-semibold text-zinc-950">{application.status}</span>, version{" "}
                    <span className="font-semibold text-zinc-950">{application.version}</span>.
                  </p>
                  <textarea
                    rows="4"
                    value={note}
                    onChange={(event) => {
                      setNote(event.target.value);
                      setFieldErrors((current) => clearFieldError(current, "note"));
                    }}
                    placeholder="Optional internal note or rejection reason"
                    aria-invalid={Boolean(fieldError(fieldErrors, "note")) || undefined}
                    className="w-full rounded-lg border border-zinc-300 px-3 py-2 text-sm outline-none focus:border-zinc-900 focus:ring-2 focus:ring-zinc-200"
                  />
                  {fieldError(fieldErrors, "note") && <p className="text-xs font-semibold text-rose-600">{fieldError(fieldErrors, "note")}</p>}
                  <div className="flex flex-wrap gap-2">
                    {nextStage && (
                      <button
                        type="button"
                        onClick={(event) => handleWorkflowSubmit(event, "advance")}
                        disabled={Boolean(pendingCommand)}
                        className="rounded-lg bg-zinc-900 px-4 py-2.5 text-sm font-semibold text-white hover:bg-zinc-800 disabled:cursor-not-allowed disabled:opacity-60"
                      >
                        {pendingCommand === "advance" ? "Advancing" : `Advance to ${nextStage}`}
                      </button>
                    )}
                    {canReject && (
                      <button
                        type="button"
                        onClick={(event) => handleWorkflowSubmit(event, "reject")}
                        disabled={Boolean(pendingCommand)}
                        className="rounded-lg border border-rose-200 px-4 py-2.5 text-sm font-semibold text-rose-700 hover:bg-rose-50 disabled:cursor-not-allowed disabled:opacity-60"
                      >
                        {pendingCommand === "reject" ? "Rejecting" : "Reject"}
                      </button>
                    )}
                    {!nextStage && !canReject && (
                      <p className="text-sm text-zinc-500">
                        No workflow commands are available for this terminal state.
                      </p>
                    )}
                  </div>
                </form>
              </section>

              <section className="rounded-lg border border-zinc-200 bg-white p-5 shadow-sm">
                <h2 className="text-base font-semibold text-zinc-950">Status history</h2>
                <div className="mt-4 space-y-4">
                  {application.status_history.map((entry) => (
                    <div key={entry.id} className="rounded-lg border border-zinc-200 p-4">
                      <div className="flex flex-wrap items-center gap-3">
                        <StatusBadge status={entry.new_status} />
                        <p className="text-sm text-zinc-600">
                          {entry.old_status ? `From ${entry.old_status}` : "Initial submission"}
                        </p>
                      </div>
                      {entry.note && <p className="mt-2 text-sm text-zinc-700">{entry.note}</p>}
                      <p className="mt-2 text-xs text-zinc-500">
                        {new Date(entry.created_at).toLocaleString()}
                      </p>
                    </div>
                  ))}
                </div>
              </section>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
