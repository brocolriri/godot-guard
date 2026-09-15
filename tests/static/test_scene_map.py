import json
import os
import tempfile
import unittest

from _common import EXAMPLE, FIXTURES, run

PROJ = os.path.join(FIXTURES, "proj")


class SceneMapTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.code, cls.out, cls.err = run("scene_map.py", PROJ)

    def test_exit_ok(self):
        self.assertEqual(self.code, 0, self.err)

    def test_header(self):
        self.assertIn("Use these paths verbatim; do not guess node names.", self.out)
        self.assertIn("Generated:", self.out)
        self.assertIn("features: 4.7, Forward Plus", self.out)

    def test_unique_and_dollar_paths(self):
        self.assertIn("`%Player`", self.out)
        self.assertIn("`$Enemies`", self.out)
        self.assertIn("`$Player`", self.out)

    def test_nested_instance_expanded(self):
        # Weapon instanced inside player.tscn, which is instanced inside main.tscn
        self.assertIn("`$Player/Weapon/Muzzle`", self.out)
        self.assertIn("Player : CharacterBody2D  %Player  instance=res://scenes/player.tscn", self.out)
        self.assertIn("(class_name Player)", self.out)

    def test_inner_unique_only_in_own_scene(self):
        self.assertIn("`%Hurtbox` in res://scenes/player.tscn", self.out)

    def test_names_with_spaces_and_quotes(self):
        self.assertIn('`%"Start Button"`', self.out)
        self.assertIn('`$"UI/Start Button"`', self.out)
        self.assertIn('`$"Enemies/Big Bad \\"Boss\\""`', self.out)

    def test_signal_table(self):
        self.assertIn("| Signal | From | To | Method |", self.out)
        self.assertIn('| pressed | `$"UI/Start Button"` | `self` | `_on_start_button_pressed` |', self.out)
        self.assertIn("| died | `$Player` | `self` | `_on_player_died` | flags=3 |", self.out)

    def test_groups_and_autoloads(self):
        self.assertIn("- `player`: `Player`", self.out)
        self.assertIn("- `boss`:", self.out)
        self.assertIn("`Events` -> res://autoload/events.gd  signals: `player_hit(damage: int)`", self.out)

    def test_script_index(self):
        self.assertIn("class_name `Player`", self.out)
        self.assertIn("signals: `died()`", self.out)
        self.assertIn("@export: `speed`, `lives`", self.out)
        self.assertIn("func: `_ready`, `make`", self.out)

    def test_json_mode(self):
        code, out, _ = run("scene_map.py", PROJ, "--json")
        self.assertEqual(code, 0)
        data = json.loads(out)
        files = [s["file"] for s in data["scenes"]]
        self.assertIn("scenes/main.tscn", files)
        main = data["scenes"][files.index("scenes/main.tscn")]
        player = next(n for n in main["nodes"] if n["path"] == "Player")
        self.assertEqual(player["access"][0], "%Player")
        self.assertEqual(player["type"], "CharacterBody2D")
        self.assertTrue(player["unique"])
        self.assertEqual(len(main["connections"]), 2)
        self.assertEqual(data["problem_count"], 0)

    def test_single_file_and_out(self):
        with tempfile.TemporaryDirectory() as td:
            out_path = os.path.join(td, ".claude", "scene-map.md")
            code, out, err = run("scene_map.py", os.path.join(PROJ, "scenes", "main.tscn"), "--out", out_path)
            self.assertEqual(code, 0, err)
            self.assertTrue(os.path.isfile(out_path))
            with open(out_path, encoding="utf-8") as fh:
                text = fh.read()
            self.assertIn("## scenes/main.tscn", text)
            self.assertNotIn("## scenes/weapon.tscn", text)

    def test_example_project(self):
        code, out, err = run("scene_map.py", EXAMPLE)
        self.assertEqual(code, 0, err)
        self.assertIn("`%Player`", out)
        self.assertIn("`$Enemies/Enemy`", out)
        self.assertIn("Ground : TileMapLayer", out)
        self.assertIn("`Events` ->", out)

    def test_usage_errors(self):
        self.assertEqual(run("scene_map.py", os.path.join(FIXTURES, "nope"))[0], 2)
        self.assertEqual(run("scene_map.py", os.path.join(FIXTURES, "godot4_clean.gd"))[0], 2)
        self.assertEqual(run("scene_map.py", "--help")[0], 0)


if __name__ == "__main__":
    unittest.main()
