"""The free->paid footer: it must appear exactly when a check found something,
and must stay out of the way everywhere else (clean runs, JSON, hooks, Pro)."""
import json
import os
import shutil
import sys
import tempfile
import unittest

import _common as C

sys.path.insert(0, C.SCRIPTS)
import upgrade_hint  # noqa: E402

STORE = "brocolriri.gumroad.com"
DIRTY = os.path.join(C.FIXTURES, "godot3_sample.gd")


class TestFooterText(unittest.TestCase):
    def test_shown_when_something_was_found(self):
        t = upgrade_hint.footer("findings", 8)
        self.assertIn(STORE, t)
        self.assertIn("8 issues", t)
        for skill in ("godot-verify", "uid-keeper", "tscn-surgeon"):
            self.assertIn(skill, t)

    def test_silent_on_clean_run(self):
        self.assertEqual(upgrade_hint.footer("findings", 0), "")

    def test_singular_plural(self):
        self.assertIn("1 issue ", upgrade_hint.footer("findings", 1))

    def test_verify_failed_variant(self):
        self.assertIn(STORE, upgrade_hint.footer("verify-failed"))

    def test_unknown_kind_is_silent(self):
        self.assertEqual(upgrade_hint.footer("whatever", 5), "")

    def test_env_var_silences(self):
        os.environ["GODOT_GUARD_NO_HINT"] = "1"
        try:
            self.assertEqual(upgrade_hint.footer("findings", 8), "")
        finally:
            del os.environ["GODOT_GUARD_NO_HINT"]

    def test_silent_for_pro_owners(self):
        """Pro ships the free scripts next to pro-only skills -> no nagging."""
        tmp = tempfile.mkdtemp()
        try:
            os.makedirs(os.path.join(tmp, "scripts"))
            os.makedirs(os.path.join(tmp, "skills", "godot-verify"))
            fake = os.path.join(tmp, "scripts", "upgrade_hint.py")
            open(fake, "w").close()
            self.assertTrue(upgrade_hint.silent(fake))
            self.assertEqual(upgrade_hint.footer("findings", 8, fake), "")
        finally:
            shutil.rmtree(tmp)

    def test_paid_marker_silences(self):
        """Any paid build drops .godot-guard-paid; the footer must respect it."""
        for depth in (0, 1, 2):
            tmp = tempfile.mkdtemp()
            try:
                base = os.path.join(tmp, "pkg", "godot-guard")
                os.makedirs(os.path.join(base, "scripts"))
                fake = os.path.join(base, "scripts", "upgrade_hint.py")
                open(fake, "w").close()
                marker_dir = [os.path.join(base, "scripts"), base, os.path.join(tmp, "pkg")][depth]
                open(os.path.join(marker_dir, ".godot-guard-paid"), "w").close()
                self.assertTrue(upgrade_hint.silent(fake), "depth %d" % depth)
            finally:
                shutil.rmtree(tmp)

    def test_shown_for_free_layout(self):
        tmp = tempfile.mkdtemp()
        try:
            os.makedirs(os.path.join(tmp, "scripts"))
            os.makedirs(os.path.join(tmp, "skills", "scene-map"))
            fake = os.path.join(tmp, "scripts", "upgrade_hint.py")
            open(fake, "w").close()
            self.assertFalse(upgrade_hint.silent(fake))
            self.assertIn(STORE, upgrade_hint.footer("findings", 3, fake))
        finally:
            shutil.rmtree(tmp)


class TestDoesNotCorruptOutput(unittest.TestCase):
    def test_api_guard_text_mode_has_footer(self):
        _, out, _ = C.run("api_guard.py", DIRTY)
        self.assertIn(STORE, out)

    def test_api_guard_json_stays_parseable(self):
        _, out, _ = C.run("api_guard.py", DIRTY, "--json")
        json.loads(out)  # would raise if the footer leaked in
        self.assertNotIn(STORE, out)

    def test_hook_mode_has_no_footer(self):
        payload = json.dumps({"tool_input": {"file_path": DIRTY}})
        _, out, err = C.run("api_guard.py", "--hook", stdin=payload)
        self.assertNotIn(STORE, out + err)


if __name__ == "__main__":
    unittest.main()
