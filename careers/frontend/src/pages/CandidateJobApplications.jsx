import { ArrowRight, BriefcaseBusiness, FileText } from "lucide-react";
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { getCandidateJobApplications } from "../api/candidate";
import { getErrorMessage } from "../api/client";
import { Alert } from "../components/Alert";
import {
  CandidateAnimatedList,
  CandidateButton,
  CandidateEmptyState,
  CandidateHero,
  CandidateLoading,
  CandidatePage,
  CandidatePagination,
  CandidateSection,
  formatDate,
  getPaginatedItems
} from "../components/candidate/CandidateUI";
import { StatusBadge } from "../components/StatusBadge";

const PAGE_SIZE = 8;

export function CandidateJobApplications() {
  const [applications, setApplications] = useState([]);
  const [error, setError] = useState("");
  const [isLoading, setIsLoading] = useState(true);
  const [page, setPage] = useState(1);

  useEffect(() => {
    async function loadApplications() {
      setError("");
      try {
        const response = await getCandidateJobApplications();
        setApplications(response.data);
      } catch (err) {
        setError(getErrorMessage(err));
      } finally {
        setIsLoading(false);
      }
    }

    loadApplications();
  }, []);

  const paginated = getPaginatedItems(applications, page, PAGE_SIZE);

  return (
    <CandidatePage>
      <CandidateHero
        eyebrow="Application tracker"
        title="Follow every submitted role without digging through email."
        copy="Your submitted applications are organized as a progress list, with status, submitted date, documents, and a clear path into the detail view."
        actions={<CandidateButton to="/candidate/jobs">Browse more roles</CandidateButton>}
      />

      {error && <Alert>{error}</Alert>}

      {isLoading ? (
        <CandidateLoading label="Loading submitted applications" />
      ) : applications.length === 0 ? (
        <CandidateEmptyState title="No job applications submitted yet" action={<CandidateButton to="/candidate/jobs">Browse jobs</CandidateButton>}>
          When you apply through the job board, each submission and its HR status timeline will appear here.
        </CandidateEmptyState>
      ) : (
        <CandidateSection eyebrow="Submissions" title={`${applications.length} submitted applications`}>
          <CandidateAnimatedList className="divide-y divide-[var(--candidate-border)]">
            {paginated.items.map((application) => (
              <article key={application.id} className="grid gap-4 py-5 lg:grid-cols-[minmax(0,1fr)_13rem_10rem] lg:items-center">
                <div className="min-w-0">
                  <p className="text-xs font-extrabold uppercase tracking-wide text-[var(--candidate-primary)]">
                    {application.job_posting.company.name}
                  </p>
                  <h2 className="mt-1 text-lg font-extrabold text-[var(--candidate-ink-strong)]">
                    {application.job_posting.title}
                  </h2>
                  <div className="mt-3 flex flex-wrap gap-3 text-sm font-bold text-[var(--candidate-muted)]">
                    <span className="inline-flex items-center gap-1.5">
                      <BriefcaseBusiness className="h-4 w-4" aria-hidden="true" />
                      Submitted {formatDate(application.submitted_at)}
                    </span>
                    <span className="inline-flex items-center gap-1.5">
                      <FileText className="h-4 w-4" aria-hidden="true" />
                      {application.attached_documents_count} document{application.attached_documents_count === 1 ? "" : "s"}
                    </span>
                  </div>
                </div>
                <StatusBadge status={application.status} />
                <Link
                  to={`/candidate/job-applications/${application.id}`}
                  className="candidate-button candidate-button--secondary w-full lg:w-auto"
                >
                  View details
                  <ArrowRight className="h-4 w-4" aria-hidden="true" />
                </Link>
              </article>
            ))}
          </CandidateAnimatedList>
          <CandidatePagination
            page={paginated.safePage}
            totalPages={paginated.totalPages}
            onPageChange={setPage}
            totalItems={applications.length}
            pageSize={PAGE_SIZE}
          />
        </CandidateSection>
      )}
    </CandidatePage>
  );
}
