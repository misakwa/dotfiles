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
import json
import os
import subprocess

WORKSPACE = os.environ.get("WORKCTL_WORKSPACE",
                           os.path.expanduser("~/Projects/vectara-bare"))
BRANCH_PREFIX = os.environ.get("WORKCTL_BRANCH_PREFIX", "misakwa/")
OWNER = os.environ.get("WORKCTL_OWNER", "vectara")

# Checks that fail permanently and say nothing about the branch. One always-red
# check would otherwise turn every pull request in the repository red.
IGNORED_CHECKS = set(
    filter(None, os.environ.get("WORKCTL_IGNORED_CHECKS", "transcript-check").split(",")))

DIRTY_KEYS = ("staged", "modified", "untracked", "deleted", "conflicted")


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

    @property
    def age_days(self):
        newest = max(os.path.getmtime(p) for p in [self.root] + list(self.checkouts))
        import time
        return int((time.time() - newest) / 86400)

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

def git_facts(workspace=None, repos=None):
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

    index = {}
    for repo, items in parallel(load, names, limit=max(len(names), 1)):
        for item in items:
            path = (item.get("worktree") or {}).get("path")
            if path:
                index[os.path.realpath(path)] = (repo, item)
    return index


def is_dirty(item):
    changes = (item.get("worktree") or {}).get("changes") or {}
    return any(changes.get(k) for k in DIRTY_KEYS)


# --- GitHub: the forge facts -----------------------------------------------

def pr_facts(repos=None, owner=None, workspace=None):
    """Map (repo, branch) to its open pull request.

    One list call per repository. Asking GitHub for statusCheckRollup in the
    same call answers HTTP 504 on repositories this size, so checks come later
    and only for the pull requests that matched a unit.
    """
    names = repos if repos is not None else bare_repos(workspace)
    who = owner or OWNER
    fields = "number,headRefName,reviewDecision,isDraft,url"

    def load(repo):
        text = run(["gh", "pr", "list", "--repo", f"{who}/{repo}", "--state", "open",
                    "--json", fields, "--limit", "300"])
        return repo, (json.loads(text) if text else [])

    index = {}
    for repo, prs in parallel(load, names, limit=max(len(names), 1)):
        for pr in prs:
            index[(repo, pr["headRefName"])] = pr
    return index


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


# --- herdr -----------------------------------------------------------------

def herdr_running():
    return "status: running" in run(["herdr", "status", "server"], allow_failure=True)


def herdr(args, quiet=False):
    """Run a herdr command and return its `result`, or None."""
    out = subprocess.run(["herdr"] + args, capture_output=True, text=True)
    if out.returncode != 0:
        if not quiet:
            import sys
            print(f"  herdr {' '.join(args)}: {out.stderr.strip()}", file=sys.stderr)
        return None
    try:
        return json.loads(out.stdout).get("result")
    except json.JSONDecodeError:
        return None


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
