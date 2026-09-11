import argparse
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

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
