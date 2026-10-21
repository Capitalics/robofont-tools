from __future__ import annotations

import ezui

from .tools import get_tool_classes
from .tools.rough_slice_model import SliceSettings


TOOL_CLASSES = get_tool_classes()


class RoboFontToolsPaletteController(ezui.WindowController):
    title = "RoboFont Tools"
    width = 320

    def build(self):
        self._closed = False
        self._tools = []
        content, description_data = self._build_tool_descriptions()
        self.w = ezui.EZWindow(
            title=self.title,
            size=(self.width, 320),
            minSize=(280, 320),
            maxSize=(400, 380),
            autosaveName="com.boryskosmynka.robofonttools.palette.v2",
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
            "DistributePointsTool": self._render_DistributePointsTool,
            "SelectBetweenTool": self._render_SelectBetweenTool,
            "RoughSliceTool": self._render_RoughSliceTool,
            "UnifyAnchorsTool": self._render_UnifyAnchorsTool,
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
            if tool_class.__name__ == "RoughSliceTool":
                tool.set_settings_provider(self._rough_slice_settings)
                tool.set_active_callback(self._rough_slice_active_changed)
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

    def _render_DistributePointsTool(self, _presentation=None):
        """Distribute Points is a one-shot action; there is nothing to render."""

    def _render_SelectBetweenTool(self, _presentation=None):
        """Select Between is a one-shot action; there is nothing to render."""

    def _render_RoughSliceTool(self, _presentation=None):
        """Rough Slice draws its preview in the Glyph Editor."""

    def _render_UnifyAnchorsTool(self, _presentation=None):
        """Anchor unification runs in its own designspace window."""

    def _rough_slice_settings(self):
        return SliceSettings(
            spacing=float(self.w.getItem("roughSliceSpacing").get()),
            gap=float(self.w.getItem("roughSliceGap").get()),
            jitter=float(self.w.getItem("roughSliceJitter").get()),
        )

    def _rough_slice_active_changed(self, active):
        if self._closed:
            return
        button = self.w.getItem("roughSliceButton")
        button.getNSButton().setTitle_("Knife Active — Drag" if active else "Activate Knife")

    def _roughSliceCallback(self, sender):
        try:
            self._rough_slice_settings().validate()
        except (ValueError, TypeError) as error:
            print(f"Rough Slice: {error}")
            return
        for tool in self._tools:
            if tool.__class__.__name__ == "RoughSliceTool":
                tool.activate()
                break

    def _distribute(self, axis):
        for tool in self._tools:
            if tool.__class__.__name__ == "DistributePointsTool":
                tool.distribute(axis)
                break

    def _distributeHorizontalCallback(self, sender):
        self._distribute("x")

    def _distributeVerticalCallback(self, sender):
        self._distribute("y")

    def _selectBetweenCallback(self, sender):
        for tool in self._tools:
            if tool.__class__.__name__ == "SelectBetweenTool":
                tool.select_between()
                break

    def _unifyAnchorsCallback(self, sender):
        for tool in self._tools:
            if tool.__class__.__name__ == "UnifyAnchorsTool":
                tool.open()
                break

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
