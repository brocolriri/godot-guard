extends Node2D

@onready var player: Player = %Player
@onready var enemies: Node2D = $Enemies
@onready var hud: CanvasLayer = $HUD

func _ready() -> void:
	player.add_to_group("player")
	Events.score_changed.connect(_on_score_changed)

func _on_score_changed(new_score: int) -> void:
	hud.set_score(new_score)

func spawn_enemy(at: Vector2) -> Enemy:
	var scene: PackedScene = load("res://scenes/enemy.tscn")
	var e: Enemy = scene.instantiate()
	e.global_position = at
	enemies.add_child(e)
	return e

func _on_player_hit(damage: int) -> void:
	print("player hit for ", damage)
