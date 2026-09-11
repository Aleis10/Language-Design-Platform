"""
Font export service — builds a TrueType font from all glyphs in a language
and records the PPUA mapping for typing in the Lexicon.

Pipeline:
  glyphs table (svg_data with embedded strokes_meta JSON)
    -> parse VectorStroke objects (glyph_canvas.VectorStroke.from_dict)
    -> font_builder.build_font_from_strokes -> TTF
    -> glyph mapping {ppua_codepoint: glyph_id} saved to .mapping.json
"""
import json
import os
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from ui.components.glyph_canvas import VectorStroke
from font_tools.font_builder import build_font_from_strokes, FONT_FAMILY


@dataclass
class FontExportResult:
    ttf_path: str
    mapping_path: str
    family_name: str
    num_glyphs: int
    mapping: Dict[str, int]  # glyph_id -> codepoint


def _extract_strokes(svg_str: str) -> List[VectorStroke]:
    """Pull VectorStroke objects from a glyph's svg_data (strokes_meta JSON)."""
    if not svg_str:
        return []
    try:
        root = ET.fromstring(svg_str)
        meta = root.find(".//{*}metadata")
        if meta is None:
            meta = root.find(".//metadata")
        if meta is not None and meta.text:
            data = json.loads(meta.text.strip())
            return [VectorStroke.from_dict(item) for item in data]
    except Exception:
        pass
    return []


def export_language_font(
    glyph_rows: List[Dict],
    output_dir: str,
    family: str = FONT_FAMILY,
) -> FontExportResult:
    """
    Build a font from DB glyph rows.

    glyph_rows: list of glyph dicts (from glyph_db.get_all_glyphs) with
                keys: id, name, svg_data
    output_dir: where to write <family>.ttf + <family>.mapping.json
    """
    os.makedirs(output_dir, exist_ok=True)
    strokes_by_name: Dict[str, List[VectorStroke]] = {}
    id_by_name: Dict[str, str] = {}
    name_by_id: Dict[str, str] = {}

    for row in glyph_rows:
        name = row.get("name") or row.get("id") or "glyph"
        strokes = _extract_strokes(row.get("svg_data", ""))
        strokes_by_name[name] = strokes
        id_by_name[name] = row.get("id", name)
        name_by_id[row.get("id", name)] = name

    ttf_path = os.path.join(output_dir, f"{family}.ttf")
    mapping = build_font_from_strokes(strokes_by_name, ttf_path, family=family)

    # mapping: sanitized_glyph_name -> codepoint  (from font_builder)
    # Convert to: glyph_id -> codepoint and save alongside
    by_id: Dict[str, int] = {}
    for name, cp in mapping.items():
        gid = id_by_name.get(name, name)
        by_id[gid] = cp

    mapping_path = os.path.join(output_dir, f"{family}.mapping.json")
    with open(mapping_path, "w") as f:
        json.dump(
            {
                "family": family,
                "ttf": os.path.basename(ttf_path),
                "glyphs": by_id,
                "notes": "codepoints are in Unicode Private Use Area U+E000+; "
                         "type the character in a field using this font to render the glyph",
            },
            f,
            indent=2,
        )

    return FontExportResult(
        ttf_path=ttf_path,
        mapping_path=mapping_path,
        family_name=family,
        num_glyphs=len(by_id),
        mapping=by_id,
    )