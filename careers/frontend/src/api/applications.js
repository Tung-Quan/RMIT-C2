import { api } from "./client";

export async function getApplications() {
  return api.get("/applications");
}

export async function createApplication(payload) {
  return api.post("/applications", payload);
}

export async function getApplication(applicationId) {
  return api.get(`/applications/${applicationId}`);
}

export async function updateApplication(applicationId, payload) {
  return api.put(`/applications/${applicationId}`, payload);
}

export async function deleteApplication(applicationId) {
  return api.delete(`/applications/${applicationId}`);
}
