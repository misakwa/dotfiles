source $HOME/.zsh/antigen.zsh

antigen use oh-my-zsh

antigen bundle command-not-found

antigen bundle git

antigen bundle zsh-users/zsh-syntax-highlighting
antigen bundle zsh-users/zsh-completions

antigen theme robbyrussell

antigen apply

for file in ~/.{path,exports,aliases,functions,extra}; do
    [ -r "$file" ] && source "$file"
done
unset file

# append completions to fpath
fpath=(${ASDF_DIR}/completions $fpath)
# initialise completions with ZSH's compinit
autoload -Uz compinit && compinit

# Created by `pipx` on 2022-03-19 12:06:44
export PATH="$PATH:/home/michael/.local/bin"
