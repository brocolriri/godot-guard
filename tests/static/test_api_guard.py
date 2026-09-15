import json
import os
import tempfile
import unittest

from _common import FIXTURES, run

import api_guard

G3 = os.path.join(FIXTURES, "godot3_sample.gd")
CLEAN = os.path.join(FIXTURES, "godot4_clean.gd")
TILEMAP = os.path.join(FIXTURES, "legacy_tilemap.tscn")

SEEDED = {  # rule id -> line number in godot3_sample.gd
    "tool_keyword": 1, "kinematic_body": 2, "export_keyword": 4, "onready_keyword": 5, "pool_array": 6,
    "funcref": 7, "yield": 13, "instance_call": 14, "connect_string": 15, "deg2rad": 16, "rand_range": 16,
    "set_shader_param": 17, "os_ticks": 18, "empty_call": 19, "signal_any": 21, "move_and_slide_arg": 28,
    "godot3_type_names": 31,
}


ALIASES = {"kinematic_body": {"kinematicbody"}, "yield": {"yield_call"}, "pool_array": {"pool_arrays"},
           "connect_string": {"connect_string_3arg"}, "move_and_slide_arg": {"move_and_slide_args"},
           "godot3_type_names": {"sprite_bare"}, "signal_any": {"signal_any_hallucination"},
           "empty_call": {"array_empty"}, "tilemap_node": {"tilemap_node"}}


def canon(rule):
    for k, v in ALIASES.items():
        if rule == k or rule in v:
            return k
    return rule


class ApiGuardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rules, _ = api_guard.load_rules(None)
        with open(G3, encoding="utf-8") as fh:
            cls.findings = api_guard.scan_text(fh.read(), G3, cls.rules)

    def test_each_seeded_idiom_found(self):
        got = {(f["rule"], f["line"]) for f in self.findings}
        for rule, line in SEEDED.items():
            self.assertIn((canon(rule), line), {(canon(r), l) for r, l in got}, "missing %s at line %d" % (rule, line))

    def test_commented_and_quoted_ignored(self):
        lines = {f["line"] for f in self.findings}
        for ln in (10, 11, 12, 22, 23, 24, 25):  # comment, strings, docstring, get_node("Spatial")
            self.assertNotIn(ln, lines, "false positive on line %d" % ln)
        self.assertFalse([f for f in self.findings if f["rule"] == "spatial"])

    def test_clean_file_has_no_findings(self):
        code, out, err = run("api_guard.py", CLEAN)
        self.assertEqual(code, 0, out + err)
        self.assertIn("0 finding(s)", out)

    def test_text_output_format(self):
        code, out, _ = run("api_guard.py", G3)
        self.assertEqual(code, 1)
        self.assertRegex(out, r'godot3_sample\.gd:13:2: \[error\] yield(_call)?: yield\(get_tree\(\)\.create_timer\(1\.0\), "timeout"\)')
        self.assertRegex(out, r"fix: yield\(obj, \"signal\"\).*-> await obj\.signal")
        self.assertIn("see: https://docs.godotengine.org", out)

    def test_json_and_severity_filter(self):
        code, out, _ = run("api_guard.py", G3, TILEMAP, "--json")
        self.assertEqual(code, 1)
        data = json.loads(out)
        self.assertEqual(data["files_scanned"], 2)
        rules = {f["rule"] for f in data["findings"]}
        self.assertTrue({"tilemap_node"} & {canon(r) for r in rules}, rules)
        code, out, _ = run("api_guard.py", TILEMAP, "--severity", "error")
        self.assertEqual(code, 0, "warn-only file must pass with --severity error")

    def test_files_from_stdin(self):
        code, out, _ = run("api_guard.py", "--files-from-stdin", "--json", stdin=G3 + "\n" + CLEAN + "\n")
        self.assertEqual(code, 1)
        self.assertEqual(json.loads(out)["files_scanned"], 2)

    def test_hook_mode_blocks_on_error(self):
        payload = json.dumps({"tool_name": "Write", "tool_input": {"file_path": G3}})
        code, out, err = run("api_guard.py", "--hook", stdin=payload)
        self.assertEqual(code, 2)
        self.assertIn("godot-guard:", err)
        self.assertIn("`yield(` -> await obj.signal", err)
        payload = json.dumps({"tool_name": "Edit", "tool_input": {"file_path": CLEAN}})
        self.assertEqual(run("api_guard.py", "--hook", stdin=payload)[0], 0)
        self.assertEqual(run("api_guard.py", "--hook", stdin='{"tool_input": {"file_path": "x.md"}}')[0], 0)
        self.assertEqual(run("api_guard.py", "--hook", stdin="not json")[0], 0)

    def test_custom_rules_json(self):
        rules = {"rules": [{"id": "custom_foo", "pattern": r"\bfoo_old\(", "godot3_form": "foo_old()",
                            "godot4_form": "foo_new()", "severity": "warning", "source_url": "https://x",
                            "agent_rule": "use foo_new"}]}
        with tempfile.TemporaryDirectory() as td:
            rp = os.path.join(td, "r.json")
            gd = os.path.join(td, "t.gd")
            with open(rp, "w") as fh:
                json.dump(rules, fh)
            with open(gd, "w") as fh:
                fh.write("func _ready():\n\tfoo_old()  # foo_old() in comment\n")
            code, out, _ = run("api_guard.py", gd, "--rules", rp, "--json")
            data = json.loads(out)
        self.assertEqual(code, 1)
        self.assertEqual(len(data["findings"]), 1)
        f = data["findings"][0]
        self.assertEqual((f["rule"], f["severity"], f["fix"], f["col"]), ("custom_foo", "warn", "foo_new()", 2))

    def test_cs_comments_and_strings(self):
        rules = [api_guard._row_to_rule({"id": "cs_old", "pattern": r"\bOldApi\(", "ext": ["cs"]}, 0, "t")]
        src = 'var a = "OldApi()"; // OldApi()\n/* OldApi()\n OldApi() */ OldApi();\n'
        found = api_guard.scan_text(src, "x.cs", rules)
        self.assertEqual([(f["line"], f["col"]) for f in found], [(3, 14)])

    def test_usage_errors(self):
        self.assertEqual(run("api_guard.py")[0], 2)
        self.assertEqual(run("api_guard.py", os.path.join(FIXTURES, "missing.gd"))[0], 2)
        self.assertEqual(run("api_guard.py", "--help")[0], 0)


if __name__ == "__main__":
    unittest.main()
