import { createHash, randomUUID } from "node:crypto";
import { Router } from "express";
import { SignJWT } from "jose";
import { AppError } from "./errors.js";

export const GATEWAY_ISSUER = "fairenrol-careers-gateway";
export const bodyDigest = (body) => createHash("sha256").update(body || "").digest("hex");

export async function signCareersContext({ user, claims, secret, audience, method, path, body }) {
  if (!secret || secret.length < 32) throw new AppError(503, "CAREERS_NOT_CONFIGURED", "Run npm run kind:setup first.");
  const role = user.roles.includes("registrar") ? "hr" : "candidate";
  return new SignJWT({
    tide_issuer: claims.iss, tide_subject: claims.sub, person_id: user.id,
    full_name: user.name, role,
    email: claims.email_verified === true && typeof claims.email === "string" ? claims.email : null,
    ...(method ? { method, path, body_sha256: bodyDigest(body) } : {}),
  }).setProtectedHeader({ alg: "HS256", typ: "JWT" }).setIssuer(GATEWAY_ISSUER)
    .setAudience(audience).setSubject(user.id).setJti(randomUUID()).setIssuedAt().setExpirationTime("30s")
    .sign(new TextEncoder().encode(secret));
}

export function careersGateway(config = {}) {
  const router = Router();
  router.use(async (req, res) => {
    const { apiUrl, chatUrl, secret } = config;
    if (!apiUrl || !chatUrl || !secret) throw new AppError(503, "CAREERS_NOT_CONFIGURED", "FairEnrol career services are not configured. Run npm run kind:setup.");
    if (req.path === "/chat-ticket" && req.method === "POST") {
      const ticket = await signCareersContext({ user: req.user, claims: req.tide, secret, audience: "careers-chat-connect" });
      return res.json({ ticket, expiresIn: 30 });
    }
    const isChat = req.path === "/chat" || req.path.startsWith("/chat/");
    const path = isChat ? req.url.slice(5) || "/" : req.url;
    if (!path.startsWith("/") || path.startsWith("//") || /(?:^|\/)\.\.(?:\/|$)/.test(decodeURIComponent(path.split("?")[0]))) throw new AppError(400, "INVALID_PATH", "Invalid career path.");
    if (/^\/(?:auth|api\/(?:auth|users))\/(?:login|register|signup)(?:[/?]|$)/.test(path)) return res.status(410).json({ detail: "Sign in through TideCloak. Password login and registration are disabled." });
    // Upload files are fetched through the document ownership endpoint, never the old public mount.
    if (/^\/uploads(?:\/|$)/.test(path)) return res.status(404).json({ detail: "Use the authenticated document download action." });
    const privateBase = new URL(isChat ? chatUrl : apiUrl);
    const destination = new URL(path, privateBase);
    const allowed = isChat ? /^\/api\/(?:auth|users|messages|groups|status)(?:[/?]|$)/ : /^\/(?:auth|applications|candidate|companies|jobs|hr|documents|ai|dashboard|processing-jobs)(?:[/?]|$)/;
    if (destination.origin !== privateBase.origin || decodeURIComponent(path).includes("\\") || !allowed.test(path)) return res.status(404).json({ detail: "FairEnrol endpoint not found" });
    const body = Buffer.isBuffer(req.body) ? req.body : Buffer.alloc(0);
    const context = await signCareersContext({ user: req.user, claims: req.tide, secret, audience: isChat ? "careers-chat" : "careers-api", method: req.method, path, body });
    const headers = { Authorization: `Bearer ${context}`, Accept: req.get("accept") || "application/json" };
    for (const name of ["content-type", "idempotency-key", "if-match"]) if (req.get(name)) headers[name] = req.get(name);
    let upstream;
    try {
      upstream = await fetch(destination, {
        method: req.method, headers, body: ["GET", "HEAD"].includes(req.method) ? undefined : body,
        redirect: "manual", signal: AbortSignal.timeout(120000),
      });
    } catch {
      throw new AppError(502, "CAREERS_UNAVAILABLE", "FairEnrol career services are unavailable. Check the Kind workloads.");
    }
    res.status(upstream.status);
    for (const name of ["content-type", "content-disposition", "etag", "retry-after", "deprecation", "sunset"]) if (upstream.headers.has(name)) res.set(name, upstream.headers.get(name));
    res.set("Cache-Control", "no-store");
    res.send(Buffer.from(await upstream.arrayBuffer()));
  });
  return router;
}
