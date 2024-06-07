import pathlib
import math
from fontTools.pens.pointPen import GuessSmoothPointPen
from fontTools.designspaceLib import processRules
import merz
import ezui
from mojo.UI import splitText, inDarkMode
from mojo.subscriber import (
    Subscriber,
    registerRoboFontSubscriber
)
from fontParts.world import(
    CurrentGlyph,
    RGlyph
)
try:
    import prepolator
    havePrepolator = True
except ModuleNotFoundError:
    havePrepolator = False


debug = __name__ == "__main__"

modeColors = dict(
    light=dict(
        background=(1, 1, 1, 1),
        fill=(0, 0, 0, 1),
        sourceBorder=(0, 0, 0, 0.25),
        locationTextFill=(1, 1, 1, 1),
        locationTextBackground=(0, 0, 0, 0.9),
    ),
    dark=dict(
        background=(0, 0, 0, 1),
        fill=(1, 1, 1, 1),
        sourceBorder=(1, 1, 1, 0.25),
        locationTextFill=(0, 0, 0, 1),
        locationTextBackground=(1, 1, 1, 0.95),
    ),
)

itemPointSize = 100
itemPadding = itemPointSize * 0.1
itemSpacing = itemPointSize * 0.1
gridInset = itemPointSize * 0.1
itemCornerRadius = itemPointSize * 0.07


# -----------------
# Window Controller
# -----------------

class SpaceRangerWindowController(Subscriber, ezui.WindowController):

    debug = debug

    def build(self,
            designspacePath=None,
            ufoOperator=None
        ):
        self.loadColors()

        if designspacePath is not None:
            ufoOperator = OpenDesignspace(
                path=designspacePath,
                showInterface=False
            )
            ufoOperator.loadFonts()

        self.ufoOperator = ufoOperator
        self.prepolator = None
        if havePrepolator:
            self.prepolator = prepolator.OpenPrepolator(
                ufoOperator=ufoOperator,
                showInterface=False
            )
        self.adjunctGlyphs = set()

        startText = "HELLO"
        glyph = CurrentGlyph()
        if glyph is not None:
            startText = "/?"

        content = """
        * HorizontalStack       @toolbarStack
        > [__]                  @textField
        > ({gearshape})         @settingsButton

        * ScrollingMerzView     @gridView
        """
        numberFieldWidth = 50
        descriptionData = dict(
            content=dict(
                spacing=0
            ),
            toolbarStack=dict(
                margins=(10, 10),
                width="fill",
                distribution="gravity"
            ),
            textField=dict(
                value=startText,
                width="fill"
            ),
            settingsButton=dict(
                gravity="trailing"
            ),
            gridView=dict(
                backgroundColor=(1, 1, 1, 1),
                width=">=300",
                height=">=300",
                delegate=self
            )
        )
        self.w = ezui.EZWindow(
            content=content,
            descriptionData=descriptionData,
            controller=self,
            title=pathlib.Path(self.ufoOperator.path).name,
            margins=(0, 0, 0, 0), #left, bottom, right, top
            size=(500, 500),
            minSize=(400, 400)
        )

        self.gridView = self.w.getItem("gridView")
        self.gridContainer = self.gridView.getMerzContainer()
        self.gridItemContainer = self.gridContainer.appendBaseSublayer(name="gridItemContainer")
        self.gridContainer.setContainerScale(1.0)

        self.settings = dict(
            discreteLocations=[],
            axisNames=[],

            discreteLocation=None,
            applyRules=False,

            xAxisName=None,
            xAxisMode="count", # count | locations
            xAxisCount=5,
            xAxisLocations=[-1000, 0, 1000],

            yAxisName=None,
            yAxisMode="count", # count | locations
            yAxisCount=5,
            yAxisLocations=[-1000, 0, 1000],

            columnWidthMode="fit",

            unprocessedGlyphNames=[],
            glyphNames=[],

            showSources=False,

            usePrepolator=True,
            highlightSources=False,
            highlightUnsmooths=False,
            unsmoothThreshold=2.0,
        )
        self.loadOperatorOptions()
        self.parseTextInput()

    def started(self):
        self.w.open()
        self.buildItems()
        self.prepareItems()
        self.updateItems()

    def destroy(self):
        self.clearObservedAdjunctObjects()

    # Grid

    def parseTextInput(self):
        glyphNames = splitText(
            self.w.getItemValue("textField"),
            cmap=self.ufoOperator.getCharacterMapping()
        )
        self.settings["unprocessedGlyphNames"] = glyphNames

    def buildItems(self):
        gridView = self.gridView
        gridItemContainer = self.gridItemContainer
        settings = self.settings
        discreteLocation = settings["discreteLocation"]
        xAxisName = settings["xAxisName"]
        yAxisName = settings["yAxisName"]
        showSources = settings["showSources"]
        # establish the values for unchosen axes
        defaultAxes = {}
        for axis in self.ufoOperator.getOrderedContinuousAxes():
            name = axis.name
            if axis.name in (xAxisName, yAxisName):
                continue
            defaultAxes[axis.name] = axis.default
        baseLocation = {}
        if discreteLocation:
            baseLocation.update(discreteLocation)
        baseLocation.update(defaultAxes)
        # column count
        sortColumnLocations = False
        if settings["xAxisMode"] == "locations":
            columnLocations = settings["xAxisLocations"]
        else:
            columnLocations = self._makeAxisSteps(xAxisName, settings["xAxisCount"])
        # row count
        sortRowLocations = False
        if not yAxisName:
            rowLocations = [0]
        else:
            if settings["yAxisMode"] == "locations":
                rowLocations = settings["yAxisLocations"]
            else:
                rowLocations = self._makeAxisSteps(yAxisName, settings["yAxisCount"])
        # sources
        sourceLocations = []
        for source in self.ufoOperator.findSourceDescriptorsForDiscreteLocation(discreteLocation):
            location = source.location
            sourceLocations.append(location)
            if showSources:
                columnLocation = location[xAxisName]
                if columnLocation not in columnLocations:
                    columnLocations.append(columnLocation)
                    sortColumnLocations = True
                if yAxisName:
                    rowLocation = location[yAxisName]
                    if rowLocation not in rowLocations:
                        sortRowLocations = True
                        rowLocations.append(rowLocation)
        if sortColumnLocations:
            columnLocations.sort()
        if sortRowLocations:
            rowLocations.sort()
        # make the layers
        self.items = []
        self.itemsInColumns = {}
        self.itemsInRows = {}
        for columnIndex, columnLocation in enumerate(columnLocations):
            if columnIndex not in self.itemsInColumns:
                self.itemsInColumns[columnIndex] = []
            for rowIndex, rowLocation in enumerate(rowLocations):
                if rowIndex not in self.itemsInRows:
                    self.itemsInRows[rowIndex] = []
                location = dict(baseLocation)
                location[xAxisName] = columnLocation
                if yAxisName is not None:
                    location[yAxisName] = rowLocation
                # base
                base = merz.Base(
                    borderWidth=1,
                    cornerRadius=itemCornerRadius,
                    # backgroundColor=(1, 0, 0, 0.25),
                    acceptsHit=True
                )
                base.setInfoValue("location", location)
                base.setInfoValue("isSource", location in sourceLocations)
                base.setInfoValue("columnIndex", columnIndex)
                base.setInfoValue("rowIndex", rowIndex)
                glyphContainerLayer = base.appendBaseSublayer(
                    name="glyphContainer"
                )
                # glyph path
                glyphContainerLayer.appendPathSublayer(
                    name="glyphPath"
                )
                # post-processing
                glyphContainerLayer.appendBaseSublayer(
                    name="unsmoothHighlights"
                )
                # location info
                locationText = "\n".join([f"{k}: {v}" for k, v in sorted(location.items())])
                locationInfoLayer = base.appendTextBoxSublayer(
                    name="locationText",
                    horizontalAlignment="left",
                    cornerRadius=itemCornerRadius,
                    padding=(itemCornerRadius, itemCornerRadius),
                    text=locationText,
                    pointSize=10,
                    figureStyle="tabular",
                    visible=False
                )
                # store
                self.items.append(base)
                self.itemsInColumns[columnIndex].append(base)
                self.itemsInRows[rowIndex].append(base)
        gridItemContainer.clearSublayers()
        for item in self.items:
            gridItemContainer.appendSublayer(item)

    def _makeAxisSteps(self, axisName, steps):
        axis = self.ufoOperator.getAxis(axisName)
        axisMinimum = axis.minimum
        axisMaximum = axis.maximum
        locations = []
        step = (axisMaximum - axisMinimum) / (steps - 1)
        for i in range(steps):
            location = axisMinimum + (i * step)
            locations.append(location)
        return locations

    adjunctGlyphs = None

    def prepareItems(self):
        settings = self.settings
        discreteLocation = settings["discreteLocation"]
        applyRules = settings["applyRules"]
        columnWidthMode = settings["columnWidthMode"]
        unprocessedGlyphNames = settings["unprocessedGlyphNames"]
        desiredSuffix = settings["glyphNameSuffix"]
        # process the glyph names
        currentGlyphName = ""
        glyph = CurrentGlyph()
        if glyph is not None:
            currentGlyphName = glyph.name
        replacements = {"/?" : currentGlyphName}
        glyphNames = [replacements.get(i, i) for i in unprocessedGlyphNames]
        suffixToApply = None
        if desiredSuffix == "_none_":
            suffixToApply = None
        elif desiredSuffix == "_auto_":
            suffixToApply = splitSuffix(currentGlyphName)
        else:
            suffixToApply = desiredSuffix
        if suffixToApply:
            allGlyphNames = self.ufoOperator.glyphNames
            suffixedGlyphNames = []
            for glyphName in glyphNames:
                t = glyphName + "." + suffixToApply
                if t in allGlyphNames:
                    glyphName = t
                suffixedGlyphNames.append(glyphName)
            glyphNames = suffixedGlyphNames
        settings["glyphNames"] = glyphNames
        # observe sources as adjunct glyphs
        if not applyRules:
            processedGlyphNames = glyphNames
        else:
            processedGlyphNames = []
            for item in self.items:
                location = item.getInfoValue("location")
                processedGlyphNames += processRules(self.ufoOperator.rules, location, glyphNames)
            processedGlyphNames = list(set(processedGlyphNames))
        newAdjunctGlyphs = set()
        for glyphName in processedGlyphNames:
            sources, unicodes = self.ufoOperator.collectSourcesForGlyph(
                glyphName,
                discreteLocation=discreteLocation,
                decomposeComponents=False,
                asMathGlyph=False
            )
            for source in sources:
                l, g, d = source
                newAdjunctGlyphs.add(g)
        for glyph in self.adjunctGlyphs:
            if glyph not in newAdjunctGlyphs:
                self.removeObservedAdjunctObject(glyph)
        for glyph in newAdjunctGlyphs:
            if glyph not in self.adjunctGlyphs:
                self.addAdjunctObjectToObserve(glyph)
        self.adjunctGlyphs = newAdjunctGlyphs

    def updateItems(self):
        gridView = self.gridView
        gridContainer = self.gridContainer
        gridItemContainer = self.gridItemContainer
        settings = self.settings
        glyphNames = settings["glyphNames"]
        discreteLocation = settings["discreteLocation"]
        applyRules = settings["applyRules"]
        xAxisName = settings["xAxisName"]
        yAxisName = settings["yAxisName"]
        columnWidthMode = settings["columnWidthMode"]
        highlightSources = settings["highlightSources"]
        checkSmooths = settings["highlightUnsmooths"]
        unsmoothThreshold = settings["unsmoothThreshold"]
        # run prepolator
        self._runPrepolator(glyphNames)
        # build the glyphs in the items
        columnWidthCalculator = {}
        for columnIndex in self.itemsInColumns:
            columnWidthCalculator[columnIndex] = []
        for item in self.items:
            location = item.getInfoValue("location")
            info = self.ufoOperator.makeOneInfo(location)
            if not applyRules:
                processedGlyphNames = glyphNames
            else:
                processedGlyphNames = processRules(self.ufoOperator.rules, location, glyphNames)
            glyph = compileGlyph(
                glyphNames=processedGlyphNames,
                ufoOperator=self.ufoOperator,
                location=location,
                incompatibleGlyphs=self.incompatibleGlyphs,
                smooth=False
            )
            scale = itemPointSize / info.unitsPerEm
            item.setInfoValue("glyph", glyph)
            item.setInfoValue("info", info)
            item.setInfoValue("scale", scale)
            columnIndex = item.getInfoValue("columnIndex")
            columnWidthCalculator[columnIndex].append(glyph.width * scale)
        # measure the columns
        if columnWidthMode == "mono":
            allWidths = []
            for w in columnWidthCalculator.values():
                allWidths += w
            columnWidth = max(w)
            columnWidth += itemPadding * 2
            columnWidths = [columnWidth for i in columnWidthCalculator]
        else:
            columnWidths = []
            for k, v in sorted(columnWidthCalculator.items()):
                columnWidth = max(v)
                columnWidth += itemPadding * 2
                columnWidths.append(columnWidth)
        # post-processing prep
        if checkSmooths:
            defaultLocation = self.ufoOperator.newDefaultLocation(discreteLocation=discreteLocation)
            model = compileGlyph(
                glyphNames=glyphNames,
                ufoOperator=self.ufoOperator,
                location=defaultLocation,
                incompatibleGlyphs=self.incompatibleGlyphs,
                smooth=True
            )
            modelSmooths = []
            for contourIndex, contour in enumerate(model.contours):
                for segmentIndex, segment in enumerate(contour.segments):
                    if segment.smooth:
                        modelSmooths.append((contourIndex, segmentIndex))
        # set the item values
        itemHeight = itemPointSize + (itemPadding * 2)
        for item in self.items:
            columnIndex = item.getInfoValue("columnIndex")
            rowIndex = item.getInfoValue("rowIndex")
            glyph = item.getInfoValue("glyph")
            info = item.getInfoValue("info")
            isSource = item.getInfoValue("isSource")
            scale = item.getInfoValue("scale")
            columnWidth = columnWidths[columnIndex]
            # the view coordinates start at the bottom,
            # so flip the row index to calculate the
            # visually proper y location.
            rowIndex = len(self.itemsInRows) - rowIndex - 1
            x = gridInset
            if columnIndex > 0:
                x += sum(columnWidths[:columnIndex])
            x += itemSpacing * columnIndex
            y = gridInset
            y += itemHeight * rowIndex
            y += itemSpacing * rowIndex
            item.setSize((columnWidth, itemHeight))
            item.setPosition((x, y))
            # update the location text
            locationTextLayer = item.getSublayer("locationText")
            with locationTextLayer.propertyGroup():
                locationTextLayer.setSize((columnWidth, itemHeight))
                locationTextLayer.setFillColor(self.locationTextFillColor)
                locationTextLayer.setBackgroundColor(self.locationTextBackgroundColor)
            # update the source indicator
            if highlightSources and isSource:
                item.setBorderColor(self.sourceBorderColor)
            else:
                item.setBorderColor(None)
            # update the glyph container
            x = (columnWidth - (glyph.width * scale)) / 2
            y = itemPadding
            y += -info.descender * scale
            glyphContainerLayer = item.getSublayer("glyphContainer")
            glyphContainerLayer.addSublayerScaleTransformation(scale, "pointSizeScale")
            glyphContainerLayer.setPosition((x, y))
            # set the path
            glyphPathLayer = glyphContainerLayer.getSublayer("glyphPath")
            with glyphPathLayer.propertyGroup():
                glyphPathLayer.setFillColor(self.fillColor)
                glyphPathLayer.setPath(glyph.getRepresentation("merz.CGPath"))
            # set the unsmooths
            unsmoothHighlightLayer = glyphContainerLayer.getSublayer("unsmoothHighlights")
            unsmoothHighlightLayer.clearSublayers()
            if checkSmooths:
                unsmoothHighlightSize = itemPointSize * 0.1 * (1.0 / scale)
                unsmoothHighlightHalfSize = unsmoothHighlightSize / 2
                for contourIndex, segmentIndex in modelSmooths:
                    contour = glyph.contours[contourIndex]
                    v = getRelativeSmoothness(
                        contour=contour,
                        segmentIndex=segmentIndex,
                        threshold=unsmoothThreshold + smoothToleranceBase
                    )
                    if v:
                        segment = contour.segments[segmentIndex]
                        onCurve = segment.onCurve
                        x = onCurve.x
                        y = onCurve.y
                        unsmoothHighlightLayer.appendOvalSublayer(
                            position=(x-unsmoothHighlightHalfSize, y-unsmoothHighlightHalfSize),
                            size=(unsmoothHighlightSize, unsmoothHighlightSize),
                            fillColor=None,
                            strokeColor=(1, 0, 0, v),
                            strokeWidth=1
                        )
        # set the grid size
        width = gridInset * 2
        width += sum(columnWidths)
        width += itemSpacing * (len(columnWidths) - 1)
        height = gridInset * 2
        height += itemHeight * len(self.itemsInRows)
        height += itemSpacing * (len(self.itemsInRows) - 1)
        gridItemContainer.setSize((width, height))
        # set the container size
        zoomScale = self.gridContainer.getContainerScale()
        gridContainer.setSize((width * zoomScale, height * zoomScale))
        gridView.setMerzViewSize((width * zoomScale, height * zoomScale))
        gridContainer.setBackgroundColor(self.backgroundColor)

    # Pre-Processing

    def _runPrepolator(self, glyphNames):
        self.incompatibleGlyphs = set()
        settings = self.settings
        if not settings["usePrepolator"]:
            return
        if self.prepolator is None:
            return
        discreteLocation = settings["discreteLocation"]
        if not glyphNames:
            return
        availableGlyphNames = self.prepolator.getCompatibilitySpaceGlyphNames(discreteLocation)
        for glyphName in glyphNames:
            if glyphName not in availableGlyphNames:
                continue
            group = self.prepolator.getCompatibilityGroupForGlyphName(glyphName, discreteLocation)
            if group.unresolvableCompatibility:
                self.incompatibleGlyphs.add(glyphName)
            else:
                for glyph in group.glyphs:
                    if group.getGlyphIsIncompatible(glyph):
                        group.matchModel(glyphs=[glyph])
                    elif group.getGlyphConfidence(glyph) <= 0.9:
                        group.matchModel(glyphs=[glyph])

    # Text

    def textFieldCallback(self, sender):
        self.parseTextInput()
        self.prepareItems()
        self.updateItems()

    # Settings

    def loadColors(self):
        if inDarkMode():
            colors = modeColors["dark"]
        else:
            colors = modeColors["light"]
        self.backgroundColor = colors["background"]
        self.fillColor = colors["fill"]
        self.sourceBorderColor = colors["sourceBorder"]
        self.locationTextFillColor = colors["locationTextFill"]
        self.locationTextBackgroundColor = colors["locationTextBackground"]

    def loadOperatorOptions(self):
        # Discrete Location
        discreteLocations = []
        discreteLocation = self.settings["discreteLocation"]
        for dL in self.ufoOperator.getDiscreteLocations():
            name = self.ufoOperator.nameLocation(dL)
            discreteLocations.append(dL)
        # don't allow an unknown discrete axis.
        if discreteLocation not in discreteLocations:
            discreteLocation = None
        if discreteLocation is None and discreteLocations:
            discreteLocation = discreteLocations[0]
        self.settings["discreteLocation"] = discreteLocation
        self.settings["discreteLocations"] = discreteLocations
        # Axes
        axisNames = []
        xAxisName = self.settings["xAxisName"]
        yAxisName = self.settings["yAxisName"]
        for axis in self.ufoOperator.getOrderedContinuousAxes():
            name = axis.name
            axisNames.append(name)
        # don't allow a y axis if there is only one axis.
        if len(axisNames) < 2:
            yAxisName = None
        # an axis name could have changed.
        # don't reference a missing name.
        if xAxisName and xAxisName not in axisNames:
            xAxisName = None
        if yAxisName and yAxisName not in axisNames:
            yAxisName = None
        # pick an initial pair of axes. type designers
        # like to look at x=width, y=weight, so that's
        # the preferred default.
        if xAxisName is None and axisNames:
            xAxisName = axisNames[0]
            if "width" in axisNames:
                xAxisName = "width"
        if yAxisName is None and len(axisNames) > 1:
            if "weight" in axisNames and xAxisName != "weight":
                yAxisName = "weight"
            if yAxisName is None:
                for name in axisNames:
                    if name != xAxisName:
                        yAxisName = name
                        break
        self.settings["axisNames"] = axisNames
        self.settings["xAxisName"] = xAxisName
        self.settings["yAxisName"] = yAxisName
        # Suffixes
        suffixes = set()
        for glyphName in self.ufoOperator.glyphNames:
            suffix = splitSuffix(glyphName)
            if not suffix:
                continue
            suffixes.add(suffix)
        self.settings["glyphNameSuffixes"] = list(sorted(suffixes))
        self.settings["glyphNameSuffix"] = "_none_"

    def settingsButtonCallback(self, sender):
        SpaceRangerGridSettingsWindowController(
            parent=sender,
            settings=self.settings,
            ufoOperator=self.ufoOperator,
            callback=self._settingsPopoverCallback,
        )

    def _settingsPopoverCallback(self):
        self.buildItems()
        self.prepareItems()
        self.updateItems()

    # RoboFont Observations

    def roboFontAppearanceChanged(self, info):
        self.loadColors()
        self.updateItems()

    def roboFontDidSwitchCurrentGlyph(self, info):
        self.prepareItems()
        self.updateItems()

    # DSE Observations

    def designspaceEditorSourcesDidChanged(self, info):
        self.prepareItems()
        self.updateItems()

    def designspaceEditorAxesDidChange(self, info):
        self.buildItems()
        self.prepareItems()
        self.updateItems()

    # XXX this only works if this object was created
    # with registerRoboFontSubscriber. instead, the
    # source glyphs are observed as adjunct objects.
    #
    # def designspaceEditorSourceGlyphDidChange(self, info):

    # Glyph Observations

    def adjunctGlyphDidChangeOutline(self, info):
        self.updateItems()

    def adjunctGlyphDidChangeMetrics(self, info):
        self.updateItems()

    # MerzView Delegate

    def acceptsFirstResponder(self, sender):
        return True

    def magnifyWithEvent(self, sender, event):
        gridView = self.gridView
        gridContainer = self.gridContainer
        gridItemContainer = self.gridItemContainer
        minScale = 0.5
        maxScale = 10.0
        magnificationDelta = event.magnification()
        if magnificationDelta < 0:
            factor = 0.9
        else:
            factor = 1.1
        scale = gridContainer.getContainerScale()
        scale *= factor
        if scale > maxScale:
            scale = maxScale
        elif scale < minScale:
            scale = minScale
        gridContainer.setContainerScale(scale)
        width, height = gridItemContainer.getSize()
        gridView.setMerzViewSize((width * scale, height * scale))

    def _findItemsForEvent(self, event):
        location = event["location"]
        location = self.gridContainer.convertWindowCoordinateToLayerCoordinate(
            point=location,
            view=self.gridView
        )
        hits = self.gridContainer.findSublayersContainingPoint(
            location,
            onlyAcceptsHit=True
        )
        return hits

    def mouseDown(self, sender, event):
        event = merz.unpackEvent(event)
        clickCount = event["clickCount"]
        if clickCount != 2:
            return
        hits = self._findItemsForEvent(event)
        for layer in hits:
            isSource = layer.getInfoValue("isSource")
            location = layer.getInfoValue("location")
            if not isSource:
                continue
            for font, fontLocation in self.ufoOperator.getFonts():
                if location == fontLocation:
                    if not font.hasInterface:
                        font.asFontParts().openInterface()
                    break

    def acceptsMouseMoved(self, sender):
        return True

    def mouseMoved(self, sender, event):
        event = merz.unpackEvent(event)
        if event["modifiers"] == ["option"]:
            hits = self._findItemsForEvent(event)
        else:
            hits = []
        for layer in self.items:
            locationLayer = layer.getSublayer("locationText")
            locationLayer.setVisible(layer in hits)


def compileGlyph(
        glyphNames,
        ufoOperator,
        location,
        incompatibleGlyphs=[],
        smooth=False
    ):
    # remove bogus y axis value
    if None in location:
        location = dict(location)
        del location[None]
    compiledGlyph = RGlyph()
    compiledGlyph.width = 0
    for glyphName in glyphNames:
        if glyphName in incompatibleGlyphs:
            continue
        compiledGlyph = RGlyph()
        for glyphName in glyphNames:
            mathGlyph = ufoOperator.makeOneGlyph(
                glyphName=glyphName,
                location=location
            )
            if mathGlyph is None:
                # operator couldn't make the glyph.
                # skip quietly because it's probably
                # bogus user input like asking for
                # a character that isn't in the fonts.
                continue
            glyph = RGlyph()
            glyph.width = mathGlyph.width
            pen = glyph.getPointPen()
            if smooth:
                pen = GuessSmoothPointPen(pen)
            mathGlyph.extractGlyph(glyph.asDefcon(), pointPen=pen)
            compiledGlyph.appendGlyph(glyph, offset=(compiledGlyph.width, 0))
            compiledGlyph.width += glyph.width
    return compiledGlyph


# ----------------
# Settings Popover
# ----------------

class SpaceRangerGridSettingsWindowController(ezui.WindowController):

    def build(self,
            parent,
            settings={},
            ufoOperator=None,
            callback=None
        ):
        self.settings = settings
        self.callback = callback

        discreteLocationNames = [
            ufoOperator.nameLocation(dL)
            for dL in settings["discreteLocations"]
        ]
        discreteLocationIndex = 0
        if settings["discreteLocation"]:
            discreteLocationIndex = settings["discreteLocations"].index(settings["discreteLocation"])
        applyRules = settings["applyRules"]
        xAxisNames = settings["axisNames"]
        xAxisIndex = 0
        if settings["xAxisName"] in xAxisNames:
            xAxisIndex = xAxisNames.index(settings["xAxisName"])
        xAxisMode = ["count", "locations"].index(settings["xAxisMode"])
        yAxisNames = []
        if len(xAxisNames) > 1:
            yAxisNames = xAxisNames
        yAxisIndex = 0
        if settings["yAxisName"] in yAxisNames:
            yAxisIndex = yAxisNames.index(settings["yAxisName"])
        yAxisMode = ["count", "locations"].index(settings["yAxisMode"])
        if settings["columnWidthMode"] == "fit":
            columnWidthMode = 0
        else:
            columnWidthMode = 1
        usePrepolator = settings["usePrepolator"]
        showSources = settings["showSources"]
        highlightSources = settings["highlightSources"]
        highlightUnsmooths = settings["highlightUnsmooths"]
        unsmoothThreshold = settings["unsmoothThreshold"]
        self.suffixes = ["_none_", "_auto_"]
        suffixOptions = ["None", "Auto"]
        suffixes = settings["glyphNameSuffixes"]
        if suffixes:
            self.suffixes.append("---")
            suffixOptions.append("---")
            for suffix in suffixes:
                self.suffixes.append(suffix)
                suffixOptions.append(suffix)
        suffixIndex = 0
        suffix = settings["glyphNameSuffix"]
        if suffix in self.suffixes:
            suffixIndex = self.suffixes.index(suffix)

        content = """
        = TwoColumnForm

        !§ Text
        : Suffix:
        (Choose ...)            @textSuffixPopUpButton


        !§ Display

        : Discrete Location:
        (Choose ...)            @discreteLocationPopUpButton

        :
        [ ] Apply Rules         @applyRulesCheckbox

        ---

        : X Axis:
        (Choose ...)            @xAxisPopUpButton

        : Mode:
        (X) Count               @xAxisModeRadioButtons
        ( ) Locations

        :
        [__]                    @xAxisValueField

        : Widths:
        (X) Fit Content         @columnWidthsRadioButtons
        ( ) Monospace

        ---

        : Y Axis:
        (Choose ...)            @yAxisPopUpButton

        : Mode:
        (X) Count               @yAxisModeRadioButtons
        ( ) Locations

        :
        [__]                    @yAxisValueField

        ---

        : Sources:
        [ ] Insert              @showSourcesCheckbox
        [ ] Highlight           @highlightSourcesCheckbox

        !§ Pre-Process

        :
        [X] Run Prepolator      @usePrepolatorCheckbox

        !§ Post-Process

        :
        [X] Highlight Unsmooths @highlightUnsmoothsCheckbox
        : Unsmooth Threshold:
        ---X--- 123             @unsmoothThresholdSlider
        """
        numberFieldWidth = 50
        descriptionData = dict(
            content=dict(
                titleColumnWidth=140,
                itemColumnWidth=200,
            ),

            textSuffixPopUpButton=dict(
                items=suffixOptions,
                selected=suffixIndex
            ),

            discreteLocationPopUpButton=dict(
                items=discreteLocationNames,
                selected=discreteLocationIndex
            ),
            applyRulesCheckbox=dict(
                value=applyRules
            ),

            xAxisPopUpButton=dict(
                items=xAxisNames,
                selected=xAxisIndex
            ),
            xAxisModeRadioButtons=dict(
                selected=xAxisMode
            ),
            columnWidthsRadioButtons=dict(
                selected=columnWidthMode
            ),

            yAxisPopUpButton=dict(
                items=yAxisNames,
                selected=yAxisIndex
            ),
            yAxisModeRadioButtons=dict(
                selected=yAxisMode
            ),

            showSourcesCheckbox=dict(
                value=showSources
            ),
            highlightSourcesCheckbox=dict(
                value=highlightSources
            ),

            usePrepolatorCheckbox=dict(
                value=usePrepolator
            ),

            highlightUnsmoothsCheckbox=dict(
                value=highlightUnsmooths
            ),
            unsmoothThresholdSlider=dict(
                minValue=0,
                maxValue=4,
                value=unsmoothThreshold,
                tickMarks=21,
                stopOnTickMarks=True
            ),
        )
        self.w = ezui.EZPopover(
            content=content,
            descriptionData=descriptionData,
            parent=parent,
            controller=self
        )
        self.xAxisModeRadioButtonsCallback(self.w.getItem("xAxisModeRadioButtons"))
        self.yAxisModeRadioButtonsCallback(self.w.getItem("yAxisModeRadioButtons"))

    def started(self):
        self.w.open()

    def destroy(self):
        self.callback = None

    def xAxisModeRadioButtonsCallback(self, sender):
        settings = self.settings
        if sender.get() == 0:
            settings["xAxisMode"] = "count"
            value = str(settings["xAxisCount"])
        else:
            settings["xAxisMode"] = "locations"
            value = " ".join([str(i) for i in settings["xAxisLocations"]])
        self.w.setItemValue("xAxisValueField", value)
        self.contentCallback(sender)

    def xAxisValueFieldCallback(self, sender):
        settings = self.settings
        mode = self.w.getItemValue("xAxisModeRadioButtons")
        value = sender.get()
        if mode == 0:
            value = parseRangeInput(value)
            if value is None:
                return
            settings["xAxisCount"] = value
        else:
            value = parseLocationInput(value)
            if value is None:
                return
            settings["xAxisLocations"] = value
        self.contentCallback(sender)

    def yAxisModeRadioButtonsCallback(self, sender):
        settings = self.settings
        if sender.get() == 0:
            settings["yAxisMode"] = "count"
            value = str(settings["yAxisCount"])
        else:
            settings["yAxisMode"] = "locations"
            value = " ".join([str(i) for i in settings["yAxisLocations"]])
        self.w.setItemValue("yAxisValueField", value)
        self.contentCallback(sender)

    def yAxisValueFieldCallback(self, sender):
        settings = self.settings
        mode = self.w.getItemValue("yAxisModeRadioButtons")
        value = sender.get()
        if mode == 0:
            value = parseRangeInput(value)
            if value is None:
                return
            settings["yAxisCount"] = value
        else:
            value = parseLocationInput(value)
            if value is None:
                return
            settings["yAxisLocations"] = value
        self.contentCallback(sender)

    def contentCallback(self, sender):
        values = self.w.getItemValues()
        settings = self.settings
        settings["glyphNameSuffix"] = self.suffixes[values["textSuffixPopUpButton"]]
        if settings["discreteLocations"]:
            settings["discreteLocation"] = settings["discreteLocations"][values["discreteLocationPopUpButton"]]
        settings["applyRules"] = values["applyRulesCheckbox"]
        settings["xAxisName"] = settings["axisNames"][values["xAxisPopUpButton"]]
        if len(settings["axisNames"]) > 1:
            settings["yAxisName"] = settings["axisNames"][values["yAxisPopUpButton"]]
        settings["columnWidthMode"] = ["fit", "mono"][values["columnWidthsRadioButtons"]]
        settings["showSources"] = values["showSourcesCheckbox"]
        settings["highlightSources"] = values["highlightSourcesCheckbox"]
        settings["usePrepolator"] = values["usePrepolatorCheckbox"]
        settings["highlightUnsmooths"] = values["highlightUnsmoothsCheckbox"]
        settings["unsmoothThreshold"] = values["unsmoothThresholdSlider"]
        self.callback()

def parseRangeInput(value):
    try:
        value = int(value)
        # can't have less than two
        if value < 2:
            value = 2
        # arbitrary "it's going to be slow because that's too many" threshold
        elif value > 20:
            value = 20
        return value
    except ValueError:
        return None

def parseLocationInput(value):
    try:
        value = [float(i.strip()) for i in value.split(" ") if i.strip()]
        return value
    except ValueError:
        return None


def splitSuffix(glyphName):
    if "." not in glyphName:
        return None
    if glyphName.startswith("."):
        return None
    base, suffix  = glyphName.split(".", 1)
    suffix = suffix.strip()
    if not suffix:
        return None
    return suffix


# ---------------------
# Post-Processing Tools
# ---------------------

def calculateAngle(point1, point2, r=None):
    width = point2[0] - point1[0]
    height = point2[1] - point1[1]
    angle = round(math.atan2(height, width) * 180 / math.pi, 3)
    if r is not None:
        angle = round(angle, r)
    return angle

def unwrapPoint(pt):
    return (pt.x, pt.y)

smoothToleranceBase = 0.05

def getRelativeSmoothness(
        contour,
        segmentIndex,
        tolerance=smoothToleranceBase,
        threshold=2
    ):
    segments = list(contour.segments)
    p = segmentIndex - 1
    n = segmentIndex + 1
    if n == len(segments):
        n = 0
    previousSegment = segments[p]
    segment = segments[segmentIndex]
    nextSegment = segments[n]
    inPoints = None
    outPoints = None
    if segment.type == "curve" and nextSegment.type == "curve":
        bcpIn = unwrapPoint(segment.offCurve[1])
        anchor = unwrapPoint(segment.onCurve)
        bcpOut = unwrapPoint(nextSegment.offCurve[0])
        inPoints = (bcpIn, anchor)
        outPoints = (anchor, bcpOut)
    elif segment.type == "curve" and nextSegment.type == "line":
        bcpIn = unwrapPoint(segment.offCurve[1])
        anchor = unwrapPoint(segment.onCurve)
        nextAnchor = unwrapPoint(nextSegment.onCurve)
        inPoints = (bcpIn, anchor)
        outPoints = (anchor, nextAnchor)
    elif segment.type == "line" and nextSegment.type == "curve":
        previousAnchor = unwrapPoint(previousSegment.onCurve)
        anchor = unwrapPoint(segment.onCurve)
        bcpOut = unwrapPoint(nextSegment.offCurve[0])
        inPoints = (previousAnchor, anchor)
        outPoints = (anchor, bcpOut)
    inAngle = calculateAngle(*inPoints)
    outAngle = calculateAngle(*outPoints)
    diff = abs(inAngle - outAngle)
    if diff <= tolerance:
        diff = 0
    elif diff > threshold:
        diff = threshold
    return diff / threshold

if __name__ == "__main__":
    SpaceRangerWindowController(ufoOperator=CurrentDesignspace())