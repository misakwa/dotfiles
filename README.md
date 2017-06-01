Minimal dotfiles
================

Uses stow

Install stow if you don't have it

Homebrew

```bash
$ brew install stow
```

Debian/Ubuntu

```bash
$ sudo apt-get install stow
```

Fedora/CentOS

```
$ dnf install stow
```

```sh
$ git clone https://github.com/misakwa/dotfiles.git ~/.dotfiles
```

# TODO: Fix .gitignore file not being stowed as expected

```
$ cd ~/.dotfiles
$ stow -R -t $HOME -v -d $HOME/.dotfiles bash tmux vcs
```
