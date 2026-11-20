# Optional fibsemOS source prototype

**M05B2B0 draft, 20 November 2026. M05B1 CPU qualification passed;
configured image return passes its public CPU fixture gates; unmerged.** This independently authored package explores an observable-only SEM
adapter for [issue #10](https://github.com/BenjaminZingsem/vSEM/issues/10).
The approved [proposal](../../docs/proposals/FIBSEMOS_INTEROP.md) separates source
work from external adoption, actual workflows and integration. Do not install this
prototype into the qualified vSEM environment. Core simulator dependencies are
unchanged; `pyproject.toml` is candidate packaging, not a complete install recipe.

## What the source contains

`Client` uses only the separate public instrument HTTP API. It accepts an explicit
numeric loopback origin and token, follows no redirects/proxies, and imports no
engine, evaluator or GUI code. Its token is kept in memory; never put it in an
upstream `SystemSettings`, device options, file, notebook output or log.

| Surface | Implemented source behavior | Qualification boundary |
|---|---|---|
| Current, relative focus, stigmation | Whole-request validation, coherent observed optics base, serialized writes, fresh readbacks | Genuine upstream/HTTP fixture bindings pass; actual vSEM image-response qualification remains |
| Stage | Complete absolute XYZ in `vsem_specimen_xyz_m`, explicit metre units; combined focus/Z bounds | No tilt, rotation, implicit frame transform or relative stage convenience |
| HFW, resolution, dwell | Observed current-raster readbacks; separate explicit scan requests | No standalone raster setters in the current public API; never present local intent as applied state |
| Single/live/configure/freeze | Public receipt operations with separate meanings | These are explicit client operations, not a replacement fibsemOS acquisition workflow |
| Stop and lease | Separate connections/locks; periodic renewal; receipt plus newer observable Stop generation | Interlock, lease loss and uncertain admission fail honestly; disconnect is not Stop |
| Raw image | Explicit image/source/cut checks; lossless uint32 little-endian bytes and public acquisition metadata | No newest-image guessing or private operation lookup |
| fibsemOS entry point and devices | Actual `FibsemMicroscope`, `Beam`, `Stage` subclasses and builders; unchanged `Imaging` service | Genuine discovery/construction and bounded binding tests pass in the disposable M05B1 environment; private/deployed adoption remains unapproved |
| Synchronous acquisition | Default refusal; explicit fixed-window opt-in returns an upstream image with an immutable raw companion | Exact public operation/source/raster/final-cut association is required; CPU fixture workflow qualification passed; actual vSEM GPU workflow not qualified |
| View saving | Generic TIFF and automatic saving explicitly refused before a write/exposure | Use the raw companion's lossless save/load; no view-only save contract is qualified |
| Auto-functions, ion/milling and other devices | Explicit refusal/absent parameters for the supported candidate paths | No autofocus, alignment, FIB or real microscope compatibility claim |

Only square 64/128/256/512/1024 rasters, 20/100/1000 microsecond dwell, HFW
0.1–5000 micrometres and integer 1–1000 pA current are representable. Current
conversion allows only a 1e-9 pA floating-point tolerance; dwell allows 1e-6 ns.
Unsupported values are rejected, not clipped or snapped. `focus_offset_m` is a
relative plugin-specific setting, not absolute working distance.

## Candidate configuration and lifecycle

The registry descriptor is lazy. The sequence qualified in the M05B1 experiment
is construct `VsemMicroscope(system)`, explicitly call `configure_api(origin, token)`,
then `connect_to_microscope('127.0.0.1', port, reset_beam_shift=False)`.
Construction/configuration do not connect. A registry auto-connection without
explicit credentials fails before network access, even if `system.info.port` exists.

The candidate connection requires electron and stage enabled; ion, manipulator
and fluorescence disabled; automatic defaults and beam-on disabled; no additional
device entries, roles or driver overrides. It builds only its own electron/stage,
binds the unchanged upstream `Imaging`, then acquires the public API lease.
Generic vendor/remote device discovery is not invoked by this facade.

Readbacks come from current server observations. The strict parameter wrapper
validates the original value before upstream coercion/clipping and reports a fresh
readback after a completed write. Unsupported aggregate restoration/default-setting
workflows fail before performing partial writes. The source preflight rejects
upstream default 1536x1024/1us settings and all unqualified reduced-area, bit-depth,
integration, interlacing, autocontrast, drift-correction and save options.

One trusted writer per API principal is required. The API has no compare-and-swap
optics or unique per-client principal. Local serialization and a second state read
detect many stale requests but cannot prevent another client racing the final POST.
Acquire-or-renew can also race expiry: an observed changed epoch halts the workflow;
the plugin cannot undo an already granted lease. A POST timeout without an ID
latches unknown admission and is never automatically replayed. With a known ID,
inspect that operation explicitly before submitting more work. Failed readback
does not mean the preceding command failed and does not authorize retry.

Call explicit Stop and confirm it before disconnect if stopping is intended.
`close()` joins its lease thread and clears the token; it never substitutes
disconnect for Stop. This prototype is for trusted development, not confinement
of an adversarial operator or a real-instrument safety system.

## Raw evidence and views

`RawFrame` retains exact bytes plus the closed public v2 acquisition projection,
including source/image identity, partial coverage, exposure-time parameter
segments, blank holds and unknown accounting. A zero count is not evidence that
a pixel was acquired: consult coverage. The raw container has a bounded JSON
header, exact raw length, and separate raw/metadata SHA256 values. Save is exclusive
creation; load never executes or extracts content. Digests detect accidental
changes, not malicious rewriting of both data and hashes. Crash durability is not
claimed.

`view(black, white, bits)` derives an explicitly labelled 8/16-bit fixed linear
window, with exact integer half-up rounding. Its provenance records source hashes,
window, clipping, scale and orientation, with the raw companion required. It is
not a calibrated electron-count image. No upstream
dtype restriction has been patched and no automatic histogram transform is used.

For an explicitly configured connected microscope,
`microscope.configure_image_return(black=9, white=101)` enables the single-image
path with that fixed raw-count window (configuration is single-use). The unchanged
pinned `fibsem.acquire.acquire_image(microscope, image_settings)` workflow then
returns a genuine upstream `FibsemImage` subclass. `.data` is a uint16 compatibility
view; it is not raw counts. The upstream constructor also produces a separate
`filtered_data` display derivative; neither this derivative nor mutable `.data`
replaces the immutable companion:

- `image.vsem_result.raw_frame`: exact uint32 bytes and acquisition-time metadata;
- `image.vsem_result.association`: defensive copy of the public operation/cut join;
- `image.vsem_result.view_provenance`: fixed window, hashes, clipping and rounding;
- `image.vsem_result.view_bytes`: immutable, original compatibility-view bytes.

The acquired pixel pitch comes from public acquisition metadata. Image settings
are request intent; parameter segments retain changes during exposure. Absolute
working distance, vendor geometry and unobserved microscope fields are not
fabricated. Upstream's pre-driver wall-clock stamp describes the call, not the
engine's episode exposure origin. The raw companion retains that episode time.

`PendingOutcome` carries a known operation ID. Explicit
`microscope.reconcile_image(operation_id, image_settings)` reads that retained
request without another exposure. Missing/mismatched delivery stays unresolved;
ambiguous admission is never replayed. Renewal, interlock and epoch loss are
explicit errors, including when they occur during raw download. Stop and lease
renewal use independent connections outside image-wait locks. A confirmed Stop
does not reinterpret the outcome of a physically completed acquisition.

Default acquisition still refuses before exposure unless image return is
configured and the server's association projection passes preflight. Generic
`image.save(...)` raises before touching the filesystem; raw save/load is
available through `image.vsem_result.raw_frame`.

## Evidence and remaining work

The [M05B1 result](../../docs/proposals/FIBSEMOS_M05B1_CPU_RESULT.md) records
all C1-C8 passing at `db93715`, including real unchanged Demo 256/1024 acquisitions,
strict binding/refusal/Stop/lease checks, source admission and cleanup. It does
not qualify an actual vSEM image return. The later [M05B2B0 result](../../docs/proposals/FIBSEMOS_M05B2B0_CPU_RESULT.md)
qualifies configured return against authored CPU HTTP fixtures only. The merged
[public association prerequisite](../../docs/proposals/FIBSEMOS_M05B2A_CORRELATION_PLAN.md)
is available in main. The owner approved
[M05B2B0](../../docs/proposals/FIBSEMOS_M05B2B0_IMAGE_BINDING_PLAN.md) implementation,
public CPU qualification and draft publication only. Its new configured-image
gates use an authored HTTP data oracle, not the physical engine. Genuine Demo/vSEM
GPU/HTTP comparison and optional-package adoption remain separate decisions/gates.

Run the independent standard-library tests from repository root:

```text
python -B -m unittest acceptance.test_fibsemos_contract acceptance.test_fibsemos_preflight acceptance.test_fibsemos_image_return
```

The original 42 tests and 26 new image-return tests pass on Windows Python 3.10.9. They use
locally authored real loopback HTTP fixtures and pure request/data logic. The full
current Linux/public runs are recorded in the qualification dossier. Tests close
their fixtures and renewal threads. AST/source checks do not
establish genuine plugin compatibility; no fake upstream module is used as proof.

Only the unit-conversion helper was delegated to a qualified local coding model;
the maintainer audited/corrected it. Protocol, authority, Stop, records, integration
design and independent tests are maintainer-owned. See [provenance](PROVENANCE.md).

The original [dependency proposal](review/dependency-proposal.json) is preserved
but rejected for execution. [M05B0 inspection](../../docs/proposals/FIBSEMOS_ARTIFACT_REVIEW.md)
verified the pinned source and all 55 wheels, and found affected packages and
unresolved native-library risk. The [replacement manifest](review/replacement-artifact-proposal.json)
proposes a separate Python 3.12 client environment. Its
[approved inert review](../../docs/proposals/FIBSEMOS_R1_ARTIFACT_REVIEW.md) is now
complete: all 52 wheels and the pinned base config/layers pass identity checks;
native/base risks remain disclosed. The separately approved
[M05B1 CPU plan](../../docs/proposals/FIBSEMOS_M05B1_CPU_PLAN.md) has now passed
in its disposable public environment. Upstream build/import/execution occurred
only there; no private fibsemOS execution or simulator GPU campaign occurred.
M05B2B0 keeps the same exact upstream source, 52 wheels and OCI base. Released
dependency adoption, private external execution, genuine Demo/vSEM GPU/HTTP
comparison, main merge and release remain separate approvals and acceptance work.
