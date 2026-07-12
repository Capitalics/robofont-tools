# RoboFont Development Notes

This repository should prefer official RoboFont APIs and documented extension patterns wherever possible. Scripts can use supporting libraries such as FontParts, Vanilla, and Defcon when they match the task, but RoboFont behavior should be verified against RoboFont documentation or local source before it is treated as stable.

## Reference Links

- [RoboFont documentation](https://doc.robofont.com/)
- [RoboFont API/reference documentation](https://www.robofont.com/documentation/reference/)
- [RoboFont how-tos](https://doc.robofont.com/documentation/how-tos/)
- [RoboFont extensions topic](https://doc.robofont.com/documentation/topics/extensions/)
- [RoboFont extension file specification](https://robofont.com/documentation/reference/extensions/extension-file-spec/)
- [Creating extensions tutorial](https://robofont.com/documentation/tutorials/creating-extensions/)
- [FontParts documentation](https://fontparts.robotools.dev/)
- [Vanilla documentation](https://vanilla.robotools.dev/)
- [Defcon documentation](https://defcon.robotools.dev/)
- RoboFont Subscriber documentation: verify availability in the current RoboFont
  docs or installed RoboFont resources before relying on it.

## Working Rules For Codex

- Do not invent RoboFont APIs.
- Prefer small runnable scripts before packaging behavior as extensions.
- Keep machine-specific paths out of version control.
- Put local paths and configuration in ignored local config files.
- Comment any AppKit or macOS-specific window-management code.
- Treat xTools integration as experimental unless verified from source.

## Testing Scripts

### Component spacing comparison

Use `scripts/testing/compare-component-spacing.py` to compare a source/base
glyph against a component-built glyph across UFOs on disk. Set `ROOT_PATH` to a
folder that contains UFO sources somewhere below it; unrelated files and folders
are ignored. The script searches recursively for `.ufo` packages, opens them
with `fontParts.world` or `defcon`, and prints a tab-separated table that can be
pasted into a spreadsheet. It does not use `CurrentFont()`, `AllFonts()`, or save
any UFO data.

Plain Python:

```sh
python scripts/testing/compare-component-spacing.py /path/to/sources --base A --component Aacute
```

DrawBot:

1. Open the script in DrawBot.
2. Set `ROOT_PATH`, `BASE_GLYPH_NAME`, and `COMPONENT_GLYPH_NAME` near the top.
3. Run the script and copy the output table.

Use `--format csv` for comma-separated output. Differences are reported in the
`flags` column, including missing glyphs, width and sidebearing deltas, bounds
deltas, unexpected component bases, component offsets, and component scales.

For a visual proof, use `scripts/testing/proof-component-spacing-drawbot.py` in
DrawBot. It produces portrait PDF pages with several UFOs per page. Each source
row has three columns: source/base glyph, component-built glyph, and an overlay.
The legend at the top marks the base glyph in cyan and the component glyph in
magenta; overlap appears as a darker blue/purple blend. Each column includes
outline fills, node markers, sidebearing lines, and a baseline. Any width,
sidebearing, bounds, component base, component offset, component scale, or
missing-glyph discrepancy is called out in red in the row label.

Near the top of the proof script, leave `SOURCE_PATH_INCLUDE_TEXT = ""` to use
every UFO below `ROOT_PATH`, or set it to text that must appear in each UFO path
when another path-based filter is useful. `SOURCE_PATH_EXCLUDE_TEXTS` skips
key-moment source folders. Set `SHOW_ONLY_SOURCES_WITH_DISCREPANCIES = True` to
draw only rows with differences, or `False` to draw all matching sources.

```sh
python scripts/testing/proof-component-spacing-drawbot.py /path/to/sources --base A --component Aacute --output component-proof.pdf
```
