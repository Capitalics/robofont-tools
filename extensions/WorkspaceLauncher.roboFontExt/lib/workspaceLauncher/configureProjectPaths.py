from mojo.UI import GetFile
from vanilla import Button, EditText, FloatingWindow, TextBox

from .loadProjectPaths import (
    clear_project_path,
    load_project_paths,
    save_project_paths,
)


RESOURCE_ROWS = (
    ("designspace", "Designspace", ["designspace"]),
    ("defaultFont", "Default font", ["ufo"]),
    ("referenceFont", "Reference font", ["ttf"]),
)


class ConfigureProjectPathsController:

    def __init__(self):
        self.w = FloatingWindow(
            (650, 180),
            "Configure Project Paths",
            minSize=(520, 170),
        )
        self.fields = {}
        self._build()
        self._load()
        self.w.bind("close", self.window_close_callback)
        self.w.open()

    def _build(self):
        for index, (resource, label, file_types) in enumerate(RESOURCE_ROWS):
            y = 12 + index * 38
            self.w.__setattr__("%sLabel" % resource, TextBox((12, y + 4, 100, 20), label))
            field = EditText((112, y, -164, 22), "")
            self.w.__setattr__("%sField" % resource, field)
            self.fields[resource] = field
            self.w.__setattr__(
                "%sChoose" % resource,
                Button((-156, y, 88, 22), "Choose…", callback=self._choose_callback(resource, label, file_types)),
            )
            self.w.__setattr__(
                "%sClear" % resource,
                Button((-62, y, 50, 22), "Clear", callback=self._clear_callback(resource)),
            )
        self.w.save = Button((-156, -32, 70, 22), "Save", callback=self.save_callback)
        self.w.closeButton = Button(
            (-78, -32, 66, 22),
            "Close",
            callback=self.close_callback,
        )

    def _load(self):
        for resource, value in load_project_paths().items():
            self.fields[resource].set(value)

    def _choose_callback(self, resource, label, file_types):
        def callback(sender):
            selected_path = GetFile(
                message="Select %s:" % label.lower(),
                title="Configure Project Paths",
                allowsMultipleSelection=False,
                fileTypes=file_types,
            )
            if selected_path is None:
                return
            self.fields[resource].set(selected_path)
            save_project_paths({resource: selected_path})
            print("Workspace Launcher saved %s path: %s" % (resource, selected_path))
        return callback

    def _clear_callback(self, resource):
        def callback(sender):
            self.fields[resource].set("")
            clear_project_path(resource)
            print("Workspace Launcher cleared %s path." % resource)
        return callback

    def save_callback(self, sender):
        paths = {resource: field.get().strip() for resource, field in self.fields.items()}
        saved = save_project_paths(paths)
        print("Workspace Launcher saved project paths: %s" % ", ".join(sorted(saved)))

    def close_callback(self, sender):
        self.w.close()

    def window_close_callback(self, sender):
        _configuration_window_closed(self)


_configuration_controller = None


def _configuration_window_closed(controller):
    global _configuration_controller
    if _configuration_controller is controller:
        _configuration_controller = None


def show_configure_project_paths():
    global _configuration_controller
    if _configuration_controller is not None:
        ns_window = _configuration_controller.w.getNSWindow()
        if ns_window.isVisible():
            ns_window.makeKeyAndOrderFront_(None)
            return _configuration_controller
    _configuration_controller = ConfigureProjectPathsController()
    return _configuration_controller
