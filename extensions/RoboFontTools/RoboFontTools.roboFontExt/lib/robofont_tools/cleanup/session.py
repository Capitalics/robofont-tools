"""Read and change the designspace's fonts for the Cleanup window.

Open fonts are changed in place with undo and left unsaved; closed UFOs are
loaded with defcon, changed, and saved. ``open_fonts`` returns
{resolved UFO path: RoboFont font}, so tests can pass an empty mapping.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .anchors import (
    apply_edit, audit_anchors, find_differences, plan_match_default, plan_remove_all,
)
from .audit import Audit, SourceMarks, ufo_layers
from .outlines import Contour, Outline, audit_outlines


@dataclass(frozen=True)
class FixResult:
    removed: tuple[tuple[str, str, int], ...]   # (source label, what, count)
    saved: tuple[str, ...]                      # closed sources that were saved
    no_undo: tuple[str, ...]                    # open sources changed without undo


@dataclass
class _Changes:
    """What one fix changed: closed UFOs still to save, open fonts without undo."""
    open_fonts: dict                                      # path -> RoboFont font
    to_save: dict[Path, set[str]] = field(default_factory=dict)  # path -> source labels
    no_undo: list[str] = field(default_factory=list)


def _load_closed(path):
    from defcon import Font
    return Font(str(path))


def _outline(glyph):
    """Plain outline data for one defcon glyph."""
    contours = tuple(
        Contour(tuple((point.segmentType or "offcurve", point.x, point.y)
                      for point in contour),
                not contour.open)
        for contour in glyph)
    return Outline(contours, tuple(component.baseGlyph for component in glyph.components))


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

    def _sources_at(self, path):
        """The sources in one UFO: the full source and any layer-sources."""
        return [source for source in self.sources if source.path == path]

    # --- the current glyph -------------------------------------------------

    def source_for(self, path, layer_name):
        """The source a Glyph Editor shows: a UFO path plus the layer on screen.

        ``layer_name`` None or the UFO's default layer means the full source.
        Returns None when that UFO or layer is not a source here.
        """
        path = Path(path).resolve()
        sharing = self._sources_at(path)
        if not sharing:
            return None
        if layer_name is not None:
            font = self._defcon_font(sharing[0], self._open_fonts())
            if layer_name == font.layers.defaultLayer.name:
                layer_name = None
        return next((source for source in sharing if source.layer == layer_name), None)

    def glyph_outlines(self, name):
        """Each source with its outline of ``name``, in designspace order.

        The outline is None where the glyph (or the source's layer) is absent.
        Open fonts are read live; closed UFOs come from the last load.
        """
        open_fonts = self._open_fonts()
        found = []
        for source in self.sources:
            layer = self._layer(source, open_fonts)
            outline = _outline(layer[name]) if layer is not None and name in layer else None
            found.append((source, outline))
        return tuple(found)

    # --- changing sources --------------------------------------------------

    def _change_glyphs(self, changes, source, names, title, change):
        """The one way to change glyphs in a source.

        ``change`` gets a defcon glyph. In an open font each glyph is changed
        inside an undo named ``title`` and left unsaved; in a closed UFO the
        source is marked for ``_save``.
        """
        font = changes.open_fonts.get(Path(source.path))
        if font is None:
            layer = self._layer(source, changes.open_fonts)
            for name in names:
                change(layer[name])
            changes.to_save.setdefault(source.path, set()).add(source.label)
            return
        layer = font.getLayer(source.layer or font.defaultLayerName)
        for name in names:
            glyph = layer[name]
            with glyph.undo(title):
                change(glyph.naked())
            glyph.changed()

    def _change_font(self, changes, source, label, change_open, change_closed):
        """Change a whole UFO: open fonts have no undo, closed ones are saved."""
        font = changes.open_fonts.get(Path(source.path))
        if font is not None:
            change_open(font)
            changes.no_undo.append(label)
            return
        change_closed(self._defcon_font(source, changes.open_fonts))
        changes.to_save.setdefault(source.path, set()).add(label)

    def _save(self, changes):
        """Save every changed closed UFO; return the changed source labels."""
        for path in changes.to_save:
            self._closed[path].save()
        return tuple(sorted(label for labels in changes.to_save.values() for label in labels))

    def _result(self, removed, changes):
        return FixResult(tuple(removed), self._save(changes), tuple(changes.no_undo))

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
        self._last_anchor_data = (default_glyphs, data)
        return default_glyphs, data

    def audit(self):
        """Read every source once and summarise what needs cleaning."""
        default_glyphs, others = self._anchor_data()
        open_fonts = self._open_fonts()
        marks = []
        for source in self.sources:
            layer = self._layer(source, open_fonts)
            if layer is None:
                continue
            guide_glyphs = glyph_guides = coloured = 0
            for glyph in layer:
                if glyph.guidelines:
                    guide_glyphs += 1
                    glyph_guides += len(glyph.guidelines)
                if glyph.markColor is not None:
                    coloured += 1
            font_guides = (len(self._defcon_font(source, open_fonts).guidelines)
                           if source.layer is None else 0)
            marks.append(SourceMarks(source.label, guide_glyphs, glyph_guides,
                                     font_guides, coloured))
        layers = []
        for path in dict.fromkeys(source.path for source in self.sources):
            sharing = self._sources_at(path)
            full = next((source for source in sharing if source.layer is None), None)
            label = full.label if full else Path(path).stem
            font = self._defcon_font(sharing[0], open_fonts)
            layers.append(ufo_layers(
                label,
                [(layer.name, len(layer)) for layer in font.layers],
                font.layers.defaultLayer.name,
                {source.layer for source in sharing if source.layer}))
        return Audit(audit_anchors(default_glyphs, others), tuple(layers), tuple(marks),
                     self._outline_audit(open_fonts))

    def _outline_audit(self, open_fonts):
        outlines = {}
        for source in self.sources:
            layer = self._layer(source, open_fonts)
            if layer is not None:
                outlines[source.label] = {glyph.name: _outline(glyph) for glyph in layer}
        default_glyphs = outlines.pop(self.default.label)
        return audit_outlines(default_glyphs, outlines)

    def scan(self):
        """Read every source once; return (audit, anchor report)."""
        audit = self.audit()
        return audit, find_differences(*self._last_anchor_data)

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

    # --- layers, guides, mark colours --------------------------------------

    def _label(self, path):
        sharing = self._sources_at(path)
        full = next((source for source in sharing if source.layer is None), None)
        return full.label if full else Path(path).stem

    def _glyph_fix(self, title, wanted, change, what):
        """Run ``change`` on every source glyph where ``wanted`` is true."""
        self._closed = {}
        changes = _Changes(self._open_fonts())
        removed = []
        for source in self.sources:
            layer = self._layer(source, changes.open_fonts)
            if layer is None:
                continue
            names = [glyph.name for glyph in layer if wanted(glyph)]
            if not names:
                continue
            removed.append((source.label, what, len(names)))
            self._change_glyphs(changes, source, names, title, change)
        return removed, changes

    def remove_extra_layers(self):
        """Delete every layer except each UFO's main layer and layer-sources."""
        self._closed = {}
        changes = _Changes(self._open_fonts())
        removed = []
        for path in dict.fromkeys(source.path for source in self.sources):
            sharing = self._sources_at(path)
            used = {source.layer for source in sharing if source.layer}
            font = self._defcon_font(sharing[0], changes.open_fonts)
            default_name = font.layers.defaultLayer.name
            extra = [(layer.name, len(layer)) for layer in font.layers
                     if layer.name != default_name and layer.name not in used]
            if not extra:
                continue
            label = self._label(path)
            removed += [(label, name, count) for name, count in extra]
            names = [name for name, _count in extra]

            def remove_open(open_font, names=names):
                for name in names:
                    open_font.removeLayer(name)

            def remove_closed(font, names=names):
                for name in names:
                    del font.layers[name]
            self._change_font(changes, sharing[0], label, remove_open, remove_closed)
        return self._result(removed, changes)

    def remove_guides(self):
        """Delete glyph guides in every source and font guides in full UFOs."""
        removed, changes = self._glyph_fix(
            "Remove Guides", lambda glyph: bool(glyph.guidelines),
            lambda glyph: glyph.clearGuidelines(), "glyph guides")
        result = []

        def clear(font):
            font.clearGuidelines()
        for source in self.sources:
            result += [item for item in removed if item[0] == source.label]
            if source.layer is not None:
                continue
            font = self._defcon_font(source, changes.open_fonts)
            if not font.guidelines:
                continue
            result.append((source.label, "font guides", len(font.guidelines)))
            self._change_font(changes, source, source.label, clear, clear)
        return self._result(result, changes)

    def strip_mark_colours(self):
        """Clear the mark colour of every glyph in every source."""
        def clear(glyph):
            glyph.markColor = None
        removed, changes = self._glyph_fix(
            "Strip Mark Colours", lambda glyph: glyph.markColor is not None,
            clear, "mark colours")
        return self._result(removed, changes)

    def _apply(self, edits, title):
        """Apply edits; return the labels of closed sources that were saved."""
        changes = _Changes(self._open_fonts())
        by_label = {source.label: source for source in self.sources}
        for edit in edits:
            self._change_glyphs(changes, by_label[edit.source], [edit.glyph], title,
                                lambda glyph, edit=edit: apply_edit(glyph, edit))
        return self._save(changes)
