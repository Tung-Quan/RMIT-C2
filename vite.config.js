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
    proxy: {
      "/api": "http://127.0.0.1:3001",
      "/careers-socket.io": { target: "http://127.0.0.1:3030", ws: true },
      "/careers-hmr": { target: "http://127.0.0.1:5174", ws: true },
      "/careers": { target: "http://127.0.0.1:5174", ws: true },
    },
  },
  preview: { host: "localhost", port: 5137, strictPort: true },
});
