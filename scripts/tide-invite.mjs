import "dotenv/config";
import { readFile } from "node:fs/promises";
const personId = process.argv[2];
if (!personId || !/^(s\d{2}|approver-[1-4]|registrar-1)$/.test(personId))
  throw new Error(
    "Usage: npm run tide:invite -- <s01..s20|approver-1..4|registrar-1>",
  );
const base = process.env.TIDECLOAK_URL;
const realm = process.env.TIDECLOAK_REALM;
const state = JSON.parse(await readFile(".local/tide-bootstrap.json", "utf8"));
if (!state.created || state.realm !== realm || state.base !== base)
  throw new Error("Run tide:setup for this development realm first.");
const auth = await fetch(
  `${base}/realms/master/protocol/openid-connect/token`,
  {
    method: "POST",
    body: new URLSearchParams({
      username: process.env.KC_BOOTSTRAP_ADMIN_USERNAME,
      password: process.env.KC_BOOTSTRAP_ADMIN_PASSWORD,
      client_id: "admin-cli",
      grant_type: "password",
    }),
  },
);
if (!auth.ok)
  throw new Error("Local realm administrator authentication failed.");
const { access_token } = await auth.json();
const headers = {
  Authorization: `Bearer ${access_token}`,
  "Content-Type": "application/json",
};
const usersResponse = await fetch(
  `${base}/admin/realms/${realm}/users?username=fairenrol-${personId}&exact=true`,
  { headers },
);
if (!usersResponse.ok)
  throw new Error(`User lookup failed (${usersResponse.status}).`);
const user = (await usersResponse.json())[0];
if (!user) throw new Error("This development identity does not exist.");
if (user.attributes?.tideUserKey?.[0])
  throw new Error(
    "This identity is already Tide-linked. Sign in with its existing Tide account.",
  );
const response = await fetch(
  `${base}/admin/realms/${realm}/tideAdminResources/get-required-action-link?userId=${user.id}&lifespan=43200`,
  {
    method: "POST",
    headers,
    body: JSON.stringify(["link-tide-account-action"]),
  },
);
if (!response.ok) throw new Error(`Invitation failed (${response.status}).`);
const raw = await response.text();
let link;
try {
  const value = JSON.parse(raw);
  link = typeof value === "string" ? value : value.link || value.url;
} catch {
  link = raw;
}
console.log(
  `Open this local development invitation for ${personId} (expires in 12 hours):\n${link}`,
);
console.log(
  "Each person must link their own Tide account. After initial governance setup, approve any pending identity changes in the Tide console.",
);
