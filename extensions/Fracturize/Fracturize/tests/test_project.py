from __future__ import annotations

import json
import math
import os
import shutil
from pathlib import Path

import pytest
from defcon import Font

from fracturize.core import (
    BRANCHING_TOPOLOGY_V1,
    RECURSIVE_TOPOLOGY_VERSION,
    generate_branching_topology_v1,
    generate_pair,
    generate_recursive_topology,
)
from fracturize.geometry import UnsupportedOutlineError
from fracturize.project import (
    OUTPUT_ROLE_KEY,
    PROJECT_ID_KEY,
    FractureProject,
    OutputGlyphEditedError,
    ProcessedGlyphError,
    ProjectConflictError,
    ProjectError,
    ProjectIntegrityError,
    StaleGlyphError,
    glyph_content_digest,
)
from fracturize.ufo import read_master


SOURCE_FIXTURE = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "Excalibur_Headline_1.0_BK_subset.ufo"
)


def copy_source(tmp_path: Path) -> Path:
    destination = tmp_path / "Source.ufo"
    shutil.copytree(SOURCE_FIXTURE, destination)
    return destination


def create_project(tmp_path: Path) -> FractureProject:
    return FractureProject.create(
        tmp_path / "project",
        copy_source(tmp_path),
        project_name="ExcaliburFracture",
        project_seed="stage2-test-seed",
        complexity=50,
    )


def test_project_creation_writes_one_empty_identified_ufo_pair_and_json(tmp_path):
    project = create_project(tmp_path)
    assert project.path.is_file()
    assert project.intact_path.is_dir()
    assert project.eroded_path.is_dir()
    data = json.loads(project.path.read_text())
    assert data["format"] == "com.fracturize.project"
    assert data["formatVersion"] == 1
    assert not data["processedGlyphs"]
    assert not Path(data["source"]["path"]).is_absolute()
    assert data["savePolicy"]["outputsMayRemainOpenInRoboFont"] is True
    assert data["savePolicy"]["finalRoboFontOwnership"] == "user-owned RoboFont documents"
    assert data["motionPolicy"]["algorithmVersion"] == "architectural-erosion-v2"
    for path, role in ((project.intact_path, "intact"), (project.eroded_path, "eroded")):
        font = Font(path)
        assert font.lib[PROJECT_ID_KEY] == data["projectID"]
        assert font.lib[OUTPUT_ROLE_KEY] == role
        assert len(font) == 0
        assert font.info.unitsPerEm == 1000
        assert font.info.familyName == "Excalibur"
        assert not font.features.text
        assert not font.groups
        assert not font.kerning
        font.close()


def test_project_creation_refuses_conflicting_paths(tmp_path):
    project = create_project(tmp_path)
    with pytest.raises(ProjectConflictError, match="refused existing paths"):
        FractureProject.create(
            project.directory,
            project.source_path,
            project_name="ExcaliburFracture",
            project_seed="another",
        )


def test_reopen_appends_to_same_pair_and_preserves_previous_glyph(tmp_path):
    project = create_project(tmp_path)
    intact_path = project.intact_path
    eroded_path = project.eroded_path
    project.process_glyph("O")
    original_intact = read_master(intact_path, "O")
    original_eroded = read_master(eroded_path, "O")
    project.close()

    reopened = FractureProject.open(project.path)
    assert reopened.intact_path == intact_path
    assert reopened.eroded_path == eroded_path
    reopened.process_glyph("H")
    assert read_master(intact_path, "O") == original_intact
    assert read_master(eroded_path, "O") == original_eroded
    for path in (intact_path, eroded_path):
        font = Font(path)
        assert set(font.keys()) == {"O", "H"}
        font.close()
    assert set(reopened.data["processedGlyphs"]) == {"O", "H"}
    FractureProject.open(project.path)


def test_legacy_project_keeps_its_recorded_recursive_topology_language(tmp_path):
    project = create_project(tmp_path)
    project.data["topologyPolicy"]["topologyVersion"] = RECURSIVE_TOPOLOGY_VERSION
    project._save()
    outline = project._load_source_outline("O")
    expected = generate_pair(
        outline,
        project.settings,
        topology_generator=generate_recursive_topology,
        topology_version=RECURSIVE_TOPOLOGY_VERSION,
    )
    actual = FractureProject.open(project.path).process_glyph("O")
    assert actual.fragments == expected.fragments


def test_existing_branching_v1_project_keeps_clean_macro_edges(tmp_path):
    project = create_project(tmp_path)
    project.data["topologyPolicy"]["topologyVersion"] = BRANCHING_TOPOLOGY_V1
    project._save()
    outline = project._load_source_outline("O")
    expected = generate_pair(
        outline,
        project.settings,
        topology_generator=generate_branching_topology_v1,
        topology_version=BRANCHING_TOPOLOGY_V1,
    )
    actual = FractureProject.open(project.path).process_glyph("O")
    assert actual.fragments == expected.fragments


def test_processed_glyph_is_never_silently_replaced(tmp_path):
    project = create_project(tmp_path)
    project.process_glyph("O")
    with pytest.raises(ProcessedGlyphError, match="replacement must be explicit"):
        project.process_glyph("O")
    with pytest.raises(ProcessedGlyphError, match="requires explicit topology regeneration"):
        project.process_glyph("O", replace_existing=True)


def test_motion_only_regeneration_reuses_persisted_topology(tmp_path):
    project = create_project(tmp_path)
    first = project.process_glyph("O")
    first_record = dict(project.data["processedGlyphs"]["O"])
    first_intact = read_master(project.intact_path, "O")
    first_eroded = read_master(project.eroded_path, "O")

    project.set_motion_settings(erosion_amount=0.82, movement_direction_degrees=-25.0)
    second = project.regenerate_motion("O")
    second_record = project.data["processedGlyphs"]["O"]
    assert second.effective_seed == first.effective_seed
    assert second_record["topologyDigest"] == first_record["topologyDigest"]
    assert second_record["topologyPath"] == first_record["topologyPath"]
    assert second_record["pairRevision"] != first_record["pairRevision"]
    assert second_record["motionAlgorithmVersion"] == "architectural-erosion-v2"
    assert read_master(project.intact_path, "O") == first_intact
    assert read_master(project.eroded_path, "O") != first_eroded
    FractureProject.open(project.path)


def test_complexity_change_requires_and_records_explicit_topology_regeneration(tmp_path):
    project = create_project(tmp_path)
    first = project.process_glyph("O")
    first_digest = project.data["processedGlyphs"]["O"]["topologyDigest"]
    project.set_complexity(75)
    assert project.glyph_status("O") == "topology-outdated"
    motion_only = project.regenerate_motion("O")
    assert motion_only.profile.value == 50
    assert project.glyph_status("O") == "topology-outdated"

    regenerated = project.regenerate_topology("O")
    assert regenerated.profile.value == 75
    assert project.data["processedGlyphs"]["O"]["topologyDigest"] != first_digest
    assert project.glyph_status("O") == "processed"


def test_rock_edge_detail_persists_marks_stale_and_motion_keeps_topology(tmp_path):
    project = create_project(tmp_path)
    first = project.process_glyph("O")
    first_record = dict(project.data["processedGlyphs"]["O"])

    project.set_rock_edge_detail(75)

    assert FractureProject.open(project.path).settings.rock_edge_detail == 75
    assert project.glyph_status("O") == "topology-outdated"
    motion_only = project.regenerate_motion("O")
    assert motion_only.rock_edge_detail == first.rock_edge_detail == 50
    assert project.data["processedGlyphs"]["O"]["topologyDigest"] == first_record["topologyDigest"]
    assert project.glyph_status("O") == "topology-outdated"

    regenerated = project.regenerate_topology("O")
    assert regenerated.rock_edge_detail == 75
    assert project.data["processedGlyphs"]["O"]["topologyRockEdgeDetail"] == 75
    assert project.data["processedGlyphs"]["O"]["topologyDigest"] != first_record["topologyDigest"]
    assert project.glyph_status("O") == "processed"


def test_source_change_marks_stale_and_preserves_outputs_until_explicit_replacement(tmp_path):
    project = create_project(tmp_path)
    project.process_glyph("O")
    old_intact = read_master(project.intact_path, "O")
    old_eroded = read_master(project.eroded_path, "O")
    old_fingerprint = project.data["processedGlyphs"]["O"]["sourceFingerprint"]

    source = Font(project.source_path)
    source["O"].width += 17
    source.save()
    source.close()

    assert project.glyph_status("O") == "stale"
    with pytest.raises(StaleGlyphError):
        project.regenerate_motion("O")
    assert read_master(project.intact_path, "O") == old_intact
    assert read_master(project.eroded_path, "O") == old_eroded
    assert project.data["processedGlyphs"]["O"]["sourceFingerprint"] == old_fingerprint

    regenerated = project.regenerate_topology("O")
    assert regenerated.intact.width == old_intact.width + 17
    assert project.glyph_status("O") == "processed"
    assert project.data["processedGlyphs"]["O"]["sourceFingerprint"] != old_fingerprint


def test_failed_stale_regeneration_preserves_previous_pair(tmp_path):
    project = create_project(tmp_path)
    project.process_glyph("O")
    intact_before = read_master(project.intact_path, "O")
    eroded_before = read_master(project.eroded_path, "O")
    record_before = dict(project.data["processedGlyphs"]["O"])

    source = Font(project.source_path)
    component = source["O"].instantiateComponent()
    component.baseGlyph = "H"
    source["O"].appendComponent(component)
    source.save()
    source.close()

    assert project.glyph_status("O") == "source-unavailable"
    with pytest.raises(UnsupportedOutlineError, match="components are unsupported"):
        project.regenerate_topology("O")
    assert read_master(project.intact_path, "O") == intact_before
    assert read_master(project.eroded_path, "O") == eroded_before
    assert project.data["processedGlyphs"]["O"]["sourceFingerprint"] == record_before["sourceFingerprint"]
    assert project.data["processedGlyphs"]["O"]["pairRevision"] == record_before["pairRevision"]


def test_component_policy_is_explicit_and_does_not_advance_project(tmp_path):
    project = create_project(tmp_path)
    with pytest.raises(UnsupportedOutlineError, match="components are unsupported"):
        project.process_glyph("i")
    assert "i" not in project.data["processedGlyphs"]
    for path in (project.intact_path, project.eroded_path):
        font = Font(path)
        assert "i" not in font
        font.close()


def test_failure_after_first_save_rolls_back_both_sides_and_project_record(tmp_path):
    project = create_project(tmp_path)

    def fail_before_eroded(stage):
        if stage == "before_eroded_save":
            raise OSError("simulated eroded save failure")

    with pytest.raises(OSError, match="simulated eroded save failure"):
        project.process_glyph("H", save_hook=fail_before_eroded)
    assert "H" not in project.data["processedGlyphs"]
    assert not project._topology_path("H").exists()
    for path in (project.intact_path, project.eroded_path):
        font = Font(path)
        assert "H" not in font
        font.close()
    FractureProject.open(project.path)


def test_failed_motion_replacement_restores_previous_pair_and_revision(tmp_path):
    project = create_project(tmp_path)
    project.process_glyph("O")
    intact_before = read_master(project.intact_path, "O")
    eroded_before = read_master(project.eroded_path, "O")
    record_before = dict(project.data["processedGlyphs"]["O"])
    project.set_motion_settings(erosion_amount=0.9)

    def fail_after_intact(stage):
        if stage == "after_intact_save":
            raise OSError("simulated failure after intact save")

    with pytest.raises(OSError, match="simulated failure after intact save"):
        project.regenerate_motion("O", save_hook=fail_after_intact)
    assert read_master(project.intact_path, "O") == intact_before
    assert read_master(project.eroded_path, "O") == eroded_before
    assert project.data["processedGlyphs"]["O"] == record_before
    FractureProject.open(project.path)


def test_open_detects_missing_or_mismatched_output_pair(tmp_path):
    project = create_project(tmp_path)
    missing = project.eroded_path.with_name("temporarily-missing.ufo")
    project.eroded_path.rename(missing)
    with pytest.raises(ProjectIntegrityError, match="output UFO missing"):
        FractureProject.open(project.path)
    missing.rename(project.eroded_path)

    eroded = Font(project.eroded_path)
    eroded.lib[PROJECT_ID_KEY] = "wrong-project"
    eroded.save()
    eroded.close()
    with pytest.raises(ProjectIntegrityError, match="project identity mismatch"):
        FractureProject.open(project.path)


def test_open_detects_unrecorded_partial_or_orphan_glyph(tmp_path):
    project = create_project(tmp_path)
    project.process_glyph("O")
    intact = Font(project.intact_path)
    intact.newGlyph("orphan")
    intact.save()
    intact.close()
    with pytest.raises(ProjectIntegrityError, match="glyph sets differ"):
        FractureProject.open(project.path)


@pytest.mark.parametrize(
    "failure_stage",
    (
        "after_serialized_validation",
        "after_topology_replace",
        "before_project_save",
        "after_project_save",
    ),
)
def test_full_commit_rollback_covers_validation_topology_and_project_record(
    tmp_path, failure_stage
):
    project = create_project(tmp_path)
    project.process_glyph("O")
    project.set_complexity(75)
    intact_before = read_master(project.intact_path, "O")
    eroded_before = read_master(project.eroded_path, "O")
    record_before = dict(project.data["processedGlyphs"]["O"])
    topology_path = project._topology_path("O")
    topology_before = topology_path.read_bytes()
    project_before = project.path.read_bytes()

    def fail(stage):
        if stage == failure_stage:
            raise OSError(f"simulated {failure_stage} failure")

    with pytest.raises(OSError, match=failure_stage):
        project.regenerate_topology("O", save_hook=fail)
    assert read_master(project.intact_path, "O") == intact_before
    assert read_master(project.eroded_path, "O") == eroded_before
    assert project.data["processedGlyphs"]["O"] == record_before
    assert topology_path.read_bytes() == topology_before
    assert project.path.read_bytes() == project_before
    FractureProject.open(project.path)


def test_post_save_reopen_exception_rolls_back_every_persistent_side(tmp_path, monkeypatch):
    project = create_project(tmp_path)
    original = project.path.read_bytes()

    def fail_read(*args, **kwargs):
        raise OSError("simulated serialized reopen failure")

    monkeypatch.setattr("fracturize.project.read_master", fail_read)
    with pytest.raises(OSError, match="serialized reopen failure"):
        project.process_glyph("H")
    assert project.path.read_bytes() == original
    assert not project._topology_path("H").exists()
    for path in (project.intact_path, project.eroded_path):
        font = Font(path)
        assert "H" not in font
        font.close()
    FractureProject.open(project.path)


def test_serialized_validation_failure_rolls_back_every_persistent_side(tmp_path, monkeypatch):
    project = create_project(tmp_path)
    original = project.path.read_bytes()
    from dataclasses import replace
    from fracturize import project as project_module

    original_validator = project_module.validate_pair

    def incompatible(**kwargs):
        return replace(original_validator(**kwargs), compatible=False)

    monkeypatch.setattr(project_module, "validate_pair", incompatible)
    with pytest.raises(ProjectError, match="serialized output validation failed"):
        project.process_glyph("H")
    assert project.path.read_bytes() == original
    assert not project._topology_path("H").exists()
    for path in (project.intact_path, project.eroded_path):
        font = Font(path)
        assert "H" not in font
        font.close()


def test_topology_replace_exception_restores_pair_topology_and_project(tmp_path, monkeypatch):
    project = create_project(tmp_path)
    project.process_glyph("O")
    project.set_complexity(75)
    intact_before = read_master(project.intact_path, "O")
    eroded_before = read_master(project.eroded_path, "O")
    topology_path = project._topology_path("O")
    topology_before = topology_path.read_bytes()
    project_before = project.path.read_bytes()
    original_replace = os.replace

    def fail_candidate_replace(source, destination):
        if str(source).endswith(".candidate.json") and Path(destination) == topology_path:
            raise OSError("simulated topology replacement failure")
        return original_replace(source, destination)

    monkeypatch.setattr("fracturize.project.os.replace", fail_candidate_replace)
    with pytest.raises(OSError, match="topology replacement failure"):
        project.regenerate_topology("O")
    assert read_master(project.intact_path, "O") == intact_before
    assert read_master(project.eroded_path, "O") == eroded_before
    assert topology_path.read_bytes() == topology_before
    assert project.path.read_bytes() == project_before
    FractureProject.open(project.path)


def test_project_record_save_exception_restores_every_commit_side(tmp_path, monkeypatch):
    project = create_project(tmp_path)
    project.process_glyph("O")
    project.set_complexity(75)
    intact_before = read_master(project.intact_path, "O")
    eroded_before = read_master(project.eroded_path, "O")
    topology_path = project._topology_path("O")
    topology_before = topology_path.read_bytes()
    project_before = project.path.read_bytes()

    def fail_save():
        raise OSError("simulated project record save failure")

    monkeypatch.setattr(project, "_save", fail_save)
    with pytest.raises(OSError, match="project record save failure"):
        project.regenerate_topology("O")
    assert read_master(project.intact_path, "O") == intact_before
    assert read_master(project.eroded_path, "O") == eroded_before
    assert topology_path.read_bytes() == topology_before
    assert project.path.read_bytes() == project_before
    FractureProject.open(project.path)


@pytest.mark.parametrize(
    "mutation, message",
    (
        (lambda data: data.pop("settings"), "settings must be an object"),
        (lambda data: data.__setitem__("settings", []), "settings must be an object"),
        (
            lambda data: data["settings"].__setitem__("minimum_scale", -0.2),
            "invalid settings",
        ),
        (
            lambda data: data["motionPolicy"].__setitem__("algorithmVersion", "unknown"),
            "unsupported motion algorithm",
        ),
        (
            lambda data: data["topologyPolicy"].__setitem__("fillRule", "even-odd"),
            "unsupported topology policy",
        ),
    ),
)
def test_open_validates_version_one_schema_policy_types_and_values(
    tmp_path, mutation, message
):
    project = create_project(tmp_path)
    data = json.loads(project.path.read_text())
    mutation(data)
    project.path.write_text(json.dumps(data))
    with pytest.raises(ProjectIntegrityError, match=message):
        FractureProject.open(project.path)


@pytest.mark.parametrize(
    "changes",
    (
        {"minimum_scale": 0.0},
        {"erosion_amount": math.inf},
        {"maximum_downward_drift_em": -0.01},
        {"maximum_baseline_crossing_fraction": 0.9},
        {
            "large_fragment_movement_multiplier": 1.0,
            "medium_fragment_movement_multiplier": 0.5,
        },
    ),
)
def test_motion_setting_api_rejects_nonfinite_or_unsafe_values(tmp_path, changes):
    project = create_project(tmp_path)
    before = project.path.read_bytes()
    with pytest.raises(ProjectError, match="invalid motion settings"):
        project.set_motion_settings(**changes)
    assert project.path.read_bytes() == before


def test_external_output_edit_is_detected_but_project_can_open_and_requires_choice(tmp_path):
    project = create_project(tmp_path)
    project.process_glyph("O")
    intact = Font(project.intact_path)
    intact["O"][0].move((9, 0))
    intact.save()
    intact.close()

    reopened = FractureProject.open(project.path)
    assert reopened.edited_outputs == {"O": ("intact",)}
    assert reopened.glyph_status("O") == "output-edited"
    with pytest.raises(OutputGlyphEditedError, match="explicit edited-output regeneration"):
        reopened.regenerate_motion("O")
    with pytest.raises(OutputGlyphEditedError, match="explicit edited-output regeneration"):
        reopened.regenerate_topology("O")
    regenerated = reopened.regenerate_topology("O", replace_edited=True)
    assert regenerated.validation.compatible
    assert reopened.glyph_status("O") == "processed"
    assert not reopened.edited_outputs
    FractureProject.open(project.path)


def test_failed_explicit_edited_output_replacement_restores_the_user_edit(tmp_path):
    project = create_project(tmp_path)
    project.process_glyph("O")
    intact = Font(project.intact_path)
    intact["O"][0].move((9, 0))
    intact.save()
    edited_digest = glyph_content_digest(intact["O"])
    intact.close()
    project_before = project.path.read_bytes()

    def fail_before_record(stage):
        if stage == "before_project_save":
            raise OSError("simulated edited replacement failure")

    with pytest.raises(OSError, match="edited replacement failure"):
        project.regenerate_topology(
            "O",
            replace_edited=True,
            save_hook=fail_before_record,
        )
    intact = Font(project.intact_path)
    assert glyph_content_digest(intact["O"]) == edited_digest
    intact.close()
    assert project.path.read_bytes() == project_before
    reopened = FractureProject.open(project.path)
    assert reopened.edited_outputs == {"O": ("intact",)}
