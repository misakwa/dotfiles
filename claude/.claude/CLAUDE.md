# Global preferences for Claude (Michael)

## Coding style
- **Naming**: descriptive of *what*, not *why*. Avoid `Simple*` / `Basic*` /
  `Easy*` prefixes — e.g. `HttpServer`, not `SimpleHttpServer`.
- **Tests**: prefer real dependencies (testcontainers, real DB) over mocks
  when feasible.
- **Always run the project's formatter and build/test** before considering
  work done. Don't rely on the user to catch lint/build failures.
- **Comments**: default to none, and when one is necessary keep it pithy —
  one short line that captures a non-obvious WHY (hidden constraint,
  counter-intuitive value, workaround). Don't re-state values written
  right below, don't label a block's purpose ("prod-only ...", "added for
  the X flow"), don't narrate helper / merge / framework internals, don't
  reference the current PR or task — those belong in the PR description,
  not in the file. If you're tempted to write a paragraph, write it in
  the PR description instead.

## Git workflow
- **Commit logical units together.** Bundle changes that belong to the same
  piece of work into a single commit; don't split a coherent change across
  multiple commits, and don't combine unrelated changes.
- **Branch prefix**: always create new branches under `misakwa/` — e.g.
  `misakwa/fix-auth-redirect`, `misakwa/add-cdc-projection`.
- **Never post comments on my behalf.** Do not post or reply to PR/issue
  comments, review threads, or bot threads on GitHub (or any other platform)
  as me. When a comment warrants a response, draft it and show it to me — I
  decide whether and what to post. (Editing the PR title/body/labels when
  finalizing a PR is fine; conversational comments are not.)

## Research: check native first
Before recommending or building a custom / third-party solution, exhaustively
check the tool's own first-party docs — actions reference, config reference,
dedicated feature pages — and verify what's built in. Only then consider
plugins or custom code.

When delegating research, phrase the question neutrally: "does <tool>
natively support X, and if not, what third-party options exist?" — never
"is there a plugin for X?". The framing biases the search away from
first-party features. Treat any "no native equivalent" claim as something
to verify against the tool's own reference before acting on it.

## Auto-mode batch review via kitty diff
At the end of an auto-mode turn, if ALL of these hold —
(a) auto mode is active,
(b) the edit batch touched ≥3 files OR changed ≥100 lines,
(c) cwd is inside a git repo,
(d) `command -v kitty` succeeds —
then run via Bash:

```bash
if [ -n "$KITTY_LISTEN_ON" ]; then
  # Inside kitty with a working remote-control socket — open a new tab in
  # the existing kitty window so the user can flip to it on their schedule.
  kitten @ launch --type=tab --tab-title='claude review' --cwd=current \
    git difftool --dir-diff -y HEAD
else
  # No kitty remote control (ghostty, iTerm, SSH, or kitty without
  # listen_on). Spawn a fresh kitty OS window for the review.
  kitty --detach -- bash -c "cd \"$PWD\" && git difftool --dir-diff -y HEAD"
fi
```

Then tell the user: "opened a kitty review tab/window — `q` when done."

Skip the launch for small edits, non-auto sessions, repos with no HEAD, or
when kitty isn't installed — fall back to a one-line text suggestion:
"to review, run `git difftool HEAD` in kitty."

## Bare repo workspaces + worktrees
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
- Branch naming follows the **Git workflow** section (`misakwa/<work>`). For
  cross-repo work, use the **same branch name in every repo**.
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
