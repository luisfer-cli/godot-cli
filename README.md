# godot-cli

Tiny terminal-first CLI for Godot 4 projects. It handles the repetitive project/scene/script/map/export work from the shell, while complex `.tscn`/`.tres` editing stays in Neovim with your Godot LSP or in Godot itself when needed.

## Terminal-first workflow

```bash
chmod +x gd.py
./gd.py project init MyGame
./gd.py scene create Main --root Node2D
./gd.py scene main Main
./gd.py node add Main Player --type CharacterBody2D
./gd.py script create player.gd --extends CharacterBody2D
./gd.py script attach Main Player player.gd
./gd.py input add jump Space
./gd.py map new Level1 32 18
./gd.py map edit Level1
./gd.py map compile Level1 LevelScene
./gd.py check --godot
./gd.py run
```

Use `godot --path .` / `gd run` to execute. Use Neovim + your `.tscn` LSP for deep scene/resource edits; this CLI deliberately avoids cloning Godot's full editor.

## Commands

- `project init <name>`: creates a minimal `project.godot`.
- `project info`: prints project name and main scene.
- `project setting get|set <section/key> [value]`: reads/writes `project.godot` settings.
- `scene create|list|main|edit`: creates/lists/sets/inspects scenes.
- `node add|list|get|set|duplicate|rename|remove`: manages simple scene nodes/properties.
- `script create|attach|list`: creates and attaches GDScript files.
- `signal connect`: adds a signal connection.
- `input add|list|remove`: manages simple input actions.
- `autoload add|list|remove`: manages autoload singletons.
- `map new|list|check|edit|compile`: edits ASCII maps and compiles them to placeholder scene nodes.
- `tilemap edit <scene> <node>`: points to the ASCII map fallback; native TileMap editing is not implemented yet.
- `tree <scene>`: prints the node tree.
- `check [--godot [godot]]`: validates parents/scripts, optionally with Godot headless.
- `test`: runs `[gd] test_command` from `project.godot`.
- `export list`: lists names from `export_presets.cfg`.
- `export run <preset> [output] [--godot godot]`: runs a Godot export preset.
- `run [--godot godot]`: runs Godot in the current project.

## TUI

```bash
./gd.py scene edit Main
./gd.py map edit Level1
```

Scene TUI: `j/k` move, `/` search, `?` help, `:w`, `:q`, `:wq`.

Map TUI: `h/j/k/l` move, printable key selects tile, `p`/space paints, `u` undo, `:w`, `:q`, `:wq`.

## ASCII maps

`levels/*.map` files are plain grids. `.` is empty; other characters become nodes when compiled:

```text
P#.
..#
```

Optional `levels/map.legend` maps characters to Godot node types:

```ini
[legend]
#=StaticBody2D
P=CharacterBody2D
```

```bash
./gd.py map new Level1 16 9
./gd.py map check Level1
./gd.py map edit Level1
./gd.py map compile Level1 LevelScene --tile-size 16
```

## Known limits

- `.tscn` support is conservative and line-preserving, not a full Godot resource parser.
- Native TileMap/TileSet editing is intentionally skipped until tileset/atlas metadata is available; ASCII maps are the terminal-first path.
- Curses TUIs are small browsers/editors, not replacements for Neovim/Godot.
- Input mapping supports basic keys first.

## Make

```bash
make test      # unittest + self-test
make check     # tests + compileall
make smoke     # real CLI smoke test in a temporary project
make export    # creates dist/godot-cli-0.1.0.tar.gz
make install   # installs as ~/.local/bin/gd
```

## Releases

Pushing a tag like `v0.1.0` runs the release workflow and uploads the tarball from `make export` to GitHub Releases.
