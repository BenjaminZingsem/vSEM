# M05B1 qualification preparation

19 November 2026: the owner approved
[CPU qualification revision 1](../../../docs/proposals/FIBSEMOS_M05B1_CPU_PLAN.md).
This directory currently contains the **inert admission component only**. There
is no execution workflow, installer, container launch or genuine upstream result
yet. It is not a production installation recipe.

The preflight found that the unchanged prototype requires setuptools 75.8.0,
outside the approved replacement graph's setuptools 84.2.1. The exact proposed
[one-line correction](../../../docs/proposals/FIBSEMOS_M05B1_PACKAGING_DECISION.md)
awaits an owner choice because revision 1 excludes product/build-file changes.
Do not ignore that requirement or execute the rejected dependency graph.

## Inert checks

`artifacts.py` is maintainer-authored standard-library inspection code. It checks
bounded regular inputs, archive paths/types/size limits, exact source SHA256 and
the reconstructed Git tree, full wheel RECORD coverage/hashes, package identity,
entry-point data and byte comparisons against a supplied source mapping. It
does not extract, import or execute archive members. Nested vendored metadata
is inventoried as data, not treated as an additional installed distribution.

`wheel_inventory` is structural evidence, **not sufficient runtime admission**.
The remaining built-wheel inspector must compare the entire package to frozen
source/assets and explicitly classify generated metadata, requirements, license
material and entry points. Installer provenance, dynamic build requirements,
runtime inventory and actual confinement remain separate execution gates.

From the repository root, the synthetic negative tests need only Python's
standard library:

```text
python -I -B integrations/fibsemos/qualification/test_artifacts.py
```

To inspect already quarantined exact inputs, use a fresh ignored output path:

```text
python -I -B integrations/fibsemos/qualification/preflight.py --source-archive /path/to/pinned-source.zip --wheel-dir /path/to/approved-wheels --output runs/maintenance/m05b1/inert-preflight.json
```

`--wheel-dir` can repeat for the original and replacement quarantines. Each
approved wheel must occur exactly once across them. Omit it for source/build-pin
inspection only. Exit 2 denotes an incompatible product build pin; exit 1 denotes
artifact failure. These are failures to qualify, never successful skipped gates.
Reports contain only inventories and observations, not execution authorization.

The 19 November local check reproduced the exact 2,163-file source tree and all
52 replacement wheel identities/RECORD inventories (9,313 files). The build pin
remains blocked. No OCI image or external package was executed. The full C1-C8
experiment is incomplete, and original acceptance/product source remain unchanged.
