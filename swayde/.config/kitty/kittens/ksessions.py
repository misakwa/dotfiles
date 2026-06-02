# ksessions — small watcher + thin save/rename wrappers around kitty's native
# session machinery.
#
# Kitty natively handles picker / jump via the `goto_session` action — see
# vim-mode.conf bindings. We add the gaps that aren't native:
#
#   1. on_close watcher       — auto-save the OS window when its last window
#                               closes (kitty has no save hook of its own)
#   2. claude --continue      — rewrite a bare `launch claude` so attach
#                               resumes the per-cwd claude session
#   3. TTL pruning            — delete *.kitty-session files older than the TTL
#   4. sticky KSESSION_NAME   — every saved `launch` line carries the session
#                               name as a user-var so attach inherits identity
#
# CLI subcommands (bound in vim-mode.conf):
#
#   save                  Save the current OS window. Silent overwrite if
#                         KSESSION_NAME is set; otherwise prompt (cwd basename
#                         default) and set KSESSION_NAME for next time.
#   name [<new>]          Set KSESSION_NAME on the focused OS window. If a
#                         session file exists for the current name, also rename
#                         the file and rewrite embedded KSESSION_NAME refs.
#                         Prompts when called with no arg.

import json
import os
import shlex
import subprocess
import sys
import time
from pathlib import Path


SESSIONS_DIR = Path(
    os.environ.get("KITTY_CONFIG_DIRECTORY", os.path.expanduser("~/.config/kitty"))
) / "sessions"
TTL_DAYS = int(os.environ.get("KSESSIONS_TTL_DAYS", "30"))


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------

def _kitty_ls():
    return json.loads(
        subprocess.run(
            ["kitten", "@", "ls"], capture_output=True, text=True, check=True
        ).stdout
    )


def _current_os_window(ls):
    """OS window containing this kitten's KITTY_WINDOW_ID, else the focused one."""
    me = os.environ.get("KITTY_WINDOW_ID")
    me = int(me) if me else None
    focused = None
    for ow in ls:
        for tab in ow.get("tabs", []):
            for w in tab.get("windows", []):
                if me is not None and w.get("id") == me:
                    return ow
                if w.get("is_focused"):
                    focused = ow
    return focused or (ls[0] if ls else None)


def _current_ksession_name(ow):
    for tab in ow.get("tabs", []):
        for w in tab.get("windows", []):
            uv = w.get("user_vars") or {}
            if uv.get("KSESSION_NAME"):
                return uv["KSESSION_NAME"]
    return None


def _cwd_basename(ow):
    for tab in ow.get("tabs", []):
        for w in tab.get("windows", []):
            cwd = w.get("cwd") or "/"
            base = os.path.basename(cwd.rstrip("/"))
            if base:
                return base
    return "session"


def _resolve_name(ow):
    """KSESSION_NAME user-var if set, else cwd basename, else 'session'."""
    return _current_ksession_name(ow) or _cwd_basename(ow)


def _set_user_var(name):
    subprocess.run(
        [
            "kitten",
            "@",
            "set-user-vars",
            "--match=state:focused",
            f"KSESSION_NAME={name}",
        ],
        check=True,
    )


def _prompt_name(default=""):
    """Prompt the user for a session name via `kitten ask`. Returns the
    typed string. `kitten ask` returns JSON like {"items": [], "response": "..."}
    — parse the response field rather than taking stdout verbatim."""
    try:
        cmd = ["kitten", "ask", "--type=line", "--prompt=session name: "]
        if default:
            cmd.extend(["--default", default])
        r = subprocess.run(cmd, capture_output=True, text=True)
        out = r.stdout.strip()
        try:
            return (json.loads(out).get("response") or "").strip()
        except (json.JSONDecodeError, AttributeError):
            return out
    except FileNotFoundError:
        return ""


def _prune():
    if TTL_DAYS <= 0 or not SESSIONS_DIR.exists():
        return
    cutoff = time.time() - TTL_DAYS * 86400
    for p in SESSIONS_DIR.glob("*.kitty-session"):
        try:
            if p.stat().st_mtime < cutoff:
                p.unlink()
        except OSError:
            pass


# -----------------------------------------------------------------------------
# Serialization
# -----------------------------------------------------------------------------

def _launch_line(w, session_name):
    """Emit a `launch ...` line. `--user-var=KSESSION_NAME=...` keeps the
    session's identity attached to every restored window."""
    uv = f"--user-var=KSESSION_NAME={session_name}"
    procs = w.get("foreground_processes") or []
    fg = procs[0] if procs else {}
    cmdline = list(fg.get("cmdline") or [])
    exe = os.path.basename(cmdline[0]) if cmdline else ""
    if exe in ("zsh", "bash", "fish", "sh"):
        return f"launch {uv}"
    if exe == "claude":
        # Gap #2 — per-cwd resume of the most recent claude session.
        return f"launch {uv} claude --continue"
    if exe in ("nvim", "vim", "ssh", "htop", "btop", "lazygit", "k9s"):
        return f"launch {uv} " + " ".join(shlex.quote(x) for x in cmdline)
    return f"launch {uv}"


def _serialize(ow, name):
    lines = []
    for ti, tab in enumerate(ow.get("tabs", [])):
        if ti > 0:
            lines.append("")
        title = (tab.get("title") or "").strip()
        lines.append(f"new_tab {title}".rstrip())
        if tab.get("layout"):
            lines.append(f"layout {tab['layout']}")
        for w in tab.get("windows", []):
            cwd = w.get("cwd") or os.path.expanduser("~")
            lines.append(f"cd {cwd}")
            lines.append(_launch_line(w, name))
    return "\n".join(lines) + "\n"


def _save(ow, name):
    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    (SESSIONS_DIR / f"{name}.kitty-session").write_text(_serialize(ow, name))


# -----------------------------------------------------------------------------
# Watcher
# -----------------------------------------------------------------------------

def on_close(boss, window, data):
    try:
        os_window_id = window.os_window_id
        remaining = sum(
            1
            for tab in boss.all_tabs
            if getattr(tab, "os_window_id", None) == os_window_id
            for w in tab
            if w.id != window.id
        )
        if remaining > 0:
            return
        ls = _kitty_ls()
        ow = next((x for x in ls if x.get("id") == os_window_id), None)
        if not ow:
            return
        _save(ow, _resolve_name(ow))
        _prune()
    except Exception as e:
        print(f"ksessions on_close: {e}", file=sys.stderr)


# After set_os_window_title runs once, kitty stops auto-syncing the OS title
# from the active tab — so every hook below must re-apply to keep it live.

def _apply_os_title(boss, os_window_id):
    try:
        ls = _kitty_ls()
    except subprocess.CalledProcessError:
        return
    ow = next((x for x in ls if x.get("id") == os_window_id), None)
    if not ow:
        return
    name = _current_ksession_name(ow)
    active_title = None
    for tab in ow.get("tabs", []):
        if not tab.get("is_focused"):
            continue
        for w in tab.get("windows", []):
            if w.get("is_focused"):
                active_title = w.get("title")
                break
        break
    if active_title is None:
        return
    title = f"[{name}] {active_title}" if name else active_title
    try:
        boss.set_os_window_title(os_window_id, title)
    except Exception as e:
        print(f"ksessions set_os_window_title: {e}", file=sys.stderr)


def on_title_change(boss, window, data):
    _apply_os_title(boss, window.os_window_id)


def on_focus_change(boss, window, data):
    if data.get("focused"):
        _apply_os_title(boss, window.os_window_id)


def on_set_user_var(boss, window, data):
    if data.get("name") == "KSESSION_NAME":
        _apply_os_title(boss, window.os_window_id)


# -----------------------------------------------------------------------------
# Subcommands
# -----------------------------------------------------------------------------

def _cmd_save(rest):
    try:
        ls = _kitty_ls()
    except subprocess.CalledProcessError as e:
        print(f"kitten @ ls failed: {e}", file=sys.stderr)
        return
    ow = _current_os_window(ls)
    if not ow:
        print("no OS window to save", file=sys.stderr)
        return
    name = _current_ksession_name(ow)
    if not name:
        # First save: prompt with cwd basename as the default.
        name = _prompt_name(default=_cwd_basename(ow))
        if not name:
            print("cancelled")
            return
        try:
            _set_user_var(name)
        except subprocess.CalledProcessError as e:
            print(f"set-user-vars failed: {e}", file=sys.stderr)
            return
    _save(ow, name)
    _prune()
    print(f"saved: {name}")


def _cmd_name(rest):
    try:
        ls = _kitty_ls()
    except subprocess.CalledProcessError as e:
        print(f"kitten @ ls failed: {e}", file=sys.stderr)
        return
    ow = _current_os_window(ls)
    if not ow:
        print("no OS window", file=sys.stderr)
        return
    old = _current_ksession_name(ow)
    new = rest[0] if rest else _prompt_name(default=old or _cwd_basename(ow))
    if not new:
        print("cancelled")
        return
    try:
        _set_user_var(new)
    except subprocess.CalledProcessError as e:
        print(f"set-user-vars failed: {e}", file=sys.stderr)
        return
    # If a session file already exists under the old name, move it and rewrite
    # the embedded KSESSION_NAME refs so attach inherits the new identity.
    if old and old != new:
        old_p = SESSIONS_DIR / f"{old}.kitty-session"
        new_p = SESSIONS_DIR / f"{new}.kitty-session"
        if old_p.exists():
            try:
                old_p.rename(new_p)
                content = new_p.read_text()
                new_p.write_text(
                    content.replace(
                        f"--user-var=KSESSION_NAME={old}",
                        f"--user-var=KSESSION_NAME={new}",
                    )
                )
                print(f"renamed file: {old}.kitty-session -> {new}.kitty-session")
            except OSError as e:
                print(f"file rename failed: {e}", file=sys.stderr)
    print(f"KSESSION_NAME = {new}")


SUBCOMMANDS = {"save": _cmd_save, "name": _cmd_name}


HELP = (
    "Usage: kitten kittens/ksessions.py <subcommand> [args]\n"
    "\n"
    "  save              Save current OS window. Silent overwrite if\n"
    "                    KSESSION_NAME is set; else prompt and set it.\n"
    "  name [<new>]      Set KSESSION_NAME on the focused OS window. Also\n"
    "                    renames the session file if one exists under the\n"
    "                    old name. Prompts when called with no arg.\n"
    "\n"
    "For picker / jump, use kitty's native actions:\n"
    "  goto_session ~/.config/kitty/sessions\n"
    "  goto_session -1\n"
)


def main(args):
    if args:
        first = args[0]
        if first.endswith("ksessions.py") or os.path.basename(first) == "ksessions":
            args = args[1:]
    args = list(args)
    if not args or args[0] in ("-h", "--help", "help"):
        sys.stdout.write(HELP)
        return None
    fn = SUBCOMMANDS.get(args[0])
    if not fn:
        print(f"unknown subcommand: {args[0]}", file=sys.stderr)
        sys.stdout.write(HELP)
        return None
    fn(args[1:])
    return None
