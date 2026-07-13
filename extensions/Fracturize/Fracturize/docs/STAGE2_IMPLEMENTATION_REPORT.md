# Stage 2 Phase A Implementation Report

> Phase C supersession: Phase A's detached-file lifecycle remains only a headless validation harness. The intended production outputs are user-owned RoboFont documents that may remain open and are saved by the user. Phase C adds generated-outline edit detection, complete ordinary-exception rollback, schema validation, safe versioned architectural motion, and independent re-validation. See `STAGE2_PHASE_C_CORRECTIONS.md`.

## Scope and status

Only Prompt 2 Phase A was executed. The independent Phase B audit, Phase C corrections, and Prompt 3 were not started.

Stage 1's geometry, non-zero fill normalization, fragment identity, Fracture Complexity, and validation policies remain the technical basis.

Before the independent audit, the fracture generator was replaced behind its existing polygon-fragment contract, first by `branching-crack-mesh-v1` and then by the rough-edged `branching-rough-crack-mesh-v2`. This did not alter project format, paired-UFO ownership, stored canonical topology, motion-only regeneration, or reopen/integrity behavior. Existing projects dispatch through their recorded topology version. See `TOPOLOGY_GENERATOR_REPORT.md` and `EDGE_PROFILE_REPORT.md`.

## Implemented architecture

New implementation modules:

- `src/fracturize/project.py` — project creation/opening, fingerprints, status, regeneration, integrity checks, and paired writes;
- `src/fracturize/topology.py` — versioned canonical topology JSON serialization;
- `scripts/run_project_proof.py` — real-font create/reopen/append/regenerate demonstration;
- `tests/test_project.py` — Phase A persistence and failure tests.

Existing modules were extended to support motion-only regeneration, replacement of generated glyphs, and conversion of saved defcon glyphs back into the shared master model.

No extension bundle, menu registration, preferences, production UI, schema migration framework, crash journal, designspace export, or Glyphs automation was added.

## Persistent project behavior

Project creation explicitly creates:

- one JSON project record;
- one empty intact UFO;
- one empty eroded UFO.

The UFO paths never depend on a glyph name. Later glyphs are appended to the same two packages. The Phase A harness opens detached defcon objects only for each operation; this is not a final output-ownership rule.

Canonical topology is stored separately per glyph. Motion-only regeneration reuses it without rerunning fracture splitting. Changing Fracture Complexity marks previous topology as outdated and requires an explicit topology-regeneration action.

See `PROJECT_FORMAT.md` for the schema, allowlists, fingerprint, ownership, and saving details.

## Real-font demonstration

The historical generated demonstration used an unchanged private font subset. That fixture and its generated artifacts have since been removed and replaced by `tests/fixtures/FracturizeRegression.ufo`.

Workflow executed:

1. create the project and both output UFOs;
2. process `O`;
3. close the project controller;
4. reopen from JSON;
5. append every other supported source glyph to the same paths;
6. update shared motion settings;
7. regenerate motion for all processed glyphs from stored topology;
8. reopen and run project integrity validation.

Results:

| Measure | Result |
| --- | ---: |
| Source glyphs | 12 |
| Processed glyphs | 11 |
| Explicit component rejections | 1 (`i`) |
| Intact UFO glyphs | 11 |
| Eroded UFO glyphs | 11 |
| Matching glyph sets | yes |
| Same paths after reopen | yes |
| All topology digests preserved during motion-only regeneration | yes |
| Motion changed for every processed glyph | yes |
| Final integrity reopen | passed |
| Source tree digest unchanged | yes |

Generated artifacts:

- `artifacts/stage2-implementation-report.json`;
- a `.fracturize.json` project record;
- an intact working UFO;
- an eroded working UFO;
- eleven canonical topology JSON records under `project-data/topology/`.

## Automated tests

Command:

```bash
PYTHONPATH=/tmp/fracturize-deps:src python3 -m pytest -q
```

Actual result:

```text
57 passed in 3.06s
```

Phase A coverage includes:

- project creation and JSON validation;
- creation of exactly one identified output pair;
- output-path conflict refusal;
- close/reopen and subsequent glyph additions;
- preservation of earlier generated glyphs;
- explicit replacement requirements;
- stored topology round trip;
- motion-only regeneration with unchanged topology;
- topology-outdated status and explicit complexity regeneration;
- canonical source fingerprinting and stale status;
- preservation of old output until stale replacement succeeds;
- failure of stale regeneration preserving the old pair;
- explicit component rejection;
- rollback after an injected failure following the intact save;
- rollback of a failed motion replacement;
- project record not advancing after failure;
- missing, mismatched, and orphan output detection;
- metadata allowlists and omission of kerning, groups, and features;
- serialized output reopening and compatibility validation.

The failure-injection tests prove ordinary exception recovery. They do not prove machine-crash recovery.

## Known limitations

1. Saving two directory UFOs plus project data is not crash-atomic.
2. External outline edits are detected but are not merged; explicit regeneration is required before replacement.
3. Project relocation and source relinking are deferred.
4. Format version 1 has no migration framework.
5. Components remain unsupported.
6. Anchors, notes, hints, guidelines, kerning, groups, features, and arbitrary lib data are omitted.
7. Curves remain polygonally flattened.
8. The branching generator is a stronger geological first pass but still has a single-impact spiderweb bias and is not a final production style.
9. Only the current Python/defcon/Shapely environment is claimed.

## Owner decisions before later product work

The following choices require product-owner input; Phase A does not assume them:

1. **Components:** continue rejecting them, or explicitly decompose them into generated output.
2. **Output ownership (resolved in Phase C):** final output UFOs are user-owned RoboFont documents and may remain open; the headless harness remains file-backed for tests.
3. **Glyph metadata:** whether anchors, notes, selected lib keys, guidelines, or hints should be copied, transformed, or omitted.
4. **Font data:** whether later releases should copy kerning, groups, and features, or generate a separate handoff source.
5. **Crash recovery:** whether real use justifies a journal/backup recovery protocol beyond current ordinary exception rollback.
6. **Portability:** whether Stage 3 must support source relinking and moved project folders in its first release.
7. **Incomplete glyph sets:** whether unprocessed source glyphs should be omitted, copied unchanged to both outputs, or handled through designspace exclusions.
8. **External-edit conflicts:** whether an edited generated glyph should hard-fail, be replaceable with confirmation, or be importable as a new topology baseline.

## Stop point

Phase A implementation is complete under its declared limitations. No independent audit verdict is offered here. Prompt 2 Phase B must be a separate read-only activity if authorized later.
