from fontTools.ttLib import TTFont
from pathlib import Path
import shutil

# ----------------------------------------
# SETTINGS
# ----------------------------------------

SOURCE = Path("Font_Files")

OLD = "Excalibur"
NEW = "Larian_Test"

# Creates Font_Files_RENAMED next to Font_Files
OUTPUT = SOURCE.parent / f"{SOURCE.name}_RENAMED"


# ----------------------------------------
# 1. COPY EVERYTHING
# ----------------------------------------

if OUTPUT.exists():
    raise FileExistsError(
        f"{OUTPUT} already exists.\n"
        "Delete it or rename it before running the script."
    )

shutil.copytree(SOURCE, OUTPUT)

print(f"\nCopied:")
print(f"  {SOURCE}")
print(f"→ {OUTPUT}")


# ----------------------------------------
# 2. CHANGE INTERNAL FONT NAMES
# ----------------------------------------

font_extensions = {".otf", ".ttf", ".woff2"}

for path in OUTPUT.rglob("*"):

    if not path.is_file():
        continue

    if path.suffix.lower() not in font_extensions:
        continue

    print(f"\nFONT: {path.relative_to(OUTPUT)}")

    try:
        font = TTFont(path)

        if "name" not in font:
            print("  No name table — skipped")
            font.close()
            continue

        changed = False

        for record in font["name"].names:
            try:
                old_text = record.toUnicode()
            except Exception:
                continue

            if OLD not in old_text:
                continue

            new_text = old_text.replace(OLD, NEW)

            print(
                f"  ID {record.nameID}: "
                f"{old_text} -> {new_text}"
            )

            try:
                record.string = new_text.encode(record.getEncoding())
            except (UnicodeEncodeError, LookupError):
                print("    WARNING: could not encode this record")
                continue

            changed = True

        if changed:
            font.save(path)
            print("  SAVED")
        else:
            print("  No internal occurrences found")

        font.close()

    except Exception as e:
        print(f"  ERROR: {e}")


# ----------------------------------------
# 3. RENAME FILES
# ----------------------------------------

# deepest paths first
all_paths = sorted(
    OUTPUT.rglob("*"),
    key=lambda p: len(p.parts),
    reverse=True
)

for path in all_paths:

    if OLD not in path.name:
        continue

    new_name = path.name.replace(OLD, NEW)
    new_path = path.with_name(new_name)

    print(f"RENAME: {path.name} -> {new_name}")
    path.rename(new_path)


# ----------------------------------------
# DONE
# ----------------------------------------

print("\n----------------------------------------")
print("DONE")
print("----------------------------------------")
print(f"Originals: {SOURCE}")
print(f"Renamed:   {OUTPUT}")