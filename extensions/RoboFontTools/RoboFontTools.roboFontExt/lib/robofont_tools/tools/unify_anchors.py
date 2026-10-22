"""Designspace anchor unifier launched from the RoboFont Tools palette."""
from __future__ import annotations

from pathlib import Path
import traceback

from .base import PaletteTool
from .unify_anchors_model import (
    anchor_plan, anchor_records, append_anchor, desired_anchor_names,
    load_designspace, order_anchors,
)


class UnifyAnchorsTool(PaletteTool):
    content = """
    * TwoColumnForm @unifyAnchorsControl
    > : Anchors:
    > (Unify from Default…) @unifyAnchorsButton
    """

    def __init__(self):
        super().__init__()
        self._window = None

    def descriptions(self):
        return {
            "unifyAnchorsControl": {"titleColumnWidth": 120, "itemColumnWidth": 142},
            "unifyAnchorsButton": {"callback": lambda sender: self.open()},
        }

    def stop(self):
        if self._window is not None:
            self._window.w.close()
            self._window = None

    def open(self):
        if self._window is None or not self._window.w.getNSWindow().isVisible():
            self._window = AnchorUnifierWindow()
        else:
            self._window.w.makeKey()


class AnchorUnifierWindow:
    def __init__(self):
        from vanilla import Button, FloatingWindow, TextBox, TextEditor

        self.designspace_path = None
        self.default_override = None
        self.default_path = None
        self.source_paths = []
        self.preview_ready = False
        self.w = FloatingWindow((570, 460), "Unify Anchors from Default",
                                minSize=(480, 380))
        self.w.loadDesignspace = Button((12, 12, 170, 24), "Load Designspace…",
                                        callback=self.load_designspace)
        self.w.chooseDefault = Button((194, 12, 170, 24), "Choose Default UFO…",
                                      callback=self.choose_default)
        self.w.designspaceInfo = TextBox((12, 44, -12, 20), "No designspace loaded")
        self.w.defaultInfo = TextBox((12, 68, -12, 20), "Default: not selected")
        self.w.preview = Button((12, 100, 120, 26), "Preview Changes",
                                callback=self.preview)
        self.w.apply = Button((144, 100, 120, 26), "Apply and Save",
                              callback=self.apply)
        self.w.apply.enable(False)
        self.w.report = TextEditor((12, 138, -12, -12), readOnly=True)
        self._report("Load a designspace. Its default source is selected automatically.\n"
                     "Preview before applying. Existing anchors keep their positions; "
                     "extra anchors are reported and retained.")
        self.w.open()

    def _report(self, message):
        self.w.report.set(message)
        print("Unify Anchors: " + message)

    def _load(self):
        self.default_path, self.source_paths = load_designspace(
            self.designspace_path, self.default_override)
        self.w.designspaceInfo.set(f"Designspace: {Path(self.designspace_path).name} "
                                   f"({len(self.source_paths)} sources)")
        self.w.defaultInfo.set(f"Default: {self.default_path.name}")
        self.preview_ready = False
        self.w.apply.enable(False)
        self._report("Sources loaded. Click Preview Changes.")

    def load_designspace(self, sender):
        from mojo.UI import GetFile
        path = GetFile(message="Choose a designspace", fileTypes=["designspace"],
                       allowsMultipleSelection=False)
        if not path:
            return
        self.designspace_path = str(path)
        self.default_override = None
        try:
            self._load()
        except Exception as error:
            self.default_path, self.source_paths = None, []
            self.w.apply.enable(False)
            self._report(f"Could not load designspace: {error}")

    def choose_default(self, sender):
        from mojo.UI import GetFile
        path = GetFile(message="Choose the default source UFO", fileTypes=["ufo"],
                       allowsMultipleSelection=False)
        if not path:
            return
        if not self.designspace_path:
            self._report("Load a designspace first.")
            return
        previous = self.default_override
        self.default_override = str(path)
        try:
            self._load()
        except Exception as error:
            self.default_override = previous
            self._report(f"Could not use that default: {error}")

    def _fonts(self):
        from defcon import Font
        from mojo.roboFont import AllFonts

        open_fonts = {Path(font.path).resolve(): font for font in AllFonts()
                      if getattr(font, "path", None)}
        return {path: open_fonts.get(path) or Font(str(path))
                for path in self.source_paths}

    def _run(self, save):
        if not self.source_paths or not self.default_path:
            self._report("Load a designspace first.")
            return
        try:
            fonts = self._fonts()
            default_font = fonts[self.default_path]
            operations = []
            lines = []
            missing_count = extra_count = skipped_count = reordered_count = 0
            for path in self.source_paths:
                if path == self.default_path:
                    continue
                font = fonts[path]
                for glyph_name in sorted(default_font.keys()):
                    default_glyph = default_font[glyph_name]
                    if glyph_name not in font:
                        if default_glyph.anchors:
                            lines.append(f"{path.name} / {glyph_name}: glyph missing; skipped")
                            skipped_count += 1
                        continue
                    glyph = font[glyph_name]
                    default_anchors = anchor_records(default_glyph)
                    source_anchors = anchor_records(glyph)
                    missing, extras, duplicates = anchor_plan(
                        default_anchors, source_anchors)
                    if duplicates:
                        lines.append(f"{path.name} / {glyph_name}: duplicate anchor names "
                                     f"{', '.join(duplicates)}; skipped")
                        skipped_count += 1
                        continue
                    target_names = desired_anchor_names(default_anchors, source_anchors)
                    current_names = [name for name, _, _ in source_anchors]
                    reorder = target_names != current_names + [name for name, _, _ in missing]
                    if missing:
                        lines.append(f"{path.name} / {glyph_name}: add "
                                     f"{', '.join(name for name, _, _ in missing)}")
                        missing_count += len(missing)
                    if reorder:
                        lines.append(f"{path.name} / {glyph_name}: match default anchor order")
                        reordered_count += 1
                    if missing or reorder:
                        operations.append((glyph, missing, target_names, font))
                    if extras:
                        lines.append(f"{path.name} / {glyph_name}: extra retained "
                                     f"{', '.join(extras)}")
                        extra_count += len(extras)
            summary = (f"Other sources: {len(self.source_paths) - 1} · "
                       f"add anchors: {missing_count} · reorder glyphs: {reordered_count} · "
                       f"retained extras: {extra_count} · "
                       f"skipped glyphs: {skipped_count}")
            if save:
                changed_fonts = set()
                for glyph, missing, target_names, font in operations:
                    for name, x, y in missing:
                        append_anchor(glyph, name, x, y)
                    order_anchors(glyph, target_names)
                    changed_fonts.add(font)
                for font in changed_fonts:
                    font.save()
                self.preview_ready = False
                self.w.apply.enable(False)
                summary = "Applied and saved. " + summary
            else:
                self.preview_ready = bool(operations)
                self.w.apply.enable(self.preview_ready)
                summary = "Preview only. " + summary
            self._report(summary + ("\n\n" + "\n".join(lines) if lines else "\nNo differences found."))
        except Exception as error:
            self.preview_ready = False
            self.w.apply.enable(False)
            self._report(f"Failed: {error}")
            traceback.print_exc()

    def preview(self, sender):
        self._run(save=False)

    def apply(self, sender):
        if self.preview_ready:
            self._run(save=True)
