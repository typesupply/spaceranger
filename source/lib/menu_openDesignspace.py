from vanilla import dialogs
from spaceranger import SpaceRangerWindowController

paths = dialogs.getFile(
    fileTypes=["designspace"],
    allowsMultipleSelection=False
)
if paths:
    SpaceRangerWindowController(
        designspacePath=paths[0]
    )