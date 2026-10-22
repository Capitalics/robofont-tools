"""Top-level menu for the extension's standalone scripts."""
from AppKit import NSApp, NSMenu, NSMenuItem
from Foundation import NSObject


MENU_TITLE = "RoboFont Tools"


class MenuTarget(NSObject):
    def openPalette_(self, sender):
        from .extension import open_window
        open_window()

    def openCleanup_(self, sender):
        from .cleanup.window import open_window
        open_window()

    def openCompatibility_(self, sender):
        from .cleanup.compatibility import open_window
        open_window()


def _item(title, action, target):
    item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(title, action, "")
    item.setTarget_(target)
    return item


def install_menu():
    """Replace our menu on reload without disturbing RoboFont's other menus."""
    global _target
    main_menu = NSApp().mainMenu()
    if main_menu is None:
        print("RoboFont Tools: main menu is unavailable")
        return

    for index in range(main_menu.numberOfItems() - 1, -1, -1):
        if str(main_menu.itemAtIndex_(index).title()) == MENU_TITLE:
            main_menu.removeItemAtIndex_(index)

    _target = MenuTarget.alloc().init()
    submenu = NSMenu.alloc().initWithTitle_(MENU_TITLE)
    submenu.addItem_(_item("Open Palette", "openPalette:", _target))

    submenu.addItem_(_item("Cleanup…", "openCleanup:", _target))
    submenu.addItem_(_item("Compatibility…", "openCompatibility:", _target))

    top = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(MENU_TITLE, "", "")
    top.setSubmenu_(submenu)
    main_menu.insertItem_atIndex_(top, max(0, main_menu.numberOfItems() - 1))


_target = None
