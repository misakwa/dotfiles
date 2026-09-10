# Work-unit workflow plan

A plan for running many units of work at once across several repositories,
without losing track of the agents, the pull requests, or the notes.

## Terms

Define these once and use them everywhere.

- **Workspace**: the directory that holds the bare repositories and the shared
  `work/` folder. Today this is `~/Projects/vectara-bare`.
- **Unit**: one directory under `work/`. It is one scope of work. A unit can
  hold several checkouts, several sub-units, and unversioned notes. `workctl`
  manages units; it does not manage repositories or branches directly.
- **Checkout**: one git worktree inside a unit.
- **Board**: the ranked list of units that need your attention.
- **Settle**: the act of finishing a unit. It closes the agent threads,
  archives the notes, removes the checkouts, and deletes the merged branches.

## The name

The tool is `workctl`. It follows the convention every operator already knows
from `systemctl`, `journalctl`, and `kubectl`: a domain, then `ctl`. The domain
is `work/`, the directory it manages.

Two earlier names failed. `wk` sat one key from `wt` on the same finger, and
the two tools run against the same directories. `unit` was too vague to carry a
command line on its own.

`workctl` is the tool. A **unit** is still the thing it manages, as defined
under Terms. The two words do different jobs and should not be merged.

## What the scan found

I scanned the workspace on 2026-09-09. These are the real numbers.

- 77 units under `work/`.
- 95 checkouts across 3 bare repositories. Two more, in one unit, come from a
  repository outside the workspace. See "One unit does not fit the layout".
- 18 open pull requests. Four are approved and unmerged. Three date from 2025.
- Eight units hold more than one checkout. One holds three.
- 18 units are already merged into the default branch but still on disk.
- 9 checkouts sit on a detached HEAD, so they carry no branch.
- 4 branch namespaces are in use: `misakwa/`, `oncaller/`, `fable/`, and bare.
- 5 units hold only notes and no checkout at all.
- Neither `wt` nor `herdr` has a configuration file yet. One herdr plugin is
  installed: `jhochenbaum.hunkdiff` v0.3.0.
- The CI signal is broken. See the next section.
- `wt`, `hunk`, and `herdr` were missing from the PATH of every non-interactive
  shell. I fixed this. See "The PATH fix".

## The CI signal is broken

Every open pull request in `provisioning` reports a failed CI status. Only one
of them has a real failure.

The cause is `transcript-check`, an external status check that points at
`https://transcript-check.demo.vectara.dev/help`. It reports `fail` with a
duration of 0 on every pull request. It is not a GitHub Actions job.

Worktrunk reports one aggregate CI status per branch, so this single always-red
check turns the whole repository red. A dashboard that trusts that aggregate
shows eight broken pull requests when the truth is two:

| Pull request | Real failure |
|---|---|
| `provisioning#2607` | `yaml-lint` |
| `platform#5911` | `test` |

`workctl` must therefore hold a list of check names to ignore, and must read the
individual check names rather than the aggregate. The right long-term fix is to
remove or repair `transcript-check` on the repository. Until that happens, the
ignore list carries it.

## Why workctl exists

Herdr's model and this workflow disagree, and no amount of configuration
reconciles them. That disagreement is the reason for this tool.

**Herdr's model: one workspace holds one worktree of one repository.**

I confirmed this three separate ways.

1. In the socket API schema, `WorkspaceInfo.worktree` is a single
   `WorkspaceWorktreeInfo` or null, never a list. That record names exactly one
   `repo_key`, one `repo_root`, and one `checkout_path`.

2. `herdr worktree open` refuses a workspace whose own directory is not a git
   work tree. A unit root, holding checkouts as subdirectories, never is:

   ```
   {"error":{"code":"not_git_worktree","message":"Herdr worktree actions
    require a workspace inside a Git work tree"}}
   ```

3. It also refuses when the target is itself a linked worktree, which is what
   every checkout in this layout is:

   ```
   {"error":{"code":"linked_worktree_source","message":"New and open worktree
    actions start from the repo parent workspace."}}
   ```

Two independent refusals. There is no argument that satisfies both.

**Your model: one unit holds several worktrees across several repositories,
plus files that are in no repository at all.**

Eight units span more than one repository. Five hold only notes and no checkout
whatsoever. Every unit carries unversioned Markdown, scripts, and images beside
its checkouts. Your `bare-repo-worktrees` skill states the intent directly: `cd
work/<name>` and start one session that sees each repository as a subdirectory.

**The consequence.** Of your 66 herdr workspaces, herdr considers 0 bound to a
worktree. The built-in sidebar rows `branch` and `git_status` are therefore
blank on every one, and always will be.

**What workctl does about it.** It stops asking herdr to model a unit, and uses
herdr only for what herdr is good at: panes, agents, focus, and a sidebar.

| Concern | Owner |
|---|---|
| What a unit is | `workctl`, derived from the folder structure |
| Worktrees and branches | `wt`, driven once per repository |
| Pull requests and checks | `gh` |
| Panes, agents, focus | `herdr` |
| Branch and CI state in the sidebar | `workctl sync`, as `$br`, `$pr`, `$ci` tokens |

A herdr workspace for a unit is a plain directory, not a worktree, and that is
deliberate. The state herdr cannot derive arrives as metadata tokens instead:

```
admin-extend-session-503     platform            -              -
api-test-suite-failures      2 repos             -              -
apiv2-delete-errors          platform@detached   -              -
artifactory-jcr-setup        provisioning        #395 approved  ok
```

The sidebar config uses `$br`, `$pr`, and `$ci` rather than the built-ins for
this reason. Do not put `branch` or `git_status` back; they cannot work here.

## One unit does not fit the layout

`workctl show ti-agent-developer` turned this up. That unit holds three
checkouts. One belongs to `provisioning`, inside the workspace. The other two
come from `vectara/ti-provisioning`, an ordinary clone at
`~/Projects/ti-provisioning` with no `.bare` directory, whose worktrees reach
into `vectara-bare/work/ti-agent-developer/`.

You made that arrangement in a rush and do not want to keep it. So `workctl`
does not model it. Repositories are found by scanning the workspace for
`.bare`, and that stays the rule.

What `workctl` does instead is refuse to hide it. A checkout that belongs to no
repository in the workspace is counted and shown, so the unit reads as
suspicious rather than quietly wrong. A unit where every checkout is unaccounted
for lands in the `UNKNOWN` bucket. Today that costs 2 checkouts in 1 unit.

Fix the unit rather than the tool. Either clone `ti-provisioning` into the
workspace as a bare repository beside the other three, or move those two
worktrees out of `work/`. Until then, treat `ti-agent-developer` as reported on
one of its three checkouts.

## The core idea

Build one command line tool, `workctl`. It reads four sources, joins them, and ranks every unit by how much it needs you.

`workctl` never stores its own state. It derives everything from the folder
structure and from what the other tools already know.

### Source 1: worktrunk, for the git facts

Run `wt list --format json` once per bare repository. It returns, for every
branch:

- the checkout path, and whether the checkout is dirty,
- `ahead` and `behind` against the default branch,
- `integration.reason`, which proves that a branch already landed.

Worktrunk also reports `pr` and `checks` when you pass `--full`, but do not use
those two fields. I measured them against the truth and they arrive
incomplete: worktrunk missed the real `yaml-lint` failure on
`provisioning#2607`, and its aggregate CI status is poisoned by the noisy check
described above. Take the git facts from worktrunk and the forge facts from
`gh`.

### Source 2: the GitHub CLI, for the forge facts

Run one call per repository:

```bash
gh pr list --repo <owner>/<repo> --state open \
   --json number,headRefName,reviewDecision,isDraft,url --limit 300
```

Join the result to the checkouts by branch name. The repositories carry 287,
114, and 4 open pull requests, and about 18 of them match a unit.

Do not ask for `statusCheckRollup` in that call. GitHub answers `HTTP 504` on
repositories this size. Fetch the checks separately, and only for the pull
requests that matched a unit:

```bash
gh pr checks <number> --repo <owner>/<repo>
```

Note that `gh pr checks` exits with status 1 when a check failed, which is the
case you care about most. Read its output regardless of the exit status.

### Source 3: herdr

Run `herdr api snapshot`. It returns every live pane with:

- `cwd`, the directory the pane runs in,
- `agent`, the agent kind, and `agent_status`, one of `idle`, `working`,
  `blocked`, `done`, or `unknown`,
- `agent_session`, which carries the Claude session identifier or the Codex
  thread identifier for that pane,
- `workspace_id`, so `workctl` can focus or close the workspace.

This call costs milliseconds. Never cache it.

### Source 4: the filesystem

Take the newest modification time across the unit directory and its checkouts.
This gives the age of the unit, which drives the cold bucket.

### The join

Two join keys. Map a checkout to its git facts by the real path. Map a checkout
to its pull request by the pair of repository name and branch name. Map an
agent to a unit by the longest path prefix of the pane `cwd`.

Never key a checkout by its repository name alone. Nothing stops a unit from
holding two worktrees of one repository, and the path is the only field
guaranteed to be unique.

A whole pass costs about 9 seconds. Cache the worktrunk and `gh` results for 5
minutes. Never cache the herdr snapshot.

## Deriving a unit from the folder structure

You chose to derive units from the folder structure instead of writing a
manifest file. The workspace holds four shapes. Apply these rules in order to
each directory `work/<name>`:

A unit holds zero, one, or many checkouts. Collect them, do not stop at the
first one.

1. If `work/<name>` holds a `.git` file, add the root itself as a checkout.
   Example: `work/cnpg-clusters`.
2. Add every child that holds a `.git` file. Example:
   `work/model-packaging/platform` and `work/model-packaging/provisioning`.
3. For every child that holds no `.git` file, look one level deeper. If a
   grandchild holds a `.git` file, then `<name>/<child>` is a separate
   sub-unit with its own checkouts. Example:
   `work/INC-355/prod-eks-tf/provisioning`.
4. If no `.git` file appears at any depth, the unit holds only notes. Example:
   `work/prod-outage`.

Rules 1, 2, and 3 all apply to the same directory. A unit can be a checkout at
its root, hold sibling checkouts, and hold sub-units, all at once. No unit does
all three today, but the rule must allow it.

Key each checkout by its path, never by its repository name. Two checkouts in
one unit may come from the same repository, and a directory name is not the
repository name: `work/ti-agent-developer/ti-provisioning-vectara-dev` is a
worktree of `ti-provisioning`, not of a repository called
`ti-provisioning-vectara-dev`.

Every other file in the unit directory is the unit's unversioned payload.
Treat Markdown files, scripts, screenshots, and logs as part of the unit.
Never delete them without asking.

I ran these rules against the real workspace. They produce 77 units with no
ambiguity. Eight units hold more than one checkout: seven hold two and
`ti-agent-developer` holds three. Sixty-four hold one. Five hold none.

## The board

Rank each unit into exactly one bucket. The order is the priority order. Read
the board from the top and stop when you run out of time.

| Bucket | Rule | Count today |
|---|---|---|
| `BLOCKED` | A herdr agent reports `blocked`. It waits on your approval or answer. | live only |
| `READY` | A herdr agent reports `done` and you have not seen its tab. | live only |
| `MERGEABLE` | A pull request is approved, no real check fails, and nothing merged it. | 4 |
| `BROKEN` | A pull request is open and a check fails that is not on the ignore list. | 2 |
| `WAITING` | A pull request is open and review is pending. No action from you. | 6 |
| `ACTIVE` | Has checkouts, no pull request, not yet integrated, touched inside 30 days. | 6 |
| `SETTLE` | Every checkout is integrated and no pull request is open. The work landed. | 18 |
| `COLD` | The same, but nothing touched for over 30 days. | 36 |
| `NOTES` | The unit holds no checkout. | 5 |

`BLOCKED` and `READY` come from herdr alone. They are the two states that lose
you the most time today, because a finished or stuck agent is invisible until
you walk the tabs by hand.

`ACTIVE` deliberately turns on recency alone, not on evidence of work. A unit
created today has no commits and no changes yet, and calling that cold would be
wrong. Two units move under this rule: a newly created one, and
`packaged-agentic-setup`, which was set up 13 days ago and never started.

## The commands

Keep the surface small. Nine commands cover the day.

### Reading

- `workctl` prints the board, grouped by bucket, newest first inside each group.
- `workctl agent-sessions [<name>]` lists the agent sessions recorded inside
  your units. See "The agent history".
- `workctl agent <name>` resumes the most recent session in a unit, or starts a
  new one.
- `workctl show <name>` prints one unit in full: every checkout, its branch, its
  pull request, its CI, its live agents, its note files, and its age.
- `workctl board --watch` prints the same board and refreshes it. This is the view
  you bind to a herdr popup.

### Acting

- `workctl new <name> --repo platform --repo provisioning` creates the branch
  `misakwa/<name>` in each repository, creates the checkouts under
  `work/<name>/`, creates a herdr workspace at the unit root, and focuses it.
  It drives worktrunk to do the work. See "How workctl new creates a unit".
  When the unit has exactly one checkout, it also binds that checkout to the
  workspace with `herdr worktree open`, which fills the built-in sidebar rows.
- `workctl go <name>` focuses the herdr workspace for the unit. If none exists, it
  creates one at the unit root.
- `workctl review <name>` opens the whole unit as one diff in Hunk, across every
  repository it touches. With no name it opens a picker over the board. See
  "Reviewing changes: two scopes, two tools".
- `workctl pr <name>` prints the pull requests and their review threads. It drafts
  replies. It never posts them.
- `workctl done <name>` settles the unit. See the next section.
- `workctl sweep --bucket settle` settles every unit in a bucket, asking before each
  one.

### Syncing

- `workctl sync` pushes the pull request state and the CI state into the herdr
  sidebar as workspace tokens. Run it on a timer.

## How workctl is put together

`workctl` is a dispatcher plus one script per command, in the shape `git` uses.
`workctl <name> [args...]` runs `workctl_<name>` with the remaining arguments.
With no arguments it runs `workctl_board`.

The dispatcher looks for a subcommand beside itself first, then on PATH, so a
stowed symlink in `~/bin` still finds its siblings in the dotfiles tree. It
replaces its own process with `os.execv`, so the subcommand owns the terminal
and the exit status, and only one extra interpreter starts.

It builds its own help by reading the first docstring line out of each
`workctl_*` file it can find:

```
$ workctl --help
usage: workctl [<command>] [args...]

With no command, workctl runs board.

commands:
  board   Rank every unit of work by how much it needs you.
  review  Review one unit as a single diff, across every repository it touches.
```

Adding a command means adding one executable file named `workctl_<name>`. The
dispatcher needs no edit, and neither does this plan.

### The scripts

Every script is a single-file Python program with a PEP 723 header, run by uv,
with no dependency beyond the standard library:

```python
#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
```

Standard library only is a real constraint, not a preference. These scripts run
from herdr keybindings and worktrunk hooks, where a broken virtual environment
would be invisible until the moment you needed the tool. Everything they need
is already there: `subprocess` to call `wt`, `gh`, `git`, `herdr`, and `hunk`,
`json` to read their output, and `concurrent.futures` to run them in parallel.

### Where they live

They are a stow package, `workctl/bin/`, which lands in `~/bin`:

```
~/.dotfiles/workctl/bin/workctl          -> ~/bin/workctl
~/.dotfiles/workctl/bin/workctl_board    -> ~/bin/workctl_board
~/.dotfiles/workctl/bin/workctl_review   -> ~/bin/workctl_review
```

`workctl` is in the Makefile's `PACKAGES` list, so `make stow` picks it up.

This needed a second PATH change. Neither `~/bin` nor `~/.local/bin` was on the
non-interactive PATH, and `uv` lives in `~/.local/bin`, so the shebang itself
would have failed inside a herdr popup. Both are now in `bash/.path`, beside
the fix described under "The PATH fix". Verified:

```
$ env -i HOME=$HOME zsh -c 'workctl board --bucket MERGEABLE'
77 units in /home/michael/Projects/vectara-bare

== MERGEABLE (4)
...
```

## Creating a unit

```bash
workctl new <name> --repo platform --repo provisioning
workctl new <name> --repo platform --base release-2026-09
workctl new <name>                       # a unit that holds only notes
workctl new <name> --repo platform --dry-run
```

It creates `work/<name>/`, creates the branch `misakwa/<name>` in each named
repository, puts each checkout at `work/<name>/<repo>`, and creates a herdr
workspace at the unit root. Override the prefix with `WORKCTL_BRANCH_PREFIX`
and the branch itself with `--branch`.

Passing no `--repo` creates a notes-only unit. Five of yours already look like
that, so it is a real case rather than a special one.

### How it creates the checkouts

`workctl` does not create worktrees itself. It calls worktrunk once per
repository, overriding the path template for that one call:

```bash
wt --config-set 'worktree-path="{{ repo_path }}/../../work/<name>/{{ remote_repo }}"' \
   switch --create misakwa/<name> --no-cd -y
```

Worktrunk answers:

```
✓ Created branch misakwa/probe-layout from main and worktree
  @ ~/Projects/vectara-bare/work/probe-layout/sandisk-prod-setup
```

That is your layout exactly, with no `misakwa-` prefix on the directory.

I tested the whole command against `sandisk-prod-setup` and `provisioning`
together. Both checkouts landed under `work/probe-unit/`, both on
`misakwa/probe-unit`, and the board picked the unit up on the next run. I
removed the probe unit, its branches, and its directory afterwards.

This matters more than the saved keystrokes. Because the creation goes through
`wt`, every worktrunk feature applies without `workctl` reimplementing any of
it: the `post-switch` and `post-start` hooks fire, the branch is created from
the right base, and `wt list` sees the result immediately. `workctl` supplies
only the two things worktrunk cannot express, the unit name as a directory and
the loop over several repositories.

Use `--no-cd` because `workctl` moves you with `herdr`, not with the shell, and
`-y` because `workctl` has already asked you whatever it needed to ask.

For a unit spanning several repositories, the loop runs once per repository
with the same `<name>` and the same branch. The herdr workspace is created at
`work/<name>/`, so one session sees every repository as a subdirectory, which
is what your `bare-repo-worktrees` skill already prescribes.

`workctl new` does not call `herdr worktree open`. Herdr refuses it for a unit
root and refuses it for a linked worktree, so there is no case where it
succeeds. `workctl sync` carries the branch state as tokens instead. See "Why
workctl exists".

When herdr is not running, `workctl new` still creates everything on disk and
says so. Nothing is lost; attach the workspace later.

### What it refuses to do

It stops rather than guessing. An unknown repository name prints the available
ones. An existing branch is reported instead of reused, with the `wt switch`
command that would attach it. An existing checkout is left alone.

## Reviewing changes: two scopes, two tools

Review happens at two different scopes, and they need different tools. Do not
try to make one tool serve both.

### Scope A: one repository, from the focused pane

This is the common case. An agent finished in `work/model-packaging/platform`
and you want to see what it did and answer it.

Herdr has community plugins for exactly this. `herdr plugin` is a real command
in your build, even though `herdr --help` does not list it:

```
herdr plugin install <owner>/<repo>[/subdir...] [--ref REF] [--yes]
herdr plugin list [--plugin ID] [--json]
herdr plugin action invoke <action_id> [--plugin ID]
herdr plugin config-dir <plugin_id>
```

Four hunk plugins exist. Two are worth considering:

| Plugin | What it adds | Comment round-trip |
|---|---|---|
| [jhochenbaum/herdr-hunk-diff](https://github.com/jhochenbaum/herdr-hunk-diff) | Five review targets: working, staged, branch, commit, stash. Auto-open on agent state change. | Yes |
| [yuucu/herdr-hunk](https://github.com/yuucu/herdr-hunk) | One toggle action. Reloads a live session when an agent finishes. | No |

Install [jhochenbaum/herdr-hunk-diff](https://github.com/jhochenbaum/herdr-hunk-diff).
It carries the one thing this plan was missing: a way to send a review back to
the agent that wrote the code.

```bash
herdr plugin install jhochenbaum/herdr-hunk-diff
herdr plugin action invoke setup-keys --plugin jhochenbaum.hunkdiff
```

Installed and verified: `jhochenbaum.hunkdiff` v0.3.0, enabled, no manifest
warnings. Note that the plugin identifier is `jhochenbaum.hunkdiff`, not the
repository name. Every later command takes the identifier.

Its manifest declares 14 actions, 10 review panes that all open with placement
`split`, one link handler that catches a clicked GitHub commit URL, and four
event hooks:

| Event | Why it matters here |
|---|---|
| `pane.agent_status_changed` | Opens or reloads a review when an agent finishes. |
| `pane.closed`, `pane.exited` | Drops the association when the agent goes away. |
| `worktree.removed` | Cleans up when a worktree disappears. `workctl done` removes worktrees, so the plugin follows along on its own. |

Its actions bind to these keys:

| Key | Action |
|---|---|
| `prefix+shift+h` | Review the changes in the focused pane's repository |
| `prefix+shift+a` | Review staged changes |
| `prefix+shift+c` | Review the last commit |
| `prefix+shift+s` | Send the inline comments to the agent that wrote the code |

The `send-review` action collects the inline comments you left in Hunk, formats
them with a template, and prompts the agent that owns the pane. It records the
comment identifiers so a second press does not send the same note twice.

Configure it at
`~/.config/herdr/plugins/config/jhochenbaum.hunkdiff/config.toml`, which
`herdr plugin config-dir jhochenbaum.hunkdiff` prints:

```toml
[review]
auto_open = false      # start here; see the note below
reuse_pane = true
placement = "split"
default_target = "auto"
watch = true

[roundtrip]
clear_after_send = true

[hunk]
bin = "/home/linuxbrew/.linuxbrew/bin/hunk"
```

Two settings need thought.

Set `auto_open = false` at first. The plugin can open a review whenever an
agent changes state. With one agent that is helpful. With eight units running
it turns into a stream of panes opening behind your back, which is the problem
this plan exists to solve. Let the board tell you which units are `READY`, then
open the review deliberately. Turn `auto_open` on later if the board proves too
slow, and pair it with `reuse_pane = true` and `on_states = ["idle"]`.

Set `[hunk] bin` to your Homebrew binary. The plugin bundles its own pinned
`hunkdiff`, so without this line you run two different versions of Hunk
depending on how the review opened.

The plugin picks the repository from the focused pane. It cannot take a path, a
patch, or a revision, and it cannot span repositories. That is the gap scope B
fills.

### Scope B: the whole unit, across repositories

A unit spans several repositories. Eight of yours do. Hunk reviews one
repository at a time, but `hunk patch` reads a patch from a file or from
standard input, so build one patch from every checkout in the unit.

Prefix each path with the checkout that produced it, so files from different
repositories never collide and the sidebar tells you which one you are reading:

```bash
git -C <checkout> diff <merge-base> \
    --src-prefix="a/<label>/" --dst-prefix="b/<label>/"
```

Concatenate one such diff per checkout, then run `hunk patch <file>`.

I tested this against `work/INC-355`, which holds two sub-units. Hunk opened
one review session titled "Patch review", showing 8 files, with the sidebar
listing `karpenter-termination-grace/provisioning/...` and
`prod-eks-tf/provisioning/...` side by side.

Give `workctl review` three modes:

- `--branch`, the default: everything since the merge base, committed and
  uncommitted. This is the whole unit of work.
- `--staged`: staged changes only.
- `--working`: uncommitted changes only.

`workctl_review` already implements all three.

Bind it beside the plugin, so the two scopes sit next to each other:

```toml
[[keys.command]]
key = "prefix+shift+u"
type = "popup"
command = "workctl review"
width = "90%"
height = "90%"
```

### How the two fit together

Read the board. Press `prefix+shift+u` to see a whole unit at once and decide
whether the work is right. Focus the pane of the repository you want to argue
with, press `prefix+shift+h` to review it alone, leave inline comments, and
press `prefix+shift+s` to send them to the agent that wrote the code.

`workctl` reaches the plugin through `herdr plugin action invoke`, so `workctl review
<name> --repo platform` can hand a single-repository review to the plugin
rather than duplicating it.

### The hunk session API

Hunk exposes a daemon API that both scopes can use later:

- `hunk session list --json` shows every live review.
- `hunk session review --include-patch --include-notes --json` returns a
  finished review as structured data. `workctl done` can record this in the
  archive, so the review survives the worktree.
- `hunk session comment add` writes a comment into a live session, which lets
  an agent answer a review inside Hunk instead of in chat.

## The worktrunk plugin: do not install it

You asked whether to use [devashish2203/herdr-worktrunk](https://github.com/devashish2203/herdr-worktrunk)
or to drive worktrunk directly. Drive worktrunk directly, through `workctl new`.

The plugin is well built. It is not wrong. It targets a model your work does
not use.

### What it does

Six workspace actions, bound with `type = "plugin_action"`:

| Action | What it runs |
|---|---|
| `worktrunk.open` | Picker over worktrees and branches; creates from the default branch |
| `worktrunk.open-current` | Same picker, but `wt switch --create --base @` |
| `worktrunk.open-with-remotes` | Same picker, including remote-tracking branches |
| `worktrunk.remove` | Picker, then removal. Worktrunk gates unmerged branches and untracked files |
| `worktrunk.merge` | Picker, then `wt merge`, then removal |
| `worktrunk.merge-no-squash` | The same with `--no-squash` |

It offers two modes. In `open_mode = "workspace"`, the default, each worktree
becomes its own nested workspace. In `open_mode = "tab"`, each worktree becomes
a tab in the current workspace.

### Why it does not fit

Three reasons, in order of weight.

**1. A herdr workspace binds to at most one worktree.** This is not a plugin
limit, it is herdr's own data model. In the socket API schema,
`WorkspaceInfo.worktree` is a single `WorkspaceWorktreeInfo` or null, never a
list, and that record names exactly one `repo_key`, one `repo_root`, and one
`checkout_path`. The plugin's own documentation states the consequence
plainly: it does not support multi-repository workspaces, and each worktree is
a single repository checkout.

Your unit is the opposite shape. `work/<name>/` is one workspace holding
several checkouts plus unversioned notes. Eight of your units span more than
one repository, and `ti-agent-developer` holds three checkouts across two of
them. Your own `bare-repo-worktrees` skill says to `cd
work/<name>` and start one session that sees each repository as a subdirectory.
The plugin would give you one workspace per repository instead of one per unit.

**2. Five of your units hold no checkout at all.** `prod-outage`,
`storage-sizing-heuristics`, and three others are real work with no git behind
them. A worktree plugin cannot represent them. `workctl` can, because it derives
units from directories rather than from worktrees.

**3. Its merge actions are dangerous in a reviewed workflow.** `wt merge`
squashes, rebases, fast-forwards the target branch, and removes the worktree,
all locally. Your work goes through GitHub pull requests that other people
review. Pressing the merge key on a branch with an open pull request would land
that branch on `master` locally and delete the worktree, going around the
review. Do not put that on a keybinding.

### What to take from it instead

Two ideas are worth copying into `workctl`.

**Let worktrunk gate removal.** `wt remove` is stricter and more useful than
`git worktree remove`. Without `--force` it fails if the checkout holds any
uncommitted change, staged, modified, or untracked. It deletes the branch only
when the branch merged, and needs `--force-delete` otherwise. It takes
`--format json`, so `workctl done` can read the result rather than parse text.

It also takes `--reap`, which terminates the processes whose working directory
sits under the checkout, such as development servers, file watchers, and
language servers, while leaving interactive shells and terminal editors alone.
Across 77 units that is worth having. Call `wt remove --reap --format json` in
step 6 and let its gates stand.

Note one gap the gate does not cover. Your notes live at `work/<name>/`, beside
the checkouts rather than inside them, so worktrunk never sees them. That is
why step 5 of the settle sequence archives them by hand before step 6 removes
anything.

### If you want a picker anyway

`wt switch` with no argument already opens worktrunk's own interactive picker,
and `wt switch -x <program>` runs a program in the worktree it selects. You can
have the picker without the plugin:

```toml
[[keys.command]]
key = "prefix+shift+g"
type = "popup"
command = "wt switch"
width = "80%"
height = "60%"
```

Check native first. This is worktrunk's own feature, and it does not add a
second way to create a worktree.

## The agent history

Each agent files its history under the directory it ran in, and each does it
differently:

| Agent | Where | Keyed by |
|---|---|---|
| Claude | `~/.claude/projects/<slug>/*.jsonl` | the directory path, with separators flattened to hyphens |
| Codex | `~/.codex/sessions/<YYYY>/<MM>/<DD>/rollout-*.jsonl` | the date. The path is inside the file, as `session_meta.payload.cwd` |
| Pi | `~/.pi/agent/sessions/-<slug>-/*.jsonl` | the same flattened path, wrapped in hyphens |

This matters because Claude started at a unit root shows only the sessions
recorded for that exact path. Work done one level down, inside a checkout, is
invisible. `workctl sessions` finds those and can move them up:

Two commands cover it. One lists, one runs.

```bash
workctl agent-sessions                          # every unit
workctl agent-sessions INC-355
workctl agent-sessions --below-root             # what a run at the root would miss
workctl agent-sessions INC-355 --move-to-root   # dry run
workctl agent-sessions INC-355 --move-to-root --apply
workctl agent-sessions --orphans

workctl agent INC-355                # resume the most recent session here
workctl agent INC-355 --new          # start a fresh one
workctl agent INC-355 --pick         # the agent's own session picker
workctl agent INC-355 --kind codex   # choose the agent
```

`workctl agent` sets the working directory to the unit root and then gets out
of the way. It does not parse session files or pass identifiers around; each
agent already knows its own history, so it delegates:

| Agent | resume | pick | new |
|---|---|---|---|
| Claude | `claude -c` | `claude -r` | `claude` |
| Codex | `codex resume --last` | `codex resume` | `codex` |
| Pi | `pi -c` | `pi -r` | `pi` |

With no `--kind` it picks the agent whose newest session in that unit is the
most recent, so `workctl agent sandisk-deploy-sept-1` opens Codex while
`workctl agent INC-355` opens Claude. With no history at all it says so and
starts a new session rather than failing.

When a session sits below the unit root it warns, because resuming at the root
cannot reach it, and names the command that would move it up.

It scans the unit root and two levels below it, which covers both
`work/<name>/<repo>` and `work/<name>/<sub>/<repo>`.

Three things learned building it.

**You already do the right thing.** Across 29 sessions in 12 units, none sits
below a unit root. You start Claude at `work/<name>/` every time. The command
is therefore a safety net rather than a daily tool.

**Moving a Claude session does not rewrite it.** About three quarters of the
records in a session carry the `cwd` they were written in. The move refiles the
file and leaves those alone. They are history, not a pointer, so the session
still resumes; it simply remembers where it ran.

**Codex cannot be moved.** It files by date, not by directory, so there is
nothing to refile. `--move-to-root` says so and skips it.

**Settling a unit strands its history.** Five units are already gone from disk
while their sessions remain: `data-rebuild-only-os`, `kafka-memory-retention`,
`milvus-querynode-strategy`, `oncaller-failures`, and `ti-INC-351`.
`--orphans` lists them. This is the gap step 5 of the settle sequence exists to
close, by recording the session identifiers in the archive before the directory
goes away.

## The settle sequence

This is the part you asked for by name. `workctl done <name>` runs these steps in
order and stops at the first step that needs a decision.

1. Check every checkout for uncommitted changes. If any exist, stop and open
   the whole unit with `workctl review <name> --working`.
2. Check every branch. Report whether it is pushed, whether a pull request is
   open, and whether it merged.
3. If a pull request merged, report the number and the date.
4. Settle the agent threads. For each herdr pane inside the unit whose agent is
   `idle` or `done`, read the session identifier from `agent_session`, record
   it, and close the pane. Claude sessions live under
   `~/.claude/projects/<slug>/`. Codex threads live under `~/.codex/sessions/`.
5. Archive the unversioned payload. Move the notes, scripts, and images to
   `<workspace>/.archive/<name>/`. Keep the notes and lose the checkouts.
   Write the recorded session identifiers into that archive directory as
   `SESSIONS.txt`, so the thread stays findable after the unit is gone. If a
   Hunk session is still live for the unit, capture it first with
   `hunk session review --include-patch --include-notes --json` and store it
   beside `SESSIONS.txt`.
6. Remove each checkout with `wt remove --reap --format json`, never with
   `git worktree remove`. Worktrunk refuses to drop a checkout holding any
   uncommitted change, kills the stray processes running inside it, and deletes
   the branch only when the branch merged. Let those gates stand. Never pass
   `--force` from `workctl done`.
7. Close the herdr workspace.

Your global rule says never to post as you. So step 4 settles only the local
Claude and Codex threads. It never resolves a GitHub review thread. `workctl pr`
drafts those replies and shows them to you.

## The PATH fix

This blocked the whole plan, so I fixed it before anything else.

`wt`, `hunk`, and `herdr` live in `/home/linuxbrew/.linuxbrew/bin`. That
directory reached the PATH only through `~/.zshrc`, which zsh reads for
interactive shells alone. Every other caller got the bare system PATH:

```
$ env -i HOME=$HOME zsh -c 'command -v wt'
(nothing)
```

That set of callers is exactly the set this plan depends on: herdr
`[[keys.command]]` popups, worktrunk hooks, herdr plugin commands, systemd user
units, and the supervised Emacs daemon.

The fix moves the PATH bootstrap to `~/.zshenv`, which zsh reads on every
invocation. The new `zsh/.zshenv` guards against sourcing twice, so the
existing `source ~/.path` line in `.zshrc` becomes a no-op:

```zsh
if [[ -z "$DOTFILES_PATH_SET" ]]; then
    export DOTFILES_PATH_SET=1
    [[ -r ~/.path ]] && source ~/.path
fi
```

I replaced the empty `~/.zshenv`, added `!.zshenv` to `zsh/.gitignore`, and
stowed the package. A clean-environment shell now finds all three binaries, and
the interactive PATH holds no duplicate entries.

A second change followed when `workctl` arrived. Neither `~/bin`, where stow
puts wrappers, nor `~/.local/bin`, where `uv` lives, was on that PATH. Both are
now in `bash/.path` for the same reason:

```zsh
export PATH="$HOME/bin:$HOME/.local/bin:$PATH"
```

`~/.exports` still adds `~/.local/bin` a second time for interactive shells.
A duplicate PATH entry is harmless, so clean it up whenever you next touch that
file.

One separate problem remains, which I did not change. `bash/.exports` line 34
reads:

```sh
export PATH=bin:$HOME/.local/bin:$PATH
```

The first entry is a relative path. Every directory you enter that holds a
`bin/` subdirectory becomes a source of commands. Decide whether to drop it.

## The herdr configuration

You chose configuration over a plugin, so this is `~/.config/herdr/config.toml`
plus two integration installs.

1. Bind the board to a popup. This gives you the single-key overview.

   ```toml
   [[keys.command]]
   key = "prefix+alt+w"
   type = "popup"
   command = "workctl board --watch"
   width = "90%"
   height = "90%"
   ```

2. Put the pull request state in the sidebar. `workctl sync` fills the tokens.

   ```toml
   [ui.sidebar.spaces]
   rows = [["state_icon", "workspace"], ["$br", "$pr", "$ci"]]
   ```

   All three are custom tokens from `workctl sync`. The built-in `branch` and
   `git_status` rows cannot work here. See "Why workctl exists".

   `workctl sync` writes each token with
   `herdr workspace report-metadata <id> --source workctl --token pr=#3325 --token ci=failed`.

3. Sort the agent panel by attention, not by position.

   ```toml
   [ui]
   agent_panel_sort = "priority"
   status_indicators = "symbols"
   ```

4. Make a blocked agent reach you in a background workspace.

   ```toml
   [ui.toast]
   delivery = "system"
   ```

5. Install the agent integrations, so herdr reports the agent status and the
   session identifier that step 4 of the settle sequence needs.

   ```bash
   herdr integration install claude
   herdr integration install codex
   ```

   Both are already installed. Verified: the herdr session hook is wired
   into `~/.claude/settings.json` and `~/.codex/`.

6. Install the Hunk review plugin and let it write its own keybindings. Done.
   See "Reviewing changes: two scopes, two tools".

   ```bash
   herdr plugin install jhochenbaum/herdr-hunk-diff
   herdr plugin action invoke setup-keys --plugin herdr-hunk-diff
   ```

   A herdr plugin runs with your full user permissions. Read the manifest with
   `herdr plugin list --json` after installing, and pin a commit with `--ref`
   if you want the version to stop moving.

7. Do not install a worktree plugin. See "The worktrunk plugin: do not install
   it". If you want worktrunk's picker on a key, bind `wt switch` as a popup;
   the picker is worktrunk's own feature.

## The worktrunk configuration

Create `~/.config/worktrunk/config.toml` and install the shell integration.

1. Install the shell hook. Without it `wt switch` cannot change your directory.

   ```bash
   wt config shell install
   ```

2. Keep `full` off. `workctl` takes the pull request and CI facts from `gh`, and
   `--full` makes `wt list` slower without making it more correct. Set only the
   columns you want when you run `wt list` by hand.

   ```toml
   [list]
   columns = ["branch", "status", "path"]
   ```

3. Set the worktree path for this workspace, so a direct `wt switch --create`
   lands in the right place. I verified the template variables against your
   repositories. For a bare repository, `{{ repo_path }}` resolves to the
   `.bare` directory and `{{ remote_repo }}` resolves to the repository name.

   ```toml
   [projects."github.com/vectara/*"]
   worktree-path = "{{ repo_path }}/../../work/{{ branch | sanitize }}/{{ remote_repo }}"
   ```

   Worktrunk has no filter that strips a prefix from a branch name, so this
   template writes `work/misakwa-fix-auth/platform`. That is the right fallback
   for the times you reach for `wt` by hand. `workctl new` overrides it per
   call, as the next section describes, and keeps your existing shape.

4. Add a post-switch hook that refreshes the sidebar.

   ```toml
   [projects."github.com/vectara/*".post-switch]
   sync = "workctl sync"
   ```

5. Install the Claude Code plugin and statusline, so the branch and its state
   show inside every agent session.

   ```bash
   wt config plugins claude install
   wt config plugins claude install-statusline
   ```

## The day

This is the loop the tools support.

1. Open herdr. Press `prefix+alt+w`. Read the board.
2. Clear `BLOCKED` first. Each one is an agent waiting on you right now.
3. Clear `READY` next. Each one is finished work you have not seen. For each:
   press `prefix+shift+u` to read the whole unit, then focus the pane you
   disagree with, press `prefix+shift+h` to review that repository alone, leave
   inline comments, and press `prefix+shift+s` to send them back to the agent.
4. Clear `MERGEABLE`. Merge the approved pull requests.
5. Look at `BROKEN`. Send each failure back to an agent, or fix it.
6. Start new work with `workctl new <name> --repo <repo>`.
7. At the end of the day, run `workctl sweep --bucket settle`.

`WAITING` and `COLD` need no daily attention. Read `WAITING` when you want to
chase a reviewer. Read `COLD` once a week.

Step 3 is the loop that was missing. Before, a finished agent was invisible
until you walked the tabs, and answering it meant retyping what you saw. Now
the board finds it and the review goes back to the agent as a prompt.

## Build order

Each command is one `workctl_<name>` script, added on its own. The dispatcher
never changes. Nothing forces a rewrite, and no step blocks the next.

Write them in Python, run by uv, standard library only, as described under "How
workctl is put together". Reach for Go only if one command proves too slow to
live with, and then rewrite that one command rather than the tool. The likely
candidate is `workctl_board --watch`, which redraws on a timer. Go is installed
at 1.25.5 if it comes to that.

Three commands exist. `workctl_board` derives the units, joins them against
worktrunk and GitHub, and prints the board. `workctl_review` opens a whole unit
in Hunk. `workctl_new` creates one. A full board takes about 9 seconds, most of
it waiting on GitHub.

```
$ workctl                                      # the board
$ workctl board --bucket MERGEABLE --bucket BROKEN
$ workctl new fix-auth --repo platform --repo provisioning
$ workctl review INC-355
$ workctl --help                               # lists what exists
```

Still missing: `go`, `show`, `sync`, `pr`, `done`, and `sweep`.

**Step 1. The scanner.** Implement the four derivation rules and print the unit
list. No network, no herdr. This step is already proven: the prototype produced
77 clean units.

**Step 2. The git and forge join.** Shell out to `wt list --format json` per
repository and to `gh pr list` per repository, in parallel. Then fetch
`gh pr checks` for the matched pull requests, also in parallel, and drop the
ignored check names. Cache to `$XDG_CACHE_HOME/workctl/` for 5 minutes. Add the
buckets that need only git and the forge: `MERGEABLE`, `BROKEN`, `WAITING`,
`SETTLE`, `COLD`, `NOTES`.

**Step 3. The herdr join.** Shell out to `herdr api snapshot`. Map each pane to
a unit by the longest path prefix. Add `BLOCKED`, `READY`, and `ACTIVE` to
`workctl_board`. Add `workctl_go`. At the end of this step the board is
complete.

**Step 4. The watch view and the herdr bindings.** Add `--watch` to
`workctl_board` and bind it to a popup. Add `workctl_sync` and the sidebar
tokens. Give `workctl_review` a picker for the no-argument case. Install the
Hunk review plugin and bind its keys beside yours. At the end of this step the
review loop closes: the board finds the finished work, `workctl review` shows
the whole unit, and the plugin sends your comments back to the agent.

**Step 5. The write commands.** `workctl_new` is done, ahead of its place in
this order, because new work should start in the new shape from the first day.
Add `workctl_done` and `workctl_sweep`. Build `workctl_done` last, because it
deletes things. Give it a `--dry-run` flag and make that the default until you
trust it.

Do not merge or close any pull request while building. The backlog is the test
data for `workctl`, and it is more useful whole. See "The triage, after the
workflow works".

## The triage, after the workflow works

Do not merge or close a single pull request yet. Build the workflow first, then
run the backlog through it. The backlog is the first real test of the tool: if
`workctl` cannot settle 77 units that grew without a system, it will not hold the
next 77.

Order the phases this way.

**Phase A. Configure. Nothing is destroyed.**

1. The PATH fix. Done.
2. Write `~/.config/worktrunk/config.toml` and run `wt config shell install`.
3. Write `~/.config/herdr/config.toml`.
4. The agent integrations for Claude and Codex are already installed.
5. Run `herdr plugin install jhochenbaum/herdr-hunk-diff` and configure it.

**Phase B. Build `workctl` through step 3 of the build order.** Stop when the board
is complete and correct. Read it for a few days without acting on it. Its job
in this phase is to prove that its buckets match reality.

**Phase C. Build the remaining write commands.** `workctl new` is already done,
so new work can start in the new shape now. Add `workctl done` with `--dry-run`
as the default.

**Phase D. Run the backlog through the tool.** Now touch the pull requests.
Work the board from the top:

1. **The four approved pull requests.** They have waited between 28 and 71 days.
   None has a real check failure.
   - `platform#7162` on `api-test-suite-failures/artifact-error-attribution`
   - `platform#7163` on `api-test-suite-failures/write-without-live-llm`
   - `provisioning#395` on `artifactory-jcr-setup`
   - `provisioning#2528` on `milvus-querynode-ephemeral`

   Review each one with `workctl review <name>` before you merge it. A pull
   request approved 71 days ago was approved against a different `master`.

2. **The two pull requests that genuinely fail.**
   - `provisioning#2607` on `cluster-capacity-validation`, failing `yaml-lint`
   - `platform#5911` on `slack-render-actions-blocks`, failing `test`

   Six others look red and are not. Repair or remove `transcript-check` on
   `provisioning` to clear that noise at its source. That single fix is worth
   more than any dashboard, because it restores the CI signal for the whole
   team, not only for you.

3. **The 18 units that already merged.** Run `workctl sweep --bucket settle`.
   Worktrunk proves each one with `integration.reason`. Seven are the
   `prod-platform-migration` sub-units, all sitting on the same commit. This is
   the safest bucket, so settle it first and let it build your trust in
   `workctl done`.

4. **The 37 cold units.** Most were created in one batch on 2026-07-27 and never
   touched again. Nine sit on a detached HEAD and carry no branch, so only the
   commits survive a delete. Review the list once, then delete.

5. **The five note-only units.** `prod-outage`, `storage-sizing-heuristics`,
   `ti-dev-release-2026-07-21`, `sandisk-production-ready`, and
   `oncaller-agents-sa-role-drift-log-noise` hold real work with no git behind
   it. Move the finished ones to `.archive/`. Keep the live ones.

6. **The branch namespaces.** You have `misakwa/`, `oncaller/`, `fable/`, and
   bare branch names. Decide whether the agent-created prefixes stay as a
   deliberate second namespace, or whether everything moves under `misakwa/`.
   `workctl` reports a unit whose branch does not match the rule.

**Phase E. Decide what earns a plugin.** See the next section.

## A later upgrade: the herdr plugin

Herdr carries a full plugin system. The current release does not expose it as a
`herdr plugin` subcommand, but the socket API accepts `plugin.link`,
`plugin.list`, `plugin.action.invoke`, and `plugin.pane.open`. A plugin
manifest declares:

- `startup`: a long-lived process. `workctl sync` could run here instead of a timer.
- `events`: hooks on 26 event names, including `pane_agent_status_changed`,
  `worktree_created`, and `workspace_focused`. A hook on the first would push a
  fresh board the moment an agent blocks, with no polling.
- `panes`: a named pane with placement `overlay`, `popup`, `split`, `tab`, or
  `zoomed`. The board becomes a first-class herdr surface.
- `actions`: commands scoped to `global`, `workspace`, `tab`, `pane`, or
  `selection`. "Settle this unit" becomes a menu entry.
- `link_handlers`: a pattern and an action. Clicking a pull request URL inside
  any pane could open `workctl show`.

Do not build this first. Build `workctl` as a plain command line tool, run it for
a week, and then decide which parts earn a plugin.

Read the Hunk plugin's manifest before writing your own. It is a working
example of every field this section describes, already installed on your
machine:

```bash
herdr plugin list --json
```

The strongest candidate for a first plugin is `workctl sync`. As a `startup`
process with an `events` hook on `pane_agent_status_changed`, it would push
fresh pull request and CI tokens into the sidebar the moment an agent changes
state, with no timer and no polling.
