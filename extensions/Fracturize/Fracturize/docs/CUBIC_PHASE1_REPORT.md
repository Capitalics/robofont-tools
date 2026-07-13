# Cubic exterior preservation — Phase 1 report

## Verdict

The intersection-and-splitting method is viable. A flattened curve is used only to locate candidate intervals. Each candidate is refined against the original cubic Bézier equation, recorded as its original contour-segment index and parameter `t`, and split with exact de Casteljau subdivision. No production generator, project, UI, motion, batch, component, or UFO-writing code changed.

Phase 2 has not started.

## Method

1. Recursively flatten one cubic into parameter-tagged proxy chords.
2. Intersect the finite fracture segment with those chords to obtain candidate parameter brackets.
3. Refine the root of the signed line/cubic crossing function with bounded Newton and bisection steps evaluated on the original Bézier.
4. Sort and deduplicate intersections by original `t`.
5. For multiple splits, convert each original `t` to the remaining piece's local parameter and apply de Casteljau subdivision.
6. Keep the resulting `CubicSegment` pieces in original contour order.

The declared intersection and exact-curve reconstruction tolerance is `1e-10` font units.

## Synthetic proof

The focused proof includes a single cubic crossed twice by one horizontal line. Both intersections are recovered in increasing parameter order on the same original segment. The proxy parameters differ measurably from the refined parameters, confirming that the flattened chords are not treated as authoritative intersections.

All split pieces remain cubic. A known half-parameter example produces the analytically expected control points. Sampling 1,001 positions over the original parameter domain confirms that recomposed pieces reproduce the original curve within the declared tolerance. Closed-contour sampling confirms that source direction and continuity are preserved.

## Regression `O` demonstration

The original synthetic regression `O` has four cubic segments on its exterior and four on its counter. A horizontal proof fracture at `y=420` produces four refined curve intersections:

| Contour | Segment | `t` | Refined point | Line error |
| --- | ---: | ---: | --- | ---: |
| exterior | 0 | 0.1240178509 | (638.9989131, 420) | 5.68e-14 |
| exterior | 1 | 0.8759821491 | (51.0010869, 420) | 0 |
| counter | 2 | 0.2063920368 | (198.4006912, 420) | 5.68e-14 |
| counter | 3 | 0.7936079632 | (491.5993088, 420) | 0 |

The standalone demonstration assembles two proof fragments from exact exterior/counter arcs and two generated internal fracture intervals. It is not connected to the production topology generator.

- Original source exterior/counter: 8 cubic segments.
- Hybrid proof exterior/counter: 12 exact cubic pieces.
- New exterior nodes: exactly 4, all corresponding to fracture intersections.
- Additional exterior approximation nodes: 0.
- Unique generated internal fracture edges: 2, each reused in reverse by its neighbour.
- Current polygonal Fracturize comparison: 217 line points.
- Maximum exact curve reconstruction error: `4.8567e-13` font units.
- Sampled normalized silhouette difference: `2.2222e-7` (limit `1e-6`).
- Sampled boundary Hausdorff distance: `0.000111925` font units (limit `0.001`).
- Source fixture changed: no.

The SVG path for the new exterior uses cubic `C` commands exclusively; only the two complementary internal cuts use line `L` commands. The outer silhouette therefore does not contain the dense polygonal approximation visible in the current result.

Generated comparison files:

- `artifacts/cubic-phase1-comparison.svg`;
- `artifacts/cubic-phase1-comparison.json`.

## Focused tests

```text
tests/test_cubic_phase1.py: 5 passed
```

Coverage includes exact control points, two intersections on one cubic, refined-versus-proxy parameters, multiple ordered splits, reconstruction error, source direction/continuity, regression-`O` segment provenance, and the exact count of introduced exterior points.

## Files added

- `test_support/cubic_intersections.py` — development-only intersection and exact subdivision utilities;
- `tests/test_cubic_phase1.py` — focused Phase 1 tests;
- `scripts/run_cubic_phase1_proof.py` — regression-`O` comparison and measurements;
- `docs/CUBIC_PHASE1_REPORT.md` — this report.

## Known limitations

- The proof handles transverse intersections with one finite straight fracture segment. Tangencies, collinear overlap, and crack polylines need explicit policies later.
- The regression-`O` hybrid assembly is deliberately specialized to a simple two-intersection horizontal cut. It is not the general face-cycle reconstruction required by Phase 2.
- Mixed line/cubic source contours are retained by the splitting helper, but Phase 1 only creates new splits on cubic source segments.
- The silhouette measurements use dense polygonal sampling only for numerical comparison; the stored and rendered exterior segments remain exact cubics.
- Multiple contours with nesting beyond one counter, overlaps, self-intersections, and components are outside this phase.
