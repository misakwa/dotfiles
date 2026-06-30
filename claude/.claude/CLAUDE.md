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
