# Workspace Tool Notes

The planned Workspace Launcher tool is a workspace-layout utility for starting a
repeatable RoboFont session. It should begin as a small script and only become an
extension after the workflow is proven.

## Planned Behavior

- Open a set of fonts and designspaces.
- Open or trigger selected xTools windows.
- Open common RoboFont windows such as Space Center.
- Arrange windows on screen.
- Later, save and restore named layouts.

## MVP Constraints

- The first version may be a script, not an extension.
- Use a local ignored JSON config for file paths and layout coordinates.
- Window matching by title is acceptable for a prototype, but should later be
  improved.
- Multi-monitor setups may be brittle.
- xTools calls must be verified against xTools4 source before relying on them.

## Risks / Unknowns

- RoboFont window APIs and AppKit behavior may vary by RoboFont and macOS
  version.
- xTools windows may not expose stable public entry points.
- Title-based window matching can fail when document names, localization, or
  window titles change.
- Layout coordinates may not transfer between displays, scaling settings, or
  monitor arrangements.
- Opening many files and panels at once may need ordering, delays, or readiness
  checks.
