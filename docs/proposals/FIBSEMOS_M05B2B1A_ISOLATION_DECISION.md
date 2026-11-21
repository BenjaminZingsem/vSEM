# M05B2B1A: local toolchain admission before actual-engine qualification

Revision 1, 21 November 2026. **Proposal only; owner choice required.**
Tracks [issue10](https://github.com/BenjaminZingsem/vSEM/issues/10).

## Current boundary

The core public operation/image association is merged at
`2e18bdafadab22c56a64cc16cc344bcd5a0bb0c1` (PR13).
Optional adapter [draft PR14](https://github.com/BenjaminZingsem/vSEM/pull/14)
is frozen at `354e851115d2afe746c8f199b256aea713e10747`; its final public CPU
qualification44775392511 and head/integration acceptance44775392645/44775403532
pass. Original PR12 remains draft and unchanged. No optional adapter is in main.

Configured upstream256/1024 image return passed against authored CPU HTTP data,
with exact uint32 companions, fixed-window views, truthful receipt/cut ordering,
reconciliation and independent Stop/renewal. This is not actual GPU-engine
interoperability. Its source,52wheel/OCI inputs and acceptance remain frozen.

No private execution envelope has been admitted for that next experiment. The
resumed read-only review found a local toolchain/storage prerequisite. Exact
private host inventories and preservation requirements are retained privately.
Do not infer readiness from an installed CLI, stopped VM, public CI, a worktree
or an ordinary WSL session. Do not start an old data store whose automatic
container restart behavior has not been excluded.

## Concrete update candidate, inspected as data

The following vendor installer was quarantined, not executed:

| Item | Inspected identity |
|---|---|
| Product | Docker Desktop4.100.0, Windows amd64, build246961, released19November2026 |
| Installer | `https://desktop.docker.com/win/main/amd64/246961/Docker%20Desktop%20Installer.exe` |
| Published checksum | [Exact vendor checksum](https://desktop.docker.com/win/main/amd64/246961/checksums.txt) |
| Bytes | 625266608 |
| SHA256 | `cf205d1ebc269f1114beb03924ed5fdb3763b38732115e3729a791488c3bde5d` |
| Windows signature | Valid Authenticode, Docker Inc; signer thumbprint `B6BD29272B07AD4D0F1322A739499D67CA3BAC3F` |

An authentic installer is not isolation qualification. Docker lists multiple
host/engine security fixes and notes storage migration on first start of this
release. Existing data must be protected before any update. See its
[security notices](https://docs.docker.com/security/security-announcements/),
[release notes](https://docs.docker.com/desktop/release-notes/#41000) and
[cold-backup guidance](https://docs.docker.com/desktop/settings-and-maintenance/backup-and-restore/).
Docker Desktop uses its vendor subscription terms, separate from vSEM's MIT
license. Do not accept a new agreement, purchase a plan or sign in for the owner.

## Proposed bounded work if option1 is chosen

1. Recheck daemon/distro/process ownership, disk identities, available storage and
   GPU state. Create a verified cold preservation copy of the existing Docker
   VM disks and necessary configuration in the privately named backup directory,
   outside the project, Git and synchronization roots. Restrict that new backup
   directory to the owner/SYSTEM; retain its manifest/hashes without exposing
   content. Treat any existing private container data as opaque, never an input
   to a test. No deletion, prune, reset, unregister or format. Do not stop unrelated
   applications. Any inconsistent or incomplete backup blocks the update.
2. Recheck exact installer hash/signature and perform only the named in-place
   vendor update, retaining installation mode. No account/group/repository-rule,
   WSL/kernel, GPU-driver, backend or networking changes; no optional products,
   model services, cloud/offload, extension or Kubernetes enablement. Do not pass
   `--accept-license`. Stop for a new agreement, required reboot, forced additional
   installer/dependency, unanticipated migration or altered artifact identity.
3. Before engine startup, prove that a fresh owned qualification store/context
   will be used and unrelated containers cannot restart. The installer changing
   a default path is not proof. If this cannot be established through supported,
   inspected configuration without deleting/re-registering existing data, stop
   and present an alternate-environment choice. Preserve the old store offline.
4. Only then start the owned updated engine noninteractively and record exact
   server/runtime/kernel/configuration hashes. No update-check substitution or
   package install. Pin the observed versions; inspect current security findings.
   WSL sharing a kernel is a disclosed residual risk, not full VM separation.
5. Qualify authored standard-library confinement probes only, using the exact
   previously reviewed Python3.12.16 Linux/amd64 OCI image
   `docker.io/library/python@sha256:0f086103b026048cc50cb5da25ec435c023c5241a83fc44daea593377abc61c4`.
   Fetch anonymously by exact identity if absent; verify config/layers before any
   launch. No fibsemOS source/build/install/import, no52-wheel installation, no
   adapter execution, no GPU compute and no actual vSEM server in this phase.
6. Independently audit all outputs, close only owned probes/containers/engine
   started for this task, preserve evidence/backups and publish a draft result.
   Then prepare the exact available M05B2B1B transport/execution proposal. Do not
   automatically proceed to that private external/GPU experiment or merge PR14.

The new backup directory and vendor installation are the only proposed host
writes outside the workspace. Their exact private paths and size constraints
are in the trusted decision handoff. New backup ACLs do not authorize changing
repository permissions, existing source ACLs, credentials or unrelated data.

## Allowed code and acceptance

Frontier-owned authored qualification/probe scripts, new independent tests,
review evidence and relevant status/proposal documentation only. No engine,
runtime, GUI/API, existing test, policy, dependency manifest or adapter source
change. No worker research/security design or unqualified local-model task.
Freeze script hashes before probes; generous finite per-job envelopes based on
measured resources; no blanket small RAM/CPU cap or aggregate budget.

Required observed evidence:

- Cold copies complete and independently hashed before update; original disks
  retained and no unrelated services/data changed. Backup contents stay private.
- Exact signed installer, resulting binaries/runtime versions, supported empty
  store admission, no automatic unrelated workload launch and no silent update.
- Containers inspected before execution: nonroot UID/GID10001; no capabilities;
  no-new-privileges; actual default seccomp; read-only root/inputs; only measured
  fresh scratch/output writable; private PID/IPC; no privileged/host namespace,
  devices/GPU, port publication, Docker socket or credential/environment mounts.
- Actual probe: only loopback; arbitrary external/host connection attempts fail;
  forbidden paths absent; host sentinel cannot be read/written; root/input writes
  denied; no privilege acquisition. Configuration flags alone do not pass.
- All subprocess/log outputs bounded and treated as data. Every container/process
  identity accounted for on success and failure; no server, watcher or owned
  desktop engine remains after closeout. Preserve failures without weakening gates.
- Unchanged main/PR12/PR14 sources and original acceptance. New harness tests and
  relevant ordinary GitHub Actions acceptance must pass. This qualifies an
  execution envelope only, not a microscope or all container-escape resistance.

## Later actual-engine experiment remains a separate choice

M05B2B1B must pin this admitted envelope, exact PR14/source/52wheel/OCI inputs and
the reviewed GPU core. The external adapter can remain CPU-only; the core owns
the explicitly selected compute GPU. Expose only the public instrument API via
an independently reviewed narrow transport. A networkless container cannot
reach a host API without an explicit transport; do not substitute host networking,
an unrestricted bridge, a Docker socket, private specimen/run mounts or a GUI token.
No transport implementation or physical GPU launch is approved by this proposal.

Real unchanged upstream Demo/vSEM256/1024 workflows, physical timing/history,
stage/focus/stigmation/zoom, raw/view attribution, partial/cancelled scans,
lease/Stop failures and exact fixture cleanup remain that next experiment's gates.
No cloud fallback, real-instrument access, private truth or answer/seed projection.

## Owner choices and rollback

1. **Recommended: approve this exact preservation/update and isolation-only
   qualification.** Permit the named backup/ACL, reviewed vendor installer,
   strictly admitted fresh-store startup and authored base-image probes, plus
   draft evidence publication. This does not permit private fibsemOS execution,
   actual engine/GPU experiments, main/PR12/PR14 merge or release. Stop at any
   unfulfilled gate and report the concrete remaining decision.
2. **Owner-managed toolchain update.** Leave all host software/data untouched by
   this agent. The owner updates/backs up their Docker environment; after explicit
   return, inspect actual versions/store/ownership and present a precise probe
   approval before running any private container or external payload.
3. **Defer the private experiment.** Keep the CPU-qualified draft unchanged and
   select a separately approved roadmap slice or return when a new defect appears.

Rollback for an unsuccessful probe is closing its exact owned processes and
retaining data. A vendor update/storage migration is not undone by a Git revert:
preserve the cold copies and original settings; do not attempt downgrade/restore
or copy over a live disk without a separately reviewed recovery action. The old
unpatched runtime must not become an execution fallback. These controls do not
promise the upgrade will succeed or authorize bypassing a failed isolation gate.
