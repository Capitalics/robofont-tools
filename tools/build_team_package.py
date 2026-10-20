#!/usr/bin/env python3
"""Build a small, explicit RoboFont Tools distribution for teammates."""
from __future__ import annotations

import argparse
import plistlib
import re
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo


ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / "extensions/RoboFontTools/RoboFontTools.roboFontExt"
ARCHIVE_NAME = "RoboFontTools-team.zip"
TOP = "RoboFontTools-team"
SCRIPTS = {
    "rename-font-package.py": ROOT / "scripts/rename-font-package.py",
    "compare-component-spacing.py": ROOT / "scripts/testing/compare-component-spacing.py",
    "proof-component-spacing-drawbot.py": ROOT / "scripts/testing/proof-component-spacing-drawbot.py",
}
PERSONAL_PATH = re.compile(rb"(?:/Users/|/home/|C:\\Users\\)")

GUIDE = """# RoboFont Tools for teammates

## Install the palette

Unzip this archive, then double-click `RoboFontTools.roboFontExt` and accept
RoboFont's installation prompt. Restart RoboFont or reload extensions. Choose
**Extensions → RoboFont Tools** to open the palette. The extension has been
validated with RoboFont 4.6. No Python package installation is needed for the
palette.

The palette contains Measure Selected Points, Contour Probe, Distribute Points,
and Select Between. For Select Between, select two points on one contour and
click **Select Points**. A second click switches to the other route on a closed
contour. Off-curve handles are included.

## Use the standalone scripts

The `scripts/` folder is separate from the palette. None of these scripts is
installed with the extension or appears in its menu.

* `rename-font-package.py`: edit `SOURCE`, `OLD`, and `NEW` at the top before
  running. Requires Python with `fontTools`. It copies the source folder and
  changes only the copy.
* `compare-component-spacing.py`: pass a folder containing UFOs as the first
  argument, or set `ROOT_PATH` to run it in DrawBot. Requires `fontParts` or
  `defcon`. It reads UFOs and prints a TSV table.
* `proof-component-spacing-drawbot.py`: pass a UFO folder or set `ROOT_PATH` in
  DrawBot. Requires DrawBot and `fontParts` or `defcon`. It reads UFOs and writes
  a PDF proof.

The project-specific Amstelvar editing scripts, xTools experiments, other
extensions, tests, and development files are deliberately absent from this
package.
"""


def add_bytes(archive: ZipFile, name: str, data: bytes) -> None:
    info = ZipInfo(f"{TOP}/{name}", date_time=(2026, 1, 1, 0, 0, 0))
    info.compress_type = ZIP_DEFLATED
    info.external_attr = 0o644 << 16
    archive.writestr(info, data)


def collect_files() -> dict[str, bytes]:
    if not BUNDLE.is_dir():
        raise FileNotFoundError(BUNDLE)
    files: dict[str, bytes] = {}
    for source in BUNDLE.rglob("*"):
        if not source.is_file():
            continue
        if source.name == "info.plist" and source.parent == BUNDLE:
            pass
        elif source.suffix == ".py" and "__pycache__" not in source.parts:
            pass
        else:
            continue
        relative = source.relative_to(BUNDLE).as_posix()
        files[f"RoboFontTools.roboFontExt/{relative}"] = source.read_bytes()

    plist = plistlib.loads(files["RoboFontTools.roboFontExt/info.plist"])
    if plist["name"] != "RoboFont Tools":
        raise ValueError("Unexpected extension metadata")
    if "RoboFontTools.roboFontExt/lib/startup.py" not in files:
        raise ValueError("Extension menu entry point is missing")

    for name, source in SCRIPTS.items():
        files[f"scripts/{name}"] = source.read_bytes()
    files["README.md"] = GUIDE.encode("utf-8")

    for name, data in files.items():
        if name.endswith(".py") and PERSONAL_PATH.search(data):
            raise ValueError(f"Personal absolute path in {name}")
    return files


def build(destination: Path) -> Path:
    files = collect_files()
    destination.mkdir(parents=True, exist_ok=True)
    archive_path = destination / ARCHIVE_NAME
    with ZipFile(archive_path, "w") as archive:
        for name, data in sorted(files.items()):
            add_bytes(archive, name, data)
    with ZipFile(archive_path) as archive:
        if archive.testzip() is not None:
            raise ValueError("Archive integrity check failed")
    return archive_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output_folder", type=Path)
    args = parser.parse_args()
    print(build(args.output_folder))
