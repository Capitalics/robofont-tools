# Fracturize workflow

## Create a project

1. Open the static source UFO in RoboFont and make it current.
2. Open **Extensions → Fracturize** and choose **Create Project**.
3. Choose a name and location for the `.fracturize.json` record. Existing project or working-font destinations are refused rather than overwritten.
4. Fracturize writes complete `-Intact.ufo` and `-Eroded.ufo` copies in that folder and opens both as ordinary RoboFont documents.
5. Continue saving the working documents with RoboFont's normal **Save / Save As** commands when you choose.

The copies initially preserve the complete source: all glyphs and layers, glyph order, metrics, Unicode values, anchors, notes, guidelines, kerning, groups, features, font info, libs, data, and images. Fracturize adds private identity metadata to distinguish the intact and eroded documents. Project creation performs the initial writes; normal editing and subsequent saves remain user-controlled.

Keep the source, intact, and eroded documents open while processing. **Open Project** first matches open documents by identity and otherwise opens the recorded paths.

## Select and preview glyphs

Choose exactly one batch source: current glyph, font-window selection, whitespace-separated manual glyph list, or all glyphs in source order. Duplicate names are collapsed while preserving order.

**Fracture Complexity** changes topology and therefore requires **Regenerate Topology** for an already processed glyph. The optional seed override also changes topology. Motion controls update the exact matched-geometry preview without changing stored outlines; commit them with **Regenerate Motion**.

The preview shows the intact master, a direct point interpolation, and the eroded master. The red contour overlay exposes the fragment contour boundaries. Automated compatibility findings and sidebearing warnings are shown separately from visual judgment. A hard structural or interpolation finding blocks both glyph writes; recognisability and erosion character remain user decisions.

## Process glyphs

- **Generate** processes unprocessed glyphs.
- **Regenerate Motion** reuses stored topology and stable fragment identity.
- **Regenerate Topology** creates a new deterministic layout using the current complexity and seed.
- **Replace Stale Glyph** explicitly rebuilds a glyph whose source outline changed.
- **Validate** checks the working-font pair, stored topology, and edited-output fingerprints.
- **Cancel Batch** stops between glyphs; already completed pairs remain committed.

Each successful operation replaces only the selected glyph's contours and components in the two working fonts. Width, Unicode values, anchors, notes, guidelines, image, ordinary glyph lib data, and all font-wide data remain untouched. Generated outlines are polygonal line contours because the current backend adaptively flattens source curves.

With **Decompose components before processing** off, component glyphs are left unchanged in both complete working copies and reported as `component preserved`; they inherit changes through any processed base glyphs. With it on, Fracturize asks once before the batch, decomposes detached source copies for generation, and writes decomposed contours to both working fonts. The open source remains unchanged.

## Manual edits and undo

The output UFOs are user-owned and may remain open. Fracturize fingerprints the generated outline on each side. If either side is changed later, regeneration offers exactly three choices:

- **Replace Generated Glyph**: replace both generated sides from stored or regenerated topology;
- **Keep Existing Edited Glyph**: skip the operation and retain the edits;
- **Cancel**: stop the batch.

There is no outline merge. An undo entry is prepared in each working font for a successful generated-outline replacement. Undoing or editing only one side makes the pair intentionally detectable as edited.

Do not independently alter widths, kerning, groups, features, font info, layers, or other shared data in one working font. Pair validation blocks generation when the documents differ outside Fracturize-owned outlines and metadata.

## Reopen a project

Choose **Open Project** and select the `.fracturize.json` file. Fracturize first matches already open fonts by private identity, then opens recorded saved paths when available. Processing stops if the source or either working font is missing, unreadable, closed, or mismatched. It does not recreate a missing side or silently relink a different font.

The project record stores settings, algorithm versions, identities, per-glyph topology paths, seeds, source fingerprints, output fingerprints, and processed/failed state. It identifies the working documents but does not make them plugin-owned.

## Current limitations

- Curves are adaptively flattened and generated contours are line-only.
- Component glyphs are either preserved unchanged or explicitly decomposed for a batch.
- Ordinary Python exceptions roll back the live pair and project state, but machine termination is not a crash-atomic multi-document transaction.
- Project relocation recovery, schema migration, edited-outline merging, background processing, automatic designspace building, and Glyphs automation are deferred.
- The fracture style retains a single-impact spiderweb bias; final visual tuning remains project-specific.
