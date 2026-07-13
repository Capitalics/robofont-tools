# Review of the Fracturize Development Prompts

Review date: 2026-07-13

## 1. Executive verdict

**Recommendation: restructure the workflow substantially before implementation.**

The product concept is feasible, and the central compatibility strategy is correct: create one fragment topology, construct the intact master from it, and derive the eroded master by applying deterministic per-fragment transforms without adding or deleting geometry. Two UFOs that accumulate processed glyphs are also a workable project model.

The prompts are not ready to run as written, however. Prompt 1 combines at least four separate proofs of concept—clipping/reconstruction, compatible transforms, persistent project/UFO writes, and RoboFont packaging—and is close to specifying the whole application. This makes it likely that a geometry experiment will acquire premature persistence and extension architecture, or that the geometry risk will be hidden behind a large amount of infrastructure.

The hardest requirement is not ordinary interpolation compatibility. Once matched fragment contours exist, compatibility can be preserved mechanically. The hardest requirement is producing a robust set of fragments whose union reconstructs the source's filled silhouette across curves, counters, nested contours, overlaps, thin features, and clipping degeneracies. The prompts acknowledge curve risk but do not choose a fill model, geometry backend, tolerance model, or supported input subset. Those decisions must precede implementation.

The two-UFO write requirement also needs more precise language. A crash-proof atomic commit across two directory-based UFO packages and a project file is not generally available as a single filesystem transaction. The achievable requirement is either a recoverable staged commit with a journal/manifest, or a documented best-effort replace protocol. “Transactional” must be defined and tested in terms of observable failure and recovery states.

Implementation should **not** begin yet. First revise the prompts into narrower gates with objective acceptance criteria and make the architectural decisions listed below.

## 2. Files, roles, and intended architecture

### Files inspected

The current `extensions/Fracturize` folder contains only:

| File | Role determined from content | Status |
| --- | --- | --- |
| `Prompt 1.md` | Prototype implementation | Complete, 406 lines |
| `Prompt 2.md` | Prototype technical review, correction, and validation | Complete, 248 lines |
| `Prompt 3.md` | Production RoboFont extension implementation | Complete, 501 lines |

The numeric filenames are ambiguous without reading them, but their contents establish the order unambiguously. No extension repository, package, bundle, tests, or other Fracturize files exist yet. The neighboring `WorkspaceLauncher.roboFontExt` is an unrelated extension and should remain only a possible local convention reference, not a dependency or destination.

### Intended architecture summarized

The prompts describe a standalone extension organized around a persistent “fracture project”:

1. A static source font remains unchanged.
2. A project owns one intact output UFO, one eroded output UFO, a seed and shared style settings, per-glyph generation state, source fingerprints, and output paths.
3. Processing a glyph produces a stable fragment model once.
4. The intact master contains every fragment at its original position and should reconstruct the source fill.
5. The eroded master contains the same fragment contours in the same order, with corresponding points transformed by translation, rotation, and positive scaling.
6. Validation precedes a paired write to the two persistent output UFOs.
7. Later glyphs are appended to the same pair, and the pair may later become sources in a designspace or be imported into Glyphs.

This separation is sound in principle:

- a pure geometry core should not depend on RoboFont UI objects;
- topology generation should be separate from the motion model;
- persistence should be separate from both geometry and UI;
- the RoboFont extension should be an adapter over those tested layers;
- fragment ordering should come from stored identity, never from transformed position.

UFO 3 is the natural output format. It provides contour and point identifiers, but those identifiers are only unique within a glyph and should not be confused with a project-wide fragment ID. A namespaced glyph lib record or a stable mapping from fragment ID to contour IDs is still needed. See the [UFO 3 GLIF specification](https://unifiedfontobject.org/versions/ufo3/glyphs/glif/).

## 3. Major technical risks and feasibility

### 3.1 Polygon clipping and curve preservation — high risk, research required

The proposed clipping operation is conceptually straightforward: normalize the glyph into a filled planar region, partition the plane into fracture cells, and intersect the filled region with each cell. Real font outlines make the implementation difficult.

- Shapely/GEOS is robust and useful for polygonal prototyping, including polygons with interior rings, but it has no smooth curve model; curves must be flattened to line segments. This is an explicit limitation of [Shapely's data model](https://shapely.readthedocs.io/en/stable/manual.html). A Shapely prototype therefore cannot claim curve preservation.
- A curve-aware path-operations backend may retain cubic segments, but its exact behavior at coincident edges, tangencies, overlaps, and very small features must be proven on the target RoboFont/Python versions. Backend availability inside RoboFont is also a deployment question.
- Reconstructing new cubic curves after arbitrary polygon clipping is not a neutral conversion. Curve fitting introduces error and generally cannot recover the original segment structure. It is acceptable only as an explicitly approximate output strategy with measured tolerances.
- “Preserving cubic geometry directly” is underspecified. A useful experiment must specify which clipping engine performs Bézier/line intersections, how curves are split at intersections, and how shared fracture edges are represented.

The prototype should initially choose one of two honest goals:

1. **Polygonal feasibility prototype:** flatten at a declared tolerance, support a controlled glyph corpus, and prove topology, reconstruction, deterministic identity, and interpolation. The output is not production curve quality.
2. **Curve-aware feasibility prototype:** select and package a curve-capable boolean backend, then prove it against adversarial font outlines before working on project persistence or UI.

Trying to prove both at once obscures the result.

### 3.2 Definition of the source silhouette — high risk, currently missing

“Match the source silhouette” is not testable until the prompts define what the source silhouette means.

- Does the source use non-zero winding, even-odd fill, or RoboFont's displayed fill semantics?
- Are overlapping source contours normalized into a union before fracturing, or treated as independent source contours?
- Are contour direction errors repaired, rejected, or reproduced?
- How are nested counter/island structures represented after intersection?
- Is visual equality measured on vector regions, raster masks, area symmetric difference, boundary distance, or a combination?

If contours are clipped independently, overlapping black contours can create duplicate fragment geometry and transformed overlaps can reveal unintended shapes. If the source is boolean-normalized first, the intact fill can match visually, but the source's original contour structure, point data, hints, and component structure are deliberately discarded. The project should state that its invariant is the normalized filled region, not preservation of original outline topology.

Counters and nested contours are implementable if the backend returns regions with holes and the code applies one explicit fill rule. A single logical fragment may yield multiple disconnected polygons and holes. Therefore “one fragment equals one contour” is not a valid assumption. The model needs `Fragment -> ordered contour parts`, with persistent IDs for both the fragment and each part.

### 3.3 Intact silhouette reconstruction — high risk but feasible

If fracture cells form a true partition and every intersection piece is retained, the union of intact fragments can equal the normalized glyph region within numerical tolerance. Seams may still appear in previews because of rasterization even when vector edges coincide; conversely, overlapping coincident edges can hide geometry errors. Validation must compare filled regions, not only point coordinates or screenshots.

The requirement “no unwanted overlaps change the black shape” should be interpreted as equality of the union, not a blanket ban on coincident boundaries. Exact equality is unrealistic with floating-point clipping and curve flattening. The prompt must define tolerances relative to UPM, for example:

- maximum normalized symmetric-difference area;
- maximum boundary deviation;
- minimum retained fragment area and edge length;
- raster comparison at specified resolutions as a secondary regression test.

The exact thresholds should be selected empirically from a disclosed test corpus rather than invented in the implementation prompt.

### 3.4 Persistent identity and compatibility — feasible with a stronger model

The one-topology/two-state strategy is the strongest part of the prompts. Once the intact fragment contours are canonicalized, the eroded contours can be generated by applying one affine transform to every point in each fragment. This preserves contour count, point count, point order, segment types, and identifiers.

Required clarifications:

- Canonical contour/point order must be assigned once before motion and serialized. Geometric sorting is acceptable only during initial canonicalization with deterministic tie-breaking; it is unsafe after transformation.
- Fragment IDs should be deterministic from the topology record, not Python's randomized `hash()` and not iteration order from a geometry library.
- Contour-part and point IDs are also needed if identity is to survive serialization and regeneration.
- IDs stored in UFO identifiers must obey UFO uniqueness rules within each glyph. Project-level identity may additionally live under a namespaced glyph lib key.
- Regenerating at another complexity value creates a new topology unless genuine hierarchical refinement is deliberately implemented. The prompts correctly warn against claiming nested complexity, but Prompt 3 still implies a stable “global visual identity”; that is a visual objective, not a topology guarantee.

### 3.5 Rotation, scaling, and intermediate interpolation — feasible with limits

Matched endpoints make the masters structurally interpolable, but that does not guarantee good intermediate shapes. Variable-font interpolation linearly interpolates point coordinates; it does not apply a true continuously rotating rigid transform. Consequently:

- a rotated/scaled end fragment follows the linear interpolation of its transformed points;
- large rotations can shear, shrink, or flip fragments at intermediate locations;
- positive scale at both masters alone is not a complete proof that the interpolated affine transform remains non-singular;
- different transform origins change the visual path and must be stable, stored, and normally based on the intact fragment geometry;
- collisions and overlaps are not compatibility errors, but may be serious visual defects.

The solution is not to ban transforms, but to cap rotation/scale ranges, analyze the determinant or polygon orientation at sampled and critical intermediate values, and inspect representative interpolation states. “Preserve recognisability” and “progression of erosion” need corpus-based visual review criteria; they cannot be guaranteed by topology validation.

### 3.6 Two-UFO transactional writing — feasible as recovery, not literal atomicity

A UFO package is a directory containing multiple files. Saving two UFO directories plus a JSON project file cannot normally be one indivisible commit. A process or machine failure can occur between replacements.

Choose and document one protocol:

- **Staged full-package commit:** write validated complete UFO copies and a project record into a staging directory on the same volume, fsync as appropriate, then replace destinations in a defined order while keeping backups and a transaction journal. On reopen, finish or roll back the recorded transaction.
- **Glyph-level journaled commit:** record before/after state and transaction status, write both sides, verify, then mark committed; recover or restore on next open.
- **Single container project:** technically simplifies atomic replacement but is less natural for directly reusable UFO outputs and conflicts with the proposed project layout.

Tests must inject failures before and after each commit step and verify reopen/recovery. A test that only raises before `save()` does not prove transaction safety. The output UFOs being open and edited in RoboFont would complicate replacement, cache invalidation, notifications, and undo, so that policy must be decided early.

### 3.7 Designspace and Glyphs handoff — feasible but not automatic

Two same-format UFOs with compatible generated glyphs can be designspace sources. fontTools' designspace tooling assumes compatible outlines and recommends relative paths for portable designspaces; see [designspaceLib documentation](https://fonttools.readthedocs.io/en/latest/designspaceLib/index.html) and its [scripting guide](https://fonttools.readthedocs.io/en/latest/designspaceLib/scripting.html).

Compatibility of processed glyphs is not sufficient for a buildable font:

- both masters need the same glyph set or explicit exclusion strategy;
- components, anchors, guidelines, groups, kerning, features, glyph order, and font info need a stated ownership/copy policy;
- `.notdef` and required build glyphs need a plan;
- a custom axis requires a four-character tag and appropriate naming/STAT decisions; an unregistered tag is valid for experimentation but has distribution and interoperability implications;
- Glyphs import is a lossy/interoperability workflow to test, not a guaranteed preservation mechanism.

The prompts should promise “candidate compatible masters” until a real designspace build and interpolation check passes.

## 4. Contradictions, duplication, and ambiguities

| Topic | Finding | Recommended resolution |
| --- | --- | --- |
| Stage boundaries | Prompt 1 says “technical prototype” but requires a repository, extension packaging, persistent project format, change detection, safe paired saves, 12 tests, and RoboFont instructions. | Limit Stage 1 to geometry and compatibility. Move persistence and packaging to later gated stages. |
| Review authority | Prompt 2 is framed as a review but also orders fixes and new tests. That permits the reviewer to change the artifact being evaluated and blurs the audit result. | Split into 2A independent audit/report and 2B approved correction/verification. |
| UI gate | Prompt 2 says not to begin full UI unless requirements pass; Prompt 3 immediately commands production UI, with no explicit instruction to stop if Prompt 2's verdict is unsuitable. | Make Prompt 3 conditional on recorded gate results and require unresolved high-severity risks to block it. |
| Project creation | Prompt 1 creates output UFOs on the first processed glyph. Prompt 3's project workflow creates UFOs during project creation. | Prefer explicit project creation before glyph processing; no lazy creation in the production workflow. A CLI prototype may use a temporary fixture project. |
| Output ownership | Prompts call the two UFOs authoritative, but do not say whether users may edit them externally or in RoboFont. | Define them as extension-managed generated artifacts. External edits must be detected or explicitly unsupported. |
| “Transactional” | All prompts require transactional writes without defining commit boundary, crash behavior, open-UFO behavior, or recovery. | Define a staged/journaled protocol and failure-injection acceptance tests. |
| Batch atomicity | Prompt 3 says “avoid partial writes” but also “report failures per glyph” and allow cancellation between glyphs. | Define atomicity per glyph pair, not per batch. Completed glyphs stay committed; the current failed/cancelled glyph commits neither side. |
| Complexity | Prompt 1 says one high-level control and merely suggests nested relation; Prompt 3 adds extensive editable advanced controls. | Treat complexity as a versioned preset mapping. Custom advanced values form an explicit profile. A change that affects topology invalidates/regenerates topology. |
| Seed derivation | All prompts conceptually agree, but do not specify a stable hash, normalization, encoding, or algorithm/version migration. | Specify a cross-platform derivation such as a versioned cryptographic digest of canonical UTF-8 fields; persist the derivation version and effective seed. |
| Curves | Prompt 1 allows polygonal prototype; Prompt 2 reviews curved regions as though they may already be supported; Prompt 3 assumes validated geometry. | Make the backend/input capability part of the prototype report. Review only claimed capabilities, and block production if the chosen quality bar is unmet. |
| Overlaps and counters | Prompt 1 requires correct counters but never defines fill normalization. Prompt 2 expects overlap testing. Prompt 3 omits the policy. | Define normalization/fill semantics and carry them through all prompts. |
| Components | Prompt 1 is silent. Prompt 2 does not explicitly test component strategy. Prompt 3 introduces decompose/skip/cancel. | Decide component policy during geometry input normalization and test it before production. |
| Anchors/metadata | Prompt 1 says copy safe lib data; Prompt 2 expects matching anchors and relevant metadata; Prompt 3 says preserve anchors “where compatible.” | Define exact allowlists and master-compatibility rules. Never copy arbitrary glyph lib data blindly. |
| Source changes | Prompt 1 requires detection; Prompt 2 verifies it; Prompt 3 adds stale states. This is consistent but too early in Prompt 1. | Move fingerprinting to the persistence proof of concept. Define precisely what the fingerprint includes. |
| UFO info | “Essential,” “appropriate,” and “relevant” font info recur without an allowlist. | Define copied, generated, and omitted fields, including variation data, features, groups, kerning, and lib keys. |
| Validation | Structural checks are repeated across all prompts, but no canonical report schema, tolerances, or severity rules are defined. | Create one validator contract used by core, CLI/tests, and UI. |
| Visual claims | “Stone-like,” “recognisable,” “family resemblance,” and “not explosive” are repeated but not objectively testable. | Use curated visual test sheets and human sign-off; keep them separate from automated pass/fail claims. |
| Designspace language | “Variable-font masters” is used before an actual designspace/build has been validated. | Call them “intact and eroded output masters” or “candidate interpolation masters” until the build gate passes. |
| Repository timing | Prompt 1 creates a new repository before the central backend decision. The review request states the current folder is only the parent location. | Do not create the repository until this review is accepted and the revised Stage 1 is agreed. |

## 5. Missing architectural decisions

These decisions should be recorded in a short architecture decision log before coding. The review does not choose final answers where the trade-off belongs to the product owner.

### Runtime and packaging

1. **Supported RoboFont range and macOS range.** Current RoboFont documentation states that RoboFont uses UFO 3 and supports Python 3.12, but the project must decide whether it supports only a current RoboFont release or a broader range. A narrow range simplifies binary dependencies and UI testing; a broad range increases users but multiplies compatibility work. See [RoboFont technical specifications](https://doc.robofont.com/).
2. **Python minimum version.** Match the selected RoboFont releases, not the developer's system Python. Current fontTools itself requires modern Python, while RoboFont embeds specific library versions; dependency pins must respect the embedded environment.
3. **UFO format.** UFO 3 is strongly indicated. Decide package directory versus UFOZ; directory UFOs are widely editable but complicate atomic replacement.
4. **Dependency policy.** Choose among bundled dependencies, RoboFont-embedded libraries, an installer-managed environment, or optional backends. Binary wheels such as Shapely/GEOS or skia-pathops must be tested on all supported macOS architectures and RoboFont's embedded Python.
5. **Licensing.** Select repository license, dependency-compatible notices, and a license for bundled test fonts. Do not assume source-font fixtures may be redistributed.

### Geometry

6. **Geometry backend.** Compare at least polygonal Shapely/GEOS, curve-aware path operations, and a limited in-house splitter. Criteria: cubic support, fill rules, determinism, robustness, wheel availability, licensing, performance, and reproducibility.
7. **Source fill normalization.** Define non-zero/even-odd behavior, overlap removal, winding repair, open contour rejection, and component decomposition.
8. **Curve policy.** Preserve/split original cubics, flatten permanently, or fit curves after polygon clipping. Each option has different accuracy and compatibility implications.
9. **Tolerance and coordinate policy.** Decide floating-point precision, rounding on UFO write, minimum area/edge thresholds, UPM-relative tolerances, and whether integer coordinates are required.
10. **Fragment model.** Define fragments with zero or more contour parts and holes, stable fragment/part/point IDs, canonical ordering, adjacency semantics, and serialization version.
11. **Topology algorithm.** “Weighted cells,” recursive splits, and fracture paths are alternatives, not a specification. Pick one minimal algorithm for the proof and define what complexity changes.
12. **Transform safety.** Define transform origin, maximum rotation/displacement, scale bounds, hidden-fragment strategy, collision policy, and intermediate-risk metrics.

### Project and UFO ownership

13. **Project format and schema.** Prefer a dedicated, versioned JSON file near the UFOs for portability and inspection; UFO lib data can duplicate a project ID but should not be the sole cross-UFO record. Define schema versioning, canonical JSON encoding, migrations, unknown-field behavior, and path rules.
14. **Authoritative data.** Decide whether the project file, serialized topology records, or generated UFO contours are the source of truth for regeneration. Without stored topology, “motion-only regeneration” may depend on reverse-engineering UFO geometry.
15. **Storage of topology.** The listed project fields do not include full fragment geometry/transforms, yet Prompt 3 requires keeping topology while regenerating motion. Store a versioned topology artifact or an exactly reproducible generator specification and effective seed; stored geometry is safer across algorithm upgrades.
16. **Open output UFO policy.** Keeping them closed and writing with headless defcon/fontParts simplifies staged replacement. Keeping them open gives immediate feedback but requires notifications, dirty-document coordination, save conflict handling, and undo policy.
17. **Object API.** Use RoboFont/FontParts objects for UI-selected source data, but consider detached recordings or headless defcon objects for pure processing and output. Passing live RoboFont objects into worker code or threads is unsafe and hard to test.
18. **Undo behavior.** Source remains unchanged, so source undo is irrelevant. If outputs are open, decide whether a paired generated-glyph write is one UI undo operation, whether saving clears it, and how undo could remain paired across two documents.
19. **Atomic/recovery strategy.** Define staging location, same-volume constraint, locks, backups, journal states, fsync expectations, recovery on launch, concurrent project opens, and failure injection.
20. **External modifications.** Decide whether edits to either output UFO are forbidden, detected by fingerprints, merged, or overwritten only with confirmation.
21. **Source identity and fingerprint.** A path is not identity. Decide whether the font fingerprint includes file identity, relevant font info, glyph outline including components, width, unicodes, anchors, and relevant lib keys. Canonicalize data so semantically identical serialization does not appear stale.

### UI and product behavior

22. **UI framework.** Vanilla is the conventional RoboFont UI choice; Merz may suit interactive drawing/overlays. Decide window/controller architecture, observer lifecycle, and which preview technology is supported by target RoboFont versions.
23. **Interpolation preview.** Prefer direct point-wise interpolation of the two generated point recordings. A designspace/font compilation for every slider movement is unnecessarily heavy. The preview must use exactly the serialized master geometry and the same point pairing as validation.
24. **Batch behavior.** Define per-glyph atomicity, progress/cancellation checkpoints, UI responsiveness, and whether pure geometry can run off the main thread while all RoboFont object access stays on the main thread.
25. **Error and status model.** Define hard errors, interpolation risks, visual warnings, stale, failed, and compatible states in one domain model before designing controls.
26. **Test assets and visual review.** License a compact UFO corpus containing lines, cubics, counters, nested contours, overlaps, components, thin joins, tiny counters, reversed contours, malformed inputs, non-Latin forms, and very large/small UPMs. The suggested `H O S a R 8` is useful but insufficient.

### Handoff

27. **Glyph-set policy.** Decide whether unprocessed source glyphs are copied unchanged into both outputs, omitted until processed, or muted/excluded in a designspace. Progressive partial UFOs may not compile as a normal variable font.
28. **Axis definition.** Choose a temporary development tag/name/range and a later distribution decision. Specify which master is the designspace default and how STAT/naming will be generated.
29. **Glyphs interoperability target.** Define tested Glyphs version, import route, expected losses, and whether imported files remain outside the authoritative project workflow.

## 6. Scope recommendations for each current stage

### Prompt 1: reduce to the central geometry risk

Keep:

- deterministic topology from a versioned project/glyph seed;
- explicit fill normalization on a small licensed test corpus;
- fragment/part identity and canonical ordering;
- intact reconstruction from fragments;
- eroded state derived by safe point-compatible transforms;
- structural compatibility checks and sampled interpolation;
- a small command-line or RoboFont-script harness that writes temporary test UFOs.

Defer:

- production extension repository/bundle/menu/preferences architecture;
- general project creation UX and user-selected paths;
- persistent multi-session project records and relocation;
- source-change detection;
- batch processing and progress UI;
- advanced complexity profiles;
- complete font-info/lib copying;
- production transaction recovery;
- Glyphs documentation and full designspace handoff;
- subjective claims of recognisability across the full character set.

Mock or explicitly exclude:

- components, initially by rejecting them with a clear diagnostic;
- arbitrary overlapping or malformed contours until the fill-normalization proof adds them deliberately;
- live RoboFont output documents and undo;
- true curve preservation if the first experiment is polygonal;
- more than one fracture algorithm/style;
- nested complexity unless it is the subject of its own experiment.

Prompt 1's current `Fragment` field list is also too prescriptive. Store only fields required to prove topology and transforms; neighbours, size class, hiding strategy, and duplicate seed values can be derived or added when a selected algorithm needs them.

### Prompt 2: separate audit from correction

First run an independent technical audit against declared prototype capabilities. It should inspect repository isolation, geometry fixtures, deterministic artifacts, validator output, interpolation samples, and actual test results. It should not modify code.

Then, only if requested, run a correction stage for bounded high-severity defects with regression tests. Architectural replacement or a backend change should return to the proof-of-concept stage rather than being smuggled into “review.”

The visual matrix should include the proposed glyphs plus adversarial fixtures. Complexity values `10, 25, 50, 75, 90` are useful sampling points, but pass/fail needs measurable fragment counts, minimum feature sizes, time/memory budgets, and silhouette tolerances. Visual quality remains human-reviewed.

### Prompt 3: productionize only validated capabilities

Prompt 3 should begin with explicit prerequisites: accepted audit verdict, chosen target versions/backend, passing recovery protocol, stored topology format, and approved UI wireflow. It should then add persistence and RoboFont integration before the full UI.

The current Prompt 3 UI scope is very large. Defer from the first production release:

- character-set selection beyond current/selected/name list;
- all debug overlays except fracture boundaries and compatibility status;
- the full advanced control matrix;
- automatic Glyphs import/export;
- sophisticated project relocation heuristics;
- numerous hiding strategies and impact/gravity models;
- background batch geometry until main-thread boundaries are proven.

An initial usable release can provide project create/open, a small stable style preset, current/selected glyph processing, an intact/eroded/interpolation preview, stale detection, safe paired writes, clear validation, and documented designspace handoff.

## 7. Recommended revised stage sequence

1. **Stage 0 — decisions and fixtures.** Record target RoboFont/Python/UFO versions, select candidate geometry backends, define source fill and tolerance policies, license the test corpus, define vocabulary, and write measurable gates.
2. **Stage 1A — clipping and intact reconstruction proof.** No extension, project files, or erosion UI. Intersect normalized test glyph regions with deterministic partitions; retain every component/hole; measure union equality and degeneracies. Compare polygonal and curve-aware approaches if the backend remains undecided.
3. **Stage 1B — compatible transform proof.** Freeze canonical fragment/part/point order; generate intact and eroded recordings; sample interpolation, orientation, determinant/area, collisions, and visual progression under bounded transforms.
4. **Stage 1C — complexity and style proof.** Define a versioned 0–100 mapping, normalize it by glyph geometry, establish performance/feature-size caps, and determine whether complexity regenerates or refines topology.
5. **Stage 2A — project persistence and paired-UFO proof.** Define the project/topology schemas, deterministic seed derivation and fingerprints; create/reopen the same UFO pair; append glyphs; implement staged or journaled recovery; inject failures.
6. **Stage 2B — independent technical audit.** Review without changing code. Produce a severity-ranked verdict and verify actual designspace compilation on a controlled glyph set.
7. **Stage 2C — bounded corrections and re-audit.** Fix approved defects, add regressions, and repeat failed gates. A backend or data-model replacement returns to the relevant proof stage.
8. **Stage 3A — RoboFont integration spike.** Prove source selection, object conversion, main-thread boundaries, output-open/closed policy, notifications, menu entry, and a minimal preview in supported RoboFont versions.
9. **Stage 3B — UX specification and minimal production extension.** Finalize wireflows/status language, create the standalone repository and bundle, implement create/open/process/preview/recover, package dependencies, and document installation/handoff.
10. **Stage 3C — batch and advanced features.** Add batch selection, advanced profiles, overlays, relocation/relinking, broader component handling, and optional interoperability features based on real use.

This sequence creates separate stop/go gates for clipping, reconstruction, interpolation, persistence, and application integration. Interface work no longer masks geometry uncertainty.

## 8. Repository location and naming

### Recommended names

- **Product/repository folder:** `Fracturize`
- **Repository name if hosted:** `robofont-fracturize`
- **Python distribution/package:** distribution `robofont-fracturize`, import package `fracturize`
- **Extension bundle:** `Fracturize.roboFontExt`
- **Project file extension:** provisional `*.fracturize.json` until the schema decision is recorded

`Fracturize` is more distinctive and less narrowly stylistic than the provisional `RockFracture`; it can cover fracture plus erosion without embedding a single material metaphor in the API. Before committing to it, check package, extension-store, and trademark/name availability. Do not use spaces or hyphens in the Python import package.

### Location

The eventual standalone repository should be created as a new child of the present parent folder:

```text
extensions/Fracturize/
    Fracturize/                 # future repository root
        Fracturize.roboFontExt/
        src/fracturize/
        tests/
        docs/
        pyproject.toml
        README.md
        LICENSE
```

That nested layout respects the statement that the current folder is a parent working location and prevents the planning files from being mistaken for repository source. A non-`src` layout is also possible and may match RoboFont bundle tooling better; choose after inspecting current extension packaging conventions. The package must have one canonical implementation, with the bundle built or linked from it rather than maintaining a second copied code tree.

### Planning document location and repository timing

Keep the three original prompts and this review in the current parent folder during planning:

```text
extensions/Fracturize/
    Prompt 1.md
    Prompt 2.md
    Prompt 3.md
    PROMPT_REVIEW.md
    Fracturize/                 # created later
```

Once the prompts are revised, move durable architecture decisions and specifications into the future repository under `docs/architecture/`. The conversational Codex prompts may remain outside the repository or be archived under `docs/planning/` if their history is useful; they should not be presented as product documentation.

Do **not** create the repository immediately. First accept this review, revise the workflow, select the Stage 0 decisions, and define the Stage 1A gate. Creating the repository after that keeps its Git history focused while still allowing architecture records to start at the first commit.

## 9. Proposed prototype acceptance criteria

These criteria apply to the narrowed geometry/compatibility prototype, not the production extension. Numeric tolerances marked “selected” must be fixed in Stage 0 from the test corpus and then written into the prompt.

### Supported input declaration

- The prototype declares its geometry backend, version, curve policy, fill rule, overlap policy, component policy, coordinate rounding, and unsupported inputs.
- A licensed fixture corpus covers at minimum: a simple exterior, counter, nested counter/island, overlapping contours, cubic curves, thin join, small counter, disconnected outline, and intentionally invalid input.
- Unsupported input fails explicitly and produces no output pair.

### Reconstruction

- Every valid fixture produces a canonical collection of fragments and contour parts with no empty contours and no parts below the selected minimum area/edge threshold.
- The union of intact fragments matches the normalized source region within the selected UPM-relative symmetric-difference and boundary-distance tolerances.
- Counters and islands retain the intended fill at specified sample points.
- Repeated runs on supported platforms produce equivalent canonical topology and IDs.

### Compatibility and identity

- Intact and eroded glyphs match in contour/part order, point count/order, segment types, winding convention, width, and stable IDs.
- No eroded fragment is deleted, reduced to zero, or independently re-clipped after motion.
- Serialized and reopened test UFOs retain the same identity mapping and pass the validator.
- Seed derivation is versioned and produces repeatable output for the same canonical inputs and distinct effective seeds for the fixture glyph names.

### Interpolation safety

- At the required sample positions `0, 10, 25, 50, 75, 90, 100`, every contour remains non-empty and above selected area/orientation thresholds, and no transform crosses a singularity.
- Structural compatibility is verified using fontTools-compatible recordings or an equivalent independent checker, not only the generator's internal objects. fontTools provides point/segment pen infrastructure suitable for recording and transforming outlines; see [fontTools pens](https://fonttools.readthedocs.io/en/latest/pens/index.html).
- A generated two-source designspace for the supported fixture glyph set passes an interpolatability check and builds or interpolates successfully with the selected toolchain.
- Visual sheets for all samples are produced for human review; “stone-like,” “recognisable,” and “non-explosive” remain explicit human acceptance items.

### Complexity

- Values `10, 25, 50, 75, 90` map to documented parameter bundles.
- The mapping is deterministic, monotonic for the parameters claimed to be monotonic, bounded by minimum feature size, and completes within selected time/memory budgets.
- The report states whether topology is regenerated or hierarchically refined when complexity changes.
- Density is normalized by a declared measure such as filled area and protected feature constraints; results for narrow and wide fixtures are reported rather than assumed comparable.

### Failure behavior and reporting

- Any failed generation creates no matched output glyph pair in the temporary test outputs.
- The validator emits a machine-readable result plus a readable summary with hard error, interpolation risk, and visual warning classifications.
- Tests report the exact environment, backend versions, fixture list, passed/failed/skipped counts, and do not convert unsupported cases into passing warnings.

Project persistence, source-change detection, paired directory recovery, and RoboFont UI behavior should have separate acceptance criteria in Stages 2A and 3A rather than being required of this prototype.

## 10. Recommended changes to each prompt

| Prompt | Keep | Revise | Move or remove |
| --- | --- | --- | --- |
| `Prompt 1.md` | One topology for both states; persistent identity; deterministic project/glyph seed concept; separation of topology and motion; explicit curve-risk disclosure; structural validation. | Declare backend/input/tolerance/fill policies; model fragment parts and holes; define canonical identity; define measurable reconstruction and interpolation gates; replace subjective automation claims with visual review. | Move repository/bundle setup, project persistence, source fingerprints, production UFO copying, transaction recovery, and most tests to later stages. Reject components initially. |
| `Prompt 2.md` | Standalone isolation review; UFO reuse checks; representative complexity samples; difficult glyph structures; intermediate inspection; severity-ranked verdict; honest test results. | Make it an audit of declared capabilities; define independent tools and thresholds; distinguish structural, geometric, and visual findings; clarify per-glyph versus batch atomicity. | Split corrections into a separate prompt. Do not authorize implementation changes in the same audit. Block production explicitly on an unsuitable verdict. |
| `Prompt 3.md` | Persistent project UX; same two authoritative output UFOs; topology/motion separation; clear regeneration choices; source stale states; explicit component choices; validator severity; per-glyph progress; direct matched-geometry preview. | Add prerequisite gates; define output-open policy, topology storage, schema migration, recovery protocol, UI framework, exact metadata allowlists, glyph-set/build policy, and a smaller first-release surface. | Defer most advanced controls/overlays, character-set selection, elaborate relocation, extensive motion modes, and Glyphs automation. Add them after a minimal production release is proven in RoboFont. |

### Prompt-quality observations

- The prompts are unusually good at repeating the core two-UFO and shared-topology invariants. Repetition has become excessive, however, and should be replaced by a referenced architecture contract shared by all stages.
- “Appropriate,” “relevant,” “safe,” “coherent,” “recognisable,” “related,” “regular,” and “production-ready” are not acceptance criteria. Each needs an allowlist, measurement, fixture, or named human review gate.
- Long feature lists invite Codex to implement breadth without resolving the key algorithm. Each stage should start with explicit non-goals and stop conditions.
- Prompt 1 over-constrains the internal `Fragment` fields before choosing the geometry algorithm, while under-specifying the multi-part/hole structure that correctness actually requires.
- Prompt 2's suggested glyphs and axis positions are useful examples but not a sufficient test design. It should require licensed fixtures and independent validation artifacts.
- Prompt 3's instruction to preserve the tested core is sound only if the prototype has a recorded accepted architecture. Otherwise it may freeze a temporary polygonal experiment into production.
- Test counts alone are not meaningful. The prompts should require exact environment data, failure injection for persistence, independently serialized/reopened UFO checks, and artifact-based visual review.

## 11. Recommended terminology

Use one vocabulary consistently in code, UI, documentation, and filenames:

| Concept | Recommended term | Notes |
| --- | --- | --- |
| Product and extension | **Fracturize** | Proper name only; do not use it as the geometry operation name. |
| Persistent work unit | **fracture project** / `Project` | Owns configuration, output paths, topology records, and glyph statuses. |
| Geometric subdivision | **fracture topology** / `Topology` | The canonical, pre-motion partition and identity graph. “Topology” must not mean merely fragment count. |
| One logical piece | **fragment** / `Fragment` | May contain multiple contour parts and holes. |
| One outline belonging to a fragment | **contour part** | Avoid assuming one contour per fragment. |
| Low-axis output | **intact master** | UI label. In code, `intact`; avoid “State 1.” |
| High-axis output | **eroded master** | UI label. In code, `eroded`; this is a moved/transformed fracture state, not a boolean erosion operation. |
| The pair | **output master pair** | Use “candidate interpolation masters” until designspace validation passes. |
| Persistent UFO paths | **intact output UFO**, **eroded output UFO** | Use “output” for files, “master” for design role. |
| High-level topology detail | **fracture complexity** | Keep the 0–100 UI control. It affects topology, not erosion motion. |
| Amount of displacement/decay | **erosion amount** | Must not change topology. |
| Per-fragment affine change | **fragment transform** | Translation, rotation, positive scaling about a stored origin. |
| Seed hierarchy | **project seed**, **glyph seed**, **seed override** | Specify derivation version; avoid “random seed” when deterministic behavior is meant. |
| Geometry equality target | **normalized source silhouette** | The filled region after the declared component/overlap/fill normalization. |
| Changed source | **stale glyph** | Output remains until a successful replacement. |
| Compatibility | **structural compatibility** | Reserve for contour/point/segment matching; keep “interpolation risk” separate. |

Avoid using **density**, **detail**, and **complexity** as interchangeable control names. Avoid calling hidden fragments “deleted” or “missing.” Avoid calling geometric self-intersection or overlap a topology change unless contour/point structure actually changes.

## 12. Final recommendation

Do not use the prompts as written. Preserve their core invariants, but restructure the workflow into explicit proofs for geometry reconstruction, compatible motion, persistence/recovery, and RoboFont integration. Revise Prompt 1 most aggressively; split Prompt 2 into audit and correction; make Prompt 3 conditional and smaller for its first production milestone.

The extension concept is implementable, but production readiness depends on research and measurements that the current prompts presently treat as implementation details. Begin implementation only after Stage 0 decisions and the narrowed clipping/reconstruction acceptance criteria have been approved.
