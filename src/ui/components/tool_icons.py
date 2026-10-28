import os
from PySide6.QtGui import QIcon

# Loads icons from the project's assets/icons folder (the same folder the sidebar uses).
# The folder is found from this file's own location, so it works wherever the project is stored.
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
ICON_DIR = os.path.join(BASE_DIR, "assets", "icons")


def icon_path(file_name: str) -> str:
    return os.path.join(ICON_DIR, file_name)


def asset_icon(file_name: str) -> QIcon:
    # a missing file gives an empty icon (and a message) instead of an error
    path = icon_path(file_name)
    if not os.path.exists(path):
        print(f"[icons] missing icon file: {path}")
        return QIcon()
    return QIcon(path)
