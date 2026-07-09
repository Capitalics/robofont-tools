#!/usr/bin/env python3
from __future__ import print_function

"""
Draw a PDF proof comparing a base glyph and component-built glyph across UFOs.

Run from DrawBot:
    Set ROOT_PATH below, then run the script.

Run from plain Python with DrawBot installed:
    python scripts/testing/proof-component-spacing-drawbot.py /path/to/ufo/root --output proof.pdf

This script opens UFOs from disk only. It does not use CurrentFont(),
AllFonts(), open RoboFont windows, or save UFO data.
"""

import argparse
import os
import sys


ROOT_PATH = "/Users/tdbk/REPOS/amstelvar-avar2/Sources/Roman"
BASE_GLYPH_NAME = "O"
COMPONENT_GLYPH_NAME = "Ocyr"
SCAN_MODE = "folder-ufos"
OUTPUT_PDF_PATH = "component-spacing-proof.pdf"
# Leave empty to include every UFO below ROOT_PATH. Set to text that must appear
# in the UFO path only when the sources need another path-based filter.
SOURCE_PATH_INCLUDE_TEXT = ""
SOURCE_PATH_EXCLUDE_TEXTS = ()
SHOW_ONLY_SOURCES_WITH_DISCREPANCIES = False

PAGE_WIDTH = 760
PAGE_HEIGHT = 1100
PAGE_MARGIN = 34
HEADER_HEIGHT = 68
ROWS_PER_PAGE = 4
ROW_GAP = 14
CELL_GAP = 14
METRIC_COLOR = (0, 0, 0, 0.32)
DISCREPANCY_COLOR = (0.9, 0, 0, 1)
BASE_COLOR = (0, 0.78, 1, 0.55)
COMPONENT_COLOR = (1, 0, 0.78, 0.55)
NODE_RADIUS = 2.2
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


def import_drawbot():
    try:
        import drawBot
    except ImportError:
        raise ImportError("Run this script in DrawBot, or install the drawBot Python package.")
    return drawBot


def find_ufo_paths(root_path):
    ufo_paths = []
    for dirpath, dirnames, _filenames in os.walk(root_path):
        dirnames[:] = sorted(dirnames)
        for dirname in list(dirnames):
            if dirname.lower().endswith(".ufo"):
                ufo_paths.append(os.path.join(dirpath, dirname))
                dirnames.remove(dirname)
    return sorted(ufo_paths)


def source_path_is_included(ufo_path):
    normalized_path = ufo_path.lower()
    if SOURCE_PATH_INCLUDE_TEXT and SOURCE_PATH_INCLUDE_TEXT.lower() not in normalized_path:
        return False
    for exclude_text in SOURCE_PATH_EXCLUDE_TEXTS:
        if exclude_text and exclude_text.lower() in normalized_path:
            return False
    return True


def open_ufo(path, open_font, defcon_font):
    if open_font is not None:
        try:
            return open_font(path, showInterface=False)
        except Exception:
            if defcon_font is None:
                raise
    return defcon_font(path)


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


def get_source_label(font, ufo_path):
    info = getattr(font, "info", None)
    family_name = getattr(info, "familyName", None) if info is not None else None
    style_name = getattr(info, "styleName", None) if info is not None else None
    label_parts = [part for part in (family_name, style_name) if part]
    if label_parts:
        return " ".join(label_parts)
    return os.path.basename(ufo_path)


def get_units_per_em(font):
    info = getattr(font, "info", None)
    units_per_em = getattr(info, "unitsPerEm", None) if info is not None else None
    return units_per_em or 1000


def get_vertical_extents(font):
    info = getattr(font, "info", None)
    ascender = getattr(info, "ascender", None) if info is not None else None
    descender = getattr(info, "descender", None) if info is not None else None
    if ascender is None:
        ascender = get_units_per_em(font)
    if descender is None:
        descender = -250
    return descender, ascender


def get_width(glyph):
    if glyph is None:
        return 0
    try:
        return glyph.width
    except Exception:
        return 0


def almost_equal(left, right):
    if left is None or right is None:
        return left == right
    return abs(left - right) < EPSILON


def number_or_blank(value):
    if value is None:
        return ""
    if isinstance(value, float):
        if abs(value - round(value)) < EPSILON:
            value = int(round(value))
        else:
            return ("%+.4f" % value).rstrip("0").rstrip(".")
    if isinstance(value, int):
        return "%+d" % value
    return str(value)


def get_margin(glyph, attr_name):
    if glyph is None:
        return None
    try:
        return getattr(glyph, attr_name)
    except Exception:
        return None


def get_discrepancy_flags(base_glyph, component_glyph):
    flags = []
    if base_glyph is None:
        flags.append("missing source")
    if component_glyph is None:
        flags.append("missing component")
    if base_glyph is None or component_glyph is None:
        return flags

    base_width = get_width(base_glyph)
    component_width = get_width(component_glyph)
    base_left = get_margin(base_glyph, "leftMargin")
    component_left = get_margin(component_glyph, "leftMargin")
    base_right = get_margin(base_glyph, "rightMargin")
    component_right = get_margin(component_glyph, "rightMargin")

    width_delta = component_width - base_width
    left_delta = component_left - base_left if base_left is not None and component_left is not None else None
    right_delta = component_right - base_right if base_right is not None and component_right is not None else None

    if not almost_equal(width_delta, 0):
        flags.append("W:%s" % number_or_blank(width_delta))
    if left_delta is not None and not almost_equal(left_delta, 0):
        flags.append("L:%s" % number_or_blank(left_delta))
    if right_delta is not None and not almost_equal(right_delta, 0):
        flags.append("R:%s" % number_or_blank(right_delta))
    return flags


def transform_point(point, matrix):
    x, y = point
    xx, xy, yx, yy, dx, dy = matrix
    return xx * x + yx * y + dx, xy * x + yy * y + dy


def concat_transform(first, second):
    xx1, xy1, yx1, yy1, dx1, dy1 = first
    xx2, xy2, yx2, yy2, dx2, dy2 = second
    return (
        xx1 * xx2 + yx1 * xy2,
        xy1 * xx2 + yy1 * xy2,
        xx1 * yx2 + yx1 * yy2,
        xy1 * yx2 + yy1 * yy2,
        xx1 * dx2 + yx1 * dy2 + dx1,
        xy1 * dx2 + yy1 * dy2 + dy1,
    )


class DrawBotGlyphPen(object):
    def __init__(self, drawbot, font, path, transform=None):
        self.drawbot = drawbot
        self.font = font
        self.path = path
        self.transform = transform or (1, 0, 0, 1, 0, 0)
        self.nodes = []

    def _point(self, point):
        transformed = transform_point(point, self.transform)
        self.nodes.append(transformed)
        return transformed

    def moveTo(self, point):
        self.path.moveTo(self._point(point))

    def lineTo(self, point):
        self.path.lineTo(self._point(point))

    def curveTo(self, *points):
        self.path.curveTo(*[self._point(point) for point in points])

    def qCurveTo(self, *points):
        if hasattr(self.path, "qCurveTo"):
            self.path.qCurveTo(*[None if point is None else self._point(point) for point in points])
            return
        if points:
            on_curve_points = [point for point in points if point is not None]
            if on_curve_points:
                self.lineTo(on_curve_points[-1])

    def closePath(self):
        self.path.closePath()

    def endPath(self):
        self.path.endPath()

    def addComponent(self, base_glyph_name, transformation):
        base_glyph = get_glyph(self.font, base_glyph_name)
        if base_glyph is None:
            return
        transform = concat_transform(self.transform, transformation)
        component_pen = DrawBotGlyphPen(self.drawbot, self.font, self.path, transform)
        base_glyph.draw(component_pen)
        self.nodes.extend(component_pen.nodes)


def glyph_to_path(drawbot, font, glyph):
    path = drawbot.BezierPath()
    if glyph is None:
        return path, []
    pen = DrawBotGlyphPen(drawbot, font, path)
    glyph.draw(pen)
    return path, pen.nodes


def draw_label(drawbot, text, x, y, width, size=11, color=(0, 0, 0, 1)):
    drawbot.fill(*color)
    drawbot.font("Helvetica")
    drawbot.fontSize(size)
    drawbot.textBox(text, (x, y, width, size * 2.4))


def draw_metrics(drawbot, glyph, cell_x, cell_y, cell_w, cell_h, scale, descender, ascender, origin_width=None):
    width = get_width(glyph)
    if origin_width is None:
        origin_width = width
    origin_x = cell_x + (cell_w - origin_width * scale) / 2
    baseline_y = cell_y + 26 - descender * scale
    top_y = baseline_y + ascender * scale
    bottom_y = baseline_y + descender * scale

    drawbot.stroke(*METRIC_COLOR)
    drawbot.strokeWidth(0.7)
    drawbot.line((origin_x, baseline_y), (origin_x + width * scale, baseline_y))
    drawbot.line((origin_x, bottom_y), (origin_x, top_y))
    drawbot.line((origin_x + width * scale, bottom_y), (origin_x + width * scale, top_y))

    return origin_x, baseline_y


def draw_glyph(drawbot, font, glyph, color, cell_x, cell_y, cell_w, cell_h, scale, descender, ascender, origin_width=None):
    path, nodes = glyph_to_path(drawbot, font, glyph)
    origin_x, baseline_y = draw_metrics(
        drawbot,
        glyph,
        cell_x,
        cell_y,
        cell_w,
        cell_h,
        scale,
        descender,
        ascender,
        origin_width,
    )

    drawbot.save()
    drawbot.translate(origin_x, baseline_y)
    drawbot.scale(scale)
    drawbot.fill(*color)
    drawbot.stroke(None)
    drawbot.drawPath(path)
    drawbot.restore()

    drawbot.fill(color[0], color[1], color[2], 1)
    drawbot.stroke(1, 1, 1, 0.85)
    drawbot.strokeWidth(0.5)
    radius = NODE_RADIUS
    for x, y in nodes:
        drawbot.oval(origin_x + x * scale - radius, baseline_y + y * scale - radius, radius * 2, radius * 2)


def draw_missing(drawbot, glyph_name, cell_x, cell_y, cell_w, cell_h):
    draw_label(drawbot, "Missing glyph: %s" % glyph_name, cell_x, cell_y + cell_h / 2, cell_w, 16, (0.85, 0, 0, 1))


def draw_page_header(drawbot, base_glyph_name, component_glyph_name):
    drawbot.newPage(PAGE_WIDTH, PAGE_HEIGHT)
    drawbot.fill(1)
    drawbot.rect(0, 0, PAGE_WIDTH, PAGE_HEIGHT)

    draw_label(drawbot, "Component spacing proof", PAGE_MARGIN, PAGE_HEIGHT - 38, PAGE_WIDTH - PAGE_MARGIN * 2, 17)
    draw_label(drawbot, "cyan source: %s" % base_glyph_name, PAGE_MARGIN, PAGE_HEIGHT - 60, 220, 9.5, BASE_COLOR)
    draw_label(drawbot, "magenta component: %s" % component_glyph_name, PAGE_MARGIN + 190, PAGE_HEIGHT - 60, 260, 9.5, COMPONENT_COLOR)
    if SHOW_ONLY_SOURCES_WITH_DISCREPANCIES:
        mode_text = "showing discrepancies only"
        mode_color = DISCREPANCY_COLOR
    else:
        mode_text = "showing all concrete UFOs"
        mode_color = (0, 0, 0, 0.55)
    draw_label(drawbot, mode_text, PAGE_WIDTH - PAGE_MARGIN - 210, PAGE_HEIGHT - 60, 210, 9.5, mode_color)


def get_row_rect(row_index):
    available_h = PAGE_HEIGHT - PAGE_MARGIN * 2 - HEADER_HEIGHT
    row_h = (available_h - ROW_GAP * (ROWS_PER_PAGE - 1)) / float(ROWS_PER_PAGE)
    row_top = PAGE_HEIGHT - PAGE_MARGIN - HEADER_HEIGHT - row_index * (row_h + ROW_GAP)
    row_y = row_top - row_h
    return PAGE_MARGIN, row_y, PAGE_WIDTH - PAGE_MARGIN * 2, row_h


def draw_source_row(
    drawbot,
    font,
    ufo_path,
    base_glyph_name,
    component_glyph_name,
    row_index,
    flags,
):
    base_glyph = get_glyph(font, base_glyph_name)
    component_glyph = get_glyph(font, component_glyph_name)
    source_label = get_source_label(font, ufo_path)
    descender, ascender = get_vertical_extents(font)
    row_x, row_y, row_w, row_h = get_row_rect(row_index)

    label_y = row_y + row_h - 20
    draw_label(drawbot, os.path.basename(ufo_path), row_x, label_y, row_w * 0.28, 10.5)
    draw_label(drawbot, source_label, row_x + row_w * 0.28, label_y, row_w * 0.26, 8, (0, 0, 0, 0.55))
    if flags:
        flag_text = "DISCREPANCY: %s" % ", ".join(flags)
        flag_color = DISCREPANCY_COLOR
        draw_label(drawbot, flag_text, row_x + row_w * 0.54, label_y, row_w * 0.46, 8.5, flag_color)

    detail_y = label_y - 13
    draw_label(drawbot, ufo_path, row_x, detail_y, row_w, 6.5, (0, 0, 0, 0.45))

    cell_y = row_y
    cell_h = row_h - 38
    cell_w = (row_w - CELL_GAP * 2) / 3.0
    cell_xs = [
        row_x,
        row_x + cell_w + CELL_GAP,
        row_x + (cell_w + CELL_GAP) * 2,
    ]
    labels = ["Source/base", "Component-built", "Overlay"]
    widths = [get_width(base_glyph), get_width(component_glyph), max(get_width(base_glyph), get_width(component_glyph))]
    vertical_size = ascender - descender
    scale = min(cell_w / max(max(widths), 1) * 0.72, cell_h / max(vertical_size, 1) * 0.82)

    for index, cell_x in enumerate(cell_xs):
        drawbot.fill(None)
        drawbot.stroke(0, 0, 0, 0.16)
        drawbot.strokeWidth(0.8)
        drawbot.rect(cell_x, cell_y, cell_w, cell_h)
        draw_label(drawbot, labels[index], cell_x + 4, cell_y + cell_h - 16, cell_w - 8, 7.5, (0, 0, 0, 0.62))

    if base_glyph is None:
        draw_missing(drawbot, base_glyph_name, cell_xs[0], cell_y, cell_w, cell_h)
    else:
        draw_glyph(drawbot, font, base_glyph, BASE_COLOR, cell_xs[0], cell_y, cell_w, cell_h, scale, descender, ascender)

    if component_glyph is None:
        draw_missing(drawbot, component_glyph_name, cell_xs[1], cell_y, cell_w, cell_h)
    else:
        draw_glyph(drawbot, font, component_glyph, COMPONENT_COLOR, cell_xs[1], cell_y, cell_w, cell_h, scale, descender, ascender)

    overlay_width = max(get_width(base_glyph), get_width(component_glyph))
    if base_glyph is not None:
        draw_glyph(
            drawbot,
            font,
            base_glyph,
            BASE_COLOR,
            cell_xs[2],
            cell_y,
            cell_w,
            cell_h,
            scale,
            descender,
            ascender,
            overlay_width,
        )
    if component_glyph is not None:
        draw_glyph(
            drawbot,
            font,
            component_glyph,
            COMPONENT_COLOR,
            cell_xs[2],
            cell_y,
            cell_w,
            cell_h,
            scale,
            descender,
            ascender,
            overlay_width,
        )


def parse_args(args):
    parser = argparse.ArgumentParser(description="Draw a PDF proof comparing a base glyph against a component-built glyph.")
    parser.add_argument("root_path", nargs="?", default=ROOT_PATH, help="Folder to search recursively for .ufo packages.")
    parser.add_argument("--base", default=BASE_GLYPH_NAME, help="Source/base glyph name.")
    parser.add_argument("--component", default=COMPONENT_GLYPH_NAME, help="Component-built glyph name.")
    parser.add_argument(
        "--scan-mode",
        choices=("folder-ufos",),
        default=SCAN_MODE,
        help="Scan mode. folder-ufos recursively finds concrete .ufo packages under root_path.",
    )
    parser.add_argument("--output", default=OUTPUT_PDF_PATH, help="PDF output path.")
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
    if options.scan_mode != "folder-ufos":
        print("Unsupported scan mode: %s" % options.scan_mode, file=sys.stderr)
        return 2

    try:
        drawbot = import_drawbot()
        open_font, defcon_font = import_openers()
    except ImportError as error:
        print(error, file=sys.stderr)
        return 2

    all_ufo_paths = find_ufo_paths(root_path)
    ufo_paths = [os.path.abspath(ufo_path) for ufo_path in all_ufo_paths if source_path_is_included(ufo_path)]
    ufo_paths = sorted(set(ufo_paths))

    if not ufo_paths:
        if all_ufo_paths:
            print(
                "Found %d .ufo packages below %s, but all were filtered out. "
                "Check SOURCE_PATH_INCLUDE_TEXT and SOURCE_PATH_EXCLUDE_TEXTS."
                % (len(all_ufo_paths), root_path),
                file=sys.stderr,
            )
        else:
            print("No .ufo packages found below: %s" % root_path, file=sys.stderr)
        return 1

    drawbot.newDrawing()
    rows_on_page = 0
    drawn_count = 0
    for ufo_path in ufo_paths:
        font = None
        try:
            font = open_ufo(ufo_path, open_font, defcon_font)
            base_glyph = get_glyph(font, options.base)
            component_glyph = get_glyph(font, options.component)
            flags = get_discrepancy_flags(base_glyph, component_glyph)
            if SHOW_ONLY_SOURCES_WITH_DISCREPANCIES and not flags:
                continue
            if rows_on_page == 0:
                draw_page_header(drawbot, options.base, options.component)
            draw_source_row(
                drawbot,
                font,
                ufo_path,
                options.base,
                options.component,
                rows_on_page,
                flags,
            )
            rows_on_page += 1
            drawn_count += 1
            if rows_on_page >= ROWS_PER_PAGE:
                rows_on_page = 0
        finally:
            if font is not None:
                close_font(font)

    if drawn_count == 0:
        draw_page_header(drawbot, options.base, options.component)
        draw_label(
            drawbot,
            "No matching UFOs to draw. Check source filtering or discrepancy-only mode.",
            PAGE_MARGIN,
            PAGE_HEIGHT / 2,
            PAGE_WIDTH - PAGE_MARGIN * 2,
            14,
            DISCREPANCY_COLOR,
        )

    output_path = os.path.abspath(os.path.expanduser(options.output))
    drawbot.saveImage(output_path)
    drawbot.endDrawing()
    print("Saved proof: %s (%d sources)" % (output_path, drawn_count))
    return 0


if __name__ == "__main__":
    main()
