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
```
