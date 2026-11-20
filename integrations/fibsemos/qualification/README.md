# Disposable public CPU qualification

## M05B2B0 extension, 20 November

The owner approved [M05B2B0 revision 1](../../../docs/proposals/FIBSEMOS_M05B2B0_IMAGE_BINDING_PLAN.md)
for opt-in image binding, this same public CPU envelope and draft publication only.
The workflow now admits only `qualification/fibsemos-m05b2b0-20261120`.
`image-binding-source.json` freezes the reviewed plugin files and packaging;
`run_cpu.py` verifies its exact digest and allows only the four named image-binding
product changes against `f4c6922`. The original 42 contracts and unchanged
`genuine.py` C1-C8 cases remain mandatory, including default pre-exposure refusal
and real Demo256/1024. All original source, wheel, base, confinement and cleanup
gates remain. No external source or dependency substitution is permitted.

`image_fixture.py` is an authored HTTP data oracle, not a physical simulator.
`genuine_images.py` adds real unchanged upstream acquisition workflows at 256/1024,
fixed-window/raw-companion checks, acquired pixel pitch, truthful absent geometry,
save refusal, vacuum, same-operation reconciliation, failures and independently
responsive Stop/periodic renewal. The new standard-library image tests run in a
separate interpreter against the installed package. Workstation checks import
only authored stdlib modules; genuine dependencies execute only in the public
containers. This qualifies software contracts, not GPU/physics or deployment.

## Preserved M05B1 baseline

19 November 2026: the owner approved
[CPU qualification revision 1](../../../docs/proposals/FIBSEMOS_M05B1_CPU_PLAN.md)
and the exact packaging correction below. The specification at `20f8790` remains
the frozen acceptance contract; its original proposed-status header is historical.
This is a maintainer-owned experiment, not a production installation recipe.
On 20 November the hosted experiment and independent audit passed C1-C8 at
`db93715`; see the [result](../../../docs/proposals/FIBSEMOS_M05B1_CPU_RESULT.md).
This qualifies only the bounded CPU software experiment. PR12 stays draft.

The preflight found that the unchanged prototype requires setuptools 75.8.0,
outside the approved replacement graph's setuptools 84.2.1. The exact proposed
[one-line correction](../../../docs/proposals/FIBSEMOS_M05B1_PACKAGING_DECISION.md)
is approved and applied on the qualification branch. All other product source,
original acceptance and artifact identities remain unchanged. No private
execution, other product repair, released dependency adoption, main merge or
release is approved. The rejected dependency graph remains prohibited.

## Inert checks

`artifacts.py` is maintainer-authored standard-library inspection code. It checks
bounded regular inputs, archive paths/types/size limits, exact source SHA256 and
the reconstructed Git tree, full wheel RECORD coverage/hashes, package identity,
entry-point data and byte comparisons against a supplied source mapping. It
does not extract, import or execute archive members. Nested vendored metadata
is inventoried as data, not treated as an additional installed distribution.

`wheel_inventory` is structural evidence, **not sufficient runtime admission**.
The built-wheel inspector compares the entire package to frozen
source/assets and explicitly classifies generated metadata, requirements, license
material and entry points. Installer provenance, dynamic build requirements,
runtime inventory and actual confinement remain separate execution gates.

From the repository root, the synthetic negative tests need only Python's
standard library:

```text
python -I -B -m unittest discover -s integrations/fibsemos/qualification -p "test_*.py" -v
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
52 replacement wheel identities/RECORD inventories (9,313 files). The corrected
build pin now passes preflight. Preparation passes 36 standard-library Windows
tests; two POSIX subprocess tests pass on the public Linux runner. Passing inert
checks alone does not satisfy C1-C8.

## Execution boundary

The isolated `fibsemos_cpu.yml` workflow originally accepted only pushes to
`qualification/fibsemos-m05b1-20261119`; its M05B2B0 branch admission is above.
`run_cpu.py` refuses
private/local execution before any fetch or launch. It uses anonymous pinned
public inputs, an explicit Ubuntu 22.04 hosted CPU runner, read-only workflow
permissions and the existing pinned checkout action without persisted credentials.

`fetch.py` verifies exact source, wheels and OCI config/layers. `confinement.py`
inspects every created container before execution; `probe.py` checks actual
restrictions separately before packages run. Containers are non-root, networkless,
read-only except fresh measured scratch/output, with dropped capabilities,
no-new-privileges and default seccomp. No host credentials, Git directory, private
mounts, GPU or published port enter. These controls do not prove escape resistance.

`container_main.py` creates a fresh venv without pip. `pip_bootstrap.py` runs only
verified pip 26.3 with base site disabled; base pip/ensurepip never run. Exact
wheels install offline with hashes and no dependency resolution. `environment.py`
inventories origins, versions, requirements and entry points. `backend_build.py`
checks declared and dynamic build requirements before calling the actual PEP 517
backend. There is no manual package-assembly fallback.

After the builder exits, `built_wheels.py` reads its output as bounded data on the
host. It compares source/assets, Python/dependency metadata, license and entry
points, classifies generated metadata and rejects unrecognized members. Only
admitted bytes enter the fresh runtime. No package-produced script or archive
member executes on the host.

`genuine.py` uses actual installed upstream classes and its unchanged Imaging
service. Observable-only loopback fixtures exercise bindings, refusals, lease
loss and Stop. Demo acquires 256- and 1024-pixel images; the vSEM adapter must
refuse unqualified synchronous acquisition before exposure. Original M05A tests
run unchanged in a separate interpreter. These gates do not qualify SEM physics,
dose, GPU execution or real-instrument use.

Child logs are bounded and emitted as base64 data with sizes, hashes and chunk
counts. No raw external stdout becomes Actions commands or shell input. Owned
containers and output mounts close on success/failure. Missing evidence, cleanup
failure and failed acceptance remain failures. No third-party source, wheel,
generated image or container payload is published as an artifact.
