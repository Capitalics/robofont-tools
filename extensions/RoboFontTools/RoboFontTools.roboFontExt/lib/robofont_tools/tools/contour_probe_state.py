"""The single live state shared by the Contour Probe palette and subscribers."""
from __future__ import annotations


class ContourProbeState:
    enabled = True


state = ContourProbeState()
