# RoboFont Tools

Private toolbox for RoboFont scripts and extensions. The first utility is
Workspace Launcher, a tool for opening common RoboFont/xTools windows and
arranging a working layout.

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

Early private toolbox for RoboFont scripts and extensions. No tools are
implemented yet.
