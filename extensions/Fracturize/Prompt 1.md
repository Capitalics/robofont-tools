# Stage 1 — Geometry and Compatibility Prototype

Create a focused technical prototype for an interpolation-compatible glyph fracture system.

This stage must prove the central geometry risks before project persistence or a RoboFont interface is built. Do not implement the production extension, persistent project workflow, batch UI, preferences, or final extension bundle in this stage.

## Product concept

The eventual product will take glyphs from a static source font and create two output masters:

- an **intact master**, assembled from independent fragments that reconstruct the source's filled silhouette;
- an **eroded master**, containing exactly the same fragment contours and points after controlled transforms.

Both masters must remain structurally compatible for interpolation.

The eventual project will reuse one intact UFO and one eroded UFO as more glyphs are processed. Persistent handling of those UFOs belongs to Stage 2. Stage 1 may write temporary test UFOs only to prove serialization and compatibility.

## Repository scope

Create a new standalone Git repository early if one does not already exist. Use the working names:

- repository folder: `Fracturize`;
- Python package: `fracturize`;
- eventual extension bundle: `Fracturize.roboFontExt`.

Keep the initial repository minimal. It should contain only what is useful for the geometry proof, such as:

- a small Python package for geometry and validation;
- tests and licensed or locally generated test fixtures;
- a short README;
- development dependency metadata;
- a decision or limitations note.

Do not build the extension bundle, menu registration, preferences, production project UI, or broad documentation yet. Keep the geometry package independent of live RoboFont UI objects so it can be tested outside RoboFont.

## Decisions to record before coding

Briefly inspect the current RoboFont, UFO, fontParts, defcon, and fontTools environment and record the actual versions used for the prototype. Do not attempt broad compatibility support.

Before implementing geometry, choose and document:

1. the polygon clipping backend;
2. the source fill rule and overlap-normalization policy;
3. the curve-flattening tolerance and coordinate-rounding policy;
4. the minimum fragment area or edge threshold;
5. the component policy;
6. the deterministic seed-derivation method;
7. the test corpus and its licensing or generation method.

Use practical choices that can be replaced later. Do not create a general backend abstraction unless a second backend is actually tested.

## Supported geometry for the first prototype

A polygonal first prototype is explicitly allowed and is the expected practical starting point.

If outlines are flattened:

- state clearly that the prototype does not preserve source Bézier curves;
- record the flattening tolerance and its relationship to units per em;
- use the same flattened geometry as the basis of both masters;
- measure reconstruction error against a clearly defined normalized source silhouette;
- do not describe polygonal output as curve-preserving or production outline quality;
- keep the clipping code isolated enough that a curve-aware implementation could replace it later without rewriting the fragment, compatibility, or validation models.

The prototype must explicitly define the **normalized source silhouette**. It should specify:

- the fill rule;
- whether overlapping source contours are unioned before fracturing;
- how contour direction errors, open contours, and malformed geometry are handled;
- how counters, nested contours, disconnected outlines, and small features are represented.

Do not clip overlapping source contours independently if that would duplicate black regions. Compare filled regions, not the source's original contour topology.

### Components

For Stage 1, choose one simple policy and enforce it consistently:

- reject component glyphs with a clear unsupported-input error; or
- decompose components before normalization and record that decomposition occurred.

Do not silently mix component and contour strategies. Component preservation is not required in this stage.

## Fracture topology

Generate one deterministic fracture topology per glyph. Construct both master states from that same topology.

Avoid independent destructive boolean operations on the intact and eroded states. The eroded master must be derived from the already canonicalized intact fragment geometry.

The fracture style should suggest irregular erosion or crumbling stone rather than a regular Voronoi mosaic or explosive glass shatter. For the first prototype, implement one understandable fracture strategy rather than several competing styles. Reasonable candidates include irregular weighted cells, recursive polygon splitting, or a small hybrid of primary divisions and secondary chips.

The output should aim for:

- large structural fragments;
- medium fragments;
- a limited number of small chips;
- varied but controlled edge angles;
- no obvious repeated motif.

These are visual goals, not automated compatibility requirements. Evaluate them separately from structural tests.

## Fragment data model and identity

A logical fragment may contain multiple disconnected contour parts and holes. Do not assume that one fragment always equals one contour.

Use a model that can represent at least:

- stable fragment ID;
- ordered contour parts belonging to the fragment;
- stable contour-part IDs;
- canonical point order and point identifiers where the output format supports them;
- area, centroid, and bounding box of the intact fragment;
- transform origin;
- translation, rotation, and positive scale for the eroded state.

Assign canonical fragment, contour-part, contour, and point order before applying motion. Never sort fragments or contours by their transformed positions.

Identifiers must be deterministic and safe to serialize. Do not use Python's process-randomized `hash()` or unordered geometry-library iteration as identity. Document whether IDs are derived or stored and how ties are resolved.

## Intact reconstruction

The intact master must be assembled from the same independent fragments used by the eroded master. It must not be the untouched source glyph with hidden extra geometry.

In the intact state:

- neighboring fragments meet at their canonical positions;
- every retained piece participates in reconstruction;
- counters and nested filled regions keep the intended fill;
- the union of all fragment geometry matches the normalized source silhouette within a declared tolerance;
- no fragment is deleted merely because it is small unless it falls below the documented minimum geometry threshold during topology construction.

Define reconstruction tolerance using measurable quantities. At minimum, report normalized symmetric-difference area or an equivalent filled-region metric. Boundary distance and raster comparisons may be added as secondary diagnostics.

Select thresholds from the fixture corpus and document them. Do not claim exact floating-point equality unless it is actually demonstrated.

## Eroded master and compatible transforms

Generate the eroded state by applying one stored affine transform to all points in each canonical fragment.

Suggested motion behavior:

- large fragments move less than small fragments;
- motion follows a global direction with deterministic variation;
- rotations are limited;
- scale remains positive and bounded away from zero;
- some fragments remain nearly fixed;
- movement should imply erosion rather than an explosion.

Fragments may overlap, move behind other fragments, shrink moderately, or become visually inconspicuous. They must not be deleted, clipped again, scaled to zero, or scaled through zero.

Use a stable transform origin based on the intact fragment geometry. Keep rotation and scale limits conservative. Linear point interpolation between the masters is not the same as continuously applying a rigid rotation, so inspect intermediate outlines for shrinking, flipping, shearing, and malformed contours.

## Fracture Complexity

Implement one primary high-level parameter:

**Fracture Complexity**, range `0–100`.

It must control a documented bundle of topology parameters rather than only a target fragment count. The bundle may include:

- target fragment count or area-normalized density;
- minimum fragment area;
- primary split count;
- secondary split or branching probability;
- small-chip probability;
- edge irregularity;
- detail depth.

Keep the mapping small and understandable. Advanced user controls are not part of Stage 1.

The mapping must:

- be deterministic for the same effective seed and complexity;
- remain bounded at high values so `100` does not automatically create unusable geometry;
- avoid tiny degenerate fragments;
- adapt to glyph area or another declared glyph measure so narrow and wide glyphs do not differ wildly without explanation;
- document which lower-level values are expected to change monotonically.

Test at least `10`, `25`, `50`, `75`, and `90`.

Changing complexity may regenerate a completely new deterministic topology. Genuine nested refinement is not required. State the actual behavior clearly and do not imply that topologies at different complexity values are related unless hierarchical refinement is implemented and tested.

## Deterministic seeds

Use a reproducible glyph-specific seed derived from:

- a prototype project seed;
- glyph name;
- complexity;
- optional glyph-specific override.

Choose a stable, versioned derivation method with canonical text encoding. The same inputs must produce the same effective seed across runs. Different glyph names should normally produce different seeds without repeating the same fracture placement.

Persisting full project settings and processed-glyph history is deferred to Stage 2.

## Automated validation

Automated validation must distinguish structural compatibility from visual quality.

For each intact/eroded pair, verify:

- same contour count and contour order;
- same point count per contour and point order;
- same segment sequence and on-curve/off-curve structure;
- compatible winding convention;
- stable fragment and contour-part identity;
- no empty or degenerate contours;
- same glyph width;
- no fragment scaled to or through zero;
- intact silhouette difference within the declared tolerance;
- successful serialization and reopening of temporary test UFOs.

Sample direct point interpolation at `0`, `10`, `25`, `50`, `75`, `90`, and `100`. Report orientation changes, near-zero areas, and other interpolation risks separately from hard structural errors.

Classify validation findings as:

- **hard error** — the pair is incompatible or invalid;
- **interpolation risk** — structurally compatible but likely to behave poorly between masters;
- **visual warning** — subjective or style-related concern.

## Visual evaluation

Do not turn subjective goals into passing automated tests.

Generate visual comparison sheets for the source silhouette, intact master, eroded master, fragment boundaries, and sampled intermediate states. Review whether the result:

- remains recognisable;
- resembles controlled erosion or crumbling stone;
- avoids an explosive or regular mosaic appearance;
- has reasonably consistent density across different glyph structures.

Use a small but varied fixture set. Include simple exteriors, counters, nested regions, overlapping contours, curves after flattening, thin features, small counters, disconnected outlines, and at least one invalid or unsupported glyph. The set `H`, `O`, `S`, `a`, `R`, and `8` is useful but not sufficient by itself.

Record visual observations honestly as human review results.

## Tests

Add focused tests for:

1. deterministic seed derivation;
2. deterministic topology for identical inputs;
3. distinct effective seeds for different glyph names;
4. normalized silhouette handling;
5. counters, nested regions, overlaps, and disconnected parts;
6. explicit component rejection or decomposition;
7. intact reconstruction tolerance;
8. stable fragment and contour-part ordering;
9. compatible intact and eroded point structures;
10. safe transform bounds and sampled intermediates;
11. complexity mapping at representative values;
12. minimum-feature and performance caps;
13. temporary UFO serialization and reopening;
14. unsupported or invalid input producing no matched output pair.

Report the actual environment, fixture list, backend versions, and passed, failed, and skipped tests.

## Stage 1 acceptance gate

Stage 1 succeeds only if:

- the normalized silhouette and polygonal limitations are documented;
- intact reconstruction passes the declared tolerance on the supported corpus;
- intact and eroded outputs are structurally compatible;
- identity survives UFO serialization and reopening;
- sampled intermediate states contain no hard structural failure;
- Fracture Complexity is deterministic, bounded, and meaningfully changes a bundle of topology parameters;
- unresolved visual or curve-quality limitations are clearly separated from automated results.

If those conditions fail, stop and recommend a focused geometry correction or backend experiment. Do not continue to persistent project handling or UI work.

## Deliverables

At completion, provide:

1. the minimal repository structure;
2. documented geometry, fill, flattening, component, and tolerance decisions;
3. an explanation of topology and stable identity;
4. an explanation of the Fracture Complexity mapping;
5. automated validation results;
6. visual review artifacts and separate human observations;
7. created and modified files;
8. known limitations, especially curve quality;
9. a verdict: `viable`, `viable after specific geometry corrections`, or `unsuitable`;
10. a clear recommendation on whether Stage 2 may begin.

Do not implement persistent project management or the RoboFont extension interface in this stage.
