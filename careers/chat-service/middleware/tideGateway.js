import jwt from "jsonwebtoken";
import { createHash, timingSafeEqual } from "node:crypto";
import { safeUser, usersRepo } from "../repositories/chatRepository.js";
import { consumeGatewayNonce } from "../lib/redis.js";

export async function verifyGateway(token, audience, request) {
  const secret = process.env.FAIRENROL_GATEWAY_SECRET;
  if (!secret || secret.length < 32) throw new Error("Gateway is not configured");
  const claims = jwt.verify(token, secret, { algorithms: ["HS256"], issuer: "fairenrol-careers-gateway", audience, maxAge: "31s" });
  if (!claims.jti || !claims.exp || !claims.iat || claims.exp - claims.iat > 31 || !claims.tide_subject || !claims.tide_issuer || !claims.person_id || !claims.full_name) throw new Error("Missing identity");
  if (request) {
    const digest = createHash("sha256").update(request.rawBody || "").digest("hex");
    const expected = String(claims.body_sha256 || "");
    if (claims.method !== request.method || claims.path !== request.originalUrl || digest.length !== expected.length || !timingSafeEqual(Buffer.from(digest), Buffer.from(expected))) throw new Error("Assertion request mismatch");
  }
  if (!await consumeGatewayNonce(claims.jti)) throw new Error("Assertion replay");
  return claims;
}

export async function resolveTideChatUser(claims) {
  const key = "tide:" + createHash("sha256").update(claims.tide_issuer + "\0" + claims.tide_subject).digest("hex");
  // Stable issuer/subject binding only: an email or query string cannot select an existing account.
  let user = (await usersRepo.list()).find(u => u.appUserId === key);
  if (!user) {
    const id = createHash("sha256").update(key).digest("hex").slice(0, 32);
    try {
      user = await usersRepo.create({ _id: id, appUserId: key, username: claims.full_name.slice(0,64), displayName: claims.full_name.slice(0,64), email: claims.email || null, password: "", profilePicture: "", bio: "FairEnrol Tide identity" });
    } catch (error) {
      user = await usersRepo.getById(id);
      if (!user) throw error;
    }
  }
  return safeUser(user);
}

export async function authorizeTideSocket(socket, next) {
  try {
    const claims = await verifyGateway(socket.handshake.auth?.ticket, "careers-chat-connect");
    socket.data.tideUser = await resolveTideChatUser(claims);
    next();
  } catch { next(new Error("A fresh Tide-authenticated chat ticket is required")); }
}
