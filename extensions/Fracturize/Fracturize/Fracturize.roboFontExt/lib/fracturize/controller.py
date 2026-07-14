from __future__ import annotations

import os
import re
import shutil
import math
from pathlib import Path

from .live_project import (
    LiveFractureProject,
    LiveProjectError,
    LiveProjectIntegrityError,
)
from .robofont_adapter import collect_glyph_names
from .geometry import UnsupportedOutlineError


class FracturizeController:
    """UI-independent orchestration for the RoboFont panel and tests."""

    def __init__(self, environment):
        self.environment = environment
        self.project = None
        self.preview_result = None
        self.preview_glyph_name = None
        self.cancel_requested = False
        self._last_refresh_integrity_error = None

    @staticmethod
    def project_path_from_dialog_result(result):
        """Normalize Vanilla's save-panel result without assuming sync behavior."""

        if not result:
            return None
        if isinstance(result, (list, tuple)):
            if not result:
                return None
            result = result[0]
        if hasattr(result, "path") and callable(result.path):
            result = result.path()
        path = Path(str(result)).expanduser()
        name = path.name
        if name.endswith(".fracturize.json"):
            return path.resolve()
        if path.suffix.lower() == ".json":
            path = path.with_name(path.stem + ".fracturize.json")
        else:
            path = path.with_name(path.name + ".fracturize.json")
        return path.resolve()

    @staticmethod
    def project_name_from_path(path):
        name = Path(path).name
        suffix = ".fracturize.json"
        return name[:-len(suffix)] if name.endswith(suffix) else Path(path).stem

    @staticmethod
    def working_font_paths(project_path, project_name):
        safe_name = re.sub(r"[^A-Za-z0-9._-]+", "-", project_name).strip("-._")
        if not safe_name:
            raise LiveProjectError("project name must contain a usable filename character")
        folder = Path(project_path).parent
        return {
            "intact": folder / f"{safe_name}-Intact.ufo",
            "eroded": folder / f"{safe_name}-Eroded.ufo",
        }

    @staticmethod
    def _emit(logger, event, **fields):
        if logger is not None:
            logger(event, **fields)

    @staticmethod
    def validate_source_font(source):
        if source is None:
            raise LiveProjectError("Open and select a saved source UFO in RoboFont first")
        source_path = getattr(source, "path", None)
        if not source_path:
            raise LiveProjectError("The current source font is unsaved. Save it as a UFO first.")
        source_path = Path(str(source_path)).resolve()
        if source_path.suffix.lower() != ".ufo" or not source_path.is_dir():
            raise LiveProjectError(f"The current source is not a readable saved UFO: {source_path}")
        return source_path

    def create_project(
        self,
        path,
        *,
        project_name,
        project_seed,
        complexity=50,
        rock_edge_detail=50,
        rock_edge_roughness=50,
        logger=None,
    ):
        path = Path(path).resolve()
        source = self.environment.current_font()
        source_path = self.validate_source_font(source)
        self._emit(logger, "current_source", path=str(source_path))
        destination = path.parent
        if not destination.exists() or not destination.is_dir():
            raise LiveProjectError(f"project destination does not exist: {destination}")
        if not os.access(destination, os.W_OK):
            raise LiveProjectError(f"project destination is not writable: {destination}")
        working_paths = self.working_font_paths(path, project_name)
        targets = (path, working_paths["intact"], working_paths["eroded"])
        conflicts = [target for target in targets if target.exists()]
        if conflicts:
            raise LiveProjectError(
                "project creation refuses existing destination(s): "
                + ", ".join(str(item) for item in conflicts)
            )
        self._emit(
            logger,
            "destination_paths",
            project=str(path),
            intact=str(working_paths["intact"]),
            eroded=str(working_paths["eroded"]),
        )
        intact = eroded = None
        created_paths = []
        try:
            base_style = source.info.styleName or "Regular"
            for role, label in (("intact", "Fracture Intact"), ("eroded", "Fracture Eroded")):
                target = working_paths[role]
                self._emit(logger, "source_duplication_start", role=role, path=str(target))
                self.environment.write_working_font_copy(
                    source,
                    target,
                    style_name=f"{base_style} {label}",
                )
                created_paths.append(target)
                self._emit(logger, "source_duplication_end", role=role, path=str(target))

            self._emit(logger, "robofont_open_start", role="intact", path=str(working_paths["intact"]))
            intact = self.environment.open_font(working_paths["intact"])
            self._emit(logger, "robofont_open_end", role="intact", path=str(working_paths["intact"]))
            self._emit(logger, "robofont_open_start", role="eroded", path=str(working_paths["eroded"]))
            eroded = self.environment.open_font(working_paths["eroded"])
            self._emit(logger, "robofont_open_end", role="eroded", path=str(working_paths["eroded"]))
            if intact is None or eroded is None:
                raise LiveProjectError("RoboFont did not return both opened working fonts")

            self._emit(logger, "project_json_write_start", path=str(path))
            project = LiveFractureProject.create(
                path,
                source,
                intact,
                eroded,
                project_name=project_name,
                project_seed=project_seed,
                complexity=complexity,
                rock_edge_detail=rock_edge_detail,
                rock_edge_roughness=rock_edge_roughness,
            )
            created_paths.append(path)
            # Persist the live-font identity assigned by project creation.
            self.environment.save_font(intact)
            self.environment.save_font(eroded)
            project.refresh_paths()
            self._emit(logger, "project_json_write_end", path=str(path))

            self._emit(logger, "controller_binding_start", project=str(path))
            project.attach_fonts(self.environment.all_fonts())
            if not project.fonts_available:
                raise LiveProjectError("created fonts could not be bound to the live project")
            self.project = project
            self._emit(logger, "controller_binding_end", project=str(path))
        except Exception:
            for font in (eroded, intact):
                if font is not None and hasattr(font, "close"):
                    font.close(save=False)
            data_directory = path.parent / f"{path.stem}-data"
            if data_directory.exists():
                shutil.rmtree(data_directory)
            for created_path in reversed(created_paths):
                if created_path.is_dir():
                    shutil.rmtree(created_path)
                elif created_path.exists():
                    created_path.unlink()
            self.project = None
            raise
        return self.project

    @staticmethod
    def open_project_path_from_dialog_result(result):
        if not result:
            return None
        if isinstance(result, (list, tuple)):
            if not result:
                return None
            result = result[0]
        if hasattr(result, "path") and callable(result.path):
            result = result.path()
        return Path(str(result)).expanduser().resolve()

    def open_project(self, path, *, logger=None):
        path = Path(path).expanduser().resolve()
        self._emit(logger, "selected_project_path", path=str(path))
        self._emit(logger, "project_validation_start", path=str(path))
        project = LiveFractureProject.open(path)
        self._emit(
            logger,
            "project_validation_end",
            path=str(path),
            format_version=project.data["formatVersion"],
            processed_count=len(project.data["processedGlyphs"]),
        )
        self._emit(logger, "font_resolution_start", path=str(path))
        available = self.environment.ensure_project_fonts_open(project, logger=logger)
        self._emit(logger, "font_resolution_end", available=available)
        if not available:
            missing = [
                role
                for role in ("source", "intact", "eroded")
                if getattr(project, f"{role}_font") is None
            ]
            raise LiveProjectError(
                "project fonts could not be opened or bound: " + ", ".join(missing)
            )
        self._emit(logger, "controller_assignment_start", path=str(path))
        self.project = project
        self._last_refresh_integrity_error = None
        self._emit(logger, "controller_assignment_end", path=str(path))
        return project

    def selected_names(self, direct_text="", *, include_current=True, include_selection=True):
        source = self.project.source_font if self.project else self.environment.current_font()
        current = self.environment.current_glyph_name() if include_current else None
        selected = (
            self.environment.selected_glyph_names(source)
            if include_selection and source is not None
            else ()
        )
        return collect_glyph_names(current, selected, direct_text)

    def resolve_glyph_names(self, mode, direct_text=""):
        source = self.project.source_font if self.project else self.environment.current_font()
        if mode == "current":
            name = self.environment.current_glyph_name()
            return (name,) if name else ()
        if mode == "selected":
            if source is None:
                return ()
            return tuple(dict.fromkeys(self.environment.selected_glyph_names(source)))
        if mode == "manual":
            return tuple(dict.fromkeys(direct_text.split()))
        if mode == "all":
            if source is None:
                return ()
            available = tuple(source.keys())
            available_set = set(available)
            ordered = [name for name in (source.glyphOrder or ()) if name in available_set]
            seen = set(ordered)
            ordered.extend(name for name in available if name not in seen)
            return tuple(dict.fromkeys(ordered))
        raise LiveProjectError(f"unknown glyph-resolution mode: {mode}")

    def refresh_project_fonts(self):
        """Bind open documents and deduplicate an unchanged integrity error."""

        if self.project is None:
            return {"available": False, "error": None, "report": False}
        fonts = list(self.environment.all_fonts())
        registered_paths = {
            Path(str(font.path)).resolve()
            for font in fonts
            if getattr(font, "path", None)
        }
        for font in (
            self.project.source_font,
            self.project.intact_font,
            self.project.eroded_font,
        ):
            path = getattr(font, "path", None) if font is not None else None
            if (
                font is not None
                and font not in fonts
                and (not path or Path(str(path)).resolve() not in registered_paths)
            ):
                fonts.append(font)
                if path:
                    registered_paths.add(Path(str(path)).resolve())
        try:
            available = self.project.attach_fonts(fonts)
        except LiveProjectIntegrityError as error:
            text = str(error)
            report = text != self._last_refresh_integrity_error
            self._last_refresh_integrity_error = text
            return {"available": False, "error": text, "report": report}
        self._last_refresh_integrity_error = None
        return {"available": available, "error": None, "report": False}

    def update_settings(self, **changes):
        if self.project is None:
            raise LiveProjectError("create or open a project first")
        self.project.update_settings(**changes)

    @staticmethod
    def _normalize_topology_slider(raw_value, label):
        if isinstance(raw_value, bool) or not isinstance(raw_value, (int, float)):
            raise LiveProjectError(f"{label} slider value must be a finite number")
        if not math.isfinite(raw_value):
            raise LiveProjectError(f"{label} slider value must be finite")
        normalized = int(round(raw_value))
        if not 0 <= normalized <= 100:
            raise LiveProjectError(f"{label} slider value must be in the range 0..100")
        return normalized

    def _set_topology_slider(self, setting_name, result_key, raw_value, *, glyph_name=None):
        if self.project is None:
            raise LiveProjectError("create or open a project first")
        label = setting_name.replace("_", " ")
        normalized = self._normalize_topology_slider(raw_value, label)
        previous = getattr(self.project.settings, setting_name)
        self.project.update_settings(**{setting_name: normalized})
        status = self.project.glyph_status(glyph_name) if glyph_name else None
        return {
            "previous": previous,
            result_key: normalized,
            "glyphStatus": status,
            "topologyStale": status == "topology-outdated",
        }

    def set_complexity_from_slider(self, raw_value, *, glyph_name=None):
        """Normalize one UI slider value and persist it as project complexity."""

        return self._set_topology_slider(
            "complexity",
            "complexity",
            raw_value,
            glyph_name=glyph_name,
        )

    def set_rock_edge_detail_from_slider(self, raw_value, *, glyph_name=None):
        """Normalize and persist the topology-only micro-edge control."""

        return self._set_topology_slider(
            "rock_edge_detail",
            "rockEdgeDetail",
            raw_value,
            glyph_name=glyph_name,
        )

    def set_rock_edge_roughness_from_slider(self, raw_value, *, glyph_name=None):
        """Normalize and persist the topology-only edge displacement control."""

        return self._set_topology_slider(
            "rock_edge_roughness",
            "rockEdgeRoughness",
            raw_value,
            glyph_name=glyph_name,
        )

    def preview(self, glyph_name, *, regenerate_topology=False, decompose_components=False):
        if self.project is None:
            raise LiveProjectError("create or open a project first")
        record = self.project.data["processedGlyphs"].get(glyph_name)
        if record is not None and not regenerate_topology:
            result = self.project.preview_motion(glyph_name)
        else:
            result = self.project.preview_new_topology(
                glyph_name,
                decompose_components=decompose_components,
            )
        self.preview_result = result
        self.preview_glyph_name = glyph_name
        return result

    def request_cancel(self):
        self.cancel_requested = True

    def component_glyph_names(self, glyph_names):
        """Return source component glyphs in batch order, without duplicates."""

        if self.project is None:
            raise LiveProjectError("create or open a project first")
        found = []
        seen = set()
        for glyph_name in glyph_names:
            if glyph_name in seen:
                continue
            seen.add(glyph_name)
            if self.project.glyph_has_components(glyph_name):
                found.append(glyph_name)
        return tuple(found)

    def process_names(
        self,
        glyph_names,
        *,
        action="generate",
        decompose_components=False,
        resolve_edited=None,
        confirm_topology_replacement=None,
        progress=None,
        item_complete=None,
    ):
        if self.project is None:
            raise LiveProjectError("create or open a project first")
        glyph_names = tuple(glyph_names)
        self.cancel_requested = False
        completed = []
        skipped = []
        rejected = []
        failed = []
        topology_replacement_accepted = None

        def notify_complete(index, glyph_name):
            if item_complete:
                item_complete(
                    index + 1,
                    len(glyph_names),
                    glyph_name,
                    {
                        "completed": tuple(completed),
                        "skipped": tuple(skipped),
                        "rejected": tuple(rejected),
                        "failed": tuple(failed),
                    },
                )

        for index, glyph_name in enumerate(glyph_names):
            if self.cancel_requested:
                break
            if progress:
                progress(index, len(glyph_names), glyph_name)
            try:
                edited = self.project.edited_roles(glyph_name)
                replace_edited = False
                if edited:
                    choice = resolve_edited(glyph_name, edited) if resolve_edited else "cancel"
                    if choice == "keep":
                        skipped.append((glyph_name, "kept edited glyph"))
                        notify_complete(index, glyph_name)
                        continue
                    if choice != "replace":
                        self.cancel_requested = True
                        break
                    replace_edited = True

                if action == "motion":
                    self.project.regenerate_motion(
                        glyph_name,
                        replace_edited=replace_edited,
                    )
                elif action in {"topology", "replace-stale"}:
                    self.project.regenerate_topology(
                        glyph_name,
                        replace_edited=replace_edited,
                    )
                elif action == "generate":
                    has_components = self.project.glyph_has_components(glyph_name)
                    if glyph_name in self.project.data["processedGlyphs"]:
                        if self.project.glyph_status(glyph_name) != "topology-outdated":
                            skipped.append((glyph_name, "already processed"))
                            notify_complete(index, glyph_name)
                            continue
                        if topology_replacement_accepted is None:
                            topology_replacement_accepted = bool(
                                confirm_topology_replacement(glyph_name)
                                if confirm_topology_replacement
                                else False
                            )
                        if not topology_replacement_accepted:
                            skipped.append((glyph_name, "topology regeneration not confirmed"))
                            notify_complete(index, glyph_name)
                            continue
                        self.project.regenerate_topology(
                            glyph_name,
                            replace_edited=replace_edited,
                        )
                        completed.append(glyph_name)
                        notify_complete(index, glyph_name)
                        continue
                    decomposed = bool(has_components)
                    result = self.project.preview_new_topology(glyph_name)
                    self.project.process_result(
                        result,
                        components_decomposed=decomposed,
                        replace_edited=replace_edited,
                    )
                else:
                    raise LiveProjectError(f"unknown processing action: {action}")
                completed.append(glyph_name)
                notify_complete(index, glyph_name)
            except UnsupportedOutlineError as error:
                self.project.record_failure(glyph_name, error)
                rejected.append((glyph_name, str(error)))
                notify_complete(index, glyph_name)
            except Exception as error:
                self.project.record_failure(glyph_name, error)
                failed.append((glyph_name, str(error)))
                notify_complete(index, glyph_name)
        return {
            "completed": completed,
            "skipped": skipped,
            "rejected": rejected,
            "failed": failed,
            "cancelled": self.cancel_requested,
        }

    def validate(self):
        if self.project is None:
            raise LiveProjectError("create or open a project first")
        return self.project.validate()
