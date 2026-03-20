import json
import math
import os
import re
import shutil
import hashlib
import struct
import sys
import time
import zlib
import zipfile
from pathlib import Path


APP_ROOT = Path(__file__).resolve().parents[1]
WORKSPACE_ROOT = APP_ROOT.parent.parent
CACHE_ROOT = APP_ROOT / "cache"
CACHE_ASSETS_DIR = CACHE_ROOT / "assets"
CACHE_IMAGES_DIR = CACHE_ROOT / "images"
CACHE_EXPORT_DIR = CACHE_ROOT / "export"
CACHE_INDEX_PATH = CACHE_ROOT / "index.json"
CACHE_VERSION = 6
ASSET_CHARS = set(b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_./\\ -")
FRAME_RATE = 30
ASSET_RE = re.compile(rb"[A-Za-z0-9_./\\ -]+\.(?:png|pcx)")
ASCII_TOKEN_RE = re.compile(rb"[A-Za-z0-9_./\\ -]{3,}")


def resolve_resources_root():
    configured = os.environ.get("ISAAC_RESOURCES_PATH", "").strip()
    if configured:
        candidate = Path(configured)
        if (candidate / "animations.b").exists():
            return candidate
        if (candidate / "resources" / "animations.b").exists():
            return candidate / "resources"
    default_root = WORKSPACE_ROOT / "PPSA03311-app0" / "resources"
    return default_root


RESOURCES_ROOT = resolve_resources_root()
ANIMATIONS_B_PATH = RESOURCES_ROOT / "animations.b"
GAME_ROOT = RESOURCES_ROOT.parent


def read_u8(data, offset):
    return data[offset], offset + 1


def read_u16(data, offset):
    return struct.unpack_from("<H", data, offset)[0], offset + 2


def read_u32(data, offset):
    return struct.unpack_from("<I", data, offset)[0], offset + 4


def read_f32(data, offset):
    return struct.unpack_from("<f", data, offset)[0], offset + 4


def round_float(value):
    return round(float(value), 6)


def exact_float(value):
    return float(value)


def sha256_hex(data):
    return hashlib.sha256(data).hexdigest()


def bytes_to_hex(data):
    return data.hex()


def hex_to_bytes(value):
    return bytes.fromhex(value) if value else b""


def pack_u8(value):
    return struct.pack("<B", int(value))


def pack_u16(value):
    return struct.pack("<H", int(value))


def pack_u32(value):
    return struct.pack("<I", int(value))


def pack_f32(value):
    return struct.pack("<f", float(value))


def clamp(value, minimum, maximum):
    return max(minimum, min(maximum, value))


def normalize_resource_path(asset_path):
    trimmed = asset_path.strip().replace("\\", "/")
    if trimmed.startswith("gfx/."):
        trimmed = trimmed[5:]
    if trimmed.startswith("./"):
        trimmed = trimmed[2:]
    return trimmed


def normalize_stem_token(value):
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def path_components(asset_path):
    return [part for part in normalize_resource_path(asset_path).lower().split("/") if part]


def path_similarity_score(left, right):
    left_parts = path_components(left)
    right_parts = path_components(right)
    score = 0
    for left_part, right_part in zip(left_parts, right_parts):
        if left_part != right_part:
            break
        score += 10
    if len(left_parts) > 1 and len(right_parts) > 1 and left_parts[-2] == right_parts[-2]:
        score += 8
    if left_parts and right_parts and Path(left_parts[-1]).stem == Path(right_parts[-1]).stem:
        score += 6
    shared = set(left_parts[:-1]) & set(right_parts[:-1])
    score += len(shared)
    return score


RESOURCE_FILE_INDEX = None
RESOURCE_PATH_ALIASES = {
    "effects/effect_006x_immortalheart.png": "effects/effect_006_hearteffect.png",
    "bosses/repentance/derpyplum.png": "bosses/repentance/babyplum.png",
    "small_coin_tear.png": "coin_tears.png",
    "items/pick ups/pickup_001_remix_heart.png": "items/pick ups/pickup_001_heart.png",
    "effects/1000.1002_cross.png": "familiar/wisps/cross.png",
    "globin_projectile.png": "meat_projectile.png",
    "echo_ring.png": "effects/effect_darkring.png",
    "eyelaser_glow.png": "glow.png",
    "electric_tears.png": "effects/effect_018_electriclaser.png",
    "effects/1000.1001_sword.png": "effects/spirit_sword.png",
    "effects/1000.1001b_lightsaber.png": "effects/tech_sword.png",
    "effects/1000.1001c_jawbone.png": "effects/effect_donkeyjawbone.png",
    "familiar/003.206_spirit.png": "effects/spookier_ghost.png",
    "familiar/003.206_spirit_black.png": "effects/spookier_ghost.png",
    "familiar/003.206_spirit_white.png": "effects/spookier_ghost_white.png",
}


def build_resource_file_index():
    exact_paths = {}
    by_name = {}
    by_stem = {}
    by_token = {}
    for path in RESOURCES_ROOT.rglob("*"):
        if not path.is_file():
            continue
        relative = normalize_resource_path(str(path.relative_to(RESOURCES_ROOT)))
        relative_lower = relative.lower()
        name_lower = path.name.lower()
        stem_lower = path.stem.lower()
        token = normalize_stem_token(stem_lower)
        exact_paths[relative_lower] = path
        by_name.setdefault(name_lower, []).append(path)
        by_stem.setdefault(stem_lower, []).append(path)
        by_token.setdefault(token, []).append(path)
    return {
        "exact": exact_paths,
        "by_name": by_name,
        "by_stem": by_stem,
        "by_token": by_token,
    }


def get_resource_file_index():
    global RESOURCE_FILE_INDEX
    if RESOURCE_FILE_INDEX is None:
        RESOURCE_FILE_INDEX = build_resource_file_index()
    return RESOURCE_FILE_INDEX


def resource_candidate_score(asset_path, resource_path):
    normalized_asset = normalize_resource_path(asset_path)
    relative = normalize_resource_path(str(resource_path.relative_to(RESOURCES_ROOT)))
    asset_name = Path(normalized_asset).name.lower()
    asset_stem = Path(normalized_asset).stem.lower()
    asset_token = normalize_stem_token(asset_stem)
    relative_lower = relative.lower()
    score = path_similarity_score(normalized_asset, relative)
    if Path(relative).name.lower() == asset_name:
        score += 50
    if Path(relative).stem.lower() == asset_stem:
        score += 35
    if normalize_stem_token(Path(relative).stem) == asset_token:
        score += 25
    if "costume" in asset_stem and "characters/costumes" in relative_lower:
        score += 18
    if asset_stem.startswith(("0", "1", "2", "3", "4", "5", "6", "7")) or any(
        token in asset_stem for token in ("backdrop", "floor", "pipes", "mausoleum", "gehenna", "planetarium", "lava")
    ):
        if "gfx/backdrop/" in relative_lower:
            score += 18
    if "boss" in normalized_asset.lower() and "/bosses/" in relative_lower:
        score += 12
    if "effect" in asset_stem and "/effects/" in relative_lower:
        score += 10
    if "characters/" in normalized_asset.lower() and "/characters/" in relative_lower:
        score += 10
    return score


def resolve_resource_file(asset_path):
    normalized = normalize_resource_path(asset_path)
    alias = RESOURCE_PATH_ALIASES.get(normalized.lower())
    if alias and alias.lower() != normalized.lower():
        resolved_alias = resolve_resource_file(alias)
        if resolved_alias:
            return resolved_alias
    path_variants = {normalized}
    suffix = Path(normalized).suffix.lower()
    if suffix == ".png":
        path_variants.add(str(Path(normalized).with_suffix(".pcx")))
        path_variants.add(str(Path(normalized).with_suffix(".PNG")))
    lower_variant = normalized.lower()
    path_variants.add(lower_variant)
    if lower_variant.endswith(".png"):
        path_variants.add(lower_variant[:-4] + ".pcx")

    index = get_resource_file_index()
    candidates = []
    for variant in path_variants:
        candidates.append(RESOURCES_ROOT / variant)
        candidates.append(RESOURCES_ROOT / "gfx" / variant)

    for candidate in candidates:
        if candidate.exists():
            return candidate

    best_path = None
    best_score = None
    names_to_try = {Path(variant).name.lower() for variant in path_variants if Path(variant).name}
    stems_to_try = {Path(variant).stem.lower() for variant in path_variants if Path(variant).stem}
    tokens_to_try = {normalize_stem_token(stem) for stem in stems_to_try if stem}
    candidate_pool = []
    seen = set()
    for name in names_to_try:
        for path in index["by_name"].get(name, []):
            if path not in seen:
                candidate_pool.append(path)
                seen.add(path)
    for stem in stems_to_try:
        for path in index["by_stem"].get(stem, []):
            if path not in seen:
                candidate_pool.append(path)
                seen.add(path)
    for token in tokens_to_try:
        for path in index["by_token"].get(token, []):
            if path not in seen:
                candidate_pool.append(path)
                seen.add(path)

    for candidate in candidate_pool:
        score = resource_candidate_score(normalized, candidate)
        if best_score is None or score > best_score:
            best_path = candidate
            best_score = score
    if best_path is not None and best_score is not None and best_score >= 20:
        return best_path
    return None


def infer_special_sheet_mapping(entry):
    asset_path_lower = entry["assetPath"].replace("\\", "/").lower()
    if not asset_path_lower.startswith("credits_page") and not asset_path_lower.startswith("contributors_page"):
        return None

    sheet_to_names = {}
    for layer in entry["layers"]:
        sheet_to_names.setdefault(layer["sheetId"], []).append(layer["name"])
    if not sheet_to_names:
        return None

    max_sheet_id = max(sheet_to_names)
    mapping = [None] * (max_sheet_id + 1)
    for sheet_id, names in sheet_to_names.items():
        chosen_asset = None
        page_name = next((name for name in names if re.fullmatch(r"Page\d+b?", name)), None)
        contrib_name = next((name for name in names if re.fullmatch(r"contri_pg\d+", name)), None)
        if page_name:
            chosen_asset = f"credits_{page_name.lower()}.png"
        elif contrib_name:
            chosen_asset = f"contributors_page{contrib_name.split('contri_pg', 1)[1]}.png"
        elif "Text" in names:
            chosen_asset = "credits_page0.png"
        elif "Black" in names:
            chosen_asset = "credits_page1.png"
        if chosen_asset and resolve_resource_file(chosen_asset):
            mapping[sheet_id] = {
                "sheetId": sheet_id,
                "assetPath": chosen_asset,
                "method": "credits-layer-name",
                "confidence": 0.98,
                "candidateScore": 50,
            }

    return mapping


def decode_pcx(path):
    data = path.read_bytes()
    if len(data) < 128:
        raise ValueError(f"PCX file too small: {path}")

    (
        manufacturer,
        _version,
        encoding,
        bits_per_pixel,
        xmin,
        ymin,
        xmax,
        ymax,
        _hdpi,
        _vdpi,
        _palette16,
        _reserved,
        color_planes,
        bytes_per_line,
        _palette_info,
        _hscreen,
        _vscreen,
        _filler,
    ) = struct.unpack("<BBBBHHHHHH48sBBHHHH54s", data[:128])

    if manufacturer != 0x0A or encoding != 1:
        raise ValueError(f"Unsupported PCX encoding in {path}")

    width = xmax - xmin + 1
    height = ymax - ymin + 1
    scanline_size = bytes_per_line * color_planes
    expected_size = scanline_size * height
    decoded = bytearray()
    cursor = 128

    while len(decoded) < expected_size and cursor < len(data):
      value = data[cursor]
      cursor += 1
      if value >= 0xC0:
          count = value & 0x3F
          if cursor >= len(data):
              break
          decoded.extend([data[cursor]] * count)
          cursor += 1
      else:
          decoded.append(value)

    if len(decoded) < expected_size:
        raise ValueError(f"Incomplete PCX decode for {path}")

    rgb = bytearray()
    if bits_per_pixel == 8 and color_planes == 1:
        if len(data) < 769 or data[-769] != 0x0C:
            raise ValueError(f"Missing 256-color palette in {path}")
        palette = data[-768:]
        for row in range(height):
            row_start = row * bytes_per_line
            row_data = decoded[row_start:row_start + width]
            for index in row_data:
                palette_offset = index * 3
                rgb.extend(palette[palette_offset:palette_offset + 3])
    elif bits_per_pixel == 8 and color_planes >= 3:
        for row in range(height):
            row_start = row * scanline_size
            red = decoded[row_start:row_start + bytes_per_line]
            green = decoded[row_start + bytes_per_line:row_start + bytes_per_line * 2]
            blue = decoded[row_start + bytes_per_line * 2:row_start + bytes_per_line * 3]
            for column in range(width):
                rgb.extend([red[column], green[column], blue[column]])
    else:
        raise ValueError(
            f"Unsupported PCX mode in {path}: {bits_per_pixel} bpp, {color_planes} planes"
        )

    return width, height, bytes(rgb)


def png_chunk(chunk_type, payload):
    crc = zlib.crc32(chunk_type + payload) & 0xFFFFFFFF
    return struct.pack(">I", len(payload)) + chunk_type + payload + struct.pack(">I", crc)


def write_png(width, height, rgb_bytes, destination):
    destination.parent.mkdir(parents=True, exist_ok=True)
    row_stride = width * 3
    scanlines = bytearray()
    for row in range(height):
        start = row * row_stride
        scanlines.append(0)
        scanlines.extend(rgb_bytes[start:start + row_stride])

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    idat = zlib.compress(bytes(scanlines), level=9)
    png = bytearray(b"\x89PNG\r\n\x1a\n")
    png.extend(png_chunk(b"IHDR", ihdr))
    png.extend(png_chunk(b"IDAT", idat))
    png.extend(png_chunk(b"IEND", b""))
    destination.write_bytes(bytes(png))


def ensure_preview_file(source_path, cache_rel_path):
    destination = CACHE_IMAGES_DIR / cache_rel_path
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() and source_path.exists() and destination.stat().st_mtime >= source_path.stat().st_mtime:
        return destination

    suffix = source_path.suffix.lower()
    if suffix == ".png":
        shutil.copy2(source_path, destination)
    elif suffix == ".pcx":
        width, height, rgb_bytes = decode_pcx(source_path)
        write_png(width, height, rgb_bytes, destination)
    else:
        raise ValueError(f"Unsupported preview source: {source_path}")
    return destination


def parse_flagged_section(data, offset):
    count, cursor = read_u32(data, offset)
    entries = []
    for _ in range(count):
        entry_id, cursor = read_u32(data, cursor)
        flag, cursor = read_u32(data, cursor)
        name_len, cursor = read_u16(data, cursor)
        name = data[cursor:cursor + name_len].decode("ascii")
        cursor += name_len
        entries.append({"id": entry_id, "sheetId": flag, "name": name})
    return entries, cursor


def parse_compact_section(data, offset):
    count, cursor = read_u32(data, offset)
    entries = []
    for _ in range(count):
        entry_id, cursor = read_u32(data, cursor)
        name_len, cursor = read_u16(data, cursor)
        name = data[cursor:cursor + name_len].decode("ascii")
        cursor += name_len
        entries.append({"id": entry_id, "name": name})
    return entries, cursor


def serialize_flagged_section(entries):
    output = bytearray()
    output.extend(pack_u32(len(entries)))
    for entry in entries:
        name_bytes = entry["name"].encode("ascii")
        output.extend(pack_u32(entry["id"]))
        output.extend(pack_u32(entry["sheetId"]))
        output.extend(pack_u16(len(name_bytes)))
        output.extend(name_bytes)
    return bytes(output)


def serialize_compact_section(entries):
    output = bytearray()
    output.extend(pack_u32(len(entries)))
    for entry in entries:
        name_bytes = entry["name"].encode("ascii")
        output.extend(pack_u32(entry["id"]))
        output.extend(pack_u16(len(name_bytes)))
        output.extend(name_bytes)
    return bytes(output)


def parse_null_frame(data, offset):
    cursor = offset
    x_position, cursor = read_f32(data, cursor)
    y_position, cursor = read_f32(data, cursor)
    x_scale, cursor = read_f32(data, cursor)
    y_scale, cursor = read_f32(data, cursor)
    delay, cursor = read_u32(data, cursor)
    visible_raw, cursor = read_u8(data, cursor)
    red_tint, cursor = read_f32(data, cursor)
    green_tint, cursor = read_f32(data, cursor)
    blue_tint, cursor = read_f32(data, cursor)
    alpha_tint, cursor = read_f32(data, cursor)
    red_offset, cursor = read_f32(data, cursor)
    green_offset, cursor = read_f32(data, cursor)
    blue_offset, cursor = read_f32(data, cursor)
    rotation, cursor = read_f32(data, cursor)
    interpolated_raw, cursor = read_u8(data, cursor)
    return (
        {
            "xPosition": exact_float(x_position),
            "yPosition": exact_float(y_position),
            "xScale": exact_float(x_scale),
            "yScale": exact_float(y_scale),
            "delay": int(delay),
            "visible": bool(visible_raw),
            "redTint": exact_float(red_tint),
            "greenTint": exact_float(green_tint),
            "blueTint": exact_float(blue_tint),
            "alphaTint": exact_float(alpha_tint),
            "redOffset": exact_float(red_offset),
            "greenOffset": exact_float(green_offset),
            "blueOffset": exact_float(blue_offset),
            "rotation": exact_float(rotation),
            "interpolated": bool(interpolated_raw),
        },
        cursor,
    )


def parse_layer_frame(data, offset):
    cursor = offset
    x_crop, cursor = read_f32(data, cursor)
    y_crop, cursor = read_f32(data, cursor)
    width, cursor = read_f32(data, cursor)
    height, cursor = read_f32(data, cursor)
    x_position, cursor = read_f32(data, cursor)
    y_position, cursor = read_f32(data, cursor)
    x_scale, cursor = read_f32(data, cursor)
    y_scale, cursor = read_f32(data, cursor)
    x_pivot, cursor = read_f32(data, cursor)
    y_pivot, cursor = read_f32(data, cursor)
    delay, cursor = read_u32(data, cursor)
    visible_raw, cursor = read_u8(data, cursor)
    red_tint, cursor = read_f32(data, cursor)
    green_tint, cursor = read_f32(data, cursor)
    blue_tint, cursor = read_f32(data, cursor)
    alpha_tint, cursor = read_f32(data, cursor)
    red_offset, cursor = read_f32(data, cursor)
    green_offset, cursor = read_f32(data, cursor)
    blue_offset, cursor = read_f32(data, cursor)
    rotation, cursor = read_f32(data, cursor)
    interpolated_raw, cursor = read_u8(data, cursor)
    return (
        {
            "xCrop": exact_float(x_crop),
            "yCrop": exact_float(y_crop),
            "width": exact_float(width),
            "height": exact_float(height),
            "xPosition": exact_float(x_position),
            "yPosition": exact_float(y_position),
            "xScale": exact_float(x_scale),
            "yScale": exact_float(y_scale),
            "xPivot": exact_float(x_pivot),
            "yPivot": exact_float(y_pivot),
            "delay": int(delay),
            "visible": bool(visible_raw),
            "redTint": exact_float(red_tint),
            "greenTint": exact_float(green_tint),
            "blueTint": exact_float(blue_tint),
            "alphaTint": exact_float(alpha_tint),
            "redOffset": exact_float(red_offset),
            "greenOffset": exact_float(green_offset),
            "blueOffset": exact_float(blue_offset),
            "rotation": exact_float(rotation),
            "interpolated": bool(interpolated_raw),
        },
        cursor,
    )


def serialize_null_frame(frame):
    output = bytearray()
    output.extend(pack_f32(frame["xPosition"]))
    output.extend(pack_f32(frame["yPosition"]))
    output.extend(pack_f32(frame["xScale"]))
    output.extend(pack_f32(frame["yScale"]))
    output.extend(pack_u32(frame["delay"]))
    output.extend(pack_u8(1 if frame["visible"] else 0))
    output.extend(pack_f32(frame["redTint"]))
    output.extend(pack_f32(frame["greenTint"]))
    output.extend(pack_f32(frame["blueTint"]))
    output.extend(pack_f32(frame["alphaTint"]))
    output.extend(pack_f32(frame["redOffset"]))
    output.extend(pack_f32(frame["greenOffset"]))
    output.extend(pack_f32(frame["blueOffset"]))
    output.extend(pack_f32(frame["rotation"]))
    output.extend(pack_u8(1 if frame["interpolated"] else 0))
    return bytes(output)


def serialize_layer_frame(frame):
    output = bytearray()
    output.extend(pack_f32(frame["xCrop"]))
    output.extend(pack_f32(frame["yCrop"]))
    output.extend(pack_f32(frame["width"]))
    output.extend(pack_f32(frame["height"]))
    output.extend(pack_f32(frame["xPosition"]))
    output.extend(pack_f32(frame["yPosition"]))
    output.extend(pack_f32(frame["xScale"]))
    output.extend(pack_f32(frame["yScale"]))
    output.extend(pack_f32(frame["xPivot"]))
    output.extend(pack_f32(frame["yPivot"]))
    output.extend(pack_u32(frame["delay"]))
    output.extend(pack_u8(1 if frame["visible"] else 0))
    output.extend(pack_f32(frame["redTint"]))
    output.extend(pack_f32(frame["greenTint"]))
    output.extend(pack_f32(frame["blueTint"]))
    output.extend(pack_f32(frame["alphaTint"]))
    output.extend(pack_f32(frame["redOffset"]))
    output.extend(pack_f32(frame["greenOffset"]))
    output.extend(pack_f32(frame["blueOffset"]))
    output.extend(pack_f32(frame["rotation"]))
    output.extend(pack_u8(1 if frame["interpolated"] else 0))
    return bytes(output)


def hex_bytes(data, max_len=64):
    chunk = data[:max_len]
    return " ".join(f"{value:02x}" for value in chunk)


def candidate_event_refs(header_bytes, event_lookup):
    candidates = []
    if not event_lookup:
        return candidates
    for rel_offset in range(0, max(len(header_bytes) - 3, 0), 4):
        value = struct.unpack_from("<I", header_bytes, rel_offset)[0]
        if value == 0:
            continue
        if value in event_lookup:
            candidates.append(
                {
                    "relativeOffset": rel_offset,
                    "eventId": value,
                    "eventName": event_lookup[value]["name"],
                }
            )
    return candidates


def summarize_gap_chunk(data, start, end, event_lookup):
    if end <= start:
        return None
    chunk = data[start:end]
    ascii_tokens = []
    seen = set()
    for match in ASCII_TOKEN_RE.finditer(chunk):
        token = match.group().decode("ascii", errors="ignore").strip()
        if token and token not in seen:
            seen.add(token)
            ascii_tokens.append(token)
        if len(ascii_tokens) >= 6:
            break
    event_hits = candidate_event_refs(chunk[: min(len(chunk), 64)], event_lookup)
    return {
        "startOffset": start,
        "endOffset": end,
        "length": end - start,
        "asciiTokens": ascii_tokens,
        "hexPreview": hex_bytes(chunk, 48),
        "eventCandidates": event_hits[:8],
    }


def decode_animation_header_bytes(header_bytes):
    decoded = {
        "rawLength": len(header_bytes),
        "kind": "unknown",
    }
    if len(header_bytes) != 63:
        return decoded

    cursor = 0
    frame_num_echo, cursor = read_u32(header_bytes, cursor)
    flags, cursor = read_u32(header_bytes, cursor)
    leading_flag, cursor = read_u8(header_bytes, cursor)
    x_position, cursor = read_f32(header_bytes, cursor)
    y_position, cursor = read_f32(header_bytes, cursor)
    x_scale, cursor = read_f32(header_bytes, cursor)
    y_scale, cursor = read_f32(header_bytes, cursor)
    duration_echo, cursor = read_u32(header_bytes, cursor)
    tint_flag, cursor = read_u8(header_bytes, cursor)
    red_tint, cursor = read_f32(header_bytes, cursor)
    green_tint, cursor = read_f32(header_bytes, cursor)
    blue_tint, cursor = read_f32(header_bytes, cursor)
    alpha_tint, cursor = read_f32(header_bytes, cursor)
    red_offset, cursor = read_f32(header_bytes, cursor)
    green_offset, cursor = read_f32(header_bytes, cursor)
    blue_offset, cursor = read_f32(header_bytes, cursor)
    rotation, cursor = read_f32(header_bytes, cursor)
    trailing_flag, cursor = read_u8(header_bytes, cursor)

    decoded.update(
        {
            "kind": "root-default-frame",
            "frameNumEcho": int(frame_num_echo),
            "flagsRaw": int(flags),
            "reservedFlag0": int(leading_flag),
            "xPosition": exact_float(x_position),
            "yPosition": exact_float(y_position),
            "xScale": exact_float(x_scale),
            "yScale": exact_float(y_scale),
            "durationEcho": int(duration_echo),
            "rootVisibleRaw": int(tint_flag),
            "rootVisible": bool(tint_flag),
            "redTint": exact_float(red_tint),
            "greenTint": exact_float(green_tint),
            "blueTint": exact_float(blue_tint),
            "alphaTint": exact_float(alpha_tint),
            "redOffset": exact_float(red_offset),
            "greenOffset": exact_float(green_offset),
            "blueOffset": exact_float(blue_offset),
            "rotation": exact_float(rotation),
            "rootInterpolatedRaw": int(trailing_flag),
            "rootInterpolated": bool(trailing_flag),
            "provenanceSummary": (
                "Decoded as the animation's root default frame. "
                "reservedFlag0 was always 0 in the scanned corpus. "
                "rootInterpolated can be set, but no separate root keyframe stream was observed."
            ),
        }
    )
    return decoded


def build_root_default_frame(animation, header_decoded=None):
    frame_num = int(animation["frameNum"])
    loop_flag = 1 if animation.get("loop") else 0
    flags_raw = 256 | loop_flag
    if header_decoded and header_decoded.get("kind") == "root-default-frame":
        flags_raw = int(header_decoded.get("flagsRaw", flags_raw))
    return {
        "kind": "root-default-frame",
        "frameNumEcho": int(header_decoded.get("frameNumEcho", frame_num)) if header_decoded else frame_num,
        "flagsRaw": flags_raw,
        "reservedFlag0": int(header_decoded.get("reservedFlag0", 0)) if header_decoded else 0,
        "xPosition": float(header_decoded.get("xPosition", 0.0)) if header_decoded else 0.0,
        "yPosition": float(header_decoded.get("yPosition", 0.0)) if header_decoded else 0.0,
        "xScale": float(header_decoded.get("xScale", 1.0)) if header_decoded else 1.0,
        "yScale": float(header_decoded.get("yScale", 1.0)) if header_decoded else 1.0,
        "durationEcho": int(header_decoded.get("durationEcho", frame_num)) if header_decoded else frame_num,
        "rootVisibleRaw": int(header_decoded.get("rootVisibleRaw", 1 if header_decoded.get("rootVisible", True) else 0)) if header_decoded else 1,
        "rootVisible": bool(header_decoded.get("rootVisible", True)) if header_decoded else True,
        "redTint": float(header_decoded.get("redTint", 1.0)) if header_decoded else 1.0,
        "greenTint": float(header_decoded.get("greenTint", 1.0)) if header_decoded else 1.0,
        "blueTint": float(header_decoded.get("blueTint", 1.0)) if header_decoded else 1.0,
        "alphaTint": float(header_decoded.get("alphaTint", 1.0)) if header_decoded else 1.0,
        "redOffset": float(header_decoded.get("redOffset", 0.0)) if header_decoded else 0.0,
        "greenOffset": float(header_decoded.get("greenOffset", 0.0)) if header_decoded else 0.0,
        "blueOffset": float(header_decoded.get("blueOffset", 0.0)) if header_decoded else 0.0,
        "rotation": float(header_decoded.get("rotation", 0.0)) if header_decoded else 0.0,
        "rootInterpolatedRaw": int(header_decoded.get("rootInterpolatedRaw", 1 if header_decoded.get("rootInterpolated", False) else 0)) if header_decoded else 0,
        "rootInterpolated": bool(header_decoded.get("rootInterpolated", False)) if header_decoded else False,
    }


def serialize_root_default_frame(header):
    output = bytearray()
    output.extend(pack_u32(header["frameNumEcho"]))
    output.extend(pack_u32(header["flagsRaw"]))
    output.extend(pack_u8(header["reservedFlag0"]))
    output.extend(pack_f32(header["xPosition"]))
    output.extend(pack_f32(header["yPosition"]))
    output.extend(pack_f32(header["xScale"]))
    output.extend(pack_f32(header["yScale"]))
    output.extend(pack_u32(header["durationEcho"]))
    output.extend(pack_u8(header.get("rootVisibleRaw", 1 if header["rootVisible"] else 0)))
    output.extend(pack_f32(header["redTint"]))
    output.extend(pack_f32(header["greenTint"]))
    output.extend(pack_f32(header["blueTint"]))
    output.extend(pack_f32(header["alphaTint"]))
    output.extend(pack_f32(header["redOffset"]))
    output.extend(pack_f32(header["greenOffset"]))
    output.extend(pack_f32(header["blueOffset"]))
    output.extend(pack_f32(header["rotation"]))
    output.extend(pack_u8(header.get("rootInterpolatedRaw", 1 if header["rootInterpolated"] else 0)))
    return bytes(output)


def serialize_animation_block(animation):
    debug_meta = animation.get("debug", {})
    header_decoded = debug_meta.get("headerDecoded") or {}
    header = build_root_default_frame(animation, header_decoded)
    name_bytes = animation["name"].encode("ascii")
    output = bytearray()
    output.extend(pack_u16(len(name_bytes)))
    output.extend(name_bytes)
    output.extend(serialize_root_default_frame(header))
    output.extend(pack_u32(len(animation["layerAnimations"])))
    for layer_animation in animation["layerAnimations"]:
        output.extend(pack_u32(layer_animation["layerId"]))
        output.extend(pack_u8(1 if layer_animation["visible"] else 0))
        output.extend(pack_u32(len(layer_animation["frames"])))
        for frame in layer_animation["frames"]:
            output.extend(serialize_layer_frame(frame))
    output.extend(pack_u32(len(animation["nullAnimations"])))
    for null_animation in animation["nullAnimations"]:
        output.extend(pack_u32(null_animation["nullId"]))
        output.extend(pack_u8(1 if null_animation["visible"] else 0))
        output.extend(pack_u32(len(null_animation["frames"])))
        for frame in null_animation["frames"]:
            output.extend(serialize_null_frame(frame))
    return bytes(output)


def lerp(a, b, t):
    return a + (b - a) * t


def interpolate_frame(current, next_frame, t, fields):
    output = dict(current)
    if not current.get("interpolated") or next_frame is None:
        return output
    for field in fields:
        output[field] = round_float(lerp(current[field], next_frame[field], t))
    return output


ROOT_INTERPOLATED_FIELDS = [
    "xPosition",
    "yPosition",
    "xScale",
    "yScale",
    "redTint",
    "greenTint",
    "blueTint",
    "alphaTint",
    "redOffset",
    "greenOffset",
    "blueOffset",
    "rotation",
]

LAYER_INTERPOLATED_FIELDS = ROOT_INTERPOLATED_FIELDS + ["xPivot", "yPivot"]


def expand_timeline(keyframes, frame_num, interpolated_fields):
    if not keyframes:
        return []

    output = []
    for index, frame in enumerate(keyframes):
        delay = max(int(frame.get("delay", 1)), 1)
        next_frame = keyframes[index + 1] if index + 1 < len(keyframes) else None
        if frame.get("interpolated") and next_frame:
            for step in range(delay):
                output.append(interpolate_frame(frame, next_frame, step / delay, interpolated_fields))
        else:
            output.extend(dict(frame) for _ in range(delay))

    if len(output) < frame_num:
        output.extend(dict(output[-1]) for _ in range(frame_num - len(output)))
    return output[:frame_num]


def build_animation_timeline(animation, layer_lookup, root_defaults=None):
    frame_num = max(int(animation["frameNum"]), 1)
    default_root = {
        "xPosition": 0.0,
        "yPosition": 0.0,
        "xScale": 1.0,
        "yScale": 1.0,
        "delay": frame_num,
        "visible": True,
        "redTint": 1.0,
        "greenTint": 1.0,
        "blueTint": 1.0,
        "alphaTint": 1.0,
        "redOffset": 0.0,
        "greenOffset": 0.0,
        "blueOffset": 0.0,
        "rotation": 0.0,
        "interpolated": False,
    }
    if root_defaults:
        default_root.update(
            {
                "xPosition": root_defaults.get("xPosition", default_root["xPosition"]),
                "yPosition": root_defaults.get("yPosition", default_root["yPosition"]),
                "xScale": root_defaults.get("xScale", default_root["xScale"]),
                "yScale": root_defaults.get("yScale", default_root["yScale"]),
                "visible": bool(root_defaults.get("rootVisible", default_root["visible"])),
                "redTint": root_defaults.get("redTint", default_root["redTint"]),
                "greenTint": root_defaults.get("greenTint", default_root["greenTint"]),
                "blueTint": root_defaults.get("blueTint", default_root["blueTint"]),
                "alphaTint": root_defaults.get("alphaTint", default_root["alphaTint"]),
                "redOffset": root_defaults.get("redOffset", default_root["redOffset"]),
                "greenOffset": root_defaults.get("greenOffset", default_root["greenOffset"]),
                "blueOffset": root_defaults.get("blueOffset", default_root["blueOffset"]),
                "rotation": root_defaults.get("rotation", default_root["rotation"]),
                "interpolated": bool(root_defaults.get("rootInterpolated", default_root["interpolated"])),
                "delay": int(root_defaults.get("durationEcho", frame_num)),
            }
        )
    root_frames = animation.get("rootFrames") or []
    if root_frames:
        root_timeline = expand_timeline(root_frames, frame_num, ROOT_INTERPOLATED_FIELDS)
    else:
        root_timeline = [default_root for _ in range(frame_num)]

    layer_timelines = {}
    for layer_animation in animation["layerAnimations"]:
        if layer_animation["frames"]:
            layer_timelines[layer_animation["layerId"]] = expand_timeline(
                layer_animation["frames"],
                frame_num,
                LAYER_INTERPOLATED_FIELDS,
            )

    null_timelines = {}
    for null_animation in animation["nullAnimations"]:
        if null_animation["frames"]:
            null_timelines[null_animation["nullId"]] = expand_timeline(
                null_animation["frames"],
                frame_num,
                ROOT_INTERPOLATED_FIELDS,
            )

    timeline_frames = []
    for frame_index in range(frame_num):
        root = root_timeline[frame_index]
        layers = []
        for layer_id, frames in layer_timelines.items():
            frame = dict(frames[frame_index])
            layer_info = layer_lookup.get(layer_id, {})
            frame["layerId"] = layer_id
            frame["layerName"] = layer_info.get("name", str(layer_id))
            frame["sheetId"] = layer_info.get("sheetId", 0)
            layers.append(frame)

        nulls = []
        for null_id, frames in null_timelines.items():
            frame = dict(frames[frame_index])
            frame["nullId"] = null_id
            nulls.append(frame)

        timeline_frames.append(
            {
                "frameIndex": frame_index,
                "root": dict(root),
                "layers": layers,
                "nulls": nulls,
            }
        )

    return timeline_frames


def parse_animation_block(data, offset, end, layer_lookup, event_lookup):
    cursor = offset
    name_len, cursor = read_u16(data, cursor)
    if cursor + name_len > end:
        raise ValueError("Animation name overran group boundary")
    name_bytes = data[cursor:cursor + name_len]
    if not name_bytes or any(b < 32 or b > 126 for b in name_bytes):
        raise ValueError("Invalid animation name")
    name = name_bytes.decode("ascii")
    cursor += name_len
    frame_num, cursor = read_u32(data, cursor)
    flags, cursor = read_u32(data, cursor)
    loop_raw = flags & 0xFF
    if frame_num > 10000 or loop_raw > 1:
        raise ValueError("Animation payload header was not plausible")
    layer_count_offset = offset + 2 + name_len + 63
    if layer_count_offset + 4 > end:
        raise ValueError("Animation payload overran group boundary")
    header_bytes = data[offset + 2 + name_len:layer_count_offset]
    layer_count = struct.unpack_from("<I", data, layer_count_offset)[0]
    if layer_count > len(layer_lookup) + 8:
        raise ValueError("Layer count was not plausible")
    cursor = layer_count_offset + 4
    layer_animations = []
    for _ in range(layer_count):
        layer_id, cursor = read_u32(data, cursor)
        visible_raw, cursor = read_u8(data, cursor)
        frame_count, cursor = read_u32(data, cursor)
        if frame_count > frame_num + 16:
            raise ValueError("Layer frame count was not plausible")
        frames = []
        for _ in range(frame_count):
            frame, cursor = parse_layer_frame(data, cursor)
            frames.append(frame)
        layer_animations.append(
            {
                "layerId": layer_id,
                "visible": bool(visible_raw),
                "frames": frames,
            }
        )

    null_count, cursor = read_u32(data, cursor)
    null_animations = []
    for _ in range(null_count):
        null_id, cursor = read_u32(data, cursor)
        visible_raw, cursor = read_u8(data, cursor)
        frame_count, cursor = read_u32(data, cursor)
        if frame_count > frame_num + 16:
            raise ValueError("Null frame count was not plausible")
        frames = []
        for _ in range(frame_count):
            frame, cursor = parse_null_frame(data, cursor)
            frames.append(frame)
        null_animations.append(
            {
                "nullId": null_id,
                "visible": bool(visible_raw),
                "frames": frames,
            }
        )

    animation = {
        "name": name,
        "offset": offset,
        "endOffset": cursor,
        "frameNum": int(frame_num),
        "loop": bool(loop_raw),
        "layerAnimations": layer_animations,
        "nullAnimations": null_animations,
        "debug": {
            "headerLength": len(header_bytes),
            "headerHex": hex_bytes(header_bytes),
            "headerWords": [
                struct.unpack_from("<I", header_bytes, rel)[0]
                for rel in range(0, min(len(header_bytes) - (len(header_bytes) % 4), 24), 4)
            ],
            "headerDecoded": decode_animation_header_bytes(header_bytes),
            "layerCountOffset": layer_count_offset,
            "flags": int(flags),
            "eventCandidates": candidate_event_refs(header_bytes, event_lookup),
            "rawBlockHex": bytes_to_hex(data[offset:cursor]),
            "rawBlockSha256": sha256_hex(data[offset:cursor]),
        },
    }
    root_defaults = animation["debug"]["headerDecoded"] if animation["debug"]["headerDecoded"].get("kind") == "root-default-frame" else None
    known_layers = sum(1 for layer in layer_animations if layer["layerId"] in layer_lookup)
    active_layers = sum(1 for layer in layer_animations if layer["frames"])
    confidence = 0.3
    if layer_animations:
        confidence += 0.3 * (known_layers / len(layer_animations))
        confidence += 0.2 * (active_layers / len(layer_animations))
    if null_animations:
        confidence += 0.1
    if animation["debug"]["eventCandidates"]:
        confidence += 0.05
    animation["debug"]["parseConfidence"] = round_float(clamp(confidence, 0.0, 0.99))
    animation["timelineFrames"] = build_animation_timeline(animation, layer_lookup, root_defaults=root_defaults)
    animation["endOffset"] = cursor
    return animation, cursor


def read_length_prefixed_ascii_name(data, offset, end, max_len=48):
    if offset + 2 > end:
        return None
    name_len = struct.unpack_from("<H", data, offset)[0]
    if name_len < 1 or name_len > max_len or offset + 2 + name_len > end:
        return None
    name_bytes = data[offset + 2:offset + 2 + name_len]
    if not name_bytes or any(value < 32 or value > 126 for value in name_bytes):
        return None
    return name_bytes.decode("ascii"), name_len


def describe_grouped_trailing_footer(data, offset, end):
    if offset == end:
        return {
            "kind": "none",
            "length": 0,
            "hex": "",
        }
    trailing = data[offset:end]
    if len(trailing) == 4 and trailing == b"\x00\x00\x00\x00":
        return {
            "kind": "zero-u32",
            "length": 4,
            "hex": bytes_to_hex(trailing),
        }
    if len(trailing) <= 32 and (b"gfx/." in trailing or b"gfx\\." in trailing):
        return {
            "kind": "group-footer",
            "length": len(trailing),
            "hex": bytes_to_hex(trailing),
        }
    return None


def scan_grouped_child_headers(data, start, end):
    headers = []
    cursor = start
    while cursor + 10 <= end:
        parsed_name = read_length_prefixed_ascii_name(data, cursor, end)
        if not parsed_name:
            cursor += 1
            continue
        name, name_len = parsed_name
        if name.startswith("gfx/") or name.startswith("gfx\\"):
            cursor += 1
            continue
        header_end = cursor + 2 + name_len + 8
        if header_end > end:
            cursor += 1
            continue
        frame_num = struct.unpack_from("<I", data, cursor + 2 + name_len)[0]
        flags = struct.unpack_from("<I", data, cursor + 2 + name_len + 4)[0]
        if frame_num < 1 or frame_num > 10000:
            cursor += 1
            continue
        if (flags & 0xFF) > 1 or (flags >> 8) > 0xFF:
            cursor += 1
            continue
        if headers and cursor - headers[-1]["offset"] < 8:
            cursor += 1
            continue
        headers.append(
            {
                "offset": cursor,
                "name": name,
                "nameLength": name_len,
                "frameNum": int(frame_num),
                "flags": int(flags),
                "loop": bool(flags & 0xFF),
                "groupHint": int(flags >> 8),
            }
        )
        cursor += max(2 + name_len, 1)
    return headers


def parse_grouped_animation_child(
    data,
    offset,
    end,
    layer_lookup,
    null_lookup,
    event_lookup,
    container_name,
    container_child_count,
):
    parsed_name = read_length_prefixed_ascii_name(data, offset, end)
    if not parsed_name:
        return None
    name, name_len = parsed_name
    cursor = offset + 2 + name_len
    frame_num, cursor = read_u32(data, cursor)
    flags, cursor = read_u32(data, cursor)
    if frame_num < 1 or frame_num > 10000:
        return None
    header_end = offset + 2 + name_len + 63
    if header_end > end:
        return None
    header_bytes = data[offset + 2 + name_len:header_end]
    header_decoded = decode_animation_header_bytes(header_bytes)
    max_root_count = min(max(int(frame_num) + 4, 8), 40, max((end - header_end) // 54, 0))
    best_candidate = None

    for root_count in range(max_root_count + 1):
        section_cursor = header_end
        root_frames = []
        try:
            for _ in range(root_count):
                root_frame, section_cursor = parse_null_frame(data, section_cursor)
                root_frames.append(root_frame)
            if section_cursor + 4 > end:
                continue
            layer_count, section_cursor = read_u32(data, section_cursor)
            if layer_count > len(layer_lookup) + 4:
                continue

            layer_animations = []
            for _ in range(layer_count):
                layer_id, section_cursor = read_u32(data, section_cursor)
                visible_raw, section_cursor = read_u8(data, section_cursor)
                frame_count, section_cursor = read_u32(data, section_cursor)
                if frame_count > frame_num + 64:
                    raise ValueError("Layer frame count was not plausible")
                frames = []
                for _ in range(frame_count):
                    frame, section_cursor = parse_layer_frame(data, section_cursor)
                    frames.append(frame)
                layer_animations.append(
                    {
                        "layerId": layer_id,
                        "visible": bool(visible_raw),
                        "frames": frames,
                    }
                )

            null_animations = []
            null_count = 0
            if section_cursor + 4 <= end:
                peek_null_count = struct.unpack_from("<I", data, section_cursor)[0]
                if peek_null_count <= len(null_lookup) + 4:
                    null_count, section_cursor = read_u32(data, section_cursor)
                    for _ in range(null_count):
                        null_id, section_cursor = read_u32(data, section_cursor)
                        visible_raw, section_cursor = read_u8(data, section_cursor)
                        frame_count, section_cursor = read_u32(data, section_cursor)
                        if frame_count > frame_num + 64:
                            raise ValueError("Null frame count was not plausible")
                        frames = []
                        for _ in range(frame_count):
                            frame, section_cursor = parse_null_frame(data, section_cursor)
                            frames.append(frame)
                        null_animations.append(
                            {
                                "nullId": null_id,
                                "visible": bool(visible_raw),
                                "frames": frames,
                            }
                        )

            event_timeline = []
            event_count = 0
            if section_cursor + 4 <= end:
                peek_event_count = struct.unpack_from("<I", data, section_cursor)[0]
                remaining_after_count = end - (section_cursor + 4)
                if peek_event_count <= len(event_lookup) + 8 and remaining_after_count >= peek_event_count * 8:
                    event_count, section_cursor = read_u32(data, section_cursor)
                    for _ in range(event_count):
                        event_id, section_cursor = read_u32(data, section_cursor)
                        event_frame, section_cursor = read_u32(data, section_cursor)
                        event_entry = {
                            "frameIndexHint": min(frame_num - 1, int(event_frame)) if frame_num > 0 else 0,
                            "eventId": int(event_id),
                            "eventName": event_lookup.get(int(event_id), {}).get("name", str(int(event_id))),
                            "source": "grouped-event-table",
                        }
                        event_timeline.append(event_entry)

            footer = describe_grouped_trailing_footer(data, section_cursor, end)
            if footer is None:
                continue

            known_layer_ids = sum(1 for animation in layer_animations if animation["layerId"] in layer_lookup)
            known_null_ids = sum(1 for animation in null_animations if animation["nullId"] in null_lookup)
            known_event_ids = sum(
                1 for event_entry in event_timeline if event_entry["eventId"] in event_lookup
            )
            score = 0
            score += 10 if layer_count == len(layer_lookup) else -abs(layer_count - len(layer_lookup))
            score += known_layer_ids * 3
            score += sum(1 for animation in layer_animations if animation["frames"])
            score += 6 if null_count == len(null_lookup) else -abs(null_count - len(null_lookup))
            score += known_null_ids * 2
            score += known_event_ids * 2
            score += root_count
            score -= footer["length"]

            candidate = {
                "score": score,
                "name": name,
                "offset": offset,
                "endOffset": section_cursor,
                "chunkEndOffset": end,
                "frameNum": int(frame_num),
                "loop": bool(flags & 0xFF),
                "rootFrames": root_frames,
                "layerAnimations": layer_animations,
                "nullAnimations": null_animations,
                "eventTimeline": event_timeline,
                "debug": {
                    "groupedContainer": True,
                    "containerName": container_name,
                    "containerChildCount": int(container_child_count),
                    "groupHint": int(flags >> 8),
                    "flags": int(flags),
                    "parseConfidence": 0.72 if footer["length"] <= 4 else 0.68,
                    "rawBlockHex": bytes_to_hex(data[offset:section_cursor]),
                    "rawBlockSha256": sha256_hex(data[offset:section_cursor]),
                    "eventCandidates": [],
                    "eventTimeline": event_timeline,
                    "headerLength": len(header_bytes),
                    "headerHex": bytes_to_hex(header_bytes),
                    "headerWords": [
                        struct.unpack_from("<I", header_bytes, rel)[0]
                        for rel in range(0, min(len(header_bytes) - (len(header_bytes) % 4), 24), 4)
                    ],
                    "headerDecoded": header_decoded,
                    "rootKeyframeCount": root_count,
                    "layerCount": int(layer_count),
                    "nullCount": int(null_count),
                    "eventCount": int(event_count),
                    "footer": footer,
                },
            }
            candidate["timelineFrames"] = build_animation_timeline(
                candidate,
                layer_lookup,
                root_defaults=header_decoded if header_decoded.get("kind") == "root-default-frame" else None,
            )
            if best_candidate is None or candidate["score"] > best_candidate["score"]:
                best_candidate = candidate
        except Exception:
            continue

    return best_candidate


def parse_grouped_animation_container(data, offset, end, layer_lookup, null_lookup, event_lookup):
    container = read_length_prefixed_ascii_name(data, offset, end)
    if not container:
        return None
    container_name, container_name_len = container
    if offset + 2 + container_name_len + 4 > end:
        return None
    child_count = struct.unpack_from("<I", data, offset + 2 + container_name_len)[0]
    if child_count < 1 or child_count > 64:
        return None
    child_start = offset + 2 + container_name_len + 4
    headers = scan_grouped_child_headers(data, child_start, end)
    if len(headers) < child_count:
        return None
    headers = headers[:child_count]

    animations = []
    parsed_bytes = child_start - offset

    for index, header in enumerate(headers):
        next_offset = headers[index + 1]["offset"] if index + 1 < len(headers) else end
        if next_offset <= header["offset"]:
            return None
        animation = parse_grouped_animation_child(
            data,
            header["offset"],
            next_offset,
            layer_lookup,
            null_lookup,
            event_lookup,
            container_name,
            int(child_count),
        )
        if animation is None:
            parsed_bytes += next_offset - header["offset"]
            animations.append(
                {
                    "name": header["name"],
                    "offset": header["offset"],
                    "endOffset": next_offset,
                    "frameNum": header["frameNum"],
                    "loop": header["loop"],
                    "layerAnimations": [],
                    "nullAnimations": [],
                    "timelineFrames": [],
                    "debug": {
                        "groupedContainer": True,
                        "containerName": container_name,
                        "containerChildCount": int(child_count),
                        "groupHint": header["groupHint"],
                        "flags": header["flags"],
                        "parseConfidence": 0.35,
                        "rawBlockHex": bytes_to_hex(data[header["offset"]:next_offset]),
                        "rawBlockSha256": sha256_hex(data[header["offset"]:next_offset]),
                        "eventCandidates": [],
                        "eventTimeline": [],
                        "headerLength": 0,
                        "headerHex": "",
                        "headerWords": [],
                        "headerDecoded": {},
                    },
                }
            )
        else:
            parsed_bytes += max(animation["endOffset"] - header["offset"], 0)
            animations.append(animation)

    total_bytes = max(end - offset, 1)
    return {
        "animations": animations,
        "debug": {
            "tailStartOffset": offset,
            "tailEndOffset": end,
            "attemptCount": 0,
            "successCount": len(animations),
            "failureSamples": [],
            "parsedCoverage": round_float(clamp(parsed_bytes / total_bytes, 0.0, 1.0)),
            "gaps": [],
            "successRanges": [
                {"startOffset": animation["offset"], "endOffset": animation["endOffset"], "name": animation["name"]}
                for animation in animations[:24]
            ],
            "mode": "grouped-container-fallback",
            "containerName": container_name,
            "containerChildCount": int(child_count),
            "childHeaders": headers[:24],
        },
    }


def parse_animations_tail_debug(data, offset, end, layer_lookup, null_lookup, event_lookup):
    animations = []
    cursor = offset
    attempts = 0
    failures = []
    success_ranges = []
    while cursor + 8 < end:
        while cursor < end and data[cursor] == 0:
            cursor += 1
        if cursor + 8 >= end:
            break
        attempts += 1
        try:
            animation, next_cursor = parse_animation_block(data, cursor, end, layer_lookup, event_lookup)
        except Exception as exc:
            if len(failures) < 24:
                failures.append({"offset": cursor, "reason": str(exc)})
            cursor += 1
            continue
        if animation["layerAnimations"] or animation["nullAnimations"]:
            animations.append(animation)
            success_ranges.append((animation["offset"], animation["endOffset"], animation["name"]))
        if next_cursor <= cursor:
            break
        cursor = next_cursor

    gaps = []
    previous = offset
    for start, finish, _name in success_ranges:
        gap = summarize_gap_chunk(data, previous, start, event_lookup)
        if gap and gap["length"] >= 4:
            gaps.append(gap)
        previous = finish
    final_gap = summarize_gap_chunk(data, previous, end, event_lookup)
    if final_gap and final_gap["length"] >= 4:
        gaps.append(final_gap)

    parsed_bytes = sum(finish - start for start, finish, _name in success_ranges)
    total_bytes = max(end - offset, 1)
    result = {
        "animations": animations,
        "debug": {
            "tailStartOffset": offset,
            "tailEndOffset": end,
            "attemptCount": attempts,
            "successCount": len(animations),
            "failureSamples": failures,
            "parsedCoverage": round_float(parsed_bytes / total_bytes),
            "gaps": gaps[:12],
            "successRanges": [
                {"startOffset": start, "endOffset": finish, "name": name}
                for start, finish, name in success_ranges[:24]
            ],
        },
    }
    grouped_result = None
    if not animations or result["debug"]["parsedCoverage"] < 0.5:
        grouped_result = parse_grouped_animation_container(data, offset, end, layer_lookup, null_lookup, event_lookup)
    if grouped_result:
        grouped_coverage = grouped_result["debug"].get("parsedCoverage", 0.0)
        direct_coverage = result["debug"].get("parsedCoverage", 0.0)
        if (
            not animations
            or grouped_coverage > direct_coverage + 0.1
            or len(grouped_result["animations"]) > len(animations)
        ):
            return grouped_result
    return result


def infer_spritesheet_mapping(entries, index):
    current = entries[index]
    special_mapping = infer_special_sheet_mapping(current)
    if special_mapping is not None:
        return special_mapping
    sheet_ids = sorted({layer["sheetId"] for layer in current["layers"]})
    if not sheet_ids:
        return []

    max_sheet_id = max(sheet_ids)
    mapping = [None] * (max_sheet_id + 1)
    mapping[max_sheet_id] = {
        "sheetId": max_sheet_id,
        "assetPath": current["assetPath"],
        "method": "primary-asset",
        "confidence": 0.92,
        "candidateScore": path_similarity_score(current["assetPath"], current["assetPath"]),
    }
    candidates = []
    for candidate in reversed(entries[:index]):
        if not candidate["resourcePath"]:
            continue
        score = path_similarity_score(current["assetPath"], candidate["assetPath"])
        candidates.append((score, candidate["id"], candidate["assetPath"]))
        if len(candidates) >= 16:
            break

    used_paths = {current["assetPath"]}
    for sheet_id in range(max_sheet_id - 1, -1, -1):
        chosen = None
        for score, _candidate_id, asset_path in candidates:
            if asset_path in used_paths:
                continue
            chosen = (score, asset_path)
            break
        if chosen:
            score, asset_path = chosen
            used_paths.add(asset_path)
            mapping[sheet_id] = {
                "sheetId": sheet_id,
                "assetPath": asset_path,
                "method": "scored-backfill",
                "confidence": round_float(clamp(0.35 + (score / 40.0), 0.0, 0.88)),
                "candidateScore": score,
            }
        else:
            mapping[sheet_id] = {
                "sheetId": sheet_id,
                "assetPath": None,
                "method": "unresolved",
                "confidence": 0.0,
                "candidateScore": 0,
            }
    return mapping


def is_tiny_reference_entry(entry):
    return (
        not entry["layers"]
        and not entry["nulls"]
        and not entry["events"]
        and (entry["groupEndOffset"] - entry["animationDataOffset"]) <= 16
    )


def normalize_slashes(value):
    return value.replace("\\", "/")


def is_probable_split_actor_reference(entry, follower, matched_sheet):
    if follower["assetOffset"] != entry["groupEndOffset"]:
        return False
    if matched_sheet.get("sheetId") != 0:
        return False

    entry_path = normalize_slashes(entry["assetPath"]).lower()
    follower_path = normalize_slashes(follower["assetPath"]).lower()
    entry_stem = Path(entry_path).stem.lower()
    follower_stem = Path(follower_path).stem.lower()
    entry_parent = str(Path(entry_path).parent).lower()
    follower_parent = str(Path(follower_path).parent).lower()

    is_boss_reference = (
        "/bosses/" in f"/{entry_path}"
        or entry_stem.startswith("boss_")
        or "ultragreed" in entry_stem
        or "momleg" in entry_stem
        or "ragman" in entry_stem
        or "monstro" in entry_stem
    )
    if not is_boss_reference:
        return False

    if follower_stem in {"shadow", "glow"}:
        return True
    if follower_stem.endswith("_body") or follower_stem.endswith("body"):
        return True
    if follower_parent == entry_parent:
        return True
    return False


def link_reference_entries(entries):
    by_id = {entry["id"]: entry for entry in entries}
    for entry in entries:
        entry["linkedActorId"] = None
        entry["linkedActorReason"] = None

    for index, entry in enumerate(entries[:-1]):
        if not is_tiny_reference_entry(entry):
            continue
        follower = entries[index + 1]
        if not follower["layers"]:
            continue
        follower_mapping = follower.get("spritesheetMapping") or []
        matched_sheet = next(
            (
                mapping
                for mapping in follower_mapping
                if mapping.get("assetPath") == entry["assetPath"]
            ),
            None,
        )
        if not matched_sheet:
            continue
        if follower["assetPath"] == entry["assetPath"]:
            continue
        if not is_probable_split_actor_reference(entry, follower, matched_sheet):
            continue
        entry["linkedActorId"] = follower["id"]
        entry["linkedActorReason"] = "follower-sheet-alias"

    for entry in entries:
        linked_actor_id = entry.get("linkedActorId")
        if linked_actor_id is not None:
            entry["linkedActorPath"] = by_id[linked_actor_id]["assetPath"]
        else:
            entry["linkedActorPath"] = None
    return entries


def parse_actor_entries():
    data = ANIMATIONS_B_PATH.read_bytes()
    matches = [match for match in ASSET_RE.finditer(data)]
    entries = []

    for index, match in enumerate(matches):
        primary_path = match.group().decode("ascii")
        cursor = match.end()
        try:
            layers, cursor = parse_flagged_section(data, cursor)
            nulls, cursor = parse_compact_section(data, cursor)
            events, cursor = parse_compact_section(data, cursor)
        except Exception:
            layers = []
            nulls = []
            events = []
        resource_path = resolve_resource_file(primary_path)
        next_offset = matches[index + 1].start() if index + 1 < len(matches) else len(data)
        entry = {
            "id": len(entries),
            "assetPath": primary_path,
            "assetOffset": match.start(),
            "groupEndOffset": next_offset,
            "resourcePath": str(resource_path) if resource_path else None,
            "resourceExists": bool(resource_path),
            "layers": layers,
            "nulls": nulls,
            "events": events,
            "animationDataOffset": cursor,
        }
        entries.append(entry)
        entry["spritesheetMapping"] = infer_spritesheet_mapping(entries, entry["id"])
        entry["spritesheets"] = [item["assetPath"] for item in entry["spritesheetMapping"]]
    return link_reference_entries(entries)


def build_detail_payload(entry, entries=None, include_animations=True):
    source_entry = entry
    if entries is not None and entry.get("linkedActorId") is not None:
        source_entry = entries[int(entry["linkedActorId"])]
    preview_rel_paths = []
    spritesheet_details = []
    for sheet_id, sheet_mapping in enumerate(source_entry["spritesheetMapping"]):
        asset_path = sheet_mapping["assetPath"]
        resource = resolve_resource_file(asset_path) if asset_path else None
        preview_rel = None
        if resource:
            normalized = normalize_resource_path(asset_path)
            preview_rel = str(Path(normalized).with_suffix(".png"))
        preview_rel_paths.append(preview_rel)
        spritesheet_details.append(
            {
                "sheetId": sheet_id,
                "assetPath": asset_path,
                "resourcePath": str(resource) if resource else None,
                "resourceExists": bool(resource),
                "previewCachePath": preview_rel,
                "mappingMethod": sheet_mapping["method"],
                "mappingConfidence": sheet_mapping["confidence"],
                "mappingScore": sheet_mapping["candidateScore"],
            }
        )

    detail = {
        "id": entry["id"],
        "assetPath": entry["assetPath"],
        "assetOffset": entry["assetOffset"],
        "groupEndOffset": entry["groupEndOffset"],
        "resourcePath": entry["resourcePath"],
        "resourceExists": entry["resourceExists"],
        "previewable": any(path is not None for path in preview_rel_paths),
        "layers": source_entry["layers"],
        "nulls": source_entry["nulls"],
        "events": source_entry["events"],
        "spritesheets": spritesheet_details,
        "animations": [],
        "fps": FRAME_RATE,
        "classification": "actor",
        "debug": {
            "animationDataOffset": source_entry["animationDataOffset"],
            "sheetMapping": source_entry["spritesheetMapping"],
            "tail": None,
            "linkedActorId": entry.get("linkedActorId"),
            "linkedActorPath": entry.get("linkedActorPath"),
            "linkedActorReason": entry.get("linkedActorReason"),
        },
    }
    if include_animations:
        data = ANIMATIONS_B_PATH.read_bytes()
        layer_lookup = {layer["id"]: layer for layer in source_entry["layers"]}
        null_lookup = {null["id"]: null for null in source_entry["nulls"]}
        event_lookup = {event["id"]: event for event in source_entry["events"]}
        tail_result = parse_animations_tail_debug(
            data,
            source_entry["animationDataOffset"],
            source_entry["groupEndOffset"],
            layer_lookup,
            null_lookup,
            event_lookup,
        )
        detail["animations"] = tail_result["animations"]
        detail["debug"]["tail"] = tail_result["debug"]
        for animation in detail["animations"]:
            debug_meta = animation.get("debug", {})
            existing_event_timeline = list(debug_meta.get("eventTimeline") or [])
            debug_meta["eventTimeline"] = existing_event_timeline + [
                {
                    "frameIndexHint": min(animation["frameNum"] - 1, candidate["relativeOffset"] // 4)
                    if animation["frameNum"] > 0 else 0,
                    "eventId": candidate["eventId"],
                    "eventName": candidate["eventName"],
                    "source": "header-candidate",
                }
                for candidate in debug_meta.get("eventCandidates", [])
            ]
        if entry.get("linkedActorId") is not None:
            detail["classification"] = "linked-reference-actor"
        elif not detail["layers"] and not detail["nulls"] and not detail["events"] and not detail["animations"]:
            detail["classification"] = "reference-sheet"
        detail["validation"] = validate_detail_payload(detail)
    else:
        if entry.get("linkedActorId") is not None:
            detail["classification"] = "linked-reference-actor"
        detail["validation"] = None
    return detail


def build_index_payload(details, source_mtime, source_size):
    assets = []
    for detail in details:
        assets.append(
            {
                "id": detail["id"],
                "assetPath": detail["assetPath"],
                "assetOffset": detail["assetOffset"],
                "resourceExists": detail["resourceExists"],
                "resourcePath": detail["resourcePath"],
                "previewable": detail["previewable"],
                "layerCount": len(detail["layers"]),
                "nullCount": len(detail["nulls"]),
                "eventCount": len(detail["events"]),
                "animationCount": 0,
            }
        )

    return {
        "meta": {
            "cacheVersion": CACHE_VERSION,
            "builtAt": int(time.time()),
            "animationsPath": str(ANIMATIONS_B_PATH),
            "resourcesPath": str(RESOURCES_ROOT),
            "sourceMtime": source_mtime,
            "sourceSize": source_size,
        },
        "assetCount": len(assets),
        "assets": assets,
    }


def validate_detail_payload(detail):
    warnings = []
    animations = detail.get("animations", [])
    spritesheets = detail.get("spritesheets", [])
    debug_tail = detail.get("debug", {}).get("tail") or {}
    classification = detail.get("classification", "actor")
    drawable_animation_count = 0
    event_candidate_count = 0
    parsed_coverage = debug_tail.get("parsedCoverage")

    missing_sheets = [sheet["sheetId"] for sheet in spritesheets if not sheet["resourceExists"]]
    if missing_sheets:
        warnings.append(f"Missing spritesheet resources for sheet ids: {', '.join(map(str, missing_sheets))}")

    for animation in animations:
        if any(frame["layers"] for frame in animation.get("timelineFrames", [])):
            drawable_animation_count += 1
        event_candidate_count += len(animation.get("debug", {}).get("eventCandidates", []))
    grouped_only = bool(animations) and all(animation.get("debug", {}).get("groupedContainer") for animation in animations)

    if classification == "reference-sheet":
        return {
            "warnings": [],
            "stats": {
                "animationCount": 0,
                "drawableAnimationCount": 0,
                "eventCandidateCount": 0,
                "parsedCoverage": parsed_coverage,
            },
        }

    if not animations:
        warnings.append("No animations parsed from the actor tail.")
    elif grouped_only and drawable_animation_count == 0:
        warnings.append("Grouped animation container recognized, but no drawable timelines were recovered.")
    elif drawable_animation_count == 0:
        warnings.append("Animations parsed, but none produced drawable layer timeline frames.")

    if parsed_coverage is not None and parsed_coverage < 0.08:
        warnings.append(f"Low parsed tail coverage: {parsed_coverage}")

    failure_count = len(debug_tail.get("failureSamples") or [])
    parsed_coverage = debug_tail.get("parsedCoverage")
    if (
        failure_count >= 12
        and (parsed_coverage is None or parsed_coverage < 0.85)
        and drawable_animation_count < max(len(animations) // 2, 1)
    ):
        warnings.append("Many parse failures were encountered while scanning the actor tail.")

    low_confidence = [
        animation["name"]
        for animation in animations
        if animation.get("debug", {}).get("parseConfidence", 0.0) < 0.5
    ]
    if low_confidence:
        warnings.append(f"Low-confidence animations: {', '.join(low_confidence[:6])}")

    unresolved_mapping = [
        str(sheet["sheetId"])
        for sheet in spritesheets
        if sheet.get("mappingConfidence", 0.0) < 0.2
    ]
    if unresolved_mapping:
        warnings.append(f"Unresolved or weak sheet mapping on sheet ids: {', '.join(unresolved_mapping)}")

    return {
        "warnings": warnings,
        "stats": {
            "animationCount": len(animations),
            "drawableAnimationCount": drawable_animation_count,
            "eventCandidateCount": event_candidate_count,
            "parsedCoverage": parsed_coverage,
        },
    }


def save_json(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")


def load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def cache_is_fresh():
    if not CACHE_INDEX_PATH.exists():
        return False
    try:
        payload = json.loads(CACHE_INDEX_PATH.read_text(encoding="utf-8"))
    except Exception:
        return False
    meta = payload.get("meta", {})
    source = ANIMATIONS_B_PATH.stat()
    return (
        meta.get("cacheVersion") == CACHE_VERSION
        and meta.get("animationsPath") == str(ANIMATIONS_B_PATH)
        and meta.get("sourceSize") == source.st_size
        and meta.get("sourceMtime") == int(source.st_mtime)
    )


def emit_progress(progress, stage, current, total, message):
    if progress:
        progress(
            {
                "type": "progress",
                "stage": stage,
                "current": current,
                "total": total,
                "message": message,
            }
        )


def ensure_cache(force=False, progress=None):
    CACHE_ROOT.mkdir(parents=True, exist_ok=True)
    CACHE_ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    CACHE_IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    emit_progress(progress, "validate", 0, 1, f"Checking {ANIMATIONS_B_PATH}")
    if not ANIMATIONS_B_PATH.exists():
        raise FileNotFoundError(f"Missing animations.b: {ANIMATIONS_B_PATH}")
    if not force and cache_is_fresh():
        emit_progress(progress, "cache", 1, 1, "Using existing cache")
        return json.loads(CACHE_INDEX_PATH.read_text(encoding="utf-8"))

    emit_progress(progress, "parse", 0, 1, "Scanning actor groups")
    entries = parse_actor_entries()
    emit_progress(progress, "parse", 1, 1, f"Found {len(entries)} actor groups")
    details = [build_detail_payload(entry, entries=entries, include_animations=False) for entry in entries]
    source = ANIMATIONS_B_PATH.stat()
    index_payload = build_index_payload(details, int(source.st_mtime), source.st_size)

    emit_progress(progress, "write", 0, len(details) + 1, "Writing cache index")
    save_json(CACHE_INDEX_PATH, index_payload)
    for detail_index, detail in enumerate(details, start=1):
        if detail_index == len(details) or detail_index % 200 == 0:
            emit_progress(
                progress,
                "write",
                detail_index,
                len(details) + 1,
                f"Indexed {detail_index}/{len(details)} actor entries",
            )
    emit_progress(progress, "done", len(details) + 1, len(details) + 1, "Cache build complete")
    return index_payload


def load_index():
    ensure_cache()
    return json.loads(CACHE_INDEX_PATH.read_text(encoding="utf-8"))


def load_asset_detail(asset_id):
    ensure_cache()
    entries = parse_actor_entries()
    return build_detail_payload(entries[int(asset_id)], entries=entries, include_animations=True)


def validate_animations(limit=None):
    ensure_cache()
    entries = parse_actor_entries()
    results = []
    target_entries = entries[:limit] if limit is not None else entries
    for entry in target_entries:
        detail = build_detail_payload(entry, entries=entries, include_animations=True)
        results.append(
            {
                "id": detail["id"],
                "assetPath": detail["assetPath"],
                "warnings": detail["validation"]["warnings"],
                "stats": detail["validation"]["stats"],
            }
        )

    warning_assets = [item for item in results if item["warnings"]]
    return {
        "assetCount": len(results),
        "warningAssetCount": len(warning_assets),
        "warningAssets": warning_assets[:100],
        "totals": {
            "animations": sum(item["stats"]["animationCount"] for item in results),
            "drawableAnimations": sum(item["stats"]["drawableAnimationCount"] for item in results),
            "eventCandidates": sum(item["stats"]["eventCandidateCount"] for item in results),
        },
    }


def ensure_asset_previews(asset_id):
    detail = load_asset_detail(asset_id)
    previews = []
    for sheet in detail["spritesheets"]:
        if not sheet["resourcePath"] or not sheet["previewCachePath"]:
            previews.append({"sheetId": sheet["sheetId"], "previewPath": None})
            continue
        preview_path = ensure_preview_file(Path(sheet["resourcePath"]), Path(sheet["previewCachePath"]))
        previews.append({"sheetId": sheet["sheetId"], "previewPath": str(preview_path)})
    return previews


def build_editable_animation_payload(animation):
    return {
        "name": animation["name"],
        "frameNum": animation["frameNum"],
        "loop": animation["loop"],
        "layerAnimations": animation["layerAnimations"],
        "nullAnimations": animation["nullAnimations"],
        "debug": {
            "headerDecoded": animation.get("debug", {}).get("headerDecoded"),
            "flags": animation.get("debug", {}).get("flags"),
            "parseConfidence": animation.get("debug", {}).get("parseConfidence"),
            "rawBlockSha256": animation.get("debug", {}).get("rawBlockSha256"),
        },
    }


def build_editable_actor_payload(asset_id):
    entries = parse_actor_entries()
    entry = entries[int(asset_id)]
    data = ANIMATIONS_B_PATH.read_bytes()
    return build_editable_actor_payload_from_entry(entry, data)


def build_editable_actor_payload_from_entry(entry, data):
    entries = parse_actor_entries()
    detail = build_detail_payload(entry, entries=entries, include_animations=True)
    actor_bytes = data[entry["assetOffset"]:entry["groupEndOffset"]]
    prefix_bytes = data[entry["assetOffset"]:entry["animationDataOffset"]]
    tail_chunks = []
    cursor = entry["animationDataOffset"]
    for animation in sorted(detail["animations"], key=lambda item: item["offset"]):
        if animation["offset"] > cursor:
            gap_bytes = data[cursor:animation["offset"]]
            tail_chunks.append(
                {
                    "type": "gap",
                    "startOffset": cursor,
                    "endOffset": animation["offset"],
                    "rawHex": bytes_to_hex(gap_bytes),
                    "rawSha256": sha256_hex(gap_bytes),
                }
            )
        raw_block = data[animation["offset"]:animation["endOffset"]]
        tail_chunks.append(
            {
                "type": "animation",
                "startOffset": animation["offset"],
                "endOffset": animation["endOffset"],
                "useRawBlockByDefault": True,
                "rawBlockHex": bytes_to_hex(raw_block),
                "rawBlockSha256": sha256_hex(raw_block),
                "parsed": build_editable_animation_payload(animation),
            }
        )
        cursor = animation["endOffset"]
    if cursor < entry["groupEndOffset"]:
        gap_bytes = data[cursor:entry["groupEndOffset"]]
        tail_chunks.append(
            {
                "type": "gap",
                "startOffset": cursor,
                "endOffset": entry["groupEndOffset"],
                "rawHex": bytes_to_hex(gap_bytes),
                "rawSha256": sha256_hex(gap_bytes),
            }
        )

    serialized_prefix = (
        entry["assetPath"].encode("ascii")
        + serialize_flagged_section(detail["layers"])
        + serialize_compact_section(detail["nulls"])
        + serialize_compact_section(detail["events"])
    )

    return {
        "schemaVersion": 1,
        "kind": "isaac-ps5-editable-actor",
        "source": {
            "animationsPath": str(ANIMATIONS_B_PATH),
            "resourcesPath": str(RESOURCES_ROOT),
        },
        "actor": {
            "id": detail["id"],
            "assetPath": detail["assetPath"],
            "assetOffset": detail["assetOffset"],
            "groupEndOffset": detail["groupEndOffset"],
            "groupLength": detail["groupEndOffset"] - detail["assetOffset"],
            "animationDataOffset": detail["debug"]["animationDataOffset"],
            "classification": detail["classification"],
            "resourcePath": detail["resourcePath"],
            "layers": detail["layers"],
            "nulls": detail["nulls"],
            "events": detail["events"],
            "spritesheets": detail["spritesheets"],
            "validation": detail["validation"],
            "rawGroupSha256": sha256_hex(actor_bytes),
            "rawPrefixHex": bytes_to_hex(prefix_bytes),
            "rawPrefixSha256": sha256_hex(prefix_bytes),
            "structuredPrefixHex": bytes_to_hex(serialized_prefix),
            "structuredPrefixSha256": sha256_hex(serialized_prefix),
            "tailChunks": tail_chunks,
        },
    }


def rebuild_actor_group_from_payload(payload, prefer_raw=True, use_structured_prefix=False):
    actor = payload["actor"]
    output = bytearray()
    force_raw_reference_sheet = (
        actor.get("classification") == "reference-sheet"
        and not actor.get("layers")
        and not actor.get("nulls")
        and not actor.get("events")
    )
    if (prefer_raw and not use_structured_prefix) or force_raw_reference_sheet:
        output.extend(hex_to_bytes(actor.get("rawPrefixHex", "")))
    else:
        output.extend(actor["assetPath"].encode("ascii"))
        output.extend(serialize_flagged_section(actor.get("layers", [])))
        output.extend(serialize_compact_section(actor.get("nulls", [])))
        output.extend(serialize_compact_section(actor.get("events", [])))

    for chunk in actor.get("tailChunks", []):
        if chunk["type"] == "gap":
            output.extend(hex_to_bytes(chunk.get("rawHex", "")))
            continue
        if chunk["type"] != "animation":
            raise ValueError(f"Unsupported tail chunk type: {chunk['type']}")
        if prefer_raw and chunk.get("useRawBlockByDefault", False) and chunk.get("rawBlockHex"):
            output.extend(hex_to_bytes(chunk["rawBlockHex"]))
        else:
            output.extend(serialize_animation_block(chunk["parsed"]))
    return bytes(output)


def save_editable_actor_bundle(asset_id):
    payload = build_editable_actor_payload(asset_id)
    destination = CACHE_EXPORT_DIR / "editable-actors" / f"{int(asset_id)}.json"
    save_json(destination, payload)
    return {
        "assetId": int(asset_id),
        "jsonPath": str(destination),
        "groupSha256": payload["actor"]["rawGroupSha256"],
    }


def sanitize_filename(value):
    return re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "_", str(value)).strip(" .") or "actor"


def sanitize_folder_name(value):
    return sanitize_filename(value).replace(".", "_")


def rebuild_actor_bundle(json_path):
    payload = load_json(json_path)
    if payload.get("kind") != "isaac-ps5-editable-actor":
        raise ValueError("Unsupported editable actor bundle")
    rebuilt = rebuild_actor_group_from_payload(
        payload,
        prefer_raw=False,
        use_structured_prefix=True,
    )
    actor = payload["actor"]
    export_dir = CACHE_EXPORT_DIR / "rebuilt-actors"
    export_dir.mkdir(parents=True, exist_ok=True)
    asset_token = sanitize_filename(actor.get("assetPath", f"actor_{actor.get('id', 'unknown')}"))
    base_name = f"{int(actor.get('id', 0)):04d}_{asset_token}"
    bin_path = export_dir / f"{base_name}.actorbin"
    json_out_path = export_dir / f"{base_name}.manifest.json"
    bin_path.write_bytes(rebuilt)
    manifest = {
        "schemaVersion": 1,
        "kind": "isaac-ps5-rebuilt-actor",
        "sourceBundlePath": str(Path(json_path).resolve()),
        "assetId": actor.get("id"),
        "assetPath": actor.get("assetPath"),
        "classification": actor.get("classification"),
        "groupLength": len(rebuilt),
        "groupSha256": sha256_hex(rebuilt),
        "originalGroupSha256": actor.get("rawGroupSha256"),
        "matchesOriginal": sha256_hex(rebuilt) == actor.get("rawGroupSha256"),
        "originalAssetOffset": actor.get("assetOffset"),
        "originalGroupEndOffset": actor.get("groupEndOffset"),
    }
    json_out_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return {
        "bundlePath": str(Path(json_path).resolve()),
        "binPath": str(bin_path),
        "manifestPath": str(json_out_path),
        "assetId": actor.get("id"),
        "assetPath": actor.get("assetPath"),
        "groupLength": len(rebuilt),
        "groupSha256": manifest["groupSha256"],
        "matchesOriginal": manifest["matchesOriginal"],
    }


def parse_sfo_bytes(data):
    if len(data) < 20:
        raise ValueError("PARAM.SFO file too small")
    magic = struct.unpack_from(">I", data, 0)[0]
    version = struct.unpack_from(">I", data, 4)[0]
    key_table_start = struct.unpack_from("<I", data, 8)[0]
    data_table_start = struct.unpack_from("<I", data, 12)[0]
    entry_count = struct.unpack_from("<I", data, 16)[0]
    if magic != 0x00505346:
        raise ValueError("Invalid PARAM.SFO magic")
    entries = []
    for index in range(entry_count):
        base = 20 + (index * 16)
        key_offset, data_fmt = struct.unpack_from("<HH", data, base)
        data_len, data_max_len, data_offset = struct.unpack_from("<III", data, base + 4)
        key_start = key_table_start + key_offset
        key_end = data.index(0, key_start)
        key = data[key_start:key_end].decode("utf-8", errors="replace")
        value_start = data_table_start + data_offset
        value_raw = data[value_start:value_start + data_max_len]
        value_used = value_raw[:data_len]
        if data_fmt == 0x0404:
            value = struct.unpack("<I", value_used[:4])[0] if len(value_used) >= 4 else 0
        else:
            trimmed = value_used[:-1] if data_fmt == 0x0402 and value_used.endswith(b"\x00") else value_used
            value = trimmed.decode("utf-8", errors="replace")
        entries.append(
            {
                "key": key,
                "keyOffset": key_offset,
                "dataFmt": data_fmt,
                "dataLen": data_len,
                "dataMaxLen": data_max_len,
                "dataOffset": data_offset,
                "value": value,
                "rawDataHex": bytes_to_hex(value_raw),
            }
        )
    return {
        "magic": magic,
        "version": version,
        "keyTableStart": key_table_start,
        "dataTableStart": data_table_start,
        "entryCount": entry_count,
        "entries": entries,
    }


def load_sfo(path):
    return parse_sfo_bytes(Path(path).read_bytes())


def serialize_sfo(payload):
    entries = payload["entries"]
    key_table = bytearray()
    data_table = bytearray()
    index_table = bytearray()
    key_offsets = {}
    for entry in entries:
        key_offsets[entry["key"]] = len(key_table)
        key_table.extend(entry["key"].encode("utf-8") + b"\x00")
    while len(key_table) % 4:
        key_table.append(0)

    for entry in entries:
        data_offset = len(data_table)
        data_fmt = int(entry["dataFmt"])
        max_len = int(entry["dataMaxLen"])
        value = entry["value"]
        if data_fmt == 0x0404:
            used = pack_u32(int(value))
        else:
            encoded = str(value).encode("utf-8")
            if data_fmt == 0x0402:
                encoded += b"\x00"
            used = encoded
        if len(used) > max_len:
            raise ValueError(f"SFO value for {entry['key']} exceeds max length {max_len}")
        raw = used + (b"\x00" * (max_len - len(used)))
        data_table.extend(raw)
        index_table.extend(pack_u16(key_offsets[entry["key"]]))
        index_table.extend(pack_u16(data_fmt))
        index_table.extend(pack_u32(len(used)))
        index_table.extend(pack_u32(max_len))
        index_table.extend(pack_u32(data_offset))

    key_table_start = 20 + len(index_table)
    data_table_start = key_table_start + len(key_table)
    output = bytearray()
    output.extend(struct.pack(">I", payload.get("magic", 0x00505346)))
    output.extend(struct.pack(">I", payload.get("version", 0x01010000)))
    output.extend(pack_u32(key_table_start))
    output.extend(pack_u32(data_table_start))
    output.extend(pack_u32(len(entries)))
    output.extend(index_table)
    output.extend(key_table)
    output.extend(data_table)
    return bytes(output)


def update_sfo_payload(payload, overrides):
    override_map = {
        "TITLE": overrides.get("titleName"),
        "TITLE_ID": overrides.get("titleId"),
        "CONTENT_ID": overrides.get("contentId"),
        "DETAIL": overrides.get("detail"),
        "SUB_TITLE": overrides.get("subtitle"),
    }
    for entry in payload["entries"]:
        if entry["key"] in override_map and override_map[entry["key"]]:
            entry["value"] = override_map[entry["key"]]
    return payload


def load_param_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def update_param_json(payload, overrides):
    default_language = (
        payload.get("localizedParameters", {}).get("defaultLanguage")
        or "en-US"
    )
    payload.setdefault("localizedParameters", {})
    payload["localizedParameters"].setdefault(default_language, {})
    if overrides.get("titleName"):
        payload["localizedParameters"][default_language]["titleName"] = overrides["titleName"]
    if overrides.get("titleId"):
        payload["titleId"] = overrides["titleId"]
    if overrides.get("contentId"):
        payload["contentId"] = overrides["contentId"]
    if overrides.get("masterVersion"):
        payload["masterVersion"] = overrides["masterVersion"]
    if overrides.get("contentVersion"):
        payload["contentVersion"] = overrides["contentVersion"]
    return payload


def write_param_json(path, payload):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(payload, indent=2), encoding="utf-8")


def export_param_bundle(param_sfo_path=None):
    param_json_path = GAME_ROOT / "sce_sys" / "param.json"
    payload = {
        "gameRoot": str(GAME_ROOT),
        "paramJsonPath": str(param_json_path) if param_json_path.exists() else None,
        "paramJson": load_param_json(param_json_path) if param_json_path.exists() else None,
        "paramSfoPath": str(Path(param_sfo_path).resolve()) if param_sfo_path else None,
        "paramSfo": load_sfo(param_sfo_path) if param_sfo_path and Path(param_sfo_path).exists() else None,
    }
    destination = CACHE_EXPORT_DIR / "metadata" / "param-edit-template.json"
    save_json(destination, payload)
    return {"jsonPath": str(destination)}


def copy_tree(source_root, destination_root, progress=None):
    source_root = Path(source_root)
    destination_root = Path(destination_root)
    files = [path for path in source_root.rglob("*") if path.is_file()]
    total = len(files)
    emit_progress(progress, "copy", 0, total or 1, f"Copying vanilla files from {source_root}")
    for index, source_path in enumerate(files, start=1):
        relative_path = source_path.relative_to(source_root)
        target_path = destination_root / relative_path
        target_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_path, target_path)
        emit_progress(progress, "copy", index, total or 1, f"Copied {relative_path}")
    return total


def collect_rebuilt_actor_manifests(rebuilt_dir):
    rebuilt_dir = Path(rebuilt_dir)
    manifests = []
    if not rebuilt_dir.exists():
        return manifests
    for manifest_path in sorted(rebuilt_dir.glob("*.manifest.json")):
        manifest = load_json(manifest_path)
        bin_path = manifest_path.with_suffix("").with_suffix(".actorbin")
        if not bin_path.exists():
            continue
        manifests.append({"manifestPath": manifest_path, "binPath": bin_path, "manifest": manifest})
    return manifests


def normalize_replacement_relative_path(source_path, replacement_root, game_root_name):
    relative_path = Path(source_path).resolve().relative_to(Path(replacement_root).resolve())
    if relative_path.parts and relative_path.parts[0] == game_root_name:
        relative_path = Path(*relative_path.parts[1:])
    if not relative_path.parts:
        raise ValueError(f"Replacement file has no game-relative path: {source_path}")
    return relative_path


def collect_file_replacements(replacement_root, game_root_name):
    replacement_root = Path(replacement_root)
    replacements = []
    if not replacement_root.exists():
        raise FileNotFoundError(f"Replacement files folder does not exist: {replacement_root}")
    for source_path in sorted(path for path in replacement_root.rglob("*") if path.is_file()):
        relative_path = normalize_replacement_relative_path(source_path, replacement_root, game_root_name)
        lowered = str(relative_path).replace("\\", "/").lower()
        if lowered in {"resources/animations.b", "sce_sys/param.json", "sce_sys/param.sfo"}:
            raise ValueError(
                f"Replacement file conflicts with a managed export target: {relative_path}. "
                "Use actor rebuilds for animations.b and the metadata editor for param files."
            )
        replacements.append(
            {
                "sourcePath": source_path,
                "relativePath": relative_path,
                "size": source_path.stat().st_size,
            }
        )
    return replacements


def apply_rebuilt_actors_to_animation_copy(animations_copy_path, rebuilt_manifests, progress=None):
    animations_copy_path = Path(animations_copy_path)
    data = bytearray(animations_copy_path.read_bytes())
    total = len(rebuilt_manifests)
    emit_progress(progress, "patch", 0, total or 1, f"Patching {animations_copy_path.name}")
    for index, item in enumerate(sorted(rebuilt_manifests, key=lambda value: value["manifest"]["originalAssetOffset"]), start=1):
        manifest = item["manifest"]
        rebuilt_bytes = item["binPath"].read_bytes()
        start = int(manifest["originalAssetOffset"])
        end = int(manifest["originalGroupEndOffset"])
        expected_length = end - start
        if len(rebuilt_bytes) != expected_length:
            raise ValueError(
                f"Rebuilt actor length mismatch for {manifest['assetPath']}: "
                f"expected {expected_length}, got {len(rebuilt_bytes)}"
            )
        data[start:end] = rebuilt_bytes
        emit_progress(progress, "patch", index, total or 1, f"Patched {manifest['assetPath']}")
    animations_copy_path.write_bytes(bytes(data))


def apply_file_replacements_to_copy(game_copy_root, replacements, progress=None):
    game_copy_root = Path(game_copy_root)
    total = len(replacements)
    emit_progress(progress, "replace", 0, total or 1, "Applying replacement files")
    for index, item in enumerate(replacements, start=1):
        target_path = game_copy_root / item["relativePath"]
        target_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(item["sourcePath"], target_path)
        emit_progress(progress, "replace", index, total or 1, f"Replaced {item['relativePath']}")


def apply_metadata_to_export(game_copy_root, config, progress=None):
    metadata = config.get("metadata", {})
    sce_sys_dir = Path(game_copy_root) / "sce_sys"
    sce_sys_dir.mkdir(parents=True, exist_ok=True)

    param_json_path = sce_sys_dir / "param.json"
    if param_json_path.exists():
        payload = load_param_json(param_json_path)
        updated = update_param_json(payload, metadata)
        write_param_json(param_json_path, updated)
        emit_progress(progress, "metadata", 1, 2, "Updated sce_sys/param.json")

    param_sfo_source = metadata.get("paramSfoSourcePath")
    if param_sfo_source and Path(param_sfo_source).exists():
        payload = load_sfo(param_sfo_source)
        updated = update_sfo_payload(payload, metadata)
        target_name = Path(param_sfo_source).name
        target_path = sce_sys_dir / target_name
        target_path.write_bytes(serialize_sfo(updated))
        emit_progress(progress, "metadata", 2, 2, f"Updated sce_sys/{target_name}")
    else:
        emit_progress(progress, "metadata", 2, 2, "No PARAM.SFO source configured")


def export_modpack(config, progress=None):
    output_root = Path(config["outputRoot"])
    if not output_root.exists():
        output_root.mkdir(parents=True, exist_ok=True)
    source_game_root = Path(config.get("sourceGameRoot") or GAME_ROOT)
    if not source_game_root.exists():
        raise FileNotFoundError(f"Missing source game root: {source_game_root}")
    modpack_name = config.get("modpackName", "IsaacModpack")
    modpack_dir = output_root / sanitize_folder_name(modpack_name)
    game_copy_root = modpack_dir / source_game_root.name
    manifest_root = modpack_dir / "modpack-manifest"
    manifest_root.mkdir(parents=True, exist_ok=True)

    copy_count = copy_tree(source_game_root, game_copy_root, progress=progress)
    rebuilt_dir = Path(config.get("rebuiltActorsDir") or (CACHE_EXPORT_DIR / "rebuilt-actors"))
    rebuilt_manifests = collect_rebuilt_actor_manifests(rebuilt_dir)
    replacement_root = config.get("replacementFilesRoot")
    replacement_files = (
        collect_file_replacements(replacement_root, source_game_root.name)
        if replacement_root
        else []
    )
    animations_copy_path = game_copy_root / "resources" / "animations.b"
    apply_rebuilt_actors_to_animation_copy(animations_copy_path, rebuilt_manifests, progress=progress)
    apply_file_replacements_to_copy(game_copy_root, replacement_files, progress=progress)
    apply_metadata_to_export(game_copy_root, config, progress=progress)

    export_manifest = {
        "schemaVersion": 1,
        "kind": "isaac-console-modpack-export",
        "modpackName": modpack_name,
        "outputRoot": str(modpack_dir),
        "sourceGameRoot": str(source_game_root),
        "gameCopyRoot": str(game_copy_root),
        "copiedFileCount": copy_count,
        "patchedActorCount": len(rebuilt_manifests),
        "replacementFileCount": len(replacement_files),
        "patchedActors": [
            {
                "assetId": item["manifest"]["assetId"],
                "assetPath": item["manifest"]["assetPath"],
                "groupSha256": item["manifest"]["groupSha256"],
                "originalAssetOffset": item["manifest"]["originalAssetOffset"],
                "originalGroupEndOffset": item["manifest"]["originalGroupEndOffset"],
            }
            for item in rebuilt_manifests
        ],
        "replacementFiles": [
            {
                "relativePath": str(item["relativePath"]).replace("\\", "/"),
                "sourcePath": str(item["sourcePath"]),
                "size": item["size"],
            }
            for item in replacement_files
        ],
        "metadata": config.get("metadata", {}),
    }
    manifest_path = manifest_root / "export-manifest.json"
    manifest_path.write_text(json.dumps(export_manifest, indent=2), encoding="utf-8")
    emit_progress(progress, "done", 1, 1, f"Modpack export complete: {modpack_dir}")
    return {
        "modpackRoot": str(modpack_dir),
        "gameCopyRoot": str(game_copy_root),
        "manifestPath": str(manifest_path),
        "copiedFileCount": copy_count,
        "patchedActorCount": len(rebuilt_manifests),
        "replacementFileCount": len(replacement_files),
    }


def verify_actor_roundtrip(asset_id, structured=False):
    payload = build_editable_actor_payload(asset_id)
    original = ANIMATIONS_B_PATH.read_bytes()[payload["actor"]["assetOffset"]:payload["actor"]["groupEndOffset"]]
    rebuilt = rebuild_actor_group_from_payload(
        payload,
        prefer_raw=not structured,
        use_structured_prefix=structured,
    )
    first_mismatch = None
    compare_len = min(len(original), len(rebuilt))
    for index in range(compare_len):
        if original[index] != rebuilt[index]:
            first_mismatch = index
            break
    if first_mismatch is None and len(original) != len(rebuilt):
        first_mismatch = compare_len
    return {
        "assetId": int(asset_id),
        "assetPath": payload["actor"]["assetPath"],
        "mode": "structured" if structured else "raw-preserved",
        "matchesOriginal": original == rebuilt,
        "originalLength": len(original),
        "rebuiltLength": len(rebuilt),
        "originalSha256": sha256_hex(original),
        "rebuiltSha256": sha256_hex(rebuilt),
        "firstMismatchOffset": first_mismatch,
    }


def verify_actor_roundtrip_from_entry(entry, data, structured=False):
    payload = build_editable_actor_payload_from_entry(entry, data)
    original = data[payload["actor"]["assetOffset"]:payload["actor"]["groupEndOffset"]]
    rebuilt = rebuild_actor_group_from_payload(
        payload,
        prefer_raw=not structured,
        use_structured_prefix=structured,
    )
    first_mismatch = None
    compare_len = min(len(original), len(rebuilt))
    for index in range(compare_len):
        if original[index] != rebuilt[index]:
            first_mismatch = index
            break
    if first_mismatch is None and len(original) != len(rebuilt):
        first_mismatch = compare_len
    return {
        "assetId": int(entry["id"]),
        "assetPath": payload["actor"]["assetPath"],
        "mode": "structured" if structured else "raw-preserved",
        "matchesOriginal": original == rebuilt,
        "originalLength": len(original),
        "rebuiltLength": len(rebuilt),
        "originalSha256": sha256_hex(original),
        "rebuiltSha256": sha256_hex(rebuilt),
        "firstMismatchOffset": first_mismatch,
    }


def verify_roundtrip_sample(limit=25):
    entries = parse_actor_entries()
    data = ANIMATIONS_B_PATH.read_bytes()
    results = []
    for entry in entries[:limit]:
        results.append(verify_actor_roundtrip_from_entry(entry, data, structured=False))
    return {
        "assetCount": len(results),
        "matchingAssets": sum(1 for item in results if item["matchesOriginal"]),
        "mismatchedAssets": [item for item in results if not item["matchesOriginal"]][:25],
    }


def verify_roundtrip_corpus(structured=False, limit=None):
    entries = parse_actor_entries()
    data = ANIMATIONS_B_PATH.read_bytes()
    results = []
    target_entries = entries[:limit] if limit is not None else entries
    for entry in target_entries:
        results.append(verify_actor_roundtrip_from_entry(entry, data, structured=structured))
    return {
        "assetCount": len(results),
        "mode": "structured" if structured else "raw-preserved",
        "matchingAssets": sum(1 for item in results if item["matchesOriginal"]),
        "mismatchCount": sum(1 for item in results if not item["matchesOriginal"]),
        "mismatchedAssets": [item for item in results if not item["matchesOriginal"]][:100],
    }


def export_cache_zip():
    index = ensure_cache()
    CACHE_EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    export_images_dir = CACHE_EXPORT_DIR / "images"
    export_assets_dir = CACHE_EXPORT_DIR / "assets"
    export_images_dir.mkdir(parents=True, exist_ok=True)
    export_assets_dir.mkdir(parents=True, exist_ok=True)

    shutil.copy2(CACHE_INDEX_PATH, CACHE_EXPORT_DIR / "index.json")
    for asset in index["assets"]:
        detail = load_asset_detail(asset["id"])
        save_json(export_assets_dir / f"{asset['id']}.json", detail)
        for sheet in detail["spritesheets"]:
            if not sheet["resourcePath"] or not sheet["previewCachePath"]:
                continue
            preview_file = ensure_preview_file(Path(sheet["resourcePath"]), Path(sheet["previewCachePath"]))
            export_target = export_images_dir / Path(sheet["previewCachePath"])
            export_target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(preview_file, export_target)

    zip_path = CACHE_ROOT / "animation-cache-export.zip"
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for file_path in CACHE_EXPORT_DIR.rglob("*"):
            if file_path.is_file():
                archive.write(file_path, file_path.relative_to(CACHE_EXPORT_DIR))
    return {"zipPath": str(zip_path)}


def summary():
    return {
        "animationsPath": str(ANIMATIONS_B_PATH),
        "resourcesPath": str(RESOURCES_ROOT),
        "assetCount": load_index()["assetCount"] if ANIMATIONS_B_PATH.exists() else 0,
        "cachePath": str(CACHE_ROOT),
        "sourceExists": ANIMATIONS_B_PATH.exists(),
    }


def main():
    args = sys.argv[1:]
    try:
        if not args or args[0] == "summary":
            payload = summary()
        elif args[0] == "ensure-cache":
            payload = ensure_cache(force="--force" in args)
        elif args[0] == "ensure-cache-stream":
            def progress_writer(event):
                print(json.dumps(event), flush=True)

            payload = ensure_cache(force="--force" in args, progress=progress_writer)
            print(json.dumps({"type": "result", "payload": payload}), flush=True)
            return
        elif args[0] == "list-assets":
            payload = load_index()["assets"]
        elif args[0] == "get-asset" and len(args) > 1:
            payload = load_asset_detail(args[1])
        elif args[0] == "ensure-asset-previews" and len(args) > 1:
            payload = ensure_asset_previews(args[1])
        elif args[0] == "export-cache-zip":
            payload = export_cache_zip()
        elif args[0] == "export-editable-actor" and len(args) > 1:
            payload = save_editable_actor_bundle(args[1])
        elif args[0] == "export-param-bundle":
            param_sfo_arg = None
            if "--param-sfo" in args:
                index = args.index("--param-sfo")
                if index + 1 < len(args):
                    param_sfo_arg = args[index + 1]
            payload = export_param_bundle(param_sfo_arg)
        elif args[0] == "rebuild-actor-bundle" and len(args) > 1:
            payload = rebuild_actor_bundle(args[1])
        elif args[0] == "export-modpack-stream" and len(args) > 1:
            config = load_json(args[1])

            def progress_writer(event):
                print(json.dumps(event), flush=True)

            payload = export_modpack(config, progress=progress_writer)
            print(json.dumps({"type": "result", "payload": payload}), flush=True)
            return
        elif args[0] == "verify-actor-roundtrip" and len(args) > 1:
            payload = verify_actor_roundtrip(args[1], structured="--structured" in args)
        elif args[0] == "verify-roundtrip-sample":
            limit = 25
            if "--limit" in args:
                limit_index = args.index("--limit")
                if limit_index + 1 < len(args):
                    limit = int(args[limit_index + 1])
            payload = verify_roundtrip_sample(limit=limit)
        elif args[0] == "verify-roundtrip-corpus":
            limit = None
            if "--limit" in args:
                limit_index = args.index("--limit")
                if limit_index + 1 < len(args):
                    limit = int(args[limit_index + 1])
            payload = verify_roundtrip_corpus(structured="--structured" in args, limit=limit)
        elif args[0] == "validate-animations":
            limit = None
            if "--limit" in args:
                limit_index = args.index("--limit")
                if limit_index + 1 < len(args):
                    limit = int(args[limit_index + 1])
            payload = validate_animations(limit=limit)
        else:
            payload = {"error": f"Unsupported command: {' '.join(args)}"}
        print(json.dumps(payload))
    except Exception as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(1)


if __name__ == "__main__":
    main()
