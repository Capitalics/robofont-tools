"""Independent tools registered in the RoboFont Tools palette."""


def get_tool_classes():
    # Keep RoboFont imports out of the pure calculation/test boundary.
    from .contour_probe import ContourProbeTool
    from .selected_points import SelectedPointsTool

    return (SelectedPointsTool, ContourProbeTool)


__all__ = ("get_tool_classes",)
