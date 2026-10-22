const currentOrigin =
  typeof window !== "undefined" ? window.location.origin : "http://localhost";
const configuredOrigin = import.meta.env?.VITE_API_BASE_URL || currentOrigin;

export const API_ORIGIN = new URL(configuredOrigin, currentOrigin).origin;
export const API_BASE_URL = new URL("/api/careers", `${API_ORIGIN}/`).href.replace(
  /\/$/,
  "",
);
