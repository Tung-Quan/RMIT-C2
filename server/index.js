import "dotenv/config";
import { postgresDatabase, initializeDatabase } from "./db.js";
import { loadAdapter } from "./auth/tide.js";
import { createApp } from "./app.js";

const db = postgresDatabase(process.env.DATABASE_URL);
await initializeDatabase(db);
const adapter = await loadAdapter(process.env.TIDE_ADAPTER_PATH);
const app = createApp({
  db,
  adapter,
  appOrigin: process.env.APP_ORIGIN,
  serveUi: process.env.NODE_ENV === "production",
});
const server = app.listen(
  Number(process.env.API_PORT || 3001),
  process.env.API_HOST || "127.0.0.1",
  () => {
    console.log(
      `FairEnrol API: http://${process.env.API_HOST || "127.0.0.1"}:${process.env.API_PORT || 3001}`,
    );
    console.log(
      `Tide authentication: ${adapter ? "configured" : "waiting for realm setup; protected endpoints fail closed"}`,
    );
  },
);
const cleanup = setInterval(
  () =>
    db
      .query("DELETE FROM dpop_replays WHERE expires_at<$1", [
        Date.now() - 60000,
      ])
      .catch((error) =>
        console.error("Replay-store cleanup failed:", error.code || error.name),
      ),
  600000,
);
cleanup.unref();
for (const signal of ["SIGINT", "SIGTERM"])
  process.on(signal, () =>
    server.close(async () => {
      clearInterval(cleanup);
      await db.close();
      process.exit(0);
    }),
  );
