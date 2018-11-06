# My dotfiles

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


```
$ cd ~/.dotfiles
$ git submodule update --init --recursive
$ stow -R -t $HOME -v -d $HOME/.dotfiles bash tmux vcs vim zsh nvim
```
