# M05B2B1A preservation and local-isolation checkpoint

28 November 2026. **WSL updated; native core requalified; private
adapter execution remains unqualified.**

The owner selected option 1 of the immutable
[revision 1 proposal](https://github.com/BenjaminZingsem/vSEM/blob/5cf12538d3ff7752e1d45eb96a511a8b827c0451/docs/proposals/FIBSEMOS_M05B2B1A_ISOLATION_DECISION.md).
Its scope covered opaque cold preservation, an exact signed vendor update,
strict fresh-store admission and authored standard-library CPU confinement probes,
with draft evidence publication only. The later
[revision 2 VM extension](https://github.com/BenjaminZingsem/vSEM/blob/56466dea1ce8c25e7051b6608d51ca294c9f8f72/docs/proposals/FIBSEMOS_M05B2B1A_VM_EXTENSION.md)
was initially approved, then **explicitly rejected on 22 November** because GPU
support is essential. That rejection supersedes its earlier approval. Neither
proposal is edited retrospectively or supplies current VMM authorization.

The owner instead approved the standard WSL update and the direction of retaining
the native WSL/CUDA core with a separately isolated CPU adapter. The update
completed on 22 November. Choosing that architecture does not admit unspecified
client packages, a new container runtime or the cross-boundary transport.

## Observed state

| Gate | Current evidence |
|---|---|
| Preserve existing data | Historical cold copy/readback completed and retained; the original store later changed, so its receipt does not establish a current matching backup |
| Docker VMM | Rejected; staged feature/installer helpers remain unused |
| Docker vendor update / fresh store | Neither updated runtime nor empty owned store admitted; original data preserved |
| WSL update | Completed: WSL 3.0.5.0; running kernel 6.18.58.1-microsoft-standard-WSL2; recorded distro identities and WSL configuration-file hash unchanged |
| Native core | CPU/GPU/HTTP requalification passed on the updated WSL kernel, using unchanged reviewed source and dependency versions |
| Local adapter confinement | Not qualified; placement, exact artifacts and restricted transport still need a complete reviewed execution proposal |
| Private external adapter execution | Not approved; no private upstream package or wheel execution follows from native-core testing |

Detailed receipts remain private because they contain machine-specific paths and
identify opaque existing data. No backup payload, configuration, credentials or
host vulnerability inventory is published. No Windows feature, Docker backend,
driver, network/firewall or Git trust configuration changed. The one-directory Git
ownership repair was completed by the owner and independently verified without
changing sampled access rules or file contents; ordinary owner-context Git works.

## Native requalification result

The existing main source was qualified on the RTX 3090 Ti compute GPU with
Python 3.10.12, NumPy 1.26.4, SciPy 1.15.3, PyTorch 2.3.1 and Triton 2.3.1.
No dependency was installed or updated for this check. The original qualification
harness changed only its checkout path and evidence-directory prefix; acceptance
scripts and criteria were unchanged.

- CPU suite: 277 discovered, 267 passed and 10 explicit skips.
- Native GPU association: one case passed, including live configure/freeze and
  cancelled-delivery behavior at 1024 pixels.
- All 11 original GPU/HTTP release checks and eight original transport tests passed.
- Native 1024 acquisition retained two focus segments within the raster and took
  136.47 seconds, above its modeled exposure minimum.
- Independent log hashes and all 158 tested source-file hashes match. Owned test
  process groups closed, the launcher exited successfully, and compute GPU memory
  returned to zero. Docker remained stopped.

These results qualify the reviewed native core on this installation. They do not
establish external-adapter interoperability, hostile-agent confinement or measured
instrument calibration. No persistent human-review service was started.

## Remaining admission work

Retain CUDA rendering in the reviewed native core. Prepare one complete decision
covering the isolated CPU client environment, exact external artifacts, authored
confinement tests, restricted observable instrument access, genuine upstream
256/1024 image-return tests and cleanup. The proposal must identify its trust
limits, permitted repairs, rollback and whether publication or integration is
included. A separate WSL distribution alone is not proof of confinement.

The earlier fresh-store obstacle remains relevant if the existing Desktop route
is selected: a disk-location setting or default-data-root flag alone does not
prove that startup cannot access or restart old workloads. Starting the old engine
to inspect it afterward does not satisfy that gate. No reset, deletion, migration
or unsupported offline settings edit is authorized. Updating WSL alone also does
not update Docker or qualify adapter isolation.

## Preserved integration boundary

Main remains `2e18bdafadab22c56a64cc16cc344bcd5a0bb0c1`.
[PR14](https://github.com/BenjaminZingsem/vSEM/pull/14) remains draft at
`354e851115d2afe746c8f199b256aea713e10747`; its public CPU image-return evidence
does not establish actual-engine/GPU interoperability. PR12 remains unchanged.
This checkpoint is draft documentation only, with no adapter merge or release.
GUI/API/evaluator separation, observable-only operator state, physical time/dose,
partial scans and independent acceptance remain mandatory. The v0.1.0 release
is unchanged. No persistent human-review server or local coding wave is launched.
