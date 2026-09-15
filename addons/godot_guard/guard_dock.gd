@tool
extends VBoxContainer
## Bottom-panel view for godot-guard: scan the project, list every finding,
## double-click a row to jump to the line.

const GUARD := preload("res://addons/godot_guard/api_guard.gd")

var _tree: Tree
var _summary: Label
var _errors_only: CheckBox
var _scan_button: Button
var _findings: Array = []


func _ready() -> void:
	custom_minimum_size = Vector2(0, 180)
	_build_ui()
	_render([])


func _build_ui() -> void:
	var bar := HBoxContainer.new()
	add_child(bar)

	_scan_button = Button.new()
	_scan_button.text = "Scan project"
	_scan_button.tooltip_text = "Scan every .gd, .tscn and .tres file outside addons/"
	_scan_button.pressed.connect(scan)
	bar.add_child(_scan_button)

	_errors_only = CheckBox.new()
	_errors_only.text = "Errors only"
	_errors_only.tooltip_text = "Hide warnings (migration debt that still runs)"
	_errors_only.toggled.connect(func(_on: bool) -> void: _render(_findings))
	bar.add_child(_errors_only)

	var spacer := Control.new()
	spacer.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	bar.add_child(spacer)

	_summary = Label.new()
	bar.add_child(_summary)

	_tree = Tree.new()
	_tree.size_flags_vertical = Control.SIZE_EXPAND_FILL
	_tree.columns = 4
	_tree.column_titles_visible = true
	_tree.hide_root = true
	_tree.set_column_title(0, "Where")
	_tree.set_column_title(1, "Rule")
	_tree.set_column_title(2, "Found")
	_tree.set_column_title(3, "Use instead")
	_tree.set_column_expand_ratio(0, 3)
	_tree.set_column_expand_ratio(1, 2)
	_tree.set_column_expand_ratio(2, 3)
	_tree.set_column_expand_ratio(3, 4)
	_tree.item_activated.connect(_on_item_activated)
	add_child(_tree)


func scan() -> void:
	_scan_button.disabled = true
	var guard := GUARD.new()
	if guard.rules.is_empty():
		_summary.text = guard.load_error
		_scan_button.disabled = false
		return
	_findings = guard.scan_project("res://")
	_render(_findings)
	_scan_button.disabled = false


func _render(findings: Array) -> void:
	_tree.clear()
	var root := _tree.create_item()
	var errors := 0
	var warns := 0
	for f in findings:
		if f["severity"] == "error":
			errors += 1
		else:
			warns += 1
	var shown := 0
	for f in findings:
		if _errors_only.button_pressed and f["severity"] != "error":
			continue
		var item := _tree.create_item(root)
		item.set_text(0, "%s:%d" % [str(f["file"]).replace("res://", ""), f["line"]])
		item.set_text(1, str(f["rule"]))
		item.set_text(2, str(f["match"]))
		item.set_text(3, str(f["fix"]).split("\n")[0])
		item.set_tooltip_text(3, _tooltip(f))
		var color := _severity_color(str(f["severity"]))
		if color.a > 0.0:
			item.set_custom_color(1, color)
		item.set_metadata(0, f)
		shown += 1
	if findings.is_empty():
		_summary.text = "No findings. Press Scan to check the project."
	else:
		_summary.text = "%d error(s), %d warning(s) — %d shown" % [errors, warns, shown]


func _tooltip(f: Dictionary) -> String:
	var parts := ["%s  ->  %s" % [f["old"], f["fix"]]]
	if not str(f["note"]).is_empty():
		parts.append(str(f["note"]))
	if not str(f["url"]).is_empty():
		parts.append(str(f["url"]))
	return "\n\n".join(parts)


func _severity_color(severity: String) -> Color:
	var theme := EditorInterface.get_editor_theme()
	if theme == null:
		return Color(0, 0, 0, 0)
	var key := "error_color" if severity == "error" else "warning_color"
	if theme.has_color(key, "Editor"):
		return theme.get_color(key, "Editor")
	return Color(0, 0, 0, 0)


func _on_item_activated() -> void:
	var item := _tree.get_selected()
	if item == null:
		return
	var f: Variant = item.get_metadata(0)
	if not (f is Dictionary):
		return
	var path := str(f["file"])
	var line := int(f["line"])
	if path.get_extension().to_lower() == "gd":
		# A file that still uses Godot 3 syntax often fails to parse, so load()
		# returns null; reveal it in the FileSystem dock instead of doing nothing.
		var script: Variant = ResourceLoader.load(path, "Script", ResourceLoader.CACHE_MODE_REUSE)
		if script is Script:
			EditorInterface.edit_script(script, line - 1, int(f["col"]) - 1, true)
		else:
			EditorInterface.select_file(path)
	else:
		EditorInterface.open_scene_from_path(path)
