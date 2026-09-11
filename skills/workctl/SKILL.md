---
name: workctl
description: Drive workctl, the CLI for units of work in a workspace (work/<unit>/<repo> checkouts, herdr workspaces, agent sessions). Use when the user says "workctl", starts or finishes a unit of work, asks what they are working on, wants a worktree for an existing branch or PR, or when the cwd sits inside a work folder beside git repositories.
---

workctl runs in any folder that holds git repositories beside a work folder.
The rule is one sentence: **the repositories and the work folder are siblings under the root.**

```
<root>/                        # the workspace root
├─ <repo>/                     #   a git repository: .bare + worktrees, or a plain clone
├─ <repo2>/
├─ work/                       #   the work folder, sibling of the repos, name configurable
│  ├─ <unit>/<repo>/           #     unit, depth 1
│  └─ <unit>/<sub>/<repo>/     #     sub-unit "<unit>/<sub>", depth 2, the limit
└─ .archive/<unit>/            #   where `workctl done` moves the notes
```

A **unit** is one directory under the work folder, derived from the folder layout alone; nothing is registered. The unit root holds the notes and is where agents start.

## Ask the CLI

This skill carries only what `--help` cannot. For flags and arguments, ask the CLI: `workctl` prints the board, `workctl --help` lists every command with a one-line description, `workctl <command> --help` gives that command's flags.

| Intent                                         | Command                     |
| ---------------------------------------------- | --------------------------- |
| What am I working on                           | `board` (or `workctl` bare) |
| Show one unit                                  | `show`                      |
| Start a unit, or add a repo to an existing one | `new`                       |
| Bring a stray checkout under the work folder   | `adopt`                     |
| Open the unit in herdr                         | `go`                        |
| Start or resume the agent in a unit            | `agent`                     |
| Which agent sessions a unit holds              | `sessions`                  |
| PRs, failing checks, review threads            | `pr`                        |
| Review the whole unit as one diff              | `review`                    |
| Refresh the herdr sidebar tokens               | `sync`                      |
| Finish a unit                                  | `done`                      |
| Finish every settled unit                      | `sweep`                     |

`workctl <unit>` and `workctl board <unit>` both stop and point at `workctl show <unit>`.

Attach an existing branch or pull request with `new --from <branch|pr:N|URL>`, the most common start, rather than creating the branch by hand and running `new` without it. When the branch is already checked out somewhere, `new` refuses and names the path; that is an `adopt` case.

## Root resolution

In order: the `--root` flag, discovery from the current directory, then `$WORKCTL_ROOT`. Where you stand beats the variable, so a shell profile can export a default root without overriding the root you are standing in. There is no hard-coded default, workctl stores no list of roots, and `$WORKCTL_WORKSPACE` is gone.

Discovery asks git for the repository's common directory and takes its grandparent, so it works from inside any checkout in either repository layout. When the directory holds no repository, workctl walks up for the work folder and takes its parent.

When a unit name is not in the resolved root, `go` looks in the other roots herdr currently has a workspace in, and refuses to guess when two of them hold the name.

`<root>/.workctl.toml` may set `work-dir`, `archive-dir`, `repos`, `branch-prefix`, `owner`, and `author`. The work folder is `work` by default and may become `.workctl`. By default workctl scans the repositories that already hold a unit plus any the config names; `--all-repos` scans every repository under the root, which matters when the root holds many.

## Sub-units

`work/<unit>/<sub>/<repo>` is the sub-unit `<unit>/<sub>`, branch `<prefix><unit>-<sub>` by default. Depth 2 is the limit.

- A checkout deeper than that belongs to no unit: the board lists it under OUTSIDE, and `done` refuses to touch the directory above it.
- A parent that holds only sub-units is not a unit itself. `show`, `pr`, `review`, and `agent` accept the parent name and gather its sub-units; `done` refuses the parent and lists the sub-units to settle one by one.

## Read the board

Buckets, in print order: BLOCKED (an agent waits on input), READY (an agent reported done), MERGEABLE (the user's PR is approved), BROKEN (a check fails), REVIEW (the PR on this checkout is someone else's), WAITING (the user's PR is open), ACTIVE, SETTLE (every checkout is integrated), COLD, NOTES (no checkout), UNKNOWN (checkouts git cannot see, or deeper than the unit), and OUTSIDE (checkouts on no unit).

**REVIEW means read, reply, approve. Never merge or settle from a REVIEW row.**

Answers from git and `gh` are cached, so after a push, a merge, or a checkout made by hand, pass `--refresh` to the next cached command, or it judges stale facts.

## Dry run, then apply

`done`, `sweep`, and `adopt` are dry runs by default; nothing on disk changes without `--apply`. Run the dry run first, read every line, resolve what stopped it, then apply.

`done` works in this order, and each stage stops the run: uncommitted changes, branch and PR state, an open PR, busy agents, archive the notes, remove each checkout, close the herdr workspace. After a real run, run the `git branch -D` lines it prints: `wt remove` deletes a branch only when it is merged, and the intent is normally to delete the worktree and the branch.

`--force-bucket` bypasses the board check only; every other stage still stops the run. Refuse it when the bucket is WAITING, MERGEABLE, or BROKEN (a PR is still open) or REVIEW (the checkout is someone else's PR).

## Strays

Two moves land a checkout outside every unit: `wt switch <branch>` alone lands at `work/<branch, / replaced by ->/<repo>`, and `git worktree add <slug>` from inside a repository folder lands beside that repository's other worktrees.

The spot for the first one follows the user's own worktrunk `worktree-path` template, not anything workctl controls. That template counts directory levels for the bare layout (`../../`), so in a root made of plain clones a hand-run `wt switch` lands one level too high. workctl is unaffected, because it passes an absolute worktree path per call.

`adopt` is the cure. It lists every stray with the unit each would get, and moves it with `git worktree move` on `--apply`. It refuses a dirty checkout, an existing destination, and a path already under the work folder. Agent sessions stay recorded at the old path; `workctl sessions --outside` lists them.

## Boundaries

- **A repository outside the resolved root.** `new` refuses it, `adopt` never lists it, the board marks the unit `?n/m repos not scanned`, and `done` stops on it. Create and remove those worktrees with plain `git -C <repo> worktree add|remove <root>/work/<unit>/<repo>`.
- **herdr not running.** `go` needs it; `new --agent`, `sync`, and the last stage of `done` report "not running" and continue without it.
- **Agent sessions recorded below the unit root.** `agent` resumes only sessions recorded at the unit root. `sessions <unit>` lists the rest as "below root", and `--move-to-root --apply` refiles them.

## When workctl is the wrong tool

- A repository outside the root: plain `git worktree`, as above.
- A unit with checkouts deeper than depth 2: settle each by hand with `wt remove` or `git worktree remove`, then run `done` for what is left.
- A throwaway checkout for one command (a bisect, a build): still `workctl new <unit> --repo <repo> --from <ref>`, so it shows on the board and `done` removes it. A hand-made worktree needs `adopt` first.

## One worked example

`~/Projects/vectara-bare` is one root, not the definition. It holds two repositories in the bare-repo layout (see `bare-repo-worktrees`, which describes one of the two supported repository layouts, not a requirement) under the branch prefix `misakwa/`.

```
~/Projects/vectara-bare/platform/.bare                  # the repository
~/Projects/vectara-bare/platform/master                 # primary checkout
~/Projects/vectara-bare/work/apiv2-ttl/platform         # unit, branch misakwa/apiv2-ttl
~/Projects/vectara-bare/work/inc-355/router/platform    # sub-unit "inc-355/router"
```
