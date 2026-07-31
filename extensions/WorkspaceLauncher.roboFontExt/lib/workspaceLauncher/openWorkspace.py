import gc
import json
import os

from AppKit import NSApp, NSMakeRect
from Foundation import NSObject
from mojo.events import postEvent
from mojo.roboFont import OpenFont, OpenWindow
from fontTools.designspaceLib import DesignSpaceDocument

from .loadProjectPaths import active_controllers, load_project_paths

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


def install_controller_capture(controller_class):
    """Remember instances constructed by OpenWindow without changing xTools4."""
    if getattr(controller_class, "_workspace_launcher_capture_installed", False):
        return

    original_init = controller_class.__init__

    def capturing_init(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        active_controllers[controller_class.__name__] = self
        print("Workspace Launcher identified controller: %s" % controller_class.__name__)

    controller_class.__init__ = capturing_init
    controller_class._workspace_launcher_capture_installed = True


def install_controller_captures():
    for controller_class in CONTROLLER_CLASSES:
        install_controller_capture(controller_class)


def controller_is_open(controller):
    try:
        window = controller.w.getNSWindow()
    except Exception:
        return False
    return window is not None and window in NSApp.windows()


def get_open_controllers():
    """Return live xTools controllers without opening or identifying by title."""
    controllers_by_class = {}

    for controller_class in CONTROLLER_CLASSES:
        controller = active_controllers.get(controller_class.__name__)
        if controller is not None and controller_is_open(controller):
            controllers_by_class[controller_class] = controller

    missing_classes = set(CONTROLLER_CLASSES).difference(controllers_by_class)
    if missing_classes:
        for candidate in gc.get_objects():
            candidate_class = type(candidate)
            if candidate_class not in missing_classes:
                continue
            if not controller_is_open(candidate):
                continue
            controllers_by_class[candidate_class] = candidate
            active_controllers[candidate_class.__name__] = candidate
            missing_classes.remove(candidate_class)
            print(
                "Workspace Launcher identified open controller: %s"
                % candidate_class.__name__
            )
            if not missing_classes:
                break

    return [
        (controller_class, controllers_by_class.get(controller_class))
        for controller_class in CONTROLLER_CLASSES
    ]


def launch(controller_class):
    # OpenWindow prevents duplicate xTools windows. It returns a boolean, not
    # a controller, so the constructor capture above retains the real object.
    was_already_open = OpenWindow(controller_class)
    controller = active_controllers.get(controller_class.__name__)
    if controller is None:
        print("Workspace Launcher controller unavailable: %s" % controller_class.__name__)
    elif was_already_open:
        print("Workspace Launcher reused controller: %s" % controller_class.__name__)
    else:
        print("Workspace Launcher opened controller: %s" % controller_class.__name__)
    return controller


LAYOUT_PATH = os.path.expanduser(
    "~/Library/Application Support/RoboFont/WorkspaceLauncher/layout.json"
)

CONTROLLER_CLASSES = [
    BlendsPreviewController,
    GlyphMemeController,
    GlyphValidatorController,
    MeasurementsController,
    VarGlyphViewer,
    ImportGlyphsIntoLayerDialog,
    MaskDialog,
]


def load_glyph_validator_designspace(controller, path):
    # This exactly mirrors its file-picker callback without opening a dialog.
    controller.designspacePath = path
    controller.designspace = DesignSpaceDocument()
    controller.designspace.read(controller.designspacePath)
    controller.defaultFont = OpenFont(controller.defaultPath, showInterface=False)
    postEvent("com.xTools4.dialogs.variable.glyphValidator.changed")
    controller.updateFontViewCallback(None)


def load_var_glyph_viewer_default_font(controller, path):
    controller.defaultPath = path
    controller.defaultFont = OpenFont(controller.defaultPath, showInterface=False)
    controller.settingsChangedCallback(None)


def load_blends_preview_reference_font(controller, path):
    controller.referenceFontPath = path
    # The xTools callback has no font-loading method; it enables comparison.
    controller._group1.compare.set(True)


TOOL_RESOURCE_HANDLERS = {
    "BlendsPreviewController": {
        "designspace": ("designspacePath", "_loadDesignspace"),
        "referenceFont": load_blends_preview_reference_font,
    },
    "GlyphMemeController": {
        "designspace": ("designspacePath", "_loadDesignspace"),
    },
    "GlyphValidatorController": {
        "designspace": load_glyph_validator_designspace,
    },
    "MeasurementsController": {
        "designspace": ("designspacePath", "_loadDesignspace"),
    },
    "VarGlyphViewer": {
        "defaultFont": load_var_glyph_viewer_default_font,
    },
}

RESOURCE_EXTENSIONS = {
    "designspace": ".designspace",
    "defaultFont": ".ufo",
    "referenceFont": ".ttf",
}


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

    restored_titles = set()
    for saved_window in saved_windows:
        title = saved_window.get("title")
        if not title:
            continue

        # Old layout files may contain several frames for the same title.
        # There is only one matching live window, so applying each record
        # would repeatedly resize that window and leave it at an arbitrary
        # later frame. New saves are unique, but keep old presets safe too.
        if title in restored_titles:
            print("Workspace Launcher skipped duplicate saved window: %s" % title)
            continue
        restored_titles.add(title)

        window = open_windows.get(title)
        if window is None:
            print("Workspace Launcher could not match saved window: %s" % title)
            continue

        restore_window(window, saved_window)
        print("Workspace Launcher restored window: %s" % title)


def valid_resource_path(resource, path):
    path = os.path.expanduser(path)
    if not os.path.exists(path):
        print("Workspace Launcher: %s not found: %s" % (resource, path))
        return None
    expected_extension = RESOURCE_EXTENSIONS[resource]
    if not path.lower().endswith(expected_extension):
        print(
            "Workspace Launcher: %s has unexpected file type (expected %s): %s"
            % (resource, expected_extension, path)
        )
        return None
    return path


def apply_resource(controller_name, controller, resource, path, handler):
    if callable(handler):
        detail = handler.__name__
    else:
        property_name, loader_name = handler
        detail = "%s + %s" % (property_name, loader_name)
    try:
        if callable(handler):
            handler(controller, path)
        else:
            setattr(controller, property_name, path)
            getattr(controller, loader_name)()
    except Exception as error:
        print(
            "Workspace Launcher: %s failed to load %s via %s: %s"
            % (controller_name, resource, detail, error)
        )
        return
    print("Workspace Launcher applied %s to %s via %s." % (resource, controller_name, detail))


def apply_project_paths(controllers):
    saved_paths = load_project_paths()
    if not saved_paths:
        print("Workspace Launcher found no saved project paths.")
        return

    valid_paths = {}
    for resource, saved_path in saved_paths.items():
        path = valid_resource_path(resource, saved_path)
        if path is not None:
            valid_paths[resource] = path
            print("Workspace Launcher found saved %s path: %s" % (resource, path))

    for controller_class, controller in controllers:
        controller_name = controller_class.__name__
        if controller is None:
            print("Workspace Launcher skipped unavailable controller: %s" % controller_name)
            continue
        handlers = TOOL_RESOURCE_HANDLERS.get(controller_name)
        if not handlers:
            print("Workspace Launcher skipped %s; it has no project path handlers." % controller_name)
            continue
        for resource, path in valid_paths.items():
            handler = handlers.get(resource)
            if handler is None:
                continue
            apply_resource(controller_name, controller, resource, path, handler)


def load_saved_project_resources():
    """Apply saved paths to applicable xTools controllers that are open now."""
    apply_project_paths(get_open_controllers())


class WorkspaceFinisher(NSObject):

    def restoreLayout_(self, sender):
        restore_layout()
        apply_project_paths(self.controllers)


def schedule_workspace_finish(controllers, delay=1.0):
    global _layout_restorer
    _layout_restorer = WorkspaceFinisher.alloc().init()
    _layout_restorer.controllers = controllers
    _layout_restorer.performSelector_withObject_afterDelay_(
        "restoreLayout:", None, delay
    )
    print(
        "Workspace Launcher scheduled layout restore and project setup in %.1f seconds."
        % delay
    )


def open_workspace():
    opened_controllers = []
    install_controller_captures()
    for controller_class in CONTROLLER_CLASSES:
        opened_controllers.append((controller_class, launch(controller_class)))

    schedule_workspace_finish(opened_controllers)
