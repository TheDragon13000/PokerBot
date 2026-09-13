extends CanvasLayer

# ============================================================
# Custom-drawn views for the "Table" and "Stack graph" tabs.
# No image assets are used -- cards/chips/lines are drawn with
# code (Control._draw()), so this looks the same on any machine.
# ============================================================

class TableView extends Control:
	var hole_your: Array = []
	var hole_opp: Array = []
	var opp_revealed: bool = false
	var community: Array = []
	var pot: int = 0
	var stacks: Dictionary = {}
	var your_name: String = "Your Bot"
	var opp_name: String = "Opponent"

	const RANK_CHARS := "23456789TJQKA"
	const SUIT_SYMBOLS := {"s": "\u2660", "h": "\u2665", "d": "\u2666", "c": "\u2663"}
	const RED_SUITS := ["h", "d"]

	func reset_all() -> void:
		stacks = {}
		reset_hand()

	func reset_hand() -> void:
		hole_your = []
		hole_opp = []
		opp_revealed = false
		community = []
		pot = 0
		queue_redraw()

	func set_hole(player_name: String, cards: Array) -> void:
		if player_name == your_name:
			hole_your = cards
		else:
			hole_opp = cards
		queue_redraw()

	func reveal_opponent() -> void:
		opp_revealed = true
		queue_redraw()

	func set_community(cards: Array) -> void:
		community = cards
		queue_redraw()

	func set_pot(p: int) -> void:
		pot = p
		queue_redraw()

	func set_stacks(s: Dictionary) -> void:
		stacks = s
		queue_redraw()

	func _card_label(card) -> String:
		var rank_val: int = int(card[0])
		var suit: String = String(card[1])
		var idx: int = clampi(rank_val - 2, 0, RANK_CHARS.length() - 1)
		return RANK_CHARS[idx] + String(SUIT_SYMBOLS.get(suit, "?"))

	func _card_color(card) -> Color:
		var suit: String = String(card[1])
		if RED_SUITS.has(suit):
			return Color(0.75, 0.16, 0.16)
		return Color(0.1, 0.1, 0.1)

	func _draw_card_at(pos: Vector2, card, face_up: bool) -> void:
		var w := 56.0
		var h := 78.0
		var rect := Rect2(pos, Vector2(w, h))
		var font := ThemeDB.fallback_font
		if face_up and card != null:
			draw_rect(rect, Color(0.97, 0.97, 0.96), true)
			draw_rect(rect, Color(0.25, 0.25, 0.25), false, 2.0)
			if font:
				draw_string(font, pos + Vector2(8, 32), _card_label(card),
					HORIZONTAL_ALIGNMENT_LEFT, -1, 20, _card_color(card))
		else:
			draw_rect(rect, Color(0.16, 0.18, 0.3), true)
			draw_rect(rect, Color(0.32, 0.35, 0.48), false, 2.0)

	func _draw() -> void:
		var mid_x := size.x / 2.0
		var font := ThemeDB.fallback_font

		var opp_y := 10.0
		if hole_opp.size() >= 2:
			_draw_card_at(Vector2(mid_x - 62, opp_y), hole_opp[0], opp_revealed)
			_draw_card_at(Vector2(mid_x + 6, opp_y), hole_opp[1], opp_revealed)
		if font:
			draw_string(font, Vector2(mid_x + 74, opp_y + 45), opp_name,
				HORIZONTAL_ALIGNMENT_LEFT, -1, 13, Color(0.8, 0.8, 0.8))

		var comm_y := 104.0
		var n := community.size()
		var comm_start_x := mid_x - (n * 60.0) / 2.0
		for i in range(n):
			_draw_card_at(Vector2(comm_start_x + i * 60.0, comm_y), community[i], true)

		var pot_y := comm_y + 96.0
		draw_circle(Vector2(mid_x, pot_y), 10, Color(0.94, 0.63, 0.15))
		if font:
			draw_string(font, Vector2(mid_x + 18, pot_y + 5), "Pot: %d" % pot,
				HORIZONTAL_ALIGNMENT_LEFT, -1, 14, Color(0.85, 0.85, 0.85))

		var your_y := pot_y + 36.0
		if hole_your.size() >= 2:
			_draw_card_at(Vector2(mid_x - 62, your_y), hole_your[0], true)
			_draw_card_at(Vector2(mid_x + 6, your_y), hole_your[1], true)
		if font:
			draw_string(font, Vector2(mid_x + 74, your_y + 45), your_name,
				HORIZONTAL_ALIGNMENT_LEFT, -1, 13, Color(0.8, 0.8, 0.8))

		var stacks_y := your_y + 96.0
		var your_stack := int(stacks.get(your_name, 0))
		var opp_stack := int(stacks.get(opp_name, 0))
		var your_color := Color(0.45, 0.8, 0.45) if your_stack >= opp_stack else Color(0.85, 0.4, 0.4)
		var opp_color := Color(0.45, 0.8, 0.45) if opp_stack >= your_stack else Color(0.85, 0.4, 0.4)
		if font:
			draw_string(font, Vector2(mid_x - 150, stacks_y), "%s: %d" % [your_name, your_stack],
				HORIZONTAL_ALIGNMENT_LEFT, -1, 14, your_color)
			draw_string(font, Vector2(mid_x + 20, stacks_y), "%s: %d" % [opp_name, opp_stack],
				HORIZONTAL_ALIGNMENT_LEFT, -1, 14, opp_color)


class GraphView extends Control:
	var points: Array = []

	func set_data(data: Array) -> void:
		points = data
		queue_redraw()

	func _draw() -> void:
		var font := ThemeDB.fallback_font
		draw_rect(Rect2(Vector2.ZERO, size), Color(0.1, 0.1, 0.12), true)

		if points.size() < 2:
			if font:
				draw_string(font, Vector2(20, size.y / 2.0), "Play a match to see the graph",
					HORIZONTAL_ALIGNMENT_LEFT, -1, 14, Color(0.55, 0.55, 0.55))
			return

		var max_val := 1.0
		for p in points:
			max_val = max(max_val, max(float(p.get("you", 0)), float(p.get("opp", 0))))

		var pad := 30.0
		var w := size.x - pad * 2.0
		var h := size.y - pad * 2.0
		var step := w / float(points.size() - 1)

		var you_pts := PackedVector2Array()
		var opp_pts := PackedVector2Array()
		for i in range(points.size()):
			var p = points[i]
			var x := pad + i * step
			you_pts.append(Vector2(x, pad + h - (float(p.get("you", 0)) / max_val) * h))
			opp_pts.append(Vector2(x, pad + h - (float(p.get("opp", 0)) / max_val) * h))

		draw_polyline(you_pts, Color(0.35, 0.8, 0.45), 2.0)
		draw_polyline(opp_pts, Color(0.85, 0.4, 0.4), 2.0)
		if font:
			draw_string(font, Vector2(pad, pad - 12), "Your stack",
				HORIZONTAL_ALIGNMENT_LEFT, -1, 12, Color(0.35, 0.8, 0.45))
			draw_string(font, Vector2(pad + 110, pad - 12), "Opponent",
				HORIZONTAL_ALIGNMENT_LEFT, -1, 12, Color(0.85, 0.4, 0.4))


# ============================================================
# Main controller
# ============================================================

const STARTER_BOT_CODE := """def my_bot(hole, community, pot, to_call, min_raise, my_stack, stage, num_opponents):
    # See the reference bar below for what each parameter means and
    # which (action, amount) tuples you can return.
    if to_call == 0:
        return (\"check\", 0)
    if to_call <= my_stack * 0.1:
        return (\"call\", to_call)
    return (\"fold\", 0)
"""

var code_input: TextEdit
var run_button: Button
var close_button: Button
var status_label: Label
var log_view: RichTextLabel
var stats_label: RichTextLabel
var tab_container: TabContainer
var table_view: TableView
var graph_view: GraphView

var pending_events: Array = []
var replay_index: int = 0
var events_per_tick: int = 1
var replay_timer: Timer

var stack_history: Array = []
var action_counts: Dictionary = {}
var hands_played: int = 0
var opp_name: String = "Opponent"


func _ready() -> void:
	process_mode = Node.PROCESS_MODE_ALWAYS
	get_tree().paused = true

	_build_ui()

	replay_timer = Timer.new()
	replay_timer.wait_time = 0.08
	replay_timer.timeout.connect(_replay_tick)
	add_child(replay_timer)

	code_input.text = STARTER_BOT_CODE
	code_input.grab_focus()


# ---------------------------------------------------------------
# UI construction
# ---------------------------------------------------------------

func _build_ui() -> void:
	var root := Control.new()
	root.set_anchors_preset(Control.PRESET_FULL_RECT)
	add_child(root)

	var bg := ColorRect.new()
	bg.color = Color(0.08, 0.06, 0.07, 0.96)
	bg.set_anchors_preset(Control.PRESET_FULL_RECT)
	root.add_child(bg)

	var margin := MarginContainer.new()
	margin.set_anchors_preset(Control.PRESET_FULL_RECT)
	margin.add_theme_constant_override("margin_left", 16)
	margin.add_theme_constant_override("margin_right", 16)
	margin.add_theme_constant_override("margin_top", 16)
	margin.add_theme_constant_override("margin_bottom", 16)
	root.add_child(margin)

	var outer_vbox := VBoxContainer.new()
	outer_vbox.add_theme_constant_override("separation", 12)
	margin.add_child(outer_vbox)

	var main_hbox := HBoxContainer.new()
	main_hbox.add_theme_constant_override("separation", 12)
	main_hbox.size_flags_vertical = Control.SIZE_EXPAND_FILL
	outer_vbox.add_child(main_hbox)

	# ---- Left: terminal ----
	var term_panel := PanelContainer.new()
	term_panel.custom_minimum_size = Vector2(300, 0)
	main_hbox.add_child(term_panel)

	var term_vbox := VBoxContainer.new()
	term_vbox.add_theme_constant_override("separation", 8)
	term_panel.add_child(term_vbox)

	var term_title := Label.new()
	term_title.text = "Code terminal"
	term_vbox.add_child(term_title)

	code_input = TextEdit.new()
	code_input.size_flags_vertical = Control.SIZE_EXPAND_FILL
	code_input.wrap_mode = TextEdit.LINE_WRAPPING_NONE
	term_vbox.add_child(code_input)

	var btn_hbox := HBoxContainer.new()
	btn_hbox.add_theme_constant_override("separation", 8)
	term_vbox.add_child(btn_hbox)

	run_button = Button.new()
	run_button.text = "Run"
	run_button.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	btn_hbox.add_child(run_button)

	close_button = Button.new()
	close_button.text = "Close"
	close_button.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	btn_hbox.add_child(close_button)

	status_label = Label.new()
	status_label.text = "Ready."
	status_label.autowrap_mode = TextServer.AUTOWRAP_WORD
	term_vbox.add_child(status_label)

	# ---- Right: results ----
	var right_vbox := VBoxContainer.new()
	right_vbox.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	right_vbox.size_flags_vertical = Control.SIZE_EXPAND_FILL
	right_vbox.add_theme_constant_override("separation", 8)
	main_hbox.add_child(right_vbox)

	tab_container = TabContainer.new()
	tab_container.size_flags_vertical = Control.SIZE_EXPAND_FILL
	right_vbox.add_child(tab_container)

	# Table tab
	var table_tab := VBoxContainer.new()
	table_tab.name = "Table"
	table_tab.add_theme_constant_override("separation", 8)
	tab_container.add_child(table_tab)

	table_view = TableView.new()
	table_view.custom_minimum_size = Vector2(0, 280)
	table_view.size_flags_vertical = Control.SIZE_EXPAND_FILL
	table_tab.add_child(table_view)

	log_view = RichTextLabel.new()
	log_view.bbcode_enabled = true
	log_view.custom_minimum_size = Vector2(0, 140)
	log_view.scroll_following = true
	table_tab.add_child(log_view)

	# Stack graph tab
	var graph_tab := VBoxContainer.new()
	graph_tab.name = "Stack graph"
	tab_container.add_child(graph_tab)

	graph_view = GraphView.new()
	graph_view.size_flags_vertical = Control.SIZE_EXPAND_FILL
	graph_tab.add_child(graph_view)

	# Match stats tab
	var stats_tab := VBoxContainer.new()
	stats_tab.name = "Match stats"
	tab_container.add_child(stats_tab)

	stats_label = RichTextLabel.new()
	stats_label.bbcode_enabled = true
	stats_label.size_flags_vertical = Control.SIZE_EXPAND_FILL
	stats_tab.add_child(stats_label)

	# ---- Bottom: reference bar ----
	outer_vbox.add_child(_make_reference_bar())

	run_button.pressed.connect(_on_run_pressed)
	close_button.pressed.connect(_on_close_pressed)


func _make_reference_bar() -> Control:
	var panel := PanelContainer.new()
	panel.custom_minimum_size = Vector2(0, 170)

	var grid := GridContainer.new()
	grid.columns = 5
	grid.add_theme_constant_override("h_separation", 16)
	panel.add_child(grid)

	grid.add_child(_make_ref_column("Actions to return", Color(0.06, 0.44, 0.34), [
		"(\"fold\", 0)",
		"(\"check\", 0)",
		"(\"call\", to_call)",
		"(\"raise\", total_chips)",
		"(\"all_in\", my_stack)",
	]))
	grid.add_child(_make_ref_column("Parameters", Color(0.33, 0.29, 0.72), [
		"hole -- your 2 cards",
		"community -- board cards",
		"to_call -- 0 means free check",
		"min_raise -- smallest raise total",
	]))
	grid.add_child(_make_ref_column("Card format", Color(0.85, 0.35, 0.19), [
		"rank 2-14 (14 = ace)",
		"suit: s h d c",
		"(14, 's') = ace of spades",
		"stage: preflop/flop/turn/river",
	]))
	grid.add_child(_make_ref_column("Reading your cards", Color(0.19, 0.5, 0.75), [
		"rank1 = hole[0][0]",
		"rank1, suit1 = hole[0]",
		"is_pair = hole[0][0] == hole[1][0]",
		"high_card = max(hole[0][0], hole[1][0]) > 10",
		"is_suited = hole[0][1] == hole[1][1]",
	]))
	grid.add_child(_make_ref_column("Tips", Color(0.83, 0.33, 0.49), [
		"Win 3 matches to face a harder bot.",
		"A crash just folds that hand.",
		"Compare equity to pot odds to bluff less.",
		"Always wrap raises in min(my_stack, ...).",
	]))
	return panel


func _make_ref_column(title: String, color: Color, lines: Array) -> Control:
	var panel := PanelContainer.new()
	panel.size_flags_horizontal = Control.SIZE_EXPAND_FILL

	var style := StyleBoxFlat.new()
	style.bg_color = Color(1, 1, 1, 0.03)
	style.border_width_left = 3
	style.border_color = color
	style.content_margin_left = 10
	style.content_margin_top = 6
	style.content_margin_bottom = 6
	style.content_margin_right = 8
	panel.add_theme_stylebox_override("panel", style)

	var box := VBoxContainer.new()
	box.add_theme_constant_override("separation", 3)
	panel.add_child(box)

	var title_label := Label.new()
	title_label.text = title
	title_label.add_theme_color_override("font_color", color)
	box.add_child(title_label)

	for line in lines:
		var l := Label.new()
		l.text = str(line)
		l.add_theme_font_size_override("font_size", 12)
		l.autowrap_mode = TextServer.AUTOWRAP_WORD
		box.add_child(l)

	return panel


# ---------------------------------------------------------------
# Running a match
# ---------------------------------------------------------------

func _py_string_literal(path: String) -> String:
	var escaped := path.replace("\\", "\\\\").replace("\"", "\\\"")
	return "\"" + escaped + "\""


func _on_run_pressed() -> void:
	run_button.disabled = true
	status_label.text = "Running your bot..."
	log_view.clear()
	stack_history = []
	action_counts = {}
	hands_played = 0
	table_view.reset_all()
	graph_view.set_data([])
	stats_label.text = ""

	var engine_path := "res://poker_engine.py"
	if not FileAccess.file_exists(engine_path):
		_show_fallback("Couldn't find poker_engine.py in the project. Make sure it's placed at res://poker_engine.py.")
		run_button.disabled = false
		return

	var engine_file := FileAccess.open(engine_path, FileAccess.READ)
	var engine_source := engine_file.get_as_text()
	engine_file.close()

	var state_real_path := ProjectSettings.globalize_path("user://poker_state.jsonl")
	var wipe := FileAccess.open(state_real_path, FileAccess.WRITE)
	if wipe:
		wipe.close()

	var footer := "\n\n# ---- Runs one ranked match against your current opponent tier ----\n" \
		+ "play_ranked_match(my_bot, state_log_path=%s)\n" % _py_string_literal(state_real_path)

	var full_script := engine_source + "\n\n# ---- Your bot code ----\n\n" + code_input.text + footer

	var temp_path := "user://temp_poker_bot.py"
	var out_file := FileAccess.open(temp_path, FileAccess.WRITE)
	if out_file == null:
		_show_fallback("Couldn't create a temp file to run.")
		run_button.disabled = false
		return
	out_file.store_string(full_script)
	out_file.close()

	var real_path := ProjectSettings.globalize_path(temp_path)
	var python_exe := "python3"
	if OS.get_name() == "Windows":
		python_exe = "python"

	var output := []
	var exit_code := OS.execute(python_exe, [real_path], output, true)

	pending_events = []
	if FileAccess.file_exists(state_real_path):
		var sf := FileAccess.open(state_real_path, FileAccess.READ)
		var text := sf.get_as_text()
		sf.close()
		for line in text.split("\n"):
			var stripped := line.strip_edges()
			if stripped == "":
				continue
			var parsed = JSON.parse_string(stripped)
			if parsed != null:
				pending_events.append(parsed)

	if pending_events.is_empty():
		var raw_output := ""
		if output.size() > 0:
			raw_output = str(output[0])
		if raw_output.strip_edges() == "":
			raw_output = "(no output -- exited with code %d)" % exit_code
		_show_fallback(raw_output)
		run_button.disabled = false
		return

	replay_index = 0
	events_per_tick = max(1, int(ceil(pending_events.size() / 200.0)))
	replay_timer.start()


func _replay_tick() -> void:
	if replay_index >= pending_events.size():
		replay_timer.stop()
		run_button.disabled = false
		if status_label.text == "Running your bot...":
			status_label.text = "Done -- press Run to play again."
		return
	var end_index: int = min(replay_index + events_per_tick, pending_events.size())
	while replay_index < end_index:
		_handle_event(pending_events[replay_index])
		replay_index += 1


func _show_fallback(text: String) -> void:
	log_view.clear()
	var safe_text := text.replace("[", "(").replace("]", ")")
	_log("[color=#e08a4a]" + safe_text + "[/color]")
	status_label.text = "Something went wrong -- see the log below."


func _log(text: String) -> void:
	log_view.append_text(text + "\n")


# ---------------------------------------------------------------
# Event handling (drives the Table / Stack graph / Match stats tabs)
# ---------------------------------------------------------------

func _handle_event(ev: Dictionary) -> void:
	var etype := String(ev.get("type", ""))
	match etype:
		"ranked_start":
			var tier := String(ev.get("tier", "easy"))
			opp_name = "Opponent (%s)" % tier.capitalize()
			table_view.your_name = "Your Bot"
			table_view.opp_name = opp_name
			status_label.text = "vs %s tier -- %d/%d wins to advance" % [
				tier.capitalize(), int(ev.get("wins_at_tier", 0)), int(ev.get("wins_to_advance", 3))]
			_log("[b]Ranked match vs %s[/b]" % tier.capitalize())

		"hand_start":
			table_view.reset_hand()
			table_view.set_stacks(ev.get("stacks", {}))
			_log("Hand #%d -- dealer: %s" % [int(ev.get("hand_num", 0)), String(ev.get("dealer", ""))])

		"blinds_posted":
			table_view.set_pot(int(ev.get("pot", 0)))
			_log("%s posts %d, %s posts %d" % [
				String(ev.get("sb_name", "")), int(ev.get("sb_amount", 0)),
				String(ev.get("bb_name", "")), int(ev.get("bb_amount", 0))])

		"hole_cards":
			table_view.set_hole(String(ev.get("player", "")), ev.get("hole", []))

		"street":
			table_view.set_community(ev.get("community", []))
			table_view.set_pot(int(ev.get("pot", 0)))
			_log("[b]%s[/b] -- pot %d" % [String(ev.get("stage", "")).capitalize(), int(ev.get("pot", 0))])

		"action":
			table_view.set_pot(int(ev.get("pot", 0)))
			var act := String(ev.get("action", ""))
			var added := int(ev.get("chips_added", 0))
			action_counts[act] = int(action_counts.get(act, 0)) + 1
			if added > 0:
				_log("%s: %s %d" % [String(ev.get("player", "")), act, added])
			else:
				_log("%s: %s" % [String(ev.get("player", "")), act])

		"showdown":
			if bool(ev.get("folded_win", false)):
				_log("[color=#d9a441]%s wins %d (opponent folded)[/color]" % [
					String(ev.get("winner", "")), int(ev.get("amount", 0))])
			else:
				table_view.reveal_opponent()
				for h in ev.get("hands", []):
					_log("%s: %s" % [String(h.get("player", "")), String(h.get("description", ""))])
				for pot_info in ev.get("pots", []):
					var winners: Dictionary = pot_info.get("winners", {})
					for wname in winners.keys():
						_log("[color=#d9a441]%s wins %s from a %d pot (%s)[/color]" % [
							wname, str(winners[wname]), int(pot_info.get("amount", 0)),
							String(pot_info.get("description", ""))])

		"hand_end":
			var stacks: Dictionary = ev.get("stacks", {})
			table_view.set_stacks(stacks)
			hands_played = int(ev.get("hand_num", hands_played))
			stack_history.append({
				"hand": hands_played,
				"you": int(stacks.get("Your Bot", 0)),
				"opp": int(stacks.get(opp_name, 0)),
			})
			graph_view.set_data(stack_history)
			_update_stats()

		"match_end":
			_log("[b]MATCH RESULT: %s[/b]" % String(ev.get("result", "")).to_upper())

		"ranked_end":
			if bool(ev.get("leveled_up", false)):
				_log("[color=#5ec26a][b]LEVEL UP -- next opponent: %s[/b][/color]" % String(ev.get("next_tier", "")).to_upper())
			status_label.text = "%s -- record %dW-%dL" % [
				String(ev.get("result", "")).to_upper(),
				int(ev.get("total_wins", 0)), int(ev.get("total_losses", 0))]
			_update_stats()

		"fatal_error":
			_log("[color=#e05555]Your bot crashed: %s[/color]" % String(ev.get("message", "")))

		_:
			pass


func _update_stats() -> void:
	var lines: Array = []
	lines.append("[b]Hands played:[/b] %d" % hands_played)
	for act in action_counts.keys():
		lines.append("%s: %d" % [String(act).capitalize(), int(action_counts[act])])
	stats_label.text = "\n".join(lines)


func _on_close_pressed() -> void:
	get_tree().paused = false
	queue_free()


func _unhandled_input(event: InputEvent) -> void:
	if event is InputEventKey and event.pressed and event.keycode == KEY_ESCAPE:
		_on_close_pressed()
