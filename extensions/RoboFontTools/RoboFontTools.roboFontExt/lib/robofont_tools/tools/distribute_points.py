"""Distribute Points: evenly space the selected points along one axis.

Unlike the other tools in this palette, this one is a one-shot action rather
than a live overlay. It owns no subscriber and no enabled state; it reads the
current glyph when a button is clicked, writes once inside a single undo
record, and returns.
"""
from __future__ import annotations

from dataclasses import dataclass
import traceback

from mojo.roboFont import CurrentGlyph

from .base import PaletteTool
from .distribute_points_model import (
    OFFCURVE,
    attached_offcurve_indices,
    even_distribution,
)

DEBUG = True
UNDO_TITLES = {
    "x": "Distribute Points Horizontally",
    "y": "Distribute Points Vertically",
}


def _debug(message):
    if DEBUG:
        print(f"Distribute Points: {message}")


@dataclass(frozen=True)
class _ContourRecord:
    """One contour that contributes at least one moving on-curve point."""

    points: tuple
    moving: dict          # contour point index -> position in participants
    closed: bool


def _collect(glyph) -> tuple[list, list[_ContourRecord]]:
    """Return the selected on-curve points and anchors, plus contour context.

    Off-curve points are never participants: they follow their on-curve point
    instead, so the curve around a moved node keeps its shape.
    """
    participants: list = []
    records: list[_ContourRecord] = []
    for contour in glyph.contours:
        points = tuple(contour.points)
        moving: dict = {}
        for index, point in enumerate(points):
            if point.type != OFFCURVE and point.selected:
                moving[index] = len(participants)
                participants.append(point)
        if moving:
            records.append(
                _ContourRecord(
                    points=points, moving=moving, closed=not contour.open
                )
            )
    for anchor in glyph.anchors:
        if anchor.selected:
            participants.append(anchor)
    return participants, records


def _move_handles(record: _ContourRecord, deltas: list, axis: str):
    """Shift each attached off-curve point by its on-curve point's delta."""
    point_types = [point.type for point in record.points]
    followers = attached_offcurve_indices(
        point_types, record.moving.keys(), record.closed
    )
    for offcurve_index, oncurve_index in followers.items():
        delta = deltas[record.moving[oncurve_index]]
        if not delta:
            continue
        point = record.points[offcurve_index]
        setattr(point, axis, float(getattr(point, axis)) + delta)


def distribute_selected_points(axis: str) -> bool:
    """Evenly space the selection along ``axis``. Returns True if it wrote.

    Every unmet precondition is a silent no-op: no glyph is touched and no
    undo record is created.
    """
    glyph = CurrentGlyph()
    if glyph is None:
        _debug("no current glyph")
        return False

    participants, records = _collect(glyph)
    if len(participants) < 3:
        _debug(f"{len(participants)} points/anchors selected; needs 3 or more")
        return False

    values = [float(getattr(participant, axis)) for participant in participants]
    distributed = even_distribution(values)
    if distributed is None:
        _debug(f"selection has no {axis} span to distribute across")
        return False

    # Deltas come from the original coordinates and are written in one pass, so
    # a shared handle can never be moved twice.
    deltas = [new - old for new, old in zip(distributed, values)]
    if not any(deltas):
        _debug("selection is already evenly distributed")
        return False

    with glyph.undo(UNDO_TITLES[axis]):
        for participant, value, delta in zip(participants, distributed, deltas):
            if delta:
                setattr(participant, axis, value)
        for record in records:
            _move_handles(record, deltas, axis)
    glyph.changed()
    _debug(f"distributed {len(participants)} points along {axis}")
    return True


class DistributePointsTool(PaletteTool):
    content = """
    * TwoColumnForm @distributePointsControl
    > : Distribute:
    > * HorizontalStack @distributePointsButtons
    >> (Horizontal) @distributeHorizontalButton
    >> (Vertical) @distributeVerticalButton
    """

    def descriptions(self):
        return {
            "distributePointsControl": {
                "titleColumnWidth": 70,
                "itemColumnWidth": 192,
            },
            "distributePointsButtons": {"distribution": "fill"},
            "distributeHorizontalButton": {
                "callback": lambda sender: self.distribute("x"),
            },
            "distributeVerticalButton": {
                "callback": lambda sender: self.distribute("y"),
            },
        }

    def distribute(self, axis: str):
        try:
            distribute_selected_points(axis)
        except Exception:
            print(f"Distribute Points: {axis} distribution failed")
            traceback.print_exc()
