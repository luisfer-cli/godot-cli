.PHONY: help test self-test check smoke export install uninstall clean

PREFIX ?= $(HOME)/.local
BIN ?= gd
DIST ?= dist
VERSION ?= 0.1.0
ARCHIVE := $(DIST)/godot-cli-$(VERSION).tar.gz

help:
	@printf '%s\n' \
	  'make test       - run unittest + self-test' \
	  'make check      - compile and run tests' \
	  'make smoke      - test the CLI in a temporary project' \
	  'make export     - create $(ARCHIVE)' \
	  'make install    - install as $(PREFIX)/bin/$(BIN)' \
	  'make uninstall  - remove $(PREFIX)/bin/$(BIN)' \
	  'make clean      - remove caches and dist'

test:
	python3 -m unittest -v
	python3 gd.py self-test

self-test:
	python3 gd.py self-test

check: test
	python3 -m compileall -q gd.py godot_cli test_gd.py

smoke:
	python3 -c 'import subprocess, sys, tempfile; from pathlib import Path; cli=Path("gd.py").resolve(); d=tempfile.TemporaryDirectory(); cmds=[["project","init","Demo"],["scene","create","Main"],["node","add","Main","Player","--type","CharacterBody2D"],["script","create","player.gd","--extends","CharacterBody2D"],["script","attach","Main","Player","player.gd"],["check"],["tree","Main"]]; [subprocess.run([sys.executable, cli, *cmd], cwd=d.name, check=True) for cmd in cmds]'

export: check
	mkdir -p $(DIST)
	tar --exclude='$(DIST)' --exclude='__pycache__' --exclude='.pytest_cache' --exclude='.ruff_cache' -czf $(ARCHIVE) gd.py godot_cli README.md Makefile test_gd.py .gitignore
	@printf 'exported: %s\n' '$(ARCHIVE)'

install:
	install -d $(PREFIX)/bin $(PREFIX)/lib/godot-cli
	cp -R godot_cli $(PREFIX)/lib/godot-cli/
	install -m 755 gd.py $(PREFIX)/lib/godot-cli/gd.py
	printf '%s\n' '#!/bin/sh' 'exec python3 "$(PREFIX)/lib/godot-cli/gd.py" "$$@"' > $(PREFIX)/bin/$(BIN)
	chmod +x $(PREFIX)/bin/$(BIN)
	@printf 'installed: %s\n' '$(PREFIX)/bin/$(BIN)'

uninstall:
	rm -f $(PREFIX)/bin/$(BIN)
	rm -rf $(PREFIX)/lib/godot-cli

clean:
	rm -rf $(DIST) __pycache__ .pytest_cache .ruff_cache
