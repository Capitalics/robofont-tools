"""Read a designspace into the sources the Cleanup window works on.

Needs fontTools but no RoboFont. A source is one UFO plus, for a sparse
layer-source (``<source layer="…">``), the layer inside it.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from fontTools.designspaceLib import DesignSpaceDocument


@dataclass(frozen=True)
class Source:
    label: str             # unique within one designspace
    path: Path
    layer: str | None      # None means the UFO's default layer


def _source_path(designspace_path, descriptor):
    value = descriptor.path or descriptor.filename
    if not value:
        raise ValueError(f"Source {descriptor.name or '(unnamed)'} has no UFO path")
    path = Path(value)
    if not path.is_absolute():
        path = Path(designspace_path).parent / path
    path = path.resolve()
    if path.suffix.lower() != ".ufo" or not path.is_dir():
        raise ValueError(f"Source UFO is missing: {path}")
    return path


def load_designspace(path, default_override=None):
    """Return (default source, all sources) in designspace order.

    ``default_override`` is a UFO path; it must be a full (non-layer) source.
    """
    path = Path(path).resolve()
    if path.suffix.lower() != ".designspace" or not path.is_file():
        raise ValueError("Choose an existing .designspace file")
    document = DesignSpaceDocument.fromfile(path)
    sources = []
    seen = set()
    labels = set()
    default = None
    default_descriptor = document.findDefault()
    for descriptor in document.sources:
        ufo = _source_path(path, descriptor)
        layer = descriptor.layerName or None
        if (ufo, layer) in seen:
            continue
        seen.add((ufo, layer))
        label = descriptor.name or ufo.stem
        if layer:
            label = f"{label} [{layer}]" if layer not in label else label
        base, number = label, 2
        while label in labels:
            label, number = f"{base} ({number})", number + 1
        labels.add(label)
        source = Source(label, ufo, layer)
        sources.append(source)
        if default_override is None and descriptor is default_descriptor:
            default = source
    if not sources:
        raise ValueError("The designspace has no source UFOs")
    if default_override is not None:
        wanted = Path(default_override).resolve()
        default = next((source for source in sources
                        if source.path == wanted and source.layer is None), None)
        if default is None:
            raise ValueError("The chosen default UFO is not a full source in this designspace")
    elif default is None:
        raise ValueError("No default source found; choose a default UFO")
    return default, sources
