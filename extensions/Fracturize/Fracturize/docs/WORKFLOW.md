# Fracturize workflow

## Create a project

1. Open the static source UFO in RoboFont and make it current.
2. Open **Extensions → Fracturize** and choose **Create Project**.
3. Choose a location for the small `.fracturize.json` record. Existing project files are refused rather than overwritten.
4. Fracturize creates two complete, untitled duplicates of the current source and opens both as ordinary RoboFont documents.
5. Save the intact and eroded documents wherever and whenever you choose with RoboFont's normal **Save / Save As** commands.

The duplicates initially preserve the complete source: all glyphs and layers, glyph order, metrics, Unicode values, anchors, notes, guidelines, kerning, groups, features, font info, libs, data, and images. Fracturize adds private identity metadata to distinguish the intact and eroded documents. It never saves the working fonts itself.

Keep the source, intact, and eroded documents open while processing. If an unsaved working document is closed, it cannot be recovered from a file path; reopen the project only after both working fonts have been saved at least once.

## Select and preview glyphs

Choose the current glyph, the font-window selection, and/or type a whitespace- or comma-separated glyph-name list. Duplicate names are collapsed.

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

Glyphs containing components require explicit confirmation. If accepted, Fracturize decomposes a detached copy for generation and writes decomposed contours to both working fonts; the source glyph remains unchanged. If declined, the glyph is skipped.

## Manual edits and undo

The output UFOs are user-owned and may remain open. Fracturize fingerprints the generated outline on each side. If either side is changed later, regeneration offers exactly three choices:

- **Replace Generated Glyph**: replace both generated sides from stored or regenerated topology;
- **Keep Existing Edited Glyph**: skip the operation and retain the edits;
- **Cancel**: stop the batch.

There is no outline merge. An undo entry is prepared in each working font for a successful generated-outline replacement. Undoing or editing only one side makes the pair intentionally detectable as edited.

Do not independently alter widths, kerning, groups, features, font info, layers, or other shared data in one working font. Pair validation blocks generation when the documents differ outside Fracturize-owned outlines and metadata.

## Reopen a project

Choose **Open Project** and select the `.fracturize.json` file. Fracturize first matches already open fonts by private identity, then opens recorded saved paths when available. Processing stops if the source or either working font is missing, unreadable, closed, or mismatched. It does not recreate a missing side or silently relink a different font.

The project record stores settings, algorithm versions, identities, per-glyph topology paths, seeds, source fingerprints, output fingerprints, and processed/failed state. It does not own or save the output documents.

## Current limitations

- Curves are adaptively flattened and generated contours are line-only.
- Selected components are decomposed, not preserved as components.
- Ordinary Python exceptions roll back the live pair and project state, but machine termination is not a crash-atomic multi-document transaction.
- Unsaved working fonts cannot be reopened after they are closed.
- Project relocation recovery, schema migration, edited-outline merging, background processing, automatic designspace building, and Glyphs automation are deferred.
- The fracture style retains a single-impact spiderweb bias; final visual tuning remains project-specific.

