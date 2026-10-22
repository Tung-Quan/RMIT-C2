import {
  ArrowLeft,
  BookmarkPlus,
  Building2,
  DollarSign,
  ExternalLink,
  MapPin,
  MonitorSmartphone
} from "lucide-react";
import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { createApplication } from "../api/applications";
import { getErrorMessage } from "../api/client";
import { getJob } from "../api/jobs";
import { employmentTypeLabel } from "../constants";
import { Alert } from "../components/Alert";
import {
  CandidateButton,
  CandidateHero,
  CandidateLoading,
  CandidatePage,
  CandidateSection,
  formatDate
} from "../components/candidate/CandidateUI";
import { StatusBadge } from "../components/StatusBadge";

export function CandidateJobDetail() {
  const { jobId } = useParams();
  const navigate = useNavigate();
  const [job, setJob] = useState(null);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);

  useEffect(() => {
    async function loadJob() {
      setError("");
      try {
        const response = await getJob(jobId);
        setJob(response.data);
      } catch (err) {
        setError(getErrorMessage(err));
      } finally {
        setIsLoading(false);
      }
    }

    loadJob();
  }, [jobId]);

  async function saveJob() {
    if (!job) return;

    setError("");
    setSuccess("");
    setIsSaving(true);
    try {
      const response = await createApplication({
        company_name: job.company.name,
        position_title: job.title,
        job_description: buildSavedJobDescription(job),
        application_status: "Saved",
        deadline: job.deadline || null,
        notes: "Saved from Job Board."
      });
      setSuccess("Job saved.");
      navigate(`/applications/${response.data.id}`);
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setIsSaving(false);
    }
  }

  if (isLoading) return <CandidateLoading label="Loading job" />;

  return (
    <CandidatePage>
      <Link to="/candidate/jobs" className="inline-flex w-fit items-center gap-2 text-sm font-extrabold text-[var(--candidate-muted)] hover:text-[var(--candidate-primary)]">
        <ArrowLeft className="h-4 w-4" aria-hidden="true" />
        Back to jobs
      </Link>

      {error && <Alert>{error}</Alert>}
      {success && <Alert type="success">{success}</Alert>}

      {job && (
        <>
          <CandidateHero
            eyebrow={job.company.name}
            title={job.title}
            copy={job.description}
            actions={
              <>
                <CandidateButton to={`/candidate/jobs/${job.id}/apply`}>Apply now</CandidateButton>
                <CandidateButton type="button" onClick={saveJob} disabled={isSaving} variant="secondary">
                  <BookmarkPlus className="h-4 w-4" aria-hidden="true" />
                  {isSaving ? "Saving" : "Save"}
                </CandidateButton>
              </>
            }
          >
            <div className="mt-5 flex flex-wrap gap-3 text-sm font-bold text-[var(--candidate-ink)]">
              <span className="inline-flex items-center gap-2">
                <MapPin className="h-4 w-4 text-[var(--candidate-primary)]" aria-hidden="true" />
                {job.location || "Location flexible"}
              </span>
              <span className="inline-flex items-center gap-2">
                <MonitorSmartphone className="h-4 w-4 text-[var(--candidate-primary)]" aria-hidden="true" />
                {job.work_mode}
              </span>
              <span>{employmentTypeLabel(job.employment_type)}</span>
              <StatusBadge status={job.status} />
            </div>
          </CandidateHero>

          <div className="grid gap-5 xl:grid-cols-[minmax(0,1.35fr)_22rem]">
            <CandidateSection eyebrow="Role" title="Overview">
              <p className="whitespace-pre-wrap text-sm leading-7 text-[var(--candidate-ink)]">{job.description}</p>
              {job.responsibilities && (
                <>
                  <h3 className="mt-6 text-sm font-extrabold text-[var(--candidate-ink-strong)]">Responsibilities</h3>
                  <p className="mt-2 whitespace-pre-wrap text-sm leading-7 text-[var(--candidate-ink)]">{job.responsibilities}</p>
                </>
              )}
              {job.requirements && (
                <>
                  <h3 className="mt-6 text-sm font-extrabold text-[var(--candidate-ink-strong)]">Requirements</h3>
                  <p className="mt-2 whitespace-pre-wrap text-sm leading-7 text-[var(--candidate-ink)]">{job.requirements}</p>
                </>
              )}
            </CandidateSection>

            <aside className="space-y-5 xl:sticky xl:top-6 xl:self-start">
              <CandidateSection eyebrow="Company" title="About the employer">
                <div className="flex items-start gap-3">
                  <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-[var(--candidate-aqua)] text-[var(--candidate-ink-strong)]">
                    <Building2 className="h-5 w-5" aria-hidden="true" />
                  </span>
                  <div className="min-w-0">
                    <p className="font-extrabold text-[var(--candidate-ink-strong)]">{job.company.name}</p>
                    <p className="mt-1 text-sm text-[var(--candidate-muted)]">{job.company.industry || "Industry not listed"}</p>
                    <p className="mt-1 text-sm text-[var(--candidate-muted)]">{job.company.location || "Location not listed"}</p>
                  </div>
                </div>
                {job.company.website && (
                  <a
                    href={job.company.website}
                    target="_blank"
                    rel="noreferrer"
                    className="mt-4 inline-flex items-center gap-2 text-sm font-extrabold text-[var(--candidate-primary)] hover:text-[var(--candidate-primary-hover)]"
                  >
                    <ExternalLink className="h-4 w-4" aria-hidden="true" />
                    Visit company website
                  </a>
                )}
              </CandidateSection>

              <CandidateSection eyebrow="Apply" title="Application details">
                <div className="space-y-3 text-sm text-[var(--candidate-ink)]">
                  <p className="flex items-center gap-2">
                    <MapPin className="h-4 w-4 text-[var(--candidate-primary)]" aria-hidden="true" />
                    Deadline: {formatDate(job.deadline)}
                  </p>
                  <p className="flex items-center gap-2">
                    <DollarSign className="h-4 w-4 text-[var(--candidate-primary)]" aria-hidden="true" />
                    Salary: {job.salary_min ?? "Not listed"} {job.salary_max ? `to ${job.salary_max}` : ""}
                  </p>
                </div>
              </CandidateSection>
            </aside>
          </div>
        </>
      )}
    </CandidatePage>
  );
}

function buildSavedJobDescription(job) {
  return [
    job.description,
    job.responsibilities ? `Responsibilities:\n${job.responsibilities}` : null,
    job.requirements ? `Requirements:\n${job.requirements}` : null
  ]
    .filter(Boolean)
    .join("\n\n");
}
