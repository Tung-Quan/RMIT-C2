import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  base: "/careers/",
  plugins: [
    react(),
    {
      name: "vite-plugin-tide-session-reload",
      handleHotUpdate({ file, server }) {
        // Refresh can leave the SDK's iframe broker alive after React replaces
        // its provider. Reload the document when the session boundary changes.
        if (/\/src\/(?:main\.jsx|context\/AuthContext\.jsx|api\/(?:client|tideTransport)\.js)$/.test(file.replaceAll("\\", "/"))) {
          server.ws.send({ type: "full-reload" });
          return [];
        }
      },
    },
  ],
  server: { host: "127.0.0.1", port: 5174, strictPort: true, hmr: { path: "/careers-hmr" } },
  build: { outDir: "dist" },
});
