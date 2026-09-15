class_name Player
extends CharacterBody2D

signal hit(damage: int)

@export var speed: float = 120.0
@onready var sprite: Sprite2D = $Sprite2D
@onready var hurtbox: Area2D = $Hurtbox

func _ready() -> void:
	hurtbox.area_entered.connect(_on_hurtbox_area_entered)

func _physics_process(_delta: float) -> void:
	var dir := Input.get_vector("ui_left", "ui_right", "ui_up", "ui_down")
	velocity = dir * speed
	move_and_slide()

func _on_hurtbox_area_entered(area: Area2D) -> void:
	if area.is_in_group("enemy_attack"):
		hit.emit(1)
		Events.player_hit.emit(1)

func get_speed() -> float:
	return speed
