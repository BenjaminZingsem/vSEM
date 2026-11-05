# Provenance and licensing

This repository starts from the clean human-reviewed finite-specimen baseline
`7012f5d0275b7a8aa58f6e62fda3da147034c396` of the original local vSEM development
repository. It intentionally begins a curated public history. Original worktrees,
experimental successor work, audit evidence and history remain preserved locally.

`baseline-files.json` records original source hashes before curation/adaptation.
Files listed there but absent here were excluded development supervisor/evidence
dependencies. `publication-changes.json` records retained changes and additions.
The finite physical model, causal engine, public projections and GUI implementation
are retained. Deployment changes replace the fixed machine GPU UUID with explicit
administrator selection, share a per-user GPU lease, admit explicitly supplied
canonical catalogue locations, and remove private review-record prerequisites.
The offline integer generator still checks its accepted helper's content hash.

New files provide deployment, a standalone API client, release acceptance, CI and
documentation. The historical saved-process-tape test is explicitly skipped because
its private tapes are not distributed; fresh actual-runtime tests are separate.

Project code and documentation are MIT licensed, as authorized by the project
owner. The included specimen generator creates procedural data; this publication
contains no external SEM image collection, trained model weights, commercial UI
artwork or acquired user data. No external dataset account is required.

NumPy, SciPy, PyTorch and Triton are dependencies installed separately and retain
their respective upstream licenses. They are not relicensed by this repository's
MIT grant. Any future real-image dataset needs per-source license/provenance and
redistribution review before being included or linked as a required download.
