# godot-guard — Godot 4 guardrails for AI coding agents

**This repo is free:** the Godot-3-ism linter, the scene map (real node paths) and the version pin —
as an **editor plugin you can enable in Godot itself**, as three Claude Code skills, and as an
`AGENTS.md` / Cursor rule for every other agent.

**The paid editions add the layer that *stops* the bad edit** instead of advising against it:
hooks that block `.uid` / `.godot/` writes, and a verify run (import → parse → every scene → N frames)
that refuses to let the agent say "done" until the project actually boots.

| | For | Price |
|---|---|---|
| **[Godot 4 Guardrails Pro](https://brocolriri.gumroad.com/l/godot-guard-pro)** | Claude Code — 12 skills, 3 hooks, 3 `CLAUDE.md` templates | **$24** |
| **[Godot 4 Guardrails Crosstool](https://brocolriri.gumroad.com/l/godot-guard-crosstool)** | Cursor · Codex CLI · GitHub Copilot — 6 topics × 3 formats, 3 Cursor hooks | **$19** |
| **[Both editions](https://brocolriri.gumroad.com/l/godot-guard-both)** | bundle (separately $43) | **$29** |

14-day refund, no questions. Details below, or scroll to [Pro version](#pro-version).

---

> **Not using Claude Code?** The same rules for **Cursor, Codex CLI and GitHub Copilot** live in
> [`crosstool/`](crosstool/) — one `AGENTS.md` and the API scanner, no plugin needed.

**Verified on Godot 4.7.2 (2026-09-15).** Three skills + one hook that stop the most common ways
Claude Code breaks a Godot 4 project:

| Problem | Skill | What it does |
|---|---|---|
| Godot 3 syntax leaks in (`yield`, `.instance()`, `connect("sig", self, "m")`, `KinematicBody2D`, `export var`, invented APIs like `Signal.any`) | `/godot-guard:godot4-api-guard` | Deterministic scanner over `.gd`/`.tscn`/`.cs` with fix + official source per rule. Runs automatically after every edit (PostToolUse hook). |
| Guessed node paths → `Node not found`, null `@onready` | `/godot-guard:scene-map` | Reads every `.tscn` and writes `.claude/scene-map.md`: node tree, types, scripts, `%unique` names, `[connection]` signals, groups, autoloads, and the exact `$Path`/`%Name` to use. |
| Wrong Godot version in Claude's head | `/godot-guard:version-pin` | Pins `project.godot` `config/features` + `godot --version` into `CLAUDE.md` with working rules, idempotently. |

Pure Python 3.8+ standard library. No MCP server, no editor plugin, no network. Works on Windows, macOS, Linux and WSL.

## Install

```text
/plugin marketplace add brocolriri/godot-guard
/plugin install godot-guard@godot-guard
```

or, without a marketplace: `git clone https://github.com/brocolriri/godot-guard && claude --plugin-dir ./godot-guard`

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

## In the Godot editor (no AI tool needed)

Copy `addons/godot_guard/` into your project and turn **godot-guard** on in
*Project > Project Settings > Plugins*. A **godot-guard** tab appears in the bottom panel:
press *Scan project* and every Godot 3 idiom in the project is listed with the line, what was
found and what to write instead. Double-click a row to jump to it.

The editor scanner is pure GDScript — no Python, no network, nothing to install — and the test
suite asserts it reports exactly what the command-line scanner reports (`tests/static/test_addon_parity.py`).

## Scripts (usable without Claude)

| Script | Purpose |
|---|---|
| `scripts/api_guard.py <path...> [--json] [--hook] [--list-rules]` | Godot-3-ism / 4.x-drift linter |
| `scripts/scene_map.py <project|file.tscn> [--out .claude/scene-map.md] [--json]` | Scene tree → markdown map |
| `scripts/version_pin.py <project> [--godot BIN] [--write CLAUDE.md]` | Version block into CLAUDE.md |

Rules live in `reference/godot3_isms.json` and `reference/deltas.json` (each row cites the official Godot doc).

## Cursor / Codex CLI / GitHub Copilot

[`crosstool/`](crosstool/) carries the same API guard in the format those tools read: a single
`AGENTS.md` (read by Codex CLI, Cursor, Copilot, Jules, Aider, Zed and ~20 others) plus
`api_guard.py` and `version_pin.py`, which need no tool at all.

```bash
cp crosstool/AGENTS.md /path/to/your/game/AGENTS.md           # Codex CLI and ~25 other agents
cp rules/godot-api-guard.mdc /path/to/your/game/.cursor/rules/  # native Cursor rule
mkdir -p /path/to/your/game/.godot-guard && cp -r crosstool/scripts crosstool/reference /path/to/your/game/.godot-guard/
```

The paid edition for those tools adds Cursor `.mdc` rules, Copilot `.instructions.md`, **three
Cursor hooks that block bad edits instead of advising against them**, the verify loop, scene map,
tscn check and uid keeper:
**[Godot 4 Guardrails for Cursor, Codex & Copilot](https://brocolriri.gumroad.com/l/godot-guard-crosstool)** — $19.

## Pro version

**[Godot 4 Guardrails Pro](https://brocolriri.gumroad.com/l/godot-guard-pro)** — $24 — adds the proof layer:
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

MIT. Not affiliated with or endorsed by the Godot Foundation, Anthropic, Anysphere (Cursor),
OpenAI, GitHub or Microsoft; those names are used descriptively.
