from __future__ import annotations

import hashlib
import json
import math
import os
import shutil
import uuid
from copy import deepcopy
from dataclasses import asdict, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from defcon import Font

from . import __version__
from .core import (
    BRANCHING_TOPOLOGY_V1,
    EDGE_PROFILE_VERSION,
    MOTION_ALGORITHM_V1,
    MOTION_ALGORITHM_VERSION,
    RECURSIVE_TOPOLOGY_VERSION,
    SEED_DERIVATION_VERSION,
    TOPOLOGY_VERSION,
    generate_pair,
    generate_branching_topology_v1,
    generate_recursive_topology,
    regenerate_motion_from_topology,
)
from .geometry import master_contours_to_union
from .input_ufo import defcon_glyph_to_outline
from .model import GenerationResult, GenerationSettings, GlyphOutline
from .topology import read_topology, topology_digest, write_topology
from .ufo import LIB_KEY, _draw_master, read_master
from .validation import validate_pair

PROJECT_FORMAT = "com.fracturize.project"
PROJECT_FORMAT_VERSION = 1
PROJECT_ID_KEY = "com.fracturize.projectID"
OUTPUT_ROLE_KEY = "com.fracturize.outputRole"
PAIR_REVISION_KEY = "com.fracturize.pairRevision"
SOURCE_FINGERPRINT_KEY = "com.fracturize.sourceFingerprint"
TOPOLOGY_DIGEST_KEY = "com.fracturize.topologyDigest"


class ProjectError(RuntimeError):
    pass


class ProjectConflictError(ProjectError):
    pass


class ProjectIntegrityError(ProjectError):
    pass


class ProcessedGlyphError(ProjectError):
    pass


class StaleGlyphError(ProjectError):
    pass


class OutputGlyphEditedError(ProjectError):
    pass


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _tree_digest(path: Path) -> str:
    digest = hashlib.sha256()
    for file_path in sorted(item for item in path.rglob("*") if item.is_file()):
        digest.update(file_path.relative_to(path).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(file_path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def _relative_path(target: Path, base: Path) -> str:
    return os.path.relpath(target.resolve(), base.resolve())


def _resolve_path(value: str, base: Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else (base / path).resolve()


def _outline_payload(outline: GlyphOutline) -> dict:
    contours = []
    for contour in outline.contours:
        segments = []
        for segment in contour.segments:
            if hasattr(segment, "control1"):
                segments.append(
                    {
                        "type": "cubic",
                        "start": list(segment.start),
                        "control1": list(segment.control1),
                        "control2": list(segment.control2),
                        "end": list(segment.end),
                    }
                )
            else:
                segments.append(
                    {"type": "line", "start": list(segment.start), "end": list(segment.end)}
                )
        contours.append({"closed": contour.closed, "segments": segments})
    return {
        "fingerprintVersion": 1,
        "name": outline.name,
        "width": outline.width,
        "unitsPerEm": outline.units_per_em,
        "unicodes": list(outline.unicodes),
        "components": list(outline.components),
        "contours": contours,
    }


def source_fingerprint(outline: GlyphOutline) -> str:
    payload = json.dumps(_outline_payload(outline), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def glyph_content_digest(glyph) -> str:
    """Hash serialized glyph content that must continue to match stored topology."""

    payload = {
        "digestVersion": 1,
        "name": glyph.name,
        "width": glyph.width,
        "unicodes": list(glyph.unicodes),
        "contours": [
            {
                "identifier": contour.identifier,
                "points": [
                    {
                        "x": point.x,
                        "y": point.y,
                        "type": point.segmentType,
                        "smooth": point.smooth,
                        "identifier": point.identifier,
                    }
                    for point in contour
                ],
            }
            for contour in glyph
        ],
        "components": [
            {
                "baseGlyph": component.baseGlyph,
                "transformation": list(component.transformation),
                "identifier": component.identifier,
            }
            for component in glyph.components
        ],
        "fragmentMap": glyph.lib.get(LIB_KEY),
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _require_mapping(value, label: str) -> dict:
    if not isinstance(value, dict):
        raise ProjectIntegrityError(f"{label} must be an object")
    return value


def _require_string(mapping: dict, key: str, label: str, *, nonempty: bool = True) -> str:
    value = mapping.get(key)
    if not isinstance(value, str) or (nonempty and not value):
        raise ProjectIntegrityError(f"{label}.{key} must be a string")
    return value


def _require_number(mapping: dict, key: str, label: str, *, positive: bool = False) -> float:
    value = mapping.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ProjectIntegrityError(f"{label}.{key} must be a finite number")
    if positive and value <= 0:
        raise ProjectIntegrityError(f"{label}.{key} must be positive")
    return float(value)


def validate_project_v1(data) -> None:
    """Small explicit validator for format version 1; this is not a migration layer."""

    root = _require_mapping(data, "project")
    if root.get("format") != PROJECT_FORMAT or root.get("formatVersion") != PROJECT_FORMAT_VERSION:
        raise ProjectIntegrityError("unsupported project format")
    for key in ("projectID", "projectName", "createdAt", "updatedAt", "generatorVersion"):
        _require_string(root, key, "project")

    source = _require_mapping(root.get("source"), "source")
    _require_string(source, "path", "source")
    _require_number(source, "unitsPerEm", "source", positive=True)
    _require_string(source, "initialTreeDigest", "source")
    for key in ("familyName", "styleName"):
        if source.get(key) is not None and not isinstance(source.get(key), str):
            raise ProjectIntegrityError(f"source.{key} must be a string or null")

    outputs = _require_mapping(root.get("outputs"), "outputs")
    for role in ("intact", "eroded"):
        output = _require_mapping(outputs.get(role), f"outputs.{role}")
        _require_string(output, "path", f"outputs.{role}")
        if output.get("role") != role:
            raise ProjectIntegrityError(f"outputs.{role}.role must be {role!r}")

    settings_data = _require_mapping(root.get("settings"), "settings")
    try:
        GenerationSettings(**settings_data)
    except (TypeError, ValueError) as error:
        raise ProjectIntegrityError(f"invalid settings: {error}") from error

    topology = _require_mapping(root.get("topologyPolicy"), "topologyPolicy")
    if topology.get("topologyVersion") not in {
        TOPOLOGY_VERSION,
        BRANCHING_TOPOLOGY_V1,
        RECURSIVE_TOPOLOGY_VERSION,
    }:
        raise ProjectIntegrityError("unsupported project topology version")
    expected_policy = {
        "seedDerivationVersion": SEED_DERIVATION_VERSION,
        "fillRule": "non-zero winding",
        "curvePolicy": "adaptive polygonal flattening",
        "componentPolicy": "explicit rejection",
    }
    for key, expected in expected_policy.items():
        if topology.get(key) != expected:
            raise ProjectIntegrityError(f"unsupported topology policy {key}")
    if topology.get("edgeProfileVersion") not in {None, EDGE_PROFILE_VERSION}:
        raise ProjectIntegrityError("unsupported topology policy edgeProfileVersion")

    motion = _require_mapping(root.get("motionPolicy"), "motionPolicy")
    if motion.get("algorithmVersion") not in {
        MOTION_ALGORITHM_V1,
        MOTION_ALGORITHM_VERSION,
    }:
        raise ProjectIntegrityError("unsupported motion algorithm version")

    for key in ("fontInfoAllowlist", "glyphDataAllowlist"):
        value = root.get(key)
        if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
            raise ProjectIntegrityError(f"{key} must be a list of strings")
    save_policy = _require_mapping(root.get("savePolicy"), "savePolicy")
    for key in ("phaseAHarness", "finalRoboFontOwnership", "atomicity"):
        _require_string(save_policy, key, "savePolicy")
    for key in ("outputsMayRemainOpenInRoboFont", "crashProof"):
        if not isinstance(save_policy.get(key), bool):
            raise ProjectIntegrityError(f"savePolicy.{key} must be a boolean")

    records = _require_mapping(root.get("processedGlyphs"), "processedGlyphs")
    for glyph_name, value in records.items():
        if not isinstance(glyph_name, str) or not glyph_name:
            raise ProjectIntegrityError("processed glyph names must be non-empty strings")
        record = _require_mapping(value, f"processedGlyphs.{glyph_name}")
        for key in (
            "status",
            "sourceFingerprint",
            "topologyPath",
            "topologyDigest",
            "pairRevision",
            "updatedAt",
            "motionAlgorithmVersion",
        ):
            _require_string(record, key, f"processedGlyphs.{glyph_name}")
        if record["status"] not in {
            "processed",
            "stale",
            "source-unavailable",
            "topology-outdated",
            "output-edited",
        }:
            raise ProjectIntegrityError(f"invalid status for {glyph_name}")
        if record["motionAlgorithmVersion"] != motion["algorithmVersion"]:
            raise ProjectIntegrityError(
                f"motion algorithm mismatch for {glyph_name}"
            )
        if isinstance(record.get("effectiveSeed"), bool) or not isinstance(
            record.get("effectiveSeed"), int
        ):
            raise ProjectIntegrityError(f"effective seed must be an integer for {glyph_name}")
        complexity = record.get("topologyComplexity")
        if isinstance(complexity, bool) or not isinstance(complexity, int) or not 0 <= complexity <= 100:
            raise ProjectIntegrityError(f"invalid topology complexity for {glyph_name}")
        edge_detail = record.get("topologyRockEdgeDetail")
        if edge_detail is not None and (
            isinstance(edge_detail, bool)
            or not isinstance(edge_detail, int)
            or not 0 <= edge_detail <= 100
        ):
            raise ProjectIntegrityError(f"invalid rock edge detail for {glyph_name}")
        motion_settings = _require_mapping(
            record.get("motionSettings"),
            f"processedGlyphs.{glyph_name}.motionSettings",
        )
        expected_motion_keys = set(settings_data) - {
            "project_seed",
            "complexity",
            "rock_edge_detail",
            "glyph_seed_override",
        }
        if set(motion_settings) != expected_motion_keys:
            raise ProjectIntegrityError(f"invalid motion settings record for {glyph_name}")
        try:
            replace(GenerationSettings(), **motion_settings)
        except (TypeError, ValueError) as error:
            raise ProjectIntegrityError(
                f"invalid motion settings record for {glyph_name}: {error}"
            ) from error
        digests = _require_mapping(record.get("contentDigests"), f"processedGlyphs.{glyph_name}.contentDigests")
        for role in ("intact", "eroded"):
            digest = _require_string(digests, role, f"processedGlyphs.{glyph_name}.contentDigests")
            if len(digest) != 64:
                raise ProjectIntegrityError(f"invalid {role} content digest for {glyph_name}")


def _copy_font_info(source: Font, destination: Font, *, family_name: str, style_name: str):
    destination.info.familyName = family_name
    destination.info.styleName = style_name
    for attribute in (
        "unitsPerEm",
        "ascender",
        "descender",
        "xHeight",
        "capHeight",
        "copyright",
    ):
        value = getattr(source.info, attribute)
        if value is not None:
            setattr(destination.info, attribute, value)
    destination.glyphOrder = list(source.keys())


class FractureProject:
    """File-backed Stage 2 harness; final RoboFont document ownership is separate."""

    def __init__(self, path: Path, data: dict):
        self.path = path.resolve()
        self.directory = self.path.parent
        self.data = data
        self._edited_outputs: dict[str, tuple[str, ...]] = {}

    @property
    def source_path(self) -> Path:
        return _resolve_path(self.data["source"]["path"], self.directory)

    @property
    def intact_path(self) -> Path:
        return _resolve_path(self.data["outputs"]["intact"]["path"], self.directory)

    @property
    def eroded_path(self) -> Path:
        return _resolve_path(self.data["outputs"]["eroded"]["path"], self.directory)

    @property
    def settings(self) -> GenerationSettings:
        return GenerationSettings(**self.data["settings"])

    @classmethod
    def create(
        cls,
        project_directory: Path,
        source_path: Path,
        *,
        project_name: str,
        project_seed: str,
        complexity: int = 50,
        rock_edge_detail: int = 50,
        intact_filename: str | None = None,
        eroded_filename: str | None = None,
        family_name: str | None = None,
        intact_style_name: str = "Fracture Intact",
        eroded_style_name: str = "Fracture Eroded",
    ) -> "FractureProject":
        project_directory = project_directory.resolve()
        source_path = source_path.resolve()
        if not source_path.is_dir():
            raise ProjectError(f"source UFO not found: {source_path}")
        settings = GenerationSettings(
            project_seed=project_seed,
            complexity=complexity,
            rock_edge_detail=rock_edge_detail,
        )
        project_directory.mkdir(parents=True, exist_ok=True)
        project_filename = f"{project_name}.fracturize.json"
        project_path = project_directory / project_filename
        intact_path = project_directory / (
            intact_filename or f"{project_name}-FractureIntact.ufo"
        )
        eroded_path = project_directory / (
            eroded_filename or f"{project_name}-FractureEroded.ufo"
        )
        conflicts = [path for path in (project_path, intact_path, eroded_path) if path.exists()]
        if conflicts:
            raise ProjectConflictError(
                "project creation refused existing paths: "
                + ", ".join(str(path) for path in conflicts)
            )

        project_id = str(uuid.uuid4())
        source = Font(source_path)
        chosen_family = family_name or source.info.familyName or project_name
        created_outputs = []
        try:
            for path, role, style_name in (
                (intact_path, "intact", intact_style_name),
                (eroded_path, "eroded", eroded_style_name),
            ):
                output = Font()
                _copy_font_info(source, output, family_name=chosen_family, style_name=style_name)
                output.lib[PROJECT_ID_KEY] = project_id
                output.lib[OUTPUT_ROLE_KEY] = role
                output.save(path)
                output.close()
                created_outputs.append(path)
        except Exception:
            for path in created_outputs:
                if path.exists():
                    shutil.rmtree(path)
            raise

        now = _utc_now()
        data = {
            "format": PROJECT_FORMAT,
            "formatVersion": PROJECT_FORMAT_VERSION,
            "projectID": project_id,
            "projectName": project_name,
            "createdAt": now,
            "updatedAt": now,
            "generatorVersion": __version__,
            "source": {
                "path": _relative_path(source_path, project_directory),
                "familyName": source.info.familyName,
                "styleName": source.info.styleName,
                "unitsPerEm": float(source.info.unitsPerEm or 1000),
                "initialTreeDigest": _tree_digest(source_path),
            },
            "outputs": {
                "intact": {"path": intact_path.name, "role": "intact"},
                "eroded": {"path": eroded_path.name, "role": "eroded"},
            },
            "settings": asdict(settings),
            "topologyPolicy": {
                "topologyVersion": TOPOLOGY_VERSION,
                "edgeProfileVersion": EDGE_PROFILE_VERSION,
                "seedDerivationVersion": SEED_DERIVATION_VERSION,
                "fillRule": "non-zero winding",
                "curvePolicy": "adaptive polygonal flattening",
                "componentPolicy": "explicit rejection",
            },
            "motionPolicy": {
                "algorithmVersion": MOTION_ALGORITHM_VERSION,
            },
            "fontInfoAllowlist": [
                "unitsPerEm",
                "ascender",
                "descender",
                "xHeight",
                "capHeight",
                "familyName",
                "styleName",
                "copyright",
                "glyphOrder",
            ],
            "glyphDataAllowlist": [
                "name",
                "width",
                "unicodes",
                "fragmentIdentifiers",
                "contourIdentifiers",
                "pointIdentifiers",
            ],
            "processedGlyphs": {},
            "savePolicy": {
                "phaseAHarness": "file-based detached defcon writes",
                "finalRoboFontOwnership": "user-owned RoboFont documents",
                "outputsMayRemainOpenInRoboFont": True,
                "atomicity": "per glyph pair with ordinary exception rollback",
                "crashProof": False,
            },
        }
        source.close()
        project = cls(project_path, data)
        project._save()
        return project

    @classmethod
    def open(cls, path: Path) -> "FractureProject":
        path = path.resolve()
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise ProjectIntegrityError(f"project file is unreadable: {error}") from error
        validate_project_v1(data)
        project = cls(path, data)
        project.validate_integrity()
        return project

    def close(self):
        """Release references held by this headless controller."""

    def _save(self):
        self.data["updatedAt"] = _utc_now()
        payload = json.dumps(self.data, indent=2, sort_keys=True) + "\n"
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(payload, encoding="utf-8")
        os.replace(temporary, self.path)

    def _topology_path(self, glyph_name: str) -> Path:
        digest = hashlib.sha256(glyph_name.encode("utf-8")).hexdigest()[:16]
        return self.directory / "project-data" / "topology" / f"{digest}.json"

    def _load_source_outline(self, glyph_name: str) -> GlyphOutline:
        source = Font(self.source_path)
        try:
            if glyph_name not in source:
                raise ProjectError(f"source glyph not found: {glyph_name}")
            return defcon_glyph_to_outline(
                source[glyph_name],
                units_per_em=float(source.info.unitsPerEm or 1000),
            )
        finally:
            source.close()

    def _generate_pair_for_project(self, outline: GlyphOutline) -> GenerationResult:
        topology_version = self.data["topologyPolicy"]["topologyVersion"]
        motion_version = self.data["motionPolicy"]["algorithmVersion"]
        if topology_version == TOPOLOGY_VERSION:
            return generate_pair(
                outline,
                self.settings,
                motion_algorithm_version=motion_version,
            )
        if topology_version == BRANCHING_TOPOLOGY_V1:
            return generate_pair(
                outline,
                self.settings,
                topology_generator=generate_branching_topology_v1,
                topology_version=BRANCHING_TOPOLOGY_V1,
                motion_algorithm_version=motion_version,
            )
        if topology_version == RECURSIVE_TOPOLOGY_VERSION:
            return generate_pair(
                outline,
                self.settings,
                topology_generator=generate_recursive_topology,
                topology_version=RECURSIVE_TOPOLOGY_VERSION,
                motion_algorithm_version=motion_version,
            )
        raise ProjectIntegrityError(f"unsupported project topology version: {topology_version}")

    def validate_integrity(self):
        validate_project_v1(self.data)
        if not self.source_path.is_dir():
            raise ProjectIntegrityError(f"source UFO missing: {self.source_path}")
        for path in (self.intact_path, self.eroded_path):
            if not path.is_dir():
                raise ProjectIntegrityError(f"output UFO missing: {path}")
        intact = Font(self.intact_path)
        eroded = Font(self.eroded_path)
        try:
            for font, role in ((intact, "intact"), (eroded, "eroded")):
                if font.lib.get(PROJECT_ID_KEY) != self.data["projectID"]:
                    raise ProjectIntegrityError(f"{role} UFO project identity mismatch")
                if font.lib.get(OUTPUT_ROLE_KEY) != role:
                    raise ProjectIntegrityError(f"{role} UFO role mismatch")
            intact_names = set(intact.keys())
            eroded_names = set(eroded.keys())
            expected = set(self.data["processedGlyphs"])
            if intact_names != eroded_names:
                raise ProjectIntegrityError("output UFO glyph sets differ")
            if intact_names != expected:
                raise ProjectIntegrityError("output UFO glyph set does not match project record")
            edited_outputs = {}
            for glyph_name, record in self.data["processedGlyphs"].items():
                topology_path = _resolve_path(record["topologyPath"], self.directory)
                if not topology_path.is_file():
                    raise ProjectIntegrityError(f"missing topology for {glyph_name}")
                if topology_digest(topology_path) != record["topologyDigest"]:
                    raise ProjectIntegrityError(f"topology digest mismatch for {glyph_name}")
                for font in (intact, eroded):
                    glyph = font[glyph_name]
                    if glyph.lib.get(PAIR_REVISION_KEY) != record["pairRevision"]:
                        raise ProjectIntegrityError(f"pair revision mismatch for {glyph_name}")
                    if glyph.lib.get(SOURCE_FINGERPRINT_KEY) != record["sourceFingerprint"]:
                        raise ProjectIntegrityError(f"source fingerprint mismatch for {glyph_name}")
                    if glyph.lib.get(TOPOLOGY_DIGEST_KEY) != record["topologyDigest"]:
                        raise ProjectIntegrityError(f"topology reference mismatch for {glyph_name}")
                changed_roles = tuple(
                    role
                    for role, font in (("intact", intact), ("eroded", eroded))
                    if glyph_content_digest(font[glyph_name])
                    != record["contentDigests"][role]
                )
                if changed_roles:
                    edited_outputs[glyph_name] = changed_roles
            self._edited_outputs = edited_outputs
        finally:
            intact.close()
            eroded.close()

    @property
    def edited_outputs(self) -> dict[str, tuple[str, ...]]:
        """Generated sides changed since their last successful project commit."""

        return dict(self._edited_outputs)

    def _refresh_output_edit_status(self, glyph_name: str) -> tuple[str, ...]:
        record = self.data["processedGlyphs"].get(glyph_name)
        if record is None:
            self._edited_outputs.pop(glyph_name, None)
            return ()
        changed = []
        for role, path in (("intact", self.intact_path), ("eroded", self.eroded_path)):
            font = Font(path)
            try:
                if glyph_name not in font or (
                    glyph_content_digest(font[glyph_name])
                    != record["contentDigests"][role]
                ):
                    changed.append(role)
            finally:
                font.close()
        if changed:
            self._edited_outputs[glyph_name] = tuple(changed)
        else:
            self._edited_outputs.pop(glyph_name, None)
        return tuple(changed)

    def _require_unedited_output(self, glyph_name: str, *, replace_edited: bool = False):
        changed = self._refresh_output_edit_status(glyph_name)
        if changed and not replace_edited:
            raise OutputGlyphEditedError(
                f"generated glyph {glyph_name} was edited in {', '.join(changed)}; "
                "explicit edited-output regeneration is required"
            )

    def glyph_status(self, glyph_name: str) -> str:
        record = self.data["processedGlyphs"].get(glyph_name)
        if record is None:
            return "unprocessed"
        if self._refresh_output_edit_status(glyph_name):
            status = "output-edited"
            if record.get("status") != status:
                record["status"] = status
                self._save()
            return status
        try:
            outline = self._load_source_outline(glyph_name)
        except Exception:
            status = "source-unavailable"
        else:
            if source_fingerprint(outline) != record["sourceFingerprint"]:
                status = "stale"
            elif record["topologyComplexity"] != self.settings.complexity:
                status = "topology-outdated"
            elif record.get(
                "topologyRockEdgeDetail",
                record["topologyComplexity"],
            ) != self.settings.rock_edge_detail:
                status = "topology-outdated"
            else:
                status = "processed"
        if record.get("status") != status:
            record["status"] = status
            self._save()
        return status

    def set_motion_settings(self, **changes):
        allowed = {
            "movement_direction_degrees",
            "movement_spread_degrees",
            "erosion_amount",
            "maximum_rotation_degrees",
            "minimum_scale",
            "large_fragment_movement_multiplier",
            "medium_fragment_movement_multiplier",
            "small_fragment_movement_multiplier",
            "baseline_retention",
            "maximum_downward_drift_em",
            "maximum_baseline_crossing_fraction",
        }
        unexpected = set(changes) - allowed
        if unexpected:
            raise ProjectError(f"not a motion-only setting: {', '.join(sorted(unexpected))}")
        try:
            settings = replace(self.settings, **changes)
        except ValueError as error:
            raise ProjectError(f"invalid motion settings: {error}") from error
        self.data["settings"] = asdict(settings)
        self._save()

    def set_complexity(self, value: int):
        try:
            settings = replace(self.settings, complexity=value)
        except ValueError as error:
            raise ProjectError(f"invalid complexity: {error}") from error
        self.data["settings"] = asdict(settings)
        self._save()

    def set_rock_edge_detail(self, value: int):
        try:
            settings = replace(self.settings, rock_edge_detail=value)
        except ValueError as error:
            raise ProjectError(f"invalid rock edge detail: {error}") from error
        self.data["settings"] = asdict(settings)
        self._save()

    def process_glyph(
        self,
        glyph_name: str,
        *,
        replace_existing: bool = False,
        regenerate_topology: bool = False,
        replace_edited: bool = False,
        save_hook: Callable[[str], None] | None = None,
    ) -> GenerationResult:
        existing = self.data["processedGlyphs"].get(glyph_name)
        if existing and not replace_existing:
            raise ProcessedGlyphError(
                f"{glyph_name} is already processed; replacement must be explicit"
            )
        if existing and not regenerate_topology:
            raise ProcessedGlyphError(
                f"{glyph_name} replacement requires explicit topology regeneration or motion-only regeneration"
            )
        if existing:
            self._require_unedited_output(
                glyph_name,
                replace_edited=replace_edited,
            )
        outline = self._load_source_outline(glyph_name)
        fingerprint = source_fingerprint(outline)
        result = self._generate_pair_for_project(outline)
        self._commit_result(
            result,
            fingerprint=fingerprint,
            topology_is_new=True,
            save_hook=save_hook,
        )
        return result

    def regenerate_topology(
        self,
        glyph_name: str,
        *,
        replace_edited: bool = False,
        save_hook: Callable[[str], None] | None = None,
    ) -> GenerationResult:
        if glyph_name not in self.data["processedGlyphs"]:
            raise ProjectError(f"glyph is not processed: {glyph_name}")
        return self.process_glyph(
            glyph_name,
            replace_existing=True,
            regenerate_topology=True,
            replace_edited=replace_edited,
            save_hook=save_hook,
        )

    def regenerate_motion(
        self,
        glyph_name: str,
        *,
        save_hook: Callable[[str], None] | None = None,
    ) -> GenerationResult:
        record = self.data["processedGlyphs"].get(glyph_name)
        if record is None:
            raise ProjectError(f"glyph is not processed: {glyph_name}")
        self._require_unedited_output(glyph_name)
        outline = self._load_source_outline(glyph_name)
        fingerprint = source_fingerprint(outline)
        if fingerprint != record["sourceFingerprint"]:
            record["status"] = "stale"
            self._save()
            raise StaleGlyphError(f"source glyph changed: {glyph_name}")
        topology_path = _resolve_path(record["topologyPath"], self.directory)
        topology, units_per_em = read_topology(topology_path)
        result = regenerate_motion_from_topology(
            topology,
            self.settings,
            units_per_em=units_per_em,
            motion_algorithm_version=self.data["motionPolicy"]["algorithmVersion"],
        )
        self._commit_result(
            result,
            fingerprint=fingerprint,
            topology_is_new=False,
            save_hook=save_hook,
        )
        return result

    def _commit_result(
        self,
        result: GenerationResult,
        *,
        fingerprint: str,
        topology_is_new: bool,
        save_hook: Callable[[str], None] | None,
    ):
        if not result.validation.compatible:
            raise ProjectError(f"blocking validation failure for {result.glyph_name}")
        topology_path = self._topology_path(result.glyph_name)
        candidate = topology_path.with_suffix(".candidate.json") if topology_is_new else None
        old_topology = topology_path.read_bytes() if topology_path.exists() else None
        old_project = self.path.read_bytes()
        old_data = deepcopy(self.data)
        backups = self._capture_pair(result.glyph_name)
        pair_revision = str(uuid.uuid4())
        try:
            if candidate is not None:
                topology_hash = write_topology(
                    result,
                    candidate,
                    units_per_em=self.data["source"]["unitsPerEm"],
                )
            else:
                topology_hash = topology_digest(topology_path)
            content_digests = self._write_pair(
                result,
                pair_revision=pair_revision,
                fingerprint=fingerprint,
                topology_hash=topology_hash,
                save_hook=save_hook,
            )
            if candidate is not None:
                if save_hook:
                    save_hook("before_topology_replace")
                topology_path.parent.mkdir(parents=True, exist_ok=True)
                os.replace(candidate, topology_path)
                if save_hook:
                    save_hook("after_topology_replace")
            record = dict(self.data["processedGlyphs"].get(result.glyph_name, {}))
            record.update(
                {
                    "status": "processed",
                    "sourceFingerprint": fingerprint,
                    "effectiveSeed": result.effective_seed,
                    "topologyPath": _relative_path(topology_path, self.directory),
                    "topologyDigest": topology_hash,
                    "topologyComplexity": result.profile.value,
                    "topologyRockEdgeDetail": result.rock_edge_detail,
                    "pairRevision": pair_revision,
                    "contentDigests": content_digests,
                    "motionAlgorithmVersion": self.data["motionPolicy"]["algorithmVersion"],
                    "motionSettings": {
                        key: value
                        for key, value in asdict(self.settings).items()
                        if key not in {
                            "project_seed",
                            "complexity",
                            "rock_edge_detail",
                            "glyph_seed_override",
                        }
                    },
                    "updatedAt": _utc_now(),
                }
            )
            self.data["processedGlyphs"][result.glyph_name] = record
            if save_hook:
                save_hook("before_project_save")
            self._save()
            if save_hook:
                save_hook("after_project_save")
            self._edited_outputs.pop(result.glyph_name, None)
        except Exception as error:
            rollback_errors = []
            try:
                self._restore_pair(result.glyph_name, backups)
            except Exception as rollback_error:
                rollback_errors.append(f"pair: {rollback_error}")
            try:
                if old_topology is None:
                    if topology_path.exists():
                        topology_path.unlink()
                else:
                    topology_path.parent.mkdir(parents=True, exist_ok=True)
                    topology_path.write_bytes(old_topology)
            except Exception as rollback_error:
                rollback_errors.append(f"topology: {rollback_error}")
            try:
                self.data = old_data
                self.path.write_bytes(old_project)
            except Exception as rollback_error:
                rollback_errors.append(f"project: {rollback_error}")
            try:
                if candidate is not None and candidate.exists():
                    candidate.unlink()
                candidate_temporary = (
                    candidate.with_suffix(candidate.suffix + ".tmp")
                    if candidate is not None
                    else None
                )
                if candidate_temporary is not None and candidate_temporary.exists():
                    candidate_temporary.unlink()
            except Exception as rollback_error:
                rollback_errors.append(f"candidate: {rollback_error}")
            if rollback_errors:
                raise ProjectIntegrityError(
                    "commit failed and rollback was incomplete: "
                    + "; ".join(rollback_errors)
                ) from error
            raise

    def _capture_pair(self, glyph_name: str) -> dict:
        backups = {}
        for role, path in (("intact", self.intact_path), ("eroded", self.eroded_path)):
            font = Font(path)
            try:
                backups[role] = deepcopy(font[glyph_name]) if glyph_name in font else None
            finally:
                font.close()
        return backups

    def _write_pair(
        self,
        result: GenerationResult,
        *,
        pair_revision: str,
        fingerprint: str,
        topology_hash: str,
        save_hook: Callable[[str], None] | None,
    ):
        glyph_name = result.glyph_name
        extra_lib = {
            PAIR_REVISION_KEY: pair_revision,
            SOURCE_FINGERPRINT_KEY: fingerprint,
            TOPOLOGY_DIGEST_KEY: topology_hash,
        }
        intact = Font(self.intact_path)
        eroded = Font(self.eroded_path)
        try:
            _draw_master(intact, result.intact, extra_lib=extra_lib)
            _draw_master(eroded, result.eroded, extra_lib=extra_lib)
            if save_hook:
                save_hook("before_intact_save")
            intact.save()
            if save_hook:
                save_hook("after_intact_save")
                save_hook("before_eroded_save")
            eroded.save()
            if save_hook:
                save_hook("after_eroded_save")
        finally:
            intact.close()
            eroded.close()

        reopened_intact = read_master(self.intact_path, glyph_name)
        reopened_eroded = read_master(self.eroded_path, glyph_name)
        source_silhouette = master_contours_to_union(result.intact.contours)
        reopened_report = validate_pair(
            source_silhouette=source_silhouette,
            intact=reopened_intact,
            eroded=reopened_eroded,
            units_per_em=self.data["source"]["unitsPerEm"],
            minimum_area=result.profile.minimum_area,
        )
        if not reopened_report.compatible:
            raise ProjectError(f"serialized output validation failed for {glyph_name}")
        if save_hook:
            save_hook("after_serialized_validation")
        content_digests = {}
        for role, path in (("intact", self.intact_path), ("eroded", self.eroded_path)):
            font = Font(path)
            try:
                content_digests[role] = glyph_content_digest(font[glyph_name])
            finally:
                font.close()
        return content_digests

    def _restore_pair(self, glyph_name: str, backups: dict):
        errors = []
        for role, path in (("intact", self.intact_path), ("eroded", self.eroded_path)):
            font = None
            try:
                font = Font(path)
                backup = backups[role]
                if backup is None:
                    if glyph_name in font:
                        del font[glyph_name]
                else:
                    if glyph_name in font:
                        del font[glyph_name]
                    font.insertGlyph(backup, name=glyph_name)
                font.save()
            except Exception as error:  # pragma: no cover - catastrophic recovery path
                errors.append(f"{role}: {error}")
            finally:
                if font is not None:
                    font.close()
        if errors:
            raise ProjectIntegrityError("paired rollback failed: " + "; ".join(errors))
