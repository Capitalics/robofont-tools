# Run glyph construction recipe for all sources
from glyphConstruction import ParseGlyphConstructionListFromString, GlyphConstructionBuilder
import glob, os
import warnings

# define glyph constructions
txt = '''
# straight
Chedescender-cy = Che + Cy-descendercomb.case@cy_descender ^ Che,Che | 0x4b6
Endescender = H + Cy-descendercomb.case@cy_descender ^ H,H | 0x4a2
Shcha = Sha + Cy-descendercomb.case@cy_descender ^ Sha,Sha | 0x429
chedescender-cy = che + cy-descendercomb@cy_descender | 0x4b7
endescender = en + cy-descendercomb@cy_descender | 0x4a3
shcha = sha + cy-descendercomb@cy_descender | 0x449
tedescender-cy = m + cy-descendercomb@cy_descender | 0x4ad
tse = u + cy-descendercomb@cy_descender | 0x446
# dzhe = u + descenderinverted-cy@cy-descenderinverted | 0x45f

# Te
Tedescender-cy = T + Cy-descendercomb.case@cy_descender_corner | 0x4ac

# diagonal
Hadescender = X + Cy-descendercombdiagonal.case@cy_descender ^ X,X | 0x4b2
Kadescender = Ka + Cy-descendercombdiagonal.case@cy_descender ^ Ka, Ka | 0x49a
Zhedescender = Zhe + Cy-descendercombdiagonal.case@cy_descender ^ Zhe,Zhe | 0x496
hadescender = x + cy-descendercomb@cy_descender_corner | 0x4b3
kadescender = ka + cy-descendercomb@cy_descender_corner | 0x49b
zhedescender = zhe + zhe-descendercomb@cy_descender | 0x497

# shared Tse/tse and Dzhe/dzhe base
Tse = TseDzhe-base.case + Cy-descendercomb.case@cy_descender ^ TseDzhe-base.case,TseDzhe-base.case | 0x426
Dzhe = TseDzhe-base.case + Dzhe-descendercomb.case@dzhe_descender | 0x40F

# Bulgarian forms
shcha.bgr = sha + cy-descendercomb@cy_descender | None
tse.bgr = u + cy-descendercomb@cy_descender | None
'''

subFamily = ['Roman', 'Italic'][1]
baseFolder = '/Users/tdbk/REPOS/amstelvar-avar2'
sourcesFolder = os.path.join(baseFolder, 'Sources', subFamily,)
tuningSourcesFolder = os.path.join(sourcesFolder, 'tuning')
referenceSourcesFolder = os.path.join(sourcesFolder, 'reference')

# get the actual glyph constructions from text
constructions = ParseGlyphConstructionListFromString(txt)

parametricUFOs = glob.glob(os.path.join(sourcesFolder, '*.ufo'))
tuningUFOs = glob.glob(os.path.join(tuningSourcesFolder, '*.ufo'))
referenceUFOs = glob.glob(os.path.join(referenceSourcesFolder, '*.ufo'))

ufoPaths = referenceUFOs
# ufoPaths = parametricUFOs

failures = []
constructionWarnings = []

for sourcePath in ufoPaths:
    sourceName = os.path.splitext(os.path.basename(sourcePath))[0]
    font = None

    try:
        font = OpenFont(sourcePath, showInterface=False)

        for construction in constructions:
            if not construction:
                continue

            glyphName = construction.split("=", 1)[0].strip()

            caughtWarnings = []

            try:
                with warnings.catch_warnings(record=True) as caughtWarnings:
                    warnings.simplefilter("always")

                    constructionGlyph = GlyphConstructionBuilder(construction, font)

                    glyph = font.newGlyph(constructionGlyph.name, clear=True)
                    constructionGlyph.draw(glyph.getPen())

                    glyph.name = constructionGlyph.name
                    glyph.unicode = constructionGlyph.unicode
                    glyph.width = constructionGlyph.width

                print(f"Construction built for /{glyph.name} in {sourceName}")

            except Exception as error:
                failures.append((
                    sourceName,
                    glyphName,
                    type(error).__name__,
                    str(error),
                ))

            for warning in caughtWarnings:
                constructionWarnings.append((
                    sourceName,
                    glyphName,
                    warning.category.__name__,
                    str(warning.message),
                ))

    except Exception as error:
        failures.append((
            sourceName,
            "[opening font]",
            type(error).__name__,
            str(error),
        ))

    finally:
        if font is not None:
            try:
                font.close(save=True)
            except Exception as error:
                failures.append((
                    sourceName,
                    "[saving font]",
                    type(error).__name__,
                    str(error),
                ))

print("\n" + "=" * 60)
print("GLYPH CONSTRUCTION REPORT")
print("=" * 60)

if failures:
    print(f"\nERRORS: {len(failures)}")
    for sourceName, glyphName, errorType, message in failures:
        print(f"- {sourceName} — /{glyphName}")
        print(f"  {errorType}: {message}")
else:
    print("\nERRORS: none")

if constructionWarnings:
    print(f"\nWARNINGS: {len(constructionWarnings)}")
    for sourceName, glyphName, warningType, message in constructionWarnings:
        print(f"- {sourceName} — /{glyphName}")
        print(f"  {warningType}: {message}")
else:
    print("\nWARNINGS: none")
    

#UC ROMAN
# Dze = S | 0x405
# Iukran = I | 0x406
# Yi = I + dieresiscomb.case@top | 0x407
# Je = J | 0x408
# Acyr = A | 0x0410
# Abrevecyr = A + breve.cyrcomb.case@top | 0x04D0
# Adieresiscyr = A + dieresiscomb.case@top | 0x04D2
# Ve = B | 0x0412
# Ghe = Gamma | 0x413
# Gje = Gamma + acutecomb.case@top | 0x0403
# Ie = E | 0x0415
# Io = E + dieresiscomb.case@top | 0x0401
# Iebrevecyr = E + breve.cyrcomb.case@top | 0x04D6
# Zhebrevecyr = Zhe + breve.cyrcomb.case@top | 04C1
# Zhedieresiscyr = Zhe + dieresiscomb.case@top | 04DC
# Igravecyr = Icyr + gravecomb.case@top | 0x040D
# Ishort = Icyr + breve.cyrcomb.case@top | 0x0419
# Kje = Ka + acutecomb.case@top | 0x040C
# Em = M | 0x41c
# En = H | 0x41d
# Ocyr = O | 0x41e
# Odieresiscyr = O + dieresiscomb.case@top | 0x4e6
# Pe = Pi | 0x041F
# Er = P | 0x420
# Es = C | 0x421
# Te = T | 0x422
# Ushort = Ucyr + breve.cyrcomb.case@top | 0x40e
# Umacroncyr = Ucyr + macroncomb.case@top | 0x4ee
# Udieresiscyr = Ucyr + dieresiscomb.case@top | 0x4f0
# Uhungarumlautcyr = Ucyr + hungarumlautcomb.case@57%,top | 0x4f2
# Ha = X | 0x425
# Yeru = Soft & I | 0x042B
# Yeru = Soft + I@Yeru_I ^ Soft,I | 0x042B
# Yu = I + Yu-dash.case@yu_dash + O@yu_dash ^ I,O | 0x042E
# Ghestroke = Gamma + horizontalbar@center | 0x0492
# Zedescendercyr = Ze + cedillacomb.case@bottom | 0x498
# Esdescendercyr = C + cedillacomb.case@bottom | 0x4aa
# Ustraight = Y | 0x4ae
# Ustraightstroke = Y + U-stroke@center | 0x4B0
# Palochka = I | 0x04C0
# Obarcyr = O + Obarcyr-stroke@center | 0x04E8
# Hastroke-cy = X + Ha-stroke@center | 0x04FE
# Ka.bgr = K | None
# El.bgr = Lambda | None
# Amacroncyr = A + macroncomb.case@top | 0xf50e
# Iemacroncyr = E + macroncomb.case@top | 0xf510
# Omacroncyr = O + macroncomb.case@top | 0xf518
# Obrevecyr = O + breve.cyrcomb.case@top | 0xf51a
# Emacroncyr = Ecyr + macroncomb.case@top | 0xf522
# Ebrevecyr = Ecyr + breve.cyrcomb.case@top | 0xf524
# Yamacron = Ya + macroncomb.case@top | 0xf528
# Yumacron = I + Yu-dash.case@yu_dash + O@yu_dash + macroncomb.case@Yu:center,top ^ I,O | 0xf52c


#LC ROMAN
# acyr = a | 0x430
# abrevecyr = a + breve.cyrcomb@top | 0x4d1
# adieresiscyr = a + dieresiscomb@top | 0x4d3
# gje = ghe + acutecomb@top | 0x453
# ie = e | 0x435
# io = e + dieresiscomb@top | 0x451
# iebrevecyr = e + breve.cyrcomb@top | 0x4d7
# zhebrevecyr = zhe + breve.cyrcomb@top | 0x4c2
# zhedieresiscyr = zhe + dieresiscomb@top | 0x4dd
# ishort = icyr + breve.cyrcomb@top | 0x439
# igravecyr = icyr + gravecomb@top | 0x45d
# kje = ka + acutecomb@top | 0x45c
# ocyr = o | 0x043E
# odieresiscyr = o + dieresiscomb@top | 0x4e7
# er = p | 0x0440
# es = c | 0x0441
# ucyr = y | 0443
# ushort = y + breve.cyrcomb@top | 0x45e
# umacroncyr = y + macroncomb@top | 0x4ef
# udieresiscyr = y + dieresiscomb@top | 0x4f1
# uhungarumlautcyr = y + hungarumlautcomb@57%,top | 0x4f3
# ha = x | 0x445
# yeru = soft + yu-i@yeru_i ^ soft,yu-i | 0x044B
# yu = yu-i + yu.bgr-stroke@yu_dash + o@yu_dash ^ yu-i,o | 0x044E
# dze = s | 0x455
# iukran = idotless + idot@top | 0x456
# yi = idotless + yi-dieresiscomb@top | 0x457
# je = jdotless + idot@top | 0x458
# tshe = h + horizontalbarlc@center | 0x045B
# ghestroke = ghe + horizontalbarlc@center | 0x493
# zedescendercyr = ze + cedillacomb@bottom | 0x499
# esdescendercyr = c + cedillacomb@bottom | 0x4ab
# ustraightstroke = ustraight + ustraight-stroke@center | 0x4b1
# shha = h | 0x4bb
# palochka = l | 0x4cf
# schwacyr = schwa | 0x4d9
# obarcyr = o + obarcyr-stroke@center | 0x04E9
# hastroke-cy = x + ha-stroke@center | 0x04FF
# igrave.bgr = u + gravecomb@top | None
# ka.bgr = k | None
# pe.bgr = n | None
# te.bgr = m | None
# yu.bgr = l + yu.bgr-stroke@yu_dash + o@yu_dash ^ l,o | None
# ishort.bgr = u + breve.cyrcomb@top | None
# ghe.locl = ghe | None
# de.locl = de | None
# pe.locl = pe | None
# te.locl = te | None
# amacroncyr = a + macroncomb@top | 0xf50f
# iemacroncyr = e + macroncomb@top | 0xf511
# omacroncyr = o + macroncomb@top | 0xf519
# obrevecyr = o + breve.cyrcomb@top | 0xf51b
# emacroncyr = ecyr + macroncomb@top | 0xf523
# ebrevecyr = ecyr + breve.cyrcomb@top | 0xf525
# yamacron = ya + macroncomb@top | 0xf529
# yumacron = yu-i + yu.bgr-stroke@yu_dash + o@yu_dash + macroncomb@yu:center,top  ^ yu-i,o | 0xf52d
# i.bgr = u | None


#ROMAN CY_DESCENDER
# Shcha = Sha + Cy-descendercomb.case@cy_descender ^ Sha, Sha+20  | 0x429
# Zhedescender = Zhe + Cy-descendercomb.case@cy_descender ^ Zhe, Zhe+20 | 0x496
# Kadescender = Ka + Cy-descendercomb.case@cy_descender ^ Ka, Ka+20 | 0x49a
# Endescender = H + Cy-descendercomb.case@cy_descender ^ H, H+20 | 0x4a2
# Tedescender-cy = T + Cy-descendercomb.case@cy_descender | 0x4ac
# Hadescender = X + Cy-descendercomb.case@cy_descender ^ X, X+20 | 0x4b2
# Chedescender-cy = Che + Cy-descendercomb.case@cy_descender ^ Che, Che+20 | 0x4b6

# shcha = sha + cy-descendercomb@cy_descender ^ sha, sha+20 | 0x449
# zhedescender = zhe + cy-descendercomb@cy_descender  ^ zhe, zhe+20 | 0x497
# kadescender = ka + cy-descendercomb@cy_descender ^ ka, ka+20 | 0x49b
# endescender = en + cy-descendercomb@cy_descender ^ en, en+20 | 0x4a3
# tedescender-cy = te + cy-descendercomb@cy_descender ^ te, te+20  | 0x4ad
# hadescender = x + cy-descendercomb@cy_descender ^ x, x+20 | 0x4b3
# chedescender-cy = che + cy-descendercomb@cy_descender ^ che, che+20 | 0x4b7
# tse.bgr = u + cy-descendercomb@cy_descender ^ u, u+20 | None
# shcha.bgr = sha.bgr + cy-descendercomb@cy_descender ^ sha.bgr, sha.bgr+20 | None


#ROMAN CY_DESCENDER NEW

# #straight
# Chedescender-cy = Che + Cy-descendercomb.case@cy_descender ^ Che, Che-10 | 0x04b6
# Endescender = H + Cy-descendercomb.case@cy_descender ^ H, H-10 | 0x04a2
# Shcha = Sha + Cy-descendercomb.case@cy_descender ^ Sha, Sha-10 | 0x0429
# chedescender-cy = che + cy-descendercomb@cy_descender ^ che, che-10 | 0x04b7
# endescender = en + cy-descendercomb@cy_descender ^ en, en-10 | 0x04a3
# shcha = sha + cy-descendercomb@cy_descender ^ sha, sha-10 | 0x0449

# #Te and te
# Tedescender-cy = T + Cy-descendercomb.case@cy_descender_corner | 0x04ac
# tedescender-cy = te + cy-descendercomb@cy_descender_corner | 0x04ad

# #diagonal
# Hadescender = X + Cy-descendercombdiagonal.case@cy_descender_corner ^ X, X-10 | 0x04b2
# Kadescender = Ka + Cy-descendercombdiagonal.case@cy_descender ^ Ka, Ka-10 | 0x049a
# Zhedescender = Zhe + Cy-descendercombdiagonal.case@cy_descender ^ Zhe, Zhe-10 | 0x0496
# hadescender = x + cy-descendercomb.diagonal@cy_descender_corner ^ x, x-10 | 0x04b3
# kadescender = ka + cy-descendercomb.diagonal@cy_descender ^ ka, ka-10 | 0x049b
# zhedescender = zhe + cy-descendercomb.diagonal@cy_descender ^ zhe, zhe-10 | 0x0497

# #bulgarian
# tse.bgr = u + cy-descendercomb.bgr@cy_descender ^ u, u-10 | None
# shcha.bgr = sha.bgr + cy-descendercomb.bgr@cy_descender ^ sha.bgr, sha.bgr-10 | None

# #shared Tse/tse and Dzhe/dzhe base
# Tse = TseDzhe-base.case + Cy-descendercomb.case@cy_descender ^ TseDzhe-base.case, TseDzhe-base.case-10 | 0x0426
# Dzhe = TseDzhe-base.case + Dzhe-descendercomb.case@dzhe_descender | 0x040f
# tse = tsedzhe-base + cy-descendercomb@cy_descender ^ tsedzhe-base, tsedzhe-base-10 | 0x0446
# dzhe = tsedzhe-base + dzhe-descendercomb@dzhe_descender | 0x045f


#UC ITALIC
# Dze = S | 0x405
# Iukran = I | 0x406
# Yi = I + dieresiscomb.case@top | 0x407
# Je = J | 0x408
# Acyr = A | 0x0410
# Abrevecyr = A + breve.cyrcomb.case@top | 0x04D0
# Adieresiscyr = A + dieresiscomb.case@top | 0x04D2
# Ve = B | 0x0412
# Ghe = Gamma | 0x413
# Gje = Gamma + acutecomb.case@top | 0x0403
# Ie = E | 0x0415
# Io = E + dieresiscomb.case@top | 0x0401
# Iebrevecyr = E + breve.cyrcomb.case@top | 0x04D6
# Zhebrevecyr = Zhe + breve.cyrcomb.case@top | 04C1
# Zhedieresiscyr = Zhe + dieresiscomb.case@top | 04DC
# Igravecyr = Icyr + gravecomb.case@top | 0x040D
# Ishort = Icyr + breve.cyrcomb.case@top | 0x0419
# Kje = Ka + acutecomb.case@top | 0x040C
# Em = M | 0x41c
# En = H | 0x41d
# Ocyr = O | 0x41e
# Odieresiscyr = O + dieresiscomb.case@top | 0x4e6
# Pe = Pi | 0x041F
# Er = P | 0x420
# Es = C | 0x421
# Te = T | 0x422
# Ushort = Ucyr + breve.cyrcomb.case@top | 0x40e
# Umacroncyr = Ucyr + macroncomb.case@top | 0x4ee
# Udieresiscyr = Ucyr + dieresiscomb.case@top | 0x4f0
# Uhungarumlautcyr = Ucyr + hungarumlautcomb.case@57%,top | 0x4f2
# Ha = X | 0x425
# Yeru = Soft & I | 0x042B
# Yu = I + Yu-dash.case@yu_dash + O@yu_dash ^ I,O | 0x042E
# Ghestroke = Gamma + horizontalbar@center | 0x0492
# Zedescendercyr = Ze + cedillacomb.case@bottom | 0x498
# Esdescendercyr = C + cedillacomb.case@bottom | 0x4aa
# Ustraight = Y | 0x4ae
# Ustraightstroke = Y + U-stroke@center | 0x4B0
# Palochka = I | 0x04C0
# Obarcyr = O + Obarcyr-stroke@center | 0x04E8
# Hastroke-cy = X + Ha-stroke@center | 0x04FE
# Ka.bgr = K | None
# El.bgr = Lambda | None
# Amacroncyr = A + macroncomb.case@top | 0xf50e
# Iemacroncyr = E + macroncomb.case@top | 0xf510
# Omacroncyr = O + macroncomb.case@top | 0xf518
# Obrevecyr = O + breve.cyrcomb.case@top | 0xf51a
# Emacroncyr = Ecyr + macroncomb.case@top | 0xf522
# Ebrevecyr = Ecyr + breve.cyrcomb.case@top | 0xf524
# Yamacron = Ya + macroncomb.case@top | 0xf528
# Yumacron = I + Yu-dash.case@yu_dash + O@yu_dash + macroncomb.case@Yu:center,top ^ I,O | 0xf52c


#LC ITALIC
# acyr = a | 0x430
# abrevecyr = a + breve.cyrcomb@top | 0x4d1
# adieresiscyr = a + dieresiscomb@top | 0x4d3
# gje = ghe + acutecomb@top | 0x453
# ie = e | 0x435
# io = e + dieresiscomb@top | 0x451
# iebrevecyr = e + breve.cyrcomb@top | 0x4d7
# zhebrevecyr = zhe + breve.cyrcomb@top | 0x4c2
# zhedieresiscyr = zhe + dieresiscomb@top | 0x4dd
# icyr = u | 0x0438
# ishort = u + breve.cyrcomb@top | 0x439
# igravecyr = u + gravecomb@top | 0x45d
# kje = ka + acutecomb@top | 0x45c
# ocyr = o | 0x043E
# odieresiscyr = o + dieresiscomb@top | 0x4e7
# pe = n | 0x43f
# er = p | 0x0440
# es = c | 0x0441
# te = m | 0x442
# ucyr = y | 0443
# ushort = y + breve.cyrcomb@top | 0x45e
# umacroncyr = y + macroncomb@top | 0x4ef
# udieresiscyr = y + dieresiscomb@top | 0x4f1
# uhungarumlautcyr = y + hungarumlautcomb@57%,top | 0x4f3
# ha = x | 0x445
# yeru = soft & idotless | 0x044B
# yu = yu-i + yu.bgr-stroke@yu_dash + o@yu_dash ^ yu-i,o | 0x044E
# dze = s | 0x455
# iukran = idotless + idot@top | 0x456
# yi = idotless + yi-dieresiscomb@top | 0x457
# je = jdotless + idot@top | 0x458
# tshe = h + horizontalbarlc@center | 0x045B
# dzhe = u + descenderinverted-cy@cy-descenderinverted | 0x45f
# ghestroke = ghe + horizontalbarlc@center | 0x493
# zedescendercyr = ze + cedillacomb@bottom | 0x499
# esdescendercyr = c + cedillacomb@bottom | 0x4ab
# ustraightstroke = ustraight + ustraight-stroke@center | 0x4b1
# shha = h | 0x4bb
# palochka = l | 0x4cf
# schwacyr = schwa | 0x4d9
# obarcyr = o + obarcyr-stroke | 0x04E9
# hastroke-cy = x + ha-stroke@center | 0x04FF
# ghe.bgr = ghe | None
# de.bgr = g | None
# igrave.bgr = u + gravecomb@top | None
# ka.bgr = k | None
# el.bgr = el | None
# en.bgr = en | None
# pe.bgr = n | None
# te.bgr = m | None
# che.bgr = che | None
# sha.bgr = sha | None
# hard.bgr = hard | None
# soft.bgr = soft | None
# yu.bgr = yu-l.bgr + yu.bgr-stroke@yu_dash + o@yu_dash ^ yu-l.bgr,o | None
# ishort.bgr = u + breve.cyrcomb@top | None
# ghe.locl = idotless + macroncomb@top | None
# de.locl = g | None
# pe.locl = u + macroncomb@top | None
# te.locl = sha + macroncomb@top | None
# amacroncyr = a + macroncomb@top | 0xf50f
# iemacroncyr = e + macroncomb@top | 0xf511
# omacroncyr = o + macroncomb@top | 0xf519
# obrevecyr = o + breve.cyrcomb@top | 0xf51b
# emacroncyr = ecyr + macroncomb@top | 0xf523
# ebrevecyr = ecyr + breve.cyrcomb@top | 0xf525
# yamacron = ya + macroncomb@top | 0xf529
# yumacron = yu-i + yu.bgr-stroke@yu_dash + o@yu_dash + macroncomb@yu:center,top  ^ yu-i,o | 0xf52d
# i.bgr = u | None


#ITALIC CY_DESCENDER
# Shcha = Sha + Cy-descendercomb.case@cy_descender | 0x429
# Zhedescender = Zhe + Cy-descendercomb.case@cy_descender | 0x496
# Kadescender = Ka + Cy-descendercomb.case@cy_descender | 0x49a
# Endescender = H + Cy-descendercomb.case@cy_descender | 0x4a2
# Tedescender-cy = T + Cy-descendercomb.case@cy_descender | 0x4ac
# Hadescender = X + Cy-descendercomb.case@cy_descender | 0x4b2
# Chedescender-cy = Che + Cy-descendercomb.case@cy_descender | 0x4b6

# tse = u + cy-descendercomb@cy_descender | 0x446
# shcha = sha + cy-descendercomb@cy_descender | 0x449
# zhedescender = zhe + cy-descendercomb@cy_descender | 0x497
# kadescender = ka + cy-descendercomb@cy_descender | 0x49b
# endescender = en + cy-descendercomb@cy_descender | 0x4a3
# tedescender-cy = m + cy-descendercomb@cy_descender | 0x4ad
# hadescender = x + cy-descendercomb@cy_descender | 0x4b3
# chedescender-cy = che + cy-descendercomb@cy_descender | 0x4b7
# tse.bgr = u + cy-descendercomb@cy_descender | None
# shcha.bgr = sha + cy-descendercomb@cy_descender | None


#ITALIC CY_DESCENDER NEW

# # straight
# Chedescender-cy = Che + Cy-descendercomb.case@cy_descender ^ Che,Che | 0x4b6
# Endescender = H + Cy-descendercomb.case@cy_descender ^ H,H | 0x4a2
# Shcha = Sha + Cy-descendercomb.case@cy_descender ^ Sha,Sha | 0x429
# chedescender-cy = che + cy-descendercomb@cy_descender | 0x4b7
# endescender = en + cy-descendercomb@cy_descender | 0x4a3
# shcha = sha + cy-descendercomb@cy_descender | 0x449
# tedescender-cy = m + cy-descendercomb@cy_descender | 0x4ad
# tse = u + cy-descendercomb@cy_descender | 0x446
# dzhe = u + descenderinverted-cy@cy-descenderinverted | 0x45f

# # Te
# Tedescender-cy = T + Cy-descendercomb.case@cy_descender_corner | 0x4ac

# # diagonal
# Hadescender = X + Cy-descendercombdiagonal.case@cy_descender ^ X,X | 0x4b2
# Kadescender = Ka + Cy-descendercombdiagonal.case@cy_descender ^ Ka, Ka | 0x49a
# Zhedescender = Zhe + Cy-descendercombdiagonal.case@cy_descender ^ Zhe,Zhe | 0x496
# hadescender = x + cy-descendercomb@cy_descender_corner | 0x4b3
# kadescender = ka + cy-descendercomb@cy_descender_corner | 0x49b
# zhedescender = zhe + zhe-descendercomb@cy_descender | 0x497

# # shared Tse/tse and Dzhe/dzhe base
# Tse = TseDzhe-base.case + Cy-descendercomb.case@cy_descender ^ TseDzhe-base.case,TseDzhe-base.case | 0x426
# Dzhe = TseDzhe-base.case + Dzhe-descendercomb.case@dzhe_descender | 0x40F

# # Bulgarian forms
# shcha.bgr = sha + cy-descendercomb@cy_descender | None
# tse.bgr = u + cy-descendercomb@cy_descender | None




































