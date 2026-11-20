# M05B2A public acquisition association: proposed owner decision

Revision 1, 20 November 2026. Planning only; not implementation approval.
Trusted core base: main0b0b907162a9ca6499bd620b6ef55ad265fafe0e.
M05A product: ca6825fb0cdcaa8aa1c4fa176965720757c195ef. M05B1 CPU results are
reviewed separately and do not authorize this feature or private external code.

## Problem and end state

An operation receipt currently identifies a command; an image identifies an
acquired source/cut. No authoritative public link connects them. Physical
completion may precede numerical delivery. The adapter must refuse synchronous
acquisition until it can associate a result without guessing the newest image.

Add one authenticated, versioned, read-only instrument API projection:
`GET /operation/<id>/acquisitions`. Use causal facts already verified by the
trusted service and immutable image publication records. No engine/numerical,
exposure, dose, timing, Stop or GUI control change. No external dependency.
An association reports an observed relation; it does not itself complete a
command, expose a sample or establish a successful image outcome.

## Exact behavior to implement if approved

- Instrument API transport only, with its existing exact numeric Host, bearer,
  no-Cookie/no-Origin and strict path rules. The GUI BFF does not gain this route.
  No credential or principal-policy change. Record operation ownership internally;
  querying a GUI-owned operation through this new route returns404. Existing
  operation/image/state routes and their projections remain unchanged.
- New response protocol `vsem.operation-acquisitions.v1`, closed explicit keys:
  protocol, operation_id, command, receipt, association, latest_cut, final_cut.
  Receipt is a coherent copy of the existing four-key public receipt. Command is
  the original public action or `lease`. Association is null until verified, then
  has exactly relation, source_id, raster_id and applied_at_ns. Relation is one
  of `started_single`, `live_session`, `configuration_applied`, `already_active`,
  `freeze_of`. Times are nonnegative integer observed episode nanoseconds.
  Cut references contain only image_id, source_id,
  raster_id, cut_elapsed_ns and outcome. Full raw bytes/coverage/timing/segments
  remain available through the existing image endpoint. No generic serialization.
- Single scan: verified RASTER_START binds its actual command ID to actual raster
  and public source. Returned cuts must match that exact causal identity. A new
  RECEIVED/accepted command cannot claim a source before start or reuse an older
  image. Rejected/unstarted/cancelled-before-start operations have null association.
- Live scan: associate the actual live source and current verified raster. A
  numerically delayed latest_cut may refer to an earlier raster of that same live
  source; its explicit raster identity must remain visible. Never present it as
  the current sweep. Do not retain or return an unbounded list of live frames.
- Configure-live: associate the first verified raster on which the requested
  geometry/dwell applies. If already active, label relation `already_active` and
  retain the observed application time; this is not a new exposure. Superseded or
  cancelled-before-application requests remain unassociated. Later requests must
  not rewrite an earlier command's observed association.
- Freeze: associate the verified existing live source/final raster using the
  actual SESSION_ENDED freeze operation ID, including the same-tick ordering case.
  Relation is `freeze_of`; it creates no new acquisition source. Cancellation and
  interrupted outcomes stay explicit. No success inference from receipt alone.
- Non-acquisition operations return their ordinary receipt and null association/
  cut references. Unknown, removed or unavailable IDs never fall back to latest
  image. Unknown/removed IDs return404. Service failure remains explicit503.
- Store constant-size association/latest/final references per retained operation.
  Retention lifetime follows existing operation/image availability; this adds no
  durable-history or eviction policy. A missing referenced image cannot be replaced
  by another source. For single/configure, final_cut means the terminal cut of the
  associated raster. For live/freeze, it means the terminal cut of the session's
  verified final raster, never an earlier completed sweep. It stays null until
  that cut is actually published, even after a COMPLETED receipt. Cancelled
  terminal cuts retain their true outcome; they are not successful acquisitions.
  Provenance indexing may add constant-size fields to already retained image
  records; it must not introduce a second unbounded live-history collection.

## Source and allowed change surface

Maintainer-owned implementation only: `runtime/hierarchical_human_service.py`,
API-only routing in `runtime/core_human_http.py`, one new explicit association
bookkeeper/projection module under runtime, new independent acceptance files,
and API/validation/status/roadmap documentation. Existing authentication predicates,
original tests/workflows, engine/numerical files, existing public schemas and
live-receipt completion semantics remain unchanged. Legacy profiles without the
projection explicitly return404, with no synthetic substitute. Review the exact
diff against the main base before integration. Stop for an expanded source or
scientific/security requirement rather than silently widening this specification.

Physics/security/timing, independent tests and integration stay frontier-owned.
Only a separately frozen pure data-helper task could be delegated after approval;
it may not own provenance decisions, routing, tests or source integration.

## Gates

1. Reproduce the current missing association and prove a client cannot select a
   correct image merely from latest_image or guessed counters.
2. Independent fact-sequence tests: single/live/configure/freeze, no-change,
   same-tick ordering, supersession, cancellation/Stop, lease loss, terminal fault,
   duplicate/late facts and delayed/out-of-order numerical publication. No wrong
   source/raster/cut pairing; no reclassification of failed outcomes as success.
3. Actual HTTP authorization/path tests: wrong/missing/duplicate bearer, Cookie,
   Origin, wrong Host, GUI token/port, GUI-owned IDs, malformed/query/extra paths,
   unknown/removed identities and service unavailability. Closed-key leak checks
   exclude private metadata, paths, seeds, specimen coefficients and evaluator data.
4. Original CPU, display and publication checks remain passing. Tests verify GET
   is side-effect-free and image reads do not block Stop/lease or drive physics.
5. Existing approved core environment only: actual compute-GPU/public-HTTP tests
   for native1024, partial/final association, live/configure/freeze, within-raster
   parameter segments, cancellation and delayed delivery; applicable original
   scientific/transport gates stay intact. Verify GPU identity/ownership afresh,
   preserve the display GPU and close all owned fixtures/processes on every path.
   No human-review server remains. No fibsemOS payload runs on the private host.
6. Full diff/provenance audit and successful expected GitHub Actions acceptance
   on exact proposed head/integration; verify merged main and post-merge CI if
   the owner chooses the merge-inclusive option below. No release tag.

## Limits, risks and choices

The principal risk is false image attribution during concurrent live changes or
delayed publication. Immutable identity joins and independent failure tests are
mandatory. This additive API is not crash durability or hostile-agent confinement.
Rollback is a reviewed revert of this feature; prior image/scientific records and
existing endpoints are preserved. Do not delete history or experimental work.

1. Recommended: approve this exact M05B2A core feature, its CPU/GPU qualification,
   reviewed PR and main merge only after all gates pass. It introduces no external
   code/artifact or dependency. It does not enable the adapter's image return,
   authorize private fibsemOS execution or the later cross-stack experiment, merge
   PR12, change permissions/policy or publish a release.
2. Approve implementation, qualification and a draft PR only; return for a separate
   integration decision. Same behavior and gates, with no main merge.
3. Defer the feature. Preserve the optional draft and qualified CPU evidence;
   synchronous vSEM acquisition remains explicitly unavailable.

The subsequent M05B2B decision must separately specify the adapter's honest
raw-count/view binding and the isolated genuine Demo/vSEM GPU/HTTP experiment.
The dependency/native/base risks accepted only for M05B1 do not become deployment
clearance. This plan is a prerequisite, not a claim that issue10 is complete.
