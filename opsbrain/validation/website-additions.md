# Website additions — OPU-106–109

Recorded 2026-10-12. User authorized adding the four proposed website features
to their respective week milestones and starting implementation. All four Linear
issues are assigned to Rifat in OpsBrain September Delivery Plan.

| Issue | Week | Result |
| --- | --- | --- |
| OPU-106 | 4 — Deploy + Ship | Readiness work package created, Backlog. Aggregate status endpoint/UI remain pending. |
| OPU-107 | 4 — Deploy + Ship | Live time-series work package created, Backlog. Preset gateway/normalization/charts remain pending. |
| OPU-108 | 5 — Authentication & Client Workspace | Export implemented locally, In Review. Actual browser download acceptance remains pending. |
| OPU-109 | 5 — Authentication & Client Workspace | First local increment implemented, In Progress. Authorized live passage resolver and isolation checks remain pending. |

## Implemented increment

- Demo and engineer Live chat offer a Markdown download after all turns finish.
  Empty, malformed, oversized-count and pending conversations cannot export.
- Reopened account investigations have their own download control, gated by the
  existing authorized workspace view and disabled during pending mutations.
- Reports preserve displayed questions/answers, sources, routing when present,
  agent outcomes/errors and latency when present. Synthetic and API provenance
  remain explicit, including partial/total failures. No hidden model context is
  serialized; generation/download make no network requests or storage writes.
- Content is enclosed in dynamically sized literal code fences so embedded
  Markdown, URLs and HTML cannot become active report markup. UTF-8 output is
  capped at 2 MiB. Download uses a fixed filename, removes its temporary anchor
  and revokes its object URL after 30 seconds.
- Citation selection opens inline native disclosure details and focuses the
  existing source target. The fixed example latency runbook provides an
  explicitly synthetic passage and fixture revision. Other sources show an
  unavailable state. Live labels never resolve arbitrary paths/URLs or display
  invented excerpts. Native disclosure controls provide keyboard open/close;
  real-browser focus/screen-reader acceptance is still pending.
- Web README and website sprint plan now document the increment, actual ticket
  IDs, queue and remaining gates. The old history proposal is marked superseded
  by OPU-97/99 so it does not create duplicate persistence work or replace the
  implemented account retention policy.

## Verification

From `opsbrain/web`:

| Check | Result |
| --- | --- |
| `npm test` | 131 passed, 0 failed; includes loopback gateway integration and nine new report/source tests. |
| `npm run check` | Passed, including both new public modules. |
| `npm run build` | Passed; 16 explicitly allowlisted public assets. |
| `../scripts/check-public-secrets.py dist` with audit virtualenv Python | 0 findings. |
| `git diff --check` | Passed. |

New tests cover partial/error reports, routing/latency, hidden-field exclusion,
Unicode and multiline content, embedded fences/hostile markup, byte limits,
object URL lifecycle, disabled controls, authorized account rendering and
citation focus/open behavior. Hostile source labels cannot resolve passages.
Controller and DOM-stub tests do not constitute visual/browser acceptance.

## Remaining work and ownership

OPU-106/107 are queued after this first report/source increment. Real backend
prerequisites remain OPU-100–103. Hosted setup/access/API acceptance stays
deferred under OPU-105; this change did not configure, publish or invite anyone.
OPU-109 requires an authorized live source contract with bounded retrieved
passages and verified workspace isolation before enabling client live access.
OPU-108 remains In Review until an actual browser verifies the download and
Unicode report contents. No claim of live acceptance or production readiness
is made by these local checks.

No Jeffin tickets, root READMEs, Terraform, deployment manifests or CI files were
modified. Existing milestone dates and completed earlier sprint work remain.
