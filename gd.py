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


def res(path: str | Path) -> str:
    p = Path(path).as_posix()
    return p if p.startswith("res://") else "res://" + p.lstrip("/")


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
    path.write_text(
        f"extends {args.extends}\n\nfunc _ready() -> void:\n\tpass\n", encoding="utf-8"
    )
    print(path)


def cmd_script_list(_: argparse.Namespace) -> None:
    for path in sorted(Path(".").rglob("*.gd")):
        print(path.as_posix())


def next_ext_id(lines: list[str]) -> str:
    return str(sum(1 for b in parse_scene(lines) if b.kind == "ext_resource") + 1)


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
    nd = n_sub.add_parser("duplicate")
    nd.add_argument("scene")
    nd.add_argument("node")
    nd.add_argument("new_name")
    nd.set_defaults(func=cmd_node_duplicate)

    s = sub.add_parser("script")
    s_sub = s.add_subparsers(required=True)
    cs = s_sub.add_parser("create")
    cs.add_argument("path")
    cs.add_argument("--extends", default="Node")
    cs.add_argument("--force", action="store_true")
    cs.set_defaults(func=cmd_script_create)
    at = s_sub.add_parser("attach")
    at.add_argument("scene")
    at.add_argument("node")
    at.add_argument("script")
    at.set_defaults(func=cmd_script_attach)
    s_sub.add_parser("list").set_defaults(func=cmd_script_list)

    sig = sub.add_parser("signal")
    sig_sub = sig.add_subparsers(required=True)
    co = sig_sub.add_parser("connect")
    co.add_argument("scene")
    co.add_argument("signal")
    co.add_argument("from_node")
    co.add_argument("to_node")
    co.add_argument("method")
    co.set_defaults(func=cmd_signal_connect)

    inp = sub.add_parser("input")
    inp_sub = inp.add_subparsers(required=True)
    ia = inp_sub.add_parser("add")
    ia.add_argument("action")
    ia.add_argument("key")
    ia.set_defaults(func=cmd_input_add)
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
    tme = tm_sub.add_parser("edit")
    tme.add_argument("scene")
    tme.add_argument("node")
    tme.set_defaults(func=cmd_tilemap_edit)

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
