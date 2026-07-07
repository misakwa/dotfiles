# Dotfiles management via GNU Stow.
#
# Uses --no-folding so stow never symlinks a whole directory: it creates real
# directories at the target and symlinks only leaf files. This keeps runtime
# state that tools write next to their config (sessions, caches, __pycache__)
# out of this repo.

STOW       ?= stow
GIT        ?= git
TARGET     ?= $(HOME)
DIR        := $(CURDIR)

ifeq ($(OS),Windows_NT)
    detected_OS := Windows
else
    detected_OS := $(shell uname -s)
endif

PACKAGES   ?= bash tmux vcs vim zsh swayde claude yazi codex pi registries wrappers llama-swap
STOW_FLAGS := --no-folding -v -t $(TARGET) -d $(DIR)

# launchd agents (~/Library/LaunchAgents) and Go's env file
# (~/Library/Application Support/go/env) live at macOS-specific paths.
ifeq ($(detected_OS),Darwin)
PACKAGES   += launchd go
endif

# launchd plists are rendered from *.plist.in with @HOME@ expanded to $(TARGET),
# so the tracked templates carry no hardcoded home directory. Rendered output is
# gitignored and `stow` depends on `render`.
PLIST_TMPL := $(wildcard launchd/Library/LaunchAgents/*.plist.in)
PLIST_OUT  := $(PLIST_TMPL:.in=)

.PHONY: help stow unstow restow check list .submodules render

help: ## Show this help
	@echo "Usage: make <target>"
	@echo
	@echo "  stow           Symlink all packages (restow: idempotent, unfolds)"
	@echo "  unstow         Remove all package symlinks"
	@echo "  restow         Alias for stow"
	@echo "  check          Dry-run stow for all packages (no changes)"
	@echo "  render         Render launchd plists from *.plist.in templates"
	@echo "  stow-<pkg>     Symlink a single package"
	@echo "  unstow-<pkg>   Remove a single package"
	@echo "  check-<pkg>    Dry-run a single package"
	@echo "  list           Print the configured packages"
	@echo
	@echo "Packages: $(PACKAGES)"

.submodules:
	$(GIT) submodule update --init --recursive

render: $(PLIST_OUT) ## Render launchd plist templates (@HOME@ -> $HOME)

launchd/Library/LaunchAgents/%.plist: launchd/Library/LaunchAgents/%.plist.in
	sed 's|@HOME@|$(TARGET)|g' $< > $@

stow: .submodules render ## Symlink all packages
	$(STOW) -R $(STOW_FLAGS) $(PACKAGES)

unstow: ## Remove all package symlinks
	$(STOW) -D $(STOW_FLAGS) $(PACKAGES)

restow: stow ## Alias for stow

check: ## Dry-run: show what stow would do for all packages
	$(STOW) -n -R $(STOW_FLAGS) $(PACKAGES)

stow-%: .submodules ## Symlink a single package
	$(STOW) -R $(STOW_FLAGS) $*

# launchd plists must be rendered before they can be symlinked
stow-launchd: render

unstow-%: ## Remove a single package
	$(STOW) -D $(STOW_FLAGS) $*

check-%: ## Dry-run a single package
	$(STOW) -n -R $(STOW_FLAGS) $*

list: ## Print the configured packages
	@echo $(PACKAGES)
