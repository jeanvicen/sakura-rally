extends CanvasLayer
## Touch-only driving controls for the web export. The original keyboard and gamepad map remains
## unchanged; this overlay only forwards held buttons to those same actions on touch devices.

const ACTIVE_STATES: Array[int] = [
	Game.State.COUNTDOWN,
	Game.State.RACING,
	Game.State.FREE_ROAM,
	Game.State.LIAISON,
]

var _root: Control
var _buttons: Dictionary = {}
var _held: Dictionary = {}
var _touch_device := false


func _ready() -> void:
	process_mode = Node.PROCESS_MODE_ALWAYS
	if not OS.has_feature("web") or not DisplayServer.is_touchscreen_available():
		return
	_touch_device = true
	layer = 30
	_root = Control.new()
	_root.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	_root.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(_root)
	_build_buttons()
	get_viewport().size_changed.connect(_layout)
	Game.state_changed.connect(_on_game_state_changed)
	Game.paused_changed.connect(_on_pause_changed)
	_layout()
	_refresh()


func _exit_tree() -> void:
	_release_all()


func _on_game_state_changed(_new_state: int, _old_state: int) -> void:
	_refresh()


func _on_pause_changed(_paused: bool) -> void:
	_refresh()


func _refresh() -> void:
	if not _touch_device:
		return
	var show_controls := ACTIVE_STATES.has(Game.state) and not Game.paused
	_root.visible = show_controls
	if not show_controls:
		_release_all()


func _build_buttons() -> void:
	_add_button("left", "←", &"steer_left", true)
	_add_button("right", "→", &"steer_right", true)
	_add_button("brake", "BRAKE", &"brake", true)
	_add_button("gas", "GAS", &"throttle", true)
	_add_button("handbrake", "HB", &"handbrake", true)
	_add_button("camera", "CAM", &"camera_next", true)
	_add_button("reset", "RESET", &"reset_car", true)
	_add_button("pause", "PAUSE", &"pause", true)


func _add_button(id: String, label: String, action: StringName, hold: bool) -> void:
	var button := Button.new()
	button.name = id
	button.text = label
	button.focus_mode = Control.FOCUS_NONE
	button.mouse_filter = Control.MOUSE_FILTER_STOP
	button.clip_text = true
	button.add_theme_color_override("font_color", Color(1.0, 0.98, 0.94, 0.95))
	button.add_theme_color_override("font_hover_color", Color.WHITE)
	button.add_theme_color_override("font_pressed_color", Color.WHITE)
	button.add_theme_font_size_override("font_size", 16)
	button.add_theme_stylebox_override("normal", _style(Color(0.035, 0.045, 0.07, 0.62), Color(1.0, 0.88, 0.90, 0.48)))
	button.add_theme_stylebox_override("hover", _style(Color(0.11, 0.07, 0.11, 0.76), Color(1.0, 0.70, 0.78, 0.8)))
	button.add_theme_stylebox_override("pressed", _style(Color(0.62, 0.17, 0.31, 0.8), Color(1.0, 0.88, 0.90, 0.95)))
	_root.add_child(button)
	_buttons[id] = button
	button.button_down.connect(_press_action.bind(action))
	button.button_up.connect(_release_action.bind(action))
	button.tree_exiting.connect(_release_action.bind(action))


func _style(fill: Color, border: Color) -> StyleBoxFlat:
	var style := StyleBoxFlat.new()
	style.bg_color = fill
	style.border_color = border
	style.set_border_width_all(1)
	style.set_corner_radius_all(20)
	style.content_margin_left = 8
	style.content_margin_right = 8
	style.content_margin_top = 7
	style.content_margin_bottom = 7
	return style


func _layout() -> void:
	if not _touch_device or _root == null:
		return
	var viewport := get_viewport().get_visible_rect().size
	if viewport.x <= 0.0 or viewport.y <= 0.0:
		return
	var size := clampf(minf(viewport.x, viewport.y) * 0.17, 58.0, 104.0)
	var small := size * 0.72
	var margin := maxf(14.0, size * 0.22)
	var bottom := viewport.y - size - margin
	var gap := size * 0.12
	_place("left", margin, bottom, size)
	_place("right", margin + size + gap, bottom, size)
	_place("brake", viewport.x - margin - size * 2.0 - gap, bottom, size)
	_place("gas", viewport.x - margin - size, bottom, size)
	_place("handbrake", viewport.x - margin - size * 2.0 - gap, bottom - small - gap, small)
	_place("camera", viewport.x - margin - small, margin, small)
	_place("pause", viewport.x - margin - small * 2.0 - gap, margin, small)
	_place("reset", viewport.x - margin - small * 3.0 - gap * 2.0, margin, small)


func _place(id: String, x: float, y: float, size: float) -> void:
	var button: Button = _buttons[id]
	button.position = Vector2(x, y)
	button.size = Vector2(size, size)
	button.custom_minimum_size = Vector2(size, size)
	button.add_theme_font_size_override("font_size", clampi(int(size * 0.19), 11, 18))


func _press_action(action: StringName) -> void:
	_held[action] = true
	Input.action_press(action)


func _release_action(action: StringName) -> void:
	if not _held.has(action):
		return
	_held.erase(action)
	Input.action_release(action)


func _release_all() -> void:
	for action: StringName in _held.keys():
		Input.action_release(action)
	_held.clear()
