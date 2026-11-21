# M05B2B1A revision 2: separate VM prerequisite

21 November 2026. **Proposal only. No host change authorized by this document.**

The owner approved the [revision 1 preservation/update/probe scope](FIBSEMOS_M05B2B1A_ISOLATION_DECISION.md).
Preservation is running; [the checkpoint](FIBSEMOS_M05B2B1A_RESULT.md) records its
actual state. The original Desktop-only update cannot establish an admitted fresh
WSL store or satisfy a separate WSL isolation prerequisite. Revision 1 explicitly
requires stopping for an unsupported fresh-store admission or newly needed host
dependency. No installer, engine or external payload has run.

## Concrete alternative

Use the same reviewed Docker Desktop 4.100.0/build246961 installer and exact
Python OCI base, with Docker VMM (Beta) selected before first engine startup.
[Docker documents](https://docs.docker.com/desktop/features/vmm/) a separate VM
boundary on Windows and requires Windows Hypervisor Platform plus Virtual Machine
Platform. This avoids changing the existing WSL/kernel/GPU toolchain. It changes
the Desktop backend and enables a Windows feature, so the original approval
does not cover it. Beta status and host-wide virtualization effects are material.

Proposed sequence if option 1 below is selected:

1. Finish the existing source-locked cold copy and its separate full readback.
   Independently audit the complete receipt set, original identities and secured
   backup ACLs. An incomplete, inconsistent or failed result stops all host writes.
2. With Windows administrator consent, enable only the existing Windows
   `HypervisorPlatform` feature using
   `Enable-WindowsOptionalFeature -Online -FeatureName HypervisorPlatform -NoRestart -LimitAccess`.
   Do not use `-All`, fetch a source, contact Windows Update, enable full Hyper-V,
   install a kernel/driver or change networking. Missing local payload or another
   dependency stops this action. The existing VirtualMachinePlatform stays as is.
   Microsoft's [parameter reference](https://learn.microsoft.com/en-us/powershell/module/dism/enable-windowsoptionalfeature)
   documents suppression of automatic restart and Windows Update sourcing.
3. If Windows requires a reboot, save evidence and stop. The owner restarts at
   their convenience after preservation finishes, then explicitly returns. No
   reboot, logon task, scheduler, watcher or automatic Codex restart is permitted.
   This same bounded approval persists after that return; first reverify state.
4. Recheck the exact signed installer and retained all-users mode. Perform the
   approved update with `install --quiet`, the existing installation directory
   and the documented `--backend=docker-vmm` selection. This revision replaces
   revision 1's instruction to retain the WSL backend; it does not change the
   approved bytes. Do not use `--accept-license`, enable optional products or sign
   in. A new agreement, forced dependency/reboot or changed artifact stops work.
5. Before engine startup, inspect installed vendor configuration and prove that
   the selected backend will use a fresh owned VM store in Docker's normal
   profile-owned VM data location, previously absent at inspection. Preserve all
   existing WSL disks/registrations offline; do not import, migrate, mount, delete,
   reset or unregister them. A selection flag alone is still insufficient. If
   supported inspected configuration does not establish fresh-store separation,
   stop. Do not invent offline keys or use an old engine to inspect its contents.
6. Start only the admitted owned VM engine. Pin observed bundled binaries,
   configuration, guest kernel and runtime. Verify the old Docker WSL distribution
   remains stopped and the fresh engine has no pre-existing containers/images.
   Preserve native write/delete exclusion on the original WSL disks during the
   qualification where compatible with the proven VM configuration. No original
   data becomes a test mount. Any unrelated workload or automatic substitution
   stops the experiment and triggers owned cleanup.
7. Run only the authored standard-library CPU confinement probes already specified
   in revision 1, using the same pinned OCI digest. Inspect containers before
   execution; require actual namespace, privilege, mount, network and host-sentinel
   negative tests. No fibsemOS, wheel installation, adapter, actual vSEM server or
   GPU compute. No new package/artifact or private transport is admitted.
8. Audit and close every owned fixture/engine, preserve all data/evidence and
   publish draft results only. No main/PR12/PR14 merge or release. Genuine
   cross-stack transport/GPU work remains a later separately reviewed choice.

No new source dependency, Python base or vendor-installer substitution is proposed.
The new host effects are the named Windows feature, explicit VM backend selection,
normal vendor-owned configuration/VM store creation and transient qualification.
No account, group, GitHub permission, credential or repository-rule change.
Resource envelopes follow measured availability; no arbitrary small RAM/CPU cap.
All original scientific, observable-state, GUI/API and acceptance contracts remain.

## Owner choices

1. **Approve this exact VM prerequisite extension and conditional CPU probe scope.**
   Permit the sequence above, including Windows administrator consent, the named
   offline feature enablement and changed backend. A required reboot is an
   explicit owner-handled checkpoint. Fresh-store proof and all original negative
   tests remain mandatory. This is not approval for external payloads or merge.
2. **Owner-managed fresh environment.** Finish preservation, leave further host
   changes pending and let the owner provide a fresh patched VM-backed Docker
   environment. Inspect and pin its actual identity/store, then present the
   concrete probe admission before any execution. Do not infer trust from a CLI.
3. **Defer local qualification.** Finish preservation only; retain the CPU-qualified
   draft adapter and all evidence without any installer/backend/feature change.

The VM alternative is recommended for independent isolation if the owner accepts
the host feature, possible reboot and Beta backend. An owner-managed environment
is the lower-intervention alternative. Neither choice waives the fresh-store gate.

Rollback is closing owned probes/engine and retaining original disks/configuration.
Enabling a host feature or changing a vendor backend is not reversed by Git revert.
Feature disablement, downgrade, disk restore, reset, migration or restarting the
old store requires a separately reviewed recovery action. No automatic rollback
may overwrite private data. Preserve the cold backup throughout.
