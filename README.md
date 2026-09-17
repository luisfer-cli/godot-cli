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

Or start from a ready-made minimal game:

```bash
mkdir MyGame && cd MyGame
gd template platformer
gd run
```

Full documentation: [luisfer-cli.github.io/godot-cli](https://luisfer-cli.github.io/godot-cli/)

## Commands

- `project init <name>`: creates a minimal `project.godot`.
- `project scaffold`: creates `scenes/`, `scripts/`, `assets/`, `levels/`.
- `project info`: prints project name and main scene.
- `project setting get|set <section/key> [value]`: reads/writes `project.godot` settings.
- `scene create|list|main|edit|instance`: creates/lists/sets/inspects scenes; `instance` embeds one scene into another.
- `node add|list|get|set|duplicate|rename|remove`: manages simple scene nodes/properties.
- `script create|attach|list`: creates and attaches GDScript files; `create --template platformer2d|topdown2d|autoload-state|menu` writes a small starter script.
- `spriteframes from-sheet`: creates SpriteFrames animations from a spritesheet and assigns them to AnimatedSprite2D.
- `asset list|check`: lists `res://` references and reports missing files.
- `collision add <scene> <node> rectangle|circle|capsule <size>`: adds a CollisionShape2D child with the right shape resource.
- `camera add <scene> <name> [--parent .] [--current] [--zoom N]`: adds a Camera2D.
- `audio add <scene> <name> <file> [--parent .]`: adds an AudioStreamPlayer referencing an audio file.
- `group add|list|remove <scene> [node] [group]`: manages node groups.
- `signal connect`: adds a signal connection. `signal list <scene>` shows existing ones.
- `input add|list|remove`: manages simple input actions. `input preset platformer|topdown` adds a common set at once.
- `autoload add|list|remove`: manages autoload singletons.
- `map new|list|check|edit|compile`: edits ASCII maps and compiles them to placeholder scene nodes.
- `tilemap edit <scene> <node>`: points to the ASCII map fallback; native TileMap editing is not implemented yet.
- `tree <scene>`: prints the node tree.
- `check [--godot [godot]]`: validates parents/scripts, optionally with Godot headless.
- `test`: runs `[gd] test_command` from `project.godot`.
- `export list`: lists names from `export_presets.cfg`.
- `export run <preset> [output] [--godot godot]`: runs a Godot export preset.
- `run [--godot godot]`: runs Godot in the current project.
- `template platformer|topdown|menu`: generates a minimal playable project in the current directory.
- `doctor`: reports project health (Godot binary, main scene, missing resources, export presets, LSP tip).
- `docs <GodotClass>`: prints the official docs URL (`--open` launches the browser).

## TUI

```bash
./gd.py scene edit Main
./gd.py map edit Level1
```

Scene TUI: `j/k` move, `/` search, `?` help, `:w`, `:q`, `:wq`.

Map TUI: `h/j/k/l` move, printable key selects tile, `p`/space paints, `u` undo, `:w`, `:q`, `:wq`.

## Spritesheets

Create a `SpriteFrames` resource from a spritesheet and assign it to an `AnimatedSprite2D` node:

```bash
./gd.py node add Main PlayerAnim --type AnimatedSprite2D --parent Player
./gd.py spriteframes from-sheet Main PlayerAnim assets/player.png \
  --anim walk --frame 16x16 --count 6 --fps 10 --columns 3
```

Optional flags: `--offset X,Y` for the first frame, `--out path.tres` for the generated resource.

Check referenced assets:

```bash
./gd.py asset list
./gd.py asset check
```

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

## Neovim + Godot Scene LSP

For serious editing of `.tscn`, `.tres` and GDScript, pair this CLI with [godot-scene-lsp](https://github.com/luisfer-cli/godot-scene-lsp): completions for scenes, node paths (`Player/Sprite`), `res://` resources, Godot classes, and project symbols.

```lua
vim.lsp.start({
  name = 'godot-scene-lsp',
  cmd = { 'godot-scene-lsp', '--stdio' },
  root_dir = vim.fs.root(0, { 'project.godot', '.git' }),
})
```

Division of labor: godot-cli for repeatable structural edits, Neovim + LSP for text editing, Godot only for visual/engine-specific work.

## Known limits

- `.tscn` support is conservative and line-preserving, not a full Godot resource parser.
- Native TileMap/TileSet editing is intentionally skipped until tileset/atlas metadata is available; ASCII maps are the terminal-first path.
- Curses TUIs are small browsers/editors, not replacements for Neovim/Godot.
- Input mapping supports basic keys first.
- `spriteframes from-sheet` writes one animation per generated `.tres`; merge/add more animations in Neovim/Godot.

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
