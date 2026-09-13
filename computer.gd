extends Area2D

# Attach this directly to the "computer" Area2D node (not the CollisionShape2D child).
# Assumes a Label child (e.g. "Press E") already exists in the scene, like yours does.

@export var code_editor_scene: PackedScene = preload("res://code_editor_ui.tscn")

@onready var label: Label = $Label

var player_in_range: bool = false
var ui_instance: CanvasLayer = null

func _ready() -> void:
	label.visible = false

func _on_body_entered(body: Node) -> void:
	print("Something entered: ", body.name, " groups: ", body.get_groups())
	if body.is_in_group("player_group"):          # <-- was "player"
		player_in_range = true
		label.visible = true

func _on_body_exited(body: Node) -> void:
	if body.is_in_group("player_group"):           # <-- was "player"
		player_in_range = false
		label.visible = false
		close_ui()

func _unhandled_input(event: InputEvent) -> void:
	if not player_in_range:
		return
	if event is InputEventKey and event.pressed and not event.echo and event.keycode == KEY_E:
		if ui_instance == null:
			open_ui()
		else:
			close_ui()

func open_ui() -> void:
	ui_instance = code_editor_scene.instantiate()
	get_tree().root.add_child(ui_instance)

func close_ui() -> void:
	if ui_instance:
		ui_instance.queue_free()
		ui_instance = null
		get_tree().paused = false          # <-- new line added
