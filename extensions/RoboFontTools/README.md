# RoboFont Tools

RoboFont Tools is a compact home for small utilities used while drawing. It
contains two read-only measurement tools, a point distribution action, a
contour selection action, a rough slicing knife, and a designspace Cleanup window.

## Supported environment

- RoboFont 4.6;
- RoboFont's bundled Python 3.12;
- macOS.

This is the repository's currently validated RoboFont environment. No
compatibility claim is made for earlier RoboFont releases.

## Installation

The installable bundle is `RoboFontTools.roboFontExt` in this directory.
Double-click it and accept RoboFont's installation prompt, or symlink the bundle
into RoboFont's user `plugins` directory while developing. Restart or reload
extensions after installing it.

No build step or third-party dependency installation is required. The extension
uses RoboFont's bundled EZUI, Subscriber, and FontParts APIs.

## Menu

RoboFont Tools adds a top-level **RoboFont Tools** menu at startup, beside the
other application menus. **Open Palette** opens the drawing palette and
**Cleanup…** opens the designspace Cleanup window (also available from the
palette). The existing **Extensions → RoboFont Tools** entry also opens the
palette.

## Opening and using the palette

Choose **Extensions → RoboFont Tools**. The existing palette is brought forward
if it is already open.

Enable **Measure Selected Points**, then select exactly two contour points in
the active Glyph Editor. A live editor overlay displays:

- direct distance;
- horizontal and vertical distance (`Δx`, `Δy`);
- angle.

Measurements follow outline order: from the first selected point to the
second as they appear in the glyph's contours, so `Δx`, `Δy` and the angle
(−180° to 180°) carry a sign.

On-curve and off-curve contour points are supported. Other selected objects are
ignored. The overlay hides unless exactly two points are selected.

The tool is completely read-only. It does not change outlines, add data or
guidelines, dirty the glyph, or save the font.

### Contour Probe

Enable **Contour Probe** and move the cursor over a closed native contour. A
live perpendicular probe reports the local filled and unfilled intervals. It
follows curves using a cached adaptive flattening of cubic segments and is
recalculated only when the outline changes. It hides whenever a measurement
would be uncertain. Open contours and glyphs containing components are
deliberately unsupported in this first version, so they never produce a
potentially misleading result.

### Distribute Points

Select three or more on-curve points and/or anchors, then click **Horizontal**
or **Vertical** in the palette's **Distribute** row.

The participants are ranked by the coordinate on the chosen axis. The lowest
and highest keep their exact positions; everything in between is respaced so
the gaps are equal. The other axis is never touched, so a horizontal distribute
changes only `x` values.

- On-curve points and anchors participate as equals.
- Off-curve points are never participants. Instead, the handles attached to a
  moved on-curve point shift with it, so the curve around the node keeps its
  shape. A quadratic off-curve sitting between two moving on-curve points is
  left alone rather than guessed at.
- New coordinates are rounded to integers, so individual gaps may differ by one
  unit across an indivisible span. The outline stays on the integer grid.
- Points sharing a coordinate keep their relative order, so the same selection
  always produces the same result.
- Each click writes one undo record.

Unlike the measurement tools, this one has no on/off switch — it does nothing
until a button is clicked. If fewer than three points are selected, no glyph is
open, or the selection has no span along the chosen axis, nothing happens: the
glyph is untouched and no undo record is created. The reason is printed to the
Output window while `DEBUG` is on.

### Select Between

Select exactly two points on the same contour, then click **Select Points** in
the palette's **Select Between** row. The endpoints and every point between
them are selected, including off-curve handles. On a closed contour, the first
click chooses the shorter route; click again without changing the selection to
switch to the other route. Further clicks alternate between the two routes.
Length is measured along the ordered point positions, including handle
positions. If the two points are on different contours, the action leaves the
selection alone. Open contours have one route, so a second click does nothing.
Changing the selection or editing the outline starts a new action. This tool
only changes selection; it does not alter outlines or create an undo record.

### Rough Slice

Set **Spacing**, **Gap**, and **Jitter** in the palette row (hover a field for
its description), then click **Activate Knife**. The button reads **Knife Active — Drag** when the tool is selected.
Drag a straight line across the outlines in the Glyph Editor; a click alone
does not cut. Each
closed contour crossed cleanly is split into two contours. The two new cut
edges receive paired points at approximately the chosen spacing (25 units by
default). The edges wiggle independently while retaining at least the chosen
gap (20 units by default) at every point along them. Jitter defaults to 30
units. Each drag is one undoable action.

Spacing accepts 5–50 units; gap and jitter cannot be negative. A gap of 0
leaves the two pieces touching along one shared rough edge.

**Two sources at once.** Pick a font in **Second source** and draw in the
default source. The same cut is made in both: the default gets gap 0, the
second source gets the **Gap** value, and both use the same rough pattern and
point count so they stay compatible for interpolation. If the results would not
be compatible, or the second source lacks the glyph or layer, neither font is
changed and the reason is printed. Undo is per font. Choose **None (single
source)** for an ordinary cut. A
drag that does not enter and leave a contour cleanly has no effect. Open
contours and components are skipped. To stop using the
knife, choose another Glyph Editor tool.
The knife appears in the Glyph Editor toolbar with a serrated blade icon.

### Cleanup (designspace)

Click **Cleanup…** in the palette (or choose **RoboFont Tools → Cleanup…**),
then **Load Designspace…**. The designspace default is used; **Choose
Default…** picks another full source. The source list shows which sources are
open in RoboFont and which are closed. Layer-sources (`<source layer="…">`)
are included; one whose layer is missing is skipped with a warning.

**Audit.** After loading, and after every rescan or fix, the audit lists what
needs doing: glyph counts per anchor issue (missing, extra, order only,
duplicate names) with the sources involved, extra layers per UFO (background
layers on their own line), glyph and font guides, and glyphs with a mark colour.
Click an anchor line to select those glyphs in the Anchors list. Layers, guides
and mark colours are reported only for now.

**Anchors.** Every glyph in the default whose anchors differ in another source
is listed: missing or extra anchor names, a different order, or duplicate
names. Glyphs absent from a source are allowed in a variable font and are only
counted. Select rows (Cmd-A for all), then:

- **Match Default** gives each source the default's anchor names in the
  default's order. Existing anchors keep their positions; missing ones are
  added at the default's coordinates and listed afterwards so you can check
  them. Rows with duplicate names are skipped.
- **Remove All Anchors** removes the glyph's anchors from every source,
  including the default.

Open fonts are changed with undo and left unsaved; closed UFOs are saved
immediately. The list rescans after each fix; **Rescan** refreshes it after
manual edits.

## Project structure

```text
RoboFontTools.roboFontExt/
    info.plist                  extension metadata and menu entry
    lib/
        start.py                startup script (installs the menu)
        startup.py              Extensions-menu entry point
        robofont_tools/
            extension.py       singleton palette lifecycle
            menu.py            top-level menu
            palette.py         stacks the registered tools in one EZWindow
            geometry.py        the measuring rule and number formatting
            tools/
                base.py                   PaletteTool: the interface every tool provides
                selected_points.py        editor overlay and event lifecycle
                selected_points_model.py  read-only presentation logic
                selected_points_state.py  shared enabled state
                contour_probe.py          live contour/counter probe
                distribute_points.py       one-shot even-distribution action
                distribute_points_model.py pure distribution maths
                select_between.py        one-shot contour selection action
                select_between_model.py  route choice and repeat-click state
                rough_slice.py          knife, single and two-source cuts
                rough_slice_model.py    paired rough edges with a guaranteed gap
                cleanup.py              palette button for the Cleanup window
            cleanup/
                sources.py     designspace sources, including layer-sources
                anchors.py     anchor differences, fix plans, applying an edit
                audit.py       the audit summary (anchors, layers, guides, colours)
                session.py     reads and changes open and closed sources
                window.py      the Cleanup window
```

Development tests live in `tests/` beside the bundle and are kept locally, not
in the repository. The team package contains only the `.roboFontExt` bundle and
separate utility scripts.

To add a tool, subclass `PaletteTool` in `robofont_tools/tools/`: give it an
EZUI `content` row and a `descriptions()` method whose callbacks are the
tool's own methods, then return the class from `get_tool_classes()`. The
palette needs no changes. Keep geometry and formatting independent of RoboFont
wherever possible. A tool that subscribes to events must expose idempotent
`start()` and `stop()` methods and release its subscriber/controller
references in `stop()`.

## Development checks

Run the dependency-free headless suite with the bundled package on `PYTHONPATH`:

```bash
cd extensions/RoboFontTools
PYTHONPATH=RoboFontTools.roboFontExt/lib python3 -m unittest discover -s tests -v
```

The tests are also compatible with pytest. The headless suite checks pure
geometry, formatting, bundle metadata, and source lifecycle contracts.
Selection, editor switching, appearance, and dirty-state behaviour must
additionally be checked inside RoboFont.
