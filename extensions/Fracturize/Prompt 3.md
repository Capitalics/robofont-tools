# Stage 3 — Conditional Minimal RoboFont Extension

Turn the validated Stage 1 geometry core and Stage 2 persistent two-UFO workflow into the first usable standalone RoboFont extension release.

Keep this release deliberately small. Preserve the tested geometry, identity, validation, and project architecture. Do not rewrite the core merely to simplify the interface.

## Mandatory prerequisite gate

Before changing code, read the Stage 1 report, the Stage 2 implementation report, the read-only audit, any correction log, and the final test results.

Proceed only if the final Stage 2 verdict is `viable` and all of these are true:

- intact reconstruction passes its declared tolerance on the supported corpus;
- generated master pairs remain structurally compatible after serialization;
- Fracture Complexity is deterministic and bounded;
- one project creates and reuses exactly one intact and one eroded UFO;
- project reopening and later glyph additions work;
- stale source glyphs are detected;
- ordinary paired-write failure behavior is tested and documented;
- no unresolved critical or high-severity defect remains.

If any prerequisite is missing, stop. Report the failed gate and return the work to the relevant earlier stage. Do not build UI around an unproven core.

## Product concept

The user works from a static source font and a persistent **fracture project** containing:

- the source font reference;
- one intact output UFO;
- one eroded output UFO;
- shared fracture and motion settings;
- processed and stale glyph status;
- stored or reproducible per-glyph topology.

Every successfully processed glyph is written to both existing output UFOs. The pair accumulates glyphs over time and may later be used as candidate designspace masters.

The source font remains unchanged. The extension manages the generated output pair and must never silently replace processed glyphs or recreate a missing side.

## First-release scope

The first release must include:

- a standalone `Fracturize.roboFontExt` bundle;
- one canonical `fracturize` Python package rather than duplicated source trees;
- menu registration and a minimal extension window;
- project creation and opening;
- current-glyph and selected-glyph processing;
- a glyph-name list input if it is simple to support reliably;
- the Fracture Complexity control;
- a small set of motion controls;
- intact, eroded, and interpolation preview;
- structural validation and clear status reporting;
- reuse of the persistent UFO pair;
- installation, workflow, limitations, and designspace-handoff documentation;
- tests for the new RoboFont integration layer.

Explicitly defer:

- crash-proof or journaled filesystem transactions;
- schema migration machinery;
- broad historical RoboFont, Python, or macOS support;
- a large advanced-control panel;
- arbitrary custom complexity profiles;
- extensive debug overlays;
- character-set browsers or complex glyph-set builders;
- background threading around RoboFont objects;
- automatic variable-font building;
- automatic Glyphs import/export;
- sophisticated project relocation and recovery;
- output-UFO collaborative editing or merge support.

Document these as deferred work rather than incomplete advertised features.

## Supported environment and extension structure

Target the exact RoboFont/Python environment validated in Stages 1 and 2, or a narrow explicitly tested range. Do not add compatibility abstractions for untested versions.

Inspect current RoboFont extension conventions for:

- bundle layout and `info.plist`;
- entry point and menu registration;
- package loading;
- preferences namespacing;
- Vanilla and preview integration;
- documentation and installation.

Adapt only the required patterns. Do not copy unrelated code or depend on a neighboring extension.

Keep layers clear:

- geometry, topology, motion, and validation core;
- project and headless UFO persistence;
- RoboFont adapters for source selection and object conversion;
- UI controllers and previews.

All live RoboFont object access must occur on the main thread. Pure geometry may remain independent and testable outside RoboFont.

## Main user workflow

Support this workflow:

1. create a fracture project or open an existing one;
2. choose the static source font;
3. choose a project folder and project name;
4. create the intact UFO, eroded UFO, and project file;
5. select the current glyph or selected glyphs;
6. adjust Fracture Complexity and basic motion settings;
7. generate a preview using canonical matched geometry;
8. review structural status and visual result;
9. explicitly process or replace the glyph;
10. validate and write both matched glyphs;
11. continue adding later glyphs to the same UFO pair;
12. close and reopen the project without losing settings or status.

Do not create output UFOs lazily during glyph processing. Project creation owns that operation.

## Project creation UI

Provide only the necessary controls:

- project name;
- project folder;
- source font;
- family name;
- intact and eroded UFO filenames;
- intact and eroded style names;
- project seed.

Suggested defaults:

- family name from the source;
- intact style name `Fracture Intact`;
- eroded style name `Fracture Eroded`;
- filenames based on the project name.

Show conflicts before creating anything. Do not overwrite existing UFOs or a project file without explicit confirmation. If safe overwrite behavior was not validated in Stage 2, refuse the operation and ask the user to choose another folder.

## Existing project UI

When opening a project, show:

- source font identity or path;
- intact and eroded UFO paths;
- project seed;
- Fracture Complexity;
- processed, stale, and failed glyph counts;
- project/generator version;
- warnings for missing or unreadable files.

If one UFO is missing, unreadable, or mismatched, stop processing and explain the problem. Do not silently recreate or relink it.

Simple source relinking may be added if it is straightforward and tested. General project relocation is deferred.

## Glyph selection and status

Support:

- current glyph;
- selected glyphs in the font window;
- a direct glyph-name list if reliable.

Show simple statuses:

- unprocessed;
- processed and compatible;
- stale because the source changed;
- failed;
- warning.

Do not build a full character-set selection interface in this release.

## Fracture Complexity and basic controls

Make **Fracture Complexity** the primary control, with range `0–100` and optional labels:

- `0`: minimal;
- `25`: sparse;
- `50`: moderate;
- `75`: dense;
- `100`: extreme.

Use the versioned, validated Stage 1 mapping. The control must update the coordinated topology parameters as tested; it must not become a direct fragment-count slider.

Expose only a small set of motion controls in the first release:

- erosion amount;
- movement direction;
- movement spread;
- limited rotation amount;
- limited scale reduction;
- seed override or regenerate action.

Keep safe bounds from Stage 1. Never allow scaling to or through zero.

Do not expose the full lower-level parameter bundle as editable advanced controls. Developer diagnostics may display derived values read-only if useful.

Clearly distinguish topology-changing actions from motion-only actions:

- changing Fracture Complexity requires explicit topology regeneration;
- changing motion controls reuses existing topology;
- preview-only changes do not mutate stored output;
- a processed glyph is never replaced without confirmation.

For a processed glyph, offer only the necessary choices:

- keep current output;
- regenerate motion with current topology;
- regenerate topology and motion;
- cancel.

## Components

Use the explicit component policy validated in earlier stages.

If component decomposition is supported, notify the user that the generated output will contain decomposed contours. If it is not supported, skip the glyph with a clear message. Do not silently decompose or mix strategies between the two output UFOs.

## Preview

Provide a compact preview containing:

- intact state;
- eroded state;
- interpolation slider from `0–100`;
- optional fracture-boundary overlay;
- compatibility status and warnings.

The interpolation preview must directly interpolate the exact matched point geometry that would be written to the two masters. Do not regenerate geometry for preview and do not fake motion with unrelated animation.

Fragment IDs, centroids, movement vectors, protected zones, size classes, and other extensive overlays are deferred. A developer-only diagnostic view is optional if it uses existing core data and does not enlarge the user workflow.

## Automated validation and visual review

Keep automated and subjective evaluation separate in both code and UI.

Automated validation must report:

- hard structural errors;
- interpolation risks;
- metadata or project warnings.

A hard error must prevent writing either glyph. Use the shared Stage 1/2 validator for contour, point, segment, winding, identity, width, degeneracy, and sampled-intermediate checks.

Visual review remains the user's decision. The preview may help the user judge recognisability, erosion character, density, and intermediate appearance, but the extension must not label those subjective qualities as automatically “passed.”

## Output UFO behavior

Reuse the exact project and paired-write implementation validated in Stage 2.

For each successful glyph:

- write the matched intact and eroded contours;
- preserve stable identity data;
- copy the supported width, Unicode, anchor, note, and lib allowlists;
- preserve all previously processed glyphs;
- update source fingerprint and project status only after the paired operation succeeds;
- save the same two existing UFOs.

Do not claim crash-proof atomic saving. Preserve and display the documented Stage 2 limitation.

Follow the Stage 2 decision about whether output UFOs remain closed or open in RoboFont. If they remain closed, offer an explicit user action to open them after successful processing if this can be implemented safely. Do not silently open, close, or replace dirty fonts.

## Multiple-glyph processing

Support a straightforward sequential loop for selected glyphs if it can reuse the Stage 2 per-glyph operation.

- validate and commit one matched pair at a time;
- show progress and per-glyph failures;
- allow cancellation between glyphs;
- preserve already completed glyphs;
- leave the current failed glyph uncommitted as a pair;
- do not use unsafe threading around RoboFont font objects.

Batch-wide atomicity is not required.

## Variable-font handoff

Provide a concise manual guide, not automated export.

Explain:

- that the two UFOs are candidate interpolation masters;
- how to create a two-source designspace with relative paths;
- how to assign intact and eroded axis locations;
- how to run an interpolatability check and test build;
- how unprocessed or missing glyphs must be handled;
- that an experimental custom axis tag is not automatically suitable for final distribution;
- which metadata, components, anchors, kerning, groups, and features are copied or omitted.

Include only a short note that manual Glyphs import may be attempted and can be lossy. Extensive Glyphs instructions or automation are deferred until a specific version and workflow are tested.

## Tests

Retain all Stage 1 and Stage 2 tests. Add focused tests for:

1. extension bundle validation and loading in the supported RoboFont environment;
2. menu registration and window lifecycle;
3. project create/open UI controllers;
4. conflict refusal;
5. current and selected glyph collection;
6. status display for unprocessed, processed, stale, failed, and warning glyphs;
7. Fracture Complexity wiring to the validated mapping;
8. topology versus motion regeneration actions;
9. preview using the exact matched output geometry;
10. hard errors preventing writes;
11. component policy messaging;
12. repeated glyph additions to the same UFO pair;
13. sequential multiple-glyph cancellation and per-glyph failure;
14. output-UFO open/closed behavior selected in Stage 2;
15. project reopening through the extension.

Run integration tests in the supported RoboFont version where automation is practical. Clearly separate tests that run outside RoboFont, tests run inside RoboFont, manual UI checks, and skipped checks.

## Documentation

Create concise documentation for:

- installation and supported environment;
- project creation and reopening;
- the persistent two-UFO workflow;
- processing later glyphs into the existing pair;
- Fracture Complexity and basic motion controls;
- topology versus motion regeneration;
- component behavior;
- source-change warnings;
- automated validation versus visual judgment;
- manual designspace handoff;
- polygon flattening and curve limitations;
- paired-save limitations;
- troubleshooting and known limitations.

Do not write documentation for deferred features as if they exist.

## Release acceptance gate

The first extension release is ready only if:

- the mandatory prerequisite gate was satisfied;
- the bundle installs and opens in the declared RoboFont environment;
- a user can create and reopen a project;
- the same output UFO pair accumulates later glyphs;
- preview uses the actual matched master geometry;
- Fracture Complexity behaves exactly as validated;
- hard compatibility errors block both writes;
- processed and stale glyphs are not silently replaced;
- tests and manual checks are reported honestly;
- curve, saving, version-support, and handoff limitations are visible in the documentation.

Do not claim broad production readiness. Call this the first supported release for the declared environment and input limitations.

## Final completion report

Provide:

1. prerequisite-gate evidence;
2. extension and repository structure;
3. created and modified files;
4. supported RoboFont/Python environment;
5. installation and project workflow;
6. explanation of continued glyph additions to the same UFO pair;
7. Fracture Complexity and deterministic seed behavior;
8. preview and validation behavior;
9. actual automated and manual test results;
10. known limitations and deferred features;
11. a recommendation for the next small improvement.

If the prerequisite gate fails, do not implement this prompt. Report which earlier stage must resume.
