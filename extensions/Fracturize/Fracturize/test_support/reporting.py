from __future__ import annotations

import html
from pathlib import Path

from fracturize.geometry import interpolate_contours, master_contours_to_union
from fracturize.model import GenerationResult


def _geometry_path(geometry) -> str:
    commands = []
    polygons = [geometry] if geometry.geom_type == "Polygon" else list(geometry.geoms)
    for polygon in polygons:
        for ring in [polygon.exterior, *polygon.interiors]:
            coords = list(ring.coords)
            commands.append(f"M {coords[0][0]:.3f} {-coords[0][1]:.3f}")
            commands.extend(f"L {x:.3f} {-y:.3f}" for x, y in coords[1:])
            commands.append("Z")
    return " ".join(commands)


def write_visual_sheet(results: list[GenerationResult], path: Path):
    cell_width = 760
    cell_height = 920
    positions = (0, 50, 100)
    groups_per_row = 2
    width = cell_width * len(positions) * groups_per_row
    height = cell_height * ((len(results) + groups_per_row - 1) // groups_per_row)
    rows = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="#f5f1e8"/>',
        '<style>text{font-family:system-ui,sans-serif;fill:#2b2925}.label{font-size:22px}.meta{font-size:14px;fill:#665f55}.outline{fill:#28241f;fill-rule:nonzero}.fracture{fill:none;stroke:#d86545;stroke-width:1.2;vector-effect:non-scaling-stroke}</style>',
    ]
    for result_index, result in enumerate(results):
        y = (result_index // groups_per_row) * cell_height
        group_x = (result_index % groups_per_row) * cell_width * len(positions)
        for column, position in enumerate(positions):
            x = group_x + column * cell_width
            contours = interpolate_contours(
                result.intact.contours, result.eroded.contours, position / 100.0
            )
            geometry = master_contours_to_union(contours)
            rows.append(f'<g transform="translate({x + 30},{y + 830})">')
            rows.append(f'<path class="outline" d="{_geometry_path(geometry)}"/>')
            for contour in contours:
                commands = [f"M {contour.points[0][0]:.3f} {-contour.points[0][1]:.3f}"]
                commands.extend(f"L {px:.3f} {-py:.3f}" for px, py in contour.points[1:])
                commands.append("Z")
                rows.append(f'<path class="fracture" d="{" ".join(commands)}"/>')
            rows.append("</g>")
            rows.append(
                f'<text class="label" x="{x + 24}" y="{y + 36}">{html.escape(result.glyph_name)} — {position}%</text>'
            )
            rows.append(
                f'<text class="meta" x="{x + 24}" y="{y + 60}">complexity {result.profile.value}; {len(result.fragments)} fragments; compatible {str(result.validation.compatible).lower()}</text>'
            )
    rows.append("</svg>")
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")


def write_topology_comparison(
    pairs: list[tuple[GenerationResult, GenerationResult]], path: Path
):
    """Write old/new intact and eroded masters in directly comparable columns."""
    cell_width = 720
    cell_height = 900
    columns = (
        ("recursive — intact", "old", "intact"),
        ("recursive — eroded", "old", "eroded"),
        ("branching mesh — intact", "new", "intact"),
        ("branching mesh — eroded", "new", "eroded"),
    )
    width = cell_width * len(columns)
    height = cell_height * len(pairs)
    rows = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="#f5f1e8"/>',
        '<style>text{font-family:system-ui,sans-serif;fill:#2b2925}.label{font-size:20px}.meta{font-size:13px;fill:#665f55}.outline{fill:#28241f;fill-rule:nonzero}.old{fill:none;stroke:#b1865b;stroke-width:1.25}.new{fill:none;stroke:#d84f3f;stroke-width:1.25}</style>',
    ]
    for row_index, (old, new) in enumerate(pairs):
        y = row_index * cell_height
        for column_index, (label, strategy, state) in enumerate(columns):
            result = old if strategy == "old" else new
            master = getattr(result, state)
            x = column_index * cell_width
            geometry = master_contours_to_union(master.contours)
            rows.append(f'<g transform="translate({x + 25},{y + 825})">')
            rows.append(f'<path class="outline" d="{_geometry_path(geometry)}"/>')
            for contour in master.contours:
                commands = [f"M {contour.points[0][0]:.3f} {-contour.points[0][1]:.3f}"]
                commands.extend(f"L {px:.3f} {-py:.3f}" for px, py in contour.points[1:])
                commands.append("Z")
                rows.append(f'<path class="{strategy}" d="{" ".join(commands)}"/>')
            rows.append("</g>")
            rows.append(f'<text class="label" x="{x + 22}" y="{y + 32}">{html.escape(result.glyph_name)} — {label}</text>')
            rows.append(f'<text class="meta" x="{x + 22}" y="{y + 55}">{len(result.fragments)} fragments; compatible {str(result.validation.compatible).lower()}</text>')
    rows.append("</svg>")
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")


def write_edge_profile_comparison(
    pairs: list[tuple[GenerationResult, GenerationResult]], path: Path
):
    """Compare one macro layout with clean and rough edge profiles at three states."""
    cell_width = 650
    cell_height = 880
    columns = tuple(
        (profile, position)
        for profile in ("clean macro", "rough profile")
        for position in (0, 50, 100)
    )
    width = cell_width * len(columns)
    height = cell_height * len(pairs)
    rows = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="#f5f1e8"/>',
        '<style>text{font-family:system-ui,sans-serif;fill:#2b2925}.label{font-size:18px}.meta{font-size:12px;fill:#665f55}.outline{fill:#28241f;fill-rule:nonzero}.clean{fill:none;stroke:#a57b52;stroke-width:1.2}.rough{fill:none;stroke:#d84f3f;stroke-width:1.2}</style>',
    ]
    for row_index, (clean, rough) in enumerate(pairs):
        y = row_index * cell_height
        for column_index, (profile_name, position) in enumerate(columns):
            result = clean if profile_name == "clean macro" else rough
            css_class = "clean" if result is clean else "rough"
            contours = interpolate_contours(
                result.intact.contours,
                result.eroded.contours,
                position / 100.0,
            )
            geometry = master_contours_to_union(contours)
            x = column_index * cell_width
            rows.append(f'<g transform="translate({x + 20},{y + 815})">')
            rows.append(f'<path class="outline" d="{_geometry_path(geometry)}"/>')
            for contour in contours:
                commands = [f"M {contour.points[0][0]:.3f} {-contour.points[0][1]:.3f}"]
                commands.extend(f"L {px:.3f} {-py:.3f}" for px, py in contour.points[1:])
                commands.append("Z")
                rows.append(f'<path class="{css_class}" d="{" ".join(commands)}"/>')
            rows.append("</g>")
            rows.append(
                f'<text class="label" x="{x + 18}" y="{y + 29}">{html.escape(result.glyph_name)} — {profile_name} — {position}%</text>'
            )
            rows.append(
                f'<text class="meta" x="{x + 18}" y="{y + 50}">{len(result.fragments)} fragments; compatible {str(result.validation.compatible).lower()}</text>'
            )
    rows.append("</svg>")
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")


def write_motion_comparison(
    pairs: list[tuple[GenerationResult, GenerationResult]], path: Path
):
    """Compare legacy breakup motion with architectural erosion on one topology."""

    cell_width = 650
    cell_height = 880
    columns = tuple(
        (profile, position)
        for profile in ("legacy breakup", "architectural erosion")
        for position in (0, 50, 100)
    )
    width = cell_width * len(columns)
    height = cell_height * len(pairs)
    rows = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="#f5f1e8"/>',
        '<style>text{font-family:system-ui,sans-serif;fill:#2b2925}.label{font-size:18px}.meta{font-size:12px;fill:#665f55}.baseline{stroke:#8a8176;stroke-width:1;stroke-dasharray:5 5}.outline{fill:#28241f;fill-rule:nonzero}.legacy{fill:none;stroke:#b1865b;stroke-width:1.2}.architectural{fill:none;stroke:#d84f3f;stroke-width:1.2}</style>',
    ]
    for row_index, (legacy, architectural) in enumerate(pairs):
        y = row_index * cell_height
        for column_index, (profile_name, position) in enumerate(columns):
            result = legacy if profile_name == "legacy breakup" else architectural
            css_class = "legacy" if result is legacy else "architectural"
            contours = interpolate_contours(
                result.intact.contours,
                result.eroded.contours,
                position / 100.0,
            )
            geometry = master_contours_to_union(contours)
            x = column_index * cell_width
            rows.append(f'<line class="baseline" x1="{x + 20}" y1="{y + 815}" x2="{x + cell_width - 20}" y2="{y + 815}"/>')
            rows.append(f'<g transform="translate({x + 20},{y + 815})">')
            rows.append(f'<path class="outline" d="{_geometry_path(geometry)}"/>')
            for contour in contours:
                commands = [f"M {contour.points[0][0]:.3f} {-contour.points[0][1]:.3f}"]
                commands.extend(f"L {px:.3f} {-py:.3f}" for px, py in contour.points[1:])
                commands.append("Z")
                rows.append(f'<path class="{css_class}" d="{" ".join(commands)}"/>')
            rows.append("</g>")
            rows.append(
                f'<text class="label" x="{x + 18}" y="{y + 29}">{html.escape(result.glyph_name)} — {profile_name} — {position}%</text>'
            )
            rows.append(
                f'<text class="meta" x="{x + 18}" y="{y + 50}">{len(result.fragments)} fragments; compatible {str(result.validation.compatible).lower()}</text>'
            )
    rows.append("</svg>")
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")
