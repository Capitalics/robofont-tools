"""One-shot Select Between action for the RoboFont Tools palette."""
from __future__ import annotations

import traceback
from typing import Callable

from mojo.roboFont import CurrentGlyph

from .select_between_model import SelectBetweenState


class SelectBetweenTool:
    content = """
    * TwoColumnForm @selectBetweenControl
    > : Select Between:
    > (Select Points) @selectBetweenButton
    """
    description_data = {
        "selectBetweenControl": {
            "titleColumnWidth": 120,
            "itemColumnWidth": 142,
        },
        "selectBetweenButton": {"callback": "_selectBetweenCallback"},
    }

    def __init__(self, render: Callable):
        self._render = render
        self._state = SelectBetweenState()

    def start(self):
        pass

    def stop(self):
        self._state.clear()

    def refresh(self):
        pass

    def select_between(self):
        try:
            if not self._state.select(CurrentGlyph()):
                print("Select Between: select exactly two points on one contour")
        except Exception:
            self._state.clear()
            print("Select Between: selection failed")
            traceback.print_exc()
