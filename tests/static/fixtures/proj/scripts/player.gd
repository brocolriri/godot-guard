class_name Player
extends CharacterBody2D

signal died
@export var speed: float = 120.0
@export_range(0, 10) var lives: int = 3
@onready var hurtbox: Area2D = %Hurtbox

func _ready() -> void:
	pass

static func make() -> Player:
	return Player.new()
