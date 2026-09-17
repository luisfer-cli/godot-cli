from pathlib import Path

pages = {
    "index.html": ("Introduction", """
<h1>godot-cli documentation</h1>
<p class='lead'>godot-cli is a terminal-first workflow for Godot 4. It helps you create, inspect, edit, check, run, and export Godot projects without opening the Godot editor for repetitive tasks.</p>
<div class='admonition note'><p><strong>Philosophy:</strong> use the CLI for repeatable project edits, use Neovim + LSP for rich text editing, and use Godot for visual or engine-specific work.</p></div>
<h2>What you can do</h2>
<div class='cards'>
  <a class='card' href='getting-started.html'><h3>Start a project</h3><p>Create a project, scene, player node, input action, and run it.</p></a>
  <a class='card' href='commands.html'><h3>Command reference</h3><p>Every command grouped by project, scene, node, script, map, and export.</p></a>
  <a class='card' href='maps.html'><h3>ASCII maps</h3><p>Edit simple 2D levels directly in the terminal.</p></a>
  <a class='card' href='godot-lsp.html'><h3>Godot Scene LSP</h3><p>Pair the CLI with completions for scenes, node paths, and resources.</p></a>
</div>
<h2>Godot in one minute</h2>
<p>Godot games are built from <strong>scenes</strong>. Scenes are trees of <strong>nodes</strong>. Nodes can have <strong>scripts</strong>. Files are referenced through <code>res://</code> paths. godot-cli edits those project files from your shell.</p>
<pre><code>gd project init MyGame
gd scene create Main --root Node2D
gd node add Main Player --type CharacterBody2D
gd script attach Main Player player.gd
gd check --godot
gd run</code></pre>
"""),
    "getting-started.html": ("Getting started", """
<h1>Getting started</h1>
<p class='lead'>This walkthrough creates a small Godot project using only shell commands.</p>
<h2>Install</h2>
<pre><code>git clone https://github.com/luisfer-cli/godot-cli.git
cd godot-cli
make install
export PATH="$HOME/.local/bin:$PATH"</code></pre>
<h2>Create a project</h2>
<pre><code>mkdir MyGame && cd MyGame
gd project init MyGame
gd scene create Main --root Node2D
gd scene main Main</code></pre>
<h2>Add a player</h2>
<pre><code>gd node add Main Player --type CharacterBody2D
gd script create player.gd --extends CharacterBody2D
gd script attach Main Player player.gd
gd input add jump Space</code></pre>
<h2>Create a level</h2>
<pre><code>gd map new Level1 24 14
gd map edit Level1
gd map compile Level1 LevelScene</code></pre>
<h2>Validate and run</h2>
<pre><code>gd check --godot
gd run</code></pre>
<div class='admonition tip'><p><strong>Tip:</strong> if your binary is not named <code>godot</code>, use <code>--godot /path/to/godot</code>.</p></div>
"""),
    "concepts.html": ("Godot concepts", """
<h1>Godot concepts for CLI users</h1>
<p class='lead'>You do not need to memorize the editor UI to understand how Godot projects are structured.</p>
<h2>Scenes</h2>
<p>A scene is a reusable tree of nodes, usually saved as a <code>.tscn</code> file. Common examples: <code>Main.tscn</code>, <code>Player.tscn</code>, <code>Enemy.tscn</code>, <code>UI.tscn</code>.</p>
<h2>Nodes</h2>
<p>Nodes are the building blocks. <code>Node2D</code> groups 2D nodes. <code>CharacterBody2D</code> is useful for controlled characters. <code>Sprite2D</code> displays textures. <code>CollisionShape2D</code> defines collision geometry.</p>
<h2>Scripts</h2>
<p>Scripts add behavior to nodes. A GDScript file usually begins with <code>extends SomeGodotClass</code>. Attach scripts with <code>gd script attach</code>.</p>
<h2>Resources and res:// paths</h2>
<p>Godot refers to project files with <code>res://</code>. Example: <code>res://player.gd</code>. The CLI normalizes paths when attaching scripts or setting project values.</p>
<h2>Where the CLI fits</h2>
<p>godot-cli changes text resources conservatively. It is not a visual scene editor. It is for repeatable operations you want in shell history, scripts, and automation.</p>
"""),
    "commands.html": ("Command reference", """
<h1>Command reference</h1>
<p class='lead'>Commands are intentionally boring and scriptable.</p>
<h2>Project</h2><pre><code>gd project init &lt;name&gt;
gd project info
gd project scaffold
gd project setting get &lt;section/key&gt;
gd project setting set &lt;section/key&gt; &lt;value&gt;</code></pre>
<h2>Scenes</h2><pre><code>gd scene create &lt;path&gt; [--root Node2D]
gd scene list
gd scene main &lt;scene&gt;
gd scene instance &lt;scene&gt; &lt;name&gt; &lt;packed.tscn&gt; [--parent .]
gd scene grep &lt;pattern&gt;
gd scene edit &lt;scene&gt;</code></pre>
<h2>Nodes</h2><pre><code>gd node add &lt;scene&gt; &lt;name&gt; [--type Node2D] [--parent .]
gd node list &lt;scene&gt;
gd node get &lt;scene&gt; &lt;node&gt; &lt;property&gt;
gd node set &lt;scene&gt; &lt;node&gt; &lt;property&gt; &lt;value&gt;
gd node duplicate &lt;scene&gt; &lt;node&gt; &lt;new_name&gt;
gd node rename &lt;scene&gt; &lt;node&gt; &lt;new_name&gt;
gd node move &lt;scene&gt; &lt;node&gt; &lt;new_parent&gt;
gd node find &lt;scene&gt; [--type T]
gd node remove &lt;scene&gt; &lt;node&gt;</code></pre>
<h2>Scripts and signals</h2><pre><code>gd script create &lt;path&gt; [--extends Node] [--template platformer2d]
gd script attach &lt;scene&gt; &lt;node&gt; &lt;script&gt;
gd script list
gd signal connect &lt;scene&gt; &lt;signal&gt; &lt;from_node&gt; &lt;to_node&gt; &lt;method&gt;
gd signal list &lt;scene&gt;</code></pre>
<h2>Spritesheets and assets</h2><pre><code>gd spriteframes from-sheet &lt;scene&gt; &lt;node&gt; &lt;image&gt; --anim &lt;name&gt; --frame WxH --count N|auto [--fps N] [--columns N] [--offset X,Y] [--out file.tres] [--append]
gd asset list
gd asset check</code></pre>
<h2>Gameplay builders</h2><pre><code>gd collision add &lt;scene&gt; &lt;node&gt; rectangle|circle|capsule &lt;size&gt;
gd camera add &lt;scene&gt; &lt;name&gt; [--parent .] [--current] [--zoom N]
gd audio add &lt;scene&gt; &lt;name&gt; &lt;file&gt; [--parent .]
gd group add|list|remove &lt;scene&gt; [node] [group]</code></pre>
<h2>Input and autoloads</h2><pre><code>gd input add &lt;action&gt; &lt;key&gt;
gd input preset platformer|topdown
gd input list
gd input remove &lt;action&gt;
gd autoload add &lt;name&gt; &lt;script&gt;
gd autoload list
gd autoload remove &lt;name&gt;</code></pre>
<h2>Templates, doctor, docs</h2><pre><code>gd template platformer|topdown|menu
gd doctor
gd docs &lt;GodotClass&gt; [--open]</code></pre>
<h2>Run, check, test, export</h2><pre><code>gd check [--godot [godot]]
gd test
gd export list
gd export run &lt;preset&gt; [output] [--godot godot]
gd run [--godot godot]
gd self-test</code></pre>
"""),
    "maps.html": ("ASCII maps", """
<h1>ASCII maps</h1>
<p class='lead'>ASCII maps are a quick way to sketch 2D levels without a visual TileMap editor.</p>
<h2>Format</h2>
<p><code>.</code> is empty. Every other character becomes a node when compiled.</p>
<pre><code>P#.
..#</code></pre>
<h2>Commands</h2>
<pre><code>gd map new Level1 16 9
gd map check Level1
gd map edit Level1
gd map compile Level1 LevelScene --tile-size 16</code></pre>
<h2>Legend</h2>
<p>Create <code>levels/map.legend</code> to map characters to Godot node types.</p>
<pre><code>[legend]
#=StaticBody2D
P=CharacterBody2D
C=Camera2D</code></pre>
<h2>Map editor keys</h2>
<table><tr><th>Key</th><th>Action</th></tr><tr><td><code>h/j/k/l</code></td><td>Move cursor</td></tr><tr><td>printable key</td><td>Select tile</td></tr><tr><td><code>p</code> or space</td><td>Paint</td></tr><tr><td><code>u</code></td><td>Undo</td></tr><tr><td><code>:w</code>, <code>:q</code>, <code>:wq</code></td><td>Write/quit</td></tr></table>
<div class='admonition note'><p><strong>Why not native TileMap?</strong> Native TileMap editing needs TileSet and atlas metadata. The CLI uses ASCII maps until that data model is worth supporting.</p></div>
"""),
    "tui.html": ("TUI editors", """
<h1>TUI editors</h1>
<p class='lead'>The TUIs are small terminal helpers with Vim-ish bindings. They are not full editor replacements.</p>
<h2>Scene browser</h2>
<pre><code>gd scene edit Main</code></pre>
<table><tr><th>Key</th><th>Action</th></tr><tr><td><code>j/k</code></td><td>Move through nodes</td></tr><tr><td><code>/</code></td><td>Search node path</td></tr><tr><td><code>?</code></td><td>Help</td></tr><tr><td><code>:w</code>, <code>:q</code>, <code>:wq</code></td><td>Write/quit</td></tr></table>
<h2>Map editor</h2>
<pre><code>gd map edit Level1</code></pre>
<p>Use this for quick ASCII map edits. Compile the map back into a scene with <code>gd map compile</code>.</p>
"""),
    "godot-integration.html": ("Godot integration", """
<h1>Godot integration</h1>
<p class='lead'>The CLI delegates engine work to the real Godot binary.</p>
<h2>Run</h2><pre><code>gd run
gd run --godot /opt/Godot_v4/godot</code></pre>
<h2>Headless check</h2><pre><code>gd check --godot</code></pre>
<h2>Exports</h2><pre><code>gd export list
gd export run Linux build/game.x86_64</code></pre>
<h2>Tests</h2><p>Configure a test command in <code>project.godot</code>.</p><pre><code>[gd]
test_command=godot --headless --path . --script res://test_runner.gd</code></pre><pre><code>gd test</code></pre>
"""),
    "godot-lsp.html": ("Godot Scene LSP", """
<h1>Godot Scene LSP</h1>
<p class='lead'>Pair godot-cli with <a href='https://github.com/luisfer-cli/godot-scene-lsp'>godot-scene-lsp</a> for rich Neovim editing.</p>
<p>The LSP is a minimal dependency-free server focused on scenes, nodes, resources, and GDScript completions while working without opening Godot.</p>
<h2>Features</h2>
<ul><li>Scene <code>.tscn</code> completions.</li><li>Node path completions like <code>Player/Sprite</code>.</li><li><code>res://...</code> resource completions for scripts, scenes, textures, audio, and project files.</li><li>Godot classes, keywords, callbacks, and project symbols.</li><li>Document symbols, definitions, references, hover, and simple diagnostics.</li></ul>
<h2>Install</h2><pre><code>git clone https://github.com/luisfer-cli/godot-scene-lsp.git
cd godot-scene-lsp
make install</code></pre>
<h2>Neovim</h2><pre><code>vim.lsp.start({
  name = 'godot-scene-lsp',
  cmd = { 'godot-scene-lsp', '--stdio' },
  root_dir = vim.fs.root(0, { 'project.godot', '.git' }),
})</code></pre>
<h2>Recommended workflow</h2><p>Use godot-cli for repeatable structural changes. Use Neovim + godot-scene-lsp for writing scripts and editing scenes/resources. Use Godot for visual authoring when the terminal stops being the fastest tool.</p>
"""),
    "gameplay.html": ("Gameplay commands", """
<h1>Gameplay commands</h1>
<p class='lead'>High-value scene building blocks without opening the editor.</p>
<h2>Instance a scene</h2><pre><code>gd scene instance Main Mob enemy.tscn --parent Enemies</code></pre>
<p>Adds a <code>PackedScene</code> external resource and a node with <code>instance=ExtResource(...)</code>.</p>
<h2>Collisions</h2><pre><code>gd collision add Main Player rectangle 16x24
# circle: radius, capsule: radius,height
gd collision add Main Aura circle 32</code></pre>
<p>Creates the <code>RectangleShape2D</code>/<code>CircleShape2D</code>/<code>CapsuleShape2D</code> sub-resource and a <code>CollisionShape2D</code> child node. Polygons stay in Neovim/Godot.</p>
<h2>Camera and audio</h2><pre><code>gd camera add Main Camera --parent Player --current --zoom 2
gd audio add Main Jump assets/jump.wav --parent Player</code></pre>
<h2>Groups and signals</h2><pre><code>gd group add Main Player enemies
gd group list Main
gd group remove Main Player enemies
gd signal connect Main body_entered Area Body _hit
gd signal list Main</code></pre>
<h2>Spritesheets</h2><pre><code>gd node add Main PlayerAnim --type AnimatedSprite2D --parent Player
gd spriteframes from-sheet Main PlayerAnim assets/player.png \
  --anim walk --frame 16x16 --count auto
gd spriteframes from-sheet Main PlayerAnim assets/player.png \
  --anim idle --frame 16x16 --count 4 --append</code></pre>
<p>Generates a <code>SpriteFrames</code> <code>.tres</code> with one <code>AtlasTexture</code> per frame and assigns it to the node. <code>--count auto</code> derives rows×columns from the real PNG size (clip warning if leftover pixels); <code>--append</code> adds a second animation to the same resource without id collisions. Then play from script:</p>
<pre><code>$PlayerAnim.play("walk")</code></pre>
<h2>Reorganizing scenes</h2><pre><code>gd node move Main Player HUD          # reparent (descendants + connections follow)
gd node find Main --type Sprite2D
gd scene grep position                 # escena:nodo:linea across all .tscn</code></pre>
<h2>Assets</h2><pre><code>gd asset list
gd asset check</code></pre><p>Finds every <code>res://</code> reference in <code>.tscn</code>/<code>.tres</code>/<code>.gd</code>/<code>project.godot</code> and reports broken ones.</p>
"""),
    "productivity.html": ("Templates & doctor", """
<h1>Templates, presets and doctor</h1>
<h2>Minimal playable game</h2><pre><code>mkdir MyGame && cd MyGame
gd template platformer
gd run</code></pre>
<p><code>platformer</code>, <code>topdown</code> and <code>menu</code> generate a small playable project: main scene, player with collision+camera, starter script, input actions and folder scaffold. Everything stays plain files you can edit.</p>
<h2>Script templates</h2><pre><code>gd script create player.gd --template platformer2d
gd script create game_state.gd --template autoload-state</code></pre>
<h2>Input presets</h2><pre><code>gd input preset platformer   # move_left A, move_right D, jump Space
gd input preset topdown      # WASD</code></pre>
<h2>Scaffold</h2><pre><code>gd project scaffold</code></pre><p>Creates <code>scenes/ scripts/ assets/ levels/</code>.</p>
<h2>Doctor</h2><pre><code>gd doctor</code></pre><p>Checks <code>project.godot</code>, Godot in <code>PATH</code>, main scene, missing <code>res://</code> resources, export presets, and reminds you about <a href='godot-lsp.html'>Godot Scene LSP</a>. Exit code 1 when something is broken.</p>
<h2>Docs lookup</h2><pre><code>gd docs CharacterBody2D
gd docs AnimatedSprite2D --open</code></pre><p>Prints (or opens) the official Godot class docs URL.</p>
"""),
    "recipes.html": ("Recipes", """
<h1>Recipes</h1>
<h2>Create a player scene</h2><pre><code>gd scene create Player --root CharacterBody2D
gd node add Player Sprite --type Sprite2D
gd node add Player Collision --type CollisionShape2D
gd script create player.gd --extends CharacterBody2D
gd script attach Player Player player.gd</code></pre>
<h2>Create a UI scene</h2><pre><code>gd scene create UI --root Control
gd node add UI Menu --type VBoxContainer
gd node add UI StartButton --type Button --parent Menu</code></pre>
<h2>Prepare export</h2><pre><code>gd check --godot
gd export list
gd export run Linux dist/my-game.x86_64</code></pre>
<h2>Use Neovim for deep edits</h2><pre><code>nvim Main.tscn player.gd</code></pre><p>With godot-scene-lsp running, you get project-aware completions for node paths and <code>res://</code> resources.</p>
"""),
    "limits.html": ("Known limits", """
<h1>Known limits</h1>
<ul><li><code>.tscn</code> support is conservative and line-preserving, not a full Godot resource parser.</li><li>Native TileMap/TileSet editing is not implemented; use ASCII maps or Neovim/Godot for full tileset metadata.</li><li><code>collision add</code> covers rectangle/circle/capsule; polygon shapes stay in the editor.</li><li>The curses TUIs are intentionally small helpers.</li><li>Input mapping supports basic keys first.</li><li>On Windows, curses may require a compatible terminal environment.</li></ul>
<h2>Design rule</h2><p>godot-cli should stay boring and scriptable. If a feature starts becoming a clone of Godot's editor, it probably belongs in Godot or the LSP instead.</p>
"""),
}

nav = [
    ("index.html", "Introduction"), ("getting-started.html", "Getting started"), ("concepts.html", "Godot concepts"),
    ("commands.html", "Command reference"), ("maps.html", "ASCII maps"), ("tui.html", "TUI editors"),
    ("godot-integration.html", "Godot integration"), ("godot-lsp.html", "Godot Scene LSP"),
    ("gameplay.html", "Gameplay commands"), ("productivity.html", "Templates & doctor"),
    ("recipes.html", "Recipes"), ("limits.html", "Known limits"),
]

page_index = [dict(url=url, title=title, text=body.replace("'", "")) for url, (title, body) in pages.items()]


def prev_next(current: str) -> str:
    urls = [u for u, _ in nav]
    titles = dict(nav)
    i = urls.index(current)
    prev = f"<a href='{urls[i - 1]}'>← {titles[urls[i - 1]]}</a>" if i else "<span></span>"
    nxt = f"<a href='{urls[i + 1]}'>{titles[urls[i + 1]]} →</a>" if i + 1 < len(urls) else "<span></span>"
    return prev + nxt


for url, (title, body) in pages.items():
    links = "\n".join(f"<a {'class=active' if u == url else ''} href='{u}'>{t}</a>" for u, t in nav)
    Path(url).write_text(f"""<!doctype html>
<html lang='en'>
<head>
  <meta charset='utf-8'>
  <meta name='viewport' content='width=device-width, initial-scale=1'>
  <title>{title} — godot-cli docs</title>
  <meta name='description' content='godot-cli documentation'>
  <link rel='stylesheet' href='styles.css'>
</head>
<body>
  <header class='topbar'><button id='menuButton' aria-label='Toggle navigation'>☰</button><a class='topbrand' href='index.html'><img src='assets/godot-documentation-logo.svg' alt='' class='top-logo'> godot-cli docs</a><a href='https://github.com/luisfer-cli/godot-cli'>GitHub</a></header>
  <aside class='sidebar' id='sidebar'>
    <a class='brand' href='index.html'><img src='assets/godot-documentation-logo.svg' alt='Godot logo'> <span>godot-cli</span></a>
    <label class='search-label' for='search'>Search</label>
    <input id='search' type='search' placeholder='Search docs...' autocomplete='off'>
    <div id='searchResults' class='search-results' hidden></div>
    <nav>{links}<a href='https://github.com/luisfer-cli/godot-scene-lsp'>Godot Scene LSP ↗</a></nav>
  </aside>
  <main class='content'>
    <div class='breadcrumbs'><a href='index.html'>Docs</a> / <span>{title}</span></div>
    <article>{body}</article>
    <nav class='pager'>{prev_next(url)}</nav>
  </main>
  <script>window.SEARCH_INDEX = {page_index!r};</script>
  <script src='docs.js'></script>
</body>
</html>
""", encoding="utf-8")
