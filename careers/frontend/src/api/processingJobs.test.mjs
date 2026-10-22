import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import test from "node:test";

const sourceRoot = join(process.cwd(), "src");

test("processing job API exposes status lookup and terminal-state helper", () => {
  const processingApi = readFileSync(join(sourceRoot, "api", "processingJobs.js"), "utf8");

  assert.match(processingApi, /\/processing-jobs\/\$\{jobId\}/);
  assert.match(processingApi, /"succeeded"/);
  assert.match(processingApi, /"failed"/);
  assert.match(processingApi, /"cancelled"/);
  assert.match(processingApi, /PROCESSING_JOB_TERMINAL_STATUSES\.has\(job\.status\)/);
});

test("202-producing route helpers keep processing job responses observable", () => {
  const documentsApi = readFileSync(join(sourceRoot, "api", "documents.js"), "utf8");
  const hrApi = readFileSync(join(sourceRoot, "api", "hr.js"), "utf8");

  assert.match(documentsApi, /\/documents\/\$\{documentId\}\/extract-text/);
  assert.match(documentsApi, /\/documents\/\$\{documentId\}\/extracted-text-status/);
  assert.match(documentsApi, /\/documents\/\$\{documentId\}\/text/);
  assert.match(hrApi, /\/hr\/jobs\/\$\{jobId\}\/parse/);
  assert.match(hrApi, /\/hr\/jobs\/\$\{jobId\}\/applicants\/extract-text/);
  assert.match(hrApi, /\/hr\/jobs\/\$\{jobId\}\/rerank/);
  assert.match(hrApi, /\/hr\/applications\/\$\{applicationId\}\/parse-cv/);
});

test("processing job hook bounds polling and cleans up on unmount", () => {
  const hook = readFileSync(join(sourceRoot, "hooks", "useProcessingJobStatus.js"), "utf8");

  assert.match(hook, /getProcessingJob\(jobId\)/);
  assert.match(hook, /isProcessingJobTerminal\(nextJob\)/);
  assert.match(hook, /maxPolls/);
  assert.match(hook, /inFlightRef/);
  assert.match(hook, /setTimeout/);
  assert.match(hook, /clearTimeout/);
  assert.match(hook, /return stop/);
});

test("candidate apply still consumes an application response", () => {
  const candidateApply = readFileSync(join(sourceRoot, "pages", "CandidateApply.jsx"), "utf8");

  assert.match(candidateApply, /applyToJob\(jobId/);
  assert.match(candidateApply, /response\.data\.id/);
  assert.match(candidateApply, /candidate\/job-applications\/\$\{response\.data\.id\}/);
});
