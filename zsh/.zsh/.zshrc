source $HOME/.zsh/antigen.zsh

antigen use oh-my-zsh

antigen bundle git
antigen bundle zsh-users/zsh-syntax-highlighting
antigen bundle zsh-users/zsh-completions

antigen theme robbyrussell

antigen apply

for file in ~/.{path,exports,aliases,functions,extra}; do
    [ -r "$file" ] && source "$file"
done
unset file

# export PATH="bin:$HOME/bin:$HOME/.cargo/bin:$HOME/.rbenv/bin:$PATH"
