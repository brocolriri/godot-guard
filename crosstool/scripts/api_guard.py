#!/usr/bin/env python3
"""api_guard.py - flag Godot 3 idioms and intra-4.x drift in .gd/.cs/.tscn files.

Usage:
  api_guard.py <path...> [--rules rules.json ...] [--json] [--severity error|warn]
  api_guard.py --files-from-stdin            # one path per line (PostToolUse pipe)
  api_guard.py --hook                        # Claude Code hook JSON on stdin

Exit codes: 0 clean, 1 findings, 2 usage error.
Hook mode: exit 2 + stderr message on `error` findings (blocks), else 0.
Rules: ../reference/godot3_isms.json + deltas.json if present, else built-ins.
Standard library only. Python 3.8+.
"""
import argparse
import glob
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    import upgrade_hint
except Exception:  # never let the footer break a scan
    upgrade_hint = None

HERE = os.path.dirname(os.path.abspath(__file__))
REF_DIR = os.path.normpath(os.path.join(HERE, "..", "reference"))
MIGRATE = "https://docs.godotengine.org/en/stable/tutorials/migrating/upgrading_to_godot_4.html"
SCAN_EXT = {".gd", ".tscn", ".tres"}

# (id, pattern, old, new, severity, note, url, ext)
BUILTIN = [
    ("yield", r"\byield\s*\(", "yield(obj, \"signal\")", "await obj.signal", "error",
     "yield() is gone; use await on a signal or coroutine.", MIGRATE, ["gd"]),
    ("instance_call", r"\.instance\s*\(\s*\)", "scene.instance()", "scene.instantiate()", "error",
     "PackedScene.instance() was renamed to instantiate().", MIGRATE, ["gd"]),
    ("connect_string", r"\.connect\s*\(\s*\"[^\"]*\"\s*,\s*[A-Za-z_][\w.]*\s*,\s*\"",
     "obj.connect(\"sig\", target, \"method\")", "obj.sig.connect(target.method)", "error",
     "Signals are first-class; connect takes a Callable.", MIGRATE, ["gd"]),
    ("kinematic_body", r"\bKinematicBody(2D)?\b", "KinematicBody2D / KinematicBody",
     "CharacterBody2D / CharacterBody3D", "error", "Renamed in 4.0; velocity is now a built-in property.",
     MIGRATE, ["gd", "tscn"]),
    ("move_and_slide_arg", r"\bmove_and_slide\s*\(\s*[^)\s]", "move_and_slide(velocity)",
     "velocity = v; move_and_slide()", "error", "move_and_slide() takes no arguments in 4.x.", MIGRATE, ["gd"]),
    ("deg2rad", r"\b(deg2rad|rad2deg)\s*\(", "deg2rad() / rad2deg()", "deg_to_rad() / rad_to_deg()", "error",
     "Math helpers renamed.", MIGRATE, ["gd"]),
    ("rand_range", r"\brand_range\s*\(", "rand_range(a, b)", "randf_range(a, b) / randi_range(a, b)", "error",
     "Renamed; pick the float or int variant.", MIGRATE, ["gd"]),
    ("set_shader_param", r"\b(set|get)_shader_param\s*\(", "set_shader_param()", "set_shader_parameter()",
     "error", "ShaderMaterial API renamed.", MIGRATE, ["gd"]),
    ("export_keyword", r"^\s*export\b", "export var x", "@export var x", "error",
     "export/onready/tool are annotations in 4.x.", MIGRATE, ["gd"]),
    ("onready_keyword", r"^\s*onready\b", "onready var x", "@onready var x", "error",
     "onready is an annotation in 4.x.", MIGRATE, ["gd"]),
    ("tool_keyword", r"^\s*tool\s*$", "tool", "@tool", "error", "tool is an annotation in 4.x.", MIGRATE, ["gd"]),
    ("pool_array", r"\bPool(String|Int|Real|Vector2|Vector3|Color|Byte)Array\b", "PoolStringArray",
     "PackedStringArray (Real->Float32/Float64, Int->Int32/Int64)", "error", "Pool*Array -> Packed*Array.",
     MIGRATE, ["gd", "tscn", "tres"]),
    ("spatial", r"\bSpatial\b", "Spatial", "Node3D", "error", "Spatial renamed to Node3D.", MIGRATE,
     ["gd", "tscn"]),
    ("godot3_type_names",
     r"\b(extends|is|as)\s+(Sprite|Position2D|Position3D|Area|RigidBody|StaticBody|Particles2D|Particles"
     r"|Navigation2D|Navigation|Camera|Light2D|Listener|VisibilityNotifier2D|VisibilityNotifier|RayCast|Skeleton"
     r"|MeshInstance|Path|PathFollow|CollisionShape|CollisionPolygon|AnimatedSprite|Texture|StreamTexture)\b",
     "extends Sprite / Area / RigidBody", "Sprite2D / Area2D-3D / RigidBody2D-3D / Node3D ...", "error",
     "Bare 2D/3D type names got explicit 2D/3D suffixes in 4.0.", MIGRATE, ["gd"]),
    ("os_ticks", r"\bOS\.get_ticks_(m|u)sec\s*\(", "OS.get_ticks_msec()", "Time.get_ticks_msec()", "error",
     "Time helpers moved from OS to the Time singleton.", MIGRATE, ["gd"]),
    ("tilemap_node", r"type=\"TileMap\"", "[node type=\"TileMap\"]", "TileMapLayer (one node per layer)",
     "warn", "TileMap is deprecated since 4.3; use TileMapLayer nodes.",
     "https://docs.godotengine.org/en/stable/classes/class_tilemaplayer.html", ["tscn"]),
    ("tilemap_class", r"\b(extends|is|as|:)\s*TileMap\b", "extends TileMap", "extends TileMapLayer", "warn",
     "TileMap is deprecated since 4.3; use TileMapLayer.",
     "https://docs.godotengine.org/en/stable/classes/class_tilemaplayer.html", ["gd"]),
    ("signal_any", r"\bSignal\.any\s*\(", "Signal.any(...)", "(does not exist) await the signals you need",
     "error", "Hallucinated API: Signal has no static any().",
     "https://docs.godotengine.org/en/stable/classes/class_signal.html", ["gd"]),
    ("empty_call", r"\.empty\s*\(\s*\)", ".empty()", ".is_empty()", "error", "Renamed.", MIGRATE, ["gd"]),
    ("funcref", r"\bfuncref\s*\(", "funcref(obj, \"m\")", "obj.m  (Callable)", "error",
     "funcref() removed; Callables are first-class.", MIGRATE, ["gd"]),
]


# ---------------------------------------------------------------- rules
def _row_to_rule(row, idx, src):
    if not isinstance(row, dict):
        return None
    pat = row.get("pattern") or row.get("regex")
    if not pat:
        return None
    rid = row.get("id") or row.get("rule_id") or row.get("name") or "%s_%d" % (src, idx)
    old = row.get("godot3_form") or row.get("old") or row.get("from") or ""
    new = row.get("godot4_form") or row.get("new") or row.get("to") or row.get("fix") or ""
    sev = str(row.get("severity", "error")).lower()
    sev = "warn" if sev.startswith("warn") else ("info" if sev == "info" else "error")
    ext = row.get("ext") or row.get("applies_to") or row.get("file_types") or row.get("files")
    if isinstance(ext, str):
        ext = [ext]
    if not ext:
        ext = ["tscn", "tres"] if "type=" in pat or "[node" in pat else ["gd"]
    ext = [e.lstrip(".").lower() for e in ext]
    try:
        rx = re.compile(pat)
    except re.error as e:
        sys.stderr.write("warning: bad regex in rule %s (%s): %s\n" % (rid, src, e))
        return None
    return {"id": str(rid), "rx": rx, "pattern": pat, "old": old, "new": new, "severity": sev,
            "note": row.get("note") or row.get("agent_rule") or "", "url": row.get("source_url") or row.get("url") or "",
            "ext": ext, "source": src}


def load_rules_file(path):
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    src = os.path.splitext(os.path.basename(path))[0]
    if isinstance(data, dict):
        rows = None
        for key in ("rules", "rows", "items", "deltas", "entries"):
            if isinstance(data.get(key), list):
                rows = data[key]
                break
        if rows is None:
            rows = [dict(v, id=v.get("id", k)) for k, v in data.items() if isinstance(v, dict)]
    else:
        rows = data
    rules = [_row_to_rule(r, i, src) for i, r in enumerate(rows)]
    return [r for r in rules if r]


def load_rules(explicit):
    files = list(explicit or [])
    if not files:
        files = [p for p in (os.path.join(REF_DIR, "godot3_isms.json"), os.path.join(REF_DIR, "deltas.json"))
                 if os.path.isfile(p)]
    rules = []
    for f in files:
        try:
            rules += load_rules_file(f)
        except (OSError, ValueError) as e:
            sys.stderr.write("warning: cannot load rules %s: %s\n" % (f, e))
    if not rules:
        rules = [_row_to_rule(dict(zip(("id", "pattern", "old", "new", "severity", "note", "url", "ext"), b)), i,
                              "builtin") for i, b in enumerate(BUILTIN)]
    return rules, files


# ---------------------------------------------------------------- scanning
def masked_spans(line, state, lang):
    """Return (list of (start,end) spans that are comment/string, new_state).
    state: None | '"""' | "'''" | '/*'  (open multi-line construct)."""
    spans, i, n = [], 0, len(line)
    if state:
        close = "*/" if state == "/*" else state
        j = line.find(close)
        if j < 0:
            return [(0, n)], state
        spans.append((0, j + len(close)))
        i, state = j + len(close), None
    while i < n:
        c = line[i]
        if lang == "gd" and c == "#":
            spans.append((i, n))
            break
        if lang == "cs" and line.startswith("//", i):
            spans.append((i, n))
            break
        if lang == "cs" and line.startswith("/*", i):
            j = line.find("*/", i + 2)
            if j < 0:
                spans.append((i, n))
                return spans, "/*"
            spans.append((i, j + 2))
            i = j + 2
            continue
        if c in "\"'":
            if lang == "gd" and line.startswith(c * 3, i):
                j = line.find(c * 3, i + 3)
                if j < 0:
                    spans.append((i, n))
                    return spans, c * 3
                spans.append((i, j + 3))
                i = j + 3
                continue
            j = i + 1
            while j < n and line[j] != c:
                j += 2 if line[j] == "\\" else 1
            spans.append((i, min(j + 1, n)))
            i = j + 1
            continue
        i += 1
    return spans, state


def scan_text(text, path, rules):
    ext = os.path.splitext(path)[1].lstrip(".").lower()
    lang = "cs" if ext == "cs" else ("gd" if ext == "gd" else "none")
    active = [r for r in rules if ext in r["ext"]]
    findings, state = [], None
    for ln, line in enumerate(text.splitlines(), 1):
        spans, state = (masked_spans(line, state, lang) if lang != "none" else ([], None))
        for r in active:
            for m in r["rx"].finditer(line):
                col = m.start()
                if any(a <= col < b for a, b in spans):
                    continue
                findings.append({"file": path, "line": ln, "col": col + 1, "rule": r["id"], "severity": r["severity"],
                                 "snippet": line.strip()[:120], "match": m.group(0), "old": r["old"], "fix": r["new"],
                                 "note": r["note"], "url": r["url"]})
    return findings


def collect_files(paths, with_cs):
    exts = SCAN_EXT | ({".cs"} if with_cs else set())
    out = []
    for p in paths:
        if os.path.isdir(p):
            for dp, dns, fns in os.walk(p):
                dns[:] = [d for d in dns if not d.startswith(".") and d != "addons"]
                out += [os.path.join(dp, f) for f in sorted(fns) if os.path.splitext(f)[1] in exts]
        elif os.path.isfile(p):
            out.append(p)
    return out


def scan_files(files, rules):
    findings = []
    for f in files:
        try:
            with open(f, encoding="utf-8", errors="replace") as fh:
                findings += scan_text(fh.read(), f, rules)
        except OSError as e:
            sys.stderr.write("warning: %s: %s\n" % (f, e))
    return findings


def format_text(findings):
    lines = []
    for f in findings:
        lines.append("%s:%d:%d: [%s] %s: %s" % (f["file"], f["line"], f["col"], f["severity"], f["rule"], f["snippet"]))
        fix = "    fix: %s -> %s" % (f["old"], f["fix"]) if f["old"] else "    fix: %s" % f["fix"]
        if f["note"]:
            fix += "  (%s)" % f["note"]
        lines.append(fix)
        if f["url"]:
            lines.append("    see: %s" % f["url"])
    return "\n".join(lines)


def hook_mode(rules):
    try:
        payload = json.load(sys.stdin)
    except ValueError:
        return 0
    ti = payload.get("tool_input") or {}
    fp = ti.get("file_path") or ti.get("path") or (payload.get("tool_response") or {}).get("filePath")
    if not fp or os.path.splitext(fp)[1] not in SCAN_EXT | {".cs"} or not os.path.isfile(fp):
        return 0
    findings = scan_files([fp], rules)
    errors = [f for f in findings if f["severity"] == "error"]
    if not errors:
        return 0
    msg = ["godot-guard: %d Godot-3/invalid API use(s) in %s - fix before continuing:" % (len(errors), fp)]
    for f in errors[:12]:
        msg.append("  line %d: `%s` -> %s [%s]" % (f["line"], f["match"], f["fix"], f["rule"]))
    if len(errors) > 12:
        msg.append("  ... and %d more (run api_guard.py %s)" % (len(errors) - 12, fp))
    sys.stderr.write("\n".join(msg) + "\n")
    return 2


def main(argv=None):
    ap = argparse.ArgumentParser(description="Scan GDScript/C#/.tscn for Godot 3 idioms and 4.x API drift.")
    ap.add_argument("paths", nargs="*", help="files or directories")
    ap.add_argument("--rules", action="append", help="rules JSON (repeatable); default ../reference/*.json or built-ins")
    ap.add_argument("--json", action="store_true", help="JSON output")
    ap.add_argument("--severity", choices=["error", "warn"], default="warn", help="minimum severity to report")
    ap.add_argument("--cs", action="store_true", help="also scan .cs files in directories")
    ap.add_argument("--files-from-stdin", action="store_true", help="read file paths, one per line, from stdin")
    ap.add_argument("--hook", action="store_true", help="Claude Code hook mode (hook JSON on stdin)")
    ap.add_argument("--list-rules", action="store_true", help="print loaded rules and exit")
    args = ap.parse_args(argv)
    rules, sources = load_rules(args.rules)
    if args.list_rules:
        for r in rules:
            print("%-24s %-6s %-10s %s" % (r["id"], r["severity"], ",".join(r["ext"]), r["pattern"]))
        return 0
    if args.hook:
        return hook_mode(rules)
    paths = list(args.paths)
    if args.files_from_stdin:
        paths += [l.strip() for l in sys.stdin if l.strip()]
    if not paths:
        ap.exit(2, "error: no paths given (or use --files-from-stdin / --hook)\n")
    missing = [p for p in paths if not os.path.exists(p)]
    if missing:
        ap.exit(2, "error: no such path: %s\n" % ", ".join(missing))
    files = collect_files(paths, args.cs)
    findings = scan_files(files, rules)
    if args.severity == "error":
        findings = [f for f in findings if f["severity"] == "error"]
    if args.json:
        print(json.dumps({"files_scanned": len(files), "rule_sources": sources or ["builtin"],
                          "rules": len(rules), "findings": findings}, indent=2))
    else:
        if findings:
            print(format_text(findings))
        print("%d finding(s) in %d file(s) [%d rules from %s]" % (
            len(findings), len(files), len(rules), ", ".join(os.path.basename(s) for s in sources) or "builtin"))
        if upgrade_hint:
            upgrade_hint.emit("findings", len(findings))
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
