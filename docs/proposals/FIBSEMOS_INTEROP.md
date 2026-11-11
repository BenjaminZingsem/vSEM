# Proposed fibsemOS interoperability slice

Status: **Awaiting owner choice; no implementation or dependency adoption approved.**
Specification M05 revision 1, 11 November 2026. Tracks
[issue #10](https://github.com/BenjaminZingsem/vSEM/issues/10) and roadmap R01.
This proposal is planning evidence, not a change to the existing instrument API
or maintenance policy. No upstream code has been installed, imported or executed
for this review. No cross-stack runtime result is claimed.

## Exact sources and findings

- vSEM baseline: `f3add4ac0eddc46c9033a0e515852dd67c3363b7`, with
  [public API](../API.md), qualified live receipts and terminal-fault documentation.
- fibsemOS review pin: `27e72f6cc8f9c014562859450ad9260411acaa12`.
  Its [registry](https://github.com/fibsem-os/fibsem-os/blob/27e72f6cc8f9c014562859450ad9260411acaa12/fibsem/drivers/registry.py)
  supports external `fibsem.drivers` entries returning a `DriverEntry`, including
  device builders and a microscope facade. Use this extension point instead of
  changing built-in vendor drivers or pretending its remote backend understands
  vSEM's HTTP protocol.
- The [device guide](https://github.com/fibsem-os/fibsem-os/blob/27e72f6cc8f9c014562859450ad9260411acaa12/docs/developers/devices.md)
  distinguishes bound/supported parameters from absent capabilities. Publish only
  supported bindings and explicit limits; never implement successful no-ops.
- The [image container](https://github.com/fibsem-os/fibsem-os/blob/27e72f6cc8f9c014562859450ad9260411acaa12/fibsem/structures/image.py)
  checks for uint8/uint16 images. vSEM's little-endian uint32 counts and causal
  records require separate lossless preservation, alongside any compatibility view.
- The [beam interface](https://github.com/fibsem-os/fibsem-os/blob/27e72f6cc8f9c014562859450ad9260411acaa12/fibsem/devices/beam.py)
  describes working distance in metres. This does not establish an absolute-WD
  mapping for vSEM's relative focus offset. Keep that upstream control unavailable
  until a distinct scientific mapping is reviewed and approved.
- [Package metadata](https://github.com/fibsem-os/fibsem-os/blob/27e72f6cc8f9c014562859450ad9260411acaa12/pyproject.toml)
  declares Python >=3.10, base scientific/server dependencies with version floors,
  and optional UI/ML/MCP/agent extras. These are not a reproducible dependency lock.
  The [upstream license](https://github.com/fibsem-os/fibsem-os/blob/27e72f6cc8f9c014562859450ad9260411acaa12/LICENSE)
  is MIT; preserve notices for adopted material. Dependency licenses still need
  their own review. The version string alone (`0.7.0.dev0`) does not identify this pin.

## Proposed package boundary

Build an independently authored optional package under `integrations/fibsemos/`
in this repository, with its own packaging and eventual environment lock. The core
vSEM install and numerical dependency pins remain independent. The plugin process
receives only a vSEM API origin/token and operator-visible records. It cannot
read the catalogue, engine/evaluator objects, private episode diagnostics or GUI
credentials. Credential values never enter configuration examples or image records.

One vSEM causal engine remains authoritative. The plugin may cache timestamped
observations, pending request intent and operation IDs, but cannot simulate
movement, focus, exposure or completion locally. Reads identify stale observations.
An unavailable response is not a fabricated current readback.

Use the pinned upstream devices/services and acquisition entry points where their
semantics fit. In particular,
[`fibsem.acquire.acquire_image`](https://github.com/fibsem-os/fibsem-os/blob/27e72f6cc8f9c014562859450ad9260411acaa12/fibsem/acquire.py)
delegates to the imaging service. Qualification must exercise that unchanged
upstream path with backend bindings, not a replacement workflow with the same name.

## Initial capability and mapping matrix

Every supported operation must validate the whole request before issuing an
exposing/moving command. A mixture of supported and unsupported fields must not
partly execute. Reject out-of-range/unrepresentable values rather than clamp.

| Area | Proposed first slice | Required evidence / limit |
|---|---|---|
| Connection and control | Explicit loopback vSEM endpoint and bearer token; acquire/renew the API lease | GUI competition, expiry and unavailable API fail honestly; no real-instrument endpoint or GUI token |
| Beam current | Convert SI amperes to integer pA, 1-1000 | Exact supported values with a specified floating-point conversion tolerance; no silent rounding to a different current |
| Field of view | HFW in metres, 0.1-5000 micrometres | Match applied HFW and acquired metadata; no arbitrary magnification calibration |
| Raster | Square 64/128/256/512/1024; dwell 20/100/1000 microseconds | Seconds-to-nanoseconds mapping; reject other shapes/dwells; preserve progressive timing |
| Stage | Absolute XYZ in the explicitly declared vSEM specimen frame | Metres, X/Y +/-25 mm, Z +/-20 micrometres; combined focus/Z bound; axis-sign and displacement checks. Tilt, rotation and undeclared coordinate transforms unavailable |
| Focus | Explicit plugin-specific relative `focus_offset_m`, +/-25 micrometres | No relabelling as absolute working distance; upstream autofocus remains unqualified/unavailable |
| Stigmation | Two dimensionless components, each +/-1 | Explicit X/Y mapping with readback and image-response tests; no claim of instrument calibration |
| ROI | Square physical HFW plus offsets in metres | Qualify conversion from any upstream normalized rectangle before exposing that convenience; retain survey/ROI source identity and partial records |
| Acquisition | SE single acquisition; live/configure/freeze exposed with their distinct semantics | Match operation, source, cut and terminal outcome; physical completion can precede image delivery |
| Stop | Independently responsive Stop with owned authority and observed generation | Freeze and disconnect do not substitute for Stop. Interlock can make Stop unconfirmed; preserve that distinction |
| Other controls | Absent or explicit unsupported error | Ion beam, milling, manipulator, chamber/vacuum actuation, voltage changes, tilt/rotation, arbitrary scan rotation, unsupported detectors and auto-functions |

Multi-field optics requests need a coherent observed base for unchanged fields,
serialized plugin writes and revalidation of authority. Do not overwrite a newer
setting with a stale cached value or turn a requested setting into an applied one.

## Images and operation outcomes

Preserve the exact raw count bytes, dimensions, byte order, source/image identifiers,
coverage/completed pixels, outcome, acquisition-time parameter segments, blank holds
and observable charge/time metadata. Unknown finalized accounting stays unknown.
Keep partial acquisitions identifiable as partial, even when unacquired pixels are
zero. Raw save/load must reproduce both bytes and metadata without a lossy view.

A `FibsemImage` compatibility view is explicitly derived. Record its source digest,
window, scale, clipping, rounding, orientation and any processing; a view-only file
must identify the required raw companion and must not claim lossless counts when
that companion is absent. For method comparisons, freeze the view transform across
the compared images. Metadata must say whether measurements are simulated counts
or another detector intensity kind; integer casting cannot establish electron
count calibration. Do not patch upstream dtype checks to claim compatibility.

Synchronous workflows may wait for terminal outcomes while a separate control
path renews the lease and can issue Stop. Do not hold a serialization lock across
an image wait that blocks either path. Retain rejected/cancelled/unknown outcomes.
After a timeout, reconcile the known operation and observed state before deciding
whether another command is safe. If admission is ambiguous and no operation ID
was received, stop the workflow for reconciliation; do not assume idempotency or
retry an exposing command. Slow accurate rendering does not justify accelerating
exposure or substituting an old frame.

## Staged approval and acceptance

### M05A: source prototype and independent contract tests

Owner choice is required before starting. Proposed scope: independently authored
plugin source/configuration, pure mapping and data-record helpers, independent CPU
tests using locally authored HTTP fixtures, and a reviewed draft PR. Allowed new
paths are `integrations/fibsemos/`, `acceptance/test_fibsemos_*.py` and related
documentation. Existing protected tests, engine/runtime, workflow, policy and core
dependency files remain outside scope.

No upstream package installation/execution, external implementation copying, GPU
campaign, main merge or release is included in M05A. Standard-library/pinned-core
helper tests may run; the genuine fibsemOS binding remains unqualified. Produce
the exact proposed dependency lock, sources/hashes/license inventory, reviewed
import/build behavior and execution-boundary plan as the concrete M05B decision.
Read-only package metadata inspection is allowed; an unresolved dependency graph
blocks adoption. Do not label the prototype installable/compatible prematurely.

Frontier owns protocol/authority/Stop semantics, architecture, numerical/image
meaning, independent tests and review. Once approved and locally qualified, exact
pure coding jobs may cover mapping-table helpers, records and configuration with
fixed allowed files and acceptance. Workers receive no credentials, external
downloads, research/design task or authority to alter tests/contracts.

### M05B: external adoption, cross-stack qualification and integration

Requires a separate owner choice on the completed M05A artifacts and exact lock.
Prepare an isolated environment, separate from the qualified vSEM environment.
Initially evaluate external inputs in approved disposable CPU CI without private
mounts/credentials. Private GPU execution needs reviewed inputs and an explicitly
approved isolation/ownership plan; a worktree or ordinary WSL is not confinement.
No vendor SDK, UI/ML/MCP/agent extra, cloud credential, real microscope or standing
server is necessary for this first capability slice.

Before integration, require all of the following:

1. Genuine plugin discovery and supported/unsupported capability tests on the exact
   upstream pin; no monkeypatch of upstream workflow or successful unsupported stub.
2. The same unchanged upstream acquisition workflow through Demo and vSEM, including
   native1024 through the actual vSEM public HTTP API. Record real outcomes/refusals.
3. Independent unit, limit, coordinate-sign, applied-readback, raw round-trip,
   partial-coverage and derived-view provenance tests, including zero-count vacuum.
4. Admission timeout, slow publication, lost response, cancellation, supersession,
   lease loss and interlock cases; independent Stop remains responsive; no duplicated
   exposure, invented completion, cleared interlock or hidden-state access.
5. Original vSEM CPU, GPU/HTTP, transport and cleanup acceptance, plus successful
   final PR/integration CI and post-merge verification. Close all owned fixtures.
6. Accurate install/configuration/capability documentation and versioned conformance
   evidence. Autofocus/alignment each need their own resolved mappings and gates.

## Risks, alternatives and rollback

The main risks are false capability claims, lossy evidence, stale settings,
completion/Stop confusion and a broad external dependency graph. The boundaries
and tests above address these explicitly; this static review does not prove them.
Simulation workflow compatibility is separate from scientific calibration and
supervised hardware transfer. It supplies no FIB physics or autonomous sample
preparation qualification.

Owner options: approve M05A as scoped, choose a documentation/interface handoff
for a separately owned bridge, or defer #10. M05A approval does not approve M05B.
No option here changes repository permissions or publishes a release. Before merge,
rollback is retaining/rejecting the isolated prototype; after separately approved
integration, disable/uninstall the optional plugin and use a reviewed revert while
preserving evidence. The core simulator and qualified environment stay independent.
