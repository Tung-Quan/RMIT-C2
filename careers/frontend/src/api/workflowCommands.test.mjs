import assert from "node:assert/strict";
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join } from "node:path";
import test from "node:test";

import { normalizeMutationError } from "./client.js";
import { isIdempotencyReplay } from "./idempotency.js";

const sourceRoot = join(process.cwd(), "src");

test("API command helpers target explicit workflow endpoints", () => {
  const hrApi = readFileSync(join(sourceRoot, "api", "hr.js"), "utf8");
  const candidateApi = readFileSync(join(sourceRoot, "api", "candidate.js"), "utf8");
  const jobsApi = readFileSync(join(sourceRoot, "api", "jobs.js"), "utf8");

  for (const endpoint of [
    "/hr/jobs/${jobId}/publish",
    "/hr/jobs/${jobId}/close",
    "/hr/jobs/${jobId}/reopen",
    "/hr/jobs/${jobId}/archive",
    "/hr/jobs/${jobId}/delete-draft",
    "/hr/applications/${applicationId}/advance",
    "/hr/applications/${applicationId}/reject"
  ]) {
    assert.match(hrApi, new RegExp(escapeRegExp(endpoint)));
  }

  assert.match(
    candidateApi,
    new RegExp(escapeRegExp("/candidate/job-applications/${applicationId}/withdraw"))
  );
  assert.match(jobsApi, new RegExp(escapeRegExp("/jobs/${jobId}/apply")));
});

test("command helpers send expectedVersion and idempotency headers", () => {
  const hrApi = readFileSync(join(sourceRoot, "api", "hr.js"), "utf8");
  const candidateApi = readFileSync(join(sourceRoot, "api", "candidate.js"), "utf8");
  const jobsApi = readFileSync(join(sourceRoot, "api", "jobs.js"), "utf8");

  assert.match(hrApi, /expectedVersion/);
  assert.match(hrApi, /idempotencyHeaders\(idempotencyKey\)/);
  assert.match(candidateApi, /expectedVersion/);
  assert.match(candidateApi, /idempotencyHeaders\(idempotencyKey\)/);
  assert.match(jobsApi, /idempotencyHeaders\(idempotencyKey\)/);
});

test("replay header and mutation error mapping are normalized", () => {
  assert.equal(isIdempotencyReplay({ headers: { "idempotency-replayed": "true" } }), true);

  assert.equal(
    normalizeMutationError({
      response: {
        status: 409,
        data: {
          detail: {
            code: "stale_version",
            expectedVersion: 4,
            currentVersion: 5
          }
        }
      }
    }).type,
    "stale"
  );

  assert.equal(
    normalizeMutationError({
      response: {
        status: 409,
        data: {
          detail: {
            code: "invalid_state_transition",
            message: "Already closed",
            currentStatus: "closed"
          }
        }
      }
    }).type,
    "invalid-transition"
  );

  assert.equal(
    normalizeMutationError({
      response: { status: 409, data: { detail: "You have already applied to this job" } }
    }).type,
    "duplicate"
  );

  assert.equal(
    normalizeMutationError({
      response: { status: 409, data: { detail: { code: "duplicate_application" } } }
    }).type,
    "duplicate"
  );

  assert.equal(
    normalizeMutationError({
      response: { status: 404, data: { detail: { code: "resource_not_found" } } }
    }).type,
    "not-found"
  );

  assert.equal(normalizeMutationError({ request: {} }).type, "network");
  assert.deepEqual(normalizeMutationError(new Error("Company profile id is missing.")), {
    type: "client",
    retryable: false,
    message: "Company profile id is missing."
  });
});

test("HR company form creates a profile when no persisted company id is available", () => {
  const companyPage = readFileSync(join(sourceRoot, "pages", "HrCompany.jsx"), "utf8");

  assert.match(companyPage, /const companyId = getCompanyId\(company\);/);
  assert.match(
    companyPage,
    /const response = companyId\s*\?\s*await updateCompany\(companyId, payload\)\s*:\s*await createCompany\(payload\);/s
  );
  assert.doesNotMatch(companyPage, /Company profile id is missing/);
  assert.match(companyPage, /err\?\.response\?\.status === 404/);
});

test("maintained frontend source does not use deprecated workflow routes", () => {
  const deprecatedFragments = [
    [["/hr/", "jobs/"].join(""), ["/st", "atus"].join("")],
    [["/hr/", "applications/"].join(""), ["/st", "atus"].join("")],
    ["api.patch(", "/candidate/job-applications/", "/withdraw"],
    ["api.delete(`", "/hr/jobs/"],
    [["update", "HrJob", "Status"].join("")],
    [["update", "HrApplication", "Status"].join("")],
    [["withdraw", "Candidate", "JobApplication"].join("")]
  ];

  for (const file of walk(sourceRoot)) {
    if (file.endsWith("workflowCommands.test.mjs")) continue;
    const text = readFileSync(file, "utf8");
    for (const fragments of deprecatedFragments) {
      assert.equal(
        fragments.every((fragment) => text.includes(fragment)),
        false,
        `${file} still contains deprecated workflow route usage`
      );
    }
  }
});

function escapeRegExp(value) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function walk(directory) {
  return readdirSync(directory).flatMap((entry) => {
    const path = join(directory, entry);
    return statSync(path).isDirectory() ? walk(path) : [path];
  });
}
