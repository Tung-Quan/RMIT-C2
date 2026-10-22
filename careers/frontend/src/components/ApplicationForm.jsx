import { Save } from "lucide-react";
import { useEffect, useState } from "react";

import { APPLICATION_STATUSES } from "../constants";
import { applicationFormSchema, clearFieldError, fieldError, validateForm } from "../validation/forms";

const emptyForm = {
  company_name: "",
  position_title: "",
  job_description: "",
  application_status: "Saved",
  deadline: "",
  notes: ""
};

export function ApplicationForm({ initialValues, isLoading, submitLabel, onSubmit }) {
  const [form, setForm] = useState(emptyForm);
  const [errors, setErrors] = useState({});

  useEffect(() => {
    if (initialValues) {
      setForm({
        company_name: initialValues.company_name || "",
        position_title: initialValues.position_title || "",
        job_description: initialValues.job_description || "",
        application_status: initialValues.application_status || "Saved",
        deadline: initialValues.deadline || "",
        notes: initialValues.notes || ""
      });
    }
  }, [initialValues]);

  function updateField(field, value) {
    setForm((current) => ({ ...current, [field]: value }));
    setErrors((current) => clearFieldError(current, field));
  }

  function handleSubmit(event) {
    event.preventDefault();
    const validation = validateForm(applicationFormSchema, form);
    if (!validation.data) {
      setErrors(validation.errors);
      return;
    }
    setErrors({});
    onSubmit(validation.data);
  }

  const inputClassName = "mt-1 w-full rounded-lg border border-zinc-300 px-3 py-2 text-zinc-950 outline-none focus:border-zinc-900 focus:ring-2 focus:ring-zinc-200";
  const errorClassName = "mt-1 text-xs font-semibold text-rose-600";

  return (
    <form onSubmit={handleSubmit} className="space-y-5 rounded-lg border border-zinc-200 bg-white p-5 shadow-sm">
      <div className="grid gap-5 md:grid-cols-2">
        <label className="block">
          <span className="text-sm font-medium text-zinc-700">Company</span>
          <input
            required
            value={form.company_name}
            onChange={(event) => updateField("company_name", event.target.value)}
            aria-invalid={Boolean(fieldError(errors, "company_name")) || undefined}
            className={inputClassName}
          />
          {fieldError(errors, "company_name") && <p className={errorClassName}>{fieldError(errors, "company_name")}</p>}
        </label>
        <label className="block">
          <span className="text-sm font-medium text-zinc-700">Position</span>
          <input
            required
            value={form.position_title}
            onChange={(event) => updateField("position_title", event.target.value)}
            aria-invalid={Boolean(fieldError(errors, "position_title")) || undefined}
            className={inputClassName}
          />
          {fieldError(errors, "position_title") && <p className={errorClassName}>{fieldError(errors, "position_title")}</p>}
        </label>
      </div>

      <label className="block">
        <span className="text-sm font-medium text-zinc-700">Job description</span>
        <textarea
          required
          rows="8"
          value={form.job_description}
          onChange={(event) => updateField("job_description", event.target.value)}
          aria-invalid={Boolean(fieldError(errors, "job_description")) || undefined}
          className={inputClassName}
        />
        {fieldError(errors, "job_description") && <p className={errorClassName}>{fieldError(errors, "job_description")}</p>}
      </label>

      <div className="grid gap-5 md:grid-cols-2">
        <label className="block">
          <span className="text-sm font-medium text-zinc-700">Status</span>
          <select
            value={form.application_status}
            onChange={(event) => updateField("application_status", event.target.value)}
            aria-invalid={Boolean(fieldError(errors, "application_status")) || undefined}
            className={inputClassName}
          >
            {APPLICATION_STATUSES.map((status) => (
              <option key={status} value={status}>{status}</option>
            ))}
          </select>
          {fieldError(errors, "application_status") && <p className={errorClassName}>{fieldError(errors, "application_status")}</p>}
        </label>
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
      </div>

      <label className="block">
        <span className="text-sm font-medium text-zinc-700">Notes</span>
        <textarea
          rows="4"
          value={form.notes}
          onChange={(event) => updateField("notes", event.target.value)}
          aria-invalid={Boolean(fieldError(errors, "notes")) || undefined}
          className={inputClassName}
        />
        {fieldError(errors, "notes") && <p className={errorClassName}>{fieldError(errors, "notes")}</p>}
      </label>

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
