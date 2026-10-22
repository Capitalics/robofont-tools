from __future__ import annotations

import ezui

from .tools import get_tool_classes


class RoboFontToolsPaletteController(ezui.WindowController):
    """Stacks the registered tools; each tool wires its own controls."""

    title = "RoboFont Tools"
    width = 320

    def build(self):
        self._closed = False
        self._tools = [tool_class() for tool_class in get_tool_classes()]
        description_data = {}
        for tool in self._tools:
            description_data.update(tool.descriptions())
        self.w = ezui.EZWindow(
            title=self.title,
            size=(self.width, 320),
            minSize=(280, 320),
            maxSize=(400, 420),
            autosaveName="com.boryskosmynka.robofonttools.palette.v2",
            miniaturizable=False,
            content="\n".join(tool.content for tool in self._tools),
            margins=10,
            sizeStyle="small",
            controller=self,
            descriptionData=description_data,
        )
        self.w.getNSWindow().setTitlebarAppearsTransparent_(True)

    def started(self):
        for tool in self._tools:
            tool.attach(self.w)
            tool.start()
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
