"""Palette button that opens the designspace Cleanup window."""
from __future__ import annotations

from .base import PaletteTool


class CleanupTool(PaletteTool):
    content = """
    * TwoColumnForm @cleanupControl
    > : Designspace:
    > (Cleanup…) @cleanupButton
    """

    def descriptions(self):
        return {
            "cleanupControl": {"titleColumnWidth": 120, "itemColumnWidth": 142},
            "cleanupButton": {"callback": lambda sender: self.open()},
        }

    def open(self):
        from ..cleanup.window import open_window
        open_window()
