import json
import os


# Keep these locations unchanged for compatibility with existing settings.
DATA_DIR = os.path.expanduser(
    "~/Library/Application Support/RoboFont/WorkspaceLauncher"
)
PROJECT_PATHS_PATH = os.path.join(DATA_DIR, "projectPaths.json")
RESOURCE_NAMES = ("designspace", "defaultFont", "referenceFont")

# This module stays imported while RoboFont is running, so it can retain the
# actual controllers created by the launcher without using window titles.
active_controllers = {}


def load_project_paths(path=PROJECT_PATHS_PATH):
    if not os.path.exists(path):
        return {}
    try:
        with open(path, encoding="utf-8") as project_paths_file:
            data = json.load(project_paths_file)
    except Exception as error:
        print("Workspace Launcher could not read project paths: %s" % error)
        return {}

    if not isinstance(data, dict):
        print("Workspace Launcher project paths file is invalid; ignoring it.")
        return {}
    return {key: value for key, value in data.items() if key in RESOURCE_NAMES and value}


def save_project_paths(paths, path=PROJECT_PATHS_PATH):
    data = load_project_paths(path)
    for key, value in paths.items():
        if key not in RESOURCE_NAMES:
            continue
        # Empty form fields are not an instruction to discard a saved path.
        if value:
            data[key] = value

    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as project_paths_file:
        json.dump(data, project_paths_file, indent=2, sort_keys=True)
        project_paths_file.write("\n")
    return data


def clear_project_path(resource, path=PROJECT_PATHS_PATH):
    if resource not in RESOURCE_NAMES:
        return
    data = load_project_paths(path)
    data.pop(resource, None)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as project_paths_file:
        json.dump(data, project_paths_file, indent=2, sort_keys=True)
        project_paths_file.write("\n")
