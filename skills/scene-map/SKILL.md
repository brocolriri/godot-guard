---
name: scene-map
description: Generate .claude/scene-map.md from every .tscn in a Godot 4 project — node tree with types, attached scripts, %unique names, [connection] signals, groups, autoloads, and the exact $Path/%Name expressions to use. Use before writing code that references nodes (get_node, $, %, @onready), after any scene edit, and whenever a "Node not found" / null @onready error appears.
argument-hint: [project_dir | file.tscn]
allowed-tools: Bash(python3 *) Read
---

# Scene map

Claude cannot see the Godot editor. Guessed node paths (`$Player/Sprite`) are the #1 source of
null references. This skill reads the `.tscn` files and writes the real tree to
`.claude/scene-map.md`, then you use those paths verbatim.

## Run it

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/scene_map.py" $ARGUMENTS --out .claude/scene-map.md
```

- No arguments: the current project directory. A single `.tscn` path maps just that scene.
- `--json` gives the same data as JSON.
- Exit `1` means the map has a `### Problems` section (unresolved instanced scene, missing script,
  format != 3). Read it: those are real breakages in the scene files.

## Then

1. `Read` `.claude/scene-map.md` (or the part for the scene you are editing).
2. In scripts, copy the **Use this** column exactly: `%Player`, `$Enemies/Enemy`, `$HUD/ScoreLabel`.
   - `%Unique` names work only from scripts inside the scene that owns them; the map lists which.
   - Nodes marked `[inside x.tscn]` belong to an instanced scene: access them through that scene's
     own script/API when possible instead of reaching through the tree.
3. Signals: prefer the `[connection]` table for what is already wired in the editor; connect the rest
   in `_ready()` with `node.signal_name.connect(callable)`.
4. Autoloads listed at the top are global singletons: call them by name (`Events.player_hit.emit(1)`).
5. Regenerate the map after any `.tscn` change. Stale map = stale paths.

## Rules

- Never invent a node name or type that is not in the map. If a node you need does not exist,
  say so and add it to the scene (with the scene-surgeon rules if you have godot-guard-pro)
  rather than assuming.
- Do not rename nodes in `.tscn` files without updating every `$Path` and `[connection]` line;
  run the map again to confirm.
