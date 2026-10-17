# menuTitle: rename anchor in all sources

"""Rename one anchor in one glyph across the Amstelvar designspace sources.

Run this script in RoboFont. Edit the settings below first, run once with
DRY_RUN = True, check the report, and then set DRY_RUN = False to save.
"""

from pathlib import Path

from fontTools.designspaceLib import DesignSpaceDocument
from mojo.roboFont import OpenFont


# settings -------------------------------------------------------------------

GLYPH_NAME = "x"
OLD_ANCHOR_NAME = "cy_descender"
NEW_ANCHOR_NAME = "cy_descender_corner"

# Leave this as None when OLD_ANCHOR_NAME is unique. If the glyph contains
# duplicate names, set this to the zero-based position of the intended anchor
# in glyph.anchors. The dry-run report lists candidate indices and positions.
ANCHOR_INDEX = None

# Include both to change every Roman and Italic source. Remove one path if the
# rename should apply to only one designspace.
REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
DESIGNSPACE_PATHS = [
    # REPOSITORY_ROOT / "Sources/Roman/AmstelvarA2-Roman.designspace",
    REPOSITORY_ROOT / "Sources/Italic/AmstelvarA2-Italic.designspace",
]

# The script makes no changes while this is True.
DRY_RUN = True


def get_source_paths(designspace_paths):
    """Return unique, resolved UFO paths in designspace order."""
    paths = []
    seen = set()

    for designspace_path in designspace_paths:
        document = DesignSpaceDocument.fromfile(designspace_path)
        for source in document.sources:
            path = source.path
            if path is None and source.filename:
                path = designspace_path.parent / source.filename
            if path is None:
                raise ValueError(
                    f"Unresolved source {source.name!r} in {designspace_path}"
                )
            path = Path(path).resolve()
            if path not in seen:
                seen.add(path)
                paths.append(path)

    return paths


def inspect_source(source_path):
    """Classify a source without modifying it."""
    if not source_path.exists():
        return "error", "UFO does not exist"

    font = OpenFont(str(source_path), showInterface=False)
    if font is None:
        return "error", "UFO could not be opened"

    try:
        if GLYPH_NAME not in font:
            return "error", f"glyph {GLYPH_NAME!r} is missing"

        anchors = list(font[GLYPH_NAME].anchors)
        anchor_names = [anchor.name for anchor in anchors]

        if ANCHOR_INDEX is not None:
            if ANCHOR_INDEX >= len(anchors):
                return "error", (
                    f"anchor index {ANCHOR_INDEX} is out of range; "
                    f"glyph has {len(anchors)} anchor(s)"
                )
            target = anchors[ANCHOR_INDEX]
            if target.name == NEW_ANCHOR_NAME:
                return "done", "already renamed"
            if target.name != OLD_ANCHOR_NAME:
                return "error", (
                    f"anchor {ANCHOR_INDEX} is {target.name!r} at "
                    f"({target.x:g}, {target.y:g}); expected {OLD_ANCHOR_NAME!r}"
                )
            if any(
                anchor.name == NEW_ANCHOR_NAME
                for index, anchor in enumerate(anchors)
                if index != ANCHOR_INDEX
            ):
                return "error", f"destination anchor {NEW_ANCHOR_NAME!r} already exists"
            return "ready", "will rename"

        old_count = anchor_names.count(OLD_ANCHOR_NAME)
        new_count = anchor_names.count(NEW_ANCHOR_NAME)

        if old_count == 1 and new_count == 0:
            return "ready", "will rename"
        if old_count == 0 and new_count == 1:
            return "done", "already renamed"
        if old_count == 0 and new_count == 0:
            return "error", (
                f"neither {OLD_ANCHOR_NAME!r} nor {NEW_ANCHOR_NAME!r} exists"
            )
        if old_count and new_count:
            return "error", f"destination anchor {NEW_ANCHOR_NAME!r} already exists"
        candidates = [
            f"{index} at ({anchor.x:g}, {anchor.y:g})"
            for index, anchor in enumerate(anchors)
            if anchor.name == OLD_ANCHOR_NAME
        ]
        return "error", (
            f"found {old_count} anchors named {OLD_ANCHOR_NAME!r}; "
            f"set ANCHOR_INDEX to one of: {', '.join(candidates)}"
        )
    finally:
        font.close()


def rename_in_source(source_path):
    font = OpenFont(str(source_path), showInterface=False)
    if font is None:
        raise RuntimeError("UFO could not be opened")

    try:
        glyph = font[GLYPH_NAME]
        glyph_anchors = list(glyph.anchors)
        if ANCHOR_INDEX is None:
            matches = [
                anchor for anchor in glyph_anchors
                if anchor.name == OLD_ANCHOR_NAME
            ]
            if len(matches) != 1:
                raise RuntimeError(
                    f"expected one {OLD_ANCHOR_NAME!r} anchor; found {len(matches)}"
                )
            target = matches[0]
        else:
            if ANCHOR_INDEX >= len(glyph_anchors):
                raise RuntimeError(f"anchor index {ANCHOR_INDEX} is out of range")
            target = glyph_anchors[ANCHOR_INDEX]
            if target.name != OLD_ANCHOR_NAME:
                raise RuntimeError(
                    f"anchor {ANCHOR_INDEX} is {target.name!r}; "
                    f"expected {OLD_ANCHOR_NAME!r}"
                )

        if any(
            anchor is not target and anchor.name == NEW_ANCHOR_NAME
            for anchor in glyph_anchors
        ):
            raise RuntimeError(f"destination anchor {NEW_ANCHOR_NAME!r} exists")

        target.name = NEW_ANCHOR_NAME
        glyph.changed()
        font.save()
    finally:
        font.close()


def main():
    if not GLYPH_NAME or not OLD_ANCHOR_NAME or not NEW_ANCHOR_NAME:
        print("Blocked: glyph and anchor names must not be empty.")
        return
    if OLD_ANCHOR_NAME == NEW_ANCHOR_NAME:
        print("Blocked: the old and new anchor names are identical.")
        return
    if (
        ANCHOR_INDEX is not None
        and (not isinstance(ANCHOR_INDEX, int) or ANCHOR_INDEX < 0)
    ):
        print("Blocked: ANCHOR_INDEX must be None or a non-negative integer.")
        return

    try:
        source_paths = get_source_paths(DESIGNSPACE_PATHS)
    except Exception as error:
        print(f"Blocked while reading designspaces: {error}")
        return

    ready = []
    already_done = []
    errors = []

    print(
        f"Preflighting {len(source_paths)} sources: glyph {GLYPH_NAME!r}, "
        f"anchor {OLD_ANCHOR_NAME!r} -> {NEW_ANCHOR_NAME!r}; "
        f"index {ANCHOR_INDEX!r}"
    )
    for source_path in source_paths:
        try:
            status, message = inspect_source(source_path)
        except Exception as error:
            status, message = "error", str(error)

        if status == "ready":
            ready.append(source_path)
        elif status == "done":
            already_done.append(source_path)
        else:
            errors.append((source_path, message))

    print(
        f"Ready: {len(ready)}; already renamed: {len(already_done)}; "
        f"errors: {len(errors)}."
    )

    if errors:
        print("Blocked: no sources were modified. Fix these issues first:")
        for source_path, message in errors:
            print(f"  {source_path.name}: {message}")
        return

    if DRY_RUN:
        print("Dry run complete; no sources were modified.")
        print("Set DRY_RUN = False and run again to apply the rename.")
        return

    failures = []
    for source_path in ready:
        try:
            rename_in_source(source_path)
            print(f"Renamed: {source_path.name}")
        except Exception as error:
            failures.append((source_path, str(error)))
            print(f"FAILED: {source_path.name}: {error}")

    print(
        f"Finished: renamed {len(ready) - len(failures)} source(s); "
        f"already renamed {len(already_done)}; failed {len(failures)}."
    )


if __name__ == "__main__":
    main()
