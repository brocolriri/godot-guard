# godot-guard — Godot 4 guardrails for Claude Code

**Verified on Godot 4.7.2 (2026-09-15).** Three skills + one hook that stop the most common ways
Claude Code breaks a Godot 4 project:

| Problem | Skill | What it does |
|---|---|---|
| Godot 3 syntax leaks in (`yield`, `.instance()`, `connect("sig", self, "m")`, `KinematicBody2D`, `export var`, invented APIs like `Signal.any`) | `/godot-guard:godot4-api-guard` | Deterministic scanner over `.gd`/`.tscn`/`.cs` with fix + official source per rule. Runs automatically after every edit (PostToolUse hook). |
| Guessed node paths → `Node not found`, null `@onready` | `/godot-guard:scene-map` | Reads every `.tscn` and writes `.claude/scene-map.md`: node tree, types, scripts, `%unique` names, `[connection]` signals, groups, autoloads, and the exact `$Path`/`%Name` to use. |
| Wrong Godot version in Claude's head | `/godot-guard:version-pin` | Pins `project.godot` `config/features` + `godot --version` into `CLAUDE.md` with working rules, idempotently. |

Pure Python 3.8+ standard library. No MCP server, no editor plugin, no network. Works on Windows, macOS, Linux and WSL.

## Install

```bash
# from the community marketplace (once listed)
/plugin marketplace add anthropics/claude-plugins-community
/plugin install godot-guard@claude-community

# or straight from this repo
git clone https://github.com/brocolriri/godot-guard
claude --plugin-dir ./godot-guard
```

Then, inside your Godot project:

```text
/godot-guard:version-pin
/godot-guard:scene-map
/godot-guard:godot4-api-guard
```

## What it looks like

```text
$ python3 scripts/api_guard.py .
player.gd:13:2: [error] yield: yield(get_tree().create_timer(1.0), "timeout")
    fix: -> await get_tree().create_timer(1.0).timeout
    see: https://docs.godotengine.org/en/stable/tutorials/migrating/upgrading_to_godot_4.html
player.gd:28:2: [error] move_and_slide_arg: move_and_slide(velocity)
    fix: velocity = v; move_and_slide()
2 finding(s) in 1 file(s)
```

```text
### Access expressions (from `Main`'s script; use verbatim)
| Node | Type | Use this | Also valid |
| Player | CharacterBody2D | `%Player` | `$Player` |
| Enemies/Enemy | CharacterBody2D | `$Enemies/Enemy` | `get_node("Enemies/Enemy")` |
| HUD/ScoreLabel | Label | `$HUD/ScoreLabel` | |
```

## Scripts (usable without Claude)

| Script | Purpose |
|---|---|
| `scripts/api_guard.py <path...> [--json] [--hook] [--list-rules]` | Godot-3-ism / 4.x-drift linter |
| `scripts/scene_map.py <project|file.tscn> [--out .claude/scene-map.md] [--json]` | Scene tree → markdown map |
| `scripts/version_pin.py <project> [--godot BIN] [--write CLAUDE.md]` | Version block into CLAUDE.md |

Rules live in `reference/godot3_isms.json` and `reference/deltas.json` (each row cites the official Godot doc).

## Pro version

**[Godot 4 Guardrails Pro](https://brocolriri.gumroad.com/l/godot-guard-pro)** adds the proof layer:
`godot-verify` (import → parse → instantiate every scene → run N frames, JSON result, honest exit code),
`tscn-surgeon` + `uid-keeper` (safe scene/resource edits with `.uid` sidecars), `typed-gdscript`,
`test-runner` (GUT/GdUnit4 headless), `signal-wiring`, `autoload-config`, `export-check`, `feature-slice`,
a `PreToolUse` hook that blocks `.uid`/`.godot/` edits, a `Stop` hook that refuses "done" without a verify run,
three `CLAUDE.md` templates (2D, 3D, C#), the 4.4→4.7 delta tables, and a worked example project.

## Compatibility

- Godot **4.7.x** (tested 4.7.2). Rules include 4.3+ deprecations (`TileMap` → `TileMapLayer`) and 4.4–4.7 changes.
- Claude Code ≥ 2.1 (skills + plugin hooks).
- Re-verified within 30 days of each new Godot minor release.

## License

MIT. Not affiliated with or endorsed by the Godot Foundation or Anthropic; "Godot" and "Claude" are used descriptively.
