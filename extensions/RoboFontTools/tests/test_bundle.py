from __future__ import annotations

import plistlib
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / "RoboFontTools.roboFontExt"


class BundleTests(unittest.TestCase):

    def test_bundle_metadata_and_menu_path(self):
        with (BUNDLE / "info.plist").open("rb") as stream:
            info = plistlib.load(stream)
        self.assertEqual(info["name"], "RoboFont Tools")
        self.assertEqual(info["requiresVersionMajor"], "4")
        self.assertEqual(info["requiresVersionMinor"], "6")
        self.assertEqual(
            info["addToMenu"],
            [
                {
                    "path": "startup.py",
                    "preferredName": "RoboFont Tools",
                    "shortKey": "",
                }
            ],
        )

    def test_runtime_structure_is_inside_bundle_and_tests_are_not(self):
        package = BUNDLE / "lib" / "robofont_tools"
        self.assertTrue((BUNDLE / "lib" / "startup.py").is_file())
        self.assertTrue((package / "extension.py").is_file())
        self.assertTrue((package / "palette.py").is_file())
        self.assertTrue((package / "geometry.py").is_file())
        self.assertTrue((package / "tools" / "selected_points.py").is_file())
        self.assertTrue(
            (package / "tools" / "selected_points_model.py").is_file()
        )
        self.assertTrue((package / "tools" / "contour_probe.py").is_file())
        self.assertTrue(
            (package / "tools" / "contour_probe_model.py").is_file()
        )
        self.assertTrue(
            (package / "tools" / "contour_probe_state.py").is_file()
        )
        self.assertTrue(
            (package / "tools" / "selected_points_state.py").is_file()
        )
        self.assertFalse((BUNDLE / "tests").exists())

    def test_runtime_sources_use_supported_lifecycle_apis(self):
        selected_points = (
            BUNDLE
            / "lib"
            / "robofont_tools"
            / "tools"
            / "selected_points.py"
        ).read_text()
        palette = (
            BUNDLE / "lib" / "robofont_tools" / "palette.py"
        ).read_text()
        self.assertIn("registerGlyphEditorSubscriber", selected_points)
        self.assertIn("unregisterGlyphEditorSubscriber", selected_points)
        self.assertIn("glyphEditorGlyphDidChangeSelection", selected_points)
        self.assertIn("glyphEditorDidSetGlyph", selected_points)
        self.assertIn("glyphEditorGlyphDidChange", selected_points)
        self.assertIn("extensionContainer", selected_points)
        self.assertIn("SelectedPointsHUD", selected_points)
        self.assertIn("getGlyphView", selected_points)
        self.assertIn("addSubview_", selected_points)
        self.assertNotIn("HUD TEST", selected_points)
        self.assertNotIn("selectedPointsInfoBox", selected_points)
        self.assertIn("ezui.EZWindow", palette)
        self.assertIn("tool.stop()", palette)
        self.assertIn('"ContourProbeTool": self._render_ContourProbeTool', palette)
        self.assertNotIn('getattr(self, f"_render_{tool_class.__name__}")', palette)
        contour_probe = (
            BUNDLE / "lib" / "robofont_tools" / "tools" / "contour_probe.py"
        ).read_text()
        self.assertIn("registerGlyphEditorSubscriber", contour_probe)
        self.assertIn("unregisterGlyphEditorSubscriber", contour_probe)
        self.assertIn("glyphEditorDidMouseMove", contour_probe)
        self.assertIn("extensionContainer", contour_probe)
        self.assertIn("from .contour_probe_state import state", contour_probe)


if __name__ == "__main__":
    unittest.main()
