class_name Enemy
extends CharacterBody2D

enum State { IDLE, CHASE, DEAD }

@export var speed: float = 60.0
@export var hp: int = 2
var state: State = State.IDLE
var target: Node2D

func _ready() -> void:
	add_to_group("enemies")
	await get_tree().create_timer(0.1).timeout
	target = get_tree().get_first_node_in_group("player")
	if target:
		state = State.CHASE

func _physics_process(_delta: float) -> void:
	match state:
		State.CHASE:
			if is_instance_valid(target):
				velocity = global_position.direction_to(target.global_position) * speed
				move_and_slide()
		_:
			velocity = Vector2.ZERO

func take_damage(amount: int) -> void:
	hp -= amount
	if hp <= 0 and state != State.DEAD:
		state = State.DEAD
		Events.enemy_died.emit(self)
		queue_free()
