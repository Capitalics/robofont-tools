import os

from fontTools.designspaceLib import DesignSpaceDocument
from mojo.UI import GetFile
from mojo.roboFont import CurrentGlyph, OpenFont
from vanilla import Button, FloatingWindow, TextBox, TextEditor


KEY = 'com.xTools4.dialogs.variable.anchorAligner'


class AnchorAlignerController:

    title = 'Anchor Aligner'
    width = 520
    height = 520
    padding = 12
    lineHeight = 24

    designspacePath = None
    designspace = None
    sourcePaths = []
    pointSelection = None
    anchorSelection = None

    def __init__(self):
        self.designspacePath = None
        self.designspace = None
        self.sourcePaths = []
        self.pointSelection = None
        self.anchorSelection = None

        self.w = FloatingWindow(
            (self.width, self.height),
            title=self.title,
            minSize=(420, 440),
        )

        p = self.padding
        y = p
        buttonWidth = 160

        self.w.loadDesignspace = Button(
            (p, y, buttonWidth, self.lineHeight),
            'Load Designspace…',
            callback=self.loadDesignspaceCallback,
        )
        self.w.reloadDesignspace = Button(
            (p + buttonWidth + p, y, buttonWidth, self.lineHeight),
            'Reload Designspace',
            callback=self.reloadDesignspaceCallback,
        )
        self.w.reloadDesignspace.enable(False)

        y += self.lineHeight + 6
        self.w.designspaceInfo = TextBox(
            (p, y, -p, 58),
            'No designspace loaded.',
        )

        y += 68
        self.w.selectPoint = Button(
            (p, y, buttonWidth, self.lineHeight),
            'Select Point',
            callback=self.selectPointCallback,
        )
        y += self.lineHeight + 4
        self.w.pointInfo = TextBox((p, y, -p, 36), 'No point selected.')

        y += 46
        self.w.selectAnchor = Button(
            (p, y, buttonWidth, self.lineHeight),
            'Select Anchor',
            callback=self.selectAnchorCallback,
        )
        y += self.lineHeight + 4
        self.w.anchorInfo = TextBox((p, y, -p, 36), 'No anchor selected.')

        y += 46
        self.w.align = Button(
            (p, y, -p, 30),
            'Align Anchor to Point Across Designspace',
            callback=self.alignCallback,
        )

        y += 40
        self.w.log = TextEditor(
            (p, y, -p, -p),
            readOnly=True,
        )
        self._setLog('Ready. Load a designspace and select a point and anchor.')

        self.w.getNSWindow().setTitlebarAppearsTransparent_(True)
        self.w.workspaceWindowIdentifier = KEY
        self.w.open()

    def _setLog(self, message):
        self.w.log.set(message)
        print(f'Anchor Aligner: {message}')

    def _sourcePath(self, source):
        path = source.path
        if not path and source.filename:
            path = os.path.join(os.path.dirname(self.designspacePath), source.filename)
        if path:
            path = os.path.normpath(os.path.abspath(path))
        return path

    def _loadDesignspace(self):
        try:
            document = DesignSpaceDocument()
            document.read(self.designspacePath)
            sourcePaths = [self._sourcePath(source) for source in document.sources]
        except Exception as error:
            self.designspace = None
            self.sourcePaths = []
            self.w.reloadDesignspace.enable(False)
            self.w.designspaceInfo.set('Unable to load designspace.')
            self._setLog(f'Error loading designspace: {error}')
            return

        self.designspace = document
        self.sourcePaths = sourcePaths
        missing = [path or '(unresolved path)' for path in sourcePaths if not path or not os.path.exists(path)]
        resolved = 'all paths resolve' if not missing else f'{len(missing)} path(s) do not resolve'
        filename = os.path.basename(self.designspacePath)
        self.w.designspaceInfo.set(
            f'{filename}\n{self.designspacePath}\n{len(sourcePaths)} source UFO(s) — {resolved}'
        )
        self.w.reloadDesignspace.enable(True)
        message = f'Loaded {filename}: {len(sourcePaths)} source UFO(s); {resolved}.'
        if missing:
            message += '\nMissing:\n' + '\n'.join(f'• {path}' for path in missing)
        self._setLog(message)

    def loadDesignspaceCallback(self, sender):
        path = GetFile(
            message='Select designspace file:',
            title=self.title,
            allowsMultipleSelection=False,
            fileTypes=['designspace'],
        )
        if not path:
            return
        self.designspacePath = path
        self._loadDesignspace()

    def reloadDesignspaceCallback(self, sender):
        if self.designspacePath:
            self._loadDesignspace()

    def selectPointCallback(self, sender):
        glyph = CurrentGlyph()
        if glyph is None:
            self._setLog('Select one point in an open glyph, then try again.')
            return
        selectedPoints = list(glyph.selectedPoints)
        if len(selectedPoints) != 1:
            self._setLog(f'Select exactly one point; found {len(selectedPoints)} selected points.')
            return

        selectedPoint = selectedPoints[0]
        location = None
        for contourIndex, contour in enumerate(glyph.contours):
            for pointIndex, point in enumerate(contour.points):
                if point is selectedPoint or point == selectedPoint:
                    location = contourIndex, pointIndex
                    break
            if location is not None:
                break
        if location is None:
            self._setLog('The selected point could not be located in a contour.')
            return

        contourIndex, pointIndex = location
        pointType = getattr(selectedPoint, 'type', None)
        self.pointSelection = dict(
            glyphName=glyph.name,
            contourIndex=contourIndex,
            pointIndex=pointIndex,
            pointType=pointType,
            x=selectedPoint.x,
            y=selectedPoint.y,
        )
        info = (
            f'{glyph.name} — contour {contourIndex}, point {pointIndex}'
            f' — x: {selectedPoint.x:g}, y: {selectedPoint.y:g}'
        )
        self.w.pointInfo.set(info)
        self._setLog(f'Selected point: {info}.')

    def selectAnchorCallback(self, sender):
        glyph = CurrentGlyph()
        if glyph is None:
            self._setLog('Select one anchor in an open glyph, then try again.')
            return
        selectedAnchors = getattr(glyph, 'selectedAnchors', None)
        if selectedAnchors is None:
            selectedAnchors = [anchor for anchor in glyph.anchors if getattr(anchor, 'selected', False)]
        selectedAnchors = list(selectedAnchors)
        if len(selectedAnchors) != 1:
            self._setLog(f'Select exactly one anchor; found {len(selectedAnchors)} selected anchors.')
            return

        anchor = selectedAnchors[0]
        if not anchor.name:
            self._setLog('The selected anchor has no name. Name it before aligning.')
            return
        self.anchorSelection = dict(
            glyphName=glyph.name,
            anchorName=anchor.name,
            x=anchor.x,
            y=anchor.y,
        )
        info = f'{glyph.name} — anchor: {anchor.name} — x: {anchor.x:g}, y: {anchor.y:g}'
        self.w.anchorInfo.set(info)
        self._setLog(f'Selected anchor: {info}.')

    def _validateSource(self, path, font):
        point = self.pointSelection
        anchor = self.anchorSelection
        glyphName = point['glyphName']
        if glyphName not in font:
            return None, f'glyph {glyphName!r} is missing'
        glyph = font[glyphName]
        contourIndex = point['contourIndex']
        if contourIndex >= len(glyph.contours):
            return None, f'contour {contourIndex} is missing in {glyphName}'
        contour = glyph.contours[contourIndex]
        pointIndex = point['pointIndex']
        if pointIndex >= len(contour.points):
            return None, f'point {pointIndex} is missing in contour {contourIndex}'
        sourcePoint = contour.points[pointIndex]
        expectedType = point['pointType']
        sourceType = getattr(sourcePoint, 'type', None)
        if expectedType is not None and sourceType != expectedType:
            return None, f'point type is {sourceType!r}; expected {expectedType!r}'
        anchors = [item for item in glyph.anchors if item.name == anchor['anchorName']]
        if not anchors:
            return None, f'anchor {anchor["anchorName"]!r} is missing'
        if len(anchors) > 1:
            return None, f'anchor {anchor["anchorName"]!r} occurs {len(anchors)} times'
        return (glyph, sourcePoint, anchors[0]), None

    def alignCallback(self, sender):
        if self.designspace is None:
            self._setLog('Load a designspace before aligning.')
            return
        if self.pointSelection is None or self.anchorSelection is None:
            self._setLog('Select exactly one point and one anchor before aligning.')
            return
        if self.pointSelection['glyphName'] != self.anchorSelection['glyphName']:
            self._setLog(
                f'Blocked: point glyph {self.pointSelection["glyphName"]!r} does not match '
                f'anchor glyph {self.anchorSelection["glyphName"]!r}.'
            )
            return

        valid = []
        errors = []
        for path in self.sourcePaths:
            label = os.path.basename(path) if path else '(unresolved source)'
            if not path or not os.path.exists(path):
                errors.append(f'{label}: UFO path does not exist')
                continue
            try:
                font = OpenFont(path, showInterface=False)
                if font is None:
                    raise RuntimeError('font could not be opened')
                objects, error = self._validateSource(path, font)
                if error:
                    errors.append(f'{label}: {error}')
                else:
                    valid.append((path, font, objects))
            except Exception as error:
                errors.append(f'{label}: {error}')

        if errors:
            self._setLog(
                f'Blocked: checked {len(self.sourcePaths)} source(s); '
                f'{len(errors)} failed validation. No sources were modified.\n'
                + '\n'.join(f'• {error}' for error in errors)
            )
            return

        modified = []
        saveErrors = []
        for path, font, objects in valid:
            glyph, sourcePoint, targetAnchor = objects
            try:
                glyph.prepareUndo('align anchor to point across designspace')
                targetAnchor.x = sourcePoint.x
                targetAnchor.y = sourcePoint.y
                glyph.changed()
                glyph.performUndo()
                font.save()
                modified.append(os.path.basename(path))
            except Exception as error:
                saveErrors.append(f'{os.path.basename(path)}: {error}')

        message = (
            f'Checked {len(self.sourcePaths)} source(s). '
            f'Modified and saved {len(modified)} of {len(self.sourcePaths)} source(s).'
        )
        if saveErrors:
            message += '\nErrors:\n' + '\n'.join(f'• {error}' for error in saveErrors)
        else:
            message += '\nModified: ' + ', '.join(modified)
        self._setLog(message)


if __name__ == '__main__':
    AnchorAlignerController()
