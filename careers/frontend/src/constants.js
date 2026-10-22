export const APPLICATION_STATUSES = ["Saved", "Applied", "Interview", "Offer", "Rejected", "Accepted"];
export const DOCUMENT_TYPES = ["CV", "Transcript", "Certificate", "Other"];
export const USER_ROLES = ["candidate", "hr"];
export const JOB_POSTING_STATUSES = ["draft", "published", "closed"];
export const JOB_APPLICATION_STATUSES = [
  "submitted",
  "under_review",
  "shortlisted",
  "interview",
  "offered",
  "rejected",
  "withdrawn"
];
export const JOB_EMPLOYMENT_TYPES = ["early_career", "part_time", "full_time"];
export const employmentTypeLabel = (value) => ({
  early_career: "Early career",
  full_time: "Full time",
  part_time: "Part time",
}[value] ?? value.replaceAll("_", " "));
export const JOB_WORK_MODES = ["onsite", "hybrid", "remote"];

export const statusClassNames = {
  Saved: "bg-zinc-100 text-zinc-700 ring-zinc-200",
  Applied: "bg-sky-50 text-sky-700 ring-sky-200",
  Interview: "bg-amber-50 text-amber-800 ring-amber-200",
  Offer: "bg-emerald-50 text-emerald-700 ring-emerald-200",
  Rejected: "bg-rose-50 text-rose-700 ring-rose-200",
  Accepted: "bg-teal-50 text-teal-700 ring-teal-200",
  submitted: "bg-sky-50 text-sky-700 ring-sky-200",
  under_review: "bg-indigo-50 text-indigo-700 ring-indigo-200",
  shortlisted: "bg-amber-50 text-amber-800 ring-amber-200",
  interview: "bg-violet-50 text-violet-700 ring-violet-200",
  offered: "bg-emerald-50 text-emerald-700 ring-emerald-200",
  rejected: "bg-rose-50 text-rose-700 ring-rose-200",
  withdrawn: "bg-zinc-100 text-zinc-700 ring-zinc-200",
  draft: "bg-zinc-100 text-zinc-700 ring-zinc-200",
  published: "bg-emerald-50 text-emerald-700 ring-emerald-200",
  closed: "bg-rose-50 text-rose-700 ring-rose-200"
};
