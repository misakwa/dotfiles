# Global engineering rules (Michael)

## Coding style
- **Naming**: describe *what*, not *why*. No `Simple*` / `Basic*` / `Easy*`
  prefixes — e.g. `HttpServer`, not `SimpleHttpServer`.
- **Tests**: prefer real dependencies (testcontainers, real DB) over mocks when
  feasible.
- **Always run the project's formatter and build/test before considering work
  done.** Don't rely on me to catch lint/build failures.

## Git workflow
- **Commit logical units together.** Bundle changes that belong to the same
  piece of work into one commit; don't split a coherent change, don't combine
  unrelated ones.
- **Branch prefix**: create new branches under `misakwa/` — e.g.
  `misakwa/fix-auth-redirect`.

## Research: check native first
Before recommending or building a custom / third-party solution, exhaustively
check the tool's own first-party docs and verify what's built in. Only then
consider plugins or custom code. When researching, phrase questions neutrally
("does <tool> natively support X, and if not what third-party options exist?")
— never "is there a plugin for X?". Treat any "no native equivalent" claim as
something to verify against the tool's own reference before acting.

## Token discipline (this stack)
- Default to the **quick path** for small/low-risk tasks. Reserve the full
  Superpowers loop (brainstorm → plan → TDD → review → finish) for risky or
  ambiguous work where planning prevents rework.
- Use context7 / pi-knowledge for docs on demand — don't pre-load.
