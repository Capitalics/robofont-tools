# RoboFont Tools

RoboFont Tools is a compact home for small utilities used while drawing. It
contains two read-only measurement tools and one editing action.

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

## Project structure

```text
RoboFontTools.roboFontExt/
    info.plist                  extension metadata and menu entry
    lib/
        startup.py              Extensions-menu entry point
        robofont_tools/
            extension.py       singleton palette lifecycle
            palette.py         EZWindow and tool registration
            geometry.py        pure calculations and formatting
            tools/
                selected_points.py        editor overlay and event lifecycle
                selected_points_model.py  read-only presentation logic
                selected_points_state.py  shared enabled state
                contour_probe.py          live contour/counter probe
                distribute_points.py       one-shot even-distribution action
                distribute_points_model.py pure distribution maths
tests/
    test_geometry.py
    test_bundle.py
    test_distribute_points_model.py
```

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
