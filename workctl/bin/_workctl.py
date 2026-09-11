"""Shared helpers for the workctl commands.

Each command is a standalone uv script. They import this module by putting
their own directory on sys.path first:

    import os, sys
    sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))
    from _workctl import Unit, derive_units, resolve_root

`realpath` matters: the commands are reached through symlinks in ~/bin, and the
module lives beside the real files.

A root is any directory holding repositories beside a work folder. A repository
is either the bare layout, `<root>/<repo>/.bare` plus worktrees, or a plain
clone at `<root>/<repo>`. Units live at `<root>/<work>/<unit>/<repo>`.
"""
import argparse
import concurrent.futures as futures
import hashlib
import json
import os
import re
import subprocess
import sys
import time
import tomllib

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

# The login changes about never, so pay `gh api user` once a week at most.
AUTHOR_TTL = int(os.environ.get("WORKCTL_AUTHOR_TTL", "604800"))

CONFIG_NAME = ".workctl.toml"


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
    try:
        out = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    except OSError:
        # A root's config may name a repository whose folder is not cloned yet,
        # and that cwd raises rather than failing the command.
        return ""
    return out.stdout if allow_failure or out.returncode == 0 else ""


def parallel(func, items, limit=12):
    items = list(items)
    if not items:
        return []
    with futures.ThreadPoolExecutor(max_workers=min(len(items), limit)) as pool:
        return list(pool.map(func, items))


# --- the root and its configuration ----------------------------------------

def subdirs(path):
    try:
        return sorted(d for d in os.listdir(path) if os.path.isdir(os.path.join(path, d)))
    except OSError:
        return []


def is_checkout(path):
    """Whether a directory is a git checkout.

    A worktree carries `.git` as a file, a plain clone as a directory.
    """
    return os.path.exists(os.path.join(path, ".git"))


def git_common_dir(path):
    """The shared git directory of a checkout: its `.bare` or its `.git`."""
    text = run(["git", "-C", path, "rev-parse", "--path-format=absolute",
                "--git-common-dir"]).strip()
    return os.path.realpath(text) if text else None


def repo_folder_of(checkout):
    """The repository folder a checkout belongs to, or None outside git."""
    common = git_common_dir(checkout)
    return os.path.dirname(common) if common else None


def repo_name_of(checkout):
    """The name of the repository folder a checkout belongs to."""
    folder = repo_folder_of(checkout)
    return os.path.basename(folder) if folder else None


def find_root(start=None):
    """The root a directory sits in, or None when there is none."""
    base = os.path.realpath(start or os.getcwd())
    folder = repo_folder_of(base)
    if folder:
        return os.path.dirname(folder)

    names = {"work", ".workctl"}
    configured = os.environ.get("WORKCTL_WORK_DIR")
    if configured:
        names.add(configured)
    path = base
    while True:
        if os.path.isfile(os.path.join(path, CONFIG_NAME)):
            return path
        if any(os.path.isdir(os.path.join(path, name)) for name in names):
            return path
        parent = os.path.dirname(path)
        if parent == path:
            return None
        path = parent


_ROOTS = {}


# The root the running command settled on. herdr_session() needs it to pick
# between two live sessions, and every command resolves a root before it asks
# herdr anything, so record it here instead of threading it through each call.
_RESOLVED_ROOT = None


def resolve_root(explicit=None, start=None):
    """The root a command works in, from the flag, the disk or the environment.

    Where you stand beats WORKCTL_ROOT, so a shell profile can export a default
    root without overriding the root you are standing in.
    """
    key = (explicit, start)
    if key in _ROOTS:
        return _ROOTS[key]

    found = explicit or find_root(start) or os.environ.get("WORKCTL_ROOT")
    if not found:
        sys.exit("workctl: no root found. Pass --root DIR, run the command "
                 "inside a root, or set WORKCTL_ROOT to the root you mean.")

    root = os.path.realpath(os.path.expanduser(found))
    _ROOTS[key] = root
    global _RESOLVED_ROOT
    if _RESOLVED_ROOT is None:
        _RESOLVED_ROOT = root
    return root


_CONFIG = {}


def load_config(root):
    """The root's `.workctl.toml`, or {} when it is absent or unreadable."""
    key = os.path.realpath(root)
    if key not in _CONFIG:
        try:
            with open(os.path.join(key, CONFIG_NAME), "rb") as handle:
                _CONFIG[key] = tomllib.load(handle)
        except (OSError, tomllib.TOMLDecodeError):
            _CONFIG[key] = {}
    return _CONFIG[key]


_WORK_DIR = None


def work_dir(root=None):
    """The path of the root's work folder."""
    root = root or resolve_root()
    name = (_WORK_DIR
            or load_config(root).get("work-dir")
            or os.environ.get("WORKCTL_WORK_DIR")
            or "work")
    return os.path.join(root, name)


def archive_dir(root):
    """The path where a settled unit's notes go."""
    return os.path.join(root, load_config(root).get("archive-dir") or ".archive")


def branch_prefix(root):
    """The prefix every branch workctl creates carries."""
    return (load_config(root).get("branch-prefix")
            or os.environ.get("WORKCTL_BRANCH_PREFIX")
            or "misakwa/")


# --- the repositories under a root -----------------------------------------

def repos(root):
    """Every repository folder directly under the root."""
    work = os.path.basename(work_dir(root))
    found = []
    for name in subdirs(root):
        if name.startswith(".") or name == work:
            continue
        path = os.path.join(root, name)
        if os.path.isdir(os.path.join(path, ".bare")) or is_checkout(path):
            found.append(name)
    return found


_ACTIVE = {}


def active_repos(root):
    """The repositories that hold a unit checkout, plus the ones config names.

    The board then costs what the work in progress costs, rather than what the
    folder holds: a root with 30 clones and 3 units still scans 3 repositories.
    """
    key = os.path.realpath(root)
    if key in _ACTIVE:
        return _ACTIVE[key]

    checkouts = [c for unit in derive_units(root) for c in unit.checkouts]
    found = []
    for folder in parallel(repo_folder_of, checkouts):
        if folder and os.path.dirname(folder) == key:
            name = os.path.basename(folder)
            if name not in found:
                found.append(name)
    for name in load_config(root).get("repos") or []:
        if name not in found:
            found.append(name)
    _ACTIVE[key] = sorted(found) or repos(root)
    return _ACTIVE[key]


def scan_repos(root, all_repos=False):
    """The repositories a command scans: the active ones, or every one."""
    return repos(root) if all_repos else active_repos(root)


def add_root_arg(ap):
    """Register the shared --root and --work-dir flags.

    Named root, not workspace: workctl also creates a herdr workspace per
    unit, and one flag called --workspace read as that one.
    """
    ap.add_argument("--root", dest="root", default=None, metavar="DIR",
                    help="directory holding the repositories "
                         "(default: found from the current directory)")
    ap.add_argument("--work-dir", dest="work_dir", default=None, metavar="NAME",
                    action=_WorkDir,
                    help="name of the folder holding the units (default: work)")


def add_repo_scope_arg(ap):
    """Register the shared --all-repos flag."""
    ap.add_argument("--all-repos", dest="all_repos", action="store_true",
                    help="scan every repository under the root, not only "
                         "those holding a unit")


class _WorkDir(argparse.Action):
    """Apply --work-dir the moment it parses, so `work_dir` sees it."""

    def __call__(self, parser, namespace, value, option_string=None):
        global _WORK_DIR
        _WORK_DIR = value
        setattr(namespace, self.dest, value)


def primary_worktree(repo, root):
    """The repository's own default-branch checkout, where `wt` commands run."""
    known = (_FORGE.get(repo) or {}).get("main")
    if known and os.path.isdir(known):
        return known
    folder = os.path.join(root, repo)
    if is_checkout(folder):
        return folder
    for branch in ("main", "master"):
        path = os.path.join(folder, branch)
        if os.path.isdir(path):
            return path
    return None


# --- the units -------------------------------------------------------------

class Unit:
    """One directory under the work folder, with every checkout inside it."""

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


def derive_units(root=None):
    """Every unit under the root, derived from the folder structure alone."""
    base = work_dir(root or resolve_root())
    units = []
    for name in subdirs(base):
        unit_root = os.path.join(base, name)
        checkouts = checkouts_of(unit_root)
        nested = []
        for child_name in subdirs(unit_root):
            child = os.path.join(unit_root, child_name)
            if is_checkout(child):
                continue
            deep = [os.path.join(child, g) for g in subdirs(child)
                    if is_checkout(os.path.join(child, g))]
            if deep:
                nested.append(Unit(f"{name}/{child_name}", child, deep))
        if checkouts or not nested:
            units.append(Unit(name, unit_root, checkouts))
        units += nested
    return units


def find_unit(name, root=None):
    """The unit with this name, or a parent standing for its sub-units.

    A directory holding only sub-units is not a unit itself, but it is still a
    natural thing to name. `INC-355` gathers the checkouts of
    `INC-355/prod-eks-tf` and `INC-355/karpenter-termination-grace`.
    """
    root = root or resolve_root()
    units = derive_units(root)
    for unit in units:
        if unit.name == name:
            return unit
    children = [u for u in units if u.name.startswith(name + "/")]
    if children:
        unit_root = os.path.join(work_dir(root), name)
        return Unit(name, unit_root, [c for u in children for c in u.checkouts])
    return None


# --- worktrunk: the git facts ----------------------------------------------

_FORGE = {}


def git_facts(root=None, repos=None, refresh=False, all_repos=False):
    """Map each checkout's real path to (repo, worktrunk record).

    Worktrunk owns the git side: the branch, the dirty state, ahead and behind,
    and whether the branch already landed. Its `pr` and `checks` fields arrive
    incomplete, so the forge facts come from gh instead.
    """
    root = root or resolve_root()
    names = list(repos) if repos is not None else scan_repos(root, all_repos)

    def load(repo):
        cwd = primary_worktree(repo, root)
        text = run(["wt", "list", "--format", "json"], cwd=cwd) if cwd else ""
        report = json.loads(text) if text else {}
        forge = (report.get("repo") or {}).get("forge") or {}
        items = report.get("items") or []
        main = next((i["worktree"]["path"] for i in items
                     if (i.get("worktree") or {}).get("main")), None)
        return repo, {"owner": forge.get("owner") or "",
                      "name": forge.get("name") or repo,
                      "main": main or ""}, items

    def build():
        index, forge = {}, {}
        for repo, facts, items in parallel(load, names, limit=max(len(names), 1)):
            forge[repo] = facts
            for item in items:
                path = (item.get("worktree") or {}).get("path")
                if path:
                    index[os.path.realpath(path)] = (repo, item)
        return index, forge

    index, forge = cached(
        "git", (root, tuple(names)), GIT_TTL, build,
        encode=lambda pair: {"items": [[p, r, it] for p, (r, it) in pair[0].items()],
                             "forge": pair[1]},
        decode=lambda blob: ({p: (r, it) for p, r, it in blob["items"]},
                             blob["forge"]),
        refresh=refresh)
    _FORGE.update(forge)
    return index


def is_dirty(item):
    changes = (item.get("worktree") or {}).get("changes") or {}
    return any(changes.get(k) for k in DIRTY_KEYS)


# --- GitHub: the forge facts -----------------------------------------------

def owner_for(repo, root=None):
    """The forge owner of a repository: vectara in vectara/platform."""
    owner = (_FORGE.get(repo) or {}).get("owner")
    if not owner and root:
        owner = _owner_in(run(["git", "remote", "get-url", "origin"],
                              cwd=os.path.join(root, repo)).strip())
    if not owner and root:
        owner = load_config(root).get("owner")
    return owner or os.environ.get("WORKCTL_OWNER", "")


def _owner_in(url):
    """The owner in git@host:owner/name.git or https://host/owner/name.git."""
    text = url.rstrip("/")
    if text.endswith(".git"):
        text = text[:-4]
    parts = text.replace(":", "/").split("/")
    return parts[-2] if len(parts) > 1 else ""


def forge_name(repo):
    """The repository's name on the forge, which may differ from its folder."""
    return (_FORGE.get(repo) or {}).get("name") or repo


def default_author():
    """The login whose pull requests count as his."""
    if os.environ.get("WORKCTL_AUTHOR"):
        return os.environ["WORKCTL_AUTHOR"]

    def build():
        return (run(["gh", "api", "user", "--jq", ".login"]).strip()
                or run(["git", "config", "user.name"]).strip())

    return cached("author", "gh", AUTHOR_TTL, build,
                  encode=lambda login: {"login": login},
                  decode=lambda blob: blob["login"])


def pr_facts(repos=None, owner=None, workspace=None, refresh=False):
    """Map (repo, branch) to its open pull request.

    One list call per repository. Asking GitHub for statusCheckRollup in the
    same call answers HTTP 504 on repositories this size, so checks come later
    and only for the pull requests that matched a unit.
    """
    root = workspace or resolve_root()
    names = list(repos) if repos is not None else active_repos(root)
    fields = "number,headRefName,reviewDecision,isDraft,url,author"

    def load(repo):
        who = owner or owner_for(repo, root)
        text = run(["gh", "pr", "list", "--repo", f"{who}/{forge_name(repo)}",
                    "--state", "open", "--json", fields, "--limit", str(PR_LIMIT)])
        return repo, (json.loads(text) if text else [])

    def build():
        index = {}
        for repo, prs in parallel(load, names, limit=max(len(names), 1)):
            for pr in prs:
                index[(repo, pr["headRefName"])] = pr
        return index

    return cached("pr", (root, owner, tuple(names), PR_LIMIT), PR_TTL, build,
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
    return not login or login == (author or default_author())


def failing_checks(pairs, owner=None, ignored=None, root=None):
    """Map (repo, number) to the names of its genuinely failing checks."""
    skip = IGNORED_CHECKS if ignored is None else ignored

    def load(key):
        repo, number = key
        who = owner or owner_for(repo, root)
        names = []
        for line in run(["gh", "pr", "checks", str(number),
                         "--repo", f"{who}/{forge_name(repo)}"],
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


def unresolved_threads(pairs, owner=None, root=None):
    """Map (repo, number) to its count of unresolved review threads.

    An approved pull request can still carry an unanswered question. Merging it
    then drops that feedback silently, so the board needs to see it.
    """

    def load(key):
        repo, number = key
        who = owner or owner_for(repo, root)
        text = run(["gh", "api", "graphql", "-f", f"query={UNRESOLVED_QUERY}",
                    "-F", f"owner={who}", "-F", f"repo={forge_name(repo)}",
                    "-F", f"number={number}"])
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
    root = os.path.realpath(workspace or resolve_root())
    held = {os.path.realpath(c) for u in derive_units(root) for c in u.checkouts}
    primaries = {os.path.realpath(p)
                 for p in (primary_worktree(r, root) for r in repos(root))
                 if p}
    found = []
    for path, (repo, item) in git.items():
        # A plain clone is its own primary worktree, and it sits directly under
        # the root, so the path rules below would read it as a stray checkout.
        if (item.get("worktree") or {}).get("main"):
            continue
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


def herdr_session(root=None):
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

    root = root or _RESOLVED_ROOT

    text = run(["herdr", "session", "list", "--json"], allow_failure=True)
    try:
        sessions = json.loads(text)["sessions"] if text else []
    except (json.JSONDecodeError, KeyError):
        sessions = []
    running = [s for s in sessions if s.get("running")]

    # A server left behind by an upgrade answers `session list` and even
    # `workspace list`, then fails every agent command with protocol_mismatch.
    # Rule it out here, or the picker hands the whole run to a dead end.
    if len(running) > 1:
        compatible = [s for s in running if _session_compatible(s["name"])]
        running = compatible or running

    # Inside a herdr pane, follow the session that owns this pane.
    socket = os.environ.get("HERDR_SOCKET_PATH")
    chosen = next((s for s in running if s.get("socket_path") == socket), None) if socket else None

    # Otherwise pick the session that actually holds this root. Preferring
    # the default session is wrong: a stray `herdr` launches an empty one, and
    # the real work then sits in a named session nobody would find.
    if chosen is None and root and len(running) > 1:
        chosen = max(running, key=lambda s: _workspaces_under(s["name"], root))
    if chosen is None and running:
        chosen = running[0]

    _SESSION = chosen["name"] if chosen else ""
    return _SESSION or None


def _session_compatible(session):
    """Whether this session's server speaks the protocol this client sends."""
    out = subprocess.run(["herdr", "--session", session, "status", "server", "--json"],
                         capture_output=True, text=True)
    if out.returncode != 0:
        return False
    try:
        return json.loads(out.stdout).get("compatible") is True
    except json.JSONDecodeError:
        return False


def _workspaces_under(session, root):
    """How many of a session's workspaces sit inside this root."""
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


def herdr_call(args):
    """Run a herdr command. Returns (result, error text); one of them is None.

    Callers that decide for themselves what an error means use this. `agent
    start` is the case: it reports agent_not_ready when the agent stops on a
    first-run prompt, and the agent is running all the same.
    """
    session = herdr_session()
    prefix = ["--session", session] if session else []
    out = subprocess.run(["herdr"] + prefix + args, capture_output=True, text=True)
    if out.returncode != 0:
        return None, out.stderr.strip() or f"exit status {out.returncode}"
    if not out.stdout.strip():
        # Some commands succeed with no body at all, such as report-metadata.
        # Only a non-zero exit means failure, so do not report an error here.
        return {}, None
    try:
        return json.loads(out.stdout).get("result"), None
    except json.JSONDecodeError:
        # A body that is not JSON is plain text, which this caller cannot use.
        # `agent read` is the one that does; it goes through herdr_text().
        return None, "expected JSON, got text"


def herdr(args, quiet=False):
    """Run a herdr command against the live session and return its `result`."""
    result, error = herdr_call(args)
    if error and not quiet:
        print(f"  herdr {' '.join(args)}: {error}", file=sys.stderr)
    return result


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


def agent_name(unit_name):
    """A unit name as herdr accepts it: `[a-z][a-z0-9_-]{0,31}`.

    herdr rejects an uppercase letter, a leading digit and anything over 32
    characters. A unit name carries none of those rules, and the name is the
    handle an attach takes, so fold one into the other here.
    """
    slug = re.sub(r"[^a-z0-9_-]", "-", unit_name.lower()).strip("-")
    if not slug or not slug[0].isalpha():
        slug = "u-" + slug
    return slug[:32]


def live_agent(name, units, kind=None):
    """A unit's live agent, or None. A blocked one wins; it waits on a person."""
    found = [a for a in agents_by_unit(units).get(name, [])
             if kind is None or a.get("agent") == kind]
    if not found:
        return None
    return next((a for a in found if a.get("agent_status") == "blocked"), found[0])


def attach_target(agent):
    """The herdr handle for one agent from `agent list`.

    Prefer the name `workctl new` gave it. An agent started by hand is detected
    but stays unnamed, and herdr then answers only to the pane that hosts it.
    """
    return agent.get("name") or agent.get("pane_id")


def herdr_attach(target):
    """Hand this terminal to a herdr agent. Does not return when it succeeds.

    `agent attach` streams live terminal frames and reads stdin, so it has to
    own the terminal. Never run it through herdr(), which captures both.
    """
    session = herdr_session()
    prefix = ["--session", session] if session else []
    os.execvp("herdr", ["herdr"] + prefix + ["agent", "attach", target])


def herdr_text(args, quiet=False):
    """Run a herdr command that answers in plain text, such as `agent read`."""
    session = herdr_session()
    prefix = ["--session", session] if session else []
    out = subprocess.run(["herdr"] + prefix + args, capture_output=True, text=True)
    if out.returncode != 0:
        if not quiet:
            print(f"  herdr {' '.join(args)}: {out.stderr.strip()}", file=sys.stderr)
        return None
    return out.stdout
