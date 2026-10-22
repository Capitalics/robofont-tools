"""The interface every palette tool provides. No RoboFont imports."""
from __future__ import annotations


class PaletteTool:
    """One section of the RoboFont Tools palette.

    The palette stacks each tool's ``content`` (ezui text), merges each tool's
    ``descriptions()``, builds the window, then calls ``attach(window)`` and
    ``start()``. A tool wires its own controls: callbacks in ``descriptions()``
    are the tool's own bound methods, and it reads its own fields through
    ``self.window.getItem(identifier)``. Identifiers must be unique across tools.
    """

    content = ""

    def __init__(self):
        self.window = None

    def descriptions(self) -> dict:
        return {}

    def attach(self, window):
        self.window = window

    def start(self):
        pass

    def stop(self):
        pass

    def refresh(self):
        pass
