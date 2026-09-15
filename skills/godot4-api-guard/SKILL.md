---
name: godot4-api-guard
description: Lint GDScript/.tscn for Godot 3 idioms and Godot 4.x API drift (yield, .instance(), string connect, KinematicBody2D, export var, TileMap node, invented APIs like Signal.any). Use after writing or editing any .gd/.cs/.tscn file in a Godot 4 project, before running the game, and whenever the user reports "method not found" / parse errors that look like Godot 3 syntax.
argument-hint: [path ...]
allowed-tools: Bash(python3 *)
---

# Godot 4 API guard

Godot 4 projects break when Godot 3 syntax leaks in. This skill runs a deterministic scanner
instead of relying on memory of the API.

## Run it

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/api_guard.py" $ARGUMENTS
```

- No arguments: scans the current project (all `.gd`, `.tscn`, `.tres`; add `--cs` for C#).
- `--json` for machine output, `--severity error` to hide warnings, `--list-rules` to see every rule and its source URL.
- Exit code `1` = findings, `0` = clean, `2` = usage error.

## What to do with findings

1. Fix every `[error]` finding using the `fix:` line. Do not "explain around" them: they are compile/runtime failures in Godot 4.
2. `[warn]` findings (e.g. `TileMap` node type, deprecated in 4.3 → `TileMapLayer`) are migration debt; fix them when you touch that file, otherwise report them.
3. Re-run until it prints `0 finding(s)`, then continue with the task (and run the verify loop if you have `godot-guard-pro`).

## Rules the scanner enforces (Godot 4.7 target)

| Godot 3 / invalid | Godot 4 |
|---|---|
| `yield(obj, "sig")` | `await obj.sig` |
| `scene.instance()` | `scene.instantiate()` |
| `obj.connect("sig", self, "m")` | `obj.sig.connect(m)` |
| `KinematicBody2D` + `move_and_slide(vel)` | `CharacterBody2D`, set `velocity`, `move_and_slide()` |
| `export var`, `onready var`, `tool` | `@export var`, `@onready var`, `@tool` |
| `deg2rad`, `rand_range`, `set_shader_param` | `deg_to_rad`, `randf_range`, `set_shader_parameter` |
| `PoolStringArray` | `PackedStringArray` |
| `Spatial`, `Sprite`, `Area`, `Position2D` | `Node3D`, `Sprite2D`, `Area3D`, `Marker2D` |
| `OS.get_ticks_msec()` | `Time.get_ticks_msec()` |
| `arr.empty()` | `arr.is_empty()` |
| `Signal.any([...])` | does not exist; use `await` per signal or a helper |
| `TileMap` node (4.3+) | `TileMapLayer` |

The full rule set with source links lives in `${CLAUDE_PLUGIN_ROOT}/reference/godot3_isms.json`
(and `deltas.json` for 4.4→4.7 changes) when present; otherwise the scanner uses its built-in rules.

## Hook (automatic)

This plugin registers a `PostToolUse` hook that runs the guard on every file you write or edit.
If it blocks with a message, fix the listed lines first. To disable the hook, remove the entry in
`hooks/hooks.json` or run with `--severity error` only.
