"""Install the RoboFont Tools script menu when RoboFont starts."""
import os
import sys

LIB_PATH = os.path.dirname(os.path.abspath(__file__))
if LIB_PATH not in sys.path:
    sys.path.insert(0, LIB_PATH)

from robofont_tools.menu import install_menu

install_menu()
