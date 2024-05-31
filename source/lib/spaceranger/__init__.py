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
collectionInset = 20

debug = __name__ == "__main__"


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

        * MerzCollectionView    @collectionView
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
            margins=(0, 0, 0, 0), #left, bottom, right, top
            size=(500, 500),
            minSize=(400, 400)
        )
        collectionView = self.w.getItem("collectionView")
        collectionView.setInset((collectionInset, collectionInset))

        self.settings = dict(
            discreteLocations=[],
            discreteLocation=None,
            axisNames=[],
            xAxisName=None,
            yAxisName=None,
            sizeMode="fit",
            pointSize=100,
            columnSettings=dict(
                locations=None,
                steps=5
            ),
            rowSettings=dict(
                locations=None,
                steps=5
            ),
            columnWidthMode="fit",
            usePrepolator=True,
            glyphNames=[],
            showSources=False,
            highlightSources=False,
            highlightUnsmooths=False,
            unsmoothTolerance=0.05,
            xAlignment="center"
        )
        self.loadOperatorOptions()
        self.parseTextInput()

    def started(self):
        self.w.open()
        self.buildItems()
        self.populateItems()

    def destroy(self):
        self.clearObservedAdjunctObjects()

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
        for discreteLocation in self.ufoOperator.getDiscreteLocations():
            name = self.ufoOperator.nameLocation(discreteLocation)
            discreteLocations.append(discreteLocation)
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

    def parseTextInput(self):
        glyphNames = splitText(
            self.w.getItemValue("textField"),
            cmap=self.ufoOperator.getCharacterMapping()
        )
        self.settings["glyphNames"] = glyphNames

    def buildItems(self):
        collectionView = self.w.getItem("collectionView")
        settings = self.settings
        # glyph names
        glyphNames = settings["glyphNames"]
        if not glyphNames:
            collectionView.set([])
            return
        currentGlyphName = ""
        glyph = CurrentGlyph()
        if glyph is not None:
            currentGlyphName = glyph.name
        replacements = {"/?" : currentGlyphName}
        glyphNames = [replacements.get(i, i) for i in glyphNames]
        # location
        discreteLocation = settings["discreteLocation"]
        xAxisName = settings["xAxisName"]
        yAxisName = settings["yAxisName"]
        defaultAxes = {}
        for axis in self.ufoOperator.axes:
            if axis.name in (xAxisName, yAxisName):
                continue
            if discreteLocation and axis.name in discreteLocation:
                continue
            defaultAxes[axis.name] = axis.default
        baseLocation = {}
        if discreteLocation:
            baseLocation.update(discreteLocation)
        baseLocation.update(defaultAxes)
        # columns and rows
        columnSettings = settings["columnSettings"]
        columnLocations = []
        if columnSettings["locations"]:
            columnLocations = columnSettings["locations"]
        else:
            columnLocations = self._makeAxisSteps(xAxisName, columnSettings["steps"])
        rowSettings = settings["rowSettings"]
        rowLocations = []
        if rowSettings["locations"]:
            rowLocations = rowSettings["locations"]
        else:
            rowLocations = self._makeAxisSteps(yAxisName, rowSettings["steps"])
        columnLocations = set(columnLocations)
        rowLocations = set(rowLocations)
        sourceLocations = []
        for source in self.ufoOperator.findSourceDescriptorsForDiscreteLocation(discreteLocation):
            sourceLocations.append(source.location)
        if settings["showSources"]:
            for sourceLocation in sourceLocations:
                columnLocations.add(sourceLocation[xAxisName])
                if yAxisName is not None:
                    rowLocations.add(sourceLocation[yAxisName])
        columnLocations = list(sorted(columnLocations))
        rowLocations = list(sorted(rowLocations))
        # adjunct glyphs
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
        # make the items
        items = []
        for rowLocation in rowLocations:
            row = []
            for columnLocation in columnLocations:
                itemLocation = dict(baseLocation)
                itemLocation[xAxisName] = columnLocation
                if yAxisName is not None:
                    itemLocation[yAxisName] = rowLocation
                isSource = itemLocation in sourceLocations
                item = collectionView.makeItem()
                item.getCALayer().setGeometryFlipped_(True)
                item.setSize((50, 50))
                # item.setBackgroundColor((1, 0, 0, 0.5))
                item.setCornerRadius(5)
                if isSource and settings["highlightSources"]:
                    item.setBorderColor(self.sourceBorderColor)
                item.setBorderWidth(1)
                item.setAllowBreakBefore(False)
                item.setForceBreakAfter(False)
                glyphContainer = merz.Base(name="glyphContainer")
                item.appendLayer("glyphContainer", glyphContainer)
                glyphPathLayer = glyphContainer.appendPathSublayer(
                    name="glyphPathLayer",
                    fillColor=self.fillColor
                )
                items.append(item)
                row.append(item)
                item.SRLocation = itemLocation
                item.SRIsSource = isSource
            row[0].setAllowBreakBefore(True)
            row[-1].setForceBreakAfter(True)
        collectionView.set(items)
        collectionView.setAlignment(settings["xAlignment"])

    def _makeAxisSteps(self, axisName, steps):
        axis = self.ufoOperator.getAxis(axisName)
        axisMinimum = axis.minimum
        axisMaximum = axis.maximum
        locations = []
        step = (axisMaximum - axisMinimum) / steps
        for i in range(steps + 1):
            location = axisMinimum + (i * step)
            locations.append(location)
        return locations

    def populateItems(self):
        settings = self.settings
        glyphNames = settings["glyphNames"]
        xAxisName = settings["xAxisName"]
        columnWidthMode = settings["columnWidthMode"]
        sizeMode = settings["sizeMode"]
        collectionView = self.w.getItem("collectionView")
        if not glyphNames:
            return
        desiredSuffix = settings["glyphNameSuffix"]
        suffixToApply = None
        if desiredSuffix == "_none_":
            suffixToApply = None
        elif desiredSuffix == "_auto":
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
        self._runPrepolator(glyphNames)
        items = collectionView.get()
        keyToLocation = {}
        keyToItem = {}
        keyToGlyph = {}
        keyToInfo = {}
        descenders = set()
        upms = None
        fitWidthCalculator = {}
        monoWidthCalculator = set()
        for item in items:
            location = item.SRLocation
            # make info
            info = self.ufoOperator.makeOneInfo(location)
            descenders.add(info.descender)
            upm = info.unitsPerEm
            # make glyph
            compiledGlyph = RGlyph()
            compiledGlyph.width = 0
            for glyphName in glyphNames:
                if glyphName in self.incompatibleGlyphs:
                    continue
                compiledGlyph = RGlyph()
                for glyphName in glyphNames:
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
            l = location[xAxisName]
            if l not in fitWidthCalculator:
                fitWidthCalculator[l] = set()
            columnWidth = compiledGlyph.width
            fitWidthCalculator[l].add(columnWidth)
            monoWidthCalculator.add(columnWidth)
            key = frozenset(location.items())
            keyToLocation[key] = location
            keyToItem[key] = item
            keyToGlyph[key] = compiledGlyph
            keyToInfo[key] = info
        # update the collection scale
        itemPadding = upm * 0.1
        columnCount = len(fitWidthCalculator)
        if columnWidthMode == "fit":
            locationToWidth = {}
            for xLocation, glyphWidths in fitWidthCalculator.items():
                locationToWidth[xLocation] = max(glyphWidths) + (itemPadding * 2)
            self.widestRow = sum(locationToWidth.values())
        else:
            columnWidth = max(monoWidthCalculator) + (itemPadding * 2)
            self.widestRow = columnWidth * len(fitWidthCalculator)
        settings["itemHeight"] = itemHeight = upm + (itemPadding * 2)
        settings["upm"] = upm
        self.updateCollectionViewScale()
        descender = min(descenders)
        # populate the items
        for key, item in keyToItem.items():
            glyph = keyToGlyph[key]
            location = keyToLocation[key]
            if columnWidthMode == "fit":
                columnWidth = locationToWidth[location[xAxisName]]
            item.setSize((columnWidth, itemHeight))
            container = item.getLayer("glyphContainer")
            pathLayer = container.getSublayer("glyphPathLayer")
            pathYOffset = itemPadding - descender
            pathXOffset = (columnWidth - glyph.width) / 2
            with container.propertyGroup():
                container.setSize(("width", "height"))
            with pathLayer.propertyGroup():
                pathLayer.setPath(glyph.getRepresentation("merz.CGPath"))
                pathLayer.setPosition((pathXOffset, pathYOffset))
        scale = collectionView.getScale()
        collectionView.set(items)

    def updateCollectionViewScale(self, reflow=False):
        collectionView = self.w.getItem("collectionView")
        settings = self.settings
        if settings["sizeMode"] == "fit":
            widestRow = self.widestRow
            documentWidth = collectionView.getNSScrollView().documentVisibleRect().size.width
            documentWidth -= collectionInset * 2
            scale = documentWidth / widestRow
        else:
            scale = settings["pointSize"] / settings["upm"]
        collectionView.setScale(scale)
        collectionView.setLineHeight(settings["itemHeight"] * scale)

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

    # Post-Processing

    # Text

    def textFieldCallback(self, sender):
        self.parseTextInput()
        self.buildItems()
        self.populateItems()

    # Settings

    def settingsButtonCallback(self, sender):
        SpaceRangerGridSettingsWindowController(
            parent=sender,
            settings=self.settings,
            ufoOperator=self.ufoOperator,
            callback=self._settingsPopoverCallback,
        )

    def _settingsPopoverCallback(self):
        self.buildItems()
        self.populateItems()

    # RoboFont Observations

    def roboFontAppearanceChanged(self, info):
        self.loadColors()
        self.buildItems()
        self.populateItems()

    def roboFontDidSwitchCurrentGlyph(self, info):
        self.parseTextInput()
        self.buildItems()
        self.populateItems()

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

    # Glyph Observations

    def adjunctGlyphDidChangeOutline(self, info):
        self.populateItems()

    def adjunctGlyphDidChangeMetrics(self, info):
        self.buildItems()
        self.populateItems()

    # Window Observations

    def windowDidResize(self, sender):
        self.updateCollectionViewScale()


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
        if settings["sizeMode"] == "fit":
            sizeMode = 0
        else:
            sizeMode = 1
        pointSize = settings["pointSize"]
        columnSettings = rangeToString(settings["columnSettings"])
        rowSettings = rangeToString(settings["rowSettings"])
        if settings["columnWidthMode"] == "fit":
            columnWidthMode = 0
        else:
            columnWidthMode = 1
        xAlignment = ["left", "center", "right"].index(settings["xAlignment"])
        usePrepolator = settings["usePrepolator"]
        showSources = settings["showSources"]
        highlightSources = settings["highlightSources"]
        highlightUnsmooths = settings["highlightUnsmooths"]
        unsmoothTolerance = settings["unsmoothTolerance"]
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

        : Size:
        ( ) Fit                 @sizeRadioButtons
        (X) Point Size
        :
        [__](±)                 @pointSizeField

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
        : Unsmooth Tolerance:
        ---X--- 123             @unsmoothToleranceSlider
        """
        numberFieldWidth = 50
        descriptionData = dict(
            content=dict(
                titleColumnWidth=130,
                itemColumnWidth=200,
            ),
            textSuffixPopUpButton=dict(
                items=suffixOptions,
                selected=suffixIndex
            ),
            sizeRadioButtons=dict(
                selected=sizeMode
            ),
            pointSizeField=dict(
                valueType="integer",
                minValue=10,
                value=pointSize,
                maxValue=500,
                valueIncrement=25,
                textFieldWidth=numberFieldWidth
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
                value=columnSettings
            ),
            rowsField=dict(
                value=rowSettings
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
            usePrepolatorCheckbox=dict(
                value=usePrepolator
            ),
            highlightUnsmoothsCheckbox=dict(
                value=highlightUnsmooths
            ),
            unsmoothToleranceSlider=dict(
                minValue=0,
                maxValue=0.5,
                value=unsmoothTolerance,
                tickMarks=11,
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
        settings["sizeMode"] = ["fit", "size"][values["sizeRadioButtons"]]
        settings["pointSize"] = values["pointSizeField"]
        if settings["discreteLocations"]:
            settings["discreteLocation"] = settings["discreteLocations"][values["discreteLocationPopUpButton"]]
        settings["xAxisName"] = settings["axisNames"][values["xAxisPopUpButton"]]
        if len(settings["axisNames"]) > 1:
            settings["yAxisName"] = settings["axisNames"][values["yAxisPopUpButton"]]
        columnSettings = parseRangeInput(values["columnsField"])
        if columnSettings:
            settings["columnSettings"] = columnSettings
        rowSettings = parseRangeInput(values["rowsField"])
        if rowSettings:
            settings["rowSettings"] = rowSettings
        settings["columnWidthMode"] = ["fit", "mono"][values["columnWidthsRadioButtons"]]
        settings["xAlignment"] = ["left", "center", "right"][values["xAlignmentRadioButtons"]]
        settings["showSources"] = values["showSourcesCheckbox"]
        settings["highlightSources"] = values["highlightSourcesCheckbox"]
        settings["usePrepolator"] = values["usePrepolatorCheckbox"]
        settings["highlightUnsmooths"] = values["highlightUnsmoothsCheckbox"]
        settings["unsmoothTolerance"] = values["unsmoothToleranceSlider"]
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

if __name__ == "__main__":
    SpaceRangerWindowController(ufoOperator=CurrentDesignspace())