# Global preferences (Michael)

Shared by Claude Code (`~/.claude/CLAUDE.md`) and Codex (`~/.codex/AGENTS.md`).
Skills in `~/.agents/skills` carry the engineering method (tdd, diagnosing-bugs,
grilling, spec-review, principle-*, unslop, how/why, …); this file holds only
what is specific to me.

## Coding style
- **Naming**: describe *what*, not *why*. No `Simple*` / `Basic*` / `Easy*`
  prefixes — `HttpServer`, not `SimpleHttpServer`.
- **Tests**: real dependencies (testcontainers, real DB) over mocks when feasible.
- **Comments**: default to none. When one is needed, one short line with a
  non-obvious WHY (hidden constraint, workaround). Never label blocks, narrate
  internals, restate values, or reference the current PR/task.
- Run the project's formatter and build/tests before calling work done.

## Git workflow
- One commit per logical unit; never split a coherent change or bundle
  unrelated ones.
- Commit messages: imperative subject plus at most a few terse bullets. No
  essays, no commit hashes. Rationale goes in the PR description.
- Branches always under `misakwa/` — e.g. `misakwa/fix-auth-redirect`.
- **Never post comments as me** on GitHub or elsewhere (PR/issue comments,
  review threads). Draft the reply and show it to me. Editing a PR's own
  title/body/labels when finalizing it is fine.
- Bare-repo workspaces (`.bare/` + `work/<name>/<repo>` worktrees): follow the
  `bare-repo-worktrees` skill.

## Research: check native first
Before recommending or building a custom / third-party solution, exhaustively
check the tool's own first-party docs and verify what's built in. When
delegating research, phrase it neutrally — "does <tool> natively support X,
and if not, what third-party options exist?" — never "is there a plugin for
X?". Verify any "no native equivalent" claim against the tool's own reference.
