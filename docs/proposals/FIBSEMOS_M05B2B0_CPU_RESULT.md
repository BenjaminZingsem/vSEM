# M05B2B0 image-return CPU qualification result

**20 November 2026: the approved public CPU image-binding gates pass.**
Implementation `192a6e4894a57abbd038c6e72eb9ed550502e7af` passed the [isolated run](https://github.com/BenjaminZingsem/vSEM/actions/runs/44774204711).
Original and configured workflows used actual pinned upstream classes in the
unchanged disposable environment. The maintainer decoded and hashed all
114 bounded evidence/log records, independently checked
container restrictions and compared all 812 upstream and 10 plugin member hashes
to exact source bytes. This is a draft-only software qualification, not an actual
vSEM GPU/physics or deployment result.

## Scope and exact inputs

The owner selected [M05B2B0 revision 1](FIBSEMOS_M05B2B0_IMAGE_BINDING_PLAN.md):
opt-in image return, public CPU isolation and draft publication only. The core
association in PR13 is already merged at `2e18bdafadab22c56a64cc16cc344bcd5a0bb0c1`.
Its 77 engine files, all runtime/GUI files, existing acceptance, policies and core
dependencies remain unchanged. Four optional product modules changed against
qualified `f4c6922`: client, protocol, bindings and the new image-result module.
The original 42 adapter tests and all original C1-C8 cases remain unchanged.

The [product-source lock](../../integrations/fibsemos/qualification/image-binding-source.json)
SHA256 is `f84615239fbdc1950ffc9d1470ee9ba6ef3e49de693ad606d7ee4447c3a9dc2b`.
Inputs remain fibsem-os/fibsem-os commit
`27e72f6cc8f9c014562859450ad9260411acaa12`, ZIP SHA256
`d24472e24c6a49fc387412d01590c57b64e338cfcf3479aa80c6da10869ee9ac`,
Git tree `0a36bb2516ad632b2fc97cc17cc15f066c35333e`; the unchanged
[52-wheel manifest](../../integrations/fibsemos/review/replacement-artifact-proposal.json)
SHA256 `a5e705b56adefa5ba884dbab2dba6ccaf036987648bc1498a05253ebcacd75a2`;
and Linux/amd64 Python3.12.16 base
`docker.io/library/python@sha256:0f086103b026048cc50cb5da25ec435c023c5241a83fc44daea593377abc61c4`.
No source/version/artifact substitution, new dependency or OS upgrade occurred.
No external payload was imported/built/executed on the private workstation or WSL.

## Observed acceptance

| Gate | Result |
|---|---|
| Isolation and environment | Original configuration checks and separate actual probe pass: nonroot UID/GID10001, zero capabilities, read-only inputs/root, no-new-privileges/seccomp, networkless with only loopback. No owner/cloud credentials, private mounts, GPU, Docker socket or real-instrument route. Verified pip26.3, offline hashed installs, 52 exact distributions before and 54 after the builds. Base pip/ensurepip never invoked. |
| Real builds and static admission | Both genuine PEP517 builds pass; dynamic build needs empty. Exact source, RECORD, dependency/Python metadata, entry points and license evidence pass; independent byte-hash comparison covers 812 upstream assets/modules and all 10 plugin modules. |
| Preserved baseline | All 38 harness tests, original 42 adapter contracts and all eight unchanged genuine C1-C8 cases pass, including discovery/bindings, authority/Stop/renewal loss, unchanged Demo256/1024 and default vSEM refusal before exposure. |
| New independent contracts | All 26 parser/raw/view/failure tests pass against the installed plugin: closed projections, ID/raster/cut association, unknown admission without replay, completion before delivery, same-operation reconciliation, corrupt/missing data and refused outcomes. Stop/renewal remain independent; authority loss during blocked raw delivery cannot become success. |
| Genuine configured images | Unchanged fibsem.acquire/Imaging/Beam returns a real FibsemImage subclass for 256/1024. View dtype/shape/bytes and acquired pixel pitch pass. Raw uint32 values above65535, zero-count vacuum, lossless save/load, acquisition parameter segments and blank holds are retained. Auxiliary upstream filtered_data is distinct from unchanged .data and raw counts. |
| Honest metadata/save limits | Requested settings remain intent; unavailable microscope state/geometry are absent. Upstream pre-driver wall-clock call stamp is not episode exposure time. Automatic saving and generic view TIFF save refuse before exposure/write; explicit raw save/load is available. |
| Failures and response | Legacy/malformed association refuses before exposure; rejected/cancelled/unknown, interlock and lost GET remain errors. Reconciliation uses the same retained ID, no second exposure. Actual periodic renewal and generation-confirmed Stop work while raw delivery blocks after fixture physical completion. |
| Cleanup | All six new genuine case records pass; no prohibited imports or remaining fixture/renewal threads. All three owned containers removed and output mount unmounted. No external source, wheel or image payload published. |

The new HTTP oracle is authored data, **not the causal engine**. Its programmed
time separation tests that the adapter does not return before its completion/cut
conditions; it does not demonstrate numerical SEM accuracy or actual engine timing.

| Configured fixture image | Declared fixture duration | Measured upstream call | Raw uint32 SHA256 |
|---|---:|---:|---|
| 256x256 | 1.357220 s | 1.619 s | `c5a33b7faf49b688c17ba2b8275caa58f68c89c39dd63a4f0edc299db3cfc8fc` |
| 1024x1024 | 21.094820 s | 22.499 s | `e8eaf3c3f2368e5bb1fdcafc00d96646cc3b04c7dfb5747431f050cfa4ea95cc` |

Built wheels are inventoried as evidence; no binary redistribution or adoption:

| Distribution | Bytes | SHA256 |
|---|---:|---|
| fibsem 0.7.0.dev0 | 3712175 | `1b3eae77e0a1390f44dd0de23dd6fc34897c01bdd1c879d0e8af7436bac5f331` |
| vsem-fibsemos 0.0.0.dev1 | 23321 | `8623506e9a058e2fda137cc5c592bf144dceb64ee8c9701434d7ab7fa63f98a3` |

The upstream wheel includes its exact MIT notice. The prototype declares MIT;
the repository notice is separately inventoried. This experiment does not qualify
a distributable package's complete notice/companion-file contract.

The public runner offered 4 CPUs and
15495503872 available memory bytes; its measured container
allowance was 13558565888 bytes. No CPU cap; the existing
180-minute finite job envelope remains. Hosted kernel/image/Docker details are
retained with the evidence, not claimed immutable by the client-image pin.

## Ordinary acceptance and stopping point

Local Linux discovery: 345 tests, 335 passed and 10 existing explicit skips.
Original/new focused Windows contracts: 68 passed. Display retention, intensity
transfer and source/publication checks pass. Hosted ordinary acceptance on the
same implementation also passes; final draft checks are recorded on
[PR14](https://github.com/BenjaminZingsem/vSEM/pull/14).

PR14 is the cumulative optional-adapter review draft following PR12. Both stay
unmerged, issue10 stays open and main remains at its approved core baseline.
No release, private external execution, real instrument use or actual cross-stack
GPU interoperability follows from these CPU fixtures. Residual
[native/base/kernel risks](FIBSEMOS_R1_ARTIFACT_REVIEW.md) remain accepted only
for this public disposable CPU experiment. M05B2B1 needs a separate exact
candidate, available isolation plan, owner decision and genuine engine workflow
qualification before that next experiment. No server or watcher remains.
