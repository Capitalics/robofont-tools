# Fracturize architecture

The live extension follows one main dependency direction:

```text
extension entry point → UI → controller → live project
                                      ↓
                         generation / topology / movement
                                      ↓
                         validation and live UFO writing
```

## Runtime boundaries

- `extension.py` owns the singleton panel lifecycle.
- `ui.py` owns Vanilla controls, dialogs, preview widgets, progress display, and RoboFont event observers. It resolves no geometry itself.
- `controller.py` translates UI actions into batch selection, settings changes, project operations, previews, and processing calls. It contains no RoboFont widgets.
- `robofont_adapter.py` is the narrow application boundary for current/open fonts, glyph selection, document opening, and preview-glyph conversion.
- `live_project.py` owns the version-1 project record, open-font binding, shared-data integrity, fingerprints, staleness, rollback, and paired live-glyph commits.
- `core.py` owns deterministic topology and movement orchestration. `geometry.py` owns flattening, non-zero-winding normalization, canonical rings, and interpolation geometry. `validation.py` owns reconstruction and compatibility checks.
- `topology.py` serializes the persistent per-glyph topology used by motion-only regeneration.
- `input_ufo.py` converts defcon glyphs into the geometry model. `ufo.py` contains the low-level master drawing/readback helpers used by validation and the historical headless harness.
- `model.py` contains immutable data exchanged across those boundaries. `fingerprints.py` contains canonical source/output digest helpers shared by the live and headless project layers.

## Development-only boundaries

- `test_support/` contains synthetic in-memory fixtures and report formatting. It is deliberately outside the extension bundle.
- `tests/fixtures/FracturizeRegression.ufo` is original synthetic regression data. Rebuild it with `scripts/build_regression_fixture.py`.
- `scripts/` contains reproducible proof, comparison, and validation commands. Their output goes to ignored `artifacts/`.
- `project.py` remains in the bundle only as the retained Stage 2 file-backed harness used by regression tests and proof scripts. The RoboFont extension does not use it for live project operations.

## Invariants worth preserving

- The source font is never modified.
- Both output glyph sides commit before project state advances; ordinary exceptions restore both sides, topology, and record state.
- Topology-changing settings never take the motion-only path.
- Working-font integrity compares meaningful shared data while excluding only explicitly documented volatile application metadata.
- Geometry and motion code remain independent of RoboFont and Vanilla.
- Generated artifacts and private font data do not belong in the extension bundle or source history.

Large reorganizations of `core.py`, `live_project.py`, or the historical `project.py` should wait until cubic-exterior work establishes the next geometry contract. Their current boundaries are more valuable than a cosmetic module split.
