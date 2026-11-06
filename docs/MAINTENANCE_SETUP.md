# Setting up owner-account maintenance

This mode uses the owner's existing `BenjaminZingsem` GitHub login. The assistant
asks the owner in the trusted conversation before incorporating external code or
implementing features. Read [the policy](MAINTENANCE_POLICY.md). No second GitHub
account, GitHub App or new API key is required.

## 1. Open the correct local checkout

Open the public vSEM checkout in a local Codex session with access to the already
authenticated GitHub CLI. Keep the earlier experimental completion goal paused.
A separate maintenance conversation avoids mixing their scopes. To clone elsewhere:

```bash
gh repo clone BenjaminZingsem/vSEM
cd vSEM
```

In an existing checkout, inspect `git status` and preserve local work before
updating. Never reset or overwrite experiments to start maintenance. Read the
approved policy/status, not a contributor's candidate branch.

## 2. Confirm account access

```bash
gh auth status --hostname github.com
gh api user --jq .login
gh repo view BenjaminZingsem/vSEM --json nameWithOwner,viewerPermission
git remote -v
git rev-parse HEAD
```

The account should be `BenjaminZingsem`; the remote should identify this repo.
Do not print a token or paste one into the conversation. If this environment is
not logged in, use `gh auth login --hostname github.com --git-protocol https --web`
and authenticate through GitHub's browser flow. Verify from the same environment
the goal will use; another computer/cloud session may not share that login.

## 3. Verify repository protection

The prepared settings are
[configs/maintenance_branch_protection.json](../configs/maintenance_branch_protection.json).
They require PRs, an up-to-date base, the GitHub Actions `acceptance` check,
resolved threads, no force-push/deletion and administrator enforcement. GitHub
Actions App ID `15368` was verified against this repository's successful check.
See [MAINTENANCE_STATUS.md](MAINTENANCE_STATUS.md) for whether they were applied.

Read-only verification:

```bash
gh api repos/BenjaminZingsem/vSEM/branches/main/protection
```

Only after explicit owner approval, apply from the checkout root:

```bash
gh api --method PUT repos/BenjaminZingsem/vSEM/branches/main/protection --input configs/maintenance_branch_protection.json
```

This replaces branch protection. If current settings changed since preparation,
review them first rather than overwriting them. Required GitHub reviewer count
is intentionally zero: a sole owner cannot approve a PR authored through that
same account. The human decision happens in chat. GitHub cannot independently
distinguish owner actions from assistant actions under the shared account.

If a rule blocks a merge, inspect the missing requirement; never disable protection
or use an administrative override. If the owner declines these settings, report
the limitation and still use reviewed PRs, successful checks and chat decisions.

## 4. Activate the goal explicitly

Read [the full activation prompt](../prompts/CONTINUOUS_MAINTENANCE.md) and paste
it into the maintenance conversation with the policy commit you approve. A concise
equivalent is:

```text
Start the continuous vSEM maintenance goal using
prompts/CONTINUOUS_MAINTENANCE.md at policy commit <APPROVED_COMMIT>.
Use my existing BenjaminZingsem GitHub account. Ask me with concrete choices before
incorporating external code or implementing features. Keep the older experimental
completion goal paused.
```

The first cycle verifies account/repo/policy, records a private resumable handoff
and inspects the actual issue/PR/check queue. If no actionable bug exists, it
proposes the next roadmap feature for your choice; it does not implement all
roadmap items automatically or install a scheduler.

If the interface retains another unfinished paused goal, use a fresh maintenance
conversation or its goal controls. Never declare the old goal complete merely
to make room. This repository cannot change the application's goal controls.

## 5. Answer decisions and pause when needed

Questions offer a bounded implementation/adoption with acceptance criteria, a
concrete narrower alternative, or deferral. They state whether approval includes
merge after tests. Reply with the option or modified scope. No reply means no
permission for that action; batch approval covers only its named tasks.

Say **"Pause the maintenance goal at the next safe checkpoint"** to pause. To
resume, ask it to read the preserved handoff and recheck source, approvals and
the queue. [ROADMAP.md](ROADMAP.md) and [MAINTENANCE_STATUS.md](MAINTENANCE_STATUS.md)
are dated public summaries; private execution/approval records stay ignored.

No issue-triggered workflow, scheduled service or permanent GPU runner is installed.
Execution may stop with session, permission or usage limits; handoffs enable
resumption. Workers/tests must not inherit owner credentials. Public candidate CI
stays on disposable hosted CPU runners. Human-review servers remain off unless
requested.
