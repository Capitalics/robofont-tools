import json
import os

from AppKit import NSApp


# Keep this location unchanged for compatibility with existing layouts.
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
    saved_titles = set()
    for window in NSApp.windows():
        data = window_to_dict(window)
        if data is None:
            continue

        # NSApp can contain multiple windows with the same title. The restore
        # code can only address one window for a given title, so save the first
        # instance only. This makes one save operation a complete replacement
        # snapshot rather than a list of conflicting frames.
        title = data["title"]
        if title in saved_titles:
            continue

        saved_titles.add(title)
        windows.append(data)
    return windows


def save_layout(path=LAYOUT_PATH):
    windows = collect_windows()
    folder = os.path.dirname(path)
    os.makedirs(folder, exist_ok=True)

    with open(path, "w") as layout_file:
        json.dump({"windows": windows}, layout_file, indent=2, sort_keys=True)
        layout_file.write("\n")

    print(
        "Workspace Launcher replaced the saved layout with %s unique windows at %s"
        % (len(windows), path)
    )
