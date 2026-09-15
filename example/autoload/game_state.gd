## Global game state. Registered as autoload "GameState".
extends Node

var score: int = 0
var lives: int = 3
var stats: Dictionary[String, int] = {"kills": 0, "hits": 0}

func _ready() -> void:
	Events.enemy_died.connect(_on_enemy_died)
	Events.player_hit.connect(_on_player_hit)

func _on_enemy_died(_enemy: Node2D) -> void:
	score += 10
	stats["kills"] += 1
	Events.score_changed.emit(score)

func _on_player_hit(damage: int) -> void:
	lives -= damage
	stats["hits"] += 1
