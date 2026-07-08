# Extension Structure Notes

This repository is intended to stay simple while tools are being explored. Stable
scripts may later be promoted into `.roboFontExt` packages, but no extension
package should be created until there is a concrete tool worth packaging.

## Intended Repository Structure

- `scripts/`: runnable RoboFont scripts and prototypes.
- `extensions/`: packaged RoboFont extensions, when a script has become stable
  enough to distribute or install as a bundle.
- `docs/`: project notes, RoboFont references, and design decisions.
- `shared/`: reusable Python helpers shared by scripts or extensions.
- `tools/`: local development utilities, build helpers, or maintenance scripts.

## RoboFont Extensions

RoboFont extensions use `.roboFontExt` bundles. A packaged extension includes an
`info.plist` file that describes extension metadata and entry points according to
the RoboFont extension file specification.

For now, keep implementation work in focused scripts. Promote a script into an
extension only when its behavior, configuration shape, and install expectations
are clear.
