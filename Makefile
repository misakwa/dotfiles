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

PACKAGES   ?= bash tmux vcs vim zsh swayde claude yazi codex pi docker wrappers llama-swap agents doom
STOW_FLAGS := --no-folding -v -t $(TARGET) -d $(DIR)

# Per-OS packages install at OS-specific paths: launchd agents and cmux on
# macOS; systemd user units on Linux. SERVICE_MGR selects the loader that
# `enable` dispatches to.
ifeq ($(detected_OS),Darwin)
PACKAGES    += launchd cmux
SERVICE_MGR := launchd
endif
ifeq ($(detected_OS),Linux)
PACKAGES    += systemd
SERVICE_MGR := systemd
endif

# launchd plists are rendered from *.plist.in with @HOME@ expanded to $(TARGET),
# so the tracked templates carry no hardcoded home directory. Rendered output is
# gitignored and `stow` depends on `render`.
PLIST_TMPL := $(wildcard launchd/Library/LaunchAgents/*.plist.in)
PLIST_OUT  := $(PLIST_TMPL:.in=)

# Long-running services, loaded per OS by `enable`: launchd agents on macOS,
# systemd user units on Linux. The wrappers in ~/bin are shared across both.
LAUNCH_AGENTS := com.misakwa.llama-swap com.misakwa.emacs
SYSTEMD_UNITS := com.misakwa.llama-swap.service com.misakwa.emacs.service

# Doom Emacs: the framework is cloned, not stowed, since it writes into its own
# worktree. Only ~/.config/doom is a package. DOOMLOCAL must match the
# DOOMLOCALDIR exported by bash/.path and wrappers/bin/emacs-daemon-service.
EMACSDIR   ?= $(TARGET)/.config/emacs
DOOMLOCAL  ?= $(TARGET)/.local/share/doom-local
DOOM_REPO  ?= https://github.com/doomemacs/core

.PHONY: help stow unstow restow check prune list .submodules render enable enable-launchd enable-systemd doom-install doom-reclone

help: ## Show this help
	@echo "Usage: make <target>"
	@echo
	@echo "  stow           Symlink all packages (restow: idempotent, unfolds)"
	@echo "  unstow         Remove all package symlinks"
	@echo "  restow         Alias for stow"
	@echo "  check          Dry-run stow for all packages (no changes)"
	@echo "  prune          Report symlinks stranded by deleted files (no changes)"
	@echo "  prune FORCE=1  Delete what prune reported"
	@echo "  render         Render launchd plists from *.plist.in templates"
	@echo "  doom-install   Clone Doom into ~/.config/emacs and install packages"
	@echo "  doom-reclone   Replace the Doom clone with a fresh one"
	@echo "  enable         Load/enable the services for this OS (launchd/systemd)"
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

ifdef SERVICE_MGR
enable: enable-$(SERVICE_MGR) ## Load/enable the long-running services for this OS
else
enable: ## Load/enable the long-running services for this OS
	@echo "No service manager configured for $(detected_OS)"
endif

enable-launchd: stow-launchd ## (macOS) (Re)load the launchd agents
	@for label in $(LAUNCH_AGENTS); do \
	  plist="$(TARGET)/Library/LaunchAgents/$$label.plist"; \
	  echo "launchd: reloading $$label"; \
	  launchctl bootout gui/$$(id -u)/$$label 2>/dev/null || true; \
	  launchctl bootstrap gui/$$(id -u) "$$plist"; \
	done

enable-systemd: stow-systemd ## (Linux) Enable + start the systemd user units
	loginctl enable-linger $$(id -un)
	systemctl --user daemon-reload
	systemctl --user enable --now $(SYSTEMD_UNITS)

# stow-doom first: `doom install` writes template init.el/config.el/packages.el
# into $DOOMDIR if they're absent, and would land real files on top of the
# package. --no-config keeps it off them even then.
doom-install: stow-doom ## Clone Doom into ~/.config/emacs and install packages
	@if [ -d "$(EMACSDIR)/.git" ]; then \
	  echo "doom: $(EMACSDIR) already present, skipping clone"; \
	else \
	  $(GIT) clone --depth 1 --recurse-submodules --shallow-submodules \
	    $(DOOM_REPO) "$(EMACSDIR)"; \
	fi
	@"$(EMACSDIR)/bin/doom" install --no-config --env

# Upgrading is a discard-and-reclone, so the pinned modules submodule never has
# to deepen in place (a fetch for a moved pin drags in its full history).
doom-reclone: ## Replace ~/.config/emacs with a fresh clone
	@case "$(DOOMLOCAL)" in "$(EMACSDIR)"*) echo "refusing: DOOMLOCAL is inside $(EMACSDIR)"; exit 1 ;; esac
	rm -rf "$(EMACSDIR)"
	@$(MAKE) doom-install

prune: ## Report symlinks stranded by deleted package files (FORCE=1 to delete)
	@scripts/stow-prune $(if $(FORCE),--force)

unstow-%: ## Remove a single package
	$(STOW) -D $(STOW_FLAGS) $*

check-%: ## Dry-run a single package
	$(STOW) -n -R $(STOW_FLAGS) $*

list: ## Print the configured packages
	@echo $(PACKAGES)
