# Stage 2 Phase C — Bounded Corrections and Re-validation

Date: 2026-07-13

## Scope

Only Prompt 2 Phase C was executed. The Stage 1 geometry and current `branching-rough-crack-mesh-v2` topology contract were retained. No RoboFont extension UI, packaging, publishing, or Prompt 3 implementation was started.

The file-backed defcon workflow remains a headless validation harness. It is not the final ownership policy: the intended extension works from the source UFO open in RoboFont, creates or updates user-owned intact and eroded RoboFont documents, permits those documents to remain open, and leaves saving to the user.

## Corrections

### Complete ordinary-exception rollback

The per-glyph commit now retains exact copies of both previous generated glyph sides, the prior topology bytes, in-memory project data, and the on-disk project record until all of these steps succeed:

1. intact glyph save;
2. eroded glyph save;
3. serialized reopen and validation;
4. topology replacement;
5. project-record save.

Any ordinary exception restores every side. This remains application-level recovery, not a claim of process-crash or power-loss atomicity.

Fault injection covers:

- failure before the eroded save;
- failure after the intact save;
- serialized reopen exception;
- serialized validation failure;
- topology replacement exception;
- failure after topology replacement;
- project-record save exception;
- failure after project-record save;
- both new-glyph and replacement rollback.

### Project format validation

`FractureProject.open()` now validates format-version-1 structure before accessing paths or fonts. The explicit validator covers required mappings and fields, output roles, primitive types, finite values, motion ranges, topology/fill/curve/component policy names, supported topology and motion versions, processed-glyph records, content digests, and save-policy types. Invalid files fail uniformly with `ProjectIntegrityError`. No schema migration system was added.

### User-owned generated glyph edit detection

Each successful glyph-pair commit stores a canonical content digest for each serialized side. The digest includes width, Unicode values, contours, point types and identities, coordinates, components, and the fragment map.

On reopen, changed generated outlines are detected without declaring the UFO forbidden to edit. The project opens and reports the affected role through `edited_outputs`; glyph status becomes `output-edited`. Motion-only regeneration and ordinary topology replacement refuse to overwrite it. Explicit topology regeneration with `replace_edited=True` is required. Phase C does not merge edited outlines.

Source-glyph fingerprints remain separate and unchanged in purpose: they detect whether the currently open source glyph has changed since its generated pair was produced. Stale source glyphs continue to preserve existing output until explicit successful regeneration.

### Safe, versioned architectural motion

Persistent project data now records `architectural-erosion-v2` independently of topology version. Processed-glyph records repeat the motion version used for their pair. The retained `fragment-affine-motion-v1` implementation exists only for reproducibility and comparison.

Version 2 implements the owner-directed visual model:

- one largest fragment is retained as a subdued structural core;
- large, medium, and small fragments have separate ordered movement multipliers;
- large fragments stay close, medium fragments move modestly, and small fragments/chips may move farther;
- downward translation is capped independently from crumble amount;
- baseline retention is a separate control;
- newly baseline-crossing fragments are capped as a proportion of the glyph, preferring small pieces when crossings are allowed;
- motion-only regeneration reuses the exact stored topology and identities.

All settings must be finite and within bounded ranges. Minimum scale is restricted to `0.5..1.0`, so linear interpolation from the intact scale of 1 cannot reach or cross zero. Objective interpolation-risk findings now make a pair incompatible and block persistent generation. Subjective `visual_warning` findings remain non-blocking.

### Licensing and repository policy

The accidental public MIT license was replaced with a private, internal-use, all-rights-reserved notice. Fracturize remains in the existing private `robofont-tools` repository; no separate Git repository was initialized or required.

The private validation UFO and its generated derivatives were marked for later removal. That cleanup is now complete; original synthetic regression data replaced them.

## Regression results

Full command:

```text
PYTHONPATH=/tmp/fracturize-deps:src python3 -m pytest -q
```

Actual result:

```text
81 passed in 5.54s
```

The 24 added tests cover complete rollback boundaries, exact project save and topology replacement failures, restoration of user-edited glyphs after failed explicit replacement, schema/policy/type/value rejection, output-edit detection and explicit replacement, unsafe/non-finite motion settings, motion-version determinism, size multipliers, structural-core and baseline bounds, and blocking interpolation risks.

## Real-font and persistent-project re-validation

The unchanged private subset was rerun through both harnesses during this historical validation.

| Measure | Result |
| --- | ---: |
| Source glyphs | 12 |
| Processed glyphs | 11 |
| Expected component rejection | 1 (`i`) |
| Processing failures | 0 |
| Incompatible glyphs | 0 |
| Source UFO unchanged | yes |
| Persistent intact glyphs | 11 |
| Persistent eroded glyphs | 11 |
| Reopen/schema/integrity check | pass |
| Motion-only topology digests preserved | yes |

The non-zero-winding overlap normalization for A, M, R, and eight remains unchanged and passes. Malformed-outline refusal remains covered.

## Independent serialized-UFO and variable-font check

`scripts/run_stage2_independent_validation.py` uses `fontTools.ufoLib.UFOReader` rather than the project reader and records results in `artifacts/stage2-phase-c-compatibility.json`.

| Measure | Result |
| --- | ---: |
| Glyphs | 11 |
| Contours | 66 |
| Points | 2,224 line points |
| Metadata mismatches | 0 |
| Structure mismatches | 0 |
| Identity mismatches | 0 |
| Winding mismatches | 0 |
| Sampled positions | 0, 10, 25, 50, 75, 90, 100 |
| Sampled self-intersections | 0 |
| Sampled zero-area contours | 0 |
| Project content-integrity reopen | pass |
| Test designspace variable-font build | pass |
| Variable axis | `EROD` |

The serialized validation inside the commit path now compares reopened output against the intended pre-save intact silhouette rather than deriving its reference from the reopened intact glyph itself.

## Motion comparison

Artifacts:

- `artifacts/motion-language-comparison.svg`;
- `artifacts/motion-language-comparison.json`.

The comparison uses identical topology for A, M, R, eight, and O at intact, 50%, and 100% states. Both motion versions remain structurally compatible.

Measured across those glyphs:

- legacy maximum downward translation: approximately 61–84 units;
- architectural maximum downward translation: 25 units;
- legacy new baseline crossings: 0–3 per glyph;
- architectural new baseline crossings: 0–1 per glyph;
- largest-fragment architectural displacement: approximately 1.1–2.8 units;
- large-fragment mean displacement remains below medium/small movement in the architectural samples.

Subjective visual review, kept separate from compatibility, finds that the new state reads as weathered separation around a stable letter skeleton rather than an explosion. Small pieces carry most of the opening. The treatment is still affine fragment motion rather than material simulation.

## Phase B finding disposition

| Phase B finding | Phase C disposition |
| --- | --- |
| High: rollback ended before full commit | corrected and fault-injected through project save |
| High: output outline edits were undetected | corrected as detectable `output-edited` state with explicit replacement |
| Medium: unsafe/unbounded motion | corrected with finite ranges, positive scale guarantee, baseline safeguards, and blocking objective risks |
| Medium: incomplete project validation | corrected with explicit version-1 validation |
| Medium: serialization-sensitive source fingerprint | intentionally retained; its sole role is conservative open-source-glyph change detection |
| Medium: explosive/slab-like motion | materially reduced by version-2 architectural motion; further taste tuning remains possible |
| Low: no separate commit/repository | superseded by owner policy: remain in the existing private repository |
| Low: fixture/public licensing ambiguity | resolved by replacing private data with original synthetic data |
| Low: serialized silhouette reference was tautological | corrected to use the intended pre-save intact silhouette |

## Remaining limitations

1. Machine termination or power failure between multiple directory-UFO writes is not crash-atomic.
2. The final live RoboFont document, dirty-state, notification, and undo integration is not implemented in the headless harness.
3. Edited generated outlines are detected but not merged into stored topology.
4. Source fingerprints deliberately remain conservative and sensitive to raw source outline changes.
5. Components remain rejected.
6. Curves remain adaptively flattened to line-only output; original cubic boundary provenance is not retained.
7. The rough crack generator still has a single-impact spiderweb bias and thin/small marks can remain low-detail.
8. Motion remains per-fragment affine translation, rotation, and scale; it is not physical erosion simulation.
9. Baseline is currently assumed to be font y=0, and size-class thresholds are fixed implementation bounds.
10. Format version 1 has no migration framework.
11. The private fixture and generated-artifact cleanup is complete.

## Decisions still needed before or during Prompt 3

1. Whether the minimal extension continues to reject components or decomposes them explicitly.
2. Where the project JSON and canonical topology live when both generated UFOs are open, user-owned RoboFont documents.
3. How RoboFont notifications, undo, document-dirty state, and unsaved external edits trigger content-integrity checks.
4. The exact UI wording and confirmation flow for replacing an `output-edited` glyph.
5. Which anchors, notes, and selected glyph/font metadata—if any—the minimal release copies.
6. Whether unprocessed glyphs are omitted or copied unchanged to both outputs.
7. Whether current single-impact topology and motion defaults are visually sufficient for the first internal UI pass.

These are Stage 3 integration/product choices and do not invalidate the Stage 2 headless architecture.

## Final verdict

**Stage 2 is viable. Prompt 3 may begin.**

The Stage 2 completion gate passes: geometry and compatibility remain intact; one persistent pair is reused; reopen and progressive addition pass; topology survives motion-only changes; source and generated-output changes are handled explicitly; ordinary-exception rollback covers the full commit; and independent serialized/designspace validation succeeds.

Prompt 3 must implement the owner-directed user-owned RoboFont document workflow rather than treating the Phase A detached-file save behavior as final product policy.
