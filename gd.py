#!/usr/bin/env python3
"""Tiny Godot CLI: edit simple Godot 4 .tscn/.gd files without opening the editor."""

from __future__ import annotations

import argparse
import configparser
import os
import re
import subprocess
import tempfile
from pathlib import Path

NODE_RE = re.compile(r'^\[node name="([^"]+)" type="([^"]+)"(?: parent="([^"]+)")?\]$')
EXT_RE = re.compile(r'^\[ext_resource type="Script" path="([^"]+)" id="([^"]+)"\]$')
CONN_RE = re.compile(
    r'^\[connection signal="([^"]+)" from="([^"]+)" to="([^"]+)" method="([^"]+)"\]$'
)


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
        raise SystemExit(f"no existe: {path}")
    return path.read_text(encoding="utf-8").splitlines()


def write_lines(path: Path, lines: list[str]) -> None:
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def nodes(lines: list[str]) -> list[dict[str, str]]:
    out = []
    for i, line in enumerate(lines):
        m = NODE_RE.match(line)
        if m:
            name, typ, parent = m.groups()
            out.append(
                {"line": str(i), "name": name, "type": typ, "parent": parent or ""}
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
        raise SystemExit(f"nodo no encontrado: {wanted}")
    return hit


def node_line(node: dict[str, str]) -> int:
    try:
        return int(node["line"])
    except ValueError as exc:
        raise SystemExit("escena inválida: línea de nodo no numérica") from exc


def node_block(lines: list[str], line_i: int) -> tuple[int, int]:
    end = next(
        (i for i in range(line_i + 1, len(lines)) if lines[i].startswith("[node ")),
        len(lines),
    )
    return line_i, end


def ext_resources(lines: list[str]) -> list[tuple[str, str]]:
    return [(m.group(1), m.group(2)) for line in lines if (m := EXT_RE.match(line))]


def cmd_project_init(args: argparse.Namespace) -> None:
    path = Path("project.godot")
    if path.exists() and not args.force:
        raise SystemExit("ya existe: project.godot")
    path.write_text(
        f'; Engine configuration file.\n\n[application]\nconfig/name="{args.name}"\n',
        encoding="utf-8",
    )
    print(path)


def cmd_project_info(_: argparse.Namespace) -> None:
    project = Path("project.godot")
    if not project.exists():
        print("No hay project.godot en este directorio")
        return
    cfg = configparser.ConfigParser()
    cfg.read(project, encoding="utf-8")
    app = cfg["application"] if cfg.has_section("application") else {}
    print(app.get("config/name", Path.cwd().name).strip('"'))
    if "run/main_scene" in app:
        print(app["run/main_scene"].strip('"'))


def cmd_scene_create(args: argparse.Namespace) -> None:
    path = scene_path(args.path)
    if path.exists() and not args.force:
        raise SystemExit(f"ya existe: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f'[gd_scene format=3]\n\n[node name="{path.stem}" type="{args.root}"]\n',
        encoding="utf-8",
    )
    print(path)


def cmd_scene_list(_: argparse.Namespace) -> None:
    for path in sorted(Path(".").rglob("*.tscn")):
        print(path.as_posix())


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
        m = CONN_RE.match(line)
        if m and (m.group(2) in doomed or m.group(3) in doomed):
            remove_lines.add(i)
    write_lines(path, [line for i, line in enumerate(lines) if i not in remove_lines])
    print("\n".join(sorted(doomed)))


def cmd_script_create(args: argparse.Namespace) -> None:
    path = Path(args.path)
    if path.exists() and not args.force:
        raise SystemExit(f"ya existe: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"extends {args.extends}\n\nfunc _ready() -> void:\n\tpass\n", encoding="utf-8"
    )
    print(path)


def cmd_script_list(_: argparse.Namespace) -> None:
    for path in sorted(Path(".").rglob("*.gd")):
        print(path.as_posix())


def next_ext_id(lines: list[str]) -> str:
    return str(sum(1 for line in lines if EXT_RE.match(line)) + 1)


def cmd_script_attach(args: argparse.Namespace) -> None:
    path = scene_path(args.scene)
    lines = read_lines(path)
    target = find_node(lines, args.node)
    script = res(args.script)
    existing = next(
        (
            m.group(2)
            for line in lines
            if (m := EXT_RE.match(line)) and m.group(1) == script
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


def cmd_check(_: argparse.Namespace) -> None:
    errors: list[str] = []
    for scene in sorted(Path(".").rglob("*.tscn")):
        lines = read_lines(scene)
        paths = {node_full_path(n) for n in nodes(lines)}
        paths.add(".")
        for n in nodes(lines):
            if n["parent"] and n["parent"] not in paths:
                errors.append(f"{scene}: padre no existe: {n['parent']} -> {n['name']}")
        for script, _ext_id in ext_resources(lines):
            if not local(script).exists():
                errors.append(f"{scene}: script no existe: {script}")
    if errors:
        print("\n".join(errors))
        raise SystemExit(1)
    print("OK")


def cmd_run(args: argparse.Namespace) -> None:
    raise SystemExit(subprocess.call([args.godot, "--path", "."]))


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
    p = argparse.ArgumentParser(prog="gd", description="CLI mínimo para Godot 4")
    sub = p.add_subparsers(required=True)

    pi = sub.add_parser("project")
    pi_sub = pi.add_subparsers(required=True)
    init = pi_sub.add_parser("init")
    init.add_argument("name")
    init.add_argument("--force", action="store_true")
    init.set_defaults(func=cmd_project_init)
    pi_sub.add_parser("info").set_defaults(func=cmd_project_info)

    sc = sub.add_parser("scene")
    sc_sub = sc.add_subparsers(required=True)
    c = sc_sub.add_parser("create")
    c.add_argument("path")
    c.add_argument("--root", default="Node2D")
    c.add_argument("--force", action="store_true")
    c.set_defaults(func=cmd_scene_create)
    sc_sub.add_parser("list").set_defaults(func=cmd_scene_list)

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

    t = sub.add_parser("tree")
    t.add_argument("scene")
    t.set_defaults(func=cmd_tree)

    sub.add_parser("check").set_defaults(func=cmd_check)

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
