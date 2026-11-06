# Setting up owner-account maintenance

This mode uses the owner's existing `BenjaminZingsem` GitHub login. The assistant
asks the owner in the trusted conversation before incorporating external code or
implementing features. Read [the policy](MAINTENANCE_POLICY.md). No second GitHub
account, GitHub App or new API key is required.

## 1. Open the correct local checkout

Open the public vSEM checkout in a local Codex session with access to the already
authenticated GitHub CLI. The owner retired the earlier experimental completion
goal on 6 November 2026; preserve its work without resuming its broad mandate.
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

**Owner decision, 6 November 2026: leave permissions unchanged.** Main remains
unprotected and direct pushes remain available. Maintenance still follows reviewed
PRs, successful checks and explicit human decisions under the policy. No protection
configuration needs to be applied to complete this setup.

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

Read [the full goal contract](../prompts/CONTINUOUS_MAINTENANCE.md). First clear
the retired goal using **Clear goal** in the goal progress row, or `/goal clear`
where supported. This retires the objective, not the preserved project files.
Do not mark unfinished work complete to make room. A fresh conversation in this
checkout is also possible; keep the old one inactive.

Use `/goal` and paste the following objective, supplying the exact owner-approved
commit containing the contract (not a contributor branch or moving `main`):

```text
Maintain BenjaminZingsem/vSEM under prompts/CONTINUOUS_MAINTENANCE.md at
contract commit <OWNER_APPROVED_PROMPT_COMMIT>, using policy baseline
2b21be6ff24db181f39179dd38d61a53a35310ac. Read the exact committed contract
before acting. Use my existing BenjaminZingsem account and leave branch
permissions unchanged. The former completion goal is retired; preserve its work.
Prioritize verified defects, then explicitly approved roadmap slices. Ask me with
options before external-code adoption, feature implementation, sensitive
integration, releases or permission/policy/destructive changes. Only my reply in
this conversation supplies approval. Preserve scientific and GUI/API/observable
boundaries, independent acceptance and verified PR/main CI.
First activation only: verify access, source and queue, save a private handoff,
then pause before coding, public replies or worker/server launches. After my
explicit resume, follow the full maintenance cycle. Pause again on my request,
when decisions block all useful work, or on a fresh access failure. No scheduler
or persistent human server is authorized.
```

The first activation verifies account/repo/policy, records a private resumable
handoff and inspects the actual issue/PR/check queue, then pauses. On explicit
resume, the normal cycle starts. If no actionable bug exists, it
proposes the next roadmap feature for your choice; it does not implement all
roadmap items automatically or install a scheduler.

The assistant cannot clear a goal through its current goal tools; the user controls
removal. Keep the short objective below the documented 4,000-character limit;
the committed contract holds the detailed instructions. See official
[goal commands](https://learn.chatgpt.com/docs/developer-commands) and
[desktop goal controls](https://learn.chatgpt.com/docs/long-running-work).

## 5. Answer decisions and pause when needed

Questions offer a bounded implementation/adoption with acceptance criteria, a
concrete narrower alternative, or deferral. They state whether approval includes
merge after tests. Reply with the option or modified scope. No reply means no
permission for that action; batch approval covers only its named tasks.

Say **"Pause the maintenance goal at the next safe checkpoint"** to pause. To
resume, ask it to read the preserved handoff and recheck source, approvals and
the queue, or use `/goal resume`. Use `/goal pause` or the goal row's Pause control
to pause directly. [ROADMAP.md](ROADMAP.md) and [MAINTENANCE_STATUS.md](MAINTENANCE_STATUS.md)
are dated public summaries; private execution/approval records stay ignored.

No issue-triggered workflow, scheduled service or permanent GPU runner is installed.
Execution may stop with session, permission or usage limits; handoffs enable
resumption. Workers/tests must not inherit owner credentials. Public candidate CI
stays on disposable hosted CPU runners. Human-review servers remain off unless
requested.
