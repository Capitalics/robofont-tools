from __future__ import annotations


_window_controller = None


def open_window():
    global _window_controller
    if _window_controller is None:
        from .ui import FracturizeWindowController

        _window_controller = FracturizeWindowController()
    else:
        _window_controller.w.show()
        _window_controller.w.makeKey()
    return _window_controller


def window_closed():
    global _window_controller
    _window_controller = None

