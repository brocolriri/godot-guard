#!/usr/bin/env python3
"""Shared helpers for the godot-guard scripts (Python 3.8+, stdlib only).

Provides: Godot binary discovery, subprocess wrapper with ANSI stripping,
Godot log parsing (ERROR / SCRIPT ERROR / WARNING blocks), project file
iteration, and a generated SceneTree "runner" that loads scripts/scenes
inside a real Godot process and reports per-item results.

Facts verified on Godot 4.7.2 (2026-09-15):
- `--check-only -s file.gd` does NOT register autoloads, so any script that
  references an autoload singleton fails with "Compile Error: Identifier not
  found: <Autoload>". It is therefore only reliable for pure syntax checks.
- Inside a `-s` SceneTree script, autoloads are already in the tree during
  `_initialize()` (not during `_init()`), so the runner does its work there.
- Godot exits 0 even after SCRIPT ERROR / ERROR lines; output must be parsed.
- Without `--ignore-error-breaks`, `-d` + a script error blocks forever.
- Godot's error lines go to stderr; on the Windows console binary stdout and
  stderr interleave out of order, so runner markers are printed via printerr.
"""
import glob
import os
import platform
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")
RES_PREFIX = "res://"
FLATPAK_CMD = "flatpak run org.godotengine.Godot"
DEFAULT_EXCLUDES = ("addons", ".godot", ".git", ".import")
ERROR_HEADS = ("SCRIPT ERROR:", "USER SCRIPT ERROR:", "ERROR:", "USER ERROR:")
WARNING_HEADS = ("WARNING:", "USER WARNING:")
MARK = "@@GG|"


class GodotError(Exception):
    """Environment problem (binary missing, project missing, ...)."""


# ----------------------------------------------------------------- platform
def is_wsl():
    if sys.platform != "linux":
        return False
    return "microsoft" in platform.release().lower() or os.path.exists(
        "/proc/sys/fs/binfmt_misc/WSLInterop")


def is_windows_exe(godot):
    return str(godot).lower().endswith(".exe")


def host_path(path, godot):
    """Convert a WSL path to a Windows path when Godot is a Windows exe."""
    path = str(path)
    if is_wsl() and is_windows_exe(godot) and not re.match(r"^[A-Za-z]:", path):
        try:
            out = subprocess.run(["wslpath", "-w", path], stdout=subprocess.PIPE,
                                 stderr=subprocess.DEVNULL, check=True, timeout=10)
            return out.stdout.decode("utf-8", "replace").strip()
        except (OSError, subprocess.SubprocessError):
            return path
    return path


# ------------------------------------------------------------------ discovery
def _executable(p):
    return p and os.path.isfile(p) and os.access(p, os.X_OK)


def _candidate_globs():
    home = Path.home()
    pats = []
    if sys.platform == "win32":
        lad = os.environ.get("LOCALAPPDATA", "")
        pf = os.environ.get("ProgramFiles", r"C:\Program Files")
        pf86 = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
        pats += [
            os.path.join(lad, "Microsoft", "WinGet", "Packages", "GodotEngine.*", "Godot*_console.exe"),
            os.path.join(lad, "Microsoft", "WinGet", "Packages", "GodotEngine.*", "Godot*.exe"),
            os.path.join(pf, "Godot*", "Godot*.exe"), os.path.join(pf86, "Godot*", "Godot*.exe"),
            str(home / "Downloads" / "Godot*_console.exe"), str(home / "Downloads" / "Godot*.exe"),
            str(home / "Desktop" / "Godot*.exe"),
            os.path.join(pf86, "Steam", "steamapps", "common", "Godot Engine", "godot*.exe"),
        ]
    elif sys.platform == "darwin":
        pats += [
            "/Applications/Godot.app/Contents/MacOS/Godot", "/Applications/Godot*.app/Contents/MacOS/Godot",
            str(home / "Applications" / "Godot*.app" / "Contents" / "MacOS" / "Godot"),
            str(home / "Library/Application Support/Steam/steamapps/common/Godot Engine/Godot.app/Contents/MacOS/Godot"),
        ]
    else:
        pats += [
            str(home / ".local" / "bin" / "godot*"), "/usr/local/bin/godot*", "/opt/godot*/godot*",
            "/opt/godot*", str(home / "godot*"), str(home / "Downloads" / "Godot_v4*"),
            str(home / ".steam" / "steam" / "steamapps" / "common" / "Godot Engine" / "godot*"),
        ]
        if is_wsl():
            pats += [
                "/mnt/c/Users/*/AppData/Local/Microsoft/WinGet/Packages/GodotEngine.*/Godot*_console.exe",
                "/mnt/c/Program Files/Godot*/Godot*_console.exe",
                "/mnt/c/Users/*/Downloads/Godot*_console.exe",
            ]
    return pats


def _version_key(p):
    m = re.search(r"(\d+)\.(\d+)(?:\.(\d+))?", os.path.basename(p))
    return tuple(int(x or 0) for x in m.groups()) if m else (0, 0, 0)


def find_godot(explicit=None):
    """Return a Godot command string, or raise GodotError.

    Order: explicit (--godot) > $GODOT_BIN > PATH > common install dirs > flatpak.
    """
    for src, val in (("--godot", explicit), ("GODOT_BIN", os.environ.get("GODOT_BIN"))):
        if val:
            if _executable(val) or shutil.which(val):
                return val
            raise GodotError("%s points to a non-executable path: %s" % (src, val))
    for name in ("godot", "godot4", "Godot", "godot4-mono", "godot-mono"):
        p = shutil.which(name)
        if p:
            return p
    found = []
    for pat in _candidate_globs():
        found += [p for p in glob.glob(pat) if _executable(p) and not p.endswith((".zip", ".txt"))]
    if found:
        found = [p for p in found if ".mono" not in p and "mono" not in os.path.basename(p)] or found
        found.sort(key=_version_key, reverse=True)
        return found[0]
    if shutil.which("flatpak"):
        try:
            r = subprocess.run(["flatpak", "info", "org.godotengine.Godot"], stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL, timeout=15)
            if r.returncode == 0:
                return FLATPAK_CMD
        except (OSError, subprocess.SubprocessError):
            pass
    raise GodotError("Godot binary not found. Set GODOT_BIN or pass --godot /path/to/godot")


def godot_cmd(godot):
    return godot.split() if godot.startswith("flatpak run ") else [godot]


# --------------------------------------------------------------------- running
class RunResult(object):
    def __init__(self, cmd, returncode, output, duration, timed_out):
        self.cmd, self.returncode, self.output = cmd, returncode, output
        self.duration, self.timed_out = duration, timed_out

    @property
    def lines(self):
        return self.output.splitlines()


def clean_output(raw):
    text = raw.decode("utf-8", "replace") if isinstance(raw, bytes) else (raw or "")
    return ANSI_RE.sub("", text).replace("\r\n", "\n").replace("\r", "\n")


def run_godot(args, cwd=None, timeout=120, godot=None):
    """Run Godot with args; stdout+stderr merged, ANSI stripped. Never raises on failure."""
    godot = godot or find_godot()
    cmd = godot_cmd(godot) + [str(a) for a in args]
    start = time.time()
    timed_out, code, out = False, None, b""
    try:
        r = subprocess.run(cmd, cwd=str(cwd) if cwd else None, stdout=subprocess.PIPE,
                           stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, timeout=timeout)
        code, out = r.returncode, r.stdout
    except subprocess.TimeoutExpired as e:
        timed_out, out = True, e.output or b""
    except OSError as e:
        raise GodotError("cannot execute %s: %s" % (cmd[0], e))
    return RunResult(cmd, code, clean_output(out), round(time.time() - start, 3), timed_out)


def get_version(godot=None, timeout=30):
    r = run_godot(["--version"], timeout=timeout, godot=godot)
    for line in r.lines:
        line = line.strip()
        if re.match(r"^\d+\.\d+", line):
            return line
    return (r.lines[-1].strip() if r.lines else "") or "unknown"


# --------------------------------------------------------------- log parsing
def parse_log(text):
    """Group Godot output into (errors, warnings) lists of one-line strings.

    A block is a head line (`ERROR: ...`, `SCRIPT ERROR: ...`, `WARNING: ...`)
    plus the indented lines that follow it (`at: ...`, backtraces). The
    returned string is `<head> | <at: location>`.
    """
    errors, warnings, cur = [], [], None

    def flush():
        if cur is None:
            return
        kind, head, at = cur
        msg = head if not at else "%s  (%s)" % (head, at)
        (errors if kind == "e" else warnings).append(msg)

    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if line[:1] not in (" ", "\t"):
            flush()
            cur = None
            if stripped.startswith(ERROR_HEADS):
                cur = ["e", stripped, ""]
            elif stripped.startswith(WARNING_HEADS):
                cur = ["w", stripped, ""]
        elif cur is not None and stripped.startswith("at:") and not cur[2]:
            cur[2] = stripped[3:].strip()
    flush()
    return errors, warnings


# ------------------------------------------------------------------ project
def require_project(path):
    p = Path(path).resolve()
    if p.is_file() and p.name == "project.godot":
        p = p.parent
    if not (p / "project.godot").is_file():
        raise GodotError("not a Godot project (no project.godot): %s" % p)
    return p


def find_project_root(start):
    p = Path(start).resolve()
    for d in [p] + list(p.parents):
        if (d / "project.godot").is_file():
            return d
    return None


def iter_project_files(root, suffixes, excludes=DEFAULT_EXCLUDES):
    """Yield files under root with the given suffixes, skipping excluded and .gdignore'd dirs."""
    root = Path(root)
    for dirpath, dirnames, filenames in os.walk(str(root)):
        rel = Path(dirpath).relative_to(root)
        top = rel.parts[0] if rel.parts else ""
        if top in excludes or (rel.parts and rel.parts[-1].startswith(".")) or ".gdignore" in filenames:
            dirnames[:] = []
            continue
        dirnames[:] = sorted(d for d in dirnames if d not in excludes and not d.startswith("."))
        for fn in sorted(filenames):
            if fn.endswith(tuple(suffixes)):
                yield Path(dirpath) / fn


def to_res_path(project, file):
    return RES_PREFIX + Path(file).resolve().relative_to(Path(project).resolve()).as_posix()


def from_res_path(project, res):
    return Path(project) / res[len(RES_PREFIX):] if res.startswith(RES_PREFIX) else Path(project) / res


# ------------------------------------------------------------------- runner
RUNNER_TEMPLATE = '''extends SceneTree
# Generated by godot-guard; safe to delete.
const KIND := "%(kind)s"
const ITEMS := %(items)s

func _initialize() -> void:
\tfor p in ITEMS:
\t\tprinterr("%(mark)sBEGIN|" + p)
\t\tvar status := "ok"
\t\tvar res = ResourceLoader.load(p, "", ResourceLoader.CACHE_MODE_REPLACE)
\t\tif res == null:
\t\t\tstatus = "load_failed"
\t\telif KIND == "scene":
\t\t\tif not (res is PackedScene):
\t\t\t\tstatus = "not_a_packed_scene"
\t\t\telse:
\t\t\t\tvar inst = res.instantiate()
\t\t\t\tif inst == null:
\t\t\t\t\tstatus = "instantiate_failed"
\t\t\t\telse:
\t\t\t\t\tinst.free()
\t\telif KIND == "script":
\t\t\tif not (res is Script):
\t\t\t\tstatus = "not_a_script"
\t\tprinterr("%(mark)sEND|" + p + "|" + status)
\tprinterr("%(mark)sDONE")
\tquit(0)
'''


def _gd_string_array(items):
    return "[" + ", ".join('"%s"' % s.replace("\\", "\\\\").replace('"', '\\"') for s in items) + "]"


def run_runner(project, kind, res_paths, godot=None, timeout=120):
    """Load (and for scenes instantiate) each res:// path inside Godot.

    Returns (RunResult, items) where items is a list of dicts
    {path, ok, status, errors, warnings}. Errors printed between an item's
    BEGIN/END markers are attributed to that item. The runner script is written
    into <project>/.godot/ (already .gdignore'd) and removed afterwards.
    """
    project = Path(project)
    godot = godot or find_godot()
    cache = project / ".godot"
    cache.mkdir(exist_ok=True)
    runner = cache / ("godot_guard_runner_%s_%d.gd" % (kind, os.getpid()))
    runner.write_text(RUNNER_TEMPLATE % {"kind": kind, "items": _gd_string_array(res_paths), "mark": MARK},
                      encoding="utf-8")
    try:
        r = run_godot(["--headless", "--path", host_path(project, godot), "-s", host_path(runner, godot)],
                      timeout=timeout, godot=godot)
    finally:
        try:
            runner.unlink()
        except OSError:
            pass
    items, by_path, current, buf, done = [], {}, None, [], False
    for p in res_paths:
        items.append({"path": p, "ok": False, "status": "not_reached", "errors": [], "warnings": []})
        by_path[p] = items[-1]
    for line in r.lines:
        s = line.strip()
        if s.startswith(MARK):
            parts = s[len(MARK):].split("|")
            if parts[0] == "BEGIN":
                current, buf = by_path.get(parts[1]), []
            elif parts[0] == "END" and current is not None:
                e, w = parse_log("\n".join(buf))
                status = parts[2] if len(parts) > 2 else "unknown"
                current.update(status=status, errors=e, warnings=w, ok=(status == "ok" and not e))
                current, buf = None, []
            elif parts[0] == "DONE":
                done = True
            continue
        if current is not None:
            buf.append(line)
    if not done or r.timed_out or (r.returncode not in (0, None)):
        # Runner never finished: attribute the whole log to whatever was not reached.
        e, w = parse_log(r.output)
        reason = "timed out after %ss" % timeout if r.timed_out else "Godot exited with code %s before finishing" % r.returncode
        for it in items:
            if it["status"] == "not_reached":
                it["errors"] = [reason] + e
                it["warnings"] = w
    return r, items


def json_dump(obj):
    import json
    return json.dumps(obj, indent=2, ensure_ascii=False)
