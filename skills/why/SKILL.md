---
name: why
description: "Use for 'why does X work this way', 'why we picked Y', design rationale, regressions, postmortems, or data-backed thresholds. Digs through source control history (git, gh, code comments, tests, in-repo docs) and returns a cited, confidence-calibrated read on decisions and tradeoffs. Use how for runtime behavior."
---

# Why

Investigate the motivation and intent behind code. Why was it built this way? What edge cases were considered? What product, business, or operational constraints shaped the design? What alternatives were rejected, and why?

Companion to the `how` skill. `how` answers what the code does and how it works. `why` answers what forces led to its shape.

## Operating Posture

Operate as a careful, cautious, precise investigator. Think like a detective piecing together a historical case from fragmentary records. When the record is thin, say so.

Concretely:

- **Evidence before narrative.** Collect the pieces first, then see what story they support. Never pick a story and recruit the evidence that fits it.
- **Precision over polish.** Prefer the exact quote and citation over a smooth paraphrase. A reader should be able to follow any claim back to its source and verify it in under a minute.
- **Consider what you haven't seen.** The evidence you find is a sample, not the whole truth. Before concluding, ask what you would expect to see if an alternative explanation were true, and whether you looked for it.
- **Name the gaps.** If a thread goes cold, a source isn't searchable, or a question has no answer, document the gap. Don't paper it over with an authoritative-sounding guess.
- **Hedge on purpose.** When evidence is indirect, your language should signal it ("appears to", "likely", "suggests"). Confidence-matching phrasing is a feature of the output, not a stylistic choice the synthesizer may override.
- **No shortcut by code-reading.** The code tells you what it does, rarely why it exists. Resist inferring intent from code shape.

## Core Epistemics

This skill builds a **patchwork understanding** from fragmented historical evidence. Tickets go stale. Commit messages lie. People change their minds between the PR description and the implementation. The original author may have left the company.

Be ruthlessly honest about what you know versus what you're inferring. The goal is not a satisfying story; it is to surface evidence, calibrate confidence, and let the user decide.

- **Cite everything.** Every claim about intent should reference a specific commit hash, PR number, ticket ID, doc path, or code comment. If you can't cite it, it's inference, not fact, and must be labeled as such.
- **Prefer "appears to" over "because".** Hedge when evidence is indirect.
- **Surface contradictions.** If two sources disagree, show both.
- **Acknowledge gaps.** An honest "we couldn't find out why" beats a confident guess.
- **Multiple hypotheses are valid.** When the evidence fits several stories, present them all with the evidence for each.
- **Beware rationalization.** Code that makes sense today may have been written for reasons that no longer apply. Don't retrofit intent.

Read `references/epistemics.md` for the full confidence framework and phrasing guide. The synthesizer must follow it.

## Step 1. Understand the Target and the Question

Parse what the user is asking. The **target** is usually a chunk of code, a pattern, a feature, or a named design decision. The **question** is usually one of:

- "Why was X designed this way?" Design rationale.
- "Why do we do X instead of Y?" Tradeoff or alternatives.
- "What edge cases motivated this?" Defensive reasoning.
- "What business or product constraint led to this?" External forcing function.
- "Why does this code still exist?" Dead-code territory.
- "What's the history of X?" Broad archaeological sweep.

If the target is vague, make your best guess from conversation context (open files, recent edits, what was just discussed). State your interpretation briefly so the user can redirect if you're off, then proceed.

## Step 2. Establish the Code Anchor

Before investigating, anchor the investigation in concrete code. You need:

- The relevant file path(s) and line range(s)
- The key symbols (function names, class names, constants)
- An initial commit list. The last few commits touching the target.
- PR numbers from merge commits (pattern `(#1234)` in the subject line)

Build this inline. It's cheap, and every investigator needs it.

```bash
# Blame target lines for last-touch commits
git blame -L <start>,<end> <file>

# Full file history, with patches, through renames
git log --follow -p -- <file>

# Last N commits touching the file, PR numbers visible
git log --oneline -20 -- <file>

# Extract PR numbers from a commit message
git log -1 --format=%B <commit>
```

Pull PR bodies and discussion via `gh` for any substantive commits:

```bash
gh pr view <number> --json title,body,author,createdAt,mergedAt,labels,closingIssuesReferences,comments,reviews
```

Capture this as seed context (file paths, symbols, commits, PR numbers, linked ticket IDs). Pass it to the investigators so they don't rediscover it.

## Step 3. Investigate

Source control is the one source always available: git history, `gh` for PRs and issues, inline comments, tests, and in-repo docs (ADRs, CHANGELOGs). It is best at surfacing *implementation-time rationale captured during review*: PR descriptions stating the problem, review threads debating alternatives, inline comments encoding non-obvious constraints, test names that encode motivating edge cases, and commit messages linking tickets or incidents.

Spawn a read-only investigator subagent (Claude Code: Agent tool with the Explore or general-purpose type; Codex: run the steps inline if no subagent tool is available). For a broad sweep, split the work across 2-3 investigators by angle (e.g. commit/PR history, in-repo docs and comments, tests and co-changed files) and launch them in a single message.

Each investigator gets:
1. The base prompt from `references/investigator-prompt.md`
2. The playbook `references/sources/code-archaeology.md`
3. The cross-cutting `references/sources/incident-postmortem.md` **if the target code looks defensive** (null checks, retry logic, timeout handling, rate limiting, feature flags, egress guards, OOM handlers)
4. The code anchor from Step 2
5. The user's original question

If other evidence systems are reachable from this environment (an issue tracker, a docs wiki, chat, observability, error tracking), treat each as an additional source: one investigator per source, same prompt, adapted from `references/source-playbook.md`. If they are not reachable, say so in Sources Consulted. That absence is a gap, not a choice.

If the target is a single trivial commit whose PR description already contains the complete answer, you may answer inline. Say so explicitly. This should be rare.

## Step 4. Synthesize

Spawn one synthesizer subagent (Claude Code: Agent tool with the general-purpose type; Codex: run inline). The synthesizer may read the codebase and run `git`/`gh` to spot-check citations, but must not write anything.

The synthesizer gets:
1. The investigator findings, including any null results and any sources skipped with justification
2. The code anchor from Step 2
3. The user's original question
4. The epistemics framework from `references/epistemics.md`
5. The synthesizer prompt template from `references/synthesizer-prompt.md`

Its job is the final output: a confidence-weighted, evidence-cited narrative with clearly separated "what we know" and "what we're inferring" sections, plus honest acknowledgment of gaps.

## Step 5. Present

Take the synthesizer's output and present it to the user. You may lightly edit for clarity or add context from the conversation, but **do not rewrite the confidence language**. The epistemic framing is the product. Dropping the hedges to sound more authoritative is the exact failure mode this skill exists to prevent.

## Output Format

The final output uses this structure. Adapt as needed, but keep the confidence separation intact.

**The Question**. Restate what the user asked, concisely.

**The Code in Question**. File paths, line ranges, and key symbols. One or two lines so the reader is anchored.

**What We Found (direct evidence)**. Claims with explicit citations (PR #, ticket ID, doc path, commit hash, code comment with file:line). Each bullet is a thing we have textual evidence for. Quote or paraphrase the source.

**What We Can Reasonably Infer**. Claims well-supported by indirect evidence, but not explicitly stated anywhere. Each bullet must explain the inference chain: "Given A and B, it's likely that C." Use hedged language.

**Competing Hypotheses**. If the evidence fits multiple stories, list them with the evidence for and against each. Don't force a winner. (Skip if there's a clear answer.)

**What We Don't Know**. Explicit gaps. Questions the evidence didn't answer. Searches that came up empty. "We searched PRs and commits for 'rate limit' and found no discussion of this specific threshold" is more useful than "we don't know why."

**Sources Consulted**. One line per source, including the ones that returned nothing or were unavailable. Format: `- <Source>: <what was searched>. <what was found, or "no relevant results," or "skipped. reason">.`

Example:
- Source control (git/gh): `git log --follow backend/retry.ts`, PRs #49074, #47812. Found PR #49074 introduced exponential backoff and linked ENG-4421.
- In-repo docs and comments: searched `docs/` and inline comments for "retry", "backoff". Found no ADR; one comment at `retry.ts:41` names the upstream 5xx incident.
- Issue tracker: skipped. Not reachable from this environment. Gap: ENG-4421 not read.

After the Sources Consulted block, if the user's `why` question is a precursor to actually changing this code, convert the lineage findings into a Preserve / Change / Avoid / Risk constraint set suitable for planning the change.

## Common Failure Modes to Avoid

- **Confident storytelling**. A bullet with no citation goes in "inferred" or "hypotheses," not "what we found."
- **Citing the code as evidence for its own intent**. "Handles the null case because it checks for null" is mechanics, not motivation.
- **Recency bias**. The current shape is often the accretion of many earlier decisions. Trace back.
- **Sycophantic agreement**. If the user suggests a reason, treat it as a hypothesis and check the evidence independently.
- **Skipping the gaps section**. An honest accounting of what you couldn't find out is part of the value.

## Reference Files

- `references/epistemics.md`. Confidence tiers and phrasing guide. The synthesizer must follow it.
- `references/investigator-prompt.md`. Base prompt template for investigator subagents.
- `references/source-playbook.md`. Index of source playbooks.
- `references/sources/code-archaeology.md`. The git + in-repo playbook. `references/sources/incident-postmortem.md` is the cross-cutting incident angle.
- `references/synthesizer-prompt.md`. Prompt template for the synthesizer subagent, including the output format.
