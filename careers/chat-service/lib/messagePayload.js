import {
  isAttachmentValidationError,
  uploadAttachmentsToS3,
} from "./s3Storage.js";

const maxAttachments = Number(process.env.CHAT_MAX_ATTACHMENTS || 4);

function cleanText(value) {
  return String(value || "").trim();
}

function normalizeIncomingAttachments({ image, attachments }) {
  const items = Array.isArray(attachments) ? [...attachments] : [];
  if (image) {
    items.unshift({
      name: "image attachment",
      contentType: "image/jpeg",
      dataUrl: image,
    });
  }
  return items.slice(0, maxAttachments + 1);
}

function attachmentValidationError(message) {
  const error = new Error(message);
  error.name = "AttachmentValidationError";
  return error;
}

function firstImageUrl(attachments) {
  return (
    attachments.find((attachment) =>
      String(attachment.contentType || attachment.type || "").startsWith(
        "image/",
      ),
    )?.url || ""
  );
}

export async function buildStoredMessagePayload({
  text,
  image,
  attachments,
  folder,
  ownerId,
}) {
  const normalizedText = cleanText(text);
  const incomingAttachments = normalizeIncomingAttachments({
    image,
    attachments,
  });

  if (incomingAttachments.length > maxAttachments) {
    throw attachmentValidationError(
      `Attach up to ${maxAttachments} files at once.`,
    );
  }

  if (!normalizedText && incomingAttachments.length === 0) {
    throw attachmentValidationError("Message must have text or an attachment.");
  }

  const storedAttachments = await uploadAttachmentsToS3(incomingAttachments, {
    folder,
    ownerId,
  });

  return {
    text: normalizedText,
    attachments: storedAttachments,
    image: firstImageUrl(storedAttachments),
  };
}

export function messagePayloadErrorResponse(error) {
  if (
    isAttachmentValidationError(error) ||
    error?.name === "AttachmentValidationError"
  ) {
    return {
      status: 400,
      body: {
        success: false,
        message: error.message,
      },
    };
  }
  return null;
}
