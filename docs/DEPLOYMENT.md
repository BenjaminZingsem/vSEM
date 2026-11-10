# Deployment and resource ownership

Run from a source checkout with the pinned requirements. Linux/WSL2, Python 3.10,
little-endian arrays and NVIDIA CUDA are the current supported path. Tested
hardware/software and release measurements are in VALIDATION.md. CPU acceptance
does not imply CPU rendering support. No model weights or cloud account are used.

Set `VSEM_GPU_UUID` before starting any Python numerical process. Use an exact
physical UUID reported by `nvidia-smi`, not a CUDA ordinal. The private numerical
child acquires a lock before setting CUDA visibility or importing GPU code.
Only the selected GPU is visible. A busy device, missing CUDA, corrupt catalogue
or insufficient measured memory causes a failure; there is no fallback or kill
of somebody else's process. The 320 MiB initial-occupancy threshold is unchanged
from the qualified baseline and is not a simulation memory limit.

All vSEM clones for a user default to `~/.cache/vsem/gpu-locks/UUID.lock`.
An administrator sharing the machine with another trusted scheduler must set
`VSEM_GPU_LOCK_DIRECTORY` to that scheduler's canonical shared lock directory.
This advisory lease coordinates cooperating programs for the same user; it is
not an operating-system GPU reservation against other users. Never unlink an
active lock file or replace its inode to bypass a busy lease.

The offline generator writes a new directory only and finalizes its manifest
after complete data files exist. An interrupted partial directory is preserved
for diagnosis and cannot start a server. Use a different output name to retry.
Every runtime load verifies the manifest and complete array hashes before
announcing scientific readiness. A prepared world can be copied between machines
as data; preserve its manifest/hash. No runtime world growth is enabled.

The launcher remains in the foreground and uses loopback-only separate ports.
SIGINT/Ctrl+C and SIGTERM request owned cleanup. It has no privileged HTTP shutdown
route. New run directories contain private credentials, raw episode records and
acquired data; they are ignored by Git. Protect them with OS permissions, including
Windows ACLs when using WSL on a mounted Windows drive. Do not upload service.log
without redaction: startup prints the human invitation there.

The release qualifier creates its new output directory as 0700 and `service.log`
as 0600 on native POSIX filesystems, independently of an ordinary 0022 umask.
It refuses an existing output directory, including a dangling output symlink,
and does not change the caller's umask. Windows-mounted filesystems still need
appropriate Windows ACLs; POSIX mode requests do not establish those ACLs.

## Private preparation diagnostics

The finite numerical worker retains at most eight small JSON failure records in
the episode's `preparation-diagnostics/` subdirectory. Each contains a coarse
allowlisted category, opaque diagnostic ID, bank ticket ID and operation ID.
The records exclude exception messages, tracebacks, specimen coefficients and
credentials. A category is a diagnostic hint, not a proven numerical root cause.
No operator endpoint exposes the directory or its records.

The subdirectory and files use private creation modes on POSIX. A pre-existing
diagnostic subdirectory is refused, and record files are created exclusively.
Record attempts and record size are bounded; a storage
failure does not prevent the original generic `BankFailed` result. No log
rotation, automatic upload or indefinite rejection history is introduced.

On `BANK_FAILED`, preserve these records alongside the private owner trace and
observable operation/image evidence. The episode is terminally interlocked and
does not resume exposure. A blank beam, a prior Stop generation or process
cleanup is not a new Stop acknowledgement. Numerical publication may be partial;
retain known versus unknown charge and delivery information explicitly. Close
the owned instance through the launcher, diagnose and use a new run directory
for any separately justified restart. Do not clear the interlock or replay an
uncertain command blindly.

Long-running retention, restart recovery, remote deployment, multi-user control
and evaluated-agent isolation require further qualification. Do not expose this
development HTTP server on a public interface or give an evaluated agent access
to its process/filesystem. The public API contains only observable instrument data,
but a local unconfined process can bypass any API by reading files or memory.
