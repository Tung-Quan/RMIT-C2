export function Alert({ type = "error", children }) {
  const className =
    type === "success"
      ? "border-emerald-200 bg-emerald-50 text-emerald-800"
      : "border-rose-200 bg-rose-50 text-rose-800";

  return (
    <div
      className={`rounded-lg border px-4 py-3 text-sm ${className}`}
      role={type === "success" ? "status" : "alert"}
      aria-live={type === "success" ? "polite" : "assertive"}
    >
      {children}
    </div>
  );
}
