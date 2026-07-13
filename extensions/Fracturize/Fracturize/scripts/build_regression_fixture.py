from __future__ import annotations

"""Build the redistributable UFO used by Fracturize integration tests.

The drawings are original geometric constructions created for this repository.
Regenerate the fixture after changing this script; do not edit its GLIF files by
hand. The fixture intentionally includes multiply-wound overlap contours,
curves, components, metadata, a background layer, kerning, groups, features,
font guidelines, and a data file.
"""

import argparse
import shutil
from pathlib import Path

from defcon import Font


GLYPH_ORDER = (
    "A",
    "H",
    "I",
    "M",
    "O",
    "R",
    "S",
    "a",
    "dotaccentcomb",
    "eight",
    "idotless",
    "i",
)


def _polygon(glyph, points):
    pen = glyph.getPen()
    pen.moveTo(points[0])
    for point in points[1:]:
        pen.lineTo(point)
    pen.closePath()


def _rectangle(glyph, x0, y0, x1, y1, *, reverse=False):
    points = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
    if reverse:
        points.reverse()
    _polygon(glyph, points)


def _cubic_ellipse(glyph, cx, cy, rx, ry, *, reverse=False):
    # Standard four-cubic ellipse approximation. Coordinates are deliberately
    # synthetic and unrelated to any production typeface.
    k = 0.5522847498307936
    segments = [
        ((cx + rx, cy), (cx + rx, cy + k * ry), (cx + k * rx, cy + ry), (cx, cy + ry)),
        ((cx, cy + ry), (cx - k * rx, cy + ry), (cx - rx, cy + k * ry), (cx - rx, cy)),
        ((cx - rx, cy), (cx - rx, cy - k * ry), (cx - k * rx, cy - ry), (cx, cy - ry)),
        ((cx, cy - ry), (cx + k * rx, cy - ry), (cx + rx, cy - k * ry), (cx + rx, cy)),
    ]
    if reverse:
        reversed_segments = []
        for start, control1, control2, end in reversed(segments):
            reversed_segments.append((end, control2, control1, start))
        segments = reversed_segments
    pen = glyph.getPen()
    pen.moveTo(segments[0][0])
    for _, control1, control2, end in segments:
        pen.curveTo(control1, control2, end)
    pen.closePath()


def _multiply_wound_overlap(glyph, *, x=40, y=0, width=290, height=620, shift=170):
    """Draw one stable self-intersecting contour with a winding-2 overlap.

    Two incomplete rectangular loops are connected by distinct diagonals. The
    crossings are point intersections rather than coincident edges, allowing
    the bounded non-zero normalization policy to distinguish intentional
    multiply-wound construction from malformed geometry.
    """

    left = x
    right = x + width
    second_left = x + shift
    second_right = second_left + width
    bottom = y
    top = y + height
    second_bottom = y - 70
    second_top = y + height - 70
    points = [
        (left, bottom),
        (right, bottom),
        (right, top),
        (left, top),
        (left, y + 120),
        (second_left, second_bottom),
        (second_right, second_bottom),
        (second_right, second_top),
        (second_left, second_top),
        (second_left, y + 70),
    ]
    _polygon(glyph, points)


def _set_basic_glyph_data(glyph, width, unicode_value=None):
    glyph.width = width
    if unicode_value is not None:
        glyph.unicodes = [unicode_value]


def build_fixture(path: Path):
    if path.exists():
        shutil.rmtree(path)

    font = Font()
    font.info.familyName = "Fracturize Regression"
    font.info.styleName = "Synthetic Regular"
    font.info.unitsPerEm = 1000
    font.info.ascender = 800
    font.info.descender = -200
    font.info.capHeight = 700
    font.info.xHeight = 500
    font.info.copyright = "Original synthetic test data; redistributable with this repository."
    font.lib["com.fracturize.fixture.provenance"] = {
        "generator": "scripts/build_regression_fixture.py",
        "license": "original synthetic regression data",
    }

    guideline = font.instantiateGuideline()
    guideline.y = 500
    guideline.name = "synthetic x-height check"
    guideline.color = "0.2,0.5,0.8,0.6"
    font.appendGuideline(guideline)

    # Four independent variants retain the historical names used by the
    # overlap-normalization regression while using original geometry.
    for name, offset, unicode_value in (
        ("A", 0, 0x0041),
        ("M", 24, 0x004D),
        ("R", 48, 0x0052),
        ("eight", 72, 0x0038),
    ):
        glyph = font.newGlyph(name)
        _set_basic_glyph_data(glyph, 590 + offset, unicode_value)
        _multiply_wound_overlap(
            glyph,
            x=35 + offset * 0.15,
            y=10 + offset * 0.1,
            width=275 + offset * 0.2,
            height=650 - offset * 0.25,
            shift=155 + offset * 0.1,
        )

    glyph = font.newGlyph("H")
    _set_basic_glyph_data(glyph, 620, 0x0048)
    _rectangle(glyph, 60, 0, 190, 700)
    _rectangle(glyph, 430, 0, 560, 700)
    _rectangle(glyph, 160, 285, 460, 420)

    glyph = font.newGlyph("I")
    _set_basic_glyph_data(glyph, 300, 0x0049)
    _rectangle(glyph, 85, 0, 215, 700)

    glyph = font.newGlyph("O")
    _set_basic_glyph_data(glyph, 690, 0x004F)
    _cubic_ellipse(glyph, 345, 350, 300, 350)
    _cubic_ellipse(glyph, 345, 350, 155, 215, reverse=True)
    glyph.note = "Synthetic cubic counter used for flattening and metadata tests."
    glyph.lib["com.fracturize.fixture.glyphData"] = {"purpose": "cubic-counter"}
    anchor = glyph.instantiateAnchor()
    anchor.name = "top"
    anchor.x = 345
    anchor.y = 735
    glyph.appendAnchor(anchor)

    glyph = font.newGlyph("S")
    _set_basic_glyph_data(glyph, 620, 0x0053)
    pen = glyph.getPen()
    pen.moveTo((540, 610))
    pen.curveTo((430, 735), (110, 730), (75, 500))
    pen.curveTo((45, 300), (465, 390), (445, 175))
    pen.curveTo((430, 25), (165, 15), (70, 130))
    pen.lineTo((145, 245))
    pen.curveTo((235, 160), (335, 165), (330, 230))
    pen.curveTo((340, 330), (35, 270), (60, 500))
    pen.curveTo((82, 725), (430, 785), (585, 690))
    pen.closePath()

    glyph = font.newGlyph("a")
    _set_basic_glyph_data(glyph, 570, 0x0061)
    _cubic_ellipse(glyph, 270, 245, 205, 235)
    _cubic_ellipse(glyph, 270, 245, 85, 115, reverse=True)
    _rectangle(glyph, 405, 0, 520, 500)

    glyph = font.newGlyph("idotless")
    _set_basic_glyph_data(glyph, 280, 0x0131)
    _rectangle(glyph, 85, 0, 195, 500)

    glyph = font.newGlyph("dotaccentcomb")
    _set_basic_glyph_data(glyph, 0, 0x0307)
    _cubic_ellipse(glyph, 140, 665, 65, 55)

    glyph = font.newGlyph("i")
    _set_basic_glyph_data(glyph, 280, 0x0069)
    pen = glyph.getPen()
    pen.addComponent("idotless", (1, 0, 0, 1, 0, 0))
    pen.addComponent("dotaccentcomb", (1, 0, 0, 1, 0, 0))

    font.groups["public.kern1.syntheticLeft"] = ["H", "I"]
    font.groups["public.kern2.syntheticRound"] = ["O", "S"]
    font.kerning[("public.kern1.syntheticLeft", "public.kern2.syntheticRound")] = -45
    font.features.text = "feature kern { pos H O -35; } kern;\n"
    font.data["com.fracturize.fixture/README.txt"] = (
        b"Original synthetic Fracturize regression fixture.\n"
    )

    background = font.layers.newLayer("public.background")
    background.color = "0.5,0.5,0.5,0.3"
    background_o = background.newGlyph("O")
    background_o.width = 690
    _rectangle(background_o, 25, -20, 665, 720)

    font.glyphOrder = list(GLYPH_ORDER)
    font.save(path, formatVersion=3)
    font.close()


def main():
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=root / "tests" / "fixtures" / "FracturizeRegression.ufo",
    )
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    build_fixture(args.output.resolve())
    print(args.output.resolve())


if __name__ == "__main__":
    main()
