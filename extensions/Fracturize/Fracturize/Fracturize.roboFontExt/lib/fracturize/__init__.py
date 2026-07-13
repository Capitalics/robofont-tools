"""Fracturize geometry, project, and RoboFont integration package."""

__version__ = "0.1.0.dev0"

from .core import generate_pair
from .model import GenerationSettings, GlyphOutline

__all__ = ["GenerationSettings", "GlyphOutline", "generate_pair"]
