from __future__ import annotations

import hashlib
import json
import logging
import math
import os
import uuid
from copy import deepcopy
from dataclasses import asdict, replace
from datetime import datetime, timezone
from pathlib import Path

from defcon import Font as DefconFont

from . import __version__
from .core import (
    EDGE_PROFILE_VERSION,
    MOTION_ALGORITHM_VERSION,
    OUTLINE_RECONSTRUCTION_VERSION,
    SEED_DERIVATION_VERSION,
    TOPOLOGY_VERSION,
    derive_effective_seed,
    generate_pair,
    regenerate_motion_from_topology,
)
from .geometry import master_contours_to_union
from .fingerprints import glyph_content_digest, source_fingerprint
from .input_ufo import defcon_glyph_to_outline
from .model import (
    CubicSegment,
    GenerationResult,
    GenerationSettings,
    MasterGlyph,
    master_contour_segments,
)
from .topology import read_topology, topology_digest, write_topology
from .ufo import LIB_KEY, master_from_glyph
from .validation import validate_pair


logger = logging.getLogger(__name__)


LIVE_PROJECT_FORMAT = "com.fracturize.live-project"
LIVE_PROJECT_VERSION = 1
PROJECT_ID_KEY = "com.fracturize.liveProjectID"
FONT_ID_KEY = "com.fracturize.liveFontID"
FONT_ROLE_KEY = "com.fracturize.liveFontRole"
PAIR_REVISION_KEY = "com.fracturize.pairRevision"
SOURCE_FINGERPRINT_KEY = "com.fracturize.sourceFingerprint"
TOPOLOGY_DIGEST_KEY = "com.fracturize.topologyDigest"

# RoboFont assigns a different Smart Sets document identifier whenever it
# opens each UFO. This is application/session metadata rather than user font
# data and cannot legitimately match across two simultaneously open masters.
# Keep this allowlist exact: every other font-lib entry remains comparable.
VOLATILE_ROBOFONT_FONT_LIB_KEYS = {
    "com.typemytype.robofont.smartSets.uniqueKey",
}


class LiveProjectError(RuntimeError):
    pass


class LiveProjectIntegrityError(LiveProjectError):
    pass


class FontsUnavailableError(LiveProjectError):
    pass


class ComponentConfirmationRequired(LiveProjectError):
    pass


class EditedOutputError(LiveProjectError):
    pass


class StaleSourceError(LiveProjectError):
    pass


def _now():
    return datetime.now(timezone.utc).isoformat()


def _native(value):
    return value.naked() if hasattr(value, "naked") else value


def _mark_changed(value):
    """Notify RoboFont wrappers when available; defcon mutations self-notify."""

    callback = getattr(value, "changed", None)
    if callback is not None:
        callback()


def _font_path(font):
    path = getattr(font, "path", None)
    return str(path) if path else None


def _font_label(font):
    info = _native(font).info
    family = info.familyName or "Untitled"
    style = info.styleName or "Regular"
    return f"{family} {style}"


def font_identity(font):
    native = _native(font)
    names = sorted(native.keys())
    return {
        "path": _font_path(font),
        "familyName": native.info.familyName,
        "styleName": native.info.styleName,
        "unitsPerEm": float(native.info.unitsPerEm or 1000),
        "glyphSetDigest": hashlib.sha256("\0".join(names).encode("utf-8")).hexdigest(),
    }


def _serializable(value):
    if hasattr(value, "getDataForSerialization"):
        return value.getDataForSerialization()
    if hasattr(value, "items"):
        return dict(value.items())
    return value


def _semantic_value(value):
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if hasattr(value, "getDataForSerialization"):
        return _semantic_value(value.getDataForSerialization())
    if hasattr(value, "items"):
        return {
            str(key): _semantic_value(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, (list, tuple)):
        return [_semantic_value(item) for item in value]
    return str(value)


def guideline_records(font):
    """Return diagnostic records for live guidelines, including volatile IDs."""

    native = _native(font)
    guidelines = getattr(font, "guidelines", native.guidelines)
    records = []
    for index, guideline in enumerate(guidelines):
        serialized = _semantic_value(_serializable(guideline))
        serialized = serialized if isinstance(serialized, dict) else {}
        records.append(
            {
                "index": index,
                "x": _semantic_value(getattr(guideline, "x", serialized.get("x"))),
                "y": _semantic_value(getattr(guideline, "y", serialized.get("y"))),
                "angle": _semantic_value(
                    getattr(guideline, "angle", serialized.get("angle"))
                ),
                "name": _semantic_value(
                    getattr(guideline, "name", serialized.get("name"))
                ),
                "color": _semantic_value(
                    getattr(guideline, "color", serialized.get("color"))
                ),
                "locked": _semantic_value(
                    getattr(guideline, "locked", serialized.get("locked"))
                ),
                "identifier": _semantic_value(
                    getattr(guideline, "identifier", serialized.get("identifier"))
                ),
                "lib": _semantic_value(
                    getattr(guideline, "lib", serialized.get("lib", {}))
                ),
            }
        )
    return records


def semantic_guidelines(font):
    """Compare guideline content while ignoring order and RoboFont document IDs.

    RoboFont may assign a different in-memory ``identifier`` to the same UFO
    guideline in each open document. The identifier and list index are not
    semantic user data. Geometry, labels, colors, locked state, and the full
    guideline lib remain strictly comparable.
    """

    semantic = [
        {
            key: value
            for key, value in record.items()
            if key not in {"index", "identifier"}
        }
        for record in guideline_records(font)
    ]
    return sorted(
        semantic,
        key=lambda record: json.dumps(record, sort_keys=True, default=str),
    )


def shared_font_data(font):
    """Data that must remain identical between the two candidate masters."""

    native = _native(font)
    owned_lib_keys = {
        PROJECT_ID_KEY,
        FONT_ID_KEY,
        FONT_ROLE_KEY,
        *VOLATILE_ROBOFONT_FONT_LIB_KEYS,
    }
    owned_glyph_keys = {
        LIB_KEY,
        PAIR_REVISION_KEY,
        SOURCE_FINGERPRINT_KEY,
        TOPOLOGY_DIGEST_KEY,
    }

    def object_data(value):
        data = _serializable(value)
        return data if isinstance(data, (dict, list, str, int, float, bool, type(None))) else str(data)

    glyph_metadata = {}
    for name in native.keys():
        glyph = native[name]
        glyph_metadata[name] = {
            "height": glyph.height,
            "verticalOrigin": getattr(glyph, "verticalOrigin", None),
            "anchors": [object_data(anchor) for anchor in glyph.anchors],
            "guidelines": [object_data(guideline) for guideline in glyph.guidelines],
            "note": glyph.note,
            "lib": {
                key: value for key, value in glyph.lib.items() if key not in owned_glyph_keys
            },
            "image": object_data(glyph.image),
        }

    non_default_layer_glyphs = {}
    default_layer = native.layers.defaultLayer

    def complete_layer_glyph_data(glyph):
        data = dict(glyph.getDataForSerialization())
        data.pop("_contours", None)
        data.pop("_shallowLoadedContours", None)
        data.pop("tempLib", None)
        data["contours"] = [
            {
                "identifier": contour.identifier,
                "points": [
                    {
                        "x": point.x,
                        "y": point.y,
                        "segmentType": point.segmentType,
                        "smooth": point.smooth,
                        "name": point.name,
                        "identifier": point.identifier,
                    }
                    for point in contour
                ],
            }
            for contour in glyph
        ]
        return data

    for layer in native.layers:
        if layer is default_layer:
            continue
        non_default_layer_glyphs[layer.name] = {
            name: complete_layer_glyph_data(layer[name])
            for name in sorted(layer.keys())
        }

    def file_digests(file_set):
        return {
            name: hashlib.sha256(file_set[name]).hexdigest()
            for name in sorted(getattr(file_set, "fileNames", ()))
        }

    info_data = dict(_serializable(native.info))
    # The two working documents intentionally have distinct role names.
    # All other font-info data must remain synchronized.
    info_data.pop("styleName", None)

    return {
        "glyphNames": sorted(native.keys()),
        "glyphOrder": list(native.glyphOrder),
        "widths": {name: native[name].width for name in native.keys()},
        "unicodes": {name: list(native[name].unicodes) for name in native.keys()},
        "glyphMetadata": glyph_metadata,
        "kerning": sorted((list(pair), value) for pair, value in native.kerning.items()),
        "groups": {name: list(members) for name, members in sorted(native.groups.items())},
        "features": native.features.text or "",
        "info": info_data,
        "fontLib": {
            key: value for key, value in native.lib.items() if key not in owned_lib_keys
        },
        "layerOrder": list(native.layers.layerOrder),
        "layerGlyphSets": {
            layer.name: sorted(layer.keys()) for layer in native.layers
        },
        "nonDefaultLayerGlyphs": non_default_layer_glyphs,
        "guidelines": semantic_guidelines(font),
        "dataFiles": file_digests(native.data),
        "imageFiles": file_digests(native.images),
    }


def validate_working_font_pair(intact_font, eroded_font):
    first = shared_font_data(intact_font)
    second = shared_font_data(eroded_font)
    differences = [key for key in first if first[key] != second[key]]
    if differences:
        details = []
        if "fontLib" in differences:
            keys = sorted(set(first["fontLib"]) | set(second["fontLib"]))
            changed = [key for key in keys if first["fontLib"].get(key) != second["fontLib"].get(key)]
            details.append(
                "fontLib values: "
                + "; ".join(
                    f"{key}: intact={first['fontLib'].get(key)!r}, "
                    f"eroded={second['fontLib'].get(key)!r}"
                    for key in changed
                )
            )
        if "guidelines" in differences:
            details.append(
                "guidelines: "
                f"intact={guideline_records(intact_font)!r}; "
                f"eroded={guideline_records(eroded_font)!r}"
            )
        raise LiveProjectIntegrityError(
            "working fonts differ outside generated outlines: "
            + ", ".join(differences)
            + ((" (" + "; ".join(details) + ")") if details else "")
        )


def _draw_outline_only(glyph, master: MasterGlyph, metadata: dict):
    """Draw a non-live outline, including the unchanged preview path."""

    glyph.clearContours()
    glyph.clearComponents()
    point_pen = glyph.getPointPen()
    fragment_map = []
    for contour in master.contours:
        point_pen.beginPath(identifier=contour.identifier)
        for index, segment in enumerate(master_contour_segments(contour)):
            if isinstance(segment, CubicSegment):
                point_pen.addPoint(segment.control1, segmentType=None)
                point_pen.addPoint(segment.control2, segmentType=None)
                segment_type = "curve"
            else:
                segment_type = "line"
            point_pen.addPoint(
                segment.end,
                segmentType=segment_type,
                identifier=contour.point_ids[index],
            )
        point_pen.endPath()
        fragment_map.append(
            {
                "contourID": contour.identifier,
                "fragmentID": contour.fragment_id,
                "partIndex": contour.part_index,
                "isHole": contour.is_hole,
            }
        )
    glyph.lib[LIB_KEY] = fragment_map
    glyph.lib.update(metadata)
    _mark_changed(glyph)


def _draw_live_outline_only(glyph, master: MasterGlyph, metadata: dict):
    """Replace the default-layer outline on the supplied live glyph object."""

    glyph.clearContours()
    glyph.clearComponents()
    pen = glyph.getPen()
    pen_calls = []
    fragment_map = []
    for contour in master.contours:
        segments = master_contour_segments(contour)
        if not segments:
            continue
        pen.moveTo(segments[0].start)
        pen_calls.append(("moveTo", (segments[0].start,)))
        for segment in segments:
            if isinstance(segment, CubicSegment):
                arguments = (segment.control1, segment.control2, segment.end)
                pen.curveTo(*arguments)
                pen_calls.append(("curveTo", arguments))
            else:
                pen.lineTo(segment.end)
                pen_calls.append(("lineTo", (segment.end,)))
        pen.closePath()
        pen_calls.append(("closePath", ()))
        fragment_map.append(
            {
                "contourID": contour.identifier,
                "fragmentID": contour.fragment_id,
                "partIndex": contour.part_index,
                "isHole": contour.is_hole,
            }
        )

    # Segment pens are the reliable RoboFont boundary for cubic commands, but
    # the protocol has no identifier arguments. Restore the generated IDs on
    # the contours and on-curve points immediately after drawing.
    drawn_contours = list(_native(glyph))
    if len(drawn_contours) != len(master.contours):
        raise LiveProjectError(
            f"live pen wrote {len(drawn_contours)} contours; expected {len(master.contours)}"
        )
    for drawn, generated in zip(drawn_contours, master.contours):
        drawn.identifier = generated.identifier
        drawn_segments = list(drawn.segments)
        if len(drawn_segments) != len(generated.point_ids):
            raise LiveProjectError(
                f"live pen wrote {len(drawn_segments)} segments in {generated.identifier}; "
                f"expected {len(generated.point_ids)}"
            )
        for drawn_segment, point_id in zip(drawn_segments, generated.point_ids):
            drawn_segment[-1].identifier = point_id

    glyph.lib[LIB_KEY] = fragment_map
    glyph.lib.update(metadata)
    _mark_changed(glyph)
    generated_counts = _master_segment_counts(master)
    live_counts = _log_glyph_segment_counts(glyph, glyph_name=master.name, stage="live")
    logger.info(
        "live outline write glyph=%s generated_cubic=%d generated_line=%d "
        "pen_calls=%r live_cubic=%d live_line=%d",
        master.name,
        generated_counts["cubic"],
        generated_counts["line"],
        pen_calls,
        live_counts["cubic"],
        live_counts["line"],
    )


def _master_segment_counts(master: MasterGlyph):
    counts = {"cubic": 0, "line": 0}
    for contour in master.contours:
        for segment in master_contour_segments(contour):
            counts["cubic" if isinstance(segment, CubicSegment) else "line"] += 1
    return counts


def _glyph_segment_counts(glyph):
    counts = {"cubic": 0, "line": 0}
    for contour in _native(glyph):
        for segment in contour.segments:
            segment_type = segment[-1].segmentType
            if segment_type == "curve":
                counts["cubic"] += 1
            elif segment_type == "line":
                counts["line"] += 1
    return counts


def _log_glyph_segment_counts(glyph, *, glyph_name, stage):
    counts = _glyph_segment_counts(glyph)
    logger.info(
        "outline segment counts glyph=%s stage=%s cubic=%d line=%d",
        glyph_name,
        stage,
        counts["cubic"],
        counts["line"],
    )
    return counts


def _glyph_snapshot(glyph):
    """Capture persistent glyph data without copying RoboFont representations."""

    native = _native(glyph)
    # tempLib is non-persistent application state and may contain Objective-C
    # representations which cannot be deep-copied. It is not modified here.
    return deepcopy(native.getDataForSerialization(blacklist=("tempLib",)))


def _restore_glyph(glyph, snapshot):
    """Restore data in place so RoboFont keeps the same live glyph object."""

    native = _native(glyph)
    native.setDataFromSerialization(deepcopy(snapshot))
    _mark_changed(native)
    if glyph is not native:
        _mark_changed(glyph)


def _notify_live_font_changed(font):
    """Mark the backing font and its RoboFont document wrapper as changed."""

    native = _native(font)
    _mark_changed(native)
    if font is not native:
        _mark_changed(font)


class LiveFractureProject:
    """Persistent metadata and topology around user-owned open RoboFont fonts."""

    def __init__(self, path, data, source_font=None, intact_font=None, eroded_font=None):
        self.path = Path(path).resolve()
        self.directory = self.path.parent
        self.data = data
        self.source_font = source_font
        self.intact_font = intact_font
        self.eroded_font = eroded_font

    @classmethod
    def create(
        cls,
        path,
        source_font,
        intact_font,
        eroded_font,
        *,
        project_name,
        project_seed,
        complexity=50,
        rock_edge_detail=50,
    ):
        path = Path(path).resolve()
        if path.exists():
            raise LiveProjectError(f"project file already exists: {path}")
        validate_working_font_pair(intact_font, eroded_font)
        settings = GenerationSettings(
            project_seed=project_seed,
            complexity=complexity,
            rock_edge_detail=rock_edge_detail,
        )
        project_id = str(uuid.uuid4())
        font_ids = {"intact": str(uuid.uuid4()), "eroded": str(uuid.uuid4())}
        for role, font in (("intact", intact_font), ("eroded", eroded_font)):
            native = _native(font)
            native.lib[PROJECT_ID_KEY] = project_id
            native.lib[FONT_ID_KEY] = font_ids[role]
            native.lib[FONT_ROLE_KEY] = role
            _mark_changed(native)
        now = _now()
        data = {
            "format": LIVE_PROJECT_FORMAT,
            "formatVersion": LIVE_PROJECT_VERSION,
            "projectID": project_id,
            "projectName": project_name,
            "createdAt": now,
            "updatedAt": now,
            "generatorVersion": __version__,
            "source": font_identity(source_font),
            "workingFonts": {
                "intact": {
                    "fontID": font_ids["intact"],
                    "path": _font_path(intact_font),
                    "label": _font_label(intact_font),
                },
                "eroded": {
                    "fontID": font_ids["eroded"],
                    "path": _font_path(eroded_font),
                    "label": _font_label(eroded_font),
                },
            },
            "settings": asdict(settings),
            "topologyPolicy": {
                "topologyVersion": TOPOLOGY_VERSION,
                "edgeProfileVersion": EDGE_PROFILE_VERSION,
                "seedDerivationVersion": SEED_DERIVATION_VERSION,
                "fillRule": "non-zero winding",
                "curvePolicy": "adaptive polygonal flattening",
                "componentPolicy": "preserve or confirm once per decomposed batch",
            },
            "motionPolicy": {"algorithmVersion": MOTION_ALGORITHM_VERSION},
            "processedGlyphs": {},
            "failedGlyphs": {},
        }
        project = cls(path, data, source_font, intact_font, eroded_font)
        project._save()
        return project

    @classmethod
    def open(cls, path):
        path = Path(path).resolve()
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception as error:
            raise LiveProjectIntegrityError(f"cannot read project: {error}") from error
        cls._validate_data(data)
        return cls(path, data)

    @staticmethod
    def _validate_data(data):
        if not isinstance(data, dict):
            raise LiveProjectIntegrityError("project root must be an object")
        if data.get("format") != LIVE_PROJECT_FORMAT or data.get("formatVersion") != 1:
            raise LiveProjectIntegrityError("unsupported live project format")
        required = (
            "projectID", "projectName", "source", "workingFonts", "settings",
            "topologyPolicy", "motionPolicy", "processedGlyphs", "failedGlyphs",
        )
        if any(key not in data for key in required):
            raise LiveProjectIntegrityError("live project is missing required fields")
        for key in ("projectID", "projectName"):
            if not isinstance(data[key], str) or not data[key]:
                raise LiveProjectIntegrityError(f"{key} must be a non-empty string")
        source = data["source"]
        if not isinstance(source, dict):
            raise LiveProjectIntegrityError("source must be an object")
        for key in ("familyName", "styleName", "path"):
            if source.get(key) is not None and not isinstance(source.get(key), str):
                raise LiveProjectIntegrityError(f"source.{key} must be a string or null")
        if not isinstance(source.get("glyphSetDigest"), str) or not source["glyphSetDigest"]:
            raise LiveProjectIntegrityError("source.glyphSetDigest must be a non-empty string")
        units_per_em = source.get("unitsPerEm")
        if (
            isinstance(units_per_em, bool)
            or not isinstance(units_per_em, (int, float))
            or not math.isfinite(units_per_em)
            or units_per_em <= 0
        ):
            raise LiveProjectIntegrityError("source.unitsPerEm must be a finite positive number")
        if not isinstance(data["settings"], dict):
            raise LiveProjectIntegrityError("settings must be an object")
        try:
            GenerationSettings(**data["settings"])
        except (TypeError, ValueError) as error:
            raise LiveProjectIntegrityError(f"invalid project settings: {error}") from error
        if not isinstance(data["topologyPolicy"], dict):
            raise LiveProjectIntegrityError("topologyPolicy must be an object")
        if data["topologyPolicy"].get("topologyVersion") != TOPOLOGY_VERSION:
            raise LiveProjectIntegrityError("unsupported topology version")
        if data["topologyPolicy"].get("edgeProfileVersion") not in {
            None,
            EDGE_PROFILE_VERSION,
        }:
            raise LiveProjectIntegrityError("unsupported edge profile version")
        if not isinstance(data["motionPolicy"], dict):
            raise LiveProjectIntegrityError("motionPolicy must be an object")
        if data["motionPolicy"].get("algorithmVersion") != MOTION_ALGORITHM_VERSION:
            raise LiveProjectIntegrityError("unsupported motion version")
        if not isinstance(data["workingFonts"], dict):
            raise LiveProjectIntegrityError("workingFonts must be an object")
        for role in ("intact", "eroded"):
            record = data["workingFonts"].get(role)
            if (
                not isinstance(record, dict)
                or not isinstance(record.get("fontID"), str)
                or not record["fontID"]
                or (record.get("path") is not None and not isinstance(record.get("path"), str))
            ):
                raise LiveProjectIntegrityError(f"invalid {role} working-font record")
        for key in ("processedGlyphs", "failedGlyphs"):
            if not isinstance(data[key], dict):
                raise LiveProjectIntegrityError(f"{key} must be an object")
        for glyph_name, record in data["processedGlyphs"].items():
            if not isinstance(glyph_name, str) or not isinstance(record, dict):
                raise LiveProjectIntegrityError("invalid processed-glyph record")
            string_fields = (
                "sourceFingerprint", "topologyPath", "topologyDigest",
                "pairRevision", "motionAlgorithmVersion",
            )
            if any(not isinstance(record.get(key), str) or not record[key] for key in string_fields):
                raise LiveProjectIntegrityError(f"invalid processed-glyph record: {glyph_name}")
            fingerprints = record.get("outputFingerprints")
            if not isinstance(fingerprints, dict) or any(
                not isinstance(fingerprints.get(role), str) or not fingerprints[role]
                for role in ("intact", "eroded")
            ):
                raise LiveProjectIntegrityError(f"invalid output fingerprints: {glyph_name}")
            for field in ("topologyComplexity",):
                value = record.get(field)
                if (
                    isinstance(value, bool)
                    or not isinstance(value, int)
                    or not 0 <= value <= 100
                ):
                    raise LiveProjectIntegrityError(
                        f"invalid {field} in processed-glyph record: {glyph_name}"
                    )
            edge_detail = record.get("topologyRockEdgeDetail")
            if edge_detail is not None and (
                isinstance(edge_detail, bool)
                or not isinstance(edge_detail, int)
                or not 0 <= edge_detail <= 100
            ):
                raise LiveProjectIntegrityError(
                    f"invalid topologyRockEdgeDetail in processed-glyph record: {glyph_name}"
                )

    @property
    def settings(self):
        return GenerationSettings(**self.data["settings"])

    @property
    def fonts_available(self):
        return all((self.source_font, self.intact_font, self.eroded_font))

    def _require_fonts(self):
        if not self.fonts_available:
            raise FontsUnavailableError("source, intact, and eroded fonts must all be open")

    def attach_fonts(self, fonts):
        source_candidates = []
        intact = eroded = None
        source_record = self.data["source"]
        for font in fonts:
            native = _native(font)
            font_id = native.lib.get(FONT_ID_KEY)
            if font_id == self.data["workingFonts"]["intact"]["fontID"]:
                intact = font
            elif font_id == self.data["workingFonts"]["eroded"]["fontID"]:
                eroded = font
            identity = font_identity(font)
            path_match = source_record.get("path") and identity.get("path") == source_record.get("path")
            identity_match = all(
                identity.get(key) == source_record.get(key)
                for key in ("familyName", "styleName", "unitsPerEm", "glyphSetDigest")
            )
            if not font_id and (path_match or identity_match):
                source_candidates.append(font)
        self.source_font = source_candidates[0] if len(source_candidates) == 1 else None
        self.intact_font = intact
        self.eroded_font = eroded
        if intact and eroded:
            validate_working_font_pair(intact, eroded)
        return self.fonts_available

    def relink_source(self, font):
        identity = font_identity(font)
        expected = self.data["source"]
        if identity["glyphSetDigest"] != expected["glyphSetDigest"] or identity["unitsPerEm"] != expected["unitsPerEm"]:
            raise LiveProjectIntegrityError("selected source font does not match project identity")
        self.source_font = font
        self.data["source"] = identity
        self._save()

    def refresh_paths(self):
        if self.source_font is not None:
            self.data["source"]["path"] = _font_path(self.source_font)
        for role, font in (("intact", self.intact_font), ("eroded", self.eroded_font)):
            if font is not None:
                self.data["workingFonts"][role]["path"] = _font_path(font)
                self.data["workingFonts"][role]["label"] = _font_label(font)
        self._save()

    def _save(self):
        self.data["updatedAt"] = _now()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(json.dumps(self.data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        os.replace(temporary, self.path)

    def _topology_path(self, glyph_name):
        digest = hashlib.sha256(glyph_name.encode("utf-8")).hexdigest()[:16]
        return self.directory / f"{self.path.stem}-data" / "topology" / f"{digest}.json"

    def _source_outline(self, glyph_name, *, decompose_components=False):
        self._require_fonts()
        native = _native(self.source_font)
        if glyph_name not in native:
            raise LiveProjectError(f"source glyph does not exist: {glyph_name}")
        glyph = native[glyph_name]
        if glyph.components:
            if not decompose_components:
                raise ComponentConfirmationRequired(
                    f"{glyph_name} contains components and requires decomposition confirmation"
                )
            # Defcon/RoboFont fonts contain observer locks and cannot be
            # deep-copied safely. Serialization gives decomposition a detached
            # component graph while leaving the open source document untouched.
            temporary_font = DefconFont()
            temporary_font.setDataFromSerialization(native.getDataForSerialization())
            temporary_font[glyph_name].decomposeAllComponents()
            glyph = temporary_font[glyph_name]
        return defcon_glyph_to_outline(
            glyph,
            units_per_em=float(native.info.unitsPerEm or 1000),
        )

    def glyph_has_components(self, glyph_name):
        """Return whether the live source glyph contains components.

        This query deliberately inspects only the source font. The generated
        working fonts may already contain output edits and must not determine
        the component policy for a Generate operation.
        """

        self._require_fonts()
        native = _native(self.source_font)
        if glyph_name not in native:
            return False
        return bool(native[glyph_name].components)

    def source_fingerprint_for_glyph(self, glyph_name, *, decompose_components=False):
        return source_fingerprint(
            self._source_outline(glyph_name, decompose_components=decompose_components)
        )

    def edited_roles(self, glyph_name):
        record = self.data["processedGlyphs"].get(glyph_name)
        if record is None or not self.fonts_available:
            return ()
        changed = []
        for role, font in (("intact", self.intact_font), ("eroded", self.eroded_font)):
            native = _native(font)
            if glyph_name not in native or glyph_content_digest(native[glyph_name]) != record["outputFingerprints"][role]:
                changed.append(role)
        return tuple(changed)

    def glyph_status(self, glyph_name):
        if glyph_name in self.data["failedGlyphs"]:
            return "failed"
        record = self.data["processedGlyphs"].get(glyph_name)
        if record is None:
            return "unprocessed"
        if self.edited_roles(glyph_name):
            return "output-edited"
        try:
            current = self.source_fingerprint_for_glyph(
                glyph_name,
                decompose_components=record.get("componentsDecomposed", False),
            )
        except Exception:
            return "source-unavailable"
        if current != record["sourceFingerprint"]:
            return "stale"
        if (
            record.get("outlineReconstructionVersion", "polygonal-v1")
            != OUTLINE_RECONSTRUCTION_VERSION
            or
            record["effectiveSeed"] != derive_effective_seed(self.settings, glyph_name)
            or record["topologyComplexity"] != self.settings.complexity
            or record.get(
                "topologyRockEdgeDetail",
                record["topologyComplexity"],
            ) != self.settings.rock_edge_detail
        ):
            return "topology-outdated"
        return "processed"

    def update_settings(self, **changes):
        try:
            settings = replace(self.settings, **changes)
        except (TypeError, ValueError) as error:
            raise LiveProjectError(f"invalid settings: {error}") from error
        self.data["settings"] = asdict(settings)
        self._save()

    def preview_new_topology(self, glyph_name, *, decompose_components=False):
        outline = self._source_outline(
            glyph_name,
            decompose_components=decompose_components,
        )
        return generate_pair(outline, self.settings)

    def preview_motion(self, glyph_name):
        record = self.data["processedGlyphs"].get(glyph_name)
        if record is None:
            raise LiveProjectError(f"glyph has no stored topology: {glyph_name}")
        if record.get("outlineReconstructionVersion", "polygonal-v1") != OUTLINE_RECONSTRUCTION_VERSION:
            raise LiveProjectError(
                f"{glyph_name} uses legacy polygonal exterior topology; explicit topology regeneration is required"
            )
        topology, units_per_em = read_topology(self.directory / record["topologyPath"])
        return regenerate_motion_from_topology(
            topology,
            self.settings,
            units_per_em=units_per_em,
            motion_algorithm_version=self.data["motionPolicy"]["algorithmVersion"],
        )

    def process_result(
        self,
        result: GenerationResult,
        *,
        components_decomposed=False,
        replace_edited=False,
        save_hook=None,
    ):
        self._require_fonts()
        # Reject shared-font divergence before either live outline is touched.
        validate_working_font_pair(self.intact_font, self.eroded_font)
        glyph_name = result.glyph_name
        if not result.validation.compatible:
            raise LiveProjectError(f"blocking validation failure for {glyph_name}")
        edited = self.edited_roles(glyph_name)
        if edited and not replace_edited:
            raise EditedOutputError(
                f"{glyph_name} was edited in {', '.join(edited)}"
            )
        source_outline = self._source_outline(
            glyph_name,
            decompose_components=components_decomposed,
        )
        source_digest = source_fingerprint(source_outline)
        topology_path = self._topology_path(glyph_name)
        candidate = topology_path.with_suffix(".candidate.json")
        old_topology = topology_path.read_bytes() if topology_path.exists() else None
        old_project = self.path.read_bytes()
        old_data = deepcopy(self.data)
        target_glyphs = {
            "intact": self.intact_font[glyph_name],
            "eroded": self.eroded_font[glyph_name],
        }
        backups = {
            role: _glyph_snapshot(glyph)
            for role, glyph in target_glyphs.items()
        }
        undo_glyphs = []
        for glyph in target_glyphs.values():
            if hasattr(glyph, "prepareUndo"):
                glyph.prepareUndo("Fracturize Generated Outline")
                undo_glyphs.append(glyph)
        try:
            topology_hash = write_topology(
                result,
                candidate,
                units_per_em=self.data["source"]["unitsPerEm"],
            )
            pair_revision = str(uuid.uuid4())
            metadata = {
                PAIR_REVISION_KEY: pair_revision,
                SOURCE_FINGERPRINT_KEY: source_digest,
                TOPOLOGY_DIGEST_KEY: topology_hash,
            }
            _draw_live_outline_only(target_glyphs["intact"], result.intact, metadata)
            _notify_live_font_changed(self.intact_font)
            if save_hook:
                save_hook("after_intact_write")
            _draw_live_outline_only(target_glyphs["eroded"], result.eroded, metadata)
            _notify_live_font_changed(self.eroded_font)
            if save_hook:
                save_hook("after_eroded_write")

            reopened_intact = master_from_glyph(_native(self.intact_font)[glyph_name])
            reopened_eroded = master_from_glyph(_native(self.eroded_font)[glyph_name])
            report = validate_pair(
                source_silhouette=master_contours_to_union(result.intact.contours),
                intact=reopened_intact,
                eroded=reopened_eroded,
                units_per_em=self.data["source"]["unitsPerEm"],
                minimum_area=result.profile.minimum_area,
            )
            if not report.compatible:
                raise LiveProjectError(f"live output validation failed for {glyph_name}")
            validate_working_font_pair(self.intact_font, self.eroded_font)
            if save_hook:
                save_hook("after_validation")
            topology_path.parent.mkdir(parents=True, exist_ok=True)
            os.replace(candidate, topology_path)
            if save_hook:
                save_hook("after_topology_replace")
            output_fingerprints = {
                "intact": glyph_content_digest(_native(self.intact_font)[glyph_name]),
                "eroded": glyph_content_digest(_native(self.eroded_font)[glyph_name]),
            }
            self.data["processedGlyphs"][glyph_name] = {
                "status": "processed",
                "sourceFingerprint": source_digest,
                "outputFingerprints": output_fingerprints,
                "topologyPath": str(topology_path.relative_to(self.directory)),
                "topologyDigest": topology_hash,
                "topologyComplexity": result.profile.value,
                "topologyRockEdgeDetail": result.rock_edge_detail,
                "outlineReconstructionVersion": result.outline_reconstruction_version,
                "effectiveSeed": result.effective_seed,
                "pairRevision": pair_revision,
                "componentsDecomposed": bool(components_decomposed),
                "motionAlgorithmVersion": self.data["motionPolicy"]["algorithmVersion"],
                "updatedAt": _now(),
            }
            self.data["failedGlyphs"].pop(glyph_name, None)
            self._save()
            for glyph in undo_glyphs:
                if hasattr(glyph, "performUndo"):
                    glyph.performUndo()
            return report
        except Exception:
            _restore_glyph(target_glyphs["intact"], backups["intact"])
            _restore_glyph(target_glyphs["eroded"], backups["eroded"])
            _notify_live_font_changed(self.intact_font)
            _notify_live_font_changed(self.eroded_font)
            for glyph in undo_glyphs:
                if hasattr(glyph, "performUndo"):
                    glyph.performUndo()
            if old_topology is None:
                if topology_path.exists():
                    topology_path.unlink()
            else:
                topology_path.write_bytes(old_topology)
            self.data = old_data
            self.path.write_bytes(old_project)
            if candidate.exists():
                candidate.unlink()
            raise

    def regenerate_motion(self, glyph_name, *, replace_edited=False, save_hook=None):
        record = self.data["processedGlyphs"].get(glyph_name)
        if record is None:
            raise LiveProjectError(f"glyph is not processed: {glyph_name}")
        current_source = self.source_fingerprint_for_glyph(
            glyph_name,
            decompose_components=record.get("componentsDecomposed", False),
        )
        if current_source != record["sourceFingerprint"]:
            raise StaleSourceError(f"source glyph changed: {glyph_name}")
        result = self.preview_motion(glyph_name)
        return self.process_result(
            result,
            components_decomposed=record.get("componentsDecomposed", False),
            replace_edited=replace_edited,
            save_hook=save_hook,
        )

    def regenerate_topology(self, glyph_name, *, replace_edited=False, save_hook=None):
        record = self.data["processedGlyphs"].get(glyph_name, {})
        result = self.preview_new_topology(
            glyph_name,
            decompose_components=record.get("componentsDecomposed", False),
        )
        return self.process_result(
            result,
            components_decomposed=record.get("componentsDecomposed", False),
            replace_edited=replace_edited,
            save_hook=save_hook,
        )

    def record_failure(self, glyph_name, error):
        self.data["failedGlyphs"][glyph_name] = {
            "message": str(error),
            "updatedAt": _now(),
        }
        self._save()

    def validate(self):
        self._require_fonts()
        validate_working_font_pair(self.intact_font, self.eroded_font)
        findings = []
        for glyph_name, record in self.data["processedGlyphs"].items():
            topology_path = self.directory / record["topologyPath"]
            if not topology_path.is_file() or topology_digest(topology_path) != record["topologyDigest"]:
                findings.append(f"{glyph_name}: topology mismatch")
            roles = self.edited_roles(glyph_name)
            if roles:
                findings.append(f"{glyph_name}: edited output ({', '.join(roles)})")
        return findings

    def sidebearing_warnings(self, result):
        warnings = []
        for state_name, master in (("intact", result.intact), ("eroded", result.eroded)):
            points = [point for contour in master.contours for point in contour.points]
            if points and (min(x for x, _ in points) < 0 or max(x for x, _ in points) > master.width):
                warnings.append(f"{state_name} fragments extend beyond sidebearings")
        return warnings
