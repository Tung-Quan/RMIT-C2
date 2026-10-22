import {
  ArrowRight,
  BriefcaseBusiness,
  FileSearch,
  Inbox,
  LayoutDashboard,
  MessageCircle,
  Search,
  Send,
  Settings,
  UserRound
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { getApplications } from "../api/applications";
import { getCandidateJobApplications } from "../api/candidate";
import { getErrorMessage } from "../api/client";
import { getHrJobs } from "../api/hr";
import { getJobs } from "../api/jobs";
import { employmentTypeLabel } from "../constants";
import { Alert } from "../components/Alert";
import {
  CandidateButton,
  CandidatePage,
  CandidateSpinner,
  cx,
  formatDate,
  formatStatusLabel
} from "../components/candidate/CandidateUI";
import { useAuth } from "../context/AuthContext";
import { parseWorkspaceSearch } from "../validation/forms";

const sharedRoutes = [
  {
    title: "Chat",
    subtitle: "Direct messages and group rooms",
    to: "/chat",
    type: "Workspace",
    icon: MessageCircle,
    keywords: "chat inbox message channel communication"
  },
  {
    title: "Settings",
    subtitle: "Preferences, privacy, and account controls",
    to: "/settings",
    type: "Workspace",
    icon: Settings,
    keywords: "setting preference account privacy"
  }
];

const candidateRoutes = [
  {
    title: "Candidate Dashboard",
    subtitle: "Deadlines, recent applications, and next actions",
    to: "/candidate/dashboard",
    type: "Navigation",
    icon: LayoutDashboard,
    keywords: "dashboard overview candidate"
  },
  {
    title: "Job Board",
    subtitle: "Browse jobs and apply with your profile",
    to: "/candidate/jobs",
    type: "Navigation",
    icon: BriefcaseBusiness,
    keywords: "job board careers early career role"
  },
  {
    title: "Submissions",
    subtitle: "Track submitted job applications",
    to: "/candidate/job-applications",
    type: "Navigation",
    icon: Send,
    keywords: "submitted submissions applications"
  },
  {
    title: "Saved Tracker",
    subtitle: "Personal applications and documents",
    to: "/applications",
    type: "Navigation",
    icon: Inbox,
    keywords: "saved tracker application document"
  },
  {
    title: "AI CV Matching",
    subtitle: "Analyze CV fit and interview preparation",
    to: "/applications/ai-cv-matching",
    type: "Navigation",
    icon: FileSearch,
    keywords: "ai cv matching resume interview"
  },
  {
    title: "Profile",
    subtitle: "Candidate details and portfolio links",
    to: "/candidate/profile",
    type: "Navigation",
    icon: UserRound,
    keywords: "profile candidate university portfolio"
  }
];

const hrRoutes = [
  {
    title: "HR Dashboard",
    subtitle: "Company hiring overview",
    to: "/hr/dashboard",
    type: "Navigation",
    icon: LayoutDashboard,
    keywords: "dashboard hr overview"
  },
  {
    title: "Company",
    subtitle: "Company profile and hiring identity",
    to: "/hr/company",
    type: "Navigation",
    icon: BriefcaseBusiness,
    keywords: "company hr profile"
  },
  {
    title: "Jobs",
    subtitle: "Manage postings and applicants",
    to: "/hr/jobs",
    type: "Navigation",
    icon: BriefcaseBusiness,
    keywords: "jobs postings applicants hr"
  }
];

function normalize(value) {
  return String(value || "").toLowerCase();
}

function matchesQuery(item, query) {
  if (!query) return true;
  const haystack = normalize(`${item.title} ${item.subtitle} ${item.type} ${item.keywords || ""} ${item.meta || ""}`);
  return haystack.includes(query);
}

function routeItemsForRole(role) {
  return [...(role === "hr" ? hrRoutes : candidateRoutes), ...sharedRoutes];
}

function mapApplication(application) {
  return {
    id: `application-${application.id}`,
    title: `${application.company_name} - ${application.position_title}`,
    subtitle: application.notes || application.job_description || "Personal tracker application",
    meta: formatStatusLabel(application.application_status),
    type: "Saved",
    to: `/applications/${application.id}`,
    icon: Inbox
  };
}

function mapJob(job) {
  return {
    id: `job-${job.id}`,
    title: job.title,
    subtitle: job.company?.name || job.location || "Published opportunity",
    meta: [job.work_mode, job.employment_type, job.deadline ? `Deadline ${formatDate(job.deadline)}` : ""]
      .filter(Boolean)
      .join(" - "),
    type: "Job",
    to: `/candidate/jobs/${job.id}`,
    icon: BriefcaseBusiness
  };
}

function mapCandidateSubmission(application) {
  return {
    id: `submission-${application.id}`,
    title: application.job_posting?.title || "Submitted application",
    subtitle: application.job_posting?.company?.name || "Candidate submission",
    meta: formatStatusLabel(application.status),
    type: "Submission",
    to: `/candidate/job-applications/${application.id}`,
    icon: Send
  };
}

function mapHrJob(job) {
  return {
    id: `hr-job-${job.id}`,
    title: job.title,
    subtitle: job.company?.name || job.location || "Hiring post",
    meta: formatStatusLabel(job.status),
    type: "HR Job",
    to: `/hr/jobs/${job.id}`,
    icon: BriefcaseBusiness
  };
}

function SearchResultItem({ item }) {
  const Icon = item.icon || Search;

  return (
    <Link
      to={item.to}
      className="group grid gap-3 rounded-lg px-3 py-3 transition hover:bg-[var(--candidate-surface-soft)] focus-visible:bg-[var(--candidate-surface-soft)] focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-[rgba(0,141,218,0.14)] sm:grid-cols-[2.5rem_minmax(0,1fr)_auto] sm:items-center"
    >
      <span className="flex h-10 w-10 items-center justify-center rounded-lg bg-white text-[var(--candidate-primary)] ring-1 ring-[var(--candidate-border)]">
        <Icon className="h-5 w-5" aria-hidden="true" />
      </span>
      <span className="min-w-0">
        <span className="block truncate text-sm font-extrabold text-[var(--candidate-ink-strong)]">{item.title}</span>
        <span className="mt-1 block truncate text-sm text-[var(--candidate-muted)]">{item.subtitle}</span>
        {item.meta && <span className="mt-1 block truncate text-xs font-bold text-[var(--candidate-primary)]">{item.meta}</span>}
      </span>
      <span className="flex items-center justify-between gap-2 sm:justify-end">
        <span className="rounded-full bg-white px-3 py-1 text-xs font-extrabold text-[var(--candidate-muted)] ring-1 ring-[var(--candidate-border)]">
          {item.type}
        </span>
        <ArrowRight className="h-4 w-4 text-[var(--candidate-muted)] transition group-hover:translate-x-0.5 group-hover:text-[var(--candidate-primary)]" aria-hidden="true" />
      </span>
    </Link>
  );
}

export function SearchResults() {
  const { user } = useAuth();
  const [searchParams, setSearchParams] = useSearchParams();
  const initialQuery = searchParams.get("q") || "";
  const [query, setQuery] = useState(initialQuery);
  const [remoteItems, setRemoteItems] = useState([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState("");
  const [fieldError, setFieldError] = useState("");

  useEffect(() => {
    setQuery(searchParams.get("q") || "");
  }, [searchParams]);

  useEffect(() => {
    let cancelled = false;
    const normalizedQuery = normalize(searchParams.get("q"));

    async function loadSearchData() {
      setIsLoading(true);
      setError("");
      try {
        const requests =
          user?.role === "hr"
            ? [getHrJobs()]
            : [getJobs({ keyword: normalizedQuery }), getApplications(), getCandidateJobApplications()];
        const responses = await Promise.allSettled(requests);
        if (cancelled) return;

        const nextItems = [];
        if (user?.role === "hr") {
          const hrJobs = responses[0].status === "fulfilled" ? responses[0].value.data : [];
          nextItems.push(...hrJobs.map(mapHrJob));
        } else {
          const jobs = responses[0].status === "fulfilled" ? responses[0].value.data : [];
          const applications = responses[1].status === "fulfilled" ? responses[1].value.data : [];
          const submissions = responses[2].status === "fulfilled" ? responses[2].value.data : [];
          nextItems.push(...jobs.map(mapJob), ...applications.map(mapApplication), ...submissions.map(mapCandidateSubmission));
        }

        const rejected = responses.find((response) => response.status === "rejected");
        if (rejected) setError(getErrorMessage(rejected.reason));
        setRemoteItems(nextItems);
      } catch (err) {
        if (!cancelled) setError(getErrorMessage(err));
      } finally {
        if (!cancelled) setIsLoading(false);
      }
    }

    loadSearchData();
    return () => {
      cancelled = true;
    };
  }, [searchParams, user?.role]);

  const normalizedQuery = normalize(searchParams.get("q"));
  const routeItems = useMemo(() => routeItemsForRole(user?.role), [user?.role]);
  const results = useMemo(() => {
    const items = [...routeItems, ...remoteItems];
    const filtered = items.filter((item) => matchesQuery(item, normalizedQuery));
    return filtered.slice(0, 30);
  }, [normalizedQuery, remoteItems, routeItems]);

  function handleSubmit(event) {
    event.preventDefault();
    const parsed = parseWorkspaceSearch(query);
    if (parsed.error) {
      setFieldError(parsed.error);
      return;
    }
    setFieldError("");
    setSearchParams(parsed.query ? { q: parsed.query } : {});
  }

  return (
    <CandidatePage>
      <section className="grid gap-5 lg:grid-cols-[minmax(0,0.65fr)_minmax(18rem,0.35fr)] lg:items-end">
        <div>
          <p className="candidate-eyebrow">Workspace search</p>
          <h1 className="candidate-title">Find the next place to move.</h1>
          <p className="candidate-copy">
            Search routes, jobs, saved tracker items, submissions, and workspace tools without exposing private configuration.
          </p>
        </div>
        <div className="candidate-soft-surface p-4">
          <p className="text-sm font-bold text-[var(--candidate-muted)]">Visible scope</p>
          <p className="mt-1 text-lg font-extrabold text-[var(--candidate-ink-strong)]">Workspace data only</p>
          <p className="mt-2 text-sm leading-6 text-[var(--candidate-muted)]">
            Secrets, API keys, and private environment values stay hidden from this interface.
          </p>
        </div>
      </section>

      <form onSubmit={handleSubmit} className="candidate-surface p-3" role="search">
        <div className="flex flex-col gap-3 sm:flex-row">
          <label className="relative min-w-0 flex-1">
            <span className="sr-only">Search workspace</span>
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-[var(--candidate-muted)]" aria-hidden="true" />
            <input
              value={query}
              onChange={(event) => {
                setQuery(event.target.value);
                setFieldError("");
              }}
              placeholder="Search jobs, applications, chat, settings..."
              maxLength={80}
              aria-invalid={Boolean(fieldError) || undefined}
              className="candidate-control m-0 min-h-12 pl-9"
            />
            {fieldError && <span className="candidate-helper text-rose-600">{fieldError}</span>}
          </label>
          <CandidateButton type="submit" className="min-h-12" disabled={isLoading}>
            <Search className="h-4 w-4" aria-hidden="true" />
            {isLoading ? "Searching" : "Search"}
          </CandidateButton>
        </div>
      </form>

      {error && <Alert>{error}</Alert>}

      <section className="candidate-surface p-4 sm:p-5">
        <div className="mb-4 flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <p className="candidate-eyebrow">Results</p>
            <h2 className="mt-1 text-lg font-extrabold text-[var(--candidate-ink-strong)]">
              {normalizedQuery ? `Matches for "${searchParams.get("q")}"` : "Quick destinations"}
            </h2>
          </div>
          {isLoading && <CandidateSpinner label="Searching" />}
        </div>

        <div className={cx("divide-y divide-[var(--candidate-border)]", isLoading && "opacity-70")}>
          {results.length === 0 && !isLoading ? (
            <div className="candidate-soft-surface px-4 py-10 text-center">
              <Search className="mx-auto h-8 w-8 text-[var(--candidate-primary)]" aria-hidden="true" />
              <p className="mt-3 text-base font-extrabold text-[var(--candidate-ink-strong)]">No matching results</p>
              <p className="mx-auto mt-2 max-w-xl text-sm leading-6 text-[var(--candidate-muted)]">
                Try a company name, job title, application status, or workspace section.
              </p>
            </div>
          ) : (
            results.map((item) => <SearchResultItem key={item.id || item.to} item={item} />)
          )}
        </div>
      </section>
    </CandidatePage>
  );
}
