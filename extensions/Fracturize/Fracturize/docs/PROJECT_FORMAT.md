# Fracturize Project Format, Version 1

Stage 2 Phase A uses a human-readable `*.fracturize.json` file stored beside two UFO 3 output packages.

This is an implementation format, not a migration commitment. Version 1 is accepted exactly; unsupported versions fail rather than being upgraded silently.

## Layout

```text
ProjectFolder/
    ProjectName.fracturize.json
    ProjectName-FractureIntact.ufo/
    ProjectName-FractureEroded.ufo/
    project-data/
        topology/
            <glyph-name-sha256-prefix>.json
```

Paths in the project file are relative to the project file. The source path may contain `..` when the source is outside the project folder. Relinking and general relocation are deferred.

## Project record

The record stores:

- format name and version;
- project UUID, name, timestamps, and generator version;
- relative source and output paths;
- source family, style, UPM, and initial full-tree digest;
- project seed, Fracture Complexity, and motion settings;
- a motion-algorithm version independent of the topology version;
- seed, topology, fill, curve, and component policies;
- font-info and glyph-data allowlists;
- processed-glyph records;
- output-open and saving policy.

Each processed-glyph record stores:

- status;
- canonical source fingerprint;
- effective topology seed;
- relative topology path and SHA-256 digest;
- topology complexity;
- current pair revision UUID;
- canonical serialized-content digests for intact and eroded glyphs;
- the motion-algorithm version used for the pair;
- motion settings used for the current output;
- update timestamp.

## Canonical topology records

One topology JSON file is stored per processed glyph. It contains the canonical intact fragment geometry rather than attempting to recover topology from an eroded UFO.

The record includes:

- glyph name, width, Unicode values, and UPM;
- effective seed and flattening tolerance;
- full complexity profile;
- bounded normalization diagnostics;
- ordered fragments;
- stable fragment, contour, and point identifiers;
- canonical intact coordinates, area, bounds, centroid, and transform origin.

Motion-only regeneration reloads this record and recomputes only translation, rotation, and scale. A complexity change requires explicit topology regeneration.

## Source fingerprint

The source fingerprint is SHA-256 over canonical JSON containing:

- fingerprint format version;
- glyph name;
- width and Unicode values;
- UPM;
- ordered contours and closed status;
- explicit segment type and line/cubic coordinates;
- component names when present.

Anchors, notes, arbitrary glyph lib data, hints, and guidelines are omitted because Stage 2 does not copy them. A change to any generation input marks a processed glyph stale. Unsupported source geometry produces `source-unavailable` rather than overwriting output.

## Output ownership and metadata

The file-backed Phase A harness opens detached defcon objects and saves UFO packages so persistence can be tested. This is not the final RoboFont ownership policy. In the intended extension, the output UFOs are user-owned RoboFont documents, may remain open, and are saved by the user through RoboFont.

Each UFO stores the project UUID and its `intact` or `eroded` role. Each generated glyph stores:

- pair revision;
- source fingerprint;
- topology digest;
- fragment-to-contour mapping;
- stable contour and point identifiers.

On project open, the implementation verifies:

- the complete version-1 project schema, policy names, types, and value ranges;
- both UFOs exist and have the expected project UUID and roles;
- their glyph sets match each other and the project record;
- topology files exist and match recorded digests;
- both glyph copies match the recorded pair revision, source fingerprint, and topology digest;
- actual outline, identity, width, Unicode, and fragment-map content matches each side's recorded content digest.

This detects missing sides, mismatched projects, incomplete new glyphs, orphan glyphs, and later edits to generated glyphs. An edited glyph does not make the project impossible to open: it receives `output-edited` status. Motion-only regeneration and ordinary topology replacement refuse to overwrite it. Explicit topology regeneration with an edited-output replacement choice is required. Edited outlines are not merged in Phase C.

## Copied data

Font-info allowlist:

- units per em;
- ascender and descender;
- x-height and cap height;
- family and distinct style names;
- copyright;
- glyph order.

Glyph-data allowlist:

- name;
- width;
- Unicode values;
- generated fragment, contour, and point identifiers.

Kerning, groups, features, variation data, arbitrary lib keys, anchors, notes, guidelines, images, and hints are deliberately omitted.

## Saving policy

Atomicity is per glyph pair, not per batch. Both glyphs are generated and validated before persistent mutation.

For each pair:

1. preserve the previous generated glyph states in memory;
2. write matched glyphs into detached intact and eroded defcon fonts;
3. save intact, then eroded;
4. reopen and structurally validate the serialized pair;
5. commit the topology record and project record;
6. retain backups until all five operations have succeeded.

If an ordinary Python exception occurs during either glyph save, serialized reopen/validation, topology replacement, or project-record save, both previous glyph sides, the previous topology, in-memory project data, and the on-disk project record are restored. Fault-injection tests cover every boundary.

This is not crash-proof. Process termination, power loss, or filesystem failure between directory-UFO saves can still require manual recovery. On reopen, pair-revision and glyph-set checks stop on detectable incomplete state; there is no journal or automated crash recovery.
