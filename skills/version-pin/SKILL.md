---
name: version-pin
description: Pin the exact Godot version of the current project into CLAUDE.md (from project.godot config/features and the installed godot binary), with the agent rules and the matching 4.x delta table. Use once when starting work on a Godot project, when the project is upgraded to a new Godot minor, or when Claude keeps using APIs from the wrong Godot version.
argument-hint: [project_dir] [--godot /path/to/godot]
allowed-tools: Bash(python3 *) Read
---

# Version pin

LLMs mix Godot 3, 4.2 and 4.7 APIs unless the target version is in front of them on every turn.
This skill writes an idempotent block into the project's `CLAUDE.md` so the pin, the renderer,
the autoloads and the working rules are always in context.

## Run it

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/version_pin.py" $ARGUMENTS --write CLAUDE.md
```

- Finds the Godot binary via `--godot`, `$GODOT_BIN`, `PATH`, then common install folders
  (winget, Program Files, `/Applications/Godot.app`, `~/.local/bin`, Steam, flatpak).
- Compares `project.godot` `config/features` (e.g. `4.7`) with `godot --version`.
  A mismatch exits `1` and is written into the block: tell the user before continuing.
- Safe to run repeatedly: it replaces the block between `<!-- godot-guard:begin -->` and
  `<!-- godot-guard:end -->` and leaves the rest of `CLAUDE.md` untouched.

## After running

1. `Read` the generated block. If the binary was not found, ask the user for the path once and
   re-run with `--godot`.
2. Follow the block's numbered rules for the rest of the session. In particular: run
   `api_guard` on every `.gd` you touch, take node paths from `scene-map`, and do not claim a
   task is finished without a verify run.
3. When `project.godot` says a different minor than the binary, do not "fix" `config/features`
   yourself: that line is what the editor uses to decide compatibility. Report it.

## Reference tables

The block links the delta table for the pinned minor (`reference/deltas_4.4-4.7.md` in this
plugin). Open it when an API is uncertain: it lists what changed in 4.4, 4.5, 4.6 and 4.7 with
the official source for each row.
