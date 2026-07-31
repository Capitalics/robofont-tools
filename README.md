# RoboFont Tools

Private toolbox for RoboFont scripts and extensions.

## Extensions

- `extensions/RoboFontTools/`: a compact, read-only drawing-utility palette.
  Version 0.1 measures ΔX, ΔY, direct distance, and angle between exactly two
  selected contour points.
- `extensions/WorkspaceLauncher.roboFontExt/`: opens common RoboFont/xTools
  windows, restores their layout, and applies saved project paths.
- `extensions/Fracturize/`: creates interpolation-compatible fractured glyph
  masters.

## Docs

- [RoboFont development notes](docs/robofont-development.md)
- [Extension structure notes](docs/extension-structure.md)
- [Workspace tool notes](docs/workspace-tool-notes.md)

## Scripts

- `scripts/testing/proof-component-spacing-drawbot.py` draws a PDF proof that
  compares a source glyph against a component-built glyph in each discovered
  UFO, without using open RoboFont fonts.
  By default it scans all concrete UFO packages below
  `/Users/tdbk/REPOS/amstelvar-avar2/Sources/Roman` and compares `Ocyr`
  against `O`.
  To scan only tuning UFOs, pass the tuning folder:
  `python scripts/testing/proof-component-spacing-drawbot.py /Users/tdbk/REPOS/amstelvar-avar2/Sources/Roman/tuning`.
  To switch back to all Roman sources, omit the path or pass
  `/Users/tdbk/REPOS/amstelvar-avar2/Sources/Roman`.
- `scripts/testing/compare-component-spacing.py` outputs a TSV/CSV table for
  component spacing checks.

## Status

Private, actively developed toolbox targeting the locally validated RoboFont
4.6 and Python 3.12 environment. Individual extension documentation records any
narrower compatibility requirements.
