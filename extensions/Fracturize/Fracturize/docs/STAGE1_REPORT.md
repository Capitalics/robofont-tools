# Stage 1 Completion Report

## Verdict

**Viable** as a polygonal proof of geometry reconstruction, persistent identity within serialized glyphs, and structural compatibility.

This verdict does not claim production curve quality, final fracture styling, persistent project behavior, or RoboFont extension readiness.

## Architecture

```text
src/fracturize/
    model.py       immutable source, fragment, master, and report models
    geometry.py    adaptive flattening and non-zero visible-union normalization
    core.py        seed derivation, complexity mapping, crack-mesh topology, and motion
    validation.py  reconstruction and sampled interpolation validation
    ufo.py         temporary UFO 3 write/read proof
    fixtures.py    generated geometry fixtures
    report.py      SVG visual artifact generation
tests/             geometry, generation, identity, and UFO round-trip tests
scripts/           proof report runner
artifacts/         JSON metrics and SVG visual sheet
```

The core does not import RoboFont or use live UI objects. Persistent project and accumulating-UFO behavior are intentionally absent.

## Geometry result

The source is adaptively flattened and normalized to its visible non-zero-winding union. A deterministic branching macro mesh receives a bounded rough multi-segment edge profile, is overlaid on that silhouette, and is polygonized. The intact state is rebuilt entirely from canonical fragments. The eroded state applies one bounded affine transform to the corresponding points of each fragment.

At complexity 50, all six supported fixtures passed reconstruction and compatibility validation:

| Fixture | Actual fragments | Normalized area difference | Boundary Hausdorff distance | Hard errors |
| --- | ---: | ---: | ---: | ---: |
| `H.overlap` | 8 | 0 | 1.14e-13 | 0 |
| `O.counter` | 11 | 0 | 2.84e-14 | 0 |
| `O.curve` | 7 | 0 | 6.43e-10 | 0 |
| `nested` | 10 | 0 | 5.68e-14 | 0 |
| `disconnected` | 10 | 0 | 1.14e-13 | 0 |
| `thin.counter` | 2 | 0 | 0 | 0 |

These values compare against the normalized flattened source on the declared precision grid. They do not measure deviation from original analytic curves.

## Complexity result

The `O.curve` reference fixture produced:

| Complexity | Target | Actual | Minimum fragment area | Compatible |
| ---: | ---: | ---: | ---: | --- |
| 10 | 2 | 2 | 4380 | yes |
| 25 | 4 | 4 | 3750 | yes |
| 50 | 8 | 7 | 2700 | yes |
| 75 | 13 | 12 | 1650 | yes |
| 90 | 16 | 14 | 1020 | yes |

The mapping also changes primary crack count, secondary link depth, chip count, edge irregularity, and minimum area. It is deterministic and bounded. It regenerates rather than refines topology. The exact target may not be reached where polygonized faces fall below the safety minimum; actual density remains non-decreasing in the sampled reference sequence.

## Automated validation

Command:

```bash
PYTHONPATH=/tmp/fracturize-deps:src python3 -m pytest -q
```

Actual result:

```text
57 passed in 3.06s
```

The exact run used temporary dependencies in `/tmp/fracturize-deps`; normal repository use should install `.[test]` in a virtual environment.

Coverage includes:

- deterministic and glyph-specific seeds;
- adaptive cubic flattening;
- visible union of overlapping contours;
- counters and nested islands;
- explicit component/open/empty rejection;
- complexity bundle and caps;
- deterministic topology and motion;
- fragment/contour/point identity;
- minimum fragment area and positive scale;
- sampled intermediate risks;
- temporary UFO 3 serialization and reopening;
- identity preservation after UFO round trip;
- line-only curve limitation;
- a one-second reference performance budget.

The complexity-90 `O.curve` reference remains below the declared one-second per-glyph prototype budget.

## Visual review

The automated validator does not judge style. The human-reviewed `artifacts/proof-sheet.svg` shows 0%, 50%, and 100% states.

Observations:

- all supported fixtures remain recognisable at the sampled states;
- motion has a consistent direction and reads as progressive breakup;
- some 100% states feel more separated than naturally eroded;
- the rough edge profile removes most long clean slice edges, while the macro layout retains a single-impact spiderweb bias and occasional triangular chips;
- flattened curved outlines show expected polygonal faceting under close inspection;
- density is bounded, but thin and disconnected forms need later visual tuning.

These are visual warnings. They do not change the structural compatibility result.

## Known limitations

1. Cubic curves are flattened and not reconstructed.
2. The branching fracture language is a bounded geological first pass, not final production-quality stone erosion.
3. Components are rejected rather than decomposed.
4. Self-intersecting source rings are supported only when the bounded non-zero overlap classifier proves a stable multiply-wound construction; malformed or unstable intersections remain rejected.
5. Deterministic topology is tied to the tested Shapely/GEOS stack.
6. The fixtures are synthetic and do not yet constitute a broad real-font corpus.
7. UFO writing is temporary proof serialization only; output UFO accumulation belongs to Stage 2.
8. Metadata beyond name, width, Unicode values, and identity data is outside Stage 1.

## Recommendation

The central polygonal reconstruction and compatibility model remains proven. The post-Stage-2 topology enhancement also demonstrates that the fracture language can be replaced behind the fragment contract without changing persistence, compatibility, UFO, or motion architecture. See `TOPOLOGY_GENERATOR_REPORT.md` for the current comparison and boundary-provenance findings.

## Excalibur overlap investigation

The first real-font run processed 7 glyphs, rejected component glyph `i`, and failed `A`, `M`, `R`, and `eight` because the original normalization gate rejected every self-intersecting ring.

Investigation showed that all four contain intentional same-fill overlapping path construction inside source contours:

- their non-adjacent original segments cross at stable points;
- the same face count and winding histogram persist when flattening tolerance is halved;
- non-zero winding reaches depth 2 in `R` and `eight`, and depth 3 in `A` and `M`;
- even-odd fill would remove multiply-wound black regions and change the visible silhouette;
- every resolved non-zero silhouette is valid and stable within the declared cross-tolerance bounds.

After bounded overlap normalization, the same validation run produced:

| Result | Previous | Current | Change |
| --- | ---: | ---: | ---: |
| Processed | 7 | 11 | +4 |
| Failed | 4 | 0 | -4 |
| Rejected | 1 | 1 | 0 |
| Incompatible | 0 | 0 | 0 |

All 11 processed glyphs also pass validation after the generated UFO pair is saved and reopened. The source UFO tree digest is unchanged. A synthetic ordinary bow-tie remains an explicit failure, demonstrating that the normalizer does not accept every self-intersection.

The bounded normalization is safe enough to carry into Prompt 2 for this tested non-zero-winding corpus. This does not authorize Stage 2 in the current task, and the refusal criteria must remain hard errors rather than warnings.
