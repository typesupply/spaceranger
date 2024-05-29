import pathlib
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

class SpaceRangerWindowController(Subscriber, ezui.WindowController):

    debug = False

    def build(self,
            designspacePath=None,
            ufoOperator=None
        ):

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

        self.loadColors()
        startText = "HELLO"
        glyph = CurrentGlyph()
        if glyph is not None:
            startText = "/?"

        content = """
        = HorizontalStack

        * TwoColumnForm         @settingsForm

        > : Text:
        > [__]                  @textField
        > : Size:
        > [_100_](±)            @sizeField
        > : Discrete Location:
        > (Choose...)           @discreteLocationPopUpButton
        > : X Axis:
        > (Choose Axis...)      @xAxisPopUpButton
        > : Y Axis:
        > (Choose Axis...)      @yAxisPopUpButton
        > : Columns:
        > [_10_]                @columnsField
        > : Rows:
        > [_10_]                @rowsField
        > : Column  Widths:
        > (X) Fit               @columnWidthRadioButtons
        > ( ) Uniform
        > :
        > [ ] Show Sources      @showSourcesCheckbox
        > :
        > [X] Highlight Sources @highlightSourcesCheckbox
        > :
        > [X] Use Prepolator    @usePrepolatorCheckbox

        * MerzCollectionView    @collectionView
        """
        numberFieldWidth = 50
        descriptionData = dict(
            settingsForm=dict(
                titleColumnWidth=120,
                itemColumnWidth=200,
                height="fit"
            ),
            textField=dict(
                value=startText
            ),
            sizeField=dict(
                valueType="integer",
                minValue=10,
                value=100,
                maxValue=500,
                valueIncrement=25,
                textFieldWidth=numberFieldWidth
            ),
            discreteLocationPopUpButton=dict(
            ),
            xAxisPopUpButton=dict(
            ),
            yAxisPopUpButton=dict(
            ),
            columnsField=dict(
                value="5"
            ),
            rowsField=dict(
                value="5"
            ),
            usePrepolatorCheckbox=dict(
                value=havePrepolator
            ),
            collectionView=dict(
                backgroundColor=(1, 1, 1, 1),
                width=">=300",
                height=">=300"
            )
        )
        self.w = ezui.EZWindow(
            content=content,
            descriptionData=descriptionData,
            controller=self,
            title=pathlib.Path(self.ufoOperator.path).name,
            minSize=(500, 200)
        )
        self.loadOperatorOptions()
        self.gridSettings = None
        self.buildGrid()

    def started(self):
        self.w.open()

    def loadColors(self):
        if inDarkMode():
            colors = modeColors["dark"]
        else:
            colors = modeColors["light"]
        self.backgroundColor = colors["background"]
        self.fillColor = colors["fill"]
        self.sourceBorderColor = colors["sourceBorder"]

    def loadOperatorOptions(self):
        self.discreteLocations = []
        discreteLocationNames = []
        for discreteLocation in self.ufoOperator.getDiscreteLocations():
            self.discreteLocations.append(discreteLocation)
            name = ", ".join([f"{k}: {v}" for k, v in sorted(discreteLocation.items())])
            discreteLocationNames.append(name)
        popUpButton = self.w.getItem("discreteLocationPopUpButton")
        popUpButton.setItems(discreteLocationNames)
        popUpButton.set(0)
        xAxisNames = []
        xAxisIndex = 0
        for axis in self.ufoOperator.getOrderedContinuousAxes():
            name = axis.name
            xAxisNames.append(name)
        if "width" in xAxisNames:
            xAxisIndex = xAxisNames.index("width")
        popUpButton = self.w.getItem("xAxisPopUpButton")
        popUpButton.setItems(xAxisNames)
        popUpButton.set(xAxisIndex)
        self.axisNames = xAxisNames
        yAxisNames = []
        yAxisIndex = 0
        if len(xAxisNames) > 1:
            yAxisNames = xAxisNames
            yAxisIndex = 1
        if "weight" in yAxisNames:
            yAxisIndex = yAxisNames.index("weight")
        popUpButton = self.w.getItem("yAxisPopUpButton")
        popUpButton.setItems(yAxisNames)
        popUpButton.set(yAxisIndex)

    def settingsFormCallback(self, sender):
        self.buildGrid()

    def buildGrid(self, force=False):
        # get the settings
        values = self.w.getItemValues()
        text = values["textField"]
        glyphNames = splitText(
            text,
            cmap=self.ufoOperator.getCharacterMapping()
        )
        if not glyphNames:
            return
        currentGlyphName = ""
        glyph = CurrentGlyph()
        if glyph is not None:
            currentGlyphName = glyph.name
        replacements = {"/?" : currentGlyphName}
        glyphNames = [replacements.get(i, i) for i in glyphNames]
        fontSize = values["sizeField"]
        itemPadding = min((15, fontSize * 0.05))
        itemSpacing = min((30, fontSize * 0.1))
        itemHeight = fontSize + (itemPadding * 2)
        discreteLocation = None
        if self.discreteLocations:
            discreteLocation = self.discreteLocations[values["discreteLocationPopUpButton"]]
        xAxisName = self.axisNames[values["xAxisPopUpButton"]]
        yAxisName = self.axisNames[values["yAxisPopUpButton"]]
        if len(self.axisNames) <= 1:
            yAxisName = None
        defaultAxes = {}
        for axis in self.ufoOperator.axes:
            if axis.name in (xAxisName, yAxisName):
                continue
            if axis.name in discreteLocation:
                continue
            defaultAxes[axis.name] = axis.default
        xSettings = values["columnsField"]
        xSettings = parseRangeInput(xSettings)
        ySettings = values["rowsField"]
        ySettings = parseRangeInput(ySettings)
        if xSettings is None or ySettings is None:
            # syntax error in field
            return False
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
        columnWidthMode = "fit same".split(" ")[values["columnWidthRadioButtons"]]
        showSources = values["showSourcesCheckbox"]
        highlightSources = values["highlightSourcesCheckbox"]
        usePrepolator = values["usePrepolatorCheckbox"]
        gridSettings = dict(
            glyphNames=glyphNames,
            adjunctGlyphs=adjunctGlyphs,
            fontSize=fontSize,
            itemHeight=itemHeight,
            itemSpacing=itemSpacing,
            itemPadding=itemPadding,
            discreteLocation=discreteLocation,
            defaultAxes=defaultAxes,
            xAxisName=xAxisName,
            yAxisName=yAxisName,
            xSettings=xSettings,
            ySettings=ySettings,
            columnWidthMode=columnWidthMode,
            showSources=showSources,
            highlightSources=highlightSources,
            usePrepolator=usePrepolator
        )
        # compare to existing settings because
        # rebuilding layers is expensive
        if not force and gridSettings == self.gridSettings:
            return
        self.gridSettings = gridSettings
        collectionView = self.w.getItem("collectionView")
        # observe sources
        for glyph in self.adjunctGlyphs:
            self.removeObservedAdjunctObject(glyph)
        for glyph in adjunctGlyphs:
            self.addAdjunctObjectToObserve(glyph)
        self.adjunctGlyphs = adjunctGlyphs
        # build columns
        sourceLocations = []
        for source in self.ufoOperator.findSourceDescriptorsForDiscreteLocation(discreteLocation):
            sourceLocations.append(source.location)
        xLocations = []
        if xSettings["locations"]:
            xLocations = xSettings["locations"]
        else:
            axis = self.ufoOperator.getAxis(xAxisName)
            xAxisMinimum = axis.minimum
            xAxisMaximum = axis.maximum
            steps = xSettings["steps"]
            for x in range(steps):
                xScalar = x / steps
                xLocation = ((xAxisMaximum - xAxisMinimum) * xScalar) + xAxisMinimum
                xLocations.append(xLocation)
        yLocations = []
        if yAxisName is not None:
            if ySettings["locations"]:
                yLocations = ySettings["locations"]
            else:
                axis = self.ufoOperator.getAxis(yAxisName)
                yAxisMinimum = axis.minimum
                yAxisMaximum = axis.maximum
                steps = ySettings["steps"]
                for y in range(steps):
                    yScalar = y / steps
                    yLocation = ((yAxisMaximum - yAxisMinimum) * yScalar) + yAxisMinimum
                    yLocations.append(yLocation)
        allXLocations = set(xLocations)
        allYLocations = set(yLocations)
        for sourceLocation in sourceLocations:
            allXLocations.add(sourceLocation[xAxisName])
            if yAxisName is not None:
                allYLocations.add(sourceLocation[yAxisName])
        allXLocations = list(sorted(allXLocations))
        allYLocations = list(sorted(allYLocations))
        lastColumnIndex = len(allXLocations) - 1
        columns = []
        for columnIndex, xLocation in enumerate(allXLocations):
            columns.append([])
            for yLocation in allYLocations:
                if discreteLocation:
                    location = dict(discreteLocation)
                else:
                    location = {}
                location.update(defaultAxes)
                isSource = False
                if xLocation not in xLocations or yLocation not in yLocations:
                    isSource = True
                location[xAxisName] = xLocation
                location[yAxisName] = yLocation
                isSource = False
                useEmptyGlyph = False
                if location in sourceLocations:
                    isSource = True
                    useEmptyGlyph = False
                elif xLocation not in xLocations and yLocation not in yLocations:
                    useEmptyGlyph = True
                item = collectionView.makeItem()
                item.getCALayer().setGeometryFlipped_(True)
                item.setCornerRadius(5)
                item.setBorderColor(self.sourceBorderColor)
                item.setBorderWidth(0)
                item.setAllowBreakBefore(columnIndex == 0)
                item.setForceBreakAfter(columnIndex == lastColumnIndex)
                glyphContainer = merz.Base(name="glyphContainer")
                item.appendLayer("glyphContainer", glyphContainer)
                glyphPathLayer = glyphContainer.appendPathSublayer(
                    name="glyphPathLayer",
                    fillColor=self.fillColor
                )
                data = dict(
                    location=location,
                    isSource=isSource,
                    useEmptyGlyph=useEmptyGlyph,
                    item=item,
                    glyphContainer=glyphContainer,
                    glyphPathLayer=glyphPathLayer
                )
                columns[-1].append(data)
        self.gridColumns = columns
        # compile the columns into rows
        items = []
        rowCount = len(columns[0])
        for rowIndex in range(rowCount):
            for columnIndex in range(len(columns)):
                data = columns[columnIndex][rowIndex]
                items.append(data["item"])
        # populate the collection view
        collectionView.setLayoutProperties(
            inset=(itemSpacing, itemSpacing),
            lineHeight=itemHeight + itemSpacing,
            spacing=itemSpacing
        )
        collectionView.set(items)
        self.populateGrid()
        return True

    def populateGrid(self):
        self._runPrepolator()
        gridSettings = self.gridSettings
        fontSize = gridSettings["fontSize"]
        columnWidthMode = gridSettings["columnWidthMode"]
        highlightSources = gridSettings["highlightSources"]
        itemPadding = gridSettings["itemPadding"]
        itemHeight = gridSettings["itemHeight"]
        glyphNames = gridSettings["glyphNames"]
        if not glyphNames:
            return
        columnWidths = []
        descenders = set([0])
        upm = 1000
        for column in self.gridColumns:
            widths = []
            for data in column:
                location = data["location"]
                isSource = data["isSource"]
                useEmptyGlyph = data["useEmptyGlyph"]
                item = data["item"]
                info = self.ufoOperator.makeOneInfo(location)
                descenders.add(info.descender)
                upm = info.unitsPerEm
                if useEmptyGlyph:
                    compiledGlyph = RGlyph()
                    compiledGlyph.width = 0
                else:
                    compiledGlyph = RGlyph()
                    for glyphName in glyphNames:
                        if glyphName in self.incompatibleGlyphs:
                            continue
                        mathGlyph = self.ufoOperator.makeOneGlyph(
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
                        mathGlyph.drawPoints(pen)
                        compiledGlyph.appendGlyph(glyph, offset=(compiledGlyph.width, 0))
                        compiledGlyph.width += glyph.width
                widths.append(compiledGlyph.width)
                data["glyph"] = compiledGlyph
                data["info"] = info
            columnWidth = max(widths)
            columnWidths.append(columnWidth)
        # set the widths and paths
        descender = min(descenders)
        scale = fontSize / upm
        glyphUnitsPadding = itemPadding * 1.0 / scale
        if columnWidthMode == "same":
            columnWidth = max(columnWidths)
            columnWidths = [columnWidth for i in columnWidths]
        for columnIndex, column in enumerate(self.gridColumns):
            columnWidth = columnWidths[columnIndex]
            columnWidth *= scale
            columnWidth += itemPadding * 2
            for data in column:
                item = data["item"]
                glyph = data["glyph"]
                container = data["glyphContainer"]
                pathLayer = data["glyphPathLayer"]
                item.setWidth(columnWidth)
                item.setHeight(itemHeight)
                container.setSize((columnWidth, itemHeight))
                path = glyph.getRepresentation("merz.CGPath")
                pathYOffset = glyphUnitsPadding - descender
                pathXOffset = glyphUnitsPadding + ((columnWidth - (glyph.width * scale)) / 2)
                if data["isSource"] and highlightSources:
                    item.setBorderWidth(1)
                else:
                    item.setBorderWidth(0)
                with container.propertyGroup():
                    container.addSublayerScaleTransformation(scale, "glyphScale")
                    container.setSize((columnWidth, itemHeight))
                with pathLayer.propertyGroup():
                    pathLayer.setPath(path)
                    pathLayer.setPosition((pathXOffset, pathYOffset))
        collectionView = self.w.getItem("collectionView")
        items = collectionView.get()
        collectionView.set(items)

    def _runPrepolator(self):
        self.incompatibleGlyphs = set()
        settings = self.gridSettings
        if not settings["usePrepolator"]:
            return
        if self.prepolator is None:
            return
        discreteLocation = settings["discreteLocation"]
        glyphNames = settings["glyphNames"]
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

    # RoboFont Observations

    def roboFontAppearanceChanged(self, info):
        self.loadColors()
        self.buildGrid(force=True)

    def roboFontDidSwitchCurrentGlyph(self, info):
        self.buildGrid(force=True)

    # DSE Observations

    def designspaceEditorSourcesDidChanged(self, info):
        self.buildGrid()

    def designspaceEditorAxesDidChange(self, info):
        self.loadOperatorOptions()
        self.buildGrid()

    # XXX this only works if this object was created
    # with registerRoboFontSubscriber. instead, the
    # source glyphs are observed as adjunct objects.
    #
    # def designspaceEditorSourceGlyphDidChange(self, info):
    #     didRebuild = self.buildGrid()
    #     if not didRebuild:
    #         self.populateGrid()

    # Glyph Observations

    def adjunctGlyphDidChangeOutline(self, info):
        self.populateGrid()

    def adjunctGlyphDidChangeMetrics(self, info):
        self.buildGrid(force=True)


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
        if data["steps"] < 1:
            return None
    return data
