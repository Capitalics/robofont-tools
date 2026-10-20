# Script inventory

These scripts are independent of the RoboFont Tools palette. Only the three
portable scripts below are included in `RoboFontTools-team.zip`.

| Script | Where to run | Notes |
| --- | --- | --- |
| `rename-font-package.py` | Python with `fontTools` | Edit `SOURCE`, `OLD`, and `NEW` before running. It copies the source folder and edits the copy. |
| `testing/compare-component-spacing.py` | Python with `fontParts` or `defcon`, or DrawBot | Read-only UFO comparison. Pass a UFO root folder on the command line, or set `ROOT_PATH` for DrawBot. |
| `testing/proof-component-spacing-drawbot.py` | DrawBot | Read-only UFO proof; writes a PDF. Pass a UFO root folder or set `ROOT_PATH`. |

The other top-level scripts are tied to a specific Amstelvar project and may
modify UFO sources. They remain in this repository for development, but are
not a general teammate package. `xTools4_suggestion/` is experimental and is
also excluded.
