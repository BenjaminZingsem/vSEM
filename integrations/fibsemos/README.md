# Optional fibsemOS source prototype

**M05A draft, 18 November 2026. Not installed, release-ready or qualified against
fibsemOS.** This independently authored package explores an observable-only SEM
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
| Current, relative focus, stigmation | Whole-request validation, coherent observed optics base, serialized writes, fresh readbacks | HTTP fixture tests pass; actual image-response and upstream binding gates remain |
| Stage | Complete absolute XYZ in `vsem_specimen_xyz_m`, explicit metre units; combined focus/Z bounds | No tilt, rotation, implicit frame transform or relative stage convenience |
| HFW, resolution, dwell | Observed current-raster readbacks; separate explicit scan requests | No standalone raster setters in the current public API; never present local intent as applied state |
| Single/live/configure/freeze | Public receipt operations with separate meanings | These are explicit client operations, not a replacement fibsemOS acquisition workflow |
| Stop and lease | Separate connections/locks; periodic renewal; receipt plus newer observable Stop generation | Interlock, lease loss and uncertain admission fail honestly; disconnect is not Stop |
| Raw image | Explicit image/source/cut checks; lossless uint32 little-endian bytes and public acquisition metadata | No newest-image guessing or private operation lookup |
| fibsemOS entry point and devices | Candidate actual `FibsemMicroscope`, `Beam`, `Stage` subclasses and builders; unchanged `Imaging` service | Statically reviewed only; M05A never imports/executes fibsemOS or these bindings |
| Synchronous acquisition | Validates complete settings, then raises `QualificationRequired` before exposure | Public operation-to-image association is missing; genuine image return is not implemented |
| Auto-functions, ion/milling and other devices | Explicit refusal/absent parameters for the supported candidate paths | No autofocus, alignment, FIB or real microscope compatibility claim |

Only square 64/128/256/512/1024 rasters, 20/100/1000 microsecond dwell, HFW
0.1–5000 micrometres and integer 1–1000 pA current are representable. Current
conversion allows only a 1e-9 pA floating-point tolerance; dwell allows 1e-6 ns.
Unsupported values are rejected, not clipped or snapped. `focus_offset_m` is a
relative plugin-specific setting, not absolute working distance.

## Candidate configuration and lifecycle

The registry descriptor is lazy. The proposed sequence, to be qualified in M05B,
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
not a calibrated electron-count image or a qualified `FibsemImage`. No upstream
dtype restriction has been patched and no automatic histogram transform is used.

## Evidence and remaining work

Run the independent standard-library tests from repository root:

```text
python -B -m unittest acceptance.test_fibsemos_contract acceptance.test_fibsemos_preflight
```

The 42 tests passed on Windows Python 3.10.9 and Linux Python 3.10.12. They use
locally authored real loopback HTTP fixtures and pure request/data logic. The full
Linux suite discovered 295 tests: 286 passed, nine existing environment/manual
skips. Tests close their fixtures and renewal threads. AST/source checks do not
establish genuine plugin compatibility; no fake upstream module is used as proof.

Only the unit-conversion helper was delegated to a qualified local coding model;
the maintainer audited/corrected it. Protocol, authority, Stop, records, integration
design and independent tests are maintainer-owned. See [provenance](PROVENANCE.md).

The original [dependency proposal](review/dependency-proposal.json) is preserved
but rejected for execution. [M05B0 inspection](../../docs/proposals/FIBSEMOS_ARTIFACT_REVIEW.md)
verified the pinned source and all 55 wheels, and found affected packages and
unresolved native-library risk. The [replacement manifest](review/replacement-artifact-proposal.json)
proposes a separate Python 3.12 client environment; its new payloads are not
downloaded or approved. See the [next decision](../../docs/proposals/FIBSEMOS_M05B_DECISION.md)
for exact scope, missing public correlation and staged qualification. No upstream
distribution was installed, imported, built or executed, no simulator GPU campaign
ran, and no main merge/release is included.
