#!/usr/bin/env python3
"""godot-verify: prove a Godot 4 project actually imports, parses, instantiates and runs.

Pipeline (each step is reported separately, all run unless skipped):
  import   `godot --headless --import`      only when .godot/ is missing or --reimport
  parse    load every .gd inside a SceneTree runner (autoloads available)
  scenes   load + instantiate every .tscn (addons/ and .godot/ excluded)
  run      run the main scene `-d --ignore-error-breaks --quit-after N`

Godot returns exit code 0 even when it printed SCRIPT ERROR / ERROR lines, so
every step is judged by parsing its output, never by the exit code alone.

Exit codes: 0 all steps ok, 1 at least one step failed, 2 usage/environment error.

Why not `--check-only`? On 4.7.2 it does not register autoloads, so any script
that references an autoload (e.g. `Events.foo.emit()`) fails with
"Compile Error: Identifier not found: Events" even though the project is fine.
Use --check-only-mode to opt into it anyway (pure syntax projects).
"""
import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import godot_common as gc  # noqa: E402
try:
    import upgrade_hint  # noqa: E402
except Exception:
    upgrade_hint = None


def step(name, ok, duration, errors=None, warnings=None, **extra):
    d = {"name": name, "ok": bool(ok), "duration": round(duration, 3),
         "errors": list(errors or []), "warnings": list(warnings or [])}
    d.update(extra)
    return d


def has_godot_cache(project):
    return (project / ".godot").is_dir() and any((project / ".godot").iterdir())


def step_import(project, godot, timeout, reimport, skip):
    if skip:
        return step("import", True, 0.0, skipped=True, note="--skip-import")
    if has_godot_cache(project) and not reimport:
        return step("import", True, 0.0, skipped=True, note=".godot/ present (use --reimport to force)")
    r = gc.run_godot(["--headless", "--import", "--path", gc.host_path(project, godot)], timeout=timeout, godot=godot)
    errors, warnings = gc.parse_log(r.output)
    if r.timed_out:
        errors.insert(0, "import timed out after %ss" % timeout)
    elif r.returncode != 0:
        errors.insert(0, "godot --import exited with code %s" % r.returncode)
    if not has_godot_cache(project):
        errors.append("no .godot/ directory was produced by --import")
    return step("import", not errors, r.duration, errors, warnings, command=r.cmd)


def _item_step(name, project, kind, files, godot, timeout, check_only=False):
    start = time.time()
    if not files:
        return step(name, True, 0.0, skipped=True, note="no %s files found" % kind)
    res_paths = [gc.to_res_path(project, f) for f in files]
    if check_only:
        return _check_only_step(name, project, res_paths, godot, timeout)
    r, items = gc.run_runner(project, kind, res_paths, godot=godot, timeout=timeout)
    errors, warnings = [], []
    for it in items:
        for e in it["errors"]:
            errors.append("%s: %s" % (it["path"], e))
        if not it["ok"] and not it["errors"]:
            errors.append("%s: %s" % (it["path"], it["status"]))
        for w in it["warnings"]:
            warnings.append("%s: %s" % (it["path"], w))
    failed = [it["path"] for it in items if not it["ok"]]
    return step(name, not failed, time.time() - start, errors, warnings, command=r.cmd,
                checked=len(items), failed=failed)


def _check_only_step(name, project, res_paths, godot, timeout):
    """Alternative parse step using `--check-only -s` per script (no autoloads!)."""
    start, errors, warnings, failed = time.time(), [], [], []
    for p in res_paths:
        r = gc.run_godot(["--headless", "--check-only", "--path", gc.host_path(project, godot), "-s", p],
                         timeout=timeout, godot=godot)
        e, w = gc.parse_log(r.output)
        if r.timed_out:
            e.insert(0, "check-only timed out after %ss" % timeout)
        if r.returncode != 0 and not e:
            e.append("exit code %s" % r.returncode)
        if e:
            failed.append(p)
        errors += ["%s: %s" % (p, x) for x in e]
        warnings += ["%s: %s" % (p, x) for x in w]
    return step(name, not failed, time.time() - start, errors, warnings, checked=len(res_paths), failed=failed,
                mode="check-only")


def main_scene(project):
    import re
    try:
        text = (project / "project.godot").read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    m = re.search(r'^run/main_scene="([^"]*)"', text, re.M)
    return m.group(1) if m else None


def step_run(project, godot, frames, timeout, scene=None):
    scene = scene or main_scene(project)
    if not scene:
        return step("run", True, 0.0, skipped=True, note="no run/main_scene in project.godot (pass --run-scene)")
    args = ["--headless", "-d", "--ignore-error-breaks", "--quit-after", str(frames), "--path",
            gc.host_path(project, godot), scene]
    r = gc.run_godot(args, timeout=timeout, godot=godot)
    errors, warnings = gc.parse_log(r.output)
    if r.timed_out:
        errors.insert(0, "run timed out after %ss (frames=%d)" % (timeout, frames))
    elif r.returncode != 0:
        errors.insert(0, "godot exited with code %s" % r.returncode)
    return step("run", not errors, r.duration, errors, warnings, command=r.cmd, scene=scene, frames=frames)


def collect(project, suffix, only=None, include_addons=False):
    excludes = tuple(x for x in gc.DEFAULT_EXCLUDES if include_addons is False or x != "addons")
    files = list(gc.iter_project_files(project, (suffix,), excludes))
    if only:
        wanted = set()
        for s in only:
            s = s.strip().replace("\\", "/")
            wanted.add(s[len(gc.RES_PREFIX):] if s.startswith(gc.RES_PREFIX) else s)
        files = [f for f in files if f.relative_to(project).as_posix() in wanted]
        missing = wanted - {f.relative_to(project).as_posix() for f in files}
        if missing:
            raise gc.GodotError("scene(s) not found in project: %s" % ", ".join(sorted(missing)))
    return files


def human(report):
    out = ["godot-verify  %s  (Godot %s)" % (report["project"], report["godot_version"])]
    for s in report["steps"]:
        tag = "SKIP" if s.get("skipped") else ("ok" if s["ok"] else "FAIL")
        extra = s.get("note") or ("%d checked" % s["checked"] if "checked" in s else "")
        out.append("  [%-4s] %-7s %6.2fs  %s" % (tag, s["name"], s["duration"], extra))
        for e in s["errors"]:
            out.append("         ERROR    " + e)
        for w in s["warnings"]:
            out.append("         warning  " + w)
    n = sum(len(s["errors"]) for s in report["steps"])
    out.append("VERIFY: %s" % ("PASS" if report["ok"] else "FAIL (%d error%s)" % (n, "" if n == 1 else "s")))
    return "\n".join(out)


def build_parser():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("project", help="project directory (contains project.godot)")
    p.add_argument("--frames", type=int, default=30, help="frames to run the main scene (default 30)")
    p.add_argument("--scenes", help="comma-separated .tscn list to instantiate instead of all")
    p.add_argument("--run-scene", help="scene to run instead of run/main_scene")
    p.add_argument("--skip-import", action="store_true", help="never run --import")
    p.add_argument("--reimport", action="store_true", help="run --import even if .godot/ exists")
    p.add_argument("--skip-run", action="store_true", help="skip the run step")
    p.add_argument("--include-addons", action="store_true", help="also check scripts/scenes under addons/")
    p.add_argument("--check-only-mode", action="store_true",
                   help="parse with `--check-only -s` per script instead of the runner (no autoloads)")
    p.add_argument("--timeout", type=float, default=120, help="seconds per Godot invocation (default 120)")
    p.add_argument("--godot", help="path to the Godot binary (else $GODOT_BIN, PATH, common dirs)")
    p.add_argument("--json", action="store_true", help="print the JSON report only")
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        project = gc.require_project(args.project)
        godot = gc.find_godot(args.godot)
        version = gc.get_version(godot, timeout=min(args.timeout, 60))
        steps = [step_import(project, godot, args.timeout, args.reimport, args.skip_import)]
        scripts = collect(project, ".gd", include_addons=args.include_addons)
        steps.append(_item_step("parse", project, "script", scripts, godot, args.timeout, args.check_only_mode))
        scenes = collect(project, ".tscn", args.scenes.split(",") if args.scenes else None, args.include_addons)
        steps.append(_item_step("scenes", project, "scene", scenes, godot, args.timeout))
        if args.skip_run:
            steps.append(step("run", True, 0.0, skipped=True, note="--skip-run"))
        else:
            steps.append(step_run(project, godot, args.frames, args.timeout, args.run_scene))
    except gc.GodotError as e:
        if args.json:
            print(gc.json_dump({"ok": False, "error": str(e)}))
        else:
            print("godot-verify: error: %s" % e, file=sys.stderr)
        return 2
    report = {"godot": godot, "godot_version": version, "project": str(project),
              "steps": steps, "ok": all(s["ok"] for s in steps)}
    print(gc.json_dump(report) if args.json else human(report))
    _write_state(project, report)
    if upgrade_hint and not args.json and not report["ok"]:
        upgrade_hint.emit("verify-failed")
    return 0 if report["ok"] else 1


def _write_state(project, report):
    """Record the last verify run for the Stop hook (verify_gate.py). Never fatal."""
    try:
        import time as _t
        d = Path(project) / ".godot-guard"
        d.mkdir(exist_ok=True)
        (d / "last_verify.json").write_text(gc.json_dump({
            "time": _t.time(), "ok": bool(report["ok"]), "godot_version": report.get("godot_version"),
            "steps": [{"name": s["name"], "ok": s["ok"]} for s in report["steps"]]}))
        gi = d / ".gitignore"
        if not gi.exists():
            gi.write_text("*\n")
    except Exception:
        pass


if __name__ == "__main__":
    sys.exit(main())
