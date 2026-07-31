import os
import sys


LIB_PATH = os.path.dirname(os.path.abspath(__file__))
if LIB_PATH not in sys.path:
    sys.path.insert(0, LIB_PATH)

from workspaceLauncher.menu import install_workspace_launcher_menu


install_workspace_launcher_menu()
