class_name Clean
extends CharacterBody2D

@export var speed: float = 100.0
@onready var sprite: Sprite2D = $Sprite2D

signal hit(amount: int)

func _ready() -> void:
	# yield(x, "y") only in a comment
	print("old code used .instance() and connect(\"a\", b, \"c\")")
	var s := '''
	yield(x, "y") in a triple-quoted string
	'''
	sprite.frame_changed.connect(_on_frame)
	await get_tree().process_frame

func _physics_process(_delta: float) -> void:
	velocity = Vector2.RIGHT * speed
	move_and_slide()

func _on_frame() -> void:
	pass
