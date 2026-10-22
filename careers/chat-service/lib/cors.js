export function parseCorsOrigins(value) {
  const origins = String(value || "")
    .split(",")
    .map((origin) => origin.trim())
    .filter(Boolean);

  if (origins.includes("*")) {
    return "*";
  }

  return origins.length
    ? origins
    : ["http://localhost:5173", "http://127.0.0.1:5173"];
}
