"""The Cleanup window: load a designspace once, then run cleanups on it.

Anchors is the only section so far; later sections reuse the same session.
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
        from vanilla import Button, FloatingWindow, List, TextBox, TextEditor

        self.designspace_path = None
        self.default_override = None
        self.session = None
        self._rows = []
        self._audit_lines = []
        self._audit = None

        self.w = FloatingWindow((680, 720), "Cleanup", minSize=(560, 600))
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
            (12, 350, -12, -190), [],
            columnDescriptions=[
                {"title": "Glyph", "key": "glyph", "width": 140},
                {"title": "Differences", "key": "differences"},
            ],
            allowsMultipleSelection=True, showColumnTitles=True,
            allowsSorting=False,
        )
        self.w.matchDefault = Button((12, -180, 150, 24), "Match Default",
                                     callback=self.match_default)
        self.w.removeAll = Button((170, -180, 170, 24), "Remove All Anchors",
                                  callback=self.remove_all)
        self.w.anchorSummary = TextBox((350, -177, -12, 18), "")
        self.w.report = TextEditor((12, -146, -12, -12), readOnly=True)
        self._enable(False)
        self._report("Load a designspace. Its default source is selected automatically.\n"
                     "Select rows (Cmd-A for all), then Match Default or Remove All Anchors.\n"
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
        for name in ("rescan", "matchDefault", "removeAll"):
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
