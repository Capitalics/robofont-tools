# Stage 1 Decisions and Limitations

> Stage 3 integration decisions are summarized at the end of this document. Earlier prototype decisions are retained as history where the live extension supersedes them.

## Geometry backend

The proof uses Shapely 2.1.2 backed by GEOS 3.13.1. Shapely is practical in the available arm64 Python 3.11 environment and provides the required noding, polygonization, union, split, precision, and measurement operations.

No general geometry-backend abstraction was added. Curve-aware clipping remains a later research task.

## Source fill and normalization

The normalized source silhouette uses the non-zero winding rule:

1. flatten every supported closed source contour;
2. node the combined linework with GEOS;
3. polygonize the noded faces;
4. evaluate each face against the source-ring winding sum;
5. union every face whose winding sum is non-zero.

This produces the visible filled union and removes duplicated black regions from same-direction overlapping contours. It deliberately does not preserve original source contour topology.

Counters and islands depend on contour winding. Open, empty, and degenerate source rings are rejected rather than repaired silently.

Self-intersecting rings receive a bounded classification step. They are normalized only when all intersections are isolated point crossings, the non-zero face decomposition contains multiply-wound black regions, and the face topology and resolved silhouette remain stable when the flattening tolerance is halved. The limits are:

- maximum cross-tolerance symmetric-difference area: 0.2% of the finer silhouette;
- maximum cross-tolerance boundary Hausdorff distance: the primary flattening tolerance;
- identical self-intersecting contour indexes, face counts, selected-face counts, and winding histogram at both tolerances.

Coincident edges, ordinary single-winding bow-ties, tolerance-sensitive topology, and silhouettes outside either geometric bound still fail explicitly. This resolves legitimate overlapping path constructions without silently repairing arbitrary malformed outlines.

## Components

Components are explicitly unsupported in Stage 1. Any component name causes `UnsupportedOutlineError` before geometry generation. This is preferable to silent decomposition in the first proof.

A later stage may add explicit decomposition, but must fingerprint the decomposed inputs and apply the same strategy to both masters.

## Adaptive curve flattening

The UPM-relative flattening tolerance is:

```text
clamp(unitsPerEm / 2000, 0.25, 1.0)
```

At 1000 UPM the tolerance is 0.5 units. Cubics are recursively subdivided with de Casteljau subdivision until both control points lie within the tolerance of the endpoint chord, or a defensive depth limit of 24 is reached.

This is a declared polygonal approximation policy, not curve preservation. All generated UFO contour points have segment type `line`. Reconstruction is measured against the normalized **flattened** silhouette, not against the original analytic Bézier curves.

## Coordinate and measurement policy

Generated coordinates remain floating point and are not rounded before temporary UFO serialization.

GEOS can retain zero-width numerical seams when many coincident fragment edges are re-polygonized. Reconstruction measurement therefore compares source and intact regions on a precision grid of:

```text
unitsPerEm × 1e-12
```

This grid removes numerical seams far below the declared visible-error tolerances without masking meaningful geometry loss.

The hard reconstruction thresholds are:

- normalized symmetric-difference area: at most `1e-8` of source area;
- filled-boundary Hausdorff distance: at most `unitsPerEm × 1e-7`.

These are measured tolerances, not exact-equality claims.

## Fracture topology and identity

The default topology version is `branching-rough-crack-mesh-v2`. A seeded visual impact point drives primary macro cracks. Secondary cross-links join neighbouring primaries at irregular radii, and complexity-dependent short boundary branches form local chips. Secondary links sharing a primary use one exact anchor so the graph has no accidental near-duplicate junctions.

Macro layout and micro edge profile are separate deterministic passes. The edge profiler subdivides each macro span at non-uniform distances, offsets intermediate points laterally, and adds bounded sharp shoulders and short notch/rebound events. Original endpoints and shared junctions remain exact. Candidate rough lines are accepted only when they are simple and preserve the macro line-intersection graph; otherwise whole-mesh deviation is reduced and ultimately falls back to the clean macro mesh. Roughening may change where, or how often, a crack crosses a concave exterior or counter boundary. Every resulting crossing is explicitly noded and reported.

The combined rough crack linework and normalized silhouette boundary are noded and polygonized; faces outside the non-zero silhouette are discarded. Undersized or surplus faces are merged deterministically across their longest shared boundary. A hard symmetric-difference check prevents incomplete coverage. Because adjacent fragments are derived from one noded linework graph, their crack edges are complementary rather than independently perturbed.

The former `recursive-split-v1` generator remains available only to the comparison harness. `branching-crack-mesh-v1` is retained for projects that already record that policy. `generate_pair()` accepts a topology generator behind a narrow polygon-fragment contract, demonstrating that the topology language can change without rewriting master compatibility, motion, persistence, or UFO code.

### Rough edge-profile bounds

At complexity 72 and 1000 UPM, the declared profile is:

| Parameter | Value | Complexity range at 1000 UPM |
| --- | ---: | ---: |
| Edge subdivision density | 32.08 segments/em | 22–36 segments/em |
| Lateral deviation amplitude | 11.76 units | 6–14 units |
| Segment-length variation | 0.4264 | 0.34–0.46 |
| Sharp-corner probability | 0.1348 | 0.07–0.16 |
| Local-notch probability | 0.0646 | 0.025–0.08 |
| Simplification threshold | 0.606 units | 0.75–0.55 units |
| Minimum segment length | 7 units | 7 units |

Density and amplitude rise gently with complexity and remain capped. Random distances, correlated offsets, sparse shoulders, and notch/rebound pairs avoid evenly spaced zigzags and periodic wobble. The minimum segment length also constrains retained macro vertices; required shared anchors take precedence, and the current shared-anchor layout keeps sampled real-font segments above the bound.

One logical fragment can contain multiple polygon parts or holes. Canonical order is assigned before motion using stable bounds, area, and normalized geometry data. Fragment identifiers use SHA-256 over the topology version, effective seed, canonical index, and normalized geometry. Contour and point identifiers derive from the fragment identifier.

No sorting occurs after transforms. Exact reproducibility is claimed for the tested Shapely/GEOS stack; GEOS algorithm changes may alter split geometry, so the backend versions are part of the prototype environment.

## Fracture Complexity

Fracture Complexity is an integer from 0–100. It coordinates:

- area-normalized target fragment count, capped at 28;
- minimum fragment area, from 0.48% down to 0.06% of em-square area;
- primary split count;
- secondary split probability;
- off-center chip probability;
- edge-angle irregularity;
- retry/detail depth.

All of these values participate in topology generation. High complexity is bounded by target-count, minimum-area, and retry caps.

Complexity changes deterministically regenerate topology using a complexity-dependent effective seed. The system does not implement nested or hierarchically related topologies.

## Seed derivation

The effective topology seed is the first 64 bits of SHA-256 over canonical UTF-8 fields separated by U+001F:

```text
sha256-v1, project seed, glyph name, complexity, optional glyph override
```

Python's randomized `hash()` is not used.

Motion uses a second SHA-256-derived random stream per stable fragment ID. This separates canonical topology identity from transformed position.

## Motion and interpolation

Every fragment uses one transform origin at its intact centroid. Motion applies bounded translation, rotation, and uniform positive scale to every point in that fragment. Persistent projects record `architectural-erosion-v2`; the legacy `fragment-affine-motion-v1` remains available only for comparison and exact interpretation of its declared version.

The version-2 visual target is architectural erosion rather than explosion or gravity-driven collapse. Motion is size-aware:

- the largest piece is retained as a stable structural core;
- large, medium, and small fragments have separate ordered movement multipliers of `0.18`, `0.55`, and `1.0` by default;
- maximum rotation is 12 degrees and is reduced by fragment size and movement class;
- minimum scale is 0.78 and cannot reach or cross zero;
- baseline retention defaults to 0.85;
- maximum downward drift defaults to 0.025 em and is independent of crumble amount;
- at most 12% of fragments may newly cross the baseline, with small chips preferred when a crossing is allowed.

All motion values must be finite and within declared safe ranges. Objective interpolation risks such as self-intersection or near-zero contour area block generation. Subjective visual warnings remain non-blocking.

Interpolation is direct linear point interpolation between the two master geometries. Samples at 0, 10, 25, 50, 75, 90, and 100 are checked for near-zero contour area and self-intersection. Structural compatibility does not guarantee aesthetic intermediate behavior.

## Test fixtures and licensing

All fixtures contain original synthetic geometry; no external font data is redistributed. The reproducible UFO built by `scripts/build_regression_fixture.py` covers legitimate multiply-wound overlaps, counters, cubic curves, components, metadata, layers, kerning, groups, features, guidelines, and data-file copying. Small in-memory fixtures additionally cover nested fills, disconnected shapes, thin counters, and malformed/open-contour rejection.

## Deferred decisions

- curve-aware clipping backend and production curve quality;
- explicit component decomposition;
- final visual tuning of the branching fracture language, including whether multiple impact hubs are desirable;
- protected features and improved thin-form density normalization;
- persistent topology/project format;
- persistent two-UFO ownership and saving;
- RoboFont object and UI integration.

## Stage 3 integration decisions

- The source is the currently open RoboFont UFO at project creation.
- The two outputs are complete, open, user-owned working copies. Project creation writes them beside the chosen project record; later saves remain under normal RoboFont user control.
- The live project record is a small versioned `.fracturize.json` beside a sibling topology-data folder and records the three font paths and identities.
- The extension modifies selected default-layer outlines and Fracturize-owned metadata only. Shared font and glyph metadata is validated across the pair.
- Components are preserved unchanged by default. Optional decomposition is confirmed once per batch and performed in a detached serialized source copy. The open source remains unchanged.
- A generated-output fingerprint mismatch requires Replace, Keep, or Cancel. There is no merge.
- RoboFont font access and batch commits remain on the main thread. The UI yields between glyphs rather than moving RoboFont objects to a worker.
- Output glyph replacement participates in each document's undo mechanism where RoboFont exposes it.
- Closing any member of the three-font set stops processing. Saved paths may be reopened automatically; missing or mismatched sides are not recreated.
- The minimal panel exposes the owner-directed motion controls but no lower-level crack-profile editor or broad advanced UI.
- The bundle targets RoboFont 4.6 / Python 3.12 and installs bounded Shapely 2.1.x through RoboFont's package installer when needed.
- The project remains internal to the private `robofont-tools` repository under an all-rights-reserved notice. No public packaging or distribution work is included.

Still deferred are curve-preserving clipping, crash-atomic multi-document transactions, schema migrations, general relocation recovery, output-outline merging, background geometry work, automatic designspace builds, Glyphs automation, and broad compatibility.
