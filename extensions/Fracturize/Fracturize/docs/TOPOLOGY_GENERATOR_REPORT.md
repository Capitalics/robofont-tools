# Branching Topology Generator Report

## Scope and stop point

This is a pre-audit implementation review. The Prompt 2 independent audit and Prompt 3 were not started. Persistent project ownership, canonical topology storage, paired-UFO writing, master compatibility, motion, and reopen validation retain their existing contracts.

## Replaceability verdict

The recursive splitter was cleanly replaceable. `generate_pair()` consumes an ordered collection of valid polygon fragments and does not depend on how those polygons were formed. Canonical contour construction, fragment and point identifiers, affine motion, compatibility validation, topology serialization, project persistence, and UFO writing all remain downstream.

The former generator is retained as `generate_recursive_topology()` for regression and visual comparison only. This report originally introduced `branching-crack-mesh-v1`. The current default is now `branching-rough-crack-mesh-v2`, which retains the branching macro layout and adds a separate irregular edge-profile pass. This intentionally gives newly generated fragments new identifiers while leaving the identity mechanism unchanged. Already persisted canonical topology remains readable and motion-regenerable without calling either generator, and projects recording v1 continue to generate with v1.

See `EDGE_PROFILE_REPORT.md` for the clean-macro versus rough-edge comparison, parameter bounds, and updated boundary-point measurements.

## Implemented fracture language

The bounded alternative:

1. derives the same deterministic per-glyph effective seed;
2. allocates complexity across disconnected silhouette components;
3. places a slightly offset visual impact hub near each component's bounds center, including inside a counter when that gives better whole-glyph coverage;
4. emits wandering multi-segment primary cracks with varied direction and length;
5. adds irregular secondary links between neighbouring primary cracks;
6. adds a bounded number of short boundary-to-boundary local chip branches;
7. nodes the crack mesh together with every exterior and counter boundary of the normalized silhouette;
8. polygonizes the linework and selects only faces covered by the silhouette;
9. deterministically merges undersized or surplus adjacent faces; and
10. hard-fails if the fragment union differs from the normalized silhouette beyond the existing measured area bound.

This is not Voronoi generation and no global recursive slices are used by the default. Complexity remains a deterministic 0–100 bundle controlling target density, minimum area, primary count, secondary depth, irregularity, and chip count. Thin forms can saturate below the requested target because minimum-area safety takes precedence over an exact fragment count.

## Real-font comparison

The historical private subset was sampled at complexity 72 with one common comparison seed. It has since been removed; the retained synthetic regression UFO exercises the same overlap, curve, counter, component, and persistence paths.

| Glyph | Recursive fragments | Branching fragments | New compatibility |
| --- | ---: | ---: | --- |
| `R` | 12 | 10 | pass |
| `O` | 11 | 11 | pass |
| `eight` | 11 | 11 | pass |
| `M` | 16 | 16 | pass |
| `S` | 8 | 7 | pass |
| `A` | 10 | 9 | pass |

The side-by-side artifact is `artifacts/topology-language-comparison.svg`; machine-readable geometry and boundary measurements are in `artifacts/topology-language-comparison.json`.

Visual evaluation is deliberately separate from the automated verdict. The branching result has visibly more angular variation, local branching, clustered chips, and impact-centered relationships than the recursive result. It no longer reads primarily as a sequence of unrelated full-width slices. It still has a noticeable single-impact spiderweb bias, and some local branches produce triangular chips. This is a stronger geological starting language, not a claim of final production styling.

## Outer-boundary point insertion

The comparison harness classifies unique fragment vertices on all normalized filled-silhouette boundaries, including counter boundaries.

| Glyph | Required crack/boundary nodes | Existing flattened boundary vertices | Unmatched clipping/noding points |
| --- | ---: | ---: | ---: |
| `R` | 31 | 142 | 0 |
| `O` | 22 | 174 | 3 |
| `eight` | 29 | 229 | 2 |
| `M` | 31 | 109 | 3 |
| `S` | 16 | 170 | 0 |
| `A` | 18 | 81 | 4 |

- Required nodes are points where generated crack linework meets an exterior or counter boundary. They must be inserted so adjacent fragments close at the same location, and the corresponding point must exist in both masters.
- Existing flattened boundary vertices come from adaptive cubic flattening or source polygon corners. They are necessary only for the current polygonal approximation; the fracture operation did not introduce them.
- Unmatched points are conservative clipping/noding artifacts: final boundary vertices that match neither a measured crack intersection nor an original flattened vertex within the declared classifier tolerance. They are retained by the polygonal proof but are not semantically required crack junctions.

Untouched exterior intervals can later preserve original cubic geometry in principle. Doing that safely requires provenance from normalized boundary intervals back to source contour and cubic parameters, followed by curve splitting only at true crack intersections. The current Shapely union/polygonization pipeline intentionally discards that provenance, so it cannot reconstruct the original cubics after the fact. Overlap-normalized regions will need an explicit policy where no single original curve owns the resolved boundary.

## Automated verification

The updated tests cover deterministic linework, multi-segment/direction variation, reconstruction, minimum area, deterministic monotonic complexity samples, stable fragment/point compatibility, boundary provenance, UFO round trips, persistent topology, paired writes, reopen integrity, and failure rollback. The real-font validation harness and the Stage 2 create/reopen/append demonstration are rerun after this implementation.

## Remaining owner decisions

1. Whether the preferred style should remain a single-impact spiderweb or permit two or more seeded impact hubs at high complexity.
2. How much angular wandering and how many triangular local chips are acceptable before the result stops reading as fractured rock.
3. Whether the old recursive generator should remain a private regression fixture or be removed after the audit; it should not become a first-release UI option by default.
4. Whether future curve-aware exterior preservation justifies source-curve provenance work, especially for overlap-normalized boundaries.
5. Whether thin marks should deliberately remain low-detail or use a separate minimum-area/density policy.
