from __future__ import annotations

from .model import CubicSegment, GlyphOutline, LineSegment, SourceContour


def line_contour(points, *, clockwise=False, closed=True):
    points = list(points)
    if clockwise:
        points.reverse()
    segments = []
    for index, start in enumerate(points):
        if index == len(points) - 1:
            if not closed:
                break
            end = points[0]
        else:
            end = points[index + 1]
        segments.append(LineSegment(start, end))
    return SourceContour(tuple(segments), closed=closed)


def rectangle(x0, y0, x1, y1, *, clockwise=False):
    return line_contour(((x0, y0), (x1, y0), (x1, y1), (x0, y1)), clockwise=clockwise)


def _reverse_contour(contour: SourceContour) -> SourceContour:
    reversed_segments = []
    for segment in reversed(contour.segments):
        if isinstance(segment, LineSegment):
            reversed_segments.append(LineSegment(segment.end, segment.start))
        else:
            reversed_segments.append(
                CubicSegment(
                    segment.end,
                    segment.control2,
                    segment.control1,
                    segment.start,
                )
            )
    return SourceContour(tuple(reversed_segments), contour.closed)


def cubic_circle(cx, cy, radius, *, clockwise=False):
    k = radius * 0.5522847498307936
    top = (cx, cy + radius)
    right = (cx + radius, cy)
    bottom = (cx, cy - radius)
    left = (cx - radius, cy)
    contour = SourceContour(
        (
            CubicSegment(top, (cx + k, cy + radius), (cx + radius, cy + k), right),
            CubicSegment(right, (cx + radius, cy - k), (cx + k, cy - radius), bottom),
            CubicSegment(bottom, (cx - k, cy - radius), (cx - radius, cy - k), left),
            CubicSegment(left, (cx - radius, cy + k), (cx - k, cy + radius), top),
        )
    )
    return _reverse_contour(contour) if clockwise else contour


def proof_fixtures() -> dict[str, GlyphOutline]:
    return {
        "H.overlap": GlyphOutline(
            "H.overlap",
            700,
            1000,
            (
                rectangle(80, 80, 220, 720),
                rectangle(480, 80, 620, 720),
                rectangle(180, 330, 520, 470),
            ),
        ),
        "O.counter": GlyphOutline(
            "O.counter",
            700,
            1000,
            (rectangle(70, 70, 630, 730), rectangle(220, 220, 480, 580, clockwise=True)),
        ),
        "O.curve": GlyphOutline(
            "O.curve",
            700,
            1000,
            (cubic_circle(350, 400, 310), cubic_circle(350, 400, 155, clockwise=True)),
        ),
        "nested": GlyphOutline(
            "nested",
            700,
            1000,
            (
                rectangle(60, 60, 640, 740),
                rectangle(170, 170, 530, 630, clockwise=True),
                rectangle(285, 285, 415, 515),
            ),
        ),
        "disconnected": GlyphOutline(
            "disconnected",
            700,
            1000,
            (rectangle(80, 100, 300, 700), rectangle(400, 100, 620, 700)),
        ),
        "thin.counter": GlyphOutline(
            "thin.counter",
            700,
            1000,
            (rectangle(100, 100, 600, 700), rectangle(128, 128, 572, 672, clockwise=True)),
        ),
    }


def component_fixture():
    return GlyphOutline("component", 700, 1000, (), components=("A",))


def open_contour_fixture():
    contour = SourceContour(
        (
            LineSegment((100, 100), (600, 100)),
            LineSegment((600, 100), (600, 700)),
        ),
        closed=False,
    )
    return GlyphOutline("open", 700, 1000, (contour,))

