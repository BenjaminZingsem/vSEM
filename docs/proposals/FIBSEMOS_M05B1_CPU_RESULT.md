# M05B1 disposable CPU qualification result

**20 November 2026: C1-C8 pass at the approved CPU-experiment scope.**
Implementation `db937154bcd30997c2897650a319a09fdbedde78` passed the
[qualification run](https://github.com/BenjaminZingsem/vSEM/actions/runs/44688299014)
and [ordinary acceptance](https://github.com/BenjaminZingsem/vSEM/actions/runs/44688299105).
Both check producers are GitHub Actions App 15368. The maintainer independently
audited the decoded evidence and scope. PR12 remains draft; main is unchanged.
This is not release/deployment clearance, GPU qualification or a successful vSEM
image return. The latter remains refused before exposure.

## Scope and provenance

The owner approved [CPU plan revision 1](FIBSEMOS_M05B1_CPU_PLAN.md) at `20f8790`
and the exact [setuptools pin correction](FIBSEMOS_M05B1_PACKAGING_DECISION.md).
All other M05A product bytes remain at `ca6825f`. Original acceptance, existing CI,
core dependencies, API, physics and GUI are unchanged. Maintainer-owned security,
confinement and acceptance work was not delegated.

Inputs remain upstream `fibsem-os/fibsem-os@27e72f6cc8f9c014562859450ad9260411acaa12`,
source ZIP SHA256 `d24472e24c6a49fc387412d01590c57b64e338cfcf3479aa80c6da10869ee9ac`,
Git tree `0a36bb2516ad632b2fc97cc17cc15f066c35333e`, the exact
[52-wheel manifest](../../integrations/fibsemos/review/replacement-artifact-proposal.json)
SHA256 `a5e705b56adefa5ba884dbab2dba6ccaf036987648bc1498a05253ebcacd75a2`,
and its pinned Linux/amd64 Python 3.12.16 OCI config/four layers. No artifact
substitution, source distribution, OS upgrade or private-host execution occurred.

## Acceptance evidence

| Gate | Observed result |
|---|---|
| C1 identity/environment | Exact source tree, all 52 wheels and OCI identities verified. Host inspected all three containers before execution. Separate probe confirmed UID/GID 10001, zero capabilities, no-new-privileges, seccomp, read-only mounts, only loopback and failed external connection. Verified pip 26.3 bootstrapped a fresh no-pip venv; 52 exact distributions before build, 54 after the two admitted builds. Base pip/ensurepip were not invoked. |
| C2 actual build/admission | Both actual PEP517 builds passed offline; declared requirements satisfied, dynamic requirements empty. After builder exit, all 812 upstream package/assets and 9 plugin source members matched frozen bytes; RECORD, Python/dependency metadata, entry points, wheel tags and license evidence passed. |
| C3 genuine discovery | Real installed upstream registry discovered the allowlisted vSEM entry point; actual microscope, Beam, Stage and unchanged Imaging service constructed. No fake upstream classes or monkeypatch supplied compatibility proof. |
| C4 bindings | Supported current/focus/stigmation/absolute XYZ writes and readbacks passed against observable-only loopback HTTP. Strict bounds/types/units and unsupported-operation refusals passed before writes. |
| C5 authority/failure | Explicit connection rules, unknown admission without replay, independent Stop-generation confirmation and real periodic lease-loss refusal passed. An unconfirmed Stop raises the original AuthorityError; disconnect is not Stop. |
| C6 Demo | Unchanged upstream Imaging acquired 256x256 and 1024x1024 generated uint8 images with matching 80 micrometre field and 20 microsecond dwell metadata. Measured call durations 1.946 s and 21.595 s. No downloaded specimen/font/video input. This is an integration smoke test, not a physical image benchmark. |
| C7 honest limit | Same supported 256/1024 settings through vSEM raised QualificationRequired before any acquisition command. Invalid upstream defaults also refused. |
| C8 evidence/cleanup | All 8 genuine case records, original 42 M05A tests and 38 harness tests passed. No prohibited imports or remaining fixture/renewal threads. All three owned containers were removed and the output mount unmounted. 106 bounded evidence/log files were decoded with complete chunk/size/hash checks. Ordinary CI: 295 tests discovered, 286 passed and 9 original explicit skips, plus passing display/content gates. |

The disposable runner exposed 4 CPUs and 15,539,146,752 available memory bytes;
the container allowance was 13,596,753,408 bytes with measured scratch/output
ceilings and no CPU cap. The finite job envelope remained 180 minutes. The actual
host image/kernel/Docker configuration is recorded in the encoded run evidence;
the hosted VM is not claimed immutable merely because the client image is pinned.

Built-wheel identities from this run, retained as evidence rather than binaries:

| Distribution | Bytes | SHA256 |
|---|---:|---|
| fibsem 0.7.0.dev0 | 3,712,175 | `fc67b32e9584c2a0a3ed0933b056d320b0097676dca5916024ae0571907e2ceb` |
| vsem-fibsemos 0.0.0.dev1 | 19,768 | `e03f931c1190517b26cbac3a1abf931ba34c7b4df333659bd4f5f8eb8fdc69b8` |

The upstream wheel contains its exact MIT notice. The prototype declares MIT;
its repository notice is separately inventoried, not bundled in the built wheel.
No built binary redistribution was approved or performed. A later distributable
package needs its own license/material and byte review; these hashes are not an
installation recipe or reusable adoption authorization.

## Failed attempts and corrections

All failures remain preserved, not relabelled as successful gates:

- [44599900995](https://github.com/BenjaminZingsem/vSEM/actions/runs/44599900995),
  `665bd65`: Docker refused compression with a one-file local log. No package ran.
  Explicitly disabling compression corrected the harness; cleanup passed.
- [44600636097](https://github.com/BenjaminZingsem/vSEM/actions/runs/44600636097),
  `6002f1b`: builds/static source inspection passed, but a loop variable overwrote
  the upstream wheel filename. Pip correctly refused installation. A source-asset
  regression now protects the filename; all owned containers closed.
- [44601591492](https://github.com/BenjaminZingsem/vSEM/actions/runs/44601591492),
  `effe5d4`: all genuine cases except one C5 assertion passed. The harness expected
  PendingOutcome instead of the original AuthorityError for missing Stop-generation
  confirmation. The correction follows the unchanged original 42-test contract;
  it does not weaken Stop or alter product behavior. Cleanup passed.

The private collector also handles GitHub CLI's UNKNOWN STEP labels by the
verified job/step time window; it preserved raw logs and verified every recovered
chunk. No package-generated text was executed or treated as maintenance authority.

## Remaining boundary

The disclosed [native/base risks](FIBSEMOS_R1_ARTIFACT_REVIEW.md) remain accepted
only for this confined CPU experiment. Containers share a kernel; these controls
do not establish resistance to every escape or qualify a real instrument.
The source prototype and experiment remain unmerged and unreleased.

The next proposed prerequisite is [M05B2A public acquisition association](FIBSEMOS_M05B2A_CORRELATION_PLAN.md).
It needs an explicit owner feature choice before coding. Adapter image binding
and genuine Demo/vSEM GPU/HTTP comparison need a subsequent exact execution and
integration decision. No private fibsemOS execution, main merge, dependency
adoption or release follows automatically from this result. Issue 10 stays open.
