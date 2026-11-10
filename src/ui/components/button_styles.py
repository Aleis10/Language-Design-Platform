from PySide6.QtCore import QSize
from PySide6.QtWidgets import QPushButton

try:
    from ui.components.tool_icons import asset_icon
except ImportError:                      # imported as a package
    from .tool_icons import asset_icon

# One place for the colours of the buttons:
#   primary (blue)   add, create, open, edit
#   success (green)  save, confirm, apply
#   danger  (red)    delete, remove, clear all   (white text)
#   neutral (white)  cancel, back, reset and other quiet actions
BLUE, BLUE_HOVER, BLUE_PRESSED = "#007acc", "#005f9e", "#004d80"
GREEN, GREEN_HOVER, GREEN_PRESSED = "#28a745", "#218838", "#1c7430"
RED, RED_HOVER, RED_PRESSED = "#d9534f", "#c9302c", "#ac2925"
DISABLED_BG, DISABLED_TEXT = "#cfd4da", "#8a9099"

ROLES = ("primary", "success", "danger", "neutral")

_FILLED = {
    "primary": (BLUE, BLUE_HOVER, BLUE_PRESSED),
    "success": (GREEN, GREEN_HOVER, GREEN_PRESSED),
    "danger": (RED, RED_HOVER, RED_PRESSED),
}


def role_stylesheet(role: str, small: bool = False) -> str:
    padding = "3px 10px" if small else "6px 14px"
    size = "font-size: 11px;" if small else ""
    if role == "neutral":
        return f"""
            QPushButton {{
                background-color: #ffffff; color: #333333; border: 1px solid #c8ccd2;
                border-radius: 4px; padding: {padding}; {size}
            }}
            QPushButton:hover {{ background-color: #eef5fc; border-color: {BLUE}; }}
            QPushButton:pressed {{ background-color: #dcebfa; }}
            QPushButton:disabled {{ background-color: #f3f4f6; color: {DISABLED_TEXT}; border-color: #e1e4e8; }}
        """
    base, hover, pressed = _FILLED[role]
    return f"""
        QPushButton {{
            background-color: {base}; color: #ffffff; border: none; border-radius: 4px;
            padding: {padding}; font-weight: bold; {size}
        }}
        QPushButton:hover {{ background-color: {hover}; }}
        QPushButton:pressed {{ background-color: {pressed}; }}
        QPushButton:disabled {{ background-color: {DISABLED_BG}; color: {DISABLED_TEXT}; }}
    """


def set_role(button: QPushButton, role: str, small: bool = False) -> QPushButton:
    """Give a button one of the shared colours. The role is also stored on the button as a property."""
    if role not in ROLES:
        raise ValueError(f"unknown button role: {role}")
    button.setProperty("role", role)
    button.setStyleSheet(role_stylesheet(role, small))
    return button


def set_icon_button(button: QPushButton, icon_file: str, tooltip: str = "", danger: bool = False,
                    size: int = 28) -> QPushButton:
    """A small flat button that shows only an icon from assets/icons (edit.svg, Trash.svg ...).
    A delete button turns red when the mouse is over it."""
    button.setText("")
    button.setIcon(asset_icon(icon_file))
    button.setIconSize(QSize(size - 12, size - 12))
    button.setFixedSize(size, size)
    button.setToolTip(tooltip)
    button.setProperty("role", "icon-danger" if danger else "icon")
    hover = RED if danger else "#e6f0fa"
    button.setStyleSheet(f"""
        QPushButton {{ background: transparent; border: none; border-radius: 4px; padding: 0; }}
        QPushButton:hover {{ background-color: {hover}; }}
        QPushButton:pressed {{ background-color: {RED_PRESSED if danger else '#cfe0f2'}; }}
    """)
    return button
