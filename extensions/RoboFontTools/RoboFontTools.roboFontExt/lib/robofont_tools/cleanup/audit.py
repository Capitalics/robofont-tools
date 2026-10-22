"""The Cleanup audit: what needs doing across a designspace. No RoboFont imports.

Read-only. Anchors have fixes in the Anchors section; layers, guides and mark
colours are reported only (fixes are planned separately).
"""
from __future__ import annotations

from dataclasses import dataclass

from .anchors import ISSUES, AnchorAudit

BACKGROUND_LAYERS = ("public.background", "background")

ISSUE_TITLES = {
    "missing": "missing anchors",
    "extra": "extra anchors",
    "order": "anchor order only",
    "duplicate": "duplicate anchor names",
}


def _glyphs(count):
    return f"{count} glyph" if count == 1 else f"{count} glyphs"


@dataclass(frozen=True)
class UfoLayers:
    label: str
    extra: tuple[tuple[str, int], ...]   # (layer name, glyph count), background excluded
    background: int | None               # glyph count, None if no background layer


@dataclass(frozen=True)
class SourceMarks:
    label: str
    guide_glyphs: int
    glyph_guides: int
    font_guides: int
    coloured_glyphs: int


@dataclass(frozen=True)
class AuditLine:
    text: str
    issue: str | None = None   # anchor issue this line selects in the list


@dataclass(frozen=True)
class Audit:
    anchors: AnchorAudit
    layers: tuple[UfoLayers, ...]
    marks: tuple[SourceMarks, ...]

    def lines(self) -> tuple[AuditLine, ...]:
        result = []
        anchor_lines = []
        for issue in ISSUES:
            count = len(self.anchors.glyphs[issue])
            if count:
                by_source = ", ".join(f"{label} {number}" for label, number
                                      in self.anchors.sources[issue].items())
                anchor_lines.append(AuditLine(
                    f"Anchors · {ISSUE_TITLES[issue]}: {_glyphs(count)} ({by_source})", issue))
        result += anchor_lines or [AuditLine("Anchors · compatible")]

        layer_lines = []
        for ufo in self.layers:
            parts = [f"{name} ({count})" for name, count in ufo.extra]
            if parts:
                layer_lines.append(AuditLine(f"Layers · {ufo.label}: {', '.join(parts)}"))
        backgrounds = [f"{ufo.label} {ufo.background}" for ufo in self.layers
                       if ufo.background]
        if backgrounds:
            layer_lines.append(AuditLine("Layers · background glyphs: " + ", ".join(backgrounds)))
        result += layer_lines or [AuditLine("Layers · no extra layers")]

        guide_parts = [f"{m.label}: {_glyphs(m.guide_glyphs)} / {m.glyph_guides} guides"
                       + (f" · {m.font_guides} font guides" if m.font_guides else "")
                       for m in self.marks if m.glyph_guides or m.font_guides]
        result.append(AuditLine("Guides · " + ("; ".join(guide_parts) or "none")))

        colour_parts = [f"{m.label} {m.coloured_glyphs}" for m in self.marks
                        if m.coloured_glyphs]
        result.append(AuditLine("Mark colours · " + (", ".join(colour_parts) or "none")))
        return tuple(result)


def ufo_layers(label, layer_counts, default_layer, used_layers):
    """Summarise one UFO's layers beyond its main layer and layer-sources.

    ``layer_counts`` is [(layer name, glyph count)] in the UFO's layer order.
    """
    extra = []
    background = None
    for name, count in layer_counts:
        if name == default_layer or name in used_layers:
            continue
        if name in BACKGROUND_LAYERS:
            background = (background or 0) + count
        else:
            extra.append((name, count))
    return UfoLayers(label, tuple(extra), background)
