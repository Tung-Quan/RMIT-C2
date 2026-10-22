import { api } from "./client";

export async function uploadApplicationDocument(applicationId, formData) {
  return api.post(`/applications/${applicationId}/documents`, formData);
}

export async function uploadCandidateDocument(formData) {
  return api.post("/candidate/documents", formData);
}

export async function listApplicationDocuments(applicationId) {
  return api.get(`/applications/${applicationId}/documents`);
}

export async function getDocumentDownloadUrl(documentId) {
  return api.get(`/documents/${documentId}/download-url`);
}

export async function extractDocumentText(documentId, { force = false } = {}) {
  return api.post(`/documents/${documentId}/extract-text`, null, { params: { force } });
}

export async function getExtractedTextStatus(documentId) {
  return api.get(`/documents/${documentId}/extracted-text-status`);
}

export async function getExtractedText(documentId) {
  return api.get(`/documents/${documentId}/text`);
}

export async function deleteDocument(documentId) {
  return api.delete(`/documents/${documentId}`);
}

export async function downloadDocument(id){const result=await api.get(`/documents/${id}/content`,{responseType:"blob"});const href=URL.createObjectURL(result.data);const a=document.createElement("a");a.href=href;a.download=result.headers["content-disposition"]?.match(/filename="([^"]+)"/)?.[1]||"document";a.click();setTimeout(()=>URL.revokeObjectURL(href),1000);}
