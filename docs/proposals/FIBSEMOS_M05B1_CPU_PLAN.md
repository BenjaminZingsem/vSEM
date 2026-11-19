# M05B1 disposable CPU qualification specification

Revision 1, **19 November 2026**. Proposed for
[draft PR12](https://github.com/BenjaminZingsem/vSEM/pull/12) after the
[R1 inert review](FIBSEMOS_R1_ARTIFACT_REVIEW.md). **Not approved or implemented.**
An owner choice approving this revision would authorize the harness/workflow and
the bounded external execution below, including the disclosed residual risks.
It would not authorize dependency adoption into released vSEM, product changes,
GPU/private-host execution, main merge or release.

## Question to resolve

Can the unchanged pinned fibsemOS package build in the inspected environment,
discover the independently authored M05A plugin, construct its real classes, use
the supported public-API bindings and run its own Demo imaging service? The
adapter's current synchronous acquisition must still refuse before exposure.
This experiment must not invent a successful vSEM image return to pass the gate.

## Frozen inputs and allowed implementation

| Input | Exact identity |
|---|---|
| vSEM baseline | `0b0b907162a9ca6499bd620b6ef55ad265fafe0e` |
| M05A implementation | `ca6825fb0cdcaa8aa1c4fa176965720757c195ef`; implementation unchanged by later inspection documents |
| Upstream MIT source | `fibsem-os/fibsem-os@27e72f6cc8f9c014562859450ad9260411acaa12` |
| Source archive | SHA256 `d24472e24c6a49fc387412d01590c57b64e338cfcf3479aa80c6da10869ee9ac`; Git tree `0a36bb2516ad632b2fc97cc17cc15f066c35333e` |
| All 52 wheels, including pip 26.3 | [Replacement manifest](../../integrations/fibsemos/review/replacement-artifact-proposal.json), SHA256 `a5e705b56adefa5ba884dbab2dba6ccaf036987648bc1498a05253ebcacd75a2` |
| CPU base, Linux/amd64 | `docker.io/library/python@sha256:0f086103b026048cc50cb5da25ec435c023c5241a83fc44daea593377abc61c4`; exact config and four layers from that manifest |
| Existing checkout action | `actions/checkout@11d5960a326750d5838078e36cf38b85af677262`, already used by the approved CI; credentials not persisted |

No mutable tag, source distribution, alternate wheel, extra, downloaded model or
OS upgrade is a fallback. The original rejected graph stays prohibited. A new
artifact/source identity requires another bounded choice.

Implement only maintainer-authored fixture, bootstrap, inventory and evidence
scripts in `integrations/fibsemos/qualification/`, an isolated
`.github/workflows/fibsemos_cpu.yml`, and supporting review documentation. Freeze
and review the resulting implementation SHA before launch. Keep existing CI,
policy, protected acceptance, both artifact manifests, plugin product source,
core requirements and engine/GUI/API files unchanged. Any product binding repair
identified by this experiment is a reported finding, not implicit repair consent.

The proposed workflow runs only on an explicitly pushed qualification branch,
not on arbitrary contributor PRs. Use a disposable GitHub-hosted Ubuntu 22.04 CPU
VM, with `contents: read`, no secrets or write permissions, no credential
persistence and no new third-party action. Record the runner image, host kernel
and container-engine versions; a hosted runner image is not claimed to be
immutable merely because the client container is pinned. No private workstation,
WSL, self-hosted runner, real-instrument route or GPU is available to the job.

## Fetch and confinement gates

1. A maintainer-owned host script anonymously fetches only the frozen public
   inputs and verifies sizes/hashes/source tree before admission. The exact OCI
   image can be pulled/loaded on this disposable VM after approval. The image and
   upstream code do not run during the network-enabled fetching phase.
2. Run build/import/test with `--network none`, explicit non-root UID/GID,
   read-only root, all capabilities dropped, `no-new-privileges`, the default
   seccomp profile, no host PID/IPC/network namespace and no device additions.
   No Docker socket, runner environment files, repository `.git`, credential,
   private file or host-home mount enters the container. Do not pass through the
   job token, cloud variables, proxy configuration or inherited Python paths.
3. Supply only exact public inputs and reviewed tests as read-only files, plus
   fresh bounded scratch/output mounts. Keep tests separate from package-written
   files. Use a minimal environment and fresh HOME. All HTTP fixtures bind to
   loopback inside the same networkless container; publish no port.
4. Independently check the host-visible container configuration before execution.
   A reviewed probe must confirm UID, mounts, capability restrictions, absence of
   credentials, read-only inputs and failed external network access. Retain this
   evidence separately from package-generated reports. Containers share a kernel;
   these controls reduce exposure and do not prove resistance to all escapes.
5. Use all available CPU capacity. Size scratch/memory ceilings from observed VM
   availability with headroom for its supervisor; do not impose a small blanket
   compute limit. Set a generous finite 180-minute job timeout and record limits.
   A resource/timeout failure is a diagnosed failure, never a reason to weaken
   isolation or use the private GPU. No aggregate task/call budget is introduced.

The controls follow the documented
[Docker execution options](https://docs.docker.com/engine/containers/run/).
They must be verified in the actual job, not accepted on the strength of this plan.

## Installer, build and runtime admission

The base contains pip 25.0.1 and older vendor copies. Do not run that pip, its
launchers or `ensurepip`. Start the base interpreter in isolated/no-site mode
and create a fresh venv **without pip**. Bootstrap only from the verified pip
26.3 wheel, with an explicitly controlled module path and target interpreter.
[pip supports managing a venv without an installed pip](https://pip.pypa.io/en/stable/topics/python-option/).
Verify the loaded installer path/version, venv prefixes and disabled system-site
packages before any package build. Failure to establish that origin blocks the job.

Install the closed wheel list offline using exact hashes, no index, no cache,
no dependency resolution and no source fallback. Verify the installed name/version
set and requirements, including the separate build toolchain. Unexpected dynamic
build requirements stop the build. Runtime discovery uses only the explicit
reviewed entry-point allowlist; omit UI/ML/MCP/agent/vendor extras. Standard
setuptools startup behavior is included in the approved execution boundary.

Build the pinned upstream and unchanged M05A packages in the confined environment.
Upstream build hooks and copied agent assets remain within that boundary. Stop
the builder before a maintainer-owned host inspector reads its output as data.
Require bounded regular files, safe wheel paths/RECORD, expected package metadata,
license material and entry points. Compare source members and copied assets to
the frozen source mapping; classify generated files explicitly. Unexpected code,
dependencies, startup hooks or entry points block runtime admission. Record the
built-wheel hash and full member inventory before installing that exact output
into a fresh runtime environment under the same confinement.

No external package code runs in the host inspector. Do not evaluate report
strings, load pickle/joblib files, run package-produced scripts or extract an
untrusted archive onto the runner host. Test reports are untrusted evidence;
independent assertions and origin/hash checks must substantiate claims.

## Acceptance

| Gate | Required evidence |
|---|---|
| C1 identity and environment | Exact approved source/wheels/config/layers; independent container inspection and negative access checks; new pip origin; no system-site contamination or undeclared distribution |
| C2 actual build | Real upstream build succeeds offline with closed dependencies; built wheel passes static admission and has a recorded SHA256/member inventory |
| C3 genuine discovery | Real upstream registry discovers only the allowlisted plugin; its actual `FibsemMicroscope`, beam and stage classes construct with explicit settings; no fake upstream classes or monkeypatch used as proof |
| C4 API bindings | Against owned observable-only loopback fixtures: supported current, relative focus, stigmation and absolute XYZ writes/readbacks; strict units and bounds; unsupported settings fail before writes; no hidden engine/GUI/evaluator import |
| C5 authority and failures | Refused automatic connection/default restoration; explicit credential handling; lease loss/renewal, timeout uncertainty and no replay; Stop with independent confirmation; fixture and thread cleanup |
| C6 unchanged Demo workflow | Real unchanged upstream Imaging service acquires supported explicit 256x256 and 1024x1024 Demo images; record shape/dtype/settings; only generated arrays and pinned packaged assets, no downloaded specimen/font/video corpus |
| C7 honest vSEM limit | The same supported settings through the plugin reach its existing `QualificationRequired` refusal before any acquisition POST/exposure; invalid defaults also refuse; no newest-image or private-state workaround |
| C8 evidence and cleanup | Independent outcomes, effective dependency/entry-point inventory, artifact/member hashes and bounded logs retained; all owned containers, fixtures and threads stop, including on failure; ordinary project CI still passes |

The Demo result is a software integration smoke test, not an SEM physics
benchmark. CPU HTTP fixtures qualify protocol behavior, not actual numerical
acquisition, dose or realtime timing. Existing 42 M05A tests and original project
acceptance must remain intact. A failure in C1-C8 cannot be changed to a skip or
success simply because the input graph is difficult to support.

Avoid invoking font decoding, URL/video I/O, arbitrary XML/PDF/image import,
telemetry, agent code or real-vendor discovery. These restrictions are part of
the test corpus, not proof that an installed package lacks such functions.

## Evidence, iteration and closeout

Capture external stdout/stderr to bounded files. A trusted host wrapper emits
only escaped or encoded records: never stream package output as GitHub workflow
commands, write it to `GITHUB_ENV`/`GITHUB_OUTPUT`, or interpolate it into shell
commands. Preserve machine-readable inventories, complete test outcomes and
selected diagnostic text in downloadable job logs; collect those logs into the
private maintenance evidence. If limits truncate required evidence, the gate is
incomplete. Do not publish third-party source, wheels, containers or built packages.
The built package is disposable; later adoption requires rebuilding/rechecking
its full bytes, not trusting a previous log or hash alone.

Approval permits implementation and correction of this harness within its stated
paths, isolated reruns with unchanged artifact identities and unchanged criteria,
and factual PR/status updates. Diagnose repeated identical failures; do not retry
blindly. New dependencies, product/API behavior, wider access, altered criteria or
additional input formats require a new owner choice. No maintainer-owned security
or acceptance work is delegated to a local coding model.

After terminal results, audit all outputs against the frozen inputs, preserve
failed evidence and report each gate. Keep PR12 draft. Actual Demo-to-vSEM image
comparison still needs the separately approved public operation/image correlation
feature and isolated GPU/HTTP qualification. Even a passing CPU experiment is
neither main-merge nor release consent.

Rollback is to stop/remove only the job's owned disposable containers and temporary
environment, retain the review evidence, and leave the qualification branch and
optional draft unmerged. The released simulator and private experiments remain
unchanged. A different base/native rebuild proposal can be prepared instead if
the owner does not accept these residual risks for this confined experiment.
