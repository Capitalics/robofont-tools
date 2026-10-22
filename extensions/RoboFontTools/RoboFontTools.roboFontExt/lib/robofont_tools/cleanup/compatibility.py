"""The Compatibility window: fix outline mismatches one glyph at a time.

It follows the current glyph (and so the current source) and compares it
with the designspace loaded in Cleanup. Two tabs:

- Points: one row per other source, the current source drawn beside a grey
  ghost of that source, with a link line joining each pair of matching points.
- Contour order: one row per source and one cell per contour. Drag a cell
  sideways in its row to reorder that source's contours.
"""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import traceback

from .outlines import Outline, describe, links


_window = None
_follower = None

CELL = 88          # contour cell, in screen points
GAP = 10
CAPTION = 16       # caption under each cell
LABELS = 150       # source label column
PAD = 10
ROW = CELL + CAPTION + 2 * GAP

DRAWING = 130      # Points tab: height of a glyph drawing
STATUS = 18        # Points tab: the status line above the drawings
APART = 40         # Points tab: space between the ghost and the current source
POINTS_ROW = STATUS + DRAWING + 2 * GAP

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

        def currentGlyphDidChangeSelection(self, info):
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
    """(UFO path or None if unsaved, layer name, glyph name, selected points)
    in the frontmost Glyph Editor, or None when no Glyph Editor is open.
    Selected points are (contour index, point index) pairs."""
    from mojo.UI import CurrentGlyphWindow
    editor = CurrentGlyphWindow()
    glyph = editor.getGlyph() if editor is not None else None
    if glyph is None:
        return None
    font = glyph.font
    return (font.path if font is not None else None), glyph.layer.name, glyph.name, \
        _selected_points(glyph)


def _selected_points(glyph):
    """(contour index, point index) of each selected point.

    The Glyph Editor gives a defcon glyph (RoboFont's DoodleGlyph), not a
    scripting RGlyph: iterate it for contours, and contours for points.
    """
    if hasattr(glyph, "naked"):     # an RGlyph, if one is ever passed
        glyph = glyph.naked()
    return frozenset((contour_index, point_index)
                     for contour_index, contour in enumerate(glyph)
                     for point_index, point in enumerate(contour) if point.selected)


def _rows_view(posSize, delegate):
    """A scrolling merz view whose clicks reach ``delegate``, even the click
    that brings the floating window forward from the Glyph Editor."""
    import objc
    from merz import ScrollingMerzView
    from merz.views import MerzDocumentView, MerzNSView

    name = "RoboFontToolsContourOrderNSView"
    try:        # an ObjC class can be defined once per app run; reloads reuse it
        ns_view_class = objc.lookUpClass(name)
    except objc.nosuchclass_error:
        ns_view_class = type(name, (MerzNSView,),
                             {"acceptsFirstMouse_": lambda self, event: True})

    class DocumentView(MerzDocumentView):
        nsViewClass = ns_view_class

    class RowsView(ScrollingMerzView):
        merzDocumentViewClass = DocumentView

    return RowsView(posSize, centered=False, delegate=delegate)


def _colours():
    """Drawing colours for the current light or dark appearance."""
    from AppKit import NSApp
    name = ""
    if NSApp() is not None:
        name = str(NSApp().effectiveAppearance().name())
    if "Dark" in name:
        return {"ink": (0.88, 0.88, 0.88, 1), "soft": (0.6, 0.6, 0.6, 1),
                "cell": (1, 1, 1, 0.06), "current": (0.3, 0.55, 1, 0.16),
                "start": (1, 0.45, 0.3, 1), "ghost": (0.5, 0.5, 0.5, 1),
                "link": (0.45, 0.65, 1, 0.7), "wrong": (1, 0.3, 0.3, 1),
                "selected": (0.3, 0.6, 1, 1)}
    return {"ink": (0.15, 0.15, 0.15, 1), "soft": (0.45, 0.45, 0.45, 1),
            "cell": (0, 0, 0, 0.05), "current": (0.2, 0.45, 1, 0.12),
            "start": (0.9, 0.3, 0.1, 1), "ghost": (0.65, 0.65, 0.65, 1),
            "link": (0.2, 0.45, 1, 0.55), "wrong": (0.9, 0.1, 0.1, 1),
            "selected": (0.1, 0.4, 1, 1)}


class CompatibilityWindow:
    def __init__(self):
        from vanilla import Button, FloatingWindow, Tabs, TextBox

        self.w = FloatingWindow((760, 460), "Compatibility", minSize=(420, 260))
        self.w.bind("close", self._closed)
        self.w.bind("resize", lambda sender: self.refresh())
        self.w.status = TextBox((12, 14, -150, 20), "")
        self.w.openCleanup = Button((-140, 10, 128, 24), "Open Cleanup",
                                    callback=self.open_cleanup)
        self.w.tabs = Tabs((12, 44, -12, -12), ["Points", "Contour order"])
        self.points, self.order = self.w.tabs[0], self.w.tabs[1]
        self.points.rows = _rows_view((0, 0, -0, -0), delegate=None)
        self.order.matchOrder = Button((12, 8, 170, 24), "Match order to Default",
                                       callback=self.match_order)
        self.order.result = TextBox((194, 12, -12, 20), "", sizeStyle="small")
        self.order.rows = _rows_view((0, 40, -0, -0), delegate=self)
        self._glyph_name = None     # the glyph drawn now
        self._result_glyph = None     # the glyph the result line is about
        self._drawn = ((), None, None, 0)   # rows, current, default, height last drawn
        self._drag = None           # (glyph name, row index, press x) while dragging
        self._from_top = {}         # rows view -> how far it is scrolled down from the top
        self.w.tabs.set(0)
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
        path, layer, name, selected = current
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
        self._glyph_name = name
        self.order.matchOrder.enable(True)
        if name != self._result_glyph:
            self.order.result.set("")
        outlines = session.glyph_outlines(name)
        self._draw_points(outlines, source, session.default, selected)
        self._draw_order(outlines, source, session.default)

    def _show(self, status, ask_for_cleanup=False):
        """Set the status line and forget the glyph: clear the drawing and
        disable the fix buttons, unless ``_refresh`` draws a glyph after."""
        self.w.status.set(status)
        self.w.openCleanup.show(ask_for_cleanup)
        self._glyph_name = None
        self.order.matchOrder.enable(False)
        self._draw_points((), None, None, frozenset())
        self._draw_order((), None, None)

    def _size_rows(self, view, width, height):
        """Size a rows view's document to at least ``width`` x ``height`` and
        return the merz container, emptied, and the height used.

        The document's y runs up from the bottom, so a new size would scroll
        the rows. Keep the same distance from the top instead: a new window
        starts at the first row, and redraws while editing don't jump.
        (Only a scrollable document says where the reader is; each refresh
        draws an empty tab first.)
        """
        container = view.getMerzContainer()
        container.clearSublayers()
        document = view.getMerzView().getNSView()
        shown = document.superview().bounds()       # the visible part
        if document.frame().size.height > shown.size.height:
            self._from_top[id(view)] = max(0, document.frame().size.height
                                           - (shown.origin.y + shown.size.height))
        width = max(shown.size.width, width)
        height = max(shown.size.height, height)
        view.setMerzViewSize((width, height))
        container.setSize((width, height))
        from_top = self._from_top.get(id(view), 0)
        document.scrollPoint_((shown.origin.x, max(0, height - shown.size.height - from_top)))
        return container, width, height

    # --- Points tab --------------------------------------------------------

    def _draw_points(self, outlines, current, default, selected):
        """One row per other source: its grey ghost, the current source beside
        it, and a link line joining each pair of matching points."""
        mine = dict(outlines).get(current) or Outline()
        rows = [(source, outline) for source, outline in outlines if source != current]
        drawn = [outline for _source, outline in rows if outline] + [mine]
        place = _SharedFit([point for outline in drawn for contour in outline.contours
                             for point in contour.points])
        container, width, height = self._size_rows(
            self.points.rows, LABELS + 2 * place.width + APART + PAD,
            len(rows) * POINTS_ROW + PAD)
        colours = _colours()
        if current is not None and not rows:
            _text(container, (PAD, height - PAD - 16), "No other sources.", 12, colours["soft"])
        for index, (source, outline) in enumerate(rows):
            top = height - PAD - index * POINTS_ROW
            self._draw_points_row(container, source, outline, mine, place, top,
                                  source == default, selected, colours)

    def _draw_points_row(self, container, source, outline, mine, place, top, is_default,
                         selected, colours):
        _text(container, (PAD, top - 16), source.label, 12, colours["ink"])
        if is_default:
            _text(container, (PAD, top - 32), "default", 10, colours["soft"])
        if outline is None:
            _text(container, (LABELS, top - 16), "absent", 11, colours["soft"])
            return
        found = links(mine, outline)
        status = found.status()
        _text(container, (LABELS, top - 16), status, 11,
              colours["soft"] if status == "compatible" else colours["wrong"])
        bottom = top - STATUS - GAP - DRAWING
        ghost = place.at(LABELS, bottom)
        here = place.at(LABELS + place.width + APART, bottom)
        ghost_points = [[ghost(x, y) for _kind, x, y in contour.points]
                        for contour in outline.contours]
        my_points = [[here(x, y) for _kind, x, y in contour.points]
                     for contour in mine.contours]
        for contour, points in zip(outline.contours, ghost_points):
            _draw_contour(container, contour, points, colours["ghost"], colours["ghost"],
                          colours["ghost"])
        for contour, points in zip(mine.contours, my_points):
            _draw_contour(container, contour, points, colours["ink"], colours["soft"],
                          colours["start"])
        for link in found.links:
            container.appendLineSublayer(
                startPoint=my_points[link.contour][link.point],
                endPoint=ghost_points[link.contour][link.point],
                strokeColor=colours["link"] if link.good else colours["wrong"],
                strokeWidth=0.5 if link.good else 1)
        for contour_index, point_index in selected:
            for points in (my_points, ghost_points):
                point = _point_at(points, contour_index, point_index)
                if point is not None:
                    _ring(container, point, 10, colours["selected"], 1.5)
        if found.first_difference is not None:
            for points in (my_points, ghost_points):
                # A contour that stops short is marked at its last point.
                point = _point_at(points, *found.first_difference, clamp=True)
                if point is not None:
                    _ring(container, point, 14, colours["wrong"], 2)

    # --- Contour order tab -------------------------------------------------

    def match_order(self, sender):
        if self._glyph_name is not None:
            self._run_order_fix(self._glyph_name,
                                lambda session, name: session.match_order_to_default(name))

    def _run_order_fix(self, name, fix):
        """Run ``fix(session, name)``, show its result line and redraw."""
        from .window import loaded
        session, _designspace = loaded()
        if session is None:
            self.refresh()
            return
        try:
            message = _order_result(fix(session, name))
        except Exception as error:
            message = f"Stopped after an error: {error}. Check the sources before saving."
            traceback.print_exc()
        self._result_glyph = name
        self.order.result.set(message)
        self.refresh()
        print(f"RoboFont Tools / Compatibility: {name}: {message}")

    # Dragging a cell. The merz view passes its AppKit mouse events (NSEvent)
    # here; positions are in the merz document view, y up from the bottom,
    # the same space the rows are drawn in. A drag stays in the row it
    # started in and survives redraws while the same glyph is shown.

    def acceptsFirstResponder(self, sender):
        # Without this, merz's hit test lets every click pass through the view
        # (seen in RoboFont: dragging did nothing).
        return True

    def _point(self, sender, event):
        return sender.convertWindowCoordinateToViewCoordinate(event.locationInWindow())

    def mouseDown(self, sender, event):
        x, y = self._point(sender, event)
        rows, _current, _default, height = self._drawn
        index = int((height - PAD - y) // ROW)
        if self._glyph_name is None or not 0 <= index < len(rows):
            return
        outline = rows[index][1]
        top = height - PAD - index * ROW
        if outline is not None and len(outline.contours) > 1 and top - CELL <= y <= top:
            self._drag = (self._glyph_name, index, x)

    def _dragged_row(self):
        """(row index, press x, source, outline) of the drag, or None when there
        is no drag or its glyph or row is gone."""
        if self._drag is None:
            return None
        name, index, press_x = self._drag
        rows = self._drawn[0]
        if name != self._glyph_name or index >= len(rows) or rows[index][1] is None:
            return None
        source, outline = rows[index]
        return index, press_x, source, outline

    def mouseDragged(self, sender, event):
        dragged = self._dragged_row()
        if dragged is None:
            return
        index, press_x, source, outline = dragged
        x, _y = self._point(sender, event)
        order = drag_order(len(outline.contours), press_x, x)
        if order is not None:      # draw the row as it would be after the drop
            outline = replace(outline, contours=tuple(outline.contours[old] for old in order))
        rows, current, default, _height = self._drawn
        rows = rows[:index] + ((source, outline),) + rows[index + 1:]
        self._draw_order(rows, current, default, preview=True)

    def mouseUp(self, sender, event):
        dragged = self._dragged_row()
        name = self._glyph_name
        self._drag = None
        if dragged is None:
            return
        _index, press_x, source, outline = dragged
        x, _y = self._point(sender, event)
        order = drag_order(len(outline.contours), press_x, x)
        if order is None:
            self.refresh()      # drop the preview
            return
        self._run_order_fix(name, lambda session, name: session.reorder_contours(
            source.label, name, order))

    def _draw_order(self, rows, current, default, preview=False):
        cells = max((len(outline.contours) for _source, outline in rows if outline), default=0)
        container, width, height = self._size_rows(
            self.order.rows, LABELS + max(cells, 1) * (CELL + GAP) + PAD, len(rows) * ROW + PAD)
        if not preview:     # a drag preview is not what the sources hold
            self._drawn = (tuple(rows), current, default, height)
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
        _draw_contour(container, contour, [place(x, y) for _kind, x, y in contour.points],
                      colours["ink"], colours["soft"], colours["start"])


def drag_order(count, press_x, release_x):
    """The new contour order after dragging a cell in a row of ``count`` cells.

    The pressed cell moves to the position of the cell nearest ``release_x``.
    None when the press missed every cell or the order stays the same.
    """
    pitch = CELL + GAP
    start, inside = divmod(press_x - LABELS, pitch)
    start = int(start)
    if not 0 <= start < count or inside > CELL:
        return None
    target = round((release_x - LABELS - CELL / 2) / pitch)
    target = min(max(target, 0), count - 1)
    if target == start:
        return None
    order = list(range(count))
    order.insert(target, order.pop(start))
    return tuple(order)


def _order_result(result):
    """One line saying what Match order to Default changed, saved and refused."""
    parts = [("Reordered " + ", ".join(result.changed)) if result.changed
             else "Nothing to reorder"]
    if result.saved:
        parts.append("saved " + ", ".join(result.saved))
    if result.refused:
        parts.append("refused " + "; ".join(f"{label} ({reason})"
                                            for label, reason in result.refused))
    return " · ".join(parts) + "."


def _text(container, position, text, size, colour, align="left"):
    """One line of text whose ``position`` is its bottom edge."""
    container.appendTextLineSublayer(
        position=position, text=text, pointSize=size, fillColor=colour,
        horizontalAlignment=align, verticalAlignment="bottom")


def _draw_contour(container, contour, placed, ink, soft, start):
    """Draw a contour as points and lines, no fill. ``placed`` holds each
    point's position in the view; the start point is drawn larger in ``start``."""
    if not placed:
        return
    from fontTools.pens.pointPen import PointToSegmentPen
    kinds = [kind for kind, _x, _y in contour.points]
    path = container.appendPathSublayer(fillColor=None, strokeColor=ink, strokeWidth=1)
    pen = PointToSegmentPen(path.getPen())
    pen.beginPath()
    for index, (kind, position) in enumerate(zip(kinds, placed)):
        if not contour.closed and index == 0:
            kind = "move"
        pen.addPoint(position, None if kind == "offcurve" else kind)
    pen.endPath()

    for index, kind in enumerate(kinds):
        if kind != "offcurve":
            continue
        for neighbour in (index - 1, (index + 1) % len(kinds)):
            if kinds[neighbour] != "offcurve" and (contour.closed or abs(neighbour - index) == 1):
                container.appendLineSublayer(startPoint=placed[index], endPoint=placed[neighbour],
                                             strokeColor=soft, strokeWidth=0.5)
    for index, (kind, (x, y)) in enumerate(zip(kinds, placed)):
        size = 7 if index == 0 else 3 if kind == "offcurve" else 4
        colour = start if index == 0 else ink
        container.appendOvalSublayer(
            position=(x - size / 2, y - size / 2), size=(size, size),
            fillColor=None if kind == "offcurve" and index else colour,
            strokeColor=colour, strokeWidth=0.75)


def _point_at(points, contour_index, point_index, clamp=False):
    """The placed point at these indices, or None where the drawing has none."""
    if contour_index >= len(points) or not points[contour_index]:
        return None
    contour = points[contour_index]
    if clamp:
        point_index = min(point_index, len(contour) - 1)
    return contour[point_index] if point_index < len(contour) else None


def _ring(container, position, size, colour, width):
    x, y = position
    container.appendOvalSublayer(position=(x - size / 2, y - size / 2), size=(size, size),
                                 fillColor=None, strokeColor=colour, strokeWidth=width)


class _SharedFit:
    """One scale for every drawing in the Points tab, so sources compare.

    ``width`` is the widest drawing in view points; ``at(left, bottom)``
    places glyph coordinates in a DRAWING-high box from ``left``, ``bottom``.
    """

    def __init__(self, points):
        xs = [point[1] for point in points] or [0]
        ys = [point[2] for point in points] or [0]
        self.left, self.bottom = min(xs), min(ys)
        self.scale = (DRAWING - 10) / max(max(ys) - min(ys), 1)
        self.width = (max(xs) - min(xs)) * self.scale + 10

    def at(self, left, bottom):
        scale = self.scale
        x_offset = left + 5 - self.left * scale
        y_offset = bottom + 5 - self.bottom * scale
        return lambda x, y: (x * scale + x_offset, y * scale + y_offset)


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
