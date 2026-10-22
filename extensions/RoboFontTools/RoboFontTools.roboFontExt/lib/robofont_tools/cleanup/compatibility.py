"""The Compatibility window: fix outline mismatches one glyph at a time.

It follows the current glyph (and so the current source) and compares it
with the designspace loaded in Cleanup. Two tabs: Points (later) and
Contour order, one row per source and one cell per contour.
"""
from __future__ import annotations

from pathlib import Path
import traceback

from .outlines import describe


_window = None
_follower = None

CELL = 88          # contour cell, in screen points
GAP = 10
CAPTION = 16       # caption under each cell
LABELS = 150       # source label column
PAD = 10
ROW = CELL + CAPTION + 2 * GAP

DIRECTION_MARKS = {"counter-clockwise": "↺", "clockwise": "↻", "open": "open", "": "?"}


def open_window():
    """Open the window once, or bring it forward."""
    global _window
    if _window is None:
        _window = CompatibilityWindow()
        _start_following()
    else:
        _window.w.show()
        _window.w.makeKey()
    _window.refresh()
    return _window


def refresh_open_window():
    """Redraw if the window is open (Cleanup calls this after loads and fixes)."""
    if _window is not None:
        _window.refresh()


def _start_following():
    global _follower
    try:
        from mojo.subscriber import Subscriber, registerCurrentGlyphSubscriber
    except ImportError:     # outside RoboFont
        return

    class CompatibilityFollower(Subscriber):
        debug = False

        def currentGlyphDidSetGlyph(self, info):
            refresh_open_window()

        def currentGlyphDidChange(self, info):
            refresh_open_window()

    _follower = CompatibilityFollower
    registerCurrentGlyphSubscriber(_follower)


def _stop_following():
    global _follower
    if _follower is None:
        return
    from mojo.subscriber import unregisterCurrentGlyphSubscriber
    unregisterCurrentGlyphSubscriber(_follower)
    _follower = None


def _current_glyph():
    """(UFO path or None if unsaved, layer name, glyph name) in the frontmost
    Glyph Editor, or None when no Glyph Editor is open."""
    from mojo.UI import CurrentGlyphWindow
    editor = CurrentGlyphWindow()
    glyph = editor.getGlyph() if editor is not None else None
    if glyph is None:
        return None
    font = glyph.font
    return (font.path if font is not None else None), glyph.layer.name, glyph.name


def _colours():
    """Drawing colours for the current light or dark appearance."""
    from AppKit import NSApp
    name = ""
    if NSApp() is not None:
        name = str(NSApp().effectiveAppearance().name())
    if "Dark" in name:
        return {"ink": (0.88, 0.88, 0.88, 1), "soft": (0.6, 0.6, 0.6, 1),
                "cell": (1, 1, 1, 0.06), "current": (0.3, 0.55, 1, 0.16),
                "start": (1, 0.45, 0.3, 1)}
    return {"ink": (0.15, 0.15, 0.15, 1), "soft": (0.45, 0.45, 0.45, 1),
            "cell": (0, 0, 0, 0.05), "current": (0.2, 0.45, 1, 0.12),
            "start": (0.9, 0.3, 0.1, 1)}


class CompatibilityWindow:
    def __init__(self):
        from merz import ScrollingMerzView
        from vanilla import Button, FloatingWindow, Tabs, TextBox

        self.w = FloatingWindow((760, 460), "Compatibility", minSize=(420, 260))
        self.w.bind("close", self._closed)
        self.w.bind("resize", lambda sender: self.refresh())
        self.w.status = TextBox((12, 14, -150, 20), "")
        self.w.openCleanup = Button((-140, 10, 128, 24), "Open Cleanup",
                                    callback=self.open_cleanup)
        self.w.tabs = Tabs((12, 44, -12, -12), ["Points", "Contour order"])
        self.points, self.order = self.w.tabs[0], self.w.tabs[1]
        self.points.note = TextBox((12, 12, -12, 40),
                                   "The Points tab comes in a later update. "
                                   "Use Contour order for now.")
        self.order.rows = ScrollingMerzView((0, 0, -0, -0), centered=False)
        self.w.tabs.set(1)
        self.w.open()

    def _closed(self, sender):
        global _window
        _window = None
        _stop_following()

    def open_cleanup(self, sender):
        from .window import open_window
        open_window()

    # --- following ---------------------------------------------------------

    def refresh(self):
        try:
            self._refresh()
        except Exception as error:
            self._show(f"Could not draw the current glyph: {error}")
            traceback.print_exc()

    def _refresh(self):
        from .window import loaded
        session, designspace = loaded()
        if session is None:
            self._show("Load a designspace in Cleanup first.", ask_for_cleanup=True)
            return
        current = _current_glyph()
        if current is None:
            self._show("Open a glyph in a Glyph Editor.")
            return
        path, layer, name = current
        source = session.source_for(path, layer) if path else None
        if source is None:
            if not path:
                self._show(f"This unsaved font is not a source of {Path(designspace).name}.")
                return
            in_designspace = any(item.path == Path(path).resolve() for item in session.sources)
            where = Path(path).name + (f" (layer {layer})" if in_designspace else "")
            self._show(f"{where} is not a source of {Path(designspace).name}.")
            return
        self._show(f"{name} · current source: {source.label} · "
                   f"default: {session.default.label}")
        self._draw_order(session.glyph_outlines(name), source, session.default)

    def _show(self, status, ask_for_cleanup=False):
        """Set the status line; clear the drawing unless a glyph is drawn after."""
        self.w.status.set(status)
        self.w.openCleanup.show(ask_for_cleanup)
        self._draw_order((), None, None)

    # --- Contour order tab -------------------------------------------------

    def _draw_order(self, rows, current, default):
        view = self.order.rows
        container = view.getMerzContainer()
        container.clearSublayers()
        visible_width, visible_height = view.getSize()
        cells = max((len(outline.contours) for _source, outline in rows if outline), default=0)
        width = max(visible_width, LABELS + max(cells, 1) * (CELL + GAP) + PAD)
        height = max(visible_height, len(rows) * ROW + PAD)
        view.setMerzViewSize((width, height))
        container.setSize((width, height))
        colours = _colours()
        for index, (source, outline) in enumerate(rows):
            top = height - PAD - index * ROW
            self._draw_row(container, source, outline, top, width, colours,
                           source == current, source == default)

    def _draw_row(self, container, source, outline, top, width, colours, is_current, is_default):
        bottom = top - ROW + GAP
        if is_current:
            container.appendRectangleSublayer(
                position=(0, bottom - GAP / 2), size=(width, ROW),
                fillColor=colours["current"])
        _text(container, (PAD, top - 16), source.label, 12, colours["ink"])
        tags = [tag for tag, on in (("default", is_default), ("current", is_current)) if on]
        if tags:
            _text(container, (PAD, top - 32), " · ".join(tags), 10, colours["soft"])
        if outline is None or not outline.contours:
            _text(container, (LABELS, top - CELL / 2),
                  "absent" if outline is None else "no contours", 12, colours["soft"])
            return
        for number, contour in enumerate(outline.contours):
            left = LABELS + number * (CELL + GAP)
            self._draw_cell(container, contour, number, left, top - CELL, colours)

    def _draw_cell(self, container, contour, number, left, bottom, colours):
        container.appendRectangleSublayer(
            position=(left, bottom), size=(CELL, CELL), fillColor=colours["cell"],
            cornerRadius=4)
        direction, count = describe(contour)
        _text(container, (left + CELL / 2, bottom - CAPTION + 2),
              f"{number + 1} · {count} pts · {DIRECTION_MARKS[direction]}", 10,
              colours["soft"], align="center")
        if not contour.points:
            return
        place = _fit(contour.points, left, bottom)
        points = [(kind, *place(x, y)) for kind, x, y in contour.points]

        from fontTools.pens.pointPen import PointToSegmentPen
        path = container.appendPathSublayer(
            fillColor=None, strokeColor=colours["ink"], strokeWidth=1)
        pen = PointToSegmentPen(path.getPen())
        pen.beginPath()
        for index, (kind, x, y) in enumerate(points):
            if not contour.closed and index == 0:
                kind = "move"
            pen.addPoint((x, y), None if kind == "offcurve" else kind)
        pen.endPath()

        for index, (kind, x, y) in enumerate(points):
            if kind != "offcurve":
                continue
            for neighbour in (index - 1, (index + 1) % len(points)):
                other = points[neighbour]
                if other[0] != "offcurve" and (contour.closed or abs(neighbour - index) == 1):
                    container.appendLineSublayer(
                        startPoint=(x, y), endPoint=other[1:],
                        strokeColor=colours["soft"], strokeWidth=0.5)
        for index, (kind, x, y) in enumerate(points):
            size = 7 if index == 0 else 3 if kind == "offcurve" else 4
            colour = colours["start"] if index == 0 else colours["ink"]
            container.appendOvalSublayer(
                position=(x - size / 2, y - size / 2), size=(size, size),
                fillColor=None if kind == "offcurve" and index else colour,
                strokeColor=colour, strokeWidth=0.75)


def _text(container, position, text, size, colour, align="left"):
    """One line of text whose ``position`` is its bottom edge."""
    container.appendTextLineSublayer(
        position=position, text=text, pointSize=size, fillColor=colour,
        horizontalAlignment=align, verticalAlignment="bottom")


def _fit(points, left, bottom):
    """A function placing glyph coordinates inside one cell, keeping proportions."""
    xs = [point[1] for point in points]
    ys = [point[2] for point in points]
    inner = CELL - 16
    width, height = max(xs) - min(xs), max(ys) - min(ys)
    scale = inner / max(width, height, 1)
    x_offset = left + (CELL - width * scale) / 2 - min(xs) * scale
    y_offset = bottom + (CELL - height * scale) / 2 - min(ys) * scale
    return lambda x, y: (x * scale + x_offset, y * scale + y_offset)
