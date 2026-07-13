from __future__ import annotations

from pathlib import Path

import pytest

from fracturize import GenerationSettings, generate_pair
from fracturize.geometry import UnsupportedOutlineError
from fracturize.input_ufo import defcon_glyph_to_outline, load_ufo_outlines


FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "Excalibur_Headline_1.0_BK_subset.ufo"


def test_real_ufo_adapter_loads_contours_and_rejects_components():
    outlines, rejected, metadata = load_ufo_outlines(FIXTURE)
    assert metadata["familyName"] == "Excalibur"
    assert metadata["unitsPerEm"] == 1000
    assert len(outlines) == 11
    assert rejected == ({"glyph": "i", "reason": "components are unsupported in Stage 1: idotless, dotaccentcomb"},)


@pytest.mark.parametrize("glyph_name", ("H", "O", "S", "a"))
def test_representative_real_glyphs_pass_stage1_validation(glyph_name):
    outlines, _, _ = load_ufo_outlines(FIXTURE)
    outline = next(item for item in outlines if item.name == glyph_name)
    result = generate_pair(outline, GenerationSettings(project_seed="real-test", complexity=50))
    assert result.validation.compatible
    assert result.validation.reconstruction.normalized_symmetric_difference <= 1e-8


@pytest.mark.parametrize("glyph_name", ("A", "M", "R", "eight"))
def test_stable_multiply_wound_real_glyphs_use_bounded_overlap_normalization(glyph_name):
    outlines, _, _ = load_ufo_outlines(FIXTURE)
    outline = next(item for item in outlines if item.name == glyph_name)
    result = generate_pair(outline, GenerationSettings(project_seed="real-test", complexity=50))
    assert result.validation.compatible
    assert result.normalization.normalization_applied
    assert result.normalization.maximum_absolute_winding >= 2
    assert result.normalization.cross_tolerance_normalized_difference <= 0.002


def test_component_glyph_is_rejected_before_generation():
    from defcon import Font

    font = Font(FIXTURE)
    with pytest.raises(UnsupportedOutlineError, match="components are unsupported"):
        defcon_glyph_to_outline(font["i"], units_per_em=1000)
    font.close()
