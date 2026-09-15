"""The in-editor GDScript scanner must agree with scripts/api_guard.py.

addons/godot_guard/api_guard.gd is a port, so it can drift. This runs both over
the same fixtures and asserts the findings are identical, rule for rule and
column for column. Skipped when no Godot binary is available (set GODOT_BIN).
"""
import json
import os
import shutil
import subprocess
import tempfile
import unittest

from _common import FIXTURES, GODOT_BIN, KIT_DIR

import api_guard

ADDON = os.path.join(KIT_DIR, "addons", "godot_guard")
PARITY_GD = os.path.join(KIT_DIR, "tests", "godot", "parity.gd")
FILES = [
    os.path.join(FIXTURES, "godot3_sample.gd"),
    os.path.join(FIXTURES, "godot4_clean.gd"),
    os.path.join(FIXTURES, "legacy_tilemap.tscn"),
]

PROJECT_GODOT = """config_version=5

[application]

config/name="godot-guard-parity"
config/features=PackedStringArray("4.7", "GL Compatibility")
"""


def key(finding):
    return (os.path.basename(finding["file"]), finding["line"], finding["col"],
            finding["rule"], finding["severity"], finding["match"])


@unittest.skipUnless(GODOT_BIN and os.path.isdir(ADDON), "no Godot binary or no addon")
class AddonParity(unittest.TestCase):
    def setUp(self):
        self.project = tempfile.mkdtemp(prefix="guard-parity-")
        shutil.copytree(ADDON, os.path.join(self.project, "addons", "godot_guard"))
        os.makedirs(os.path.join(self.project, "tests", "godot"))
        shutil.copy(PARITY_GD, os.path.join(self.project, "tests", "godot", "parity.gd"))
        with open(os.path.join(self.project, "project.godot"), "w", encoding="utf-8") as fh:
            fh.write(PROJECT_GODOT)

    def tearDown(self):
        shutil.rmtree(self.project, ignore_errors=True)

    def gdscript_scan(self):
        proc = subprocess.run(
            [GODOT_BIN, "--headless", "--path", self.project, "-s", "tests/godot/parity.gd", "--"] + FILES,
            capture_output=True, text=True, timeout=300)
        self.assertIn("###JSON###", proc.stdout, "parity.gd produced no JSON:\n%s%s" % (proc.stdout, proc.stderr))
        payload = proc.stdout.split("###JSON###", 1)[1].strip().splitlines()[0]
        return json.loads(payload)

    def test_same_rules_and_findings(self):
        gd = self.gdscript_scan()
        rules, _ = api_guard.load_rules(None)
        py_findings = api_guard.scan_files(FILES, rules)

        self.assertEqual(gd["rules"], len(rules), "rule count differs between the two scanners")
        self.assertEqual(sorted(key(f) for f in py_findings),
                         sorted(key(f) for f in gd["findings"]),
                         "the editor addon and the CLI scanner disagree")
        self.assertTrue(py_findings, "fixtures should produce findings")


if __name__ == "__main__":
    unittest.main()
