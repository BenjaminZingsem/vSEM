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
discovery. Seven transport integration tests require the explicit environment
variables below; the one historical saved-tape test is skipped because those
private recordings are not distributed. All other tests must pass.

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

Separately qualify transport isolation on the same hardware:

```bash
export VSEM_TEST_CATALOGUE="$(realpath data/sample-1280um)"
export VSEM_TEST_CATALOGUE_SHA256=PASTE_MANIFEST_SHA256
python -B -m unittest acceptance.test_finite_transports
```

The tests check distinct GUI/API credentials, invitation/CSRF, denied private
routes and fields, control ownership, live evolution without requests and acquired
count access. They close their transient service. Do not run two GPU fixtures
concurrently or bypass the ownership lock.

CPU hosted CI cannot qualify CUDA behavior, performance, or visual usability.
Fresh-clone setup and all GPU changes require a recorded local acceptance run;
human review remains the instructions in HUMAN_REVIEW.md.
