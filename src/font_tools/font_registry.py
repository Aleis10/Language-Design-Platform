"""
Font registry — loads the exported conlang font at app start so logogram
characters (PPUA U+E000+) render in QLineEdit/text fields.

The Glyphs page "Export Font" button writes:
  <data_dir>/fonts/<LanguageName>.ttf
  <data_dir>/fonts/<LanguageName>.mapping.json   {glyph_id: codepoint}
"""
import json
import os
from typing import Dict, Optional

from PySide6.QtGui import QFontDatabase

from font_tools.font_builder import FONT_FAMILY

FONTS_SUBDIR = "fonts"


def get_fonts_dir(data_dir: str) -> str:
    d = os.path.join(data_dir, FONTS_SUBDIR)
    os.makedirs(d, exist_ok=True)
    return d


def register_language_font(data_dir: str) -> Optional[str]:
    """
    Register the first available .ttf in <data_dir>/fonts with Qt.
    Returns the family name if registered, else None.
    """
    fonts_dir = get_fonts_dir(data_dir)
    if not os.path.isdir(fonts_dir):
        return None

    candidates = sorted(
        f for f in os.listdir(fonts_dir)
        if f.lower().endswith((".ttf", ".otf"))
    )
    for fname in candidates:
        path = os.path.join(fonts_dir, fname)
        fid = QFontDatabase.addApplicationFont(path)
        families = QFontDatabase.applicationFontFamilies(fid)
        if families:
            return families[0]
    return None


def load_font_mapping(data_dir: str) -> Dict[str, int]:
    """
    Load {glyph_id: codepoint} for the exported font.
    Returns {} if none exists yet.
    """
    fonts_dir = get_fonts_dir(data_dir)
    if not os.path.isdir(fonts_dir):
        return {}
    for fname in sorted(os.listdir(fonts_dir)):
        if fname.endswith(".mapping.json"):
            try:
                with open(os.path.join(fonts_dir, fname), "r", encoding="utf-8") as f:
                    data = json.load(f)
                glyphs = data.get("glyphs", {})
                return {gid: int(cp) for gid, cp in glyphs.items()}
            except Exception:
                continue
    return {}


def glyph_codepoint(data_dir: str, glyph_id: str) -> Optional[int]:
    """Character (PPUA int) that types this glyph, or None if no font export."""
    return load_font_mapping(data_dir).get(glyph_id)


def glyph_character(data_dir: str, glyph_id: str) -> str:
    cp = glyph_codepoint(data_dir, glyph_id)
    if cp is None:
        return ""
    return chr(cp)


def conlang_font(family: Optional[str] = None, point_size: int = 11):
    """
    QFont using the conlang family (falling back to system font for Latin).
    PPUA chars render as logograms; Latin/ASCII uses Qt's fallback.
    """
    from PySide6.QtGui import QFont
    return QFont(family or FONT_FAMILY, point_size)


def apply_conlang_font(widget, data_dir: str, point_size: int = 11) -> None:
    """
    Set a widget's font to the conlang font if a mapping exists for data_dir.
    Falls back to family via font_registry mapping (does nothing if no export).
    """
    from PySide6.QtGui import QFont
    fam = register_language_font(data_dir) or FONT_FAMILY
    # Only apply if Qt knows the family (registered)
    if fam:
        widget.setFont(QFont(fam, point_size))