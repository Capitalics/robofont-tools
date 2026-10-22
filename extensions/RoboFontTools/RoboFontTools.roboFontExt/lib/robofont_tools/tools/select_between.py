"""One-shot Select Between action for the RoboFont Tools palette."""
from __future__ import annotations

import traceback

from mojo.roboFont import CurrentGlyph

from .base import PaletteTool
from .select_between_model import SelectBetweenState


class SelectBetweenTool(PaletteTool):
    content = """
    * TwoColumnForm @selectBetweenControl
    > : Select Between:
    > (Select Points) @selectBetweenButton
    """

    def __init__(self):
        super().__init__()
        self._state = SelectBetweenState()

    def descriptions(self):
        return {
            "selectBetweenControl": {
                "titleColumnWidth": 120,
                "itemColumnWidth": 142,
            },
            "selectBetweenButton": {"callback": lambda sender: self.select_between()},
        }

    def stop(self):
        self._state.clear()

    def select_between(self):
        try:
            if not self._state.select(CurrentGlyph()):
                print("Select Between: select exactly two points on one contour")
        except Exception:
            self._state.clear()
            print("Select Between: selection failed")
            traceback.print_exc()
