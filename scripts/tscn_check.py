#!/usr/bin/env python3
"""tscn-check: static validation of Godot 4 text scenes/resources (.tscn/.tres, format=3).

Checks (no Godot needed):
  - every ExtResource("id") / SubResource("id") reference exists in the headers
  - ext_resource path="res://..." exists on disk (when a project root is found)
  - duplicate ext/sub resource ids
  - every node's parent="..." resolves to a previously declared node
    (paths inside an instanced sub-scene / inherited scene are accepted)
  - no duplicate sibling node names
  - load_steps (if present) == ext_resources + sub_resources + 1  (Godot's rule; warning)
  - uid="..." format (uid://<base-36 lowercase>)
  - instance=ExtResource(...) targets a PackedScene ext_resource
  - [connection] from/to paths resolve
  - absolute OS paths in string values (warning)
  - 4.6+ unique_id on node headers: informational count only
Optional --instantiate loads each file in a real Godot process (scenes are instantiated).

Exit codes: 0 no errors, 1 findings (errors; warnings too with --strict), 2 usage error.
"""
import argparse
import re
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import godot_common as gc  # noqa: E402
try:
    import upgrade_hint  # noqa: E402
except Exception:
    upgrade_hint = None

KNOWN = ("gd_scene", "gd_resource", "ext_resource", "sub_resource", "node", "connection", "editable", "resource")
HEADER_RE = re.compile(r"^\[(" + "|".join(KNOWN) + r")(?:\s+(.*))?\]\s*$")
ATTR_RE = re.compile(r'(\w+)=("(?:[^"\\]|\\.)*"|\[[^\]]*\]|[^\s\]]+)')
REF_RE = re.compile(r'\b(ExtResource|SubResource)\(\s*"?([^")]*?)"?\s*\)')
UID_RE = re.compile(r"^uid://[0-9a-z]+$")
ABS_PATH_RE = re.compile(r'"((?:[A-Za-z]:[\\/]|\\\\|/(?:home|Users|mnt|tmp|opt|var)/)[^"]*)"')
STRING_RE = re.compile(r'"((?:[^"\\]|\\.)*)"')


class Finding(dict):
    def __init__(self, severity, file, line, code, message):
        super().__init__(severity=severity, file=str(file), line=line, code=code, message=message)


def unquote(v):
    return v[1:-1].encode("utf-8").decode("unicode_escape") if len(v) >= 2 and v[0] == v[-1] == '"' else v


def parse_attrs(text):
    return {k: unquote(v) for k, v in ATTR_RE.findall(text or "")}


def check_text(text, file, project=None):
    """Validate one file's text; return (findings, info dict)."""
    f = []
    ext, sub, nodes, instance_nodes = {}, {}, {}, set()
    siblings, header_attrs, kind_first = set(), {}, None
    unique_ids, node_count = 0, 0
    section = None  # (kind, attrs, line)
    lines = text.splitlines()

    def resolves(path):
        """A node path is valid if declared, or lies inside an instanced/inherited node."""
        if path in nodes or path == ".":
            return True
        parts = path.split("/")
        if "." in instance_nodes:  # inherited scene: anything may exist in the base
            return True
        for i in range(len(parts), 0, -1):
            if "/".join(parts[:i]) in instance_nodes:
                return True
        return False

    def check_refs(body, ln, allow_sub=True):
        for kind, rid in REF_RE.findall(body):
            if kind == "ExtResource" and rid not in ext:
                f.append(Finding("error", file, ln, "missing_ext_ref", 'ExtResource("%s") is not declared' % rid))
            elif kind == "SubResource" and rid not in sub:
                f.append(Finding("error", file, ln, "missing_sub_ref",
                                 'SubResource("%s") is not declared (or declared after use)' % rid))
        for m in ABS_PATH_RE.finditer(body):
            f.append(Finding("warning", file, ln, "abs_os_path", "absolute OS path in value: %s" % m.group(1)))

    for i, raw in enumerate(lines, 1):
        line = raw.rstrip()
        if not line.strip() or line.lstrip().startswith(";"):
            continue
        m = HEADER_RE.match(line)
        if not m:
            if section is None:
                f.append(Finding("error", file, i, "text_before_header", "content before first [header]"))
            else:
                check_refs(line, i)
            continue
        kind, attrs = m.group(1), parse_attrs(m.group(2))
        section = (kind, attrs, i)
        if kind_first is None:
            kind_first = kind
            header_attrs = attrs
            if kind not in ("gd_scene", "gd_resource"):
                f.append(Finding("error", file, i, "bad_first_header", "first header must be [gd_scene] or [gd_resource]"))
            fmt = attrs.get("format")
            if fmt is None:
                f.append(Finding("warning", file, i, "no_format", "header has no format= (expected format=3)"))
            elif fmt != "3":
                f.append(Finding("error", file, i, "bad_format", "format=%s (Godot 4 text resources use format=3)" % fmt))
            if "uid" in attrs and not UID_RE.match(attrs["uid"]):
                f.append(Finding("error", file, i, "bad_uid", "malformed uid=%r (expected uid://<lowercase base36>)" % attrs["uid"]))
            continue
        if kind == "ext_resource":
            rid, path, rtype = attrs.get("id"), attrs.get("path"), attrs.get("type")
            for need in ("id", "path", "type"):
                if need not in attrs:
                    f.append(Finding("error", file, i, "missing_attr", "[ext_resource] without %s=" % need))
            if rid in ext:
                f.append(Finding("error", file, i, "dup_ext_id", 'duplicate ext_resource id="%s"' % rid))
            if rid is not None:
                ext[rid] = rtype
            if "uid" in attrs and not UID_RE.match(attrs["uid"]):
                f.append(Finding("error", file, i, "bad_uid", "malformed uid=%r" % attrs["uid"]))
            if path:
                if ABS_PATH_RE.match('"%s"' % path):
                    f.append(Finding("warning", file, i, "abs_os_path", "ext_resource path is an OS path: %s" % path))
                elif project and path.startswith(gc.RES_PREFIX) and not gc.from_res_path(project, path).exists():
                    f.append(Finding("error", file, i, "missing_ext_file", "ext_resource path does not exist: %s" % path))
        elif kind == "sub_resource":
            rid = attrs.get("id")
            if rid is None or "type" not in attrs:
                f.append(Finding("error", file, i, "missing_attr", "[sub_resource] needs type= and id="))
            if rid in sub:
                f.append(Finding("error", file, i, "dup_sub_id", 'duplicate sub_resource id="%s"' % rid))
            sub[rid] = attrs.get("type")
        elif kind == "node":
            node_count += 1
            name, parent = attrs.get("name"), attrs.get("parent")
            if "unique_id" in attrs:
                unique_ids += 1
            if not name:
                f.append(Finding("error", file, i, "missing_attr", "[node] without name="))
                continue
            if node_count == 1:
                if parent is not None:
                    f.append(Finding("error", file, i, "root_has_parent", "root node must not have parent="))
                path = "."
            else:
                if parent is None:
                    f.append(Finding("error", file, i, "no_parent", 'node "%s" has no parent= (only the root may omit it)' % name))
                    continue
                if not resolves(parent):
                    f.append(Finding("error", file, i, "bad_parent",
                                     'node "%s": parent="%s" does not match any node declared above' % (name, parent)))
                path = name if parent == "." else parent + "/" + name
                if (parent, name) in siblings:
                    f.append(Finding("error", file, i, "dup_sibling", 'duplicate node "%s" under parent="%s"' % (name, parent)))
                siblings.add((parent, name))
            nodes[path] = attrs
            inst = attrs.get("instance")
            if inst:
                instance_nodes.add(path)
                rm = REF_RE.match(inst)
                if not rm or rm.group(1) != "ExtResource":
                    f.append(Finding("error", file, i, "bad_instance", "instance= must be ExtResource(\"id\"): %s" % inst))
                elif rm.group(2) not in ext:
                    f.append(Finding("error", file, i, "missing_ext_ref", 'instance=ExtResource("%s") is not declared' % rm.group(2)))
                elif ext[rm.group(2)] != "PackedScene":
                    f.append(Finding("error", file, i, "instance_not_packed_scene",
                                     'instance=ExtResource("%s") is type %s, not PackedScene' % (rm.group(2), ext[rm.group(2)])))
            if "type" not in attrs and not inst and node_count > 1 and not resolves(path):
                f.append(Finding("warning", file, i, "no_type", 'node "%s" has neither type= nor instance=' % name))
        elif kind == "connection":
            for key in ("from", "to"):
                p = attrs.get(key)
                if p is None:
                    f.append(Finding("error", file, i, "missing_attr", "[connection] without %s=" % key))
                elif not resolves(p):
                    f.append(Finding("error", file, i, "bad_connection", '[connection] %s="%s" does not resolve to a node' % (key, p)))
            for key in ("signal", "method"):
                if key not in attrs:
                    f.append(Finding("error", file, i, "missing_attr", "[connection] without %s=" % key))
        elif kind == "editable":
            p = attrs.get("path")
            if p and p not in instance_nodes:
                f.append(Finding("warning", file, i, "editable_not_instance", '[editable path="%s"] is not an instanced node' % p))
    if kind_first is None:
        f.append(Finding("error", file, 0, "empty", "no [gd_scene]/[gd_resource] header found"))
    ls = header_attrs.get("load_steps")
    if ls is not None:
        expected = len(ext) + len(sub) + 1
        if not ls.isdigit() or int(ls) != expected:
            f.append(Finding("warning", file, 1, "load_steps_mismatch",
                             "load_steps=%s but ext(%d)+sub(%d)+1 = %d" % (ls, len(ext), len(sub), expected)))
    info = {"ext_resources": len(ext), "sub_resources": len(sub), "nodes": node_count,
            "nodes_with_unique_id": unique_ids, "kind": kind_first}
    if kind_first == "gd_scene" and node_count and unique_ids < node_count:
        f.append(Finding("info", file, 0, "unique_id",
                         "%d/%d nodes have unique_id (Godot 4.6+ adds it on save; missing is fine)" % (unique_ids, node_count)))
    return f, info


def collect_files(target):
    t = Path(target)
    if t.is_file():
        return [t]
    if t.is_dir():
        return list(gc.iter_project_files(t, (".tscn", ".tres"), excludes=(".godot", ".git")))
    raise gc.GodotError("no such file or directory: %s" % target)


def instantiate(files, godot, timeout, project=None):
    groups = {}
    for fp in files:
        root = project or gc.find_project_root(fp)
        if root is None:
            raise gc.GodotError("cannot find project.godot above %s (pass --project)" % fp)
        groups.setdefault(root, []).append(fp)
    results = []
    for root, fps in groups.items():
        for kind, suffix in (("scene", ".tscn"), ("resource", ".tres")):
            paths = [gc.to_res_path(root, fp) for fp in fps if fp.suffix == suffix]
            if paths:
                _, items = gc.run_runner(root, kind, paths, godot=godot, timeout=timeout)
                results += items
    return results


def human(report):
    out = []
    for fd in report["findings"]:
        loc = "%s:%s" % (fd["file"], fd["line"]) if fd["line"] else fd["file"]
        out.append("%-7s %s: [%s] %s" % (fd["severity"], loc, fd["code"], fd["message"]))
    for it in report.get("instantiate", []):
        out.append("%-7s %s: [instantiate] %s" % ("ok" if it["ok"] else "error", it["path"], it["status"]))
        out += ["        " + e for e in it["errors"]]
    c = report["counts"]
    out.append("tscn-check: %d file(s), %d error(s), %d warning(s) -> %s" % (
        report["files"], c["error"], c["warning"], "PASS" if report["ok"] else "FAIL"))
    return "\n".join(out)


def build_parser():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("target", help=".tscn/.tres file or a directory to scan recursively")
    p.add_argument("--project", help="project root (default: nearest project.godot above each file)")
    p.add_argument("--instantiate", action="store_true", help="also load/instantiate each file in Godot")
    p.add_argument("--strict", action="store_true", help="warnings also fail (exit 1)")
    p.add_argument("--timeout", type=float, default=120, help="seconds per Godot invocation")
    p.add_argument("--godot", help="path to the Godot binary")
    p.add_argument("--json", action="store_true", help="print the JSON report only")
    return p


def hook_main():
    """PostToolUse hook mode: read Claude Code hook JSON on stdin, check the edited scene/resource file.
    exit 2 + stderr message on errors (Claude sees it), else exit 0."""
    try:
        data = json.load(sys.stdin)
    except Exception:
        return 0
    path = (data.get("tool_input") or {}).get("file_path") or ""
    if not path.lower().endswith((".tscn", ".tres", ".escn")):
        return 0
    fp = Path(path)
    if not fp.is_file():
        return 0
    try:
        findings, _ = check_text(fp.read_text(encoding="utf-8", errors="replace"), fp, gc.find_project_root(fp))
    except Exception as e:
        sys.stderr.write("tscn-check hook: could not check %s: %s\n" % (path, e))
        return 0
    errs = [f for f in findings if f["severity"] == "error"]
    if not errs:
        return 0
    lines = ["godot-guard tscn-check: %d error(s) in %s - fix before continuing:" % (len(errs), path)]
    for f in errs[:8]:
        lines.append("  line %s: %s" % (f.get("line", "?"), f.get("message") or f.get("msg") or f))
    lines.append("  then run: python3 \"${CLAUDE_PLUGIN_ROOT}/scripts/tscn_check.py\" \"%s\" --instantiate" % path)
    sys.stderr.write("\n".join(lines) + "\n")
    return 2


def main(argv=None):
    if "--hook" in (argv if argv is not None else sys.argv[1:]):
        return hook_main()
    args = build_parser().parse_args(argv)
    try:
        files = collect_files(args.target)
        findings, per_file = [], {}
        for fp in files:
            project = Path(args.project).resolve() if args.project else gc.find_project_root(fp)
            fs, info = check_text(fp.read_text(encoding="utf-8", errors="replace"), fp, project)
            findings += fs
            per_file[str(fp)] = info
        inst = []
        if args.instantiate:
            godot = gc.find_godot(args.godot)
            inst = instantiate(files, godot, args.timeout, Path(args.project).resolve() if args.project else None)
    except gc.GodotError as e:
        if args.json:
            print(gc.json_dump({"ok": False, "error": str(e)}))
        else:
            print("tscn-check: error: %s" % e, file=sys.stderr)
        return 2
    counts = {s: sum(1 for x in findings if x["severity"] == s) for s in ("error", "warning", "info")}
    counts["error"] += sum(1 for it in inst if not it["ok"])
    ok = counts["error"] == 0 and not (args.strict and counts["warning"])
    report = {"ok": ok, "files": len(files), "counts": counts, "findings": findings, "info": per_file,
              "instantiate": inst}
    print(gc.json_dump(report) if args.json else human(report))
    if upgrade_hint and not args.json and not ok:
        upgrade_hint.emit("findings", counts["error"] + counts["warning"])
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
