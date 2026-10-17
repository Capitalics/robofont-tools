# Align named anchors to baseline
# and horizontally between two contour points.
import glob, os

from math import radians, tan

subFamily = ['Roman', 'Italic'][0]
baseFolder = '/Users/tdbk/REPOS/amstelvar-avar2'
sourcesFolder = os.path.join(baseFolder, 'Sources', subFamily,)
tuningSourcesFolder = os.path.join(sourcesFolder, 'tuning')
referenceSourcesFolder = os.path.join(sourcesFolder, 'reference')

settings = [
    # glyph name, anchor name, contour index, point 1 index, point 2 index
    # ("Zhe", "cy_descender", 2, 7, 2),
    # ("Ka", "cy_descender", 2, 7, 2),
    # ("H", "cy_descender", 2, 2, 11),
    # ("T", "cy_descender", 0, 14, 9),
    # ("TseDzhe-base.case", "cy_descender", 0, 14, 23),
    # ("Sha", "cy_descender", 0, 2, 11),
    # ("Che", "cy_descender", 1, 2, 11),
    # ("X", "cy_descender", 0, 26, 21),

    # Lowercase
    # ("u", "cy_descender", 0, 2, 8),
    # ("en", "cy_descender", 1, 1, 8),
    # ("sha", "cy_descender", 2, 2, 8),
    # ("m", "cy_descender", 2, 1, 16),
    # ("che", "cy_descender", 1, 1, 8),
    ("ka", "cy_descender", 2, 7, 2)
]


parametricUFOs = glob.glob(os.path.join(sourcesFolder, '*.ufo'))
tuningUFOs = glob.glob(os.path.join(tuningSourcesFolder, '*.ufo'))
referenceUFOs = glob.glob(os.path.join(referenceSourcesFolder, '*.ufo'))

ufoPaths = referenceUFOs

def projectToBaseline(p1, p2, italicAngle, baselineY=0):
    x = (p1.x + p2.x) / 2
    y = (p1.y + p2.y) / 2

    return (
        x + (y - baselineY) * tan(radians(italicAngle)),
        baselineY,
    )

for ufoPath in ufoPaths:
    fontChanged = False
    font = OpenFont(ufoPath, showInterface=False)
    
    for glyphName, anchorName, contourIndex, pointIndex1, pointIndex2 in settings:

        if glyphName not in font:
            print(f"Missing glyph: /{glyphName}")
            continue

        glyph = font[glyphName]

        if contourIndex >= len(glyph.contours):
            print(f"/{glyphName}: contour {contourIndex} does not exist")
            continue

        contour = glyph.contours[contourIndex]

        if pointIndex1 >= len(contour.points) or pointIndex2 >= len(contour.points):
            print(
                f"/{glyphName}: invalid point indices "
                f"{pointIndex1}, {pointIndex2}"
            )
            continue

        p1 = contour.points[pointIndex1]
        p2 = contour.points[pointIndex2]

        # Find named anchor
        anchor = None

        for a in glyph.anchors:
            if a.name == anchorName:
                anchor = a
                break

        if anchor is None:
            print(f"/{glyphName}: anchor '{anchorName}' not found")
            continue

        # Position anchor
        x, _ = projectToBaseline(
            p1,
            p2,
            font.info.italicAngle or 0,
        )
            
        anchor.x = round(x)
        anchor.y = 0
        fontChanged = True
        
        glyph.changed()

        print(
            f"/{glyphName}: {anchorName} -> "
            f"({anchor.x}, {anchor.y})"
        )
        
    font.close(save=fontChanged)