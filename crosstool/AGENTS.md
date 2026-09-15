# Godot 4 Guardrails — Godot 4 rules for AI coding agents

This file is the project's agent contract. Read it before writing Godot code, and
follow the verification rules before reporting any task complete.

Helper scripts referenced below live in `.godot-guard/scripts/` (python3, stdlib only).

## Contents

- [Godot 4 API guard (no Godot 3 idioms, no invented APIs)](#godot-4-api-guard-no-godot-3-idioms-no-invented-apis)

---

## Godot 4 API guard (no Godot 3 idioms, no invented APIs)

Godot 4 projects break when Godot 3 syntax leaks in. Your training data is full of Godot 3.
Do not write Godot code from memory — check it against the table below, then run the scanner.

### Run the scanner after every edit

```bash
python3 .godot-guard/scripts/api_guard.py <files or .>
```

Exit `0` = clean, `1` = findings, `2` = usage error. `--json` for machine output,
`--severity error` to hide warnings, `--list-rules` to print every rule with its docs URL.
Fix every `[error]` finding with the `fix:` line it prints. `[warn]` findings are migration
debt: fix them when you touch that file, otherwise report them. Re-run until `0 finding(s)`.

### Godot 3 idioms that are errors in Godot 4 (73 rules, verified against Godot 4.7 class reference (docs 'stable' = 4.7), 4.7 branch source, upgrading_to_godot_4 guide)

| Never write | Write instead |
|---|---|
| `yield(obj, "signal") / var x = yield(f(), "completed")` | `await obj.signal / var x = await f()` |
| `yield(get_tree().create_timer(1.0), "timeout")` | `await get_tree().create_timer(1.0).timeout` |
| `(hallucination) await get_tree().create_timer(1.0)` | `await get_tree().create_timer(1.0).timeout` |
| `obj.connect("pressed", self, "_on_pressed")` | `obj.pressed.connect(_on_pressed)  # or obj.connect("pressed", Callable(self, "_on_pressed"))` |
| `obj.disconnect("sig", self, "m") / obj.is_connected("sig", self, "m")` | `obj.sig.disconnect(m) / obj.sig.is_connected(m)` |
| `(hallucination) await Signal.any([a, b])` | `await a  # Signal has no any(); await one signal, or write a small aggregator node/lambda` |
| `funcref(self, "method")` | `Callable(self, "method")  # or just self.method` |
| `thread.start(self, "_work", data)` | `thread.start(_work.bind(data))` |
| `$Tween.interpolate_property(...); $Tween.start(); yield($Tween, "tween_all_completed")` | `var t := create_tween(); t.tween_property(obj, "prop", final_val, dur); await t.finished` |
| `yield(get_tree(), "idle_frame")` | `await get_tree().process_frame` |
| `._ready()  (call parent implementation)` | `super()  # or super._ready()` |
| `packed_scene.instance()` | `packed_scene.instantiate()` |
| `get_tree().change_scene(path) / change_scene_to(packed)` | `get_tree().change_scene_to_file(path) / change_scene_to_packed(packed)` |
| `extends KinematicBody2D / KinematicBody` | `extends CharacterBody2D / CharacterBody3D` |
| `velocity = move_and_slide(velocity, Vector2.UP)` | `velocity = v  # property move_and_slide()  # no args, returns bool` |
| `velocity = move_and_slide(velocity)` | `move_and_slide()  # velocity is updated in place` |
| `move_and_slide_with_snap(velocity, snap, up)` | `move_and_slide()  # snapping via floor_snap_length property` |
| `get_slide_count()` | `get_slide_collision_count()` |
| `add_force(offset, force) / add_central_force(f) / add_torque(t)` | `apply_force(force, position=Vector2.ZERO) / apply_central_force(f) / apply_torque(t)` |
| `body.mode = RigidBody2D.MODE_STATIC` | `body.freeze = true; body.freeze_mode = RigidBody2D.FREEZE_MODE_STATIC` |
| `raycast.cast_to` | `raycast.target_position` |
| `Physics2DServer / PhysicsServer / Physics2DDirectSpaceState` | `PhysicsServer2D / PhysicsServer3D / PhysicsDirectSpaceState2D / PhysicsDirectSpaceState3D` |
| `deg2rad(x) / rad2deg(x)` | `deg_to_rad(x) / rad_to_deg(x)` |
| `rand_range(a, b)` | `randf_range(a, b)  # ints: randi_range(a, b)` |
| `a.linear_interpolate(b, t)` | `a.lerp(b, t)` |
| `stepify(x, s) / v.clamped(len) / v.tangent()` | `snapped(x, s) / v.limit_length(len) / v.orthogonal()` |
| `TYPE_REAL` | `TYPE_FLOAT` |
| `mat.set_shader_param("p", v)` | `mat.set_shader_parameter("p", v)` |
| `var f = File.new(); f.open(path, File.READ)` | `var f := FileAccess.open(path, FileAccess.READ)  # null on failure; FileAccess.get_open_error()` |
| `File.READ` | `FileAccess.READ` |
| `var d = Directory.new(); d.open(path)` | `var d := DirAccess.open(path)  # or static DirAccess.dir_exists_absolute(), make_dir_recursive_absolute(), get_files_at()` |
| `OS.get_ticks_msec()` | `Time.get_ticks_msec()  # / Time.get_ticks_usec()` |
| `OS.get_datetime() / OS.get_unix_time()` | `Time.get_datetime_dict_from_system() / Time.get_unix_time_from_system()` |
| `OS.get_screen_size() / OS.window_size` | `DisplayServer.screen_get_size() / get_window().size / DisplayServer.window_set_mode()` |
| `if Engine.editor_hint:` | `if Engine.is_editor_hint():` |
| `JSON.parse(text).result / parse_json(text) / to_json(data) / JSON.print(data)` | `JSON.parse_string(text) / JSON.stringify(data)  # or var j := JSON.new(); j.parse(text); j.data` |
| `str2var / var2str / bytes2var / var2bytes` | `str_to_var / var_to_str / bytes_to_var / var_to_bytes` |
| `s.percent_encode() / s.http_escape()` | `s.uri_encode()` |
| `event.button_index == BUTTON_LEFT` | `event.button_index == MOUSE_BUTTON_LEFT` |
| `event.scancode` | `event.keycode  # / physical_keycode` |
| `event.doubleclick` | `event.double_click` |
| `Input.warp_mouse_position(p)` | `Input.warp_mouse(p)` |
| `get_tree().set_input_as_handled()` | `get_viewport().set_input_as_handled()` |
| `export var speed = 10 / export(int, 0, 100) var hp` | `@export var speed := 10 / @export_range(0, 100) var hp: int` |
| `export(int, "Warrior", "Mage") var cls` | `@export_enum("Warrior", "Mage") var cls: int` |
| `onready var sprite = $Sprite` | `@onready var sprite: Sprite2D = $Sprite2D` |
| `tool` | `@tool` |
| `var hp = 10 setget set_hp, get_hp` | `var hp := 10: 	set(value): 		hp = value 	get: 		return hp` |
| `remote func f(): / master func / puppet func` | `@rpc("any_peer") func f(): / @rpc("authority", "call_local")` |
| `pause_mode = PAUSE_MODE_PROCESS` | `process_mode = Node.PROCESS_MODE_ALWAYS  # INHERIT→PROCESS_MODE_INHERIT, STOP→PROCESS_MODE_PAUSABLE` |
| `PoolByteArray / PoolIntArray / PoolRealArray / PoolStringArray / PoolVector2Array ...` | `PackedByteArray / PackedInt32Array / PackedFloat32Array / PackedStringArray / PackedVector2Array ...` |
| `var t: Transform / Quat(...)` | `var t: Transform3D / Quaternion(...)` |
| `extends Reference` | `extends RefCounted` |
| `export(Texture) var icon` | `@export var icon: Texture2D` |
| `DynamicFont` | `FontFile` |
| `Color.palegreen / Color.white` | `Color.PALE_GREEN / Color.WHITE` |
| `extends Spatial` | `extends Node3D` |
| `extends Sprite / var s: AnimatedSprite` | `extends Sprite2D / var s: AnimatedSprite2D` |
| `Particles2D / Particles / Light2D` | `GPUParticles2D / GPUParticles3D / PointLight2D` |
| `Position2D / Position3D` | `Marker2D / Marker3D` |
| `VisibilityNotifier2D / VisibilityNotifier / VisibilityEnabler2D` | `VisibleOnScreenNotifier2D / VisibleOnScreenNotifier3D / VisibleOnScreenEnabler2D` |
| `extends Area / RigidBody / StaticBody / Camera / CollisionShape` | `extends Area3D / RigidBody3D / StaticBody3D / Camera3D / CollisionShape3D  (Listener→AudioListener3D)` |
| `VisualServer` | `RenderingServer` |
| `tilemap.set_cellv(pos, tile_id) / set_cell(x, y, id)` | `layer.set_cell(coords: Vector2i, source_id: int = -1, atlas_coords: Vector2i = Vector2i(-1, -1), alternative_tile: int = 0) / get_cell_source_id(coords)` |
| `tilemap.world_to_map(p) / map_to_world(c)` | `layer.local_to_map(p) / map_to_local(c)` |
| `ctrl.rect_position / rect_size / rect_min_size / rect_scale / rect_global_position` | `ctrl.position / size / custom_minimum_size / scale / global_position` |
| `add_color_override("font_color", c)` | `add_theme_color_override("font_color", c)` |
| `ctrl.set_tooltip("x")` | `ctrl.tooltip_text = "x"  # set_tooltip_text()` |
| `arr.empty()` | `arr.is_empty()` |
| `arr.invert()` | `arr.reverse()` |
| `is_a_parent_of(n)` | `is_ancestor_of(n)` |
| `agent.get_next_location() / set_target_location(p)` | `agent.get_next_path_position() / agent.target_position = p` |
| `[node type="KinematicBody2D"] etc. (Godot 3 class names in a scene file)` | `Godot 4 class names: CharacterBody2D, Node3D, Sprite2D, Area2D/3D, RigidBody2D/3D, Marker2D, VisibleOnScreenNotifier2D, MeshInstance3D, Camera3D, RayCast3D ...` |

#### Migration debt — fix when you touch the file (19 rules)

- `obj.connect("pressed", callable)  (string-based, still valid)` -> `obj.pressed.connect(callable)`
- `(hallucination) await sig.wait()` -> `await sig`
- `(hallucination) Object.instance_from_id(id)` -> `instance_from_id(id)  # global function; also is_instance_id_valid(id)`
- `apply_impulse(offset, impulse)` -> `apply_impulse(impulse, position=Vector2(0, 0))`
- `var t = ImageTexture.new(); t.create_from_image(img)` -> `var t := ImageTexture.create_from_image(img)  # static, returns ImageTexture`
- `node.translation` -> `node.position`
- `extends TileMap  (deprecated since 4.3)` -> `extends TileMapLayer  (one node per layer)`
- `ParallaxBackground + ParallaxLayer` -> `Parallax2D  (4.3+)`
- `camera.current = true` -> `camera.enabled = true; camera.make_current()`
- `ctrl.margin_left` -> `ctrl.offset_left`
- `button.pressed = true` -> `button.button_pressed = true`
- `anim.playing = true / anim.frames = sf` -> `anim.play() / anim.stop() / anim.sprite_frames = sf`
- `update()  # request redraw` -> `queue_redraw()`
- `node.raise()` -> `node.move_to_front()`
- `node.filename` -> `node.scene_file_path`
- `shape.extents` -> `shape.size`
- `arr.remove(i)` -> `arr.remove_at(i)`
- `[node type="TileMap"] (deprecated since 4.3)` -> `[node type="TileMapLayer"] one per layer`
- `[node type="ParallaxBackground"] / ParallaxLayer` -> `[node type="Parallax2D"] (4.3+)`

### Invented APIs — these do not exist in Godot 4.7

`Signal.any([...])`, `Signal.timeout()`, `Node.get_child_by_name()`, `Array.find_index()`.
If you cannot point at a docs page for a method, do not call it. For "first of two signals"
use the `CONNECT_ONE_SHOT` + `await get_tree().process_frame` helper, not `Signal.any`.

### Version pinning

`project.godot` → `config/features` holds the project's engine minor (e.g. `4.7`).
Read it before writing code, and never emit syntax newer than that minor. If the installed
binary (`godot --version`) disagrees with `config/features`, stop and report it — do not
"fix" `config/features` yourself, that line is what the editor uses to decide compatibility.

```bash
python3 .godot-guard/scripts/version_pin.py . --write AGENTS.md   # writes an idempotent pin block
```

### What changed in each 4.x minor (53 changes)

Emit syntax only from the minor the project pins or older.

**4.4** — Typed dictionaries `Dictionary[K, V]`; .uid sidecar files for scripts and shaders; @export_file stores uid:// instead of res:// when set from the Inspector; FileAccess.store_* now return bool; OS.read_string_from_stdin(buffer_size) parameter is now required; RenderingDevice.draw_list_begin() signature reduced; GraphEdit.frame_rect_changed signal parameter type; Curve enforces min_value/max_value; CSG uses the Manifold library; Jolt Physics integrated into the engine (opt-in); @export_tool_button annotation; Android sensor events disabled by default

**4.5** — @abstract classes and methods; Variadic functions (rest parameter); Resource.duplicate(true) no longer duplicates external subresources; @export_file_path annotation; RichTextLabel.add_image/update_image parameters; Node.get_rpc_config renamed; JSONRPC.set_scope replaced; RenderingServer interpolation methods removed; TileMapLayer physics chunking on by default; Area3D always reports static-body overlaps; Navigation regions update asynchronously by default; ProjectSettings.add_property_info() warns on invalid keys; 3D importer non-joint node hierarchy fix; Android C# exports require .NET 9

**4.6** — Jolt Physics is the default 3D physics engine for new projects; D3D12 default rendering driver on Windows for new projects; load_steps no longer written; per-node unique_id saved; AnimationPlayer animation-name properties are StringName; FileAccess.get_as_text() lost its skip_cr parameter; StreamPeerTCP/TCPServer methods moved to base classes; EditorFileDialog.add_side_menu() removed; Glow and volumetric fog defaults/appearance; AStar get_point_path/get_id_path return empty when the source is disabled/solid; MeshInstance3D.skeleton default; Android build template directory layout

**4.7** — Overrides of typed-return methods inherit the return type and need an explicit return; Packed array element assignment no longer calls the property setter; Object.is_class() takes StringName; Mouse and keyboard device IDs are no longer 0; Tween.tween_await(signal) / AwaitTweener; RichTextLabel.add_image/update_image sizing parameters; AudioStreamPlayer.area_mask default 1 → 0; AudioEffectSpectrumAnalyzer.tap_back_pos removed; WorldBoundaryShape3D plane distance sign; SoftBody3D mass and linear_stiffness under Jolt; AnimationNodeBlendSpace1D/2D sync → sync_mode enum; LinearToSRGB no clamp; CanvasItem line feather removed; New projects default to stretch mode canvas_items / aspect expand; Minimum macOS 11 (Big Sur); LookAtModifier3D.relative default true → false

**4.8-dev** — [UPCOMING] String literals used as comments trigger STANDALONE_EXPRESSION

The full tables live in `.godot-guard/reference/godot3_isms.md` (92 rules) and
`.godot-guard/reference/deltas_4.4-4.7.md` (53 changes), each row with its official source URL.
