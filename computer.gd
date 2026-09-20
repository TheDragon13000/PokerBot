extends Area2D

# Attach this directly to the "computer" Area2D node (not the CollisionShape2D child).
# Assumes a Label child (e.g. "Press E") already exists in the scene, like yours does.
#
# Pressing E opens the PokerBot Lab (Bet2Bot running in a WebView) — see
# pokerbot_lab/pokerbot_lab.gd, registered as the `PokerBotLab` autoload. The original
# Python code editor (code_editor_ui.tscn) is still in the project and can be opened
# instead by setting `use_code_editor` on this node.

@export var use_code_editor: bool = false
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
		if _is_ui_open():
			close_ui()
		else:
			open_ui()

func _is_ui_open() -> bool:
	if use_code_editor:
		return is_instance_valid(ui_instance)
	return PokerBotLab.is_open()

func open_ui() -> void:
	if use_code_editor:
		ui_instance = code_editor_scene.instantiate()
		get_tree().root.add_child(ui_instance)
	else:
		PokerBotLab.open()

func close_ui() -> void:
	if use_code_editor:
		if is_instance_valid(ui_instance):
			ui_instance.queue_free()
			get_tree().paused = false
		ui_instance = null
	else:
		PokerBotLab.close()
