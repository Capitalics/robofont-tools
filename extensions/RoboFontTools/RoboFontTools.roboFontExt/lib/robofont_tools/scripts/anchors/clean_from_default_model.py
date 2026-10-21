"""Pure planning for removing anchor names absent from a default glyph."""
from __future__ import annotations


def extra_anchor_names(default_names, source_names):
    """Return source extras in their original order, including duplicates."""
    allowed = set(default_names)
    return tuple(name for name in source_names if name not in allowed)


def plan_font(default_glyph_anchors, source_glyph_anchors):
    """Return (changes, missing glyphs) without modifying either font.

    The mappings contain glyph names and ordered anchor-name sequences.
    Glyphs absent from the default are skipped, while a default glyph with no
    anchors intentionally removes every anchor from its matching source glyph.
    """
    changes = {}
    missing = []
    for glyph_name, source_names in source_glyph_anchors.items():
        if glyph_name not in default_glyph_anchors:
            if source_names:
                missing.append(glyph_name)
            continue
        extras = extra_anchor_names(default_glyph_anchors[glyph_name], source_names)
        if extras:
            changes[glyph_name] = extras
    return changes, tuple(sorted(missing))
