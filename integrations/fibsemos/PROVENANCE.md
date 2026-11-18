# M05A source and review provenance

Reviewed 18 November 2026. Baseline vSEM main:
`0b0b907162a9ca6499bd620b6ef55ad265fafe0e`.
Approved specification:
[`a8412bdb`](https://github.com/BenjaminZingsem/vSEM/blob/a8412bdb165b37b50142f11f92ca40ed8f89d745/docs/proposals/FIBSEMOS_INTEROP.md).
The owner approved independently authored source, CPU fixture tests, qualified
local pure coding and a draft PR. This does not authorize external execution,
core API changes, main merge or release.

Upstream interface pin:
[`27e72f6cc8f9c014562859450ad9260411acaa12`](https://github.com/fibsem-os/fibsem-os/tree/27e72f6cc8f9c014562859450ad9260411acaa12).
Interfaces were inspected anonymously as source text. No upstream implementation
was copied into product files, installed, imported or executed. Candidate source
references its public class/function names and supplies original behavior.
Relevant declarations:

- [registry and builders](https://github.com/fibsem-os/fibsem-os/blob/27e72f6cc8f9c014562859450ad9260411acaa12/fibsem/drivers/registry.py)
- [beam](https://github.com/fibsem-os/fibsem-os/blob/27e72f6cc8f9c014562859450ad9260411acaa12/fibsem/devices/beam.py),
  [stage](https://github.com/fibsem-os/fibsem-os/blob/27e72f6cc8f9c014562859450ad9260411acaa12/fibsem/devices/stage.py),
  [parameter layer](https://github.com/fibsem-os/fibsem-os/blob/27e72f6cc8f9c014562859450ad9260411acaa12/fibsem/devices/core.py)
- [settings](https://github.com/fibsem-os/fibsem-os/blob/27e72f6cc8f9c014562859450ad9260411acaa12/fibsem/structures/settings.py),
  [system/device configuration](https://github.com/fibsem-os/fibsem-os/blob/27e72f6cc8f9c014562859450ad9260411acaa12/fibsem/structures/system.py),
  [unchanged imaging service](https://github.com/fibsem-os/fibsem-os/blob/27e72f6cc8f9c014562859450ad9260411acaa12/fibsem/services/imaging.py)

The `units.py` candidate came from one commissioned pure conversion task using
qualified local Qwen/Qwen3.8-27B revision
`5a7da681f60570ab5b439a587e912d2e5eddb582`, GGUF SHA256
`e00082f779fa385cee8c68a3ec8833a75778cc87272240b942f74e0b8243e520`,
runtime commit `8345f333951c661d166b00e6f9362e553768f292`.
The run used a credential-free networkless envelope, 32k context and an 8192-token
generation allowance. It returned text only and could not run code or edit tests.
The maintainer fixed endpoint conversion ordering and HFW terminology, reviewed
all code, and independently checked all 1000 supported current values plus invalid
inputs. Local model output is provenance, not correctness evidence.

All other source and acceptance are independently maintainer-authored. The raw
container/view are local representations; no upstream `FibsemImage` implementation
or monkeypatch is included. Genuine discovery, imports, device construction and
Demo/vSEM comparison have not run. Original runtime, engine, workflows, policy,
core dependency files and pre-existing tests are outside this change.

The metadata-only dependency evidence was generated 12 November and integrity
rechecked 18 November. The exact proposal SHA256 is
`833d86b382d95636115f89fdfd06df276806fb9fec8868c336d015a07c844bf5`.
The [audit record](review/metadata-audit.json) records its method and limits.
Subsequent M05B0 approval covered inert source/archive inspection only. The complete
source tree and all 55 wheel payload identities now pass structural checks; see
the [artifact report](../../docs/proposals/FIBSEMOS_ARTIFACT_REVIEW.md). Advisory and
native-library findings reject the original graph for execution. The replacement
manifest is a metadata proposal, not adopted code. No upstream payload is added
to Git and no built upstream wheel or genuine runtime workflow is qualified.
