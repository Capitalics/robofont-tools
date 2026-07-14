from __future__ import annotations

from dataclasses import dataclass, field
import math
from typing import Literal

Point = tuple[float, float]


@dataclass(frozen=True)
class LineSegment:
    start: Point
    end: Point


@dataclass(frozen=True)
class CubicSegment:
    start: Point
    control1: Point
    control2: Point
    end: Point


Segment = LineSegment | CubicSegment


@dataclass(frozen=True)
class SourceContour:
    segments: tuple[Segment, ...]
    closed: bool = True


@dataclass(frozen=True)
class GlyphOutline:
    name: str
    width: float
    units_per_em: float
    contours: tuple[SourceContour, ...]
    components: tuple[str, ...] = ()
    unicodes: tuple[int, ...] = ()


@dataclass(frozen=True)
class ComplexityProfile:
    value: int
    target_fragments: int
    minimum_area: float
    primary_split_count: int
    secondary_probability: float
    chip_probability: float
    edge_irregularity: float
    detail_depth: int


@dataclass(frozen=True)
class GenerationSettings:
    project_seed: str = "fracturize-proof"
    complexity: int = 50
    rock_edge_detail: int = 50
    rock_edge_roughness: int = 50
    glyph_seed_override: str | None = None
    movement_direction_degrees: float = -72.0
    movement_spread_degrees: float = 24.0
    erosion_amount: float = 0.55
    maximum_rotation_degrees: float = 12.0
    minimum_scale: float = 0.78
    large_fragment_movement_multiplier: float = 0.18
    medium_fragment_movement_multiplier: float = 0.55
    small_fragment_movement_multiplier: float = 1.0
    baseline_retention: float = 0.85
    maximum_downward_drift_em: float = 0.025
    maximum_baseline_crossing_fraction: float = 0.12

    def __post_init__(self):
        if not isinstance(self.project_seed, str) or not self.project_seed:
            raise ValueError("project_seed must be a non-empty string")
        if isinstance(self.complexity, bool) or not isinstance(self.complexity, int):
            raise ValueError("complexity must be an integer in the range 0..100")
        if not 0 <= self.complexity <= 100:
            raise ValueError("complexity must be in the range 0..100")
        if isinstance(self.rock_edge_detail, bool) or not isinstance(
            self.rock_edge_detail, int
        ):
            raise ValueError("rock_edge_detail must be an integer in the range 0..100")
        if not 0 <= self.rock_edge_detail <= 100:
            raise ValueError("rock_edge_detail must be in the range 0..100")
        if isinstance(self.rock_edge_roughness, bool) or not isinstance(
            self.rock_edge_roughness, int
        ):
            raise ValueError("rock_edge_roughness must be an integer in the range 0..100")
        if not 0 <= self.rock_edge_roughness <= 100:
            raise ValueError("rock_edge_roughness must be in the range 0..100")
        if self.glyph_seed_override is not None and not isinstance(
            self.glyph_seed_override, str
        ):
            raise ValueError("glyph_seed_override must be a string or null")

        ranges = {
            "movement_direction_degrees": (-360.0, 360.0),
            "movement_spread_degrees": (0.0, 180.0),
            "erosion_amount": (0.0, 1.0),
            "maximum_rotation_degrees": (0.0, 30.0),
            "minimum_scale": (0.5, 1.0),
            "large_fragment_movement_multiplier": (0.0, 1.0),
            "medium_fragment_movement_multiplier": (0.0, 1.5),
            "small_fragment_movement_multiplier": (0.0, 2.0),
            "baseline_retention": (0.0, 1.0),
            "maximum_downward_drift_em": (0.0, 0.08),
            "maximum_baseline_crossing_fraction": (0.0, 0.5),
        }
        for name, (minimum, maximum) in ranges.items():
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError(f"{name} must be a finite number")
            if not math.isfinite(value):
                raise ValueError(f"{name} must be finite")
            if not minimum <= value <= maximum:
                raise ValueError(f"{name} must be in the range {minimum}..{maximum}")
        if not (
            self.large_fragment_movement_multiplier
            <= self.medium_fragment_movement_multiplier
            <= self.small_fragment_movement_multiplier
        ):
            raise ValueError(
                "fragment movement multipliers must be ordered large <= medium <= small"
            )


@dataclass(frozen=True)
class MasterContour:
    identifier: str
    fragment_id: str
    part_index: int
    is_hole: bool
    points: tuple[Point, ...]
    point_ids: tuple[str, ...]
    # Ordered closed-path segments. Older topology records omit this field and
    # are interpreted as cyclic line segments through ``points``.
    segments: tuple[Segment, ...] = ()


def master_contour_segments(contour: MasterContour) -> tuple[Segment, ...]:
    if contour.segments:
        return contour.segments
    if not contour.points:
        return ()
    return tuple(
        LineSegment(contour.points[index - 1], point)
        for index, point in enumerate(contour.points)
    )


@dataclass(frozen=True)
class Fragment:
    identifier: str
    area: float
    centroid: Point
    bounds: tuple[float, float, float, float]
    transform_origin: Point
    intact_contours: tuple[MasterContour, ...]
    translation: Point
    rotation_degrees: float
    scale: float


@dataclass(frozen=True)
class MasterGlyph:
    name: str
    width: float
    unicodes: tuple[int, ...]
    contours: tuple[MasterContour, ...]


FindingLevel = Literal["hard_error", "interpolation_risk", "visual_warning"]


@dataclass(frozen=True)
class ValidationFinding:
    level: FindingLevel
    code: str
    message: str


@dataclass(frozen=True)
class ReconstructionMetrics:
    source_area: float
    intact_area: float
    symmetric_difference_area: float
    normalized_symmetric_difference: float
    hausdorff_distance: float


@dataclass(frozen=True)
class NormalizationDiagnostics:
    fill_rule: str
    normalization_applied: bool
    cause: str
    self_intersecting_contours: tuple[int, ...]
    point_crossing_count: int
    primary_face_count: int
    reference_face_count: int
    winding_histogram: tuple[int, ...]
    maximum_absolute_winding: int
    nonzero_area: float
    evenodd_area: float
    cross_tolerance_symmetric_difference: float
    cross_tolerance_normalized_difference: float
    cross_tolerance_hausdorff_distance: float


@dataclass(frozen=True)
class ValidationReport:
    compatible: bool
    reconstruction: ReconstructionMetrics
    findings: tuple[ValidationFinding, ...]
    sampled_positions: tuple[int, ...]


@dataclass(frozen=True)
class GenerationResult:
    glyph_name: str
    effective_seed: int
    flattening_tolerance: float
    rock_edge_detail: int
    rock_edge_roughness: int
    profile: ComplexityProfile
    normalization: NormalizationDiagnostics
    fragments: tuple[Fragment, ...]
    intact: MasterGlyph
    eroded: MasterGlyph
    validation: ValidationReport
    notes: tuple[str, ...] = field(default_factory=tuple)
    outline_reconstruction_version: str = "polygonal-v1"
