"""Remove extra anchors from open UFOs using one open font as the default."""
from __future__ import annotations

import traceback

from .clean_from_default_model import plan_font


_window = None


def _font_key(font):
    """Use the underlying open font, since AllFonts may return new wrappers."""
    return id(font.naked() if hasattr(font, "naked") else font)


def _unique_fonts(fonts):
    seen = set()
    result = []
    for font in fonts:
        if _font_key(font) not in seen:
            seen.add(_font_key(font))
            result.append(font)
    return result


def open_window():
    global _window
    if _window is None:
        _window = CleanAnchorsWindow()
    else:
        _window.w.show()
        _window.w.makeKey()
        _window.refresh_fonts(None)
    return _window


class CleanAnchorsWindow:
    def __init__(self):
        from vanilla import Button, FloatingWindow, PopUpButton, TextBox, TextEditor

        self.fonts = []
        self.preview_signature = None
        self.w = FloatingWindow(
            (650, 480), "Remove Extra Anchors from Open UFOs",
            minSize=(520, 380), closeCallback=self._closed,
        )
        self.w.defaultLabel = TextBox((12, 15, 95, 20), "Default UFO:")
        self.w.defaultFont = PopUpButton(
            (108, 12, -120, 24), [], callback=self._selection_changed
        )
        self.w.refresh = Button((12, 48, 120, 25), "Refresh Open UFOs",
                                callback=self.refresh_fonts)
        self.w.preview = Button((145, 48, 120, 25), "Preview Changes",
                                callback=self.preview)
        self.w.apply = Button((278, 48, 170, 25), "Apply (Leave Unsaved)",
                              callback=self.apply)
        self.w.apply.enable(False)
        self.w.report = TextEditor((12, 86, -12, -12), readOnly=True)
        self.refresh_fonts(None)
        self.w.open()

    def _closed(self, sender):
        global _window
        _window = None

    def _report(self, message):
        self.w.report.set(message)
        print("RoboFont Tools / Anchors: " + message)

    def _invalidate_preview(self):
        self.preview_signature = None
        self.w.apply.enable(False)

    @staticmethod
    def _label(font, index):
        family = getattr(font.info, "familyName", None) or "Untitled"
        style = getattr(font.info, "styleName", None) or "Regular"
        path = getattr(font, "path", None) or "unsaved"
        return f"{index + 1}. {family} {style} — {path}"

    def refresh_fonts(self, sender):
        from mojo.roboFont import AllFonts

        previous = self._default_font() if self.fonts else None
        self.fonts = _unique_fonts(AllFonts())
        self.w.defaultFont.setItems([
            self._label(font, index) for index, font in enumerate(self.fonts)
        ])
        if previous is not None:
            for index, font in enumerate(self.fonts):
                if _font_key(font) == _font_key(previous):
                    self.w.defaultFont.set(index)
                    break
        self._invalidate_preview()
        if len(self.fonts) < 2:
            self._report("Open at least two UFOs, then click Refresh Open UFOs.")
        else:
            self._report(
                f"{len(self.fonts)} open UFOs. Choose the default, then preview. "
                "All other open UFOs will be checked. Nothing is saved automatically."
            )

    def _default_font(self):
        index = self.w.defaultFont.get()
        if index is None or index < 0 or index >= len(self.fonts):
            return None
        return self.fonts[index]

    def _selection_changed(self, sender):
        self._invalidate_preview()
        self._report("Default changed. Preview again before applying.")

    @staticmethod
    def _anchor_map(font):
        return {
            name: tuple(anchor.name for anchor in font[name].anchors)
            for name in font.keys()
        }

    def _plan(self):
        from mojo.roboFont import AllFonts

        current_fonts = _unique_fonts(AllFonts())
        if len(self.fonts) < 2 or {
            _font_key(font) for font in current_fonts
        } != {_font_key(font) for font in self.fonts}:
            raise ValueError("Open UFOs changed. Refresh and preview again.")
        default = self._default_font()
        if default is None:
            raise ValueError("Choose a default UFO.")

        default_map = self._anchor_map(default)
        operations = []
        lines = [f"Default: {self._label(default, self.fonts.index(default))}", ""]
        missing_count = 0
        for font in self.fonts:
            if font is default:
                continue
            changes, missing = plan_font(default_map, self._anchor_map(font))
            lines.append(self._label(font, self.fonts.index(font)))
            for name, extras in sorted(changes.items()):
                operations.append((font, name, extras))
                lines.append(f"  {name}: remove {', '.join(str(x) for x in extras)}")
            if missing:
                missing_count += len(missing)
                lines.append("  No matching default glyph; skipped: " + ", ".join(missing))
            if not changes and not missing:
                lines.append("  No changes")
            lines.append("")
        signature = (
            _font_key(default),
            tuple(sorted(_font_key(font) for font in self.fonts)),
            tuple((_font_key(font), name, extras) for font, name, extras in operations),
        )
        return operations, signature, lines, missing_count

    def preview(self, sender):
        self._invalidate_preview()
        try:
            operations, signature, lines, missing = self._plan()
        except Exception as error:
            self._report(str(error))
            return
        anchor_count = sum(len(extras) for _, _, extras in operations)
        summary = (
            f"Preview: {anchor_count} anchors in {len(operations)} glyphs "
            f"across {len(self.fonts) - 1} other UFOs; "
            f"{missing} glyphs skipped.\nChanges will remain unsaved.\n\n"
        )
        self._report(summary + "\n".join(lines))
        if operations:
            self.preview_signature = signature
            self.w.apply.enable(True)

    def apply(self, sender):
        if self.preview_signature is None:
            return
        try:
            operations, signature, _, _ = self._plan()
            if signature != self.preview_signature:
                self._invalidate_preview()
                self._report("Anchors changed since the preview. Preview again before applying.")
                return
            self._invalidate_preview()
            removed = 0
            for font, glyph_name, extras in operations:
                glyph = font[glyph_name]
                default = self._default_font()[glyph_name]
                allowed = {anchor.name for anchor in default.anchors}
                raw_glyph = glyph.naked() if hasattr(glyph, "naked") else glyph
                anchors = [anchor for anchor in raw_glyph.anchors
                           if anchor.name not in allowed]
                if not anchors:
                    continue
                with glyph.undo("Remove Extra Anchors"):
                    for anchor in anchors:
                        raw_glyph.removeAnchor(anchor)
                glyph.changed()
                removed += len(anchors)
            self._report(
                f"Removed {removed} anchors from {len(operations)} glyphs. "
                "Changes are open in RoboFont and have not been saved."
            )
        except Exception as error:
            self._invalidate_preview()
            self._report(f"Stopped after an error: {error}. Check the open UFOs before saving.")
            traceback.print_exc()
