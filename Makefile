.PHONY: help test self-test check smoke export install uninstall clean

PREFIX ?= $(HOME)/.local
BIN ?= gd
DIST ?= dist
VERSION ?= 0.1.0
ARCHIVE := $(DIST)/godot-cli-$(VERSION).tar.gz

help:
	@printf '%s\n' \
	  'make test       - corre unittest + self-test' \
	  'make check      - compila y corre tests' \
	  'make smoke      - prueba el CLI en un proyecto temporal' \
	  'make export     - genera $(ARCHIVE)' \
	  'make install    - instala como $(PREFIX)/bin/$(BIN)' \
	  'make uninstall  - borra $(PREFIX)/bin/$(BIN)' \
	  'make clean      - borra caches y dist'

test:
	python3 -m unittest -v
	python3 gd.py self-test

self-test:
	python3 gd.py self-test

check: test
	python3 -m compileall -q gd.py test_gd.py

smoke:
	python3 -c 'import subprocess, sys, tempfile; from pathlib import Path; cli=Path("gd.py").resolve(); d=tempfile.TemporaryDirectory(); cmds=[["project","init","Demo"],["scene","create","Main"],["node","add","Main","Player","--type","CharacterBody2D"],["script","create","player.gd","--extends","CharacterBody2D"],["script","attach","Main","Player","player.gd"],["check"],["tree","Main"]]; [subprocess.run([sys.executable, cli, *cmd], cwd=d.name, check=True) for cmd in cmds]'

export: check
	mkdir -p $(DIST)
	tar --exclude='$(DIST)' --exclude='__pycache__' --exclude='.pytest_cache' --exclude='.ruff_cache' -czf $(ARCHIVE) gd.py README.md Makefile test_gd.py .gitignore
	@printf 'exportado: %s\n' '$(ARCHIVE)'

install:
	install -d $(PREFIX)/bin
	install -m 755 gd.py $(PREFIX)/bin/$(BIN)
	@printf 'instalado: %s\n' '$(PREFIX)/bin/$(BIN)'

uninstall:
	rm -f $(PREFIX)/bin/$(BIN)

clean:
	rm -rf $(DIST) __pycache__ .pytest_cache .ruff_cache
