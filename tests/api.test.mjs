import { after, before, beforeEach, test } from "node:test";
import assert from "node:assert/strict";
import { createHash, randomUUID } from "node:crypto";
import { PGlite } from "@electric-sql/pglite";
import {
  calculateJwkThumbprint,
  exportJWK,
  generateKeyPair,
  SignJWT,
} from "jose";
import { initializeDatabase, linkIdentity } from "../server/db.js";
import { createApp } from "../server/app.js";
import { postgresDatabase } from "../server/db.js";
import pg from "pg";
import "dotenv/config";

const issuer = "http://localhost:8080/realms/fairenrol";
const origin = "http://fairenrol.test";
const users = [
  "registrar-1",
  "approver-1",
  "approver-2",
  "approver-3",
  "approver-4",
  "s01",
  "s04",
  "s17",
  "s18",
];
let engine,
  db,
  server,
  base,
  realmKey,
  publicKey,
  proofKey,
  publicProof,
  thumbprint,
  testSchema,
  control;
before(async () => {
  if (process.env.FAIRENROL_TEST_POSTGRES === "1") {
    // Create a disposable, randomly named schema. Never truncate the app's public schema.
    testSchema = `fairenrol_test_${randomUUID().replaceAll("-", "")}`;
    control = new pg.Pool({ connectionString: process.env.DATABASE_URL });
    await control.query(`CREATE SCHEMA ${testSchema}`);
    const url = new URL(process.env.DATABASE_URL);
    url.searchParams.set("options", `-c search_path=${testSchema}`);
    db = postgresDatabase(url.href);
  } else {
    engine = new PGlite();
    db = {
      query: async (q, a) =>
        !a && q.includes(";")
          ? (await engine.exec(q)).at(-1)
          : engine.query(q, a),
      transaction: (fn) => engine.transaction(fn),
    };
  }
  realmKey = await generateKeyPair("EdDSA", { extractable: true });
  proofKey = await generateKeyPair("ES256", { extractable: true });
  publicKey = {
    ...(await exportJWK(realmKey.publicKey)),
    kid: "test-vvk",
    alg: "EdDSA",
  };
  publicProof = await exportJWK(proofKey.publicKey);
  thumbprint = await calculateJwkThumbprint(publicProof);
  await initializeDatabase(db);
  const adapter = {
    realm: "fairenrol",
    resource: "fairenrol-client",
    "auth-server-url": "http://localhost:8080",
    jwk: { keys: [publicKey] },
  };
  const app = createApp({ db, adapter, appOrigin: origin });
  server = app.listen(0, "127.0.0.1");
  await new Promise((resolve) => server.once("listening", resolve));
  base = `http://127.0.0.1:${server.address().port}`;
});
beforeEach(async () => {
  await db.query(
    "TRUNCATE app_lock,people,courses,dpop_replays RESTART IDENTITY CASCADE",
  );
  await db.query("INSERT INTO app_lock(id) VALUES(1)");
  await initializeDatabase(db);
  for (const personId of users)
    await linkIdentity(db, { issuer, subject: personId, personId });
});
after(async () => {
  if (server) await new Promise((resolve) => server.close(resolve));
  await engine?.close();
  if (control) {
    await db.close();
    if (!/^fairenrol_test_[a-f0-9]{32}$/.test(testSchema))
      throw new Error("Refusing to drop an unexpected test schema");
    await control.query(`DROP SCHEMA ${testSchema} CASCADE`);
    await control.end();
  }
});

async function headers(user, path, method = "GET", options = {}) {
  const now = Math.floor(Date.now() / 1000);
  const role = user.startsWith("approver")
    ? "approver"
    : user.startsWith("registrar")
      ? "registrar"
      : "student";
  const claims = {
    iss: issuer,
    sub: user,
    azp: "fairenrol-client",
    exp: now + 300,
    iat: now,
    realm_access: { roles: [role] },
    cnf: { jkt: thumbprint },
    ...options.claims,
  };
  const token = await new SignJWT(claims)
    .setProtectedHeader({ alg: "EdDSA", kid: "test-vvk" })
    .sign(options.realmPrivateKey || realmKey.privateKey);
  const proof = await new SignJWT({
    jti: randomUUID(),
    htm: method,
    htu: new URL(path, origin).href.split("?")[0],
    iat: now,
    ath: createHash("sha256").update(token).digest("base64url"),
    ...options.proof,
  })
    .setProtectedHeader({ alg: "ES256", typ: "dpop+jwt", jwk: publicProof })
    .sign(proofKey.privateKey);
  return {
    Authorization: `DPoP ${token}`,
    DPoP: proof,
    "Content-Type": "application/json",
    "Idempotency-Key": options.key || randomUUID(),
  };
}
async function call(user, path, method = "GET", body, options) {
  const response = await fetch(base + path, {
    method,
    headers: await headers(user, path, method, options),
    ...(body === undefined ? {} : { body: JSON.stringify(body) }),
  });
  return { status: response.status, body: await response.json() };
}
const proposal = {
  kind: "force",
  courseId: "comp3100",
  studentId: "s04",
  reason: "Private accommodation evidence for authorized reviewers.",
  publicReason: "Approved exceptional course access.",
};
async function request(user = "registrar-1", body = proposal) {
  const result = await call(user, "/api/exception-requests", "POST", body);
  assert.equal(result.status, 200, JSON.stringify(result.body));
  return result.body.id;
}

test("protected endpoints require an authenticated identity; public views disclose no identities", async () => {
  assert.equal((await fetch(base + "/api/me")).status, 401);
  const me = await call("s17", "/api/me");
  assert.equal(me.status, 200);
  assert.equal(me.body.id, "s17");
  const state = await call("s17", "/api/state");
  assert.deepEqual(state.body.people, []);
  assert.deepEqual(state.body.requests, []);
  assert.equal("roster" in state.body.courses[0], false);
  assert.deepEqual(
    await (await fetch(base + "/api/public/exceptions")).json(),
    [],
  );
});

test("expired, wrong issuer/client, unbound and forged access tokens fail", async () => {
  const wrongKey = await generateKeyPair("EdDSA");
  for (const options of [
    { claims: { exp: 1 } },
    { claims: { iss: "https://wrong.example/realms/fairenrol" } },
    { claims: { azp: "other-client" } },
    { claims: { cnf: {} } },
    { claims: { iat: Math.floor(Date.now() / 1000) + 600 } },
    { realmPrivateKey: wrongKey.privateKey },
  ])
    assert.equal(
      (await call("s17", "/api/me", "GET", undefined, options)).status,
      401,
    );
});

test("DPoP is mandatory; Bearer downgrade, altered method/URL/token hash and replay fail", async () => {
  const valid = await headers("s17", "/api/me");
  const bearer = {
    ...valid,
    Authorization: valid.Authorization.replace("DPoP ", "Bearer "),
  };
  assert.equal(
    (await fetch(base + "/api/me", { headers: bearer })).status,
    401,
  );
  const missing = { ...valid };
  delete missing.DPoP;
  assert.equal(
    (await fetch(base + "/api/me", { headers: missing })).status,
    401,
  );
  for (const proof of [
    { htm: "POST" },
    { htu: "https://other.example/api/me" },
    { ath: "wrong" },
    { iat: 1 },
  ]) {
    assert.equal(
      (await call("s17", "/api/me", "GET", undefined, { proof })).status,
      401,
    );
  }
  assert.equal((await fetch(base + "/api/me", { headers: valid })).status, 200);
  assert.equal((await fetch(base + "/api/me", { headers: valid })).status, 401);
});

test("DPoP replay storage is shared across independent authenticators", async () => {
  const adapter = {
    realm: "fairenrol",
    resource: "fairenrol-client",
    "auth-server-url": "http://localhost:8080",
    jwk: { keys: [publicKey] },
  };
  const second = createApp({ db, adapter, appOrigin: origin }).listen(
    0,
    "127.0.0.1",
  );
  await new Promise((resolve) => second.once("listening", resolve));
  try {
    const proof = await headers("s17", "/api/me");
    assert.equal(
      (await fetch(base + "/api/me", { headers: proof })).status,
      200,
    );
    assert.equal(
      (
        await fetch(`http://127.0.0.1:${second.address().port}/api/me`, {
          headers: proof,
        })
      ).status,
      401,
    );
  } finally {
    await new Promise((resolve) => second.close(resolve));
  }
});

test("students cannot impersonate a peer or invoke registrar/reviewer mutations", async () => {
  assert.equal(
    (
      await call("s17", "/api/courses/comp3100/capacity", "PATCH", {
        capacity: 4,
      })
    ).status,
    403,
  );
  assert.equal(
    (
      await call("s17", "/api/courses/comp3100/enrolments", "POST", {
        studentId: "s04",
      })
    ).status,
    400,
  );
  assert.equal(
    (await call("s17", "/api/exception-requests", "POST", proposal)).status,
    403,
  );
  const id = await request();
  assert.equal(
    (
      await call(
        "registrar-1",
        `/api/exception-requests/${id}/approvals`,
        "POST",
        {},
      )
    ).status,
    403,
  );
  assert.equal(
    (await call("registrar-1", "/api/courses/comp3100/force-enrol", "POST", {}))
      .status,
    404,
  );
});

test("simultaneous last-seat joins preserve one seat, FIFO and uniqueness", async () => {
  await db.query(
    "INSERT INTO courses(id,code,name,capacity) VALUES('last-seat','TEST101','Concurrency',1)",
  );
  const results = await Promise.all(
    ["s17", "s18"].map((user) =>
      call(user, "/api/courses/last-seat/enrolments", "POST", {}),
    ),
  );
  assert.deepEqual(
    results.map((r) => r.status),
    [200, 200],
  );
  const rows = (
    await db.query(
      "SELECT * FROM memberships WHERE course_id='last-seat' ORDER BY sort_order",
    )
  ).rows;
  assert.equal(rows.length, 2);
  assert.equal(rows[0].status, "enrolled");
  assert.equal(rows[1].status, "waiting");
  await call(
    rows[0].person_id,
    "/api/courses/last-seat/enrolments",
    "POST",
    {},
  );
  assert.equal(
    (await db.query("SELECT * FROM memberships WHERE course_id='last-seat'"))
      .rows.length,
    2,
  );
});

test("withdrawal and capacity increases promote existing waiting students in order", async () => {
  assert.equal(
    (await call("s01", "/api/courses/comp3100/enrolments/me", "DELETE", {}))
      .status,
    200,
  );
  assert.equal(
    (
      await db.query(
        "SELECT status FROM memberships WHERE course_id='comp3100' AND person_id='s04'",
      )
    ).rows[0].status,
    "enrolled",
  );
  assert.equal(
    (
      await call("registrar-1", "/api/courses/comp3100/capacity", "PATCH", {
        capacity: 4,
      })
    ).status,
    200,
  );
  assert.equal(
    (
      await db.query(
        "SELECT status FROM memberships WHERE course_id='comp3100' AND person_id='s05'",
      )
    ).rows[0].status,
    "enrolled",
  );
  assert.equal(
    (
      await call("registrar-1", "/api/courses/comp3100/capacity", "PATCH", {
        capacity: 1,
      })
    ).status,
    409,
  );
});

test("two distinct approvals apply an exception once; private reasons stay private", async () => {
  const id = await request();
  assert.equal(
    (
      await call(
        "approver-1",
        `/api/exception-requests/${id}/approvals`,
        "POST",
        {},
      )
    ).status,
    200,
  );
  assert.equal(
    (
      await call(
        "approver-1",
        `/api/exception-requests/${id}/approvals`,
        "POST",
        {},
      )
    ).status,
    409,
  );
  assert.equal(
    (
      await call(
        "approver-4",
        `/api/exception-requests/${id}/approvals`,
        "POST",
        {},
      )
    ).status,
    403,
  );
  const final = await Promise.all(
    ["approver-2", "approver-3"].map((user) =>
      call(user, `/api/exception-requests/${id}/approvals`, "POST", {}),
    ),
  );
  assert.deepEqual(final.map((r) => r.status).sort(), [200, 409]);
  assert.equal(
    Number(
      (
        await db.query(
          "SELECT count(*) AS n FROM audit_events WHERE kind='exception.applied'",
        )
      ).rows[0].n,
    ),
    1,
  );
  const publicView = await (
    await fetch(base + "/api/public/exceptions")
  ).json();
  assert.equal(publicView[0].reason, proposal.publicReason);
  assert.equal(JSON.stringify(publicView).includes(proposal.reason), false);
  assert.equal("data" in publicView[0], false);
});

test("a requester cannot review their own proposal, and denial closes a request", async () => {
  const id = await request("approver-1");
  assert.equal(
    (
      await call(
        "approver-1",
        `/api/exception-requests/${id}/approvals`,
        "POST",
        {},
      )
    ).status,
    403,
  );
  assert.equal(
    (
      await call(
        "approver-2",
        `/api/exception-requests/${id}/denial`,
        "POST",
        {},
      )
    ).status,
    200,
  );
  assert.equal(
    (
      await call(
        "approver-3",
        `/api/exception-requests/${id}/approvals`,
        "POST",
        {},
      )
    ).status,
    409,
  );
});

test("course mutations invalidate an earlier proposal; no stale action executes", async () => {
  const id = await request();
  await call("registrar-1", "/api/courses/comp3100/capacity", "PATCH", {
    capacity: 4,
  });
  const result = await call(
    "approver-1",
    `/api/exception-requests/${id}/approvals`,
    "POST",
    {},
  );
  assert.equal(result.status, 409);
  assert.equal(result.body.error.code, "STALE_REQUEST");
});

test("panel replacements require the old panel and invalidate other pending proposals", async () => {
  const other = await request();
  const id = await request("registrar-1", {
    kind: "panel",
    replaceId: "approver-3",
    candidateId: "approver-4",
    reason: "A reviewer is stepping down.",
    publicReason: "Scheduled panel membership rotation.",
  });
  assert.equal(
    (
      await call(
        "approver-4",
        `/api/exception-requests/${id}/approvals`,
        "POST",
        {},
      )
    ).status,
    403,
  );
  await call(
    "approver-1",
    `/api/exception-requests/${id}/approvals`,
    "POST",
    {},
  );
  await call(
    "approver-2",
    `/api/exception-requests/${id}/approvals`,
    "POST",
    {},
  );
  assert.deepEqual(
    (
      await db.query("SELECT person_id FROM panel_members ORDER BY person_id")
    ).rows.map((p) => p.person_id),
    ["approver-1", "approver-2", "approver-4"],
  );
  assert.equal(
    (
      await db.query("SELECT status FROM exception_requests WHERE id=$1", [
        other,
      ])
    ).rows[0].status,
    "stale",
  );
});

test("idempotent retries return the same request; changed payloads conflict", async () => {
  const key = randomUUID();
  const a = await call(
    "registrar-1",
    "/api/exception-requests",
    "POST",
    proposal,
    { key },
  );
  const b = await call(
    "registrar-1",
    "/api/exception-requests",
    "POST",
    proposal,
    { key },
  );
  assert.equal(a.body.id, b.body.id);
  assert.equal(
    (
      await call(
        "registrar-1",
        "/api/exception-requests",
        "POST",
        { ...proposal, reason: "A different reason." },
        { key },
      )
    ).status,
    409,
  );
});

test("deactivation revokes app access immediately; revoked earlier approvals cannot execute", async () => {
  const id = await request();
  await call(
    "approver-1",
    `/api/exception-requests/${id}/approvals`,
    "POST",
    {},
  );
  await db.query("UPDATE people SET active=false WHERE id='approver-1'");
  assert.equal((await call("approver-1", "/api/me")).status, 403);
  assert.equal(
    (
      await call(
        "approver-2",
        `/api/exception-requests/${id}/approvals`,
        "POST",
        {},
      )
    ).status,
    409,
  );
});

test("queue jump and removal execute only after approval and preserve promotion order", async () => {
  const jump = await request("registrar-1", {
    ...proposal,
    kind: "jump",
    studentId: "s06",
  });
  await call(
    "approver-1",
    `/api/exception-requests/${jump}/approvals`,
    "POST",
    {},
  );
  assert.equal(
    (
      await call(
        "approver-2",
        `/api/exception-requests/${jump}/approvals`,
        "POST",
        {},
      )
    ).status,
    200,
  );
  const waiting = (
    await db.query(
      "SELECT person_id FROM memberships WHERE course_id='comp3100' AND status='waiting' ORDER BY sort_order",
    )
  ).rows;
  assert.equal(waiting[0].person_id, "s06");
  const remove = await request("registrar-1", {
    ...proposal,
    kind: "remove",
    studentId: "s01",
  });
  await call(
    "approver-1",
    `/api/exception-requests/${remove}/approvals`,
    "POST",
    {},
  );
  assert.equal(
    (
      await call(
        "approver-2",
        `/api/exception-requests/${remove}/approvals`,
        "POST",
        {},
      )
    ).status,
    200,
  );
  assert.equal(
    (
      await db.query(
        "SELECT status FROM memberships WHERE course_id='comp3100' AND person_id='s06'",
      )
    ).rows[0].status,
    "enrolled",
  );
  assert.equal(
    (
      await db.query(
        "SELECT * FROM memberships WHERE course_id='comp3100' AND person_id='s01'",
      )
    ).rows.length,
    0,
  );
});

test("a fresh API instance sees committed enrolment data", async () => {
  assert.equal(
    (await call("s17", "/api/courses/comp3100/enrolments", "POST", {})).status,
    200,
  );
  const adapter = {
    realm: "fairenrol",
    resource: "fairenrol-client",
    "auth-server-url": "http://localhost:8080",
    jwk: { keys: [publicKey] },
  };
  const second = createApp({ db, adapter, appOrigin: origin }).listen(
    0,
    "127.0.0.1",
  );
  await new Promise((resolve) => second.once("listening", resolve));
  try {
    const result = await fetch(
      `http://127.0.0.1:${second.address().port}/api/state`,
      { headers: await headers("s17", "/api/state") },
    ).then((r) => r.json());
    assert.equal(
      result.courses.find((c) => c.id === "comp3100").myStatus,
      "waiting",
    );
  } finally {
    await new Promise((resolve) => second.close(resolve));
  }
});
