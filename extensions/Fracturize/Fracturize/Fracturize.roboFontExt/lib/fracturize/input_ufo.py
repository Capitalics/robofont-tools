from __future__ import annotations

from pathlib import Path

from defcon import Font

from .geometry import UnsupportedOutlineError
from .model import CubicSegment, GlyphOutline, LineSegment, SourceContour


def defcon_glyph_to_outline(glyph, *, units_per_em: float) -> GlyphOutline:
    """Convert one defcon glyph to the Stage 1 source model without mutation."""

    if glyph.components:
        component_names = ", ".join(component.baseGlyph for component in glyph.components)
        raise UnsupportedOutlineError(
            f"components are unsupported in Stage 1: {component_names}"
        )

    contours = []
    for contour_index, contour in enumerate(glyph):
        if contour.open:
            raise UnsupportedOutlineError(f"contour {contour_index} is open")
        defcon_segments = list(contour.segments)
        if not defcon_segments:
            raise UnsupportedOutlineError(f"contour {contour_index} is empty")

        previous_oncurve = defcon_segments[-1][-1]
        segments = []
        for segment_index, segment in enumerate(defcon_segments):
            oncurve = segment[-1]
            segment_type = oncurve.segmentType
            start = (float(previous_oncurve.x), float(previous_oncurve.y))
            end = (float(oncurve.x), float(oncurve.y))
            if segment_type == "line":
                if len(segment) != 1:
                    raise UnsupportedOutlineError(
                        f"contour {contour_index} line segment {segment_index} has off-curves"
                    )
                segments.append(LineSegment(start, end))
            elif segment_type == "curve":
                if len(segment) != 3:
                    raise UnsupportedOutlineError(
                        f"contour {contour_index} cubic segment {segment_index} does not have two controls"
                    )
                control1, control2, _ = segment
                segments.append(
                    CubicSegment(
                        start,
                        (float(control1.x), float(control1.y)),
                        (float(control2.x), float(control2.y)),
                        end,
                    )
                )
            else:
                raise UnsupportedOutlineError(
                    f"unsupported segment type {segment_type!r} at contour {contour_index}, segment {segment_index}"
                )
            previous_oncurve = oncurve
        contours.append(SourceContour(tuple(segments), closed=True))

    if not contours:
        raise UnsupportedOutlineError("outline has no contours")

    return GlyphOutline(
        name=glyph.name,
        width=float(glyph.width or 0),
        units_per_em=float(units_per_em),
        contours=tuple(contours),
        unicodes=tuple(glyph.unicodes),
    )


def load_ufo_outlines(path: Path):
    """Load supported outlines and explicit per-glyph rejection records."""

    font = Font(path)
    units_per_em = float(font.info.unitsPerEm or 1000)
    outlines = []
    rejected = []
    for glyph_name in font.keys():
        glyph = font[glyph_name]
        try:
            outlines.append(defcon_glyph_to_outline(glyph, units_per_em=units_per_em))
        except UnsupportedOutlineError as error:
            rejected.append({"glyph": glyph_name, "reason": str(error)})
    metadata = {
        "familyName": font.info.familyName,
        "styleName": font.info.styleName,
        "unitsPerEm": units_per_em,
        "glyphCount": len(font),
        "glyphOrder": list(font.keys()),
    }
    font.close()
    return tuple(outlines), tuple(rejected), metadata

