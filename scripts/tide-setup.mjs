import "dotenv/config";
import { readFile, writeFile, mkdir } from "node:fs/promises";
import { randomUUID } from "node:crypto";
import {
  postgresDatabase,
  initializeDatabase,
  linkIdentity,
} from "../server/db.js";

const base = (process.env.TIDECLOAK_URL || "http://localhost:8080").replace(
  /\/+$/,
  "",
);
const realm = process.env.TIDECLOAK_REALM || "fairenrol";
const client = process.env.TIDECLOAK_CLIENT || "fairenrol-client";
const appUrl = process.env.APP_ORIGIN || "http://localhost:5137";
const email = process.env.TIDE_LICENSE_EMAIL;
if (
  process.env.TIDE_TERMS_ACCEPTED !== "yes" ||
  !email ||
  !/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email)
) {
  throw new Error(
    "The licence owner must supply TIDE_LICENSE_EMAIL and explicitly set TIDE_TERMS_ACCEPTED=yes after accepting https://tide.org/legal.",
  );
}
if (!process.env.KC_BOOTSTRAP_ADMIN_PASSWORD)
  throw new Error(
    "Set KC_BOOTSTRAP_ADMIN_PASSWORD in the gitignored .env file.",
  );
const db = postgresDatabase(process.env.DATABASE_URL);
await mkdir(".local", { recursive: true });
const statePath = ".local/tide-bootstrap.json";
let state = await readFile(statePath, "utf8")
  .then(JSON.parse)
  .catch((error) => {
    if (error.code !== "ENOENT") throw error;
    return null;
  });
if (state && (state.realm !== realm || state.base !== base))
  throw new Error(
    "The saved bootstrap belongs to a different realm. Use a separate workspace; do not overwrite a live realm.",
  );
const save = () => writeFile(statePath, JSON.stringify(state, null, 2) + "\n");
let cachedToken,
  tokenExpires = 0;
async function token() {
  if (Date.now() < tokenExpires) return cachedToken;
  const response = await fetch(
    `${base}/realms/master/protocol/openid-connect/token`,
    {
      method: "POST",
      body: new URLSearchParams({
        username: process.env.KC_BOOTSTRAP_ADMIN_USERNAME || "admin",
        password: process.env.KC_BOOTSTRAP_ADMIN_PASSWORD,
        grant_type: "password",
        client_id: "admin-cli",
      }),
      signal: AbortSignal.timeout(20000),
    },
  );
  if (!response.ok)
    throw new Error(`Master-admin authentication failed (${response.status}).`);
  const data = await response.json();
  cachedToken = data.access_token;
  tokenExpires = Date.now() + Math.max(0, data.expires_in - 10) * 1000;
  return cachedToken;
}
async function admin(
  path,
  { method = "GET", body, allow404 = false } = {},
  retry = true,
) {
  const response = await fetch(`${base}/admin/${path}`, {
    method,
    headers: {
      Authorization: `Bearer ${await token()}`,
      ...(body instanceof URLSearchParams
        ? {}
        : body === undefined
          ? {}
          : { "Content-Type": "application/json" }),
    },
    ...(body === undefined
      ? {}
      : {
          body: body instanceof URLSearchParams ? body : JSON.stringify(body),
        }),
    signal: AbortSignal.timeout(180000),
  });
  if (response.status === 401 && retry) {
    tokenExpires = 0;
    return admin(path, { method, body, allow404 }, false);
  }
  if (allow404 && response.status === 404) return null;
  const text = await response.text();
  if (!response.ok)
    throw new Error(
      `Tide ${method} ${path} failed (${response.status}): ${text.slice(0, 400)}`,
    );
  if (!text) return null;
  try {
    return JSON.parse(text);
  } catch {
    return text;
  }
}
async function drainBootstrap() {
  for (let pass = 0; pass < 10; pass++) {
    const pending = await admin(
      `realms/${realm}/iga/change-requests?status=PENDING`,
    );
    if (!Array.isArray(pending))
      throw new Error("Unexpected IGA change-request response.");
    if (!pending.length) return;
    if (
      pending.some((cr) =>
        ["DISABLE_IGA", "DELETE_REALM", "OFFBOARD_REALM"].includes(
          cr.actionType,
        ),
      )
    )
      throw new Error(
        "Destructive governance request found. Review it in the Tide console; bootstrap will not approve it.",
      );
    let advanced = false;
    for (const cr of pending) {
      try {
        const result = await admin(
          `realms/${realm}/iga/change-requests/${cr.id}/approve`,
          { method: "POST", body: {} },
        );
        if (result?.mode === "needs-approval")
          throw new Error(
            "This realm requires human multi-admin signing. Review the pending changes in the Tide console.",
          );
        advanced ||= !!result?.committed;
      } catch (error) {
        if (
          !error.message.includes("(412)") &&
          !error.message.includes("(409)")
        )
          throw error;
      }
    }
    if (!advanced) {
      const remaining = await admin(
        `realms/${realm}/iga/change-requests?status=PENDING`,
      );
      for (const cr of remaining.filter((cr) => cr.readyToCommit)) {
        await admin(`realms/${realm}/iga/change-requests/${cr.id}/commit`, {
          method: "POST",
        });
        advanced = true;
      }
      if (!advanced)
        throw new Error(
          "Bootstrap changes require governance review; nothing was silently skipped.",
        );
    }
  }
  throw new Error(
    "IGA changes remain after ten dependency passes. Review the Tide console.",
  );
}

try {
  await initializeDatabase(db);
  console.log("Waiting for local TideCloak…");
  for (let tries = 0; ; tries++) {
    try {
      await token();
      break;
    } catch (error) {
      if (tries >= 45) throw error;
      await new Promise((resolve) => setTimeout(resolve, 2000));
    }
  }
  const existing = await admin(`realms/${realm}`, { allow404: true });
  if (existing && !state?.created)
    throw new Error(
      `Realm ${realm} already exists outside this bootstrap. It has been preserved. Use an exported adapter or choose a new realm name.`,
    );
  if (!existing) {
    state = {
      base,
      realm,
      client,
      created: false,
      licensed: false,
      iga: false,
      signed: false,
      governanceGranted: false,
    };
    const templateText = await readFile(
      "node_modules/@tideorg/mcp/templates/shared/realm.json.template",
      "utf8",
    );
    const template = JSON.parse(
      templateText
        .replaceAll("REALM_NAME", realm)
        .replaceAll("CLIENT_NAME", client)
        .replaceAll("CLIENT_APP_URL", appUrl),
    );
    template.accessTokenLifespan = 300;
    for (const name of ["student", "registrar", "approver"])
      template.roles.realm.push({ name });
    const people = (await db.query("SELECT * FROM people ORDER BY id")).rows;
    template.users = people.map((person) => ({
      id: randomUUID(),
      username: `fairenrol-${person.id}`,
      enabled: true,
      firstName: person.name.split(" ")[0],
      lastName: person.name.split(" ").slice(1).join(" ") || "User",
      ...(person.id === "registrar-1" ? { email } : {}),
      attributes: { tideInvitable: ["true"] },
      // Importing explicit roles does not add Keycloak's default composite.
      // Tide attests it as universal, so omitting the local edge makes token
      // roles/audiences disagree with the ORK's attested derivation.
      realmRoles: [...new Set([template.defaultRole.name, ...person.roles])],
    }));
    console.log(
      `Creating ${realm} from the canonical Tide realm template with invite-only development identities…`,
    );
    await admin("realms", { method: "POST", body: template });
    state.created = true;
    await save();
  }
  if (!state.licensed) {
    console.log(
      "Initializing the user-authorized Tide licence and realm keys…",
    );
    const result = await admin(
      `realms/${realm}/vendorResources/setUpTideRealm`,
      {
        method: "POST",
        body: new URLSearchParams({ email, isRagnarokEnabled: "true" }),
      },
    );
    if (/NEED_PAYMENT/i.test(JSON.stringify(result)))
      throw new Error(
        "Tide requested a paid licence; no payment was authorized.",
      );
    state.licensed = true;
    await save();
  }
  if (!state.iga) {
    const representation = await admin(`realms/${realm}`);
    representation.attributes = {
      ...representation.attributes,
      "iga.attestor": "tide",
    };
    await admin(`realms/${realm}`, { method: "PUT", body: representation });
    await admin(`realms/${realm}/tide-admin/toggle-iga`, {
      method: "POST",
      body: new URLSearchParams({ isIGAEnabled: "true" }),
    });
    state.iga = true;
    await save();
  }
  if (!state.governanceGranted) await drainBootstrap();
  const realmModel = await admin(`realms/${realm}`);
  const defaultRole = realmModel.defaultRole;
  if (!defaultRole?.id)
    throw new Error(
      "The realm has no default role; refusing to finish bootstrap.",
    );
  const bootstrapUsers = await admin(`realms/${realm}/users?max=100`);
  const missingDefaults = [];
  for (const user of bootstrapUsers) {
    const roles = await admin(
      `realms/${realm}/users/${user.id}/role-mappings/realm`,
    );
    if (!roles.some((role) => role.id === defaultRole.id))
      missingDefaults.push(user);
  }
  if (missingDefaults.length && state.governanceGranted)
    throw new Error(
      `${missingDefaults.length} existing user(s) lack the realm default-role mapping. ` +
        "Tide universally attests this role, so their token claims can disagree with ORKs. " +
        "The realm is already governed: use its approved repair workflow; bootstrap will not bypass it.",
    );
  for (const user of missingDefaults)
    await admin(`realms/${realm}/users/${user.id}/role-mappings/realm`, {
      method: "POST",
      body: [defaultRole],
    });
  if (missingDefaults.length) await drainBootstrap();
  for (const user of missingDefaults) {
    const roles = await admin(
      `realms/${realm}/users/${user.id}/role-mappings/realm`,
    );
    if (!roles.some((role) => role.id === defaultRole.id))
      throw new Error(
        "Default-role mapping did not commit; refusing the governance transition.",
      );
  }
  const clients = await admin(
    `realms/${realm}/clients?clientId=${encodeURIComponent(client)}`,
  );
  if (!clients[0]?.id)
    throw new Error("The FairEnrol client is not active after bootstrap.");
  const adapter = await admin(
    `realms/${realm}/vendorResources/get-installations-provider?clientId=${clients[0].id}&providerId=keycloak-oidc-keycloak-json`,
  );
  if (
    !adapter?.jwk?.keys?.length ||
    !adapter.vendorId ||
    !adapter.homeOrkUrl ||
    adapter.credentials?.secret
  )
    throw new Error(
      "Tide did not return a complete public adapter; refusing to save it.",
    );
  await writeFile(
    "public/tidecloak.json",
    JSON.stringify(adapter, null, 2) + "\n",
  );
  const remoteUsers = await admin(`realms/${realm}/users?max=100`);
  const people = (await db.query("SELECT id FROM people")).rows;
  for (const person of people) {
    const user = remoteUsers.find(
      (u) => u.username === `fairenrol-${person.id}`,
    );
    if (user)
      await linkIdentity(db, {
        issuer: `${base}/realms/${realm}`,
        subject: user.id,
        personId: person.id,
      });
  }
  const owner = remoteUsers.find((u) => u.username === "fairenrol-registrar-1");
  if (!owner) throw new Error("Registrar identity was not found.");
  const linked = owner.attributes?.tideUserKey?.[0];
  if (linked && !state.governanceGranted) {
    await drainBootstrap();
    const idp = await admin(`realms/${realm}/identity-provider/instances/tide`);
    idp.config.CustomAdminUIDomain = `${base}/realms/${realm}/tide-console/`;
    await admin(`realms/${realm}/identity-provider/instances/tide`, {
      method: "PUT",
      body: idp,
    });
    await admin(`realms/${realm}/vendorResources/sign-idp-settings`, {
      method: "POST",
    });
    state.signed = true;
    await save();
    const management = (
      await admin(`realms/${realm}/clients?clientId=realm-management`)
    )[0];
    const role = await admin(
      `realms/${realm}/clients/${management.id}/roles/tide-realm-admin`,
    );
    await admin(
      `realms/${realm}/users/${owner.id}/role-mappings/clients/${management.id}`,
      { method: "POST", body: [role] },
    );
    await drainBootstrap();
    state.governanceGranted = true;
    await save();
    console.log(
      "The registrar is linked and the initial realm governance role is committed.",
    );
  }
  if (!linked) {
    const invitation = await admin(
      `realms/${realm}/tideAdminResources/get-required-action-link?userId=${owner.id}&lifespan=43200`,
      { method: "POST", body: ["link-tide-account-action"] },
    );
    state.ownerInvite =
      typeof invitation === "string"
        ? invitation
        : invitation.link || invitation.url;
    await save();
    console.log(
      "ACTION REQUIRED: Open the registrar invitation to link your Tide account:",
    );
    console.log(state.ownerInvite || JSON.stringify(invitation));
    console.log(
      "Then run npm run tide:setup again to finish signing and initial realm governance.",
    );
  }
  console.log(
    "Public adapter exported. Application identities are mapped; no simulated authentication was enabled.",
  );
} finally {
  await db.close();
}
