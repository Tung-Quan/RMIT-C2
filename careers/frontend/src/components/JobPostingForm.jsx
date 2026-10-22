import { Save } from "lucide-react";
import { useEffect, useState } from "react";

import { employmentTypeLabel, JOB_EMPLOYMENT_TYPES, JOB_POSTING_STATUSES, JOB_WORK_MODES } from "../constants";
import { clearFieldError, fieldError, jobPostingFormSchema, validateForm } from "../validation/forms";

const emptyForm = {
  title: "",
  description: "",
  requirements: "",
  responsibilities: "",
  location: "",
  employment_type: "early_career",
  work_mode: "onsite",
  salary_min: "",
  salary_max: "",
  deadline: "",
  status: "draft"
};

export function JobPostingForm({
  initialValues,
  isLoading,
  showStatus = true,
  submitLabel,
  onSubmit
}) {
  const [form, setForm] = useState(emptyForm);
  const [errors, setErrors] = useState({});

  useEffect(() => {
    if (!initialValues) return;
    setForm({
      title: initialValues.title || "",
      description: initialValues.description || "",
      requirements: initialValues.requirements || "",
      responsibilities: initialValues.responsibilities || "",
      location: initialValues.location || "",
      employment_type: initialValues.employment_type || "early_career",
      work_mode: initialValues.work_mode || "onsite",
      salary_min: initialValues.salary_min ?? "",
      salary_max: initialValues.salary_max ?? "",
      deadline: initialValues.deadline || "",
      status: initialValues.status || "draft"
    });
  }, [initialValues]);

  function updateField(field, value) {
    setForm((current) => ({ ...current, [field]: value }));
    setErrors((current) => clearFieldError(current, field));
  }

  function handleSubmit(event) {
    event.preventDefault();
    const validation = validateForm(jobPostingFormSchema, form);
    if (!validation.data) {
      setErrors(validation.errors);
      return;
    }
    setErrors({});
    const { status, ...payload } = validation.data;
    if (showStatus) {
      payload.status = status;
    }
    onSubmit(payload);
  }

  const inputClassName = "mt-1 w-full rounded-lg border border-zinc-300 px-3 py-2 outline-none focus:border-zinc-900 focus:ring-2 focus:ring-zinc-200";
  const errorClassName = "mt-1 text-xs font-semibold text-rose-600";

  return (
    <form onSubmit={handleSubmit} className="space-y-5 rounded-lg border border-zinc-200 bg-white p-5 shadow-sm">
      <div className="grid gap-5 md:grid-cols-2">
        <label className="block">
          <span className="text-sm font-medium text-zinc-700">Job title</span>
          <input
            required
            value={form.title}
            onChange={(event) => updateField("title", event.target.value)}
            aria-invalid={Boolean(fieldError(errors, "title")) || undefined}
            className={inputClassName}
          />
          {fieldError(errors, "title") && <p className={errorClassName}>{fieldError(errors, "title")}</p>}
        </label>
        <label className="block">
          <span className="text-sm font-medium text-zinc-700">Location</span>
          <input
            value={form.location}
            onChange={(event) => updateField("location", event.target.value)}
            aria-invalid={Boolean(fieldError(errors, "location")) || undefined}
            className={inputClassName}
          />
          {fieldError(errors, "location") && <p className={errorClassName}>{fieldError(errors, "location")}</p>}
        </label>
      </div>

      <label className="block">
        <span className="text-sm font-medium text-zinc-700">Description</span>
        <textarea
          required
          rows="8"
          value={form.description}
          onChange={(event) => updateField("description", event.target.value)}
          aria-invalid={Boolean(fieldError(errors, "description")) || undefined}
          className={inputClassName}
        />
        {fieldError(errors, "description") && <p className={errorClassName}>{fieldError(errors, "description")}</p>}
      </label>

      <div className="grid gap-5 md:grid-cols-2">
        <label className="block">
          <span className="text-sm font-medium text-zinc-700">Requirements</span>
          <textarea
            rows="5"
            value={form.requirements}
            onChange={(event) => updateField("requirements", event.target.value)}
            aria-invalid={Boolean(fieldError(errors, "requirements")) || undefined}
            className={inputClassName}
          />
          {fieldError(errors, "requirements") && <p className={errorClassName}>{fieldError(errors, "requirements")}</p>}
        </label>
        <label className="block">
          <span className="text-sm font-medium text-zinc-700">Responsibilities</span>
          <textarea
            rows="5"
            value={form.responsibilities}
            onChange={(event) => updateField("responsibilities", event.target.value)}
            aria-invalid={Boolean(fieldError(errors, "responsibilities")) || undefined}
            className={inputClassName}
          />
          {fieldError(errors, "responsibilities") && <p className={errorClassName}>{fieldError(errors, "responsibilities")}</p>}
        </label>
      </div>

      <div className="grid gap-5 md:grid-cols-2 xl:grid-cols-4">
        <label className="block">
          <span className="text-sm font-medium text-zinc-700">Employment type</span>
          <select
            value={form.employment_type}
            onChange={(event) => updateField("employment_type", event.target.value)}
            aria-invalid={Boolean(fieldError(errors, "employment_type")) || undefined}
            className={inputClassName}
          >
            {JOB_EMPLOYMENT_TYPES.map((value) => (
              <option key={value} value={value}>{employmentTypeLabel(value)}</option>
            ))}
          </select>
          {fieldError(errors, "employment_type") && <p className={errorClassName}>{fieldError(errors, "employment_type")}</p>}
        </label>
        <label className="block">
          <span className="text-sm font-medium text-zinc-700">Work mode</span>
          <select
            value={form.work_mode}
            onChange={(event) => updateField("work_mode", event.target.value)}
            aria-invalid={Boolean(fieldError(errors, "work_mode")) || undefined}
            className={inputClassName}
          >
            {JOB_WORK_MODES.map((value) => (
              <option key={value} value={value}>{value}</option>
            ))}
          </select>
          {fieldError(errors, "work_mode") && <p className={errorClassName}>{fieldError(errors, "work_mode")}</p>}
        </label>
        <label className="block">
          <span className="text-sm font-medium text-zinc-700">Salary min</span>
          <input
            type="number"
            min="0"
            value={form.salary_min}
            onChange={(event) => updateField("salary_min", event.target.value)}
            aria-invalid={Boolean(fieldError(errors, "salary_min")) || undefined}
            className={inputClassName}
          />
          {fieldError(errors, "salary_min") && <p className={errorClassName}>{fieldError(errors, "salary_min")}</p>}
        </label>
        <label className="block">
          <span className="text-sm font-medium text-zinc-700">Salary max</span>
          <input
            type="number"
            min="0"
            value={form.salary_max}
            onChange={(event) => updateField("salary_max", event.target.value)}
            aria-invalid={Boolean(fieldError(errors, "salary_max")) || undefined}
            className={inputClassName}
          />
          {fieldError(errors, "salary_max") && <p className={errorClassName}>{fieldError(errors, "salary_max")}</p>}
        </label>
      </div>

      <div className="grid gap-5 md:grid-cols-2">
        <label className="block">
          <span className="text-sm font-medium text-zinc-700">Deadline</span>
          <input
            type="date"
            value={form.deadline}
            onChange={(event) => updateField("deadline", event.target.value)}
            aria-invalid={Boolean(fieldError(errors, "deadline")) || undefined}
            className={inputClassName}
          />
          {fieldError(errors, "deadline") && <p className={errorClassName}>{fieldError(errors, "deadline")}</p>}
        </label>
        {showStatus && (
          <label className="block">
            <span className="text-sm font-medium text-zinc-700">Status</span>
            <select
              value={form.status}
              onChange={(event) => updateField("status", event.target.value)}
              aria-invalid={Boolean(fieldError(errors, "status")) || undefined}
              className={inputClassName}
            >
              {JOB_POSTING_STATUSES.map((value) => (
                <option key={value} value={value}>{value}</option>
              ))}
            </select>
            {fieldError(errors, "status") && <p className={errorClassName}>{fieldError(errors, "status")}</p>}
          </label>
        )}
      </div>

      <button
        type="submit"
        disabled={isLoading}
        className="inline-flex items-center gap-2 rounded-lg bg-zinc-900 px-4 py-2.5 text-sm font-semibold text-white hover:bg-zinc-800 disabled:cursor-not-allowed disabled:opacity-60"
      >
        <Save className="h-4 w-4" />
        {isLoading ? "Saving" : submitLabel}
      </button>
    </form>
  );
}
