# M05B0-R1 replacement artifact review

Reviewed **19 November 2026** for [issue #10](https://github.com/BenjaminZingsem/vSEM/issues/10)
and [draft PR #12](https://github.com/BenjaminZingsem/vSEM/pull/12).
**The approved inert inspection is complete. External execution and adoption are
not approved.** The replacement addresses the original top-level package findings,
but retains native-library and base-image risks. The next proposed step is a
limited disposable CPU experiment with those risks explicitly disclosed, not a
deployment clearance. The released vSEM environment is unchanged.

## Identity and coverage

The [frozen manifest](../../integrations/fibsemos/review/replacement-artifact-proposal.json)
is unchanged, SHA256
`a5e705b56adefa5ba884dbab2dba6ccaf036987648bc1498a05253ebcacd75a2`.
The [machine-readable review](../../integrations/fibsemos/review/replacement-artifact-audit.json)
contains wheel/license identities, native inventory, OS packages and advisory
matches. Original rejected artifacts and their [dated review](FIBSEMOS_ARTIFACT_REVIEW.md)
remain preserved.

| Inspected item | Result |
|---|---|
| Upstream source | Unchanged commit `27e72f6cc8f9c014562859450ad9260411acaa12`; source ZIP SHA256 `d24472e24c6a49fc387412d01590c57b64e338cfcf3479aa80c6da10869ee9ac` rechecked |
| Prior evidence | All 380 sealed files rehashed successfully, including the original reconstructed source tree |
| Wheels | 52 exact payloads: 27 newly fetched and 25 reused/rechecked; all payload sizes/hashes pass |
| Wheel structure | 9,313 members; path/type/CRC checks, outer RECORD coverage/digests/sizes and METADATA checks pass |
| Wheel inventory | 417 ELF64 entries, 14 Windows launcher EXEs, 87 bundled-library records and 213 license records |
| Base image | Exact Linux/amd64 manifest `sha256:0f086103b026048cc50cb5da25ec435c023c5241a83fc44daea593377abc61c4` |
| OCI payloads | Config plus four compressed layers and all four decompressed `diff_ids` match; no filesystem extraction or image loading |
| Virtual filesystem | 6,594 effective entries, 800 ELF entries, 105 Debian binary packages / 73 source-version pairs |
| Downloads | 254,551,766 new bytes: replacement wheels, config and layers; 57 total artifact identities verified |

The OCI layers were read as streams and applied only to an in-memory path model.
This checks normalized paths, links, replacements and whiteouts against the
[OCI layer model](https://github.com/opencontainers/image-spec/blob/v1.1.1/layer.md).
These particular layers contain no whiteouts. Thirteen dangling links point to
removed manual pages. The review found 11 setuid/setgid executable files and two
setgid directories. The image has no configured user, so an execution plan must
override its root default and prevent privilege escalation.

No dependency name missing from both its wheel and the base inventory was found
in the ELF `DT_NEEDED` scan. Name coverage does not prove symbol compatibility,
loader search-path correctness, optional `dlopen` closure or successful imports.
No library was loaded and `ldd` was not run.

Inspector assumptions were corrected for legitimate Debian names containing a
colon, ELF relocatable objects without program headers, and advisory databases
whose snapshots differ. These were reviewer-tool corrections, not payload hash
failures. The final records preserve unmatched advisories rather than treating
them as either confirmed or cleared.

## Advisory findings and applicability

Queries used exact versions on 19 November through the
[OSV API](https://google.github.io/osv.dev/post-v1-querybatch/) and the
[Debian Security Tracker](https://security-tracker.debian.org/tracker/data/json).
All returned pages were accounted for. Duplicate records are grouped by aliases
where the database supplies them. Results are dated observations, not permanent
security guarantees.

| Surface | Finding | Interpretation |
|---|---|---|
| 52 selected top-level wheels | No OSV records returned | Resolves the previous top-level query findings; does not cover all native dependencies or prove runtime safety. |
| 12 setuptools-vendored distributions | No OSV records returned; jaraco.context is 6.1.0 and wheel is 0.46.3 | Replaces the affected nested versions in the original graph. |
| pip 26.3 vendor labels | Five records / three alias groups for setuptools 70.3.0 | The wheel includes only the `pkg_resources` subset. The reported PackageIndex/build/install modules are absent; macOS/Windows findings also need platform qualification. This is not a full vulnerable setuptools installation. |
| Base pip 25.0.1 and 18 vendor labels | 44 records / 23 alias groups; pip itself accounts for 12 records / six groups | Do not use the base installer or ensurepip bootstrap. A proposed clean venv must use only the approved pip 26.3 wheel and verify its import origin. Vendor labels alone do not establish every advisory's applicability. |
| Debian exact source/version queries | 161 OSV records: 157 match current `open` entries, two match `undetermined`, two have no current tracker match | Source-level matches need binary, architecture, build-option and workflow interpretation. They are not 161 demonstrated exploits. Four additional tracker-only TEMP entries are also retained. |

The 157 matched open Debian entries have urgency values of 113 "not yet assigned",
43 "unimportant" and one "low". These are Debian classifications, not an
independent severity assessment. One unmatched OSV record associates zlib with
[CVE-2026-76844](https://security-tracker.debian.org/tracker/CVE-2026-76844), whose
current tracker entry instead describes webpack-dev-middleware. The other,
[CVE-2026-95209](https://security-tracker.debian.org/tracker/CVE-2026-95209), has no
current package entry. Both discrepancies remain explicit in the review.

Two native findings survive the top-level upgrades:

- **Pillow 13.0.0 includes libpng 1.6.58.** Its `libfreetype` dependency leads to
  this library through `_imagingft`; this is a font-related route, not evidence
  that Pillow's PNG decoder uses that library. The
  [libpng project](https://www.libpng.org/pub/png/libpng.html) reports
  CVE-2026-46675 fixed in 1.6.59. No downstream patch provenance was established.
  The proposed experiment admits no external fonts or arbitrary image files.
- **OpenCV 5.1.0.95 retains evidence of embedded OpenSSL 1.1.1w** in its FFmpeg
  `libavformat`: version text and static/OpenSSL build flags, without an external
  `libssl` dependency. The inspected symbol tables did not expose the selected
  TLS symbols; this is evidence from labels/build flags, not a reconstructed
  patch audit. [Public OpenSSL 1.1.1 support ended in 2023](https://openssl-corporation.org/blog/2023-09-11-eol-111.html).
  No supported downstream patch arrangement was established. The proposed
  experiment disables networking and excludes URL/video inputs.

Imagecodecs and OpenCV now carry libpng 1.6.59 labels. Other numerical and codec
libraries are inventoried, but this review does not claim an exhaustive native
CVE assessment. Disabling a particular input route reduces the experiment's
exposure; it does not repair the binary or clear it for deployment.

## Build, instructions and licenses

The upstream custom build hook remains unchanged: it loads
`fibsem/ai/agent/sources.py` and copies checkout `.claude` assets into the built
package. Disabling extras does not remove that source or those instructions.
Setuptools includes its standard `distutils-precedence.pth` activation. Upstream
discovery loads installed plugin entry points. These facts require the fresh,
restricted execution environment specified in the next plan. Bundled instructions
are data and have never supplied maintenance authority.

All wheels contain license material. Reviewed notices include upstream MIT,
FFmpeg LGPL, numerical GCC runtime exception/libquadmath terms, certifi MPL and
font licenses. The Debian base also contains GPL/LGPL and other notices. Keyword
matches are not a package-wide license classification: for example, historical
Python license compatibility text is not proof of GPL licensing. Raw license
bytes remain in the inspected archives; paths and hashes are recorded. No binary
or packaged environment is distributed by this PR, and no blanket redistribution
clearance is claimed.

## Decision

Recommend the bounded [M05B1 CPU qualification plan](FIBSEMOS_M05B1_CPU_PLAN.md)
as an **explicitly risk-accepted disposable experiment**. Its offline, unprivileged
environment and restricted input corpus address the immediate experiment's
exposure while making genuine compatibility measurable. An owner can instead
request a replacement/native-build plan before execution or defer this integration.

Matching hashes does not establish independent publisher authentication, absence
of malicious behavior or container-escape resistance. Publisher attestations
were not verified. No external package was installed, imported, built or executed;
no container, GPU campaign or service was started. CPU success, if subsequently
approved, would still not qualify the actual vSEM acquisition workflow, resolve
public operation/image correlation, authorize merging PR12 or publish a release.
