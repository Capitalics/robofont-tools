from __future__ import annotations

from pathlib import Path

import pytest

from fracturize import GenerationSettings, generate_pair
from fracturize.geometry import UnsupportedOutlineError
from fracturize.input_ufo import defcon_glyph_to_outline, load_ufo_outlines


FIXTURE = Path(__file__).resolve().parent / "fixtures" / "FracturizeRegression.ufo"


def test_regression_ufo_adapter_loads_contours_and_rejects_components():
    outlines, rejected, metadata = load_ufo_outlines(FIXTURE)
    assert metadata["familyName"] == "Fracturize Regression"
    assert metadata["unitsPerEm"] == 1000
    assert len(outlines) == 11
    assert rejected == ({
        "glyph": "i",
        "reason": (
            "components require decomposition before polygonal generation: "
            "idotless, dotaccentcomb"
        ),
    },)


@pytest.mark.parametrize("glyph_name", ("H", "O", "S", "a"))
def test_representative_regression_glyphs_pass_polygonal_validation(glyph_name):
    outlines, _, _ = load_ufo_outlines(FIXTURE)
    outline = next(item for item in outlines if item.name == glyph_name)
    result = generate_pair(outline, GenerationSettings(project_seed="real-test", complexity=50))
    assert result.validation.compatible
    assert result.validation.reconstruction.normalized_symmetric_difference <= 1e-8


@pytest.mark.parametrize("glyph_name", ("A", "M", "R", "eight"))
def test_stable_multiply_wound_glyphs_use_bounded_overlap_normalization(glyph_name):
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
    with pytest.raises(UnsupportedOutlineError, match="components require decomposition"):
        defcon_glyph_to_outline(font["i"], units_per_em=1000)
    font.close()


def test_regression_ufo_retains_shared_data_and_declared_provenance():
    from defcon import Font

    font = Font(FIXTURE)
    assert font.lib["com.fracturize.fixture.provenance"]["generator"] == (
        "scripts/build_regression_fixture.py"
    )
    assert font.glyphOrder == [
        "A", "H", "I", "M", "O", "R", "S", "a",
        "dotaccentcomb", "eight", "idotless", "i",
    ]
    assert font.groups["public.kern1.syntheticLeft"] == ["H", "I"]
    assert font.kerning[
        ("public.kern1.syntheticLeft", "public.kern2.syntheticRound")
    ] == -45
    assert "feature kern" in font.features.text
    assert len(font.guidelines) == 1
    assert "public.background" in font.layers
    assert "com.fracturize.fixture/README.txt" in font.data.fileNames
    assert font["O"].note
    assert font["O"].anchors[0].name == "top"
    assert len(font["i"].components) == 2
    font.close()
