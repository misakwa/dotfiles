# Sourced on every zsh invocation, interactive or not. Non-interactive shells
# skip .zshrc, so tools launched by herdr keybindings, worktrunk hooks, systemd
# units, and editors would otherwise get only the system PATH.
if [[ -z "$DOTFILES_PATH_SET" ]]; then
    export DOTFILES_PATH_SET=1
    [[ -r ~/.path ]] && source ~/.path
fi
