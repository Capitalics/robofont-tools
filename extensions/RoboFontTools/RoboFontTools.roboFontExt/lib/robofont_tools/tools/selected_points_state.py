"""The single live state shared by Measure Selected Points and its subscriber."""
from __future__ import annotations


class SelectedPointsState:
    enabled = True


state = SelectedPointsState()
