extends TileMap

@export var short_duration_min: float = 0.03
@export var short_duration_max: float = 0.08
@export var long_duration_min: float = 0.3
@export var long_duration_max: float = 0.8
@export var pause_between_patterns_min: float = 12.5
@export var pause_between_patterns_max: float = 10.0

const DIM_ALPHA := 0.1
const BRIGHT_ALPHA := 0.9

var patterns := [
	["short", "short", "long"],
	["long", "short"],
	["short", "long", "short"],
	["short", "short", "short", "long"],
]

var current_pattern: Array
var current_index: int

func _ready() -> void:
	randomize()
	modulate.a = DIM_ALPHA
	_run_next_pattern()

func _run_next_pattern() -> void:
	current_pattern = patterns[randi() % patterns.size()]
	current_index = 0
	_play_beat()

func _play_beat() -> void:
	if current_index >= current_pattern.size():
		modulate.a = DIM_ALPHA
		var pause := randf_range(pause_between_patterns_min, pause_between_patterns_max)
		get_tree().create_timer(pause).timeout.connect(_run_next_pattern)
		return

	var beat: String = current_pattern[current_index]
	var duration: float

	if beat == "short":
		duration = randf_range(short_duration_min, short_duration_max)
	else:
		duration = randf_range(long_duration_min, long_duration_max)

	modulate.a = BRIGHT_ALPHA
	get_tree().create_timer(duration).timeout.connect(_end_beat)

func _end_beat() -> void:
	modulate.a = DIM_ALPHA
	var gap := randf_range(0.02, 0.06)
	get_tree().create_timer(gap).timeout.connect(_advance_beat)

func _advance_beat() -> void:
	current_index += 1
	_play_beat()
