import { ArrowRight, MapPin, RotateCcw, Search } from "lucide-react";
import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { getErrorMessage } from "../api/client";
import { getJobs } from "../api/jobs";
import { Alert } from "../components/Alert";
import {
  CandidateAnimatedList,
  CandidateButton,
  CandidateEmptyState,
  CandidateHero,
  CandidateInput,
  CandidateLoading,
  CandidatePage,
  CandidatePagination,
  CandidateSection,
  CandidateSelect,
  formatDate,
  getPaginatedItems
} from "../components/candidate/CandidateUI";
import { StatusBadge } from "../components/StatusBadge";
import { employmentTypeLabel, JOB_EMPLOYMENT_TYPES, JOB_WORK_MODES } from "../constants";
import { clearFieldError, fieldError, jobSearchFiltersSchema, validateForm } from "../validation/forms";

const initialFilters = {
  keyword: "",
  location: "",
  work_mode: "",
  employment_type: ""
};

const PAGE_SIZE = 8;

function getFiltersFromParams(searchParams) {
  return {
    keyword: searchParams.get("keyword") || "",
    location: searchParams.get("location") || "",
    work_mode: searchParams.get("work_mode") || "",
    employment_type: searchParams.get("employment_type") || ""
  };
}

function getPageFromParams(searchParams) {
  const page = Number(searchParams.get("page") || "1");
  return Number.isFinite(page) && page > 0 ? Math.floor(page) : 1;
}

function buildJobSearchParams(filters, page = 1) {
  const params = new URLSearchParams();
  Object.entries(filters).forEach(([key, value]) => {
    if (String(value || "").trim()) params.set(key, String(value).trim());
  });
  if (page > 1) params.set("page", String(page));
  return params;
}

export function CandidateJobs() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [filters, setFilters] = useState(() => getFiltersFromParams(searchParams));
  const [jobs, setJobs] = useState([]);
  const [error, setError] = useState("");
  const [fieldErrors, setFieldErrors] = useState({});
  const [isLoading, setIsLoading] = useState(true);
  const page = getPageFromParams(searchParams);

  async function loadJobs(activeFilters) {
    setError("");
    setIsLoading(true);
    try {
      const response = await getJobs(activeFilters);
      setJobs(response.data);
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setIsLoading(false);
    }
  }

  useEffect(() => {
    const nextFilters = getFiltersFromParams(searchParams);
    setFilters(nextFilters);
    loadJobs(nextFilters);
  }, [searchParams]);

  function updateFilter(field, value) {
    setFilters((current) => ({ ...current, [field]: value }));
    setFieldErrors((current) => clearFieldError(current, field));
  }

  function handleSubmit(event) {
    event.preventDefault();
    const validation = validateForm(jobSearchFiltersSchema, filters);
    if (!validation.data) {
      setFieldErrors(validation.errors);
      setError(validation.formError);
      return;
    }
    setFieldErrors({});
    setSearchParams(buildJobSearchParams(validation.data, 1));
  }

  function handleReset() {
    setFilters(initialFilters);
    setSearchParams(new URLSearchParams());
  }

  function handlePageChange(nextPage) {
    setSearchParams(buildJobSearchParams(getFiltersFromParams(searchParams), nextPage), {
      preventScrollReset: true
    });
  }

  const paginated = getPaginatedItems(jobs, page, PAGE_SIZE);
  const activeFilters = Object.entries(getFiltersFromParams(searchParams)).filter(([, value]) => value);

  useEffect(() => {
    if (!isLoading && jobs.length > 0 && paginated.safePage !== page) {
      setSearchParams(buildJobSearchParams(getFiltersFromParams(searchParams), paginated.safePage), {
        replace: true,
        preventScrollReset: true
      });
    }
  }, [isLoading, jobs.length, page, paginated.safePage, searchParams, setSearchParams]);

  return (
    <CandidatePage>
      <CandidateHero
        eyebrow="Career opportunities"
        title="Browse opportunities with enough context to choose confidently."
        copy="Search by role, location, work mode, or employment type. Keep the page light, focused, and easy to scan on mobile."
        imageSrc="/assets/home/opportunities/opportunity-career-fair-desktop.webp"
      />

      {error && <Alert>{error}</Alert>}

      <CandidateSection eyebrow="Filters" title="Find a good fit">
        <form onSubmit={handleSubmit} className="grid gap-3 lg:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)_12rem_13rem_auto_auto] lg:items-end">
          <CandidateInput
            label="Keyword"
            value={filters.keyword}
            onChange={(event) => updateFilter("keyword", event.target.value)}
            placeholder="Search title, company, or keyword"
            error={fieldError(fieldErrors, "keyword")}
          />
          <CandidateInput
            label="Location"
            value={filters.location}
            onChange={(event) => updateFilter("location", event.target.value)}
            placeholder="City, country, remote"
            error={fieldError(fieldErrors, "location")}
          />
          <CandidateSelect
            label="Work mode"
            value={filters.work_mode}
            onChange={(event) => updateFilter("work_mode", event.target.value)}
            error={fieldError(fieldErrors, "work_mode")}
          >
            <option value="">All modes</option>
            {JOB_WORK_MODES.map((value) => (
              <option key={value} value={value}>{employmentTypeLabel(value)}</option>
            ))}
          </CandidateSelect>
          <CandidateSelect
            label="Employment"
            value={filters.employment_type}
            onChange={(event) => updateFilter("employment_type", event.target.value)}
            error={fieldError(fieldErrors, "employment_type")}
          >
            <option value="">All types</option>
            {JOB_EMPLOYMENT_TYPES.map((value) => (
              <option key={value} value={value}>{value}</option>
            ))}
          </CandidateSelect>
          <CandidateButton type="submit">
            <Search className="h-4 w-4" aria-hidden="true" />
            Search
          </CandidateButton>
          <CandidateButton type="button" onClick={handleReset} variant="secondary">
            <RotateCcw className="h-4 w-4" aria-hidden="true" />
            Reset
          </CandidateButton>
        </form>
        {activeFilters.length > 0 && (
          <div className="mt-4 flex flex-wrap gap-2" aria-label="Active filters">
            {activeFilters.map(([key, value]) => (
              <span key={key} className="rounded-full bg-[var(--candidate-surface-soft)] px-3 py-1 text-xs font-extrabold text-[var(--candidate-ink)] ring-1 ring-[var(--candidate-border)]">
                {key.replace("_", " ")}: {value}
              </span>
            ))}
          </div>
        )}
      </CandidateSection>

      {isLoading ? (
        <CandidateLoading label="Loading jobs" />
      ) : jobs.length === 0 ? (
        <CandidateEmptyState title="No jobs matched those filters" action={<CandidateButton type="button" onClick={handleReset}>Clear filters</CandidateButton>}>
          Try a broader keyword, leave location open, or browse all work modes.
        </CandidateEmptyState>
      ) : (
        <CandidateSection
          eyebrow="Open roles"
          title={`${jobs.length} published opportunities`}
          className="overflow-hidden"
        >
          <CandidateAnimatedList className="divide-y divide-[var(--candidate-border)]">
            {paginated.items.map((job) => (
              <article key={job.id} className="grid gap-4 py-5 lg:grid-cols-[minmax(0,1fr)_15rem] lg:items-start">
                <div className="min-w-0">
                  <p className="text-xs font-extrabold uppercase tracking-wide text-[var(--candidate-primary)]">
                    {job.company.name}
                  </p>
                  <h2 className="mt-1 text-xl font-extrabold text-[var(--candidate-ink-strong)]">{job.title}</h2>
                  <div className="mt-3 flex flex-wrap gap-2 text-sm font-bold text-[var(--candidate-muted)]">
                    <span className="inline-flex items-center gap-1.5">
                      <MapPin className="h-4 w-4" aria-hidden="true" />
                      {job.location || "Location flexible"}
                    </span>
                    <span>{job.work_mode}</span>
                    <span>{employmentTypeLabel(job.employment_type)}</span>
                  </div>
                  <p className="mt-4 line-clamp-3 text-sm leading-6 text-[var(--candidate-ink)]">
                    {job.description}
                  </p>
                </div>
                <div className="flex flex-col gap-3 lg:items-end">
                  <StatusBadge status={job.status} />
                  <p className="text-sm font-bold text-[var(--candidate-muted)]">
                    Deadline: {formatDate(job.deadline)}
                  </p>
                  <Link
                    to={`/candidate/jobs/${job.id}`}
                    className="candidate-button candidate-button--secondary w-full lg:w-auto"
                  >
                    View job
                    <ArrowRight className="h-4 w-4" aria-hidden="true" />
                  </Link>
                </div>
              </article>
            ))}
          </CandidateAnimatedList>
          <CandidatePagination
            page={paginated.safePage}
            totalPages={paginated.totalPages}
            onPageChange={handlePageChange}
            totalItems={jobs.length}
            pageSize={PAGE_SIZE}
          />
        </CandidateSection>
      )}
    </CandidatePage>
  );
}
