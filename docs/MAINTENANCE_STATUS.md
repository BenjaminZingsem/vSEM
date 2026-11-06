# Maintenance status

Last verified: **6 November 2026**.

| Item | State |
|---|---|
| Simulator | v0.1.0 research release; generic/uncalibrated; charging and damage inactive |
| Policy | Owner-account mode selected; external-code incorporation and feature implementation require owner choices in chat |
| Account | Existing `BenjaminZingsem` GitHub login verified; no separate bot required |
| Continuous maintenance goal | Not started by policy/setup publication |
| Earlier experimental goal | Paused; preserve separate source and handoffs |
| Main protection | Owner chose to leave permissions unchanged on 6 November: main remains unprotected and direct pushes remain available; prepared configuration is not applied |
| CI | Catalogue read-ahead fix and two new regressions included; local CPU and actual GPU/HTTP gates pass; hosted results are in [Actions](https://github.com/BenjaminZingsem/vSEM/actions/workflows/ci.yml) |
| Human-review instance / local coding wave | None launched for this setup |
| Queue | No open issue/PR at preceding planning inspection; activation must recheck |

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

Use [the setup guide](MAINTENANCE_SETUP.md) to activate and
[the roadmap](ROADMAP.md) for delivered capabilities and next gates. This page is
a dated record, not a live monitor. Update it when the goal starts, pauses, changes
phase or reaches a material blocker. Link public PR/test evidence without private
run credentials, hidden scenario data or approval transcripts.
