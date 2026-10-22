import { z } from "zod";

import {
  APPLICATION_STATUSES,
  DOCUMENT_TYPES,
  JOB_EMPLOYMENT_TYPES,
  JOB_POSTING_STATUSES,
  JOB_WORK_MODES,
  USER_ROLES
} from "../constants.js";
import { isPasswordValid } from "../utils/passwordValidation.js";

export const CHAT_MAX_ATTACHMENTS = 4;
export const CHAT_MAX_ATTACHMENT_BYTES = 5 * 1024 * 1024;
export const CHAT_ALLOWED_ATTACHMENT_TYPES = [
  "image/jpeg",
  "image/png",
  "image/gif",
  "image/webp",
  "application/pdf",
  "application/msword",
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
  "application/vnd.ms-excel",
  "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
  "application/vnd.ms-powerpoint",
  "application/vnd.openxmlformats-officedocument.presentationml.presentation",
  "text/plain",
  "text/csv",
  "application/zip"
];

const currentYear = new Date().getFullYear();

const CONTROL_CHARACTER_PATTERN = /[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]/;
const HTML_TAG_PATTERN = /<\/?[a-z][\s\S]*>/i;
const DANGEROUS_MARKUP_PATTERN = /<(script|iframe|object|embed|svg|math|meta|link|style)\b/i;
const INLINE_EVENT_PATTERN = /\bon[a-z]+\s*=/i;
const DANGEROUS_PROTOCOL_PATTERN = /(?:^|[\s"'(<])(?:javascript|vbscript)\s*:/i;
const DANGEROUS_DATA_URI_PATTERN = /(?:^|[\s"'(<])data\s*:\s*text\/html/i;
const TEMPLATE_INJECTION_PATTERN = /(?:\{\{[\s\S]*?\}\}|\$\{[\s\S]*?\}|<%[\s\S]*?%>)/;
const SQL_INJECTION_PROBE_PATTERN =
  /(?:['"`]\s*(?:or|and)\s+['"]?\w+['"]?\s*=\s*['"]?\w+|\b(?:or|and)\s+\d+\s*=\s*\d+\b|;\s*--|\/\*|\*\/|\bunion\s+(?:all\s+)?select\b|\bdrop\s+table\b|\binformation_schema\b)/i;
const MEANINGFUL_TEXT_PATTERN = /[\p{L}\p{N}]/u;
const UNSAFE_URL_CHARACTER_PATTERN = /[\s<>"'`\\]/;
const UNSAFE_FILE_NAME_PATTERN = /[\\/:*?"<>|\x00-\x1F\x7F]/;
const DATA_URL_BASE64_PATTERN =
  /^data:(?:[a-z0-9][a-z0-9.+-]*\/[a-z0-9][a-z0-9.+-]*)?(?:;[a-z0-9-]+=[a-z0-9.+_-]+)*;base64,[a-z0-9+/]+={0,2}$/i;
const CHAT_DATA_URL_MAX_LENGTH = Math.ceil(CHAT_MAX_ATTACHMENT_BYTES * 1.4) + 256;

function getUnsafeTextMessage(value, label, options = {}) {
  const text = String(value ?? "");

  if (!text) return "";
  if (CONTROL_CHARACTER_PATTERN.test(text)) return `${label} contains unsupported control characters.`;
  if (HTML_TAG_PATTERN.test(text) || DANGEROUS_MARKUP_PATTERN.test(text) || INLINE_EVENT_PATTERN.test(text)) {
    return `${label} cannot contain HTML or script markup.`;
  }
  if (DANGEROUS_PROTOCOL_PATTERN.test(text) || DANGEROUS_DATA_URI_PATTERN.test(text)) {
    return `${label} cannot contain script URLs.`;
  }
  if (!options.allowTemplateSyntax && TEMPLATE_INJECTION_PATTERN.test(text)) {
    return `${label} cannot contain template injection syntax.`;
  }
  if (!options.allowSqlProbeText && SQL_INJECTION_PROBE_PATTERN.test(text)) {
    return `${label} looks like an injection attempt.`;
  }

  return "";
}

function safeText(schema, label, options) {
  return schema.superRefine((value, context) => {
    const message = getUnsafeTextMessage(value, label, options);
    if (message) {
      context.addIssue({
        code: z.ZodIssueCode.custom,
        message
      });
    }
  });
}

function hasMeaningfulText(label) {
  return (schema) =>
    schema.refine((value) => !value || MEANINGFUL_TEXT_PATTERN.test(value), {
      message: `${label} needs at least one letter or number.`
    });
}

const requiredText = (label, max = 160, min = 1) =>
  safeText(
    hasMeaningfulText(label)(
      z.string().trim().min(min, `${label} is required.`).max(max, `${label} must be ${max} characters or fewer.`)
    ),
    label
  );

const optionalText = (label, max = 1000) =>
  safeText(hasMeaningfulText(label)(z.string().trim().max(max, `${label} must be ${max} characters or fewer.`)), label).transform(
    (value) => value || null
  );

const optionalFilterText = (label, max = 80) =>
  safeText(hasMeaningfulText(label)(z.string().trim().max(max, `${label} must be ${max} characters or fewer.`)), label);

const fileName = (label = "File name") =>
  requiredText(label, 255).refine((value) => !UNSAFE_FILE_NAME_PATTERN.test(value) && !value.includes(".."), {
    message: `${label} cannot contain path or markup characters.`
  });

const chatDataUrl = z
  .string()
  .trim()
  .min(1, "Attachment data is missing.")
  .max(CHAT_DATA_URL_MAX_LENGTH, "Attachment data is too large.")
  .refine((value) => DATA_URL_BASE64_PATTERN.test(value), {
    message: "Attachment data must be a base64 data URL."
  })
  .refine((value) => !DANGEROUS_DATA_URI_PATTERN.test(value), {
    message: "Attachment data cannot be HTML."
  })
  .refine((value) => CHAT_ALLOWED_ATTACHMENT_TYPES.includes(getDataUrlMimeType(value)), {
    message: "Attachment data type is not supported."
  });

function getDataUrlMimeType(value) {
  return String(value || "")
    .match(/^data:([^;,]*)/i)?.[1]
    ?.toLowerCase();
}

function isSafeHttpUrl(value) {
  if (UNSAFE_URL_CHARACTER_PATTERN.test(value)) return false;

  try {
    const url = new URL(value);
    return ["http:", "https:"].includes(url.protocol) && !url.username && !url.password;
  } catch {
    return false;
  }
}

const optionalUrl = (label) =>
  z
    .string()
    .trim()
    .max(2048, `${label} is too long.`)
    .transform((value) => value || null)
    .refine((value) => value === null || /^https?:\/\/\S+$/i.test(value), {
      message: `${label} must start with http:// or https://.`
    })
    .refine((value) => value === null || isSafeHttpUrl(value), {
      message: `${label} must be a safe http:// or https:// URL.`
    });

const optionalDate = (label) =>
  z
    .string()
    .trim()
    .refine((value) => !value || /^\d{4}-\d{2}-\d{2}$/.test(value), {
      message: `${label} must be a valid date.`
    })
    .transform((value) => value || null);

const optionalMoney = (label) =>
  z.preprocess((value) => {
    const text = String(value ?? "").trim();
    return text === "" ? null : Number(text);
  }, z.union([z.number().finite().nonnegative(`${label} must be zero or higher.`), z.null()]));

const nullablePositiveId = z.preprocess((value) => Number(value), z.number().int().positive());

const settingsSchemaShape = {
  density: z.enum(["comfortable", "compact"]),
  startPage: z.enum(["role-home", "chat", "search"]),
  emailDigest: z.boolean(),
  chatNotifications: z.boolean(),
  deadlineReminders: z.boolean(),
  privacyMode: z.boolean()
};

export const loginSchema = z.object({
  email: requiredText("Email", 254).email("Enter a valid email address."),
  password: z.string().min(1, "Password is required.").max(128, "Password is too long.")
});

export const registerSchema = z
  .object({
    full_name: requiredText("Full name", 120, 2),
    email: requiredText("Email", 254).email("Enter a valid email address."),
    password: z.string().min(1, "Password is required.").max(64, "Password must be 64 characters or fewer."),
    confirmPassword: z.string().min(1, "Confirm your password."),
    role: z.enum(USER_ROLES)
  })
  .refine((data) => isPasswordValid(data.password), {
    path: ["password"],
    message: "Password does not meet the security requirements."
  })
  .refine((data) => data.password === data.confirmPassword, {
    path: ["confirmPassword"],
    message: "Passwords do not match."
  });

export const applicationFormSchema = z.object({
  company_name: requiredText("Company", 160),
  position_title: requiredText("Position", 180),
  job_description: requiredText("Job description", 12000, 10),
  application_status: z.enum(APPLICATION_STATUSES),
  deadline: optionalDate("Deadline"),
  notes: optionalText("Notes", 4000)
});

export const jobPostingFormSchema = z
  .object({
    title: requiredText("Job title", 180, 3),
    description: requiredText("Description", 12000, 20),
    requirements: optionalText("Requirements", 6000),
    responsibilities: optionalText("Responsibilities", 6000),
    location: optionalText("Location", 160),
    employment_type: z.enum(JOB_EMPLOYMENT_TYPES),
    work_mode: z.enum(JOB_WORK_MODES),
    salary_min: optionalMoney("Salary min"),
    salary_max: optionalMoney("Salary max"),
    deadline: optionalDate("Deadline"),
    status: z.enum(JOB_POSTING_STATUSES)
  })
  .refine((data) => data.salary_min === null || data.salary_max === null || data.salary_min <= data.salary_max, {
    path: ["salary_max"],
    message: "Salary max must be greater than or equal to salary min."
  });

export const companyProfileSchema = z.object({
  name: requiredText("Company name", 160, 2),
  description: optionalText("Description", 4000),
  website: optionalUrl("Website"),
  industry: optionalText("Industry", 120),
  location: optionalText("Location", 160),
  logo_url: optionalUrl("Logo URL")
});

export const candidateProfileSchema = z.object({
  full_name: requiredText("Full name", 120, 2),
  university: requiredText("University", 180, 2),
  major: requiredText("Major", 160, 2),
  graduation_year: z.preprocess((value) => {
    const text = String(value ?? "").trim();
    return text === "" ? null : Number(text);
  }, z.number().int().min(1900, "Graduation year is too early.").max(currentYear + 8, "Graduation year is too far in the future.")),
  phone: optionalText("Phone", 40),
  location: requiredText("Location", 160, 2),
  linkedin_url: optionalUrl("LinkedIn URL"),
  github_url: optionalUrl("GitHub URL"),
  portfolio_url: optionalUrl("Portfolio URL"),
  bio: requiredText("Bio", 1500, 10)
});

export const candidateApplySchema = z.object({
  cover_letter_text: optionalText("Cover letter", 6000),
  candidate_note: optionalText("Candidate note", 1500),
  document_ids: z.array(nullablePositiveId).min(1, "Select or upload at least one document before applying.")
});

export const cvAnalysisSchema = z
  .object({
    selectedDocumentId: z.string().trim(),
    cvText: safeText(z.string().trim().max(50000, "CV text is too long."), "CV text", {
      allowTemplateSyntax: true,
      allowSqlProbeText: true
    })
  })
  .refine((data) => Boolean(data.selectedDocumentId || data.cvText.length >= 20), {
    path: ["cvText"],
    message: "Choose an uploaded .txt CV or paste at least 20 characters of CV text."
  });

export const workflowNoteSchema = z.object({
  note: optionalText("Workflow note", 1500)
});

export const workspaceSearchSchema = z.object({
  q: optionalFilterText("Search", 80)
});

export const jobSearchFiltersSchema = z.object({
  keyword: optionalFilterText("Keyword", 80),
  location: optionalFilterText("Location", 80),
  work_mode: z.union([z.literal(""), z.enum(JOB_WORK_MODES)]),
  employment_type: z.union([z.literal(""), z.enum(JOB_EMPLOYMENT_TYPES)])
});

export const settingsSchema = z.object(settingsSchemaShape);

export const documentUploadFileSchema = z.object({
  name: fileName(),
  size: z.number().positive("Choose a non-empty file.").max(10 * 1024 * 1024, "Document must be 10MB or smaller.")
});

export const chatAttachmentFileSchema = z
  .object({
    name: fileName(),
    type: z.string().trim(),
    size: z.number().positive("Choose a non-empty file.").max(CHAT_MAX_ATTACHMENT_BYTES, "Attachment must be 5MB or smaller.")
  })
  .superRefine((file, context) => {
    if (file.type && !CHAT_ALLOWED_ATTACHMENT_TYPES.includes(file.type)) {
      context.addIssue({
        code: z.ZodIssueCode.custom,
        path: ["type"],
        message: "That file type is not supported for chat attachments."
      });
    }
  });

export const chatAttachmentPayloadSchema = z
  .object({
    id: z.string().optional(),
    name: fileName("Attachment name"),
    type: z
      .string()
      .trim()
      .max(160)
      .optional()
      .refine((value) => !value || CHAT_ALLOWED_ATTACHMENT_TYPES.includes(value), {
        message: "That file type is not supported for chat attachments."
      }),
    size: z.number().positive().max(CHAT_MAX_ATTACHMENT_BYTES),
    dataUrl: chatDataUrl
  })
  .superRefine((attachment, context) => {
    const dataUrlType = getDataUrlMimeType(attachment.dataUrl);
    if (attachment.type && dataUrlType && attachment.type !== dataUrlType) {
      context.addIssue({
        code: z.ZodIssueCode.custom,
        path: ["dataUrl"],
        message: "Attachment data does not match the selected file type."
      });
    }
  });

export const chatMessageSchema = z
  .object({
    text: safeText(z.string().trim().max(2000, "Messages must be 2000 characters or fewer."), "Message", {
      allowTemplateSyntax: true,
      allowSqlProbeText: true
    }),
    attachments: z.array(chatAttachmentPayloadSchema).max(CHAT_MAX_ATTACHMENTS, `Attach up to ${CHAT_MAX_ATTACHMENTS} files at once.`)
  })
  .refine((data) => Boolean(data.text || data.attachments.length), {
    path: ["text"],
    message: "Write a message or attach a file."
  });

export const chatGroupSchema = z.object({
  name: requiredText("Group name", 80, 2),
  memberIds: z.array(z.string().min(1)).min(1, "Choose at least one member.")
});

export function validateForm(schema, values) {
  const result = schema.safeParse(values);
  if (result.success) {
    return { data: result.data, errors: {}, formError: "" };
  }

  const flattened = result.error.flatten();
  return {
    data: null,
    errors: flattened.fieldErrors,
    formError: flattened.formErrors[0] || firstFieldError(flattened.fieldErrors) || "Review the highlighted fields."
  };
}

export function firstFieldError(errors) {
  return Object.values(errors || {}).flat().find(Boolean) || "";
}

export function fieldError(errors, field) {
  return errors?.[field]?.[0] || "";
}

export function clearFieldError(errors, field) {
  if (!errors?.[field]) return errors || {};
  const nextErrors = { ...errors };
  delete nextErrors[field];
  return nextErrors;
}

export function parseWorkspaceSearch(value) {
  const result = validateForm(workspaceSearchSchema, { q: value });
  return {
    query: result.data?.q || "",
    error: result.formError
  };
}

export function validateChatFile(file) {
  const result = chatAttachmentFileSchema.safeParse({
    name: file?.name || "",
    type: file?.type || "",
    size: file?.size || 0
  });
  return result.success ? "" : result.error.issues[0]?.message || "That file cannot be attached.";
}

export function validateDocumentFile(file) {
  const result = documentUploadFileSchema.safeParse({
    name: file?.name || "",
    size: file?.size || 0
  });
  return result.success ? "" : result.error.issues[0]?.message || "That file cannot be uploaded.";
}

export function formatFileSize(bytes) {
  if (!Number.isFinite(bytes) || bytes <= 0) return "0 B";
  const units = ["B", "KB", "MB", "GB"];
  const exponent = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1);
  const value = bytes / 1024 ** exponent;
  return `${value >= 10 || exponent === 0 ? Math.round(value) : value.toFixed(1)} ${units[exponent]}`;
}
