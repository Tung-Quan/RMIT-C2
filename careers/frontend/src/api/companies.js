import { api } from "./client";

export async function createCompany(payload) {
  return api.post("/companies", payload);
}

export async function getMyCompany() {
  return api.get("/companies/me");
}

export async function updateCompany(companyId, payload) {
  const normalizedCompanyId = Number(companyId);
  if (!Number.isInteger(normalizedCompanyId) || normalizedCompanyId <= 0) {
    throw new Error("Company profile id is missing. Refresh the page and try again.");
  }
  return api.put(`/companies/${normalizedCompanyId}`, payload);
}
