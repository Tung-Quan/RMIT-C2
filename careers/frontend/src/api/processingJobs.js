import { api } from "./client";

export const PROCESSING_JOB_TERMINAL_STATUSES = new Set(["succeeded", "failed", "cancelled"]);

export function isProcessingJobTerminal(job) {
  return Boolean(job && PROCESSING_JOB_TERMINAL_STATUSES.has(job.status));
}

export async function getProcessingJob(jobId) {
  return api.get(`/processing-jobs/${jobId}`);
}
