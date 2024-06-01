import pathlib
import math
from fontTools.pens.pointPen import GuessSmoothPointPen
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
        sourceBorder=(0, 0, 0, 0.25)
    ),
    dark=dict(
        background=(0, 0, 0, 1),
        fill=(1, 1, 1, 1),
        sourceBorder=(1, 1, 1, 0.25)
    ),
)

itemPointSize = 100
itemPadding = itemPointSize * 0.1
itemSpacing = itemPointSize * 0.1
gridInset = itemPointSize * 0.1


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
            discreteLocation=None,
            axisNames=[],
            xAxisName=None,
            xAxisSettings=dict(
                locations=None,
                steps=5
            ),
            yAxisName=None,
            yAxisSettings=dict(
                locations=None,
                steps=5
            ),
            columnWidthMode="fit",
            xAlignment="center",

            unprocessedGlyphNames=[],
            glyphNames=[],

            showSources=False,

            usePrepolator=True,
            highlightSources=True,
            highlightUnsmooths=True,
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
        columnSettings = settings["xAxisSettings"]
        if columnSettings["locations"]:
            columnLocations = columnSettings["locations"]
        else:
            sortColumnLocations = True
            columnLocations = self._makeAxisSteps(xAxisName, columnSettings["steps"])
        # row count
        sortRowLocations = False
        rowSettings = settings["yAxisSettings"]
        if not yAxisName:
            rowLocations = [0]
        else:
            sortRowLocations = True
            if rowSettings["locations"]:
                rowLocations = rowSettings["locations"]
            else:
                rowLocations = self._makeAxisSteps(yAxisName, rowSettings["steps"])
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
                    cornerRadius=10,
                    # backgroundColor=(1, 0, 0, 0.25)
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
        adjunctGlyphs = set()
        for glyphName in glyphNames:
            sources, unicodes = self.ufoOperator.collectSourcesForGlyph(
                glyphName,
                discreteLocation=discreteLocation,
                decomposeComponents=False,
                asMathGlyph=False
            )
            for source in sources:
                l, g, d = source
                adjunctGlyphs.add(g)
        for glyph in self.adjunctGlyphs:
            self.removeObservedAdjunctObject(glyph)
        for glyph in adjunctGlyphs:
            self.addAdjunctObjectToObserve(glyph)
        self.adjunctGlyphs = adjunctGlyphs

    def updateItems(self):
        gridView = self.gridView
        gridContainer = self.gridContainer
        gridItemContainer = self.gridItemContainer
        settings = self.settings
        glyphNames = settings["glyphNames"]
        discreteLocation = settings["discreteLocation"]
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
            glyph = compileGlyph(
                glyphNames=glyphNames,
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
        minScale = 0.25
        maxScale = 5.0
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
        xAxisNames = settings["axisNames"]
        xAxisIndex = 0
        if settings["xAxisName"] in xAxisNames:
            xAxisIndex = xAxisNames.index(settings["xAxisName"])
        yAxisNames = []
        if len(xAxisNames) > 1:
            yAxisNames = xAxisNames
        yAxisIndex = 0
        if settings["yAxisName"] in yAxisNames:
            yAxisIndex = yAxisNames.index(settings["yAxisName"])
        xAxisSettings = rangeToString(settings["xAxisSettings"])
        yAxisSettings = rangeToString(settings["yAxisSettings"])
        if settings["columnWidthMode"] == "fit":
            columnWidthMode = 0
        else:
            columnWidthMode = 1
        xAlignment = ["left", "center", "right"].index(settings["xAlignment"])
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

        : X Axis:
        (Choose ...)            @xAxisPopUpButton

        : Y Axis:
        (Choose ...)            @yAxisPopUpButton

        : Columns:
        [__]                    @columnsField

        : Rows:
        [__]                    @rowsField

        : Column Widths:
        (X) Fit Content         @columnWidthsRadioButtons
        ( ) Monospace

        : Sources:
        [ ] Insert              @showSourcesCheckbox
        [ ] Highlight           @highlightSourcesCheckbox

        : Alignment:
        ( ) Left                @xAlignmentRadioButtons
        (X) Center
        ( ) Right

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
            xAxisPopUpButton=dict(
                items=xAxisNames,
                selected=xAxisIndex
            ),
            yAxisPopUpButton=dict(
                items=yAxisNames,
                selected=yAxisIndex
            ),
            columnsField=dict(
                value=xAxisSettings
            ),
            rowsField=dict(
                value=yAxisSettings
            ),
            columnWidthsRadioButtons=dict(
                selected=columnWidthMode
            ),
            showSourcesCheckbox=dict(
                value=showSources
            ),
            highlightSourcesCheckbox=dict(
                value=highlightSources
            ),
            xAlignmentRadioButtons=dict(
                selected=xAlignment
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

    def started(self):
        self.w.open()

    def destroy(self):
        self.callback = None

    def contentCallback(self, sender):
        values = self.w.getItemValues()
        settings = self.settings
        settings["glyphNameSuffix"] = self.suffixes[values["textSuffixPopUpButton"]]
        if settings["discreteLocations"]:
            settings["discreteLocation"] = settings["discreteLocations"][values["discreteLocationPopUpButton"]]
        settings["xAxisName"] = settings["axisNames"][values["xAxisPopUpButton"]]
        if len(settings["axisNames"]) > 1:
            settings["yAxisName"] = settings["axisNames"][values["yAxisPopUpButton"]]
        xAxisSettings = parseRangeInput(values["columnsField"])
        if xAxisSettings:
            settings["xAxisSettings"] = xAxisSettings
        yAxisSettings = parseRangeInput(values["rowsField"])
        if yAxisSettings:
            settings["yAxisSettings"] = yAxisSettings
        settings["columnWidthMode"] = ["fit", "mono"][values["columnWidthsRadioButtons"]]
        settings["xAlignment"] = ["left", "center", "right"][values["xAlignmentRadioButtons"]]
        settings["showSources"] = values["showSourcesCheckbox"]
        settings["highlightSources"] = values["highlightSourcesCheckbox"]
        settings["usePrepolator"] = values["usePrepolatorCheckbox"]
        settings["highlightUnsmooths"] = values["highlightUnsmoothsCheckbox"]
        settings["unsmoothThreshold"] = values["unsmoothThresholdSlider"]
        self.callback()


def parseRangeInput(text):
    """
    - integer: number of steps
    - space separated numbers: locations
    """
    data = dict(
        steps=None,
        locations=None
    )
    text = text.strip()
    if " " in text:
        try:
            data["locations"] = [float(i.strip()) for i in text.split(" ") if i.strip()]
        except ValueError:
            return None
    else:
        try:
            data["steps"] = int(text)
        except ValueError:
            return None
        if data["steps"] < 2:
            return None
    return data

def rangeToString(data):
    if data["locations"]:
        return " ".join([str(i) for i in data["locations"]])
    return str(data["steps"])

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