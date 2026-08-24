# Source playbooks

The why skill gives each investigator a single source-specific playbook. Source control is always available; the others apply only when that system is reachable from the environment, and the git playbook is the template to adapt.

| Source | Playbook |
|---|---|
| Source control history (git, `gh`, in-repo docs, tests, comments) | [`code-archaeology.md`](./sources/code-archaeology.md) |
| Issue / ticket tracker, long-form docs, team chat, observability, error tracking | Adapt `code-archaeology.md`: what the source contains, how to search it, what good evidence looks like, pitfalls, what to return |

Cross-cutting:

- [`incident-postmortem.md`](./sources/incident-postmortem.md). Add this if the target code looks defensive (null checks, retry, timeout, rate limit, feature flag, egress guard, OOM handler).
