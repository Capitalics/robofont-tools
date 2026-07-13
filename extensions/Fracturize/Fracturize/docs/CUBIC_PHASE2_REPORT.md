# Cubic exterior preservation — Phase 2 report

## Verdict

The one-glyph hybrid reconstruction is viable for the bounded regression `O` case. Five fragments are reconstructed from the existing clean Fracturize macro topology. Every source-silhouette interval is an exact cubic parameter range; every internal fracture interval is generated line geometry.

This is still a development proof. Production generation, models, serialization, UFO writing, project persistence, motion, batching, components, project workflows, and UI were not changed. Phase 3 has not started.

## Reconstruction method

1. Generate the existing deterministic clean macro crack mesh and canonical polygon faces.
2. Extract every pairwise shared face boundary once. These become canonical internal polyline edges.
3. Classify the remaining face boundary as source exterior by mapping it to the original source contours.
4. Intersect macro crack segments with the original cubic segments using the Phase 1 parameter-refinement method.
5. Retain only intersections that terminate an actual shared face edge; discarded/merged crack candidates do not add source points.
6. Split original cubics with exact de Casteljau subdivision and store each piece's source contour, segment, and `[t0, t1]` range.
7. Assign each exact exterior piece to its adjacent canonical face.
8. Snap only shared-edge endpoints to the exact split nodes, then assemble closed face cycles. Exterior pieces may never reverse; this preserves source contour direction.
9. Store each internal edge once and use the same identified line segments in exact reverse order for the neighbouring face.
10. Apply the existing guide fragment's affine motion to on-curve points and cubic controls. Intact and eroded structures therefore remain identical.

## Regression `O` result

Settings: project seed `cubic-phase2`, Fracture Complexity `30`, clean macro edge profile.

| Measurement | Result |
| --- | ---: |
| Macro crack polylines | 7 |
| Hybrid fragments | 5 |
| Logical shared internal edges | 6 |
| Unique internal line segments | 12 |
| Internal line-segment instances | 24 (two complementary uses each) |
| Preserved exact cubic intervals | 16 |
| New exterior intersection nodes | 8 |
| Additional exterior approximation nodes | 0 |
| Preserved counters | 1 |
| Normalized sampled silhouette difference | 4.2990e-7 |
| Sampled boundary Hausdorff distance | 0.000111908 units |
| Structural compatibility | pass |
| Sampled interpolation at 0/25/50/75/100% | pass |
| Source UFO unchanged | yes |

The measurement limits are `1e-6` normalized symmetric difference and `0.001` font units Hausdorff distance. Polygonal sampling is used only to measure the result. Stored hybrid exterior geometry remains cubic.

Every one of the eight original `O` source cubics is covered continuously from `t=0` through `t=1`. The 16 stored pieces arise only from the eight actual fracture intersections. No flattened source-boundary vertices appear in the hybrid contours.

## Visual comparison

The comparison shows:

1. original cubic source;
2. the current line-only macro result;
3. hybrid intact fragments;
4. direct compatible interpolation at 50%;
5. hybrid eroded fragments.

Generated artifacts:

- `artifacts/cubic-phase2-comparison.svg`;
- `artifacts/cubic-phase2-comparison.json`.

The hybrid SVG uses cubic `C` commands for exterior source intervals. Line `L` commands represent only canonical internal fracture segments.

## Focused tests

```text
tests/test_cubic_phase2.py: 5 passed
```

The tests cover multiple cracks and fragments, macro fragment/motion identity, exterior/internal classification, exact source parameter coverage, introduced-node accounting, complementary shared edges, closed valid contours, counter reconstruction, silhouette error, intact/eroded structural compatibility, and sampled interpolation validity.

## Files added

- `test_support/hybrid_reconstruction.py` — development-only hybrid face reconstruction;
- `tests/test_cubic_phase2.py` — focused Phase 2 tests;
- `scripts/run_cubic_phase2_proof.py` — numerical and visual comparison harness;
- `docs/CUBIC_PHASE2_REPORT.md` — this report.

## Unsupported cases and ambiguities

- components;
- overlapping or self-intersecting source contours;
- tangent or collinear crack/source intersections;
- source line segments that require a new intersection split;
- arbitrary nested contour arrangements beyond the tested single counter;
- macro face graphs whose endpoint matching is ambiguous after polygon merging;
- production topology persistence and UFO curve serialization.

The current face-cycle assembler deliberately fails on ambiguity rather than falling back to polygonal exterior output. These cases need explicit Phase 3 support or rejection policies before production integration.
