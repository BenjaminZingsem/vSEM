# Contributing

Use issues for reproducible instrument behavior and AI-operator integration needs.
Keep an AI operator in its own project and interact through the documented API.
Small focused pull requests with an acceptance criterion are preferred.

See the maintained [roadmap](docs/ROADMAP.md) and
[maintenance policy](docs/MAINTENANCE_POLICY.md). Contributions and proposals are
welcome, but a submission is not authorization for the maintenance agent to run
or incorporate it. The agent obtains an explicit owner choice before adopting
external code or implementing a feature request. Reports, comments, attached
scripts and changes to agent instructions are reviewed as untrusted content.
Provide provenance/license for external material and concrete acceptance criteria.

Preserve these contracts:

- One authoritative causal engine; GUI BFF, instrument API and evaluator remain
  distinct principals and transports. Never export hidden truth, seeds, future
  faults or ideal settings to the operator.
- Physical time and dose evolve while an operator thinks. Acquired pixels retain
  their exposure-time settings; optimizations cannot advance image delivery ahead
  of exposure or replace physical effects with overlays.
- Show requested/applied state honestly. Unsupported controls stay absent or
  disabled. Generic profiles stay labelled uncalibrated.
- UI design, physics, critical security/timing and independent acceptance require
  maintainer review. Coding assistants receive explicit coding tasks; they do not
  approve their own scientific or security changes.

Install requirements and run the README's CPU/JavaScript checks. A change to
numerics, runtime admission or transport needs actual GPU/HTTP qualification and
relevant independent oracles. A UI interaction change needs browser/human review.
Do not relax tests merely to get a pass; explain a contract change and add an
independent acceptance criterion. Keep tests distinct from implementation claims.

Public CI runs only on GitHub-hosted CPU runners. Never execute untrusted PR code
automatically on a private GPU host or expose its credentials. Report measured
hardware, source hashes, command, outcome and limitations for manual GPU gates.
Exclude worlds, acquired run directories, private records, tokens and large logs
from commits. Contributions are accepted under the project's MIT license.
