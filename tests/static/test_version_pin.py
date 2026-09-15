import json
import os
import tempfile
import unittest

from _common import EXAMPLE, FIXTURES, GODOT_BIN, run

import version_pin

PROJ = os.path.join(FIXTURES, "proj")


class VersionPinTests(unittest.TestCase):
    def test_compare(self):
        self.assertEqual(version_pin.compare("4.7", "4.7.2"), "match")
        self.assertEqual(version_pin.compare("4.7", "4.6.1"), "mismatch")
        self.assertEqual(version_pin.compare("4.7", None), "unknown")
        self.assertEqual(version_pin.compare(None, "4.7.2"), "no-feature")

    def test_block_content_without_binary(self):
        code, out, err = run("version_pin.py", PROJ, "--no-run")
        self.assertEqual(code, 0, err)
        self.assertIn(version_pin.BEGIN, out)
        self.assertIn(version_pin.END, out)
        self.assertIn("**Godot 4.7**", out)
        self.assertIn("Renderer: forward_plus", out)
        self.assertIn("Main scene: res://scenes/main.tscn", out)
        self.assertIn("`Events` -> res://autoload/events.gd", out)
        self.assertIn("Delta table for this minor:", out)
        self.assertIn("### Rules for the agent", out)
        rules = [l for l in out.splitlines() if l[:2].rstrip(".").isdigit()]
        self.assertTrue(5 <= len(rules) <= 8, rules)
        self.assertIn("verify.py", out)
        self.assertIn("scene-map", out)
        self.assertIn(".uid", out)

    def test_write_is_idempotent(self):
        with tempfile.TemporaryDirectory() as td:
            md = os.path.join(td, "CLAUDE.md")
            with open(md, "w") as fh:
                fh.write("# My project\n\nSome notes.\n")
            for _ in range(2):
                code, out, err = run("version_pin.py", PROJ, "--no-run", "--write", md)
                self.assertEqual(code, 0, err)
            with open(md, encoding="utf-8") as fh:
                text = fh.read()
            self.assertEqual(text.count(version_pin.BEGIN), 1)
            self.assertEqual(text.count(version_pin.END), 1)
            self.assertTrue(text.startswith("# My project\n\nSome notes.\n"))
            # third run reports unchanged
            code, out, _ = run("version_pin.py", PROJ, "--no-run", "--write", md)
            self.assertIn("unchanged", out)
            # block in the middle of a file is replaced in place
            with open(md, "w") as fh:
                fh.write("top\n%s\nOLD\n%s\nbottom\n" % (version_pin.BEGIN, version_pin.END))
            run("version_pin.py", PROJ, "--no-run", "--write", md)
            with open(md, encoding="utf-8") as fh:
                text = fh.read()
            self.assertNotIn("OLD", text)
            self.assertTrue(text.startswith("top\n") and text.endswith("bottom\n"))
            self.assertEqual(text.count(version_pin.BEGIN), 1)

    def test_write_creates_missing_file(self):
        with tempfile.TemporaryDirectory() as td:
            md = os.path.join(td, "CLAUDE.md")
            code, _, err = run("version_pin.py", PROJ, "--no-run", "--write", md, "--json")
            self.assertEqual(code, 0, err)
            self.assertTrue(os.path.isfile(md))

    def test_mismatch_exit_code(self):
        with tempfile.TemporaryDirectory() as td:
            with open(os.path.join(td, "project.godot"), "w") as fh:
                fh.write('[application]\nconfig/features=PackedStringArray("4.3", "Mobile")\n')
            data = {"generated": "x", "project_version": "4.3", "binary": "/b", "binary_version": "4.7.2",
                    "binary_raw": "", "status": version_pin.compare("4.3", "4.7.2"), "renderer": "mobile",
                    "main_scene": None, "autoloads": [], "delta_table": "d"}
            self.assertIn("MISMATCH", version_pin.build_block(data))
            code, out, _ = run("version_pin.py", td, "--no-run", "--json")
            self.assertEqual(code, 0)
            self.assertEqual(json.loads(out)["renderer"], "Mobile")

    @unittest.skipUnless(os.path.isfile(GODOT_BIN), "Godot binary not available")
    def test_real_binary(self):
        code, out, err = run("version_pin.py", EXAMPLE, "--godot", GODOT_BIN, "--json")
        self.assertEqual(code, 0, err)
        data = json.loads(out)
        self.assertEqual(data["status"], "match")
        self.assertTrue(data["binary_version"].startswith("4.7"))
        self.assertIn("OK, binary matches pin", data["block"])

    def test_usage_error(self):
        with tempfile.TemporaryDirectory() as td:
            self.assertEqual(run("version_pin.py", td)[0], 2)
        self.assertEqual(run("version_pin.py", "--help")[0], 0)


if __name__ == "__main__":
    unittest.main()
