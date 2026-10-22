import { api } from "./client";
import { idempotencyHeaders } from "./idempotency";

export async function getHrDashboard() {
  return api.get("/hr/dashboard");
}

export async function getHrJobs() {
  return api.get("/hr/jobs");
}

export async function getHrJob(jobId) {
  return api.get(`/hr/jobs/${jobId}`);
}

export async function createHrJob(payload) {
  return api.post("/hr/jobs", payload);
}

export async function updateHrJob(jobId, payload) {
  return api.put(`/hr/jobs/${jobId}`, payload);
}

export async function parseHrJob(jobId) {
  return api.post(`/hr/jobs/${jobId}/parse`);
}

export async function extractHrApplicantText(jobId, { force = false } = {}) {
  return api.post(`/hr/jobs/${jobId}/applicants/extract-text`, null, { params: { force } });
}

export async function rerankHrJob(jobId) {
  return api.post(`/hr/jobs/${jobId}/rerank`);
}

export async function publishJob(jobId, expectedVersion, idempotencyKey) {
  return api.post(
    `/hr/jobs/${jobId}/publish`,
    { expectedVersion },
    idempotencyHeaders(idempotencyKey)
  );
}

export async function closeJob(jobId, expectedVersion, idempotencyKey) {
  return api.post(
    `/hr/jobs/${jobId}/close`,
    { expectedVersion },
    idempotencyHeaders(idempotencyKey)
  );
}

export async function reopenJob(jobId, expectedVersion, idempotencyKey) {
  return api.post(
    `/hr/jobs/${jobId}/reopen`,
    { expectedVersion },
    idempotencyHeaders(idempotencyKey)
  );
}

export async function archiveJob(jobId, expectedVersion, idempotencyKey) {
  return api.post(
    `/hr/jobs/${jobId}/archive`,
    { expectedVersion },
    idempotencyHeaders(idempotencyKey)
  );
}

export async function deleteDraftJob(jobId, expectedVersion, idempotencyKey) {
  return api.post(
    `/hr/jobs/${jobId}/delete-draft`,
    { expectedVersion },
    idempotencyHeaders(idempotencyKey)
  );
}

export async function getHrJobApplications(jobId) {
  return api.get(`/hr/jobs/${jobId}/applications`);
}

export async function getHrApplication(applicationId) {
  return api.get(`/hr/applications/${applicationId}`);
}

export async function advanceApplication(applicationId, payload, idempotencyKey) {
  return api.post(
    `/hr/applications/${applicationId}/advance`,
    payload,
    idempotencyHeaders(idempotencyKey)
  );
}

export async function rejectApplication(applicationId, payload, idempotencyKey) {
  return api.post(
    `/hr/applications/${applicationId}/reject`,
    payload,
    idempotencyHeaders(idempotencyKey)
  );
}

export async function parseHrApplicationCv(applicationId) {
  return api.post(`/hr/applications/${applicationId}/parse-cv`);
}

export async function getHrDocumentDownloadUrl(documentId) {
  return api.get(`/hr/documents/${documentId}/download-url`);
}
