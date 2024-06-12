from vanilla import dialogs
from spaceranger import OpenSpaceRanger

paths = dialogs.getFile(
    fileTypes=["designspace"],
    allowsMultipleSelection=False
)
if paths:
    OpenSpaceRanger(
        path=paths[0]
    )