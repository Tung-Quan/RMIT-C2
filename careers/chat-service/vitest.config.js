import { defineConfig } from "vitest/config";

// Isolate this service from the parent React/Vite application's configuration.
export default defineConfig({
  test: {
    include: ["tests/**/*.test.js"],
    coverage: { provider: "v8", reporter: ["text", "json-summary"] },
  },
});
