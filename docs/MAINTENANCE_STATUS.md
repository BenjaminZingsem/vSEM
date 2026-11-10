# Maintenance status

Last verified: **10 November 2026**.

| Item | State |
|---|---|
| Simulator | v0.1.0 research release; generic/uncalibrated; charging and damage inactive |
| Policy | Owner-account mode selected; external-code incorporation and feature implementation require owner choices in chat |
| Account | Existing `BenjaminZingsem` GitHub login verified; no separate bot required |
| Continuous maintenance goal | Initialized separately; approved operator-integration repairs and cleanup extension qualified; further features require an owner choice |
| Earlier experimental goal | Retired by the owner on 6 November; preserve source/evidence; clearing its interface entry is user-controlled |
| Main protection | Owner chose to leave permissions unchanged on 6 November: main remains unprotected and direct pushes remain available; prepared configuration is not applied |
| CI | Catalogue read-ahead fix and two new regressions included; local CPU and actual GPU/HTTP gates pass; hosted results are in [Actions](https://github.com/BenjaminZingsem/vSEM/actions/workflows/ci.yml) |
| Human-review instance / local coding wave | No persistent human instance or local coding wave; qualification uses owned transient fixtures |
| Queue | Qualified repairs for #5-#8 are in PR9; #4 has a reporter correction withdrawing its upstream cleanup inference. Consult GitHub for current issue/merge state. |

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

## Qualified operator-integration repairs, 10 November

The owner approved implementation, independent qualification and reviewed merge
of [live receipts (#5)](https://github.com/BenjaminZingsem/vSEM/issues/5),
[private diagnostics (#6)](https://github.com/BenjaminZingsem/vSEM/issues/6),
[qualifier permissions (#7)](https://github.com/BenjaminZingsem/vSEM/issues/7) and
[queue-refusal accounting (#8)](https://github.com/BenjaminZingsem/vSEM/issues/8).
The candidate adds no dependency and changes no engine file or numerical loop.

Final candidate evidence: 253 Linux CPU tests, 244 passed and nine explicit
skips (eight separate GPU transport cases and one private historical fixture).
Windows focused regressions and 14 catalogue tests pass; POSIX-only cases skip
on Windows. Display retention and intensity-transfer checks pass. Original-source
comparisons reproduce the receipt, rejection-accounting and permission problems,
and the missing controlled-worker diagnostic.

An earlier candidate passed every acquisition check but failed the immediate
child-absence assertion; its failed evidence remains retained. A later baseline
run passed, and finite multiprocessing probes showed an instantaneous observation
hazard. Those observations do not identify the child in the original full-run
failure or establish a production failure rate.

The owner separately approved a five-second, birth-identity-aware exit observation.
It sends no signals, performs no reaping and fails on a remaining live process,
zombie or unknown identity. Deterministic tests exercise delayed exit, persistent
children, read errors and PID reuse. The final implementation `94ce480` passed
all 11 actual GPU/HTTP release checks, including a native 1024 acquisition in
123.37 seconds with two focus segments. Launcher exit was 0 and all three
recorded children were already absent at the first observation. All eight actual
GPU transport tests passed in 61.27 seconds, including configure/freeze receipts.
Both fixture process groups were empty afterward and the selected GPU returned
to 0 MiB. Native POSIX output/log modes were verified as 0700/0600.

All 77 engine files, the original numerical loop and existing transport test
functions remain unchanged. No dependency or public diagnostic route was added.
See [validation](VALIDATION.md) and [PR9](https://github.com/BenjaminZingsem/vSEM/pull/9)
for the final scope and hosted integration checks. Local qualification does not
replace successful acceptance CI on the final PR/integration and merged main.
The underlying numerical failure reported in #6 remains unidentified; diagnostics
are not presented as a solver repair or permission to clear an interlock.
