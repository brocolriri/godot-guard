@tool
extends EditorPlugin
## Adds a "godot-guard" tab to the editor's bottom panel.

const DOCK := preload("res://addons/godot_guard/guard_dock.gd")

var _dock: Control


func _enter_tree() -> void:
	_dock = DOCK.new()
	_dock.name = "godot-guard"
	add_control_to_bottom_panel(_dock, "godot-guard")


func _exit_tree() -> void:
	if _dock != null:
		remove_control_from_bottom_panel(_dock)
		_dock.queue_free()
		_dock = null
