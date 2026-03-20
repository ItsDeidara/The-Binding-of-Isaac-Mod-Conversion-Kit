import copy
import json
import re
import sys
import xml.etree.ElementTree as ET
import struct
import zlib
from dataclasses import dataclass
from pathlib import Path
from typing import Callable


WORKSPACE_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_GAME_ROOT = WORKSPACE_ROOT / "PPSA03311-app0"
DEFAULT_RESOURCES_ROOT = DEFAULT_GAME_ROOT / "resources"


def normalize_rel_path(path):
    return str(Path(path)).replace("\\", "/")


def read_be_u32(data, offset):
    return struct.unpack_from(">I", data, offset)[0], offset + 4


def paeth_predictor(left, up, up_left):
    predictor = left + up - up_left
    distance_left = abs(predictor - left)
    distance_up = abs(predictor - up)
    distance_up_left = abs(predictor - up_left)
    if distance_left <= distance_up and distance_left <= distance_up_left:
        return left
    if distance_up <= distance_up_left:
        return up
    return up_left


def undo_png_filters(raw, width, height, bytes_per_pixel):
    stride = width * bytes_per_pixel
    output = bytearray(height * stride)
    cursor = 0
    prior = bytearray(stride)
    for row in range(height):
        filter_type = raw[cursor]
        cursor += 1
        current = bytearray(raw[cursor:cursor + stride])
        cursor += stride
        for index in range(stride):
            left = current[index - bytes_per_pixel] if index >= bytes_per_pixel else 0
            up = prior[index]
            up_left = prior[index - bytes_per_pixel] if index >= bytes_per_pixel else 0
            if filter_type == 0:
                pass
            elif filter_type == 1:
                current[index] = (current[index] + left) & 0xFF
            elif filter_type == 2:
                current[index] = (current[index] + up) & 0xFF
            elif filter_type == 3:
                current[index] = (current[index] + ((left + up) // 2)) & 0xFF
            elif filter_type == 4:
                current[index] = (current[index] + paeth_predictor(left, up, up_left)) & 0xFF
            else:
                raise ValueError(f"Unsupported PNG filter type: {filter_type}")
        start = row * stride
        output[start:start + stride] = current
        prior = current
    return bytes(output)


def decode_png_rgba(path):
    data = Path(path).read_bytes()
    if not data.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ValueError(f"Unsupported PNG signature: {path}")
    cursor = 8
    width = height = None
    bit_depth = color_type = None
    palette = None
    transparency = None
    compressed = bytearray()

    while cursor < len(data):
        chunk_length, cursor = read_be_u32(data, cursor)
        chunk_type = data[cursor:cursor + 4]
        cursor += 4
        chunk_data = data[cursor:cursor + chunk_length]
        cursor += chunk_length
        cursor += 4
        if chunk_type == b"IHDR":
            width = struct.unpack_from(">I", chunk_data, 0)[0]
            height = struct.unpack_from(">I", chunk_data, 4)[0]
            bit_depth = chunk_data[8]
            color_type = chunk_data[9]
            if bit_depth != 8:
                raise ValueError(f"Unsupported PNG bit depth {bit_depth} in {path}")
        elif chunk_type == b"PLTE":
            palette = [tuple(chunk_data[index:index + 3]) for index in range(0, len(chunk_data), 3)]
        elif chunk_type == b"tRNS":
            transparency = chunk_data
        elif chunk_type == b"IDAT":
            compressed.extend(chunk_data)
        elif chunk_type == b"IEND":
            break

    if width is None or height is None or color_type is None:
        raise ValueError(f"Incomplete PNG file: {path}")

    bytes_per_pixel_map = {2: 3, 3: 1, 6: 4}
    if color_type not in bytes_per_pixel_map:
        raise ValueError(f"Unsupported PNG color type {color_type} in {path}")
    filtered = zlib.decompress(bytes(compressed))
    raw = undo_png_filters(filtered, width, height, bytes_per_pixel_map[color_type])
    rgba = bytearray()

    if color_type == 6:
        rgba.extend(raw)
    elif color_type == 2:
        for index in range(0, len(raw), 3):
            rgba.extend(raw[index:index + 3])
            rgba.append(255)
    elif color_type == 3:
        if palette is None:
            raise ValueError(f"Indexed PNG missing palette: {path}")
        alpha_table = transparency or b""
        for index in raw:
            red, green, blue = palette[index]
            alpha = alpha_table[index] if index < len(alpha_table) else 255
            rgba.extend((red, green, blue, alpha))
    return width, height, bytes(rgba)


def rle_pcx_row(row_bytes):
    encoded = bytearray()
    index = 0
    while index < len(row_bytes):
        value = row_bytes[index]
        run = 1
        while index + run < len(row_bytes) and row_bytes[index + run] == value and run < 63:
            run += 1
        if run > 1 or value >= 0xC0:
            encoded.append(0xC0 | run)
            encoded.append(value)
        else:
            encoded.append(value)
        index += run
    return bytes(encoded)


def encode_pcx_rgba(width, height, rgba_bytes):
    bytes_per_line = width if width % 2 == 0 else width + 1
    header = bytearray(128)
    header[0] = 0x0A
    header[1] = 5
    header[2] = 1
    header[3] = 8
    struct.pack_into("<H", header, 4, 0)
    struct.pack_into("<H", header, 6, 0)
    struct.pack_into("<H", header, 8, width - 1)
    struct.pack_into("<H", header, 10, height - 1)
    struct.pack_into("<H", header, 12, width)
    struct.pack_into("<H", header, 14, height)
    header[64] = 0
    header[65] = 4
    struct.pack_into("<H", header, 66, bytes_per_line)
    struct.pack_into("<H", header, 68, 1)
    struct.pack_into("<H", header, 70, width)
    struct.pack_into("<H", header, 72, height)

    output = bytearray(header)
    stride = width * 4
    for row in range(height):
        start = row * stride
        row_bytes = rgba_bytes[start:start + stride]
        channels = [bytearray(bytes_per_line) for _ in range(4)]
        for column in range(width):
            pixel = row_bytes[column * 4:(column + 1) * 4]
            for plane in range(4):
                channels[plane][column] = pixel[plane]
        for plane in channels:
            output.extend(rle_pcx_row(plane))
    return bytes(output)


def convert_png_to_pcx(source_path, destination_path):
    width, height, rgba = decode_png_rgba(source_path)
    destination_path = Path(destination_path)
    destination_path.parent.mkdir(parents=True, exist_ok=True)
    destination_path.write_bytes(encode_pcx_rgba(width, height, rgba))


def indent_xml(element, level=0):
    indent = "\n" + level * "  "
    if len(element):
        if not element.text or not element.text.strip():
            element.text = indent + "  "
        for child in element:
            indent_xml(child, level + 1)
        if not element[-1].tail or not element[-1].tail.strip():
            element[-1].tail = indent
    elif level and (not element.tail or not element.tail.strip()):
        element.tail = indent


def clone_element(element):
    return copy.deepcopy(element)


def stringify_key(parts):
    return "|".join("" if value is None else str(value) for value in parts)


def require_attrs(element, attrs):
    return tuple(element.attrib.get(attr) for attr in attrs)


def child_key_by_attrs(*attrs):
    def builder(element):
        return stringify_key(require_attrs(element, attrs))

    return builder


def entity_key(element):
    return stringify_key((element.attrib.get("id"), element.attrib.get("variant"), element.attrib.get("subtype")))


def item_key(element):
    return stringify_key((element.tag, element.attrib.get("id")))


def pool_key(element):
    return stringify_key((element.attrib.get("Name"),))


def pool_item_key(element):
    return stringify_key((element.attrib.get("Id"),))


@dataclass(frozen=True)
class XmlRule:
    root_tag: str
    child_key: Callable
    nested_collections: dict[str, Callable] | None = None


XML_RULES = {
    "achievements.xml": XmlRule("achievements", child_key_by_attrs("id")),
    "babies.xml": XmlRule("babies", child_key_by_attrs("id")),
    "bosscolors.xml": XmlRule("bosscolors", child_key_by_attrs("id", "variant")),
    "challenges.xml": XmlRule("challenges", child_key_by_attrs("id")),
    "costumes2.xml": XmlRule("costumes", child_key_by_attrs("id")),
    "entities2.xml": XmlRule("entities", entity_key),
    "itempools.xml": XmlRule("ItemPools", pool_key, nested_collections={"Pool": pool_item_key}),
    "items.xml": XmlRule("items", item_key),
    "locusts.xml": XmlRule("locusts", child_key_by_attrs("name")),
    "music.xml": XmlRule("music", child_key_by_attrs("id")),
    "playerforms.xml": XmlRule("playerforms", child_key_by_attrs("id")),
    "players.xml": XmlRule("players", child_key_by_attrs("id")),
    "pocketitems.xml": XmlRule("pocketitems", child_key_by_attrs("id")),
    "stages.xml": XmlRule("stages", child_key_by_attrs("id")),
    "wisps.xml": XmlRule("wisps", child_key_by_attrs("name")),
}

ROOT_TAG_TO_RULE = {rule.root_tag: name for name, rule in XML_RULES.items()}

LEGACY_POCKETITEM_CARDLIKE_ID_MAP = {
    0: 0,
    1: 1,
    2: 2,
    3: 3,
    4: 4,
    5: 5,
    6: 6,
    7: 7,
    8: 8,
    9: 9,
    10: 10,
    11: 11,
    12: 12,
    13: 13,
    14: 14,
    15: 15,
    16: 16,
    17: 17,
    18: 18,
    19: 19,
    20: 20,
    21: 21,
    22: 22,
    23: 23,
    24: 24,
    25: 25,
    26: 26,
    27: 31,
    28: 32,
    29: 33,
    30: 34,
    31: 35,
    32: 36,
    33: 37,
    34: 38,
    35: 39,
    36: 40,
    37: 42,
    38: 43,
    39: 44,
    40: 45,
    41: 46,
    42: 47,
    43: 48,
    44: 49,
    45: 50,
}


def load_tree(path):
    text = Path(path).read_text(encoding="utf-8", errors="replace")
    sanitized = sanitize_xml_text(text)
    return ET.ElementTree(ET.fromstring(sanitized))


def sanitize_xml_text(text):
    # Some PC mods ship loosely-formed XML with bare ampersands in attribute values.
    return re.sub(r"&(?!#?[A-Za-z0-9]+;)", "&amp;", text)


def find_game_xml_target(mod_relative_path, game_root=DEFAULT_GAME_ROOT):
    rel = Path(mod_relative_path)
    normalized = normalize_rel_path(rel)
    if normalized == "metadata.xml":
        return None
    direct_target = Path(game_root) / rel
    if direct_target.exists():
        return direct_target
    if rel.parts and rel.parts[0].startswith("resources-dlc"):
        folded = Path("resources", *rel.parts[1:])
        folded_target = Path(game_root) / folded
        if folded_target.exists():
            return folded_target
    return direct_target


def find_game_file_target(mod_relative_path, game_root=DEFAULT_GAME_ROOT):
    rel = Path(mod_relative_path)
    normalized = normalize_rel_path(rel)
    if normalized == "metadata.xml":
        return {"kind": "mod-metadata", "targetPath": None, "targetExists": False, "relativeTarget": None}

    direct_target = Path(game_root) / rel
    if direct_target.exists():
        return {
            "kind": "exact",
            "targetPath": direct_target,
            "targetExists": True,
            "relativeTarget": direct_target.relative_to(game_root),
        }

    if rel.parts and rel.parts[0].startswith("resources-dlc"):
        folded = Path("resources", *rel.parts[1:])
        folded_target = Path(game_root) / folded
        if folded_target.exists():
            return {
                "kind": "folded-dlc",
                "targetPath": folded_target,
                "targetExists": True,
                "relativeTarget": folded,
            }
        rel = folded

    if rel.suffix.lower() == ".png":
        pcx_target = (Path(game_root) / rel).with_suffix(".pcx")
        if pcx_target.exists():
            return {
                "kind": "png-to-pcx",
                "targetPath": pcx_target,
                "targetExists": True,
                "relativeTarget": pcx_target.relative_to(game_root),
            }

    return {
        "kind": "new",
        "targetPath": Path(game_root) / rel,
        "targetExists": False,
        "relativeTarget": rel,
    }


def parse_mod_metadata(metadata_path):
    root = load_tree(metadata_path).getroot()
    payload = {}
    for child in root:
        payload[child.tag] = (child.text or "").strip()
    return payload


def merge_simple_children(vanilla_root, mod_root, key_builder):
    vanilla_index = {key_builder(child): child for child in list(vanilla_root)}
    stats = {"replaced": 0, "appended": 0, "unchanged": 0}
    for mod_child in list(mod_root):
        key = key_builder(mod_child)
        if key in vanilla_index:
            vanilla_root.remove(vanilla_index[key])
            vanilla_root.append(clone_element(mod_child))
            vanilla_index[key] = vanilla_root[-1]
            stats["replaced"] += 1
        else:
            vanilla_root.append(clone_element(mod_child))
            stats["appended"] += 1
    return stats


def merge_nested_collection(vanilla_parent, mod_parent, nested_key_builder):
    vanilla_children = {nested_key_builder(child): child for child in list(vanilla_parent)}
    stats = {"replaced": 0, "appended": 0, "unchanged": 0}
    for mod_child in list(mod_parent):
        key = nested_key_builder(mod_child)
        if key in vanilla_children:
            vanilla_parent.remove(vanilla_children[key])
            vanilla_parent.append(clone_element(mod_child))
            vanilla_children[key] = vanilla_parent[-1]
            stats["replaced"] += 1
        else:
            vanilla_parent.append(clone_element(mod_child))
            stats["appended"] += 1
    return stats


def merge_by_rule(vanilla_tree, mod_tree, rule):
    vanilla_root = vanilla_tree.getroot()
    mod_root = mod_tree.getroot()
    if vanilla_root.tag != rule.root_tag:
        raise ValueError(f"Vanilla root tag mismatch: expected {rule.root_tag}, got {vanilla_root.tag}")
    if mod_root.tag != rule.root_tag:
        raise ValueError(f"Mod root tag mismatch: expected {rule.root_tag}, got {mod_root.tag}")

    if not rule.nested_collections:
        stats = merge_simple_children(vanilla_root, mod_root, rule.child_key)
        return {"rootTag": rule.root_tag, **stats}

    vanilla_index = {rule.child_key(child): child for child in list(vanilla_root)}
    stats = {"replaced": 0, "appended": 0, "unchanged": 0, "nested": {}}
    for mod_child in list(mod_root):
        top_key = rule.child_key(mod_child)
        vanilla_child = vanilla_index.get(top_key)
        if vanilla_child is None:
            vanilla_root.append(clone_element(mod_child))
            stats["appended"] += 1
            continue
        stats["replaced"] += 1
        for attr_name, attr_value in mod_child.attrib.items():
            vanilla_child.set(attr_name, attr_value)
        nested_builder = rule.nested_collections.get(mod_child.tag)
        if nested_builder:
            nested_stats = merge_nested_collection(vanilla_child, mod_child, nested_builder)
            stats["nested"][top_key] = nested_stats
        else:
            vanilla_root.remove(vanilla_child)
            vanilla_root.append(clone_element(mod_child))
    return {"rootTag": rule.root_tag, **stats}


def merge_game_xml(vanilla_path, mod_path):
    rule = XML_RULES.get(Path(vanilla_path).name.lower())
    if not rule:
        raise ValueError(f"No XML merge rule is defined for {Path(vanilla_path).name}")
    vanilla_tree = load_tree(vanilla_path)
    mod_tree = load_tree(mod_path)
    vanilla_name = Path(vanilla_path).name.lower()
    compatibility = analyze_tree_compatibility(vanilla_name, vanilla_tree, mod_tree)
    if vanilla_name == "pocketitems.xml" and compatibility.get("legacyPocketitemsSchema"):
        summary = merge_legacy_pocketitems(vanilla_tree, mod_tree)
    else:
        validate_merge_compatibility(vanilla_name, vanilla_tree, mod_tree)
        summary = merge_by_rule(vanilla_tree, mod_tree, rule)
    indent_xml(vanilla_tree.getroot())
    return vanilla_tree, summary


def write_tree(tree, output_path):
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    tree.write(output_path, encoding="utf-8", xml_declaration=False)


def compare_mod_directory(mod_root, game_root=DEFAULT_GAME_ROOT):
    mod_root = Path(mod_root)
    game_root = Path(game_root)
    report = {
        "modRoot": str(mod_root),
        "gameRoot": str(game_root),
        "metadata": {},
        "xmlFiles": [],
        "assetFiles": [],
        "counts": {
            "xmlConvertible": 0,
            "xmlBlocked": 0,
            "assetExact": 0,
            "assetFoldedDlc": 0,
            "assetNeedsConversion": 0,
            "assetNew": 0,
        },
    }
    metadata_path = mod_root / "metadata.xml"
    if metadata_path.exists():
        report["metadata"] = parse_mod_metadata(metadata_path)

    for mod_path in sorted(mod_root.rglob("*.xml")):
        rel_path = mod_path.relative_to(mod_root)
        normalized_rel = normalize_rel_path(rel_path)
        if normalized_rel == "metadata.xml":
            report["xmlFiles"].append(
                {
                    "relativePath": normalized_rel,
                    "kind": "mod-metadata",
                    "mergeMode": "descriptor-only",
                }
            )
            continue
        target_path = find_game_xml_target(rel_path, game_root)
        target_name = target_path.name.lower()
        report["xmlFiles"].append(
            {
                "relativePath": normalized_rel,
                "kind": "gameplay-xml",
                "targetPath": str(target_path),
                "targetExists": target_path.exists(),
                "mergeRule": target_name if target_name in XML_RULES else None,
                "compatibility": analyze_xml_compatibility(target_path, mod_path) if target_path.exists() and target_name in XML_RULES else None,
            }
        )
        if report["xmlFiles"][-1]["compatibility"] and report["xmlFiles"][-1]["compatibility"]["compatible"] is False and not report["xmlFiles"][-1]["compatibility"].get("legacyPocketitemsSchema"):
            report["counts"]["xmlBlocked"] += 1
        else:
            report["counts"]["xmlConvertible"] += 1

    for mod_path in sorted(mod_root.rglob("*")):
        if not mod_path.is_file():
            continue
        rel_path = mod_path.relative_to(mod_root)
        normalized_rel = normalize_rel_path(rel_path)
        if normalized_rel == "metadata.xml" or mod_path.suffix.lower() == ".xml":
            continue
        target = find_game_file_target(rel_path, game_root)
        entry = {
            "relativePath": normalized_rel,
            "kind": target["kind"],
            "targetPath": str(target["targetPath"]) if target["targetPath"] else None,
            "targetExists": target["targetExists"],
            "relativeTarget": normalize_rel_path(target["relativeTarget"]) if target["relativeTarget"] else None,
        }
        report["assetFiles"].append(entry)
        if target["kind"] == "exact":
            report["counts"]["assetExact"] += 1
        elif target["kind"] == "folded-dlc":
            report["counts"]["assetFoldedDlc"] += 1
        elif target["kind"] == "png-to-pcx":
            report["counts"]["assetNeedsConversion"] += 1
        elif target["kind"] == "new":
            report["counts"]["assetNew"] += 1
    return report


def compare_mod_root(mods_root, game_root=DEFAULT_GAME_ROOT):
    mods_root = Path(mods_root)
    game_root = Path(game_root)
    mods = []
    for child in sorted(path for path in mods_root.iterdir() if path.is_dir()):
        report = compare_mod_directory(child, game_root)
        mods.append(
            {
                "modName": child.name,
                "path": str(child),
                "metadata": report.get("metadata", {}),
                "counts": report.get("counts", {}),
                "xmlFiles": report.get("xmlFiles", []),
                "assetFiles": report.get("assetFiles", []),
            }
        )
    return {
        "modsRoot": str(mods_root),
        "gameRoot": str(game_root),
        "modCount": len(mods),
        "mods": mods,
    }


def pocketitems_schema_signature(root):
    cards = [child for child in root if child.tag == "card"]
    pills = [child for child in root if child.tag == "pilleffect"]
    return {
        "cardCount": len(cards),
        "pillCount": len(pills),
        "minCardId": min((int(child.attrib["id"]) for child in cards if child.attrib.get("id", "").isdigit()), default=None),
        "maxCardId": max((int(child.attrib["id"]) for child in cards if child.attrib.get("id", "").isdigit()), default=None),
        "minPillId": min((int(child.attrib["id"]) for child in pills if child.attrib.get("id", "").isdigit()), default=None),
        "maxPillId": max((int(child.attrib["id"]) for child in pills if child.attrib.get("id", "").isdigit()), default=None),
        "hasHudAttr": any("hud" in child.attrib for child in cards),
        "hasPickupAttr": any("pickup" in child.attrib for child in cards),
        "hasTypeAttr": any("type" in child.attrib for child in cards),
    }


def analyze_xml_compatibility(vanilla_path, mod_path):
    vanilla_name = Path(vanilla_path).name.lower()
    vanilla_tree = load_tree(vanilla_path)
    mod_tree = load_tree(mod_path)
    return analyze_tree_compatibility(vanilla_name, vanilla_tree, mod_tree)


def analyze_tree_compatibility(vanilla_name, vanilla_tree, mod_tree):
    result = {
        "compatible": True,
        "issues": [],
        "legacyPocketitemsSchema": False,
    }
    if vanilla_name == "pocketitems.xml":
        vanilla_sig = pocketitems_schema_signature(vanilla_tree.getroot())
        mod_sig = pocketitems_schema_signature(mod_tree.getroot())
        result["vanillaSignature"] = vanilla_sig
        result["modSignature"] = mod_sig
        legacy_layout = (
            mod_sig["hasHudAttr"]
            and not mod_sig["hasPickupAttr"]
            and not mod_sig["hasTypeAttr"]
            and mod_sig["minPillId"] == 0
            and mod_sig["maxCardId"] is not None
            and mod_sig["maxCardId"] < 100
        )
        if legacy_layout:
            result["legacyPocketitemsSchema"] = True
            result["issues"].append(
                "legacy-pocketitems-schema: requires card/rune id remapping before merge"
            )
    return result


def validate_merge_compatibility(vanilla_name, vanilla_tree, mod_tree):
    compatibility = analyze_tree_compatibility(vanilla_name, vanilla_tree, mod_tree)
    if compatibility.get("legacyPocketitemsSchema"):
        return
    if compatibility["compatible"]:
        return
    raise ValueError("; ".join(compatibility["issues"]))


def build_pocketitems_indexes(root):
    cardlike_by_id = {}
    pills_by_id = {}
    for child in root:
        item_id = child.attrib.get("id")
        if item_id is None:
            continue
        if child.tag == "pilleffect":
            pills_by_id[item_id] = child
        else:
            cardlike_by_id[item_id] = child
    return cardlike_by_id, pills_by_id


def merge_selected_attributes(target, source, allowed_attrs):
    replaced = 0
    for attr in allowed_attrs:
        if attr not in source.attrib:
            continue
        if target.attrib.get(attr) != source.attrib[attr]:
            target.set(attr, source.attrib[attr])
            replaced += 1
    return replaced


def merge_legacy_pocketitems(vanilla_tree, legacy_tree):
    vanilla_root = vanilla_tree.getroot()
    legacy_root = legacy_tree.getroot()
    vanilla_cardlike, vanilla_pills = build_pocketitems_indexes(vanilla_root)
    summary = {
        "rootTag": "pocketitems",
        "legacyConverted": True,
        "replaced": 0,
        "appended": 0,
        "unchanged": 0,
        "skipped": [],
    }

    for child in legacy_root:
        legacy_id_text = child.attrib.get("id")
        if legacy_id_text is None or not legacy_id_text.isdigit():
            summary["skipped"].append({"reason": "missing-or-non-numeric-id", "tag": child.tag, "attrs": child.attrib})
            continue
        legacy_id = int(legacy_id_text)

        if child.tag == "pilleffect":
            target = vanilla_pills.get(str(legacy_id))
            if target is None:
                summary["skipped"].append({"reason": "missing-pill-target", "legacyId": legacy_id, "tag": child.tag})
                continue
            merge_selected_attributes(target, child, {"name", "description", "greedmode", "achievement"})
            summary["replaced"] += 1
            continue

        mapped_id = LEGACY_POCKETITEM_CARDLIKE_ID_MAP.get(legacy_id)
        if mapped_id is None:
            summary["skipped"].append({"reason": "unmapped-cardlike-id", "legacyId": legacy_id, "tag": child.tag})
            continue
        target = vanilla_cardlike.get(str(mapped_id))
        if target is None:
            summary["skipped"].append({"reason": "missing-cardlike-target", "legacyId": legacy_id, "mappedId": mapped_id, "tag": child.tag})
            continue
        merge_selected_attributes(target, child, {"name", "description", "greedmode", "achievement"})
        summary["replaced"] += 1

    return summary


def merge_mod_xml_file(mod_xml_path, output_path, game_root=DEFAULT_GAME_ROOT):
    mod_xml_path = Path(mod_xml_path)
    if mod_xml_path.name.lower() == "metadata.xml":
        raise ValueError("Mod metadata.xml is descriptor-only and must not be merged into game data.")
    lowered_parts = [part.lower() for part in mod_xml_path.parts]
    relative = Path(mod_xml_path.name)
    if "resources" in lowered_parts:
        index = lowered_parts.index("resources")
        relative = Path(*mod_xml_path.parts[index:])
    elif any(part.startswith("resources-dlc") for part in lowered_parts):
        for index, part in enumerate(lowered_parts):
            if part.startswith("resources-dlc"):
                relative = Path(*mod_xml_path.parts[index:])
                break
    vanilla_target = find_game_xml_target(relative, game_root)
    if not vanilla_target.exists() and mod_xml_path.name.lower() in XML_RULES:
        vanilla_target = Path(game_root) / "resources" / mod_xml_path.name
    if not vanilla_target.exists():
        mod_root_tag = load_tree(mod_xml_path).getroot().tag
        mapped_name = ROOT_TAG_TO_RULE.get(mod_root_tag)
        if mapped_name:
            vanilla_target = Path(game_root) / "resources" / mapped_name
    if not vanilla_target.exists():
        raise FileNotFoundError(f"No vanilla XML target found for {relative}")
    merged_tree, summary = merge_game_xml(vanilla_target, mod_xml_path)
    write_tree(merged_tree, output_path)
    return {
        "modXmlPath": str(mod_xml_path),
        "vanillaXmlPath": str(vanilla_target),
        "outputPath": str(output_path),
        "summary": summary,
    }


def build_mod_overlay(config):
    mods_root = Path(config["modsRoot"])
    output_root = Path(config["outputRoot"])
    game_root = Path(config.get("gameRoot") or DEFAULT_GAME_ROOT)
    selected_mods = config.get("selectedMods", [])
    output_root.mkdir(parents=True, exist_ok=True)

    report = {
        "modsRoot": str(mods_root),
        "gameRoot": str(game_root),
        "outputRoot": str(output_root),
        "selectedMods": selected_mods,
        "processedMods": [],
        "copiedAssets": 0,
        "mergedXmlFiles": 0,
        "skippedFiles": [],
    }

    for mod_name in selected_mods:
        mod_root = mods_root / mod_name
        if not mod_root.exists():
            report["skippedFiles"].append({"modName": mod_name, "reason": "missing-mod-folder"})
            continue
        processed = {"modName": mod_name, "copiedAssets": 0, "mergedXmlFiles": 0, "skippedFiles": []}
        for mod_path in sorted(path for path in mod_root.rglob("*") if path.is_file()):
            rel_path = mod_path.relative_to(mod_root)
            normalized_rel = normalize_rel_path(rel_path)
            if normalized_rel == "metadata.xml":
                continue

            if mod_path.suffix.lower() == ".xml":
                target_path = find_game_xml_target(rel_path, game_root)
                target_name = target_path.name.lower()
                if target_name not in XML_RULES or not target_path.exists():
                    processed["skippedFiles"].append({"relativePath": normalized_rel, "reason": "unsupported-xml-target"})
                    continue
                overlay_target_rel = target_path.relative_to(game_root)
                overlay_target_path = output_root / overlay_target_rel
                base_xml_path = overlay_target_path if overlay_target_path.exists() else target_path
                merged_tree, _summary = merge_game_xml(base_xml_path, mod_path)
                write_tree(merged_tree, overlay_target_path)
                processed["mergedXmlFiles"] += 1
                report["mergedXmlFiles"] += 1
                continue

            if mod_path.suffix.lower() == ".lua":
                processed["skippedFiles"].append(
                    {
                        "relativePath": normalized_rel,
                        "reason": "unsupported-lua-runtime-on-console",
                    }
                )
                continue

            target = find_game_file_target(rel_path, game_root)
            if target["kind"] == "png-to-pcx":
                overlay_target_path = output_root / target["relativeTarget"]
                convert_png_to_pcx(mod_path, overlay_target_path)
                processed["copiedAssets"] += 1
                report["copiedAssets"] += 1
                continue

            relative_target = target["relativeTarget"] or rel_path
            overlay_target_path = output_root / relative_target
            overlay_target_path.parent.mkdir(parents=True, exist_ok=True)
            overlay_target_path.write_bytes(mod_path.read_bytes())
            processed["copiedAssets"] += 1
            report["copiedAssets"] += 1

        report["processedMods"].append(processed)
        report["skippedFiles"].extend(
            [{"modName": mod_name, **entry} for entry in processed["skippedFiles"]]
        )

    return report


def print_json(payload):
    print(json.dumps(payload, indent=2))


def main():
    args = sys.argv[1:]
    if not args:
        print_json(
            {
                "commands": [
                    "compare-mod <modRoot> [gameRoot]",
                    "merge-file <modXmlPath> <outputPath> [gameRoot]",
                    "list-rules",
                ]
            }
        )
        return

    command = args[0]
    if command == "list-rules":
        print_json(
            {
                "rules": {
                    name: {
                        "rootTag": rule.root_tag,
                        "nestedCollections": sorted((rule.nested_collections or {}).keys()),
                    }
                    for name, rule in sorted(XML_RULES.items())
                }
            }
        )
        return

    if command == "compare-mod" and len(args) >= 2:
        mod_root = args[1]
        game_root = args[2] if len(args) >= 3 else DEFAULT_GAME_ROOT
        print_json(compare_mod_directory(mod_root, game_root))
        return

    if command == "compare-mod-root" and len(args) >= 2:
        mods_root = args[1]
        game_root = args[2] if len(args) >= 3 else DEFAULT_GAME_ROOT
        print_json(compare_mod_root(mods_root, game_root))
        return

    if command == "merge-file" and len(args) >= 3:
        mod_xml_path = args[1]
        output_path = args[2]
        game_root = args[3] if len(args) >= 4 else DEFAULT_GAME_ROOT
        print_json(merge_mod_xml_file(mod_xml_path, output_path, game_root))
        return

    if command == "build-mod-overlay" and len(args) >= 2:
        config_path = args[1]
        config = json.loads(Path(config_path).read_text(encoding="utf-8"))
        print_json(build_mod_overlay(config))
        return

    raise SystemExit(f"Unsupported command: {' '.join(args)}")


if __name__ == "__main__":
    main()
