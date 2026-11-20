# M05B2B0: optional adapter image return and public CPU qualification

Revision 1, 20 November 2026. Proposal only; no implementation approval.
Tracks [issue #10](https://github.com/BenjaminZingsem/vSEM/issues/10).

## Source and prerequisite

The independent core association prerequisite is merged in
[PR #13](https://github.com/BenjaminZingsem/vSEM/pull/13), main
`2e18bdafadab22c56a64cc16cc344bcd5a0bb0c1`, with passing CPU/GPU/HTTP and
[post-merge CI](https://github.com/BenjaminZingsem/vSEM/actions/runs/44750777826).
Its [public contract](https://github.com/BenjaminZingsem/vSEM/blob/2e18bdafadab22c56a64cc16cc344bcd5a0bb0c1/docs/API.md#command-to-image-association)
now makes exact command/image attribution possible. The optional adapter still
refuses acquisition and remains unmerged in draft
[PR #12](https://github.com/BenjaminZingsem/vSEM/pull/12).

Proposed adapter/harness base: qualified
`f4c6922678f8c993bd8b7e7d385432c7b1b3b740`, executable bytes identical to the
reviewed M05B1 implementation `db937154bcd30997c2897650a319a09fdbedde78`.
The [CPU result](FIBSEMOS_M05B1_CPU_RESULT.md) is evidence, not permission for
private execution or deployment. Existing upstream source, 52-wheel manifest,
OCI base and all source/artifact hashes remain exactly frozen. No new dependency,
external patch, version, binary, model, dataset or optional extra is proposed.

## Result to implement if approved

An explicitly configured caller can use the unchanged pinned upstream
`fibsem.acquire.acquire_image`/Imaging/Beam workflow to obtain an SE image from
the optional vSEM driver. The image is an honestly labelled uint16 compatibility
view; its lossless uint32 counts and complete observable metadata remain separately
available. This stage qualifies that behavior against authored public CPU HTTP
fixtures, not against a real vSEM GPU runtime. It does not finish issue #10.

1. Add strict closed parsing for `vsem.operation-acquisitions.v1`, matching the
   known operation ID, public action, receipt, association and exact terminal cut.
   Probe the endpoint using the existing known lease operation before submitting
   an exposing command. A legacy/missing/malformed projection refuses before
   exposure; never guess the newest image or predict counters.
2. Validate the whole supported single-image request and an explicit fixed count
   window before admission. Preserve the present default refusal when no image
   policy is configured. Provide a single-use configuration method accepting
   integer `black` and `white`, `0 <= black < white <= 2**32-1`; output is uint16.
   No auto-window, new physical control or absolute working-distance mapping.
3. Submit exactly once, retain the returned operation ID and wait independently
   for physical `COMPLETED` and its published terminal cut with outcome
   `COMPLETED`. Missing references remain pending/unavailable, never old-frame
   substitutions. Check source/image/raster identity, dimensions, dwell, field,
   offsets, full completed coverage and all response types before returning.
   Preserve acquisition-time parameter segments and blank holds; an intervening
   optics or stage change is not a reason to relabel the whole image.
4. A GET failure after a known operation raises an explicit pending-outcome result
   carrying that ID. Provide explicit reconciliation of the same known operation;
   it may read/wait, never issue another exposure. Unknown POST admission remains
   halted without retry. Rejected/cancelled/unknown receipts, cancelled cuts,
   renewal loss, interlock, absent/mismatched records and protocol failures remain
   explicit errors. No automatic Stop or interlock clearing on a timeout.
5. Keep lease renewal and generation-confirmed Stop responsive on independent
   connections, outside image-wait locks. Preserve the existing writer ownership,
   connection, units/bounds, unsupported capability and no-replay contracts.
6. Retain an immutable acquisition result with the exact association, RawFrame
   bytes/metadata and fixed-window provenance. Use the existing integer
   round-half-up window transform, without autoscaling, orientation changes or
   filters on raw counts or the returned `.data`. Preserve RawFrame save/load
   bytes and metadata exactly. Its format does not acquire durability claims.
7. Return a real upstream FibsemImage-compatible object, with explicit vSEM
   accessors for raw data, association and view provenance. Pixel pitch comes
   from acquired metadata; requested settings remain labelled intent. Do not
   fabricate unavailable microscope fields, absolute WD, hardware geometry or
   UTC exposure timestamps. Upstream's pre-driver wall-clock acquisition stamp
   is not the engine's episode exposure time; retain that distinction.
8. Inert inspection shows FibsemImage's constructor creates a separate
   `filtered_data` display array. Preserve the genuine constructor and document
   that auxiliary derivative; prove `.data` still equals the declared fixed
   view and raw counts remain unchanged. Do not patch upstream filtering/dtype
   checks or pass a fake image class as compatibility proof.
9. Automatic image saving stays refused by whole-request preflight. Until a
   reviewed companion-aware view format exists, explicitly refuse the returned
   compatibility object's generic TIFF save before any filesystem write. RawFrame
   save/load remains available. Do not emit an unlabelled view-only file that
   loses its required raw companion or claims lossless counts. This limit must
   be visible in docs/capabilities and genuine tests, not a successful no-op.

Generic upstream live streaming, autofocus, arbitrary ROI conversion, FIB,
vendor SDKs and undeclared settings remain unavailable. Existing explicit
submit/configure/freeze helpers retain their semantics; no core GUI/API, physics,
timing, dose, Stop, schemas, credentials or permissions change.

## Allowed implementation and execution

Maintainer-owned changes only to optional adapter client/protocol/records/
bindings and a narrowly named image-result module, new independent acceptance,
the authored qualification fixtures/cases, branch-specific CPU workflow admission
and relevant optional-adapter/proposal/status documentation. Original tests,
core dependencies, engine/runtime, policy, source/artifact manifests and baseline
CI remain protected. Preserve all existing default-refusal tests; add explicit
configured success cases. Do not change C1-C8 to reinterpret an old failure as pass.

Local execution is limited to independently authored stdlib/core contract tests
and inert source/artifact inspection. Genuine external imports/builds/tests run
only in the already specified disposable public CPU envelope: exact source/tree,
52 wheels and pinned OCI identities; nonroot; read-only inputs; dropped capabilities;
no-new-privileges/seccomp; no network during execution; no private mounts, owner/
cloud credentials, real instrument routes or unrelated plugins. Fetch and execution
remain separate. No new action, installer, package or OS update. Keep the generous
finite per-job envelope and preserve all failed evidence. Source/build changes
must be reviewed against the frozen allowlist before runtime installation.

Physics, security/timing, provenance, independent acceptance and integration remain
frontier-owned. Only a separately frozen pure data-coding helper with exact inputs,
outputs and allowed files may use an already qualified local model. It cannot
change interpretation, acceptance, supervisor or scope.

## Acceptance and stopping point

- Independent parser/failure/identity/ordering tests, late/out-of-order delivery,
  missing records, rejection/cancellation, unknown admission without replay,
  explicit same-operation reconciliation and responsive lease/Stop paths.
- Exact raw round-trip, zero-count vacuum, counts above 65535, window endpoints,
  clipping/rounding, source hashes, unchanged orientation and partial-record
  identification. Reject raw/view/association mismatches before reporting success.
- Genuine registry and real unchanged upstream acquisition workflow for 256/1024
  through both Demo and the authored vSEM HTTP fixture. Verify actual image type,
  view dtype/bytes, pixel pitch, raw companion/provenance, unsupported save/default
  refusal, no premature completion, no hidden imports/fields and fixture cleanup.
- Original 42 M05A contracts, all existing C1-C8 tests, confinement probes, artifact/
  installed-distribution checks, independent static wheel admission, source/
  publication guards and ordinary GitHub Actions acceptance must remain passing.
- Preserve exact candidate, dependency and built-wheel hashes and a complete
  factual dossier. Stop at reviewed draft outputs; do not merge PR #12, adopt the
  optional package into main, publish a binary/release or claim real vSEM GPU
  interoperability from a fixture. Existing scientific/transport core gates stay
  prerequisites for the subsequent actual cross-stack experiment.

M05B2B1 needs its own exact reviewed candidate and available isolation plan before
private execution: the external adapter can remain CPU-only while the reviewed
core owns the GPU. No private catalogue/run/owner credentials or Docker socket may
enter that environment. A worktree or ordinary WSL session is not confinement.
Disclosed native/base/kernel residual risks remain accepted only for public CPU
qualification until the owner explicitly chooses a later experiment envelope.

## Choices and rollback

1. Recommended: approve this exact M05B2B0 source/image-binding implementation and
   confined public CPU qualification, plus draft publication only. No main/PR #12
   merge, private external execution, GPU experiment, new dependency or release.
2. Defer image-binding code and first prepare the complete available M05B2B1
   isolation/transport plan through read-only inspection. No daemon or payload
   launch; return with the exact boundary and risks before any implementation.
3. Defer fibsemOS integration. Keep the qualified core association and CPU evidence,
   leave issue #10/draft PR #12 open and select another bounded roadmap proposal later.

The risk is false attribution, lossy/mislabelled image provenance or blocking
authority during a synchronous wait. Independent identity/failure tests and real
upstream CPU execution address those specific gates, not deployment isolation.
Rollback at this draft-only stage is leaving the candidate unmerged; any future
adoption still requires a reviewed revert path and separate integration approval.
