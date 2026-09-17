import argparse
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import gd


class GodotCliTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.cwd = Path.cwd()
        os.chdir(self.tmp.name)

    def tearDown(self) -> None:
        os.chdir(self.cwd)
        self.tmp.cleanup()

    def scene(self) -> str:
        return Path("Main.tscn").read_text(encoding="utf-8")

    def test_create_add_attach_tree_and_check(self) -> None:
        gd.cmd_project_init(argparse.Namespace(name="Demo", force=False))
        gd.cmd_scene_create(argparse.Namespace(path="Main", root="Node2D", force=False))
        gd.cmd_node_add(
            argparse.Namespace(
                scene="Main", name="Player", type="CharacterBody2D", parent="."
            )
        )
        gd.cmd_node_add(
            argparse.Namespace(
                scene="Main", name="Sprite", type="Sprite2D", parent="Player"
            )
        )
        gd.cmd_script_create(
            argparse.Namespace(path="player.gd", extends="CharacterBody2D", force=False)
        )
        gd.cmd_script_attach(
            argparse.Namespace(scene="Main", node="Player", script="player.gd")
        )
        gd.cmd_signal_connect(
            argparse.Namespace(
                scene="Main",
                signal="ready",
                from_node="Player",
                to_node="Player",
                method="_on_ready",
            )
        )
        gd.cmd_check(argparse.Namespace())

        text = self.scene()
        self.assertIn('[node name="Main" type="Node2D"]', text)
        self.assertIn('[node name="Player" type="CharacterBody2D" parent="."]', text)
        self.assertIn('[node name="Sprite" type="Sprite2D" parent="Player"]', text)
        self.assertIn(
            '[ext_resource type="Script" path="res://player.gd" id="1"]', text
        )
        self.assertIn('script = ExtResource("1")', text)
        self.assertIn(
            '[connection signal="ready" from="Player" to="Player" method="_on_ready"]',
            text,
        )

    def test_parser_handles_extra_attrs_and_preserves_unknown_blocks(self) -> None:
        Path("Main.tscn").write_text(
            '[gd_scene load_steps=2 format=3 uid="uid://demo"]\n\n'
            '[sub_resource type="RectangleShape2D" id="RectangleShape2D_1"]\n'
            "size = Vector2(8, 9)\n\n"
            '[node name="Main" type="Node2D"]\n'
            'metadata/foo = "keep"\n\n'
            '[node name="Child" type="Node2D" parent="." index="0"]\n'
            "position = Vector2(1, 2)\n",
            encoding="utf-8",
        )

        gd.cmd_node_rename(
            argparse.Namespace(scene="Main", node="Child", new_name="Hero")
        )

        text = self.scene()
        self.assertIn('[node name="Hero" type="Node2D" parent="." index="0"]', text)
        self.assertIn(
            '[sub_resource type="RectangleShape2D" id="RectangleShape2D_1"]', text
        )
        self.assertIn("size = Vector2(8, 9)", text)
        self.assertIn('metadata/foo = "keep"', text)
        self.assertIn("position = Vector2(1, 2)", text)

    def test_rename_updates_children_and_connections(self) -> None:
        gd.cmd_scene_create(argparse.Namespace(path="Main", root="Node2D", force=False))
        gd.cmd_node_add(
            argparse.Namespace(scene="Main", name="Player", type="Node2D", parent=".")
        )
        gd.cmd_node_add(
            argparse.Namespace(
                scene="Main", name="Sprite", type="Sprite2D", parent="Player"
            )
        )
        gd.cmd_signal_connect(
            argparse.Namespace(
                scene="Main",
                signal="ready",
                from_node="Player",
                to_node="Player",
                method="_on_ready",
            )
        )

        gd.cmd_node_rename(
            argparse.Namespace(scene="Main", node="Player", new_name="Hero")
        )

        text = self.scene()
        self.assertIn('[node name="Hero" type="Node2D" parent="."]', text)
        self.assertIn('[node name="Sprite" type="Sprite2D" parent="Hero"]', text)
        self.assertIn('from="Hero" to="Hero"', text)
        self.assertNotIn("Player", text)

    def test_remove_deletes_children_and_connections(self) -> None:
        gd.cmd_scene_create(argparse.Namespace(path="Main", root="Node2D", force=False))
        gd.cmd_node_add(
            argparse.Namespace(scene="Main", name="Player", type="Node2D", parent=".")
        )
        gd.cmd_node_add(
            argparse.Namespace(
                scene="Main", name="Sprite", type="Sprite2D", parent="Player"
            )
        )
        gd.cmd_signal_connect(
            argparse.Namespace(
                scene="Main",
                signal="ready",
                from_node="Player",
                to_node="Player",
                method="_on_ready",
            )
        )

        gd.cmd_node_remove(argparse.Namespace(scene="Main", node="Player"))

        text = self.scene()
        self.assertIn('[node name="Main" type="Node2D"]', text)
        self.assertNotIn("Player", text)
        self.assertNotIn("Sprite", text)
        self.assertNotIn("connection", text)

    def test_check_fails_on_missing_script_and_parent(self) -> None:
        Path("Broken.tscn").write_text(
            "[gd_scene format=3]\n\n"
            '[ext_resource type="Script" path="res://missing.gd" id="1"]\n\n'
            '[node name="Child" type="Node2D" parent="Missing"]\n',
            encoding="utf-8",
        )

        with self.assertRaises(SystemExit) as err:
            gd.cmd_check(argparse.Namespace())
        self.assertEqual(err.exception.code, 1)

    def test_core_cli_commands(self) -> None:
        gd.cmd_project_init(argparse.Namespace(name="Demo", force=False))
        gd.cmd_scene_create(argparse.Namespace(path="Main", root="Node2D", force=False))
        gd.cmd_scene_main(argparse.Namespace(scene="Main"))
        gd.cmd_node_add(
            argparse.Namespace(scene="Main", name="Player", type="Node2D", parent=".")
        )
        gd.cmd_node_set(
            argparse.Namespace(
                scene="Main", node="Player", property="position", value="Vector2(1, 2)"
            )
        )
        gd.cmd_node_duplicate(
            argparse.Namespace(scene="Main", node="Player", new_name="Enemy")
        )
        gd.cmd_project_setting_set(
            argparse.Namespace(key="display/window/size/viewport_width", value="1280")
        )
        gd.cmd_input_add(argparse.Namespace(action="jump", key="Space"))
        gd.cmd_autoload_add(argparse.Namespace(name="Game", path="game.gd"))

        self.assertIn(
            'run/main_scene="res://Main.tscn"', Path("project.godot").read_text()
        )
        self.assertIn("position = Vector2(1, 2)", self.scene())
        self.assertIn('[node name="Enemy" type="Node2D" parent="."]', self.scene())
        project = Path("project.godot").read_text()
        self.assertIn("viewport_width=1280", project)
        self.assertIn("jump=", project)
        self.assertIn('Game="*res://game.gd"', project)

    def test_godot_headless_commands(self) -> None:
        gd.cmd_project_init(argparse.Namespace(name="Demo", force=False))
        gd.cmd_scene_create(argparse.Namespace(path="Main", root="Node2D", force=False))
        with (
            mock.patch("gd.shutil.which", return_value="/bin/godot"),
            mock.patch("gd.subprocess.call", return_value=0) as call,
        ):
            gd.cmd_check(argparse.Namespace(godot="godot"))
            call.assert_called_with(["godot", "--headless", "--path", ".", "--quit"])
            with self.assertRaises(SystemExit) as err:
                gd.cmd_run(argparse.Namespace(godot="godot"))
            self.assertEqual(err.exception.code, 0)
            call.assert_called_with(["godot", "--path", "."])

    def test_godot_missing_and_export_test_helpers(self) -> None:
        with (
            mock.patch("gd.shutil.which", return_value=None),
            self.assertRaises(SystemExit) as err,
        ):
            gd.cmd_run(argparse.Namespace(godot="godot"))
        self.assertIn("Godot not found", str(err.exception))

        with self.assertRaises(SystemExit) as err:
            gd.cmd_test(argparse.Namespace())
        self.assertIn("no GDScript test runner configured", str(err.exception))

        Path("project.godot").write_text("[gd]\ntest_command=python3 --version\n")
        Path("export_presets.cfg").write_text('[preset.0]\nname="Linux"\n')
        self.assertEqual(gd.export_presets(), ["Linux"])
        with (
            mock.patch("gd.subprocess.call", return_value=0) as call,
            self.assertRaises(SystemExit) as err,
        ):
            gd.cmd_test(argparse.Namespace())
        self.assertEqual(err.exception.code, 0)
        call.assert_called_with(["python3", "--version"])
        with (
            mock.patch("gd.shutil.which", return_value="/bin/godot"),
            mock.patch("gd.subprocess.call", return_value=0) as call,
            self.assertRaises(SystemExit) as err,
        ):
            gd.cmd_export_run(
                argparse.Namespace(
                    godot="godot", preset="Linux", output="build/game.x86_64"
                )
            )
        self.assertEqual(err.exception.code, 0)
        call.assert_called_with(
            [
                "godot",
                "--headless",
                "--path",
                ".",
                "--export-release",
                "Linux",
                "build/game.x86_64",
            ]
        )

    def test_scene_tui_helpers(self) -> None:
        Path("Main.tscn").write_text(
            "[gd_scene format=3]\n\n"
            '[node name="Main" type="Node2D"]\n\n'
            '[node name="Player" type="CharacterBody2D" parent="."]\n'
            "position = Vector2(1, 2)\n\n"
            '[node name="Sprite" type="Sprite2D" parent="Player"]\n',
            encoding="utf-8",
        )
        lines = gd.read_lines(Path("Main.tscn"))

        self.assertEqual(
            gd.scene_tree_rows(lines),
            [
                ("Main", "Main (Node2D)"),
                ("Player", "Player (CharacterBody2D)"),
                ("Player/Sprite", "  Sprite (Sprite2D)"),
            ],
        )
        self.assertEqual(gd.node_props(lines, "Player"), ["position = Vector2(1, 2)"])

    def test_map_ascii_new_check_compile(self) -> None:
        gd.cmd_map_new(
            argparse.Namespace(path="Level1", width=3, height=2, fill=".", force=False)
        )
        self.assertEqual(Path("levels/Level1.map").read_text(), "...\n...\n")
        Path("levels/Level1.map").write_text("P#.\n..#\n")
        Path("levels/map.legend").write_text(
            "[legend]\n#=StaticBody2D\nP=CharacterBody2D\n"
        )

        gd.cmd_map_check(argparse.Namespace(path="Level1"))
        gd.cmd_map_compile(
            argparse.Namespace(map="Level1", scene="LevelScene", tile_size=8)
        )

        text = Path("LevelScene.tscn").read_text()
        self.assertIn('[node name="LevelScene" type="Node2D"]', text)
        self.assertIn('[node name="P_0_0" type="CharacterBody2D" parent="."]', text)
        self.assertIn('[node name="#_1_0" type="StaticBody2D" parent="."]', text)
        self.assertIn("position = Vector2(8, 0)", text)
        self.assertIn("position = Vector2(16, 8)", text)

    def test_map_check_fails_on_ragged_map(self) -> None:
        Path("levels").mkdir()
        Path("levels/bad.map").write_text("..\n...\n")
        with self.assertRaises(SystemExit) as err:
            gd.cmd_map_check(argparse.Namespace(path="bad"))
        self.assertEqual(err.exception.code, 1)

    def test_map_edit_helpers_and_tilemap_message(self) -> None:
        self.assertEqual(gd.set_map_tile(["..", ".."], 1, 0, "P"), [".P", ".."])
        self.assertEqual(gd.set_map_tile([".."], 9, 0, "P"), [".."])
        with self.assertRaises(ValueError):
            gd.set_map_tile([".."], 0, 0, "bad")
        with self.assertRaises(SystemExit) as err:
            gd.cmd_tilemap_edit(argparse.Namespace(scene="Main", node="TileMap"))
        self.assertIn("gd map edit", str(err.exception))

    def test_real_cli_smoke(self) -> None:
        cli = Path(gd.__file__).resolve()
        for args in (
            ["project", "init", "Demo"],
            ["scene", "create", "Main"],
            ["node", "add", "Main", "Player", "--type", "CharacterBody2D"],
            ["script", "create", "player.gd", "--extends", "CharacterBody2D"],
            ["script", "attach", "Main", "Player", "player.gd"],
            ["check"],
        ):
            subprocess.run([sys.executable, cli, *args], check=True)

        tree = subprocess.check_output([sys.executable, cli, "tree", "Main"], text=True)
        scenes = subprocess.check_output(
            [sys.executable, cli, "scene", "list"], text=True
        )
        scripts = subprocess.check_output(
            [sys.executable, cli, "script", "list"], text=True
        )
        self.assertIn("Player (CharacterBody2D)", tree)
        self.assertIn("Main.tscn", scenes)
        self.assertIn("player.gd", scripts)


if __name__ == "__main__":
    unittest.main()
