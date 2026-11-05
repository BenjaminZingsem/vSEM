# Release validation

Release gates are recorded here after execution; qualification is in progress.
Do not treat this draft as a passed GPU release.

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
