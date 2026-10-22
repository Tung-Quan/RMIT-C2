export function createApi(secureFetch) {
  return async (
    path,
    { method = "GET", body, signal, idempotencyKey } = {},
  ) => {
    const headers = { Accept: "application/json" };
    if (method !== "GET") {
      headers["Content-Type"] = "application/json";
      headers["Idempotency-Key"] = idempotencyKey || crypto.randomUUID();
    }
    const response = await secureFetch(
      new URL(path, window.location.origin).href,
      {
        method,
        headers,
        signal,
        cache: "no-store",
        ...(body !== undefined ? { body: JSON.stringify(body) } : {}),
      },
    );
    const data = await response.json().catch(() => null);
    if (!response.ok) {
      const error = new Error(
        data?.error?.message || `The server returned ${response.status}.`,
      );
      error.status = response.status;
      throw error;
    }
    return data;
  };
}
