# Security scope

This release is a trusted local development sandbox. Separate GUI/API credentials,
closed command schemas, loopback binding and observable projections are tested.
It does not provide OS confinement against an untrusted evaluated agent, remote
HTTPS deployment, crash durability or real-instrument connectivity.

Do not post tokens, browser invitations, connection.json, private episode records
or exploit-sensitive details in public issues. Use GitHub's private vulnerability
reporting for this repository when available. For ordinary non-sensitive defects,
open a minimal reproducible issue. The maintainer will confirm a supported fix;
there is no guaranteed response SLA for this initial research release.

Dependencies are pinned for reproducible numerical behavior. Updating them requires
independent scientific and transport qualification; pins do not imply a general
security certification. Never load untrusted Python code or model files into the
runtime. No external ML model is required by vSEM.
