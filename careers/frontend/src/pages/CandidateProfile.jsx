import {
  ArrowUpRight,
  BriefcaseBusiness,
  CheckCircle2,
  Github,
  GraduationCap,
  Linkedin,
  Loader2,
  Mail,
  MapPin,
  Phone,
  Save,
  Sparkles,
  UserRound
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { getCandidateProfile, updateCandidateProfile } from "../api/candidate";
import { getErrorMessage } from "../api/client";
import { Alert } from "../components/Alert";
import { candidateProfileSchema, clearFieldError, fieldError, validateForm } from "../validation/forms";

const emptyForm = {
  full_name: "",
  university: "",
  major: "",
  graduation_year: "",
  phone: "",
  location: "",
  linkedin_url: "",
  github_url: "",
  portfolio_url: "",
  bio: ""
};

const requiredFields = ["full_name", "university", "major", "graduation_year", "location", "bio"];
const optionalFields = ["phone", "linkedin_url", "github_url", "portfolio_url"];

function getInitials(name) {
  return (
    name
      .trim()
      .split(/\s+/)
      .slice(0, 2)
      .map((part) => part[0]?.toUpperCase())
      .join("") || "CP"
  );
}

function Field({ label, name, value, onChange, icon: Icon, type = "text", helper, error, ...props }) {
  const inputId = `candidate-profile-${name}`;

  return (
    <label className="profile-field" htmlFor={inputId}>
      <span className="profile-field__label">{label}</span>
      <span className="profile-field__control">
        {Icon && <Icon className="h-4 w-4 text-slate-400" aria-hidden="true" />}
        <input
          id={inputId}
          name={name}
          type={type}
          value={value}
          onChange={(event) => onChange(name, event.target.value)}
          aria-invalid={Boolean(error) || undefined}
          className="profile-input"
          {...props}
        />
      </span>
      {error ? <span className="profile-field__helper text-rose-600">{error}</span> : helper && <span className="profile-field__helper">{helper}</span>}
    </label>
  );
}

function TextAreaField({ label, name, value, onChange, helper, error }) {
  const inputId = `candidate-profile-${name}`;

  return (
    <label className="profile-field md:col-span-2" htmlFor={inputId}>
      <span className="profile-field__label">{label}</span>
      <textarea
        id={inputId}
        name={name}
        rows="7"
        value={value}
        onChange={(event) => onChange(name, event.target.value)}
        aria-invalid={Boolean(error) || undefined}
        className="profile-textarea"
      />
      {error ? <span className="profile-field__helper text-rose-600">{error}</span> : helper && <span className="profile-field__helper">{helper}</span>}
    </label>
  );
}

function ProfileSkeleton() {
  return (
    <div className="profile-page space-y-5" aria-busy="true" aria-label="Loading candidate profile">
      <div className="profile-skeleton h-72 rounded-[1.25rem]" />
      <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_20rem]">
        <div className="profile-skeleton h-[34rem] rounded-2xl" />
        <div className="profile-skeleton h-80 rounded-2xl" />
      </div>
    </div>
  );
}

function ProfilePreview({ form, completion }) {
  const name = form.full_name || "Candidate Profile";
  const roleLine = [form.major, form.university].filter(Boolean).join(" at ") || "Career-ready candidate";
  const location = form.location || "Location pending";

  return (
    <div className="profile-preview" aria-label="Profile preview">
      <div className="flex items-start justify-between gap-4">
        <div className="flex items-center gap-3">
          <div className="profile-avatar" aria-hidden="true">
            {getInitials(name)}
          </div>
          <div className="min-w-0">
            <p className="truncate text-base font-semibold text-slate-950">{name}</p>
            <p className="mt-1 truncate text-sm text-slate-500">{roleLine}</p>
          </div>
        </div>
        <span className="rounded-full bg-teal-50 px-3 py-1 text-xs font-semibold text-teal-700 ring-1 ring-teal-200">
          {completion}% ready
        </span>
      </div>

      <div className="mt-6 rounded-2xl bg-slate-950 p-4 text-white">
        <div className="flex items-center justify-between gap-4">
          <span className="text-sm text-slate-300">Profile strength</span>
          <span className="font-mono text-sm font-semibold">{completion}%</span>
        </div>
        <div className="mt-3 h-2 rounded-full bg-white/15">
          <div className="h-2 rounded-full bg-teal-300" style={{ width: `${completion}%` }} />
        </div>
      </div>

      <dl className="mt-5 space-y-3">
        <div className="profile-preview__row">
          <dt><MapPin className="h-4 w-4" aria-hidden="true" /> Location</dt>
          <dd>{location}</dd>
        </div>
        <div className="profile-preview__row">
          <dt><GraduationCap className="h-4 w-4" aria-hidden="true" /> Graduation</dt>
          <dd>{form.graduation_year || "Pending"}</dd>
        </div>
        <div className="profile-preview__row">
          <dt><BriefcaseBusiness className="h-4 w-4" aria-hidden="true" /> Portfolio</dt>
          <dd>{form.portfolio_url ? "Connected" : "Not added"}</dd>
        </div>
      </dl>
    </div>
  );
}

function Section({ eyebrow, title, children, delay = 0 }) {
  return (
    <section className="profile-section" style={{ "--profile-delay": `${delay}ms` }}>
      <div className="mb-5">
        <p className="profile-eyebrow">{eyebrow}</p>
        <h2 className="mt-1 text-lg font-semibold text-slate-950">{title}</h2>
      </div>
      {children}
    </section>
  );
}

function ReadinessRail({ form, completion, profileId }) {
  const checks = [
    { label: "Identity", done: Boolean(form.full_name && form.phone) },
    { label: "Academic details", done: Boolean(form.university && form.major && form.graduation_year) },
    { label: "Location", done: Boolean(form.location) },
    { label: "Professional links", done: Boolean(form.linkedin_url || form.github_url || form.portfolio_url) },
    { label: "Bio", done: Boolean(form.bio) }
  ];

  return (
    <aside className="space-y-5">
      <section className="profile-section" style={{ "--profile-delay": "180ms" }}>
        <div className="flex items-start gap-3">
          <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-teal-50 text-teal-700 ring-1 ring-teal-200">
            <Sparkles className="h-5 w-5" aria-hidden="true" />
          </span>
          <div>
            <p className="profile-eyebrow">Readiness</p>
            <h2 className="mt-1 text-lg font-semibold text-slate-950">Profile quality</h2>
          </div>
        </div>
        <div className="mt-5 rounded-2xl bg-slate-50 p-4">
          <div className="flex items-center justify-between gap-4">
            <span className="text-sm font-medium text-slate-700">Completion</span>
            <span className="font-mono text-sm font-semibold text-slate-950">{completion}%</span>
          </div>
          <div className="mt-3 h-2.5 rounded-full bg-slate-200">
            <div className="h-2.5 rounded-full bg-teal-500" style={{ width: `${completion}%` }} />
          </div>
        </div>
        <ul className="mt-5 space-y-3">
          {checks.map((check) => (
            <li key={check.label} className="flex items-center gap-3 text-sm text-slate-700">
              <CheckCircle2
                className={`h-4 w-4 ${check.done ? "text-teal-600" : "text-slate-300"}`}
                aria-hidden="true"
              />
              {check.label}
            </li>
          ))}
        </ul>
      </section>

      <section className="profile-section" style={{ "--profile-delay": "240ms" }}>
        <p className="profile-eyebrow">System state</p>
        <h2 className="mt-1 text-lg font-semibold text-slate-950">Visibility snapshot</h2>
        <dl className="mt-5 space-y-4">
          <div className="flex items-center justify-between gap-4">
            <dt className="text-sm text-slate-600">Profile record</dt>
            <dd className="text-sm font-semibold text-slate-950">{profileId ? "Created" : "Draft"}</dd>
          </div>
          <div className="flex items-center justify-between gap-4">
            <dt className="text-sm text-slate-600">Primary contact</dt>
            <dd className="text-sm font-semibold text-slate-950">{form.phone ? "Added" : "Missing"}</dd>
          </div>
          <div className="flex items-center justify-between gap-4">
            <dt className="text-sm text-slate-600">External proof</dt>
            <dd className="text-sm font-semibold text-slate-950">
              {[form.linkedin_url, form.github_url, form.portfolio_url].filter(Boolean).length}/3
            </dd>
          </div>
        </dl>
      </section>
    </aside>
  );
}

export function CandidateProfile() {
  const [form, setForm] = useState(emptyForm);
  const [profileId, setProfileId] = useState(null);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [fieldErrors, setFieldErrors] = useState({});
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);

  useEffect(() => {
    async function loadProfile() {
      setError("");
      try {
        const response = await getCandidateProfile();
        const profile = response.data;
        setProfileId(profile.id);
        setForm({
          full_name: profile.full_name || "",
          university: profile.university || "",
          major: profile.major || "",
          graduation_year: profile.graduation_year ?? "",
          phone: profile.phone || "",
          location: profile.location || "",
          linkedin_url: profile.linkedin_url || "",
          github_url: profile.github_url || "",
          portfolio_url: profile.portfolio_url || "",
          bio: profile.bio || ""
        });
      } catch (err) {
        setError(getErrorMessage(err));
      } finally {
        setIsLoading(false);
      }
    }

    loadProfile();
  }, []);

  const completion = useMemo(() => {
    const completedRequired = requiredFields.filter((field) => Boolean(String(form[field] ?? "").trim())).length;
    const completedOptional = optionalFields.filter((field) => Boolean(String(form[field] ?? "").trim())).length;
    return Math.round(((completedRequired + completedOptional) / (requiredFields.length + optionalFields.length)) * 100);
  }, [form]);

  function updateField(field, value) {
    setSuccess("");
    setForm((current) => ({ ...current, [field]: value }));
    setFieldErrors((current) => clearFieldError(current, field));
  }

  async function handleSubmit(event) {
    event.preventDefault();
    setError("");
    setSuccess("");
    const validation = validateForm(candidateProfileSchema, form);
    if (!validation.data) {
      setFieldErrors(validation.errors);
      setError(validation.formError);
      return;
    }
    setFieldErrors({});
    setIsSaving(true);
    try {
      const response = await updateCandidateProfile(validation.data);
      setProfileId(response.data.id);
      setSuccess("Candidate profile updated.");
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setIsSaving(false);
    }
  }

  if (isLoading) return <ProfileSkeleton />;

  return (
    <div className="profile-page">
      <div className="mb-5 flex flex-col justify-between gap-3 sm:flex-row sm:items-center">
        <div>
          <p className="profile-eyebrow">Candidate workspace</p>
          <h1 className="mt-1 text-2xl font-semibold text-slate-950 sm:text-3xl">Candidate profile</h1>
        </div>
        <button type="submit" form="candidate-profile-form" disabled={isSaving} className="profile-primary-action">
          {isSaving ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : <Save className="h-4 w-4" aria-hidden="true" />}
          {isSaving ? "Saving profile" : profileId ? "Save profile" : "Create profile"}
        </button>
      </div>

      {error && <Alert>{error}</Alert>}
      {success && <Alert type="success">{success}</Alert>}

      <section className="profile-hero" aria-labelledby="candidate-profile-hero-title">
        <div className="profile-hero__content">
          <p className="profile-hero__kicker">
            <UserRound className="h-4 w-4" aria-hidden="true" />
            HR-ready identity
          </p>
          <h2 id="candidate-profile-hero-title" className="profile-hero__title">
            Shape the profile employers see before they open your documents.
          </h2>
          <p className="profile-hero__copy">
            Keep your academic details, contact channels, portfolio links, and short bio aligned so applications feel
            complete instead of scattered.
          </p>
          <div className="mt-6 grid gap-3 sm:grid-cols-3">
            <div className="profile-proof"><Mail className="h-4 w-4 text-sky-600" aria-hidden="true" /> Contactable</div>
            <div className="profile-proof"><GraduationCap className="h-4 w-4 text-teal-600" aria-hidden="true" /> Academic context</div>
            <div className="profile-proof"><ArrowUpRight className="h-4 w-4 text-amber-600" aria-hidden="true" /> Proof links</div>
          </div>
        </div>
        <ProfilePreview form={form} completion={completion} />
      </section>

      <div className="mt-5 grid gap-5 lg:grid-cols-[minmax(0,1fr)_20rem]">
        <form id="candidate-profile-form" onSubmit={handleSubmit} className="space-y-5">
          <Section eyebrow="Identity" title="Personal details" delay={80}>
            <div className="grid gap-4 md:grid-cols-2">
              <Field label="Full name" name="full_name" value={form.full_name} onChange={updateField} icon={UserRound} error={fieldError(fieldErrors, "full_name")} />
              <Field label="Phone" name="phone" value={form.phone} onChange={updateField} icon={Phone} autoComplete="tel" error={fieldError(fieldErrors, "phone")} />
              <Field label="Location" name="location" value={form.location} onChange={updateField} icon={MapPin} helper="City, country, or preferred work region." error={fieldError(fieldErrors, "location")} />
            </div>
          </Section>

          <Section eyebrow="Education" title="Academic signal" delay={140}>
            <div className="grid gap-4 md:grid-cols-3">
              <Field label="University" name="university" value={form.university} onChange={updateField} icon={GraduationCap} error={fieldError(fieldErrors, "university")} />
              <Field label="Major" name="major" value={form.major} onChange={updateField} icon={BriefcaseBusiness} error={fieldError(fieldErrors, "major")} />
              <Field
                label="Graduation year"
                name="graduation_year"
                type="number"
                min="1900"
                max="2100"
                value={form.graduation_year}
                onChange={updateField}
                icon={GraduationCap}
                error={fieldError(fieldErrors, "graduation_year")}
              />
            </div>
          </Section>

          <Section eyebrow="Portfolio" title="Proof and professional links" delay={200}>
            <div className="grid gap-4 md:grid-cols-2">
              <Field label="LinkedIn URL" name="linkedin_url" value={form.linkedin_url} onChange={updateField} icon={Linkedin} type="url" autoComplete="url" error={fieldError(fieldErrors, "linkedin_url")} />
              <Field label="GitHub URL" name="github_url" value={form.github_url} onChange={updateField} icon={Github} type="url" autoComplete="url" error={fieldError(fieldErrors, "github_url")} />
              <Field label="Portfolio URL" name="portfolio_url" value={form.portfolio_url} onChange={updateField} icon={ArrowUpRight} type="url" autoComplete="url" helper="Add a case-study site, personal page, or project collection." error={fieldError(fieldErrors, "portfolio_url")} />
            </div>
          </Section>

          <Section eyebrow="Narrative" title="Candidate bio" delay={260}>
            <div className="grid gap-4 md:grid-cols-2">
              <TextAreaField
                label="Bio"
                name="bio"
                value={form.bio}
                onChange={updateField}
                helper="Summarize your focus, strongest evidence, and what career opportunities you want next."
                error={fieldError(fieldErrors, "bio")}
              />
            </div>
          </Section>
        </form>

        <ReadinessRail form={form} completion={completion} profileId={profileId} />
      </div>
    </div>
  );
}
