#!/usr/bin/env python3
"""uid-keeper: keep Godot 4.4+ `.uid` sidecars and uid references consistent.

  uid_keeper.py <project_dir> [--fix]        scan the project
  uid_keeper.py move <src> <dst> [--apply]   rename a file with its sidecar and fix path refs

Scan reports:
  missing_sidecar   .gd/.cs/.gdshader/.gdextension without a .uid (Godot generates on --import)  [warning]
  orphan_sidecar    .uid whose owner file is gone                                              [warning, --fix deletes]
  bad_uid_format    sidecar content is not `uid://...`                                          [error]
  duplicate_uid     same uid in more than one sidecar / .tscn / .tres / .import                 [error]
  uid_mismatch      [ext_resource uid=... path=...] where uid != the target's real uid          [error, --fix rewrites]
  missing_target    [ext_resource path=...] whose file does not exist                           [error]
`--fix` never edits the contents of a .uid file.

`move` renames src -> dst together with src.uid (and src.import), and rewrites
`"res://old"` occurrences in .tscn/.tres/.godot/.import files and in
.godot/global_script_class_cache.cfg. Occurrences in .gd/.cs scripts are listed
for manual editing. Dry-run unless --apply. After --apply it runs
`godot --headless --import` because Godot 4.4+ resolves `uid=` references through
the binary .godot/uid_cache.bin, which still maps the uid to the OLD path (verified
on 4.7.2: the loader then ignores the correct path= and fails). --no-reimport skips it.

Exit codes: 0 clean (or all fixed), 1 findings remain, 2 usage error.
"""
import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import godot_common as gc  # noqa: E402

SIDECAR_TYPES = (".gd", ".cs", ".gdshader", ".gdextension")
UID_RE = re.compile(r"^uid://[0-9a-z]+$")
HEADER_UID_RE = re.compile(r'^\[(?:gd_scene|gd_resource)\b[^\]]*\buid="([^"]*)"')
EXT_RE = re.compile(r'^\[ext_resource\b(?=[^\]]*\bpath="([^"]*)")(?=[^\]]*\buid="([^"]*)")?')
IMPORT_UID_RE = re.compile(r'^uid="([^"]*)"', re.M)
SCAN_EXCLUDES = (".godot", ".git")


def finding(severity, code, file, message, fixable=False):
    return {"severity": severity, "code": code, "file": str(file), "message": message, "fixable": fixable}


def real_uid(project, target, sidecar_uids):
    """Return the uid the loader would resolve for target, or None if unknown."""
    if target in sidecar_uids:
        return sidecar_uids[target]
    if target.suffix in (".tscn", ".tres") and target.is_file():
        for line in target.read_text(encoding="utf-8", errors="replace").splitlines()[:3]:
            m = HEADER_UID_RE.match(line)
            if m:
                return m.group(1)
        return None
    imp = target.with_name(target.name + ".import")
    if imp.is_file():
        m = IMPORT_UID_RE.search(imp.read_text(encoding="utf-8", errors="replace"))
        return m.group(1) if m else None
    return None


def scan(project):
    findings, uid_sources, sidecar_uids = [], {}, {}
    all_files = list(gc.iter_project_files(project, ("",), SCAN_EXCLUDES))  # every file
    by_path = set(all_files)
    for fp in all_files:
        if fp.suffix == ".uid":
            owner = fp.with_name(fp.name[:-4])
            uid = fp.read_text(encoding="utf-8", errors="replace").strip()
            if not UID_RE.match(uid):
                findings.append(finding("error", "bad_uid_format", fp, "sidecar content is not uid://...: %r" % uid[:40]))
                continue
            if owner not in by_path:
                findings.append(finding("warning", "orphan_sidecar", fp, "owner file missing: %s" % owner.name, fixable=True))
                continue
            sidecar_uids[owner] = uid
            uid_sources.setdefault(uid, []).append(fp)
        elif fp.suffix == ".import":
            m = IMPORT_UID_RE.search(fp.read_text(encoding="utf-8", errors="replace"))
            if m:
                uid_sources.setdefault(m.group(1), []).append(fp)
    for fp in all_files:
        if fp.suffix in SIDECAR_TYPES and fp not in sidecar_uids:
            findings.append(finding("warning", "missing_sidecar", fp, "no %s.uid sidecar (run: godot --headless --import)" % fp.name))
    for fp in all_files:
        if fp.suffix not in (".tscn", ".tres"):
            continue
        for ln, line in enumerate(fp.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
            hm = HEADER_UID_RE.match(line)
            if hm:
                uid_sources.setdefault(hm.group(1), []).append(fp)
                continue
            em = EXT_RE.match(line)
            if not em:
                continue
            path, uid = em.group(1), em.group(2)
            if not path.startswith(gc.RES_PREFIX):
                continue
            target = gc.from_res_path(project, path)
            if not target.exists():
                findings.append(finding("error", "missing_target", "%s:%d" % (fp, ln), "ext_resource path does not exist: %s" % path))
                continue
            actual = real_uid(project, target, sidecar_uids)
            if uid and actual and uid != actual:
                findings.append(finding("error", "uid_mismatch", "%s:%d" % (fp, ln),
                                        "ext_resource uid=%s but %s has %s" % (uid, path, actual), fixable=True))
    for uid, srcs in sorted(uid_sources.items()):
        if len(set(srcs)) > 1:
            findings.append(finding("error", "duplicate_uid", ", ".join(str(s) for s in srcs), "uid %s used by %d files" % (uid, len(set(srcs)))))
    return findings


def apply_fixes(project, findings):
    fixed = []
    for fd in findings:
        if not fd["fixable"]:
            continue
        if fd["code"] == "orphan_sidecar":
            Path(fd["file"]).unlink()
            fixed.append("deleted orphan sidecar %s" % fd["file"])
        elif fd["code"] == "uid_mismatch":
            file, ln = fd["file"].rsplit(":", 1)
            m = re.search(r"uid=(uid://\S+) but (\S+) has (uid://\S+)", fd["message"])
            fp = Path(file)
            lines = fp.read_text(encoding="utf-8").split("\n")
            i = int(ln) - 1
            lines[i] = lines[i].replace('uid="%s"' % m.group(1), 'uid="%s"' % m.group(3), 1)
            fp.write_text("\n".join(lines), encoding="utf-8")
            fixed.append("%s: uid %s -> %s" % (fd["file"], m.group(1), m.group(3)))
        fd["fixed"] = True
    return fixed


def cmd_check(args):
    project = gc.require_project(args.project)
    findings = scan(project)
    fixed = apply_fixes(project, findings) if args.fix else []
    remaining = [f for f in findings if not f.get("fixed")]
    errors = [f for f in remaining if f["severity"] == "error"]
    ok = not errors and not (args.strict and remaining)
    report = {"ok": ok, "project": str(project), "findings": findings, "fixed": fixed,
              "counts": {"error": len(errors), "warning": len(remaining) - len(errors)}}
    if args.json:
        print(gc.json_dump(report))
    else:
        for f in findings:
            tag = "fixed" if f.get("fixed") else f["severity"]
            print("%-7s [%s] %s: %s" % (tag, f["code"], f["file"], f["message"]))
        print("uid-keeper: %d error(s), %d warning(s)%s -> %s" % (
            len(errors), report["counts"]["warning"], ", %d fixed" % len(fixed) if fixed else "", "PASS" if ok else "FAIL"))
    return 0 if ok else 1


def plan_move(src, dst):
    src = Path(src).resolve()
    if not src.exists():
        raise gc.GodotError("source does not exist: %s" % src)
    if src.is_dir():
        raise gc.GodotError("moving directories is not supported; move files one at a time")
    project = gc.find_project_root(src)
    if project is None:
        raise gc.GodotError("no project.godot above %s" % src)
    dst = Path(dst)
    if not dst.is_absolute():
        dst = Path.cwd() / dst
    dst = dst.resolve()
    if dst.is_dir():
        dst = dst / src.name
    if dst.exists():
        raise gc.GodotError("destination already exists: %s" % dst)
    try:
        dst.relative_to(project)
    except ValueError:
        raise gc.GodotError("destination is outside the project: %s" % dst)
    old_res, new_res = gc.to_res_path(project, src), gc.RES_PREFIX + dst.relative_to(project).as_posix()
    renames = [(src, dst)]
    for extra in (".uid", ".import"):
        side = src.with_name(src.name + extra)
        if side.is_file():
            renames.append((side, dst.with_name(dst.name + extra)))
    needle = '"%s"' % old_res
    rewrites, manual = [], []
    for fp in gc.iter_project_files(project, (".tscn", ".tres", ".godot", ".import", ".gd", ".cs"), SCAN_EXCLUDES):
        text = fp.read_text(encoding="utf-8", errors="replace")
        n = text.count(needle)
        if not n:
            continue
        if fp.suffix in (".gd", ".cs"):
            for ln, line in enumerate(text.splitlines(), 1):
                if needle in line:
                    manual.append({"file": str(fp), "line": ln, "text": line.strip()})
        else:
            rewrites.append({"file": str(fp), "count": n})
    return {"project": str(project), "src": str(src), "dst": str(dst), "old_res": old_res, "new_res": new_res,
            "renames": [{"from": str(a), "to": str(b)} for a, b in renames], "rewrites": rewrites, "manual": manual}


def apply_move(plan):
    needle, repl = '"%s"' % plan["old_res"], '"%s"' % plan["new_res"]
    for rw in plan["rewrites"]:
        fp = Path(rw["file"])
        fp.write_text(fp.read_text(encoding="utf-8").replace(needle, repl), encoding="utf-8")
    for rn in plan["renames"]:
        Path(rn["to"]).parent.mkdir(parents=True, exist_ok=True)
        Path(rn["from"]).rename(rn["to"])
    new_import = Path(plan["dst"]).with_name(Path(plan["dst"]).name + ".import")
    if new_import.is_file():  # .import records its own source path
        new_import.write_text(new_import.read_text(encoding="utf-8").replace(needle, repl), encoding="utf-8")
    # Godot's class_name cache is plain text and keeps the old path until the next
    # import; a stale entry makes the moved script fail with "hides a global script class".
    cache = Path(plan["project"]) / ".godot" / "global_script_class_cache.cfg"
    if cache.is_file():
        text = cache.read_text(encoding="utf-8", errors="replace")
        if needle in text:
            cache.write_text(text.replace(needle, repl), encoding="utf-8")
            plan["rewrites"].append({"file": str(cache), "count": text.count(needle)})


def reimport(plan, godot):
    r = gc.run_godot(["--headless", "--import", "--path", gc.host_path(plan["project"], godot)], timeout=300, godot=godot)
    errors, _ = gc.parse_log(r.output)
    if r.timed_out:
        errors.insert(0, "import timed out")
    elif r.returncode != 0:
        errors.insert(0, "godot --import exited with code %s" % r.returncode)
    plan["reimport"] = {"ok": not errors, "errors": errors, "command": r.cmd}
    return not errors


def cmd_move(args):
    plan = plan_move(args.src, args.dst)
    plan["applied"] = bool(args.apply)
    ok = True
    if args.apply:
        apply_move(plan)
        if not args.no_reimport:
            try:
                ok = reimport(plan, gc.find_godot(args.godot))
            except gc.GodotError as e:  # moved, but caches are stale: say so and fail
                plan["reimport"] = {"ok": False, "errors": ["%s (re-run: godot --headless --import)" % e]}
                ok = False
    if args.json:
        print(gc.json_dump(plan))
    else:
        print("%s %s -> %s" % ("MOVED" if args.apply else "DRY-RUN (add --apply)", plan["old_res"], plan["new_res"]))
        for rn in plan["renames"]:
            print("  rename  %s -> %s" % (rn["from"], rn["to"]))
        for rw in plan["rewrites"]:
            print("  rewrite %s (%d ref%s)" % (rw["file"], rw["count"], "" if rw["count"] == 1 else "s"))
        for m in plan["manual"]:
            print("  MANUAL  %s:%d: %s" % (m["file"], m["line"], m["text"]))
        if "reimport" in plan:
            print("  reimport %s" % ("ok" if plan["reimport"]["ok"] else "FAILED: " + "; ".join(plan["reimport"]["errors"])))
        elif args.apply:
            print("  note: --no-reimport given; .godot/uid_cache.bin stays stale until `godot --headless --import`")
    return 0 if ok and not plan["manual"] else 1


def build_parser():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd")
    c = sub.add_parser("check", help="scan a project (default when the first argument is a directory)")
    c.add_argument("project")
    c.add_argument("--fix", action="store_true", help="rewrite mismatched uid= refs and delete orphan sidecars")
    c.add_argument("--strict", action="store_true", help="warnings also fail")
    c.add_argument("--json", action="store_true")
    m = sub.add_parser("move", help="rename a file with its .uid sidecar and fix res:// path references")
    m.add_argument("src")
    m.add_argument("dst", help="new file path, or an existing directory")
    m.add_argument("--apply", action="store_true", help="write changes (default: dry-run)")
    m.add_argument("--no-reimport", action="store_true",
                   help="skip the `godot --headless --import` that --apply runs to refresh .godot/uid_cache.bin")
    m.add_argument("--godot", help="path to the Godot binary (for the re-import)")
    m.add_argument("--json", action="store_true")
    return p


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] not in ("check", "move", "-h", "--help"):
        argv.insert(0, "check")
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.cmd:
        parser.print_help()
        return 2
    try:
        return cmd_move(args) if args.cmd == "move" else cmd_check(args)
    except gc.GodotError as e:
        if args.json:
            print(gc.json_dump({"ok": False, "error": str(e)}))
        else:
            print("uid-keeper: error: %s" % e, file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
