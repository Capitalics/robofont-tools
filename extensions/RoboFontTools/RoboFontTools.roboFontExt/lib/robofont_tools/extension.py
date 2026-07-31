from __future__ import annotations


_window_controller = None


def open_window():
    """Open the palette once, or bring the existing palette forward."""
    global _window_controller
    if _window_controller is None:
        from .palette import RoboFontToolsPaletteController

        _window_controller = RoboFontToolsPaletteController()
        print("RoboFontTools: palette created")
    else:
        _window_controller.w.show()
        _window_controller.w.makeKey()
        _window_controller.refresh()
    return _window_controller


def window_closed():
    global _window_controller
    _window_controller = None
