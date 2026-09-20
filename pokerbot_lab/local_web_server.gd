class_name LocalWebServer
extends RefCounted

const HOST := "127.0.0.1"
const START_PORT := 18321
const PORT_ATTEMPTS := 20

var _pid := -1
var _port := -1
var _runtime_root := ""

func start() -> Dictionary:
	if _pid > 0 and OS.is_process_running(_pid):
		return {"ok": true, "url": url()}

	var python := _find_python()
	if python.is_empty():
		return {"ok": false, "error": "Python 3 is required for this prototype's local web server."}

	# res:// files live inside the exported PCK and cannot be served by an external
	# process. Materialize the bundled site and server script into user:// once per
	# build; in the editor, use the source directory directly for faster iteration.
	var prepared := _prepare_runtime_files()
	if not prepared.get("ok", false):
		return prepared
	var root: String = prepared["root"]
	var script: String = prepared["script"]

	for candidate in range(START_PORT, START_PORT + PORT_ATTEMPTS):
		var args := PackedStringArray([script, "--root", root, "--port", str(candidate)])
		var pid := OS.create_process(python, args, false)
		if pid <= 0:
			continue
		_pid = pid
		_port = candidate
		return {"ok": true, "url": url()}
	return {"ok": false, "error": "Could not start the local Bet2Bot server."}

func stop() -> void:
	if _pid > 0 and OS.is_process_running(_pid):
		OS.kill(_pid)
	_pid = -1
	_port = -1

func url() -> String:
	return "http://%s:%d/?embed=1" % [HOST, _port]

func _prepare_runtime_files() -> Dictionary:
	if OS.has_feature("editor"):
		return {
			"ok": true,
			"root": ProjectSettings.globalize_path("res://pokerbot_lab/web"),
			"script": ProjectSettings.globalize_path("res://pokerbot_lab/local_server.py"),
		}

	_runtime_root = ProjectSettings.globalize_path("user://bet2bot_local")
	var marker := _runtime_root.path_join(".bundle-version")
	var version := _read_text("res://pokerbot_lab/web/bundle-version.txt").strip_edges()
	if version.is_empty():
		return {"ok": false, "error": "Bundled Bet2Bot version is missing."}
	if not FileAccess.file_exists(marker) or _read_text(marker).strip_edges() != version:
		_remove_tree(_runtime_root)
		DirAccess.make_dir_recursive_absolute(_runtime_root)
		var copied := _copy_resource_tree("res://pokerbot_lab/web", _runtime_root)
		if not copied.get("ok", false):
			return copied
		var script_copy := _runtime_root.path_join("local_server.py")
		var script_data := FileAccess.get_file_as_bytes("res://pokerbot_lab/local_server.py")
		if script_data.is_empty():
			return {"ok": false, "error": "Bundled local server script is missing."}
		var script_out := FileAccess.open(script_copy, FileAccess.WRITE)
		if script_out == null:
			return {"ok": false, "error": "Cannot create local server script."}
		script_out.store_buffer(script_data)
		var marker_out := FileAccess.open(marker, FileAccess.WRITE)
		if marker_out != null:
			marker_out.store_string(version)
	return {
		"ok": true,
		"root": _runtime_root,
		"script": _runtime_root.path_join("local_server.py"),
	}

func _copy_resource_tree(source: String, destination: String) -> Dictionary:
	var directory := DirAccess.open(source)
	if directory == null:
		return {"ok": false, "error": "Bundled Bet2Bot files cannot be opened."}
	DirAccess.make_dir_recursive_absolute(destination)
	directory.list_dir_begin()
	while true:
		var name := directory.get_next()
		if name.is_empty():
			break
		if name == "." or name == "..":
			continue
		var source_path := source.path_join(name)
		var destination_path := destination.path_join(name)
		if directory.current_is_dir():
			var nested := _copy_resource_tree(source_path, destination_path)
			if not nested.get("ok", false):
				directory.list_dir_end()
				return nested
		else:
			var bytes := FileAccess.get_file_as_bytes(source_path)
			var output := FileAccess.open(destination_path, FileAccess.WRITE)
			if output == null:
				directory.list_dir_end()
				return {"ok": false, "error": "Cannot extract bundled file: " + name}
			output.store_buffer(bytes)
	directory.list_dir_end()
	return {"ok": true}

func _remove_tree(path: String) -> void:
	if not DirAccess.dir_exists_absolute(path):
		return
	var directory := DirAccess.open(path)
	if directory == null:
		return
	directory.list_dir_begin()
	while true:
		var name := directory.get_next()
		if name.is_empty():
			break
		if name == "." or name == "..":
			continue
		var child := path.path_join(name)
		if directory.current_is_dir():
			_remove_tree(child)
		else:
			DirAccess.remove_absolute(child)
	directory.list_dir_end()
	DirAccess.remove_absolute(path)

func _read_text(path: String) -> String:
	var file := FileAccess.open(path, FileAccess.READ)
	return file.get_as_text() if file != null else ""

func _find_python() -> String:
	if OS.get_name() == "Windows":
		# Same assumption the code editor already makes: `python` on PATH.
		return "python"
	for path in ["/usr/bin/python3", "/opt/homebrew/bin/python3", "/usr/local/bin/python3"]:
		if FileAccess.file_exists(path):
			return path
	return ""
