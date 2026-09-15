extends RefCounted
## GDScript port of scripts/api_guard.py — scans .gd/.tscn/.tres for Godot 3
## idioms and invalid 4.x API use.
##
## No editor classes are touched here, so this file also runs headless:
##     godot --headless --path <project> -s tests/godot/parity.gd
##
## Findings are Dictionaries:
##   {file, line, col, rule, severity, snippet, match, old, fix, note, url}

const SCAN_EXT := ["gd", "tscn", "tres"]
const RULES_PATH := "res://addons/godot_guard/reference/godot3_isms.json"

var rules: Array = []
var load_error := ""


func _init(rules_path: String = RULES_PATH) -> void:
	load_rules(rules_path)


# ------------------------------------------------------------------ rules
func load_rules(path: String) -> int:
	rules.clear()
	load_error = ""
	var text := _read_file(path)
	if text.is_empty():
		load_error = "cannot read rules: %s" % path
		return 0
	var json := JSON.new()
	if json.parse(text) != OK:
		load_error = "bad JSON in %s at line %d: %s" % [path, json.get_error_line(), json.get_error_message()]
		return 0
	var data: Variant = json.data
	var rows: Array = []
	if data is Dictionary:
		for key in ["rules", "rows", "items", "deltas", "entries"]:
			if data.has(key) and data[key] is Array:
				rows = data[key]
				break
	elif data is Array:
		rows = data
	var src := path.get_file().get_basename()
	for i in rows.size():
		var rule := _row_to_rule(rows[i], i, src)
		if not rule.is_empty():
			rules.append(rule)
	return rules.size()


func _row_to_rule(row: Variant, idx: int, src: String) -> Dictionary:
	if not (row is Dictionary):
		return {}
	var pat := str(_first(row, ["pattern", "regex"], ""))
	if pat.is_empty():
		return {}
	var rx := RegEx.new()
	if rx.compile(pat) != OK:
		push_warning("godot-guard: bad regex in rule %s (%s)" % [_first(row, ["id"], idx), src])
		return {}
	var sev := str(_first(row, ["severity"], "error")).to_lower()
	if sev.begins_with("warn"):
		sev = "warn"
	elif sev != "info":
		sev = "error"
	var ext_raw: Variant = _first(row, ["ext", "applies_to", "file_types", "files"], null)
	var ext: Array = []
	if ext_raw is String:
		ext = [ext_raw]
	elif ext_raw is Array:
		ext = (ext_raw as Array).duplicate()
	if ext.is_empty():
		ext = ["tscn", "tres"] if (pat.contains("type=") or pat.contains("[node")) else ["gd"]
	var ext_clean: Array = []
	for e in ext:
		ext_clean.append(str(e).lstrip(".").to_lower())
	return {
		"id": str(_first(row, ["id", "rule_id", "name"], "%s_%d" % [src, idx])),
		"rx": rx,
		"pattern": pat,
		"old": str(_first(row, ["godot3_form", "old", "from"], "")),
		"new": str(_first(row, ["godot4_form", "new", "to", "fix"], "")),
		"severity": sev,
		"note": str(_first(row, ["note", "agent_rule"], "")),
		"url": str(_first(row, ["source_url", "url"], "")),
		"ext": ext_clean,
	}


func _first(row: Dictionary, keys: Array, fallback: Variant) -> Variant:
	for k in keys:
		if row.has(k) and row[k] != null and str(row[k]) != "":
			return row[k]
	return fallback


# ---------------------------------------------------------------- masking
## Spans of the line that are comment or string, so a match inside them is not
## a finding. `state` carries an open multi-line construct between lines:
## "" | '"""' | "'''" | "/*".
func masked_spans(line: String, state: String, lang: String) -> Dictionary:
	var spans: Array = []
	var i := 0
	var n := line.length()
	if not state.is_empty():
		var close := "*/" if state == "/*" else state
		var j := line.find(close)
		if j < 0:
			return {"spans": [[0, n]], "state": state}
		spans.append([0, j + close.length()])
		i = j + close.length()
		state = ""
	while i < n:
		var c := line[i]
		if lang == "gd" and c == "#":
			spans.append([i, n])
			break
		if lang == "cs" and line.substr(i, 2) == "//":
			spans.append([i, n])
			break
		if lang == "cs" and line.substr(i, 2) == "/*":
			var j2 := line.find("*/", i + 2)
			if j2 < 0:
				spans.append([i, n])
				return {"spans": spans, "state": "/*"}
			spans.append([i, j2 + 2])
			i = j2 + 2
			continue
		if c == "\"" or c == "'":
			var triple := c.repeat(3)
			if lang == "gd" and line.substr(i, 3) == triple:
				var j3 := line.find(triple, i + 3)
				if j3 < 0:
					spans.append([i, n])
					return {"spans": spans, "state": triple}
				spans.append([i, j3 + 3])
				i = j3 + 3
				continue
			var j4 := i + 1
			while j4 < n and line[j4] != c:
				j4 += 2 if line[j4] == "\\" else 1
			spans.append([i, mini(j4 + 1, n)])
			i = j4 + 1
			continue
		i += 1
	return {"spans": spans, "state": state}


# --------------------------------------------------------------- scanning
func scan_text(text: String, path: String) -> Array:
	var ext := path.get_extension().to_lower()
	var lang := "cs" if ext == "cs" else ("gd" if ext == "gd" else "none")
	var active: Array = []
	for r in rules:
		if ext in r["ext"]:
			active.append(r)
	var findings: Array = []
	var state := ""
	var line_no := 0
	for line in text.split("\n", true):
		line_no += 1
		if line.ends_with("\r"):
			line = line.substr(0, line.length() - 1)
		var spans: Array = []
		if lang != "none":
			var res := masked_spans(line, state, lang)
			spans = res["spans"]
			state = res["state"]
		for r in active:
			for m in (r["rx"] as RegEx).search_all(line):
				var col: int = m.get_start(0)
				var masked := false
				for s in spans:
					if s[0] <= col and col < s[1]:
						masked = true
						break
				if masked:
					continue
				findings.append({
					"file": path,
					"line": line_no,
					"col": col + 1,
					"rule": r["id"],
					"severity": r["severity"],
					"snippet": line.strip_edges().substr(0, 120),
					"match": m.get_string(0),
					"old": r["old"],
					"fix": r["new"],
					"note": r["note"],
					"url": r["url"],
				})
	return findings


func scan_file(path: String) -> Array:
	var text := _read_file(path)
	if text.is_empty():
		return []
	return scan_text(text, path)


## Every scannable file under `root`, skipping hidden dirs and `addons/`
## (the same exclusions the command-line scanner uses).
func collect_files(root: String = "res://") -> Array:
	var out: Array = []
	var stack: Array = [root]
	while not stack.is_empty():
		var dir_path: String = stack.pop_back()
		var dir := DirAccess.open(dir_path)
		if dir == null:
			continue
		dir.list_dir_begin()
		var dirs: Array = []
		var files: Array = []
		var name := dir.get_next()
		while name != "":
			if not name.begins_with("."):
				var full := dir_path.path_join(name)
				if dir.current_is_dir():
					if name != "addons":
						dirs.append(full)
				elif name.get_extension().to_lower() in SCAN_EXT:
					files.append(full)
			name = dir.get_next()
		dir.list_dir_end()
		files.sort()
		out.append_array(files)
		dirs.sort()
		dirs.reverse()
		stack.append_array(dirs)
	return out


func scan_project(root: String = "res://") -> Array:
	var findings: Array = []
	for f in collect_files(root):
		findings.append_array(scan_file(f))
	return findings


func format_text(findings: Array) -> String:
	var lines: Array = []
	for f in findings:
		lines.append("%s:%d:%d: [%s] %s: %s" % [f["file"], f["line"], f["col"], f["severity"], f["rule"], f["snippet"]])
		var fix: String = ("    fix: %s -> %s" % [f["old"], f["fix"]]) if not str(f["old"]).is_empty() else ("    fix: %s" % f["fix"])
		if not str(f["note"]).is_empty():
			fix += "  (%s)" % f["note"]
		lines.append(fix)
		if not str(f["url"]).is_empty():
			lines.append("    see: %s" % f["url"])
	return "\n".join(lines)


func _read_file(path: String) -> String:
	var fa := FileAccess.open(path, FileAccess.READ)
	if fa == null:
		return ""
	var text := fa.get_as_text()
	fa.close()
	return text
