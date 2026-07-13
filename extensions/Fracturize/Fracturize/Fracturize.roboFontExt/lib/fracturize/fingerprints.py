from __future__ import annotations

import hashlib
import json

from .model import GlyphOutline
from .ufo import LIB_KEY


def _outline_payload(outline: GlyphOutline) -> dict:
    contours = []
    for contour in outline.contours:
        segments = []
        for segment in contour.segments:
            if hasattr(segment, "control1"):
                segments.append(
                    {
                        "type": "cubic",
                        "start": list(segment.start),
                        "control1": list(segment.control1),
                        "control2": list(segment.control2),
                        "end": list(segment.end),
                    }
                )
            else:
                segments.append(
                    {
                        "type": "line",
                        "start": list(segment.start),
                        "end": list(segment.end),
                    }
                )
        contours.append({"closed": contour.closed, "segments": segments})
    return {
        "fingerprintVersion": 1,
        "name": outline.name,
        "width": outline.width,
        "unitsPerEm": outline.units_per_em,
        "unicodes": list(outline.unicodes),
        "components": list(outline.components),
        "contours": contours,
    }


def source_fingerprint(outline: GlyphOutline) -> str:
    payload = json.dumps(
        _outline_payload(outline),
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def glyph_content_digest(glyph) -> str:
    """Hash generated content that must continue to match stored topology."""

    payload = {
        "digestVersion": 1,
        "name": glyph.name,
        "width": glyph.width,
        "unicodes": list(glyph.unicodes),
        "contours": [
            {
                "identifier": contour.identifier,
                "points": [
                    {
                        "x": point.x,
                        "y": point.y,
                        "type": point.segmentType,
                        "smooth": point.smooth,
                        "identifier": point.identifier,
                    }
                    for point in contour
                ],
            }
            for contour in glyph
        ],
        "components": [
            {
                "baseGlyph": component.baseGlyph,
                "transformation": list(component.transformation),
                "identifier": component.identifier,
            }
            for component in glyph.components
        ],
        "fragmentMap": glyph.lib.get(LIB_KEY),
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()
