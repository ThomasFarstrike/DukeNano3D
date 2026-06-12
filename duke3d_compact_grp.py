#!/usr/bin/env python3
import argparse
import csv
import io
import os
from pathlib import Path
import shutil
import re
import struct
import subprocess
import sys
from collections import defaultdict

def run(cmd, cwd, check=True):
    print(f"[run] {cmd} (cwd={cwd})")
    subprocess.run(cmd, cwd=cwd, check=check)

def find_tool(script_dir: Path, tool_name: str) -> Path:
    # Search project-local tool locations first so compact.sh keeps working
    # after repository reshuffles.
    search_dirs = [
        script_dir,
        script_dir / "eduke32-for-DukeNano3D",
    ]

    for base_dir in search_dirs:
        candidate = base_dir / tool_name
        if candidate.exists() and os.access(candidate, os.X_OK):
            return candidate

    which = shutil.which(tool_name)
    if which:
        return Path(which)

    searched = ", ".join(str(p) for p in search_dirs)
    raise FileNotFoundError(
        f"Required tool '{tool_name}' not found in local dirs ({searched}) or PATH"
    )

def collect_files(temp_dir: Path, patterns):
    files = []
    for pattern in patterns:
        files.extend(sorted(temp_dir.glob(pattern)))
    return files

def get_tile_raw_size(arttool: Path, cwd: Path, tile_num: int):
    proc = subprocess.run(
        [str(arttool), "info", str(tile_num)],
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
    )
    output = (proc.stdout or "") + "\n" + (proc.stderr or "")
    match = re.search(rf"Tile\s+{tile_num}:\s+(\d+)x(\d+)", output)
    if not match:
        return None
    width = int(match.group(1))
    height = int(match.group(2))
    return width * height


def get_tile_anim_info(arttool: Path, cwd: Path, tile_num: int):
    proc = subprocess.run(
        [str(arttool), "info", str(tile_num)],
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
    )
    output = (proc.stdout or "") + "\n" + (proc.stderr or "")

    match_type = re.search(r"AnimType:\s*(\d+)", output)
    match_frames = re.search(r"AnimFrames:\s*(\d+)", output)
    match_speed = re.search(r"AnimSpeed:\s*(\d+)", output)

    anim_type = int(match_type.group(1)) if match_type else 0
    anim_frames = int(match_frames.group(1)) if match_frames else 0
    anim_speed = int(match_speed.group(1)) if match_speed else 0

    if anim_frames <= 0 or anim_type == 0:
        first_tile = tile_num
        last_tile = tile_num
    elif anim_type == 3:  # PICANM_ANIMTYPE_BACK
        first_tile = tile_num - anim_frames
        last_tile = tile_num
    else:
        # PICANM_ANIMTYPE_OSC / PICANM_ANIMTYPE_FWD
        first_tile = tile_num
        last_tile = tile_num + anim_frames

    return {
        "type": anim_type,
        "frames": anim_frames,
        "speed": anim_speed,
        "first": first_tile,
        "last": last_tile,
    }


def get_tile_anim_range(arttool: Path, cwd: Path, tile_num: int):
    info = get_tile_anim_info(arttool, cwd, tile_num)
    return info["first"], info["last"]


def _decode_art_offset(value: int) -> int:
    # ART stores offsets as signed int8. Some arttool builds print those
    # bytes as unsigned 0..255 in "info" output, so convert if needed.
    if value > 127:
        return value - 256
    return value


def get_tile_offsets(arttool: Path, cwd: Path, tile_num: int):
    proc = subprocess.run(
        [str(arttool), "info", str(tile_num)],
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
    )
    output = (proc.stdout or "") + "\n" + (proc.stderr or "")
    match = re.search(r"Xofs:\s*(-?\d+),\s*Yofs:\s*(-?\d+)", output)
    if not match:
        return 0, 0

    raw_x = int(match.group(1))
    raw_y = int(match.group(2))
    return _decode_art_offset(raw_x), _decode_art_offset(raw_y)


def _collect_available_tile_numbers(cwd: Path):
    tile_numbers = set()

    for art_file in sorted(cwd.glob("tiles*.art")):
        idx = tilefile_index_from_name(art_file.name)
        if idx is None:
            continue
        start = idx * 256
        tile_numbers.update(range(start, start + 256))

    for art_file in sorted(cwd.glob("TILES*.ART")):
        idx = tilefile_index_from_name(art_file.name)
        if idx is None:
            continue
        start = idx * 256
        tile_numbers.update(range(start, start + 256))

    return tile_numbers


def expand_required_tiles_with_animation_frames(arttool: Path, cwd: Path, required_tiles):
    expanded = set(required_tiles)
    if not required_tiles:
        return expanded

    available_tiles = _collect_available_tile_numbers(cwd)
    if not available_tiles:
        return expanded

    parent = {tile: tile for tile in available_tiles}

    def find(tile):
        while parent[tile] != tile:
            parent[tile] = parent[parent[tile]]
            tile = parent[tile]
        return tile

    def union(a, b):
        ra = find(a)
        rb = find(b)
        if ra != rb:
            parent[rb] = ra

    tile_set = available_tiles
    for tile in sorted(tile_set):
        anim_info = get_tile_anim_info(arttool, cwd, tile)
        if anim_info["frames"] <= 0 or anim_info["type"] <= 0:
            continue

        first_tile = min(anim_info["first"], anim_info["last"])
        last_tile = max(anim_info["first"], anim_info["last"])

        for anim_tile in range(first_tile, last_tile + 1):
            if anim_tile in tile_set:
                union(tile, anim_tile)

    components = defaultdict(set)
    for tile in tile_set:
        components[find(tile)].add(tile)

    for tile in list(required_tiles):
        if tile in tile_set:
            expanded.update(components[find(tile)])
            continue

        # Fallback when a required tile lies outside discovered ART ranges.
        first_tile, last_tile = get_tile_anim_range(arttool, cwd, tile)
        if first_tile > last_tile:
            first_tile, last_tile = last_tile, first_tile
        for anim_tile in range(first_tile, last_tile + 1):
            if anim_tile >= 0:
                expanded.add(anim_tile)

    return expanded


def parse_tilefiles_arg(value: str):
    parts = [p.strip() for p in value.split(",") if p.strip()]
    if not parts:
        raise argparse.ArgumentTypeError("Expected comma-separated tile file indices, e.g. 0,1,2")

    indices = []
    for part in parts:
        if not part.isdigit():
            raise argparse.ArgumentTypeError(
                f"Invalid tile file index '{part}'. Expected non-negative integers like 0,1,2"
            )
        indices.append(int(part))

    return sorted(set(indices))


def parse_tile_numbers_arg(value: str):
    parts = [p.strip() for p in value.split(",") if p.strip()]
    if not parts:
        raise argparse.ArgumentTypeError("Expected comma-separated tile numbers, e.g. 1289,1290,407")

    numbers = []
    for part in parts:
        if not part.isdigit():
            raise argparse.ArgumentTypeError(
                f"Invalid tile number '{part}'. Expected non-negative integers like 1289,1290"
            )
        numbers.append(int(part))

    return sorted(set(numbers))


def parse_map_arg(value: str):
    parts = [Path(p.strip()).name for p in value.split(",") if p.strip()]
    if not parts:
        raise argparse.ArgumentTypeError(
            "Expected comma-separated map filenames, e.g. E1L1.MAP,E1L2.MAP"
        )
    return parts


def find_file_case_insensitive(base_dir: Path, name: str):
    normalized = name.lower()

    direct = base_dir / name
    if direct.exists() and direct.is_file():
        return direct

    for candidate in base_dir.iterdir():
        if candidate.is_file() and candidate.name.lower() == normalized:
            return candidate

    return None


def parse_used_tiles_from_mapinfo_output(output: str):
    section_match = re.search(r"=== COMBINED TILE USAGE ===(.*?)(?:\n=== |\Z)", output, flags=re.DOTALL)
    section = section_match.group(1) if section_match else output

    lines = section.splitlines()
    used_tiles = set()
    in_tiles = False

    for line in lines:
        if not in_tiles:
            if re.search(r"used_tiles\s*\(\d+\)\s*:", line):
                in_tiles = True
                _, _, tail = line.partition(":")
                used_tiles.update(int(v) for v in re.findall(r"\b\d+\b", tail))
            continue

        if line.strip() == "":
            continue

        # End when indentation style changes (next label/section).
        if not line.startswith(" "):
            break

        used_tiles.update(int(v) for v in re.findall(r"\b\d+\b", line))

    return used_tiles


def tilefile_index_from_name(name: str):
    match = re.match(r"^tiles(\d{3})\.art$", name, flags=re.IGNORECASE)
    if not match:
        return None
    return int(match.group(1))


def parse_includeart_arg(value: str):
    name = Path(value).name
    if not re.match(r"^tiles\d{3}\.art$", name, flags=re.IGNORECASE):
        raise argparse.ArgumentTypeError(
            f"Invalid ART filename '{value}'. Expected TILESNNN.ART, e.g. TILES012.ART"
        )
    return name.lower()


def parse_excludefiles_arg(value: str):
    parts = [Path(p.strip()).name for p in value.split(",") if p.strip()]
    if not parts:
        raise argparse.ArgumentTypeError(
            "Expected comma-separated filenames, e.g. TILES3280.PNG,TILES3281.PNG"
        )

    normalized = set()
    for part in parts:
        name = part.lower()
        stem, suffix = os.path.splitext(name)

        if suffix == ".pcx":
            normalized.add(f"{stem}.png")
            continue

        if suffix == ".voc":
            normalized.add(name)
            normalized.add(f"{stem}.wav")
            continue

        # Includes direct .wav excludes as-is.
        normalized.add(name)

    return sorted(normalized)


def parse_includefiles_arg(value: str):
    parts = [Path(p.strip()).name for p in value.split(",") if p.strip()]
    if not parts:
        raise argparse.ArgumentTypeError(
            "Expected comma-separated filenames, e.g. GAME.CON,LOOKUP.DAT"
        )

    return sorted({part.lower() for part in parts})


def strip_con_line_comment(line: str):
    return line.split("//", 1)[0].rstrip("\n")


def normalize_con_filename_token(token: str):
    token = token.strip().strip("\"'")
    token = token.rstrip(",;")
    return Path(token).name.lower()


def looks_like_mid_token(token: str):
    return normalize_con_filename_token(token).endswith(".mid")


def determine_required_mid_files_from_user_con(temp_dir: Path, selected_map_name: str, nomenusongs: bool = False):
    user_con = find_file_case_insensitive(temp_dir, "USER.CON")
    if user_con is None:
        print("[warn] USER.CON not found; keeping all music files")
        return None

    map_to_slot = {}
    music_by_volume = {}

    current_music_volume = None

    with user_con.open("r", encoding="utf-8", errors="replace") as fh:
        for line_num, raw_line in enumerate(fh, start=1):
            uncommented = strip_con_line_comment(raw_line)
            stripped = uncommented.strip()

            if not stripped:
                continue

            tokens = stripped.split()
            if not tokens:
                continue

            keyword = tokens[0].lower()

            if keyword == "definelevelname":
                current_music_volume = None
                if len(tokens) >= 4 and tokens[1].isdigit() and tokens[2].isdigit():
                    volume = int(tokens[1])
                    level = int(tokens[2])
                    map_name = normalize_con_filename_token(tokens[3])
                    map_to_slot[map_name] = (volume, level)
                else:
                    print(f"[debug] USER.CON:{line_num}: ignored malformed definelevelname: {stripped}")
                continue

            if keyword == "music":
                current_music_volume = None
                if len(tokens) >= 2 and tokens[1].isdigit():
                    current_music_volume = int(tokens[1])
                    track_tokens = [normalize_con_filename_token(t) for t in tokens[2:] if looks_like_mid_token(t)]
                    music_by_volume.setdefault(current_music_volume, []).extend(track_tokens)
                else:
                    print(f"[debug] USER.CON:{line_num}: ignored malformed music line: {stripped}")
                continue

            # Continuation support:
            #  - classic indentation-based continued music lists
            #  - non-indented lines containing only MID tokens after a music line
            if current_music_volume is not None:
                continuation_tokens = [normalize_con_filename_token(t) for t in tokens if looks_like_mid_token(t)]
                if continuation_tokens and (
                    raw_line[:1].isspace()
                    or len(continuation_tokens) == len(tokens)
                ):
                    music_by_volume.setdefault(current_music_volume, []).extend(continuation_tokens)
                    continue

            current_music_volume = None

    required = set() if nomenusongs else set(music_by_volume.get(0, []))

    selected_map_name_norm = normalize_con_filename_token(selected_map_name)
    slot = map_to_slot.get(selected_map_name_norm)

    print(
        f"[debug] USER.CON parse summary: maps={len(map_to_slot)} music_volumes={sorted(music_by_volume.keys())} "
        f"selected_map={selected_map_name_norm}"
    )

    if slot is None:
        sample_maps = sorted(map_to_slot.keys())[:12]
        print(
            f"[warn] Map {selected_map_name_norm} not found in USER.CON definelevelname list; "
            "including only title/end music"
        )
        if sample_maps:
            print(f"[debug] USER.CON map samples: {', '.join(sample_maps)}")
        print(f"[debug] USER.CON title/end tracks: {sorted(required)}")
        return required

    volume, level = slot

    # In USER.CON, definelevelname volumes are usually 0-based while music
    # episode lists are usually 1-based (`music 1 ...` for episode 1). Also,
    # `music 0 ...` is commonly title/end tracks and should not be used for
    # episode level mapping when a shifted episode list exists.
    direct_tracks = music_by_volume.get(volume) or []
    shifted_volume = volume + 1
    shifted_tracks = music_by_volume.get(shifted_volume) or []

    if shifted_tracks:
        volume_tracks = shifted_tracks
        resolved_music_volume = shifted_volume
    else:
        volume_tracks = direct_tracks
        resolved_music_volume = volume

    print(
        f"[debug] USER.CON music candidates for map volume {volume}: "
        f"direct(volume={volume}, tracks={len(direct_tracks)}) "
        f"shifted(volume={shifted_volume}, tracks={len(shifted_tracks)})"
    )

    print(
        f"[debug] USER.CON slot for {selected_map_name_norm}: definelevelname volume={volume} level={level} "
        f"resolved_music_volume={resolved_music_volume} track_count={len(volume_tracks or [])}"
    )

    if level < len(volume_tracks or []):
        chosen_track = volume_tracks[level]
        required.add(chosen_track)
        print(f"[debug] USER.CON selected map track: {chosen_track}")
    else:
        print(
            f"[warn] No music track for definelevelname volume {volume} "
            f"(resolved music volume {resolved_music_volume}) level {level} in USER.CON; "
            "including only title/end music"
        )

    print(f"[debug] USER.CON required MID files: {sorted(required)}")
    return required


def normalize_case_insensitive_options(argv, option_names):
    normalized = []
    lower_opts = {opt.lower(): opt for opt in option_names}

    for arg in argv:
        if not arg.startswith("--"):
            normalized.append(arg)
            continue

        key, sep, value = arg.partition("=")
        canonical = lower_opts.get(key.lower())
        if canonical:
            normalized.append(f"{canonical}{sep}{value}" if sep else canonical)
        else:
            normalized.append(arg)

    return normalized


def _read_csv_rows(csv_path: Path):
    if not csv_path.exists():
        raise FileNotFoundError(f"Required model CSV not found: {csv_path}")

    raw_lines = csv_path.read_text(encoding="utf-8", errors="replace").splitlines()
    filtered = [line for line in raw_lines if line.strip() and not line.lstrip().startswith("#")]
    if not filtered:
        return []

    reader = csv.DictReader(io.StringIO("\n".join(filtered)))
    return list(reader)


def _resolve_single_tile_token(token: str, defines: dict):
    value = token.strip()
    if not value:
        return None

    if re.match(r"^-?\d+$", value):
        return int(value)

    name_offset_match = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)([+-]\d+)?$", value)
    if not name_offset_match:
        return None

    base_name = name_offset_match.group(1).lower()
    base_value = defines.get(base_name)
    if base_value is None:
        return None

    offset_token = name_offset_match.group(2)
    if not offset_token:
        return base_value

    return base_value + int(offset_token)


def _resolve_tile_token_to_set(token: str, defines: dict):
    value = token.strip()
    if not value:
        return set()

    if ".." in value:
        left, right = value.split("..", 1)
        start = _resolve_single_tile_token(left, defines)
        end = _resolve_single_tile_token(right, defines)
        if start is None or end is None:
            return set()
        if end < start:
            start, end = end, start
        return set(range(start, end + 1))

    if re.match(r"^-?\d+\s*-\s*-?\d+$", value):
        left, right = value.split("-", 1)
        start = _resolve_single_tile_token(left, defines)
        end = _resolve_single_tile_token(right, defines)
        if start is None or end is None:
            return set()
        if end < start:
            start, end = end, start
        return set(range(start, end + 1))

    resolved = _resolve_single_tile_token(value, defines)
    if resolved is None:
        return set()
    return {resolved}


def _parse_tile_token_list(value: str, defines: dict):
    tiles = set()
    for token in (value or "").split("|"):
        tiles.update(_resolve_tile_token_to_set(token, defines))
    return {tile for tile in tiles if tile >= 0}


def _tile_model_dir(script_dir: Path):
    return script_dir / "data" / "tile_model"


def load_tile_runtime_rules_from_csv(defines: dict, script_dir: Path):
    model_dir = _tile_model_dir(script_dir)

    trigger_span_rules = []
    for row in _read_csv_rows(model_dir / "tile_spans.csv"):
        category = (row.get("category") or "").strip().lower()
        trigger_tokens = (row.get("trigger") or "").strip()
        length_token = (row.get("length") or "").strip()
        if not category or not trigger_tokens or not length_token:
            continue
        if category not in {"sprite_precache", "spawn_span"}:
            continue

        try:
            length = int(length_token)
        except ValueError:
            continue
        if length <= 0:
            continue

        triggers = _parse_tile_token_list(trigger_tokens, defines)
        if not triggers:
            continue

        trigger_span_rules.append(
            {
                "category": category,
                "name": (row.get("notes") or "").strip(),
                "triggers": triggers,
                "length": length,
            }
        )

    transition_rules = []
    for row in _read_csv_rows(model_dir / "tile_transitions.csv"):
        category = (row.get("category") or "").strip().lower()
        trigger_tokens = (row.get("trigger") or "").strip()
        include_tokens = (row.get("include") or "").strip()
        if not category or not trigger_tokens or not include_tokens:
            continue

        triggers = _parse_tile_token_list(trigger_tokens, defines)
        includes = _parse_tile_token_list(include_tokens, defines)
        if not triggers or not includes:
            continue

        transition_rules.append(
            {
                "category": category,
                "name": (row.get("notes") or "").strip(),
                "triggers": triggers,
                "includes": includes,
            }
        )

    return trigger_span_rules, transition_rules


def load_tile_baselines_from_csv(defines: dict, script_dir: Path):
    model_dir = _tile_model_dir(script_dir)
    baselines = defaultdict(set)

    for row in _read_csv_rows(model_dir / "tile_baselines.csv"):
        category = (row.get("category") or "").strip().lower()
        item_tokens = (row.get("item") or "").strip()
        if not category or not item_tokens:
            continue
        baselines[category].update(_parse_tile_token_list(item_tokens, defines))

    return baselines


def build_runtime_essentials_allowlist(temp_dir: Path, script_dir: Path):
    defines = build_tile_defines_from_cons(temp_dir)
    baselines = load_tile_baselines_from_csv(defines, script_dir)
    return set(baselines.get("runtime_essential", set()))


def build_ultra_minimal_menu_allowlist(temp_dir: Path, script_dir: Path):
    defines = build_tile_defines_from_cons(temp_dir)
    baselines = load_tile_baselines_from_csv(defines, script_dir)
    return set(baselines.get("menu_ultra", set()))


def expand_required_tiles_with_enemy_runtime_ranges(required_tiles, temp_dir: Path, script_dir: Path):
    """Expand map-derived tiles with enemy runtime spans loaded from CSV model files."""
    expanded = set(required_tiles)
    if not expanded:
        return expanded

    defines = build_tile_defines_from_cons(temp_dir)
    _trigger_span_rules, transition_rules = load_tile_runtime_rules_from_csv(defines, script_dir)

    for rule in transition_rules:
        if rule["category"] != "enemy_runtime":
            continue
        if expanded & rule["triggers"]:
            expanded.update(rule["includes"])

    return expanded


def expand_required_tiles_with_sprite_precache_ranges(required_tiles, temp_dir: Path, script_dir: Path):
    """Apply sprite runtime rules loaded from CSV model files."""
    expanded = set(required_tiles)
    if not expanded:
        return expanded

    defines = build_tile_defines_from_cons(temp_dir)
    trigger_span_rules, transition_rules = load_tile_runtime_rules_from_csv(defines, script_dir)

    for rule in trigger_span_rules:
        matching_triggers = expanded & rule["triggers"]
        if not matching_triggers:
            continue
        length = rule["length"]
        for trigger in matching_triggers:
            expanded.update(range(trigger, trigger + length))

    for rule in transition_rules:
        if expanded & rule["triggers"]:
            expanded.update(rule["includes"])

    return expanded

def parse_tile_id_from_token(token: str, defines: dict):
    if re.match(r"^-?\d+$", token):
        return int(token)
    return defines.get(token.lower())


def parse_sound_id_from_token(token: str, defines: dict):
    return parse_tile_id_from_token(token, defines)



def parse_con_defines_and_sounds(
    con_path: Path,
    defines: dict,
    voc_to_sound_ids: dict,
    sound_fields_by_id: dict,
    sound_id_to_files: dict,
    unresolved_sound_tokens: set,
):
    with con_path.open("r", encoding="utf-8", errors="replace") as fh:
        for raw_line in fh:
            line = strip_con_line_comment(raw_line).strip()
            if not line:
                continue

            # Examples:
            #   define PISTOL_FIRE 3
            #   sound PISTOL_FIRE PISTOL.VOC ...
            #   definesound INSERT_CLIP clipin.voc 0 0 0 0 0
            tokens = line.split()
            if not tokens:
                continue

            keyword = tokens[0].lower()
            if keyword == "define" and len(tokens) >= 3:
                name = tokens[1].lower()
                value = tokens[2]
                if re.match(r"^-?\d+$", value):
                    defines[name] = int(value)
                continue

            if keyword in {"sound", "definesound"} and len(tokens) >= 3:
                sound_token = tokens[1]
                sound_file = Path(tokens[2]).name
                suffix = Path(sound_file).suffix.lower()
                if suffix not in {".voc", ".wav"}:
                    continue

                sound_id = parse_sound_id_from_token(sound_token, defines)
                if sound_id is None:
                    unresolved_sound_tokens.add(sound_token)
                    continue

                sound_file_lc = sound_file.lower()
                voc_to_sound_ids.setdefault(sound_file_lc, set()).add(sound_id)
                sound_id_to_files.setdefault(sound_id, set()).add(sound_file_lc)

                # USER.CON definesound format:
                # definesound <value> <filename> <pitch_lower> <pitch_upper> <priority> <type> <distance>
                if keyword == "definesound" and len(tokens) >= 8:
                    sound_fields_by_id[sound_id] = {
                        "minpitch": tokens[3],
                        "maxpitch": tokens[4],
                        "priority": tokens[5],
                        "type": tokens[6],
                        "distance": tokens[7],
                    }



def build_sound_maps_from_cons(temp_dir: Path):
    defines = {}
    voc_to_sound_ids = {}
    sound_fields_by_id = {}
    sound_id_to_files = {}
    unresolved_sound_tokens = set()

    # Parse all CON files in deterministic order. This covers common DUKE3D
    # layouts where sound tokens are defined in one CON and used in another.
    con_files = sorted(
        [p for p in temp_dir.iterdir() if p.is_file() and p.suffix.lower() == ".con"],
        key=lambda p: p.name.lower(),
    )
    for con_file in con_files:
        parse_con_defines_and_sounds(
            con_file,
            defines,
            voc_to_sound_ids,
            sound_fields_by_id,
            sound_id_to_files,
            unresolved_sound_tokens,
        )

    return voc_to_sound_ids, sound_fields_by_id, sound_id_to_files, defines, unresolved_sound_tokens



def parse_con_defines_and_precache_ranges(con_path: Path, defines: dict, precache_ranges: dict):
    with con_path.open("r", encoding="utf-8", errors="replace") as fh:
        for raw_line in fh:
            line = strip_con_line_comment(raw_line).strip()
            if not line:
                continue

            tokens = line.split()
            if not tokens:
                continue

            keyword = tokens[0].lower()
            if keyword == "define" and len(tokens) >= 3:
                name = tokens[1].lower()
                value = tokens[2]
                if re.match(r"^-?\d+$", value):
                    defines[name] = int(value)
                continue

            # CON syntax: precache <startTile> <endTile> <cacheFlag>
            if keyword == "precache" and len(tokens) >= 3:
                start_tile = parse_tile_id_from_token(tokens[1], defines)
                end_tile = parse_tile_id_from_token(tokens[2], defines)
                if start_tile is None or end_tile is None:
                    continue
                if start_tile < 0 or end_tile < 0:
                    continue
                if end_tile < start_tile:
                    start_tile, end_tile = end_tile, start_tile

                previous_end = precache_ranges.get(start_tile, start_tile)
                precache_ranges[start_tile] = max(previous_end, end_tile)


def build_precache_ranges_from_cons(temp_dir: Path):
    defines = {}
    precache_ranges = {}

    con_files = sorted(
        [p for p in temp_dir.iterdir() if p.is_file() and p.suffix.lower() == ".con"],
        key=lambda p: p.name.lower(),
    )
    for con_file in con_files:
        parse_con_defines_and_precache_ranges(con_file, defines, precache_ranges)

    return precache_ranges



def expand_required_tiles_with_con_precache_ranges(required_tiles, precache_ranges):
    if not required_tiles or not precache_ranges:
        return set(required_tiles)

    expanded = set(required_tiles)
    for tile in list(required_tiles):
        end_tile = precache_ranges.get(tile)
        if end_tile is None:
            continue
        expanded.update(range(tile, end_tile + 1))

    return expanded


def build_tile_defines_from_cons(temp_dir: Path):
    defines = {}

    con_files = sorted(
        [p for p in temp_dir.iterdir() if p.is_file() and p.suffix.lower() == ".con"],
        key=lambda p: p.name.lower(),
    )

    for con_file in con_files:
        with con_file.open("r", encoding="utf-8", errors="replace") as fh:
            for raw_line in fh:
                line = strip_con_line_comment(raw_line).strip()
                if not line:
                    continue

                tokens = line.split()
                if len(tokens) < 3 or tokens[0].lower() != "define":
                    continue

                name = tokens[1].lower()
                value_token = tokens[2]

                if re.match(r"^-?\d+$", value_token):
                    defines[name] = int(value_token)
                    continue

                resolved = defines.get(value_token.lower())
                if resolved is not None:
                    defines[name] = resolved

    return defines


def build_runtime_spawn_tile_dependencies(temp_dir: Path):
    game_con = find_file_case_insensitive(temp_dir, "GAME.CON")
    if game_con is None:
        return {}

    defines = build_tile_defines_from_cons(temp_dir)

    state_spawns = defaultdict(set)
    state_calls = defaultdict(set)
    actor_spawns = defaultdict(set)
    actor_state_calls = defaultdict(set)
    actor_actor_calls = defaultdict(set)

    current_state = None
    current_actor = None

    def add_spawn_token(token: str):
        tile_id = defines.get(token.lower())
        if tile_id is None or tile_id < 0:
            return
        if current_state is not None:
            state_spawns[current_state].add(tile_id)
        elif current_actor is not None:
            actor_spawns[current_actor].add(tile_id)

    with game_con.open("r", encoding="utf-8", errors="replace") as fh:
        for raw_line in fh:
            line = strip_con_line_comment(raw_line).strip()
            if not line:
                continue

            tokens = line.split()
            if not tokens:
                continue

            keyword = tokens[0].lower()
            if keyword == "state" and len(tokens) >= 2 and current_state is None and current_actor is None:
                current_state = tokens[1].lower()
                current_actor = None
            elif keyword == "actor" and len(tokens) >= 2 and current_state is None and current_actor is None:
                current_actor = tokens[1].lower()
                current_state = None
            elif keyword == "useractor" and len(tokens) >= 3 and current_state is None and current_actor is None:
                current_actor = tokens[2].lower()
                current_state = None
            elif keyword == "enda":
                current_actor = None
            elif keyword == "ends":
                current_state = None

            for match in re.finditer(r"\b(?:spawn|debris|guts)\s+([A-Za-z_][A-Za-z0-9_]*)", line, flags=re.IGNORECASE):
                add_spawn_token(match.group(1))

            if current_state is not None:
                for match in re.finditer(r"\bstate\s+([A-Za-z_][A-Za-z0-9_]*)", line, flags=re.IGNORECASE):
                    state_calls[current_state].add(match.group(1).lower())
            elif current_actor is not None:
                for match in re.finditer(r"\bstate\s+([A-Za-z_][A-Za-z0-9_]*)", line, flags=re.IGNORECASE):
                    actor_state_calls[current_actor].add(match.group(1).lower())
                for match in re.finditer(r"\bcactor\s+([A-Za-z_][A-Za-z0-9_]*)", line, flags=re.IGNORECASE):
                    actor_actor_calls[current_actor].add(match.group(1).lower())

    state_cache = {}

    def collect_state_spawns(state_name: str, visiting: set):
        cached = state_cache.get(state_name)
        if cached is not None:
            return cached

        if state_name in visiting:
            return set()

        visiting.add(state_name)
        result = set(state_spawns.get(state_name, set()))
        for next_state in state_calls.get(state_name, set()):
            result.update(collect_state_spawns(next_state, visiting))
        visiting.remove(state_name)

        state_cache[state_name] = result
        return result

    actor_cache = {}

    def collect_actor_spawns(actor_name: str, visiting: set):
        cached = actor_cache.get(actor_name)
        if cached is not None:
            return cached

        if actor_name in visiting:
            return set()

        visiting.add(actor_name)
        result = set(actor_spawns.get(actor_name, set()))
        for state_name in actor_state_calls.get(actor_name, set()):
            result.update(collect_state_spawns(state_name, set()))
        for next_actor in actor_actor_calls.get(actor_name, set()):
            result.update(collect_actor_spawns(next_actor, visiting))
        visiting.remove(actor_name)

        actor_cache[actor_name] = result
        return result

    dependencies = {}
    actor_names = set(actor_spawns.keys()) | set(actor_state_calls.keys()) | set(actor_actor_calls.keys())
    for actor_name in actor_names:
        trigger_tile = defines.get(actor_name)
        if trigger_tile is None or trigger_tile < 0:
            continue
        spawned_tiles = collect_actor_spawns(actor_name, set())
        if spawned_tiles:
            dependencies[trigger_tile] = spawned_tiles

    return dependencies


def expand_required_tiles_with_con_spawn_dependencies(required_tiles, temp_dir: Path, script_dir: Path):
    if not required_tiles:
        return set(required_tiles)

    defines = build_tile_defines_from_cons(temp_dir)
    trigger_span_rules, _transition_rules = load_tile_runtime_rules_from_csv(defines, script_dir)
    dependencies = build_runtime_spawn_tile_dependencies(temp_dir)
    if not dependencies:
        return set(required_tiles)

    spawned_tiles = set()
    for tile in list(required_tiles):
        spawned = dependencies.get(tile)
        if spawned:
            spawned_tiles.update(spawned)

    for rule in trigger_span_rules:
        if rule["category"] != "spawn_span":
            continue
        if spawned_tiles & rule["triggers"]:
            for trigger in rule["triggers"]:
                if trigger in spawned_tiles:
                    spawned_tiles.update(range(trigger, trigger + rule["length"]))

    expanded = set(required_tiles)
    expanded.update(spawned_tiles)

    return expanded


def _format_tile_with_name(tile: int, names_by_tile: dict):
    names = names_by_tile.get(tile)
    if names:
        return f"{tile}({names[0]})"
    return str(tile)


def print_runtime_spawn_dependency_report(temp_dir: Path):
    defines = build_tile_defines_from_cons(temp_dir)
    dependencies = build_runtime_spawn_tile_dependencies(temp_dir)

    names_by_tile = defaultdict(list)
    for name, tile in defines.items():
        if tile >= 0:
            names_by_tile[tile].append(name.upper())
    for tile in names_by_tile:
        names_by_tile[tile].sort()

    print(f"[debug] runtime spawn dependencies: {len(dependencies)} trigger tiles")
    for trigger_tile in sorted(dependencies):
        spawned_tiles = sorted(dependencies[trigger_tile])
        spawned_label = ", ".join(_format_tile_with_name(t, names_by_tile) for t in spawned_tiles)
        print(
            f"[debug]   trigger {_format_tile_with_name(trigger_tile, names_by_tile)} "
            f"-> {spawned_label}"
        )


def dump_runtime_spawn_dependency_report(temp_dir: Path, output_path: Path):
    defines = build_tile_defines_from_cons(temp_dir)
    dependencies = build_runtime_spawn_tile_dependencies(temp_dir)

    names_by_tile = defaultdict(list)
    for name, tile in defines.items():
        if tile >= 0:
            names_by_tile[tile].append(name.upper())
    for tile in names_by_tile:
        names_by_tile[tile].sort()

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as fh:
        fh.write(f"trigger_count={len(dependencies)}\n")
        for trigger_tile in sorted(dependencies):
            trigger_label = _format_tile_with_name(trigger_tile, names_by_tile)
            spawned_tiles = sorted(dependencies[trigger_tile])
            spawned_label = ", ".join(_format_tile_with_name(t, names_by_tile) for t in spawned_tiles)
            fh.write(f"{trigger_label} -> {spawned_label}\n")


def dump_required_tiles(required_tiles, output_path: Path):
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as fh:
        for tile in sorted(required_tiles or []):
            fh.write(f"{tile}\n")


def _sound_model_dir(script_dir: Path):
    return script_dir / "data" / "sound_model"


def _parse_sound_token_list(value: str, defines: dict):
    sounds = set()
    for token in (value or "").split("|"):
        sounds.update(_resolve_tile_token_to_set(token, defines))
    return {sound_id for sound_id in sounds if sound_id >= 0}


def load_sound_model_from_csv(defines: dict, script_dir: Path):
    model_dir = _sound_model_dir(script_dir)

    baselines = defaultdict(set)
    for row in _read_csv_rows(model_dir / "sound_baselines.csv"):
        category = (row.get("category") or "").strip().lower()
        item_tokens = (row.get("item") or "").strip()
        if not category or not item_tokens:
            continue
        baselines[category].update(_parse_sound_token_list(item_tokens, defines))

    transition_rules = []
    for row in _read_csv_rows(model_dir / "sound_transitions.csv"):
        category = (row.get("category") or "").strip().lower()
        trigger_type = (row.get("trigger_type") or "").strip().lower()
        trigger_token = (row.get("trigger") or "").strip()
        include_token = (row.get("include") or "").strip()
        if not category or not trigger_type or not include_token:
            continue

        trigger_values = None
        if trigger_type != "always":
            if trigger_token and trigger_token != "*":
                trigger_values = _parse_sound_token_list(trigger_token, defines)
                if not trigger_values:
                    continue
            elif trigger_token != "*":
                continue

        include_mode = "static"
        include_values = set()
        include_token_lc = include_token.lower()
        if include_token_lc == "@trigger_value":
            include_mode = "trigger_value"
        elif include_token_lc == "@trigger_value_minus_10000":
            include_mode = "trigger_value_minus_10000"
        else:
            include_values = _parse_sound_token_list(include_token, defines)
            if not include_values:
                continue

        transition_rules.append(
            {
                "category": category,
                "trigger_type": trigger_type,
                "trigger_values": trigger_values,
                "include_mode": include_mode,
                "include_values": include_values,
                "name": (row.get("notes") or "").strip(),
            }
        )

    return baselines, transition_rules


def parse_map_runtime_context(map_path: Path):
    context = {
        "sprite_picnums": set(),
        "sprite_lotags": set(),
        "sprite_hitags": set(),
        "wall_lotags": set(),
        "wall_hitags": set(),
        "sector_lotags": set(),
        "sector_hitags": set(),
    }

    with map_path.open("rb") as fh:
        header = fh.read(20)
        if len(header) != 20:
            return context

        version = struct.unpack("<I", header[:4])[0]
        if version < 7 or version > 9:
            return context

        numsectors_raw = fh.read(2)
        if len(numsectors_raw) != 2:
            return context
        numsectors = struct.unpack("<H", numsectors_raw)[0]

        for _ in range(numsectors):
            sector = fh.read(40)
            if len(sector) != 40:
                return context
            lotag = struct.unpack_from("<h", sector, 34)[0]
            hitag = struct.unpack_from("<h", sector, 36)[0]
            context["sector_lotags"].add(lotag)
            context["sector_hitags"].add(hitag)

        numwalls_raw = fh.read(2)
        if len(numwalls_raw) != 2:
            return context
        numwalls = struct.unpack("<H", numwalls_raw)[0]

        for _ in range(numwalls):
            wall = fh.read(32)
            if len(wall) != 32:
                return context
            lotag = struct.unpack_from("<h", wall, 28)[0]
            hitag = struct.unpack_from("<h", wall, 30)[0]
            context["wall_lotags"].add(lotag)
            context["wall_hitags"].add(hitag)

        numsprites_raw = fh.read(2)
        if len(numsprites_raw) != 2:
            return context
        numsprites = struct.unpack("<H", numsprites_raw)[0]

        for _ in range(numsprites):
            sprite = fh.read(44)
            if len(sprite) != 44:
                return context
            picnum = struct.unpack_from("<h", sprite, 14)[0]
            lotag = struct.unpack_from("<h", sprite, 40)[0]
            hitag = struct.unpack_from("<h", sprite, 42)[0]
            context["sprite_picnums"].add(picnum)
            context["sprite_lotags"].add(lotag)
            context["sprite_hitags"].add(hitag)

    return context


def build_con_runtime_sound_dependencies(temp_dir: Path, defines: dict):
    state_sounds = defaultdict(set)
    state_calls = defaultdict(set)
    actor_sounds = defaultdict(set)
    actor_state_calls = defaultdict(set)
    actor_actor_calls = defaultdict(set)
    global_sounds = set()
    unresolved_sound_tokens = set()

    current_state = None
    current_actor = None

    con_files = sorted(
        [p for p in temp_dir.iterdir() if p.is_file() and p.suffix.lower() == ".con"],
        key=lambda p: p.name.lower(),
    )

    def add_sound_token(token: str):
        sound_id = parse_sound_id_from_token(token, defines)
        if sound_id is None or sound_id < 0:
            unresolved_sound_tokens.add(token)
            return
        if current_state is not None:
            state_sounds[current_state].add(sound_id)
        elif current_actor is not None:
            actor_sounds[current_actor].add(sound_id)
        else:
            global_sounds.add(sound_id)

    sound_call_re = re.compile(r"\b(?:sound|soundonce|globalsound|spritesound)\s+([A-Za-z_][A-Za-z0-9_]*|-?\d+)", flags=re.IGNORECASE)
    state_call_re = re.compile(r"\bstate\s+([A-Za-z_][A-Za-z0-9_]*)", flags=re.IGNORECASE)
    cactor_call_re = re.compile(r"\bcactor\s+([A-Za-z_][A-Za-z0-9_]*)", flags=re.IGNORECASE)

    for con_file in con_files:
        with con_file.open("r", encoding="utf-8", errors="replace") as fh:
            for raw_line in fh:
                line = strip_con_line_comment(raw_line).strip()
                if not line:
                    continue

                tokens = line.split()
                if not tokens:
                    continue

                keyword = tokens[0].lower()
                if keyword == "state" and len(tokens) >= 2 and current_state is None and current_actor is None:
                    current_state = tokens[1].lower()
                    current_actor = None
                elif keyword == "actor" and len(tokens) >= 2 and current_state is None and current_actor is None:
                    current_actor = tokens[1].lower()
                    current_state = None
                elif keyword == "useractor" and len(tokens) >= 3 and current_state is None and current_actor is None:
                    current_actor = tokens[2].lower()
                    current_state = None
                elif keyword == "enda":
                    current_actor = None
                elif keyword == "ends":
                    current_state = None

                for match in sound_call_re.finditer(line):
                    add_sound_token(match.group(1))

                if current_state is not None:
                    for match in state_call_re.finditer(line):
                        state_calls[current_state].add(match.group(1).lower())
                elif current_actor is not None:
                    for match in state_call_re.finditer(line):
                        actor_state_calls[current_actor].add(match.group(1).lower())
                    for match in cactor_call_re.finditer(line):
                        actor_actor_calls[current_actor].add(match.group(1).lower())

    state_cache = {}

    def collect_state_sounds(state_name: str, visiting: set):
        cached = state_cache.get(state_name)
        if cached is not None:
            return cached

        if state_name in visiting:
            return set()

        visiting.add(state_name)
        result = set(state_sounds.get(state_name, set()))
        for next_state in state_calls.get(state_name, set()):
            result.update(collect_state_sounds(next_state, visiting))
        visiting.remove(state_name)

        state_cache[state_name] = result
        return result

    actor_cache = {}

    def collect_actor_sounds(actor_name: str, visiting: set):
        cached = actor_cache.get(actor_name)
        if cached is not None:
            return cached

        if actor_name in visiting:
            return set()

        visiting.add(actor_name)
        result = set(actor_sounds.get(actor_name, set()))
        for state_name in actor_state_calls.get(actor_name, set()):
            result.update(collect_state_sounds(state_name, set()))
        for next_actor in actor_actor_calls.get(actor_name, set()):
            result.update(collect_actor_sounds(next_actor, visiting))
        visiting.remove(actor_name)

        actor_cache[actor_name] = result
        return result

    dependencies = {}
    actor_names = set(actor_sounds.keys()) | set(actor_state_calls.keys()) | set(actor_actor_calls.keys())
    for actor_name in actor_names:
        trigger_tile = defines.get(actor_name)
        if trigger_tile is None or trigger_tile < 0:
            continue
        actor_sound_ids = collect_actor_sounds(actor_name, set())
        if actor_sound_ids:
            dependencies[trigger_tile] = actor_sound_ids

    return dependencies, global_sounds, unresolved_sound_tokens


def analyze_c_sound_runtime_paths(script_dir: Path):
    src_dir = script_dir / "eduke32-for-DukeNano3D" / "source" / "duke3d" / "src"
    files = [
        "sector.cpp",
        "player.cpp",
        "actors.cpp",
        "game.cpp",
        "screens.cpp",
        "gamedef.cpp",
    ]

    supports_hitag_sound_id = False
    supports_lotag_sound_id = False
    supports_lotag_minus_10000 = False
    static_sound_tokens = set()
    unresolved_expressions = set()

    first_arg_re = re.compile(r"\b(?:A_PlaySound|S_PlaySound|S_PlaySound3D)\s*\(\s*([^,\)]+)")
    simple_symbol_re = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
    simple_int_re = re.compile(r"^-?\d+$")

    for name in files:
        path = src_dir / name
        if not path.exists():
            continue
        with path.open("r", encoding="utf-8", errors="replace") as fh:
            for raw_line in fh:
                line = raw_line.split("//", 1)[0]
                for match in first_arg_re.finditer(line):
                    expr = match.group(1).strip()
                    if not expr:
                        continue

                    expr_lc = expr.lower()
                    if "hitag" in expr_lc:
                        supports_hitag_sound_id = True
                    if "lotag" in expr_lc:
                        supports_lotag_sound_id = True
                    if "lotag" in expr_lc and "10000" in expr_lc and "-" in expr_lc:
                        supports_lotag_minus_10000 = True

                    if simple_symbol_re.match(expr) or simple_int_re.match(expr):
                        static_sound_tokens.add(expr)
                        continue

                    if (
                        "hitag" in expr_lc
                        or "lotag" in expr_lc
                    ):
                        continue

                    unresolved_expressions.add(expr)

    return {
        "supports_hitag_sound_id": supports_hitag_sound_id,
        "supports_lotag_sound_id": supports_lotag_sound_id,
        "supports_lotag_minus_10000": supports_lotag_minus_10000,
        "static_sound_tokens": static_sound_tokens,
        "unresolved_expressions": unresolved_expressions,
    }


def _add_sound_dependency_edges(edges: list, reason: str, sound_ids: set, sound_id_to_files: dict):
    for sound_id in sorted(sound_ids):
        files = sorted(sound_id_to_files.get(sound_id, set()))
        edges.append(
            {
                "reason": reason,
                "sound_id": sound_id,
                "files": files,
            }
        )


def build_required_sound_model(
    temp_dir: Path,
    script_dir: Path,
    selected_map_files,
    required_tiles,
):
    (
        _file_to_sound_ids,
        _sound_fields_by_id,
        sound_id_to_files,
        defines,
        unresolved_sound_tokens_from_defs,
    ) = build_sound_maps_from_cons(temp_dir)

    baselines, transition_rules = load_sound_model_from_csv(defines, script_dir)

    map_context = {
        "sprite_picnums": set(),
        "sprite_lotags": set(),
        "sprite_hitags": set(),
        "wall_lotags": set(),
        "wall_hitags": set(),
        "sector_lotags": set(),
        "sector_hitags": set(),
    }
    for map_file in selected_map_files:
        parsed = parse_map_runtime_context(map_file)
        for key in map_context:
            map_context[key].update(parsed[key])

    con_actor_dependencies, con_global_sounds, unresolved_con_sound_tokens = build_con_runtime_sound_dependencies(temp_dir, defines)
    c_runtime = analyze_c_sound_runtime_paths(script_dir)

    required_sound_ids = set()
    edges = []

    baseline_sounds = set(baselines.get("runtime_essential", set()))
    required_sound_ids.update(baseline_sounds)
    _add_sound_dependency_edges(edges, "baseline:runtime_essential", baseline_sounds, sound_id_to_files)

    required_tiles_set = set(required_tiles or [])
    con_actor_added = set()
    for trigger_tile, sound_ids in con_actor_dependencies.items():
        if trigger_tile in required_tiles_set:
            con_actor_added.update(sound_ids)
            _add_sound_dependency_edges(
                edges,
                f"con_actor:tile:{trigger_tile}",
                set(sound_ids),
                sound_id_to_files,
            )
    required_sound_ids.update(con_actor_added)

    required_sound_ids.update(con_global_sounds)
    _add_sound_dependency_edges(edges, "con_global", con_global_sounds, sound_id_to_files)

    c_static_sound_ids = set()
    for token in c_runtime["static_sound_tokens"]:
        resolved_id = parse_sound_id_from_token(token, defines)
        if resolved_id is not None and resolved_id >= 0:
            c_static_sound_ids.add(resolved_id)
    if c_static_sound_ids:
        required_sound_ids.update(c_static_sound_ids)
        _add_sound_dependency_edges(edges, "c_runtime:static_calls", c_static_sound_ids, sound_id_to_files)

    context_sets = {
        "tile_present": required_tiles_set,
        "map_sprite_pic": map_context["sprite_picnums"],
        "map_sprite_lotag": map_context["sprite_lotags"],
        "map_sprite_hitag": map_context["sprite_hitags"],
        "map_sector_lotag": map_context["sector_lotags"],
        "map_wall_lotag": map_context["wall_lotags"],
    }

    for rule in transition_rules:
        trigger_type = rule["trigger_type"]
        if trigger_type == "always":
            matched = {0}
        else:
            source_set = context_sets.get(trigger_type)
            if source_set is None:
                continue
            if rule["trigger_values"] is None:
                matched = set(source_set)
            else:
                matched = set(source_set) & set(rule["trigger_values"])
        if not matched:
            continue

        include_mode = rule["include_mode"]
        include_ids = set()
        if include_mode == "static":
            include_ids.update(rule["include_values"])
        elif include_mode == "trigger_value":
            include_ids.update(v for v in matched if v >= 0)
        elif include_mode == "trigger_value_minus_10000":
            include_ids.update((v - 10000) for v in matched if v >= 10000)
        if not include_ids:
            continue

        required_sound_ids.update(include_ids)
        _add_sound_dependency_edges(
            edges,
            f"csv:{rule['category']}:{trigger_type}:{rule['name'] or 'rule'}",
            include_ids,
            sound_id_to_files,
        )

    c_dynamic_added = set()
    if c_runtime["supports_hitag_sound_id"]:
        c_dynamic_added.update(v for v in map_context["sprite_hitags"] if v >= 0)
    if c_runtime["supports_lotag_sound_id"]:
        c_dynamic_added.update(v for v in map_context["sprite_lotags"] if v >= 0)
        c_dynamic_added.update(v for v in map_context["wall_lotags"] if v >= 0)
    if c_runtime["supports_lotag_minus_10000"]:
        c_dynamic_added.update((v - 10000) for v in map_context["sector_lotags"] if v >= 10000)
    if c_dynamic_added:
        required_sound_ids.update(c_dynamic_added)
        _add_sound_dependency_edges(edges, "c_runtime:dynamic_map_tags", c_dynamic_added, sound_id_to_files)

    known_sound_ids = set(sound_id_to_files.keys())
    unknown_required_sound_ids = sorted(sound_id for sound_id in required_sound_ids if sound_id not in known_sound_ids)
    required_sound_ids = {sound_id for sound_id in required_sound_ids if sound_id in known_sound_ids}

    required_sound_files = set()
    for sound_id in required_sound_ids:
        for src_file in sound_id_to_files.get(sound_id, set()):
            stem = Path(src_file).stem.lower()
            required_sound_files.add(f"{stem}.voc")
            required_sound_files.add(f"{stem}.wav")

    unresolved = {
        "con_sound_tokens": sorted(unresolved_con_sound_tokens),
        "con_def_sound_tokens": sorted(unresolved_sound_tokens_from_defs),
        "c_runtime_expressions": sorted(c_runtime["unresolved_expressions"]),
        "unknown_required_sound_ids": unknown_required_sound_ids,
    }

    return {
        "required_sound_ids": required_sound_ids,
        "required_sound_files": required_sound_files,
        "sound_id_to_files": sound_id_to_files,
        "edges": edges,
        "unresolved": unresolved,
    }


def print_required_sound_report(model: dict):
    required_sound_ids = sorted(model["required_sound_ids"])
    edges = model["edges"]

    reason_counts = defaultdict(int)
    for edge in edges:
        reason_counts[edge["reason"]] += 1

    print(f"[debug] required sounds: {len(required_sound_ids)} IDs")
    for reason in sorted(reason_counts):
        print(f"[debug]   {reason}: {reason_counts[reason]} sound(s)")

    for edge in sorted(edges, key=lambda e: (e["sound_id"], e["reason"])):
        files = ",".join(edge["files"]) if edge["files"] else "(no-file)"
        print(f"[debug]   sound {edge['sound_id']} <= {edge['reason']} files={files}")


def dump_required_sounds(model: dict, output_path: Path):
    output_path.parent.mkdir(parents=True, exist_ok=True)
    sound_id_to_files = model["sound_id_to_files"]
    with output_path.open("w", encoding="utf-8") as fh:
        for sound_id in sorted(model["required_sound_ids"]):
            files = ",".join(sorted(sound_id_to_files.get(sound_id, set())))
            fh.write(f"{sound_id}\t{files}\n")


def dump_sound_dependency_edges(model: dict, output_path: Path):
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as fh:
        fh.write("reason\tsound_id\tfiles\n")
        for edge in sorted(model["edges"], key=lambda e: (e["reason"], e["sound_id"])):
            fh.write(f"{edge['reason']}\t{edge['sound_id']}\t{','.join(edge['files'])}\n")


def print_sound_model_unresolved(model: dict):
    unresolved = model["unresolved"]
    if unresolved["con_sound_tokens"]:
        print(
            f"[warn] unresolved CON sound tokens ({len(unresolved['con_sound_tokens'])}): "
            f"{', '.join(unresolved['con_sound_tokens'][:24])}"
        )
    if unresolved["con_def_sound_tokens"]:
        print(
            f"[warn] unresolved CON definesound/sound tokens ({len(unresolved['con_def_sound_tokens'])}): "
            f"{', '.join(unresolved['con_def_sound_tokens'][:24])}"
        )
    if unresolved["c_runtime_expressions"]:
        print(
            f"[warn] unresolved C sound expressions ({len(unresolved['c_runtime_expressions'])}): "
            f"{', '.join(unresolved['c_runtime_expressions'][:24])}"
        )
    if unresolved["unknown_required_sound_ids"]:
        print(
            f"[warn] required sound IDs without CON file mapping ({len(unresolved['unknown_required_sound_ids'])}): "
            f"{', '.join(str(v) for v in unresolved['unknown_required_sound_ids'][:24])}"
        )


def print_required_sound_summary(model: dict):
    required_ids = set(model["required_sound_ids"])
    files = set()
    for entry in model["sound_id_to_files"].values():
        files.update(entry)
    mapped_ids = {sid for sid, names in model["sound_id_to_files"].items() if names}

    missing_known_files = sorted(files - {f for f in model["required_sound_files"] if f.endswith(".voc")})
    if missing_known_files:
        preview = ", ".join(missing_known_files[:16])
        if len(missing_known_files) > 16:
            preview += ", ..."
        print(
            f"[debug] sound model exclusion sample ({len(missing_known_files)} known VOCs excluded): {preview}"
        )

    print(
        f"[debug] sound model coverage: required_ids={len(required_ids)} mapped_ids={len(mapped_ids)} "
        f"known_sound_files={len(files)}"
    )



def main():
    normalized_argv = normalize_case_insensitive_options(
        sys.argv[1:],
        [
            "--pngfolder",
            "--map",
            "--includeart",
            "--ultraminimalmenu",
            "--excludefiles",
            "--includefiles",
            "--replacefile",
            "--adpcmwav",
            "--adpcmwidth",
            "--maxsoundsize",
            "--nomenusongs",
            "--camerasdestructable",
            "--pngquant",
            "--pngiterations",
            "--resumetile",
            "--debug-runtime-spawns",
            "--debug-sounds",
            "--dump-required-sounds",
            "--dump-sound-deps",
        ],
    )

    parser = argparse.ArgumentParser(description="Re-package Duke Nukem 3D GRP with PNG tiles and duke3d.def")
    parser.add_argument("grpfile", help="Path to .grp file to compact")
    parser.add_argument("--temp-dir", default="temp_folder", help="Temporary working directory")
    parser.add_argument("--output", default="newfile.grp", help="Output GRP filename")
    parser.add_argument("--keep-temp", action="store_true", help="Keep temporary working directory")
    parser.add_argument(
        "--tilefilestopng",
        "--tilesfilestopng",
        "--tilestopng",
        type=parse_tilefiles_arg,
        help="Only convert specific TILESXXX.ART files to PNG (comma-separated indices, e.g. 0,1,2). Untouched ART files stay in output.",
    )
    parser.add_argument(
        "--onlysmaller",
        action="store_true",
        help="Only replace tiles when PNG is smaller than raw tile data; keeps ART files in output",
    )
    parser.add_argument(
        "--zopflipng",
        action="store_true",
        help="Run zopflipng with fixed high-compression settings on each generated PNG",
    )
    parser.add_argument(
        "--pngquant",
        metavar="QUALITY",
        type=str,
        help=(
            "Run ~/software/pngquant --quality QUALITY --speed 1 --posterize 2 on each generated PNG "
            "(applied after convert, before zopflipng). QUALITY is a single value or MIN-MAX range, "
            "e.g. --pngquant 70 or --pngquant 10-70."
        ),
    )
    parser.add_argument(
        "--pngiterations",
        metavar="N",
        type=int,
        help=(
            "Repeat the pngquant+zopflipng cycle N times on each generated PNG. "
            "Requires --pngquant. Each iteration runs pngquant, "
            "then zopflipng (if --zopflipng)."
        ),
    )
    parser.add_argument(
        "--pngfolder",
        metavar="DIRNAME",
        help="Use pre-generated TILE####.PNG files from DIRNAME instead of exporting/converting from ART files",
    )
    parser.add_argument(
        "--map",
        metavar="MAP1,MAP2,...",
        type=parse_map_arg,
        help=(
            "Limit tile processing to tiles used by one or more map files "
            "(comma-separated, case-insensitive), e.g. E1L1.MAP,E1L2.MAP. "
            "If omitted, all .MAP files in the extracted GRP are used."
        ),
    )
    parser.add_argument(
        "--includeart",
        metavar="FILE.ART",
        action="append",
        type=parse_includeart_arg,
        help="Force-include FILE.ART from extracted temp folder (repeatable, e.g. --includeart TILES012.ART)",
    )
    parser.add_argument(
        "--ultraminimalmenu",
        action="store_true",
        help=(
            "Include a runtime baseline tile allowlist for --map builds, derived from "
            "source/duke3d/src/premap.cpp + HUD/menu draw code. "
            "Adds non-map essentials like crosshair, weapon HUD tiles and core FX/projectile tiles."
        ),
    )
    parser.add_argument(
        "--excludefiles",
        metavar="FILE1,FILE2,...",
        action="append",
        type=parse_excludefiles_arg,
        help=(
            "Exclude one or more filenames from the final GRP (comma-separated, repeatable). "
            "Special handling: .pcx excludes same basename as .png, and .voc excludes both .voc and .wav. "
            "Example: --excludefiles TILES3280.PCX,SHOTGUN.VOC"
        ),
    )
    parser.add_argument(
        "--includefiles",
        metavar="FILE1,FILE2,...",
        action="append",
        type=parse_includefiles_arg,
        help=(
            "Force-include one or more filenames in the final GRP (comma-separated, repeatable). "
            "Applied at the end of file selection and overrides excludes/filtering options. "
            "Every listed file must exist in extracted temp dir; otherwise the script aborts."
        ),
    )
    parser.add_argument(
        "--replacefile",
        nargs=2,
        action="append",
        metavar=("GRP_NAME", "SOURCE_PATH"),
        help=(
            "Replace a file in the final GRP with content from an external source file (repeatable). "
            "Example: --replacefile TILE0269.PNG ../somefolder/TILE0269.PNG"
        ),
    )
    parser.add_argument(
        "--debug-tiles",
        metavar="TILE1,TILE2,...",
        type=parse_tile_numbers_arg,
        help=(
            "Print per-tile animation diagnostics after build (for PNG-only packs). "
            "Example: --debug-tiles 1289,1290,407,411,2813"
        ),
    )
    parser.add_argument(
        "--adpcmwav",
        action="store_true",
        help=(
            "Convert each .VOC in the extracted GRP to ADPCM IMA WAV "
            "and emit matching sound { id N file name.wav } entries in duke3d.def"
        ),
    )
    parser.add_argument(
        "--adpcmwidth",
        metavar="N",
        type=int,
        choices=range(2, 6),
        help=(
            "Use adpcm-xq two-pass conversion width N (2..5) for --adpcmwav: "
            "ffmpeg VOC->WAV then adpcm-xq -wN WAV->ADPCM WAV"
        ),
    )
    parser.add_argument(
        "--maxsoundsize",
        metavar="N",
        type=int,
        help="Exclude .VOC/.WAV files larger than N bytes from the final GRP",
    )
    parser.add_argument(
        "--nomenusongs",
        action="store_true",
        help="Exclude menu/title music (MID) files from the repacked GRP to save space",
    )
    parser.add_argument(
        "--camerasdestructable",
        action="store_true",
        help=(
            "Patch USER.CON after extraction: change "
            "'define CAMERASDESTRUCTABLE      NO' to YES"
        ),
    )
    parser.add_argument(
        "--resumetile",
        metavar="N",
        type=int,
        help=(
            "Resume an interrupted run from tile number N. "
            "Skips GRP extraction and reuses the existing temp directory; "
            "tiles already converted (< N) are re-emitted into duke3d.def "
            "from existing TILE####.PNG files without reprocessing."
        ),
    )
    parser.add_argument(
        "--debug-runtime-spawns",
        action="store_true",
        help=(
            "Print trigger->spawned tile dependencies derived from GAME.CON actor/state "
            "spawn/debris/guts paths. Useful to audit map-compaction runtime tile coverage."
        ),
    )
    parser.add_argument(
        "--dump-runtime-spawn-deps",
        metavar="FILE",
        help="Write computed CON runtime spawn dependencies to FILE",
    )
    parser.add_argument(
        "--dump-required-tiles",
        metavar="FILE",
        help="Write final required tile set (sorted, one tile per line) to FILE",
    )
    parser.add_argument(
        "--debug-sounds",
        action="store_true",
        help="Print why each sound ID/file was included by the runtime sound model",
    )
    parser.add_argument(
        "--dump-required-sounds",
        metavar="FILE",
        help="Write final required sound IDs/files to FILE",
    )
    parser.add_argument(
        "--dump-sound-deps",
        metavar="FILE",
        help="Write sound dependency edges (reason -> sound id -> files) to FILE",
    )

    args = parser.parse_args(normalized_argv)

    if args.maxsoundsize is not None and args.maxsoundsize < 0:
        parser.error("--maxsoundsize requires a non-negative integer")

    if args.adpcmwidth is not None and not args.adpcmwav:
        parser.error("--adpcmwidth requires --adpcmwav")

    selected_tile_files = set(args.tilefilestopng or [])
    included_art_files = set(args.includeart or [])
    excluded_files = {
        name
        for group in (args.excludefiles or [])
        for name in group
    }
    included_files = {
        name
        for group in (args.includefiles or [])
        for name in group
    }
    included_audio_files = set()
    for include_name in included_files:
        stem, suffix = os.path.splitext(include_name)
        if suffix.lower() in {".voc", ".wav"}:
            included_audio_files.add(f"{stem}.voc")
            included_audio_files.add(f"{stem}.wav")

    work_dir = Path.cwd().resolve()
    script_dir = Path(__file__).resolve().parent
    grp_path = (work_dir / args.grpfile).resolve()

    replace_files = {}
    if args.replacefile:
        for grp_name, source_path in args.replacefile:
            normalized_name = Path(grp_name).name.lower()
            source = Path(source_path)
            if not source.is_absolute():
                source = (work_dir / source).resolve()
            replace_files[normalized_name] = source
    if not grp_path.exists():
        print(f"Input GRP not found: {grp_path}")
        return 1

    temp_dir = (work_dir / args.temp_dir).resolve()

    resume_tile = args.resumetile if args.resumetile is not None else -1

    if resume_tile >= 0:
        if not temp_dir.exists():
            print(f"[error] --resumetile: temp directory '{temp_dir}' does not exist; cannot resume")
            return 1
        print(f"[info] --resumetile {resume_tile}: reusing existing temp directory, skipping extraction")
    else:
        # Always remove default temp_folder as requested, then remove selected temp dir.
        default_temp_dir = (work_dir / "temp_folder").resolve()
        if default_temp_dir.exists():
            shutil.rmtree(default_temp_dir)

        if temp_dir.exists():
            shutil.rmtree(temp_dir)
        temp_dir.mkdir(parents=True)

    kextract = find_tool(script_dir, "kextract")
    kgroup = find_tool(script_dir, "kgroup")
    arttool = find_tool(script_dir, "arttool")
    mapinfo = find_tool(script_dir, "mapinfo")
    convert = None
    if not args.pngfolder:
        convert = shutil.which("convert")
        if not convert:
            raise FileNotFoundError("Required tool 'convert' (ImageMagick) not found in PATH")

    zopflipng = None
    if args.zopflipng and not args.pngfolder:
        zopflipng = shutil.which("zopflipng")
        if not zopflipng:
            raise FileNotFoundError("Requested --zopflipng but tool 'zopflipng' was not found in PATH")

    if args.pngiterations is not None:
        if args.pngiterations < 1:
            parser.error("--pngiterations N requires N >= 1")
        if not args.pngquant:
            parser.error("--pngiterations requires --pngquant")

    pngquant = None
    if args.pngquant and not args.pngfolder:
        pngquant = Path.home() / "software" / "pngquant"
        if not (pngquant.exists() and os.access(pngquant, os.X_OK)):
            raise FileNotFoundError(
                f"Requested --pngquant but '{pngquant}' was not found or is not executable"
            )

    if args.pngfolder and (args.zopflipng or args.pngquant):
        print("[info] --pngfolder was provided: skipping --zopflipng/--pngquant and using precomputed PNGs as-is")

    ffmpeg = None
    adpcm_xq = None
    if args.adpcmwav:
        ffmpeg = shutil.which("ffmpeg")
        if not ffmpeg:
            raise FileNotFoundError("Requested --adpcmwav but tool 'ffmpeg' was not found in PATH")

        if args.adpcmwidth is not None:
            adpcm_xq = Path("/home/user/sources/adpcm-xq/adpcm-xq")
            if not (adpcm_xq.exists() and os.access(adpcm_xq, os.X_OK)):
                raise FileNotFoundError(
                    "Requested --adpcmwidth but '/home/user/sources/adpcm-xq/adpcm-xq' was not found or is not executable"
                )

    png_sources = {}
    if args.pngfolder:
        png_dir = Path(args.pngfolder)
        if not png_dir.is_absolute():
            png_dir = (work_dir / png_dir).resolve()

        if not png_dir.exists() or not png_dir.is_dir():
            print(f"PNG folder not found or not a directory: {png_dir}")
            return 1

        for png_file in sorted(png_dir.iterdir()):
            if not png_file.is_file():
                continue
            match = re.match(r"^tile(\d{4})\.png$", png_file.name, flags=re.IGNORECASE)
            if not match:
                continue
            tile_num = int(match.group(1))
            png_sources[tile_num] = png_file

    if resume_tile < 0:
        # Step 1: extract GRP into temp_dir
        run([str(kextract), str(grp_path), "*"], cwd=temp_dir)

        # arttool expects lowercase tiles*.art names; normalize early so
        # --map animation expansion (arttool info) can resolve tile metadata.
        for art_file in temp_dir.glob("TILES*.ART"):
            art_file.rename(temp_dir / art_file.name.lower())

    # --camerasdestructable: patch USER.CON define before any further processing.
    if args.camerasdestructable and resume_tile < 0:
        user_con = find_file_case_insensitive(temp_dir, "USER.CON")
        if user_con is None:
            print("[warn] --camerasdestructable: USER.CON not found; skipping patch")
        else:
            original_text = user_con.read_text(encoding="utf-8", errors="replace")
            patched_text = re.sub(
                r"(?m)^(\s*define\s+CAMERASDESTRUCTABLE\s+)NO(\s*(?://[^\n]*)?)$",
                r"\1YES\2",
                original_text,
                flags=re.IGNORECASE,
            )
            if patched_text == original_text:
                print(
                    "[warn] --camerasdestructable: 'define CAMERASDESTRUCTABLE      NO' "
                    "not found in USER.CON; no change made"
                )
            else:
                user_con.write_text(patched_text, encoding="utf-8")
                print(
                    f"[info] --camerasdestructable: patched {user_con.name} "
                    "CAMERASDESTRUCTABLE NO -> YES"
                )

    if args.debug_runtime_spawns:
        print_runtime_spawn_dependency_report(temp_dir)

    if args.dump_runtime_spawn_deps:
        deps_dump_path = Path(args.dump_runtime_spawn_deps)
        if not deps_dump_path.is_absolute():
            deps_dump_path = (work_dir / deps_dump_path).resolve()
        dump_runtime_spawn_dependency_report(temp_dir, deps_dump_path)
        print(f"[info] wrote runtime spawn dependency dump: {deps_dump_path}")

    required_tiles = None
    required_sound_files = None
    required_sound_model = None
    required_mid_files = None
    selected_map_names = set()
    map_files_to_process = []

    if args.map:
        map_files_to_process = []
        for requested_map in args.map:
            map_file = find_file_case_insensitive(temp_dir, requested_map)
            if map_file is None:
                print(f"Map file not found in extracted GRP (case-insensitive): {requested_map}")
                return 1
            map_files_to_process.append(map_file)
    else:
        map_files_to_process = sorted(
            [p for p in temp_dir.iterdir() if p.is_file() and p.suffix.lower() == ".map"],
            key=lambda p: p.name.lower(),
        )

    if map_files_to_process:
        required_tiles = set()
        for map_file in map_files_to_process:
            selected_map_names.add(map_file.name.lower())

            mapinfo_proc = subprocess.run(
                [str(mapinfo), str(map_file)],
                cwd=temp_dir,
                check=False,
                capture_output=True,
                text=True,
            )
            mapinfo_output = (mapinfo_proc.stdout or "") + "\n" + (mapinfo_proc.stderr or "")
            if mapinfo_proc.returncode != 0:
                print(f"[error] mapinfo failed for map {map_file.name}; aborting")
                if mapinfo_output.strip():
                    print(mapinfo_output)
                return 1

            used_tiles_for_map = parse_used_tiles_from_mapinfo_output(mapinfo_output)
            required_tiles.update(used_tiles_for_map)
            print(f"[info] map {map_file.name}: found {len(used_tiles_for_map)} directly used tiles")

        if args.map:
            print(
                f"[info] --map selected {len(selected_map_names)} map(s): "
                f"{', '.join(sorted(selected_map_names))}"
            )
        else:
            print(f"[info] --map not provided: using all maps ({len(selected_map_names)} total)")

        print(f"[info] map-based tile restriction initial set size: {len(required_tiles)}")

        expanded_tiles = expand_required_tiles_with_animation_frames(arttool, temp_dir, required_tiles)
        added_tiles = len(expanded_tiles) - len(required_tiles)
        if added_tiles > 0:
            required_tiles = expanded_tiles
            print(
                f"[info] map-based tile set: added {added_tiles} animation-frame tiles "
                f"(total now {len(required_tiles)})"
            )

        enemy_expanded_tiles = expand_required_tiles_with_enemy_runtime_ranges(required_tiles, temp_dir, script_dir)
        enemy_added_tiles = len(enemy_expanded_tiles) - len(required_tiles)
        if enemy_added_tiles > 0:
            required_tiles = enemy_expanded_tiles
            print(
                f"[info] map-based tile set: added {enemy_added_tiles} enemy runtime-frame tiles "
                f"(total now {len(required_tiles)})"
            )

        con_precache_ranges = build_precache_ranges_from_cons(temp_dir)
        con_precache_tiles = expand_required_tiles_with_con_precache_ranges(required_tiles, con_precache_ranges)
        con_precache_added = len(con_precache_tiles) - len(required_tiles)
        if con_precache_added > 0:
            required_tiles = con_precache_tiles
            print(
                f"[info] map-based tile set: added {con_precache_added} CON precache-range tiles "
                f"(total now {len(required_tiles)})"
            )

        required_mid_files = set()
        for selected_map_name in sorted(selected_map_names):
            map_required_mid_files = determine_required_mid_files_from_user_con(temp_dir, selected_map_name, args.nomenusongs)
            if map_required_mid_files is None:
                required_mid_files = None
                break
            required_mid_files.update(map_required_mid_files)

        if required_mid_files is not None:
            label = "music files" if args.nomenusongs else "music files (title/end + all selected map tracks)"
            print(
                f"[info] map-based music filtering: including {len(required_mid_files)} {label}"
            )
    else:
        print("[warn] No .MAP files found in extracted GRP; skipping map-based tile restriction")

    if required_tiles is not None:
        sprite_precache_tiles = expand_required_tiles_with_sprite_precache_ranges(required_tiles, temp_dir, script_dir)
        sprite_precache_added = len(sprite_precache_tiles) - len(required_tiles)
        if sprite_precache_added > 0:
            required_tiles = sprite_precache_tiles
            print(
                f"[info] map-based tile set: added {sprite_precache_added} sprite runtime-precache tiles "
                f"(total now {len(required_tiles)})"
            )

        con_spawn_tiles = expand_required_tiles_with_con_spawn_dependencies(required_tiles, temp_dir, script_dir)
        con_spawn_added = len(con_spawn_tiles) - len(required_tiles)
        if con_spawn_added > 0:
            required_tiles = con_spawn_tiles
            print(
                f"[info] map-based tile set: added {con_spawn_added} CON runtime-spawn tiles "
                f"(total now {len(required_tiles)})"
            )

        runtime_essential_tiles = build_runtime_essentials_allowlist(temp_dir, script_dir)
        runtime_essential_expanded = set(required_tiles)
        runtime_essential_expanded.update(runtime_essential_tiles)
        runtime_essential_added = len(runtime_essential_expanded) - len(required_tiles)
        if runtime_essential_added > 0:
            required_tiles = runtime_essential_expanded
            print(
                f"[info] map-based tile set: added {runtime_essential_added} runtime-essential tiles "
                f"(total now {len(required_tiles)})"
            )

    if args.ultraminimalmenu:
        menu_allow_tiles = build_ultra_minimal_menu_allowlist(temp_dir, script_dir)
        if required_tiles is None:
            required_tiles = set()
        required_tiles.update(menu_allow_tiles)
        print(
            f"[info] --ultraminimalmenu: added {len(menu_allow_tiles)} "
            f"menu/precache tiles; total required tiles now {len(required_tiles)}"
        )

    # Final animation closure pass after all required-tile sources are merged
    # (--map, runtime state tiles, --ultraminimalmenu, etc.).
    # Without this, tiles introduced late (e.g. by --ultraminimalmenu) can miss
    # their dependent PICANM frames and cause skipped animtilerange entries.
    if required_tiles is not None:
        fully_expanded_tiles = expand_required_tiles_with_animation_frames(arttool, temp_dir, required_tiles)
        final_anim_added = len(fully_expanded_tiles) - len(required_tiles)
        if final_anim_added > 0:
            required_tiles = fully_expanded_tiles
            print(
                f"[info] required tiles finalization: added {final_anim_added} animation-frame tiles "
                f"after merging all tile sources (total now {len(required_tiles)})"
            )

        if args.dump_required_tiles:
            required_dump_path = Path(args.dump_required_tiles)
            if not required_dump_path.is_absolute():
                required_dump_path = (work_dir / required_dump_path).resolve()
            dump_required_tiles(required_tiles, required_dump_path)
            print(f"[info] wrote required tiles dump: {required_dump_path}")

        required_sound_model = build_required_sound_model(
            temp_dir,
            script_dir,
            map_files_to_process,
            required_tiles,
        )
        required_sound_files = set(required_sound_model["required_sound_files"])
        print(
            f"[info] map-based sound model: required {len(required_sound_model['required_sound_ids'])} sound IDs "
            f"({len(required_sound_files)} file name targets including .voc/.wav pairs)"
        )

        if args.debug_sounds:
            print_required_sound_report(required_sound_model)

        if args.dump_required_sounds:
            required_sounds_dump_path = Path(args.dump_required_sounds)
            if not required_sounds_dump_path.is_absolute():
                required_sounds_dump_path = (work_dir / required_sounds_dump_path).resolve()
            dump_required_sounds(required_sound_model, required_sounds_dump_path)
            print(f"[info] wrote required sounds dump: {required_sounds_dump_path}")

        if args.dump_sound_deps:
            sound_deps_dump_path = Path(args.dump_sound_deps)
            if not sound_deps_dump_path.is_absolute():
                sound_deps_dump_path = (work_dir / sound_deps_dump_path).resolve()
            dump_sound_dependency_edges(required_sound_model, sound_deps_dump_path)
            print(f"[info] wrote sound dependency dump: {sound_deps_dump_path}")

        print_sound_model_unresolved(required_sound_model)
        if args.debug_sounds:
            print_required_sound_summary(required_sound_model)

    # arttool expects lowercase tilesXXX.art filenames for files we process.
    if selected_tile_files:
        for tile_file_index in sorted(selected_tile_files):
            selected_upper = temp_dir / f"TILES{tile_file_index:03d}.ART"
            selected_lower = temp_dir / f"tiles{tile_file_index:03d}.art"
            if selected_upper.exists() and not selected_lower.exists():
                selected_upper.rename(selected_lower)
    else:
        for art_file in temp_dir.glob("TILES*.ART"):
            art_file.rename(temp_dir / art_file.name.lower())

    # normalize palette file casing for runtime lookup
    palette_upper = temp_dir / "PALETTE.DAT"
    palette_lower = temp_dir / "palette.dat"
    if palette_upper.exists() and not palette_lower.exists():
        palette_upper.rename(palette_lower)

    # Step 2: extract tiles*.art, convert to PNG, build duke3d.def
    duke_def_path = temp_dir / "duke3d.def"
    if duke_def_path.exists():
        duke_def_path.unlink()

    replaced_voc_files = set()

    with duke_def_path.open("w", encoding="utf-8") as duke_def:
        written_tiles = set()
        missing_required_png_sources = []
        skipped_zero_size_tiles_without_png = []
        anim_def_candidates = {}
        emitted_anim_ranges = []

        if args.adpcmwav:
            voc_sound_ids, sound_fields_by_id, _sound_id_to_files, _sound_defines, _unresolved_sound_tokens = build_sound_maps_from_cons(temp_dir)
            emitted_sound_defs = 0

            if resume_tile >= 0:
                # On resume, WAV files were already produced; just emit their def entries.
                for wav_file in sorted(temp_dir.glob("*.wav"), key=lambda p: p.name.lower()):
                    voc_name = wav_file.stem.lower() + ".voc"
                    wav_name = wav_file.name.lower()
                    force_include_audio = voc_name in included_audio_files or wav_name in included_audio_files
                    if (
                        required_sound_files is not None
                        and wav_name not in required_sound_files
                        and voc_name not in required_sound_files
                        and not force_include_audio
                    ):
                        continue
                    replaced_voc_files.add(voc_name)
                    if wav_name in excluded_files and not force_include_audio:
                        print(
                            f"[info] --excludefiles: keeping converted {wav_file.name} but skipping sound {{ ... }} def entry"
                        )
                        continue
                    if wav_name in excluded_files and force_include_audio:
                        print(
                            f"[info] --includefiles: forcing sound {{ ... }} def entry for {wav_file.name} despite --excludefiles"
                        )
                    if args.maxsoundsize is not None:
                        source_voc = find_file_case_insensitive(temp_dir, voc_name)
                        if source_voc is None:
                            print(
                                f"[warn] --maxsoundsize: source {voc_name} not found during resume; "
                                f"falling back to {wav_file.name} size check"
                            )
                            if wav_file.stat().st_size > args.maxsoundsize and not force_include_audio:
                                print(
                                    f"[info] --maxsoundsize: keeping converted {wav_file.name} but skipping sound {{ ... }} def entry "
                                    f"({wav_file.stat().st_size} bytes > {args.maxsoundsize})"
                                )
                                continue
                            if wav_file.stat().st_size > args.maxsoundsize and force_include_audio:
                                print(
                                    f"[info] --includefiles: forcing sound {{ ... }} def entry for {wav_file.name} despite --maxsoundsize "
                                    f"({wav_file.stat().st_size} bytes > {args.maxsoundsize})"
                                )
                        elif source_voc.stat().st_size > args.maxsoundsize and not force_include_audio:
                            print(
                                f"[info] --maxsoundsize: keeping converted {wav_file.name} but skipping sound {{ ... }} def entry "
                                f"(source {source_voc.name}: {source_voc.stat().st_size} bytes > {args.maxsoundsize})"
                            )
                            continue
                        elif source_voc.stat().st_size > args.maxsoundsize and force_include_audio:
                            print(
                                f"[info] --includefiles: forcing sound {{ ... }} def entry for {wav_file.name} despite --maxsoundsize "
                                f"(source {source_voc.name}: {source_voc.stat().st_size} bytes > {args.maxsoundsize})"
                            )

                    sound_ids = sorted(voc_sound_ids.get(voc_name, set()))
                    if not sound_ids:
                        continue

                    replaced_voc_files.add(voc_name)
                    for sound_id in sound_ids:
                        sound_fields = sound_fields_by_id.get(sound_id)
                        if sound_fields:
                            duke_def.write(
                                "sound { "
                                f"id {sound_id} "
                                f"file {wav_file.name} "
                                f"minpitch {sound_fields['minpitch']} "
                                f"maxpitch {sound_fields['maxpitch']} "
                                f"priority {sound_fields['priority']} "
                                f"type {sound_fields['type']} "
                                f"distance {sound_fields['distance']} "
                                "}\n"
                            )
                        else:
                            duke_def.write(f"sound {{ id {sound_id} file {wav_file.name} }}\n")
                        emitted_sound_defs += 1
                if emitted_sound_defs > 0:
                    duke_def.write("\n")
                    print(f"[info] --resumetile: re-emitted {emitted_sound_defs} sound entries from existing WAV files")

            voc_files = sorted(
                [p for p in temp_dir.iterdir() if p.is_file() and p.suffix.lower() == ".voc"],
                key=lambda p: p.name.lower(),
            )

            for voc_file in voc_files:
                if resume_tile >= 0:
                    break  # skip all VOC conversion on resume

                wav_name = f"{voc_file.stem.lower()}.wav"
                force_include_audio = voc_file.name.lower() in included_audio_files or wav_name in included_audio_files
                if (
                    required_sound_files is not None
                    and voc_file.name.lower() not in required_sound_files
                    and wav_name not in required_sound_files
                    and not force_include_audio
                ):
                    continue
                wav_path = temp_dir / wav_name

                if args.adpcmwidth is None:
                    ffmpeg_proc = subprocess.run(
                        [ffmpeg, "-y", "-i", str(voc_file), "-c:a", "adpcm_ima_wav", str(wav_path)],
                        cwd=temp_dir,
                        check=False,
                        capture_output=True,
                        text=True,
                    )
                    if ffmpeg_proc.returncode != 0 or not wav_path.exists():
                        print(f"[error] ffmpeg --adpcmwav failed for {voc_file.name}; aborting")
                        if ffmpeg_proc.stdout:
                            print(ffmpeg_proc.stdout)
                        if ffmpeg_proc.stderr:
                            print(ffmpeg_proc.stderr)
                        return 1
                else:
                    intermediate_wav_path = temp_dir / f"{voc_file.stem.lower()}.__pcm.wav"
                    intermediate_wav_path.unlink(missing_ok=True)
                    wav_path.unlink(missing_ok=True)

                    ffmpeg_proc = subprocess.run(
                        [ffmpeg, "-y", "-i", str(voc_file), str(intermediate_wav_path)],
                        cwd=temp_dir,
                        check=False,
                        capture_output=True,
                        text=True,
                    )
                    if ffmpeg_proc.returncode != 0 or not intermediate_wav_path.exists():
                        print(f"[error] ffmpeg first pass (--adpcmwidth) failed for {voc_file.name}; aborting")
                        if ffmpeg_proc.stdout:
                            print(ffmpeg_proc.stdout)
                        if ffmpeg_proc.stderr:
                            print(ffmpeg_proc.stderr)
                        return 1

                    adpcm_xq_proc = subprocess.run(
                        [str(adpcm_xq), f"-w{args.adpcmwidth}", str(intermediate_wav_path), str(wav_path)],
                        cwd=temp_dir,
                        check=False,
                        capture_output=True,
                        text=True,
                    )
                    intermediate_wav_path.unlink(missing_ok=True)

                    if adpcm_xq_proc.returncode != 0 or not wav_path.exists():
                        print(
                            f"[error] adpcm-xq second pass (--adpcmwidth {args.adpcmwidth}) failed for {voc_file.name}; aborting"
                        )
                        if adpcm_xq_proc.stdout:
                            print(adpcm_xq_proc.stdout)
                        if adpcm_xq_proc.stderr:
                            print(adpcm_xq_proc.stderr)
                        return 1

                replaced_voc_files.add(voc_file.name.lower())

                if (voc_file.name.lower() in excluded_files or wav_name in excluded_files) and not force_include_audio:
                    print(
                        f"[info] --excludefiles: keeping converted {wav_name} but skipping sound {{ ... }} def entry"
                    )
                    continue
                if (voc_file.name.lower() in excluded_files or wav_name in excluded_files) and force_include_audio:
                    print(
                        f"[info] --includefiles: forcing sound {{ ... }} def entry for {wav_name} despite --excludefiles"
                    )

                if args.maxsoundsize is not None and voc_file.stat().st_size > args.maxsoundsize and not force_include_audio:
                    print(
                        f"[info] --maxsoundsize: keeping converted {wav_name} but skipping sound {{ ... }} def entry "
                        f"(source {voc_file.name}: {voc_file.stat().st_size} bytes > {args.maxsoundsize})"
                    )
                    continue
                if args.maxsoundsize is not None and voc_file.stat().st_size > args.maxsoundsize and force_include_audio:
                    print(
                        f"[info] --includefiles: forcing sound {{ ... }} def entry for {wav_name} despite --maxsoundsize "
                        f"(source {voc_file.name}: {voc_file.stat().st_size} bytes > {args.maxsoundsize})"
                    )

                sound_ids = sorted(voc_sound_ids.get(voc_file.name.lower(), set()))
                if not sound_ids:
                    print(f"[warn] No sound ID found in CON files for {voc_file.name}; skipping sound {{ ... }} def entry")
                    continue

                for sound_id in sound_ids:
                    sound_fields = sound_fields_by_id.get(sound_id)
                    if sound_fields:
                        duke_def.write(
                            "sound { "
                            f"id {sound_id} "
                            f"file {wav_name} "
                            f"minpitch {sound_fields['minpitch']} "
                            f"maxpitch {sound_fields['maxpitch']} "
                            f"priority {sound_fields['priority']} "
                            f"type {sound_fields['type']} "
                            f"distance {sound_fields['distance']} "
                            "}\n"
                        )
                    else:
                        duke_def.write(f"sound {{ id {sound_id} file {wav_name} }}\n")

                    emitted_sound_defs += 1

            if emitted_sound_defs > 0:
                duke_def.write("\n")
                print(f"[info] --adpcmwav: emitted {emitted_sound_defs} sound entries in duke3d.def")

        if selected_tile_files:
            art_files = [
                temp_dir / f"tiles{tile_file_index:03d}.art"
                for tile_file_index in sorted(selected_tile_files)
                if (temp_dir / f"tiles{tile_file_index:03d}.art").exists()
            ]
        else:
            art_files = sorted(temp_dir.glob("tiles*.art"))
        for art_file in art_files:
            name = art_file.stem  # TILES000
            digits = "".join(ch for ch in name if ch.isdigit())
            tile_index = int(digits) if digits else 0
            tiles_to_remove = []

            for tile_nr in range(256):
                global_tile = tile_index * 256 + tile_nr
                if required_tiles is not None and global_tile not in required_tiles:
                    continue
                global_padded = f"{global_tile:04d}"

                # --resumetile: for tiles already processed, re-emit the def entry
                # from the existing PNG without rerunning convert/pngquant/zopflipng.
                if resume_tile >= 0 and global_tile < resume_tile:
                    out_png = temp_dir / f"TILE{global_padded}.PNG"
                    if out_png.exists():
                        xofs, yofs = get_tile_offsets(arttool, temp_dir, global_tile)
                        if xofs == 0 and yofs == 0:
                            duke_def.write(f"tilefromtexture {global_tile} {{ file {out_png.name} }}\n")
                        else:
                            duke_def.write(
                                f"tilefromtexture {global_tile} {{ file {out_png.name} xoffset {xofs} yoffset {yofs} }}\n"
                            )
                        written_tiles.add(global_tile)
                        anim_info = get_tile_anim_info(arttool, temp_dir, global_tile)
                        if anim_info["frames"] > 0 and anim_info["type"] > 0:
                            anim_def_candidates[global_tile] = anim_info
                    continue

                local_pcx = temp_dir / f"tile{global_padded}.pcx"
                if local_pcx.exists():
                    local_pcx.unlink()

                out_png = temp_dir / f"TILE{global_padded}.PNG"
                if out_png.exists():
                    out_png.unlink()

                if args.pngfolder:
                    source_png = png_sources.get(global_tile)
                    if not source_png:
                        raw_size = get_tile_raw_size(arttool, temp_dir, global_tile)
                        if raw_size == 0:
                            skipped_zero_size_tiles_without_png.append(global_tile)
                            continue
                        missing_required_png_sources.append(global_tile)
                        continue
                    shutil.copy2(source_png, out_png)
                else:
                    export_proc = subprocess.run(
                        [str(arttool), "exporttile", str(global_tile)],
                        cwd=temp_dir,
                        check=False,
                        capture_output=True,
                        text=True,
                    )
                    #if export_proc.returncode != 0:
                    #    if local_pcx.exists():
                    #        local_pcx.unlink()
                    #    continue

                    if not local_pcx.exists():
                        continue

                    convert_proc = subprocess.run([
                        convert,
                        str(local_pcx),
                        #"-alpha", "off",
                        "-alpha", "on",
                        "-transparent", "#FC00FC",
                        "-strip",
                        "-define", "png:compression-level=9",
                        "-define", "png:compression-strategy=1",
                        "-define", "png:exclude-chunks=date,time",
                        "-colors", "256",
                        f"PNG8:{out_png}",
                    ], cwd=temp_dir, check=False, capture_output=True, text=True)

                    if convert_proc.returncode != 0 or not out_png.exists():
                        print(f"[error] convert failed for tile {global_tile}; aborting")
                        if convert_proc.stdout:
                            print(convert_proc.stdout)
                        if convert_proc.stderr:
                            print(convert_proc.stderr)
                        if out_png.exists():
                            out_png.unlink()
                        return 1

                if args.pngquant and not args.pngfolder:
                    for _pngquant_iter in range(args.pngiterations if args.pngiterations is not None else 1):
                        pngquant_proc = subprocess.run(
                            [
                                str(pngquant),
                                "--quality", args.pngquant,
                                "--speed", "1",
                                "--posterize", "2",
                                "--ext", ".PNG",
                                "--force",
                                str(out_png),
                            ],
                            cwd=temp_dir,
                            check=False,
                            capture_output=True,
                            text=True,
                        )
                        if pngquant_proc.returncode == 99:
                            # Exit 99: quantised result would fall below the --quality floor;
                            # pngquant left the original file untouched — stop iterating.
                            break
                        elif pngquant_proc.returncode != 0:
                            print(f"[error] pngquant failed for tile {global_tile} (exit {pngquant_proc.returncode}); aborting")
                            if pngquant_proc.stdout:
                                print(pngquant_proc.stdout)
                            if pngquant_proc.stderr:
                                print(pngquant_proc.stderr)
                            return 1

                        if args.zopflipng:
                            zopflipng_iter_proc = subprocess.run(
                                [
                                    str(zopflipng),
                                    "--iterations=10", # 500 is better
                                    "--filters=01234mepb",
                                    "--lossy_8bit",
                                    "--lossy_transparent",
                                    "-y",
                                    str(out_png),
                                    str(out_png),
                                ],
                                cwd=temp_dir,
                                check=False,
                                capture_output=True,
                                text=True,
                            )
                            if zopflipng_iter_proc.returncode != 0:
                                print(f"[error] zopflipng (pngquant iteration {_pngquant_iter + 1}) failed for tile {global_tile}; aborting")
                                if zopflipng_iter_proc.stdout:
                                    print(zopflipng_iter_proc.stdout)
                                if zopflipng_iter_proc.stderr:
                                    print(zopflipng_iter_proc.stderr)
                                return 1

                # Standalone zopflipng pass: only when --pngquant is not active
                # (pngquant iterations already include zopflipng interleaved).
                if args.zopflipng and not args.pngfolder and not args.pngquant:
                    zopflipng_proc = subprocess.run(
                        [
                            str(zopflipng),
                            "--iterations=500",
                            "--filters=01234mepb",
                            "--lossy_8bit",
                            "--lossy_transparent",
                            "-y",
                            str(out_png),
                            str(out_png),
                        ],
                        cwd=temp_dir,
                        check=False,
                        capture_output=True,
                        text=True,
                    )
                    if zopflipng_proc.returncode != 0:
                        print(f"[error] zopflipng failed for tile {global_tile}; aborting")
                        if zopflipng_proc.stdout:
                            print(zopflipng_proc.stdout)
                        if zopflipng_proc.stderr:
                            print(zopflipng_proc.stderr)
                        return 1

                if out_png.name.lower() in excluded_files:
                    if args.onlysmaller:
                        subprocess.run(
                            [str(arttool), "rmtile", str(global_tile)],
                            cwd=temp_dir, check=False, capture_output=True,
                        )
                    out_png.unlink()
                    continue

                raw_size = get_tile_raw_size(arttool, temp_dir, global_tile)
                png_size = out_png.stat().st_size

                if args.onlysmaller:
                    # Only do arttool rmtile in --onlysmaller mode (requested: buggy otherwise).
                    if raw_size is not None and png_size < raw_size:
                        rm_proc = subprocess.run(
                            [str(arttool), "rmtile", str(global_tile)],
                            cwd=temp_dir,
                            check=False,
                            capture_output=True,
                            text=True,
                        )
                        if rm_proc.returncode == 0:
                            xofs, yofs = get_tile_offsets(arttool, temp_dir, global_tile)
                            if xofs == 0 and yofs == 0:
                                duke_def.write(f"tilefromtexture {global_tile} {{ file {out_png.name} }}\n")
                            else:
                                duke_def.write(
                                    f"tilefromtexture {global_tile} {{ file {out_png.name} xoffset {xofs} yoffset {yofs} }}\n"
                                )
                            written_tiles.add(global_tile)
                        else:
                            print(f"[warn] rmtile failed for tile {global_tile}, keeping ART tile")
                            out_png.unlink()
                    else:
                        out_png.unlink()
                else:
                    # In normal mode, keep ART as-is and override via DEF only.
                    xofs, yofs = get_tile_offsets(arttool, temp_dir, global_tile)
                    if xofs == 0 and yofs == 0:
                        duke_def.write(f"tilefromtexture {global_tile} {{ file {out_png.name} }}\n")
                    else:
                        duke_def.write(
                            f"tilefromtexture {global_tile} {{ file {out_png.name} xoffset {xofs} yoffset {yofs} }}\n"
                        )
                    written_tiles.add(global_tile)

                if global_tile in written_tiles and global_tile not in anim_def_candidates:
                    anim_info = get_tile_anim_info(arttool, temp_dir, global_tile)
                    if anim_info["frames"] > 0 and anim_info["type"] > 0:
                        anim_def_candidates[global_tile] = anim_info

                # Keep PCX files for debugging when --keep-temp is used.

        if skipped_zero_size_tiles_without_png:
            skipped_zero_size_tiles_without_png = sorted(set(skipped_zero_size_tiles_without_png))
            print(
                f"[info] --pngfolder: skipped {len(skipped_zero_size_tiles_without_png)} "
                "required tile(s) that are 0x0 in ART and have no TILE####.PNG source"
            )

        if missing_required_png_sources:
            missing_required_png_sources = sorted(set(missing_required_png_sources))
            preview = ",".join(str(t) for t in missing_required_png_sources[:24])
            if len(missing_required_png_sources) > 24:
                preview += ",..."
            print(
                f"[error] --pngfolder missing required TILE####.PNG files for "
                f"{len(missing_required_png_sources)} non-empty tile(s): {preview}"
            )
            print("[error] Should we be aborting to avoid silently skipping required tiles?")
            #return 1

        # When --onlysmaller includes ART files in the output, purge non-required
        # tiles from ART so they don't bloat the final GRP. Only required tiles
        # (map-derived, runtime-essential, menu, animation-frames) should remain.
        if args.onlysmaller and required_tiles is not None and not selected_tile_files:
            removed_non_required = 0
            for art_file in art_files:
                name = art_file.stem
                digits = "".join(ch for ch in name if ch.isdigit())
                tile_index = int(digits) if digits else 0
                for tile_nr in range(256):
                    global_tile = tile_index * 256 + tile_nr
                    if global_tile not in required_tiles:
                        subprocess.run(
                            [str(arttool), "rmtile", str(global_tile)],
                            cwd=temp_dir,
                            check=False,
                            capture_output=True,
                            text=True,
                        )
                        removed_non_required += 1
            if removed_non_required > 0:
                print(f"[info] --onlysmaller: removed {removed_non_required} non-required tiles from ART files")

        # Remove ART files that no longer carry any tile data.  We parse the
        # offset table directly: if every offset entry is 0 the file is all-
        # header and can be dropped, even if arttool left stale padding.
        if args.onlysmaller and required_tiles is not None and not selected_tile_files:
            empty_removed = 0
            for art_file in list(art_files):
                if not art_file.exists():
                    continue
                raw = art_file.read_bytes()
                if len(raw) < 16:
                    continue
                # ART format:
                #   0-3  version (= 1)
                #   4-7  numtiles (ignored by reader; writer always sets to 0)
                #   8-11 first tile number
                #  12-15 last tile number
                #  16+  tilesizx[i] (2B each), tilesizy[i] (2B each),
                #       picanm[i] (4B each), then pixel data.
                start_tile = struct.unpack_from("<I", raw, 8)[0]
                end_tile   = struct.unpack_from("<I", raw, 12)[0]
                ntiles = end_tile - start_tile + 1
                widths_off = 16
                heights_off = widths_off + ntiles * 2
                pix_data_off = heights_off + ntiles * 2  # tile pixel data follows picanm array
                non_empty = 0
                for i in range(ntiles):
                    w = struct.unpack_from("<H", raw, widths_off + i * 2)[0]
                    h = struct.unpack_from("<H", raw, heights_off + i * 2)[0]
                    if w * h > 0:
                        non_empty += 1
                if non_empty == 0:
                    art_file.unlink()
                    empty_removed += 1
            if empty_removed > 0:
                print(f"[info] --onlysmaller: removed {empty_removed} empty ART file(s) from output (no tile data left)")

        # Sparse ART file optimization: for files with few tiles, the 2064 B
        # header overhead may outweigh the raw-vs-PNG per-tile savings.
        # When PNG-total for a file's tiles < ART file size, convert all
        # tiles to PNG and drop the ART file.
        if (args.onlysmaller and required_tiles is not None
                and not selected_tile_files and args.pngfolder and png_sources):
            sparse_converted = 0
            for art_file in list(art_files):
                if not art_file.exists():
                    continue
                raw = art_file.read_bytes()
                if len(raw) < 16:
                    continue
                start_tile = struct.unpack_from("<I", raw, 8)[0]
                end_tile   = struct.unpack_from("<I", raw, 12)[0]
                ntiles = end_tile - start_tile + 1
                widths_off = 16
                heights_off = widths_off + ntiles * 2
                picanm_off = heights_off + ntiles * 2

                total_png = 0
                to_convert = []
                ok = True
                for i in range(ntiles):
                    w = struct.unpack_from("<H", raw, widths_off + i * 2)[0]
                    h = struct.unpack_from("<H", raw, heights_off + i * 2)[0]
                    if w * h == 0:
                        continue
                    global_tile = start_tile + i
                    png_path = png_sources.get(global_tile)
                    if not png_path:
                        ok = False
                        break
                    total_png += png_path.stat().st_size
                    picanm = struct.unpack_from("<I", raw, picanm_off + i * 4)[0]
                    xofs = _decode_art_offset(picanm & 0xFF)
                    yofs = _decode_art_offset((picanm >> 8) & 0xFF)
                    to_convert.append((global_tile, xofs, yofs))

                if not ok or total_png >= len(raw):
                    continue

                # Convert all tiles: copy PNGs, rmtile from ART, write def entries
                for global_tile, xofs, yofs in to_convert:
                    source_png = png_sources[global_tile]
                    out_png = temp_dir / f"TILE{global_tile:04d}.PNG"
                    if not out_png.exists():
                        shutil.copy2(source_png, out_png)

                    subprocess.run(
                        [str(arttool), "rmtile", str(global_tile)],
                        cwd=temp_dir, check=False, capture_output=True,
                    )

                    if global_tile not in written_tiles:
                        if xofs == 0 and yofs == 0:
                            duke_def.write(
                                f"tilefromtexture {global_tile} {{ file {out_png.name} }}\n"
                            )
                        else:
                            duke_def.write(
                                f"tilefromtexture {global_tile} {{ file {out_png.name} "
                                f"xoffset {xofs} yoffset {yofs} }}\n"
                            )
                        written_tiles.add(global_tile)

                art_file.unlink()
                sparse_converted += 1

            if sparse_converted > 0:
                print(f"[info] --onlysmaller: converted {sparse_converted} sparse ART file(s) to PNG-only "
                      f"(PNG total < file overhead)")

        emitted_anim_defs = 0
        skipped_anim_defs = 0
        skipped_anim_details = []
        for anchor_tile in sorted(anim_def_candidates):
            info = anim_def_candidates[anchor_tile]
            first_tile = min(info["first"], info["last"])
            last_tile = max(info["first"], info["last"])
            needed_tiles = set(range(first_tile, last_tile + 1))

            if not needed_tiles.issubset(written_tiles):
                skipped_anim_defs += 1
                missing_tiles = sorted(needed_tiles - written_tiles)
                skipped_anim_details.append(
                    {
                        "anchor": anchor_tile,
                        "first": first_tile,
                        "last": last_tile,
                        "type": info["type"],
                        "speed": info["speed"],
                        "missing": missing_tiles,
                    }
                )
                continue

            range_end = info["first"] if info["type"] == 3 else info["last"]
            duke_def.write(
                f"animtilerange {anchor_tile} {range_end} {info['speed']} {info['type']}\n"
            )
            emitted_anim_defs += 1
            emitted_anim_ranges.append((anchor_tile, first_tile, last_tile, info["type"], info["speed"]))

        if emitted_anim_defs > 0 or skipped_anim_defs > 0:
            print(
                f"[info] duke3d.def: emitted {emitted_anim_defs} animtilerange entries "
                f"(skipped {skipped_anim_defs} due to incomplete frame coverage)"
            )

        for skipped in skipped_anim_details:
            print(
                "[info] duke3d.def: skipped animtilerange "
                f"anchor={skipped['anchor']} range={skipped['first']}..{skipped['last']} "
                f"type={skipped['type']} speed={skipped['speed']} "
                f"reason=incomplete frame coverage; missing tiles: "
                f"{','.join(str(t) for t in skipped['missing'])}"
            )

        if args.debug_tiles:
            print("[debug] Animation diagnostics for requested tiles:")
            for tile in args.debug_tiles:
                anim_info = get_tile_anim_info(arttool, temp_dir, tile)
                png_path = temp_dir / f"TILE{tile:04d}.PNG"
                covered_by_emitted_range = any(start <= tile <= end for _, start, end, _, _ in emitted_anim_ranges)
                print(
                    "[debug] "
                    f"tile={tile} png={'yes' if png_path.exists() else 'no'} "
                    f"tilefromtexture={'yes' if tile in written_tiles else 'no'} "
                    f"animtype={anim_info['type']} animframes={anim_info['frames']} animspeed={anim_info['speed']} "
                    f"animrange={anim_info['first']}..{anim_info['last']} "
                    f"covered_by_animtilerange={'yes' if covered_by_emitted_range else 'no'}"
                )

    # Step 3: repack GRP. ART files are included for --onlysmaller or selective tile-file processing.
    patterns = [
        "*.VOC", "*.voc",
        "*.WAV", "*.wav",
        "*.PNG", "*.png",
        "*.CON", "*.con",
        "*.DAT", "*.dat",
        "*.BIN", "*.bin",
        "*.MAP", "*.map",
        "duke3d.def",
        "*.MID", "*.mid",
    ]
    if args.onlysmaller or selected_tile_files or included_art_files:
        patterns.extend(["*.ART", "*.art"])

    files = collect_files(temp_dir, patterns)

    if included_art_files:
        files = [
            f for f in files
            if f.suffix.lower() != ".art"
            or f.name.lower() in included_art_files
        ]

    if excluded_files:
        files = [f for f in files if f.name.lower() not in excluded_files]

    if args.maxsoundsize is not None:
        if args.adpcmwav:
            filtered_files = []
            for f in files:
                suffix = f.suffix.lower()
                if suffix not in {".voc", ".wav"}:
                    filtered_files.append(f)
                    continue

                if suffix == ".voc":
                    if f.stat().st_size <= args.maxsoundsize:
                        filtered_files.append(f)
                    continue

                source_voc_name = f"{f.stem}.voc"
                source_voc = find_file_case_insensitive(temp_dir, source_voc_name)
                check_path = source_voc if source_voc is not None else f
                if check_path.stat().st_size <= args.maxsoundsize:
                    filtered_files.append(f)
            files = filtered_files
        else:
            files = [
                f for f in files
                if f.suffix.lower() not in {".voc", ".wav"}
                or f.stat().st_size <= args.maxsoundsize
            ]

    if args.adpcmwav and replaced_voc_files:
        files = [
            f for f in files
            if f.suffix.lower() != ".voc"
            or f.name.lower() not in replaced_voc_files
        ]

    if required_tiles is not None:
        needed_art_indices = {tile // 256 for tile in required_tiles}
        files = [
            f for f in files
            if f.suffix.lower() != ".art"
            or tilefile_index_from_name(f.name) in needed_art_indices
            or f.name.lower() in included_art_files
        ]

    if selected_map_names:
        files = [
            f for f in files
            if f.suffix.lower() != ".map"
            or f.name.lower() in selected_map_names
        ]

    if required_sound_files is not None:
        files = [
            f for f in files
            if f.suffix.lower() not in {".voc", ".wav"}
            or f.name.lower() in required_sound_files
        ]

    if required_mid_files is not None:
        files = [
            f for f in files
            if f.suffix.lower() != ".mid"
            or f.name.lower() in required_mid_files
        ]

    if selected_tile_files and not args.onlysmaller:
        selected_processed = {f"tiles{idx:03d}.art" for idx in selected_tile_files}
        selected_processed.update({f"TILES{idx:03d}.ART" for idx in selected_tile_files})
        files = [
            f for f in files
            if f.name not in selected_processed
            or f.name.lower() in included_art_files
        ]

    if included_files:
        missing_included_files = []
        forced_included_paths = []
        for include_name in sorted(included_files):
            include_path = find_file_case_insensitive(temp_dir, include_name)
            if include_path is None and args.adpcmwav:
                stem, suffix = os.path.splitext(include_name)
                if suffix.lower() == ".wav":
                    source_voc_name = f"{stem}.voc"
                    source_voc_path = find_file_case_insensitive(temp_dir, source_voc_name)
                    if source_voc_path is not None:
                        include_path = temp_dir / f"{stem}.wav"
            if include_path is None:
                missing_included_files.append(include_name)
            else:
                forced_included_paths.append(include_path)

        if missing_included_files:
            print("[error] --includefiles requested file(s) not found in extracted temp dir:")
            for missing_name in missing_included_files:
                print(f"[error]   {missing_name}")
            print("[error] Aborting because --includefiles must resolve every listed file.")
            return 1

        files.extend(forced_included_paths)

    if replace_files:
        missing_replace_files = []
        for grp_name, source_path in sorted(replace_files.items()):
            if not source_path.exists():
                missing_replace_files.append((grp_name, str(source_path)))
                continue
            existing = find_file_case_insensitive(temp_dir, grp_name)
            dest = existing if existing is not None else (temp_dir / grp_name)
            shutil.copy2(source_path, dest)
            print(f"[info] --replacefile: {dest.name} <- {source_path}")
            if dest not in files:
                files.append(dest)
        if missing_replace_files:
            print("[error] --replacefile requested source file(s) not found:")
            for grp_name, missing_path in missing_replace_files:
                print(f"[error]   {grp_name} -> {missing_path}")
            print("[error] Aborting because --replacefile must resolve every listed source file.")
            return 1

    # de-duplicate while preserving order
    files = list(dict.fromkeys(files))

    if not files:
        print("No files found to pack.")
        return 1

    has_art_files_in_pack = any(f.suffix.lower() == ".art" for f in files)
    if not has_art_files_in_pack and emitted_anim_defs == 0:
        print(
            "[warn] Packing without ART files and without animtilerange entries. "
            "Animated tiles may render as first frame only."
        )

    output_path = (work_dir / args.output).resolve()
    run([str(kgroup), str(output_path)] + [str(p) for p in files], cwd=temp_dir)

    if not args.keep_temp:
        shutil.rmtree(temp_dir)

    print(f"Created: {output_path}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
