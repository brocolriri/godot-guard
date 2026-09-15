## Global event bus. Registered as autoload "Events".
extends Node

signal player_hit(damage: int)
signal enemy_died(enemy: Node2D)
signal score_changed(new_score: int)
