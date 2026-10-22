import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { dpopRelay } from "./shared/dpop-relay.js";

export default defineConfig({
  plugins: [
    react(),
    {
      name: "tide-dpop-relay",
      configureServer: (server) => {
        server.middlewares.use(dpopRelay());
      },
      configurePreviewServer: (server) => {
        server.middlewares.use(dpopRelay());
      },
    },
  ],
  server: {
    host: "localhost",
    port: 5137,
    strictPort: true,
    proxy: { "/api": "http://127.0.0.1:3001" },
  },
  preview: { host: "localhost", port: 5137, strictPort: true },
});
