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

    def test_spriteframes_from_sheet(self) -> None:
        Path("assets").mkdir()
        Path("assets/player.png").write_bytes(b"png")
        gd.cmd_scene_create(argparse.Namespace(path="Main", root="Node2D", force=False))
        gd.cmd_node_add(
            argparse.Namespace(
                scene="Main", name="Anim", type="AnimatedSprite2D", parent="."
            )
        )

        gd.cmd_spriteframes_from_sheet(
            argparse.Namespace(
                scene="Main",
                node="Anim",
                image="assets/player.png",
                anim="walk",
                frame="16x16",
                count=3,
                fps=12.0,
                offset="4,8",
                columns=2,
                out=None,
            )
        )

        scene = self.scene()
        frames = Path("assets/player.spriteframes.tres").read_text()
        self.assertIn(
            '[ext_resource type="SpriteFrames" path="res://assets/player.spriteframes.tres" id="1"]',
            scene,
        )
        self.assertIn('sprite_frames = ExtResource("1")', scene)
        self.assertIn('[gd_resource type="SpriteFrames"', frames)
        self.assertIn('path="res://assets/player.png"', frames)
        self.assertIn('name": &"walk"', frames)
        self.assertIn('speed": 12.0', frames)
        self.assertIn("region = Rect2(4, 8, 16, 16)", frames)
        self.assertIn("region = Rect2(20, 8, 16, 16)", frames)
        self.assertIn("region = Rect2(4, 24, 16, 16)", frames)

    def test_spriteframes_requires_animatedsprite2d(self) -> None:
        Path("sprite.png").write_bytes(b"png")
        gd.cmd_scene_create(argparse.Namespace(path="Main", root="Node2D", force=False))
        with self.assertRaises(SystemExit) as err:
            gd.cmd_spriteframes_from_sheet(
                argparse.Namespace(
                    scene="Main",
                    node="Main",
                    image="sprite.png",
                    anim="idle",
                    frame="16x16",
                    count=1,
                    fps=8.0,
                    offset="0,0",
                    columns=None,
                    out=None,
                )
            )
        self.assertIn("not AnimatedSprite2D", str(err.exception))

    def test_asset_refs_and_check(self) -> None:
        Path("assets").mkdir()
        Path("assets/ok.png").write_bytes(b"png")
        Path("Main.tscn").write_text(
            "[gd_scene format=3]\n\n"
            '[ext_resource type="Texture2D" path="res://assets/ok.png" id="1"]\n'
            '[ext_resource type="Texture2D" path="res://assets/missing.png" id="2"]\n',
            encoding="utf-8",
        )

        self.assertEqual(
            gd.asset_refs(), ["res://assets/missing.png", "res://assets/ok.png"]
        )
        with self.assertRaises(SystemExit) as err:
            gd.cmd_asset_check(argparse.Namespace())
        self.assertEqual(err.exception.code, 1)
        Path("assets/missing.png").write_bytes(b"png")
        gd.cmd_asset_check(argparse.Namespace())

    def test_gameplay_node_commands(self) -> None:
        gd.cmd_scene_create(argparse.Namespace(path="Main", root="Node2D", force=False))
        gd.cmd_scene_create(
            argparse.Namespace(path="Enemy", root="Node2D", force=False)
        )
        Path("sfx.ogg").write_bytes(b"ogg")
        gd.cmd_node_add(
            argparse.Namespace(
                scene="Main", name="Player", type="CharacterBody2D", parent="."
            )
        )

        gd.cmd_scene_instance(
            argparse.Namespace(
                scene="Main", name="Mob", packed="Enemy.tscn", parent="."
            )
        )
        gd.cmd_collision_add(
            argparse.Namespace(
                scene="Main", node="Player", shape="rectangle", size="8x16"
            )
        )
        gd.cmd_collision_add(
            argparse.Namespace(scene="Main", node="Player", shape="circle", size="4.5")
        )
        gd.cmd_collision_add(
            argparse.Namespace(
                scene="Main", node="Player", shape="capsule", size="4,12"
            )
        )
        gd.cmd_camera_add(
            argparse.Namespace(
                scene="Main", name="Cam", parent=".", current=True, zoom=2.0
            )
        )
        gd.cmd_audio_add(
            argparse.Namespace(
                scene="Main", name="Jump", file="sfx.ogg", parent="Player"
            )
        )

        text = self.scene()
        self.assertIn(
            '[ext_resource type="PackedScene" path="res://Enemy.tscn" id="1"]', text
        )
        self.assertIn('[node name="Mob" parent="." instance=ExtResource("1")]', text)
        self.assertIn(
            '[sub_resource type="RectangleShape2D" id="RectangleShape2D_1"]', text
        )
        self.assertIn("size = Vector2(8, 16)", text)
        self.assertIn("radius = 4.5", text)
        self.assertIn("height = 12.0", text)
        self.assertIn(
            '[node name="Collision" type="CollisionShape2D" parent="Player"]', text
        )
        self.assertIn(
            '[node name="Collision2" type="CollisionShape2D" parent="Player"]', text
        )
        self.assertIn(
            '[node name="Collision3" type="CollisionShape2D" parent="Player"]', text
        )
        self.assertIn("current = true", text)
        self.assertIn("zoom = Vector2(2.0, 2.0)", text)
        self.assertIn('[ext_resource type="AudioStream" path="res://sfx.ogg"', text)
        self.assertIn("stream = ExtResource(", text)
        self.assertIn("load_steps=", text.splitlines()[0])

    def test_group_and_signal_list(self) -> None:
        gd.cmd_scene_create(argparse.Namespace(path="Main", root="Node2D", force=False))
        gd.cmd_node_add(
            argparse.Namespace(
                scene="Main", name="Player", type="CharacterBody2D", parent="."
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

        gd.cmd_group_add(
            argparse.Namespace(scene="Main", node="Player", group="enemies")
        )
        self.assertIn('groups=["enemies"]', self.scene())
        gd.cmd_group_add(
            argparse.Namespace(scene="Main", node="Player", group="controllable")
        )
        self.assertIn('groups=["enemies", "controllable"]', self.scene())
        gd.cmd_group_remove(
            argparse.Namespace(scene="Main", node="Player", group="enemies")
        )
        self.assertIn('groups=["controllable"]', self.scene())

        lines = gd.read_lines(Path("Main.tscn"))
        node = gd.find_node(lines, "Player")
        self.assertEqual(gd.node_groups(lines, node), ["controllable"])

        import io
        from contextlib import redirect_stdout

        buf = io.StringIO()
        with redirect_stdout(buf):
            gd.cmd_signal_list(argparse.Namespace(scene="Main"))
        buf = io.StringIO()
        with redirect_stdout(buf):
            gd.cmd_signal_list(argparse.Namespace(scene="Main"))
        self.assertIn("Player.ready -> Player:_on_ready", buf.getvalue())

    def test_templates_and_productivity(self) -> None:
        gd.cmd_input_preset(argparse.Namespace(name="platformer"))
        gd.cmd_project_scaffold(argparse.Namespace())
        for d in ("scenes", "scripts", "assets", "levels"):
            self.assertTrue(Path(d).is_dir())
        project = Path("project.godot")
        project.write_text("[input]\n")
        gd.cmd_input_preset(argparse.Namespace(name="topdown"))
        text = project.read_text()
        for action in ("move_up", "move_down", "move_left", "move_right"):
            self.assertIn(action, text)

        gd.cmd_script_create(
            argparse.Namespace(
                path="scripts/p.gd", template="platformer2d", extends=None, force=False
            )
        )
        self.assertIn("move_and_slide()", Path("scripts/p.gd").read_text())

    def test_template_platformer_and_doctor_docs(self) -> None:
        import io
        from contextlib import redirect_stdout

        gd.cmd_template(argparse.Namespace(name="platformer"))
        gd.cmd_check(argparse.Namespace())
        scene = Path("Main.tscn").read_text()
        self.assertIn('[node name="Player" type="CharacterBody2D" parent="."]', scene)
        self.assertIn("Camera2D", scene)
        self.assertIn("script = ExtResource", scene)

        buf = io.StringIO()
        with redirect_stdout(buf):
            gd.cmd_doctor(argparse.Namespace())
        report = buf.getvalue()
        self.assertIn("ok: main_scene", report)
        self.assertIn("godot-scene-lsp", report)
        self.assertIn("luisfer-cli/godot-scene-lsp", report)

        buf = io.StringIO()
        with redirect_stdout(buf):
            gd.cmd_docs(argparse.Namespace(cls="CharacterBody2D", open=False))
        self.assertIn("class_characterbody2d.html", buf.getvalue())

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
