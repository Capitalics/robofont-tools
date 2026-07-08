import json
import os

from AppKit import NSApp, NSMakeRect
from Foundation import NSObject
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


LAYOUT_PATH = os.path.expanduser(
    "~/Library/Application Support/RoboFont/WorkspaceLauncher/layout.json"
)

CONTROLLERS = [
    BlendsPreviewController,
    GlyphMemeController,
    GlyphValidatorController,
    MeasurementsController,
    VarGlyphViewer,
    ImportGlyphsIntoLayerDialog,
    MaskDialog,
]


def get_window_title(window):
    title = window.title()
    if not title:
        return None
    return str(title)


def get_titled_windows():
    windows = {}
    for window in NSApp.windows():
        title = get_window_title(window)
        if title and title not in windows:
            windows[title] = window
    return windows


def load_layout(path=LAYOUT_PATH):
    print("Workspace Launcher layout path: %s" % path)
    if not os.path.exists(path):
        print("Workspace Launcher layout file does not exist; skipping restore.")
        return []

    with open(path) as layout_file:
        layout = json.load(layout_file)

    windows = layout.get("windows", [])
    print("Workspace Launcher loaded %s saved windows." % len(windows))
    return windows


def restore_window(window, saved_window):
    frame = NSMakeRect(
        float(saved_window["x"]),
        float(saved_window["y"]),
        float(saved_window["width"]),
        float(saved_window["height"]),
    )
    window.setFrame_display_(frame, True)


def restore_layout():
    saved_windows = load_layout()
    if not saved_windows:
        return

    open_windows = get_titled_windows()
    open_titles = sorted(open_windows.keys())
    print("Workspace Launcher open windows before restore:")
    for title in open_titles:
        print("  - %s" % title)

    for saved_window in saved_windows:
        title = saved_window.get("title")
        if not title:
            continue

        window = open_windows.get(title)
        if window is None:
            print("Workspace Launcher could not match saved window: %s" % title)
            continue

        restore_window(window, saved_window)
        print("Workspace Launcher restored window: %s" % title)


class LayoutRestorer(NSObject):

    def restoreLayout_(self, sender):
        restore_layout()


def schedule_layout_restore(delay=1.0):
    global _layout_restorer
    _layout_restorer = LayoutRestorer.alloc().init()
    _layout_restorer.performSelector_withObject_afterDelay_(
        "restoreLayout:", None, delay
    )
    print("Workspace Launcher scheduled layout restore in %.1f seconds." % delay)


for controller in CONTROLLERS:
    launch(controller)

schedule_layout_restore()
