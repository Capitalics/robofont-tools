# Fracturize installation

Fracturize is an internal RoboFont extension. The supported target is the currently validated application environment:

- RoboFont 4.6;
- RoboFont's bundled Python 3.12;
- macOS on Apple silicon;
- Shapely 2.1.x / GEOS, installed into RoboFont's external-packages folder.

No compatibility claim is made for older RoboFont, Python, or macOS versions.

## Install the bundle

The extension bundle is `Fracturize.roboFontExt` at the repository root. Either double-click it and accept RoboFont's installation prompt, or create a development symlink to it in RoboFont's user `plugins` folder. Restart RoboFont after installing or replacing the bundle.

On the first launch, Fracturize checks for Shapely. If it is absent, RoboFont's package installer opens and installs the bounded dependency `shapely>=2.1,<3` into RoboFont's external packages. Restart RoboFont once more after that installation.

The extension deliberately relies on RoboFont's bundled defcon, fontParts, fontTools, Vanilla, and preview APIs. It does not vendor those packages and has no public distribution or update mechanism.

## Launch

Open a source UFO in RoboFont and make its font window current. Choose **Extensions → Fracturize**. The same menu command brings the existing panel forward instead of opening duplicate panels.

## Development tests

Tests, the regression UFO, and validation scripts are kept locally by the maintainer and are not part of this repository.
