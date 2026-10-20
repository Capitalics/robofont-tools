"""Independent tools registered in the RoboFont Tools palette."""


def get_tool_classes():
    # Keep RoboFont imports out of the pure calculation/test boundary.
    from .contour_probe import ContourProbeTool
    from .distribute_points import DistributePointsTool
    from .select_between import SelectBetweenTool
    from .selected_points import SelectedPointsTool

    return (SelectedPointsTool, ContourProbeTool, DistributePointsTool, SelectBetweenTool)


__all__ = ("get_tool_classes",)
