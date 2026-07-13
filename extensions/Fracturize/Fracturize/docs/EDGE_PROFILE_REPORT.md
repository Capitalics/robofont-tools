# Rough Crack-Edge Profile Report

## Scope and verdict

The crack-edge geometry was improved without changing compatibility, UFO writing, project persistence, stored topology, or motion architecture. The Prompt 2 read-only audit was not started.

The default `branching-rough-crack-mesh-v2` generator separates:

- **macro layout** — impact hub, primary directions, secondary links, chips, and shared graph junctions;
- **micro edge profile** — short non-uniform subdivisions, lateral deviations, sharp shoulders, and sparse local notch/rebound events.

Both clean and rough comparisons use the same macro mesh. A single rough polyline is noded once and therefore becomes the shared boundary of both neighbouring fragments; opposite sides are exactly complementary rather than separately randomized.

## Bounded profile

The public `EdgeProfileParameters` bundle exposes all requested controls. At the comparison setting of complexity 72 and 1000 UPM:

| Parameter | Value |
| --- | ---: |
| Edge subdivision density | 32.08 segments/em |
| Lateral deviation amplitude | 11.76 units |
| Segment-length variation | 0.4264 |
| Sharp-corner probability | 0.1348 |
| Local-notch probability | 0.0646 |
| Simplification threshold | 0.606 units |
| Minimum segment length | 7 units |

Complexity changes density from 22 to 36 segments/em and deviation amplitude from 6 to 14 units at 1000 UPM. Other probabilities rise gently but remain below 0.2. This bounds high-complexity detail rather than allowing unlimited micro-noise.

Subdivision distances are randomized within the segment-length bound. Lateral offsets combine independent and partially correlated changes, so they do not alternate mechanically. Sharp events produce occasional shoulders; notch events produce a short displacement followed by a partial rebound. The result is angular and non-periodic rather than a sine wave or uniform zigzag.

## Mesh safeguards

The profiler preserves macro endpoints and shared secondary anchors verbatim. Every candidate line must:

1. remain a simple, non-self-intersecting polyline;
2. preserve the macro mesh's semantic line-intersection graph;
3. satisfy the declared minimum generated segment length; and
4. node and report every resulting exterior or counter-boundary crossing.

Whole-mesh deviation is reduced deterministically when a candidate changes the macro intersection graph. The clean macro mesh is the bounded final fallback. A rough path may meet a concave glyph boundary more often than its clean macro path; those additional intersections become necessary shared fragment nodes. Polygonization then uses the existing coverage check and reconstruction tolerances. Fragment ordering, identifier derivation, matched point construction, affine motion, interpolation checks, and UFO serialization are unchanged. New v2 geometry intentionally produces new fragment IDs through the existing topology-versioned identity mechanism.

Projects recording `recursive-split-v1` or `branching-crack-mesh-v1` continue to dispatch to those generators. Existing stored canonical topology remains independent of generator execution.

## Same-layout comparison

The Excalibur sample used one project seed and complexity 72. Every sampled clean and rough pair passed structural compatibility. All rough lines were simple and all semantic intersection graphs matched their clean macro graph.

| Glyph | Clean segments | Rough segments | Clean median length | Rough median length | Clean fragments | Rough fragments |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `O` | 42 | 380 | 246.1 | 33.9 | 11 | 11 |
| `A` | 42 | 375 | 252.6 | 32.7 | 8 | 9 |
| `S` | 34 | 242 | 215.1 | 33.2 | 8 | 8 |
| `R` | 42 | 304 | 234.1 | 34.0 | 11 | 11 |
| `M` | 61 | 653 | 269.9 | 33.9 | 14 | 13 |
| `eight` | 42 | 316 | 238.9 | 31.7 | 11 | 11 |

The broad line graph is identical. Small fragment-count differences in `A` and `M` occur after polygonization because rough geometry changes which small cells fall below the existing minimum-area merge threshold; it does not introduce a different macro crack plan.

The visual artifact `artifacts/edge-profile-comparison.svg` shows clean and rough intact, 50%, and eroded states. Visual evaluation is separate from the automated verdict. The rough version replaces long cut-like edges with many short angular facets and reads substantially closer to broken stone. It preserves the dominant crack direction. Some shoulders remain visually strong at complexity 72, and the underlying single-impact spiderweb bias remains a separate macro-layout choice.

## Outer-boundary points

Counts below describe final rough fragments, after minimum-area merging:

| Glyph | Necessary crack/boundary nodes | Existing flattened boundary vertices | Clipping-only nodes |
| --- | ---: | ---: | ---: |
| `O` | 27 | 174 | 0 |
| `A` | 24 | 81 | 3 |
| `S` | 23 | 170 | 0 |
| `R` | 24 | 142 | 0 |
| `M` | 35 | 109 | 0 |
| `eight` | 22 | 229 | 0 |

- Necessary nodes are actual surviving crack intersections with an exterior or counter boundary. They must appear in both masters to close the corresponding complementary fragments. Relative to the clean layout, roughening adds four such nodes in `O`, one in `A`, two in `S`, and six in `M`; `R` and `eight` are unchanged.
- Existing vertices come from the normalized adaptively flattened silhouette and are not introduced by fracture roughening.
- Clipping-only nodes match neither a surviving crack intersection nor a baseline flattened vertex. Three conservative unmatched nodes remain in `A`; they are polygon noding residue, not semantic crack junctions.

Full coordinates for each category are recorded in `artifacts/edge-profile-comparison.json`.

## Remaining owner decisions

1. Whether the current 22–36 segments/em density is appropriately monumental or should use slightly larger facets.
2. Whether the maximum 14-unit lateral amplitude and current shoulder frequency are strong enough, especially at intermediate states.
3. Whether `A` and `M` should retain minimum-area merging exactly as now or prioritize identical clean/rough fragment counts for comparisons.
4. Whether multiple impact hubs should later alter the macro layout; this is intentionally outside the edge-profile change.
5. Whether future curve-aware exterior preservation justifies source-curve provenance work.
