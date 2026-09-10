"""Shared helpers for the workctl commands.

Each command is a standalone uv script. They import this module by putting
their own directory on sys.path first:

    import os, sys
    sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))
    from _workctl import Unit, derive_units, workspace_root

`realpath` matters: the commands are reached through symlinks in ~/bin, and the
module lives beside the real files.
"""
import concurrent.futures as futures
import hashlib
import json
import os
import subprocess
import time

WORKSPACE = os.environ.get("WORKCTL_WORKSPACE",
                           os.path.expanduser("~/Projects/vectara-bare"))
BRANCH_PREFIX = os.environ.get("WORKCTL_BRANCH_PREFIX", "misakwa/")
OWNER = os.environ.get("WORKCTL_OWNER", "vectara")
AUTHOR = os.environ.get("WORKCTL_AUTHOR", "misakwa")

# The unit model holds checkouts at depth 1 and 2. Scan deeper than that so a
# command can see the checkouts the model does not hold, rather than treating
# the directory that holds them as notes.
SCAN_DEPTH = int(os.environ.get("WORKCTL_SCAN_DEPTH", "5"))

# `gh pr list` truncates silently at --limit. platform sits near 295 open pull
# requests, so a limit of 300 drops the oldest without saying so.
PR_LIMIT = int(os.environ.get("WORKCTL_PR_LIMIT", "1000"))

# Checks that fail permanently and say nothing about the branch. One always-red
# check would otherwise turn every pull request in the repository red.
IGNORED_CHECKS = set(
    filter(None, os.environ.get("WORKCTL_IGNORED_CHECKS", "transcript-check").split(",")))

DIRTY_KEYS = ("staged", "modified", "untracked", "deleted", "conflicted")

# `wt list` and `gh pr list` cost about 10 seconds each on this workspace, so a
# cold board takes 20. That is a blank window on a keybinding, so cache both for
# long enough that a keypress rarely pays it. Pass --refresh when it matters.
GIT_TTL = int(os.environ.get("WORKCTL_GIT_TTL", "300"))
PR_TTL = int(os.environ.get("WORKCTL_PR_TTL", "300"))


def cache_dir():
    base = os.environ.get("XDG_CACHE_HOME") or os.path.expanduser("~/.cache")
    path = os.path.join(base, "workctl")
    os.makedirs(path, exist_ok=True)
    return path


def cached(name, key, ttl, build, encode, decode, refresh=False):
    """Read a cached answer, or build and store one.

    A stale or unreadable file is a miss, never an error: the cache exists to
    save time, so it must never be the reason a command fails.
    """
    digest = hashlib.sha1(repr(key).encode()).hexdigest()[:12]
    path = os.path.join(cache_dir(), f"{name}-{digest}.json")
    if not refresh and ttl > 0 and os.path.isfile(path):
        if time.time() - os.path.getmtime(path) < ttl:
            try:
                with open(path, encoding="utf-8") as handle:
                    return decode(json.load(handle))
            except (OSError, ValueError, KeyError, TypeError):
                pass
    value = build()
    try:
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(encode(value), handle)
    except (OSError, TypeError):
        pass
    return value


# --- process helpers -------------------------------------------------------

def run(cmd, cwd=None, allow_failure=False):
    """Standard output of a command, or "" when it failed.

    `gh pr checks` exits non-zero when a check failed, which is the case
    workctl cares about most, so pass allow_failure for it.
    """
    out = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    return out.stdout if allow_failure or out.returncode == 0 else ""


def parallel(func, items, limit=12):
    items = list(items)
    if not items:
        return []
    with futures.ThreadPoolExecutor(max_workers=min(len(items), limit)) as pool:
        return list(pool.map(func, items))


# --- the workspace and its units -------------------------------------------

def subdirs(path):
    try:
        return sorted(d for d in os.listdir(path) if os.path.isdir(os.path.join(path, d)))
    except OSError:
        return []


def is_checkout(path):
    return os.path.isfile(os.path.join(path, ".git"))


def work_dir(workspace=None):
    return os.path.join(workspace or WORKSPACE, "work")


def bare_repos(workspace=None):
    root = workspace or WORKSPACE
    return [d for d in subdirs(root) if os.path.isdir(os.path.join(root, d, ".bare"))]


def add_root_arg(ap):
    """Register the shared --root flag.

    Named root, not workspace: workctl also creates a herdr workspace per
    unit, and one flag called --workspace read as that one.
    """
    ap.add_argument("--root", dest="root", default=WORKSPACE, metavar="DIR",
                    help="directory holding the bare repositories "
                         "(default: %(default)s)")


def primary_worktree(repo, workspace=None):
    """The repository's own default-branch checkout, where `wt` commands run."""
    root = workspace or WORKSPACE
    for branch in ("main", "master"):
        path = os.path.join(root, repo, branch)
        if os.path.isdir(path):
            return path
    return None


class Unit:
    """One directory under work/, with every checkout inside it."""

    def __init__(self, name, root, checkouts):
        self.name = name
        self.root = root
        self.checkouts = checkouts

    def __repr__(self):
        return f"Unit({self.name!r}, {len(self.checkouts)} checkouts)"

    def hidden_checkouts(self):
        """Checkouts on disk that the unit model does not hold.

        A directory holding one of these is not notes. Moving it breaks the
        `.bare/worktrees/*` link of a live worktree.
        """
        known = {os.path.realpath(p) for p in self.checkouts}
        # `derive_units` models a sub-unit's checkouts one level deeper. Those
        # belong to that sub-unit, so they are not hidden from this one.
        for child in subdirs(self.root):
            child_path = os.path.join(self.root, child)
            if is_checkout(child_path):
                continue
            for grand in subdirs(child_path):
                deep = os.path.join(child_path, grand)
                if is_checkout(deep):
                    known.add(os.path.realpath(deep))
        return [p for p in all_checkouts(self.root)
                if os.path.realpath(p) not in known]

    @property
    def age_days(self):
        """Days since the unit was last worked on.

        Directory mtime alone dates a unit by its last `mv`: one mass move in
        July gave 36 units the same age. Commit dates and agent session files
        record when work happened, so they win when either exists.
        """
        newest = max(os.path.getmtime(p)
                     for p in [self.root] + list(self.checkouts))
        newest = max([newest] + self.commit_times() + self.session_times())
        return int((time.time() - newest) / 86400)

    def commit_times(self):
        found = []
        for checkout in self.checkouts:
            text = run(["git", "-C", checkout, "log", "-1", "--format=%ct"]).strip()
            if text.isdigit():
                found.append(int(text))
        return found

    def session_times(self):
        found = []
        for base in (CLAUDE_ROOT, PI_ROOT):
            directory = os.path.join(base, slug(self.root))
            for name in (os.listdir(directory) if os.path.isdir(directory) else []):
                if name.endswith(".jsonl"):
                    found.append(os.path.getmtime(os.path.join(directory, name)))
        return found

    def label_for(self, checkout):
        """A path prefix naming the checkout inside its unit, for combined diffs."""
        inside = os.path.relpath(checkout, self.root)
        return os.path.basename(self.root) if inside == "." else inside


def checkouts_of(root):
    """Every checkout in one unit directory.

    A unit may be a checkout at its own root, hold sibling checkouts, and hold
    sub-units one level deeper. All three can be true at once, so collect them
    all rather than stopping at the first.
    """
    found = [root] if is_checkout(root) else []
    for child_name in subdirs(root):
        child = os.path.join(root, child_name)
        if is_checkout(child):
            found.append(child)
    return found


def all_checkouts(root, max_depth=SCAN_DEPTH):
    """Every checkout under a directory, at any depth.

    `checkouts_of` answers what the unit model holds. This answers what is
    really on disk, so a caller can refuse to touch the difference.
    """
    found = []

    def walk(path, depth):
        here = is_checkout(path)
        if here:
            found.append(path)
        # A worktree never holds another, but a unit root may be a checkout
        # and still hold siblings, so only stop descending below the root.
        if depth >= max_depth or (here and depth > 0):
            return
        for name in subdirs(path):
            if not name.startswith("."):
                walk(os.path.join(path, name), depth + 1)

    walk(root, 0)
    return found


def derive_units(workspace=None):
    """Every unit in the workspace, derived from the folder structure alone."""
    base = work_dir(workspace)
    units = []
    for name in subdirs(base):
        root = os.path.join(base, name)
        checkouts = checkouts_of(root)
        nested = []
        for child_name in subdirs(root):
            child = os.path.join(root, child_name)
            if is_checkout(child):
                continue
            deep = [os.path.join(child, g) for g in subdirs(child)
                    if is_checkout(os.path.join(child, g))]
            if deep:
                nested.append(Unit(f"{name}/{child_name}", child, deep))
        if checkouts or not nested:
            units.append(Unit(name, root, checkouts))
        units += nested
    return units


def find_unit(name, workspace=None):
    """The unit with this name, or a parent standing for its sub-units.

    A directory holding only sub-units is not a unit itself, but it is still a
    natural thing to name. `INC-355` gathers the checkouts of
    `INC-355/prod-eks-tf` and `INC-355/karpenter-termination-grace`.
    """
    units = derive_units(workspace)
    for unit in units:
        if unit.name == name:
            return unit
    children = [u for u in units if u.name.startswith(name + "/")]
    if children:
        root = os.path.join(work_dir(workspace), name)
        return Unit(name, root, [c for u in children for c in u.checkouts])
    return None


# --- worktrunk: the git facts ----------------------------------------------

def git_facts(workspace=None, repos=None, refresh=False):
    """Map each checkout's real path to (repo, worktrunk record).

    Worktrunk owns the git side: the branch, the dirty state, ahead and behind,
    and whether the branch already landed. Its `pr` and `checks` fields arrive
    incomplete, so the forge facts come from gh instead.
    """
    root = workspace or WORKSPACE
    names = repos if repos is not None else bare_repos(root)

    def load(repo):
        cwd = primary_worktree(repo, root)
        text = run(["wt", "list", "--format", "json"], cwd=cwd) if cwd else ""
        return repo, (json.loads(text)["items"] if text else [])

    def build():
        index = {}
        for repo, items in parallel(load, names, limit=max(len(names), 1)):
            for item in items:
                path = (item.get("worktree") or {}).get("path")
                if path:
                    index[os.path.realpath(path)] = (repo, item)
        return index

    return cached("git", (root, tuple(names)), GIT_TTL, build,
                  encode=lambda idx: [[p, r, it] for p, (r, it) in idx.items()],
                  decode=lambda rows: {p: (r, it) for p, r, it in rows},
                  refresh=refresh)


def is_dirty(item):
    changes = (item.get("worktree") or {}).get("changes") or {}
    return any(changes.get(k) for k in DIRTY_KEYS)


# --- GitHub: the forge facts -----------------------------------------------

def pr_facts(repos=None, owner=None, workspace=None, refresh=False):
    """Map (repo, branch) to its open pull request.

    One list call per repository. Asking GitHub for statusCheckRollup in the
    same call answers HTTP 504 on repositories this size, so checks come later
    and only for the pull requests that matched a unit.
    """
    names = repos if repos is not None else bare_repos(workspace)
    who = owner or OWNER
    fields = "number,headRefName,reviewDecision,isDraft,url,author"

    def load(repo):
        text = run(["gh", "pr", "list", "--repo", f"{who}/{repo}", "--state", "open",
                    "--json", fields, "--limit", str(PR_LIMIT)])
        return repo, (json.loads(text) if text else [])

    def build():
        index = {}
        for repo, prs in parallel(load, names, limit=max(len(names), 1)):
            for pr in prs:
                index[(repo, pr["headRefName"])] = pr
        return index

    return cached("pr", (who, tuple(names), PR_LIMIT), PR_TTL, build,
                  encode=lambda idx: [[r, b, pr] for (r, b), pr in idx.items()],
                  decode=lambda rows: {(r, b): pr for r, b, pr in rows},
                  refresh=refresh)


def pr_author(pr):
    return ((pr or {}).get("author") or {}).get("login") or ""


def is_own_pr(pr, author=None):
    """Whether a pull request is his. An unknown author counts as his.

    `gh` omits the author on a pull request it cannot attribute, and calling
    that someone else's would hide real work.
    """
    login = pr_author(pr)
    return not login or login == (author or AUTHOR)


def failing_checks(pairs, owner=None, ignored=None):
    """Map (repo, number) to the names of its genuinely failing checks."""
    who = owner or OWNER
    skip = IGNORED_CHECKS if ignored is None else ignored

    def load(key):
        repo, number = key
        names = []
        for line in run(["gh", "pr", "checks", str(number), "--repo", f"{who}/{repo}"],
                        allow_failure=True).splitlines():
            parts = line.split("\t")
            if len(parts) > 1 and parts[1] == "fail":
                names.append(parts[0].strip())
        return key, sorted({n for n in names if n not in skip})

    return dict(parallel(load, pairs))


UNRESOLVED_QUERY = """
query($owner: String!, $repo: String!, $number: Int!) {
  repository(owner: $owner, name: $repo) {
    pullRequest(number: $number) {
      reviewThreads(first: 100) { nodes { isResolved comments(first: 1) { totalCount } } }
    }
  }
}
"""


def unresolved_threads(pairs, owner=None):
    """Map (repo, number) to its count of unresolved review threads.

    An approved pull request can still carry an unanswered question. Merging it
    then drops that feedback silently, so the board needs to see it.
    """
    who = owner or OWNER

    def load(key):
        repo, number = key
        text = run(["gh", "api", "graphql", "-f", f"query={UNRESOLVED_QUERY}",
                    "-F", f"owner={who}", "-F", f"repo={repo}", "-F", f"number={number}"])
        try:
            nodes = json.loads(text)["data"]["repository"]["pullRequest"]["reviewThreads"]["nodes"]
        except (KeyError, TypeError, ValueError):
            return key, 0
        return key, sum(1 for t in nodes
                        if not t["isResolved"] and t["comments"]["totalCount"])

    return dict(parallel(load, pairs))


def outside_units(git, workspace=None):
    """Worktrees worktrunk reports that no unit holds.

    Siblings in `<root>/<repo>/<slug>`, units at `<root>/<name>/<repo>`, and
    checkouts deeper than a sub-unit. The board never mentions these, so an
    open pull request can sit in one unseen.
    """
    root = os.path.realpath(workspace or WORKSPACE)
    held = {os.path.realpath(c) for u in derive_units(workspace) for c in u.checkouts}
    primaries = {os.path.realpath(p)
                 for p in (primary_worktree(r, workspace) for r in bare_repos(workspace))
                 if p}
    found = []
    for path, (repo, item) in git.items():
        if path in held or path in primaries:
            continue
        rest = path[len(root) + 1:] if path.startswith(root + os.sep) else ""
        if not rest:
            continue
        # Agents and tools keep their own worktrees under dot-directories such
        # as `<repo>/.bare/.claude/worktrees/`. Those are not his work.
        if any(part.startswith(".") for part in rest.split(os.sep)):
            continue
        found.append((repo, path, item))
    return sorted(found, key=lambda row: row[1])


# --- agent session history -------------------------------------------------

CLAUDE_ROOT = os.path.expanduser("~/.claude/projects")
CODEX_ROOT = os.path.expanduser("~/.codex/sessions")
PI_ROOT = os.path.expanduser("~/.pi/agent/sessions")

DEPTH = 2


def slug(path):
    """Claude and Pi name a directory by its path with the separators flattened."""
    return path.replace(os.sep, "-")


def candidates(unit, depth=DEPTH):
    """The unit root and every directory under it, to the given depth."""
    found = [unit.root]
    frontier = [unit.root]
    for _ in range(depth):
        nxt = []
        for parent in frontier:
            for name in subdirs(parent):
                if name.startswith("."):
                    continue
                child = os.path.join(parent, name)
                found.append(child)
                nxt.append(child)
        frontier = nxt
    return found


def claude_sessions(paths):
    by_slug = {slug(p): p for p in paths}
    found = []
    for entry in os.listdir(CLAUDE_ROOT) if os.path.isdir(CLAUDE_ROOT) else []:
        path = by_slug.get(entry)
        if not path:
            continue
        directory = os.path.join(CLAUDE_ROOT, entry)
        for name in sorted(os.listdir(directory)):
            if name.endswith(".jsonl"):
                found.append(("claude", path, os.path.join(directory, name)))
    return found


def first_record(path):
    try:
        with open(path, encoding="utf-8", errors="replace") as handle:
            return json.loads(handle.readline())
    except (OSError, ValueError):
        return {}


def codex_sessions(paths):
    """Codex files by date, not by directory, so read the cwd out of each one."""
    wanted = set(paths)
    found = []
    for base, _, names in os.walk(CODEX_ROOT):
        for name in sorted(names):
            if not name.endswith(".jsonl"):
                continue
            path = os.path.join(base, name)
            cwd = (first_record(path).get("payload") or {}).get("cwd")
            if cwd in wanted:
                found.append(("codex", cwd, path))
    return found


def pi_sessions(paths):
    by_slug = {f"-{slug(p)}-": p for p in paths}
    found = []
    for entry in os.listdir(PI_ROOT) if os.path.isdir(PI_ROOT) else []:
        path = by_slug.get(entry)
        if not path:
            continue
        directory = os.path.join(PI_ROOT, entry)
        for name in sorted(os.listdir(directory)):
            if name.endswith(".jsonl"):
                found.append(("pi", path, os.path.join(directory, name)))
    return found


def sessions_for(unit, kinds, depth=DEPTH):
    paths = candidates(unit, depth)
    found = []
    if "claude" in kinds:
        found += claude_sessions(paths)
    if "codex" in kinds:
        found += codex_sessions(paths)
    if "pi" in kinds:
        found += pi_sessions(paths)

    rows = []
    for kind, path, file in found:
        rows.append(dict(unit=unit.name, kind=kind, cwd=path, file=file,
                         at_root=os.path.realpath(path) == os.path.realpath(unit.root),
                         age=int((time.time() - os.path.getmtime(file)) / 86400),
                         size=os.path.getsize(file)))
    return sorted(rows, key=lambda r: (r["cwd"], r["file"]))


# --- herdr -----------------------------------------------------------------

_SESSION = None


def herdr_session():
    """The name of the herdr session to talk to, or None when none runs.

    Herdr supports named sessions, and the default one is often not the live
    one: `herdr status server` reports "not running" while a named session is
    serving every real pane. Resolve the session once, then pass it explicitly.
    """
    global _SESSION
    if _SESSION is not None:
        return _SESSION or None

    if os.environ.get("WORKCTL_HERDR_SESSION"):
        _SESSION = os.environ["WORKCTL_HERDR_SESSION"]
        return _SESSION

    text = run(["herdr", "session", "list", "--json"], allow_failure=True)
    try:
        sessions = json.loads(text)["sessions"] if text else []
    except (json.JSONDecodeError, KeyError):
        sessions = []
    running = [s for s in sessions if s.get("running")]

    # Inside a herdr pane, follow the session that owns this pane.
    socket = os.environ.get("HERDR_SOCKET_PATH")
    chosen = next((s for s in running if s.get("socket_path") == socket), None) if socket else None

    # Otherwise pick the session that actually holds this workspace. Preferring
    # the default session is wrong: a stray `herdr` launches an empty one, and
    # the real work then sits in a named session nobody would find.
    if chosen is None and len(running) > 1:
        chosen = max(running, key=lambda s: _workspaces_under(s["name"], WORKSPACE))
    if chosen is None and running:
        chosen = running[0]

    _SESSION = chosen["name"] if chosen else ""
    return _SESSION or None


def _workspaces_under(session, root):
    """How many of a session's workspaces sit inside this workspace directory."""
    out = subprocess.run(["herdr", "--session", session, "workspace", "list"],
                         capture_output=True, text=True)
    if out.returncode != 0:
        return 0
    try:
        spaces = json.loads(out.stdout)["result"]["workspaces"]
    except (ValueError, KeyError):
        return 0
    ids = [w["workspace_id"] for w in spaces]
    if not ids:
        return 0
    detail = subprocess.run(["herdr", "--session", session, "api", "snapshot"],
                            capture_output=True, text=True)
    try:
        snap = json.loads(detail.stdout)["result"]
    except (ValueError, KeyError):
        return len(ids)
    panes = (snap.get("snapshot") or snap).get("panes") or []
    hits = sum(1 for p in panes if (p.get("cwd") or "").startswith(root))
    return hits or len(ids)


def herdr_running():
    return herdr_session() is not None


def herdr(args, quiet=False):
    """Run a herdr command against the live session and return its `result`."""
    session = herdr_session()
    prefix = ["--session", session] if session else []
    out = subprocess.run(["herdr"] + prefix + args, capture_output=True, text=True)
    if out.returncode != 0:
        if not quiet:
            import sys
            print(f"  herdr {' '.join(args)}: {out.stderr.strip()}", file=sys.stderr)
        return None
    try:
        return json.loads(out.stdout).get("result")
    except json.JSONDecodeError:
        # Some commands succeed with no body at all, such as report-metadata.
        # Only a non-zero exit means failure, so do not report None here.
        return {}


def agents_by_unit(units):
    """Map a unit name to the live agents running inside it.

    A pane belongs to the unit whose root is the longest prefix of its cwd, so
    a sub-unit wins over its parent.
    """
    result = herdr(["agent", "list"], quiet=True) if herdr_running() else None
    if not result:
        return {}

    roots = sorted(((os.path.realpath(u.root), u.name) for u in units),
                   key=lambda pair: -len(pair[0]))
    found = {}
    for agent in result.get("agents", []):
        cwd = agent.get("foreground_cwd") or agent.get("cwd")
        if not cwd:
            continue
        real = os.path.realpath(cwd)
        for root, name in roots:
            if real == root or real.startswith(root + os.sep):
                found.setdefault(name, []).append(agent)
                break
    return found
