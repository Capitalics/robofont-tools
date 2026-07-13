# Stage 3 completion report

## Verdict

The minimal internal RoboFont extension is implemented. Its geometry, motion, topology, persistence, compatibility, and ordinary-exception rollback contracts remain intact, and the new open-document workflow is covered by headless integration tests.

The code is ready for a controlled first in-RoboFont smoke session. It is **not yet appropriate to claim a completed live application test on the real project**: RoboFont 4.6 launched with the development bundle installed, but macOS denied assistive access to the test process, so the Extensions menu and panel could not be driven or inspected programmatically. Shapely is also not yet present in RoboFont's external packages; the first manual menu launch must run RoboFont's dependency installer and be followed by a restart.

## Delivered extension

Bundle: `Fracturize.roboFontExt`

The bundle contains one canonical `fracturize` package plus:

- a validated `info.plist` menu registration;
- a dependency-aware menu entry point;
- a singleton extension/window lifecycle;
- a main-thread RoboFont adapter;
- a UI-independent controller;
- a versioned live-project implementation;
- a focused Vanilla panel with project, selection, complexity/seed, owner-directed motion, exact preview, validation, regeneration, and cancellation controls.

No fixtures, generated UFOs, artifacts, public packaging, or release machinery are inside the bundle.

## Working-font behavior

Project creation duplicates the current open source font twice through RoboFont/fontParts, opens both duplicates as untitled user documents, verifies that the copy retained complete shared data, adds only private role/identity metadata, and writes the project JSON. The user owns both documents and controls Save / Save As. Fracturize performs no final UFO save.

Processing replaces only selected default-layer contours/components and Fracturize-owned glyph metadata. Ordinary glyph metadata and all font-wide data remain untouched. Pair validation compares glyph sets/order, horizontal and vertical metrics, Unicode values, anchors, guidelines, notes, images, ordinary libs, kerning, groups, features, font info, layer structure and full non-default-layer glyph data, font guidelines, data, and images.

Component glyphs require explicit confirmation and use detached serialization for decomposition. A later output edit is detected by fingerprints and requires Replace, Keep, or Cancel. Motion-only regeneration reads stored topology; complexity or seed changes require explicit topology regeneration.

## Test results

Final automated run on 2026-07-13:

| Check | Result |
| --- | --- |
| Retained Stage 1/2 plus Stage 3 pytest suite | **106 passed in 7.28 s** |
| New RoboFont integration/project tests | **25 passed** (included above) |
| Bundle plist lint | **pass** |
| Python bundle compile/static entry-point check | **pass** |
| Independent serialized UFO validation | **11 glyphs, compatible pair** |
| Independent test designspace variable-font build | **pass** |
| Private source fixture mutation | **none** |
| Private fixture inside extension bundle | **none** |
| Accidental nested Git repository | **removed** |

The new tests cover bundle/menu declarations, lifecycle cleanup, source/selection/name collection, full duplication, outline-only replacement, exact preview geometry, motion/topology separation, seed and complexity invalidation, component confirmation, manual-edit choices, full rollback, hard-error blocking, progressive pair reuse, stale-source handling, per-glyph batch failure, cancellation, project reopen/relink, conflict refusal, strict version-1 schema validation, shared-data mismatch detection, and private-asset exclusion.

## Actual RoboFont status

Verified in the installed local application environment:

- RoboFont 4.6 is installed and uses bundled Python 3.12.
- A development symlink to the bundle exists in RoboFont's user `plugins` folder.
- RoboFont launched and remained running with that bundle installed.
- No new RoboFont crash report appeared during this launch.

Not verified inside the live UI:

- Extensions-menu discovery and entry invocation;
- Shapely installation through RoboFont's package installer;
- panel construction and observer callbacks;
- live source duplication, glyph write, undo, Save / Save As path refresh, close/reopen, and manual-edit dialogs.

The attempted UI inspection failed because `osascript` lacks macOS Accessibility permission. This is a test-environment limitation, not evidence that the UI passed or failed. Headless controller tests use defcon fonts and fake RoboFont environment boundaries; they do not replace the pending manual application smoke.

## Installation and launch

The development symlink is already installed locally. Restart RoboFont, choose **Extensions → Fracturize**, allow RoboFont to install `shapely>=2.1,<3` if prompted, restart again, open the static source UFO, and choose the same menu item to open the panel. Full steps are in `docs/INSTALLATION.md` and `docs/WORKFLOW.md`.

## Remaining limitations

1. Curves are adaptively flattened to line contours; original cubic geometry is not preserved.
2. Component outputs are decomposed after confirmation.
3. Unsaved output documents cannot be recovered after closing.
4. Rollback covers ordinary exceptions, not process termination or power failure across open documents.
5. Edited generated outlines cannot be merged.
6. General relocation/recovery and schema migrations are absent.
7. The red preview overlay strokes complete fragment contours, including exterior portions; it is not a provenance-filtered crack-only diagnostic.
8. Geometry remains synchronous on RoboFont's main thread. The UI yields between glyphs, but a complex individual glyph can temporarily block interaction.
9. The current visual language retains a single-impact spiderweb bias and needs owner evaluation on the full real project.
10. Broad compatibility, advanced crack controls, automated variable-font export, Glyphs automation, public packaging, and distribution remain explicitly deferred.
11. Private Excalibur fixtures and artifacts remain for current validation and require later cleanup.

## Owner decisions still needed

- Approve or tune the topology and architectural-motion defaults after the first real-project visual session.
- Choose the routine project-JSON location and Save As naming convention for the two user-owned UFOs.
- Decide whether the current full-fragment contour overlay is sufficient or whether a later crack-only overlay is worth implementing.
- Decide when curve-preserving boundary work becomes a priority relative to producing this project's polygonal masters.
- Schedule removal of the private fixture/artifact corpus before any future sharing or packaging.

## Readiness

Prompt 3 implementation is complete at the code and automated-validation level. The extension is ready for a **controlled first-use smoke test**, starting with Shapely installation and a synthetic or disposable UFO. Begin real-project production only after the pending RoboFont UI workflow—create, duplicate, preview, process, undo, save, reopen, and edited-output warning—has been exercised manually once in RoboFont 4.6.

