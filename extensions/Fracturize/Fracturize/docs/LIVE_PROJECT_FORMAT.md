# Live RoboFont project format

The first extension release writes JSON format `com.fracturize.live-project`, version `1`. This format is intentionally small and has strict open-time type, range, topology-version, and motion-version validation. There is no migration framework.

The root stores:

- a unique project ID, name, timestamps, and generator version;
- source path/identity, UPM, and glyph-set digest;
- intact and eroded working-font IDs, labels, and most recent saved paths;
- validated generation and motion settings;
- topology, seed-derivation, fill, curve, component, and motion policies;
- processed-glyph and failed-glyph maps;
- a private-fixture cleanup marker.

Each processed glyph stores its source fingerprint, both generated-output fingerprints, relative topology path and digest, topology complexity, effective seed, pair revision, component-decomposition decision, motion-algorithm version, and update time.

Canonical topology files live in `<project-stem>-data/topology/` beside the project JSON. They remain separate so motion-only regeneration can reuse exact intact geometry and stable fragment identity.

The working UFOs are not project-owned files. Their font libs contain only the project ID, unique working-font ID, and intact/eroded role required for safe relinking. Processed glyph libs additionally contain stable fragment mapping, pair revision, source fingerprint, and topology digest.

Shared-font validation compares every meaningful font-lib entry except the project-format identity keys above and the exact RoboFont runtime key `com.typemytype.robofont.smartSets.uniqueKey`. RoboFont assigns that Smart Sets identifier independently to each open document, so the values necessarily differ between the intact and eroded windows. No namespace or prefix is ignored: all other user, application, and unexpected `com.fracturize.*` entries must remain equal.

Source fingerprints are conservative open-source-glyph change detectors only. Output fingerprints detect later manual changes to generated outlines. Neither is an ownership or save restriction.

An ordinary exception during a glyph commit restores both prior output glyphs, the previous topology file, and the previous project JSON. This is not a journaled or crash-atomic transaction across open RoboFont documents.
