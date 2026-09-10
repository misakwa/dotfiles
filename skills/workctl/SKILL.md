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

A unit holds checkouts at depth 1 and 2 only. A worktree anywhere else
(`work/<unit>/<a>/<b>/<repo>`, `<root>/<repo>/<slug>`, `<root>/<name>/<repo>`)
belongs to no unit: the board lists it under OUTSIDE, `show` lists it as
"deeper than the unit", and `done` refuses to touch the directory above it.
`workctl adopt` brings it in.

## Intent to command

| Intent | Command |
|---|---|
| What am I working on | `workctl` (same as `workctl board`); `--refresh` after a push, merge, or new checkout |
| Show me this unit | `workctl show <unit>` |
| Start a unit on a new branch | `workctl new <unit> --repo <repo> [--repo <repo2>] [--base <ref>]` |
| Worktree for an existing branch or PR | `workctl new <unit> --repo <repo> --from <branch\|pr:N\|PR URL>` |
| Notes-only unit (incident, investigation) | `workctl new <unit>` |
| Add a repo to an existing unit | `workctl new <unit> --repo <repo2>` (or `--from` for an existing branch) |
| Sub-unit | `workctl new <unit>/<sub> --repo <repo>`; branch defaults to `misakwa/<unit>-<sub>` |
| Bring a stray checkout under work/ | `workctl adopt` to list; `workctl adopt <path> [--unit NAME]`, then `--apply` |
| Open the unit in herdr | `workctl go <unit>`; `workctl go` alone lists unit names |
| Resume the agent in a unit | `workctl agent <unit>` (`--new`, `--pick`, `--kind codex`) |
| Which sessions does a unit hold | `workctl agent-sessions <unit>`; `--orphans` (removed units); `--outside` (stray checkouts) |
| PRs, failing checks, review threads | `workctl pr <unit> --threads` (`--draft` prints reply drafts; it never posts) |
| Review the whole unit as one diff | `workctl review <unit>` (opens hunk); `--staged`; `--working` |
| Sidebar tokens in herdr | `workctl sync` (the wt post-switch hook already runs it) |
| Finish a unit | `workctl done <unit> --refresh --dry-run`, then `--apply` |
| Finish every SETTLE unit | `workctl sweep --refresh --dry-run`, then `--apply --yes` |

`workctl <unit>` and `workctl board <unit>` both stop and point at
`workctl show <unit>`. Every command takes `--root DIR`, the directory that
holds the bare repos; it is never the unit name and never the herdr workspace.

## Start a unit

`workctl new <unit> --repo <repo>` creates branch `misakwa/<unit>` in each
repo, checks it out at `work/<unit>/<repo>` through `wt switch --create`,
and creates a herdr workspace at the unit root when herdr runs. `--agent`
starts claude in that workspace; `--no-herdr` skips herdr. `--dry-run`
prints the exact `wt` command and performs the same refusals as a real run.

- An existing unit is extended: checkouts already in place are kept, only
  the missing repo is created. The new branch follows the default name, so
  when the unit's existing checkout sits on a different branch (INC-355's
  sub-units use `misakwa/<sub>`), pass `--branch` to match it.
- `--base <ref>` applies to every `--repo`. For a stacked branch pass one
  `--repo` per call.
- A unit whose root is itself a checkout takes no second repo: "a worktree
  cannot hold another worktree".
- Repos outside the workspace are refused ("unknown repository"); see
  boundaries.

### Attach an existing branch or PR

This is the most common start: a PR of his to continue, a colleague's PR to
review, a branch pushed from elsewhere.

```bash
workctl new <unit> --repo <repo> --from misakwa/<branch>   # fetches origin first
workctl new <unit> --repo <repo> --from pr:<N>             # wt fetches the PR head
workctl new <unit> --repo <repo> --from https://github.com/vectara/<repo>/pull/<N>
```

`--from` needs `--repo` and takes no `--base` or `--branch`. When the branch
is already checked out somewhere, `new` refuses and names the path; that is
an `adopt` case. Creating the branch by hand and then running `new` without
`--from` also refuses, with the `--from` line to run.

Two things to avoid, because both land the checkout outside every unit:
bare `wt switch <branch>` follows his config template and lands at
`work/misakwa-<branch>/<repo>`; `git worktree add <slug>` from inside
`<root>/<repo>/` lands beside `master/`. Both then need `adopt`.

### Sub-units

`work/<unit>/<sub>/<repo>` is sub-unit `<unit>/<sub>`, branch
`misakwa/<unit>-<sub>` by default. Two older conventions exist on disk
(`misakwa/<sub>` under INC-355, `misakwa/agents-<sub>` under
api-test-suite-failures); pass `--branch` only to match one of those when
extending such a unit. A parent that holds only sub-units is not a unit:
`show`, `pr`, `review`, `agent` accept the parent name and gather the
sub-units; `done` refuses it and lists the sub-units to settle one by one.

### Adopt a stray checkout

`workctl adopt` lists every worktree `wt list` knows that no unit holds,
with the unit each would get (`<root>/<repo>/<slug>` becomes
`work/<slug>/<repo>`; `<root>/<name>/<repo>` becomes `work/<name>/<repo>`).
`workctl adopt <path>` is a dry run; `--apply` moves it with
`git worktree move`, which keeps the `.bare/worktrees/*` link. It refuses a
dirty checkout, an existing destination, and a path already under `work/`
(the depth-3 checkouts under `storage-sizing-heuristics/capacity-page` stay
where they are; settle them by hand). Agent sessions stay recorded at the
old path: `workctl agent-sessions --outside` lists them, and `workctl agent`
refuses a name that exists both under `work/` and at the workspace root
until one of them is adopted or removed.

## Read the board

Sections, in the order printed: BLOCKED (an agent waits on input), READY
(an agent reported done), MERGEABLE (his PR is approved), BROKEN (a check
fails), REVIEW (the PR on this checkout is someone else's; the author is
shown, `by halfriced`), WAITING (his PR is open), ACTIVE, SETTLE (every
checkout is integrated per `wt list`), COLD, NOTES (no checkout), UNKNOWN
(checkouts `wt` cannot see, or `+N checkouts deeper than the unit`), and
OUTSIDE (checkouts on no unit, grouped by location, with their PRs).
`--bucket <name>` filters and validates; `--json` gives the same rows with
`bucket` set.

- REVIEW means read, reply, approve; never merge or settle from it. "N
  unanswered" on a MERGEABLE row counts unresolved threads on his own PR.
- `?n/m outside workspace` marks checkouts `wt list` did not report: a repo
  outside the workspace, or a cache older than the checkout.
- `age` follows the newest commit or agent session file in the unit.
- `transcript-check` is ignored on purpose (it fails on every PR);
  `--ignore-check <name>` adds more.

### What is cached

`wt list` and `gh pr list` answers are cached for 300 s. `board`, `show`,
`sync`, `adopt`, `done`, and `sweep` read that cache and take `--refresh`;
`agent-sessions --outside` reads it without a `--refresh`. `pr` calls gh
directly and is always live; `review`, `agent`, `go`, and `new` read git or
herdr directly. After a push, a merge, or a checkout made by hand, pass
`--refresh` to the next cached command, or it judges the old facts.

## Finish a unit

`workctl done <unit>` is a dry run; nothing changes without `--apply`. The
seven steps, each of which stops the run: 1 uncommitted changes, 2 branches
and PR state (asked of GitHub directly), 3 open PR (`--allow-open-pr` to
pass), 4 busy agents (idle panes are closed on `--apply`), 5 archive the
notes to `.archive/<unit>/`, 6 `wt remove --reap` per checkout, 7 close the
herdr workspace.

Always in this order:

1. `workctl done <unit> --refresh --dry-run`. Read every step.
2. Resolve what stopped it. Step 1 prints the `git status --porcelain`
   line to run; `workctl review <unit> --working` shows the same changes,
   untracked files included. Step 5 refuses when a directory at the unit
   root holds worktrees the unit does not model, names each one, and exits
   1 in dry run and apply alike; move them out or settle them by hand.
3. `workctl done <unit> --apply` (asks once; `--yes` skips the prompt).
4. Run the `git -C <root>/<repo> branch -D <branch>` lines the run prints
   after step 6. `wt remove` deletes a branch only when it is merged; his
   intent is normally "delete the worktree and the branch".

`--force-bucket` bypasses the board check only, in both its forms: a bucket
that is not SETTLE, and a unit the board does not list or a board that
could not be read. Steps 1, 3, 4, and 5 still stop the run, and step 2 asks
GitHub directly, so a forced run still reads real PR state. The refusal
offers `--refresh` first; use that. Reach for `--force-bucket` for a COLD
detached-HEAD unit with nothing to keep, or a NOTES unit he wants archived.
Refuse it when the bucket is WAITING, MERGEABLE, or BROKEN (his PR is open)
or REVIEW (the checkout is someone else's PR).

`sweep` runs `done` per unit of one bucket against a single board snapshot
and asks before each unit. Without a terminal it says so up front and skips
every unit; pass `--yes` only after a dry run.

## Boundaries

- **Repos outside the workspace** (`ti-provisioning`). `new` refuses them,
  `adopt` never lists them (`wt list` covers the bare repos only), the board
  marks the unit `?n/m outside workspace`, and `done` step 6 stops on them. Create and remove those worktrees with
  `git -C ~/Projects/<repo> worktree add|remove <root>/work/<unit>/<repo>`,
  then settle the rest.
- **herdr.** workctl talks to the running session (`herdr session list
  --json`), or the one `WORKCTL_HERDR_SESSION` names. Two sessions exist
  (`default`, `vectara`); workspaces created in one are not visible from the
  other. `go` needs herdr; `new --agent`, `sync`, and `done` step 7 report
  "not running" and continue without it.
- **Agent sessions.** `agent` resumes only sessions recorded at the unit
  root. Sessions started one level down are listed by `agent-sessions
  <unit>` as "below root"; `--move-to-root --apply` refiles them (claude and
  pi only; codex files by date).

## When workctl is the wrong tool

- A repo outside the workspace: plain `git worktree`, as above.
- A unit with checkouts deeper than `work/<unit>/<sub>/<repo>`: settle each
  checkout by hand with `wt remove` or `git worktree remove`, then run
  `workctl done` for what is left.
- A throwaway checkout for one command (bisect, a build):
  `workctl new <unit> --repo <repo> --from <ref>` still, so it shows on the
  board and `done` removes it; a hand-made worktree needs `adopt` first.
