import { createHash } from "node:crypto";
import { readFile } from "node:fs/promises";
import {
  calculateJwkThumbprint,
  createLocalJWKSet,
  decodeProtectedHeader,
  importJWK,
  jwtVerify,
} from "jose";
import { AppError } from "../errors.js";

export async function loadAdapter(path = "public/tidecloak.json") {
  try {
    const adapter = JSON.parse(await readFile(path, "utf8"));
    if (
      !adapter.jwk?.keys?.length ||
      !adapter.realm ||
      !adapter.resource ||
      !adapter["auth-server-url"]
    ) {
      throw new Error(
        "Tide adapter must contain realm, resource, auth-server-url and embedded jwk.keys.",
      );
    }
    if (adapter.credentials?.secret)
      throw new Error("A public SPA adapter must not contain a client secret.");
    return adapter;
  } catch (error) {
    if (error.code === "ENOENT") return null;
    throw error;
  }
}

// Adapted from Tide MCP templates/dpop-verify/verifyDpop.ts. Uses a shared PostgreSQL replay store.
export function tideAuthenticator({
  adapter,
  db,
  appOrigin,
  maxTokenAge = 600,
}) {
  const keys = adapter && createLocalJWKSet(adapter.jwk);
  const issuer =
    adapter &&
    `${adapter["auth-server-url"].replace(/\/+$/, "")}/realms/${adapter.realm}`;
  const origin = new URL(appOrigin).origin;
  return async (req) => {
    if (!adapter)
      throw new AppError(
        503,
        "AUTH_NOT_CONFIGURED",
        "TideCloak setup is incomplete. Export the Tide adapter and restart the API.",
      );
    const auth = req.get("authorization") || "";
    if (!/^DPoP [^\s]+$/i.test(auth))
      throw new AppError(
        401,
        "UNAUTHORIZED",
        "A DPoP-bound access token is required.",
      );
    const token = auth.slice(5);
    let claims, replayKey, replayExpires;
    try {
      ({ payload: claims } = await jwtVerify(token, keys, {
        issuer,
        algorithms: ["EdDSA", "ES256", "ES384", "ES512"],
        requiredClaims: ["sub", "exp", "iat"],
        maxTokenAge,
        clockTolerance: 5,
      }));
      if (
        claims.azp !== adapter.resource ||
        typeof claims.sub !== "string" ||
        !claims.sub ||
        !claims.cnf?.jkt
      )
        throw new Error("Client or binding mismatch");
      const proof = req.get("dpop");
      if (!proof || proof.length > 16000) throw new Error("Missing proof");
      const header = decodeProtectedHeader(proof);
      if (
        header.typ !== "dpop+jwt" ||
        header.alg !== "ES256" ||
        !header.jwk ||
        header.jwk.d ||
        header.jwk.k
      )
        throw new Error("Invalid proof header");
      const proofKey = await importJWK(header.jwk, "ES256");
      const { payload } = await jwtVerify(proof, proofKey, {
        algorithms: ["ES256"],
      });
      const thumbprint = await calculateJwkThumbprint(header.jwk);
      const expectedUrl = new URL(req.originalUrl, origin);
      expectedUrl.search = "";
      expectedUrl.hash = "";
      if (expectedUrl.origin !== origin)
        throw new Error("Unexpected request origin");
      if (
        thumbprint !== claims.cnf.jkt ||
        payload.ath !==
          createHash("sha256").update(token).digest("base64url") ||
        payload.htm !== req.method ||
        payload.htu !== expectedUrl.href ||
        !Number.isFinite(payload.iat) ||
        Math.abs(Date.now() / 1000 - payload.iat) > 60 ||
        typeof payload.jti !== "string" ||
        !payload.jti ||
        payload.jti.length > 200
      )
        throw new Error("Proof does not match request");
      replayKey = `${thumbprint}:${payload.jti}`;
      replayExpires = Math.ceil((payload.iat + 65) * 1000);
    } catch {
      throw new AppError(
        401,
        "UNAUTHORIZED",
        "The access token or DPoP proof is invalid, expired, or already used.",
      );
    }
    // Keep storage failures outside the credential-error handler: a database outage is not a bad login.
    const replay = await db.query(
      `INSERT INTO dpop_replays(key,expires_at) VALUES($1,$2)
       ON CONFLICT(key) DO UPDATE SET expires_at=EXCLUDED.expires_at WHERE dpop_replays.expires_at < $3 RETURNING key`,
      [replayKey, replayExpires, Date.now()],
    );
    if (!replay.rows.length)
      throw new AppError(
        401,
        "UNAUTHORIZED",
        "The DPoP proof has already been used.",
      );
    return claims;
  };
}
