# Godot 4.7 headless command-line facts (for a verification script)

Verified 2026-09-15 against the official [Command line tutorial](https://docs.godotengine.org/en/stable/tutorials/editor/command_line_tutorial.html) (docs `stable` = 4.7), the `4.7` branch of [`main/main.cpp`](https://github.com/godotengine/godot/blob/4.7/main/main.cpp) (help text + exit paths), [`core/io/logger.cpp`](https://github.com/godotengine/godot/blob/4.7/core/io/logger.cpp), [`modules/gdscript/gdscript.cpp`](https://github.com/godotengine/godot/blob/4.7/modules/gdscript/gdscript.cpp), and the 4.7 class reference ([SceneTree](https://docs.godotengine.org/en/stable/classes/class_scenetree.html), [MainLoop](https://docs.godotengine.org/en/stable/classes/class_mainloop.html)).

## Build-availability legend (from the tutorial)

| tag | meaning |
|---|---|
| `release` | editor builds, debug export templates and release export templates |
| `debug` | editor builds and debug export templates only |
| `extended` | editor builds, and export templates compiled with `disable_path_overrides=false` (= `OVERRIDE_PATH_ENABLED` in main.cpp) |
| `editor` | **editor builds only** |

The tutorial also warns: *"unknown command line arguments have no effect whatsoever. The engine will not warn you when using a command line argument that doesn't exist with a given build type."* So a script must check the exit code and output, never assume a flag was honored.

## Flags

| flag | availability | verified behavior | source |
|---|---|---|---|
| `--headless` | release | "Enable headless mode (`--display-driver headless --audio-driver Dummy`). Useful for servers and with `--script`." Required on machines without GPU access (CI); on GPU machines it only prevents a window. | tutorial; main.cpp help |
| `--path <dir>` | extended | `<dir>` must contain `project.godot`; sets the working directory (`OS::set_cwd`); invalid path prints `Invalid project path specified ... aborting.` and aborts. | main.cpp `--path` handler |
| `-s`, `--script <script>` | extended | Runs a script that **must inherit `SceneTree` or `MainLoop`**; path is `res://`-relative to the project or an absolute filesystem path. If it does not inherit one of those: alert `Can't load the script "..." as it doesn't inherit from SceneTree or MainLoop.` and `EXIT_FAILURE`. Load failure: `Can't load script: ...` and `EXIT_FAILURE`. | tutorial "Running a script"; main.cpp `Main::start` |
| `--main-loop <GlobalClassName>` | extended | Run a MainLoop by global class name; missing class or wrong base → `EXIT_FAILURE`. | main.cpp |
| `--check-only` | extended | "Only parse for errors and quit (use with `--script`)." Implementation: `return script_res->is_valid() ? EXIT_SUCCESS : EXIT_FAILURE;` — i.e. **exit 0 if the script (and what it statically depends on) parses/analyzes, exit 1 otherwise**. It only checks the one script given to `--script`; it does not walk the project. The script does not need to extend SceneTree for `--check-only` (the base-type check happens after the check-only return). | main.cpp lines ~4368-4374 |
| `--quit` | release | "Quit after the first iteration." Sets `quit_after = 1`; in editor builds also sets `wait_for_import = true`. | main.cpp |
| `--quit-after <int>` | release | "Quit after the given number of iterations. Set to 0 to disable." Compared against `Engine::_process_frames` each iteration (`_process_frames >= quit_after` → exit). Missing number → `Missing number of iterations, aborting.` | main.cpp |
| `-d`, `--debug` | release | "Debug (local stdout debugger)." Sets `debug_uri = "local://"` and `OS::_debug_stdout = true`; script errors/warnings from the debugger are printed to stdout. Tutorial: `godot -d` / `godot -d scene.tscn`. | tutorial "Debugging"; main.cpp |
| `--ignore-error-breaks` | release | "If debugger is connected, prevents sending error breakpoints." Use together with `-d` so runtime errors do not pause the local debugger. | main.cpp help |
| `-v`, `--verbose` | release | "Use verbose stdout mode" (`OS::_verbose_stdout = true`); also forwarded to editor-spawned instances. | main.cpp |
| `-q`, `--quiet` | release | Silences stdout messages; errors are still displayed. | tutorial |
| `--no-header` | release | Do not print the engine version / rendering method header. | tutorial |
| `--log-file <file>` | release | Write output/error log to a path (absolute or project-relative). | main.cpp help |
| `-e`, `--editor` | **editor** | Start the editor instead of running the scene. | tutorial |
| `--import` | **editor** | "Starts the editor, waits for any resources to be imported, and then quits." Implies `--editor` and `--quit` (sets `editor = true; wait_for_import = true; quit_after = 1`). | tutorial; main.cpp |
| `--editor --quit --headless` | **editor** | Equivalent older idiom for "reimport and exit": `--quit` in an editor build sets `wait_for_import = true`, so the exit is delayed until the first filesystem scan finishes (`EditorFileSystem::doing_first_scan()`). Prefer `--import`. | main.cpp `--quit` handler + iteration loop |
| `--export-release <preset> <path>` | **editor** | Export in release mode; `<preset>` must match a name in `export_presets.cfg` (quote names with spaces); `<path>` is absolute **or relative to the project directory (not the cwd)**, must include the binary filename, and the target directory must exist. Requires installed export templates. `--export-debug` same but debug template; both imply `--import`. | tutorial "Exporting"; main.cpp help |
| `--export-pack <preset> <path>` | **editor** | Only the PCK/ZIP (format by extension). Implies `--import`. `--export-patch` + `--patches` for delta packs. | tutorial |
| `--doctool [path]` | **editor** | Dumps the engine API reference as XML into `<path>` (default `.`), merging with existing files; **implies `--headless`**. Must be run from the Godot repo root or given a path pointing there (`--doctool must be run from the Godot repository's root folder ... aborting` → `EXIT_FAILURE`). `--gdscript-docs <path>` generates docs from `##` comments in a project's scripts instead. | main.cpp; tutorial |
| `--validate-extension-api <file>` | **editor** | Non-zero exit if incompatibilities are detected (`valid ? EXIT_SUCCESS : EXIT_FAILURE`). | tutorial; main.cpp |
| `--scene <path-or-uid>` | extended | Scene to start. Passing a positional `scene.tscn` also works (`godot -d scene.tscn`). If a UID cannot be resolved: `Main scene's path could not be resolved from UID. Make sure the project is imported first.` → `EXIT_FAILURE`. | main.cpp |
| `--` / `++` | release | Everything after is a user argument, readable with `OS.get_cmdline_user_args()`. | tutorial |

## Exit codes (from main.cpp, 4.7)

- Normal exit is `EXIT_SUCCESS` (0). A script sets its own code with `get_tree().quit(exit_code: int = 0)` (SceneTree) — `quit()` defaults to 0.
- `MainLoop._process(delta) -> bool` / `_physics_process(delta) -> bool`: returning `true` ends the loop (MainLoop class reference); exit code stays 0 unless set otherwise.
- Startup failures return `EXIT_FAILURE` (1): unloadable `--script`, script not inheriting SceneTree/MainLoop, `--check-only` parse failure, missing export preset name (`Missing export preset name, aborting.`), invalid `--path`, bad `--doctool` path, unresolvable main-scene UID, `Couldn't detect whether to run the editor, the project manager or a specific project.`
- `OS::set_exit_code(EXIT_FAILURE)` is called for: self-contained editor colocated with a project; `--build-solutions` without a project or a failed C# build.
- **`--export-*` does not set a non-zero exit code for a failed export in `main.cpp`** — the export is dispatched to `EditorNode::export_preset(...)` and the process ends via the normal quit path. The kit's `export-check` skill must therefore verify the output file exists and parse stderr, not trust exit 0 (the SPEC.md "종료코드 0 함정" item). Exit code behavior of `EditorNode::export_preset` itself was **not verified** here; treat exit 0 as "no fatal startup error", nothing more.
- Runtime script errors (`push_error`, failed asserts in debug, unhandled errors) do **not** by themselves change the exit code; they print to stderr. A verification script must grep stderr/stdout for `ERROR:`/`SCRIPT ERROR:`/`WARNING:` lines.
- The lock file is only removed when the exit code is `EXIT_SUCCESS`; a leftover lock file is a hint of a failed run.

## Where output goes

| what | stream | source |
|---|---|---|
| `print()`, `OS.print`, verbose messages | **stdout** (`StdLogger::logv`: `vprintf`) | logger.cpp |
| Engine errors/warnings (`ERROR:`, `WARNING:`, `SCRIPT ERROR:`), `printerr()`, `push_error()`, `push_warning()` | **stderr** (`vfprintf(stderr, ...)` when `p_err`) | logger.cpp; `OS::print_error` |
| GDScript **static warnings** (UNUSED_VARIABLE, STANDALONE_EXPRESSION, ...) during `--check-only` / script load | Only forwarded when a script debugger is active (`EngineDebugger::is_active()` → `send_error(... ERR_HANDLER_WARNING ...)`), i.e. with `-d`. Without `-d` static warnings are not printed by `GDScript::reload`. Warnings are controlled by `debug/gdscript/warnings/enable` (default true), can be promoted to errors per-warning in Project Settings › Debug › GDScript, and `res://addons` is excluded by default via `debug/gdscript/warnings/directory_rules`. | gdscript.cpp ~L873-879, ~L2878-2884; [warning system](https://docs.godotengine.org/en/stable/tutorials/scripting/gdscript/warning_system.html) |
| `-d` local debugger output (script errors with backtraces, warnings) | stdout (`_debug_stdout = true`) | main.cpp |
| `--log-file` | duplicates both streams to the file | main.cpp help |

Practical consequence for the verifier: run with `--headless -d --ignore-error-breaks`, capture **both** streams, and treat any `SCRIPT ERROR`/`ERROR` line as failure regardless of exit code.

## Minimal `--script` runner (verified shape)

```gdscript
#!/usr/bin/env -S godot -s
extends SceneTree

func _init():
    print("Hello!")
    quit()          # quit(exit_code := 0)
```

Run: `godot --headless --path /proj -s res://tools/verify.gd` (the tutorial example uses `godot -s sayhello.gd`; if no `project.godot` exists at the path the cwd is used as the project unless `--path` is given). A `MainLoop` subclass may be used instead and can also be selected with `application/run/main_loop_type`.

Recommended verification sequence (each step's exit code and stderr checked):

1. `godot --headless --path <proj> --import` — reimport, needs an **editor** binary.
2. `godot --headless --path <proj> -s <file.gd> --check-only` per script — parse/analyze only; exit 1 on failure. Note: scripts can be checked even if they do not extend SceneTree (the check-only return happens before the base-type test).
3. `godot --headless --path <proj> -d --ignore-error-breaks --quit-after <N>` — run the main scene for N frames; or `-s res://verify_scenes.gd` that `instantiate()`s every `.tscn` and calls `quit(1)` on failure.
4. `godot --headless --path <proj> --export-release "<preset>" <out>` — then check that `<out>` exists and stderr has no `ERROR`.

## Notes / unverified

- `--check-only`, `-s/--script`, `--main-loop` and `--path` are `extended` (not editor-only) per the tutorial legend and `#if defined(OVERRIDE_PATH_ENABLED)` in main.cpp. Whether the official downloadable export templates are built with `disable_path_overrides` was **not verified**; use the **editor** binary for all steps above (steps 1 and 4 require it anyway).
- Whether `--check-only` reports warnings promoted to errors as failures was not tested here (it returns `script_res->is_valid()`, which reflects the compile result including treat-as-error warnings, but this is inferred from source, not run).
- `EditorNode::export_preset` exit-code behavior: not verified (see Exit codes).
