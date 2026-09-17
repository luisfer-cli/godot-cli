#!/usr/bin/env python3
"""Tiny Godot CLI: edit simple Godot 4 .tscn/.gd files without opening the editor."""

from __future__ import annotations

import argparse
import configparser
import os
import re
import shlex
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

HEADER_RE = re.compile(r"^\[([A-Za-z_]+)(?:\s+(.*))?\]$")
ATTR_RE = re.compile(r'(\w+)=(?:"([^"]*)"|([^\s]+))')
PROP_RE = re.compile(r"^([^=]+?)\s*=\s*(.*)$")
RES_RE = re.compile(r"res://[^\s\"'\])},]+")


def res(path: str | Path) -> str:
    p = Path(path).as_posix()
    return p if p.startswith("res://") else "res://" + p.lstrip("/")


SCRIPT_TEMPLATES = {
    "platformer2d": """extends CharacterBody2D

const SPEED := 120.0
const JUMP_VELOCITY := -300.0

func _physics_process(delta: float) -> void:
	if not is_on_floor():
		velocity += get_gravity() * delta
	if Input.is_action_just_pressed("jump") and is_on_floor():
		velocity.y = JUMP_VELOCITY
	velocity.x = Input.get_axis("move_left", "move_right") * SPEED
	move_and_slide()
""",
    "topdown2d": """extends CharacterBody2D

const SPEED := 150.0

func _physics_process(_delta: float) -> void:
	velocity = Input.get_vector("move_left", "move_right", "move_up", "move_down") * SPEED
	move_and_slide()
""",
    "autoload-state": """extends Node

var score := 0
var lives := 3

func add_score(points: int) -> void:
	score += points
""",
    "menu": """extends Control

func _ready() -> void:
	$Menu/Start.pressed.connect(_on_start)

func _on_start() -> void:
	print("start")
""",
}

INPUT_PRESETS = {
    "platformer": {"move_left": "A", "move_right": "D", "jump": "Space"},
    "topdown": {
        "move_up": "W",
        "move_down": "S",
        "move_left": "A",
        "move_right": "D",
    },
}


def local(path: str) -> Path:
    return Path(path[6:] if path.startswith("res://") else path)


def scene_path(path: str) -> Path:
    p = Path(path)
    return p if p.suffix else p.with_suffix(".tscn")


def read_lines(path: Path) -> list[str]:
    if not path.exists():
        raise SystemExit(f"not found: {path}")
    return path.read_text(encoding="utf-8").splitlines()


def write_lines(path: Path, lines: list[str]) -> None:
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


@dataclass
class SceneBlock:
    kind: str
    attrs: dict[str, str]
    props: dict[str, str]
    start: int
    end: int


def parse_attrs(text: str) -> dict[str, str]:
    return {
        m.group(1): m.group(2) if m.group(2) is not None else m.group(3)
        for m in ATTR_RE.finditer(text)
    }


def parse_scene(lines: list[str]) -> list[SceneBlock]:
    headers: list[tuple[int, str, dict[str, str]]] = []
    for i, line in enumerate(lines):
        if m := HEADER_RE.match(line):
            headers.append((i, m.group(1), parse_attrs(m.group(2) or "")))
    blocks: list[SceneBlock] = []
    for pos, (start, kind, attrs) in enumerate(headers):
        end = headers[pos + 1][0] if pos + 1 < len(headers) else len(lines)
        props = {}
        for line in lines[start + 1 : end]:
            if m := PROP_RE.match(line.strip()):
                props[m.group(1)] = m.group(2)
        blocks.append(SceneBlock(kind, attrs, props, start, end))
    return blocks


def nodes(lines: list[str]) -> list[dict[str, str]]:
    out = []
    for block in parse_scene(lines):
        if block.kind == "node":
            out.append(
                {
                    "line": str(block.start),
                    "name": block.attrs.get("name", ""),
                    "type": block.attrs.get("type", ""),
                    "parent": block.attrs.get("parent", ""),
                }
            )
    return out


def node_full_path(node: dict[str, str]) -> str:
    parent = node["parent"]
    return node["name"] if not parent or parent == "." else f"{parent}/{node['name']}"


def find_node(lines: list[str], wanted: str) -> dict[str, str]:
    hit = next(
        (n for n in nodes(lines) if n["name"] == wanted or node_full_path(n) == wanted),
        None,
    )
    if not hit:
        raise SystemExit(f"node not found: {wanted}")
    return hit


def scene_tree_rows(lines: list[str]) -> list[tuple[str, str]]:
    ns = nodes(lines)
    by_parent: dict[str, list[dict[str, str]]] = {}
    for n in ns:
        by_parent.setdefault(n["parent"], []).append(n)

    rows: list[tuple[str, str]] = []

    def walk(parent: str, depth: int = 0) -> None:
        for n in by_parent.get(parent, []):
            path = node_full_path(n)
            rows.append((path, f"{'  ' * depth}{n['name']} ({n['type']})"))
            walk(path, depth + 1)

    walk("")
    walk(".")
    return rows


def node_props(lines: list[str], node: str) -> list[str]:
    hit = find_node(lines, node)
    start, end = node_block(lines, node_line(hit))
    return [
        line.strip() for line in lines[start + 1 : end] if PROP_RE.match(line.strip())
    ]


def node_line(node: dict[str, str]) -> int:
    try:
        return int(node["line"])
    except ValueError as exc:
        raise SystemExit("invalid scene: node line is not numeric") from exc


def node_block(lines: list[str], line_i: int) -> tuple[int, int]:
    end = next(
        (i for i in range(line_i + 1, len(lines)) if HEADER_RE.match(lines[i])),
        len(lines),
    )
    return line_i, end


def ext_resources(lines: list[str]) -> list[tuple[str, str]]:
    return [
        (b.attrs["path"], b.attrs["id"])
        for b in parse_scene(lines)
        if b.kind == "ext_resource"
        and b.attrs.get("type") == "Script"
        and "path" in b.attrs
        and "id" in b.attrs
    ]


def prop_line(lines: list[str], start: int, end: int, prop: str) -> int | None:
    for i in range(start + 1, end):
        if (m := PROP_RE.match(lines[i].strip())) and m.group(1) == prop:
            return i
    return None


def set_section_value(path: Path, section: str, key: str, value: str | None) -> None:
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    header = f"[{section}]"
    start = next((i for i, line in enumerate(lines) if line == header), None)
    if start is None:
        if lines and lines[-1] != "":
            lines.append("")
        lines += [header]
        start = len(lines) - 1
    end = next(
        (i for i in range(start + 1, len(lines)) if HEADER_RE.match(lines[i])),
        len(lines),
    )
    hit = next(
        (i for i in range(start + 1, end) if lines[i].split("=", 1)[0] == key),
        None,
    )
    if value is None:
        if hit is not None:
            del lines[hit]
    elif hit is None:
        lines.insert(end, f"{key}={value}")
    else:
        lines[hit] = f"{key}={value}"
    write_lines(path, lines)


def section_items(path: Path, section: str) -> dict[str, str]:
    if not path.exists():
        return {}
    lines = path.read_text(encoding="utf-8").splitlines()
    start = next((i for i, line in enumerate(lines) if line == f"[{section}]"), None)
    if start is None:
        return {}
    end = next(
        (i for i in range(start + 1, len(lines)) if HEADER_RE.match(lines[i])),
        len(lines),
    )
    return dict(line.split("=", 1) for line in lines[start + 1 : end] if "=" in line)


def key_event(name: str) -> str:
    codes = {"Space": 32, "Enter": 4194309, "Escape": 4194305}
    code = codes.get(name, ord(name.upper()) if len(name) == 1 else 0)
    return f'{{"deadzone":0.5,"events":[Object(InputEventKey,"keycode":{code})]}}'


GAME_TEMPLATES: dict[str, list[tuple[str, tuple]]] = {
    "platformer": [
        ("project_init", ("MyGame",)),
        ("scene_create", ("Main", "Node2D")),
        ("scene_main", ("Main",)),
        ("node_add", ("Main", "Player", "CharacterBody2D", ".")),
        ("collision_add", ("Main", "Player", "rectangle", "16x24")),
        ("camera_add", ("Main", "Camera", "Player", True, None)),
        ("script_create", ("scripts/player.gd", "platformer2d")),
        ("script_attach", ("Main", "Player", "scripts/player.gd")),
        ("input_preset", ("platformer",)),
        ("project_scaffold", ()),
    ],
    "topdown": [
        ("project_init", ("MyGame",)),
        ("scene_create", ("Main", "Node2D")),
        ("scene_main", ("Main",)),
        ("node_add", ("Main", "Player", "CharacterBody2D", ".")),
        ("collision_add", ("Main", "Player", "circle", "8")),
        ("camera_add", ("Main", "Camera", "Player", True, 2.0)),
        ("script_create", ("scripts/player.gd", "topdown2d")),
        ("script_attach", ("Main", "Player", "scripts/player.gd")),
        ("input_preset", ("topdown",)),
        ("project_scaffold", ()),
    ],
    "menu": [
        ("project_init", ("MyGame",)),
        ("scene_create", ("Main", "Control")),
        ("scene_main", ("Main",)),
        ("node_add", ("Main", "Menu", "VBoxContainer", ".")),
        ("node_add", ("Main", "Start", "Button", "Menu")),
        ("script_create", ("scripts/menu.gd", "menu")),
        ("script_attach", ("Main", "Main", "scripts/menu.gd")),
        ("project_scaffold", ()),
    ],
}


def cmd_input_preset(args: argparse.Namespace) -> None:
    if args.name not in INPUT_PRESETS:
        raise SystemExit(f"unknown preset: {args.name}; use platformer|topdown")
    for action, key in INPUT_PRESETS[args.name].items():
        set_section_value(Path("project.godot"), "input", action, key_event(key))
        print(f"{action} -> {key}")


def cmd_project_scaffold(_: argparse.Namespace) -> None:
    for d in ("scenes", "scripts", "assets", "levels"):
        Path(d).mkdir(parents=True, exist_ok=True)
        print(d)


def cmd_template(args: argparse.Namespace) -> None:
    steps = GAME_TEMPLATES[args.name]
    for cmd, a in steps:
        if cmd == "project_init":
            cmd_project_init(argparse.Namespace(name=a[0], force=True))
        elif cmd == "scene_create":
            cmd_scene_create(argparse.Namespace(path=a[0], root=a[1], force=True))
        elif cmd == "scene_main":
            cmd_scene_main(argparse.Namespace(scene=a[0]))
        elif cmd == "node_add":
            cmd_node_add(
                argparse.Namespace(scene=a[0], name=a[1], type=a[2], parent=a[3])
            )
        elif cmd == "collision_add":
            cmd_collision_add(
                argparse.Namespace(scene=a[0], node=a[1], shape=a[2], size=a[3])
            )
        elif cmd == "camera_add":
            cmd_camera_add(
                argparse.Namespace(
                    scene=a[0], name=a[1], parent=a[2], current=a[3], zoom=a[4]
                )
            )
        elif cmd == "script_create":
            cmd_script_create(
                argparse.Namespace(path=a[0], template=a[1], extends=None, force=True)
            )
        elif cmd == "script_attach":
            cmd_script_attach(argparse.Namespace(scene=a[0], node=a[1], script=a[2]))
        elif cmd == "input_preset":
            cmd_input_preset(argparse.Namespace(name=a[0]))
        elif cmd == "project_scaffold":
            cmd_project_scaffold(argparse.Namespace())
    print(f"template {args.name} ready")


def cmd_doctor(_: argparse.Namespace) -> None:
    problems = 0
    if Path("project.godot").exists():
        print("ok: project.godot")
    else:
        print("error: project.godot missing (gd project init <name>)")
        problems += 1
    godot = shutil.which("godot")
    print(
        f"ok: godot found at {godot}"
        if godot
        else "warn: godot not in PATH; pass --godot or install it"
    )
    try:
        main = section_items(Path("project.godot"), "application").get("run/main_scene")
    except Exception:
        main = None
    if main:
        path = local(main.strip('"'))
        if path.exists():
            print(f"ok: main_scene {main}")
        else:
            print(f"error: main_scene does not exist: {main}")
            problems += 1
    else:
        print("warn: no main_scene set (gd scene main <scene>)")
    missing = [r for r in asset_refs() if not local(r).exists()]
    if missing:
        problems += 1
        print(f"error: {len(missing)} missing resource(s): " + ", ".join(missing))
    else:
        print("ok: resources")
    if Path("export_presets.cfg").exists():
        print(f"ok: {len(export_presets())} export preset(s)")
    else:
        print("warn: no export_presets.cfg")
    print(
        "tip: install godot-scene-lsp for .tscn/.gd completion in Neovim (github.com/luisfer-cli/godot-scene-lsp)"
    )
    if problems:
        raise SystemExit(1)


def cmd_docs(args: argparse.Namespace) -> None:
    url = (
        f"https://docs.godotengine.org/en/stable/classes/class_{args.cls.lower()}.html"
    )
    print(url)
    print(
        "tip: godot-scene-lsp completes Godot classes in Neovim (github.com/luisfer-cli/godot-scene-lsp)"
    )
    if getattr(args, "open", False):
        import webbrowser

        webbrowser.open(url)


def cmd_project_init(args: argparse.Namespace) -> None:
    path = Path("project.godot")
    if path.exists() and not args.force:
        raise SystemExit("already exists: project.godot")
    path.write_text(
        f'; Engine configuration file.\n\n[application]\nconfig/name="{args.name}"\n',
        encoding="utf-8",
    )
    print(path)


def cmd_project_info(_: argparse.Namespace) -> None:
    project = Path("project.godot")
    if not project.exists():
        print("No project.godot in this directory")
        return
    cfg = configparser.ConfigParser()
    cfg.read(project, encoding="utf-8")
    app = cfg["application"] if cfg.has_section("application") else {}
    print(app.get("config/name", Path.cwd().name).strip('"'))
    if "run/main_scene" in app:
        print(app["run/main_scene"].strip('"'))


def cmd_project_setting_get(args: argparse.Namespace) -> None:
    section, key = args.key.split("/", 1)
    try:
        print(section_items(Path("project.godot"), section)[key])
    except KeyError as exc:
        raise SystemExit(f"setting not found: {args.key}") from exc


def cmd_project_setting_set(args: argparse.Namespace) -> None:
    section, key = args.key.split("/", 1)
    set_section_value(Path("project.godot"), section, key, args.value)
    print(f"{args.key}={args.value}")


def cmd_scene_create(args: argparse.Namespace) -> None:
    path = scene_path(args.path)
    if path.exists() and not args.force:
        raise SystemExit(f"already exists: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f'[gd_scene format=3]\n\n[node name="{path.stem}" type="{args.root}"]\n',
        encoding="utf-8",
    )
    print(path)


def cmd_scene_list(_: argparse.Namespace) -> None:
    for path in sorted(Path(".").rglob("*.tscn")):
        print(path.as_posix())


def cmd_scene_main(args: argparse.Namespace) -> None:
    main = res(scene_path(args.scene))
    set_section_value(
        Path("project.godot"), "application", "run/main_scene", f'"{main}"'
    )
    print(main)


def cmd_node_add(args: argparse.Namespace) -> None:
    path = scene_path(args.scene)
    lines = read_lines(path)
    parent = (
        f' parent="{args.parent}"'
        if args.parent and args.parent != "."
        else ' parent="."'
    )
    lines += ["", f'[node name="{args.name}" type="{args.type}"{parent}]']
    write_lines(path, lines)
    print(f"{args.parent}/{args.name}" if args.parent not in ("", ".") else args.name)


def cmd_node_list(args: argparse.Namespace) -> None:
    for n in nodes(read_lines(scene_path(args.scene))):
        print(f"{node_full_path(n)} ({n['type']})")


def cmd_node_get(args: argparse.Namespace) -> None:
    lines = read_lines(scene_path(args.scene))
    node = find_node(lines, args.node)
    start, end = node_block(lines, node_line(node))
    line_i = prop_line(lines, start, end, args.property)
    if line_i is None:
        raise SystemExit(f"property not found: {args.property}")
    print(lines[line_i].split("=", 1)[1].strip())


def cmd_node_set(args: argparse.Namespace) -> None:
    path = scene_path(args.scene)
    lines = read_lines(path)
    node = find_node(lines, args.node)
    start, end = node_block(lines, node_line(node))
    line = f"{args.property} = {args.value}"
    if (line_i := prop_line(lines, start, end, args.property)) is None:
        lines.insert(end, line)
    else:
        lines[line_i] = line
    write_lines(path, lines)
    print(line)


def cmd_node_duplicate(args: argparse.Namespace) -> None:
    path = scene_path(args.scene)
    lines = read_lines(path)
    node = find_node(lines, args.node)
    start, end = node_block(lines, node_line(node))
    block = lines[start:end]
    block[0] = block[0].replace(f'name="{node["name"]}"', f'name="{args.new_name}"', 1)
    lines[end:end] = ["", *block]
    write_lines(path, lines)
    print(args.new_name)


def cmd_node_rename(args: argparse.Namespace) -> None:
    path = scene_path(args.scene)
    lines = read_lines(path)
    node = find_node(lines, args.node)
    old_path = node_full_path(node)
    new_path = args.new_name if "/" in old_path else args.new_name
    if "/" in old_path:
        new_path = old_path.rsplit("/", 1)[0] + "/" + args.new_name
    line_i = node_line(node)
    lines[line_i] = lines[line_i].replace(
        f'name="{node["name"]}"', f'name="{args.new_name}"', 1
    )
    for i, line in enumerate(lines):
        lines[i] = line.replace(f'parent="{old_path}"', f'parent="{new_path}"')
        lines[i] = lines[i].replace(f'from="{old_path}"', f'from="{new_path}"')
        lines[i] = lines[i].replace(f'to="{old_path}"', f'to="{new_path}"')
    write_lines(path, lines)
    print(f"{old_path} -> {new_path}")


def cmd_node_remove(args: argparse.Namespace) -> None:
    path = scene_path(args.scene)
    lines = read_lines(path)
    ns = nodes(lines)
    target = find_node(lines, args.node)
    target_path = node_full_path(target)
    doomed = {target_path}
    changed = True
    while changed:
        changed = False
        for n in ns:
            parent = n["parent"]
            if parent in doomed or any(parent.startswith(p + "/") for p in doomed):
                full = node_full_path(n)
                if full not in doomed:
                    doomed.add(full)
                    changed = True
    remove_lines: set[int] = set()
    for n in ns:
        if node_full_path(n) in doomed:
            start, end = node_block(lines, node_line(n))
            remove_lines.update(range(start, end))
    for i, line in enumerate(lines):
        if (m := HEADER_RE.match(line)) and m.group(1) == "connection":
            attrs = parse_attrs(m.group(2) or "")
            if attrs.get("from") in doomed or attrs.get("to") in doomed:
                remove_lines.add(i)
    write_lines(path, [line for i, line in enumerate(lines) if i not in remove_lines])
    print("\n".join(sorted(doomed)))


def cmd_script_create(args: argparse.Namespace) -> None:
    path = Path(args.path)
    if path.exists() and not args.force:
        raise SystemExit(f"already exists: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    template = getattr(args, "template", None)
    if template:
        if template not in SCRIPT_TEMPLATES:
            raise SystemExit(f"unknown template: {template}")
        content = SCRIPT_TEMPLATES[template]
    else:
        content = f"extends {args.extends}\n\nfunc _ready() -> void:\n\tpass\n"
    path.write_text(content, encoding="utf-8")
    print(path)


def cmd_script_list(_: argparse.Namespace) -> None:
    for path in sorted(Path(".").rglob("*.gd")):
        print(path.as_posix())


def next_ext_id(lines: list[str]) -> str:
    return str(sum(1 for b in parse_scene(lines) if b.kind == "ext_resource") + 1)


def add_ext_resource(lines: list[str], rtype: str, path: str) -> str:
    existing = next(
        (
            b.attrs["id"]
            for b in parse_scene(lines)
            if b.kind == "ext_resource"
            and b.attrs.get("path") == path
            and "id" in b.attrs
        ),
        None,
    )
    if existing:
        return existing
    ext_id = next_ext_id(lines)
    insert_at = next(
        (i for i, line in enumerate(lines) if line.startswith("[node ")), len(lines)
    )
    lines.insert(
        insert_at, f'[ext_resource type="{rtype}" path="{path}" id="{ext_id}"]'
    )
    if insert_at + 1 < len(lines) and lines[insert_at + 1] != "":
        lines.insert(insert_at + 1, "")
    return ext_id


def fix_load_steps(lines: list[str]) -> None:
    if not lines or not lines[0].startswith("[gd_scene"):
        return
    steps = (
        sum(1 for b in parse_scene(lines) if b.kind in ("ext_resource", "sub_resource"))
        + 1
    )
    if re.search(r"load_steps=\d+", lines[0]):
        lines[0] = re.sub(r"load_steps=\d+", f"load_steps={steps}", lines[0])
    else:
        lines[0] = lines[0][:-1] + f" load_steps={steps}]"


def node_parent_attr(lines: list[str], node: dict[str, str]) -> str:
    root = nodes(lines)[0]
    return (
        "."
        if node["name"] == root["name"] and not node["parent"]
        else node_full_path(node)
    )


def parse_size(text: str) -> tuple[int, int]:
    try:
        left, right = text.lower().split("x", 1)
        return int(left), int(right)
    except ValueError as exc:
        raise SystemExit(f"expected WxH, got: {text}") from exc


def parse_xy(text: str) -> tuple[int, int]:
    try:
        left, right = text.split(",", 1)
        return int(left), int(right)
    except ValueError as exc:
        raise SystemExit(f"expected X,Y, got: {text}") from exc


def write_spriteframes(
    path: Path,
    image: str,
    anim: str,
    frame: tuple[int, int],
    count: int,
    fps: float,
    offset: tuple[int, int],
    columns: int,
) -> None:
    if count < 1:
        raise SystemExit("count must be >= 1")
    if fps <= 0:
        raise SystemExit("fps must be > 0")
    width, height = frame
    ox, oy = offset
    lines = [
        f'[gd_resource type="SpriteFrames" load_steps={count + 2} format=3]',
        "",
        f'[ext_resource type="Texture2D" path="{res(image)}" id="1"]',
    ]
    frames = []
    for i in range(count):
        col = i % columns
        row = i // columns
        sub_id = f"AtlasTexture_{i + 1}"
        frames.append(sub_id)
        lines += [
            "",
            f'[sub_resource type="AtlasTexture" id="{sub_id}"]',
            'atlas = ExtResource("1")',
            f"region = Rect2({ox + col * width}, {oy + row * height}, {width}, {height})",
        ]
    frame_items = ", ".join(
        f'{{"duration": 1.0, "texture": SubResource("{sub_id}")}}' for sub_id in frames
    )
    lines += [
        "",
        "[resource]",
        f'animations = [{{"frames": [{frame_items}], "loop": true, "name": &"{anim}", "speed": {fps}}}]',
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    write_lines(path, lines)


def cmd_script_attach(args: argparse.Namespace) -> None:
    path = scene_path(args.scene)
    lines = read_lines(path)
    target = find_node(lines, args.node)
    script = res(args.script)
    existing = next(
        (
            b.attrs["id"]
            for b in parse_scene(lines)
            if b.kind == "ext_resource"
            and b.attrs.get("path") == script
            and "id" in b.attrs
        ),
        None,
    )
    ext_id = existing or next_ext_id(lines)

    inserted = 0
    if not existing:
        insert_at = next(
            (i for i, line in enumerate(lines) if line.startswith("[node ")), len(lines)
        )
        if lines[0].startswith("[gd_scene") and "load_steps=" not in lines[0]:
            lines[0] = lines[0][:-1] + " load_steps=2]"
        lines.insert(
            insert_at, f'[ext_resource type="Script" path="{script}" id="{ext_id}"]'
        )
        inserted = 1
        if insert_at + 1 < len(lines) and lines[insert_at + 1] != "":
            lines.insert(insert_at + 1, "")
            inserted = 2

    line_i = node_line(target) + inserted
    _, end = node_block(lines, line_i)
    prop = f'script = ExtResource("{ext_id}")'
    for i in range(line_i + 1, end):
        if lines[i].startswith("script = "):
            lines[i] = prop
            break
    else:
        lines.insert(line_i + 1, prop)
    write_lines(path, lines)
    print(f"{args.node} -> {script}")


def cmd_spriteframes_from_sheet(args: argparse.Namespace) -> None:
    scene = scene_path(args.scene)
    lines = read_lines(scene)
    target = find_node(lines, args.node)
    if target["type"] != "AnimatedSprite2D":
        raise SystemExit(f"node is not AnimatedSprite2D: {args.node}")
    image_path = local(args.image)
    if not image_path.exists():
        raise SystemExit(f"image not found: {args.image}")

    frame = parse_size(args.frame)
    offset = parse_xy(args.offset)
    out = (
        Path(args.out)
        if args.out
        else Path(args.image).with_suffix(".spriteframes.tres")
    )
    columns = args.columns or args.count
    write_spriteframes(
        out, args.image, args.anim, frame, args.count, args.fps, offset, columns
    )

    resource = res(out)
    existing = next(
        (
            b.attrs["id"]
            for b in parse_scene(lines)
            if b.kind == "ext_resource"
            and b.attrs.get("path") == resource
            and "id" in b.attrs
        ),
        None,
    )
    ext_id = existing or next_ext_id(lines)
    inserted = 0
    if not existing:
        insert_at = next(
            (i for i, line in enumerate(lines) if line.startswith("[node ")), len(lines)
        )
        lines.insert(
            insert_at,
            f'[ext_resource type="SpriteFrames" path="{resource}" id="{ext_id}"]',
        )
        inserted = 1
        if insert_at + 1 < len(lines) and lines[insert_at + 1] != "":
            lines.insert(insert_at + 1, "")
            inserted = 2

    line_i = node_line(target) + inserted
    _, end = node_block(lines, line_i)
    prop = f'sprite_frames = ExtResource("{ext_id}")'
    if (hit := prop_line(lines, line_i, end, "sprite_frames")) is None:
        lines.insert(end, prop)
    else:
        lines[hit] = prop
    write_lines(scene, lines)
    print(f"{args.node} -> {resource}:{args.anim}")


def project_files() -> list[Path]:
    suffixes = {".tscn", ".tres", ".gd", ".godot"}
    return [
        p
        for p in Path(".").rglob("*")
        if p.is_file()
        and p.suffix in suffixes
        and ".git" not in p.parts
        and "dist" not in p.parts
    ]


def asset_refs() -> list[str]:
    refs: set[str] = set()
    for path in project_files():
        refs.update(RES_RE.findall(path.read_text(encoding="utf-8", errors="ignore")))
    return sorted(refs)


def cmd_asset_list(_: argparse.Namespace) -> None:
    for ref in asset_refs():
        print(ref)


def cmd_asset_check(_: argparse.Namespace) -> None:
    missing = [ref for ref in asset_refs() if not local(ref).exists()]
    if missing:
        print("\n".join(f"missing: {ref}" for ref in missing))
        raise SystemExit(1)
    print("OK")


def cmd_scene_instance(args: argparse.Namespace) -> None:
    path = scene_path(args.scene)
    lines = read_lines(path)
    packed = local(res(args.packed))
    if not packed.exists():
        raise SystemExit(f"scene not found: {args.packed}")
    ext_id = add_ext_resource(lines, "PackedScene", res(args.packed))
    parent = args.parent or "."
    lines += [
        "",
        f'[node name="{args.name}" parent="{parent}" instance=ExtResource("{ext_id}")]',
    ]
    fix_load_steps(lines)
    write_lines(path, lines)
    print(f"{args.name} -> {res(args.packed)}")


def parse_float(text: str) -> float:
    try:
        return float(text)
    except ValueError as exc:
        raise SystemExit(f"expected number, got: {text}") from exc


def cmd_collision_add(args: argparse.Namespace) -> None:
    shapes = {
        "rectangle": "RectangleShape2D",
        "circle": "CircleShape2D",
        "capsule": "CapsuleShape2D",
    }
    if args.shape not in shapes:
        raise SystemExit(f"unknown shape: {args.shape}; use rectangle|circle|capsule")
    path = scene_path(args.scene)
    lines = read_lines(path)
    node = find_node(lines, args.node)
    kind = shapes[args.shape]
    if args.shape == "rectangle":
        w, h = parse_size(args.size)
        props = [f"size = Vector2({w}, {h})"]
    elif args.shape == "circle":
        props = [f"radius = {parse_float(args.size)}"]
    else:
        r, h = args.size.split(",", 1)
        props = [f"radius = {parse_float(r)}", f"height = {parse_float(h)}"]
    subs = sum(1 for b in parse_scene(lines) if b.kind == "sub_resource")
    sid = f"{kind}_{subs + 1}"
    insert_at = next(
        (i for i, line in enumerate(lines) if line.startswith("[node ")), len(lines)
    )
    lines[insert_at:insert_at] = [
        f'[sub_resource type="{kind}" id="{sid}"]',
        *props,
        "",
    ]
    parent = node_parent_attr(lines, node)
    count = sum(
        1
        for x in nodes(lines)
        if x["parent"] == parent and x["type"] == "CollisionShape2D"
    )
    name = "Collision" if count == 0 else f"Collision{count + 1}"
    lines += [
        "",
        f'[node name="{name}" type="CollisionShape2D" parent="{parent}"]',
        f'shape = SubResource("{sid}")',
    ]
    fix_load_steps(lines)
    write_lines(path, lines)
    print(f"{parent}/{name} {kind}")


def cmd_camera_add(args: argparse.Namespace) -> None:
    path = scene_path(args.scene)
    lines = read_lines(path)
    props = []
    if args.current:
        props.append("current = true")
    if args.zoom is not None:
        props.append(f"zoom = Vector2({args.zoom}, {args.zoom})")
    parent = args.parent or "."
    lines += [
        "",
        f'[node name="{args.name}" type="Camera2D" parent="{parent}"]',
        *props,
    ]
    write_lines(path, lines)
    print(f"{parent}/{args.name}")


def cmd_audio_add(args: argparse.Namespace) -> None:
    path = scene_path(args.scene)
    lines = read_lines(path)
    audio = local(res(args.file))
    if not audio.exists():
        raise SystemExit(f"audio file not found: {args.file}")
    ext_id = add_ext_resource(lines, "AudioStream", res(args.file))
    parent = args.parent or "."
    lines += [
        "",
        f'[node name="{args.name}" type="AudioStreamPlayer" parent="{parent}"]',
        f'stream = ExtResource("{ext_id}")',
    ]
    fix_load_steps(lines)
    write_lines(path, lines)
    print(f"{parent}/{args.name} -> {res(args.file)}")


def node_groups(lines: list[str], node: dict[str, str]) -> list[str]:
    line = lines[node_line(node)]
    m = re.search(r"groups=\[(.*?)\]", line)
    if not m:
        return []
    return [g.strip().strip('"') for g in m.group(1).split(",") if g.strip()]


def set_node_groups(lines: list[str], node: dict[str, str], groups: list[str]) -> None:
    i = node_line(node)
    head = re.sub(r"\s*groups=\[[^\]]*\]", "", lines[i][: lines[i].rindex("]")])
    if groups:
        head += " groups=[" + ", ".join(f'"{g}"' for g in groups) + "]"
    lines[i] = head + "]"


def cmd_group_add(args: argparse.Namespace) -> None:
    path = scene_path(args.scene)
    lines = read_lines(path)
    node = find_node(lines, args.node)
    groups = node_groups(lines, node)
    if args.group not in groups:
        groups.append(args.group)
        set_node_groups(lines, node, groups)
        write_lines(path, lines)
    print(f"{node_full_path(node)} -> {', '.join(groups)}")


def cmd_group_list(args: argparse.Namespace) -> None:
    lines = read_lines(scene_path(args.scene))
    if args.node:
        print(" ".join(node_groups(lines, find_node(lines, args.node))))
        return
    for n in nodes(lines):
        groups = node_groups(lines, n)
        if groups:
            print(f"{node_full_path(n)}: {', '.join(groups)}")


def cmd_group_remove(args: argparse.Namespace) -> None:
    path = scene_path(args.scene)
    lines = read_lines(path)
    node = find_node(lines, args.node)
    groups = [g for g in node_groups(lines, node) if g != args.group]
    set_node_groups(lines, node, groups)
    write_lines(path, lines)
    print(f"{node_full_path(node)} -> {', '.join(groups) or '(no groups)'}")


def cmd_signal_list(args: argparse.Namespace) -> None:
    for line in read_lines(scene_path(args.scene)):
        if (m := HEADER_RE.match(line)) and m.group(1) == "connection":
            a = parse_attrs(m.group(2) or "")
            print(f"{a['from']}.{a['signal']} -> {a['to']}:{a['method']}")


def cmd_signal_connect(args: argparse.Namespace) -> None:
    path = scene_path(args.scene)
    lines = read_lines(path)
    find_node(lines, args.from_node)
    find_node(lines, args.to_node)
    line = f'[connection signal="{args.signal}" from="{args.from_node}" to="{args.to_node}" method="{args.method}"]'
    if line not in lines:
        lines += ["", line]
        write_lines(path, lines)
    print(line)


def cmd_input_add(args: argparse.Namespace) -> None:
    set_section_value(Path("project.godot"), "input", args.action, key_event(args.key))
    print(f"{args.action} -> {args.key}")


def cmd_input_list(_: argparse.Namespace) -> None:
    for action in sorted(section_items(Path("project.godot"), "input")):
        print(action)


def cmd_input_remove(args: argparse.Namespace) -> None:
    set_section_value(Path("project.godot"), "input", args.action, None)
    print(args.action)


def cmd_autoload_add(args: argparse.Namespace) -> None:
    set_section_value(
        Path("project.godot"), "autoload", args.name, f'"*{res(args.path)}"'
    )
    print(f"{args.name} -> {res(args.path)}")


def cmd_autoload_list(_: argparse.Namespace) -> None:
    for name, path in sorted(section_items(Path("project.godot"), "autoload").items()):
        print(f"{name} {path.strip(chr(34)).lstrip('*')}")


def cmd_autoload_remove(args: argparse.Namespace) -> None:
    set_section_value(Path("project.godot"), "autoload", args.name, None)
    print(args.name)


def cmd_tree(args: argparse.Namespace) -> None:
    ns = nodes(read_lines(scene_path(args.scene)))
    if not ns:
        return
    by_parent: dict[str, list[dict[str, str]]] = {}
    root = ns[0]
    for n in ns:
        by_parent.setdefault(n["parent"], []).append(n)

    def walk(parent: str, prefix: str = "") -> None:
        kids = by_parent.get(parent, [])
        for i, n in enumerate(kids):
            last = i == len(kids) - 1
            print(prefix + ("└── " if last else "├── ") + f"{n['name']} ({n['type']})")
            walk(node_full_path(n), prefix + ("    " if last else "│   "))

    print(f"{root['name']} ({root['type']})")
    walk(".")


def require_godot(godot: str) -> str:
    if shutil.which(godot):
        return godot
    raise SystemExit(
        f"Godot not found: {godot}. Install it or pass --godot /path/to/godot"
    )


def cmd_check(args: argparse.Namespace) -> None:
    errors: list[str] = []
    for scene in sorted(Path(".").rglob("*.tscn")):
        lines = read_lines(scene)
        paths = {node_full_path(n) for n in nodes(lines)}
        paths.add(".")
        for n in nodes(lines):
            if n["parent"] and n["parent"] not in paths:
                errors.append(
                    f"{scene}: parent does not exist: {n['parent']} -> {n['name']}"
                )
        for script, _ext_id in ext_resources(lines):
            if not local(script).exists():
                errors.append(f"{scene}: script does not exist: {script}")
    if errors:
        print("\n".join(errors))
        raise SystemExit(1)
    if getattr(args, "godot", None):
        code = subprocess.call(
            [require_godot(args.godot), "--headless", "--path", ".", "--quit"]
        )
        if code:
            raise SystemExit(code)
    print("OK")


def cmd_run(args: argparse.Namespace) -> None:
    raise SystemExit(subprocess.call([require_godot(args.godot), "--path", "."]))


def cmd_test(args: argparse.Namespace) -> None:
    cmd = section_items(Path("project.godot"), "gd").get("test_command")
    if not cmd:
        raise SystemExit(
            "no GDScript test runner configured; set gd/test_command first"
        )
    raise SystemExit(subprocess.call(shlex.split(cmd)))


def export_presets() -> list[str]:
    cfg = configparser.ConfigParser()
    cfg.read("export_presets.cfg", encoding="utf-8")
    return [
        (cfg[section].get("name") or section).strip('"')
        for section in cfg.sections()
        if re.fullmatch(r"preset\.\d+", section)
    ]


def cmd_export_list(_: argparse.Namespace) -> None:
    for name in export_presets():
        print(name)


def cmd_export_run(args: argparse.Namespace) -> None:
    if args.preset not in export_presets():
        raise SystemExit(f"export preset not found: {args.preset}")
    cmd = [
        require_godot(args.godot),
        "--headless",
        "--path",
        ".",
        "--export-release",
        args.preset,
    ]
    if args.output:
        cmd.append(args.output)
    raise SystemExit(subprocess.call(cmd))


def map_path(path: str) -> Path:
    p = Path(path)
    return p if p.suffix else Path("levels") / p.with_suffix(".map")


def read_map(path: Path) -> list[str]:
    lines = read_lines(path)
    return [line for line in lines if not line.startswith(";")]


def map_errors(rows: list[str]) -> list[str]:
    if not rows:
        return ["empty map"]
    width = len(rows[0])
    return [
        f"line {i}: width {len(row)} != {width}"
        for i, row in enumerate(rows, 1)
        if len(row) != width
    ]


def map_legend() -> dict[str, str]:
    path = Path("levels/map.legend")
    items = section_items(path, "legend") if path.exists() else {}
    return {"#": "StaticBody2D", "P": "CharacterBody2D", **items}


def cmd_map_new(args: argparse.Namespace) -> None:
    path = map_path(args.path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and not args.force:
        raise SystemExit(f"already exists: {path}")
    write_lines(path, [args.fill * args.width for _ in range(args.height)])
    print(path)


def cmd_map_list(_: argparse.Namespace) -> None:
    for path in sorted(Path("levels").rglob("*.map")):
        print(path.as_posix())


def cmd_map_check(args: argparse.Namespace) -> None:
    errors = map_errors(read_map(map_path(args.path)))
    if errors:
        print("\n".join(errors))
        raise SystemExit(1)
    print("OK")


def set_map_tile(rows: list[str], x: int, y: int, tile: str) -> list[str]:
    if len(tile) != 1:
        raise ValueError("tile must be one character")
    if y < 0 or y >= len(rows) or x < 0 or x >= len(rows[y]):
        return rows
    out = rows[:]
    out[y] = out[y][:x] + tile + out[y][x + 1 :]
    return out


def cmd_map_compile(args: argparse.Namespace) -> None:
    rows = read_map(map_path(args.map))
    if errors := map_errors(rows):
        print("\n".join(errors))
        raise SystemExit(1)
    legend = map_legend()
    lines = [
        "[gd_scene format=3]",
        "",
        f'[node name="{scene_path(args.scene).stem}" type="Node2D"]',
    ]
    # ponytail: placeholder nodes, switch to TileMapLayer when atlas/tileset metadata exists.
    for y, row in enumerate(rows):
        for x, ch in enumerate(row):
            if ch == ".":
                continue
            typ = legend.get(ch, "Node2D")
            lines += [
                "",
                f'[node name="{ch}_{x}_{y}" type="{typ}" parent="."]',
                f"position = Vector2({x * args.tile_size}, {y * args.tile_size})",
            ]
    path = scene_path(args.scene)
    path.parent.mkdir(parents=True, exist_ok=True)
    write_lines(path, lines)
    print(path)


def cmd_map_edit(args: argparse.Namespace) -> None:
    import curses

    path = map_path(args.path)
    rows = read_map(path)
    if errors := map_errors(rows):
        print("\n".join(errors))
        raise SystemExit(1)
    undo: list[list[str]] = []

    def draw(
        stdscr: curses.window, x: int, y: int, tile: str, message: str = ""
    ) -> None:
        stdscr.clear()
        height, width = stdscr.getmaxyx()
        stdscr.addstr(
            0, 0, f"gd map edit {path} tile={tile} ?:help :q quit", curses.A_BOLD
        )
        for row_i, row in enumerate(rows[: height - 2]):
            for col_i, ch in enumerate(row[: width - 1]):
                mode = curses.A_REVERSE if (col_i, row_i) == (x, y) else curses.A_NORMAL
                stdscr.addstr(row_i + 1, col_i, ch, mode)
        if message:
            stdscr.addstr(height - 1, 0, message[: width - 1])
        stdscr.refresh()

    def save() -> None:
        write_lines(path, rows)

    def run(stdscr: curses.window) -> None:
        nonlocal rows
        x = y = 0
        tile = "#"
        message = "h/j/k/l move, p paint, any printable selects tile, u undo"
        while True:
            draw(stdscr, x, y, tile, message)
            key = stdscr.get_wch()
            message = ""
            if key in ("h", curses.KEY_LEFT):
                x = max(0, x - 1)
            elif key in ("l", curses.KEY_RIGHT):
                x = min(len(rows[y]) - 1, x + 1)
            elif key in ("k", curses.KEY_UP):
                y = max(0, y - 1)
                x = min(x, len(rows[y]) - 1)
            elif key in ("j", curses.KEY_DOWN):
                y = min(len(rows) - 1, y + 1)
                x = min(x, len(rows[y]) - 1)
            elif key in ("p", " "):
                undo.append(rows[:])
                rows = set_map_tile(rows, x, y, tile)
            elif key == "u" and undo:
                rows = undo.pop()
            elif key == "?":
                message = (
                    "h/j/k/l move, char selects tile, p/space paint, u undo, :w/:q/:wq"
                )
            elif key == ":":
                curses.echo()
                stdscr.addstr(curses.LINES - 1, 0, ":")
                cmd = stdscr.getstr().decode()
                curses.noecho()
                if cmd == "w":
                    save()
                    message = "written"
                elif cmd == "wq":
                    save()
                    return
                elif cmd == "q":
                    return
            elif isinstance(key, str) and len(key) == 1 and key.isprintable():
                tile = key

    curses.wrapper(run)


def cmd_tilemap_edit(_: argparse.Namespace) -> None:
    raise SystemExit(
        "native TileMap edit is not implemented; use `gd map edit <map>` then `gd map compile <map> <scene>`"
    )


def cmd_scene_edit(args: argparse.Namespace) -> None:
    import curses

    path = scene_path(args.scene)
    lines = read_lines(path)
    rows = scene_tree_rows(lines)
    if not rows:
        raise SystemExit("scene has no nodes")

    def draw(stdscr: curses.window, selected: int, message: str = "") -> None:
        stdscr.clear()
        height, width = stdscr.getmaxyx()
        split = max(24, width // 2)
        stdscr.addstr(0, 0, f"gd scene edit {path}  ?:help  :q quit", curses.A_BOLD)
        for i, (_node_path, label) in enumerate(rows[: height - 2]):
            mode = curses.A_REVERSE if i == selected else curses.A_NORMAL
            stdscr.addstr(i + 1, 0, label[: split - 1], mode)
        props = node_props(lines, rows[selected][0])
        stdscr.addstr(1, split, rows[selected][0][: width - split - 1], curses.A_BOLD)
        for i, prop in enumerate(props[: height - 4]):
            stdscr.addstr(i + 3, split, prop[: width - split - 1])
        if message:
            stdscr.addstr(height - 1, 0, message[: width - 1])
        stdscr.refresh()

    def run(stdscr: curses.window) -> None:
        selected = 0
        message = "j/k move, / search, d delete, :w/:q/:wq, i opens hint"
        while True:
            draw(stdscr, selected, message)
            key = stdscr.get_wch()
            message = ""
            if key in ("q",):
                return
            if key in ("j", curses.KEY_DOWN):
                selected = min(selected + 1, len(rows) - 1)
            elif key in ("k", curses.KEY_UP):
                selected = max(selected - 1, 0)
            elif key in ("h", "l"):
                message = "h/l reserved; use Neovim+LSP for deep .tscn edits"
            elif key == "?":
                message = "vim-ish: j/k move, / find, d delete, :w save, :q quit"
            elif key == "i":
                message = "edit properties with: gd node set ... or Neovim+LSP"
            elif key == "d":
                message = "delete with: gd node remove ... (not inside TUI yet)"
            elif key == "/":
                curses.echo()
                stdscr.addstr(curses.LINES - 1, 0, "/")
                query = stdscr.getstr().decode()
                curses.noecho()
                hit = next((i for i, r in enumerate(rows) if query in r[0]), selected)
                selected = hit
            elif key == ":":
                curses.echo()
                stdscr.addstr(curses.LINES - 1, 0, ":")
                cmd = stdscr.getstr().decode()
                curses.noecho()
                if cmd in ("q", "wq"):
                    return
                if cmd == "w":
                    write_lines(path, lines)
                    message = "written"

    curses.wrapper(run)


def self_test() -> None:
    with tempfile.TemporaryDirectory() as d:
        cwd = Path.cwd()
        try:
            os.chdir(d)
            cmd_project_init(argparse.Namespace(name="Demo", force=False))
            cmd_scene_create(
                argparse.Namespace(path="Main", root="Node2D", force=False)
            )
            cmd_node_add(
                argparse.Namespace(
                    scene="Main", name="Player", type="CharacterBody2D", parent="."
                )
            )
            cmd_node_add(
                argparse.Namespace(
                    scene="Main", name="Sprite", type="Sprite2D", parent="Player"
                )
            )
            cmd_script_create(
                argparse.Namespace(
                    path="player.gd", extends="CharacterBody2D", force=False
                )
            )
            cmd_script_attach(
                argparse.Namespace(scene="Main", node="Player", script="player.gd")
            )
            cmd_signal_connect(
                argparse.Namespace(
                    scene="Main",
                    signal="ready",
                    from_node="Player",
                    to_node="Player",
                    method="_on_ready",
                )
            )
            cmd_node_rename(
                argparse.Namespace(scene="Main", node="Player", new_name="Hero")
            )
            cmd_check(argparse.Namespace())
            text = Path("Main.tscn").read_text(encoding="utf-8")
            assert '[node name="Hero" type="CharacterBody2D" parent="."]' in text
            assert '[node name="Sprite" type="Sprite2D" parent="Hero"]' in text
            assert 'script = ExtResource("1")' in text
            assert 'from="Hero" to="Hero"' in text
            cmd_node_remove(argparse.Namespace(scene="Main", node="Hero"))
            assert "Hero" not in Path("Main.tscn").read_text(encoding="utf-8")
        finally:
            os.chdir(cwd)


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="gd", description="Tiny CLI for Godot 4")
    sub = p.add_subparsers(required=True)

    pi = sub.add_parser("project")
    pi_sub = pi.add_subparsers(required=True)
    init = pi_sub.add_parser("init")
    init.add_argument("name")
    init.add_argument("--force", action="store_true")
    init.set_defaults(func=cmd_project_init)
    pi_sub.add_parser("info").set_defaults(func=cmd_project_info)
    pi_sub.add_parser("scaffold").set_defaults(func=cmd_project_scaffold)
    setting = pi_sub.add_parser("setting")
    setting_sub = setting.add_subparsers(required=True)
    sg = setting_sub.add_parser("get")
    sg.add_argument("key")
    sg.set_defaults(func=cmd_project_setting_get)
    ss = setting_sub.add_parser("set")
    ss.add_argument("key")
    ss.add_argument("value")
    ss.set_defaults(func=cmd_project_setting_set)

    sc = sub.add_parser("scene")
    sc_sub = sc.add_subparsers(required=True)
    c = sc_sub.add_parser("create")
    c.add_argument("path")
    c.add_argument("--root", default="Node2D")
    c.add_argument("--force", action="store_true")
    c.set_defaults(func=cmd_scene_create)
    sc_sub.add_parser("list").set_defaults(func=cmd_scene_list)
    main_scene = sc_sub.add_parser("main")
    main_scene.add_argument("scene")
    main_scene.set_defaults(func=cmd_scene_main)
    edit_scene = sc_sub.add_parser("edit")
    edit_scene.add_argument("scene")
    edit_scene.set_defaults(func=cmd_scene_edit)
    inst = sc_sub.add_parser("instance")
    inst.add_argument("scene")
    inst.add_argument("name")
    inst.add_argument("packed")
    inst.add_argument("--parent", default=".")
    inst.set_defaults(func=cmd_scene_instance)

    n = sub.add_parser("node")
    n_sub = n.add_subparsers(required=True)
    a = n_sub.add_parser("add")
    a.add_argument("scene")
    a.add_argument("name")
    a.add_argument("--type", default="Node2D")
    a.add_argument("--parent", default=".")
    a.set_defaults(func=cmd_node_add)
    nl = n_sub.add_parser("list")
    nl.add_argument("scene")
    nl.set_defaults(func=cmd_node_list)
    rn = n_sub.add_parser("rename")
    rn.add_argument("scene")
    rn.add_argument("node")
    rn.add_argument("new_name")
    rn.set_defaults(func=cmd_node_rename)
    rm = n_sub.add_parser("remove")
    rm.add_argument("scene")
    rm.add_argument("node")
    rm.set_defaults(func=cmd_node_remove)
    ng = n_sub.add_parser("get")
    ng.add_argument("scene")
    ng.add_argument("node")
    ng.add_argument("property")
    ng.set_defaults(func=cmd_node_get)
    ns = n_sub.add_parser("set")
    ns.add_argument("scene")
    ns.add_argument("node")
    ns.add_argument("property")
    ns.add_argument("value")
    ns.set_defaults(func=cmd_node_set)
    dup = n_sub.add_parser("duplicate")
    dup.add_argument("scene")
    dup.add_argument("node")
    dup.add_argument("new_name")
    dup.set_defaults(func=cmd_node_duplicate)

    s = sub.add_parser("script")
    s_sub = s.add_subparsers(required=True)
    cs = s_sub.add_parser("create")
    cs.add_argument("path")
    cs.add_argument("--extends", default="Node")
    cs.add_argument("--template", choices=sorted(SCRIPT_TEMPLATES))
    cs.add_argument("--force", action="store_true")
    cs.set_defaults(func=cmd_script_create)
    at = s_sub.add_parser("attach")
    at.add_argument("scene")
    at.add_argument("node")
    at.add_argument("script")
    at.set_defaults(func=cmd_script_attach)
    s_sub.add_parser("list").set_defaults(func=cmd_script_list)

    sf = sub.add_parser("spriteframes")
    sf_sub = sf.add_subparsers(required=True)
    sheet = sf_sub.add_parser("from-sheet")
    sheet.add_argument("scene")
    sheet.add_argument("node")
    sheet.add_argument("image")
    sheet.add_argument("--anim", required=True)
    sheet.add_argument("--frame", required=True, help="frame size, e.g. 16x16")
    sheet.add_argument("--count", type=int, required=True)
    sheet.add_argument("--fps", type=float, default=8.0)
    sheet.add_argument("--offset", default="0,0")
    sheet.add_argument("--columns", type=int)
    sheet.add_argument("--out")
    sheet.set_defaults(func=cmd_spriteframes_from_sheet)

    asset = sub.add_parser("asset")
    asset_sub = asset.add_subparsers(required=True)
    asset_sub.add_parser("list").set_defaults(func=cmd_asset_list)
    asset_sub.add_parser("check").set_defaults(func=cmd_asset_check)

    sig = sub.add_parser("signal")
    sig_sub = sig.add_subparsers(required=True)
    co = sig_sub.add_parser("connect")
    co.add_argument("scene")
    co.add_argument("signal")
    co.add_argument("from_node")
    co.add_argument("to_node")
    co.add_argument("method")
    co.set_defaults(func=cmd_signal_connect)
    sl = sig_sub.add_parser("list")
    sl.add_argument("scene")
    sl.set_defaults(func=cmd_signal_list)

    col = sub.add_parser("collision")
    col_sub = col.add_subparsers(required=True)
    ca = col_sub.add_parser("add")
    ca.add_argument("scene")
    ca.add_argument("node")
    ca.add_argument("shape", choices=["rectangle", "circle", "capsule"])
    ca.add_argument("size", help="WxH | radius | radius,height")
    ca.set_defaults(func=cmd_collision_add)

    cam = sub.add_parser("camera")
    cam_sub = cam.add_subparsers(required=True)
    cma = cam_sub.add_parser("add")
    cma.add_argument("scene")
    cma.add_argument("name")
    cma.add_argument("--parent", default=".")
    cma.add_argument("--current", action="store_true")
    cma.add_argument("--zoom", type=float)
    cma.set_defaults(func=cmd_camera_add)

    aud = sub.add_parser("audio")
    aud_sub = aud.add_subparsers(required=True)
    ada = aud_sub.add_parser("add")
    ada.add_argument("scene")
    ada.add_argument("name")
    ada.add_argument("file")
    ada.add_argument("--parent", default=".")
    ada.set_defaults(func=cmd_audio_add)

    grp = sub.add_parser("group")
    grp_sub = grp.add_subparsers(required=True)
    ga = grp_sub.add_parser("add")
    ga.add_argument("scene")
    ga.add_argument("node")
    ga.add_argument("group")
    ga.set_defaults(func=cmd_group_add)
    gl = grp_sub.add_parser("list")
    gl.add_argument("scene")
    gl.add_argument("node", nargs="?")
    gl.set_defaults(func=cmd_group_list)
    gr = grp_sub.add_parser("remove")
    gr.add_argument("scene")
    gr.add_argument("node")
    gr.add_argument("group")
    gr.set_defaults(func=cmd_group_remove)

    inp = sub.add_parser("input")
    inp_sub = inp.add_subparsers(required=True)
    ia = inp_sub.add_parser("add")
    ia.add_argument("action")
    ia.add_argument("key")
    ia.set_defaults(func=cmd_input_add)
    ip = inp_sub.add_parser("preset")
    ip.add_argument("name", choices=sorted(INPUT_PRESETS))
    ip.set_defaults(func=cmd_input_preset)
    inp_sub.add_parser("list").set_defaults(func=cmd_input_list)
    ir = inp_sub.add_parser("remove")
    ir.add_argument("action")
    ir.set_defaults(func=cmd_input_remove)

    au = sub.add_parser("autoload")
    au_sub = au.add_subparsers(required=True)
    aa = au_sub.add_parser("add")
    aa.add_argument("name")
    aa.add_argument("path")
    aa.set_defaults(func=cmd_autoload_add)
    au_sub.add_parser("list").set_defaults(func=cmd_autoload_list)
    ar = au_sub.add_parser("remove")
    ar.add_argument("name")
    ar.set_defaults(func=cmd_autoload_remove)

    mp = sub.add_parser("map")
    mp_sub = mp.add_subparsers(required=True)
    mn = mp_sub.add_parser("new")
    mn.add_argument("path")
    mn.add_argument("width", type=int)
    mn.add_argument("height", type=int)
    mn.add_argument("--fill", default=".")
    mn.add_argument("--force", action="store_true")
    mn.set_defaults(func=cmd_map_new)
    mp_sub.add_parser("list").set_defaults(func=cmd_map_list)
    mc = mp_sub.add_parser("check")
    mc.add_argument("path")
    mc.set_defaults(func=cmd_map_check)
    mco = mp_sub.add_parser("compile")
    mco.add_argument("map")
    mco.add_argument("scene")
    mco.add_argument("--tile-size", type=int, default=16)
    mco.set_defaults(func=cmd_map_compile)
    me = mp_sub.add_parser("edit")
    me.add_argument("path")
    me.set_defaults(func=cmd_map_edit)

    tm = sub.add_parser("tilemap")
    tm_sub = tm.add_subparsers(required=True)
    tile_edit = tm_sub.add_parser("edit")
    tile_edit.add_argument("scene")
    tile_edit.add_argument("node")
    tile_edit.set_defaults(func=cmd_tilemap_edit)

    tmpl = sub.add_parser("template")
    tmpl.add_argument("name", choices=sorted(GAME_TEMPLATES))
    tmpl.set_defaults(func=cmd_template)

    sub.add_parser("doctor").set_defaults(func=cmd_doctor)

    docs = sub.add_parser("docs")
    docs.add_argument("cls")
    docs.add_argument("--open", action="store_true")
    docs.set_defaults(func=cmd_docs)

    t = sub.add_parser("tree")
    t.add_argument("scene")
    t.set_defaults(func=cmd_tree)

    chk = sub.add_parser("check")
    chk.add_argument("--godot", nargs="?", const="godot", default=None)
    chk.set_defaults(func=cmd_check)

    test = sub.add_parser("test")
    test.set_defaults(func=cmd_test)

    exp = sub.add_parser("export")
    exp_sub = exp.add_subparsers(required=True)
    exp_sub.add_parser("list").set_defaults(func=cmd_export_list)
    er = exp_sub.add_parser("run")
    er.add_argument("preset")
    er.add_argument("output", nargs="?")
    er.add_argument("--godot", default="godot")
    er.set_defaults(func=cmd_export_run)

    r = sub.add_parser("run")
    r.add_argument("--godot", default="godot")
    r.set_defaults(func=cmd_run)

    st = sub.add_parser("self-test")
    st.set_defaults(func=lambda _: self_test())
    return p


def main(argv: list[str] | None = None) -> None:
    args = parser().parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
