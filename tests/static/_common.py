"""Shared helpers for tests/static."""
import os
import subprocess
import sys

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
KIT_DIR = os.path.normpath(os.path.join(TESTS_DIR, "..", ".."))
SCRIPTS = os.path.join(KIT_DIR, "plugin", "scripts")
if not os.path.isdir(SCRIPTS):  # repo layout: scripts/ at the repo root
    SCRIPTS = os.path.join(KIT_DIR, "scripts")
FIXTURES = os.path.join(TESTS_DIR, "fixtures")
EXAMPLE = os.path.join(KIT_DIR, "example")
_DEFAULT_GODOT = "/mnt/d/Claude/_tools/godot/Godot_v4.7.2-stable_linux.x86_64"
GODOT_BIN = os.environ.get("GODOT_BIN") or (_DEFAULT_GODOT if os.path.exists(_DEFAULT_GODOT) else "")

if SCRIPTS not in sys.path:
    sys.path.insert(0, SCRIPTS)


def run(script, *args, stdin=None):
    """Run a plugin script; returns (exit_code, stdout, stderr)."""
    p = subprocess.run([sys.executable, os.path.join(SCRIPTS, script)] + list(args), input=stdin,
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True, timeout=120)
    return p.returncode, p.stdout, p.stderr
