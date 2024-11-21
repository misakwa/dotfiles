[[ -r ~/.zsh/znap/znap.zsh ]] ||
    git clone --depth 1 -- https://github.com/marlonrichert/zsh-snap.git ~/.zsh/znap

source ~/.zsh/znap/znap.zsh

bindkey -e


znap prompt sindresorhus/pure

znap source ohmyzsh/ohmyzsh lib/{git,history}

znap source marlonrichert/zsh-edit
znap source marlonrichert/zsh-autocomplete

ZSH_AUTOSUGGEST_STRATEGY=( history )
znap source zsh-users/zsh-autosuggestions

ZSH_HIGHLIGHT_HIGHLIGHTERS=( main brackets )
znap source zsh-users/zsh-syntax-highlighting

for file in ~/.{path,exports,aliases,functions,extra}; do
    [ -r "$file" ] && source "$file"
done
unset file

# fpath=(${ASDF_DIR}/completions $fpath)
