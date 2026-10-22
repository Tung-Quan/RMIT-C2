import { api } from "./client";
import { idempotencyHeaders } from "./idempotency";

function normalizeFilterValue(value) {
  if (typeof value !== "string") {
    return value;
  }

  const trimmedValue = value.trim();
  return trimmedValue === "" ? undefined : trimmedValue;
}

export async function getJobs(params = {}) {
  const cleanedParams = Object.fromEntries(
    Object.entries(params)
      .map(([key, value]) => [key, normalizeFilterValue(value)])
      .filter(([, value]) => value !== "" && value !== null && value !== undefined)
  );
  return api.get("/jobs", { params: cleanedParams });
}

export async function getJob(jobId) {
  return api.get(`/jobs/${jobId}`);
}

export async function applyToJob(jobId, payload, idempotencyKey) {
  return api.post(`/jobs/${jobId}/apply`, payload, idempotencyHeaders(idempotencyKey));
}
