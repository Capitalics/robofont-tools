# RoboFont Tools source repository

This repository contains several independent RoboFont projects. The team
package contains the drawing palette and portable utility scripts only.

| Source | Purpose | In the team package? |
| --- | --- | --- |
| `extensions/RoboFontTools/RoboFontTools.roboFontExt/` | Installable drawing palette | Yes |
| `scripts/rename-font-package.py` | Rename a copy of a compiled font package | Yes |
| `scripts/testing/compare-component-spacing.py` | Compare UFO component spacing | Yes |
| `scripts/testing/proof-component-spacing-drawbot.py` | Draw a spacing proof PDF | Yes |
| `scripts/AlignAnchors_parametric.py`, `ConstructGlyphs_Parametric.py`, `rename-anchor_new.py` | Amstelvar-specific editing scripts | No |
| `scripts/xTools4_suggestion/` | Experimental xTools integration | No |
| `extensions/WorkspaceLauncher.roboFontExt/` | Personal workspace setup | No |
| `extensions/Fracturize/` | Separate, experimental extension | No |
| `docs/` | Development notes | No |

See [the palette guide](extensions/RoboFontTools/README.md) and
[the script guide](scripts/README.md) for details. Development tests are kept
locally by the maintainer and are not part of this repository.

## Build a teammate package

Run `python3 tools/build_team_package.py /path/to/output-folder`. It writes
`RoboFontTools-team.zip`, containing one installable `.roboFontExt` folder,
three portable scripts, and a short installation guide. The builder uses an
explicit file list and rejects personal absolute paths in packaged Python
files. Generated caches, reports, tests, and unrelated projects are excluded.

The palette targets the locally validated RoboFont 4.6 and Python 3.12
environment. Live behavior should still be checked in RoboFont before wider
distribution.
