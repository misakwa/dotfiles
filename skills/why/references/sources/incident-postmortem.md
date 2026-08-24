# Incident & Postmortem Context

Not a separate source, a **cross-cutting angle**. Incidents often motivate defensive code ("we added this check after the X outage"), so if the target looks defensive (null checks, retry logic, timeout handling, rate limiting, feature flags), specifically hunt for incident history across every available source:

- **Git**: commits with messages like "fix for incident", "add defensive check", "revert" followed by "re-apply with..." are strong signals
- **`gh`**: PRs and issues labeled `incident`, `sev-*`, `postmortem`, `reliability`; PR bodies that link an incident ID or postmortem
- **In-repo docs**: `docs/`, `postmortems/`, ADRs, CHANGELOG entries mentioning the target file, feature, or error string
- **Tests**: regression tests added in the same PR whose names encode the failure ("test_no_retry_storm_on_upstream_5xx")
- **Other reachable systems** (issue tracker, docs wiki, chat, observability, error tracking): search for the incident ID, the target symbol, and the ship date window

If you find an incident link, fetch the full postmortem. Postmortems typically have an "Action Items" section that ties directly to code changes. When multiple sources corroborate (an incident ID appears in a ticket, which appears in a postmortem, which links to the target PR), the evidence is especially strong.

Worth spending time on when the code's defensive character makes an incident-driven origin plausible. Skip it for code that doesn't look defensive.
