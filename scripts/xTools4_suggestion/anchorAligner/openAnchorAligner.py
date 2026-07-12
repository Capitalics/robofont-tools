# menuTitle: Anchor Aligner

from importlib import reload

import xTools4.dialogs.variable.AnchorAligner
from mojo.roboFont import OpenWindow
from xTools4.dialogs.variable.AnchorAligner import AnchorAlignerController


reload(xTools4.dialogs.variable.AnchorAligner)

OpenWindow(AnchorAlignerController)
