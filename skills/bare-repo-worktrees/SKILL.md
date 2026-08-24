---
name: bare-repo-worktrees
description: Layout and commands for Michael's bare-repo workspaces (a workspace dir holding bare git repos with .bare/ plus a shared work/ folder of worktrees). Use when creating, listing, or removing git worktrees, starting a new branch of work, or when the cwd contains a .bare directory or a work/<name>/<repo> path.
---

The **workspace** is the top-level directory holding one or more **bare** git
repos plus a shared `work/` folder — it is not itself a git repo (no `.git` at
its root). Each bare repo folder under it has `.bare/` (git data), a `.git`
gitdir file pointing at `.bare/`, and a primary worktree named for the default
branch (`main` or `master`).

Layout:
```
<workspace>/                # the workspace root (NOT a git repo)
├─ <repo>/                  # a bare repo folder
│  ├─ .bare/                #   git data (the actual bare repo)
│  ├─ .git                  #   gitdir file: `gitdir: ./.bare`
│  └─ <main|master>/        #   primary worktree (the repo's default branch)
├─ <other-repo>/            # same shape
└─ work/<name>/             # one unit of work; one subfolder per repo involved
   └─ <repo>/               #   worktree on branch misakwa/<name>
```

- **Never edit files in a bare repo root** — always work inside a worktree
  (the primary one or a `work/<name>/<repo>/`).
- Branches are named `misakwa/<name>`. For cross-repo work, use the **same
  branch name in every repo**.
- All feature worktrees go under `work/<name>/`, one subfolder per repo. The
  layout is flat: `misakwa/` lives on the branch, never as a directory.

> Always pass the worktree path as an **absolute** path. With `git -C <repo>`,
> a relative worktree path resolves against `<repo>`, not your cwd — landing
> the worktree inside the bare root instead of `work/`.

Create (repeat per repo for cross-repo work, same `<name>`/branch; base off the
repo's default branch, `origin/main` or `origin/master`):
```bash
git -C <workspace>/<repo> \
    worktree add <workspace>/work/<name>/<repo> \
    -b misakwa/<name> origin/<main|master>
```
Then `cd work/<name>` and start ONE session — it sees each repo as a subdir, so
all are in scope with no `/add-dir`.

Manage:
- Fetch before branching: `git -C <repo> fetch --all --prune`.
- List: `git -C <repo> worktree list`.
- Remove: `git -C <repo> worktree remove work/<name>/<repo>`, then
  `git -C <repo> branch -d misakwa/<name>` (`-D` to force).
- Git may append a number to a worktree's internal admin name when two share a
  basename — harmless; the on-disk paths are what matter.
