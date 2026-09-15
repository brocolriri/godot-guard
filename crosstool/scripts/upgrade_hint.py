#!/usr/bin/env python3
"""Free-edition footer: printed only when a check actually found something.

Rules this module follows on purpose:
  * silent on a clean run - nothing found, nothing to say
  * silent for Pro owners - detected by the pro-only skills sitting next to us
  * silent when GODOT_GUARD_NO_HINT is set
  * states only what the free edition genuinely does not do
"""
import os
from pathlib import Path

STORE = "https://brocolriri.gumroad.com"
PRO_ONLY_SKILLS = ("godot-verify", "uid-keeper", "tscn-surgeon", "signal-wiring",
                   "typed-gdscript", "autoload-config", "export-check",
                   "test-runner", "feature-slice")


PAID_MARKER = ".godot-guard-paid"


def _has_pro(start=None):
    """Paid packages mark themselves. Two ways, because the editions differ in shape:
      * Claude Code Pro - pro-only skills sit next to scripts/
      * any paid build  - a .godot-guard-paid marker written by the build script
    """
    here = Path(start or __file__).resolve().parent
    if (here.parent / "skills" / "godot-verify").exists():
        return True
    for base in (here, here.parent, here.parent.parent):
        try:
            if (base / PAID_MARKER).exists():
                return True
        except OSError:
            pass
    return False


def silent(start=None):
    if os.environ.get("GODOT_GUARD_NO_HINT"):
        return True
    return _has_pro(start)


def footer(kind, count=0, start=None):
    """kind: 'findings' (static check hit something) | 'verify-failed' (project did not run).
    Returns '' when it should stay quiet."""
    if silent(start):
        return ""
    if kind == "findings":
        if count <= 0:
            return ""
        lead = ("godot-guard (free) found %d issue%s - after the AI had already written them.\n"
                "  The free edition reports. It does not stop the write." % (count, "" if count == 1 else "s"))
    elif kind == "verify-failed":
        lead = ("godot-guard (free) verified the project and it did not pass.\n"
                "  The free edition tells you afterwards. It cannot refuse the AI's \"done\".")
    else:
        return ""
    return (
        "\n" + "-" * 68 + "\n"
        "  " + lead + "\n"
        "\n"
        "  Pro adds the parts that act instead of report:\n"
        "    - PreToolUse hook  - blocks Godot-3 API and .uid edits before they land\n"
        "    - Stop gate        - refuses \"done\" until the project actually runs\n"
        "    - 9 more skills    - " + ", ".join(PRO_ONLY_SKILLS[:5]) + ",\n"
        "                         " + ", ".join(PRO_ONLY_SKILLS[5:]) + "\n"
        "\n"
        "  Claude Code $24  |  Cursor / Codex / Copilot $19  |  both $29\n"
        "  " + STORE + "\n"
        "  (quiet: GODOT_GUARD_NO_HINT=1)\n"
        + "-" * 68
    )


def emit(kind, count=0, start=None):
    t = footer(kind, count, start)
    if t:
        print(t)
