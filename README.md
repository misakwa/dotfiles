# My dotfiles

Uses stow

Install stow if you don't have it

Homebrew

```bash
brew install stow
```

Debian/Ubuntu

```bash
sudo apt-get install stow
```

Fedora/CentOS

```
dnf install stow
```

```sh
git clone https://github.com/misakwa/dotfiles.git ~/.dotfiles
```

```sh
$ cd ~/.dotfiles
$ git submodule update --init --recursive
$ make check   # dry-run: preview the symlinks
$ make stow    # create the symlinks
```

Management is done through the `Makefile` (GNU Stow with `--no-folding`, so
only individual files are symlinked and tools' runtime state stays out of the
repo):

```sh
$ make stow           # symlink all packages
$ make unstow         # remove all symlinks
$ make check          # dry-run all packages
$ make stow-<pkg>     # e.g. make stow-swayde
$ make list           # show configured packages
$ make prune          # report what deleted files left behind
$ make prune FORCE=1  # delete what prune reported
```

`make prune` wraps `scripts/stow-prune`, which reports two kinds of leftovers:
symlinks inside the repo whose target is gone (an `agents/` skill link, say,
after the skill was renamed in `skills/`), and launchd plists still rendered
from a `*.plist.in` that no longer exists. It reports by default and deletes
only with `FORCE=1`, and it flags a launchd job still loaded after its plist
was removed, since deleting the file does not unload the service.

Detection of the first kind is `chkstow -t "$HOME/.dotfiles" --badlinks`, which
ships with stow. Point it at the repo, not at `$HOME`: it walks whatever tree
you give it, and against `$HOME` it reports every broken symlink on the system.
It only reports — removal is the script's half.

## Repository structure

Each top-level directory is a **stow package** for one tool (e.g. `tmux/`,
`zsh/`, `yazi/`, `cmux/`). Inside a package, files are laid out exactly as they
should appear under `$HOME`, so the package path mirrors the install path:

```
cmux/.config/cmux/cmux.json   ->  ~/.config/cmux/cmux.json
zsh/.zshrc                    ->  ~/.zshrc
```

Because stow runs with `--no-folding`, only the leaf files are symlinked; the
parent directories (`~/.config/cmux/`, …) stay real, so runtime state a tool
writes next to its config (sessions, caches) never leaks into this repo.

To add a config: create `<pkg>/<path-relative-to-$HOME>`, add `<pkg>` to
`PACKAGES` in the `Makefile`, then `make stow-<pkg>`. Configs an app rewrites
in place should be edited in the repo file (the source of truth), not through
the `~` symlink.

Packages are OS-gated in the `Makefile`: most are shared, while macOS-only
(`launchd`, `cmux`) and Linux-only (`systemd`) packages live behind
`Darwin`/`Linux` guards and are stowed only on that platform.
