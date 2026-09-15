tool
extends KinematicBody2D

export var speed = 100
onready var sprite = $Sprite
var pool = PoolStringArray()
var cb = funcref(self, "hit")

func _ready():
	# yield(get_tree(), "idle_frame") is commented out
	print("scene.instance() inside string")
	var s = "connect(\"pressed\", self, \"x\")"
	yield(get_tree().create_timer(1.0), "timeout")
	var e = load("res://enemy.tscn").instance()
	$Button.connect("pressed", self, "_on_pressed")
	var r = deg2rad(90) + rand_range(1, 2)
	material.set_shader_param("tint", Color.red)
	var t = OS.get_ticks_msec()
	if pool.empty():
		pass
	await Signal.any([a, b])
	"""
	yield(x, "y") in a docstring
	"""
	var node = get_node("Spatial")

func _physics_process(delta):
	move_and_slide(velocity)

func hit(body):
	if body is Sprite:
		pass
