"""The Cleanup window: load a designspace once, then run cleanups on it.

Sections: Anchors, then Layers / Guides / Mark colours, then Absent glyphs.
All share one session and its open-vs-closed save rule.
"""
from __future__ import annotations

from pathlib import Path
import traceback

from .session import CleanupSession
from .sources import load_designspace


_window = None


def open_window():
    global _window
    if _window is None:
        _window = CleanupWindow()
    else:
        _window.w.show()
        _window.w.makeKey()
    return _window


def _open_fonts():
    from mojo.roboFont import AllFonts
    return {Path(font.path).resolve(): font for font in AllFonts()
            if getattr(font, "path", None)}


class CleanupWindow:
    def __init__(self):
        from vanilla import (
            Button, FloatingWindow, List, PopUpButton, TextBox, TextEditor,
        )

        self.designspace_path = None
        self.default_override = None
        self.session = None
        self._rows = []
        self._audit_lines = []
        self._audit = None
        self._absent = ()

        self.w =FloatingWindow((680, 880), "Cleanup", minSize=(560, 780))
        self.w.bind("close", self._closed)

        # Designspace header, shared by every section.
        self.w.loadDesignspace = Button((12, 12, 150, 24), "Load Designspace…",
                                        callback=self.load_designspace)
        self.w.chooseDefault = Button((170, 12, 150, 24), "Choose Default…",
                                      callback=self.choose_default)
        self.w.rescan = Button((328, 12, 90, 24), "Rescan", callback=self.rescan)
        self.w.designspaceInfo = TextBox((12, 46, -12, 18), "No designspace loaded")
        self.w.sources = List(
            (12, 68, -12, 100), [],
            columnDescriptions=[
                {"title": "Source", "key": "label"},
                {"title": "State", "key": "state", "width": 150},
            ],
            allowsMultipleSelection=False, showColumnTitles=True,
        )

        # Audit: what needs doing. Click an anchor line to select those glyphs.
        self.w.auditTitle = TextBox((12, 178, -12, 18), "Audit")
        self.w.audit = List(
            (12, 198, -12, 120), [],
            columnDescriptions=[{"title": "Status", "key": "text"}],
            allowsMultipleSelection=False, showColumnTitles=False,
            allowsSorting=False, selectionCallback=self._audit_selected,
        )

        # Anchors section.
        self.w.anchorsTitle = TextBox((12, 328, -12, 18), "Anchors")
        self.w.anchorRows = List(
            (12, 350, -12, -350), [],
            columnDescriptions=[
                {"title": "Glyph", "key": "glyph", "width": 140},
                {"title": "Differences", "key": "differences"},
            ],
            allowsMultipleSelection=True, showColumnTitles=True,
            allowsSorting=False,
        )
        self.w.matchDefault = Button((12, -340, 150, 24), "Match Default",
                                     callback=self.match_default)
        self.w.removeAll = Button((170, -340, 170, 24), "Remove All Anchors",
                                  callback=self.remove_all)
        self.w.anchorSummary = TextBox((350, -337, -12, 18), "")

        # Whole-designspace removals; the audit above previews what goes.
        self.w.marksTitle = TextBox((12, -302, -12, 18), "Layers · Guides · Mark colours")
        self.w.removeLayers = Button((12, -280, 170, 24), "Remove Extra Layers",
                                     callback=self.remove_layers)
        self.w.removeGuides = Button((190, -280, 150, 24), "Remove Guides",
                                     callback=self.remove_guides)
        self.w.stripColours = Button((348, -280, 170, 24), "Strip Mark Colours",
                                     callback=self.strip_colours)

        # Absent glyphs: names to paste into Add Glyphs, per source.
        self.w.absentTitle = TextBox((12, -240, 110, 18), "Absent glyphs")
        self.w.absentSource = PopUpButton((122, -242, 260, 22), [],
                                          callback=self._show_absent)
        self.w.copyAbsent = Button((392, -243, 80, 24), "Copy",
                                   callback=self.copy_absent)
        self.w.absentNames = TextEditor((12, -212, -12, 70), readOnly=True)
        self.w.report = TextEditor((12, -132, -12, -12), readOnly=True)
        self._enable(False)
        self._report("Load a designspace. Its default source is selected automatically.\n"
                     "Select rows (Cmd-A for all), then Match Default or Remove All Anchors.\n"
                     "Layer, guide and colour buttons act on the whole designspace; "
                     "the audit shows what they remove.\n"
                     "Open fonts are changed with undo and left unsaved; "
                     "closed UFOs are saved.")
        self.w.open()

    # --- window helpers ----------------------------------------------------

    def _closed(self, sender):
        global _window
        _window = None

    def _report(self, message):
        self.w.report.set(message)
        print("RoboFont Tools / Cleanup: " + message.splitlines()[0])

    def _enable(self, enabled):
        for name in ("rescan", "matchDefault", "removeAll", "removeLayers",
                     "removeGuides", "stripColours", "copyAbsent"):
            getattr(self.w, name).enable(enabled)

    def _selected_glyphs(self):
        return [self._rows[index].glyph for index in self.w.anchorRows.getSelection()
                if index < len(self._rows)]

    # --- designspace -------------------------------------------------------

    def _load(self):
        default, sources = load_designspace(self.designspace_path, self.default_override)
        self.session = CleanupSession(default, sources, _open_fonts)
        self.w.designspaceInfo.set(
            f"{Path(self.designspace_path).name} · {len(sources)} sources · "
            f"default: {default.label}")
        self._enable(True)
        self.rescan(None)

    def load_designspace(self, sender):
        from mojo.UI import GetFile
        path = GetFile(message="Choose a designspace", fileTypes=["designspace"],
                       allowsMultipleSelection=False)
        if not path:
            return
        previous = self.designspace_path, self.default_override
        self.designspace_path, self.default_override = str(path), None
        try:
            self._load()
        except Exception as error:
            self.designspace_path, self.default_override = previous
            self._report(f"Could not load designspace: {error}")

    def choose_default(self, sender):
        if not self.designspace_path:
            self._report("Load a designspace first.")
            return
        from mojo.UI import GetFile
        path = GetFile(message="Choose the default source UFO", fileTypes=["ufo"],
                       allowsMultipleSelection=False)
        if not path:
            return
        previous = self.default_override
        self.default_override = str(path)
        try:
            self._load()
        except Exception as error:
            self.default_override = previous
            self._report(f"Could not use that default: {error}")

    def rescan(self, sender):
        if self.session is None:
            return
        try:
            self._show_sources()
            audit, report = self.session.scan()
        except Exception as error:
            self._rows = []
            self._audit = None
            self._audit_lines = []
            self.w.anchorRows.set([])
            self.w.audit.set([])
            self._set_absent(())
            self._report(f"Scan failed: {error}")
            traceback.print_exc()
            return
        self._audit = audit
        self._audit_lines = list(audit.lines())
        self.w.audit.set([{"text": line.text} for line in self._audit_lines])
        self._rows = list(report.rows)
        self.w.anchorRows.set([{"glyph": row.glyph, "differences": row.differences}
                               for row in report.rows])
        self.w.anchorSummary.set(
            f"{len(report.rows)} glyphs differ · {len(report.absent)} absent from "
            f"some sources (allowed) · {len(report.outside_default)} not in default")
        self._set_absent(report.absent_by_source)
        lines = [f"Scanned. {len(report.rows)} glyphs have anchor differences."]
        lines += list(self.session.warnings)
        if sender is not None or len(lines) > 1:
            self._report("\n".join(lines))

    def _audit_selected(self, sender):
        selection = sender.getSelection()
        if not selection or self._audit is None:
            return
        line = self._audit_lines[selection[0]]
        if line.issue is None:
            return
        wanted = set(self._audit.anchors.glyphs[line.issue])
        self.w.anchorRows.setSelection(
            [index for index, row in enumerate(self._rows) if row.glyph in wanted])
        self.w.anchorRows.scrollToSelection()

    # --- absent glyphs ---------------------------------------------------------

    def _set_absent(self, absent_by_source):
        current = self._absent_label()
        self._absent = tuple(absent_by_source)
        labels = [label for label, _names in self._absent]
        self.w.absentSource.setItems(
            [f"{label} — {len(names)} missing" for label, names in self._absent]
            or ["No source is missing glyphs"])
        self.w.absentSource.set(labels.index(current) if current in labels else 0)
        self.w.absentSource.enable(bool(self._absent))
        self.w.copyAbsent.enable(bool(self._absent))
        self._show_absent(None)

    def _absent_label(self):
        index = self.w.absentSource.get()
        if 0 <= index < len(self._absent):
            return self._absent[index][0]
        return None

    def _absent_text(self):
        index = self.w.absentSource.get()
        if 0 <= index < len(self._absent):
            return " ".join(self._absent[index][1])
        return ""

    def _show_absent(self, sender):
        self.w.absentNames.set(self._absent_text())

    def copy_absent(self, sender):
        text = self._absent_text()
        if not text:
            return
        from AppKit import NSPasteboard, NSPasteboardTypeString
        board = NSPasteboard.generalPasteboard()
        board.clearContents()
        board.setString_forType_(text, NSPasteboardTypeString)
        count = len(text.split())
        self._report(f"Copied {count} glyph name{'s' if count != 1 else ''} "
                     f"missing from {self._absent_label()}.")

    def _show_sources(self):
        items = []
        for source in self.session.sources:
            state = "open · undo, unsaved" if self.session.is_open(source) else "closed · saved on fix"
            if source == self.session.default:
                state = "default · " + state
            items.append({"label": source.label, "state": state})
        self.w.sources.set(items)

    # --- anchor fixes ----------------------------------------------------------

    def _fix(self, action, verb):
        glyphs = self._selected_glyphs()
        if not glyphs:
            self._report("Select one or more rows first (Cmd-A selects all).")
            return
        try:
            saved, skipped, edits = action(glyphs)
        except Exception as error:
            self._report(f"Stopped after an error: {error}. "
                         "Check the sources before saving.")
            traceback.print_exc()
            self.rescan(None)
            return
        source_count = len({edit.source for edit in edits})
        lines = [f"{verb}: {len(edits)} glyph edit{'s' if len(edits) != 1 else ''} "
                 f"across {source_count} source{'s' if source_count != 1 else ''}."]
        if saved:
            lines.append("Saved closed UFOs: " + ", ".join(saved))
        if skipped:
            lines.append("Skipped (duplicate anchor names): " + ", ".join(skipped))
        copied = [f"{edit.source} / {edit.glyph}: {', '.join(edit.added)}"
                  for edit in edits if edit.added]
        if copied:
            lines.append("")
            lines.append("Anchors added at the default's coordinates — check these:")
            lines += copied
        self.rescan(None)
        self._report("\n".join(lines + list(self.session.warnings)))

    def match_default(self, sender):
        self._fix(self.session.match_default, "Matched default")

    def remove_all(self, sender):
        self._fix(self.session.remove_all, "Removed all anchors")

    # --- layers, guides, mark colours --------------------------------------

    def _whole_fix(self, action, verb, nothing):
        if self.session is None:
            return
        try:
            result = action()
        except Exception as error:
            self._report(f"Stopped after an error: {error}. "
                         "Check the sources before saving.")
            traceback.print_exc()
            self.rescan(None)
            return
        if not result.removed:
            lines = [nothing]
        else:
            lines = [f"{verb}:"] + [f"  {label}: {what} ({count})"
                                    for label, what, count in result.removed]
        if result.saved:
            lines.append("Saved closed UFOs: " + ", ".join(result.saved))
        if result.no_undo:
            lines.append("Changed without undo (open, unsaved — revert the font to undo): "
                         + ", ".join(result.no_undo))
        self.rescan(None)
        self._report("\n".join(lines + list(self.session.warnings)))

    def remove_layers(self, sender):
        self._whole_fix(self.session.remove_extra_layers, "Removed layers",
                        "No extra layers to remove.")

    def remove_guides(self, sender):
        self._whole_fix(self.session.remove_guides, "Removed guides", "No guides to remove.")

    def strip_colours(self, sender):
        self._whole_fix(self.session.strip_mark_colours, "Stripped mark colours",
                        "No mark colours to strip.")
