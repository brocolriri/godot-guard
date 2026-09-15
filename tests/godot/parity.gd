extends SceneTree
## Prints what addons/godot_guard/api_guard.gd finds, as JSON, so the Python
## test suite can assert the in-editor scanner agrees with scripts/api_guard.py.
##
##   godot --headless --path <project> -s tests/godot/parity.gd -- <file>...

func _init() -> void:
	var guard = load("res://addons/godot_guard/api_guard.gd").new()
	if guard.rules.is_empty():
		push_error("godot-guard: no rules loaded: " + guard.load_error)
		quit(2)
		return
	var out := {"rules": guard.rules.size(), "findings": []}
	for path in OS.get_cmdline_user_args():
		var text := FileAccess.get_file_as_string(path)
		if text.is_empty():
			push_error("godot-guard: cannot read " + path)
			quit(2)
			return
		out["findings"].append_array(guard.scan_text(text, path))
	print("###JSON###")
	print(JSON.stringify(out))
	quit(0)
