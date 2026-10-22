import "dotenv/config";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { createHash } from "node:crypto";
const origin = process.env.APP_ORIGIN || "http://localhost:5137";
const adapter = JSON.parse(await readFile("public/tidecloak.json", "utf8"));
const issuer = `${adapter["auth-server-url"].replace(/\/+$/, "")}/realms/${adapter.realm}`;
const path = `/tide_dpop/iss/${Buffer.from(issuer).toString("hex")}/aud/${Buffer.from(adapter.resource).toString("hex")}/tide_dpop_auth.html`;
const response = await fetch(new URL(path, origin));
assert.equal(
  response.status,
  200,
  "The real issuer/client relay path must return 200",
);
assert.equal(response.headers.get("allow-csp-from"), "*");
const bytes = Buffer.from(await response.arrayBuffer());
const canonical = await readFile(
  "node_modules/@tidecloak/js/tide_dpop_auth.html",
);
assert.deepEqual(
  bytes,
  canonical,
  "The served relay must match the installed SDK byte for byte",
);
for (const tag of ["script", "style"]) {
  for (const match of bytes
    .toString()
    .matchAll(new RegExp(`<${tag}[^>]*>([\\s\\S]*?)</${tag}>`, "gi"))) {
    assert.ok(
      response.headers
        .get("content-security-policy")
        ?.includes(
          `sha256-${createHash("sha256").update(match[1]).digest("base64")}`,
        ),
    );
  }
}
assert.equal(
  (
    await fetch(
      new URL("/tide_dpop/iss/6161/aud/6262/tide_dpop_auth.html", origin),
    )
  ).status,
  403,
  "Unknown issuer/client must be rejected",
);
const health = await fetch(new URL("/api/health", origin)).then((r) =>
  r.json(),
);
assert.equal(health.status, "ok");
assert.equal(health.authentication, "configured");
assert.equal((await fetch(new URL("/api/me", origin))).status, 401);
console.log(
  "PASS: database health, adapter, real relay URL, canonical bytes, CSP hashes, unknown-realm rejection, unauthenticated API rejection.",
);
console.log(
  "Personal Tide login and multi-user account linking require human interaction.",
);
