[[ -r ~/.zsh/znap/znap.zsh ]] ||
    git clone --depth 1 -- https://github.com/marlonrichert/zsh-snap.git ~/.zsh/znap

source ~/.zsh/znap/znap.zsh

bindkey -e


znap prompt sindresorhus/pure

znap source ohmyzsh/ohmyzsh lib/{git,history,key-bindings,clipboard} plugins/{command-not-found,asdf,git,aws}

# znap source marlonrichert/zsh-edit
# znap source marlonrichert/zsh-autocomplete

ZSH_AUTOSUGGEST_STRATEGY=( history )
znap source zsh-users/zsh-autosuggestions

znap source zsh-users/zsh-history-substring-search

ZSH_HIGHLIGHT_HIGHLIGHTERS=( main brackets )
# znap source zsh-users/zsh-syntax-highlighting

# znap source johanhaleby/kubetail

eval "$(/home/linuxbrew/.linuxbrew/bin/brew shellenv)"

for file in ~/.{path,exports,aliases,functions,extra}; do
    [ -r "$file" ] && source "$file"
done
unset file

# Paperspace
export PAPERSPACE_INSTALL="/home/michael/.paperspace"
export PATH="$PAPERSPACE_INSTALL/bin:$PATH"
