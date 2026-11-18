# fibsemOS next decision after M05A

Revision 1, 18 November 2026. **Proposal only; no additional approval is implied.**
The [source prototype](../../integrations/fibsemos/README.md) is an optional draft
for [#10](https://github.com/BenjaminZingsem/vSEM/issues/10). M05A does not install
or execute fibsemOS, change the core API, merge main or publish a release.

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
metadata sidecars against PyPI. Payload hashes are index claims, not independently
hashed downloaded binaries. Python/base-image and installer artifacts, upstream
source archive, built wheel and dynamic build closure are still missing. This is
not yet a complete install lock or vulnerability assessment.

NumPy 1.26.4 and SciPy 1.15.3 remain selected. OpenCV 4.11.0.86 permits NumPy 1;
five newer candidates required NumPy 2. That compatibility choice does not prove
the older release secure. FastAPI 0.162.5 brings opentelemetry-api 1.45.2, with no
SDK/exporter selected. An API dependency alone does not establish active telemetry.
FastAPI's 0.121.0 floor omits it but requires an older Starlette graph; choosing
that alternative requires a fresh complete resolution and security review.

Native/scientific/codec/XML/PDF dependencies make payload review material.
Metadata declares bundled FFmpeg under LGPL 2.1, GCC runtime with GPL exception,
libquadmath under LGPL, Matplotlib font licenses and certifi MPL 2.0, among others.
Top-level MIT/BSD labels are not a complete bundled-license inventory. Actual
LICENSE/NOTICE/native-library contents remain to be inspected before redistribution.

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

1. **M05B0 artifact inspection:** fetch the exact upstream revision and the 55
   named wheels as inert data into a disposable quarantine; verify wheel payload
   hashes and Git-tree/source identities; review archive paths, hooks, bundled
   instructions, licenses, native libraries and current advisories. Do not import,
   install, build, run scripts or modify product code. If any hash, dependency or
   source identity differs, stop that artifact and report it. Produce the complete
   execution candidate, including environment/installer identities and a concrete
   proposed CPU workflow, for a separate owner choice.
2. **M05B1 CPU execution, only after that choice:** stage only accepted artifacts
   in a disposable CPU runner. No private mounts, owner/cloud tokens, real
   instrument/network route or unrelated installed entry points. Fetching and
   executing are separate phases; disable network during build/import/test.
   Fail on undeclared dynamic dependencies. Qualify genuine discovery, device
   construction, supported/refused operations and the unchanged Demo workflow.
   Record effective dependencies and built-artifact hashes. This is not yet GPU
   or cross-stack acceptance and does not authorize merge.
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

Recommended next choice: **approve M05B0 inert artifact inspection only** on the
pin and 55-wheel proposal above. It closes the missing source/payload review before
asking for execution. It includes no install/build/import, dependency adoption into
the project, core API change, main merge or release. A narrower choice is to prepare
a revised dependency graph (for example an older FastAPI alternative) without
fetching payloads. Deferral leaves the source-only draft and #10 open.

The correlation slice can be prepared independently, but implementation needs a
separate bounded choice. Do not bundle unfinished core semantics into external
package consent. Until integration is separately approved, rollback is leaving the
optional draft unmerged and the qualified simulator untouched. After any future
approved merge, disabling/removing the optional plugin plus a reviewed revert
preserves a clear recovery path; preserve scientific records and review evidence.
