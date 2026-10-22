# Fracturize

Fracturize is a private, internal RoboFont extension for producing two interpolation-compatible working fonts from a static source UFO:

- an intact fractured master;
- an eroded fractured master.

The extension lives inside the existing private `robofont-tools` repository. It is not a separate repository, public package, or public release.

## First-use workflow

Open a saved source UFO in RoboFont 4.6, install `Fracturize.roboFontExt`, then choose **Extensions → Fracturize**. Creating a project writes two complete working copies beside the chosen `.fracturize.json` file and opens them in RoboFont. They are ordinary user-owned documents; subsequent saving remains under the user's control through RoboFont.

Every processed glyph is written to that same open intact/eroded pair. The project JSON records identity, settings, versioned topology, deterministic seeds, source and output fingerprints, and per-glyph status. It does not save or own the output UFOs.

See:

- [installation](docs/INSTALLATION.md);
- [working with projects and glyphs](docs/WORKFLOW.md);
- [manual designspace handoff](docs/DESIGNSPACE_HANDOFF.md);
- [current architecture](docs/ARCHITECTURE.md).

## Implemented core

- non-zero-winding visible-union normalization for legitimate overlaps;
- adaptive polygonal flattening of cubic curves;
- deterministic branching fracture meshes with rough complementary crack edges;
- stable fragment, contour, and point identifiers;
- bounded Fracture Complexity from 0–100;
- versioned architectural erosion with a stable core, size-aware motion, baseline retention, and bounded downward drift;
- exact matched-geometry endpoint and interpolation previews;
- reconstruction, structural compatibility, sampled interpolation, and paired-font validation;
- persistent topology, motion-only regeneration, stale-source detection, edited-output detection, and ordinary-exception rollback;
- project-level component preservation or one-confirmation detached decomposition;
- sequential current/selected/manual/all-glyph processing with progress and cooperative cancellation;
- a minimal RoboFont bundle, menu item, panel, lifecycle observers, and user-owned open-font workflow.

## Important limits

Generated contours are line-only: native cubic curve preservation remains research work. Machine termination is not covered by a crash-proof transaction. Edited outlines are detected but never merged. General project relocation, migrations, broad version compatibility, background processing, advanced controls, public packaging, variable-font automation, and Glyphs automation are deferred.

## Development

The canonical Python package is inside `Fracturize.roboFontExt/lib`. Tests, regression fixtures, and proof scripts are kept locally by the maintainer and are not part of this repository.
