# FairEnrol implementation status

Updated 22 October 2026. These are observed local-development results, not a production-readiness claim.

## Implemented

- React dashboards backed by an Express API and persistent PostgreSQL records.
- Tide JWT verification with the exported embedded key, strict issuer/client checks, mandatory ES256 DPoP and atomic shared replay detection.
- Verified subject-to-person mapping, active-account checks, intersected Tide/application roles and server-enforced ownership.
- Transactional enrolment, withdrawal, FIFO promotion and capacity changes.
- Independent two-of-three exception approval, no self-approval, duplicate-vote prevention, denial, stale-request handling and one-time execution.
- Queue jumps, removals and panel replacement through approved exceptions; forced enrolment includes the proposed resulting capacity.
- Restricted reviewer details, redacted public explanations, persistent audits and mutation idempotency.
- Local Docker services with persistent volumes, gitignored secrets, resumable bootstrap and human account-linking scripts.
- Bootstrap now imports the realm default role with application roles, checks the mappings before initial governance finalization and refuses to bypass approval on an already-governed inconsistent realm.

## Local infrastructure

| Item                   | Observed state                                                                                    |
| ---------------------- | ------------------------------------------------------------------------------------------------- |
| Frontend               | `http://localhost:5137`                                                                           |
| API                    | `127.0.0.1:3001`, database health passes                                                          |
| PostgreSQL             | Docker PostgreSQL 17, persistent named volume, loopback port 54329                                |
| TideCloak              | Local Docker, observed version 0.14.41                                                            |
| SDK                    | `@tidecloak/js` 0.14.41, React wrapper 0.14.33                                                    |
| Realm/client           | `fairenrol` / `fairenrol-client`                                                                  |
| Licence and owner link | Completed using the owner's explicit terms acceptance and manual Tide account linking             |
| Governance             | IGA enabled in Tide mode, initial admin grant committed; one later repair CR remains PENDING      |
| Public adapter         | Embedded Ed25519 verification key and signed app-origin entry exported                            |
| Temporary diagnostics  | Observer container removed; running TideCloak has no diagnostic proxy/trust environment overrides |
| Secrets                | `.env`, `.local/` and the local public adapter are ignored by Git                                 |

The fictional development profile **Taylor Reed** is mapped to the owner's linked Tide identity. Other seeded names are demonstration data.

## Verification evidence

| Check                             | Result                                                                                                                                                          |
| --------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| API integration suite with PGlite | **15 passed**, latest run after the repair; generated cryptographic keys, no login bypass                                                                       |
| Same suite with Docker PostgreSQL | **15 passed** in the earlier implementation check, using an isolated disposable schema                                                                          |
| Frontend production build         | Passed after the repair                                                                                                                                         |
| `npm run verify`                  | Passed after restoring normal Docker transport: health, real relay URL, canonical bytes, CSP, unknown issuer/client rejection and unauthenticated API rejection |
| Tide doctor                       | Latest: **15 PASS, 1 WARN, 0 FAIL**; warning is the pending repair CR. Earlier pre-CR check had 16 passes                                                       |
| Attestation integrity             | **97/97 FairEnrol + 92/92 console signatures valid** before deploying the one-row repair                                                                        |
| Real registrar login              | **Passed**: Tide token accepted by protected API; course dashboard shows the linked registrar and live course data                                              |
| Restart/reload                    | **Passed** after normal TideCloak recreation and observer removal; browser reload returns the authenticated dashboard                                           |
| Presentation checks               | Desktop/mobile login and three role dashboards checked earlier using explicitly mocked UI fixtures                                                              |
| Full real multi-user journey      | **Not completed**: remaining mappings need governed repair, then separate student/reviewer linking and acceptance                                               |

The API suite covers forged/expired/wrong-client tokens, proof tampering/replay, ownership/role bypass, last-seat concurrency, FIFO, two distinct votes, concurrent final approvals, self-approval, denial, stale authority, panel replacement, idempotency and deactivation.

![Real registrar dashboard after normal-container restart](images/fairenrol-tide-login-success.png)

## Resolved login defect

The original bootstrap imported each seed user's application roles but omitted `default-roles-fairenrol`. Explicit Keycloak import did not add it implicitly. ORK derived the signed realm default composite, including `account`, while Keycloak's token audience omitted it:

```text
TIDE-ORK-ATTESTATION-INVALID
claim 'aud' does not match attested value
 token: [fairenrol-client, realm-management]
 attested: [account, fairenrol-client, realm-management]
```

This was a bootstrap/data mismatch. TideCloak's signing error appeared as `Network request failed` in the browser. Existing attestation signatures were valid; signature validity alone did not establish claim consistency.

After explicit user authorization, exactly one existing default-role mapping was restored offline for the linked registrar. The procedure took a fresh H2 backup and verified all 189 signatures before applying the staged file. It preserved the realm, link, IGA and DPoP. Actual login and protected API access then succeeded. The temporary observer recorded successful ORK signing, and normal transport was restored before the final reload check. See [the repair record](TIDECLOAK_DEFAULT_ROLE_REPAIR.md) and [Vietnamese diagnosis](TIDECLOAK_LOGIN_DIAGNOSIS.md).

## Pending governance and acceptance

Repair CR `1623e3b2-14c0-4d0b-9aec-29a0f425d1e7` remains **PENDING, 0/1**, with exactly the reviewed default-role/user row. The local projection is repaired, but no governance approval has been fabricated. Both built-in consoles and a temporary same-origin SDK panel were attempted. The standard `/approve` API returned `needs-approval`; the enclave window did not appear in the in-app browser and no signed model was returned. The precise popup/handshake cause remains unconfirmed. The temporary panel is ignored local diagnostic material and is not part of the production build.

The other **24** seed accounts still lack this default mapping and were not modified offline. Repair them through the normal Tide governance ceremony when it is available, then invite separate humans for student/reviewer acceptance. Do not repeat the registrar's authorized offline exception for those accounts or rerun bootstrap expecting it to bypass this condition.

Remaining operations work: explicit logout/fresh-login acceptance, a complete real-user queue/approval demonstration, backup/restore drill, and deployment-specific TLS, monitoring and rate limiting. Course exceptions currently rely on tested server rules; independent cryptographic signing of course payloads is a separate feature.

The local app and normal Docker services remain running. No commit, push, public deployment or message to the Tide team was performed.
