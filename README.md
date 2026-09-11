# godot-cli

CLI mínimo para tocar proyectos Godot 4 desde terminal sin abrir el editor para tareas repetitivas.

## Uso

```bash
chmod +x gd.py
./gd.py project init MiJuego
./gd.py scene create Main --root Node2D
./gd.py node add Main Player --type CharacterBody2D
./gd.py node add Main Sprite --type Sprite2D --parent Player
./gd.py script create player.gd --extends CharacterBody2D
./gd.py script attach Main Player player.gd
./gd.py signal connect Main ready Player Player _on_ready
./gd.py tree Main
./gd.py check
./gd.py run
```

## Comandos

- `project init <nombre>`: crea `project.godot` mínimo.
- `project info`: muestra nombre y escena principal desde `project.godot`.
- `scene create <ruta> [--root Node2D]`: crea una escena `.tscn` simple.
- `scene list`: lista escenas.
- `node add <escena> <nombre> [--type Node2D] [--parent .]`: añade un nodo.
- `node list <escena>`: lista nodos.
- `node rename <escena> <nodo|ruta> <nuevo_nombre>`: renombra y actualiza hijos/señales.
- `node remove <escena> <nodo|ruta>`: borra un nodo, hijos y señales asociadas.
- `script create <ruta> [--extends Node]`: crea un `.gd` básico.
- `script attach <escena> <nodo|ruta> <script>`: adjunta un script a un nodo.
- `script list`: lista scripts.
- `signal connect <escena> <signal> <from_node> <to_node> <method>`: conecta señales.
- `tree <escena>`: imprime el árbol de nodos.
- `check`: valida padres y scripts faltantes.
- `run [--godot godot]`: ejecuta Godot en el proyecto actual.

## Make

```bash
make test      # unittest + self-test
make check     # test + compileall
make smoke     # prueba CLI real en proyecto temporal
make export    # crea dist/godot-cli-0.1.0.tar.gz
make install   # instala como ~/.local/bin/gd
```

Para exportarlo:

```bash
make export
```

Para instalarlo localmente:

```bash
make install
# luego usa: gd scene create Main
```

Sin LSP por ahora: eso queda como proyecto separado cuando este CLI ya sea útil.
