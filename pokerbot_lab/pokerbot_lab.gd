extends CanvasLayer

# PokerBot Lab — the Bet2Bot app running inside the in-game computer.
#
# Registered as the `PokerBotLab` autoload (see project.godot), so one instance lives for
# the whole game: the web app (and its Python engine, which takes a few seconds to boot)
# loads once at startup and is simply shown/hidden as the player uses the computer.
# `computer.gd` calls open() / close(); this layer pauses the game while open, exactly
# like the original code_editor_ui did.
#
# Bet2Bot is served from the bundled copy in pokerbot_lab/web on 127.0.0.1 (no internet
# needed) and rendered by the Godot WRY WebView (patched build — see addons/godot_wry).

const LocalWebServer = preload("res://pokerbot_lab/local_web_server.gd")

@onready var root: Control = $Root
@onready var webview: WebView = $Root/Margin/Layout/Screen/WebView
@onready var title_label: Label = $Root/Margin/Layout/Header/Title
@onready var status_label: Label = $Root/Margin/Layout/Header/Status
@onready var close_button: Button = $Root/Margin/Layout/Header/Close
@onready var loading_label: Label = $Root/Margin/Layout/Screen/Loading

var _server := LocalWebServer.new()
var _open := false
var _page_ready := false

func _ready() -> void:
	process_mode = Node.PROCESS_MODE_ALWAYS
	root.visible = false
	webview.set_visible(false)
	close_button.pressed.connect(close)
	webview.page_load_started.connect(_on_page_load_started)
	webview.page_load_finished.connect(_on_page_load_finished)
	webview.ipc_message.connect(_on_ipc_message)

	var started: Dictionary = _server.start()
	if started.get("ok", false):
		webview.load_url(started["url"])
	else:
		_set_status(String(started.get("error", "Local server failed to start.")))

	if OS.has_environment("POKERBOT_LAB_AUTOTEST"):
		call_deferred("open")

func _exit_tree() -> void:
	_server.stop()

func is_open() -> bool:
	return _open

func open() -> void:
	if _open:
		return
	_open = true
	get_tree().paused = true
	root.visible = true
	loading_label.visible = not _page_ready
	if _page_ready:
		_show_webview()

func close() -> void:
	if not _open:
		return
	_open = false
	webview.focus_parent()
	webview.set_visible(false)
	root.visible = false
	get_tree().paused = false

func _unhandled_input(event: InputEvent) -> void:
	if _open and event.is_action_pressed("ui_cancel"):
		close()
		get_viewport().set_input_as_handled()

func _show_webview() -> void:
	# Let the frame draw first so the native view appears over the finished chrome.
	await get_tree().process_frame
	if not _open or not _page_ready:
		return
	loading_label.visible = false
	webview.set_visible(true)
	webview.resize()
	webview.focus()

func _on_page_load_started(_url: String) -> void:
	_page_ready = false
	_set_status("Loading Bet2Bot…")

func _on_page_load_finished(url: String) -> void:
	_page_ready = true
	_set_status("")
	print("PokerBot Lab: loaded ", url)
	# Tell the web app it is hosted inside the game (lets it adapt later).
	webview.eval("window.__pokerbotHost = 'godot'; ipc.postMessage(JSON.stringify({type:'bet2bot_loaded', title:document.title}))")
	if _open:
		_show_webview()

func _on_ipc_message(message: String) -> void:
	var data: Variant = JSON.parse_string(message)
	if typeof(data) != TYPE_DICTIONARY:
		return
	match String(data.get("type", "")):
		"bet2bot_loaded":
			print("PokerBot Lab: IPC OK — ", data.get("title", ""))
			if OS.has_environment("POKERBOT_LAB_AUTOTEST"):
				_run_geometry_test()
		_:
			pass

func _set_status(text: String) -> void:
	status_label.text = text

# ---------------------------------------------------------------------------
# Self-test (POKERBOT_LAB_AUTOTEST=1): verify the native WebView sits exactly on its
# Control at several window sizes on every attached display, then quit.
# ---------------------------------------------------------------------------
func _run_geometry_test() -> void:
	await get_tree().process_frame
	var failures := 0
	var godot_scale := maxf(DisplayServer.screen_get_max_scale(), 1.0)
	var sizes := [
		["default", Vector2i(1152, 648), false],
		["large", Vector2i(1600, 1000), false],
		["small", Vector2i(900, 500), false],
		["fullscreen", Vector2i.ZERO, true],
	]
	for screen in range(DisplayServer.get_screen_count()):
		DisplayServer.window_set_mode(DisplayServer.WINDOW_MODE_WINDOWED)
		DisplayServer.window_set_current_screen(screen)
		for i in range(8):
			await get_tree().process_frame
		for c in sizes:
			if c[2]:
				DisplayServer.window_set_mode(DisplayServer.WINDOW_MODE_FULLSCREEN)
			else:
				DisplayServer.window_set_mode(DisplayServer.WINDOW_MODE_WINDOWED)
				DisplayServer.window_set_size(c[1])
			for i in range(8):
				await get_tree().process_frame
			webview.resize()
			await get_tree().process_frame
			var xform: Transform2D = get_viewport().get_final_transform() * webview.get_global_transform_with_canvas()
			var expected := Rect2(xform.origin / godot_scale,
				Vector2(webview.size.x * xform.x.length(), webview.size.y * xform.y.length()) / godot_scale)
			var actual: Rect2 = webview.get_native_bounds()
			var ok := actual.position.distance_to(expected.position) <= 2.0 and actual.size.distance_to(expected.size) <= 2.0
			if not ok:
				failures += 1
			print("GEOM screen%d %s win=%s expected=%s actual=%s %s" % [
				screen, c[0], DisplayServer.window_get_size(), expected, actual, "OK" if ok else "MISMATCH"])
	DisplayServer.window_set_mode(DisplayServer.WINDOW_MODE_WINDOWED)
	print("GEOMTEST %s" % ("PASS" if failures == 0 else "FAIL %d" % failures))
	get_tree().quit(0 if failures == 0 else 1)
