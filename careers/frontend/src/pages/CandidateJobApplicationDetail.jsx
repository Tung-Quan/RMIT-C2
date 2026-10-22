import {downloadDocument} from "../api/documents";
import { ArrowLeft, Download, FileText, ShieldAlert } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";

import {
  getCandidateJobApplication,
  withdrawApplication
} from "../api/candidate";
import { normalizeMutationError, resolveApiUrl } from "../api/client";
import { getDocumentDownloadUrl } from "../api/documents";
import { isIdempotencyReplay } from "../api/idempotency";
import { Alert } from "../components/Alert";
import {
  CandidateButton,
  CandidateEmptyState,
  CandidateHero,
  CandidateLoading,
  CandidatePage,
  CandidateSection,
  formatDateTime
} from "../components/candidate/CandidateUI";
import { StatusBadge } from "../components/StatusBadge";
import { useIdempotencyKeys } from "../hooks/useIdempotencyKeys";

const withdrawableStatuses = new Set(["submitted", "under_review", "shortlisted", "interview"]);

export function CandidateJobApplicationDetail() {
  const { applicationId } = useParams();
  const [application, setApplication] = useState(null);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [isLoading, setIsLoading] = useState(true);
  const [activeDocumentId, setActiveDocumentId] = useState(null);
  const [isWithdrawing, setIsWithdrawing] = useState(false);
  const withdrawInFlightRef = useRef(false);
  const { getKey, clearKey } = useIdempotencyKeys();

  async function loadApplication({ clearMessage = true } = {}) {
    if (clearMessage) {
      setError("");
      setSuccess("");
    }
    try {
      const response = await getCandidateJobApplication(applicationId);
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

  async function openDocument(documentId) {
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

  async function handleWithdraw() {
    if (withdrawInFlightRef.current) return;
    if (!application?.version) {
      setError("Refresh this application before withdrawing.");
      return;
    }
    if (!window.confirm("Withdraw this job application?")) return;
    const actionId = `application:${application.id}:withdraw`;
    const idempotencyKey = getKey(actionId);
    setError("");
    setSuccess("");
    withdrawInFlightRef.current = true;
    setIsWithdrawing(true);
    try {
      const response = await withdrawApplication(applicationId, application.version, idempotencyKey);
      clearKey(actionId);
      setApplication(response.data);
      setSuccess(
        isIdempotencyReplay(response)
          ? "Application withdrawal retry completed."
          : "Application withdrawn."
      );
    } catch (err) {
      const mutationError = normalizeMutationError(err);
      if (mutationError.type !== "network") clearKey(actionId);
      if (["stale", "invalid-transition"].includes(mutationError.type)) {
        await loadApplication({ clearMessage: false });
      }
      setError(mutationError.message);
    } finally {
      withdrawInFlightRef.current = false;
      setIsWithdrawing(false);
    }
  }

  const canWithdraw = application && withdrawableStatuses.has(application.status);

  if (isLoading) return <CandidateLoading label="Loading submitted application" />;

  return (
    <CandidatePage>
      <Link to="/candidate/job-applications" className="inline-flex w-fit items-center gap-2 text-sm font-extrabold text-[var(--candidate-muted)] hover:text-[var(--candidate-primary)]">
        <ArrowLeft className="h-4 w-4" aria-hidden="true" />
        Back to submissions
      </Link>

      {error && <Alert>{error}</Alert>}
      {success && <Alert type="success">{success}</Alert>}

      {application && (
        <>
          <CandidateHero
            eyebrow={application.job_posting.company.name}
            title={application.job_posting.title}
            copy={`Submitted ${formatDateTime(application.submitted_at)}. Track HR status updates, attached documents, and your submitted notes here.`}
            actions={<StatusBadge status={application.status} />}
          />

          <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_24rem]">
            <div className="space-y-5">
              <CandidateSection eyebrow="Submission" title="Your application notes">
                <div className="grid gap-5 md:grid-cols-2">
                  <div>
                    <h3 className="text-sm font-extrabold text-[var(--candidate-ink-strong)]">Cover letter</h3>
                    <p className="mt-2 whitespace-pre-wrap text-sm leading-7 text-[var(--candidate-ink)]">
                      {application.cover_letter_text || "No cover letter provided."}
                    </p>
                  </div>
                  <div>
                    <h3 className="text-sm font-extrabold text-[var(--candidate-ink-strong)]">Candidate note</h3>
                    <p className="mt-2 whitespace-pre-wrap text-sm leading-7 text-[var(--candidate-ink)]">
                      {application.candidate_note || "No note provided."}
                    </p>
                  </div>
                </div>
              </CandidateSection>

              <CandidateSection eyebrow="Progress" title="Status timeline">
                <div className="space-y-0">
                  {application.status_history.map((entry, index) => (
                    <div key={entry.id} className="relative grid gap-3 border-l-2 border-[var(--candidate-border)] pb-6 pl-5 last:pb-0">
                      <span className="absolute -left-[0.44rem] top-0 h-3 w-3 rounded-full bg-[var(--candidate-primary)] ring-4 ring-white" />
                      <div className="flex flex-wrap items-center gap-3">
                        <StatusBadge status={entry.new_status} />
                        <p className="text-sm font-bold text-[var(--candidate-muted)]">
                          {entry.old_status ? `From ${entry.old_status}` : index === application.status_history.length - 1 ? "Initial submission" : "Status update"}
                        </p>
                      </div>
                      {entry.note && <p className="text-sm leading-6 text-[var(--candidate-ink)]">{entry.note}</p>}
                      <p className="text-xs font-bold text-[var(--candidate-muted)]">{formatDateTime(entry.created_at)}</p>
                    </div>
                  ))}
                </div>
              </CandidateSection>
            </div>

            <aside className="space-y-5 xl:sticky xl:top-6 xl:self-start">
              <CandidateSection eyebrow="Documents" title="Attached files">
                <div className="space-y-3">
                  {application.attached_documents.length === 0 && (
                    <CandidateEmptyState title="No documents attached">
                      This submission does not currently include files.
                    </CandidateEmptyState>
                  )}
                  {application.attached_documents.map((document) => (
                    <div key={document.id} className="candidate-soft-surface flex items-center justify-between gap-4 p-4">
                      <div className="min-w-0">
                        <p className="truncate text-sm font-extrabold text-[var(--candidate-ink-strong)]">{document.file_name}</p>
                        <p className="mt-1 text-xs font-bold uppercase tracking-wide text-[var(--candidate-primary)]">{document.document_type}</p>
                      </div>
                      <button
                        type="button"
                        onClick={() => openDocument(document.document_id)}
                        disabled={activeDocumentId === document.document_id}
                        className="candidate-button candidate-button--secondary p-2"
                        title="Download document"
                      >
                        {activeDocumentId === document.document_id ? (
                          <FileText className="h-4 w-4" aria-hidden="true" />
                        ) : (
                          <Download className="h-4 w-4" aria-hidden="true" />
                        )}
                      </button>
                    </div>
                  ))}
                </div>
              </CandidateSection>

              {canWithdraw && (
                <CandidateSection eyebrow="Control" title="Withdraw application">
                  <p className="flex gap-2 text-sm leading-6 text-[var(--candidate-muted)]">
                    <ShieldAlert className="mt-0.5 h-4 w-4 shrink-0 text-[var(--candidate-danger)]" aria-hidden="true" />
                    Withdrawing updates this submission status and adds a timeline event.
                  </p>
                  <CandidateButton
                    type="button"
                    onClick={handleWithdraw}
                    disabled={isWithdrawing}
                    variant="danger"
                    className="mt-4 w-full"
                  >
                    {isWithdrawing ? "Withdrawing" : "Withdraw"}
                  </CandidateButton>
                </CandidateSection>
              )}
            </aside>
          </div>
        </>
      )}
    </CandidatePage>
  );
}
