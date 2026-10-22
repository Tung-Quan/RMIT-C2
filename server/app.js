import express from "express";
import { existsSync } from "node:fs";
import { resolve } from "node:path";
import { z } from "zod";
import { AppError } from "./errors.js";
import { tideAuthenticator } from "./auth/tide.js";
import * as service from "./services.js";
import { dpopRelay } from "../shared/dpop-relay.js";
import { careersGateway } from "./careers-gateway.js";
import httpProxy from "http-proxy-3";

const id = z.string().min(1).max(100);
const reasons = {
  reason: z.string().trim().min(5).max(2000),
  publicReason: z.string().trim().min(5).max(240),
};
const requestSchema = z.discriminatedUnion("kind", [
  ...["force", "jump", "remove"].map((kind) =>
    z
      .object({
        kind: z.literal(kind),
        courseId: id,
        studentId: id,
        ...reasons,
      })
      .strict(),
  ),
  z
    .object({
      kind: z.literal("panel"),
      replaceId: id,
      candidateId: id,
      ...reasons,
    })
    .strict(),
]);

export function createApp({
  db,
  adapter,
  appOrigin = "http://localhost:5137",
  allowedOrigins = [],
  serveUi = false,
  careers,
}) {
  const app = express();
  if (careers?.chatUrl) {
    const socketProxy = httpProxy.createProxyServer({ target: careers.chatUrl, changeOrigin: true });
    app.locals.careersSocketProxy = socketProxy;
    app.use("/careers-socket.io", (req, res) => {
      req.url = req.originalUrl;
      socketProxy.web(req, res, {}, () => {
        if (!res.headersSent) res.status(502).json({ error: { code: "CHAT_UNAVAILABLE", message: "Chat service is unavailable." } });
      });
    });
  }
  app.disable("x-powered-by");
  const corsOrigins = new Set([
    new URL(appOrigin).origin,
    "http://localhost:5137",
    "https://localhost",
    "capacitor://localhost",
    ...allowedOrigins,
  ]);
  app.use((req, res, next) => {
    const origin = req.get("origin");
    if (origin && corsOrigins.has(origin)) {
      res.set("Access-Control-Allow-Origin", origin);
      res.set("Access-Control-Allow-Methods", "GET,POST,PATCH,DELETE,OPTIONS");
      res.set(
        "Access-Control-Allow-Headers",
        "Accept, Authorization, Content-Type, DPoP, Idempotency-Key, X-Requested-With",
      );
      res.set("Access-Control-Expose-Headers", "DPoP-Nonce, WWW-Authenticate");
      res.vary("Origin");
    }
    if (req.method === "OPTIONS")
      return origin && corsOrigins.has(origin)
        ? res.sendStatus(204)
        : res.sendStatus(403);
    next();
  });
  app.use((req, res, next) => {
    res.set("X-Content-Type-Options", "nosniff");
    if (req.path.startsWith("/api")) res.set("Cache-Control", "no-store");
    next();
  });
  const authenticate = tideAuthenticator({ adapter, db, appOrigin });
  const requireSession = async (req, res, next) => {
    req.tide = await authenticate(req);
    req.user = await service.currentUser(db, req.tide);
    next();
  };
  app.use("/api/careers", requireSession, express.raw({ type: () => true, limit: "26mb" }), careersGateway(careers));
  app.use(express.json({ limit: "12kb" }));
  app.get("/api/health", async (req, res) => {
    await db.query("SELECT 1");
    res.json({
      status: "ok",
      authentication: adapter ? "configured" : "setup-required",
    });
  });
  app.get("/api/public/exceptions", async (req, res) =>
    res.json(await service.publicExceptions(db)),
  );
  app.use("/api", requireSession);
  app.get("/api/me", (req, res) => res.json(req.user));
  app.get("/api/state", async (req, res) =>
    res.json(await service.snapshot(db, req.user)),
  );
  app.get("/api/courses", async (req, res) =>
    res.json((await service.snapshot(db, req.user)).courses),
  );
  app.get("/api/exception-requests", async (req, res) =>
    res.json((await service.snapshot(db, req.user)).requests),
  );
  const command = (schema, run) => async (req, res) => {
    const data = schema.parse(req.body ?? {});
    res.json(
      await service.mutate(
        db,
        req.user,
        `${req.method} ${req.path}`,
        req.get("idempotency-key"),
        data,
        (tx) => run(tx, req.user, req, data),
      ),
    );
  };
  const empty = z.object({}).strict();
  app.post(
    "/api/courses/:id/enrolments",
    command(empty, (tx, user, req) => service.enrol(tx, user, req.params.id)),
  );
  app.delete(
    "/api/courses/:id/enrolments/me",
    command(empty, (tx, user, req) =>
      service.enrol(tx, user, req.params.id, true),
    ),
  );
  app.patch(
    "/api/courses/:id/capacity",
    command(
      z.object({ capacity: z.number().int().min(1).max(10000) }).strict(),
      (tx, user, req, body) =>
        service.setCapacity(tx, user, req.params.id, body.capacity),
    ),
  );
  app.post(
    "/api/exception-requests",
    command(requestSchema, (tx, user, req, body) =>
      service.createRequest(tx, user, body),
    ),
  );
  app.post(
    "/api/exception-requests/:id/approvals",
    command(empty, (tx, user, req) => service.vote(tx, user, req.params.id)),
  );
  app.post(
    "/api/exception-requests/:id/denial",
    command(empty, (tx, user, req) =>
      service.vote(tx, user, req.params.id, true),
    ),
  );
  app.use("/api", (req, res) =>
    res.status(404).json({
      error: { code: "NOT_FOUND", message: "API endpoint not found." },
    }),
  );
  app.use(
    dpopRelay({
      adapterPath: process.env.TIDE_ADAPTER_PATH || "public/tidecloak.json",
    }),
  );
  if (serveUi && existsSync("dist/index.html")) {
    if (existsSync("careers/frontend/dist/index.html")) {
      app.use("/careers", express.static(resolve("careers/frontend/dist"), { index: false }));
      app.get(["/careers", "/careers/{*path}"], (req, res, next) => {
        if (req.path.includes(".")) return next();
        res.sendFile(resolve("careers/frontend/dist/index.html"));
      });
    }
    app.use(express.static(resolve("dist"), { index: false }));
    app.get("/{*path}", (req, res, next) => {
      // Missing JSON/assets must not masquerade as index.html.
      if (req.path.includes(".")) return next();
      res.sendFile(resolve("dist/index.html"));
    });
  }
  app.use((error, req, res, next) => {
    if (res.headersSent) return next(error);
    if (error instanceof z.ZodError)
      return res.status(400).json({
        error: {
          code: "INVALID_INPUT",
          message: error.issues
            .map((i) => `${i.path.join(".") || "body"}: ${i.message}`)
            .join("; "),
        },
      });
    const status =
      error instanceof AppError
        ? error.status
        : error.status === 400 || error.status === 413
          ? error.status
          : 500;
    if (status === 500)
      console.error(
        "API request failed:",
        error.code || error.name,
        error.message,
      );
    res.status(status).json({
      error: {
        code:
          error instanceof AppError
            ? error.code
            : status === 500
              ? "INTERNAL_ERROR"
              : "INVALID_REQUEST",
        message:
          status === 500
            ? "The request could not be completed. Please try again."
            : error.message,
      },
    });
  });
  return app;
}
