from mojo.roboFont import OpenWindow

try:
    from xTools4.dialogs.variable.BlendsPreview import BlendsPreviewController
    from xTools4.dialogs.variable.GlyphMeme import GlyphMemeController
    from xTools4.dialogs.variable.GlyphValidator import GlyphValidatorController
    from xTools4.dialogs.variable.Measurements import MeasurementsController
    from xTools4.dialogs.variable.VarGlyphViewer import VarGlyphViewer
    from xTools4.dialogs.glyphs.old.layersImport import ImportGlyphsIntoLayerDialog
    from xTools4.dialogs.glyphs.old.layersMask import MaskDialog
except Exception as error:
    print("Workspace Launcher could not import an xTools4 controller:")
    print(error)
    raise


def launch(controller):
    OpenWindow(controller)


CONTROLLERS = [
    BlendsPreviewController,
    GlyphMemeController,
    GlyphValidatorController,
    MeasurementsController,
    VarGlyphViewer,
    ImportGlyphsIntoLayerDialog,
    MaskDialog,
]


for controller in CONTROLLERS:
    launch(controller)
