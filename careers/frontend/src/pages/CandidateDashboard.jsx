import { ArrowRight, BriefcaseBusiness, Clock3, FileText, Send } from "lucide-react";
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { getCandidateDashboard } from "../api/candidate";
import { getErrorMessage } from "../api/client";
import { Alert } from "../components/Alert";
import {
  CandidateAnimatedList,
  CandidateButton,
  CandidateEmptyState,
  CandidateHero,
  CandidateLoading,
  CandidateMetric,
  CandidatePage,
  CandidateSection,
  formatDateTime
} from "../components/candidate/CandidateUI";
import { StatusBadge } from "../components/StatusBadge";
import { useAuth } from "../context/AuthContext";

export function CandidateDashboard() {
  const { user } = useAuth();
  const [dashboard, setDashboard] = useState(null);
  const [error, setError] = useState("");
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    async function loadDashboard() {
      setError("");
      try {
        const response = await getCandidateDashboard();
        setDashboard(response.data);
      } catch (err) {
        setError(getErrorMessage(err));
      } finally {
        setIsLoading(false);
      }
    }

    loadDashboard();
  }, []);

  if (isLoading) return <CandidateLoading label="Loading candidate dashboard" />;

  const displayName = user?.full_name || user?.email?.split("@")[0] || "there";
  const progressSteps = [
    { label: "Discover", done: true },
    { label: "Save", done: Boolean(dashboard?.total_personal_applications) },
    { label: "Apply", done: Boolean(dashboard?.total_submitted_job_applications) },
    { label: "Track", done: Boolean(dashboard?.recent_job_applications?.length) }
  ];

  return (
    <CandidatePage>
      <CandidateHero
        eyebrow="Candidate workspace"
        title={`Welcome back, ${displayName}. Keep your career search moving.`}
        copy="Review deadlines, recent submissions, and documents from one calm place, then jump into the next best action."
        imageSrc="/assets/home/hero/hero-career-workspace-desktop.webp"
        actions={
          <>
            <CandidateButton to="/candidate/jobs">
              Browse jobs
              <ArrowRight className="h-4 w-4" aria-hidden="true" />
            </CandidateButton>
            <CandidateButton to="/candidate/profile" variant="secondary">Refine profile</CandidateButton>
          </>
        }
      >
        <div className="mt-6 grid gap-2 rounded-xl bg-white/75 p-3 ring-1 ring-[var(--candidate-border)] sm:grid-cols-4">
          {progressSteps.map((step, index) => (
            <div key={step.label} className="flex items-center gap-2 text-sm font-extrabold text-[var(--candidate-ink)]">
              <span className={`flex h-7 w-7 items-center justify-center rounded-full text-xs ${step.done ? "bg-[var(--candidate-primary)] text-white" : "bg-[var(--candidate-surface-soft)] text-[var(--candidate-muted)] ring-1 ring-[var(--candidate-border)]"}`}>
                {index + 1}
              </span>
              {step.label}
            </div>
          ))}
        </div>
      </CandidateHero>

      {error && <Alert>{error}</Alert>}

      {dashboard && (
        <>
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            <CandidateMetric icon={BriefcaseBusiness} label="Saved opportunities" value={dashboard.total_personal_applications} helper="Personal tracker roles" />
            <CandidateMetric icon={Send} label="Submitted applications" value={dashboard.total_submitted_job_applications} helper="Sent to HR teams" />
            <CandidateMetric icon={FileText} label="Recent documents" value={dashboard.recent_documents.length} helper="Fresh upload activity" />
            <CandidateMetric icon={Clock3} label="Upcoming deadlines" value={dashboard.upcoming_deadlines.length} helper="Next decision points" />
          </div>

          <div className="grid gap-5 lg:grid-cols-[minmax(0,1.2fr)_22rem]">
            <CandidateSection
              eyebrow="Submissions"
              title="Recent job applications"
              action={<CandidateButton to="/candidate/job-applications" variant="secondary">View all</CandidateButton>}
            >
              <CandidateAnimatedList>
                {dashboard.recent_job_applications.length === 0 && (
                  <CandidateEmptyState
                    title="No submitted applications yet"
                    action={<CandidateButton to="/candidate/jobs">Browse jobs</CandidateButton>}
                  >
                    Start with the job board, attach a CV, and your submitted applications will appear here.
                  </CandidateEmptyState>
                )}
                {dashboard.recent_job_applications.map((application) => (
                  <Link
                    key={application.id}
                    to={`/candidate/job-applications/${application.id}`}
                    className="candidate-list-row rounded-lg px-1 hover:bg-[var(--candidate-surface-soft)] sm:grid-cols-[minmax(0,1fr)_auto] sm:items-center"
                  >
                    <div className="min-w-0">
                      <p className="truncate text-sm font-extrabold text-[var(--candidate-ink-strong)]">
                        {application.job_posting.company.name}
                      </p>
                      <p className="mt-1 truncate text-sm text-[var(--candidate-muted)]">
                        {application.job_posting.title}
                      </p>
                    </div>
                    <StatusBadge status={application.status} />
                  </Link>
                ))}
              </CandidateAnimatedList>
            </CandidateSection>

            <CandidateSection eyebrow="Timing" title="Upcoming deadlines">
              <div className="space-y-3">
                {dashboard.upcoming_deadlines.length === 0 && (
                  <CandidateEmptyState title="No deadlines on deck">
                    When tracker items or submitted jobs have future deadlines, they will collect here.
                  </CandidateEmptyState>
                )}
                {dashboard.upcoming_deadlines.map((item) => (
                  <div key={`${item.type}-${item.label}-${item.deadline}`} className="border-l-4 border-[var(--candidate-secondary)] py-2 pl-3">
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <p className="truncate text-sm font-extrabold text-[var(--candidate-ink-strong)]">{item.label}</p>
                        <p className="mt-1 text-xs font-bold uppercase tracking-wide text-[var(--candidate-muted)]">{item.type}</p>
                      </div>
                      <StatusBadge status={item.status} />
                    </div>
                    <p className="mt-2 text-sm text-[var(--candidate-muted)]">Deadline: {item.deadline}</p>
                  </div>
                ))}
              </div>
            </CandidateSection>
          </div>

          <CandidateSection
            eyebrow="Documents"
            title="Recent documents"
            action={<CandidateButton to="/applications" variant="secondary">Manage tracker documents</CandidateButton>}
          >
            <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
              {dashboard.recent_documents.length === 0 && (
                <div className="md:col-span-2 xl:col-span-3">
                  <CandidateEmptyState title="No documents yet">
                    Upload CVs, transcripts, and certificates through your personal tracker applications.
                  </CandidateEmptyState>
                </div>
              )}
              {dashboard.recent_documents.map((document) => (
                <div key={document.id} className="candidate-soft-surface p-4">
                  <p className="truncate text-sm font-extrabold text-[var(--candidate-ink-strong)]">{document.file_name}</p>
                  <p className="mt-1 text-xs font-bold uppercase tracking-wide text-[var(--candidate-primary)]">{document.document_type}</p>
                  <p className="mt-2 text-xs text-[var(--candidate-muted)]">
                    Uploaded {formatDateTime(document.created_at)}
                  </p>
                </div>
              ))}
            </div>
          </CandidateSection>
        </>
      )}
    </CandidatePage>
  );
}
