# Digital Keyboard font pipeline
# Stroke rendering → TTF building → Qt font registration

from .typeface_style import DEFAULT_STYLE, RANGES, normalize_style, is_default
from .digital_keyboard import (
    build_font_from_strokes,
    FilledContour,
    FONT_FAMILY,
    PPUA_START,
    PPUA_END,
    export_language_font,
    build_preview_font,
    register_preview_font,
    FontExportResult,
    register_language_font,
    load_font_mapping,
    glyph_codepoint,
    glyph_character,
    conlang_font,
    apply_conlang_font,
    active_conlang_family,
    has_ppua,
    get_fonts_dir,
    track_conlang_widget,
    track_conlang_combo,
    apply_conlang_to_fields,
    install_conlang_delegate,
    ConlangItemDelegate,
    ConlangLabel,
    sync_label_font,
    install_conlang_autofont,
)

__all__ = [
    "build_font_from_strokes", "FilledContour", "FONT_FAMILY", "PPUA_START", "PPUA_END",
    "export_language_font", "build_preview_font", "register_preview_font", "FontExportResult",
    "DEFAULT_STYLE", "RANGES", "normalize_style", "is_default", "register_language_font",
    "load_font_mapping", "glyph_codepoint", "glyph_character", "conlang_font",
    "apply_conlang_font", "active_conlang_family", "has_ppua", "get_fonts_dir",
    "track_conlang_widget", "track_conlang_combo", "apply_conlang_to_fields", 
    "install_conlang_delegate", "ConlangItemDelegate", "ConlangLabel", "sync_label_font", "install_conlang_autofont",
]
