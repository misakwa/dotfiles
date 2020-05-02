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

[ -r "~/.nodenv/completions/nodenv.zsh" ] && source "~/.nodenv/completions/nodenv.zsh"

autoload -U +X bashcompinit && bashcompinit
