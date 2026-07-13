# Manual designspace handoff

The intact and eroded UFOs are candidate interpolation masters, not a finished variable-font export. Save both through RoboFont, validate the Fracturize project, and keep the UFOs together with a manually authored designspace file using relative source paths.

A minimal two-source designspace can use a development axis such as:

```xml
<axis tag="EROD" name="Erosion" minimum="0" default="0" maximum="1000"/>
<source filename="MyProject-Intact.ufo" name="intact">
  <location><dimension name="Erosion" xvalue="0"/></location>
</source>
<source filename="MyProject-Eroded.ufo" name="eroded">
  <location><dimension name="Erosion" xvalue="1000"/></location>
</source>
```

`EROD` is an experimental internal tag, not an automatically suitable registered axis for final distribution. Decide the final axis model and naming separately.

Before a test build:

1. Run Fracturize validation with all three project fonts open.
2. Run a standard interpolatability check on the saved UFO pair.
3. Sample intermediate locations, not only the endpoints.
4. Build a disposable test variable font with fontTools/fontmake or the project's established build tool.
5. Inspect spacing, sidebearing overhangs, counters, anchors, and shaping behavior.

Because project creation duplicates the full source twice, unprocessed glyphs remain identical static glyphs at both sources. Processed glyphs use compatible line-only contours with stable identifiers. Widths, vertical metrics, Unicode values, anchors, notes, kerning, groups, feature code, font info, libs, layers, guidelines, data, and images start as complete source copies and are expected to stay synchronized. Selected component glyphs are decomposed in both generated outputs after confirmation.

Manual import of the two UFOs into Glyphs may be attempted, but no Glyphs version or round-trip has been validated. Import can alter identifiers, layers, components, metadata, or interpolation behavior; extensive Glyphs instructions and automation are deferred.

