from AppKit import NSApp, NSMenu, NSMenuItem
from Foundation import NSObject

from .configureProjectPaths import show_configure_project_paths
from .openWorkspace import (
    install_controller_captures,
    load_saved_project_resources,
    open_workspace,
)
from .saveLayout import save_layout


MENU_TITLE = "Workspace Launcher"


class WorkspaceLauncherMenuTarget(NSObject):

    def openWorkspace_(self, sender):
        open_workspace()

    def loadProjectPaths_(self, sender):
        load_saved_project_resources()

    def configureProjectPaths_(self, sender):
        show_configure_project_paths()

    def saveLayout_(self, sender):
        save_layout()


def _menu_item(title, action, target):
    item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(title, action, "")
    item.setTarget_(target)
    return item


def _remove_existing_menu_items(main_menu):
    # Remove only our own top-level entries, including duplicates left behind
    # by development reloads. Iterating backwards keeps indices stable.
    for index in range(main_menu.numberOfItems() - 1, -1, -1):
        item = main_menu.itemAtIndex_(index)
        if str(item.title()) == MENU_TITLE:
            main_menu.removeItemAtIndex_(index)


def install_workspace_launcher_menu():
    global _menu_target

    # Capture xTools controllers even when their panels are opened manually.
    install_controller_captures()

    main_menu = NSApp().mainMenu()
    if main_menu is None:
        print("Workspace Launcher could not find RoboFont's main menu.")
        return

    _remove_existing_menu_items(main_menu)

    _menu_target = WorkspaceLauncherMenuTarget.alloc().init()
    submenu = NSMenu.alloc().initWithTitle_(MENU_TITLE)
    submenu.addItem_(_menu_item("Open", "openWorkspace:", _menu_target))
    submenu.addItem_(_menu_item("Load", "loadProjectPaths:", _menu_target))
    submenu.addItem_(
        _menu_item(
            "Configure Project Paths…",
            "configureProjectPaths:",
            _menu_target,
        )
    )
    submenu.addItem_(_menu_item("Save Layout", "saveLayout:", _menu_target))

    top_level_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
        MENU_TITLE, "", ""
    )
    top_level_item.setSubmenu_(submenu)

    # Match xTools4's placement immediately before the Help menu.
    insertion_index = max(0, main_menu.numberOfItems() - 1)
    main_menu.insertItem_atIndex_(top_level_item, insertion_index)
    print("Workspace Launcher installed its top-level menu.")


_menu_target = None
