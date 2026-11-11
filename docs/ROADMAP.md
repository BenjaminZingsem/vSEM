# Project status and roadmap

Last reviewed: **11 November 2026**. Released: **v0.1.0**, an MIT-licensed research
sandbox. The broader implementation goal is **retired by the owner**;
there is no unattended maintenance service. The owner-account maintenance policy
and launch instructions are published; initialization is complete and the owner
approved the now-merged repair batch described below. See [setup](MAINTENANCE_SETUP.md) and
[status](MAINTENANCE_STATUS.md).

## What works today

| Area | Public status | Evidence / limits |
|---|---|---|
| Core imaging and control | Released | Stage XYZ, focus, two-axis stigmation, physical field width/zoom, live scans, alignment ROI and native 1024 acquisition. [GUI walkthrough](GUI_WALKTHROUGH.md). |
| Acquisition semantics | Released | Timed exposure, partial images, applied-parameter segments, dose accounting and Stop. Numerical delivery may take longer than modeled exposure. [Validation](VALIDATION.md). |
| Specimen | Released, bounded scope | Finite offline-prepared 1.28 mm procedural specimen; exterior vacuum; runtime generation disabled. |
| GUI and instrument API | Released for trusted development | Separate principals/transports over one causal engine; observable-only API. This is not OS confinement for hostile agents. [API](API.md). |
| Documentation and CI | Released | Setup, API example, review checklist, seven real GUI screenshots, CPU/display/content checks. GPU qualification is a separate manual gate. |
| Charging and beam damage | Not active in the release | Experimental work exists separately and still needs integration/qualification. Spatial material codes alone are not physical feedback. |
| Calibration, persistent replay and hostile-agent confinement | Not delivered | See R04–R06 below and [scientific scope](SCIENCE.md). |

Reports #5-#8 are resolved by merged [PR9](https://github.com/BenjaminZingsem/vSEM/pull/9)
with passing post-merge CI. #4 is closed following its reporter correction.
[Issue #10](https://github.com/BenjaminZingsem/vSEM/issues/10) requests a fibsemOS
plugin; the [bounded M05 proposal](proposals/FIBSEMOS_INTEROP.md) awaits owner choice.
Consult
[live issues](https://github.com/BenjaminZingsem/vSEM/issues) and
[pull requests](https://github.com/BenjaminZingsem/vSEM/pulls) for current activity;
the dated observation above is not a live status indicator.

## Work order and acceptance

Verified security problems, scientific/data-integrity regressions and reproducible
core-imaging bugs take precedence over feature work. An open request is not
automatically accepted scope. When no actionable defect remains, select the next
approved, unblocked roadmap slice. Before implementing a new feature or incorporating
external code, interrupt and present concrete choices to the owner in chat. Listing
a feature here does not approve implementation. A request awaiting reproduction or
a decision need not prevent independent already-authorized work.

The IDs below preserve the existing post-release priorities. They are not release
dates or permission to begin every item. They should become small issues/PRs with
explicit acceptance criteria when work is authorized.

| ID | Deliverable | Current status | Required acceptance / dependencies |
|---|---|---|---|
| R00 | Supervised repository maintenance | Initialized; first approved repair batch merged and main verified | Use the [maintenance policy](MAINTENANCE_POLICY.md), existing owner account and explicit chat choices before external code/features. Verify account, approved revision, execution boundaries and chosen PR/CI protection. Shared-account chat approval is a procedural gate, not independently enforced by GitHub. |
| R01 | Support a separate AI-operator project | API/example released; M05 fibsemOS proposal awaiting owner choice; broader task harness planned | [M05](proposals/FIBSEMOS_INTEROP.md) preserves raw counts, observable state and truthful outcomes in an optional SEM plugin. Exact external adoption and genuine Demo/vSEM workflow qualification remain separate gates. Reproducible focus, stigmation, stage, zoom, ROI and 1024 tasks need observable histories and documented failure cases. Agent learning/policy code belongs in its own project. |
| R02 | Causal charging, damage and spatial material response | Experimental, not integrated | Independently verify exposure history, conductivity/sensitivity combinations, changes within a raster, timing and numerical accuracy. Qualify full-frame performance and human-visible scenarios before integration. No decorative effects or claims based only on code presence. |
| R03 | Performance, storage and hardware coverage | Qualified baseline; expansion planned | Measure startup, repeated scans, ROI, zoom and 1024 delivery on named hardware; improve cache/chunk/storage behavior without changing scientific bounds or dose/timing. Qualify each additional GPU explicitly. May proceed in independent slices alongside R01/R02. |
| R04 | Crash-durable replay and bounded storage retention | Planned | Versioned records, recovery from interrupted writes, acquisition-time/partial-frame fidelity, retention controls and tested migration/rollback. Buffered development records do not meet this gate. |
| R05 | Deployment for untrusted evaluated agents | Planned; required before hostile evaluations | Audited process/filesystem/network separation; private evaluator/scenario data inaccessible to the operator; negative access tests and explicit threat model. Trusted API experiments in R01 do not require claiming this is already solved. |
| R06 | Broader SEM controls and calibrated profiles | Planned; evidence dependent | Research actual SEM interactions, implement causal behavior for each control, validate against measured references and qualify human usability. Keep unsupported controls absent/disabled and generic profiles labelled uncalibrated. |

Merged maintainer-owned batch: truthful configure/freeze lifecycle (#5), bounded
private preparation diagnostics and terminal-fault documentation (#6), private
qualification output (#7), and bounded refusal accounting (#8). The separately
approved finite cleanup observer preserves failure for remaining live/zombie or
unknown process identities. Implementation `94ce480` passes 244 CPU cases,
all 11 actual GPU/HTTP release checks and eight GPU transport cases; native1024
retains both focus segments and owned fixtures close cleanly. Nine CPU skips
are explicit and documented in [validation](VALIDATION.md). No
broader physical control, charging/damage integration or new roadmap slice is
approved by this batch. Core SEM imaging and useful automation scenarios
take priority over image editing, analysis and unrelated peripheral features.

## Keeping this page accurate

Update this page with each merged change that affects capability, milestone
status, accepted priority, a blocker or qualification evidence. Each active slice
must name its issue/PR, responsible maintainer, acceptance criterion and next gate.
Use **Planned**, **In progress**, **Awaiting review**, **Blocked**, **Merged** and
**Released** distinctly. Record why a blocker exists; attach test/commit evidence
before marking a milestone complete. A merged change is not necessarily released.

Update [HUMAN_REVIEW.md](HUMAN_REVIEW.md) and the GUI walkthrough when interactions
change; keep scientific limits and API documentation consistent. A release should
summarize delivered changes and known limitations. Do not publish private local
paths, credentials, hidden specimen/evaluator data or sensitive vulnerability
details as progress evidence.

Policy changes and roadmap implementation scope require the owner's decision. The
[continuous goal prompt](../prompts/CONTINUOUS_MAINTENANCE.md) describes how a
future maintenance run would use this roadmap; merely committing it does not
start a service or reactivate the retired completion mandate.
