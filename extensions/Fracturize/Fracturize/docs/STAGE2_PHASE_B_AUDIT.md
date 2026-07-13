# Stage 2 Phase B — Independent Read-Only Audit

Date: 2026-07-13

## Scope and audit target

This audit covers only the Stage 2 Phase B read-only review requested by `Prompt 2.md`. It reviews the completed Stage 1 proof, the Stage 2 Phase A persistent project implementation, the real-font fixture and reports, the generated UFO pair, and the current branching topology with roughened crack edges. It does not include corrections or any Prompt 3 work.

The repository has no Git commit (`HEAD` does not exist), and every current path is untracked. To make the audit target reproducible despite that limitation, the pre-audit tree was recorded as a byte-level SHA-256 manifest digest:

- audited tree: `652fcabfe897d4fffcf123c975167beb3b109b5c05911eb7226b29bb70e05216` (171 files);
- source fixture: `e0c3f0d3e0aca5433850bfd8dd6e6abcf13d267e3265ae4e7ebcdf14a1100dc6` (23 files).

The audit added only this report and independent validation artifacts. No implementation file was modified.

## Executive verdict

**Viable after bounded corrections.**

The central architecture is sound. Persistent topology, deterministic identity, motion-only regeneration, explicit topology regeneration, progressive glyph addition, real-font normalization, and serialized interpolation compatibility all work on the audited artifacts. The complete automated suite passes, and an independently constructed designspace builds a variable font successfully.

Prompt 3 should not begin yet. Two high-severity integrity gaps need bounded corrections first: ordinary exceptions after the two UFO saves can leave the pair ahead of the project record, and reopening does not detect external outline changes when the metadata remains unchanged. Motion-setting bounds and project-schema validation should also be corrected before a UI exposes these APIs.

No critical finding was observed in the current generated artifacts. The audited UFO pair is structurally compatible and builds successfully.

## Audit methods and results

### Automated and independent checks

- Full suite: **57 passed** in 3.16 seconds.
- Independent UFO reading used `fontTools.ufoLib.UFOReader`, not the project reader.
- Generated pair: 11 glyphs, 66 contours, 2,224 points.
- Pair metadata, glyph order, widths, Unicode values, contour counts, point counts, identifiers, point identifiers, winding roles, and segment types match.
- All serialized points are line points, consistently with the declared polygonal Stage 1 limitation.
- Interpolation samples at 0, 10, 25, 50, 75, 90, and 100 percent found zero self-intersections and zero zero-area contours for the generated pair.
- An independent designspace with an `EROD` axis was written to `artifacts/stage2-audit.designspace`.
- `fontmake` 3.5.1 with `ufo2ft` 2.30.0 successfully built a variable TrueType font with compatibility checking enabled. The result contains `fvar`, `gvar`, `HVAR`, and `STAT` tables and the expected 11 project glyphs plus `.notdef`.
- Machine-readable independent results are in `artifacts/stage2-audit-compatibility.json`.

### Targeted fault injection

Temporary project copies were used; the checked-in artifacts were not changed.

- Existing tests correctly roll back a failure between the intact and eroded UFO saves.
- A forced exception on the first post-save reopen left both UFOs containing the new glyph while the on-disk project record did not. Reopening then failed with `output UFO glyph set does not match project record`.
- A forced project-record save failure after UFO and topology writes produced the same mismatch and also left the new topology committed.
- Removing a segment from an intact output contour while retaining its glyph metadata was not detected by `FractureProject.open()`.
- Project files with `settings` missing or with `settings` set to a list were accepted by `open()`; failure is deferred until code accesses the settings.
- Public motion settings accepted negative minimum scales. This can create contour collapse or orientation reversal while the sampled validator can still report the pair as compatible.

## What is working

### Persistent topology and deterministic identity

Topology is serialized separately per glyph, its digest is stored in the project record and glyph libs, and fragment, contour, and point identifiers survive UFO serialization. Reopening the supplied project finds matching topology files and metadata for all 11 processed glyphs.

The current topology policy is explicitly recorded as `branching-rough-crack-mesh-v2`. Older recursive and branching-v1 policy dispatch remains explicit, so the topology generator is replaceable without changing the UFO or motion model.

### Motion-only regeneration and complexity regeneration

Motion-only regeneration reads the stored intact topology and derives transforms independently; it does not call fracture generation. Tests demonstrate an unchanged topology digest and intact master with a changed eroded master. This is a sufficiently clean separation for later direction, spread, erosion, rotation, and scale controls.

Complexity participates in deterministic seed derivation and changes the topology only after explicit topology regeneration. Until then, glyph status becomes `topology-outdated`. This is the correct safety boundary. Complexity is not a nested refinement control, and existing documentation states that limitation.

### Reopen and progressive addition

The project owns one intact UFO and one eroded UFO, reopens them from disk for each operation, preserves prior glyphs, and progressively adds new glyphs. Duplicate processing and implicit replacement are refused. The outputs are kept closed outside operations as declared.

### Real-font normalization

The real-font policy is bounded and appropriate for the current polygonal proof:

- components are explicitly rejected;
- cubic outlines are adaptively flattened using the declared tolerance;
- visible fill is normalized using the **non-zero winding fill rule** before Shapely fracture processing;
- legitimate overlap constructions in A, M, R, and eight are resolved;
- genuinely malformed self-intersecting outlines are rejected rather than silently repaired;
- the source UFO tree digest is unchanged.

The real-font run reports 11 processed glyphs, one expected component rejection, no processing failures, and no compatibility failures.

### Updated fracture language

The current implementation separates macro crack layout from micro edge profile. Primary cracks, secondary branches, and chips retain a deterministic graph, while long spans are subdivided and laterally perturbed with bounded shoulders and notches. Tests cover determinism, endpoint and junction preservation, minimum segment length, simple crack lines, coverage, and compatibility.

Subjective visual review confirms a material improvement over clean cuts: rough edges read as angular broken material while preserving broad crack direction. This is a visual assessment, separate from automated compatibility results.

## Severity-ranked findings

### High — rollback does not cover the complete ordinary-exception commit path

`_write_pair()` retains backups only through the two UFO saves. Its reopen calls occur outside the guarded save block. `_commit_result()` then replaces the topology candidate and saves the project record, but its exception handler only removes an uncommitted candidate.

Consequently, an ordinary post-save read/validation exception, topology replacement exception, or project-record save exception can leave both UFOs and possibly the topology ahead of the project JSON. This was reproduced, and the resulting project refuses to reopen. This is not the explicitly deferred crash-proof transaction problem; it is an ordinary-exception rollback gap within the implementation's stated guarantee.

Bounded correction:

- retain pair and previous-topology backups until post-save validation and project-record save both succeed;
- restore both UFO glyphs, the prior topology file, and in-memory project data on every ordinary exception in that interval;
- add fault-injection tests for post-save reading, serialized validation, topology replacement, and project `_save()` failures.

### High — integrity checks trust metadata and do not detect changed output outlines

`validate_integrity()` verifies project/role identifiers, glyph sets, topology file digests, pair revisions, source fingerprints, and topology references. It does not digest or structurally compare the actual serialized outlines. An externally altered intact glyph therefore passed reopening as long as its metadata remained present.

This allows a mismatched pair to be treated as healthy and weakens persistent topology ownership. For the minimal closed-output product, the bounded solution is to store and verify a canonical serialized-content digest for each side of every glyph. A mismatch should hard-stop with a clear external-edit error.

Supporting editable generated masters would require a much larger conflict/merge policy and is not recommended for the first release.

### Medium — motion controls accept unsafe values and validation samples can miss collapse

`GenerationSettings` has no invariant checks, and `set_motion_settings()` validates names but not values. Negative scale targets and extreme erosion/rotation values are accepted. The validator checks only seven positions, labels near-zero area as `interpolation_risk`, and defines `compatible` solely by absence of `hard_error`. A scale crossing between samples can therefore be missed entirely.

Bounded correction:

- validate finite values and safe ranges at the settings-model/project API boundary;
- analytically reject any scale interpolation that reaches or crosses zero;
- define whether any interpolation-risk finding blocks a persistent write or is an explicit warning requiring user acknowledgement;
- test boundary values independently from future UI widgets.

The default Stage 2 settings are safe in the independent sample and build checks.

### Medium — project schema and policy are not fully validated on open

`open()` checks only the top-level format/version before calling integrity checks. Missing or wrongly typed `settings` were accepted. Required nested keys, value types and ranges, output roles/paths, and supported topology policy should be validated immediately and reported uniformly as `ProjectIntegrityError`.

This does not require migrations or a general schema framework. A small explicit version-1 validator is sufficient.

### Medium — source fingerprinting is serialization-sensitive

The source fingerprint is based on ordered raw contour/segment data. Harmless contour start-point rotation or ordering changes can therefore mark a glyph stale even when the normalized visible silhouette and all generation inputs are unchanged. The generator operates on normalized flattened geometry, so a canonical generation-input fingerprint would better match actual staleness.

This is a false-positive/reprocessing issue rather than a compatibility risk. The owner should decide whether conservative raw-outline detection is preferred for the first release.

### Medium — current fracture language still has bounded visual limitations

Subjectively, the roughened topology is fit for continued development, but it still has a pronounced single-impact/spiderweb bias. At maximum erosion some glyphs read as separated slabs rather than eroded rock. Very small or thin regions, especially the dot accent, receive little visible fracture detail, while a few long macro cuts remain visually dominant in R and eight.

These are not automated compatibility failures and should not be mixed with them. They are owner-directed art decisions: accept this as the minimal first-release language, or allocate a bounded visual-tuning correction before UI work.

### Low — audit target and fixture provenance are not release-ready

There is no commit to identify, and the entire tree is untracked. The digest above makes this audit identifiable, but corrections and Prompt 3 should start from an initial commit or tag. Generated caches and `.DS_Store` files also need normal repository hygiene.

The then-current external fixture had no documented redistribution license. This finding is resolved: it was removed and replaced by original synthetic regression data.

### Low — serialized reconstruction validation uses the reopened intact master as its source

The post-save check constructs `source_silhouette` from the reopened intact master itself. It can verify pair structure and interpolation but cannot independently prove that serialization preserved the intended intact silhouette. Current independent checks found no serialization damage, so this is not a present artifact failure. The implementation check should nevertheless compare against the pre-save normalized source or stored topology geometry during the bounded integrity correction.

## Visual review, kept separate from compatibility

Automated verdict:

- deterministic topology: pass;
- full silhouette coverage within declared tolerance: pass;
- complementary neighbouring edges: pass;
- serialized point compatibility: pass;
- sampled interpolation safety on the generated real-font pair: pass;
- independent variable-font build: pass.

Subjective verdict:

- roughening is clearly more geological than the clean macro layout;
- broad direction, crack junctions, counters, and glyph recognition remain legible;
- the visual vocabulary is still angular and slab-like rather than deeply eroded;
- single-center branching and sparse treatment of small islands remain noticeable.

## Motion/topology separation verdict

The architecture is sufficiently separated for later minimal UI controls. Topology owns normalized fragments, stable identities, compatible contour/point structures, and transform origins. Motion owns only deterministic translation, rotation, and scale derived per fragment. Stored topology can be reused without regenerating crack geometry.

Before UI work, the motion layer needs value constraints and a clear write-blocking policy for interpolation risks. A motion-algorithm version should also be considered if exact regeneration across future code releases is a product requirement; topology versioning alone does not freeze future transform behavior.

## Required corrections before Prompt 3

1. Extend ordinary-exception rollback through serialized reopen/validation, topology commit, and project-record commit.
2. Add canonical output-content integrity digests and reject externally edited generated outlines on reopen.
3. Add explicit version-1 project schema, policy, type, and setting-range validation.
4. Constrain motion values and guarantee that scale cannot collapse or reverse anywhere on the axis.
5. Add regression tests for all of the above, then repeat the independent UFO/designspace build check.

The source-fingerprint canonicalization and visual tuning can remain owner-scoped decisions, provided their current limitations are documented.

## Owner decisions required

1. **Output ownership:** keep generated UFOs strictly project-owned and reject any external outline edit (recommended for the first release), or design a broader editable-output conflict policy.
2. **Motion safety policy:** choose permitted ranges and whether any interpolation-risk result blocks writing or is an acknowledged warning. Zero/negative scale should always be rejected.
3. **Visual threshold:** accept the current single-impact, angular rock language for the minimal extension, or request one bounded tuning pass before Prompt 3.
4. **Source-change semantics:** retain conservative raw-outline fingerprints or canonicalize fingerprints to the normalized generation input.
5. **Reproducibility:** create an initial commit/tag before corrections and Prompt 3.
6. **Fixture licensing:** resolved by replacing the private subset with an original synthetic fixture.
7. **Motion versioning:** decide whether future motion regeneration must reproduce transforms from older application versions exactly.

## Final recommendation

Proceed to the bounded Stage 2 corrections phase only after the owner decisions above that affect correction behavior. Do not begin Prompt 3 yet. The implementation is not unsuitable and does not need architectural replacement; its geometry, topology persistence, and interpolation model have passed the central proof. The remaining blockers are contained integrity and input-policy defects plus explicit product choices.
