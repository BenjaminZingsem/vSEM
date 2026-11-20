# Release validation

Local release preparation on 5 November 2026:

| Gate | Observed result |
|---|---|
| Independent scientific/boundary/resource suite | 215 discovered; 207 passed, 8 explicit skips |
| Fresh clone in CPU-only Python environment | Same 207 passes; NumPy/SciPy only, no Torch |
| Scan/ROI display retention | 7 behavioral cases passed |
| Histogram/display transfer | 5 valid + 12 rejection cases passed |
| Offline full-world preparation | 9,314,217,887 bytes verified; all 27 codes; 150.44 s |
| Actual GPU/public-HTTP acquisition | Focus, stigmation, XYZ, zoom, ROI and native 1024 passed |
| Within-raster focus change | Same 1024 acquisition contains both applied-focus segments |
| Actual GUI/API isolation | All 7 integration tests passed |
| Fixture shutdown | Launcher exit 0; owned children absent |
| Fresh clone + empty GPU environment | Full GPU/HTTP gate passed; 1024 acquisition 121.72 s; clean shutdown |
| Source/content review | No retained run credentials, large artifacts or external image assets |
| Scientific source scope | 77 engine ASTs unchanged except explicit device configuration |

The 1024 acquisition with a focus change took 126.83 seconds in the first release
fixture, including preparation/rendering. It was not delivered ahead of exposure.
Focused 64-pixel contrast standard deviation was 101.36 counts versus 84.37 when
defocused; Z defocus was 83.70. These are measured smoke-test observations, not
calibration claims or hardware-independent performance guarantees.

The supported GPU/dependency installation also succeeded in an empty virtual
environment. The fresh clone passed the full GPU/HTTP gate, including signed
stage displacement (correlation 0.9115) and both within-raster focus segments.
Its implementation commit is `9cf689f8d01f2f95e58d511841f1156866f0ff58`;
subsequent release changes record documentation and provenance only.
See [first fixture](release-validation.json) and
[fresh-install fixture](fresh-install-validation.json) for the measured results.
Hardware: RTX 3090 Ti, 24 GB; WSL2 Ubuntu, Python 3.10.12, NumPy 1.26.4,
SciPy 1.15.3, Torch 2.3.1+cu121, Triton 2.3.1. See the pinned requirements and
constraints files for the transitive dependency versions.

## Reproduce CPU and display gates

Use the commands in README.md. No GPU test is silently selected during ordinary
discovery. Eight transport integration tests and one command/image association
test require the explicit environment variables below; the one historical
saved-tape test is skipped because those private recordings are not distributed.
All other tests must pass. Dated test totals below describe their named revisions.

## Actual GPU / HTTP release gate

On an approved idle GPU, after preparing the finite catalogue:

```bash
python -B scripts/qualify_release.py \
  --catalogue-directory data/sample-1280um \
  --catalogue-manifest-sha256 PASTE_MANIFEST_SHA256 \
  --output runs/release-check-001
```

This starts a transient foreground runtime on ephemeral loopback ports, uses the
public HTTP API to acquire images, and closes its owned server/children afterward.
It checks visible focus/stigmation, XYZ response, image displacement, physical zoom,
ROI, actual 1024 counts, mid-raster parameter segments, exposure pacing, observable
state and Stop. Raw acceptance acquisitions are saved in the ignored output folder.

Cleanup requires a successful launcher exit and disappearance of its recorded
child process identities. After launcher exit, the qualifier observes those
identities for up to five seconds to allow helper finalization. A reused PID with
a different birth identity is distinct from the original child. A live child,
zombie or unreadable identity remaining at the deadline fails qualification.
The observer sends no signals and performs no reaping. It retains the initial
identities, observed states and elapsed wait in the private `result.json`.
This process-exit interval does not extend exposure or replace the separate Stop
check. A failed result must be investigated and retained, not rerun until green.

Separately qualify transport isolation on the same hardware:

```bash
export VSEM_TEST_CATALOGUE="$(realpath data/sample-1280um)"
export VSEM_TEST_CATALOGUE_SHA256=PASTE_MANIFEST_SHA256
python -B -m unittest acceptance.test_finite_transports
python -B -m unittest acceptance.test_operation_acquisitions_gpu
```

The tests check distinct GUI/API credentials, invitation/CSRF, denied private
routes and fields, control ownership, live evolution without requests and acquired
count access. They close their transient service. Do not run two GPU fixtures
concurrently or bypass the ownership lock.

The association case uses the same qualified core environment and actual public
HTTP API. It checks a native1024 partial/final cut with both within-raster focus
segments, compares the cut's raster with the independently retained immutable
image identity, applies a live configuration, freezes its final raster and checks
interrupted single-image delivery after Stop. All owned threads and physical/
numerical processes must close. It runs no external adapter or fibsemOS payload.

The added live-receipt case starts a 64-square live raster, applies a 128-square
configuration, freezes a matching complete frame and confirms both individual
operation receipts. It separately confirms Stop generation advance, raw count
dimensions, exposure pacing and absence of private diagnostic fields. CPU-only
regressions cover request versus application, supersession, cancellation, event
ordering, queue-refusal accounting, POSIX output privacy and controlled worker
diagnostics. These checks do not reproduce the cause of a real numerical fault.

CPU hosted CI cannot qualify CUDA behavior, performance, or visual usability.
Fresh-clone setup and all GPU changes require a recorded local acceptance run;
human review remains the instructions in HUMAN_REVIEW.md.

## Operator-integration maintenance qualification, 10 November 2026

Reviewed implementation: `94ce4804e64bf06ca645cb1cda969155892802ab`, in
[PR9](https://github.com/BenjaminZingsem/vSEM/pull/9). Later documentation-only
updates do not alter the qualified runtime, qualifier or tests.

| Gate | Observed result |
|---|---|
| Final Linux CPU suite | 253 discovered; 244 passed; 9 explicit skips |
| GPU skip coverage | All 8 opt-in transport tests passed separately in 61.27 s |
| Remaining CPU skip | One historical private saved-tape fixture is not distributed |
| Actual GPU/public HTTP release gate | All 11 acquisition/authentication/observable/Stop checks passed |
| Native 1024 with mid-raster focus | 123.37 s, 2 applied-focus segments, complete native counts |
| Shutdown | Launcher exit 0; all 3 recorded child identities absent at first observation |
| Owned fixture groups and GPU | Both groups absent; selected GPU returned to 0 MiB |
| Native POSIX output privacy | Output directory 0700; service.log 0600 |
| Display checks | 7 retention cases; 5 valid and 12 rejected transfer cases passed |
| Source invariants | All 77 engine files, original numerical loop and existing transport test functions unchanged |

The hardware and qualified dependency versions are the same RTX 3090 Ti/WSL2
configuration recorded above. The cleanup observer needed less than 0.001 s in
this run; deterministic tests separately exercise delayed exit and persistent
live/zombie/unknown failures. This successful run does not identify the child
in the earlier failed immediate-cleanup observation. Failed evidence is retained.
The actual numerical cause of the historical `BANK_FAILED` report remains
unknown; controlled diagnostics tests are not a numerical failure reproducer.
Final hosted PR/integration and post-merge checks remain independently required.

## Public operation/image association, 20 November 2026

The [M05B2A specification](proposals/FIBSEMOS_M05B2A_CORRELATION_PLAN.md) adds an
API-only read projection over verified causal facts and immutable numerical
publication. Original receipts, images, authentication, all 77 engine files and
original acceptance/workflow bytes remain unchanged. It adds no dependency.
Reviewed implementation: `29c3f3406f56430c804fb62a4be96d84589c7f1b` in
[PR13](https://github.com/BenjaminZingsem/vSEM/pull/13). Subsequent documentation
edits preserve all qualified executable/test bytes.

| Gate | Observed result |
|---|---|
| Linux CPU suite | 277 discovered; 267 passed; 10 explicit skips |
| New independent CPU/HTTP checks | 23 passed: fact ordering, genuine scalar identities, supersession, failures, closed fields, GUI ownership, exact auth/path refusals and read-only GET/Stop admission |
| New actual GPU/public HTTP case | Native 1024 partial/final attribution with both focus segments; live/configure/freeze and interrupted single acquisition passed in 219.95 s |
| Original GPU release gate | All 11 checks passed; native 1024 with two focus segments in 125.21 s |
| Original GPU transport suite | All 8 cases passed in 52.82 s |
| Display gates | 7 retention cases; 5 valid and 12 rejected transfer cases passed |
| Independent provenance/content review | Exact approved source scope; original auth and artifact I/O unchanged; exported publication guard and local links pass |
| Cleanup | All 3 owned qualification groups absent; launcher exit 0; all 3 tracked release children absent; selected compute GPU returned to its initial 280 MiB |

Ten CPU skips are explicit: the original eight opt-in GPU transport cases, the
new opt-in GPU association case, and one undistributed historical saved-tape
fixture. All nine opt-in GPU cases passed separately. Hardware/environment is the
same named RTX 3090 Ti/24 GB, WSL2 Ubuntu/Python 3.10.12 and pinned dependency versions
above. The independent evidence audit rehashed logs and all 158 tested source
files against the candidate. Hosted CI must independently pass on the actual
head/integration and post-merge main; local evidence does not replace that gate.

This is core API qualification. No external fibsemOS payload ran privately, no
optional adapter was merged, and no new release or human-review server was
launched. Genuine cross-stack image return remains a separate M05B2B gate.
