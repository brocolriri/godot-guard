#!/usr/bin/env python3
"""scene_map.py - dump Godot 4 .tscn scenes as an agent-readable map.
Usage: scene_map.py <project_dir|file.tscn> [--out .claude/scene-map.md] [--json]
Exit: 0 ok, 1 problems (unresolved refs, format!=3), 2 usage error. Stdlib only, Python 3.8+."""
import argparse
import datetime
import json
import os
import re
import sys

IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
MAX_DEPTH = 8


# ---------------------------------------------------------------- tscn parsing
def _read_string(s, i):
    """Parse a quoted string starting at s[i] == '"'. Returns (value, next_i)."""
    out, i = [], i + 1
    while i < len(s) and s[i] != '"':
        if s[i] == "\\" and i + 1 < len(s):
            out.append({"n": "\n", "t": "\t"}.get(s[i + 1], s[i + 1]))
            i += 1
        else:
            out.append(s[i])
        i += 1
    return "".join(out), i + 1


def _read_value(s, i):
    """Parse one header/property value. Returns (value, next_i)."""
    n = len(s)
    while i < n and s[i] == " ":
        i += 1
    if i >= n:
        return None, i
    c = s[i]
    if c == '"':
        return _read_string(s, i)
    if c == "[":  # array of values
        items, i = [], i + 1
        while i < n and s[i] != "]":
            if s[i] in " ,":
                i += 1
            else:
                v, i = _read_value(s, i)
                items.append(v)
        return items, i + 1
    m = re.match(r"([A-Za-z_][A-Za-z0-9_]*)\(", s[i:])
    if m:  # ExtResource("id"), SubResource("id"), Vector2(1, 2) ...
        depth, j = 0, i
        while j < n:
            if s[j] == '"':
                _, j = _read_string(s, j)
                continue
            depth += {"(": 1, ")": -1}.get(s[j], 0)
            if depth == 0 and s[j] == ")":
                break
            j += 1
        raw = s[i:j + 1]
        inner = re.match(r"(ExtResource|SubResource)\(\s*\"?([^\")]*)\"?\s*\)", raw)
        if inner:
            return {"ref": inner.group(1), "id": inner.group(2)}, j + 1
        return raw, j + 1
    m = re.match(r"[^\s,\]]+", s[i:])
    tok = m.group(0)
    return tok, i + len(tok)


def parse_header(line):
    """'[node name="A" parent="."]' -> ('node', {'name': 'A', 'parent': '.'})"""
    body = line.strip()[1:-1]
    m = re.match(r"([A-Za-z_]+)\s*", body)
    kind, i, attrs = m.group(1), m.end(), {}
    while i < len(body):
        m = re.match(r"\s*([A-Za-z_][A-Za-z0-9_/]*)\s*=", body[i:])
        if not m:
            break
        key = m.group(1)
        val, i = _read_value(body, i + m.end())
        attrs[key] = val
    return kind, attrs


def parse_tscn(path):
    """Return dict: format, uid, ext (id->attrs), nodes (list), connections."""
    scene = {"file": path, "format": None, "uid": None, "ext": {},
             "nodes": [], "connections": [], "problems": []}
    with open(path, encoding="utf-8", errors="replace") as fh:
        lines = fh.read().splitlines()
    cur = None
    for raw in lines:
        line = raw.strip()
        if not line:
            continue
        if line.startswith("[") and line.endswith("]") and re.match(r"\[[a-z_]+[\s\]]", line):
            kind, attrs = parse_header(line)
            cur = None
            if kind == "gd_scene":
                scene["format"], scene["uid"] = attrs.get("format"), attrs.get("uid")
            elif kind == "ext_resource":
                scene["ext"][attrs.get("id")] = attrs
            elif kind == "node":
                cur = {"attrs": attrs, "props": {}}
                scene["nodes"].append(cur)
            elif kind == "connection":
                scene["connections"].append(attrs)
            continue
        if cur is not None:
            m = re.match(r"([A-Za-z_][A-Za-z0-9_/]*)\s*=\s*(.*)$", line)
            if m:
                val, _ = _read_value(m.group(2), 0)
                cur["props"][m.group(1)] = val
    if scene["format"] != "3":
        scene["problems"].append("format=%s (expected 3 for Godot 4)" % scene["format"])
    return scene


# ---------------------------------------------------------------- scripts
SCRIPT_RE = {
    "class_name": re.compile(r"^\s*class_name\s+([A-Za-z_]\w*)", re.M),
    "extends": re.compile(r"^\s*extends\s+([\w.\"/]+)", re.M),
    "signals": re.compile(r"^\s*signal\s+([A-Za-z_]\w*)(\([^)]*\))?", re.M),
    "exports": re.compile(r"^\s*@export[^\n]*?\bvar\s+([A-Za-z_]\w*)", re.M),
    "funcs": re.compile(r"^\s*(?:static\s+)?func\s+([A-Za-z_]\w*)\s*\(", re.M),
}


def script_info(abs_path, cache):
    if abs_path in cache:
        return cache[abs_path]
    info = {"class_name": None, "extends": None, "signals": [], "exports": [], "funcs": []}
    try:
        with open(abs_path, encoding="utf-8", errors="replace") as fh:
            src = fh.read()
    except OSError:
        cache[abs_path] = None
        return None
    for key in ("class_name", "extends"):
        m = SCRIPT_RE[key].search(src)
        info[key] = m.group(1) if m else None
    info["signals"] = [a + (b or "()") for a, b in SCRIPT_RE["signals"].findall(src)]
    info["exports"] = SCRIPT_RE["exports"].findall(src)
    info["funcs"] = SCRIPT_RE["funcs"].findall(src)
    cache[abs_path] = info
    return info


# ---------------------------------------------------------------- project
def find_project_root(start):
    d = os.path.abspath(start if os.path.isdir(start) else os.path.dirname(start))
    while not os.path.isfile(os.path.join(d, "project.godot")):
        if os.path.dirname(d) == d:
            return None
        d = os.path.dirname(d)
    return d


def parse_project(root):
    info = {"features": [], "main_scene": None, "autoloads": [], "name": None}
    if not root:
        return info
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
            key, val = m.group(1), m.group(2)
            if section == "application":
                if key == "config/features":
                    info["features"] = re.findall(r'"([^"]*)"', val)
                elif key in ("run/main_scene", "config/name"):
                    info[key.split("/")[1]] = val.strip('"')
            elif section == "autoload":
                info["autoloads"].append({"name": key, "path": val.strip('"').lstrip("*"),
                                          "singleton": val.strip('"').startswith("*")})
    return info


def res_to_abs(res, root, base_dir):
    if res.startswith("res://"):
        return os.path.join(root or base_dir, res[6:].replace("/", os.sep))
    return os.path.normpath(os.path.join(base_dir, res))


# ---------------------------------------------------------------- tree build
def gd_path(path):
    """Filesystem-like scene path -> $ expression (quotes when needed)."""
    if path == "":
        return "self"
    if all(IDENT_RE.match(seg) for seg in path.split("/")):
        return "$" + path
    return '$"%s"' % path.replace('"', '\\"')


def unique_expr(name):
    return "%" + name if IDENT_RE.match(name) else '%"' + name.replace('"', '\\"') + '"'


class Builder:
    def __init__(self, root, script_cache):
        self.root, self.sc, self.scene_cache = root, script_cache, {}

    def load(self, abs_path, stack=()):
        abs_path = os.path.normpath(abs_path)
        if abs_path in self.scene_cache:
            return self.scene_cache[abs_path]
        if abs_path in stack or len(stack) > MAX_DEPTH or not os.path.isfile(abs_path):
            return None
        scene, nodes, by_path = parse_tscn(abs_path), [], {}
        base, problems = os.path.dirname(abs_path), scene["problems"]
        for entry in scene["nodes"]:
            a, p = entry["attrs"], entry["props"]
            name, parent = a.get("name", "?"), a.get("parent")
            path = "" if parent is None else (name if parent == "." else parent + "/" + name)
            node = by_path.get(path)
            if node is None:
                node = by_path[path] = {"path": path, "name": name, "type": a.get("type"), "script": None,
                                        "unique": False, "groups": [], "instance": None,
                                        "parent": None if parent is None else ("" if parent == "." else parent)}
                nodes.append(node)
            node["type"] = a.get("type") or node["type"]
            node["groups"] = list(a.get("groups") or node["groups"])
            inst = a.get("instance")
            if isinstance(inst, dict) and inst.get("ref") == "ExtResource":
                ipath = node["instance"] = scene["ext"].get(inst["id"], {}).get("path")
                sub = self.load(res_to_abs(ipath, self.root, base), stack + (abs_path,)) if ipath else None
                if sub is None:
                    problems.append("%s: cannot resolve instance %s" % (path or name, ipath))
                    node["type"] = node["type"] or "?"
                else:
                    node["type"], node["script"] = sub["nodes"][0]["type"], sub["nodes"][0]["script"]
                    for child in sub["nodes"][1:]:  # expand the instanced subtree
                        cpath = path + "/" + child["path"]
                        if cpath not in by_path:
                            c = by_path[cpath] = dict(child, path=cpath, from_scene=ipath, unique=False,
                                                      unique_inner=child["unique"],
                                                      parent=path + ("/" + child["parent"] if child["parent"] else ""))
                            nodes.append(c)
            elif a.get("instance_placeholder"):
                node["instance"], node["type"] = a["instance_placeholder"], node["type"] or "InstancePlaceholder"
            v = p.get("script")
            if isinstance(v, dict) and v.get("ref") == "ExtResource":
                node["script"] = scene["ext"].get(v["id"], {}).get("path")
            elif v == "null":
                node["script"] = None
            node["unique"] = node["unique"] or str(p.get("unique_name_in_owner", "")).lower() == "true"
            if node["type"] is None:
                node["type"] = "?"
                problems.append("%s: no type/instance and no matching inherited node" % (path or name))
        for n in nodes:
            si = script_info(res_to_abs(n["script"], self.root, base), self.sc) if n["script"] else None
            if n["script"] and si is None:
                problems.append("%s: script not found %s" % (n["path"] or n["name"], n["script"]))
            n["class_name"] = si["class_name"] if si else None
            n["access"] = ([unique_expr(n["name"])] if n["unique"] else []) + [gd_path(n["path"])]
            if n["path"]:
                n["access"].append('get_node("%s")' % n["path"].replace('"', '\\"'))
        scene["nodes"] = nodes
        self.scene_cache[abs_path] = scene
        return scene


# ---------------------------------------------------------------- rendering
def rel(path, root):
    try:
        return os.path.relpath(path, root).replace(os.sep, "/") if root else path
    except ValueError:
        return path


def _conn_path(v):
    return gd_path("" if v in (".", None) else v)


def render_scene(scene, root):
    nodes, rootn = scene["nodes"], scene["nodes"][0]
    out = ["## %s" % rel(scene["file"], root),
           "Root: `%s` (%s)%s" % (rootn["name"], rootn["type"], "  script: `%s`" % rootn["script"] if rootn["script"] else ""),
           "", "### Node tree", "```"]
    children = {}
    for n in nodes:
        children.setdefault(n["parent"], []).append(n)

    def walk(n, depth):
        bits = ["%s : %s" % (n["name"], n["type"])]
        bits += [unique_expr(n["name"])] if n["unique"] else []
        bits += ["instance=%s" % n["instance"]] if n["instance"] else []
        if n["script"]:
            bits.append("script=%s%s" % (n["script"], " (class_name %s)" % n["class_name"] if n["class_name"] else ""))
        bits += ["groups=%s" % ",".join(n["groups"])] if n["groups"] else []
        bits += ["[inside %s]" % n["from_scene"].split("/")[-1]] if n.get("from_scene") else []
        out.append("  " * depth + "  ".join(bits))
        for c in children.get(n["path"], []):
            walk(c, depth + 1)
    walk(rootn, 0)
    out += ["```", "", "### Access expressions (from `%s`'s script; use verbatim)" % rootn["name"],
            "| Node | Type | Use this | Also valid |", "|---|---|---|---|"]
    out += ["| %s | %s | `%s` | %s |" % (n["path"], n["type"], n["access"][0], ", ".join("`%s`" % a for a in n["access"][1:]))
            for n in nodes[1:]]
    inner = [n for n in nodes if n.get("unique_inner")]
    if inner:
        out += ["", "Unique names that only work *inside* their own scene script (not from `%s`): %s" % (
            rootn["name"], ", ".join("`%s` in %s" % (unique_expr(n["name"]), n["from_scene"]) for n in inner))]
    out += ["", "### Signal connections (`[connection]` lines)"]
    if scene["connections"]:
        out += ["| Signal | From | To | Method | Extra |", "|---|---|---|---|---|"]
        for c in scene["connections"]:
            extra = ", ".join("%s=%s" % kv for kv in c.items() if kv[0] not in ("signal", "from", "to", "method"))
            out.append("| %s | `%s` | `%s` | `%s` | %s |" % (c.get("signal"), _conn_path(c.get("from")),
                                                            _conn_path(c.get("to")), c.get("method"), extra))
    else:
        out.append("(none in this file)")
    groups = {}
    for n in nodes:
        for g in n["groups"]:
            groups.setdefault(g, []).append(n["path"] or n["name"])
    if groups:
        out += ["", "### Groups"] + ["- `%s`: %s" % (g, ", ".join("`%s`" % m for m in ms)) for g, ms in sorted(groups.items())]
    if scene["problems"]:
        out += ["", "### Problems"] + ["- %s" % p for p in scene["problems"]]
    return "\n".join(out + [""])


def render_scripts(script_cache, root):
    out = ["## Scripts (signals / @export / func)"]
    for path in sorted(p for p, v in script_cache.items() if v):
        si = script_cache[path]
        head = rel(path, root) + ("  class_name `%s`" % si["class_name"] if si["class_name"] else "")
        out.append("- **%s**" % (head + ("  extends `%s`" % si["extends"] if si["extends"] else "")))
        for label, key in (("signals", "signals"), ("@export", "exports"), ("func", "funcs")):
            if si[key]:
                out.append("  - %s: %s" % (label, ", ".join("`%s`" % x for x in si[key])))
    return "\n".join(out + [""])


def build_all(target):
    root = find_project_root(target)
    proj = parse_project(root)
    if os.path.isdir(target):
        files = []
        for dp, dns, fns in os.walk(target):
            dns[:] = [d for d in dns if not d.startswith(".") and d != "addons"]
            files += [os.path.join(dp, f) for f in fns if f.endswith(".tscn")]
        files.sort()
    else:
        files = [os.path.abspath(target)]
    sc = {}
    builder = Builder(root, sc)
    scenes = [s for s in (builder.load(f) for f in files) if s]
    for al in proj["autoloads"]:
        if al["path"].endswith(".gd"):
            script_info(res_to_abs(al["path"], root, root or "."), sc)
    problems = sum(len(s["problems"]) for s in scenes)
    stamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    md = ["# Scene map (godot-guard)", "Generated: %s" % stamp,
          "Project: %s  |  features: %s  |  main scene: %s" % (
              proj["name"] or rel(root or target, None), ", ".join(proj["features"]) or "?", proj["main_scene"] or "?"),
          "", "**Use these paths verbatim; do not guess node names.** Regenerate after editing any .tscn.", ""]
    if proj["autoloads"]:
        md.append("## Autoloads (global singletons, call by name)")
        for al in proj["autoloads"]:
            si = sc.get(res_to_abs(al["path"], root, root or "."))
            extra = "  signals: " + ", ".join("`%s`" % x for x in si["signals"]) if si and si["signals"] else ""
            md.append("- `%s` -> %s%s%s" % (al["name"], al["path"], "" if al["singleton"] else " (not a singleton)", extra))
        md.append("")
    md += [render_scene(s, root) for s in scenes] + [render_scripts(sc, root)]
    for s in scenes:
        s["file"] = rel(s["file"], root)
    data = {"generated": stamp, "project_root": root, "features": proj["features"], "main_scene": proj["main_scene"],
            "autoloads": proj["autoloads"], "scenes": scenes,
            "scripts": {rel(p, root): v for p, v in sc.items() if v}, "problem_count": problems}
    return "\n".join(md), data, problems


def main(argv=None):
    ap = argparse.ArgumentParser(description="Dump Godot 4 .tscn node trees, paths, signals into a markdown map.")
    ap.add_argument("target", help="project directory or a single .tscn file")
    ap.add_argument("--out", help="write markdown here (e.g. .claude/scene-map.md); default: stdout")
    ap.add_argument("--json", action="store_true", help="emit JSON instead of markdown")
    args = ap.parse_args(argv)
    if not os.path.exists(args.target) or (os.path.isfile(args.target) and not args.target.endswith(".tscn")):
        ap.exit(2, "error: target must be a project directory or a .tscn file: %s\n" % args.target)
    text, data, problems = build_all(args.target)
    if not data["scenes"]:
        ap.exit(2, "error: no .tscn files found under %s\n" % args.target)
    payload = json.dumps(data, indent=2) if args.json else text
    if args.out:
        os.makedirs(os.path.dirname(os.path.abspath(args.out)) or ".", exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(payload + "\n")
        print("wrote %s (%d scenes, %d problems)" % (args.out, len(data["scenes"]), problems))
    else:
        print(payload)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
