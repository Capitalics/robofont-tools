#!/usr/bin/env python3
from __future__ import print_function

"""
Compare spacing for a base glyph and a component-built glyph across UFOs.

Run from plain Python:
    python scripts/testing/compare-component-spacing.py /path/to/ufo/root

Run from DrawBot:
    Set ROOT_PATH below, then run the script. It does not use CurrentFont(),
    AllFonts(), or open fonts in RoboFont windows.
"""

import argparse
import csv
import os
import sys


ROOT_PATH = "User/tdbk/REPOS/amstelvar-avar2/Sources/"
BASE_GLYPH_NAME = "O"
COMPONENT_GLYPH_NAME = "Ocyr"
OUTPUT_FORMAT = "tsv"  # "tsv" or "csv"

EPSILON = 0.0001


def import_openers():
    try:
        from fontParts.world import OpenFont
    except ImportError:
        OpenFont = None

    try:
        from defcon import Font
    except ImportError:
        Font = None

    if OpenFont is None and Font is None:
        raise ImportError("Install fontParts or defcon to open UFOs from disk.")

    return OpenFont, Font


def find_ufo_paths(root_path):
    ufo_paths = []
    for dirpath, dirnames, _filenames in os.walk(root_path):
        dirnames[:] = sorted(dirnames)
        for dirname in list(dirnames):
            if dirname.lower().endswith(".ufo"):
                ufo_paths.append(os.path.join(dirpath, dirname))
                dirnames.remove(dirname)
    return sorted(ufo_paths)


def open_ufo(path, open_font, defcon_font):
    if open_font is not None:
        try:
            return open_font(path, showInterface=False), "fontParts"
        except TypeError:
            if defcon_font is None:
                raise
        except Exception:
            if defcon_font is None:
                raise
    return defcon_font(path), "defcon"


def close_font(font):
    close = getattr(font, "close", None)
    if close is not None:
        close()


def glyph_exists(font, glyph_name):
    try:
        return glyph_name in font
    except Exception:
        has_key = getattr(font, "has_key", None)
        if has_key is not None:
            return has_key(glyph_name)
        return glyph_name in font.keys()


def get_glyph(font, glyph_name):
    if not glyph_exists(font, glyph_name):
        return None
    return font[glyph_name]


def number_or_blank(value):
    if value is None:
        return ""
    if isinstance(value, float):
        if abs(value - round(value)) < EPSILON:
            return str(int(round(value)))
        return ("%.4f" % value).rstrip("0").rstrip(".")
    return str(value)


def tuple_or_blank(values):
    if values is None:
        return ""
    return " ".join(number_or_blank(value) for value in values)


def almost_equal(left, right):
    if left is None or right is None:
        return left == right
    return abs(left - right) < EPSILON


def tuple_delta(left, right):
    if left is None or right is None:
        return None
    if len(left) != len(right):
        return None
    return tuple(left_value - right_value for left_value, right_value in zip(left, right))


def tuple_equal(left, right):
    if left is None or right is None:
        return left == right
    if len(left) != len(right):
        return False
    return all(almost_equal(left_value, right_value) for left_value, right_value in zip(left, right))


def get_bounds(glyph):
    bounds = getattr(glyph, "bounds", None)
    if bounds is None:
        return None
    return tuple(bounds)


def get_margin(glyph, attr_name):
    try:
        return getattr(glyph, attr_name)
    except Exception:
        return None


def get_width(glyph):
    try:
        return glyph.width
    except Exception:
        return None


def get_component_transform(component):
    transformation = getattr(component, "transformation", None)
    if transformation is not None:
        return tuple(transformation)

    values = []
    for attr_name in ("xScale", "xyScale", "yxScale", "yScale", "xOffset", "yOffset"):
        values.append(getattr(component, attr_name, None))
    if any(value is not None for value in values):
        return tuple(values)
    return None


def get_component_base_name(component):
    for attr_name in ("baseGlyph", "baseGlyphName"):
        value = getattr(component, attr_name, None)
        if value:
            return value
    return ""


def get_components(glyph):
    components = getattr(glyph, "components", [])
    return list(components)


def describe_components(glyph):
    components = get_components(glyph)
    base_names = []
    transforms = []
    offsets = []
    scales = []

    for component in components:
        base_name = get_component_base_name(component)
        transform = get_component_transform(component)
        base_names.append(base_name)

        if transform is None:
            transforms.append("%s@" % base_name)
            offsets.append("")
            scales.append("")
            continue

        transforms.append("%s@%s" % (base_name, tuple_or_blank(transform)))
        if len(transform) >= 6:
            x_scale, xy_scale, yx_scale, y_scale, x_offset, y_offset = transform[:6]
            offsets.append("%s %s" % (number_or_blank(x_offset), number_or_blank(y_offset)))
            scales.append("%s %s %s %s" % (
                number_or_blank(x_scale),
                number_or_blank(xy_scale),
                number_or_blank(yx_scale),
                number_or_blank(y_scale),
            ))
        else:
            offsets.append("")
            scales.append("")

    return {
        "count": len(components),
        "base_names": base_names,
        "transforms": transforms,
        "offsets": offsets,
        "scales": scales,
    }


def has_nonzero_offset(component_description):
    for offset in component_description["offsets"]:
        if not offset:
            continue
        values = [float(value) for value in offset.split()]
        if any(abs(value) >= EPSILON for value in values):
            return True
    return False


def has_nonidentity_scale(component_description):
    for scale in component_description["scales"]:
        if not scale:
            continue
        values = [float(value) for value in scale.split()]
        if len(values) != 4:
            continue
        x_scale, xy_scale, yx_scale, y_scale = values
        if (
            abs(x_scale - 1) >= EPSILON
            or abs(xy_scale) >= EPSILON
            or abs(yx_scale) >= EPSILON
            or abs(y_scale - 1) >= EPSILON
        ):
            return True
    return False


def get_source_label(font, ufo_path):
    info = getattr(font, "info", None)
    family_name = getattr(info, "familyName", None) if info is not None else None
    style_name = getattr(info, "styleName", None) if info is not None else None
    label_parts = [part for part in (family_name, style_name) if part]
    if label_parts:
        return " ".join(label_parts)
    return os.path.basename(ufo_path)


def compare_ufo(ufo_path, base_glyph_name, component_glyph_name, open_font, defcon_font):
    font = None
    opener_name = ""
    try:
        font, opener_name = open_ufo(ufo_path, open_font, defcon_font)
        base_glyph = get_glyph(font, base_glyph_name)
        component_glyph = get_glyph(font, component_glyph_name)
        source_label = get_source_label(font, ufo_path)

        flags = []
        if base_glyph is None:
            flags.append("MISSING_BASE")
        if component_glyph is None:
            flags.append("MISSING_COMPONENT")

        base_width = get_width(base_glyph) if base_glyph is not None else None
        component_width = get_width(component_glyph) if component_glyph is not None else None
        base_left = get_margin(base_glyph, "leftMargin") if base_glyph is not None else None
        component_left = get_margin(component_glyph, "leftMargin") if component_glyph is not None else None
        base_right = get_margin(base_glyph, "rightMargin") if base_glyph is not None else None
        component_right = get_margin(component_glyph, "rightMargin") if component_glyph is not None else None
        base_bounds = get_bounds(base_glyph) if base_glyph is not None else None
        component_bounds = get_bounds(component_glyph) if component_glyph is not None else None

        width_delta = component_width - base_width if base_width is not None and component_width is not None else None
        left_delta = component_left - base_left if base_left is not None and component_left is not None else None
        right_delta = component_right - base_right if base_right is not None and component_right is not None else None
        bounds_delta = tuple_delta(component_bounds, base_bounds)

        component_description = describe_components(component_glyph) if component_glyph is not None else {
            "count": 0,
            "base_names": [],
            "transforms": [],
            "offsets": [],
            "scales": [],
        }

        if width_delta is not None and not almost_equal(width_delta, 0):
            flags.append("WIDTH_DIFF")
        if left_delta is not None and not almost_equal(left_delta, 0):
            flags.append("LEFT_MARGIN_DIFF")
        if right_delta is not None and not almost_equal(right_delta, 0):
            flags.append("RIGHT_MARGIN_DIFF")
        if not tuple_equal(component_bounds, base_bounds):
            flags.append("BOUNDS_DIFF")
        if component_glyph is not None and base_glyph_name not in component_description["base_names"]:
            flags.append("COMPONENT_BASE_DIFF")
        if has_nonzero_offset(component_description):
            flags.append("COMPONENT_OFFSET_DIFF")
        if has_nonidentity_scale(component_description):
            flags.append("COMPONENT_SCALE_DIFF")

        return {
            "source_label": source_label,
            "ufo_folder": os.path.basename(ufo_path),
            "ufo_path": ufo_path,
            "opener": opener_name,
            "base_glyph": base_glyph_name,
            "component_glyph": component_glyph_name,
            "base_width": number_or_blank(base_width),
            "component_width": number_or_blank(component_width),
            "width_delta": number_or_blank(width_delta),
            "base_left_margin": number_or_blank(base_left),
            "component_left_margin": number_or_blank(component_left),
            "left_margin_delta": number_or_blank(left_delta),
            "base_right_margin": number_or_blank(base_right),
            "component_right_margin": number_or_blank(component_right),
            "right_margin_delta": number_or_blank(right_delta),
            "base_bounds": tuple_or_blank(base_bounds),
            "component_bounds": tuple_or_blank(component_bounds),
            "bounds_delta": tuple_or_blank(bounds_delta),
            "component_count": number_or_blank(component_description["count"]),
            "component_base_glyphs": ";".join(component_description["base_names"]),
            "component_transforms": ";".join(component_description["transforms"]),
            "component_offsets": ";".join(component_description["offsets"]),
            "component_scales": ";".join(component_description["scales"]),
            "flags": ";".join(flags) if flags else "OK",
        }
    except Exception as error:
        return {
            "source_label": os.path.basename(ufo_path),
            "ufo_folder": os.path.basename(ufo_path),
            "ufo_path": ufo_path,
            "opener": opener_name,
            "base_glyph": base_glyph_name,
            "component_glyph": component_glyph_name,
            "base_width": "",
            "component_width": "",
            "width_delta": "",
            "base_left_margin": "",
            "component_left_margin": "",
            "left_margin_delta": "",
            "base_right_margin": "",
            "component_right_margin": "",
            "right_margin_delta": "",
            "base_bounds": "",
            "component_bounds": "",
            "bounds_delta": "",
            "component_count": "",
            "component_base_glyphs": "",
            "component_transforms": "",
            "component_offsets": "",
            "component_scales": "",
            "flags": "OPEN_ERROR:%s" % error,
        }
    finally:
        if font is not None:
            close_font(font)


FIELDNAMES = [
    "source_label",
    "ufo_folder",
    "ufo_path",
    "opener",
    "base_glyph",
    "component_glyph",
    "base_width",
    "component_width",
    "width_delta",
    "base_left_margin",
    "component_left_margin",
    "left_margin_delta",
    "base_right_margin",
    "component_right_margin",
    "right_margin_delta",
    "base_bounds",
    "component_bounds",
    "bounds_delta",
    "component_count",
    "component_base_glyphs",
    "component_transforms",
    "component_offsets",
    "component_scales",
    "flags",
]


def write_rows(rows, output_format):
    delimiter = "\t" if output_format == "tsv" else ","
    writer = csv.DictWriter(sys.stdout, fieldnames=FIELDNAMES, delimiter=delimiter)
    writer.writeheader()
    for row in rows:
        writer.writerow(row)


def parse_args(args):
    parser = argparse.ArgumentParser(
        description="Compare base glyph spacing against a component-built glyph across UFOs."
    )
    parser.add_argument("root_path", nargs="?", default=ROOT_PATH, help="Folder to search recursively for .ufo packages.")
    parser.add_argument("--base", default=BASE_GLYPH_NAME, help="Source/base glyph name.")
    parser.add_argument("--component", default=COMPONENT_GLYPH_NAME, help="Component-built glyph name.")
    parser.add_argument("--format", choices=("tsv", "csv"), default=OUTPUT_FORMAT, help="Output table format.")
    return parser.parse_args(args)


def main(args=None):
    options = parse_args(args if args is not None else sys.argv[1:])
    root_path = os.path.abspath(os.path.expanduser(options.root_path)) if options.root_path else ""

    if not root_path:
        print("Set ROOT_PATH or pass a root folder path.", file=sys.stderr)
        return 2
    if not os.path.isdir(root_path):
        print("Root folder does not exist: %s" % root_path, file=sys.stderr)
        return 2

    try:
        open_font, defcon_font = import_openers()
    except ImportError as error:
        print(error, file=sys.stderr)
        return 2
    ufo_paths = find_ufo_paths(root_path)
    rows = [
        compare_ufo(ufo_path, options.base, options.component, open_font, defcon_font)
        for ufo_path in ufo_paths
    ]
    write_rows(rows, options.format)
    return 0


if __name__ == "__main__":
    sys.exit(main())
