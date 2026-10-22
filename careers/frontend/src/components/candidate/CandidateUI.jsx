import { motion, useReducedMotion } from "motion/react";
import { ChevronLeft, ChevronRight, Inbox, Loader2 } from "lucide-react";
import { Link } from "react-router-dom";

export function cx(...classes) {
  return classes.filter(Boolean).join(" ");
}

export function formatStatusLabel(status) {
  return String(status || "")
    .replace(/_/g, " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

export function formatDate(value) {
  if (!value) return "No date listed";
  return new Date(value).toLocaleDateString();
}

export function formatDateTime(value) {
  if (!value) return "No date listed";
  return new Date(value).toLocaleString();
}

export function CandidatePage({ children, className }) {
  return <div className={cx("candidate-shell candidate-page", className)}>{children}</div>;
}

export function CandidateHero({ eyebrow, title, copy, actions, imageSrc, children }) {
  return (
    <section className="candidate-hero" aria-labelledby="candidate-page-title">
      <div className={cx("grid gap-5", imageSrc && "lg:grid-cols-[minmax(0,1fr)_24rem] lg:items-center")}>
        <div>
          {eyebrow && <p className="candidate-eyebrow">{eyebrow}</p>}
          <h1 id="candidate-page-title" className="candidate-title">{title}</h1>
          {copy && <p className="candidate-copy">{copy}</p>}
          {actions && <div className="mt-5 flex flex-wrap gap-3">{actions}</div>}
          {children}
        </div>
        {imageSrc && (
          <div className="hidden overflow-hidden rounded-xl border border-[var(--candidate-border)] bg-[rgba(255,253,246,0.72)] p-2 shadow-sm md:block">
            <img
              src={imageSrc}
              alt=""
              width="720"
              height="480"
              className="h-56 w-full rounded-lg object-cover lg:h-64"
              loading="eager"
              fetchpriority="high"
            />
          </div>
        )}
      </div>
    </section>
  );
}

export function CandidateButton({ to, children, variant = "primary", className, ...props }) {
  const buttonClassName = cx(
    "candidate-button",
    variant === "primary" && "candidate-button--primary",
    variant === "secondary" && "candidate-button--secondary",
    variant === "danger" && "candidate-button--danger",
    className
  );

  if (to) {
    return <Link to={to} className={buttonClassName} {...props}>{children}</Link>;
  }

  return <button className={buttonClassName} {...props}>{children}</button>;
}

export function CandidateSection({ title, eyebrow, action, children, className }) {
  return (
    <section className={cx("candidate-surface p-4 sm:p-5", className)}>
      {(title || eyebrow || action) && (
        <div className="mb-4 flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
          <div>
            {eyebrow && <p className="candidate-eyebrow">{eyebrow}</p>}
            {title && <h2 className="mt-1 text-lg font-extrabold text-[var(--candidate-ink-strong)]">{title}</h2>}
          </div>
          {action}
        </div>
      )}
      {children}
    </section>
  );
}

export function CandidateMetric({ icon: Icon, label, value, helper }) {
  return (
    <div className="candidate-soft-surface p-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-sm font-bold text-[var(--candidate-muted)]">{label}</p>
          <p className="mt-1 text-3xl font-extrabold text-[var(--candidate-ink-strong)]">{value}</p>
        </div>
        {Icon && (
          <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-[var(--candidate-aqua)] text-[var(--candidate-ink-strong)]">
            <Icon className="h-5 w-5" aria-hidden="true" />
          </span>
        )}
      </div>
      {helper && <p className="mt-2 text-sm text-[var(--candidate-muted)]">{helper}</p>}
    </div>
  );
}

export function CandidateEmptyState({ title, children, action }) {
  return (
    <div className="candidate-soft-surface px-4 py-8 text-center">
      <Inbox className="mx-auto h-8 w-8 text-[var(--candidate-primary)]" aria-hidden="true" />
      <p className="mt-3 text-base font-extrabold text-[var(--candidate-ink-strong)]">{title}</p>
      {children && <p className="mx-auto mt-2 max-w-xl text-sm leading-6 text-[var(--candidate-muted)]">{children}</p>}
      {action && <div className="mt-4 flex justify-center">{action}</div>}
    </div>
  );
}

export function CandidateLoading({ label = "Loading" }) {
  return (
    <div className="candidate-page" aria-busy="true" aria-label={label}>
      <div className="candidate-skeleton h-40 rounded-xl" />
      <div className="grid gap-4 md:grid-cols-2">
        <div className="candidate-skeleton h-48 rounded-xl" />
        <div className="candidate-skeleton h-48 rounded-xl" />
      </div>
    </div>
  );
}

export function CandidateSpinner({ label }) {
  return (
    <span className="inline-flex items-center gap-2 text-sm font-bold text-[var(--candidate-muted)]">
      <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
      {label}
    </span>
  );
}

export function FieldShell({ label, helper, error, children }) {
  return (
    <label className="candidate-field">
      <span className="candidate-label">{label}</span>
      {children}
      {error ? (
        <span className="candidate-helper text-rose-600">{error}</span>
      ) : (
        helper && <span className="candidate-helper">{helper}</span>
      )}
    </label>
  );
}

export function CandidateInput({ label, helper, error, ...props }) {
  return (
    <FieldShell label={label} helper={helper} error={error}>
      <input className="candidate-control" aria-invalid={Boolean(error) || undefined} {...props} />
    </FieldShell>
  );
}

export function CandidateSelect({ label, helper, error, children, ...props }) {
  return (
    <FieldShell label={label} helper={helper} error={error}>
      <select className="candidate-control" aria-invalid={Boolean(error) || undefined} {...props}>{children}</select>
    </FieldShell>
  );
}

export function CandidateTextarea({ label, helper, error, ...props }) {
  return (
    <FieldShell label={label} helper={helper} error={error}>
      <textarea className="candidate-control min-h-32 resize-y" aria-invalid={Boolean(error) || undefined} {...props} />
    </FieldShell>
  );
}

export function CandidateAnimatedList({ children, className }) {
  const reduceMotion = useReducedMotion();
  const items = Array.isArray(children) ? children : [children];

  return (
    <div className={className}>
      {items.map((child, index) => (
        <motion.div
          key={child?.key || index}
          initial={reduceMotion ? false : { opacity: 0, y: 10 }}
          animate={reduceMotion ? undefined : { opacity: 1, y: 0 }}
          transition={{ duration: 0.26, delay: Math.min(index * 0.04, 0.24) }}
        >
          {child}
        </motion.div>
      ))}
    </div>
  );
}

export function CandidatePagination({ page, totalPages, onPageChange, totalItems, pageSize }) {
  if (totalPages <= 1) return null;
  const start = (page - 1) * pageSize + 1;
  const end = Math.min(page * pageSize, totalItems);

  return (
    <nav className="candidate-divider mt-5 flex flex-col gap-3 pt-4 sm:flex-row sm:items-center sm:justify-between" aria-label="Pagination">
      <p className="text-sm font-bold text-[var(--candidate-muted)]">
        Showing {start}-{end} of {totalItems}
      </p>
      <div className="flex items-center gap-2">
        <CandidateButton type="button" variant="secondary" onClick={() => onPageChange(page - 1)} disabled={page === 1}>
          <ChevronLeft className="h-4 w-4" aria-hidden="true" />
          Previous
        </CandidateButton>
        <span className="px-2 text-sm font-extrabold text-[var(--candidate-ink)]">
          {page} / {totalPages}
        </span>
        <CandidateButton type="button" variant="secondary" onClick={() => onPageChange(page + 1)} disabled={page === totalPages}>
          Next
          <ChevronRight className="h-4 w-4" aria-hidden="true" />
        </CandidateButton>
      </div>
    </nav>
  );
}

export function getPaginatedItems(items, page, pageSize) {
  const totalPages = Math.max(1, Math.ceil(items.length / pageSize));
  const safePage = Math.min(page, totalPages);
  const start = (safePage - 1) * pageSize;
  return {
    items: items.slice(start, start + pageSize),
    totalPages,
    safePage
  };
}
