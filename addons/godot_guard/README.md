# godot-guard (editor plugin)

Flags Godot 3 idioms and invalid 4.x API use in `.gd`, `.tscn` and `.tres`, from inside the editor.

## Enable

1. Copy this `godot_guard` folder into your project's `addons/` directory.
2. *Project > Project Settings > Plugins* — turn **godot-guard** on.
3. Open the **godot-guard** tab in the bottom panel and press **Scan project**.

Each row is one finding: where it is, the exact text found, and what to write instead.
Double-click a row to jump to it. *Errors only* hides warnings (deprecations that still run).

## What it reads

`reference/godot3_isms.json` — 92 rules, each with the official documentation URL for the change.
Matches inside comments, strings and triple-quoted blocks are ignored.

It reports; it never edits your files. Pure GDScript: no Python, no external tool, no network.

## Verified on

Godot 4.7.2 and 4.4.1. The repository's test suite asserts this scanner reports exactly the same
findings as the command-line scanner it was ported from.

Source and command-line version: https://github.com/brocolriri/godot-guard — MIT.
