import json
import os

from AppKit import NSApp


LAYOUT_DIR = os.path.expanduser(
    "~/Library/Application Support/RoboFont/WorkspaceLauncher"
)
LAYOUT_PATH = os.path.join(LAYOUT_DIR, "layout.json")


def frame_to_dict(frame):
    return {
        "x": float(frame.origin.x),
        "y": float(frame.origin.y),
        "width": float(frame.size.width),
        "height": float(frame.size.height),
    }


def window_to_dict(window):
    title = window.title()
    if not title:
        return None

    data = {"title": str(title)}
    data.update(frame_to_dict(window.frame()))
    return data


def collect_windows():
    windows = []
    for window in NSApp.windows():
        data = window_to_dict(window)
        if data is not None:
            windows.append(data)
    return windows


def save_layout(path=LAYOUT_PATH):
    windows = collect_windows()
    folder = os.path.dirname(path)
    os.makedirs(folder, exist_ok=True)

    with open(path, "w") as layout_file:
        json.dump({"windows": windows}, layout_file, indent=2, sort_keys=True)
        layout_file.write("\n")

    print("Workspace Launcher saved %s windows to %s" % (len(windows), path))


save_layout()
