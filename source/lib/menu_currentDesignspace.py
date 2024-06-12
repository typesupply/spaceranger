from spaceranger import OpenSpaceRanger
from vanilla.dialogs import message

ufoOperator = CurrentDesignspace()
if ufoOperator is None:
    message(
        messageText="A designspace is not open.",
        informativeText="Please open a designspace and try again."
    )
else:
    OpenSpaceRanger(
        ufoOperator=ufoOperator
    )