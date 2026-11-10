# Maintenance status

Last verified: **10 November 2026**.

| Item | State |
|---|---|
| Simulator | v0.1.0 research release; generic/uncalibrated; charging and damage inactive |
| Policy | Owner-account mode selected; external-code incorporation and feature implementation require owner choices in chat |
| Account | Existing `BenjaminZingsem` GitHub login verified; no separate bot required |
| Continuous maintenance goal | Initialized separately; owner approved the bounded operator-integration repair batch below |
| Earlier experimental goal | Retired by the owner on 6 November; preserve source/evidence; clearing its interface entry is user-controlled |
| Main protection | Owner chose to leave permissions unchanged on 6 November: main remains unprotected and direct pushes remain available; prepared configuration is not applied |
| CI | Catalogue read-ahead fix and two new regressions included; local CPU and actual GPU/HTTP gates pass; hosted results are in [Actions](https://github.com/BenjaminZingsem/vSEM/actions/workflows/ci.yml) |
| Human-review instance / local coding wave | No persistent human instance or local coding wave; qualification uses owned transient fixtures |
| Queue | Five open reports at inspection: #4 has a reporter correction withdrawing the upstream cleanup inference; #5-#8 form the approved repair batch |

The owner chose procedural maintenance safeguards instead of GitHub branch
protection. Continue reviewed PRs, the successful GitHub Actions `acceptance`
check (App 15368), and explicit chat choices under the maintenance policy.
Do not apply the prepared protection configuration without a new owner request.

Earlier main run [42211474688](https://github.com/BenjaminZingsem/vSEM/actions/runs/42211474688)
failed the existing concurrent specimen-file change test. The owner approved
the independently written fix `b3066b0` for publication and merge after successful
CI. The fix uses raw reads and preserves chunk sizes across short reads; original
size, identity and hash checks remain. Both added regressions fail against the
original implementation and pass with the fix; original tests are unchanged.

Local qualification: Windows catalogue suite 14 passed; Linux suite 215 passed
with eight expected skips. Actual GPU/public HTTP focus, stigmation, stage XYZ,
zoom, ROI, observable state, Stop and 1024-pixel acquisition with two within-raster
focus segments passed. The 1024 acquisition took 133.16 seconds on the qualified
RTX 3090 Ti. The owned launcher exited successfully, children closed and GPU
memory was released. This repair adds no dependency and does not activate a goal.

The replacement [goal contract](../prompts/CONTINUOUS_MAINTENANCE.md) defines the
initial verification-and-pause checkpoint, normal maintenance priorities,
explicit owner choices, local coding boundaries and acceptance/handoff rules.
Publication alone did not activate it. Initialization is now complete. The retired completion goal's blanket
development authority does not carry over; its unfinished experiments remain
available for individually approved roadmap work.

Use [the setup guide](MAINTENANCE_SETUP.md) to activate and
[the roadmap](ROADMAP.md) for delivered capabilities and next gates. This page is
a dated record, not a live monitor. Update it when the goal starts, pauses, changes
phase or reaches a material blocker. Link public PR/test evidence without private
run credentials, hidden scenario data or approval transcripts.

## Operator-integration repairs, 10 November

The owner approved implementation, independent qualification and reviewed merge
of [live receipts (#5)](https://github.com/BenjaminZingsem/vSEM/issues/5),
[private diagnostics (#6)](https://github.com/BenjaminZingsem/vSEM/issues/6),
[qualifier permissions (#7)](https://github.com/BenjaminZingsem/vSEM/issues/7) and
[queue-refusal accounting (#8)](https://github.com/BenjaminZingsem/vSEM/issues/8).
The candidate adds no dependency and changes no engine file or numerical loop.

Current candidate evidence: 247 Linux CPU tests, 238 passed and nine explicit
skips (eight separate GPU transport cases and one private historical fixture).
Windows focused regressions and 14 catalogue tests pass; POSIX-only cases skip
on Windows. Display retention and intensity-transfer checks pass. Original-source
comparisons reproduce the receipt, rejection-accounting and permission problems,
and the missing controlled-worker diagnostic.

Qualification is not yet complete. All 11 GPU/public-HTTP acquisition checks
passed, including native 1024 with two focus segments, but the qualifier's final
immediate child-absence assertion failed. The later owned process group was
absent. That distinction is retained; no assertion or status has been weakened.
All eight separate GPU transport tests pass, including live configure/freeze
terminal receipts. The unchanged baseline passed under read-only diagnostic
observation. A separate finite multiprocessing reproduction demonstrated a
timing hazard in immediate absence checks, including still-exiting helpers;
live reaping alone did not make the immediate check reliable. This does not
identify the unobserved child in the failed full qualification.

A separate local proposal adds a five-second, birth-identity-aware exit
observation to the qualifier. It does not kill processes or treat a present
zombie as absent, and it fails when an owned child remains at the deadline.
Deterministic CPU cases and 24 real subprocess lifecycles pass. It has not been
integrated or GPU-qualified; changing cleanup acceptance beyond the approved
permission fix requires an additional owner choice. The repair remains a
[draft PR](https://github.com/BenjaminZingsem/vSEM/pull/9); both hosted acceptance
jobs passed for implementation `e2853a0`.
Do not merge or describe this candidate as fully qualified until those gates pass.
The underlying numerical failure reported in #6 remains unidentified; diagnostics
are not presented as a solver repair or permission to clear an interlock.
