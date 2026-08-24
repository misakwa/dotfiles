#!/usr/bin/env python3
"""Stop hook for Claude Code and Codex: open a kitty dir-diff when an unattended turn edited >=3 files or >=100 lines."""
import json
import os
import re
import shutil
import subprocess
import sys

UNATTENDED_MODES = {"auto", "bypassPermissions"}
CLAUDE_EDIT_TOOLS = {"Edit", "Write", "MultiEdit", "NotebookEdit"}
PATCH_FILE = re.compile(r"^\*\*\* (?:Update|Add|Delete) File: (.+)$", re.M)
MIN_FILES, MIN_LINES = 3, 100


def entries(transcript):
    for line in open(transcript, encoding="utf-8"):
        try:
            yield json.loads(line)
        except ValueError:
            continue


def claude_edits(transcript, prompt_id):
    files, in_turn, current = set(), prompt_id is None, None
    for entry in entries(transcript):
        if entry.get("isSidechain"):
            continue
        if entry.get("type") == "user" and entry.get("promptId"):
            if entry["promptId"] != current:
                current = entry["promptId"]
                in_turn = current == prompt_id
                if in_turn:
                    files.clear()
            continue
        if not in_turn or entry.get("type") != "assistant":
            continue
        for block in entry.get("message", {}).get("content") or []:
            if block.get("type") == "tool_use" and block.get("name") in CLAUDE_EDIT_TOOLS:
                inp = block.get("input") or {}
                path = inp.get("file_path") or inp.get("notebook_path")
                if path:
                    files.add(path)
    return files


def codex_edits(transcript, turn_id, cwd):
    files, in_turn, turn_cwd = set(), turn_id is None, cwd
    for entry in entries(transcript):
        payload = entry.get("payload") or {}
        if entry.get("type") == "turn_context":
            in_turn = payload.get("turn_id") == turn_id
            if in_turn:
                files.clear()
                turn_cwd = payload.get("cwd") or cwd
            continue
        if not in_turn or entry.get("type") != "response_item" or payload.get("name") != "apply_patch":
            continue
        patch = payload.get("input") or payload.get("arguments") or ""
        if patch.startswith("{"):
            try:
                patch = json.loads(patch).get("input", "")
            except ValueError:
                patch = ""
        for path in PATCH_FILE.findall(patch):
            files.add(os.path.join(turn_cwd, path.strip()))
    return files


def changed_lines(cwd, files):
    out = subprocess.run(["git", "diff", "--numstat", "HEAD", "--"] + sorted(files),
                         cwd=cwd, capture_output=True, text=True).stdout
    total = 0
    for row in out.splitlines():
        added, deleted = row.split("\t")[:2]
        total += (int(added) if added.isdigit() else 0) + (int(deleted) if deleted.isdigit() else 0)
    for path in files:
        tracked = subprocess.run(["git", "ls-files", "--error-unmatch", path], cwd=cwd, capture_output=True).returncode == 0
        if not tracked and os.path.isfile(path):
            with open(path, "rb") as fh:
                total += sum(1 for _ in fh)
    return total


def main():
    hook = json.load(sys.stdin)
    cwd = hook.get("cwd") or os.getcwd()
    transcript = hook.get("transcript_path")
    if hook.get("permission_mode") not in UNATTENDED_MODES or not shutil.which("kitty") or not transcript:
        return
    if subprocess.run(["git", "rev-parse", "--verify", "HEAD"], cwd=cwd, capture_output=True).returncode != 0:
        return
    if "prompt_id" in hook:
        files = claude_edits(transcript, hook["prompt_id"])
    else:
        files = codex_edits(transcript, hook.get("turn_id"), cwd)
    if not files:
        return
    if len(files) < MIN_FILES and changed_lines(cwd, files) < MIN_LINES:
        return
    if os.environ.get("KITTY_LISTEN_ON"):
        subprocess.run(["kitten", "@", "launch", "--type=tab", "--tab-title=agent review", "--cwd=current",
                        "git", "difftool", "--dir-diff", "-y", "HEAD"], cwd=cwd)
        where = "tab"
    else:
        subprocess.Popen(["kitty", "--detach", "--directory", cwd, "--", "git", "difftool", "--dir-diff", "-y", "HEAD"],
                         cwd=cwd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        where = "window"
    print(json.dumps({"systemMessage": f"opened a kitty review {where} — `q` when done."}))


if __name__ == "__main__":
    main()
