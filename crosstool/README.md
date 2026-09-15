# godot-guard for Cursor, Codex CLI and GitHub Copilot

The same Godot 4 guardrails as the Claude Code plugin above, in the format the other AI coding
tools read. This free folder is the **API guard** half: the 92 Godot-3-idiom rules and the
4.4 → 4.7 deltas, written into an `AGENTS.md` your agent will actually load, plus the two
scripts that check a file without any tool installed.

## Install

```bash
cp crosstool/AGENTS.md      /path/to/your/game/AGENTS.md
mkdir -p /path/to/your/game/.godot-guard
cp -r crosstool/scripts crosstool/reference /path/to/your/game/.godot-guard/
```

`AGENTS.md` at the project root is read by Codex CLI, and by Cursor, Copilot, Jules, Aider, Zed
and ~20 other agents. Nothing else to configure.

## Use

```bash
python3 .godot-guard/scripts/api_guard.py .          # 0 = clean, 1 = findings, 2 = usage error
python3 .godot-guard/scripts/api_guard.py --list-rules
python3 .godot-guard/scripts/version_pin.py . --write AGENTS.md
```

```text
$ python3 .godot-guard/scripts/api_guard.py .
player.gd:13:2: [error] yield: yield(get_tree().create_timer(1.0), "timeout")
    fix: -> await get_tree().create_timer(1.0).timeout
    see: https://docs.godotengine.org/en/stable/tutorials/migrating/upgrading_to_godot_4.html
2 finding(s) in 1 file(s)
```

Python 3.9+ standard library only. No MCP server, no editor plugin, no network.

## What the paid edition adds

**[Godot 4 Guardrails for Cursor, Codex &amp; Copilot](https://brocolriri.gumroad.com/l/godot-guard-crosstool)**:

- Cursor `.cursor/rules/godot-*.mdc` (6 topics, attached by file type) and Copilot
  `.github/instructions/*.instructions.md` — not just the single `AGENTS.md`.
- **Three Cursor hooks that enforce instead of advise**: `preToolUse` denies edits to `.uid`
  sidecars and `.godot/` and refuses a bare `mv` of a Godot resource; `postToolUse` feeds the
  scanner's findings back into the conversation; `stop` demands a verify run when sources
  changed since the last passing one.
- `verify.py` — import → parse (with autoloads loaded) → instantiate every scene → run N frames
  → PASS / FAIL. Godot's own CLI exits `0` on `SCRIPT ERROR`; this doesn't.
- `scene_map.py`, `tscn_check.py`, `uid_keeper.py`, the generator (`build_rules.py` + editable
  topic sources), the installer, and an example project that passes.

Using Claude Code? That edition is
**[Godot 4 Guardrails Pro](https://brocolriri.gumroad.com/l/godot-guard-pro)**.

## License

MIT, same as the rest of this repository. Not affiliated with or endorsed by the Godot
Foundation, Anysphere (Cursor), OpenAI, GitHub or Microsoft.
