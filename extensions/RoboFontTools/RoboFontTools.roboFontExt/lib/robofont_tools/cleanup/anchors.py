"""Anchor compatibility across designspace sources. No RoboFont imports.

Glyph data comes in as plain mappings: glyph name -> ordered list of
(anchor name, x, y). Sources are identified by their label. The goal is that
every glyph in the default has the same anchor names, in the same order, in
every source that has the glyph.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass


@dataclass(frozen=True)
class Row:
    glyph: str
    differences: str     # e.g. "Bold: missing bottom · Light: order"
    duplicates: bool     # a duplicate name makes Match Default impossible


@dataclass(frozen=True)
class Report:
    rows: tuple[Row, ...]
    absent: tuple[str, ...]           # default glyphs missing from some source (allowed)
    outside_default: tuple[str, ...]  # glyphs only in other sources (never built)


@dataclass(frozen=True)
class GlyphEdit:
    """Make one glyph's anchors exactly ``target``, in that order.

    Anchors already present keep their own position; names in ``added`` are
    created at the target coordinates (copied from the default).
    """
    source: str
    glyph: str
    target: tuple[tuple[str, float, float], ...]
    added: tuple[str, ...]


def _names(anchors):
    return [name for name, _x, _y in anchors]


def _duplicates(anchors):
    return sorted(name for name, count in Counter(_names(anchors)).items() if count > 1)


def _compare(default_anchors, anchors):
    """Describe how ``anchors`` differ from the default, or return ''."""
    duplicates = _duplicates(anchors)
    if duplicates:
        return "duplicate " + ", ".join(duplicates)
    default_names, names = _names(default_anchors), _names(anchors)
    if names == default_names:
        return ""
    missing = [name for name in default_names if name not in names]
    extra = [name for name in names if name not in default_names]
    parts = []
    if missing:
        parts.append("missing " + ", ".join(missing))
    if extra:
        parts.append("extra " + ", ".join(extra))
    return " · ".join(parts) or "order"


ISSUES = ("missing", "extra", "order", "duplicate")


def issues(default_anchors, anchors):
    """Return the set of ISSUES for one source glyph against the default."""
    if _duplicates(anchors):
        return {"duplicate"}
    default_names, names = _names(default_anchors), _names(anchors)
    if names == default_names:
        return set()
    found = set()
    if any(name not in names for name in default_names):
        found.add("missing")
    if any(name not in default_names for name in names):
        found.add("extra")
    return found or {"order"}


@dataclass(frozen=True)
class AnchorAudit:
    glyphs: dict      # issue -> tuple of glyph names
    sources: dict     # issue -> {source label: glyph count}


def audit_anchors(default_glyphs, others) -> AnchorAudit:
    """Count glyphs per issue, overall and per source ("default" for its own duplicates)."""
    glyphs = {issue: set() for issue in ISSUES}
    sources = {issue: {} for issue in ISSUES}

    def note(issue, glyph_name, label):
        glyphs[issue].add(glyph_name)
        sources[issue][label] = sources[issue].get(label, 0) + 1

    for glyph_name, default_anchors in default_glyphs.items():
        if _duplicates(default_anchors):
            note("duplicate", glyph_name, "default")
            continue
        for label, source_glyphs in others.items():
            if glyph_name in source_glyphs:
                for issue in issues(default_anchors, source_glyphs[glyph_name]):
                    note(issue, glyph_name, label)
    return AnchorAudit({issue: tuple(sorted(names)) for issue, names in glyphs.items()},
                       sources)


def find_differences(default_glyphs, others) -> Report:
    """Compare every default glyph with the same glyph in each other source."""
    rows = []
    absent = set()
    for glyph_name in sorted(default_glyphs):
        default_anchors = default_glyphs[glyph_name]
        notes = []
        duplicates = bool(_duplicates(default_anchors))
        if duplicates:
            notes.append("default: duplicate " + ", ".join(_duplicates(default_anchors)))
        for label, glyphs in others.items():
            if glyph_name not in glyphs:
                absent.add(glyph_name)
                continue
            if duplicates:
                continue
            note = _compare(default_anchors, glyphs[glyph_name])
            if note:
                notes.append(f"{label}: {note}")
                duplicates = duplicates or note.startswith("duplicate")
        if notes:
            rows.append(Row(glyph_name, " · ".join(notes), duplicates))
    outside = {name for glyphs in others.values() for name in glyphs} - set(default_glyphs)
    return Report(tuple(rows), tuple(sorted(absent)), tuple(sorted(outside)))


def plan_match_default(default_glyphs, others, glyph_names):
    """Return (edits, skipped glyphs) that make sources match the default."""
    edits = []
    skipped = []
    for glyph_name in glyph_names:
        default_anchors = default_glyphs.get(glyph_name)
        if default_anchors is None:
            continue
        sources = [(label, glyphs[glyph_name]) for label, glyphs in others.items()
                   if glyph_name in glyphs]
        if _duplicates(default_anchors) or any(_duplicates(a) for _l, a in sources):
            skipped.append(glyph_name)
            continue
        target = tuple(default_anchors)
        for label, anchors in sources:
            if _names(anchors) == _names(default_anchors):
                continue
            added = tuple(name for name in _names(default_anchors)
                          if name not in _names(anchors))
            edits.append(GlyphEdit(label, glyph_name, target, added))
    return tuple(edits), tuple(skipped)


def plan_remove_all(default_label, default_glyphs, others, glyph_names):
    """Return edits that remove the glyphs' anchors from every source."""
    edits = []
    every = {default_label: default_glyphs, **others}
    for glyph_name in glyph_names:
        for label, glyphs in every.items():
            if glyphs.get(glyph_name):
                edits.append(GlyphEdit(label, glyph_name, (), ()))
    return tuple(edits)


def apply_edit(glyph, edit: GlyphEdit):
    """Apply ``edit`` to a defcon glyph (use ``naked()`` for a RoboFont glyph)."""
    if not edit.target:
        glyph.clearAnchors()
        return
    target_names = [name for name, _x, _y in edit.target]
    existing = {anchor.name: anchor for anchor in glyph.anchors}
    for anchor in list(glyph.anchors):
        if anchor.name not in target_names:
            glyph.removeAnchor(anchor)
    for name, x, y in edit.target:
        if name not in existing:
            anchor = glyph.instantiateAnchor()
            anchor.name, anchor.x, anchor.y = name, x, y
            glyph.appendAnchor(anchor)
    # Reorder the anchor objects themselves so positions and metadata stay.
    current = {anchor.name: anchor for anchor in glyph.anchors}
    for index, name in enumerate(target_names):
        anchor = current[name]
        if glyph.anchors[index] is anchor:
            continue
        glyph.removeAnchor(anchor)
        glyph.insertAnchor(index, anchor)
