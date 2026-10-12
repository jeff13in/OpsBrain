# OPU-91: private hosted preview and acceptance gate

Started 2026-10-11. Status: **in progress**. Scope and acceptance criteria:
[website sprint plan](website-sprint-plan.md#opu-91--private-hosted-preview-and-acceptance-gate).

## Delivered in this increment

- Frontend CI runs `npm test`, `npm run check` and `npm run build` with Node.js
  22 for applicable pushes and pull requests.
- The active `joint` collaboration branch is included in push and pull-request
  CI triggers. Existing image publication remains limited to `main` and
  `jeffin-dev`; deployment remains limited to `main`.
- The local test/build commands and allowlisted output remain unchanged.
- A private static preview is deployed at
  `https://opsbrain-private-preview.fluffyflea64.chatgpt.site`. The hosting
  project is recorded in `web/.openai/hosting.json`; the manifest contains no
  credential.
- Current host access is `custom` with the owner as the only allowed identity.
  External viewer invitations are supported. The static deployment has no
  production API upstream and therefore remains Demo-only.

## Verification

| Check | Result |
| --- | --- |
| `npm test` | 63 passed; no skipped or failed tests |
| `npm run check` | JavaScript syntax checks passed |
| `npm run build` | Ten allowlisted static assets produced |
| Private deployment | Succeeded; owner-only access confirmed after publish |
| Hosted desktop capture | Home rendered without visible clipping or layout failure |
| `git diff --check` | Passed |

The first sandboxed test run passed 60 tests and could not bind three temporary
loopback servers (`EPERM`). The permitted rerun passed all 63 tests. The suite
made no external network request.

An authenticated production request returned HTTP 200 but confirmed that the
static host does not apply a source `_headers` file. The ineffective file was
removed. A document CSP and referrer policy now protect the static page; HTTP
anti-framing, HSTS, MIME and permissions headers remain pending with the hosted
gateway/server deployment.

## Deployment and rollback

- Site project identity is tracked in `web/.openai/hosting.json`; access policy,
  source credentials and runtime secrets remain in the hosting control plane.
- Run `npm test`, `npm run check` and `npm run build` from `web/`, then publish
  the verified `dist/` output through the existing Sites project.
- Current production deployment: `appgdep_6acc0aa7d39c8191982078d40781cf55`;
  saved version: `appgprj_6acc032024148191bae5d79b101a30e4~appgver_f6c30104051c8191a80fbc7f18404b94`.
- Roll back by redeploying the previously accepted saved version from the Sites
  version history. Do not rebuild an old source revision and label it as the
  same saved version.

## Remaining before completion

- Add the second approved viewer identity and verify denied access for an
  unauthenticated and an unapproved identity.
- Configure the protected same-origin API upstream and run the real-backend
  success, partial failure, total failure, timeout and malformed-response paths.
- Deliver HTTP anti-framing, HSTS, MIME, referrer and permissions headers with
  the protected gateway/server, then repeat the production header check.
- Complete and record desktop/mobile, keyboard, reduced-motion, storage and
  screen-reader browser acceptance for every route.
- Assign the identity, gateway and rollback owners and rehearse one rollback.

The current working tree does not contain the approved viewer emails or a
reachable protected backend origin. Those values must be configured through the
hosting control plane, not committed to source.


## User-directed deferral — October 12, 2026

Hosted identity/access and protected API setup are preserved in OPU-105 at the
user's request. No host change or publication occurred. See the
[Rifat-only local review](week4-rifat.md) for current fixes/122-test evidence;
OPU-91 remains open for unverified browser/hosted acceptance.
