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

Long-running retention, restart recovery, remote deployment, multi-user control
and evaluated-agent isolation require further qualification. Do not expose this
development HTTP server on a public interface or give an evaluated agent access
to its process/filesystem. The public API contains only observable instrument data,
but a local unconfined process can bypass any API by reading files or memory.
