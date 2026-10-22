[![Built with TideCloak](https://tide.org/badges/built-with-tidecloak.svg)](https://tide.org/)

# FairEnrol

FairEnrol is a course registration app with FIFO waiting lists and independently reviewed exceptions. React/Vite renders the interface; an Express API verifies Tide identities and DPoP proofs; PostgreSQL stores enrolments, requests, votes and audit events.

**Live status (22 October 2026):** the linked registrar signs in with Tide and loads the protected course dashboard. Reload also succeeds after restoring normal Docker transport. The bootstrap default-role defect was repaired for this account with explicit owner authorization. One repair CR remains pending because the enclave approval window did not appear in the browser panel. The other 24 seeded accounts still need their default mappings repaired through governance and their own account linking. See [implementation status and evidence](docs/IMPLEMENTATION_STATUS.md).

## What works

- Real TideCloak provider, strict DPoP, canonical relay page and server-side verification using the adapter's embedded public keys.
- A linked identity maps to one application person. Roles require both verified Tide claims and an active application assignment. The working UI has no identity impersonation switcher.
- Persistent course enrolment, self-withdrawal, capacity changes and FIFO promotion.
- Exception proposals for forced enrolment, queue jumps, removal and panel replacement. Two distinct panel members must approve; a requester cannot review their own proposal.
- Database transactions prevent duplicate enrolments, oversubscribed ordinary admission, duplicate execution and concurrent panel/course changes invalidating approvals.
- Restricted reviewer details and a separate public explanation. Public responses contain no student roster or private evidence.
- Idempotent mutation retries and a shared PostgreSQL DPoP replay store.

Course exceptions are **server-enforced rules using Tide-authenticated identities**. Tide IGA governs identity and configuration changes. It does not automatically protect course database rows against an operator with database/server control. Custom cryptographic course-exception signing is a separate future feature.

## Local setup (Windows PowerShell)

Requirements: Node.js 22 or newer, Docker Desktop using Linux containers, network access to Tide's services, and a human Tide account for each demo identity being used. The Tide development image connects to Tide's live cryptographic network.

```powershell
npm.cmd ci
Copy-Item .env.example .env
```

Fill the gitignored `.env` with strong local `POSTGRES_PASSWORD` and `KC_BOOTSTRAP_ADMIN_PASSWORD` values; set `DATABASE_URL` using the same database password. Set the licence owner's `TIDE_LICENSE_EMAIL` and `TIDE_TERMS_ACCEPTED=yes` only after that person explicitly accepts [Tide's terms](https://tide.org/legal). Do not commit the file. This workspace has already been configured with the owner's supplied settings and randomly generated passwords.

```powershell
docker compose up -d
npm.cmd run tide:setup
```

The setup command preserves an existing unrelated realm. On a fresh local setup it imports Tide MCP's complete realm template, adds invite-only development identities with the realm default role and application roles, initializes the licence and embedded keys, enables Tide-mode IGA, exports the public adapter and maps identities into PostgreSQL. It checks default-role mappings before the first admin grant. Initial settings are recorded in the gitignored `.local/` directory so the command can resume. An already-governed realm with missing default mappings is rejected for manual governance repair; the script does not bypass approval. This applies to the 24 remaining seed mappings in this existing workspace; use the running configured app without rerunning bootstrap meanwhile.

The first run prints an invitation for `registrar-1`. Open it yourself and complete Tide account linking. Then run `npm.cmd run tide:setup` again: it signs the identity-provider settings and commits the initial `tide-realm-admin` grant **after** the account is linked. Later governed changes use the Tide console and the applicable human approval ceremony. Do not approve unfamiliar requests just to clear the queue.

```powershell
npm.cmd run dev
```

`dev` starts the FairEnrol API and both Vite frontends. Open [FairEnrol](http://localhost:5137/) and the [Careers workspace](http://localhost:5137/careers/), then sign in with the Tide account linked to the registrar. PostgreSQL is available on **54329**, and TideCloak stays on **8080**. Use `localhost:5137` consistently because the DPoP proof must match the configured `APP_ORIGIN`.

The initial registrar's display name is the fictional seeded profile **Taylor Reed**. The setup maps the owner's linked Tide identity to that development profile. Seeded names are demonstration data, not a university directory.

## Use separate demo identities

```powershell
npm.cmd run tide:invite -- s17
npm.cmd run tide:invite -- approver-1
npm.cmd run tide:invite -- approver-2
npm.cmd run tide:invite -- approver-3
```

Each command prints a local invitation valid for 12 hours; it does not email anyone. Each person must complete linking with their own Tide account. After the initial governance grant, review and approve pending identity-link changes in the [Tide console](http://localhost:8080/realms/fairenrol/tide-console/). Use separate browser profiles or log out between identities. Do not link one person's Tide account to multiple development people.

Development profiles: `s01`–`s20` are students; `registrar-1` is the registrar; `approver-1`–`approver-3` form the panel; `approver-4` is an eligible reserve. A panel request can select the reserve but cannot grant an ineligible registrar approval authority. Granting a new Tide role is a separate governed identity operation.

For an existing, verified subject needing an explicit application mapping:

```powershell
npm.cmd run users:link -- s17 VERIFIED_TIDE_SUBJECT
```

This local administrator command refuses conflicting bindings and does not grant Tide roles. Do not use a username/display name in place of the actual token subject.

## Demonstrate the complete journey

1. Sign in as `s17`, join a full course's waiting list, and refresh: the record persists.
2. Sign in as the registrar and propose an exception for a waiting student, with private reviewer details and a safe public summary.
3. Sign in as panel member 1 and approve. The enrolment remains unchanged.
4. Sign in as panel member 2 and approve. The request applies once and its explanation appears in the public list.
5. Verify the registrar cannot directly reorder a queue or impersonate a reviewer. The API enforces these restrictions independently of the UI.

A forced enrolment raises the course capacity if necessary; the proposal displays the resulting capacity before approval. Normal capacity increases promote existing waiting students in order. A decrease below current enrolment is rejected. Course/panel changes mark affected pending proposals stale so reviewers must evaluate a fresh proposal.

## Verification

```powershell
npm.cmd test
npm.cmd run build
npm.cmd run verify
```

`npm test` runs cryptographically signed API integration tests against isolated embedded PostgreSQL (PGlite). To verify the actual Docker PostgreSQL transaction behavior:

```powershell
$env:FAIRENROL_TEST_POSTGRES = '1'
npm.cmd test
Remove-Item Env:\FAIRENROL_TEST_POSTGRES
```

The PostgreSQL test mode creates and later drops only a randomly named `fairenrol_test_*` schema. It does not truncate application records. Test keys are generated in memory; there is no production test-login endpoint or authentication bypass.

`npm run verify` requires the running app and checks database/API health, the real realm/client relay URL, the served relay bytes and CSP hashes, rejection of an unknown realm, and unauthenticated API rejection.

Tide doctor can also be run in Git Bash:

```bash
bash node_modules/@tideorg/mcp/templates/shared/tide-doctor.sh --app . --check
```

Install `jq` for live `--url`/`--realm` checks so doctor can read the real adapter. Without it, this version can probe dummy issuer/client values and receive an expected 403. Keep issuer/client validation in place. The latest complete run returned 15 passes, zero failures and one pending-CR warning.

The earlier presentation checks used explicit identity/state fixtures. Separately, real Tide registrar login, authenticated API data and browser reload after a normal-container restart have now been verified. Real student/reviewer acceptance remains pending separate linking and governed mapping repairs. See `docs/IMPLEMENTATION_STATUS.md`.

## FairEnrol Careers and Capacitor

The candidate and hiring workflows are part of FairEnrol at [`/careers/`](http://localhost:5137/careers/). Tide remains the single human sign-in provider. FairEnrol verifies the Tide token, DPoP proof, replay state and active-person mapping before it sends a short-lived signed assertion to the private careers API or chat service.

The Android and iOS wrappers package both React apps and keep the existing backend separate. `npm.cmd run build:mobile` stages the Careers build under `dist/careers/`; `npm.cmd run cap:sync` copies it into the native projects. See the [Capacitor setup and Android/iOS test/build steps](docs/CAPACITOR.md). Windows can build and test Android; iOS builds require macOS and Xcode.

Useful checks:

```powershell
npm.cmd test
npm.cmd run build:all
npm.cmd run careers:test
npm --prefix careers/chat-service run test:ci
```

## Source map

| Path                            | Responsibility                                                                   |
| ------------------------------- | -------------------------------------------------------------------------------- |
| `src/main.jsx`                  | Load the public adapter and initialize the strict DPoP provider.                 |
| `src/App.jsx`                   | Role-aware dashboards, course commands and exception review.                     |
| `src/api/client.js`             | Absolute `secureFetch` requests and mutation idempotency keys.                   |
| `server/auth/tide.js`           | Local-key JWT verification and mandatory DPoP verification/replay checks.        |
| `server/services.js`            | Identity mapping, FIFO transactions, permissions, exception votes and execution. |
| `server/app.js`                 | Validated API routes, errors and optional built frontend hosting.                |
| `server/db.js`                  | PostgreSQL connection, idempotent schema creation and initial seed.              |
| `db/migrations/001_initial.sql` | Tables, uniqueness constraints and execution/replay records.                     |
| `shared/dpop-relay.js`          | Relay URL validation and headers in development and production.                  |
| `scripts/tide-setup.mjs`        | Resumable local realm bootstrap and initial account linking.                     |
| `tests/api.test.mjs`            | Authorization, proof, transaction and approval behavior.                         |

The mutation service deliberately locks a single database row, serializing this small application's writes across API processes. This favors correctness for the current scope; a larger deployment should split locks by resource while preserving panel/request consistency.

## Operations and limits

- Stop app processes with Ctrl+C and stop containers with `docker compose stop`. These preserve volumes. Removing volumes destroys course/realm data; no reset command does that automatically.
- The initial seed runs only when the course table is empty. Existing waiting students fill vacant seats during seeding, so the fixtures also obey FIFO.
- App deactivation (`people.active=false`) removes application access immediately. Tide-role changes may remain reflected in an already-issued token until expiry (the bootstrap uses a five-minute access-token lifetime). Keep application assignments synchronized with governed Tide changes.
- The public adapter contains verification/configuration information, never an admin password or client secret. Keep server credentials in `.env` or a secret manager.
- `npm run build` generates the frontend. For one-origin hosting, set `APP_ORIGIN` to the actual public HTTPS origin and run `npm start`; Express serves `dist` and `/api`. The current Docker Tide image, H2 database and loopback configuration are for local development. Production infrastructure, backups/restore drills, rate limiting and monitoring still need deployment-specific work.
- The code and configured local realm are not a completed multi-user acceptance run until separate students/reviewers finish linking and the journey is exercised with their real accounts.
