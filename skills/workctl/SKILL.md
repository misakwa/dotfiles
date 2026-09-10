---
name: workctl
description: Drive workctl, Michael's CLI for units of work in the vectara-bare workspace (work/<unit>/<repo> worktrees, herdr workspaces, agent sessions). Use when the user says "workctl", starts or finishes a unit of work, asks what they are working on, wants a worktree for an existing branch or PR, or when the cwd is under work/<name>/.
---

A **unit** is one directory under `work/`. workctl derives units from the
folder layout alone; nothing is registered. Every checkout inside a unit is a
worktree of a bare repo in the same workspace (see `bare-repo-worktrees`).

```
<root>/                       # WORKCTL_WORKSPACE, default ~/Projects/vectara-bare
├─ <repo>/.bare/  <repo>/master/   # bare repo + primary worktree
├─ work/<unit>/                    # unit root: notes live here, agents start here
│  ├─ <repo>/                      #   checkout, depth 1
│  └─ <sub>/<repo>/                #   sub-unit "<unit>/<sub>", depth 2
└─ .archive/<unit>/                # where `workctl done` moves the notes
```

workctl sees checkouts at depth 1 and 2 only. A checkout anywhere else
(`work/<unit>/<a>/<b>/<repo>`, `<root>/<repo>/<slug>`, `<root>/<name>/<repo>`)
is invisible to every command, and `done` can move it. See "Finish a unit".

## Intent to command

| Intent | Command |
|---|---|
| What am I working on | `workctl` (same as `workctl board`); add `--refresh` after a push or merge |
| Show me this unit | `workctl show <unit>` |
| Start a unit on a new branch | `workctl new <unit> --repo <repo> [--repo <repo2>] [--base <ref>]` |
| Notes-only unit (incident, investigation) | `workctl new <unit>` |
| Worktree for an existing branch or PR | not `workctl new`; see "Attach an existing branch or PR" |
| Sub-unit | `workctl new <unit>/<sub> --repo <repo> --branch misakwa/<unit>-<sub>` |
| Open the unit in herdr | `workctl go <unit>`; `workctl go` alone lists unit names |
| Resume the agent in a unit | `workctl agent <unit>` (`--new`, `--pick`, `--kind codex`) |
| Which sessions does a unit hold | `workctl agent-sessions <unit>`; `--orphans` lists history of removed units |
| PRs, failing checks, review threads | `workctl pr <unit> --threads` (`--draft` prints reply drafts; it never posts) |
| Review the whole unit as one diff | `workctl review <unit>` (opens hunk); `--staged`; `--working` |
| Sidebar tokens in herdr | `workctl sync` (the wt post-switch hook already runs it) |
| Finish a unit | `workctl done <unit> --dry-run`, then `workctl done <unit> --apply` |
| Finish every SETTLE unit | `workctl sweep --dry-run`, then `--apply` |

Two forms that fail: `workctl board <unit>` (the positional is the root
directory, so it answers "no work/ directory under <unit>") and
`workctl <unit>` ("no such command"). The unit view is `workctl show`.

Every command takes `--root DIR` (the directory holding the bare repos).
`--root` is never the unit name and never the herdr workspace.

## Start a unit

`workctl new <unit> --repo <repo>` creates branch `misakwa/<unit>` in each
repo, checks it out at `work/<unit>/<repo>` through `wt switch --create`,
and creates a herdr workspace at the unit root when herdr runs. Add
`--agent` to start claude in that workspace, `--no-herdr` to skip herdr.

- Run `--dry-run` first. It prints the exact `wt` command but skips the
  branch-exists check, so a real run can still refuse.
- `new` refuses a branch that already exists ("run `wt switch`"). Do not
  follow that hint bare; use the attach recipe below.
- `--base <ref>` applies to every `--repo`. For a stacked branch pass one
  `--repo` per call.
- A failed run leaves an empty `work/<unit>/`; remove it with `rmdir`, or the
  board shows a NOTES unit.
- Repos outside the workspace (`ti-provisioning`) are refused; see boundaries.

### Attach an existing branch or PR

This is the most common start (a PR of his to continue, a colleague's PR to
review, a branch pushed from elsewhere). workctl has no command for it. Two
incantations keep the checkout inside the model; anything else lands outside.

With worktrunk (same override `workctl new` uses; verified with `--create`,
the attach form differs only by dropping it):

```bash
cd <root>/<repo>/master
wt --config-set 'worktree-path="{{ repo_path }}/../../work/<unit>/{{ remote_repo }}"' \
   switch <branch> --no-cd -y          # or: switch pr:<N>  (documented in wt switch --help, not run)
```

With plain git (what his sessions have always done):

```bash
git -C <root>/<repo> fetch origin --prune
git -C <root>/<repo> worktree add <root>/work/<unit>/<repo> <branch>
```

Then `workctl board --refresh` (the git facts are cached; without it the new
checkout shows as `?1/1 outside workspace`) and `workctl go <unit>` when herdr
should hold it.

Plain `wt switch <branch>` without the override obeys his config template and
lands at `work/misakwa-<unit>/<repo>`: a unit named after the branch, with
the prefix baked into the directory. `git worktree add <slug>` from inside
`<root>/<repo>/` lands at `<root>/<repo>/<slug>`, invisible to the board.

### Add a repo to an existing unit

`workctl new <unit> --repo <repo2>` works when `misakwa/<unit>` does not yet
exist in `<repo2>` (dry-run verified only). For an existing branch use the
attach recipe. When the unit root is itself a checkout (the unit directory
holds `.git`), add nothing: the new worktree would nest inside the old one.

### Sub-units and branch names

`work/<unit>/<sub>/<repo>` is sub-unit `<unit>/<sub>`. Three branch
conventions exist on disk (`misakwa/<sub>`, `misakwa/<unit>-<sub>`,
`misakwa/agents-<sub>`). For new work use `misakwa/<unit>-<sub>`, the
majority form and the one the workspace CLAUDE.md prescribes. Pass it with
`--branch`: the default would be `misakwa/<unit>/<sub>`, three segments,
which nothing else uses.

A parent that holds only sub-units (`INC-355`) is not a unit. `show`, `pr`,
`review`, `agent` accept the parent name and gather the sub-units; `done`
refuses it and lists the sub-units to settle one by one.

## Read the board

Buckets, in the order printed: BLOCKED (an agent waits on input), READY (an
agent reported done), MERGEABLE (a PR is approved), BROKEN (a check fails),
WAITING (a PR is open), ACTIVE, SETTLE (every checkout is integrated per
`wt list`), COLD, NOTES (no checkout), UNKNOWN (checkouts `wt` cannot see).
`--bucket <name>` filters; `--json` for parsing.

- The `wt list` and `gh pr list` answers are cached for 300 s. After a push,
  merge, or new checkout, pass `--refresh`, or the board and `done` judge
  stale facts. Only `board` has `--refresh`; `show`, `pr`, `sync`, `done`
  reuse whatever the cache holds.
- `age` is the mtime of the unit root and its checkouts, not activity. A
  unit committed to daily can read 45 d; ACTIVE vs COLD (30 d) follows it.
- PRs are matched by branch name with no author filter. A checkout of
  another person's branch shows their PR as MERGEABLE or BROKEN, and
  "N unanswered" counts threads Michael opened and they answered. Check
  the author before acting on MERGEABLE.
- `?n/m outside workspace` marks checkouts `wt list` did not report: a repo
  outside the workspace, or a cache older than the checkout.
- `gh pr list` runs with `--limit 300`; platform sits near 295 open PRs. A
  WAITING unit that drops to SETTLE with no merge is a sign the cap dropped
  its PR.
- `transcript-check` is ignored on purpose (it fails on every PR).
  `--ignore-check <name>` adds more.

## Finish a unit

`workctl done <unit>` is a dry run; nothing changes without `--apply`. The
seven steps, each of which stops the run: 1 uncommitted changes, 2 branches
and PR state, 3 open PR (`--allow-open-pr` to pass), 4 busy agents (idle
panes are closed on `--apply`), 5 archive, 6 `wt remove --reap` per checkout,
7 close the herdr workspace.

Always in this order:

1. `workctl board --refresh` so the bucket reflects the merge.
2. `workctl done <unit> --dry-run`. Read step 5 and step 6 in full.
3. Count the worktrees under the unit and compare with the checkouts the
   dry run listed:
   `find <root>/work/<unit> -name .git | wc -l`.
   Equal counts: continue. More on disk than listed: stop. Step 5 moves
   every non-checkout entry at the unit root into `<root>/.archive/<unit>/`,
   directories included, so a directory that holds a deeper checkout is
   moved with its live worktrees inside, and their `.bare/worktrees/*`
   links break. Move those worktrees out (`git worktree move`, unverified
   here) or settle by hand.
4. `workctl done <unit> --apply` (asks once; `--yes` skips the prompt).

`--force-bucket` bypasses the board check only, in both its forms: a bucket
that is not SETTLE, and a unit the board does not list or a board that could
not be read at all. Steps 1, 3, 4 still stop the run, and step 2 asks GitHub
directly, so a forced run still reads real PR state. Use it when the board is stale and
`--refresh` was not enough, or for a COLD detached-HEAD unit with nothing to
keep. Refuse it when the bucket is WAITING, MERGEABLE, or BROKEN (a real PR
is open) and when the bucket is NOTES (the archive step is the whole action;
do it by hand so the notes land where he wants them).

`wt remove` deletes the branch only when it is merged. An abandoned or
closed-unmerged branch stays behind. His intent is normally "delete the
worktree and the branch", so after `done` on such a unit run
`git -C <root>/<repo> branch -D <branch>` and say so.

Step 1 points at `workctl review <unit> --working` for uncommitted changes.
That view is `git diff`, so untracked files (`??` lines) never appear in it;
read them with `git -C <checkout> status --porcelain` instead.

`sweep` runs `done` per unit of one bucket against a single board snapshot.
Without a tty every unit is skipped; pass `--yes` only after a dry run.

## Boundaries

- **Repos outside the workspace.** `new` refuses them ("unknown
  repository"), the board marks the unit `?n/m outside workspace`, and
  `done` step 6 stops on them. Create and remove those worktrees with
  `git -C ~/Projects/<repo> worktree add|remove`, then settle the rest.
- **Checkouts outside the model.** `wt list --format json` run in
  `<root>/<repo>/master` reports every worktree, including siblings in
  `<root>/<repo>/<slug>` and units at `<root>/<name>/<repo>`. The board never
  mentions them. When a same-named directory also exists under `work/`
  (`packaged-agentic-setup` today), `workctl agent <name>` starts a fresh
  agent there and misses the sessions recorded at the real directory.
- **herdr.** workctl talks to the running session (`herdr session list
  --json`), or the one `WORKCTL_HERDR_SESSION` names. Two sessions exist
  (`default`, `vectara`); workspaces created in one are not visible from the
  other. `go`, `new --agent`, `sync`, and `done` step 7 need herdr running;
  everything else works without it.
- **Agent sessions.** `agent` resumes only sessions recorded at the unit
  root. Sessions started one level down are listed by `agent-sessions
  <unit>` as "below root"; `--move-to-root --apply` refiles them (claude and
  pi only).

## When workctl is the wrong tool

- An existing branch or PR: the attach recipe above, not `workctl new`.
- A repo outside the workspace: plain `git worktree`.
- A unit with checkouts deeper than `work/<unit>/<sub>/<repo>`: settle it by
  hand with `wt remove` or `git worktree remove` per checkout, then move the
  notes yourself.
- A throwaway checkout for one command (bisect, a build): `git -C
  <root>/<repo> worktree add <root>/work/<unit>/<repo> ...` so it still
  shows on the board, and remove it the same way.
