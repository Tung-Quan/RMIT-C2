import axios from "axios";
import { tideAdapter } from "./tideTransport.js";
import { API_BASE_URL, API_ORIGIN } from "./config.js";

export { API_BASE_URL, API_ORIGIN };
export const TOKEN_KEY = "fairenrol_careers_token";
export const STORAGE_KEY_PREFIX = "fairenrol_careers_";
export const AUTH_EXPIRED_EVENT = "fairenrol_careers_auth_expired";

export const api = axios.create({
  baseURL: API_BASE_URL, adapter: tideAdapter
});

export function getStoredToken() { return null; }

export function setStoredToken() { throw new Error("Use the TideCloak session; tokens are not stored here."); }

export function clearStoredToken() {
  localStorage.removeItem(TOKEN_KEY);
}

function clearPrefixedStorage(storage) {
  const keys = [];
  for (let index = 0; index < storage.length; index += 1) {
    const key = storage.key(index);
    if (key?.startsWith(STORAGE_KEY_PREFIX)) {
      keys.push(key);
    }
  }
  keys.forEach((key) => storage.removeItem(key));
}

export function clearLocalSession() {
  clearPrefixedStorage(localStorage);
  clearPrefixedStorage(sessionStorage);
}

export function resolveApiUrl(value) {
  if (!value) return value;
  if (value.startsWith("http://") || value.startsWith("https://")) {
    return value;
  }
  return `${API_BASE_URL}${value.startsWith("/") ? "" : "/"}${value}`;
}

function isAuthEndpoint(url) {
  if (!url) return false;
  return url.includes("/auth/login") || url.includes("/auth/register");
}



api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (
      error?.response?.status === 401 &&
      getStoredToken() &&
      !isAuthEndpoint(error.config?.url)
    ) {
      clearLocalSession();
      window.dispatchEvent(new CustomEvent(AUTH_EXPIRED_EVENT));
    }
    return Promise.reject(error);
  }
);

export function getErrorMessage(error) {
  return normalizeMutationError(error).message;
}

export function normalizeMutationError(error) {
  if (!error?.response) {
    if (!error?.request && typeof error?.message === "string" && error.message) {
      return {
        type: "client",
        retryable: false,
        message: error.message
      };
    }
    return {
      type: "network",
      retryable: true,
      message: "Network error. Check your connection and try again."
    };
  }

  const { status, data } = error.response;
  const detail = error?.response?.data?.detail;

  if (status === 401) {
    if (isAuthEndpoint(error.config?.url)) {
      return {
        type: "unauthorized",
        message: typeof detail === "string" ? detail : "Incorrect email or password."
      };
    }
    return { type: "unauthorized", message: "Your session expired. Please sign in again." };
  }
  if (status === 403) {
    return { type: "forbidden", message: "You do not have permission to do that." };
  }
  if (status === 404) {
    return { type: "not-found", message: messageFromDetail(detail) || "Resource not found." };
  }
  if (Array.isArray(detail)) {
    return {
      type: "validation",
      message: detail.map(formatValidationDetail).join(". ")
    };
  }
  if (detail?.code === "stale_version") {
    return {
      type: "stale",
      currentVersion: detail.currentVersion,
      expectedVersion: detail.expectedVersion,
      message:
        "This item was changed by another user or session. We loaded the latest version. Review the current state before trying again."
    };
  }
  if (detail?.code === "invalid_state_transition") {
    return {
      type: "invalid-transition",
      currentState: detail.currentState || detail.currentStatus,
      message: detail.message || "That workflow action is no longer valid for the latest state."
    };
  }
  if (detail?.code === "idempotency_key_reused") {
    return {
      type: "idempotency-reused",
      message:
        detail.message || "This action was retried with different details. Start a new action and try again."
    };
  }
  if (detail?.code === "duplicate_application") {
    return {
      type: "duplicate",
      message: detail.message || "You already applied to this job. Open your submissions to review it."
    };
  }
  if (detail?.code === "resource_not_found" || detail?.code === "not_found") {
    return {
      type: "not-found",
      message: detail.message || "Resource not found."
    };
  }
  if (status === 409 && typeof detail === "string" && detail.toLowerCase().includes("already applied")) {
    return {
      type: "duplicate",
      message: "You already applied to this job. Open your submissions to review it."
    };
  }
  if (status === 409) {
    return {
      type: "conflict",
      message: messageFromDetail(detail) || "This action conflicts with the latest server state."
    };
  }

  return {
    type: "unknown",
    message: messageFromDetail(detail) || data?.message || error?.message || "Something went wrong"
  };
}

function formatValidationDetail(item) {
  if (typeof item === "string") return item;
  const location = Array.isArray(item?.loc) ? item.loc.at(-1) : null;
  return location ? `${location}: ${item?.msg || "Invalid value"}` : item?.msg || "Invalid request";
}

function messageFromDetail(detail) {
  if (typeof detail === "string") {
    return detail;
  }
  if (detail && typeof detail === "object" && typeof detail.message === "string") {
    return detail.message;
  }
  return "";
}
