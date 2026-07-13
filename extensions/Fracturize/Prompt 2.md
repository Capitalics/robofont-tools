# Stage 2 — Persistent Two-UFO Project, Audit, and Corrections

Extend the successful Stage 1 geometry prototype into a practical persistent project workflow that progressively builds one intact output UFO and one eroded output UFO.

This prompt contains three distinct phases:

1. **Phase A — implementation** of persistent project and two-UFO handling;
2. **Phase B — read-only audit** of the complete Stage 1 and Phase A result;
3. **Phase C — bounded corrections and re-verification** based on the audit.

Keep the phases separate. Do not modify implementation during Phase B. Record the audit verdict before beginning Phase C.

Do not build the production RoboFont interface in this stage.

## Prerequisite gate

Read the Stage 1 report and actual test results before making changes.

Proceed only if Stage 1 concluded that the geometry is `viable`, or `viable after specific geometry corrections` and those corrections have been completed and verified.

If intact reconstruction, structural compatibility, deterministic identity, or temporary UFO serialization still has a hard failure, stop and report that Stage 2 is blocked. Do not hide a geometry failure behind project-management code.

## Intended project model

A **fracture project** owns:

- one source font;
- one intact output UFO;
- one eroded output UFO;
- one persistent project configuration;
- shared fracture and erosion settings;
- per-glyph generation status and source fingerprints.

The two output UFOs are created once per project. Every later successfully processed glyph is appended to that same pair. The system must never create a new UFO pair per glyph.

The source font remains unchanged. The output UFOs are generated project artifacts and must not be silently overwritten or recreated.

# Phase A — Implementation

## Keep the implementation practical

Continue in the standalone Stage 1 repository. Add only the persistence and headless UFO-management layers required for this stage.

Do not add:

- a full extension bundle or menu registration;
- a production GUI;
- schema migration machinery;
- crash-proof multi-package transaction infrastructure;
- broad RoboFont or Python compatibility shims;
- extensive advanced controls;
- automated Glyphs import/export.

A simple command-line tool, test harness, or small RoboFont development script is sufficient to exercise project creation, reopening, and glyph processing.

## Project configuration

Use a dedicated, human-readable JSON project file stored beside the output UFOs unless the existing prototype provides a clearly better tested format.

The first format should include a simple format version but does not need a migration framework. Store only data needed to reopen and continue the project:

- project name and format version;
- source font path or identity;
- intact and eroded UFO paths;
- project seed and seed-derivation version;
- Fracture Complexity value;
- shared topology settings;
- shared erosion and motion settings;
- processed glyph records;
- effective glyph seeds or overrides;
- source glyph fingerprints;
- topology record location or sufficient reproducible topology data;
- generator version.

Prefer relative paths when the project file and UFOs live together. Absolute source paths are acceptable for this stage if the limitation is documented. Project relocation and source relinking may be deferred to Stage 3 or later.

Validate the project file on open. If either output UFO is missing, unreadable, or does not match the project identity, stop with a clear error. Do not silently recreate one side.

## Topology persistence

Stage 3 will need to regenerate motion without regenerating topology. Therefore, do not rely on reverse-engineering topology from transformed output contours.

Choose and document one practical method:

- store the canonical per-glyph topology in the project or a small project data directory; or
- store a complete, versioned generator record that is proven to reproduce identical canonical topology with the pinned generator version.

Stored canonical geometry is preferred if algorithm changes could otherwise alter old glyphs. Avoid an elaborate database or migration system.

## Source identity and change detection

Define a deterministic source-glyph fingerprint that includes the inputs which affect generation. At minimum consider:

- normalized outline or decomposed geometry;
- width;
- Unicode values;
- component data if decomposition is supported;
- relevant anchors or glyph metadata that will be copied.

Canonicalize fingerprint input so harmless serialization differences do not mark a glyph stale.

When a processed source glyph changes:

- mark it stale;
- preserve the existing generated pair;
- warn rather than silently replacing it;
- allow an explicit regeneration attempt;
- replace the previous pair only after new outputs pass validation.

## Output UFO creation

Create the intact and eroded UFOs during explicit project creation, not lazily during the first glyph operation.

Use UFO 3 unless Stage 1 established a compelling alternative. Ask for or accept explicit destination paths and refuse conflicts unless overwrite is explicitly enabled for a test scenario.

Copy a documented allowlist of font information, such as:

- units per em;
- ascender and descender;
- x-height and cap height;
- family name;
- copyright where appropriate;
- glyph order where useful.

Assign distinct style names, for example:

- `Fracture Intact`;
- `Fracture Eroded`.

Do not blindly copy source variation data, arbitrary lib keys, kerning, groups, or features. State which data is copied, generated, and omitted.

## Glyph processing and metadata

For each requested glyph:

1. load and fingerprint the source glyph;
2. normalize input using the Stage 1 geometry policy;
3. create or load its canonical topology;
4. build intact and eroded states from that topology;
5. run the shared validator;
6. prepare both output glyphs without mutating either persistent UFO;
7. commit the matched glyphs to the same existing UFO pair;
8. save both UFOs;
9. update the project record only after both saves succeed;
10. reopen or re-read the saved outputs in tests and validate them again.

Preserve previously generated glyphs. Copy a documented glyph-data allowlist:

- glyph name;
- width;
- Unicode values;
- stable fragment/contour/point identity;
- selected anchors, notes, or lib data only when explicitly supported.

Component glyphs must follow the Stage 1 policy: explicitly reject them or explicitly decompose them. Do not silently change policy between glyphs or between the two UFOs.

## Practical paired-write safety

The goal in this stage is reliable application-level paired writing, not a crash-proof filesystem transaction across two directory UFOs and a JSON file.

At minimum:

- generate and validate both glyphs before mutating persistent fonts;
- keep the pre-write glyph state in memory or a simple temporary backup;
- if writing or ordinary saving of either side raises an error, restore both in-memory glyph states where possible and do not mark the project record committed;
- detect an incomplete prior save when reopening if practical;
- document the remaining risk of process or machine failure between saves.

Do not claim literal atomicity or crash-proof behavior. A journaled recovery system can be considered later if real use demonstrates the need.

Define atomicity per glyph pair, not per multi-glyph batch. In a sequence of glyphs, already completed glyphs may remain saved; the current failing glyph must not be intentionally committed to only one side.

For this stage, prefer keeping output UFOs closed in RoboFont and writing them through detached fontParts/defcon-compatible objects if that matches the tested environment. If another policy is chosen, document how dirty documents, notifications, save conflicts, and undo are handled. Do not leave this behavior implicit.

## Reopening and continued processing

Demonstrate this exact workflow:

1. create one project and its two UFOs;
2. process one glyph;
3. close all project objects;
4. reopen the project from its JSON file;
5. process one or more additional glyphs;
6. verify that the same two UFO paths are reused;
7. verify that earlier glyphs are unchanged;
8. verify that all generated glyph pairs remain compatible.

Changing motion-only settings should reuse stored topology. Changing Fracture Complexity or another topology setting should require explicit topology regeneration. Never silently replace a processed glyph.

## Phase A tests

Retain all Stage 1 tests and add focused tests for:

1. project creation and JSON validation;
2. creation of exactly one UFO pair;
3. refusal of conflicting output paths;
4. project closing and reopening;
5. appending later glyphs to the same UFO pair;
6. preservation of previously generated glyphs;
7. deterministic project and glyph settings after reopen;
8. topology persistence and motion-only regeneration;
9. explicit topology regeneration after complexity changes;
10. source fingerprinting and stale status;
11. source-change replacement only after validation;
12. component rejection or explicit decomposition;
13. paired validation before persistent mutation;
14. ordinary write/save failure rollback where it can be simulated reliably;
15. project record not advancing after a failed pair;
16. saved UFO reopening and independent compatibility validation;
17. preservation of the documented font and glyph metadata allowlists.

Report actual results and limitations. Do not represent a simulated exception before saving as proof of crash recovery.

# Phase B — Read-only Audit

After Phase A implementation and tests are complete, stop changing code and conduct a distinct audit.

Record the repository commit or exact working-tree state being reviewed. Inspect the implementation, generated artifacts, reports, and actual test output.

## Repository audit

Verify:

- the repository is standalone;
- geometry code remains independent of RoboFont UI code;
- persistence and UFO management are isolated from geometry;
- no neighboring extension is imported or modified;
- test fixtures and licenses are clear;
- no premature production extension architecture has been added.

## Geometry and complexity regression audit

Confirm that Stage 1 guarantees still hold after persistence was added:

- normalized silhouette reconstruction;
- counters, nested regions, overlaps, and flattened curves;
- stable fragment, contour-part, contour, and point identity;
- compatible intact and eroded outputs;
- bounded transforms and sampled intermediate states;
- deterministic Fracture Complexity at `10`, `25`, `50`, `75`, and `90`;
- acceptable performance and minimum feature size.

Determine whether changing complexity regenerates or refines topology and confirm that the documentation tells the truth.

## Persistent project audit

Verify:

- output UFOs are created once during project creation;
- later glyphs use the same paths and preserve old glyphs;
- reopen restores the same project settings;
- topology can be reused for motion-only regeneration;
- stale source glyphs are detected without overwriting output;
- missing or mismatched output UFOs cause a clear stop;
- project data and output metadata match the documented allowlists;
- failure handling does not deliberately leave one side updated;
- limitations of non-crash-proof saving are clearly stated.

## Independent compatibility audit

Use an independent serialized-UFO or fontTools-based check where practical. Do not rely only on the generator's internal validator.

For each generated pair, compare:

- glyph set and glyph names;
- widths and supported metadata;
- contour and point counts and ordering;
- segment and on-curve/off-curve structure;
- winding convention;
- fragment and contour-part IDs;
- sampled interpolated outlines.

Create a small two-source designspace for the supported test glyph set and verify interpolatability or a test build with the chosen toolchain. This is a validation artifact, not yet a production export feature.

## Visual audit

Review visual sheets separately from automated checks. Assess recognisability, erosion character, density across varied glyphs, and intermediate progression. Label these findings as human judgments.

Do not fail or pass structural compatibility merely because the result is aesthetically preferred or disliked.

## Audit report and gate

List defects in severity order:

- **critical** — data loss, incompatible masters, corrupt or mismatched project pair;
- **high** — failed reconstruction, identity instability, reproducibility failure, or unsafe ordinary save behavior;
- **medium** — important usability, portability, performance, or visual limitation;
- **low** — documentation, naming, or minor quality issue.

Give one verdict:

- `viable`;
- `viable after specific corrections`;
- `unsuitable`.

The audit report must be written before any Phase C edits begin.

# Phase C — Bounded Corrections and Re-verification

If the audit verdict is `viable`, do not invent correction work. Proceed to the Stage 2 completion report.

If the verdict is `viable after specific corrections`:

1. fix the listed critical and high-severity defects that do not require replacing the geometry architecture;
2. add a regression test for each corrected defect;
3. rerun the full Stage 1 and Stage 2 test suite;
4. repeat the affected independent and visual audit checks;
5. publish a short correction log and final verdict.

Do not hide unresolved problems behind warnings. If a correction requires a new geometry backend, fragment model, or major rewrite, stop and return to Stage 1 with a focused proof rather than replacing the architecture inside Phase C.

If the audit verdict is `unsuitable`, do not perform production work. Report the blocking reasons and the smallest next experiment that could change the verdict.

## Stage 2 completion gate

Stage 2 succeeds only if the final audit shows:

- Stage 1 geometry and compatibility guarantees still pass;
- exactly one persistent UFO pair is created and reused;
- later glyphs can be appended without changing earlier ones;
- project reopening restores usable settings and topology;
- stale source glyphs are handled explicitly;
- ordinary paired-write failures are handled as documented;
- saved UFOs pass independent compatibility validation;
- the remaining crash-window and curve limitations are documented honestly.

## Final deliverables

Provide:

1. Phase A implementation summary and changed files;
2. project-file and topology-storage description;
3. two-UFO creation, reuse, and paired-write behavior;
4. source fingerprint and stale-glyph behavior;
5. actual test results;
6. the separate Phase B audit report;
7. the Phase C correction log and regression results, if corrections were needed;
8. remaining technical and visual limitations;
9. the final verdict;
10. a clear recommendation on whether Stage 3 may begin.

Do not create the production extension UI unless this final gate passes.
