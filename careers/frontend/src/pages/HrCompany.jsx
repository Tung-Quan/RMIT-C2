import { useEffect, useState } from "react";

import { createCompany, getMyCompany, updateCompany } from "../api/companies";
import { getErrorMessage } from "../api/client";
import { Alert } from "../components/Alert";
import { clearFieldError, companyProfileSchema, fieldError, validateForm } from "../validation/forms";

const emptyForm = {
  name: "",
  description: "",
  website: "",
  industry: "",
  location: "",
  logo_url: ""
};

function getCompanyId(company) {
  const id = Number(company?.id ?? company?.company_id);
  return Number.isInteger(id) && id > 0 ? id : null;
}

function normalizeCompany(value) {
  if (!value) return null;
  const company = value.company || value;
  const id = getCompanyId(company) || getCompanyId(value);
  return id ? { ...company, id } : null;
}

function formFromCompany(company) {
  return {
    name: company?.name || "",
    description: company?.description || "",
    website: company?.website || "",
    industry: company?.industry || "",
    location: company?.location || "",
    logo_url: company?.logo_url || ""
  };
}

export function HrCompany() {
  const [company, setCompany] = useState(null);
  const [form, setForm] = useState(emptyForm);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [fieldErrors, setFieldErrors] = useState({});
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);

  useEffect(() => {
    async function loadCompany() {
      setError("");
      try {
        const response = await getMyCompany();
        const loadedCompany = normalizeCompany(response.data);
        setCompany(loadedCompany);
        setForm(formFromCompany(loadedCompany));
      } catch (err) {
        if (err?.response?.status === 404) {
          setCompany(null);
          setForm(emptyForm);
        } else {
          setError(getErrorMessage(err));
        }
      } finally {
        setIsLoading(false);
      }
    }

    loadCompany();
  }, []);

  function updateField(field, value) {
    setForm((current) => ({ ...current, [field]: value }));
    setFieldErrors((current) => clearFieldError(current, field));
  }

  async function handleSubmit(event) {
    event.preventDefault();
    setError("");
    setSuccess("");
    const validation = validateForm(companyProfileSchema, form);
    if (!validation.data) {
      setFieldErrors(validation.errors);
      setError(validation.formError);
      return;
    }
    setFieldErrors({});
    setIsSaving(true);
    const payload = validation.data;

    const companyId = getCompanyId(company);
    try {
      const response = companyId
        ? await updateCompany(companyId, payload)
        : await createCompany(payload);
      const savedCompany = normalizeCompany(response.data);
      setCompany(savedCompany);
      setSuccess(companyId ? "Company updated." : "Company created.");
    } catch (err) {
      if (!companyId && err?.response?.status === 409) {
        try {
          const response = await getMyCompany();
          const loadedCompany = normalizeCompany(response.data);
          if (loadedCompany) {
            setCompany(loadedCompany);
            setForm(formFromCompany(loadedCompany));
            setSuccess("Company profile already exists. Loaded the latest profile.");
            return;
          }
        } catch {
          // Fall through to the original conflict message if the refresh cannot recover.
        }
      }
      setError(getErrorMessage(err));
    } finally {
      setIsSaving(false);
    }
  }

  if (isLoading) return <p className="text-sm text-zinc-500">Loading company profile</p>;
  const inputClassName = "mt-1 w-full rounded-lg border border-zinc-300 px-3 py-2 outline-none focus:border-zinc-900 focus:ring-2 focus:ring-zinc-200";
  const errorClassName = "mt-1 text-xs font-semibold text-rose-600";

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold text-zinc-950">Company profile</h1>
        <p className="mt-1 text-sm text-zinc-500">
          Set up the company identity candidates will see on the job board.
        </p>
      </div>

      {error && <Alert>{error}</Alert>}
      {success && <Alert type="success">{success}</Alert>}

      <form onSubmit={handleSubmit} className="space-y-5 rounded-lg border border-zinc-200 bg-white p-5 shadow-sm">
        <div className="grid gap-5 md:grid-cols-2">
          <label className="block">
            <span className="text-sm font-medium text-zinc-700">Company name</span>
            <input
              required
              value={form.name}
              onChange={(event) => updateField("name", event.target.value)}
              aria-invalid={Boolean(fieldError(fieldErrors, "name")) || undefined}
              className={inputClassName}
            />
            {fieldError(fieldErrors, "name") && <p className={errorClassName}>{fieldError(fieldErrors, "name")}</p>}
          </label>
          <label className="block">
            <span className="text-sm font-medium text-zinc-700">Industry</span>
            <input
              value={form.industry}
              onChange={(event) => updateField("industry", event.target.value)}
              aria-invalid={Boolean(fieldError(fieldErrors, "industry")) || undefined}
              className={inputClassName}
            />
            {fieldError(fieldErrors, "industry") && <p className={errorClassName}>{fieldError(fieldErrors, "industry")}</p>}
          </label>
        </div>

        <div className="grid gap-5 md:grid-cols-2">
          <label className="block">
            <span className="text-sm font-medium text-zinc-700">Website</span>
            <input
              value={form.website}
              onChange={(event) => updateField("website", event.target.value)}
              aria-invalid={Boolean(fieldError(fieldErrors, "website")) || undefined}
              className={inputClassName}
            />
            {fieldError(fieldErrors, "website") && <p className={errorClassName}>{fieldError(fieldErrors, "website")}</p>}
          </label>
          <label className="block">
            <span className="text-sm font-medium text-zinc-700">Location</span>
            <input
              value={form.location}
              onChange={(event) => updateField("location", event.target.value)}
              aria-invalid={Boolean(fieldError(fieldErrors, "location")) || undefined}
              className={inputClassName}
            />
            {fieldError(fieldErrors, "location") && <p className={errorClassName}>{fieldError(fieldErrors, "location")}</p>}
          </label>
        </div>

        <label className="block">
          <span className="text-sm font-medium text-zinc-700">Logo URL</span>
          <input
            value={form.logo_url}
            onChange={(event) => updateField("logo_url", event.target.value)}
            aria-invalid={Boolean(fieldError(fieldErrors, "logo_url")) || undefined}
            className={inputClassName}
          />
          {fieldError(fieldErrors, "logo_url") && <p className={errorClassName}>{fieldError(fieldErrors, "logo_url")}</p>}
        </label>

        <label className="block">
          <span className="text-sm font-medium text-zinc-700">Description</span>
          <textarea
            rows="6"
            value={form.description}
            onChange={(event) => updateField("description", event.target.value)}
            aria-invalid={Boolean(fieldError(fieldErrors, "description")) || undefined}
            className={inputClassName}
          />
          {fieldError(fieldErrors, "description") && <p className={errorClassName}>{fieldError(fieldErrors, "description")}</p>}
        </label>

        <button
          type="submit"
          disabled={isSaving}
          className="inline-flex items-center justify-center rounded-lg bg-zinc-900 px-4 py-2.5 text-sm font-semibold text-white hover:bg-zinc-800 disabled:cursor-not-allowed disabled:opacity-60"
        >
          {isSaving ? "Saving" : company ? "Save company" : "Create company"}
        </button>
      </form>
    </div>
  );
}
