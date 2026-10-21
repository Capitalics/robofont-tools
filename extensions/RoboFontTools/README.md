# RoboFont Tools

RoboFont Tools is a compact home for small utilities used while drawing. It
contains two read-only measurement tools, a point distribution action, a
contour selection action, a rough slicing knife, and a designspace anchor tool.

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

## Script menu

RoboFont Tools adds a top-level **RoboFont Tools** menu at startup, beside the
other application menus. **Open Palette** opens the existing drawing palette.
Standalone scripts are grouped by task so future scripts can be added without
another palette button. The existing **Extensions → RoboFont Tools** entry also
opens the palette.

Choose **RoboFont Tools → Anchors → Remove Extras from Open UFOs…** to clean
anchors across the fonts currently open in RoboFont. Choose one open UFO as the
default and click **Preview Changes**. For each matching glyph in every other
open UFO, the script lists anchors whose names are absent from that glyph in
the default. A source glyph with no matching default glyph is skipped and
reported. If the matching default glyph has no anchors, all anchors in that
source glyph are listed for removal.

Click **Apply (Leave Unsaved)** to remove the listed anchors. The script checks
the open fonts and anchor plan again before applying. Each changed glyph gets
an undo action. The UFOs remain open with unsaved changes so you can inspect
them and decide when to save. The default UFO is never changed.

## Opening and using the palette

Choose **Extensions → RoboFont Tools**. The existing palette is brought forward
if it is already open.

Enable **Measure Selected Points**, then select exactly two contour points in
the active Glyph Editor. A live editor overlay displays:

- absolute horizontal distance (`ΔX`);
- absolute vertical distance (`ΔY`);
- direct Euclidean distance;
- compact labels for the distance and deltas.

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

Set **Spacing**, **Gap**, and **Jitter** in the palette, then click **Activate
Knife**. The button reads **Knife Active — Drag** when the tool is selected.
Drag a straight line across the outlines in the Glyph Editor; a click alone
does not cut. Each
closed contour crossed cleanly is split into two contours. The two new cut
edges receive paired points at approximately the chosen spacing (25 units by
default). The edges wiggle independently while retaining at least the chosen
gap (20 units by default) at every point along them. Jitter defaults to 30
units. Each drag is one undoable action.

Spacing accepts 5–50 units; gap must be positive and jitter nonnegative. A
drag that does not enter and leave a contour cleanly has no effect. Open
contours and components are skipped. To stop using the
knife, choose another Glyph Editor tool.
The knife appears in the Glyph Editor toolbar with a serrated blade icon.

### Unify Anchors from Default

Click **Unify from Default…**, load a `.designspace`, and check the default UFO
shown in the window. The designspace default is selected automatically; use
**Choose Default UFO…** to select another source in that designspace. Click
**Preview Changes** to see changes per glyph and source, then **Apply and Save**.

The tool adds anchors missing from each non-default source at the default's
coordinates. Anchors already present keep their names and source-specific
positions. Anchors are put in the default's order for xTools compatibility.
Anchors found only in a non-default source are listed and retained after the
default anchors.
Glyphs missing from a source and glyphs with duplicate anchor names are listed
and skipped. The tool changes anchor data only; it does not alter outlines or
convert between cubic and quadratic curves. Open source fonts are updated in
RoboFont, and changed sources are saved. Because extra anchors remain by choice,
xTools may still flag those glyphs as anchor incompatible until you review the
extras.

## Project structure

```text
RoboFontTools.roboFontExt/
    info.plist                  extension metadata and menu entry
    lib/
        startup.py              Extensions-menu entry point
        robofont_tools/
            extension.py       singleton palette lifecycle
            menu.py            top-level script menu
            palette.py         EZWindow and tool registration
            geometry.py        pure calculations and formatting
            tools/
                selected_points.py        editor overlay and event lifecycle
                selected_points_model.py  read-only presentation logic
                selected_points_state.py  shared enabled state
                contour_probe.py          live contour/counter probe
                distribute_points.py       one-shot even-distribution action
                distribute_points_model.py pure distribution maths
                select_between.py        one-shot contour selection action
                select_between_model.py  route choice and repeat-click state
                rough_slice.py          interactive knife and contour slicing
                rough_slice_model.py    paired rough edges with a guaranteed gap
                unify_anchors.py       designspace anchor window and source updates
                unify_anchors_model.py default detection and anchor comparison
            scripts/
                anchors/
                    clean_from_default.py       open-UFO cleanup window and action
                    clean_from_default_model.py per-glyph removal plan
tests/
    test_geometry.py
    test_bundle.py
    test_distribute_points_model.py
    test_select_between.py
    test_rough_slice_model.py
```

The `tests/` folder is beside the installable bundle, not inside it. The team
package contains only the `.roboFontExt` bundle and separate utility scripts.

To add a future tool, place its logic in `robofont_tools/tools/`, give its tool
class an EZUI row (`content` and `description_data`), and return the class from
`get_tool_classes()`. Keep geometry and formatting independent of RoboFont
wherever possible. A tool that subscribes to events must expose idempotent
`start()` and `stop()` methods and release its
subscriber/controller references in `stop()`.

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
