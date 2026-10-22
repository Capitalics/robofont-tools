"""Outline compatibility against the Default source. No RoboFont imports.

Outlines come in as plain data: contours of ordered (point type, x, y), with
"offcurve" for off-curve points, plus component base-glyph names. Points
match by contour index and point index, the way interpolation pairs them.
"""
from __future__ import annotations

from dataclasses import dataclass
from itertools import permutations


@dataclass(frozen=True)
class Contour:
    points: tuple[tuple[str, float, float], ...]
    closed: bool = True


@dataclass(frozen=True)
class Outline:
    contours: tuple[Contour, ...] = ()
    components: tuple[str, ...] = ()


def _types(points):
    return tuple(point[0] for point in points)


def _reversed(contour):
    """The contour's points running the other way, keeping its start point.

    An on-curve point's type names the segment that arrives at it, so after
    reversal each takes the type of the next on-curve point in the old order.
    """
    points = list(contour.points)
    if not points:
        return ()
    on_curve = [index for index, point in enumerate(points) if point[0] != "offcurve"]
    following = on_curve[1:] + on_curve[:1] if contour.closed else on_curve[1:]
    types = {index: points[after][0] for index, after in zip(on_curve, following)}
    flipped = [(types.get(index, kind), x, y) for index, (kind, x, y) in enumerate(points)]
    if contour.closed:
        return tuple(flipped[:1] + flipped[:0:-1])
    flipped.reverse()
    return (("move", *flipped[0][1:]),) + tuple(flipped[1:])


def _normalised(points):
    """Points scaled into their own unit box, so masters of any weight compare."""
    if not points:
        return []
    xs = [point[1] for point in points]
    ys = [point[2] for point in points]
    width = (max(xs) - min(xs)) or 1
    height = (max(ys) - min(ys)) or 1
    return [((x - min(xs)) / width, (y - min(ys)) / height) for x, y in zip(xs, ys)]


def _distance(a, b):
    return sum((ax - bx) ** 2 + (ay - by) ** 2
               for (ax, ay), (bx, by) in zip(_normalised(a), _normalised(b)))


def _area(points):
    """Twice the signed area of the point polygon; positive is counter-clockwise."""
    return sum(x0 * y1 - x1 * y0 for (_t0, x0, y0), (_t1, x1, y1)
               in zip(points, points[1:] + points[:1]))


def describe(contour: Contour):
    """Return (direction, point count) for a Contour order cell.

    Direction is "counter-clockwise", "clockwise", "open", or "" when a
    closed contour has no area to tell by.
    """
    points = list(contour.points)
    if not contour.closed:
        direction = "open"
    else:
        area = _area(points)
        direction = "counter-clockwise" if area > 0 else "clockwise" if area < 0 else ""
    return direction, len(points)


def align(default: Contour, contour: Contour):
    """Return (reversed, rotation) that make ``contour`` line up with ``default``.

    ``rotation`` is the index (after any reversal) of the point that should
    be the start point. None when no rotation or reversal makes the point
    types line up. Direction comes from the sign of the area when both
    contours have one; position picks the start point and breaks other ties.
    """
    if default.closed != contour.closed or len(default.points) != len(contour.points):
        return None
    if not contour.points:
        return False, 0
    wanted = _types(default.points)
    directions = (False, True)
    if default.closed:
        default_area, area = _area(list(default.points)), _area(list(contour.points))
        if default_area and area:
            directions = ((default_area > 0) != (area > 0),)
    best = None
    for flip in directions:
        points = list(_reversed(contour) if flip else contour.points)
        rotations = range(len(points)) if contour.closed else (0,)
        for rotation in rotations:
            candidate = points[rotation:] + points[:rotation]
            if _types(candidate) != wanted:
                continue
            cost = _distance(default.points, candidate)
            if best is None or cost < best[0] - 1e-9:
                best = (cost, flip, rotation)
    return None if best is None else best[1:]


def _structure(contour):
    """Point types, the same under any start point or direction."""
    forward, backward = _types(contour.points), _types(_reversed(contour))
    if not contour.closed or not forward:
        return contour.closed, min(forward, backward)
    return True, min(sequence[index:] + sequence[:index]
                     for sequence in (forward, backward) for index in range(len(sequence)))


def _centres(contours):
    """Each contour's centre, scaled into the glyph's unit box."""
    centres = [(sum(p[1] for p in c.points) / len(c.points),
                sum(p[2] for p in c.points) / len(c.points)) if c.points else (0, 0)
               for c in contours]
    return _normalised([("", x, y) for x, y in centres])


def contour_order(default: tuple[Contour, ...], contours: tuple[Contour, ...]):
    """Return, for each default contour, the index of its match in ``contours``.

    Contours match when their point structure lines up under some start
    point and direction; the contour's position in the glyph breaks ties
    between contours of the same structure. None when no order lines up.
    """
    if len(default) != len(contours) or not default:
        return None if len(default) != len(contours) else ()
    groups = {}
    for side, items in enumerate((default, contours)):
        for index, contour in enumerate(items):
            groups.setdefault(_structure(contour), ([], []))[side].append(index)
    if any(len(wanted) != len(found) for wanted, found in groups.values()):
        return None
    default_centres, centres = _centres(default), _centres(contours)

    def cost(i, j):
        (ax, ay), (bx, by) = default_centres[i], centres[j]
        return (ax - bx) ** 2 + (ay - by) ** 2

    order = [None] * len(default)
    for wanted, found in groups.values():
        for i, j in _assign(wanted, found, cost):
            order[i] = j
    return tuple(order)


@dataclass(frozen=True)
class OrderPlan:
    order: tuple[int, ...] | None   # for each default contour, the index of its match
    reason: str = ""                # why there is no order


def plan_order(default: tuple[Contour, ...], contours: tuple[Contour, ...]) -> OrderPlan:
    """The contour order that makes ``contours`` match ``default``, or a refusal."""
    if len(default) != len(contours):
        count = f"{len(contours)} contour" + ("" if len(contours) == 1 else "s")
        return OrderPlan(None, f"{count}, the Default source has {len(default)}")
    order = contour_order(default, contours)
    if order is None:
        return OrderPlan(None, "contours differ in points from the Default source")
    return OrderPlan(order)


def _assign(wanted, found, cost):
    """Pair ``wanted`` with ``found`` at the lowest total cost, keeping order on ties."""
    best = list(zip(wanted, found))
    if len(wanted) > 6:
        pairs = sorted((cost(i, j), i, j) for i in wanted for j in found)
        used_i, used_j, best = set(), set(), []
        for _cost, i, j in pairs:
            if i not in used_i and j not in used_j:
                used_i.add(i)
                used_j.add(j)
                best.append((i, j))
        return best
    best_cost = sum(cost(i, j) for i, j in best)
    for permutation in permutations(found):
        pairs = list(zip(wanted, permutation))
        total = sum(cost(i, j) for i, j in pairs)
        if total < best_cost - 1e-9:
            best, best_cost = pairs, total
    return best


def _contour_kinds(default, contour):
    if default.closed != contour.closed:
        return {"open/closed"}
    found = align(default, contour)
    if found is None:
        return {"points"}
    flip, rotation = found
    kinds = set()
    if flip:
        kinds.add("direction")
    if rotation:
        kinds.add("start point")
    return kinds


KINDS = ("contour count", "contour order", "start point", "direction",
         "points", "open/closed", "components")

KIND_TITLES = {
    "contour count": "contour count",
    "contour order": "contour order",
    "start point": "start point",
    "direction": "direction",
    "points": "point count/types",
    "open/closed": "open vs closed",
    "components": "components",
}


@dataclass(frozen=True)
class OutlineRow:
    glyph: str
    mismatches: str                             # e.g. "Bold: direction · Light: start point"
    kinds: tuple[tuple[str, tuple[str, ...]], ...]  # (source label, kinds in KINDS order)


@dataclass(frozen=True)
class OutlineAudit:
    rows: tuple[OutlineRow, ...]
    glyphs: dict    # kind -> tuple of glyph names
    sources: dict   # kind -> {source label: glyph count}

    def line(self) -> str:
        parts = []
        for kind in KINDS:
            count = len(self.glyphs[kind])
            if count:
                by_source = ", ".join(f"{label} {number}"
                                      for label, number in self.sources[kind].items())
                glyphs = f"{count} glyph" if count == 1 else f"{count} glyphs"
                parts.append(f"{KIND_TITLES[kind]}: {glyphs} ({by_source})")
        return "Outlines · " + (" · ".join(parts) or "compatible")


def audit_outlines(default_glyphs, others) -> OutlineAudit:
    """Compare every default glyph with the same glyph in each other source.

    ``default_glyphs`` maps glyph name -> Outline; ``others`` maps source
    label -> the same. Glyphs absent from a source are skipped, not reported.
    """
    rows = []
    glyphs = {kind: [] for kind in KINDS}
    sources = {kind: {} for kind in KINDS}
    for name in sorted(default_glyphs):
        found = []
        for label, outlines in others.items():
            if name not in outlines:
                continue
            kinds = mismatches(default_glyphs[name], outlines[name])
            if not kinds:
                continue
            ordered = tuple(kind for kind in KINDS if kind in kinds)
            found.append((label, ordered))
            for kind in ordered:
                if name not in glyphs[kind]:
                    glyphs[kind].append(name)
                sources[kind][label] = sources[kind].get(label, 0) + 1
        if found:
            text = " · ".join(f"{label}: {', '.join(kinds)}" for label, kinds in found)
            rows.append(OutlineRow(name, text, tuple(found)))
    return OutlineAudit(tuple(rows), {kind: tuple(names) for kind, names in glyphs.items()},
                        sources)


def mismatches(default: Outline, other: Outline) -> set[str]:
    """Return the outline mismatch kinds of ``other`` against ``default``."""
    kinds = set()
    if len(default.contours) != len(other.contours):
        kinds.add("contour count")
    else:
        order = contour_order(default.contours, other.contours)
        if order is None:
            order = range(len(other.contours))
        elif list(order) != list(range(len(order))):
            kinds.add("contour order")
        for default_contour, index in zip(default.contours, order):
            kinds |= _contour_kinds(default_contour, other.contours[index])
    if default.components != other.components:
        kinds.add("components")
    return kinds
