# M05B1 packaging-pin decision

Prepared 19 November 2026 against qualification base
`20f87901566b3be070fc05f7ab4d8c64b5b0fa4a`. **Proposed, not applied.**
The owner approved [CPU qualification revision 1](FIBSEMOS_M05B1_CPU_PLAN.md).
That approval keeps the M05A product and build configuration unchanged.

## Finding and exact proposed change

`integrations/fibsemos/pyproject.toml` requires `setuptools==75.8.0`.
The approved replacement wheel manifest contains `setuptools==84.2.1` and
explicitly excludes the rejected original graph from execution. The upstream
`setuptools>=45` requirement accepts the replacement, but the plugin's exact pin
does not. This is a static compatibility finding; neither build has run.

Proposed sole product change:

```diff
 [build-system]
-requires = ["setuptools==75.8.0"]
+requires = ["setuptools==84.2.1"]
 build-backend = "setuptools.build_meta"
```

This uses the already inspected and execution-approved wheel in the unchanged
[replacement manifest](../../integrations/fibsemos/review/replacement-artifact-proposal.json)
(SHA256 `a5e705b56adefa5ba884dbab2dba6ccaf036987648bc1498a05253ebcacd75a2`).
It adds no artifact, dependency or API behavior. The runtime plugin source stays
at M05A `ca6825fb0cdcaa8aa1c4fa176965720757c195ef`. New setuptools can change wheel
metadata or package inclusion; the isolated build and independent source/member,
metadata, entry-point and license audit must detect those differences. A successful
build alone does not qualify compatibility.

## Choices

1. **Approve this exact pin correction and continue M05B1 (recommended).**
   Extend allowed files by this one line. Preserve all C1-C8 gates, pinned source,
   wheels, base, isolation, public CPU-only execution and original acceptance.
   Allow the reviewed qualification branch and factual PR/status updates. No
   product API repair, private execution, main merge, dependency adoption into
   released vSEM or release. Rollback is a reviewed revert of this one line and
   the existing disposal of qualification containers; PR12 remains draft.
2. **Retain the original product and stop at the incompatibility.** Preserve the
   prepared qualification harness and evidence. Genuine installed-plugin gates
   remain unqualified; do not bypass the declared build requirement.

The maintenance policy treats dependencies/build configuration as sensitive,
and revision 1 explicitly excludes product changes. The earlier execution
approval persists; only this discovered packaging change needs a new choice.
No old setuptools execution, manual package assembly, altered source export or
ignored build requirement is an alternative qualification path.
