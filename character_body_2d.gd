class_name Player
extends CharacterBody2D

@export var speed: float = 100.0
@export var acceleration: float = 20.0
@export var friction: float = 25.0
@export var idle_delay: float = 1.5

@onready var animated_sprite: AnimatedSprite2D = $AnimatedSprite2D

var last_direction: String = "down"
var idle_timer: float = 0.0
var is_idling: bool = false

func _physics_process(delta: float) -> void:
	var input_dir := Vector2.ZERO
	input_dir.x = Input.get_axis("MoveL", "MoveR")
	input_dir.y = Input.get_axis("MoveU", "MoveD")
	input_dir = input_dir.normalized()

	if input_dir != Vector2.ZERO:
		velocity = velocity.lerp(input_dir * speed, acceleration * delta)
		update_animation(input_dir)
		idle_timer = 0.0
		is_idling = false
	else:
		velocity = velocity.lerp(Vector2.ZERO, friction * delta)
		if not is_idling:
			animated_sprite.stop()
			animated_sprite.frame = 5
			idle_timer += delta
			if idle_timer >= idle_delay:
				is_idling = true
				animated_sprite.play("idle")

	move_and_slide()

func update_animation(dir: Vector2) -> void:
	if abs(dir.x) > abs(dir.y):
		last_direction = "right" if dir.x > 0 else "left"
	else:
		last_direction = "down" if dir.y > 0 else "up"
	animated_sprite.play(last_direction)
