import assert from "node:assert/strict";
import test from "node:test";

import {
  CHAT_MAX_ATTACHMENTS,
  chatAttachmentFileSchema,
  chatMessageSchema,
  companyProfileSchema,
  documentUploadFileSchema,
  jobPostingFormSchema,
  parseWorkspaceSearch,
  registerSchema,
  validateForm
} from "./forms.js";

const validJobPosting = {
  title: "Backend Intern",
  description: "Build APIs and improve platform reliability.",
  requirements: "",
  responsibilities: "",
  location: "",
  employment_type: "early_career",
  work_mode: "hybrid",
  salary_min: "",
  salary_max: "",
  deadline: "",
  status: "draft"
};

test("job posting validation trims text and rejects inverted salary range", () => {
  const result = validateForm(jobPostingFormSchema, {
    ...validJobPosting,
    title: " Backend Intern ",
    employment_type: "early_career",
    work_mode: "hybrid",
    salary_min: "900",
    salary_max: "500",
    deadline: "",
    status: "draft"
  });

  assert.equal(result.data, null);
  assert.match(result.errors.salary_max[0], /greater than or equal/);
});

test("workspace search trims query and enforces a short bounded input", () => {
  assert.deepEqual(parseWorkspaceSearch("  react intern  "), {
    query: "react intern",
    error: ""
  });

  const parsed = parseWorkspaceSearch("x".repeat(81));
  assert.equal(parsed.query, "");
  assert.match(parsed.error, /80 characters/);
});

test("shared form validation blocks obvious injection payloads", () => {
  const scriptResult = validateForm(jobPostingFormSchema, {
    ...validJobPosting,
    title: "<img src=x onerror=alert(1)>"
  });

  assert.equal(scriptResult.data, null);
  assert.match(scriptResult.errors.title[0], /HTML or script markup/);

  const sqlResult = validateForm(jobPostingFormSchema, {
    ...validJobPosting,
    description: "Build APIs for reporting. ' OR 1=1; DROP TABLE users"
  });

  assert.equal(sqlResult.data, null);
  assert.match(sqlResult.errors.description[0], /injection attempt/);

  const templateResult = validateForm(jobPostingFormSchema, {
    ...validJobPosting,
    requirements: "{{constructor.constructor('alert(1)')()}}"
  });

  assert.equal(templateResult.data, null);
  assert.match(templateResult.errors.requirements[0], /template injection/);
});

test("profile and search validation reject malformed user input before requests", () => {
  const registerResult = validateForm(registerSchema, {
    full_name: "!!!",
    email: "candidate@example.com",
    password: "Str0ng!Pass",
    confirmPassword: "Str0ng!Pass",
    role: "candidate"
  });

  assert.equal(registerResult.data, null);
  assert.match(registerResult.errors.full_name[0], /letter or number/);

  const companyResult = validateForm(companyProfileSchema, {
    name: "Acme Labs",
    description: "",
    website: "javascript:alert(1)",
    industry: "",
    location: "",
    logo_url: "https://example.com/logo.png"
  });

  assert.equal(companyResult.data, null);
  assert.match(companyResult.errors.website[0], /http:\/\/ or https:\/\//);

  const parsed = parseWorkspaceSearch("<script>alert(1)</script>");
  assert.equal(parsed.query, "");
  assert.match(parsed.error, /HTML or script markup/);
});

test("file validation rejects unsafe file names and forged attachment data", () => {
  const unsafeDocument = documentUploadFileSchema.safeParse({
    name: "../resume.pdf",
    size: 2048
  });

  assert.equal(unsafeDocument.success, false);
  assert.match(unsafeDocument.error.issues[0].message, /path or markup/);

  const unsafeAttachment = chatAttachmentFileSchema.safeParse({
    name: "avatar<script>.png",
    type: "image/png",
    size: 2048
  });

  assert.equal(unsafeAttachment.success, false);
  assert.match(unsafeAttachment.error.issues[0].message, /path or markup|HTML or script markup/);

  const forgedMessage = chatMessageSchema.safeParse({
    text: "",
    attachments: [
      {
        name: "payload.html",
        type: "text/plain",
        size: 128,
        dataUrl: "data:text/html;base64,PHNjcmlwdD5hbGVydCgxKTwvc2NyaXB0Pg=="
      }
    ]
  });

  assert.equal(forgedMessage.success, false);
  assert.match(forgedMessage.error.issues.map((issue) => issue.message).join(" "), /not supported|cannot be HTML|does not match/);
});

test("chat message validation allows attachments without text and caps batch size", () => {
  const attachment = {
    name: "portfolio.pdf",
    type: "application/pdf",
    size: 1000,
    dataUrl: "data:application/pdf;base64,ZmFrZQ=="
  };

  assert.equal(validateForm(chatMessageSchema, { text: "", attachments: [attachment] }).formError, "");

  const tooMany = validateForm(chatMessageSchema, {
    text: "",
    attachments: Array.from({ length: CHAT_MAX_ATTACHMENTS + 1 }, (_, index) => ({
      ...attachment,
      id: String(index)
    }))
  });

  assert.equal(tooMany.data, null);
  assert.match(tooMany.errors.attachments[0], /Attach up to/);

  const unsafeMessage = validateForm(chatMessageSchema, {
    text: "javascript:alert(1)",
    attachments: []
  });

  assert.equal(unsafeMessage.data, null);
  assert.match(unsafeMessage.errors.text[0], /script URLs/);
});
