# Contributor instructions

Read README.md, docs/SCIENCE.md, docs/API.md and the relevant acceptance tests
before implementation. Follow CONTRIBUTING.md. This is an SEM sandbox.

Keep the causal engine authoritative and GUI/API/evaluator boundaries distinct.
Never give an operator hidden physical truth, ideal values, seeds or future faults.
Physical acquisition time, dose, partial images and exposure-time metadata are
mandatory. Slower accurate computation is allowed; faster-than-modeled acquisition
is not. Unsupported controls must not look implemented. Profiles are uncalibrated.

Architecture, physics, critical timing/security, UI design, independent acceptance
and final integration are maintainer-owned. Delegate only explicit pure coding
tasks with closed scope and acceptance criteria. Never allow a coding worker to
modify protected tests/contracts or approve its own release. No cloud fallback,
real-instrument routes or worker access to maintainer credentials.

Preserve private local work and immutable inputs. Keep worlds, logs, run credentials
and experimental handoffs out of Git. Automated fixtures close owned processes.
Maintain docs/HUMAN_REVIEW.md; do not launch a persistent human-review server unless
the user explicitly requests it. Run checks appropriate to the change and record
their actual results. Do not claim numerical qualification from CPU CI alone.
