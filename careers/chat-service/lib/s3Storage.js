import { PutObjectCommand, S3Client } from "@aws-sdk/client-s3";
import crypto from "node:crypto";
import path from "node:path";
import "./env.js";

const DATA_URI_PATTERN = /^data:([^;,]+)?(;base64)?,(.*)$/s;

const region = process.env.AWS_REGION || process.env.S3_REGION || "us-east-1";
const endpoint = process.env.S3_ENDPOINT_URL || "";
const bucket = process.env.S3_BUCKET || "";
const publicBaseUrl = (process.env.S3_PUBLIC_BASE_URL || "").replace(/\/$/, "");
const uploadPrefix = (process.env.CHAT_UPLOAD_PREFIX || "chat-service").replace(
  /^\/+|\/+$/g,
  "",
);
const maxImageBytes = Number(
  process.env.CHAT_MAX_IMAGE_BYTES || 5 * 1024 * 1024,
);
const maxAttachmentBytes = Number(
  process.env.CHAT_MAX_ATTACHMENT_BYTES || maxImageBytes,
);
const allowedAttachmentTypes = new Set(
  (
    process.env.CHAT_ALLOWED_ATTACHMENT_TYPES ||
    [
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
      "application/zip",
    ].join(",")
  )
    .split(",")
    .map((value) => value.trim())
    .filter(Boolean),
);

const hasStaticCredentials =
  Boolean(process.env.AWS_ACCESS_KEY_ID) &&
  Boolean(process.env.AWS_SECRET_ACCESS_KEY);

const clientConfig = { region };

if (endpoint) {
  clientConfig.endpoint = endpoint;
  clientConfig.forcePathStyle = process.env.S3_FORCE_PATH_STYLE !== "false";
}

if (hasStaticCredentials) {
  clientConfig.credentials = {
    accessKeyId: process.env.AWS_ACCESS_KEY_ID,
    secretAccessKey: process.env.AWS_SECRET_ACCESS_KEY,
    sessionToken: process.env.AWS_SESSION_TOKEN || undefined,
  };
}

const s3 = new S3Client(clientConfig);

function isHttpUrl(value) {
  return /^https?:\/\//i.test(String(value || ""));
}

function extensionForContentType(contentType) {
  if (!contentType) return ".bin";
  if (contentType === "image/jpeg") return ".jpg";
  if (contentType === "image/png") return ".png";
  if (contentType === "image/gif") return ".gif";
  if (contentType === "image/webp") return ".webp";
  return `.${
    contentType
      .split("/")
      .pop()
      ?.replace(/[^A-Za-z0-9]/g, "") || "bin"
  }`;
}

function contentTypeFromFileName(fileName) {
  const extension = path.extname(String(fileName || "")).toLowerCase();
  if (extension === ".jpg" || extension === ".jpeg") return "image/jpeg";
  if (extension === ".png") return "image/png";
  if (extension === ".gif") return "image/gif";
  if (extension === ".webp") return "image/webp";
  if (extension === ".pdf") return "application/pdf";
  if (extension === ".doc") return "application/msword";
  if (extension === ".docx")
    return "application/vnd.openxmlformats-officedocument.wordprocessingml.document";
  if (extension === ".xls") return "application/vnd.ms-excel";
  if (extension === ".xlsx")
    return "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet";
  if (extension === ".ppt") return "application/vnd.ms-powerpoint";
  if (extension === ".pptx")
    return "application/vnd.openxmlformats-officedocument.presentationml.presentation";
  if (extension === ".txt") return "text/plain";
  if (extension === ".csv") return "text/csv";
  if (extension === ".zip") return "application/zip";
  return "application/octet-stream";
}

function cleanFileName(value) {
  return (
    String(value || "attachment")
      .replace(/[\\/:*?"<>|]/g, "-")
      .replace(/\s+/g, " ")
      .trim()
      .slice(0, 180) || "attachment"
  );
}

function attachmentValidationError(message) {
  const error = new Error(message);
  error.name = "AttachmentValidationError";
  return error;
}

export function isAttachmentValidationError(error) {
  return error?.name === "AttachmentValidationError";
}

function parseDataPayload(
  value,
  fallbackContentType = "application/octet-stream",
) {
  const input = String(value || "").trim();
  if (!input || isHttpUrl(input)) return null;

  const dataUriMatch = input.match(DATA_URI_PATTERN);
  if (dataUriMatch) {
    const contentType = dataUriMatch[1] || fallbackContentType;
    const isBase64 = Boolean(dataUriMatch[2]);
    const body = dataUriMatch[3] || "";
    return {
      contentType,
      buffer: isBase64
        ? Buffer.from(body, "base64")
        : Buffer.from(decodeURIComponent(body)),
    };
  }

  return {
    contentType: fallbackContentType,
    buffer: Buffer.from(input, "base64"),
  };
}

function publicUrlForKey(key) {
  if (publicBaseUrl) return `${publicBaseUrl}/${key}`;
  if (endpoint) return `${endpoint.replace(/\/$/, "")}/${bucket}/${key}`;
  return `https://${bucket}.s3.${region}.amazonaws.com/${key}`;
}

export async function uploadImageToS3(value, { folder, ownerId } = {}) {
  if (!value || isHttpUrl(value)) return value;
  const attachment = await uploadAttachmentToS3(
    {
      name: "image",
      contentType: "image/jpeg",
      dataUrl: value,
    },
    { folder: folder || "images", ownerId, maxBytes: maxImageBytes },
  );
  return attachment?.url || value;
}

export async function uploadAttachmentToS3(
  value,
  { folder, ownerId, maxBytes = maxAttachmentBytes } = {},
) {
  if (!value) return null;

  if (typeof value === "string") {
    if (isHttpUrl(value)) {
      return {
        name: "attachment",
        contentType: "application/octet-stream",
        size: 0,
        url: value,
      };
    }
    value = {
      name: "attachment",
      contentType: "application/octet-stream",
      dataUrl: value,
    };
  }

  const name = cleanFileName(value.name || value.fileName);
  const declaredContentType = value.contentType || value.type || "";
  const inferredContentType = contentTypeFromFileName(name);
  const contentType =
    !declaredContentType || declaredContentType === "application/octet-stream"
      ? inferredContentType
      : declaredContentType;
  const source = value.dataUrl || value.data || value.base64 || value.url;

  if (isHttpUrl(source)) {
    return {
      name,
      contentType,
      size: Number(value.size || 0),
      url: source,
    };
  }

  if (!allowedAttachmentTypes.has(contentType)) {
    throw attachmentValidationError(
      `Attachment type ${contentType} is not allowed.`,
    );
  }

  const parsed = parseDataPayload(source, contentType);
  if (!parsed) return null;
  if (parsed.buffer.length > maxBytes) {
    throw attachmentValidationError(
      `Attachment upload exceeds ${maxBytes} bytes.`,
    );
  }

  if (!bucket) {
    return {
      name,
      contentType: parsed.contentType,
      size: parsed.buffer.length,
      url: source,
      storage: "inline",
    };
  }

  const extension =
    path.extname(name) || extensionForContentType(parsed.contentType);
  const objectKey = path.posix.join(
    uploadPrefix,
    folder || "attachments",
    String(ownerId || "anonymous"),
    `${crypto.randomUUID()}${extension}`,
  );

  await s3.send(
    new PutObjectCommand({
      Bucket: bucket,
      Key: objectKey,
      Body: parsed.buffer,
      ContentType: parsed.contentType,
      ContentDisposition: `inline; filename="${name.replace(/"/g, "")}"`,
    }),
  );

  return {
    name,
    contentType: parsed.contentType,
    size: parsed.buffer.length,
    url: publicUrlForKey(objectKey),
    s3Key: objectKey,
  };
}

export async function uploadAttachmentsToS3(attachments, options = {}) {
  const values = Array.isArray(attachments) ? attachments : [];
  const uploaded = await Promise.all(
    values.map((attachment) => uploadAttachmentToS3(attachment, options)),
  );
  return uploaded.filter(Boolean);
}
