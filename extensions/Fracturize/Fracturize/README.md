# Fracturize

Fracturize is a private, internal RoboFont extension for producing two interpolation-compatible working fonts from a static source UFO:

- an intact fractured master;
- an eroded fractured master.

The extension lives inside the existing private `robofont-tools` repository. It is not a separate repository, public package, or public release.

## First-use workflow

Open a source UFO in RoboFont 4.6, install `Fracturize.roboFontExt`, then choose **Extensions → Fracturize**. Creating a project opens two complete, unsaved duplicates of the current source font. They are ordinary user-owned RoboFont documents; use RoboFont's own **Save / Save As** commands for them.

Every processed glyph is written to that same open intact/eroded pair. The project JSON records identity, settings, versioned topology, deterministic seeds, source and output fingerprints, and per-glyph status. It does not save or own the output UFOs.

See:

- [installation](docs/INSTALLATION.md);
- [working with projects and glyphs](docs/WORKFLOW.md);
- [manual designspace handoff](docs/DESIGNSPACE_HANDOFF.md);
- [Stage 3 completion status](docs/STAGE3_COMPLETION_REPORT.md).

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
- explicit component confirmation and detached decomposition;
- sequential current/selected/named glyph processing with cancellation between glyphs;
- a minimal RoboFont bundle, menu item, panel, lifecycle observers, and user-owned open-font workflow.

## Important limits

Generated contours are line-only: native cubic curve preservation remains research work. Machine termination is not covered by a crash-proof transaction. Unsaved working documents cannot be recovered after closing. Edited outlines are detected but never merged. General project relocation, migrations, broad version compatibility, background processing, advanced controls, public packaging, variable-font automation, and Glyphs automation are deferred.

The private Excalibur subset and generated artifacts remain in the repository for current validation. They are outside the extension bundle and marked for removal during a later cleanup; they must never be distributed.

## Development validation

The canonical Python package is inside `Fracturize.roboFontExt/lib`. Run the complete retained suite with that package on `PYTHONPATH`:

```bash
PYTHONPATH=Fracturize.roboFontExt/lib python -m pytest -q
```

The Stage 1/2 reports and comparison artifacts remain in `docs/` and `artifacts/` as the technical basis for this minimal integration.

