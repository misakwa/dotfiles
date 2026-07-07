# Dotfiles management via GNU Stow.
#
# Uses --no-folding so stow never symlinks a whole directory: it creates real
# directories at the target and symlinks only leaf files. This keeps runtime
# state that tools write next to their config (sessions, caches, __pycache__)
# out of this repo.

STOW       ?= stow
TARGET     ?= $(HOME)
DIR        := $(CURDIR)
PACKAGES   ?= bash tmux vcs vim zsh swayde claude yazi codex pi
STOW_FLAGS := --no-folding -v -t $(TARGET) -d $(DIR)

.PHONY: help stow unstow restow check list

help: ## Show this help
	@echo "Usage: make <target>"
	@echo
	@echo "  stow           Symlink all packages (restow: idempotent, unfolds)"
	@echo "  unstow         Remove all package symlinks"
	@echo "  restow         Alias for stow"
	@echo "  check          Dry-run stow for all packages (no changes)"
	@echo "  stow-<pkg>     Symlink a single package"
	@echo "  unstow-<pkg>   Remove a single package"
	@echo "  check-<pkg>    Dry-run a single package"
	@echo "  list           Print the configured packages"
	@echo
	@echo "Packages: $(PACKAGES)"

stow: ## Symlink all packages
	$(STOW) -R $(STOW_FLAGS) $(PACKAGES)

unstow: ## Remove all package symlinks
	$(STOW) -D $(STOW_FLAGS) $(PACKAGES)

restow: stow ## Alias for stow

check: ## Dry-run: show what stow would do for all packages
	$(STOW) -n -R $(STOW_FLAGS) $(PACKAGES)

stow-%: ## Symlink a single package
	$(STOW) -R $(STOW_FLAGS) $*

unstow-%: ## Remove a single package
	$(STOW) -D $(STOW_FLAGS) $*

check-%: ## Dry-run a single package
	$(STOW) -n -R $(STOW_FLAGS) $*

list: ## Print the configured packages
	@echo $(PACKAGES)
