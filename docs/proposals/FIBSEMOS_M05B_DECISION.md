# fibsemOS next decision after M05A

Revision 3, 19 November 2026. **R1 inspection complete; no execution approval.**
The [source prototype](../../integrations/fibsemos/README.md) is an optional draft
for [#10](https://github.com/BenjaminZingsem/vSEM/issues/10). M05A does not install
or execute fibsemOS, change the core API, merge main or publish a release.

The approved M05B0 inspection is complete. All original artifact identities pass,
but the 55-wheel graph is **rejected for execution** because of advisory findings
and unresolved native-library risk. See the [inspection report](FIBSEMOS_ARTIFACT_REVIEW.md).
The separately approved M05B0-R1 inspection is also complete: all 52 replacement
wheels and the pinned Python 3.12 base config/layers pass identity and structural
checks. Remaining native/OS findings are disclosed in the
[R1 review](FIBSEMOS_R1_ARTIFACT_REVIEW.md). No external package or container ran.
The next proposed choice is the bounded [M05B1 CPU experiment](FIBSEMOS_M05B1_CPU_PLAN.md),
with explicit acceptance of residual risks for that disposable environment only.

## Exact proposed artifacts and known limits

The upstream MIT source pin is
[`27e72f6cc8f9c014562859450ad9260411acaa12`](https://github.com/fibsem-os/fibsem-os/tree/27e72f6cc8f9c014562859450ad9260411acaa12).
Its declared version `0.7.0.dev0` alone is insufficient identity. Reviewed Git blob
identities include `pyproject.toml` `94aeeb551425fbf19ae6f14f74207808707a5afe`,
`setup.py` `a0b68f46605275649a80b96a0ee5332a600961c0` and MIT `LICENSE`
`99ec6763132a1df7f5345a6042ad732ccee652dc`.

[dependency-proposal.json](../../integrations/fibsemos/review/dependency-proposal.json)
has SHA256 `833d86b382d95636115f89fdfd06df276806fb9fec8868c336d015a07c844bf5`.
It contains 55 exact CPython 3.10.12/Linux x86_64 wheel filenames, URLs,
PyPI-published payload hashes, metadata hashes, requirements, enabled extras and
full declared license fields. Fifty packages are runtime, seven build, with two
shared. The static audit closes 108 active requirement edges and verifies all 55
metadata sidecars against PyPI. M05B0 now independently verifies all downloaded
payloads and the complete source Git tree. It found affected Pillow/setuptools and
vendored dependencies; the graph must not be installed. The original proposal is
preserved for provenance. Built-wheel and dynamic-build closure remain unqualified.

The rejected graph kept NumPy 1.26.4/SciPy 1.15.3 and therefore an older OpenCV.
The replacement removes that coupling: a separate client environment can use
Python 3.12 and newer numerical/codec packages while core vSEM retains its
qualified requirements. Metadata compatibility alone does not prove behavior.
Both proposals include opentelemetry-api without an SDK/exporter; this does not
establish active telemetry or waive the proposed network isolation.

Native/scientific/codec/XML/PDF dependencies make payload review material.
Metadata declares bundled FFmpeg under LGPL 2.1, GCC runtime with GPL exception,
libquadmath under LGPL, Matplotlib font licenses and certifi MPL 2.0, among others.
Top-level MIT/BSD labels are not a complete bundled-license inventory. M05B0 has
recorded actual LICENSE/NOTICE/native-library contents; redistribution and any
replacement payload still need their applicable review and approval.

## Build and execution boundary

[setup.py](https://github.com/fibsem-os/fibsem-os/blob/27e72f6cc8f9c014562859450ad9260411acaa12/setup.py)
registers a custom `build_py`, which loads
[`fibsem/ai/agent/sources.py`](https://github.com/fibsem-os/fibsem-os/blob/27e72f6cc8f9c014562859450ad9260411acaa12/fibsem/ai/agent/sources.py)
and, for a non-editable build, copies checkout `.claude` skills/agents into package
assets. Disabling the agent extra does not remove this build behavior. These
packaged instructions are untrusted data, never maintenance authority. Inspection
of two hook files is not a whole-source or dynamic-build audit.

The [plugin loader](https://github.com/fibsem-os/fibsem-os/blob/27e72f6cc8f9c014562859450ad9260411acaa12/fibsem/plugins/loader.py)
enumerates installed entry points and loads plugin objects. A shared environment
can execute unrelated plugins. Genuine qualification therefore needs a fresh,
reviewed environment, not the existing simulator environment.

Proposed stages, each respecting its approval boundary:

1. **M05B0 and M05B0-R1 complete:** the original source/55 wheels were
   inspected without execution. The [replacement manifest](../../integrations/fibsemos/review/replacement-artifact-proposal.json)
   freezes 52 wheels (25 reused and 27 new), pip 26.3 and the Linux/amd64
   Python 3.12.16 OCI manifest/config/four-layer identities. Its SHA256 is
   `a5e705b56adefa5ba884dbab2dba6ccaf036987648bc1498a05253ebcacd75a2`.
   The owner approved inert inspection of those exact payloads. All identities,
   wheel records and layer compressed/decompressed hashes pass. Native/OS/license
   and build/startup findings are recorded; no external execution occurred.
   The proposed base's old pip must not bootstrap a test. Pillow's libpng and
   OpenCV's embedded OpenSSL evidence remain unresolved for deployment.
2. **M05B1 CPU execution, only after a separate execution approval:** stage the exact artifacts
   in a disposable CPU runner. No private mounts, owner/cloud tokens, real
   instrument/network route or unrelated installed entry points. Fetching and
   executing are separate phases; disable network during build/import/test.
   Fail on undeclared dynamic dependencies. Qualify genuine discovery, device
   construction, supported/refused operations and the unchanged Demo workflow.
   Record effective dependencies and built-artifact hashes. This is not yet GPU
   or cross-stack acceptance and does not authorize merge. The concrete
   [revision 1 specification](FIBSEMOS_M05B1_CPU_PLAN.md) defines allowed files,
   confinement, clean installer bootstrap, all eight gates and failure handling.
3. **M05B2 actual vSEM comparison:** needs the correlation change below, reviewed
   CPU evidence and a separately approved isolated GPU/HTTP plan. Use the named
   compute GPU while preserving the display GPU; expose only the authorized public
   API to the external environment. Run the same unchanged upstream acquisition
   workflow through Demo and vSEM, native1024 and scientific/transport/failure
   gates from the original proposal. Close all owned fixtures. Main integration
   and any release need explicit approval and successful actual-head CI.

## Public acquisition correlation proposal

The current public operation receipt identifies a command, while image metadata
identifies a source/raster. No public authoritative association connects the two.
Physical completion can also precede numerical image publication. Using the newest
image, predicting counters or reading private native metadata would violate the
contract. The prototype refuses synchronous acquisition before exposure.

Proposed independent core slice: add an authenticated, versioned, read-only
`GET /operation/<id>/acquisitions` projection. It would report only sources and
image cuts already associated with that operation, under an explicitly reviewed
public schema. Existing operation receipts stay unchanged. An admitted but
unstarted/rejected operation has no invented source/image; started operations can
have an observable source without a published image; partial/final publication
retains identity and coverage. Single, live and freeze associations must be defined
separately. Unknown/evicted identities must not fall back to the latest image.

Before coding, refine the exact mapping in a bounded approval packet covering
runtime route/projection, client consumption, documentation and independent tests.
No hidden physical parameters, evaluator answers, seeds or future faults may be
included. Acceptance must cover loss/timeouts, cancellation, live supersession,
freeze, delayed numerical publication, wrong principal and retained/evicted records;
actual GPU/HTTP1024 must prove correlation and cleanup without changing exposure,
dose, partial-frame semantics or Stop. This is a new observable capability, not an
already-approved M05A repair. It requires its own trusted owner decision.

## Owner choices and rollback

1. **Recommended: approve M05B1 CPU qualification revision 1.** Implement its
   maintainer-owned harness and isolated workflow, then build/import/test the exact
   inspected artifacts on disposable public CPU infrastructure. This explicitly
   accepts the disclosed native/base residual risks for that restricted experiment,
   with offline execution, no root privileges, no base-pip bootstrap and the
   limited input corpus. Correct the harness and rerun within the same scope and
   criteria as needed. No product/API changes, artifact substitutions, private-host
   or GPU execution, released dependency adoption, main merge or release.
2. **Prepare a replacement/native-build plan first.** Do further read-only
   metadata/source research to specify a base and native-library build strategy
   addressing the residual findings. Do not fetch new payloads or execute builds.
   Present the exact additional artifacts and costs before another scoped choice;
   a new dependency label alone is not proof that bundled components are fixed.
3. **Defer fibsemOS.** Preserve the unmerged prototype and evidence, leave #10 open
   and retain the released simulator. No further external execution or feature
   implementation is authorized by deferral.

The [maintenance policy](../MAINTENANCE_POLICY.md) requires the next explicit owner
choice because installation/build/import and the new execution workflow exceed
the inspection-only approval. Hash/structure success does not supply consent or
establish a safe deployed environment. The inspection does not need repeating.

The correlation slice can be prepared independently, but implementation needs a
separate bounded choice. Do not bundle unfinished core semantics into external
package consent. Until integration is separately approved, rollback is leaving the
optional draft unmerged and the qualified simulator untouched. After any future
approved merge, disabling/removing the optional plugin plus a reviewed revert
preserves a clear recovery path; preserve scientific records and review evidence.
