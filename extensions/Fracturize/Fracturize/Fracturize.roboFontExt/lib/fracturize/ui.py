from __future__ import annotations

import json
import traceback

from AppKit import NSColor
from Foundation import NSDate, NSRunLoop
from PyObjCTools.AppHelper import callAfter, callLater
from mojo.events import addObserver, removeObserver
from mojo.glyphPreview import GlyphPreview
from vanilla import (
    Button,
    CheckBox,
    EditText,
    FloatingWindow,
    Slider,
    TextBox,
    TextEditor,
)
from vanilla.dialogs import ask, askYesNo, getFile, message, putFile

from .controller import FracturizeController
from .geometry import interpolate_contours
from .model import MasterGlyph
from .robofont_adapter import RoboFontEnvironment, master_to_preview_glyph

# Long enough that a continuous slider drag never regenerates mid-gesture,
# short enough to feel immediate once the drag settles.
TOPOLOGY_SLIDER_DEBOUNCE_SECONDS = 0.25


class FracturizeWindowController:
    observer_events = (
        "currentGlyphChanged",
        "fontDidSave",
        "fontDidClose",
    )

    def __init__(self):
        self.environment = RoboFontEnvironment()
        self.controller = FracturizeController(self.environment)
        self._batch_queue = []
        self._batch_action = None
        self._batch_decompose_components = False
        self._batch_cancelled = False
        self._batch_integrity_error_shown = False
        self._batch_running = False
        self._closed = False
        self._topology_debounce_token = 0
        self._topology_compatibility_message = ""
        self._build_window()
        for event in self.observer_events:
            addObserver(self, "roboFontEvent", event)
        self.w.bind("close", self.windowCloseCallback)
        self.w.open()
        self.refresh_ui()

    def _build_window(self):
        self.w = FloatingWindow(
            (980, 900),
            "Fracturize",
            minSize=(900, 780),
        )
        self.w.createProject = Button((15, 12, 110, 24), "Create Project", callback=self.createProjectCallback)
        self.w.openProject = Button((132, 12, 105, 24), "Open Project", callback=self.openProjectCallback)
        self.w.projectStatus = TextBox((250, 15, -15, 20), "No project")
        self.w.sourceIndicator = TextBox((15, 44, -15, 18), "Source: —")
        self.w.intactIndicator = TextBox((15, 64, -15, 18), "Intact: —")
        self.w.erodedIndicator = TextBox((15, 84, -15, 18), "Eroded: —")

        self.w.useCurrent = CheckBox((15, 112, 110, 20), "Current glyph (0)", value=True, callback=self.selectionModeCallback)
        self.w.useSelection = CheckBox((130, 112, 140, 20), "Selected glyphs (0)", value=False, callback=self.selectionModeCallback)
        self.w.useManual = CheckBox((275, 112, 145, 20), "Manual glyph list (0)", value=False, callback=self.selectionModeCallback)
        self.w.useAll = CheckBox((425, 112, 125, 20), "All glyphs (0)", value=False, callback=self.selectionModeCallback)
        self.w.glyphNames = EditText((555, 108, 190, 24), placeholder="A B C", callback=self.manualNamesCallback)
        self.w.glyphStatus = TextBox((755, 112, -15, 20), "Glyph status: —")

        self.w.controlsTitle = TextBox((15, 146, 430, 20), "Fracture and motion controls")
        self.w.seedLabel = TextBox((15, 174, 160, 18), "Seed override")
        self.w.seed = EditText((180, 170, 255, 24), callback=self.seedCallback)

        self._add_slider("complexity", "Fracture Complexity", 200, 0, 100, 50, self.complexityCallback)
        self._add_slider("edgeDetail", "Rock Edge Detail", 230, 0, 100, 50, self.rockEdgeDetailCallback)
        self._add_slider("edgeRoughness", "Rock Edge Roughness", 260, 0, 100, 50, self.rockEdgeRoughnessCallback)
        self._add_slider("crumble", "Overall Crumble Amount", 290, 0, 100, 55, self.motionCallback)
        self._add_slider("largeMove", "Large Fragment Movement", 320, 0, 100, 18, self.motionCallback)
        self._add_slider("mediumMove", "Medium Fragment Movement", 350, 0, 150, 55, self.motionCallback)
        self._add_slider("smallMove", "Small Fragment Movement", 380, 0, 200, 100, self.motionCallback)
        self._add_slider("direction", "Movement Direction", 410, -180, 180, -72, self.motionCallback)
        self._add_slider("spread", "Directional Spread", 440, 0, 90, 24, self.motionCallback)
        self._add_slider("baseline", "Baseline Retention", 470, 0, 100, 85, self.motionCallback)
        self._add_slider("downward", "Maximum Downward Drift", 500, 0, 80, 25, self.motionCallback)
        self._add_slider("cohesion", "Structural Cohesion", 530, 0, 100, 56, self.motionCallback)
        self._add_slider("rotation", "Rotation Amount", 560, 0, 30, 12, self.motionCallback)
        self.w.decomposeComponents = CheckBox(
            (15, 585, 320, 20),
            "Decompose components before processing",
            value=False,
        )

        self.w.previewTitle = TextBox((465, 146, -15, 20), "Exact matched-geometry preview")
        self.w.intactLabel = TextBox((465, 174, 145, 18), "Intact")
        self.w.middleLabel = TextBox((625, 174, 145, 18), "Interpolation 50%")
        self.w.erodedLabel = TextBox((785, 174, 145, 18), "Eroded")
        stroke = NSColor.systemRedColor()
        self.w.intactPreview = GlyphPreview((465, 195, 145, 235), contourStrokeColor=stroke)
        self.w.middlePreview = GlyphPreview((625, 195, 145, 235), contourStrokeColor=stroke)
        self.w.erodedPreview = GlyphPreview((785, 195, 145, 235), contourStrokeColor=stroke)
        self.w.interpolation = Slider((465, 440, 465, 20), minValue=0, maxValue=100, value=50, callback=self.interpolationCallback)
        self.w.boundaryOverlay = CheckBox((465, 470, 185, 20), "Fracture-boundary overlay", value=True, callback=self.overlayCallback)
        self.w.compatibility = TextBox((660, 472, 270, 18), "Compatibility: —")
        self.w.warningDisplay = TextEditor((465, 500, 465, 120), readOnly=True)

        self.w.generate = Button((15, 610, 90, 26), "Generate", callback=self.generateCallback)
        self.w.preview = Button((110, 610, 90, 26), "Preview", callback=self.previewCallback)
        self.w.motionOnly = Button((205, 610, 125, 26), "Regenerate Motion", callback=self.motionOnlyCallback)
        self.w.topology = Button((335, 610, 125, 26), "Regenerate Topology", callback=self.topologyCallback)
        self.w.validate = Button((15, 644, 95, 26), "Validate", callback=self.validateCallback)
        self.w.replaceStale = Button((116, 644, 145, 26), "Replace Stale Glyph", callback=self.replaceStaleCallback)
        self.w.cancel = Button((267, 644, 155, 26), "Cancel Batch", callback=self.cancelCallback)
        self.w.cancel.enable(False)
        self.w.log = TextEditor((15, 695, 430, -15), readOnly=True)
        self.w.batchStatus = TextEditor((465, 695, -15, -15), readOnly=True)
        self._set_batch_status(0, 0, "—", 0, 0, 0, 0)

    def _add_slider(self, name, label, y, minimum, maximum, value, callback):
        setattr(self.w, f"{name}Label", TextBox((15, y + 2, 165, 18), label))
        setattr(
            self.w,
            name,
            Slider((180, y, 205, 20), minValue=minimum, maxValue=maximum, value=value, callback=callback),
        )
        setattr(self.w, f"{name}Value", TextBox((392, y + 2, 45, 18), str(round(value, 2))))

    def _log(self, text):
        existing = self.w.log.get() or ""
        self.w.log.set(existing + ("\n" if existing else "") + str(text))

    def _label(self, font):
        if font is None:
            return "— (closed or unavailable)"
        info = font.info
        label = f"{info.familyName or 'Untitled'} {info.styleName or 'Regular'}"
        return label + (f" — {font.path}" if font.path else " — unsaved user document")

    def _selected_names(self):
        mode = self._active_mode()
        direct_text = self.w.glyphNames.get() if mode == "manual" else ""
        return self.controller.resolve_glyph_names(mode, direct_text)

    def _active_mode(self):
        for mode, control_name in (
            ("current", "useCurrent"),
            ("selected", "useSelection"),
            ("manual", "useManual"),
            ("all", "useAll"),
        ):
            if getattr(self.w, control_name).get():
                return mode
        self.w.useCurrent.set(True)
        return "current"

    def _update_selection_count(self):
        try:
            current_count = len(self.controller.resolve_glyph_names("current"))
            selected_count = len(self.controller.resolve_glyph_names("selected"))
            manual_count = len(
                self.controller.resolve_glyph_names("manual", self.w.glyphNames.get())
            )
            all_count = len(self.controller.resolve_glyph_names("all"))
        except Exception:
            current_count = selected_count = manual_count = all_count = 0
        self.w.useCurrent.setTitle(f"Current glyph ({current_count})")
        self.w.useSelection.setTitle(f"Selected glyphs ({selected_count})")
        self.w.useManual.setTitle(f"Manual glyph list ({manual_count})")
        self.w.useAll.setTitle(f"All glyphs ({all_count})")

    def selectionModeCallback(self, sender):
        controls = (
            self.w.useCurrent,
            self.w.useSelection,
            self.w.useManual,
            self.w.useAll,
        )
        if sender is not None:
            for control in controls:
                control.set(control is sender)
        self._update_selection_count()
        self.refresh_ui()
        self.previewCurrent(regenerate_topology=False)

    def manualNamesCallback(self, sender):
        self.selectionModeCallback(self.w.useManual)

    def _current_preview_name(self):
        names = self._selected_names()
        return names[0] if names else None

    def _load_settings(self):
        project = self.controller.project
        if project is None:
            return
        settings = project.settings
        values = {
            "complexity": settings.complexity,
            "edgeDetail": settings.rock_edge_detail,
            "edgeRoughness": settings.rock_edge_roughness,
            "crumble": settings.erosion_amount * 100,
            "largeMove": settings.large_fragment_movement_multiplier * 100,
            "mediumMove": settings.medium_fragment_movement_multiplier * 100,
            "smallMove": settings.small_fragment_movement_multiplier * 100,
            "direction": settings.movement_direction_degrees,
            "spread": settings.movement_spread_degrees,
            "baseline": settings.baseline_retention * 100,
            "downward": settings.maximum_downward_drift_em * 1000,
            "cohesion": (settings.minimum_scale - 0.5) * 200,
            "rotation": settings.maximum_rotation_degrees,
        }
        for name, value in values.items():
            getattr(self.w, name).set(value)
            getattr(self.w, f"{name}Value").set(str(round(value, 1)))
        self.w.seed.set(settings.glyph_seed_override or "")

    def refresh_ui(self):
        self._update_selection_count()
        project = self.controller.project
        if project is None:
            self.w.projectStatus.set("No project — current open font will be used as source")
            self.w.sourceIndicator.set("Source: " + self._label(self.environment.current_font()))
            return
        binding = self.controller.refresh_project_fonts()
        if binding["error"] and binding["report"]:
            self._log("Working-font integrity failure: " + binding["error"])
        if binding["error"]:
            state = "Stopped: working-font integrity failure"
        else:
            state = "Ready" if binding["available"] else "Stopped: source or working font is closed"
        self.w.projectStatus.set(
            f"{state} — v{project.data['generatorVersion']} — "
            f"{len(project.data['processedGlyphs'])} processed, "
            f"{len(project.data['failedGlyphs'])} failed"
        )
        self.w.sourceIndicator.set("Source: " + self._label(project.source_font))
        self.w.intactIndicator.set("Intact: " + self._label(project.intact_font))
        self.w.erodedIndicator.set("Eroded: " + self._label(project.eroded_font))
        name = self._current_preview_name()
        if name:
            self.w.glyphStatus.set(f"Glyph status: {name} — {project.glyph_status(name)}")

    def createProjectCallback(self, sender):
        self._structured_create_log("callback_entered")
        source = self.environment.current_font()
        self._structured_create_log(
            "current_source",
            path=str(getattr(source, "path", None)),
        )
        try:
            self.controller.validate_source_font(source)
        except Exception as error:
            self._report_creation_failure(error)
            return
        default_name = (source.info.familyName or "FracturizeProject").replace(" ", "")
        putFile(
            title="Create Fracturize Project",
            fileName=default_name + ".fracturize.json",
            fileTypes=["json"],
            parentWindow=self.w,
            resultCallback=self._createProjectDialogResult,
            cancelCallback=self._createProjectDialogCancelled,
        )

    def _createProjectDialogCancelled(self):
        self._structured_create_log("dialog_cancelled")

    def _createProjectDialogResult(self, result):
        self._structured_create_log("dialog_result_received", result=result)
        path = self.controller.project_path_from_dialog_result(result)
        if path is None:
            self._structured_create_log("dialog_cancelled")
            return
        project_name = self.controller.project_name_from_path(path)
        self._structured_create_log(
            "selection_resolved",
            path=str(path),
            project_name=project_name,
        )
        try:
            self.controller.create_project(
                path,
                project_name=project_name,
                project_seed=project_name,
                complexity=round(self.w.complexity.get()),
                rock_edge_detail=round(self.w.edgeDetail.get()),
                rock_edge_roughness=round(self.w.edgeRoughness.get()),
                logger=self._structured_create_log,
            )
            self._load_settings()
            self._log("Created project, wrote both working UFOs, and opened them in RoboFont.")
            self._structured_create_log("ui_refresh_start")
            self.refresh_ui()
            self._structured_create_log("ui_refresh_end")
        except Exception as error:
            self._report_creation_failure(error)

    def _structured_create_log(self, event, **fields):
        self._structured_log("create_project", event, **fields)

    def _report_creation_failure(self, error):
        self._report_project_failure(
            scope="create_project",
            title="Project creation failed",
            error=error,
        )

    def openProjectCallback(self, sender):
        self._structured_open_log("callback_entered")
        getFile(
            title="Open Fracturize Project",
            fileTypes=["json"],
            parentWindow=self.w,
            resultCallback=self._openProjectDialogResult,
            cancelCallback=self._openProjectDialogCancelled,
        )

    def _openProjectDialogCancelled(self):
        self._structured_open_log("dialog_cancelled")

    def _openProjectDialogResult(self, result):
        self._structured_open_log("dialog_result_received", result=result)
        path = self.controller.open_project_path_from_dialog_result(result)
        if path is None:
            self._structured_open_log("dialog_result_empty")
            message("Project open failed", "No project file was selected.", alertStyle="critical", parentWindow=self.w)
            return
        try:
            project = self.controller.open_project(path, logger=self._structured_open_log)
            self._load_settings()
            self._structured_open_log(
                "settings_restored",
                complexity=project.settings.complexity,
                rock_edge_detail=project.settings.rock_edge_detail,
                rock_edge_roughness=project.settings.rock_edge_roughness,
                processed_count=len(project.data["processedGlyphs"]),
            )
            self._log(f"Opened project: {project.path}")
            self._structured_open_log("ui_refresh_scheduled")
            callAfter(self._finishOpenProjectRefresh)
        except Exception as error:
            self._report_open_failure(error)

    def _finishOpenProjectRefresh(self):
        self._structured_open_log("ui_refresh_start")
        self.refresh_ui()
        self.previewCurrent(regenerate_topology=False)
        self._structured_open_log("ui_refresh_end", state=self.w.projectStatus.get())

    def _structured_open_log(self, event, **fields):
        self._structured_log("open_project", event, **fields)

    def _structured_log(self, scope, event, **fields):
        record = {"scope": scope, "event": event, **fields}
        line = "[Fracturize] " + json.dumps(record, default=str, sort_keys=True)
        print(line, flush=True)
        self._log(line)

    def _report_open_failure(self, error):
        self._report_project_failure(
            scope="open_project",
            title="Project open failed",
            error=error,
        )

    def _report_project_failure(self, *, scope, title, error):
        trace = traceback.format_exc()
        if trace.strip() == "NoneType: None":
            trace = "".join(traceback.format_exception(type(error), error, error.__traceback__))
        print(trace, flush=True)
        self._log(trace.rstrip())
        self._structured_log(
            scope,
            "failure",
            error_type=type(error).__name__,
            error=str(error),
        )
        message(
            title,
            str(error),
            alertStyle="critical",
            parentWindow=self.w,
        )

    def _motion_changes(self):
        return {
            "erosion_amount": self.w.crumble.get() / 100.0,
            "large_fragment_movement_multiplier": self.w.largeMove.get() / 100.0,
            "medium_fragment_movement_multiplier": self.w.mediumMove.get() / 100.0,
            "small_fragment_movement_multiplier": self.w.smallMove.get() / 100.0,
            "movement_direction_degrees": self.w.direction.get(),
            "movement_spread_degrees": self.w.spread.get(),
            "baseline_retention": self.w.baseline.get() / 100.0,
            "maximum_downward_drift_em": self.w.downward.get() / 1000.0,
            "minimum_scale": 0.5 + self.w.cohesion.get() / 200.0,
            "maximum_rotation_degrees": self.w.rotation.get(),
        }

    def complexityCallback(self, sender):
        self.w.complexityValue.set(str(round(sender.get())))
        self._schedule_topology_update("Topology change: explicit regeneration required")

    def rockEdgeDetailCallback(self, sender):
        self.w.edgeDetailValue.set(str(round(sender.get())))
        self._schedule_topology_update(
            "Rock Edge Detail change: explicit regeneration required"
        )

    def rockEdgeRoughnessCallback(self, sender):
        self.w.edgeRoughnessValue.set(str(round(sender.get())))
        self._schedule_topology_update(
            "Rock Edge Roughness change: explicit regeneration required"
        )

    def _schedule_topology_update(self, compatibility_message):
        """Coalesce continuous slider drags into one deferred regeneration."""

        if not self.controller.project:
            return
        self._topology_compatibility_message = compatibility_message
        self._topology_debounce_token += 1
        callLater(
            TOPOLOGY_SLIDER_DEBOUNCE_SECONDS,
            self._apply_topology_sliders,
            self._topology_debounce_token,
        )

    def _apply_topology_sliders(self, token):
        if self._closed or token != self._topology_debounce_token:
            return
        if not self.controller.project:
            return
        if self._batch_running:
            callLater(
                TOPOLOGY_SLIDER_DEBOUNCE_SECONDS,
                self._apply_topology_sliders,
                token,
            )
            return
        try:
            glyph_name = self._current_preview_name()
            self.controller.set_complexity_from_slider(
                self.w.complexity.get(),
                glyph_name=glyph_name,
            )
            self.controller.set_rock_edge_detail_from_slider(
                self.w.edgeDetail.get(),
                glyph_name=glyph_name,
            )
            self.controller.set_rock_edge_roughness_from_slider(
                self.w.edgeRoughness.get(),
                glyph_name=glyph_name,
            )
            self.previewCurrent(regenerate_topology=True)
            self.w.compatibility.set(self._topology_compatibility_message)
            self.refresh_ui()
        except Exception as error:
            self._log(error)

    def seedCallback(self, sender):
        if self.controller.project:
            value = sender.get().strip() or None
            try:
                self.controller.update_settings(glyph_seed_override=value)
                self.w.compatibility.set("Topology seed change: explicit regeneration required")
                self.refresh_ui()
            except Exception as error:
                self._log(error)

    def motionCallback(self, sender):
        for name in (
            "crumble", "largeMove", "mediumMove", "smallMove", "direction",
            "spread", "baseline", "downward", "cohesion", "rotation",
        ):
            getattr(self.w, f"{name}Value").set(str(round(getattr(self.w, name).get(), 1)))
        if self.controller.project:
            try:
                self.controller.update_settings(**self._motion_changes())
                self.previewCurrent(regenerate_topology=False)
            except Exception as error:
                self._log(error)

    def previewCurrent(self, *, regenerate_topology=False):
        name = self._current_preview_name()
        if not name or not self.controller.project or not self.controller.project.fonts_available:
            return
        try:
            result = self.controller.preview(
                name,
                regenerate_topology=regenerate_topology,
            )
            self._set_preview(result)
        except Exception as error:
            self.w.compatibility.set("Preview unavailable")
            self.w.warningDisplay.set(str(error))

    def _set_preview(self, result):
        upm, descender = self._preview_metrics()
        self.w.intactPreview.setGlyph(
            master_to_preview_glyph(result.intact, units_per_em=upm, descender=descender)
        )
        self.w.erodedPreview.setGlyph(
            master_to_preview_glyph(result.eroded, units_per_em=upm, descender=descender)
        )
        self._set_middle_preview(result)
        self.w.compatibility.set(
            "Compatibility: PASS" if result.validation.compatible else "Compatibility: BLOCKED"
        )
        warnings = [f"{finding.level}: {finding.message}" for finding in result.validation.findings]
        warnings.extend(self.controller.project.sidebearing_warnings(result))
        self.w.warningDisplay.set("\n".join(warnings) if warnings else "No automated warnings. Visual judgment remains yours.")

    def _preview_metrics(self):
        source = self.controller.project.source_font
        upm = float(source.info.unitsPerEm or 1000)
        descender = float(source.info.descender or -0.25 * upm)
        return upm, descender

    def _set_middle_preview(self, result):
        position = self.w.interpolation.get() / 100.0
        contours = interpolate_contours(result.intact.contours, result.eroded.contours, position)
        master = MasterGlyph(
            result.glyph_name,
            result.intact.width,
            result.intact.unicodes,
            contours,
        )
        upm, descender = self._preview_metrics()
        self.w.middlePreview.setGlyph(
            master_to_preview_glyph(master, units_per_em=upm, descender=descender)
        )
        self.w.middleLabel.set(f"Interpolation {round(position * 100)}%")

    def interpolationCallback(self, sender):
        if self.controller.preview_result is not None:
            self._set_middle_preview(self.controller.preview_result)

    def overlayCallback(self, sender):
        color = NSColor.systemRedColor() if sender.get() else NSColor.clearColor()
        for name in ("intactPreview", "middlePreview", "erodedPreview"):
            getattr(self.w, name).getNSView().setContourStrokeColor_(color)

    def _resolve_edited(self, glyph_name, roles):
        return ask(
            "Generated glyph was edited",
            f"{glyph_name} differs in {', '.join(roles)}. No outline merge is available.",
            buttonTitles=[
                ("Cancel", "cancel"),
                ("Keep Existing Edited Glyph", "keep"),
                ("Replace Generated Glyph", "replace"),
            ],
            parentWindow=self.w,
        )

    def _confirm_topology_replacement(self, glyph_name):
        return bool(
            askYesNo(
                "Regenerate fracture topology?",
                f"{glyph_name} was generated with different fracture complexity, Rock Edge Detail, Rock Edge Roughness, or seed. Replace both generated outlines with the selected topology?",
                parentWindow=self.w,
            )
        )

    def _set_batch_status(
        self,
        position,
        total,
        glyph_name,
        completed,
        skipped,
        rejected,
        failed,
    ):
        self.w.batchStatus.set(
            f"Progress:\n{position} / {total}\n\n"
            f"Current:\n{glyph_name}\n\n"
            f"Completed: {completed}\n"
            f"Skipped: {skipped}\n"
            f"Rejected: {rejected}\n"
            f"Failed: {failed}"
        )

    def _set_batch_running(self, running):
        self._batch_running = running
        for name in (
            "generate",
            "preview",
            "openProject",
            "createProject",
            "motionOnly",
            "topology",
            "replaceStale",
            "decomposeComponents",
        ):
            getattr(self.w, name).enable(not running)
        self.w.cancel.enable(running)

    @staticmethod
    def _yield_ui_events():
        NSRunLoop.currentRunLoop().runUntilDate_(
            NSDate.dateWithTimeIntervalSinceNow_(0.001)
        )

    def _begin_batch(self, action):
        if not self.controller.project or not self.controller.project.fonts_available:
            message("Project fonts unavailable", "Open or relink source, intact, and eroded fonts first.", parentWindow=self.w)
            return
        binding = self.controller.refresh_project_fonts()
        if binding["error"]:
            if binding["report"]:
                self._log("Working-font integrity failure: " + binding["error"])
            message(
                "Working-font integrity failure",
                binding["error"],
                alertStyle="critical",
                parentWindow=self.w,
            )
            return
        names = list(self._selected_names())
        if not names:
            message("No glyphs selected", parentWindow=self.w)
            return
        decompose_components = bool(
            action == "generate" and self.w.decomposeComponents.get()
        )
        if decompose_components:
            component_names = self.controller.component_glyph_names(names)
            if component_names:
                choice = ask(
                    "Decompose component glyphs?",
                    "Component glyphs will be decomposed before fracture generation.\n\n"
                    "This operation affects only the generated working UFOs.\n"
                    "The source UFO will not be modified.\n\n"
                    "Continue?",
                    buttonTitles=[
                        ("Cancel", "cancel"),
                        ("Continue", "continue"),
                    ],
                    parentWindow=self.w,
                )
                if choice != "continue":
                    self._log("Generate cancelled before processing component glyphs.")
                    return
        self._batch_action = action
        self._batch_decompose_components = decompose_components
        self._batch_cancelled = False
        self._batch_integrity_error_shown = False
        self._batch_queue = list(names)
        self._batch_counts = {
            "completed": 0,
            "skipped": 0,
            "rejected": 0,
            "failed": 0,
        }
        self._set_batch_status(0, len(names), "—", 0, 0, 0, 0)
        self._set_batch_running(True)
        self._log(f"Starting {action} for {len(names)} glyph(s).")
        callAfter(self._process_batch)

    def _batch_progress(self, index, total, glyph_name):
        self.w.glyphStatus.set(f"Processing {index + 1}/{total}: {glyph_name}")
        self._set_batch_status(
            index + 1,
            total,
            glyph_name,
            self._batch_counts["completed"],
            self._batch_counts["skipped"],
            self._batch_counts["rejected"],
            self._batch_counts["failed"],
        )
        self._yield_ui_events()

    def _batch_item_complete(self, position, total, glyph_name, summary):
        self._batch_counts = {
            key: len(summary[key])
            for key in ("completed", "skipped", "rejected", "failed")
        }
        self._set_batch_status(
            position,
            total,
            glyph_name,
            self._batch_counts["completed"],
            self._batch_counts["skipped"],
            self._batch_counts["rejected"],
            self._batch_counts["failed"],
        )
        self._yield_ui_events()

    def _process_batch(self):
        names = tuple(self._batch_queue)
        self._batch_queue = []
        if self._batch_cancelled or not names:
            self._log("Batch cancelled before processing." if self._batch_cancelled else "Batch contained no glyphs.")
            self._set_batch_running(False)
            return
        try:
            result = self.controller.process_names(
                names,
                action=self._batch_action,
                decompose_components=self._batch_decompose_components,
                resolve_edited=self._resolve_edited,
                confirm_topology_replacement=self._confirm_topology_replacement,
                progress=self._batch_progress,
                item_complete=self._batch_item_complete,
            )
        except Exception as error:
            self._log(f"Batch stopped by an unexpected error: {error}")
            message(
                "Batch processing failed",
                str(error),
                alertStyle="critical",
                parentWindow=self.w,
            )
            return
        finally:
            self._set_batch_running(False)
        for glyph_name in result["completed"]:
            self._log(f"Completed: {glyph_name}")
        for glyph_name, reason in result["skipped"]:
            self._log(f"Skipped {glyph_name}: {reason}")
        for glyph_name, reason in result["rejected"]:
            self._log(f"Rejected {glyph_name}: {reason}")
        for glyph_name, reason in result["failed"]:
            if (
                "working fonts differ outside generated outlines" in reason
                and not self._batch_integrity_error_shown
            ):
                self._log(f"Failed {glyph_name}: {reason}")
                message(
                    "Working-font integrity failure",
                    reason,
                    alertStyle="critical",
                    parentWindow=self.w,
                )
                self._batch_integrity_error_shown = True
            elif "working fonts differ outside generated outlines" not in reason:
                self._log(f"Failed {glyph_name}: {reason}")
        self._log(
            "Batch result: "
            f"{len(result['completed'])} completed, "
            f"{len(result['skipped'])} skipped, "
            f"{len(result['rejected'])} rejected, "
            f"{len(result['failed'])} failed."
        )
        if result["completed"]:
            self._log("Completed glyphs: " + ", ".join(result["completed"]))
        if result["skipped"]:
            self._log("Skipped glyphs: " + ", ".join(name for name, reason in result["skipped"]))
        if result["rejected"]:
            self._log("Rejected glyphs: " + ", ".join(name for name, reason in result["rejected"]))
        if result["failed"]:
            self._log("Failed glyphs: " + ", ".join(name for name, reason in result["failed"]))
        if result["cancelled"]:
            self._log("Batch cancelled; completed glyphs were kept.")
        if result.get("saveError"):
            self._log("Working-font save failure: " + result["saveError"])
            message(
                "Working-font save failed",
                result["saveError"],
                alertStyle="critical",
                parentWindow=self.w,
            )
        self.refresh_ui()
        self.previewCurrent(regenerate_topology=False)

    def generateCallback(self, sender):
        self._begin_batch("generate")

    def previewCallback(self, sender):
        self.previewCurrent(regenerate_topology=False)

    def motionOnlyCallback(self, sender):
        self._begin_batch("motion")

    def topologyCallback(self, sender):
        self._begin_batch("topology")

    def replaceStaleCallback(self, sender):
        self._begin_batch("replace-stale")

    def cancelCallback(self, sender):
        self._batch_cancelled = True
        self.controller.request_cancel()
        self._log("Cancellation requested; stopping after the current glyph.")

    def validateCallback(self, sender):
        try:
            findings = self.controller.validate()
            self._log("Validation passed." if not findings else "Validation warnings:\n" + "\n".join(findings))
        except Exception as error:
            self._log(f"Validation failed: {error}")

    def roboFontEvent(self, notification):
        if self.controller.project:
            try:
                if notification.get("name") == "fontDidSave":
                    self.controller.project.refresh_paths()
            except Exception as error:
                self._log(error)
        self.refresh_ui()

    def windowCloseCallback(self, sender):
        self._closed = True
        self._topology_debounce_token += 1
        for event in self.observer_events:
            removeObserver(self, event)
        for name in ("intactPreview", "middlePreview", "erodedPreview"):
            getattr(self.w, name).setGlyph(None)
        from .extension import window_closed

        window_closed()
