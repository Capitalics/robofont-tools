"""Read and change the designspace's fonts for the Cleanup window.

Open fonts are changed in place with undo and left unsaved; closed UFOs are
loaded with defcon, changed, and saved. ``open_fonts`` returns
{resolved UFO path: RoboFont font}, so tests can pass an empty mapping.
"""
from __future__ import annotations

from pathlib import Path

from .anchors import apply_edit, find_differences, plan_match_default, plan_remove_all


def _load_closed(path):
    from defcon import Font
    return Font(str(path))


class CleanupSession:
    def __init__(self, default, sources, open_fonts, load_closed=_load_closed):
        self.default = default
        self.sources = list(sources)
        self._open_fonts = open_fonts
        self._load_closed = load_closed
        self._closed = {}   # path -> defcon Font, reloaded on every scan
        self.warnings = ()  # sources skipped in the last scan, with the reason

    # --- fonts -----------------------------------------------------------

    def is_open(self, source):
        return Path(source.path) in self._open_fonts()

    def _defcon_font(self, source, open_fonts):
        font = open_fonts.get(Path(source.path))
        if font is not None:
            return font.naked() if hasattr(font, "naked") else font
        if source.path not in self._closed:
            self._closed[source.path] = self._load_closed(source.path)
        return self._closed[source.path]

    def _layer(self, source, open_fonts):
        font = self._defcon_font(source, open_fonts)
        if source.layer is None:
            return font.layers.defaultLayer
        if source.layer not in font.layers:
            return None
        return font.layers[source.layer]

    # --- anchors ---------------------------------------------------------

    def _anchor_data(self):
        self._closed = {}
        open_fonts = self._open_fonts()
        data = {}
        warnings = []
        for source in self.sources:
            layer = self._layer(source, open_fonts)
            if layer is None:
                if source == self.default:
                    raise ValueError(f"{source.label}: layer '{source.layer}' not found")
                warnings.append(f"{source.label}: layer '{source.layer}' not found; skipped")
                continue
            data[source.label] = {
                glyph.name: [(a.name, a.x, a.y) for a in glyph.anchors]
                for glyph in layer
            }
        self.warnings = tuple(warnings)
        default_glyphs = data.pop(self.default.label)
        return default_glyphs, data

    def anchor_report(self):
        default_glyphs, others = self._anchor_data()
        return find_differences(default_glyphs, others)

    def match_default(self, glyph_names):
        default_glyphs, others = self._anchor_data()
        edits, skipped = plan_match_default(default_glyphs, others, glyph_names)
        return self._apply(edits, "Match Default Anchors"), skipped, edits

    def remove_all(self, glyph_names):
        default_glyphs, others = self._anchor_data()
        edits = plan_remove_all(self.default.label, default_glyphs, others, glyph_names)
        return self._apply(edits, "Remove All Anchors"), (), edits

    def _apply(self, edits, title):
        """Apply edits; return the labels of closed sources that were saved."""
        open_fonts = self._open_fonts()
        by_label = {source.label: source for source in self.sources}
        changed_closed = {}   # path -> labels
        for edit in edits:
            source = by_label[edit.source]
            font = open_fonts.get(Path(source.path))
            if font is not None:
                layer = font.getLayer(source.layer or font.defaultLayerName)
                glyph = layer[edit.glyph]
                with glyph.undo(title):
                    apply_edit(glyph.naked(), edit)
                glyph.changed()
            else:
                apply_edit(self._layer(source, open_fonts)[edit.glyph], edit)
                changed_closed.setdefault(source.path, set()).add(source.label)
        for path in changed_closed:
            self._closed[path].save()
        return tuple(sorted(label for labels in changed_closed.values() for label in labels))
