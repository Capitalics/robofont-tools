from __future__ import annotations

import json
import plistlib
from copy import deepcopy
from dataclasses import replace
from pathlib import Path

import pytest
from defcon import Font

from fracturize.controller import FracturizeController
from fracturize.live_project import (
    FONT_ID_KEY,
    LiveFractureProject,
    LiveProjectError,
    VOLATILE_ROBOFONT_FONT_LIB_KEYS,
    _draw_live_outline_only,
    _glyph_segment_counts,
    _log_glyph_segment_counts,
    guideline_records,
    glyph_content_digest,
    shared_font_data,
    validate_working_font_pair,
)
from fracturize.model import CubicSegment, LineSegment, MasterContour, MasterGlyph
from fracturize.robofont_adapter import collect_glyph_names, master_to_preview_glyph
from fracturize.ufo import master_from_glyph


ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / "Fracturize.roboFontExt"
SOURCE_FIXTURE = ROOT / "tests" / "fixtures" / "FracturizeRegression.ufo"


class FakeEnvironment:
    def __init__(self, source, *, fail_on_write=None):
        self.source = source
        self.fonts = [source]
        self.current_name = "O"
        self.selection = ("A", "M")
        self.fail_on_write = fail_on_write
        self.write_count = 0
        self.opened_paths = []

    def current_font(self):
        return self.source

    def current_glyph_name(self):
        return self.current_name

    def selected_glyph_names(self, font=None):
        return self.selection

    def write_working_font_copy(self, source, path, *, style_name):
        self.write_count += 1
        if self.fail_on_write == self.write_count:
            raise OSError(f"injected working-font write failure {self.write_count}")
        duplicate = Font()
        duplicate.setDataFromSerialization(source.getDataForSerialization())
        duplicate.info.styleName = style_name
        duplicate.save(path)

    def open_font(self, path):
        self.opened_paths.append(Path(path).resolve())
        font = Font(path)
        self.fonts.append(font)
        return font

    def save_font(self, font):
        font.save()

    def all_fonts(self):
        return list(self.fonts)

    def ensure_project_fonts_open(self, project, logger=None):
        project.attach_fonts(self.fonts)
        opened = []
        for role in ("intact", "eroded"):
            if getattr(project, f"{role}_font") is None:
                path = project.data["workingFonts"][role].get("path")
                if path:
                    opened.append(self.open_font(path))
        if project.source_font is None and project.data["source"].get("path"):
            opened.append(self.open_font(project.data["source"]["path"]))
        return project.attach_fonts([*self.fonts, *opened])


class LiveGlyphProxy:
    """Small RoboFont-like wrapper used to verify live wrapper writes."""

    def __init__(self, glyph):
        self._glyph = glyph
        self.changed_calls = 0

    def naked(self):
        return self._glyph

    def changed(self):
        self.changed_calls += 1
        self._glyph.dirty = True

    def __getattr__(self, name):
        return getattr(self._glyph, name)


class RecordingLiveGlyphProxy(LiveGlyphProxy):
    """RoboFont-like glyph whose segment pen records the protocol boundary."""

    def __init__(self, glyph):
        super().__init__(glyph)
        self.pen_calls = []

    def getPen(self):
        recording = self
        delegate = self._glyph.getPen()

        class RecordingPen:
            def moveTo(self, point):
                recording.pen_calls.append(("moveTo", (point,)))
                delegate.moveTo(point)

            def lineTo(self, point):
                recording.pen_calls.append(("lineTo", (point,)))
                delegate.lineTo(point)

            def curveTo(self, *points):
                recording.pen_calls.append(("curveTo", points))
                delegate.curveTo(*points)

            def closePath(self):
                recording.pen_calls.append(("closePath", ()))
                delegate.closePath()

        return RecordingPen()


class LiveFontProxy:
    def __init__(self, font):
        self._font = font
        self._glyphs = {}
        self.changed_calls = 0

    def naked(self):
        return self._font

    def changed(self):
        self.changed_calls += 1
        self._font.dirty = True

    def __getitem__(self, glyph_name):
        if glyph_name not in self._glyphs:
            self._glyphs[glyph_name] = LiveGlyphProxy(self._font[glyph_name])
        return self._glyphs[glyph_name]

    def __getattr__(self, name):
        return getattr(self._font, name)


class GuidelineFontProxy:
    def __init__(self, font, guidelines):
        self._font = font
        self.guidelines = guidelines

    def naked(self):
        return self._font

    def __getattr__(self, name):
        return getattr(self._font, name)


class SemanticGuideline:
    def __init__(
        self,
        *,
        x=0,
        y=0,
        angle=0,
        name=None,
        color=None,
        locked=False,
        identifier=None,
        lib=None,
    ):
        self.x = x
        self.y = y
        self.angle = angle
        self.name = name
        self.color = color
        self.locked = locked
        self.identifier = identifier
        self.lib = {} if lib is None else lib


def guideline_pair(project, intact_guidelines, eroded_guidelines):
    return (
        GuidelineFontProxy(project.intact_font, intact_guidelines),
        GuidelineFontProxy(project.eroded_font, eroded_guidelines),
    )


def enriched_source():
    source = Font(SOURCE_FIXTURE)
    source.groups["com.example.A"] = ["A"]
    source.kerning[("A", "O")] = -37
    source.features.text = "feature kern { pos A O -37; } kern;"
    source.lib["com.example.privateData"] = {"preserve": True}
    source.data["com.example/readme.txt"] = b"synthetic fixture data"
    source.glyphOrder = list(source.keys())
    anchor = source["O"].instantiateAnchor()
    anchor.name = "top"
    anchor.x = 317
    anchor.y = 720
    source["O"].appendAnchor(anchor)
    source["O"].note = "preserve this note"
    guideline = source.instantiateGuideline()
    guideline.x = 0
    guideline.y = 0
    guideline.name = "baseline"
    source.appendGuideline(guideline)
    background = source.layers.newLayer("background")
    background.insertGlyph(source["O"], name="O")
    return source


@pytest.fixture
def live_controller(tmp_path):
    source = enriched_source()
    environment = FakeEnvironment(source)
    controller = FracturizeController(environment)
    project = controller.create_project(
        tmp_path / "Internal.fracturize.json",
        project_name="Internal",
        project_seed="stage3-tests",
        complexity=50,
    )
    return controller, project, environment


def test_bundle_plist_menu_and_single_canonical_package():
    with (BUNDLE / "info.plist").open("rb") as stream:
        info = plistlib.load(stream)
    assert info["name"] == "Fracturize"
    assert info["requiresVersionMajor"] == "4"
    assert info["requiresVersionMinor"] == "6"
    assert info["addToMenu"] == [
        {"path": "startup.py", "preferredName": "Fracturize", "shortKey": ""}
    ]
    assert (BUNDLE / "lib" / "fracturize" / "ui.py").is_file()
    assert not (ROOT / "src" / "fracturize").exists()
    startup = (BUNDLE / "lib" / "startup.py").read_text()
    assert "installNeededPackages" in startup
    assert "shapely>=2.1,<3" in startup


def test_window_source_registers_and_cleans_up_observers():
    source = (BUNDLE / "lib" / "fracturize" / "ui.py").read_text()
    assert "addObserver(self" in source
    assert "removeObserver(self" in source
    assert "window_closed()" in source
    assert "fontDidClose" in source
    assert "fontDidSave" in source
    assert "callAfter(self._process_batch)" in source
    assert "resultCallback=self._createProjectDialogResult" in source
    assert "resultCallback=self._openProjectDialogResult" in source
    assert "cancelCallback=self._openProjectDialogCancelled" in source
    assert "traceback.format_exc()" in source
    assert "self.controller.set_complexity_from_slider(" in source
    assert "regenerate_topology=True" in source


def test_regression_ufo_is_outside_the_extension_bundle():
    assert not list(BUNDLE.rglob("*.ufo"))
    assert (ROOT / "tests" / "fixtures" / "FracturizeRegression.ufo").is_dir()


def test_glyph_collection_combines_current_selection_and_direct_names():
    assert collect_glyph_names("O", ("A", "O"), "M, R eight") == (
        "O", "A", "M", "R", "eight"
    )


def test_selection_modes_resolve_current_selection_and_manual_names(live_controller):
    controller, project, environment = live_controller
    assert controller.selected_names("", include_current=True, include_selection=False) == ("O",)
    assert controller.selected_names("", include_current=False, include_selection=True) == ("A", "M")
    assert controller.selected_names("H R eight", include_current=False, include_selection=False) == (
        "H",
        "R",
        "eight",
    )


def test_four_mutually_exclusive_modes_resolve_expected_names(live_controller):
    controller, project, environment = live_controller
    environment.current_name = "O"
    environment.selection = ("A", "M", "A")
    source_order = tuple(project.source_font.glyphOrder)
    remaining = tuple(name for name in project.source_font.keys() if name not in source_order)

    assert controller.resolve_glyph_names("current") == ("O",)
    assert controller.resolve_glyph_names("selected") == ("A", "M")
    assert controller.resolve_glyph_names("manual", "H R H missingGlyph") == (
        "H",
        "R",
        "missingGlyph",
    )
    assert controller.resolve_glyph_names("all") == source_order + remaining


def test_batch_summary_separates_completed_skipped_rejected_and_failed(live_controller):
    controller, project, environment = live_controller
    controller.process_names(["O"], action="generate")

    result = controller.process_names(
        ["O", "i", "missingGlyph", "I"],
        action="generate",
    )

    assert result["completed"] == ["i", "I"]
    assert result["skipped"] == [("O", "already processed")]
    assert result["rejected"] == []
    assert result["failed"][0][0] == "missingGlyph"
    assert result["cancelled"] is False


def test_cooperative_batch_cancellation_stops_after_completed_glyph(live_controller):
    controller, project, environment = live_controller
    updates = []

    def item_complete(position, total, glyph_name, summary):
        updates.append((position, glyph_name, len(summary["completed"])))
        if position == 2:
            controller.request_cancel()

    result = controller.process_names(
        ["O", "I", "A"],
        action="generate",
        item_complete=item_complete,
    )

    assert result["completed"] == ["O", "I"]
    assert result["cancelled"] is True
    assert project.glyph_status("A") == "unprocessed"
    assert updates == [(1, "O", 1), (2, "I", 2)]


def test_batch_progress_reports_each_glyph_and_running_totals(live_controller):
    controller, project, environment = live_controller
    starts = []
    completions = []

    result = controller.process_names(
        ["O", "missingGlyph", "I"],
        action="generate",
        progress=lambda index, total, name: starts.append((index + 1, total, name)),
        item_complete=lambda position, total, name, summary: completions.append(
            (
                position,
                total,
                name,
                len(summary["completed"]),
                len(summary["skipped"]),
                len(summary["rejected"]),
                len(summary["failed"]),
            )
        ),
    )

    assert starts == [(1, 3, "O"), (2, 3, "missingGlyph"), (3, 3, "I")]
    assert completions == [
        (1, 3, "O", 1, 0, 0, 0),
        (2, 3, "missingGlyph", 1, 0, 0, 1),
        (3, 3, "I", 2, 0, 0, 1),
    ]
    assert result["completed"] == ["O", "I"]


def test_batch_ui_has_all_mode_progress_cancel_and_button_locking():
    source = (BUNDLE / "lib" / "fracturize" / "ui.py").read_text()
    assert '"All glyphs (0)"' in source
    assert "item_complete=self._batch_item_complete" in source
    assert "NSDate.dateWithTimeIntervalSinceNow_" in source
    assert 'self.w.cancel.enable(running)' in source
    for button in ("generate", "preview", "openProject", "createProject"):
        assert f'"{button}"' in source


def test_resolved_names_deduplicate_across_all_modes_preserving_order(live_controller):
    controller, project, environment = live_controller
    environment.current_name = "A"
    environment.selection = ("A", "M", "O")
    assert controller.selected_names("M R A") == ("A", "M", "O", "R")


def test_ui_batch_passes_complete_resolved_list_to_process_names():
    source = (BUNDLE / "lib" / "fracturize" / "ui.py").read_text()
    assert "names = tuple(self._batch_queue)" in source
    call = source.index("self.controller.process_names(")
    assert "names," in source[call:call + 100]
    assert "Selected glyphs ({selected_count})" in source


def test_project_creation_writes_and_opens_complete_named_working_fonts(live_controller):
    controller, project, environment = live_controller
    source_data = shared_font_data(project.source_font)
    assert shared_font_data(project.intact_font) == source_data
    assert shared_font_data(project.eroded_font) == source_data
    assert Path(project.intact_font.path).name == "Internal-Intact.ufo"
    assert Path(project.eroded_font.path).name == "Internal-Eroded.ufo"
    assert Path(project.intact_font.path).is_dir()
    assert Path(project.eroded_font.path).is_dir()
    assert project.path.is_file()
    assert project.intact_font.info.styleName.endswith("Fracture Intact")
    assert project.eroded_font.info.styleName.endswith("Fracture Eroded")
    assert project.intact_font.lib[FONT_ID_KEY]
    assert project.eroded_font.lib[FONT_ID_KEY]
    assert project.intact_font.lib[FONT_ID_KEY] != project.eroded_font.lib[FONT_ID_KEY]
    assert project.intact_font.data["com.example/readme.txt"] == b"synthetic fixture data"
    assert project.data["workingFonts"]["intact"]["path"] == str(project.intact_font.path)
    assert controller.project is project
    assert project.fonts_available
    validate_working_font_pair(project.intact_font, project.eroded_font)


@pytest.mark.parametrize("result", [None, [], ()])
def test_create_project_dialog_cancellation_has_no_path(result):
    assert FracturizeController.project_path_from_dialog_result(result) is None


def test_create_project_dialog_result_is_normalized(tmp_path):
    selected = tmp_path / "Weathering.json"
    assert FracturizeController.project_path_from_dialog_result([str(selected)]) == (
        tmp_path / "Weathering.fracturize.json"
    )


def test_create_project_rejects_unsaved_source(tmp_path):
    source = Font()
    controller = FracturizeController(FakeEnvironment(source))
    with pytest.raises(LiveProjectError, match="unsaved"):
        controller.create_project(
            tmp_path / "Unsaved.fracturize.json",
            project_name="Unsaved",
            project_seed="unsaved",
        )
    assert not list(tmp_path.glob("Unsaved*"))


def test_create_project_rejects_invalid_destination(tmp_path):
    controller = FracturizeController(FakeEnvironment(enriched_source()))
    missing = tmp_path / "missing" / "Invalid.fracturize.json"
    with pytest.raises(LiveProjectError, match="destination does not exist"):
        controller.create_project(
            missing,
            project_name="Invalid",
            project_seed="invalid",
        )
    assert controller.project is None


def test_create_project_rolls_back_a_midway_failure(tmp_path):
    environment = FakeEnvironment(enriched_source(), fail_on_write=2)
    controller = FracturizeController(environment)
    path = tmp_path / "Rollback.fracturize.json"
    with pytest.raises(OSError, match="write failure 2"):
        controller.create_project(
            path,
            project_name="Rollback",
            project_seed="rollback",
        )
    assert controller.project is None
    assert not path.exists()
    assert not (tmp_path / "Rollback-Intact.ufo").exists()
    assert not (tmp_path / "Rollback-Eroded.ufo").exists()


def test_generate_replaces_only_outlines_and_owned_metadata(live_controller):
    controller, project, environment = live_controller
    source = project.source_font["O"]
    intact_before = deepcopy(project.intact_font["O"])
    eroded_before = deepcopy(project.eroded_font["O"])
    result = controller.process_names(["O"], action="generate")
    assert result["completed"] == ["O"]
    intact = project.intact_font["O"]
    eroded = project.eroded_font["O"]
    assert intact.width == eroded.width == source.width
    assert intact.unicodes == eroded.unicodes == source.unicodes
    assert intact.note == eroded.note == intact_before.note == eroded_before.note
    assert [(a.name, a.x, a.y) for a in intact.anchors] == [
        (a.name, a.x, a.y) for a in source.anchors
    ]
    assert len(intact) and len(eroded)
    assert glyph_content_digest(intact) != glyph_content_digest(eroded)
    assert project.intact_font.kerning == project.eroded_font.kerning
    assert project.intact_font.groups == project.eroded_font.groups
    assert project.intact_font.features.text == project.eroded_font.features.text
    validate_working_font_pair(project.intact_font, project.eroded_font)


def test_preview_is_the_exact_master_geometry_that_will_be_written(live_controller):
    controller, project, environment = live_controller
    preview = controller.preview("O", regenerate_topology=True)
    assert preview.validation.compatible
    assert master_from_glyph(master_to_preview_glyph(preview.intact)) == preview.intact
    controller.process_names(["O"], action="generate")
    assert master_from_glyph(project.intact_font["O"]) == preview.intact


def test_motion_regeneration_preserves_topology_and_complexity_requires_topology_action(live_controller):
    controller, project, environment = live_controller
    controller.process_names(["O"], action="generate")
    first = deepcopy(project.data["processedGlyphs"]["O"])
    intact_before = master_from_glyph(project.intact_font["O"])
    controller.update_settings(erosion_amount=0.8)
    controller.process_names(["O"], action="motion")
    second = project.data["processedGlyphs"]["O"]
    assert second["topologyDigest"] == first["topologyDigest"]
    assert master_from_glyph(project.intact_font["O"]) == intact_before
    controller.update_settings(complexity=75)
    assert project.glyph_status("O") == "topology-outdated"
    controller.process_names(["O"], action="topology")
    assert project.data["processedGlyphs"]["O"]["topologyDigest"] != first["topologyDigest"]


def test_complexity_slider_state_persists_marks_stale_and_generate_requires_confirmation(live_controller):
    controller, project, environment = live_controller
    controller.process_names(["O"], action="generate")
    first = deepcopy(project.data["processedGlyphs"]["O"])

    change = controller.set_complexity_from_slider(
        89.6,
        glyph_name="O",
    )
    assert change == {
        "previous": 50,
        "complexity": 90,
        "glyphStatus": "topology-outdated",
        "topologyStale": True,
    }
    assert LiveFractureProject.open(project.path).settings.complexity == 90

    declined = controller.process_names(["O"], action="generate")
    assert declined["skipped"] == [("O", "topology regeneration not confirmed")]
    assert project.data["processedGlyphs"]["O"]["topologyDigest"] == first["topologyDigest"]

    accepted = controller.process_names(
        ["O"],
        action="generate",
        confirm_topology_replacement=lambda glyph_name: True,
    )
    assert accepted["completed"] == ["O"]
    second = deepcopy(project.data["processedGlyphs"]["O"])
    assert second["topologyDigest"] != first["topologyDigest"]
    assert second["topologyComplexity"] == 90
    assert project.glyph_status("O") == "processed"

    controller.process_names(["O"], action="topology")
    assert project.data["processedGlyphs"]["O"]["topologyDigest"] == second["topologyDigest"]

    controller.update_settings(erosion_amount=0.7)
    controller.process_names(["O"], action="motion")
    assert project.data["processedGlyphs"]["O"]["topologyDigest"] == second["topologyDigest"]


def test_complexity_preview_uses_selected_value_without_committing(live_controller):
    controller, project, environment = live_controller
    controller.process_names(["O"], action="generate")
    record = deepcopy(project.data["processedGlyphs"]["O"])
    controller.set_complexity_from_slider(10, glyph_name="O")

    preview = controller.preview("O", regenerate_topology=True)

    assert preview.profile.value == 10
    assert len(preview.fragments) == preview.profile.target_fragments == 2
    assert project.data["processedGlyphs"]["O"] == record
    assert project.glyph_status("O") == "topology-outdated"


def test_rock_edge_detail_slider_persists_marks_stale_and_requires_replacement(live_controller):
    controller, project, environment = live_controller
    controller.process_names(["O"], action="generate")
    original = deepcopy(project.data["processedGlyphs"]["O"])

    change = controller.set_rock_edge_detail_from_slider(74.6, glyph_name="O")

    assert change == {
        "previous": 50,
        "rockEdgeDetail": 75,
        "glyphStatus": "topology-outdated",
        "topologyStale": True,
    }
    assert LiveFractureProject.open(project.path).settings.rock_edge_detail == 75
    declined = controller.process_names(["O"], action="generate")
    assert declined["skipped"] == [("O", "topology regeneration not confirmed")]
    assert project.data["processedGlyphs"]["O"] == original

    accepted = controller.process_names(
        ["O"],
        action="generate",
        confirm_topology_replacement=lambda glyph_name: True,
    )
    assert accepted["completed"] == ["O"]
    record = project.data["processedGlyphs"]["O"]
    assert record["topologyRockEdgeDetail"] == 75
    assert record["topologyDigest"] != original["topologyDigest"]
    assert project.glyph_status("O") == "processed"


def test_rock_edge_detail_preview_and_motion_only_keep_commit_boundaries(live_controller):
    controller, project, environment = live_controller
    controller.process_names(["O"], action="generate")
    original = deepcopy(project.data["processedGlyphs"]["O"])
    controller.set_rock_edge_detail_from_slider(100, glyph_name="O")

    preview = controller.preview("O", regenerate_topology=True)

    assert preview.rock_edge_detail == 100
    assert preview.validation.compatible
    assert project.data["processedGlyphs"]["O"] == original
    controller.process_names(["O"], action="motion")
    after_motion = project.data["processedGlyphs"]["O"]
    assert after_motion["topologyDigest"] == original["topologyDigest"]
    assert after_motion["topologyRockEdgeDetail"] == 50
    assert project.settings.rock_edge_detail == 100
    assert project.glyph_status("O") == "topology-outdated"


def test_rock_edge_roughness_slider_persists_marks_stale_and_previews(live_controller):
    controller, project, environment = live_controller
    controller.process_names(["O"], action="generate")
    original = deepcopy(project.data["processedGlyphs"]["O"])

    change = controller.set_rock_edge_roughness_from_slider(99.6, glyph_name="O")
    preview = controller.preview("O", regenerate_topology=True)

    assert change == {
        "previous": 50,
        "rockEdgeRoughness": 100,
        "glyphStatus": "topology-outdated",
        "topologyStale": True,
    }
    assert LiveFractureProject.open(project.path).settings.rock_edge_roughness == 100
    assert preview.rock_edge_roughness == 100
    assert preview.validation.compatible
    assert project.data["processedGlyphs"]["O"] == original


def test_ui_exposes_rock_edge_roughness_directly_below_detail():
    source = (BUNDLE / "lib" / "fracturize" / "ui.py").read_text()

    detail = source.index('self._add_slider("edgeDetail", "Rock Edge Detail"')
    roughness = source.index('self._add_slider("edgeRoughness", "Rock Edge Roughness"')
    crumble = source.index('self._add_slider("crumble", "Overall Crumble Amount"')
    assert detail < roughness < crumble
    assert '"edgeRoughness": settings.rock_edge_roughness' in source
    assert "def rockEdgeRoughnessCallback(self, sender):" in source
    assert "self.controller.set_rock_edge_roughness_from_slider(" in source


def test_batch_generation_uses_saved_rock_edge_detail(live_controller):
    controller, project, environment = live_controller
    controller.set_rock_edge_detail_from_slider(25)

    result = controller.process_names(["O", "I"], action="generate")

    assert result["completed"] == ["O", "I"]
    assert all(
        project.data["processedGlyphs"][name]["topologyRockEdgeDetail"] == 25
        for name in result["completed"]
    )


def test_ui_exposes_rock_edge_detail_callback_and_restores_numeric_setting():
    source = (BUNDLE / "lib" / "fracturize" / "ui.py").read_text()

    assert '"Rock Edge Detail"' in source
    assert '"edgeDetail": settings.rock_edge_detail' in source
    assert "def rockEdgeDetailCallback(self, sender):" in source
    assert "self.controller.set_rock_edge_detail_from_slider(" in source
    assert "self.previewCurrent(regenerate_topology=True)" in source


def test_seed_change_requires_explicit_topology_regeneration(live_controller):
    controller, project, environment = live_controller
    controller.process_names(["O"], action="generate")
    old_seed = project.data["processedGlyphs"]["O"]["effectiveSeed"]
    controller.update_settings(glyph_seed_override="alternate-layout")
    assert project.glyph_status("O") == "topology-outdated"
    controller.process_names(["O"], action="topology")
    assert project.glyph_status("O") == "processed"
    assert project.data["processedGlyphs"]["O"]["effectiveSeed"] != old_seed


def test_component_preprocessing_is_automatic_and_never_modifies_source(live_controller):
    controller, project, environment = live_controller
    before = {
        "source": glyph_content_digest(project.source_font["i"]),
        "intact": glyph_content_digest(project.intact_font["i"]),
        "eroded": glyph_content_digest(project.eroded_font["i"]),
    }

    generated = controller.process_names(["i"], action="generate")

    assert generated["completed"] == ["i"]
    assert generated["rejected"] == []
    assert project.data["processedGlyphs"]["i"]["componentsDecomposed"] is True
    assert glyph_content_digest(project.source_font["i"]) == before["source"]
    assert glyph_content_digest(project.intact_font["i"]) != before["intact"]
    assert glyph_content_digest(project.eroded_font["i"]) != before["eroded"]
    assert not project.intact_font["i"].components
    assert not project.eroded_font["i"].components


def test_component_checkbox_on_decomposes_only_generated_working_glyphs(live_controller):
    controller, project, environment = live_controller
    source_digest = glyph_content_digest(project.source_font["i"])
    source_components = len(project.source_font["i"].components)

    accepted = controller.process_names(
        ["i"], action="generate", decompose_components=True
    )

    assert accepted["completed"] == ["i"]
    assert project.data["processedGlyphs"]["i"]["componentsDecomposed"] is True
    assert glyph_content_digest(project.source_font["i"]) == source_digest
    assert len(project.source_font["i"].components) == source_components
    assert not project.intact_font["i"].components
    assert not project.eroded_font["i"].components


def test_automatic_preprocessing_and_saved_cubics_for_requested_glyph_shapes(tmp_path):
    source = enriched_source()

    def append_component(glyph, base_name, transformation=(1, 0, 0, 1, 0, 0)):
        component = glyph.instantiateComponent()
        component.baseGlyph = base_name
        component.transformation = transformation
        glyph.appendComponent(component)

    agrave = source.newGlyph("Agrave")
    agrave.width = source["A"].width
    append_component(agrave, "A")
    # The low accent deliberately intersects the A so the detached boolean
    # preprocessing path is exercised, not merely component decomposition.
    append_component(agrave, "dotaccentcomb", (1, 0, 0, 1, 140, 0))

    adieresis = source.newGlyph("Adieresis")
    adieresis.width = source["A"].width
    append_component(adieresis, "A")
    append_component(adieresis, "dotaccentcomb", (0.7, 0, 0, 0.7, 40, 320))
    append_component(adieresis, "dotaccentcomb", (0.7, 0, 0, 0.7, 250, 320))

    names = ("O", "A", "Agrave", "Adieresis")
    source_digests = {name: glyph_content_digest(source[name]) for name in names}
    source_component_counts = {name: len(source[name].components) for name in names}
    environment = FakeEnvironment(source)
    controller = FracturizeController(environment)
    project = controller.create_project(
        tmp_path / "Preprocessed.fracturize.json",
        project_name="Preprocessed",
        project_seed="automatic-preprocessing",
        complexity=20,
    )

    previews = {name: controller.preview(name, regenerate_topology=True) for name in names}
    result = controller.process_names(names, action="generate")

    assert result["completed"] == list(names)
    assert result["rejected"] == result["failed"] == []
    assert all(previews[name].normalization.normalization_applied is False for name in names)
    for name in names:
        assert glyph_content_digest(project.source_font[name]) == source_digests[name]
        assert len(project.source_font[name].components) == source_component_counts[name]
        assert not project.intact_font[name].components
        assert not project.eroded_font[name].components
        assert master_from_glyph(project.intact_font[name]) == previews[name].intact
        assert master_from_glyph(project.eroded_font[name]) == previews[name].eroded
    validate_working_font_pair(project.intact_font, project.eroded_font)

    project.intact_font.save()
    project.eroded_font.save()
    reopened_intact = Font(project.data["workingFonts"]["intact"]["path"])
    reopened_eroded = Font(project.data["workingFonts"]["eroded"]["path"])
    validate_working_font_pair(reopened_intact, reopened_eroded)
    for name in names:
        assert not reopened_intact[name].components
        assert not reopened_eroded[name].components
        assert master_from_glyph(reopened_intact[name]) == previews[name].intact
        assert master_from_glyph(reopened_eroded[name]) == previews[name].eroded
    for role_font in (reopened_intact, reopened_eroded):
        for name in ("O", "Agrave", "Adieresis"):
            assert _glyph_segment_counts(role_font[name])["cubic"] > 0


def test_generate_confirms_once_and_replaces_both_batch_outputs(live_controller):
    controller, project, environment = live_controller
    assert controller.process_names(["O", "I"], action="generate")["completed"] == [
        "O",
        "I",
    ]
    before = {
        (role, name): glyph_content_digest(getattr(project, f"{role}_font")[name])
        for role in ("intact", "eroded")
        for name in ("O", "I")
    }
    controller.update_settings(complexity=70)
    assert project.glyph_status("O") == project.glyph_status("I") == "topology-outdated"
    confirmations = []

    result = controller.process_names(
        ["O", "I"],
        action="generate",
        confirm_topology_replacement=lambda glyph_name: confirmations.append(glyph_name) or True,
    )

    assert result["completed"] == ["O", "I"]
    assert confirmations == ["O"]
    for role in ("intact", "eroded"):
        font = getattr(project, f"{role}_font")
        for name in ("O", "I"):
            assert glyph_content_digest(font[name]) != before[(role, name)]
            assert project.glyph_status(name) == "processed"
    reopened_project = LiveFractureProject.open(project.path)
    assert all(
        reopened_project.data["processedGlyphs"][name]["topologyComplexity"] == 70
        for name in ("O", "I")
    )
    validate_working_font_pair(project.intact_font, project.eroded_font)


def test_component_batch_preflight_finds_each_source_component_once(live_controller):
    controller, project, environment = live_controller

    assert controller.component_glyph_names(["O", "i", "i", "missingGlyph"]) == ("i",)


def test_ui_uses_one_batch_component_warning_and_no_per_glyph_confirmation():
    source = (BUNDLE / "lib" / "fracturize" / "ui.py").read_text()
    controller_source = (BUNDLE / "lib" / "fracturize" / "controller.py").read_text()

    assert '"Decompose components before processing"' in source
    assert "value=False" in source[source.index("self.w.decomposeComponents"):][:220]
    assert source.count("Component glyphs will be decomposed before fracture generation.") == 1
    assert "self.controller.component_glyph_names(names)" in source
    assert "decompose_components=self._batch_decompose_components" in source
    assert "_confirm_decomposition" not in source
    assert "confirm_decomposition" not in controller_source


def test_manual_edit_choices_never_silently_overwrite(live_controller):
    controller, project, environment = live_controller
    controller.process_names(["O"], action="generate")
    project.intact_font["O"][0].move((5, 0))
    edited_digest = glyph_content_digest(project.intact_font["O"])
    assert project.glyph_status("O") == "output-edited"
    kept = controller.process_names(
        ["O"], action="topology", resolve_edited=lambda name, roles: "keep"
    )
    assert kept["skipped"] == [("O", "kept edited glyph")]
    assert glyph_content_digest(project.intact_font["O"]) == edited_digest
    cancelled = controller.process_names(
        ["O"], action="topology", resolve_edited=lambda name, roles: "cancel"
    )
    assert cancelled["cancelled"] is True
    assert glyph_content_digest(project.intact_font["O"]) == edited_digest
    replaced = controller.process_names(
        ["O"], action="topology", resolve_edited=lambda name, roles: "replace"
    )
    assert replaced["completed"] == ["O"]
    assert project.glyph_status("O") == "processed"


def test_live_rollback_restores_both_user_glyphs_topology_and_project(live_controller):
    controller, project, environment = live_controller
    preview = controller.preview("O", regenerate_topology=True)
    intact_before = deepcopy(project.intact_font["O"])
    eroded_before = deepcopy(project.eroded_font["O"])
    project_before = project.path.read_bytes()

    def fail(stage):
        if stage == "after_topology_replace":
            raise OSError("fault after topology replacement")

    with pytest.raises(OSError, match="topology replacement"):
        project.process_result(preview, save_hook=fail)
    assert glyph_content_digest(project.intact_font["O"]) == glyph_content_digest(intact_before)
    assert glyph_content_digest(project.eroded_font["O"]) == glyph_content_digest(eroded_before)
    assert project.path.read_bytes() == project_before
    assert not project._topology_path("O").exists()


def test_live_wrapper_glyphs_are_replaced_in_place_and_documents_are_dirtied(live_controller):
    controller, project, environment = live_controller
    preview = controller.preview("O", regenerate_topology=True)
    intact = LiveFontProxy(project.intact_font)
    eroded = LiveFontProxy(project.eroded_font)
    project.intact_font = intact
    project.eroded_font = eroded
    intact_glyph = intact["O"]
    eroded_glyph = eroded["O"]
    metadata_before = {
        role: {
            key: deepcopy(glyph.naked().getDataForSerialization()[key])
            for key in ("width", "height", "unicodes", "anchors", "guidelines", "note", "image")
        }
        for role, glyph in (("intact", intact_glyph), ("eroded", eroded_glyph))
    }
    intact.naked().dirty = False
    eroded.naked().dirty = False

    project.process_result(preview)

    assert intact["O"] is intact_glyph
    assert eroded["O"] is eroded_glyph
    assert master_from_glyph(intact_glyph.naked()) == preview.intact
    assert master_from_glyph(eroded_glyph.naked()) == preview.eroded
    for role, glyph in (("intact", intact_glyph), ("eroded", eroded_glyph)):
        serialized = glyph.naked().getDataForSerialization()
        assert {
            key: serialized[key]
            for key in ("width", "height", "unicodes", "anchors", "guidelines", "note", "image")
        } == metadata_before[role]
        assert glyph.changed_calls > 0
    assert intact.changed_calls > 0
    assert eroded.changed_calls > 0
    assert intact.naked().dirty
    assert eroded.naked().dirty
    assert project.data["processedGlyphs"]["O"]["status"] == "processed"


def test_live_segment_pen_preserves_cubics_in_both_ufo_masters_after_reopen(tmp_path, caplog):
    segments = (
        CubicSegment((0, 100), (-35, 75), (-35, 25), (0, 0)),
        LineSegment((0, 0), (100, 0)),
        LineSegment((100, 0), (0, 100)),
    )

    def master(role, x_offset):
        shifted = tuple(
            CubicSegment(
                (segment.start[0] + x_offset, segment.start[1]),
                (segment.control1[0] + x_offset, segment.control1[1]),
                (segment.control2[0] + x_offset, segment.control2[1]),
                (segment.end[0] + x_offset, segment.end[1]),
            )
            if isinstance(segment, CubicSegment)
            else LineSegment(
                (segment.start[0] + x_offset, segment.start[1]),
                (segment.end[0] + x_offset, segment.end[1]),
            )
            for segment in segments
        )
        contour = MasterContour(
            identifier=f"fragment-{role}",
            fragment_id="fragment-0",
            part_index=0,
            is_hole=False,
            points=tuple(segment.end for segment in shifted),
            point_ids=tuple(f"fragment-{role}-p{index}" for index in range(3)),
            segments=shifted,
        )
        return MasterGlyph("testCurve", 500, (), (contour,))

    expected_methods = ["moveTo", "curveTo", "lineTo", "lineTo", "closePath"]
    reopened_counts = {}
    reopened_structures = {}
    with caplog.at_level("INFO", logger="fracturize.live_project"):
        for role, x_offset in (("intact", 0), ("eroded", 12)):
            font = Font()
            glyph = font.newGlyph("testCurve")
            live_glyph = RecordingLiveGlyphProxy(glyph)
            generated = master(role, x_offset)

            _draw_live_outline_only(live_glyph, generated, {})

            assert _glyph_segment_counts(live_glyph) == {"cubic": 1, "line": 2}
            assert [method for method, arguments in live_glyph.pen_calls] == expected_methods
            path = tmp_path / f"{role}.ufo"
            font.save(path)
            font.close()
            reopened = Font(path)
            reopened_counts[role] = _log_glyph_segment_counts(
                reopened["testCurve"],
                glyph_name="testCurve",
                stage=f"{role}_save_reopen",
            )
            reopened_structures[role] = tuple(
                segment[-1].segmentType
                for contour in reopened["testCurve"]
                for segment in contour.segments
            )
            reopened.close()

    assert reopened_counts == {
        "intact": {"cubic": 1, "line": 2},
        "eroded": {"cubic": 1, "line": 2},
    }
    assert reopened_structures == {
        "intact": ("curve", "line", "line"),
        "eroded": ("curve", "line", "line"),
    }
    assert "generated_cubic=1 generated_line=2" in caplog.text
    assert "'curveTo'" in caplog.text
    assert "live_cubic=1 live_line=2" in caplog.text
    assert "stage=intact_save_reopen cubic=1 line=2" in caplog.text
    assert "stage=eroded_save_reopen cubic=1 line=2" in caplog.text


def test_live_wrapper_failure_restores_both_sides_in_place_before_project_commit(live_controller):
    controller, project, environment = live_controller
    preview = controller.preview("O", regenerate_topology=True)
    intact = LiveFontProxy(project.intact_font)
    eroded = LiveFontProxy(project.eroded_font)
    project.intact_font = intact
    project.eroded_font = eroded
    intact_glyph = intact["O"]
    eroded_glyph = eroded["O"]
    intact_before = deepcopy(intact_glyph.naked().getDataForSerialization())
    eroded_before = deepcopy(eroded_glyph.naked().getDataForSerialization())
    project_before = project.path.read_bytes()

    def fail_after_first_side(stage):
        if stage == "after_intact_write":
            assert "O" not in project.data["processedGlyphs"]
            raise OSError("fault after live intact write")

    with pytest.raises(OSError, match="live intact write"):
        project.process_result(preview, save_hook=fail_after_first_side)

    assert intact["O"] is intact_glyph
    assert eroded["O"] is eroded_glyph
    assert intact_glyph.naked().getDataForSerialization() == intact_before
    assert eroded_glyph.naked().getDataForSerialization() == eroded_before
    assert project.path.read_bytes() == project_before
    assert "O" not in project.data["processedGlyphs"]
    assert not project._topology_path("O").exists()


def test_hard_validation_failure_blocks_both_live_writes(live_controller):
    controller, project, environment = live_controller
    result = controller.preview("O", regenerate_topology=True)
    blocked = replace(result, validation=replace(result.validation, compatible=False))
    intact_before = glyph_content_digest(project.intact_font["O"])
    eroded_before = glyph_content_digest(project.eroded_font["O"])
    with pytest.raises(LiveProjectError, match="blocking validation"):
        project.process_result(blocked)
    assert glyph_content_digest(project.intact_font["O"]) == intact_before
    assert glyph_content_digest(project.eroded_font["O"]) == eroded_before


def test_sequential_batch_preserves_success_and_reports_later_failure(live_controller):
    controller, project, environment = live_controller
    result = controller.process_names(["O", "missingGlyph", "I"], action="generate")
    assert result["completed"] == ["O", "I"]
    assert result["failed"][0][0] == "missingGlyph"
    assert project.glyph_status("missingGlyph") == "failed"
    assert project.glyph_status("O") == "processed"


def test_later_glyph_additions_reuse_the_same_open_pair(live_controller):
    controller, project, environment = live_controller
    intact = project.intact_font
    eroded = project.eroded_font
    controller.process_names(["O"], action="generate")
    controller.process_names(["I"], action="generate")
    assert project.intact_font is intact
    assert project.eroded_font is eroded
    assert set(project.data["processedGlyphs"]) == {"O", "I"}
    assert project.glyph_status("O") == project.glyph_status("I") == "processed"


def test_source_change_is_reported_as_stale_without_overwriting(live_controller):
    controller, project, environment = live_controller
    controller.process_names(["O"], action="generate")
    output_before = glyph_content_digest(project.intact_font["O"])
    project.source_font["O"][0].move((1, 0))
    assert project.glyph_status("O") == "stale"
    result = controller.process_names(["O"], action="motion")
    assert result["failed"] and "source glyph changed" in result["failed"][0][1]
    assert glyph_content_digest(project.intact_font["O"]) == output_before


def test_batch_cancellation_is_checked_between_glyphs(live_controller):
    controller, project, environment = live_controller

    def progress(index, total, name):
        if index == 0:
            controller.request_cancel()

    result = controller.process_names(["O", "I"], action="generate", progress=progress)
    assert result["completed"] == ["O"]
    assert result["cancelled"] is True
    assert project.glyph_status("I") == "unprocessed"


def test_project_reopen_relinks_same_open_user_fonts(live_controller):
    controller, project, environment = live_controller
    controller.process_names(["O"], action="generate")
    path = project.path
    reopened_controller = FracturizeController(environment)
    reopened = reopened_controller.open_project(path)
    assert reopened.source_font is project.source_font
    assert reopened.intact_font is project.intact_font
    assert reopened.eroded_font is project.eroded_font
    assert reopened.glyph_status("O") == "processed"


def test_open_project_dialog_result_normalizes_selected_path(live_controller):
    controller, project, environment = live_controller
    assert controller.open_project_path_from_dialog_result([str(project.path)]) == project.path
    assert controller.open_project_path_from_dialog_result(()) is None


def test_open_project_restores_settings_and_uses_already_open_fonts(live_controller):
    controller, project, environment = live_controller
    controller.update_settings(complexity=73, rock_edge_detail=82)
    environment.opened_paths.clear()
    reopened_controller = FracturizeController(environment)

    reopened = reopened_controller.open_project(project.path)

    assert reopened.settings.complexity == 73
    assert reopened.settings.rock_edge_detail == 82
    assert reopened.fonts_available
    assert environment.opened_paths == []


def test_open_project_opens_and_binds_missing_working_fonts(live_controller):
    controller, project, environment = live_controller
    source_only = FakeEnvironment(project.source_font)
    reopened_controller = FracturizeController(source_only)

    reopened = reopened_controller.open_project(project.path)

    expected = {
        Path(project.data["workingFonts"][role]["path"]).resolve()
        for role in ("intact", "eroded")
    }
    assert reopened.fonts_available
    assert set(source_only.opened_paths) == expected


def test_open_project_invalid_path_raises_and_ui_has_clear_failure_path(live_controller, tmp_path):
    controller, project, environment = live_controller
    missing = tmp_path / "missing.fracturize.json"
    with pytest.raises(Exception):
        controller.open_project(missing)
    source = (BUNDLE / "lib" / "fracturize" / "ui.py").read_text()
    assert "def _report_open_failure" in source
    assert 'title="Project open failed"' in source
    assert "def _report_project_failure" in source
    assert "print(trace, flush=True)" in source


def test_complete_resolved_batch_reaches_process_names_and_continues_after_failure(live_controller):
    controller, project, environment = live_controller
    environment.current_name = "O"
    environment.selection = ("missingGlyph", "I")
    names = controller.selected_names("I")
    progress_names = []

    result = controller.process_names(
        names,
        action="generate",
        progress=lambda index, total, name: progress_names.append(name),
    )

    assert names == ("O", "missingGlyph", "I")
    assert progress_names == list(names)
    assert result["completed"] == ["O", "I"]
    assert result["failed"][0][0] == "missingGlyph"
    assert project.glyph_status("I") == "processed"


def test_project_schema_contains_required_live_reproducibility_fields(live_controller):
    controller, project, environment = live_controller
    controller.process_names(["O"], action="generate")
    data = json.loads(project.path.read_text())
    assert data["format"] == "com.fracturize.live-project"
    assert data["formatVersion"] == 1
    assert data["motionPolicy"]["algorithmVersion"] == "in-place-dispersal-v3"
    assert data["topologyPolicy"]["topologyVersion"] == "branching-rough-crack-mesh-v2"
    assert data["topologyPolicy"]["edgeProfileVersion"] == "independent-rock-edge-detail-v1"
    record = data["processedGlyphs"]["O"]
    assert record["sourceFingerprint"]
    assert record["outputFingerprints"]["intact"]
    assert record["outputFingerprints"]["eroded"]
    assert record["topologyPath"]
    assert record["topologyRockEdgeDetail"] == 50


def test_create_refuses_an_existing_project_file(tmp_path):
    source = enriched_source()
    controller = FracturizeController(FakeEnvironment(source))
    path = tmp_path / "existing.fracturize.json"
    path.write_text("do not replace")
    with pytest.raises(LiveProjectError, match="refuses existing destination"):
        controller.create_project(
            path,
            project_name="Existing",
            project_seed="existing",
        )
    assert path.read_text() == "do not replace"


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda data: data.update(settings=[]), "settings must be an object"),
        (lambda data: data["source"].update(unitsPerEm=float("inf")), "finite positive"),
        (lambda data: data.update(topologyPolicy=[]), "topologyPolicy must be an object"),
        (lambda data: data.update(processedGlyphs=[]), "processedGlyphs must be an object"),
    ],
)
def test_live_project_open_rejects_invalid_version_one_data(live_controller, mutation, message):
    controller, project, environment = live_controller
    data = json.loads(project.path.read_text())
    mutation(data)
    project.path.write_text(json.dumps(data))
    with pytest.raises(Exception, match=message):
        LiveFractureProject.open(project.path)


def test_pair_integrity_detects_non_outline_data_changes(live_controller):
    controller, project, environment = live_controller
    project.eroded_font.kerning[("A", "O")] = -99
    with pytest.raises(Exception, match="kerning"):
        validate_working_font_pair(project.intact_font, project.eroded_font)


def test_pair_integrity_allows_only_the_exact_volatile_robofont_font_lib_key(live_controller):
    controller, project, environment = live_controller
    key, = VOLATILE_ROBOFONT_FONT_LIB_KEYS
    project.intact_font.lib[key] = "intact-document-id"
    project.eroded_font.lib[key] = "eroded-document-id"
    validate_working_font_pair(project.intact_font, project.eroded_font)


def test_pair_integrity_rejects_user_font_lib_difference_with_values(live_controller):
    controller, project, environment = live_controller
    project.intact_font.lib["com.example.userData"] = {"side": "intact"}
    with pytest.raises(Exception) as caught:
        validate_working_font_pair(project.intact_font, project.eroded_font)
    message = str(caught.value)
    assert "com.example.userData" in message
    assert "intact={'side': 'intact'}" in message
    assert "eroded=None" in message


def test_pair_integrity_rejects_unexpected_fracturize_font_lib_difference(live_controller):
    controller, project, environment = live_controller
    project.eroded_font.lib["com.fracturize.unexpectedData"] = "must not be ignored"
    with pytest.raises(Exception, match="com.fracturize.unexpectedData"):
        validate_working_font_pair(project.intact_font, project.eroded_font)


def test_pair_integrity_accepts_identical_font_lib_data(live_controller):
    controller, project, environment = live_controller
    value = {"nested": [1, 2, 3]}
    project.intact_font.lib["com.example.identical"] = deepcopy(value)
    project.eroded_font.lib["com.example.identical"] = deepcopy(value)
    validate_working_font_pair(project.intact_font, project.eroded_font)


def test_pair_integrity_accepts_identical_semantic_guidelines(live_controller):
    controller, project, environment = live_controller
    intact, eroded = guideline_pair(
        project,
        [SemanticGuideline(x=10, y=20, angle=30, name="cap", color="1,0,0,1", locked=True, lib={"com.example.note": "user"})],
        [SemanticGuideline(x=10, y=20, angle=30, name="cap", color="1,0,0,1", locked=True, lib={"com.example.note": "user"})],
    )
    validate_working_font_pair(intact, eroded)


def test_pair_integrity_ignores_only_guideline_identifier_and_order(live_controller):
    controller, project, environment = live_controller
    first = SemanticGuideline(x=10, y=20, angle=30, name="first", identifier="robofont-intact-a")
    second = SemanticGuideline(x=40, y=50, angle=60, name="second", identifier="robofont-intact-b")
    intact, eroded = guideline_pair(
        project,
        [first, second],
        [
            SemanticGuideline(x=40, y=50, angle=60, name="second", identifier="robofont-eroded-b"),
            SemanticGuideline(x=10, y=20, angle=30, name="first", identifier="robofont-eroded-a"),
        ],
    )
    assert guideline_records(intact)[0]["identifier"] == "robofont-intact-a"
    assert guideline_records(eroded)[1]["identifier"] == "robofont-eroded-a"
    validate_working_font_pair(intact, eroded)


@pytest.mark.parametrize(
    ("field", "changed"),
    [
        ("x", 11),
        ("y", 21),
        ("angle", 31),
        ("name", "changed"),
        ("color", "0,1,0,1"),
    ],
)
def test_pair_integrity_rejects_changed_guideline_geometry_or_label(live_controller, field, changed):
    controller, project, environment = live_controller
    values = {"x": 10, "y": 20, "angle": 30, "name": "cap", "color": "1,0,0,1"}
    changed_values = dict(values)
    changed_values[field] = changed
    intact, eroded = guideline_pair(
        project,
        [SemanticGuideline(**values, identifier="volatile-a")],
        [SemanticGuideline(**changed_values, identifier="volatile-b")],
    )
    with pytest.raises(Exception) as caught:
        validate_working_font_pair(intact, eroded)
    text = str(caught.value)
    assert "guidelines" in text
    assert field in text
    assert "index" in text


def test_pair_integrity_rejects_changed_guideline_user_lib(live_controller):
    controller, project, environment = live_controller
    intact, eroded = guideline_pair(
        project,
        [SemanticGuideline(lib={"com.example.userData": {"side": "intact"}})],
        [SemanticGuideline(lib={"com.example.userData": {"side": "eroded"}})],
    )
    with pytest.raises(Exception, match="com.example.userData"):
        validate_working_font_pair(intact, eroded)


def test_repeated_ui_refresh_deduplicates_unchanged_integrity_error(live_controller):
    controller, project, environment = live_controller
    intact, eroded = guideline_pair(
        project,
        [SemanticGuideline(x=10, identifier="volatile-a")],
        [SemanticGuideline(x=11, identifier="volatile-b")],
    )
    environment.fonts = [project.source_font, intact, eroded]

    first = controller.refresh_project_fonts()
    second = controller.refresh_project_fonts()

    assert first["error"] == second["error"]
    assert first["report"] is True
    assert second["report"] is False
    ui_source = (BUNDLE / "lib" / "fracturize" / "ui.py").read_text()
    assert "binding = self.controller.refresh_project_fonts()" in ui_source
