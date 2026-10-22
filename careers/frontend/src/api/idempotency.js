export function createIdempotencyKey() {
  if (globalThis.crypto?.randomUUID) {
    return globalThis.crypto.randomUUID();
  }

  return `cmd-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

export function idempotencyHeaders(idempotencyKey) {
  return idempotencyKey
    ? {
        headers: {
          "Idempotency-Key": idempotencyKey
        }
      }
    : undefined;
}

export function isIdempotencyReplay(response) {
  return String(response?.headers?.["idempotency-replayed"] || "").toLowerCase() === "true";
}
