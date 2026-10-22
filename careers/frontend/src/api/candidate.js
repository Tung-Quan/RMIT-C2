import { api } from "./client";
import { idempotencyHeaders } from "./idempotency";

export async function getCandidateProfile() {
  return api.get("/candidate/profile");
}

export async function updateCandidateProfile(payload) {
  return api.put("/candidate/profile", payload);
}

export async function getCandidateDashboard() {
  return api.get("/candidate/dashboard");
}

export async function getCandidateDocuments() {
  return api.get("/candidate/documents");
}

export async function getCandidateJobApplications() {
  return api.get("/candidate/job-applications");
}

export async function getCandidateJobApplication(applicationId) {
  return api.get(`/candidate/job-applications/${applicationId}`);
}

export async function withdrawApplication(applicationId, expectedVersion, idempotencyKey) {
  return api.post(
    `/candidate/job-applications/${applicationId}/withdraw`,
    { expectedVersion },
    idempotencyHeaders(idempotencyKey)
  );
}
