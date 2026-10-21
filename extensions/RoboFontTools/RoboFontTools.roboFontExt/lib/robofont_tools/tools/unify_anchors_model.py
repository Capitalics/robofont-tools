"""Plan anchor additions against a designspace default without moving anchors."""
from __future__ import annotations

from collections import Counter
from pathlib import Path

from fontTools.designspaceLib import DesignSpaceDocument


def source_path(designspace_path, source):
    value = source.path or source.filename
    if not value:
        raise ValueError(f"Source {source.name or '(unnamed)'} has no UFO path")
    path = Path(value)
    if not path.is_absolute():
        path = Path(designspace_path).parent / path
    path = path.resolve()
    if path.suffix.lower() != ".ufo" or not path.is_dir():
        raise ValueError(f"Source UFO is missing: {path}")
    return path


def load_designspace(path, default_override=None):
    path = Path(path).resolve()
    if path.suffix.lower() != ".designspace" or not path.is_file():
        raise ValueError("Choose an existing .designspace file")
    document = DesignSpaceDocument.fromfile(path)
    sources = list(dict.fromkeys(source_path(path, source) for source in document.sources))
    if not sources:
        raise ValueError("The designspace has no source UFOs")
    if default_override:
        default = Path(default_override).resolve()
        if default not in sources:
            raise ValueError("The chosen default UFO is not a source in this designspace")
    else:
        default_source = document.findDefault()
        if default_source is None:
            raise ValueError("No default source found; choose a default UFO")
        default = source_path(path, default_source)
    return default, sources


def anchor_plan(default_anchors, source_anchors):
    """Return (missing anchors, extra names, duplicate names) for one glyph.

    Anchor values are (name, x, y). Duplicates make name matching ambiguous, so
    callers must skip that glyph rather than guess which anchor to preserve.
    """
    default = list(default_anchors)
    source = list(source_anchors)
    default_counts = Counter(name for name, _, _ in default)
    source_counts = Counter(name for name, _, _ in source)
    duplicates = sorted(name for name, count in (default_counts | source_counts).items()
                        if max(default_counts[name], source_counts[name]) > 1)
    if duplicates:
        return [], [], duplicates
    missing = [(name, x, y) for name, x, y in default if name not in source_counts]
    extras = [name for name, _, _ in source if name not in default_counts]
    return missing, extras, []


def anchor_records(glyph):
    return [(anchor.name, anchor.x, anchor.y) for anchor in glyph.anchors]


def desired_anchor_names(default_anchors, source_anchors):
    default_names = [name for name, _, _ in default_anchors]
    return default_names + [name for name, _, _ in source_anchors
                            if name not in default_names]


def append_anchor(glyph, name, x, y):
    if hasattr(glyph, "instantiateAnchor"):  # defcon glyph from a closed UFO
        anchor = glyph.instantiateAnchor()
        anchor.name, anchor.x, anchor.y = name, x, y
        glyph.appendAnchor(anchor)
    else:  # RoboFont/FontParts glyph in an open UFO
        glyph.appendAnchor(name, (x, y))


def order_anchors(glyph, names):
    """Reorder the underlying anchor objects, retaining positions and metadata."""
    raw_glyph = glyph.naked() if hasattr(glyph, "naked") else glyph
    by_name = {anchor.name: anchor for anchor in raw_glyph.anchors}
    for index, name in enumerate(names):
        anchor = by_name[name]
        if raw_glyph.anchors[index] is anchor:
            continue
        raw_glyph.removeAnchor(anchor)
        raw_glyph.insertAnchor(index, anchor)
