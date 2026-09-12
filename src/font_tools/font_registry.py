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
    return load_font_mapping(data_dir).get(glyph_id)

def glyph_character(data_dir: str, glyph_id: str) -> str:
    cp = glyph_codepoint(data_dir, glyph_id)
    if cp is None:
        return ""
    return chr(cp)

def conlang_font(family: Optional[str] = None, point_size: int = 11):
    from PySide6.QtGui import QFont
    return QFont(family or FONT_FAMILY, point_size)

def apply_conlang_font(widget, data_dir: str, point_size: int = 11) -> None:
    from PySide6.QtGui import QFont
    fam = register_language_font(data_dir) or FONT_FAMILY
    if fam:
        widget.setFont(QFont(fam, point_size))