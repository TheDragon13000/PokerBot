extends Area2D

@onready var label: Label = $Label
@onready var code_page: Node = get_node("/root/Main/code_page")  # adjust path

func _ready() -> void:
	label.visible = false
	body_entered.connect(_on_body_entered)
	body_exited.connect(_on_body_exited)

func _on_body_entered(body: Node2D) -> void:
	if body.is_in_group("player"):
		label.visible = true
		label.text = "Press E to interact"
		code_page.trigger()  # code_page needs a method called trigger()

func _on_body_exited(body: Node2D) -> void:
	if body.is_in_group("player"):
		label.visible = false
