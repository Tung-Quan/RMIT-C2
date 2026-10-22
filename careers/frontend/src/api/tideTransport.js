import axios, { AxiosError } from "axios";
import { API_ORIGIN } from "./config.js";

let secureFetch;
export function bindTideTransport(transport) { secureFetch = transport; }

export async function tideAdapter(config) {
  if (!secureFetch) throw new AxiosError("Tide session is still initializing", "ERR_AUTH_INITIALIZING", config);
  const url = new URL(axios.getUri(config), window.location.origin);
  if (url.origin !== API_ORIGIN || !url.pathname.startsWith("/api/careers/")) throw new AxiosError("Unexpected API destination", "ERR_INVALID_URL", config);
  const headers = new Headers(config.headers?.toJSON() || config.headers || {});
  headers.delete("authorization"); headers.delete("dpop");
  if (config.data instanceof FormData) headers.delete("content-type");
  const signal = config.timeout ? AbortSignal.any([...(config.signal ? [config.signal] : []), AbortSignal.timeout(config.timeout)]) : config.signal;
  const response = await secureFetch(url.href, {
    method: (config.method || "GET").toUpperCase(), headers, signal,
    body: ["get", "head"].includes(config.method) ? undefined : config.data,
    cache: "no-store",
  });
  const result = { data: config.responseType === "blob" ? await response.blob() : config.responseType === "arraybuffer" ? await response.arrayBuffer() : await response.text(), status: response.status, statusText: response.statusText, headers: Object.fromEntries(response.headers), config, request: null };
  if (config.validateStatus && !config.validateStatus(response.status)) throw new AxiosError("Request returned HTTP " + response.status, response.status >= 500 ? "ERR_BAD_RESPONSE" : "ERR_BAD_REQUEST", config, null, result);
  return result;
}
