# M05B2B1A preservation and local-isolation checkpoint

21 November 2026. **In progress; no local execution envelope qualified.**

The owner selected option 1 of the immutable
[revision 1 proposal](https://github.com/BenjaminZingsem/vSEM/blob/5cf12538d3ff7752e1d45eb96a511a8b827c0451/docs/proposals/FIBSEMOS_M05B2B1A_ISOLATION_DECISION.md).
The scope covers opaque cold preservation, the exact signed vendor update,
strict fresh-store admission and authored standard-library CPU confinement probes.
It permits draft evidence publication only. It does not admit private fibsemOS
execution, wheel installation, actual vSEM/GPU experiments, adapter integration,
main/PR12/PR14 merge or a release.

## Observed state

| Gate | Current evidence |
|---|---|
| Preserve existing data | Cold copy running with native source write/delete exclusion; separate full destination readback required before acceptance |
| Preservation acceptance | Six native Windows copy/locking/readback cases pass; 17 independent receipt/ACL cases pass; actual complete backup still pending |
| Vendor update | Exact approved installer identity rechecked as data; execution held until complete preservation passes |
| Fresh owned store | Not admitted; a default path or a CLI context alone is insufficient |
| Local confinement probe | Not run; requires admitted updated runtime and empty owned store |
| Private external/actual GPU experiment | Not authorized by this scope |

Authored preservation/audit scripts and detailed receipts remain private because
they contain machine-specific paths and identify opaque existing data. No backup
payload, private configuration, credentials or host vulnerability inventory is
included here. The updater will not accept a new license, reboot, install an
additional dependency or silently change WSL/kernel/backend/network settings.

## Admission findings

The documented [disk-location setting](https://docs.docker.com/desktop/settings-and-maintenance/settings/)
and [installer default-data-root flag](https://docs.docker.com/desktop/setup/install/windows-install/)
do not establish that an existing installation will start with an empty store.
Starting the old engine and listing its containers afterward cannot exclude an
automatic unrelated restart. Unsupported offline edits, deletion, reset and
distribution re-registration are outside the approved procedure.

The current [vendor release notes](https://docs.docker.com/desktop/release-notes/#4980)
also identify a WSL-specific AF_VSOCK isolation fix with a separate WSL version
prerequisite. The approved Desktop artifact alone cannot be assumed to satisfy
that prerequisite. No exploit or external package has been executed to test it.
A newly required WSL/backend change needs a separate owner choice.

The [separate VM prerequisite proposal](FIBSEMOS_M05B2B1A_VM_EXTENSION.md)
offers the concrete next choice. Its feature/backend/reboot scope is unapproved.
Keep the original installer held while that choice is pending; preservation
continues independently. Do not weaken acceptance or treat an authentic installer
as proof of isolation. No other process automatically applies the update.

## Preserved integration boundary

Main remains `2e18bdafadab22c56a64cc16cc344bcd5a0bb0c1`.
[PR14](https://github.com/BenjaminZingsem/vSEM/pull/14) remains draft at
`354e851115d2afe746c8f199b256aea713e10747`; its public CPU image-return evidence
does not establish actual-engine/GPU interoperability. PR12 remains unchanged.
GUI/API/evaluator separation, observable-only operator state, physical time/dose,
partial scans and independent acceptance remain mandatory. The v0.1.0 release
is unchanged. No persistent human-review server or local coding wave is running.
