from __future__ import annotations

from copy import deepcopy

from defcon import Font

from .live_project import _draw_outline_only, _mark_changed, _native, shared_font_data
from .model import MasterGlyph


def collect_glyph_names(current_name=None, selected_names=(), direct_text=""):
    names = []
    if current_name:
        names.append(current_name)
    names.extend(selected_names or ())
    names.extend(
        token
        for token in direct_text.replace(",", " ").split()
        if token
    )
    return tuple(dict.fromkeys(names))


def master_to_preview_glyph(master: MasterGlyph, *, units_per_em=1000, descender=-250):
    preview_font = Font()
    preview_font.info.unitsPerEm = units_per_em
    preview_font.info.descender = descender
    glyph = preview_font.newGlyph(master.name)
    glyph.width = master.width
    glyph.unicodes = list(master.unicodes)
    _draw_outline_only(glyph, master, {})
    return glyph


class RoboFontEnvironment:
    """All direct RoboFont calls are isolated in this main-thread adapter."""

    def __init__(self):
        from AppKit import NSThread
        from mojo.roboFont import AllFonts, CurrentFont, CurrentGlyph, NewFont, OpenFont

        self._NSThread = NSThread
        self._all_fonts = AllFonts
        self._current_font = CurrentFont
        self._current_glyph = CurrentGlyph
        self._new_font = NewFont
        self._open_font = OpenFont

    def assert_main_thread(self):
        if not self._NSThread.isMainThread():
            raise RuntimeError("RoboFont objects must be accessed on the main thread")

    def all_fonts(self):
        self.assert_main_thread()
        return list(self._all_fonts())

    def current_font(self):
        self.assert_main_thread()
        return self._current_font()

    def current_glyph_name(self):
        self.assert_main_thread()
        glyph = self._current_glyph()
        return glyph.name if glyph is not None else None

    def selected_glyph_names(self, font=None):
        self.assert_main_thread()
        font = font or self.current_font()
        if font is None:
            return ()
        names = getattr(font, "selectedGlyphNames", None)
        if names is None:
            names = getattr(font, "selection", ())
        if not names:
            layer = getattr(font, "defaultLayer", None)
            if layer is None and hasattr(font, "layers"):
                layer = getattr(font.layers, "defaultLayer", None)
            if layer is not None:
                names = getattr(layer, "selectedGlyphNames", names)
        return tuple(names or ())

    def _copy_complete_font(self, source_font, *, show_interface):
        self.assert_main_thread()
        duplicate = self._new_font(showInterface=show_interface)
        duplicate.copyData(source_font)
        source_native = _native(source_font)
        duplicate_native = _native(duplicate)
        # RoboFont seeds a new document with environment-owned default lib
        # entries. Project copies must instead start with the source UFO's
        # persistent lib exactly; Fracturize identity is added later.
        duplicate_native.lib.clear()
        duplicate_native.lib.update(deepcopy(dict(source_native.lib)))
        for file_name in getattr(source_native.data, "fileNames", ()):
            duplicate_native.data[file_name] = deepcopy(source_native.data[file_name])
        for file_name in getattr(source_native.images, "fileNames", ()):
            duplicate_native.images[file_name] = deepcopy(source_native.images[file_name])
        _mark_changed(duplicate_native)
        source_data = shared_font_data(source_font)
        duplicate_data = shared_font_data(duplicate)
        if source_data != duplicate_data:
            differing = [key for key in source_data if source_data[key] != duplicate_data[key]]
            raise RuntimeError("font duplication lost data: " + ", ".join(differing))
        return duplicate

    def write_working_font_copy(self, source_font, path, *, style_name):
        """Write a complete UFO copy without leaving a hidden document open."""

        self.assert_main_thread()
        duplicate = self._copy_complete_font(source_font, show_interface=False)
        try:
            duplicate.info.styleName = style_name
            duplicate.save(
                path=str(path),
                formatVersion=3,
                fileStructure="package",
            )
        finally:
            duplicate.close(save=False)

    def save_font(self, font):
        self.assert_main_thread()
        font.save()

    def open_font(self, path):
        self.assert_main_thread()
        return self._open_font(path, showInterface=True)

    def ensure_project_fonts_open(self, project, logger=None):
        self.assert_main_thread()
        fonts = self.all_fonts()
        if logger is not None:
            logger("already_open_fonts", paths=[str(font.path) for font in fonts if font.path])
        project.attach_fonts(fonts)
        opened = []
        for role in ("intact", "eroded"):
            if getattr(project, f"{role}_font") is not None:
                if logger is not None:
                    logger("font_matched", role=role, path=str(getattr(project, f"{role}_font").path))
                continue
            path = project.data["workingFonts"][role].get("path")
            if path:
                if logger is not None:
                    logger("font_open_start", role=role, path=path)
                font = self.open_font(path)
                if font is not None:
                    opened.append(font)
                if logger is not None:
                    logger("font_open_end", role=role, path=path, returned=font is not None)
        if project.source_font is None and project.data["source"].get("path"):
            path = project.data["source"]["path"]
            if logger is not None:
                logger("font_open_start", role="source", path=path)
            font = self.open_font(path)
            if font is not None:
                opened.append(font)
            if logger is not None:
                logger("font_open_end", role="source", path=path, returned=font is not None)
        registered = self.all_fonts()
        # OpenFont returns the live document object before AllFonts necessarily
        # reflects document registration. Bind against both sets.
        candidates = list(registered)
        candidates.extend(font for font in opened if font not in candidates)
        project.attach_fonts(candidates)
        return project.fonts_available
