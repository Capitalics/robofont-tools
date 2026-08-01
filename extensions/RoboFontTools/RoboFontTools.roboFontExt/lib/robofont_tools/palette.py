from __future__ import annotations

import ezui

from .tools import get_tool_classes


TOOL_CLASSES = get_tool_classes()


class RoboFontToolsPaletteController(ezui.WindowController):
    title = "RoboFont Tools"
    width = 300

    def build(self):
        self._closed = False
        self._tools = []
        content, description_data = self._build_tool_descriptions()
        self.w = ezui.EZWindow(
            title=self.title,
            size=(self.width, 110),
            minSize=(self.width, 110),
            maxSize=(360, 160),
            autosaveName="com.boryskosmynka.robofonttools.toggler.palette",
            miniaturizable=False,
            content=content,
            margins=10,
            sizeStyle="small",
            controller=self,
            descriptionData=description_data,
        )
        self.w.getNSWindow().setTitlebarAppearsTransparent_(True)

    def _build_tool_descriptions(self):
        content_parts = []
        description_data = {}
        for tool_class in TOOL_CLASSES:
            content_parts.append(tool_class.content)
            description_data.update(tool_class.description_data)
        return "\n".join(content_parts), description_data

    def started(self):
        renderers = {
            "SelectedPointsTool": self._render_SelectedPointsTool,
            "ContourProbeTool": self._render_ContourProbeTool,
        }
        for tool_class in TOOL_CLASSES:
            renderer = renderers.get(tool_class.__name__)
            if renderer is None:
                print(
                    "RoboFontTools: no palette renderer registered for "
                    f"{tool_class.__name__}"
                )
                continue
            tool = tool_class(renderer)
            tool.start()
            if tool_class.__name__ == "ContourProbeTool":
                self.w.getItem("contourProbeEnabled").set(tool.is_enabled())
            elif tool_class.__name__ == "SelectedPointsTool":
                self.w.getItem("selectedPointsEnabled").set(tool.is_enabled())
            self._tools.append(tool)
        self.w.open()
        print("RoboFontTools: palette started")

    def destroy(self):
        self._closed = True
        for tool in reversed(self._tools):
            tool.stop()
        self._tools.clear()
        from .extension import window_closed

        window_closed()

    def refresh(self):
        if self._closed:
            return
        for tool in self._tools:
            tool.refresh()

    def _render_SelectedPointsTool(self, _presentation=None):
        """Selected Points renders its values in the glyph-editor HUD."""

    def _render_ContourProbeTool(self, _presentation=None):
        """Contour Probe's controls are defined by EZUI; no value rendering."""

    def _contourProbeEnabledCallback(self, sender):
        for tool in self._tools:
            if tool.__class__.__name__ == "ContourProbeTool":
                tool.set_enabled(sender.get())
                break

    def _selectedPointsEnabledCallback(self, sender):
        for tool in self._tools:
            if tool.__class__.__name__ == "SelectedPointsTool":
                tool.set_enabled(sender.get())
                break
