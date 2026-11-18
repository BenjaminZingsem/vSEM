# M05B0 inert artifact review

Reviewed 18 November 2026 for [issue #10](https://github.com/BenjaminZingsem/vSEM/issues/10)
and [draft PR #12](https://github.com/BenjaminZingsem/vSEM/pull/12).
**Inspection is complete at the scope below. The original dependency proposal is
rejected for execution.** No upstream package was installed, imported, built or
executed. The optional adapter remains unqualified and unmerged. This finding
concerns the proposed external client environment; the released simulator's two
core dependencies remain unchanged.

## Artifact identity and inspection coverage

| Item | Verified result |
|---|---|
| Upstream source | fibsem-os/fibsem-os commit `27e72f6cc8f9c014562859450ad9260411acaa12` |
| Original wheel proposal SHA256 | `833d86b382d95636115f89fdfd06df276806fb9fec8868c336d015a07c844bf5` |
| Source ZIP SHA256 | `d24472e24c6a49fc387412d01590c57b64e338cfcf3479aa80c6da10869ee9ac` |
| Reconstructed source Git tree | `0a36bb2516ad632b2fc97cc17cc15f066c35333e` |
| Downloaded payloads | One source ZIP and 55 wheels, 226,055,255 bytes total |
| Source verification | All 2,163 files match pinned Git blob identities; reconstructed trees match; no extra/missing files, symlinks or gitlinks |
| Wheel verification | All payload hashes/sizes, 9,665 member CRCs, outer RECORD coverage/digests/sizes and embedded METADATA hashes pass |
| Native inventory | 412 ELF64 entries and eight Windows launcher EXEs; 84 bundled-library records inspected statically |
| Additional inventories | 16 vendored Python distributions inside setuptools; license files, entry points, startup files and upstream instruction assets recorded |

Archives were read directly as data, without extraction. Checks covered unsafe
paths, duplicate names, encrypted entries, special files and review-size bounds.
ELF dependency names, SONAMEs and loader paths were read from bytes without loading
libraries or running `ldd`. Every wheel includes license material; full text and
hashes are retained in private review evidence. An initial inspector assumption
about nested setuptools RECORD files was corrected to select the outer wheel
RECORD; nested files remain covered by that record. No payload mismatch occurred.

Matching a PyPI hash or Git tree establishes byte consistency, not independent
publisher authentication, absence of malicious code or runtime safety. Publisher
attestations were not cryptographically verified. This review does not claim a
whole-program security proof or exhaustive native vulnerability coverage.

## Findings that prevent execution of the original graph

The 18 November OSV query covered all 55 exact package/version pairs and all 16
identified vendored Python distributions. Results were grouped by overlapping
advisory aliases; duplicate database records are not distinct vulnerabilities.
Reachability and exploitability in a particular workflow were not tested.

| Component | Finding | Consequence |
|---|---|---|
| Pillow 12.3.0 | 62 advisory records form 43 alias groups, including native-memory issues; returned fixes point to 13.0.0 | Do not execute the old proposal. PyPI metadata for 13.0.0 requires Python >=3.11, so the CPython 3.10 target cannot simply take that upgrade. |
| setuptools 75.8.0 | Five records form three groups: package download path traversal; macOS manifest normalization; Windows namespace-package path handling | Separate platform-specific impact from the Linux case; replace/review the build toolchain rather than carrying the old pin forward. |
| Vendored jaraco.context 5.3.0 | Two records describe one path traversal issue; fixed in 6.1.0 | Top-level setuptools metadata did not reveal the full vulnerable inventory. |
| Vendored wheel 0.43.0 | Two records describe one unpack path/permission issue; fixed in 0.46.2 | Review nested distributions in the replacement payload too. |

Primary references: [Pillow multi-frame storage advisory](https://github.com/python-pillow/Pillow/security/advisories/GHSA-v9pv-5gc8-w2m6),
[Pillow 13.0.0 metadata](https://pypi.org/pypi/pillow/13.0.0/json),
[setuptools download traversal](https://github.com/advisories/GHSA-5rjg-fvgr-3xxf),
[macOS manifest issue](https://github.com/advisories/GHSA-h35f-9h28-mq5c),
[Windows namespace issue](https://github.com/advisories/GHSA-xmj3-9gf7-h52w),
[jaraco.context advisory](https://github.com/advisories/GHSA-58pv-8j8x-9vj2) and
[vendored wheel advisory](https://github.com/advisories/GHSA-8rrh-rw8j-w5fx).

The absence of an OSV PyPI result for another package does not clear its bundled
native libraries. OpenCV 4.11.0.86 contains OpenSSL 1.1.1w and FFmpeg 5.1.6 labels;
its libpng label is 1.6.44. Imagecodecs carries libpng 1.6.47 and Pillow carries
1.6.58. [OpenSSL ended public 1.1.1 support in September 2023](https://openssl-corporation.org/blog/2023-09-11-eol-111.html).
The [libpng project reports CVE-2026-46675 fixed in 1.6.59](https://www.libpng.org/pub/png/libpng.html).
Those observed labels predate the fix and require replacement or verified patch
provenance. Strings alone cannot establish a downstream binary's actual patch
status; no supported downstream OpenSSL arrangement was established here.

## Build, import and license boundaries

The pinned upstream [build hook](https://github.com/fibsem-os/fibsem-os/blob/27e72f6cc8f9c014562859450ad9260411acaa12/setup.py)
loads `fibsem/ai/agent/sources.py` by path. Its non-editable build calls `ship` to
copy checkout `.claude` skills, agents and playbooks into package assets. This
does not call every helper in that module. Omitting agent extras does not remove
the hook or packaged instructions. None of those instructions was adopted as
maintenance authority. The base package also contains optional UI/ML/agent source;
uninstalled extras do not mean those source files are absent.

Setuptools 75.8.0 contains `distutils-precedence.pth`, which can activate
`_distutils_hack` on a later Python startup. Installation is therefore an execution
boundary even before an explicit package import. Upstream plugin discovery loads
installed entry points; future tests require a fresh environment with an audited
entry-point allowlist, no unrelated plugins and no real-instrument access.

The upstream source has an MIT license, but the wheel ecosystem is not uniformly
MIT. Bundled notices include FFmpeg LGPL terms, GCC runtime exception terms,
libquadmath LGPL terms, certifi MPL 2.0 and font licenses. These need preservation
and a redistribution decision for any packaged environment. License keyword hits
were inspected in context: Python license history saying "GPL-compatible" does
not make pandas or typing-extensions GPL software. This inventory is not blanket
legal clearance. No third-party source or binary payload is vendored in this PR.

## Concrete replacement proposal

The [replacement artifact manifest](../../integrations/fibsemos/review/replacement-artifact-proposal.json)
is metadata only, SHA256
`a5e705b56adefa5ba884dbab2dba6ccaf036987648bc1498a05253ebcacd75a2`.
The original proposal remains preserved unchanged. The new target is a separate
CPython 3.12.16 Linux/amd64 client environment. Its 52 records close 94 active
requirement edges: 47 runtime packages and six build/installer packages, with one
shared. All selected metadata sidecar hashes and wheel tags pass independent
static checks. Twenty-five payloads exactly match already inspected wheels;
27 new payloads total 209,276,581 bytes and have **not** been fetched.

Candidates include Pillow 13.0.0, setuptools 84.2.1, pip 26.3, NumPy 2.5.5,
SciPy 1.18.1, OpenCV 5.1.0.95 and imagecodecs 2026.11.11. These satisfy declared
metadata constraints, not proven runtime compatibility. The 18 November OSV query
returned no entries for the 52 top-level versions; their bundled and OS components
remain unreviewed. These versions would belong only to the optional client.
vSEM keeps its qualified Python/NumPy/SciPy environment and public HTTP boundary.

The exact proposed base is
`docker.io/library/python@sha256:0f086103b026048cc50cb5da25ec435c023c5241a83fc44daea593377abc61c4`
for Linux/amd64, discovered through `3.12.16-slim-bookworm`. The registry index
and architecture manifest hashes were verified as metadata. Four layer digests
(45,269,504 compressed bytes) and the 5,681-byte config digest are frozen in the
proposal. No layer/config payload was fetched, image loaded or container started.
Effective OS packages, Python and bundled installer still require inert inspection.

Recommended next scope is **M05B0-R1 inspection only**: inspect those 27 exact new
wheels, the exact OCI config/four layers and the 25 reused wheels as needed; verify
digests, archive contents, startup/build behavior, bundled licenses and advisories.
Read layers directly, accounting for whiteouts/links without applying them to the
host filesystem. Any mismatch or newly required payload stops that artifact.
Prepare the final execution packet; do not silently substitute versions. No image
pull/load/run, install, import, build, product change, merge or release is included.

## CPU qualification plan after a separate execution decision

1. Freeze the accepted source, wheels, installer, OCI base and original adapter
   source commit. Record the full effective environment and entry-point inventory.
   Inspect the built wheel again before runtime admission. Fail undeclared dynamic
   dependencies; no source distribution or online resolver fallback.
2. Run only in approved disposable public CPU infrastructure. Fetching belongs to
   a separate phase; build/import/test containers have networking disabled, a fresh
   home, minimal environment, no owner/cloud tokens, private mounts, host socket,
   GPU or real-instrument route. Keep only bounded temporary/output mounts.
3. Qualify real upstream plugin discovery, class construction and the unchanged
   Demo imaging service with explicit supported settings. Test vSEM bindings
   against maintainer-owned public-API fixtures, including their present refusal
   before synchronous acquisition. Do not use fake upstream classes as evidence.
4. Record dependency/built-wheel hashes, outcomes and fixture cleanup. Actual
   Demo-to-vSEM acquisition comparison requires the separately approved public
   operation/image correlation slice and GPU/HTTP plan. CPU success is not that
   scientific/transport qualification, merge approval or release approval.

See the [decision packet](FIBSEMOS_M05B_DECISION.md) for owner choices and rollback.
