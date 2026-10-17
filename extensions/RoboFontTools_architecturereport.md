# Workspace Launcher: Current Architecture Report

**Scope.** This is an analysis-only report of the current Workspace Launcher
bundle and the adjacent RoboFont Tools extension. No extension source was
changed. Evidence labels used throughout are **[source]** (this repository),
**[docs]** (official RoboFont documentation), **[inferred]**, and
**[unresolved]**.

## 1. Executive summary

Workspace Launcher is a RoboFont 4.4 startup extension that installs one
top-level menu. Its **Open** action is a fixed seven-item list of xTools4
controller classes. It opens each class with `mojo.roboFont.OpenWindow`, then
uses a one-second AppKit delayed callback to restore frames by window title and
apply saved project paths. **[source]**

The present design is workable for one known set of xTools4 palettes, but it
has two incompatible identity mechanisms: controller-class identity for the
xTools4 launch phase, and title-only identity for the save/restore phase. The
layout file contains only a title and frame. It cannot reopen missing windows,
differentiate two same-titled windows, record window ownership/context, or
identify an adapter. **[source]**

RoboFont Tools already presents a better extension-facing launch contract:
`robofont_tools.extension.open_window()` owns a singleton EZUI controller,
reuses/focuses it on later calls, and returns that controller. It is a strong
first non-xTools4 candidate for a registry adapter, but Workspace Launcher
does not currently import or open it. **[source]**

Recommended direction: create one capability-based registry pipeline with
isolated adapters. Move every existing xTools4 recipe into that pipeline first;
then add a RoboFont Tools adapter; finally add only documented native-window
adapters. Keep unknown windows as frame/diagnostic records, never as inferred
Python imports or arbitrary constructors. **[inferred]**

## 2. Current file and module map

```text
extensions/
├── WorkspaceLauncher.roboFontExt/
│   ├── info.plist                         bundle metadata; startup declaration
│   └── lib/
│       ├── start.py                       adds bundle lib to sys.path; installs menu
│       └── workspaceLauncher/
│           ├── __init__.py                package marker
│           ├── menu.py                    AppKit menu/Objective-C action target
│           ├── openWorkspace.py           xTools4 imports, launch, restore, paths
│           ├── saveLayout.py              title/frame layout snapshot writer
│           ├── loadProjectPaths.py        JSON path settings and controller retention
│           └── configureProjectPaths.py   Vanilla configuration floating window
├── RoboFontTools/
│   ├── README.md                          installation/use/development notes
│   ├── pyproject.toml                     test/project configuration
│   ├── tests/                             headless bundle, model and geometry tests
│   └── RoboFontTools.roboFontExt/
│       ├── info.plist                     Extensions-menu registration and metadata
│       └── lib/
│           ├── startup.py                 menu entry; opens the palette
│           └── robofont_tools/
│               ├── extension.py           singleton palette lifecycle/public opener
│               ├── palette.py             EZUI `RoboFontToolsPaletteController`
│               ├── geometry.py            pure measurement utilities
│               └── tools/                 measurement tools, state and models
└── docs/workspace-tool-notes.md           earlier plan and known limitations
```

There are no Workspace Launcher tests or bundle-local documentation in this
checkout. RoboFont Tools has four test modules plus bundle tests. **[source]**

### Startup and menu callbacks

| Concern | Implementation | Details |
| --- | --- | --- |
| Startup | `lib/start.py` → `install_workspace_launcher_menu()` | `info.plist` declares `mainScript=start.py` and `launchAtStartUp=true`. **[source]** |
| Menu installation | `workspaceLauncher.menu.install_workspace_launcher_menu` | Calls `install_controller_captures()`, removes duplicate top-level items named `Workspace Launcher`, then inserts its menu immediately before the last main-menu item (assumed Help). **[source]** |
| Open | `WorkspaceLauncherMenuTarget.openWorkspace_` → `open_workspace()` | Opens all seven xTools4 classes and schedules finalization. **[source]** |
| Load | `loadProjectPaths_` → `load_saved_project_resources()` | Applies saved resource paths only to xTools4 controllers already open; it does not load a layout. **[source]** |
| Configure Project Paths | `configureProjectPaths_` → `show_configure_project_paths()` | Opens/focuses a singleton Vanilla `FloatingWindow`. **[source]** |
| Save Layout | `saveLayout_` → `save_layout()` | Replaces the complete title/frame snapshot. **[source]** |

### Important functions/classes

| Module | Name | Purpose, callers, side effects and assumptions |
| --- | --- | --- |
| `start.py` | module body | Prepends bundle `lib` to `sys.path`, imports and runs menu installation. Assumes startup execution once RoboFont's menu is available. **[source]** |
| `menu.py` | `WorkspaceLauncherMenuTarget` | Objective-C target retaining callbacks for menu actions. Instantiated by `install_workspace_launcher_menu`; methods delegate with no arguments/context. **[source]** |
| `menu.py` | `install_workspace_launcher_menu()` | Installs controller constructor monkey patches, reconstructs menu, holds `_menu_target`. Assumes `NSApp().mainMenu()` exists and final top-level item is Help. **[source]** |
| `openWorkspace.py` | `install_controller_capture()` | Replaces each xTools controller's `__init__` to retain the constructed instance in `active_controllers`, marking the class to avoid repeat wrapping. This mutates third-party classes and assumes their constructor is the lifecycle point. **[source]** |
| `openWorkspace.py` | `get_open_controllers()` | Returns known controller instances; first uses retained objects, then scans `gc.get_objects()` for instances of exact classes. Side effect: adds recovered controllers to `active_controllers`. Assumes `controller.w.getNSWindow()` and membership in `NSApp.windows()`. **[source]** |
| `openWorkspace.py` | `launch(controller_class)` | Calls `OpenWindow(controller_class)`, obtains captured controller by class name, logs reuse/new state. Assumes `OpenWindow` returns `True` for an already-open controller, as official docs state. **[source][docs]** |
| `openWorkspace.py` | `open_workspace()` | Iterates `CONTROLLER_CLASSES`, launches all, schedules finalization. This is a list-driven registry only in the narrow sense of a list of classes; resource handlers are separately keyed by class name. **[source]** |
| `openWorkspace.py` | `restore_layout()` | Loads JSON; builds the first live `NSWindow` per nonempty title; restores matching frames once per saved title. It never opens a missing window. **[source]** |
| `openWorkspace.py` | `schedule_workspace_finish()` / `WorkspaceFinisher.restoreLayout_` | Retains an Objective-C finisher globally and invokes it after 1.0 seconds. It calls frame restoration then applies project paths. No readiness test or retry exists. **[source]** |
| `openWorkspace.py` | `apply_project_paths()` | Validates saved resource files/extensions and dispatches special handlers for five named xTools classes. It can open UFOs invisibly for two handlers. **[source]** |
| `saveLayout.py` | `collect_windows()` / `save_layout()` | Enumerates every `NSApp.windows()` item with a title, captures frame floats, removes duplicate titles (first wins), and overwrites JSON. **[source]** |
| `loadProjectPaths.py` | `active_controllers` | Process-lifetime dictionary from class-name strings to controllers. It deliberately retains controllers. **[source]** |
| `loadProjectPaths.py` | `load_project_paths`, `save_project_paths`, `clear_project_path` | Reads/writes selected resource paths while preserving legacy location. Empty fields do not delete values; explicit clear does. **[source]** |
| `configureProjectPaths.py` | `ConfigureProjectPathsController` / `show_configure_project_paths()` | Vanilla dialog with designspace/UFO/TTF choosers. A module global provides single-instance/focus behavior. **[source]** |

## 3. Current Open call flow

```text
Workspace Launcher > Open
  → WorkspaceLauncherMenuTarget.openWorkspace_
  → open_workspace()
  → install_controller_captures()
  → for each CONTROLLER_CLASSES item: launch(class)
  → OpenWindow(class)
  → controller __init__ capture → active_controllers[class name]
  → schedule_workspace_finish(..., 1.0 seconds)
  → restore_layout() by title
  → apply_project_paths() by controller class-name handler
```

`OpenWindow` is the sole window-opening API in Workspace Launcher. It is not
menu simulation or `exec`-ed scripts. RoboFont documents it as opening a
controller only if that controller is not already open, returning `True` when
it was already open and `False` when a new instance was opened. **[source][docs]**

### Launch set and xTools4 references

The exact source launch data is:

```python
CONTROLLER_CLASSES = [
    BlendsPreviewController, GlyphMemeController, GlyphValidatorController,
    MeasurementsController, VarGlyphViewer, ImportGlyphsIntoLayerDialog,
    MaskDialog,
]
```

| Title / menu path | Controller / module | Exact opening and lifecycle |
| --- | --- | --- |
| **[unresolved]** actual title; xTools4 variable dialog `BlendsPreview` | `BlendsPreviewController` / `xTools4.dialogs.variable.BlendsPreview` | `OpenWindow(BlendsPreviewController)`; captured under class name; duplicate prevention delegated to `OpenWindow`; later layout match is title-only. A reference-font handler also directly sets `referenceFontPath` and private-looking `_group1.compare`. **[source]** |
| **[unresolved]** actual title; `GlyphMeme` | `GlyphMemeController` / `xTools4.dialogs.variable.GlyphMeme` | `OpenWindow(GlyphMemeController)`; capture and title match as above; designspace handler sets `designspacePath`, calls `_loadDesignspace`. **[source]** |
| **[unresolved]** actual title; `GlyphValidator` | `GlyphValidatorController` / `xTools4.dialogs.variable.GlyphValidator` | `OpenWindow(GlyphValidatorController)`; special handler builds/reads `DesignSpaceDocument`, invisibly calls `OpenFont`, posts xTools event, and calls `updateFontViewCallback`. **[source]** |
| **[unresolved]** actual title; `Measurements` | `MeasurementsController` / `xTools4.dialogs.variable.Measurements` | `OpenWindow(MeasurementsController)`; designspace property/private loader handler. **[source]** |
| **[unresolved]** actual title; `VarGlyphViewer` | `VarGlyphViewer` / `xTools4.dialogs.variable.VarGlyphViewer` | `OpenWindow(VarGlyphViewer)`; special default-font handler assigns `defaultPath`, invisibly opens font, calls `settingsChangedCallback`. **[source]** |
| **[unresolved]** actual title; old glyph-layer import dialog | `ImportGlyphsIntoLayerDialog` / `xTools4.dialogs.glyphs.old.layersImport` | `OpenWindow(ImportGlyphsIntoLayerDialog)`; no resource handler. **[source]** |
| **[unresolved]** actual title; old glyph-layer mask dialog | `MaskDialog` / `xTools4.dialogs.glyphs.old.layersMask` | `OpenWindow(MaskDialog)`; no resource handler. **[source]** |

No xTools4 menu paths/titles are present in Workspace Launcher source. The
paths above are import/module paths, not confirmed user-visible menu paths;
they need xTools4 source or runtime inspection. The local suggested
`AnchorAligner` script separately illustrates the same class-import plus
`OpenWindow(AnchorAlignerController)` pattern, but it is not launched by this
extension. **[source]**

All hardcoded xTools4 dependencies are the seven imports/classes, the complete
`CONTROLLER_CLASSES` sequence, the capture monkey patch/GC recovery designed
for those classes, class-name-keyed `TOOL_RESOURCE_HANDLERS`, the
`com.xTools4.dialogs.variable.glyphValidator.changed` event, and assumptions
about xTools controller attributes/methods listed above. **[source]**

## 4. Current Save Layout call flow and persistence

```text
Workspace Launcher > Save Layout
  → save_layout()
  → collect_windows()
  → NSApp.windows()
  → window.title(), window.frame()
  → first window for each nonempty title
  → ~/Library/Application Support/RoboFont/WorkspaceLauncher/layout.json
```

The writer records only `title`, `x`, `y`, `width`, and `height`, all frame
values as floats. It stores no class/module/controller/owner/screen/context or
stable identifier. A representative anonymised file is:

```json
{
  "windows": [
    {"title": "Example Palette", "x": 140.0, "y": 90.0,
     "width": 420.0, "height": 300.0}
  ]
}
```

`NSApp.windows()` is enumerated without filtering by bundle, visibility,
window class, document ownership, or whether the window can be reopened.
Untitled windows are excluded. Same-title windows are possible according to the
code comment; only the first encountered one is saved. Each save is a complete
replacement (`"w"`), not a merge, so absent windows disappear from the saved
layout. **[source]**

Screen identity is not saved. AppKit frame coordinates are copied unchanged,
so no coordinate conversion, display lookup, clipping, or scale handling is
done; a changed monitor topology may place a frame off-screen. **[source]**

## 5. Current Restore Layout call flow

The delayed finisher runs one second after all `OpenWindow` calls. It reads
`layout.json`, converts live `NSApp.windows()` to a dictionary keyed by first
nonempty title, and calls `setFrame_display_(NSMakeRect(...), True)` for a
matching record. Duplicate saved titles are skipped. Missing/untitled records
are skipped and logged; there is no retry. **[source]**

Thus **restoring a frame** means moving a window already open at the instant of
the one delayed pass. It does **not** mean reopening a previously saved window.
The only attempted reopen work is the fixed xTools4 launch set that runs first,
regardless of which records are saved. **[source]**

## 6. Project-path configuration/persistence

Project paths live separately at
`~/Library/Application Support/RoboFont/WorkspaceLauncher/projectPaths.json`.
The accepted keys are `designspace`, `defaultFont`, and `referenceFont`; values
are nonempty strings. Example:

```json
{
  "defaultFont": "/project/Sources/Regular.ufo",
  "designspace": "/project/Family.designspace",
  "referenceFont": "/project/reference.ttf"
}
```

The configuration dialog persists a selection immediately and its Save button
persists all nonempty field values. Clearing is the only deletion mechanism.
At Open finalization, handlers validate path existence and a fixed extension
before applying only to named xTools controller classes. **[source]**

## 7. RoboFont Tools opening analysis

RoboFont Tools requires RoboFont 4.6 and registers `startup.py` as an
Extensions-menu entry (it is not startup-launched). `startup.py` imports
`robofont_tools.extension.open_window` and calls it. **[source]**

The public opening API is:

```text
module:       robofont_tools.extension
callable:     open_window()
identifier:   [not yet declared; proposed adapter-owned identifier]
title:        RoboFont Tools
controller:   robofont_tools.palette.RoboFontToolsPaletteController
```

`open_window()` holds `_window_controller`. On its first call it instantiates
the EZUI `WindowController`; subsequent calls call `w.show()`, `w.makeKey()`,
and `refresh()` on the same controller, then return it. `destroy()` stops tools
and calls `window_closed()` to clear the retained singleton. This is confirmed
single-instance behavior, assuming EZUI invokes `destroy()` on close. Its
palette uses `ezui.EZWindow` (not a direct Vanilla or raw AppKit window), sets
the actual title through `title = "RoboFont Tools"`, and supplies an EZUI
autosave name `com.boryskosmynka.robofonttools.toggler.palette`. **[source]**

This is a clean public API suitable for registration: it is explicit, returns a
controller, avoids duplicate palettes, and has a known expected title. It lacks
a published stable Workspace Launcher identifier/readiness method, so an
adapter should provide those without relying on the title alone. **[inferred]**

## 8. Native RoboFont windows

| Window | Verified opener/context | Assessment |
| --- | --- | --- |
| Space Center | `mojo.UI.OpenSpaceCenter(font, newWindow=False)`. Docs also provide `CurrentSpaceCenter`, `AllSpaceCenters`, and corresponding window accessors. A font object is required; `newWindow=False` requests reuse instead of forcing a new window. **[docs]** | **Verified but context-dependent.** Save font path or a resolvable open-font identity, then use API and inspect result/window mapping at runtime. |
| Glyph Editor | `mojo.UI.OpenGlyphWindow(glyph=None, newWindow=False)`. Requires an `RGlyph`; `newWindow=True` forces another glyph window. `AllGlyphWindows`/`CurrentGlyphWindow` exist. **[docs]** | **Verified but context-dependent.** Persist font path plus glyph name (and possibly layer/window policy); do not title-match. |
| Font Overview | `mojo.roboFont.OpenFont(pathOrObject, showInterface=True)` opens a font UI; docs describe the Font Overview as the parent window shown when a font is created/opened. **[docs]** | **Verified but context-dependent.** The input is a file path/object; matching the particular overview `NSWindow` needs runtime verification, especially in single-window mode. |
| Output Window | `mojo.UI.OutputWindow()` is documented and exposes `clear()`. Documentation does not state that calling it creates/shows/focuses the window. **[docs]** | **No reliable public opener found** from available docs; it may be inspectable if already open, but should not get an opener yet. |
| Scripting Window | Docs verify menu route `Python > Scripting Window` and shortcut Option-Command-R, but no documented Python opener/controller is identified. **[docs]** | **No reliable public opener found.** Menu invocation would be a fragile fallback and should not be a baseline adapter. |
| Preferences | Available docs describe the Preferences Editor but no public Python opener/controller was found in inspected references. **[docs]** | **No reliable public opener found.** |

The official API additionally exposes `AllWindows`, `AllFontWindows`,
`AllGlyphWindows`, `AllSpaceCenters`, and `AllSpaceCenterWindows`, which are
useful for native matching rather than generic `NSApp.windows()` alone.
**[docs]** Official documentation confirms events for glyph/space-center open
and close; they can support readiness diagnostics, but this report does not
infer an undocumented controller or opener from them. **[docs]**

## 9. Window types and launch strategies

One low-level opening operation cannot safely cover every type. The registry
should describe these strategies:

1. **Controller class:** `OpenWindow(controller_class)` for xTools4-like
   controllers; duplicate policy supplied by RoboFont.
2. **Extension public function/singleton:** call an extension's documented
   `open_window()` and use its returned controller (RoboFont Tools).
3. **Vanilla/EZUI/NSPanel owner:** an extension-provided adapter owns lifecycle
   and exposes an `NSWindow`; the wrapper class alone is diagnostic metadata.
4. **Native public API:** documented APIs such as `OpenSpaceCenter` and
   `OpenGlyphWindow`, with required font/glyph context.
5. **Document window:** `OpenFont(path, showInterface=True)` with a saved,
   user-approved font path and document identity.
6. **Glyph window:** font path plus glyph name/layer and explicit new/reuse
   policy.
7. **Menu fallback:** only when a verified public API does not exist; lower
   reliability and version-sensitive.
8. **Position-only unknown window:** persist diagnostics/frame but do not
   attempt reopening.

## 10. Inspection plan for real window objects

The checkout cannot instantiate RoboFont/AppKit window objects; no RoboFont
application or xTools4 package source was located locally. The following is a
safe temporary-development probe plan, not a proposed permanent extension
change. **[source][unresolved]**

1. Open one representative of each requested type: an xTools4 controller,
   RoboFont Tools palette, Vanilla `FloatingWindow`, EZUI controller, raw
   `NSPanel`, Space Center, Output Window, Scripting Window, Font Overview and
   Glyph Editor.
2. For each `NSApp.windows()` entry, log title; Objective-C class (`class_()`);
   frame/screen; visibility; `windowController()` and its Objective-C/Python
   class/module where bridged; content view class; represented URL/document;
   delegate; and any identifier/autosave name exposed by documented wrapper
   APIs. Do not retain objects or invoke methods merely discovered by name.
3. For known adapter candidates, separately ask their public controller for the
   wrapped window (`controller.w.getNSWindow()` where documented by that
   extension), and record stable domain context: font path, glyph name/layer,
   Space Center font, or extension identifier.
4. Compare every result to `AllWindows`, `AllGlyphWindows`,
   `AllSpaceCenters`, `CurrentFontWindow`, and `CurrentGlyphWindow` to establish
   whether native wrappers expose the same `NSWindow`. Test a second window
   with the same visible title and a second monitor if available.

Expected discovery is deliberately type-dependent: title and `NSWindow` class
are broadly discoverable from a live `NSWindow`; controller/module ownership,
represented document, font/glyph context, a stable identifier, and a safe
reopen callable are **not** guaranteed by AppKit and must be confirmed per
adapter. Vanilla/EZUI wrappers, raw `NSPanel`s, and RoboFont document windows
must not be treated as structurally identical. **[inferred]**

## 11. Automatic discovery: safe limits

### Safe automation

- Capture current title, frame, visibility and AppKit window class as a
  snapshot diagnostic.
- Persist a frame with an explicit coordinate-space/screen descriptor when
  available.
- Ask registered adapters to identify their own open windows and serialize only
  their documented JSON-safe context.
- Use official RoboFont collection APIs for known native window types.

### Heuristic metadata

- Python/Objective-C controller class and module names, content-view class,
  represented-document description, title, bundle guess and autosave name.
- A title/class/module fingerprint for diagnostics or manual adapter authoring.

These can improve reports or matching confidence but must not become executable
instructions merely because they were observed. **[inferred]**

### Unsafe/unreliable inference

- Importing an arbitrary observed module and constructing its observed class.
- Assuming a controller constructor has no arguments or carries the same
  singleton semantics as `OpenWindow`.
- Deriving extension ownership from a generic `NSWindow`.
- Guessing a document/glyph from title, invoking private APIs, replaying menu
  actions by localized titles, or assuming frames work across display layouts.

## 12. Registry, adapters and self-registration

| Option | Benefits | Risks/limits |
| --- | --- | --- |
| A. Central built-in registry | Simple load order, one supported catalog, ideal for current xTools4 baseline. | Workspace Launcher becomes coupled to optional extensions and native API details. |
| B. Isolated adapter modules | Separates xTools4/RoboFont Tools/native dependencies; optional imports can fail locally without disabling the launcher; easy unit tests. | Still needs a central discovery/registration point. |
| C. Extension self-registration | Third parties own their opening/context semantics and can work without being hardcoded. | Installation/reload ordering, duplicate registration, API-version negotiation and stale callbacks require a defined protocol. |

Recommend **A + B now, C later**. A small central registry should load built-in
adapter modules (`adapters.xtools4`, `adapters.robofont_tools`,
`adapters.robofont_native`); each adapter should import optional dependencies
lazily and report unavailable status. After that contract is stable, expose
optional self-registration with adapter ID uniqueness, API version, source
bundle name, unregister/reload handling, and idempotent replacement rules.
Extensions must not require Workspace Launcher to function. **[inferred]**

## 13. Recommended unified architecture

Use adapters that express capability instead of pretending that all windows are
controller classes. A practical contract is:

```text
WindowAdapter
    adapter_id, display_name, api_version
    identify(ns_window) -> WindowIdentity | None
    find_existing(saved_record) -> window | None
    open(saved_record) -> window/controller/result | Unavailable
    is_ready(window_or_result) -> bool
    serialize_context(window_or_result) -> JSON dict
    restore_frame(window, frame, display) -> outcome
```

The registry owns record validation, ID allocation, adapter selection, bounded
retry scheduling, diagnostics, optional-dependency status, and migration. The
adapter owns opening policy, duplicate/reuse semantics, context serialization,
and type-specific matching. This supports xTools4 controller classes, the
RoboFont Tools singleton, Vanilla/EZUI/NSPanel owners, public native APIs and
document/glyph context without hiding their differences. **[inferred]**

## 14. Proposed versioned saved-layout schema

```json
{
  "schemaVersion": 2,
  "savedAt": "2026-08-01T12:00:00Z",
  "coordinateSpace": {"kind": "appkit-screen", "screens": []},
  "windows": [
    {
      "id": "robofont-tools.palette:default",
      "adapter": "com.boryskosmynka.workspace.robofont-tools.palette",
      "title": "RoboFont Tools",
      "context": {},
      "frame": {"x": 140.0, "y": 90.0, "width": 300.0, "height": 110.0},
      "match": {"windowClass": "NSPanel", "controllerClass": "RoboFontToolsPaletteController"},
      "discovered": {"adapterVersion": 1},
      "status": "reopenable"
    }
  ]
}
```

`id` is a per-record stable identity, normally adapter namespace plus an
adapter-defined instance/context key. `adapter` selects executable behavior;
`context` is JSON-only domain data such as a saved font path/glyph name;
`match`/`discovered` are non-authoritative diagnostics; and `status` records
`reopenable`, `position-only`, `unavailable`, or `unresolved`. Never save
Python objects, source code, arbitrary import strings, callable names inferred
from a window, or machine-specific path hacks where an adapter ID suffices.
**[inferred]**

Migration from v1 is deterministic: wrap each old `{title,x,y,width,height}`
in a v2 position-only record, retain title/frame, use a generated legacy ID,
and leave `adapter` unset. Optionally let a known adapter claim an old record
only via an explicit migration mapping confirmed by stable expected title; do
not silently execute it. Preserve the original file or write a backup before
the first destructive schema upgrade. **[inferred]**

## 15. Incremental migration plan

1. Add source-level unit tests/temporary diagnostics that characterize today’s
   seven launch requests, one-second delayed restore, and v1 title/frame JSON.
2. Introduce registry core and xTools4 adapter records that call the existing
   `OpenWindow` recipes; retain current capture logic only behind that adapter.
3. Have save/restore use adapter identity first while retaining v1 reader
   compatibility and title-only fallback for legacy/unknown windows.
4. Give every known xTools4 record a stable adapter ID; move resource handlers
   into its per-tool adapter/context policy.
5. Add RoboFont Tools through `robofont_tools.extension.open_window()` as the
   same pipeline’s second adapter, not as another menu-specific branch.
6. Add Space Center, glyph, and document adapters only through documented APIs
   and verified runtime matching; leave Output/Scripting/Preferences
   position-only meanwhile.
7. Retain unknown windows as diagnostics/frame-only records.
8. Remove direct `CONTROLLER_CLASSES` launch orchestration only after behavior
   parity, migration tests, and missing-dependency behavior are verified.

Key risks: xTools4 import/startup timing; monkey-patched constructor lifetime;
`OpenWindow` semantics; duplicate titles/windows; changed localized titles;
stale layout/adapters; missing optional extensions; monitor coordinate changes;
and private xTools properties/event APIs. **[source][inferred]**

## 16. Tests and diagnostics

Current automated coverage exists only for RoboFont Tools: bundle metadata and
source lifecycle contracts, geometry, selected-points model, and contour-probe
model. Tests use `unittest` and are documented as headless; UI/editor behavior
still needs RoboFont. Workspace Launcher has no tests in this checkout.
**[source]**

Future headless tests: registry ID/duplicate rules; adapter availability;
matching precedence; xTools4 recipe objects with mocks; singleton duplicate
policy; v1/v2 schema validation and migration; unknown-window position-only
handling; retry backoff; missing optional extensions; same-title windows; and
screen-frame policy. RoboFont integration tests: actual `OpenWindow` behavior,
controller capture/close, EZUI lifecycle, native Space Center/glyph/document
matching, multi-monitor coordinate behavior, and display readiness. **[inferred]**

Useful diagnostic output per open window should print: `title`, AppKit window
class, controller class/module when discoverable, matched adapter, stable
identifier, frame and screen descriptor, serialized context, and reopen
capability/status. It must report failures rather than attempt speculative
opening. **[inferred]**

## 17. Questions requiring RoboFont runtime inspection

- The actual xTools4 titles, menu paths, controller window wrappers, and
  readiness timing for all seven classes.
- Whether all xTools4 constructors safely tolerate the existing monkey patch,
  and whether controller class names are globally unique.
- `NSWindow`/controller/content-view/document/delegate information for each
  requested window type, especially raw panels and native windows.
- Whether the RoboFont Tools EZUI window has a stable inspectable autosave
  identifier and exactly when `destroy()` runs.
- How `OpenSpaceCenter`, `OpenGlyphWindow`, and `OpenFont` map their returned
  objects to `NSWindow`, including duplicate policy in current RoboFont 4.6.
- Whether Output Window has a current documented show/open API; whether a
  supported Scripting/Preferences API exists in the installed version.
- Effects of multi-window/single-window mode, multiple monitors, Retina scale,
  hidden/minimized windows, and same-title windows.

## 18. Suggested next implementation milestone

Build a non-invasive **window diagnostics + v2 registry core** milestone first:
adapter registration, known-window identification, v1 read compatibility, and
report-only inspection of live windows. Then put the existing seven xTools4
entries behind adapters with behavior-parity tests. Do not add new openers
until their runtime identity and documented lifecycle are verified.

## Sources consulted

- Repository sources listed in the file map and `docs/workspace-tool-notes.md`.
- Official [mojo.roboFont API](https://robofont.com/documentation/reference/api/mojo/mojo-robofont), including `OpenWindow` and `OpenFont`.
- Official [mojo.UI API](https://robofont.com/documentation/reference/api/mojo/mojo-ui/), including `OpenSpaceCenter`, `OpenGlyphWindow`, native window accessors, and `OutputWindow`.
- Official [RoboFont workspace overview](https://doc.robofont.com/documentation/topics/workspace-overview), [Space Center](https://robofont.com/documentation/reference/workspace/space-center/), [Scripting Window](https://www.robofont.com/documentation/reference/workspace/scripting-window/), [Output Window](https://robofont.com/documentation/reference/workspace/output-window), [Font Overview](https://robofont.com/documentation/reference/workspace/font-overview/), and [Glyph Editor](https://doc.robofont.com/documentation/reference/workspace/glyph-editor/).

## Console summary

- **Report path:** `extensions/RoboFontTools_architecturereport.md`
- **Files inspected:** 7 Workspace Launcher source/metadata files; 3 RoboFont Tools runtime files; RoboFont Tools README and 4 test modules; `docs/workspace-tool-notes.md`; local xTools4 Anchor Aligner example; official RoboFont API/workspace documentation.
- **Current hardcoded launch count:** 7 xTools4 controller classes.
- **Identified opening strategies:** 8.
- **Top recommendations:** use a central registry with isolated adapters; migrate xTools4 first so it shares the one pipeline; retain unknown windows as position-only and never infer executable launch code.
