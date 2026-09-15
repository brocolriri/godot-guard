#!/usr/bin/env python3
"""version_pin.py - pin the Godot version in AGENTS.md from project.godot + `godot --version`.

Usage:
  version_pin.py <project_dir> [--godot BIN] [--write AGENTS.md] [--json] [--reference DIR]

Prints (or inserts into AGENTS.md, idempotently) a block between
<!-- godot-guard:begin --> / <!-- godot-guard:end --> markers.
Exit codes: 0 ok, 1 findings (version mismatch / missing features), 2 usage error.
Standard library only. Python 3.8+. Deliberately does not import godot_common.py.
"""
import argparse
import datetime
import glob
import json
import os
import re
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BEGIN, END = "<!-- godot-guard:begin -->", "<!-- godot-guard:end -->"
RULES = [
    "Target Godot {ver} only. Never use Godot 3 API (yield, .instance(), connect(\"sig\", obj, \"m\"), "
    "KinematicBody2D, export var, deg2rad ...). Run scripts/api_guard.py on every .gd you touch.",
    "Node paths come from .godot-guard/scene-map.md (regenerate with scripts/scene_map.py). Use `%Unique` / `$Path` "
    "exactly as listed; never guess node names or types.",
    "Before saying a task is done, run scripts/verify.py (import, parse, instantiate, run N frames) and quote "
    "its result. No verify run = not done.",
    "Never hand-edit or delete .uid files, and never edit .tscn/.tres unless the scene-surgeon rules allow it; "
    "keep ExtResource ids and parent= paths consistent.",
    "Use typed GDScript: explicit return types, no := on Variant, override signatures must match the parent "
    "(4.7 typed returns).",
    "Signals: `obj.sig.connect(callable)` / `sig.emit(args)`; scene connections live in [connection] lines.",
    "New autoloads are registered in project.godot [autoload]; do not create hidden singletons.",
    "When an API is uncertain for this minor version, check the delta table listed above before writing code.",
]


def parse_project(root):
    info = {"features": [], "main_scene": None, "renderer": None, "autoloads": [], "name": None}
    section = None
    with open(os.path.join(root, "project.godot"), encoding="utf-8", errors="replace") as fh:
        for line in fh:
            line = line.strip()
            if line.startswith("[") and line.endswith("]"):
                section = line[1:-1]
                continue
            m = re.match(r"([\w/]+)\s*=\s*(.*)$", line)
            if not m:
                continue
            k, v = m.group(1), m.group(2).strip('"')
            if section == "application":
                if k == "config/features":
                    info["features"] = re.findall(r'"([^"]*)"', m.group(2))
                elif k == "run/main_scene":
                    info["main_scene"] = v
                elif k == "config/name":
                    info["name"] = v
            elif section == "rendering" and k == "renderer/rendering_method":
                info["renderer"] = v
            elif section == "autoload":
                info["autoloads"].append((k, v.lstrip("*")))
    return info


def feature_version(features):
    for f in features:
        if re.match(r"^\d+\.\d+$", f):
            return f
    return None


def feature_renderer(features):
    for f in features:
        if f in ("Forward Plus", "Mobile", "GL Compatibility"):
            return f
    return None


def find_godot(explicit=None):
    """--godot > $GODOT_BIN > PATH > common install locations. Returns path or None."""
    cands = [c for c in (explicit, os.environ.get("GODOT_BIN")) if c]
    for name in ("godot4", "godot", "Godot", "godot4-mono", "godot-mono"):
        p = shutil.which(name)
        if p:
            cands.append(p)
    home = os.path.expanduser("~")
    patterns = [
        os.path.join(home, "godot", "Godot*"), os.path.join(home, ".local", "bin", "Godot*"),
        os.path.join(home, "bin", "Godot*"), "/opt/godot/Godot*", "/usr/local/bin/Godot*",
        "/Applications/Godot.app/Contents/MacOS/Godot", os.path.join(home, "Applications", "Godot.app", "Contents", "MacOS", "Godot"),
        os.path.join(os.environ.get("ProgramFiles", r"C:\Program Files"), "Godot", "Godot*.exe"),
        os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "Godot", "Godot*.exe"),
        "/mnt/c/Program Files/Godot/Godot*.exe", "/mnt/d/Claude/_tools/godot/Godot*",
    ]
    for pat in patterns:
        cands += sorted(glob.glob(pat), reverse=True)
    for c in cands:
        if os.path.isfile(c) and os.access(c, os.X_OK):
            return c
    return None


def godot_version(binary):
    try:
        out = subprocess.run([binary, "--version"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                             timeout=30, universal_newlines=True).stdout
    except (OSError, subprocess.SubprocessError) as e:
        return None, str(e)
    for line in reversed(out.splitlines()):
        m = re.match(r"\s*(\d+\.\d+(?:\.\d+)?)[.\-]?(\w+)?", line)
        if m:
            return m.group(1), line.strip()
    return None, out.strip()[-200:]


def compare(project_ver, binary_ver):
    """'4.7' vs '4.7.2' -> 'match'; different minor -> 'mismatch'; None -> 'unknown'."""
    if not project_ver:
        return "no-feature"
    if not binary_ver:
        return "unknown"
    return "match" if ".".join(binary_ver.split(".")[:2]) == project_ver else "mismatch"


def delta_pointer(ref_dir, minor):
    if not minor:
        return "reference/deltas.json (no version pinned)"
    names = ["deltas_%s.md" % minor, "deltas_%s.json" % minor]
    names += sorted(os.path.basename(p) for p in glob.glob(os.path.join(ref_dir, "deltas_*-%s.md" % minor)))
    for pat in sorted(glob.glob(os.path.join(ref_dir, "deltas_*-*.md"))):
        m = re.search(r"deltas_(\d+\.\d+)-(\d+\.\d+)\.md$", pat)
        if m and float(m.group(1)) <= float(minor) <= float(m.group(2)):
            names.append(os.path.basename(pat))
    for n in names:
        if os.path.isfile(os.path.join(ref_dir, n)):
            return "reference/%s (rows tagged %s)" % (n, minor)
    if os.path.isfile(os.path.join(ref_dir, "deltas.json")):
        return "reference/deltas.json (filter rows where version == %s)" % minor
    return "reference/deltas_%s.md (not found yet - generate the reference tables)" % minor


def build_block(data):
    lines = [BEGIN, "## Godot version pin (godot-guard, generated %s)" % data["generated"]]
    pin = data["project_version"] or "?"
    bin_txt = ("%s (%s)" % (data["binary_version"], data["binary"])) if data["binary_version"] else \
        ("not found - set GODOT_BIN" if not data["binary"] else "unreadable: %s" % data["binary_raw"])
    status = {"match": "OK, binary matches pin", "mismatch": "MISMATCH - binary minor != project pin, fix before coding",
              "unknown": "unverified", "no-feature": "project.godot has no version feature"}[data["status"]]
    lines += ["- Pinned version: **Godot %s** (project.godot config/features) - binary: %s - %s" % (pin, bin_txt, status),
              "- Renderer: %s" % (data["renderer"] or "?"),
              "- Main scene: %s" % (data["main_scene"] or "?"),
              "- Autoloads: %s" % (", ".join("`%s` -> %s" % a for a in data["autoloads"]) or "(none)"),
              "- Delta table for this minor: %s" % data["delta_table"],
              "", "### Rules for the agent"]
    lines += ["%d. %s" % (i, r.format(ver=pin)) for i, r in enumerate(RULES, 1)]
    lines.append(END)
    return "\n".join(lines)


def upsert_block(text, block):
    if BEGIN in text and END in text:
        b = text.index(BEGIN)
        e = text.index(END, b) + len(END)
        return text[:b] + block + text[e:]
    sep = "" if not text else ("\n" if text.endswith("\n") else "\n\n")
    return text + sep + block + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser(description="Pin Godot version + agent rules into AGENTS.md.")
    ap.add_argument("project_dir")
    ap.add_argument("--godot", help="Godot binary (default: $GODOT_BIN, PATH, common locations)")
    ap.add_argument("--write", metavar="AGENTS.md", help="insert/replace the block in this file")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--reference", default=os.path.normpath(os.path.join(HERE, "..", "reference")),
                    help="directory holding deltas_*.md / deltas.json")
    ap.add_argument("--no-run", action="store_true", help="do not execute the Godot binary")
    args = ap.parse_args(argv)
    pg = os.path.join(args.project_dir, "project.godot")
    if not os.path.isfile(pg):
        ap.exit(2, "error: no project.godot in %s\n" % args.project_dir)
    proj = parse_project(args.project_dir)
    pver = feature_version(proj["features"])
    binary = None if args.no_run else find_godot(args.godot)
    bver, raw = (godot_version(binary) if binary else (None, ""))
    status = compare(pver, bver)
    data = {"generated": datetime.date.today().isoformat(), "project": proj["name"], "project_version": pver,
            "renderer": proj["renderer"] or feature_renderer(proj["features"]), "features": proj["features"],
            "main_scene": proj["main_scene"], "autoloads": proj["autoloads"], "binary": binary,
            "binary_version": bver, "binary_raw": raw, "status": status,
            "delta_table": delta_pointer(args.reference, pver)}
    block = build_block(data)
    data["block"] = block
    if args.write:
        old = ""
        if os.path.isfile(args.write):
            with open(args.write, encoding="utf-8") as fh:
                old = fh.read()
        new = upsert_block(old, block)
        if new != old:
            with open(args.write, "w", encoding="utf-8") as fh:
                fh.write(new)
        data["written"] = args.write
        data["changed"] = new != old
    if args.json:
        print(json.dumps(data, indent=2))
    elif args.write:
        print("%s %s: Godot %s vs binary %s -> %s" % ("updated" if data["changed"] else "unchanged", args.write,
                                                      pver, bver or "?", status))
    else:
        print(block)
    return 1 if status in ("mismatch", "no-feature") else 0


if __name__ == "__main__":
    sys.exit(main())
